from fastapi.testclient import TestClient

from rosie import audit, main
from rosie.web_sources import CrawlResult, WebPage


class FakeKnowledgeBase:
    def __init__(self) -> None:
        self.ingested: list[tuple[str, str, str]] = []
        self.reclassified: list[str] = []

    def ingest(self, text: str, source: str, kind: str, *, replace_kind: bool = False) -> int:
        self.ingested.append((text, source, kind))
        if replace_kind:
            self.reclassified.append(source)
        return 1

    def search(self, query: str, kind: str | None = None, limit: int = 5) -> list[dict[str, str | float]]:
        if kind == "runbook":
            return []
        return [{"text": "Check the service logs.", "source": "operations.md", "kind": "document", "score": 0.9}]


class FakeGraph:
    def __init__(self, answer: str = "Check the service logs. Source: operations.md") -> None:
        self.answer = answer

    def invoke(self, state: dict) -> dict:
        return {
            "answer": self.answer,
            "evidence": [{"text": "Check the service logs.", "source": "operations.md", "kind": "document", "score": 0.9}],
            "runbook_gap": True,
        }


def test_health_and_chat_are_documentation_aware(monkeypatch) -> None:
    timestamps = iter((10.0, 12.3456))
    monkeypatch.setattr(main, "get_knowledge_base", lambda: FakeKnowledgeBase())
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph())
    monkeypatch.setattr(main, "perf_counter", lambda: next(timestamps))
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)

    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/api/chat", json={"question": "Why is the service down?"})
    assert response.status_code == 200
    assert response.json()["evidence"][0]["source"] == "operations.md"
    assert "<p>Check the service logs." in response.json()["answer_html"]
    assert response.json()["runbook_gap"] is True
    assert response.json()["duration_seconds"] == 2.346


def test_chat_renders_markdown_and_sanitizes_unsafe_html(monkeypatch) -> None:
    answer = "**Check logs**\n\n<script>alert(1)</script> [unsafe](javascript:alert(1))"
    monkeypatch.setattr(main, "get_knowledge_base", lambda: FakeKnowledgeBase())
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph(answer))
    monkeypatch.setattr(main, "perf_counter", lambda: 1.0)
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)

    response = TestClient(main.app).post("/api/chat", json={"question": "Check logs"})

    assert response.status_code == 200
    assert "<strong>Check logs</strong>" in response.json()["answer_html"]
    assert "<script>" not in response.json()["answer_html"]
    assert "javascript:" not in response.json()["answer_html"]


def test_chat_linkifies_plain_urls_with_underscores(monkeypatch) -> None:
    url = "https://homelab.refol.us/reverse-proxy_with_oauth2_integration.html"
    monkeypatch.setattr(main, "get_knowledge_base", lambda: FakeKnowledgeBase())
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph(f"See {url}."))
    monkeypatch.setattr(main, "perf_counter", lambda: 1.0)
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)

    response = TestClient(main.app).post("/api/chat", json={"question": "Show the reference"})

    assert response.status_code == 200
    assert f'<a href="{url}"' in response.json()["answer_html"]


def test_chat_linkifies_backtick_wrapped_source_urls(monkeypatch) -> None:
    urls = [
        "https://homelab.refol.us/add_truenas_local_users.html",
        "https://homelab.refol.us/truenas_role_contributor_guide.html",
    ]
    answer = f"1. `{urls[0]}` (runbook)\n2. `{urls[1]}` (document)"
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph(answer))
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)

    response = TestClient(main.app).post("/api/chat", json={"question": "Show the references"})

    assert response.status_code == 200
    assert response.json()["answer"] == answer
    for url in urls:
        assert f'<a href="{url}"' in response.json()["answer_html"]


def test_home_page_exposes_source_sync_and_last_sync_status() -> None:
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert 'id="ask" type="submit" disabled' in response.text
    assert 'id="sync-sources"' in response.text
    assert 'id="sync-status"' in response.text
    assert "'/api/ingest/sources'" in response.text
    assert "result.duration_seconds" in response.text
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
        assert kwargs["runbook_index"] == (url == main.settings.runbook_source_url)
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


def test_source_sync_counts_overlapping_pages_once_with_runbook_priority(monkeypatch) -> None:
    knowledge = FakeKnowledgeBase()
    runbook = WebPage(url="https://homelab.test/recovery.html", title="Recovery", text="Check logs.")
    document = WebPage(url="https://homelab.test/overview.html", title="Overview", text="Architecture.")

    def fake_crawl(url: str, **kwargs) -> CrawlResult:
        return CrawlResult(
            pages=[runbook] if kwargs["runbook_index"] else [document, runbook],
            errors=[],
        )

    monkeypatch.setattr(main, "get_knowledge_base", lambda: knowledge)
    monkeypatch.setattr(main, "crawl_html_source", fake_crawl)
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)

    result = TestClient(main.app).post("/api/ingest/sources").json()

    assert result["pages"] == result["chunks"] == 2
    assert result["pages_by_kind"] == {"document": 1, "runbook": 1}
    assert [(source, kind) for _, source, kind in knowledge.ingested] == [
        (document.url, "document"), (runbook.url, "runbook"),
    ]
    assert knowledge.reclassified == [document.url, runbook.url]
