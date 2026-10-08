from types import SimpleNamespace

from rosie.knowledge import KnowledgeBase, OllamaEmbeddingClient


class FakeEmbeddings:
    def embed_documents(self, passages: list[str]) -> list[list[float]]:
        return [[float(index), 1.0] for index, _ in enumerate(passages)]


class FakeQdrant:
    def __init__(self) -> None:
        self.ids = {"stale-point"}

    def collection_exists(self, collection: str) -> bool:
        return True

    def scroll(self, **kwargs):
        return [SimpleNamespace(id=point_id) for point_id in self.ids], None

    def upsert(self, collection_name: str, points: list) -> None:
        self.ids.update(point.id for point in points)

    def delete(self, collection_name: str, points_selector) -> None:
        self.ids.difference_update(points_selector.points)


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
    knowledge.embeddings = FakeEmbeddings()
    knowledge.collection = "test"

    first_count = knowledge.ingest("alpha bravo charlie delta", "https://example.test/page.html", "runbook")
    first_ids = set(knowledge.client.ids)
    second_count = knowledge.ingest("alpha bravo charlie delta", "https://example.test/page.html", "runbook")

    assert first_count == second_count
    assert len(knowledge.client.ids) == first_count
    assert knowledge.client.ids == first_ids