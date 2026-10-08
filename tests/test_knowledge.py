from types import SimpleNamespace

from rosie.knowledge import KnowledgeBase, OllamaEmbeddingClient


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, passages: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(index), 1.0] for index, _ in enumerate(passages)]


class FakeQdrant:
    def __init__(self) -> None:
        self.points = {"stale-point": {"text": "stale content"}}

    @property
    def ids(self) -> set[str]:
        return set(self.points)

    def collection_exists(self, collection: str) -> bool:
        return True

    def scroll(self, **kwargs):
        return [SimpleNamespace(id=point_id, payload=payload) for point_id, payload in self.points.items()], None

    def upsert(self, collection_name: str, points: list) -> None:
        self.points.update((point.id, point.payload) for point in points)

    def delete(self, collection_name: str, points_selector) -> None:
        for point_id in points_selector.points:
            self.points.pop(point_id, None)


def test_ollama_embedding_client_does_not_send_generation_options(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    class FakeOllamaClient:
        def __init__(self, host: str) -> None:
            assert host == "http://ollama.test:11434"

        def embed(self, *, model: str, input: list[str]) -> dict[str, list[list[float]]]:
            calls.append((model, input))
            return {"embeddings": [[0.1, 0.2] for _ in input]}

    monkeypatch.setattr("rosie.knowledge.Client", FakeOllamaClient)
    embeddings = OllamaEmbeddingClient("nomic-embed-text", "http://ollama.test:11434")

    assert embeddings.embed_documents(["first", "second"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert embeddings.embed_query("query") == [0.1, 0.2]
    assert calls == [
        ("nomic-embed-text", ["first", "second"]),
        ("nomic-embed-text", ["query"]),
    ]


def test_ingest_replaces_existing_source_chunks_without_duplicates() -> None:
    knowledge = KnowledgeBase.__new__(KnowledgeBase)
    knowledge.client = FakeQdrant()
    embeddings = FakeEmbeddings()
    knowledge.embeddings = embeddings
    knowledge.collection = "test"

    first_count = knowledge.ingest("alpha bravo charlie delta", "https://example.test/page.html", "runbook")
    first_ids = set(knowledge.client.ids)
    second_count = knowledge.ingest("alpha bravo charlie delta", "https://example.test/page.html", "runbook")

    assert first_count == second_count
    assert embeddings.calls == 1
    assert len(knowledge.client.ids) == first_count
    assert knowledge.client.ids == first_ids

    knowledge.ingest("alpha bravo charlie echo", "https://example.test/page.html", "runbook")

    assert embeddings.calls == 2
    assert knowledge.client.ids == first_ids
    assert any("echo" in point["text"] for point in knowledge.client.points.values())