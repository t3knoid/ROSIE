from fastapi.testclient import TestClient

from rosie import audit, main
from rosie.web_sources import CrawlResult, WebPage


class FakeKnowledgeBase:
    def __init__(self) -> None:
        self.ingested: list[tuple[str, str, str]] = []

    def ingest(self, text: str, source: str, kind: str) -> int:
        self.ingested.append((text, source, kind))
        return 1

    def search(self, query: str, kind: str | None = None, limit: int = 5) -> list[dict[str, str | float]]:
        if kind == "runbook":
            return []
        return [{"text": "Check the service logs.", "source": "operations.md", "kind": "document", "score": 0.9}]


class FakeGraph:
    def invoke(self, state: dict) -> dict:
        return {
            "answer": "Check the service logs. Source: operations.md",
            "evidence": [{"text": "Check the service logs.", "source": "operations.md", "kind": "document", "score": 0.9}],
            "runbook_gap": True,
        }


def test_health_and_chat_are_documentation_aware(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_knowledge_base", lambda: FakeKnowledgeBase())
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph())
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)

    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/api/chat", json={"question": "Why is the service down?"})
    assert response.status_code == 200
    assert response.json()["evidence"][0]["source"] == "operations.md"
    assert response.json()["runbook_gap"] is True


def test_home_page_exposes_source_sync_and_last_sync_status() -> None:
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert 'id="sync-sources"' in response.text
    assert 'id="sync-status"' in response.text
    assert "'/api/ingest/sources'" in response.text
    assert "rosie-last-successful-source-sync" in response.text


def test_ingest_validates_file_and_records_extracted_text(monkeypatch) -> None:
    knowledge = FakeKnowledgeBase()
    monkeypatch.setattr(main, "get_knowledge_base", lambda: knowledge)
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)

    response = client.post(
        "/api/ingest",
        files={"file": ("runbook.md", b"Restart after checking logs.", "text/markdown")},
        data={"kind": "runbook"},
    )
    assert response.status_code == 200
    assert response.json() == {"source": "runbook.md", "kind": "runbook", "chunks": 1}

    unsupported = client.post("/api/ingest", files={"file": ("script.py", b"pass")})
    assert unsupported.status_code == 415


def test_ingest_configured_sources_indexes_overview_and_runbooks(monkeypatch) -> None:
    knowledge = FakeKnowledgeBase()
    requested: list[str] = []

    def fake_crawl(url: str, **kwargs) -> CrawlResult:
        requested.append(url)
        kind_title = "Home Lab Overview" if url == main.settings.documentation_source_url else "Runbook"
        return CrawlResult(pages=[WebPage(url=url, title=kind_title, text="Operational guidance.")], errors=[])

    monkeypatch.setattr(main, "get_knowledge_base", lambda: knowledge)
    monkeypatch.setattr(main, "crawl_html_source", fake_crawl)
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)

    response = client.post("/api/ingest/sources")

    assert response.status_code == 200
    assert response.json()["pages_by_kind"] == {"document": 1, "runbook": 1}
    assert requested == [main.settings.documentation_source_url, main.settings.runbook_source_url]
    assert [item[2] for item in knowledge.ingested] == ["document", "runbook"]
