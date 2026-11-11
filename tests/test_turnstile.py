import httpx
import pytest
from fastapi.testclient import TestClient

from rosie import audit, main, turnstile
from rosie.config import settings


@pytest.fixture(autouse=True)
def ready_sources(monkeypatch):
    monkeypatch.setitem(main.app.state._state, "source_sync", {**main.initial_sync_status(), "ready": True})
    monkeypatch.setattr(audit, "record", lambda *args, **kwargs: None)


@pytest.fixture
def turnstile_on(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_site_key", "site-key")
    monkeypatch.setattr(settings, "turnstile_secret_key", "secret-key")


class AnsweringGraph:
    def invoke(self, state):
        return {"answer": "Check the logs.", "evidence": [], "runbook_gap": True}


def fake_siteverify(monkeypatch, *, success=True, error=None, error_codes=None):
    calls = []

    def post(url, data, timeout):
        calls.append({"url": url, **data})
        if error:
            raise error
        body = {"success": success, "error-codes": error_codes or []}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(turnstile.httpx, "post", post)
    return calls


def test_config_reports_the_site_key_only_when_turnstile_is_on(turnstile_on, monkeypatch) -> None:
    client = TestClient(main.app)
    assert client.get("/api/config").json() == {"turnstile_site_key": "site-key"}
    monkeypatch.setattr(settings, "turnstile_secret_key", "")
    assert client.get("/api/config").json() == {"turnstile_site_key": None}


def test_chat_without_turnstile_needs_no_token(monkeypatch) -> None:
    calls = fake_siteverify(monkeypatch)
    monkeypatch.setattr(main, "get_investigation_graph", lambda: AnsweringGraph())
    assert TestClient(main.app).post("/api/chat", json={"question": "Is DNS up?"}).status_code == 200
    assert calls == []


@pytest.mark.parametrize("token", [None, ""])
def test_chat_rejects_a_missing_token_without_asking_cloudflare(turnstile_on, monkeypatch, token) -> None:
    calls = fake_siteverify(monkeypatch)
    monkeypatch.setattr(main, "get_investigation_graph", lambda: pytest.fail("the model must not run"))
    response = TestClient(main.app).post("/api/chat", json={"question": "Is DNS up?", "turnstile_token": token})
    assert response.status_code == 403
    assert calls == []


def test_chat_rejects_a_token_cloudflare_refuses(turnstile_on, monkeypatch) -> None:
    calls = fake_siteverify(monkeypatch, success=False)
    monkeypatch.setattr(main, "get_investigation_graph", lambda: pytest.fail("the model must not run"))
    response = TestClient(main.app).post("/api/chat", json={"question": "Is DNS up?", "turnstile_token": "used"})
    assert response.status_code == 403
    assert calls[0]["response"] == "used"


def test_a_rejected_token_logs_cloudflares_reason(turnstile_on, monkeypatch, caplog) -> None:
    fake_siteverify(monkeypatch, success=False, error_codes=["timeout-or-duplicate"])
    with caplog.at_level("WARNING", logger="rosie.turnstile"):
        assert turnstile.verify("used") is False
    assert "timeout-or-duplicate" in caplog.text


def test_chat_answers_after_cloudflare_accepts_the_token(turnstile_on, monkeypatch) -> None:
    calls = fake_siteverify(monkeypatch, success=True)
    monkeypatch.setattr(main, "get_investigation_graph", lambda: AnsweringGraph())
    response = TestClient(main.app).post(
        "/api/chat",
        json={"question": "Is DNS up?", "turnstile_token": "fresh"},
        headers={"CF-Connecting-IP": "203.0.113.7"},
    )
    assert response.status_code == 200
    assert calls == [{
        "url": turnstile.SITEVERIFY_URL,
        "secret": "secret-key",
        "response": "fresh",
        "remoteip": "203.0.113.7",
    }]


def test_chat_fails_closed_when_cloudflare_is_unreachable(turnstile_on, monkeypatch) -> None:
    fake_siteverify(monkeypatch, error=httpx.ConnectError("no route"))
    monkeypatch.setattr(main, "get_investigation_graph", lambda: pytest.fail("the model must not run"))
    response = TestClient(main.app).post("/api/chat", json={"question": "Is DNS up?", "turnstile_token": "fresh"})
    assert response.status_code == 503
