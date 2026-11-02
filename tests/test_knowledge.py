from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient

from rosie.knowledge import KnowledgeBase, LlamaCppEmbeddingClient


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


def test_llama_cpp_embedding_client_uses_openai_compatible_api(monkeypatch) -> None:
    clients: list[tuple[str, str, bool]] = []

    class FakeOpenAIEmbeddings:
        def __init__(self, *, model: str, base_url: str, api_key: str, check_embedding_ctx_length: bool) -> None:
            clients.append((model, base_url, check_embedding_ctx_length))

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [0.1, 0.2]

    monkeypatch.setattr("rosie.knowledge.OpenAIEmbeddings", FakeOpenAIEmbeddings)
    embeddings = LlamaCppEmbeddingClient("local-embedding", "http://llama.test:8081/v1")

    assert embeddings.embed_documents(["first", "second"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert embeddings.embed_query("query") == [0.1, 0.2]
    assert clients == [("local-embedding", "http://llama.test:8081/v1", False)]


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


@pytest.mark.parametrize("kind", ["document", "runbook"])
@pytest.mark.parametrize("unchanged", [False, True])
def test_source_sync_replaces_conflicting_kind_without_touching_other_sources(kind, unchanged) -> None:
    knowledge = KnowledgeBase.__new__(KnowledgeBase)
    knowledge.client = QdrantClient(":memory:")
    knowledge.embeddings = FakeEmbeddings()
    knowledge.collection = "test"
    source = "https://example.test/page.html"
    other_source = "https://example.test/other.html"
    other_kind = "runbook" if kind == "document" else "document"

    try:
        knowledge.ingest("Other source content", other_source, other_kind)
        knowledge.ingest("Incorrect classification", source, other_kind)
        if unchanged:
            knowledge.ingest("Current content", source, kind)
        calls = knowledge.embeddings.calls

        knowledge.ingest("Current content", source, kind, replace_kind=True)

        points, _ = knowledge.client.scroll(knowledge.collection, with_payload=True)
        assert {(point.payload["source"], point.payload["kind"]) for point in points} == {
            (source, kind), (other_source, other_kind),
        }
        assert knowledge.embeddings.calls == calls + (0 if unchanged else 1)
    finally:
        knowledge.client.close()