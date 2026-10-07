from uuid import uuid4

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
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
            )
        self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={"text": passage, "source": source, "kind": kind},
                )
                for passage, vector in zip(passages, vectors, strict=True)
            ],
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
