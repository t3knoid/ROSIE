from types import SimpleNamespace

from rosie.knowledge import KnowledgeBase


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