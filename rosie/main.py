import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
import logging
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from rosie import audit
from rosie.config import settings
from rosie.documents import SUPPORTED_SUFFIXES, document_passages, passages, runbook_index_passages
from rosie.knowledge import KnowledgeBase
from rosie.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    Evidence,
    HealthResponse,
    IngestResult,
    LocalIngestResult,
    PublishRequest,
    PublishResult,
    Runbook,
    RunbookDraftRequest,
    RunbookGapResult,
    SourceSyncFailure,
    SourceSyncResult,
    SourceSyncStatus,
)
from rosie.publisher import GitRepositoryPublisher
from rosie.rendering import markdown_to_safe_html
from rosie.runbooks import to_markdown
from rosie.web_sources import WebPage, crawl_html_source
from rosie.workflow import build_investigation_graph, draft_runbook
from rosie.gpu_status import router as gpu_router

def initial_sync_status() -> dict[str, object]:
    return {"ready": False, "syncing": False, "last_success": None, "error": None, "result": None}


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.source_sync = initial_sync_status()
    stopping = asyncio.Event()

    async def startup_sync():
        while not application.state.source_sync["ready"]:
            try:
                await asyncio.to_thread(ingest_configured_sources)
            except Exception:
                logging.getLogger(__name__).exception("Startup source sync failed")
            if application.state.source_sync["ready"] or stopping.is_set():
                return
            try:
                await asyncio.wait_for(stopping.wait(), timeout=30)
                return
            except TimeoutError:
                pass

    task = asyncio.create_task(startup_sync())
    try:
        yield
    finally:
        stopping.set()
        await task


API_DESCRIPTION = """
ROSIE (Root-cause Observation, SRE Incident Examiner) answers operations questions from
indexed documentation and runbooks. Version 0.1 is documentation-only: it never connects
to or changes infrastructure.

**Typical flow**

1. Content is indexed. The configured documentation and runbook sites sync automatically at
   startup; `POST /api/ingest/sources` re-syncs them, and `POST /api/ingest` or
   `POST /api/ingest/local` add files.
2. Poll `GET /api/ingest/sources/status` until `ready` is `true`.
3. Ask questions with `POST /api/chat`, or retrieve evidence alone with `GET /api/search`.
4. Draft, export, and publish runbooks with the `/api/runbooks` endpoints.

**Dependencies:** indexing and search need the llama.cpp embedding server and Qdrant;
chat and runbook drafts also need the llama.cpp chat server. `/api/chat` returns 503 if
any of them is unreachable, and `/api/runbooks/draft` returns 503 if the chat model fails;
other endpoints return 500 when a service is down.

**Security:** there is no authentication. Expose this port only on trusted networks.
Every ingest, search, question, and runbook operation is written to the JSON Lines audit log.
"""

OPENAPI_TAGS = [
    {"name": "Health", "description": "Liveness and read-only hardware status."},
    {
        "name": "Ingestion",
        "description": "Add content to the knowledge base. Each passage is stored as a `document` or a `runbook`.",
    },
    {"name": "Investigation", "description": "Search indexed content and ask ROSIE questions."},
    {
        "name": "Runbooks",
        "description": "Check runbook coverage, and draft, export, and publish runbooks. Nothing is committed to Git automatically.",
    },
]

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
app.state.source_sync = initial_sync_status()
source_sync_lock = Lock()
app.include_router(gpu_router)

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


@app.get("/health", tags=["Health"], summary="Liveness check", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """Report that the API process is running.

    This does not check llama.cpp, Qdrant, or source sync readiness; use
    `GET /api/ingest/sources/status` for readiness.
    """
    return {"status": "ok", "service": "rosie"}


@app.post(
    "/api/ingest",
    tags=["Ingestion"],
    summary="Upload and index one file",
    response_model=IngestResult,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid `kind`, or the file could not be parsed."},
        413: {"model": ErrorResponse, "description": "The file is larger than 10 MB."},
        415: {"model": ErrorResponse, "description": "Unsupported file type."},
        422: {"model": ErrorResponse, "description": "No text could be extracted from the file."},
    },
)
async def ingest_document(
    file: UploadFile = File(
        ...,
        description="Markdown (`.md`, `.markdown`), HTML (`.html`, `.htm`), PDF, DOCX, ODT, or plain text (`.txt`); 10 MB maximum.",
    ),
    kind: str = Form(
        "document",
        description="Store the content as `document` or `runbook`.",
        json_schema_extra={"enum": ["document", "runbook"]},
    ),
) -> dict[str, str | int]:
    """Extract text from an uploaded file, split it into passages, and index them.

    The file is stored under its base file name. Uploading a file with the same name and
    `kind` replaces the earlier version's passages; unchanged passages are not re-embedded.

    Example: `curl -F "file=@disk-full.md" -F "kind=runbook" http://localhost:8001/api/ingest`
    """
    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload Markdown, HTML, PDF, DOCX, ODT, or plain text")
    if kind not in {"document", "runbook"}:
        raise HTTPException(status_code=400, detail="kind must be 'document' or 'runbook'")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Documents must be 10 MB or smaller")
    # Parsing, embedding, and Qdrant writes block; keep them off the event loop.
    return await asyncio.to_thread(_ingest_uploaded_document, filename, content, kind)


