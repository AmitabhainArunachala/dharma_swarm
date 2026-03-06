"""Knowledge-store interfaces and backends.

Backends:
- InMemoryKnowledgeStore: zero-dependency local fallback (default)
- QdrantKnowledgeStore: vector backend when `qdrant-client` + server are available
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _metadata_match(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if metadata.get(key) != value:
            return False
    return True


def _hash_embed(text: str, dim: int = 256) -> list[float]:
    """Deterministic lightweight embedding for infra-light operation."""
    vec = [0.0] * max(8, dim)
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(vec)
        sign = -1.0 if int(digest[8:10], 16) % 2 else 1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


@dataclass(slots=True)
class KnowledgeRecord:
    """Knowledge payload stored for retrieval."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: uuid4().hex[:16])
    created_at: datetime = field(default_factory=_utc_now)


class KnowledgeStore(Protocol):
    """Backend contract for knowledge retrieval and storage."""

    def add(self, record: KnowledgeRecord) -> str: ...

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeRecord, float]]: ...

    @property
    def size(self) -> int: ...


class InMemoryKnowledgeStore:
    """Simple semantic-ish local store for bootstrapping and tests."""

    def __init__(self) -> None:
        self._records: list[KnowledgeRecord] = []

    def add(self, record: KnowledgeRecord) -> str:
        self._records.append(record)
        return record.record_id

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeRecord, float]]:
        query_tokens = _tokenize(query)
        out: list[tuple[KnowledgeRecord, float]] = []
        for rec in self._records:
            if filters and not _metadata_match(rec.metadata, filters):
                continue
            score = _jaccard(query_tokens, _tokenize(rec.text))
            out.append((rec, score))
        out.sort(key=lambda item: item[1], reverse=True)
        return out[: max(1, k)]

    @property
    def size(self) -> int:
        return len(self._records)


class QdrantKnowledgeStore:
    """Qdrant-backed knowledge store.

    Uses deterministic hash-embeddings to keep runtime lightweight.
    You can later replace `_hash_embed` with sentence-transformers without
    changing the storage/query contract.
    """

    def __init__(
        self,
        *,
        url: str = "http://127.0.0.1:6333",
        collection: str = "dgc_artifacts",
        vector_size: int = 256,
        timeout_sec: float = 1.5,
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        self._qmodels = qmodels
        self._client = QdrantClient(url=url, timeout=timeout_sec)
        self._collection = collection
        self._vector_size = vector_size

        existing = {
            c.name for c in self._client.get_collections().collections
        }
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def add(self, record: KnowledgeRecord) -> str:
        point = self._qmodels.PointStruct(
            id=record.record_id,
            vector=_hash_embed(record.text, dim=self._vector_size),
            payload={
                "text": record.text,
                "metadata": record.metadata,
                "created_at": record.created_at.isoformat(),
            },
        )
        self._client.upsert(
            collection_name=self._collection,
            points=[point],
        )
        return record.record_id

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeRecord, float]]:
        query_filter = None
        if filters:
            must = []
            for key, value in filters.items():
                must.append(
                    self._qmodels.FieldCondition(
                        key=f"metadata.{key}",
                        match=self._qmodels.MatchValue(value=value),
                    )
                )
            query_filter = self._qmodels.Filter(must=must)

        hits = self._client.search(
            collection_name=self._collection,
            query_vector=_hash_embed(query, dim=self._vector_size),
            limit=max(1, k),
            query_filter=query_filter,
            with_payload=True,
        )

        out: list[tuple[KnowledgeRecord, float]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            created_raw = payload.get("created_at")
            created_at = _utc_now()
            if isinstance(created_raw, str):
                try:
                    created_at = datetime.fromisoformat(created_raw)
                except ValueError:
                    created_at = _utc_now()
            rec = KnowledgeRecord(
                text=str(payload.get("text", "")),
                metadata=dict(payload.get("metadata", {})),
                record_id=str(hit.id),
                created_at=created_at,
            )
            out.append((rec, float(hit.score or 0.0)))
        return out

    @property
    def size(self) -> int:
        # "points_count" may be None when not yet indexed; normalize to int.
        info = self._client.get_collection(self._collection)
        return int(info.points_count or 0)


def _make_qdrant_store(
    *,
    url: str,
    collection: str,
    vector_size: int,
) -> QdrantKnowledgeStore:
    return QdrantKnowledgeStore(
        url=url,
        collection=collection,
        vector_size=vector_size,
    )


def create_knowledge_store(
    prefer_qdrant: bool = True,
    *,
    backend: str | None = None,
    qdrant_url: str = "http://127.0.0.1:6333",
    qdrant_collection: str = "dgc_artifacts",
    qdrant_vector_size: int = 256,
    settings: Any | None = None,
) -> KnowledgeStore:
    """Create a knowledge store with graceful fallback.

    Backend resolution:
    - explicit `backend` arg if provided
    - else `DGC_KNOWLEDGE_BACKEND` env (`local` or `qdrant`)
    - fallback to `local`
    """
    if settings is not None:
        backend = backend or getattr(settings, "knowledge_backend", "local")
        qdrant_url = getattr(settings, "qdrant_url", qdrant_url)
        qdrant_collection = getattr(settings, "qdrant_collection", qdrant_collection)
        qdrant_vector_size = int(
            getattr(settings, "qdrant_vector_size", qdrant_vector_size)
        )
    elif backend is None:
        import os

        backend = os.getenv("DGC_KNOWLEDGE_BACKEND", "local")

    selected = (backend or "local").strip().lower()
    if selected not in {"local", "qdrant"}:
        selected = "local"

    if selected == "qdrant" or (prefer_qdrant and selected != "local"):
        try:
            return _make_qdrant_store(
                url=qdrant_url,
                collection=qdrant_collection,
                vector_size=qdrant_vector_size,
            )
        except Exception:
            return InMemoryKnowledgeStore()

    return InMemoryKnowledgeStore()
