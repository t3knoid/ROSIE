from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from rosie import audit
from rosie.config import settings
from rosie.documents import SUPPORTED_SUFFIXES, load_document
from rosie.knowledge import KnowledgeBase
from rosie.models import ChatRequest, ChatResponse, Evidence, PublishRequest, Runbook, RunbookDraftRequest
from rosie.publisher import GitRepositoryPublisher
from rosie.runbooks import to_markdown
from rosie.workflow import build_investigation_graph, draft_runbook

app = FastAPI(title=settings.app_name, version="0.1.0")


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()


@lru_cache
def get_investigation_graph():
    return build_investigation_graph(get_knowledge_base())


@lru_cache
def get_publisher() -> GitRepositoryPublisher:
    return GitRepositoryPublisher(settings.repository_path)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "rosie"}


@app.post("/api/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    kind: str = Form("document"),
) -> dict[str, str | int]:
    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload Markdown, HTML, PDF, DOCX, ODT, or plain text")
    if kind not in {"document", "runbook"}:
        raise HTTPException(status_code=400, detail="kind must be 'document' or 'runbook'")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Documents must be 10 MB or smaller")
    try:
        text = load_document(filename, content)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not text.strip():
        raise HTTPException(status_code=422, detail="No text could be extracted from the document")
    count = get_knowledge_base().ingest(text, filename, kind)
    audit.record("document_ingested", {"source": filename, "kind": kind, "chunks": count})
    return {"source": filename, "kind": kind, "chunks": count}


@app.post("/api/ingest/local")
def ingest_local_documents() -> dict[str, int]:
    root = Path(settings.docs_path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Documentation directory not found: {root}")
    documents = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES]
    total = 0
    for path in documents:
        try:
            text = load_document(path.name, path.read_bytes())
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail=f"Could not read {path}: {error}") from error
        kind = "runbook" if "runbook" in path.name.casefold() or "runbooks" in path.parts else "document"
        total += get_knowledge_base().ingest(text, str(path.relative_to(root)), kind)
    audit.record("local_documents_ingested", {"directory": str(root), "files": len(documents), "chunks": total})
    return {"files": len(documents), "chunks": total}


@app.get("/api/search")
def search_documents(q: str, kind: str | None = None, limit: int = 5) -> list[Evidence]:
    if kind not in {None, "document", "runbook"}:
        raise HTTPException(status_code=400, detail="kind must be 'document' or 'runbook'")
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 20")
    results = get_knowledge_base().search(q, kind=kind, limit=limit)
    audit.record("documentation_searched", {"query": q, "kind": kind, "result_count": len(results)})
    return [Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"])) for item in results]


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = get_investigation_graph().invoke({"question": request.question})
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"ROSIE could not reach its Ollama or Qdrant service: {error}") from error
    evidence = [
        Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"]))
        for item in result.get("evidence", [])
    ]
    audit.record(
        "question_investigated",
        {"question": request.question, "evidence": [item.source for item in evidence], "runbook_gap": result.get("runbook_gap", True)},
    )
    return ChatResponse(answer=result["answer"], evidence=evidence, runbook_gap=result.get("runbook_gap", True))


@app.get("/api/runbooks/gap")
def identify_runbook_gap(q: str) -> dict[str, bool | str | list[Evidence]]:
    results = get_knowledge_base().search(q, kind="runbook", limit=3)
    evidence = [
        Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"]))
        for item in results
    ]
    gap = not evidence
    audit.record("runbook_gap_checked", {"query": q, "gap": gap, "evidence": [item.source for item in evidence]})
    assessment = "No matching runbook is indexed." if gap else "Potentially relevant runbook evidence found; review for completeness."
    return {"gap": gap, "assessment": assessment, "evidence": evidence}


@app.post("/api/runbooks/draft", response_model=Runbook)
def create_runbook_draft(request: RunbookDraftRequest) -> Runbook:
    evidence = get_knowledge_base().search(request.incident, limit=6)
    try:
        runbook = draft_runbook(request.incident, evidence)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Could not generate a runbook draft with Ollama: {error}") from error
    audit.record("runbook_drafted", {"title": runbook.title, "evidence": [item["source"] for item in evidence]})
    return runbook


@app.post("/api/runbooks/export", response_class=PlainTextResponse)
def export_runbook(runbook: Runbook) -> PlainTextResponse:
    audit.record("runbook_exported", {"title": runbook.title})
    return PlainTextResponse(
        to_markdown(runbook),
        headers={"Content-Disposition": f'attachment; filename="{runbook.title[:80]}.md"'},
    )


@app.post("/api/runbooks/publish")
def publish_runbook(request: PublishRequest) -> dict[str, str]:
    try:
        path = get_publisher().create(request.path, request.runbook)
    except (ValueError, FileExistsError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    audit.record("runbook_published", {"path": str(path)})
    return {"path": str(path), "status": "written; review and commit with Git"}
