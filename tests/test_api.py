import asyncio

from fastapi.testclient import TestClient
import pytest

from rosie import audit, main
from rosie.web_sources import CrawlResult, WebPage


@pytest.fixture(autouse=True)
def ready_sources(monkeypatch):
    monkeypatch.setitem(main.app.state._state, "source_sync", {**main.initial_sync_status(), "ready": True})


def sync_result(pages: int, errors: list[str]) -> dict[str, object]:
    """A source sync result in the shape `_ingest_configured_sources` returns."""
    return {"pages": pages, "chunks": pages, "pages_by_kind": {"document": pages, "runbook": 0}, "errors": errors}


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
    assert '<a id="sync-sources" href="#sync-status"' in response.text
    assert '<button id="sync-sources"' not in response.text
    assert 'id="sync-status"' in response.text
    assert response.text.index('id="question-form"') < response.text.index('id="sync-sources"') < response.text.index('</main>')
    assert 'aria-label="Incident question" disabled' in response.text
    assert 'Checking source sync...' in response.text
    assert 'askButton.disabled = !sourcesReady || isInvestigating || !input.value.trim();' in response.text
    assert "'/api/ingest/sources/status'" in response.text
    assert "'/api/ingest/sources'" in response.text
    assert "result.duration_seconds" in response.text
    assert 'localStorage' not in response.text


def test_home_page_moves_hardware_into_collapsed_footer() -> None:
    page = TestClient(main.app).get("/").text

    assert '<aside' not in page
    assert 'grid-template-columns' not in page
    assert page.index('</main>') < page.index('<footer id="gpu-panel"')
    assert '<details>' in page and '<details open' not in page
    assert '<summary>Hardware: <span id="gpu-summary"' in page
    assert 'id="gpu-detail"' in page
    assert "'/api/health/gpu'" in page


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


def test_chat_is_blocked_until_server_sync_succeeds(monkeypatch):
    main.app.state.source_sync = main.initial_sync_status()
    monkeypatch.setattr(main, "_ingest_configured_sources", lambda: sync_result(2, []))
    monkeypatch.setattr(main, "get_investigation_graph", lambda: FakeGraph())
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)
    assert client.post("/api/chat", json={"question": "Check logs"}).status_code == 503
    assert not client.get("/api/ingest/sources/status").json()["ready"]
    assert client.post("/api/ingest/sources").status_code == 200
    status = client.get("/api/ingest/sources/status").json()
    assert status["ready"] and status["last_success"]
    assert client.post("/api/chat", json={"question": "Check logs"}).status_code == 200


def test_startup_runs_source_sync_and_resets_readiness(monkeypatch):
    calls = []

    def ingest():
        calls.append(main.app.state.source_sync["ready"])
        return sync_result(2, [])

    monkeypatch.setattr(main, "_ingest_configured_sources", ingest)

    async def run_lifespan():
        async with main.lifespan(main.app):
            assert not main.app.state.source_sync["ready"]

    asyncio.run(run_lifespan())
    assert calls == [False]
    assert main.app.state.source_sync["ready"]


@pytest.mark.parametrize("partial", [True, False])
def test_failed_initial_sync_stays_locked_and_can_be_retried(monkeypatch, partial):
    main.app.state.source_sync = main.initial_sync_status()

    def ingest():
        if partial:
            return sync_result(1, ["Page unavailable"])
        raise main.HTTPException(status_code=502, detail="Source unavailable")

    monkeypatch.setattr(main, "_ingest_configured_sources", ingest)
    client = TestClient(main.app)
    client.post("/api/ingest/sources")
    status = client.get("/api/ingest/sources/status").json()
    assert not status["ready"] and not status["syncing"] and status["error"]
    monkeypatch.setattr(main, "_ingest_configured_sources", lambda: sync_result(2, []))
    assert client.post("/api/ingest/sources").status_code == 200
    assert client.get("/api/ingest/sources/status").json()["ready"]


def test_overlapping_sync_is_rejected():
    with main.source_sync_lock:
        assert TestClient(main.app).post("/api/ingest/sources").status_code == 409


def test_failed_startup_keeps_app_available_but_prompt_locked(monkeypatch):
    def ingest():
        raise RuntimeError("Embedding service unavailable")

    monkeypatch.setattr(main, "_ingest_configured_sources", ingest)

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
    status = TestClient(main.app).get("/api/ingest/sources/status").json()
    assert not status["ready"] and not status["syncing"]
    assert status["error"] == "Embedding service unavailable"


def test_failed_refresh_does_not_discard_initial_readiness(monkeypatch):
    monkeypatch.setattr(main, "_ingest_configured_sources", lambda: sync_result(1, ["Unavailable"]))
    client = TestClient(main.app)
    assert client.post("/api/ingest/sources").status_code == 200
    assert client.get("/api/ingest/sources/status").json()["ready"]


def test_startup_retries_until_initial_sync_succeeds(monkeypatch):
    calls = []

    def ingest():
        calls.append(True)
        return sync_result(1, ["Not ready"] if len(calls) == 1 else [])

    async def skip_retry_delay(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(main, "_ingest_configured_sources", ingest)
    monkeypatch.setattr(main.asyncio, "wait_for", skip_retry_delay)

    async def run_lifespan():
        async with main.lifespan(main.app):
            while not main.app.state.source_sync["ready"]:
                await asyncio.sleep(0)

    asyncio.run(run_lifespan())
    assert len(calls) == 2


def test_export_handles_non_latin1_and_unsafe_titles(monkeypatch) -> None:
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)
    client = TestClient(main.app)
    title = 'Disk full — "recovery"\nsteps'
    response = client.post("/api/runbooks/export", json={"title": title, "purpose": "p", "scope": "s"})
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert 'filename="Disk-full-recovery-steps.md"' in disposition
    assert "filename*=UTF-8''Disk%20full%20%E2%80%94%20%22recovery%22%20steps.md" in disposition
    assert response.text.startswith(f"# {title}")


def test_ingest_rejects_upload_without_text(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_knowledge_base", lambda: FakeKnowledgeBase())
    client = TestClient(main.app)
    response = client.post("/api/ingest", files={"file": ("empty.md", b"   \n")})
    assert response.status_code == 422


def test_every_endpoint_is_documented_in_openapi() -> None:
    schema = main.app.openapi()
    assert schema["info"]["description"]
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            name = f"{method.upper()} {path}"
            assert operation.get("summary"), f"{name} has no summary"
            assert operation.get("description"), f"{name} has no description"
            assert operation.get("tags"), f"{name} has no tag"
            content = operation["responses"]["200"].get("content", {})
            schemas = [media.get("schema", {}) for media in content.values()]
            assert any(schemas) or "text/plain" in content, f"{name} has an untyped 200 response"


def test_enter_sends_prompt_and_shift_enter_adds_line() -> None:
    page = TestClient(main.app).get("/").text
    assert "input.addEventListener('keydown'" in page
    assert "event.shiftKey || event.isComposing" in page
    assert "form.requestSubmit(askButton)" in page
    assert "Shift+Enter for a new line" in page


def test_prompt_explains_that_questions_are_independent() -> None:
    page = TestClient(main.app).get("/").text
    assert 'aria-describedby="prompt-hint"' in page
    assert 'id="prompt-hint"' in page
    assert "ROSIE does not see earlier questions or answers" in page
    assert page.index('id="question-form"') < page.index('id="prompt-hint"') < page.index('id="sync-sources"')
