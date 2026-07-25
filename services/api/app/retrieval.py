from functools import lru_cache
from typing import Any

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

from app.config import settings

COLLECTION = "policy_chunks_v1"


@lru_cache
def qdrant() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=20)


@lru_cache
def dense_model() -> TextEmbedding:
    return TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")


@lru_cache
def sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding("Qdrant/bm25")


@lru_cache
def reranker() -> TextCrossEncoder:
    return TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")


def ensure_collection() -> None:
    client = qdrant()
    if client.collection_exists(COLLECTION):
        return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))},
    )
    for field in ("tenant_id", "status", "policy_version_id", "effective_date", "acl"):
        client.create_payload_index(COLLECTION, field, models.PayloadSchemaType.KEYWORD)


def index_chunks(chunks: list[dict[str, Any]]) -> None:
    if not chunks:
        return
    ensure_collection()
    texts = [item["content"] for item in chunks]
    dense_vectors = list(dense_model().embed(texts))
    sparse_vectors = list(sparse_model().embed(texts))
    points = []
    for item, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True):
        points.append(models.PointStruct(
            id=item["point_id"],
            vector={
                "dense": dense.tolist(),
                "sparse": models.SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
            },
            payload=item,
        ))
    qdrant().upsert(COLLECTION, points=points, wait=True)


def hybrid_search(query: str, tenant_id: str, roles: list[str], effective_date: str, limit: int = 8) -> list[dict[str, Any]]:
    ensure_collection()
    dense = next(dense_model().query_embed(query))
    sparse = next(sparse_model().query_embed(query))
    must = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
        models.FieldCondition(key="status", match=models.MatchValue(value="PUBLISHED")),
        models.FieldCondition(key="acl", match=models.MatchAny(any=roles)),
        models.FieldCondition(key="effective_date", range=models.Range(lte=effective_date)),
    ]
    result = qdrant().query_points(
        COLLECTION,
        prefetch=[
            models.Prefetch(query=dense.tolist(), using="dense", limit=20, filter=models.Filter(must=must)),
            models.Prefetch(query=models.SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()), using="sparse", limit=20, filter=models.Filter(must=must)),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=20,
        with_payload=True,
    ).points
    if not result:
        return []
    candidates = [point.payload or {} for point in result]
    scores = list(reranker().rerank(query, [str(item.get("content", "")) for item in candidates]))
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: float(pair[1]), reverse=True)
    return [{**item, "rerank_score": float(score)} for item, score in ranked[: max(4, min(limit, 8))] if float(score) >= 0.05]
