from uuid import NAMESPACE_URL, uuid5

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models

from rosie.config import settings
from rosie.documents import chunks


class LlamaCppEmbeddingClient:
    def __init__(self, model: str, base_url: str) -> None:
        self.embeddings = OpenAIEmbeddings(
            model=model,
            base_url=base_url,
            api_key="llama.cpp",
            check_embedding_ctx_length=False,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embeddings.embed_query(text)


class KnowledgeBase:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embeddings = LlamaCppEmbeddingClient(
            model=settings.llama_embedding_model,
            base_url=settings.llama_embedding_base_url,
        )
        self.collection = settings.qdrant_collection

    def ingest(self, content: str | list[str], source: str, kind: str = "document", *, replace_kind: bool = False) -> int:
        """Index text (split into passages here) or ready-made passages under one source.

        Replaces the source's earlier passages of the same kind. Passages whose text is
        unchanged are not re-embedded. With `replace_kind`, passages stored for this source
        under the other kind are removed.
        """
        passages = chunks(content) if isinstance(content, str) else [passage for passage in content if passage.strip()]
        if not passages:
            return 0
        point_ids = [
            str(uuid5(NAMESPACE_URL, f"rosie:{kind}:{source}:{index}"))
            for index in range(len(passages))
        ]
        collection_exists = self.client.collection_exists(self.collection)
        source_filter = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value=source)),
                models.FieldCondition(key="kind", match=models.MatchValue(value=kind)),
            ]
        )
        existing_passages: dict[str, str] = {}
        if collection_exists:
            offset = None
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=source_filter,
                    limit=256,
                    offset=offset,
                    with_payload=["text"],
                )
                existing_passages.update(
                    (str(point.id), str((point.payload or {}).get("text", "")))
                    for point in points
                )
                if offset is None:
                    break

        if len(existing_passages) == len(point_ids) and all(
            existing_passages.get(point_id) == passage
            for point_id, passage in zip(point_ids, passages, strict=True)
        ):
            if replace_kind:
                self._delete_other_kinds(source, kind)
            return len(passages)

        vectors = self.embeddings.embed_documents(passages)
        if not collection_exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
            )
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
        stale_ids = set(existing_passages).difference(point_ids)
        if stale_ids:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=list(stale_ids)),
            )
        if replace_kind:
            self._delete_other_kinds(source, kind)
        return len(passages)

    def _delete_other_kinds(self, source: str, kind: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))],
                    must_not=[models.FieldCondition(key="kind", match=models.MatchValue(value=kind))],
                )
            ),
            wait=True,
        )

    def delete_sources(self, sources: list[str]) -> None:
        """Remove every passage stored under any of these sources."""
        if not sources or not self.client.collection_exists(self.collection):
            return
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[models.FieldCondition(key="source", match=models.MatchAny(any=sources))])
            ),
            wait=True,
        )

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