def _ingest_uploaded_document(filename: str, content: bytes, kind: str) -> dict[str, str | int]:
    try:
        document = document_passages(filename, content)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not document:
        raise HTTPException(status_code=422, detail="No text could be extracted from the document")
    count = get_knowledge_base().ingest(document, filename, kind)
    audit.record("document_ingested", {"source": filename, "kind": kind, "chunks": count})
    return {"source": filename, "kind": kind, "chunks": count}


@app.post(
    "/api/ingest/local",
    tags=["Ingestion"],
    summary="Index the local knowledge directory",
    response_model=LocalIngestResult,
    responses={
        400: {"model": ErrorResponse, "description": "A file could not be parsed. Indexing stops at that file."},
        404: {"model": ErrorResponse, "description": "The configured directory does not exist."},
    },
)
def ingest_local_documents() -> dict[str, int]:
    """Index every supported file under `DOCS_PATH` (`/app/knowledge` in Docker Compose).

    A file is stored as a `runbook` if its name contains "runbook" or it is inside a
    `runbooks` directory; otherwise it is a `document`. Each file is stored under its path
    relative to the directory. Files deleted from the directory are not removed from the index.
    """
    root = Path(settings.docs_path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Documentation directory not found: {root}")
    documents = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES]
    total = 0
    for path in documents:
        try:
            document = document_passages(path.name, path.read_bytes())
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail=f"Could not read {path}: {error}") from error
        kind = "runbook" if "runbook" in path.name.casefold() or "runbooks" in path.parts else "document"
        total += get_knowledge_base().ingest(document, str(path.relative_to(root)), kind)
    audit.record("local_documents_ingested", {"directory": str(root), "files": len(documents), "chunks": total})
    return {"files": len(documents), "chunks": total}


def _ingest_configured_sources() -> dict[str, object]:
    sources = [
        (settings.documentation_source_url, "document"),
        (settings.runbook_source_url, "runbook"),
    ]
    page_count = 0
    chunk_count = 0
    pages_by_kind = {"document": 0, "runbook": 0}
    errors: list[str] = []
    knowledge = get_knowledge_base()
    pages: dict[str, tuple[WebPage, str]] = {}
    index: WebPage | None = None
    index_summary: list[str] = []

    for source_url, kind in sources:
        try:
            result = crawl_html_source(
                source_url,
                max_pages=settings.web_source_max_pages,
                timeout_seconds=settings.web_source_timeout_seconds,
                max_page_bytes=settings.web_source_max_page_bytes,
                runbook_index=kind == "runbook",
            )
        except ValueError as error:
            errors.append(f"{source_url}: {error}")
            continue
        errors.extend(result.errors)
        for page in result.pages:
            pages[page.url] = (page, kind)
        if result.index_page:
            # The runbook index is a list of runbooks, not a runbook. Store it as a document,
            # led by a passage saying what the page is.
            index = result.index_page
            pages[index.url] = (index, "document")
            titles = {page.url: page.title for page in result.pages}
            index_summary = runbook_index_passages(
                index.title,
                index.url,
                [(link.heading, link.title or titles.get(link.url) or link.url) for link in result.index_links],
            )

    for page, kind in pages.values():
        sections = list(page.sections) or [((), page.text)]
        page_passages = passages(page.title, sections)
        if index and page is index:
            page_passages = index_summary + page_passages
        chunk_count += knowledge.ingest(page_passages, page.url, kind, replace_kind=True)
        page_count += 1
        pages_by_kind[kind] += 1
    # Earlier versions indexed a site's /index.html separately from its root page.
    knowledge.delete_sources([
        url + alias for url in pages if urlsplit(url).path == "/" for alias in ("index.html", "index.htm")
    ])

    if not page_count:
        raise HTTPException(
            status_code=502,
            detail={"message": "No configured documentation pages could be fetched.", "errors": errors},
        )
    audit.record(
        "web_sources_ingested",
        {"pages": page_count, "chunks": chunk_count, "pages_by_kind": pages_by_kind, "errors": errors},
    )
    return {"pages": page_count, "chunks": chunk_count, "pages_by_kind": pages_by_kind, "errors": errors}


