"""Unified memory lattice facade over runtime events, recall, and facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.engine.hybrid_retriever import HybridRetriever
from dharma_swarm.engine.unified_index import UnifiedIndex
from dharma_swarm.event_log import EventLog
from dharma_swarm.memory import StrangeLoopMemory
from dharma_swarm.models import MemoryEntry, MemoryLayer
from dharma_swarm.runtime_contract import RuntimeEnvelope
from dharma_swarm.runtime_state import MemoryFact, RuntimeStateStore


@dataclass(frozen=True)
class MemoryRecallHit:
    record_id: str
    source_kind: str
    text: str
    score: float
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


class MemoryLattice:
    """Coordinate evidence, facts, retrieval, and strange-loop memory."""

    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        event_log_dir: Path | str | None = None,
    ) -> None:
        self.runtime_state = RuntimeStateStore(db_path)
        self.event_store = EventMemoryStore(self.runtime_state.db_path)
        self.index = UnifiedIndex(self.runtime_state.db_path)
        self.retriever = HybridRetriever(self.index)
        self.strange_loop = StrangeLoopMemory(self.runtime_state.db_path)
        self.event_log = EventLog(event_log_dir)

    async def init_db(self) -> None:
        await self.runtime_state.init_db()
        await self.event_store.init_db()
        await self.strange_loop.init_db()

    async def close(self) -> None:
        await self.strange_loop.close()

    async def ingest_runtime_envelope(
        self,
        envelope: RuntimeEnvelope | dict[str, Any],
        *,
        write_jsonl: bool = True,
    ) -> bool:
        inserted = await self.event_store.ingest_envelope(envelope)
        if inserted and write_jsonl:
            self.event_log.append_envelope(envelope)
        return inserted

    async def remember(
        self,
        content: str,
        layer: MemoryLayer,
        *,
        source: str = "agent",
        tags: list[str] | None = None,
        development_marker: bool = False,
        bypass_fitness: bool = False,
    ) -> MemoryEntry:
        entry = await self.strange_loop.remember(
            content,
            layer,
            source=source,
            tags=tags,
            development_marker=development_marker,
            bypass_fitness=bypass_fitness,
        )
        if layer != MemoryLayer.IMMEDIATE:
            self.index.index_document(
                "strange_loop",
                f"strangeloop://{entry.id}",
                entry.content,
                {
                    "memory_layer": entry.layer.value,
                    "memory_tags": list(entry.tags),
                    "memory_source": entry.source,
                    "development_marker": entry.development_marker,
                    "witness_quality": entry.witness_quality,
                    "recorded_at": entry.timestamp.isoformat(),
                },
            )
        return entry

    async def always_on_context(self, max_chars: int = 3000) -> str:
        return await self.strange_loop.get_context(max_chars=max_chars)

    def index_document(
        self,
        source_kind: str,
        source_path: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str:
        return self.index.index_document(source_kind, source_path, text, metadata)

    def index_note_file(
        self,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.index.index_note_file(path, metadata=metadata)

    async def record_fact(
        self,
        text: str,
        *,
        fact_kind: str = "fact",
        truth_state: str = "candidate",
        confidence: float = 0.5,
        session_id: str = "",
        task_id: str = "",
        source_event_id: str = "",
        source_artifact_id: str = "",
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> MemoryFact:
        fact = MemoryFact(
            fact_id=self.runtime_state.new_fact_id(),
            fact_kind=fact_kind,
            truth_state=truth_state,
            text=text,
            confidence=float(confidence),
            session_id=session_id,
            task_id=task_id,
            source_event_id=source_event_id,
            source_artifact_id=source_artifact_id,
            provenance=dict(provenance or {}),
            metadata=dict(metadata or {}),
        )
        saved = await self.runtime_state.record_memory_fact(fact)
        self.index.index_document(
            "memory_fact",
            f"memory://{saved.fact_id}",
            saved.text,
            {
                **saved.metadata,
                "fact_id": saved.fact_id,
                "fact_kind": saved.fact_kind,
                "truth_state": saved.truth_state,
                "session_id": saved.session_id,
                "task_id": saved.task_id,
                "source_event_id": saved.source_event_id,
                "source_artifact_id": saved.source_artifact_id,
                "confidence": saved.confidence,
            },
        )
        return saved

    async def promote_fact(
        self,
        fact_id: str,
        *,
        truth_state: str = "promoted",
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryFact:
        updated = await self.runtime_state.update_memory_fact_truth(
            fact_id,
            truth_state=truth_state,
            confidence=confidence,
            metadata=metadata,
        )
        self.index.index_document(
            "memory_fact",
            f"memory://{updated.fact_id}",
            updated.text,
            {
                **updated.metadata,
                "fact_id": updated.fact_id,
                "fact_kind": updated.fact_kind,
                "truth_state": updated.truth_state,
                "session_id": updated.session_id,
                "task_id": updated.task_id,
                "source_event_id": updated.source_event_id,
                "source_artifact_id": updated.source_artifact_id,
                "confidence": updated.confidence,
            },
        )
        return updated

    async def replay_session(self, session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        return await self.event_store.replay_session(session_id, limit=limit)

    async def replay_trace(self, trace_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        return await self.event_store.replay_trace(trace_id, limit=limit)

    async def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        session_id: str | None = None,
        task_id: str | None = None,
        truth_state: str | None = None,
        consumer: str | None = None,
    ) -> list[MemoryRecallHit]:
        filters: dict[str, Any] = {}
        if session_id:
            filters["session_id"] = session_id
        if task_id:
            filters["task_id"] = task_id
        if truth_state:
            filters["truth_state"] = truth_state
        hits = self.retriever.search(
            query,
            limit=limit,
            filters=filters or None,
            consumer=consumer,
        )
        return [
            MemoryRecallHit(
                record_id=hit.record.record_id,
                source_kind=str(hit.record.metadata.get("source_kind", "unknown")),
                text=hit.record.text,
                score=float(hit.score),
                created_at=hit.record.created_at,
                metadata=dict(hit.record.metadata),
                evidence=dict(hit.evidence),
            )
            for hit in hits
        ]
