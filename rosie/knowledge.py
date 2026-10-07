from uuid import NAMESPACE_URL, uuid5

from langchain_ollama import OllamaEmbeddings
from qdrant_client import QdrantClient, models

from rosie.config import settings
from rosie.documents import chunks


class KnowledgeBase:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embeddings = OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
        )
        self.collection = settings.qdrant_collection

    def ingest(self, text: str, source: str, kind: str = "document") -> int:
        passages = chunks(text)
        if not passages:
            return 0
        vectors = self.embeddings.embed_documents(passages)
        collection_exists = self.client.collection_exists(self.collection)
        if not collection_exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
            )
        source_filter = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value=source)),
                models.FieldCondition(key="kind", match=models.MatchValue(value=kind)),
            ]
        )
        existing_ids: set[str] = set()
        if collection_exists:
            offset = None
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=source_filter,
                    limit=256,
                    offset=offset,
                    with_payload=False,
                )
                existing_ids.update(str(point.id) for point in points)
                if offset is None:
                    break
        point_ids = [
            str(uuid5(NAMESPACE_URL, f"rosie:{kind}:{source}:{index}"))
            for index in range(len(passages))
        ]
        self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"text": passage, "source": source, "kind": kind},
                )
                for point_id, passage, vector in zip(point_ids, passages, vectors, strict=True)
            ],
        )
        stale_ids = existing_ids.difference(point_ids)
        if stale_ids:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=list(stale_ids)),
            )
        return len(passages)

    def search(self, query: str, kind: str | None = None, limit: int = 5) -> list[dict[str, str | float]]:
        if not self.client.collection_exists(self.collection):
            return []
        vector = self.embeddings.embed_query(query)
        query_filter = None
        if kind:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="kind", match=models.MatchValue(value=kind))]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=settings.relevance_threshold,
            with_payload=True,
        )
        return [
            {
                "text": str(point.payload.get("text", "")),
                "source": str(point.payload.get("source", "unknown")),
                "kind": str(point.payload.get("kind", "document")),
                "score": float(point.score),
            }
            for point in response.points
        ]
