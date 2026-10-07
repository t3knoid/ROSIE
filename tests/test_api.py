from fastapi.testclient import TestClient

from rosie import audit, main


class FakeKnowledgeBase:
    def ingest(self, text: str, source: str, kind: str) -> int:
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