@app.get(
    "/api/ingest/sources/status",
    tags=["Ingestion"],
    summary="Get source sync status and readiness",
    response_model=SourceSyncStatus,
)
def source_sync_status() -> dict[str, object]:
    """Report whether ROSIE is ready to answer questions, and the state of the latest sync.

    `ready` becomes `true` after the first sync that finishes with no errors and then stays
    `true` until the API restarts. The status is held in memory and resets on restart.
    """
    return app.state.source_sync


@app.post(
    "/api/ingest/sources",
    tags=["Ingestion"],
    summary="Sync the configured documentation and runbook sites",
    response_model=SourceSyncResult,
    responses={
        409: {"model": ErrorResponse, "description": "A sync is already running."},
        502: {"model": SourceSyncFailure, "description": "No pages could be fetched from either source."},
    },
)
def ingest_configured_sources() -> dict[str, object]:
    """Fetch and index pages from `DOCUMENTATION_SOURCE_URL` and `RUNBOOK_SOURCE_URL`.

    - **Documentation:** crawled recursively from the start page.
    - **Runbooks:** only pages linked directly from the runbook index's main content
      (not its header, navigation, or footer). The index page itself is not indexed.
    - Only same-origin HTTPS pages whose paths end in `.html` or `.htm` (or are `/`) are followed.
      Redirects are not followed. Each source is limited to `WEB_SOURCE_MAX_PAGES` pages and each
      page to `WEB_SOURCE_MAX_PAGE_BYTES`.
    - A URL found by both crawls is stored once, as a runbook.
    - Unchanged pages are not re-embedded. Pages no longer reachable are left in the index.

    The request blocks until the sync finishes, which can take several minutes. A 200 response
    with a non-empty `errors` list is a partial failure: the pages listed were skipped and
    `ready` is not set.
    """
    if not source_sync_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Source sync is already running")
    previous = app.state.source_sync
    app.state.source_sync = {**previous, "syncing": True, "error": None}
    try:
        result = _ingest_configured_sources()
        errors = result["errors"]
        app.state.source_sync = {
            "ready": previous["ready"] or not errors,
            "syncing": False,
            "last_success": previous["last_success"] if errors else datetime.now(timezone.utc).isoformat(),
            "error": f"Source sync reported partial failures: {errors}" if errors else None,
            "result": result,
        }
        return result
    except Exception as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        app.state.source_sync = {**previous, "syncing": False, "error": str(detail)}
        raise
    finally:
        source_sync_lock.release()


@app.get(
    "/api/search",
    tags=["Investigation"],
    summary="Search indexed content",
    response_model=list[Evidence],
    responses={400: {"model": ErrorResponse, "description": "Invalid `kind` or `limit`."}},
)
def search_documents(
    q: str = Query(description="Text to search for. Matching is by meaning, not exact words.", examples=["disk full"]),
    kind: str | None = Query(
        None,
        description="Return only `document` or only `runbook` passages. Omit to search both.",
        json_schema_extra={"enum": ["document", "runbook"]},
    ),
    limit: int = Query(5, description="Maximum number of passages to return, from 1 to 20."),
) -> list[Evidence]:
    """Return the passages most similar to the query, best match first.

    Only passages scoring at least `RELEVANCE_THRESHOLD` are returned, so the list can be
    empty. This does not call the chat model.
    """
    if kind not in {None, "document", "runbook"}:
        raise HTTPException(status_code=400, detail="kind must be 'document' or 'runbook'")
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 20")
    results = get_knowledge_base().search(q, kind=kind, limit=limit)
    audit.record("documentation_searched", {"query": q, "kind": kind, "result_count": len(results)})
    return [Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"])) for item in results]


@app.post(
    "/api/chat",
    tags=["Investigation"],
    summary="Ask ROSIE a question",
    response_model=ChatResponse,
    responses={503: {"model": ErrorResponse, "description": "Sources have not finished syncing, or llama.cpp or Qdrant could not be reached."}},
)
def chat(request: ChatRequest) -> ChatResponse:
    """Investigate a question using indexed documentation and runbooks.

    ROSIE retrieves the best-matching passages (`CHAT_EVIDENCE_LIMIT`, default 2), adds the
    best-matching runbook passage if one matches and is not already included, and asks the
    chat model for an answer based on that evidence. Each call is independent; earlier questions are not remembered.

    Returns 503 until `GET /api/ingest/sources/status` reports `ready`. Answers usually take
    several seconds to a few minutes depending on the GPU.
    """
    if not app.state.source_sync["ready"]:
        raise HTTPException(status_code=503, detail="Sources must finish syncing before investigating")
    started_at = perf_counter()
    try:
        result = get_investigation_graph().invoke({"question": request.question})
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"ROSIE could not reach its llama.cpp or Qdrant service: {error}") from error
    evidence = [
        Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"]))
        for item in result.get("evidence", [])
    ]
    audit.record(
        "question_investigated",
        {"question": request.question, "evidence": [item.source for item in evidence], "runbook_gap": result.get("runbook_gap", True)},
    )
    duration_seconds = round(perf_counter() - started_at, 3)
    return ChatResponse(
        answer=result["answer"],
        answer_html=markdown_to_safe_html(result["answer"]),
        evidence=evidence,
        runbook_gap=result.get("runbook_gap", True),
        duration_seconds=duration_seconds,
    )


@app.get(
    "/api/runbooks/gap",
    tags=["Runbooks"],
    summary="Check whether a runbook covers a topic",
    response_model=RunbookGapResult,
)
def identify_runbook_gap(
    q: str = Query(description="The incident or task to look for a runbook about.", examples=["certificate expired"]),
) -> dict[str, bool | str | list[Evidence]]:
    """Search only runbook passages and report a gap if none match.

    A match means a runbook is related, not that it fully covers the topic; review the
    returned evidence. This does not call the chat model.
    """
    results = get_knowledge_base().search(q, kind="runbook", limit=3)
    evidence = [
        Evidence(source=str(item["source"]), kind=str(item["kind"]), text=str(item["text"]), score=float(item["score"]))
        for item in results
    ]
    gap = not evidence
    audit.record("runbook_gap_checked", {"query": q, "gap": gap, "evidence": [item.source for item in evidence]})
    assessment = "No matching runbook is indexed." if gap else "Potentially relevant runbook evidence found; review for completeness."
    return {"gap": gap, "assessment": assessment, "evidence": evidence}


@app.post(
    "/api/runbooks/draft",
    tags=["Runbooks"],
    summary="Draft a runbook for an incident",
    response_model=Runbook,
    responses={503: {"model": ErrorResponse, "description": "The chat model could not produce a valid runbook."}},
)
def create_runbook_draft(request: RunbookDraftRequest) -> Runbook:
    """Generate a structured runbook draft from the incident description and up to 6 matching passages.

    The draft is returned only; nothing is saved. Review and edit it, then pass it to
    `POST /api/runbooks/export` or `POST /api/runbooks/publish`. Generation can take minutes.
    """
    evidence = get_knowledge_base().search(request.incident, limit=6)
    try:
        runbook = draft_runbook(request.incident, evidence)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Could not generate a runbook draft with llama.cpp: {error}") from error
    audit.record("runbook_drafted", {"title": runbook.title, "evidence": [item["source"] for item in evidence]})
    return runbook


@app.post(
    "/api/runbooks/export",
    tags=["Runbooks"],
    summary="Export a runbook as Markdown",
    response_class=PlainTextResponse,
    responses={200: {"description": "The runbook as a Markdown file download.", "content": {"text/plain": {}}}},
)
def export_runbook(runbook: Runbook) -> PlainTextResponse:
    """Render a runbook as Markdown and return it as a file download named after its title.

    Each section becomes a `##` heading; empty sections read "Not specified". Nothing is saved.
    """
    audit.record("runbook_exported", {"title": runbook.title})
    return PlainTextResponse(
        to_markdown(runbook),
        headers={"Content-Disposition": _markdown_attachment_header(runbook.title)},
    )


def _markdown_attachment_header(title: str) -> str:
    """Build a Content-Disposition header that is always valid Latin-1 (RFC 6266/5987)."""
    name = " ".join(title.split())[:80] or "runbook"
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "runbook"
    return f"attachment; filename=\"{fallback}.md\"; filename*=UTF-8''{quote(name + '.md', safe='')}"


@app.post(
    "/api/runbooks/publish",
    tags=["Runbooks"],
    summary="Save a runbook to the publish repository",
    response_model=PublishResult,
    responses={400: {"model": ErrorResponse, "description": "The path is invalid, escapes the repository, or the file already exists."}},
)
def publish_runbook(request: PublishRequest) -> dict[str, str]:
    """Write the runbook as a new Markdown file in the publish directory.

    In Docker Compose this is the host directory set by `RUNBOOK_PUBLISH_PATH` (default
    `./docs/rosie/generated-runbooks`); `path` is relative to it.

    Existing files are never overwritten. The file is not committed: review it and commit
    it with Git yourself. Published runbooks are not indexed automatically.
    """
    try:
        path = get_publisher().create(request.path, request.runbook)
    except (ValueError, FileExistsError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    audit.record("runbook_published", {"path": str(path)})
    return {"path": str(path), "status": "written; review and commit with Git"}
