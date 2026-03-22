"""Concrete intelligence-side sovereign adapters.

These adapters keep the contract surface in :mod:`dharma_swarm.contracts`
authoritative while reusing DHARMA-owned runtime stores:

- ``memory_facts`` in :mod:`dharma_swarm.runtime_state` back ``MemoryPlane``
- :mod:`dharma_swarm.engine.event_memory` keeps an audit trail for contract writes
- :mod:`dharma_swarm.skills` backs discovered/curated skills
- adapter-owned SQLite tables capture generic skill and evaluation records that
  do not yet have a first-class canonical table elsewhere
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

logger = logging.getLogger(__name__)

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import MemoryFact, RuntimeStateStore
from dharma_swarm.skills import SkillDefinition, SkillRegistry

from .common import EvaluationRecord, MemoryRecord, MemoryTruthState, SkillArtifact, SkillPromotionState
from .intelligence import EvaluationSink, LearningEngine, MemoryPlane, SkillStore

_SKILLS_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_skill_artifacts (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    promotion_state TEXT NOT NULL,
    source_run_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_EVALUATIONS_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_evaluation_records (
    evaluation_id TEXT PRIMARY KEY,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    evaluator TEXT NOT NULL,
    metric TEXT NOT NULL,
    score REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
)"""

_MODELS_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_model_snapshots (
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (entity_kind, entity_id)
)"""

_INTELLIGENCE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_intelligence_skills_state_updated"
    " ON intelligence_skill_artifacts(promotion_state, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_intelligence_evals_subject_metric_time"
    " ON intelligence_evaluation_records(subject_kind, subject_id, metric, recorded_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_intelligence_evals_task_time"
    " ON intelligence_evaluation_records(task_id, recorded_at DESC)",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _parse_dt(raw: str | None) -> datetime:
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            logger.debug("Datetime parse failed", exc_info=True)
    return _utc_now()


def _coerce_memory_truth(raw: str | MemoryTruthState) -> MemoryTruthState:
    if isinstance(raw, MemoryTruthState):
        return raw
    try:
        return MemoryTruthState(str(raw))
    except ValueError:
        return MemoryTruthState.CANDIDATE


def _coerce_skill_state(raw: str | SkillPromotionState) -> SkillPromotionState:
    if isinstance(raw, SkillPromotionState):
        return raw
    try:
        return SkillPromotionState(str(raw))
    except ValueError:
        return SkillPromotionState.DRAFT


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if cleaned:
                result.append(cleaned)
        return result
    return []


def _dedupe_dict_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        marker = (
            row.get("kind", ""),
            row.get("skill_id", ""),
            row.get("preferred_role", ""),
            row.get("recommended_model", ""),
            row.get("recommended_provider", ""),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


async def _ensure_intelligence_schema(runtime_state: RuntimeStateStore) -> None:
    await runtime_state.init_db()
    async with aiosqlite.connect(runtime_state.db_path) as db:
        await db.execute(_SKILLS_DDL)
        await db.execute(_EVALUATIONS_DDL)
        await db.execute(_MODELS_DDL)
        for statement in _INTELLIGENCE_INDEXES:
            await db.execute(statement)
        await db.commit()


def _skill_registry_record(definition: SkillDefinition) -> SkillArtifact:
    return SkillArtifact(
        skill_id=f"registry:{definition.name}",
        name=definition.name,
        version="registry",
        description=definition.description,
        promotion_state=SkillPromotionState.PROMOTED,
        source_run_id="",
        metadata={
            "source_path": definition.source_path or "",
            "model": definition.model,
            "provider": definition.provider,
            "autonomy": definition.autonomy,
            "tools": list(definition.tools),
            "tags": list(definition.tags),
            "keywords": list(definition.keywords),
            "context_weights": definition.context_weights.model_dump(),
            "system_prompt": definition.system_prompt,
            "source": "skill_registry",
        },
    )


def _row_to_skill(row: sqlite3.Row | aiosqlite.Row) -> SkillArtifact:
    metadata = _json_load(row["metadata_json"], {})
    return SkillArtifact(
        skill_id=str(row["skill_id"]),
        name=str(row["name"]),
        version=str(row["version"]),
        description=str(row["description"] or ""),
        promotion_state=_coerce_skill_state(str(row["promotion_state"] or "")),
        source_run_id=str(row["source_run_id"] or ""),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


def _row_to_evaluation(row: sqlite3.Row | aiosqlite.Row) -> EvaluationRecord:
    metadata = _json_load(row["metadata_json"], {})
    return EvaluationRecord(
        evaluation_id=str(row["evaluation_id"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        evaluator=str(row["evaluator"]),
        metric=str(row["metric"]),
        score=float(row["score"]),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        evidence_refs=tuple(_json_load(row["evidence_refs_json"], [])),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


class SovereignMemoryPlaneAdapter(MemoryPlane):
    """Contract adapter backed by canonical ``memory_facts`` rows."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        event_store: EventMemoryStore | None = None,
    ) -> None:
        self.runtime_state = runtime_state or RuntimeStateStore()
        self.event_store = event_store or EventMemoryStore(self.runtime_state.db_path)

    async def write_memory(self, record: MemoryRecord) -> MemoryRecord:
        await self.runtime_state.init_db()

        metadata = dict(record.metadata)
        provenance = dict(record.provenance)
        if record.agent_id:
            metadata.setdefault("agent_id", record.agent_id)
        metadata.setdefault("score", float(record.score))

        fact = MemoryFact(
            fact_id=record.record_id or self.runtime_state.new_fact_id(),
            fact_kind=record.kind,
            truth_state=record.truth_state.value,
            text=record.text,
            confidence=float(record.score),
            session_id=record.session_id,
            task_id=record.task_id,
            source_event_id=str(provenance.get("source_event_id", "")),
            source_artifact_id=str(provenance.get("source_artifact_id", "")),
            provenance=provenance,
            metadata=metadata,
        )
        saved = await self.runtime_state.record_memory_fact(fact)
        materialized = self._memory_record_from_fact(saved)
        await self._emit_memory_event("write_memory", materialized)
        return materialized

    async def get_memory(self, record_id: str) -> MemoryRecord | None:
        fact = await self.runtime_state.get_memory_fact(record_id)
        if fact is None:
            return None
        return self._memory_record_from_fact(fact)

    async def query_memory(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        truth_state: MemoryTruthState | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        fetch_limit = max(limit, 1)
        if agent_id:
            fetch_limit = max(fetch_limit * 5, 100)
        facts = await self.runtime_state.list_memory_facts(
            session_id=session_id,
            task_id=task_id,
            truth_state=truth_state.value if truth_state is not None else None,
            limit=fetch_limit,
        )
        records = [self._memory_record_from_fact(fact) for fact in facts]
        if agent_id:
            records = [record for record in records if record.agent_id == agent_id]
        return records[: max(limit, 1)]

    async def set_truth_state(
        self,
        *,
        record_id: str,
        truth_state: MemoryTruthState,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        updated = await self.runtime_state.update_memory_fact_truth(
            record_id,
            truth_state=truth_state.value,
            metadata=metadata,
        )
        materialized = self._memory_record_from_fact(updated)
        await self._emit_action_event(
            action_name="set_memory_truth_state",
            decision=truth_state.value,
            confidence=materialized.score,
            session_id=materialized.session_id,
            agent_id=materialized.agent_id,
            task_id=materialized.task_id,
            record_id=materialized.record_id,
            kind=materialized.kind,
        )
        return materialized

    def _memory_record_from_fact(self, fact: MemoryFact) -> MemoryRecord:
        metadata = dict(fact.metadata)
        provenance = dict(fact.provenance)
        if fact.source_event_id and "source_event_id" not in provenance:
            provenance["source_event_id"] = fact.source_event_id
        if fact.source_artifact_id and "source_artifact_id" not in provenance:
            provenance["source_artifact_id"] = fact.source_artifact_id
        agent_id = str(metadata.get("agent_id") or provenance.get("agent_id") or "")
        score = float(metadata.get("score", fact.confidence))
        return MemoryRecord(
            record_id=fact.fact_id,
            kind=fact.fact_kind,
            text=fact.text,
            truth_state=_coerce_memory_truth(fact.truth_state),
            session_id=fact.session_id,
            task_id=fact.task_id,
            agent_id=agent_id,
            score=score,
            metadata=metadata,
            provenance=provenance,
        )

    async def _emit_memory_event(self, action_name: str, record: MemoryRecord) -> None:
        if not record.session_id:
            return
        envelope = RuntimeEnvelope.create(
            event_type=RuntimeEventType.MEMORY_EVENT,
            source="contracts.intelligence.memory",
            agent_id=record.agent_id or "memory-plane",
            session_id=record.session_id,
            trace_id=record.task_id or record.record_id,
            payload={
                "memory_id": record.record_id,
                "memory_type": record.kind,
                "importance": max(0, min(int(round(record.score * 100)), 100)),
                "summary": record.text[:160],
                "action_name": action_name,
                "truth_state": record.truth_state.value,
                "task_id": record.task_id,
            },
        )
        await self.event_store.ingest_envelope(envelope)

    async def _emit_action_event(
        self,
        *,
        action_name: str,
        decision: str,
        confidence: float,
        session_id: str,
        agent_id: str,
        **payload: Any,
    ) -> None:
        if not session_id:
            return
        envelope = RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="contracts.intelligence.memory",
            agent_id=agent_id or "memory-plane",
            session_id=session_id,
            trace_id=str(payload.get("task_id") or payload.get("record_id") or action_name),
            payload={
                "action_name": action_name,
                "decision": decision,
                "confidence": max(0.0, min(float(confidence), 1.0)),
                **payload,
            },
        )
        await self.event_store.ingest_envelope(envelope)


class SovereignSkillStoreAdapter(SkillStore):
    """Hybrid skill store over discovered skills and adapter-owned skill records."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        skill_dirs: list[Path] | None = None,
    ) -> None:
        self.runtime_state = runtime_state or RuntimeStateStore()
        self.skill_registry = SkillRegistry(skill_dirs=skill_dirs)

    async def save_skill(self, skill: SkillArtifact) -> SkillArtifact:
        await _ensure_intelligence_schema(self.runtime_state)
        now = _utc_now_iso()
        resolved_skill = replace(skill, skill_id=skill.skill_id or _new_id("skill"))
        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            await db.execute(
                "INSERT INTO intelligence_skill_artifacts"
                " (skill_id, name, version, description, promotion_state, source_run_id,"
                " metadata_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(skill_id) DO UPDATE SET"
                " name = excluded.name,"
                " version = excluded.version,"
                " description = excluded.description,"
                " promotion_state = excluded.promotion_state,"
                " source_run_id = excluded.source_run_id,"
                " metadata_json = excluded.metadata_json,"
                " updated_at = excluded.updated_at",
                (
                    resolved_skill.skill_id,
                    resolved_skill.name,
                    resolved_skill.version,
                    resolved_skill.description,
                    resolved_skill.promotion_state.value,
                    resolved_skill.source_run_id,
                    _json_dump(resolved_skill.metadata),
                    now,
                    now,
                ),
            )
            await db.commit()
        saved = await self.get_skill(resolved_skill.skill_id)
        assert saved is not None
        return saved

    async def get_skill(self, skill_id: str) -> SkillArtifact | None:
        await _ensure_intelligence_schema(self.runtime_state)
        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT skill_id, name, version, description, promotion_state,"
                    " source_run_id, metadata_json, created_at, updated_at"
                    " FROM intelligence_skill_artifacts WHERE skill_id = ?",
                    (skill_id,),
                )
            ).fetchone()
        if row is not None:
            return _row_to_skill(row)

        discovered = self.skill_registry.get(skill_id.removeprefix("registry:")) or self.skill_registry.get(skill_id)
        if discovered is not None:
            return _skill_registry_record(discovered)
        return None

    async def list_skills(
        self,
        *,
        promotion_state: SkillPromotionState | None = None,
        limit: int = 100,
    ) -> list[SkillArtifact]:
        await _ensure_intelligence_schema(self.runtime_state)
        query = (
            "SELECT skill_id, name, version, description, promotion_state,"
            " source_run_id, metadata_json, created_at, updated_at"
            " FROM intelligence_skill_artifacts WHERE 1=1"
        )
        params: list[Any] = []
        if promotion_state is not None:
            query += " AND promotion_state = ?"
            params.append(promotion_state.value)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(limit, 1))

        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()

        persisted = [_row_to_skill(row) for row in rows]
        if promotion_state not in (None, SkillPromotionState.PROMOTED):
            return persisted[: max(limit, 1)]

        discovered_rows = [
            _skill_registry_record(skill)
            for skill in self.skill_registry.list_all()
        ]
        persisted_ids = {skill.skill_id for skill in persisted}
        combined = persisted + [
            skill
            for skill in discovered_rows
            if skill.skill_id not in persisted_ids
        ]
        return combined[: max(limit, 1)]

    async def promote_skill(
        self,
        *,
        skill_id: str,
        promotion_state: SkillPromotionState,
        metadata: dict[str, Any] | None = None,
    ) -> SkillArtifact:
        existing = await self.get_skill(skill_id)
        if existing is None:
            raise KeyError(f"skill {skill_id} not found")
        updated = replace(
            existing,
            promotion_state=promotion_state,
            metadata={**existing.metadata, **(metadata or {})},
        )
        return await self.save_skill(updated)


class SovereignEvaluationSinkAdapter(EvaluationSink):
    """Generic evaluation sink aligned with DHARMA's artifact-plus-fact pattern."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        event_store: EventMemoryStore | None = None,
        memory_plane: MemoryPlane | None = None,
    ) -> None:
        self.runtime_state = runtime_state or RuntimeStateStore()
        self.event_store = event_store or EventMemoryStore(self.runtime_state.db_path)
        self.memory_plane = memory_plane or SovereignMemoryPlaneAdapter(
            runtime_state=self.runtime_state,
            event_store=self.event_store,
        )

    async def record_evaluation(self, record: EvaluationRecord) -> EvaluationRecord:
        await _ensure_intelligence_schema(self.runtime_state)
        resolved = await self._resolve_binding(record)
        resolved = replace(resolved, evaluation_id=resolved.evaluation_id or _new_id("eval"))
        now = _utc_now_iso()

        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO intelligence_evaluation_records"
                " (evaluation_id, subject_kind, subject_id, evaluator, metric, score,"
                " session_id, task_id, run_id, evidence_refs_json, metadata_json, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    resolved.evaluation_id,
                    resolved.subject_kind,
                    resolved.subject_id,
                    resolved.evaluator,
                    resolved.metric,
                    float(resolved.score),
                    resolved.session_id,
                    resolved.task_id,
                    resolved.run_id,
                    _json_dump(list(resolved.evidence_refs)),
                    _json_dump(resolved.metadata),
                    now,
                ),
            )
            await db.commit()

        await self.memory_plane.write_memory(
            MemoryRecord(
                record_id=self.runtime_state.new_fact_id(),
                kind="evaluation_metric",
                text=(
                    f"Evaluation {resolved.metric} for {resolved.subject_kind}"
                    f" {resolved.subject_id} scored {float(resolved.score):.3f}."
                ),
                truth_state=MemoryTruthState.PROMOTED,
                session_id=resolved.session_id,
                task_id=resolved.task_id,
                agent_id=resolved.evaluator,
                score=max(0.0, min(float(resolved.score), 1.0)),
                metadata={
                    "evaluation_id": resolved.evaluation_id,
                    "subject_kind": resolved.subject_kind,
                    "subject_id": resolved.subject_id,
                    "metric": resolved.metric,
                    "score": float(resolved.score),
                    "evidence_refs": list(resolved.evidence_refs),
                    **resolved.metadata,
                },
                provenance={"run_id": resolved.run_id},
            )
        )
        await self._emit_event(resolved)
        return resolved

    async def list_evaluations(
        self,
        *,
        subject_kind: str | None = None,
        subject_id: str | None = None,
        metric: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationRecord]:
        await _ensure_intelligence_schema(self.runtime_state)
        query = (
            "SELECT evaluation_id, subject_kind, subject_id, evaluator, metric, score,"
            " session_id, task_id, run_id, evidence_refs_json, metadata_json, recorded_at"
            " FROM intelligence_evaluation_records WHERE 1=1"
        )
        params: list[Any] = []
        if subject_kind is not None:
            query += " AND subject_kind = ?"
            params.append(subject_kind)
        if subject_id is not None:
            query += " AND subject_id = ?"
            params.append(subject_id)
        if metric is not None:
            query += " AND metric = ?"
            params.append(metric)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(max(limit, 1))

        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_evaluation(row) for row in rows]

    async def summarize_subject(
        self,
        *,
        subject_kind: str,
        subject_id: str,
    ) -> dict[str, Any]:
        rows = await self.list_evaluations(
            subject_kind=subject_kind,
            subject_id=subject_id,
            limit=500,
        )
        if not rows:
            return {
                "subject_kind": subject_kind,
                "subject_id": subject_id,
                "evaluation_count": 0,
                "metrics": {},
            }

        metrics: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = metrics.setdefault(
                row.metric,
                {"count": 0, "avg_score": 0.0, "max_score": float(row.score), "latest_score": float(row.score)},
            )
            bucket["count"] += 1
            bucket["avg_score"] += float(row.score)
            bucket["max_score"] = max(bucket["max_score"], float(row.score))
            bucket["latest_score"] = float(row.score)
        for metric_bucket in metrics.values():
            metric_bucket["avg_score"] = round(
                metric_bucket["avg_score"] / max(metric_bucket["count"], 1),
                4,
            )

        average_score = sum(float(row.score) for row in rows) / max(len(rows), 1)
        return {
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "evaluation_count": len(rows),
            "average_score": round(average_score, 4),
            "latest_evaluation_id": rows[0].evaluation_id,
            "metrics": metrics,
        }

    async def _resolve_binding(self, record: EvaluationRecord) -> EvaluationRecord:
        if not record.run_id:
            return record
        run = await self.runtime_state.get_delegation_run(record.run_id)
        if run is None:
            raise KeyError(f"delegation run {record.run_id} not found")
        return replace(
            record,
            session_id=record.session_id or run.session_id,
            task_id=record.task_id or run.task_id,
        )

    async def _emit_event(self, record: EvaluationRecord) -> None:
        if not record.session_id:
            return
        envelope = RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="contracts.intelligence.evaluations",
            agent_id=record.evaluator,
            session_id=record.session_id,
            trace_id=record.run_id or record.task_id or record.evaluation_id,
            payload={
                "action_name": "record_evaluation",
                "decision": "recorded",
                "confidence": max(0.0, min(float(record.score), 1.0)),
                "evaluation_id": record.evaluation_id,
                "subject_kind": record.subject_kind,
                "subject_id": record.subject_id,
                "metric": record.metric,
                "task_id": record.task_id,
                "run_id": record.run_id,
            },
        )
        await self.event_store.ingest_envelope(envelope)


class SovereignLearningEngineAdapter(LearningEngine):
    """Learning adapter grounded in task evidence, skill discovery, and evals."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        event_store: EventMemoryStore | None = None,
        memory_plane: MemoryPlane | None = None,
        skill_store: SkillStore | None = None,
        evaluation_sink: EvaluationSink | None = None,
        skill_dirs: list[Path] | None = None,
    ) -> None:
        self.runtime_state = runtime_state or RuntimeStateStore()
        self.event_store = event_store or EventMemoryStore(self.runtime_state.db_path)
        self.memory_plane = memory_plane or SovereignMemoryPlaneAdapter(
            runtime_state=self.runtime_state,
            event_store=self.event_store,
        )
        self.skill_store = skill_store or SovereignSkillStoreAdapter(
            runtime_state=self.runtime_state,
            skill_dirs=skill_dirs,
        )
        self.evaluation_sink = evaluation_sink or SovereignEvaluationSinkAdapter(
            runtime_state=self.runtime_state,
            event_store=self.event_store,
            memory_plane=self.memory_plane,
        )
        self.skill_registry = SkillRegistry(skill_dirs=skill_dirs)

    async def extract_skill_candidates(
        self,
        *,
        session_id: str = "",
        run_id: str = "",
        task_id: str = "",
    ) -> list[SkillArtifact]:
        resolved_session_id, resolved_task_id = await self._resolve_scope(
            session_id=session_id,
            run_id=run_id,
            task_id=task_id,
        )
        evidence = await self._task_evidence_text(
            session_id=resolved_session_id,
            task_id=resolved_task_id,
            run_id=run_id,
        )
        if not evidence.strip():
            return []

        matches = self.skill_registry.match(evidence, top_k=3)
        candidates: list[SkillArtifact] = []
        for match in matches:
            digest = hashlib.sha256(
                f"{run_id}|{resolved_session_id}|{resolved_task_id}|{match.name}".encode("utf-8")
            ).hexdigest()[:12]
            candidates.append(
                SkillArtifact(
                    skill_id=f"skillcand_{digest}",
                    name=match.name,
                    version="candidate-v1",
                    description=(
                        f"{match.description or match.name} Learned candidate from"
                        f" task evidence in {resolved_task_id or resolved_session_id or run_id}."
                    ),
                    promotion_state=SkillPromotionState.CANDIDATE,
                    source_run_id=run_id,
                    metadata={
                        "source": "learning_engine",
                        "matched_skill_id": f"registry:{match.name}",
                        "session_id": resolved_session_id,
                        "task_id": resolved_task_id,
                        "evidence_preview": evidence[:240],
                        "keywords": list(match.keywords),
                        "tags": list(match.tags),
                    },
                )
            )
        return candidates

    async def update_user_model(
        self,
        *,
        user_id: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._update_model("user", user_id, evidence)

    async def update_agent_model(
        self,
        *,
        agent_id: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._update_model("agent", agent_id, evidence)

    async def propose_routing_hints(
        self,
        *,
        task_id: str,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        evidence_text = await self._task_evidence_text(
            session_id=session_id,
            task_id=task_id,
            run_id="",
        )
        hints: list[dict[str, Any]] = []
        for index, skill in enumerate(self.skill_registry.match(evidence_text, top_k=3)):
            hints.append(
                {
                    "kind": "skill_match",
                    "skill_id": f"registry:{skill.name}",
                    "skill_name": skill.name,
                    "preferred_role": skill.name,
                    "confidence": round(max(0.2, 0.9 - (index * 0.2)), 3),
                    "source": "skill_registry",
                }
            )

        evaluations = await self.evaluation_sink.list_evaluations(
            subject_kind="task",
            subject_id=task_id,
            limit=20,
        )
        for evaluation in evaluations:
            preferred_roles = _coerce_string_list(evaluation.metadata.get("preferred_roles"))
            preferred_roles.extend(_coerce_string_list(evaluation.metadata.get("preferred_role")))
            for role in preferred_roles:
                hints.append(
                    {
                        "kind": "evaluation_preference",
                        "preferred_role": role,
                        "confidence": max(0.0, min(float(evaluation.score), 1.0)),
                        "metric": evaluation.metric,
                        "evaluation_id": evaluation.evaluation_id,
                        "source": "evaluation_sink",
                    }
                )
            recommended_model = str(evaluation.metadata.get("recommended_model") or "").strip()
            if recommended_model:
                hints.append(
                    {
                        "kind": "model_recommendation",
                        "recommended_model": recommended_model,
                        "recommended_provider": str(
                            evaluation.metadata.get("recommended_provider") or ""
                        ).strip(),
                        "confidence": max(0.0, min(float(evaluation.score), 1.0)),
                        "metric": evaluation.metric,
                        "evaluation_id": evaluation.evaluation_id,
                        "source": "evaluation_sink",
                    }
                )

        ranked = sorted(
            _dedupe_dict_rows(hints),
            key=lambda row: float(row.get("confidence", 0.0)),
            reverse=True,
        )
        return ranked[:10]

    async def _update_model(
        self,
        entity_kind: str,
        entity_id: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        await _ensure_intelligence_schema(self.runtime_state)
        current = await self._get_model_snapshot(entity_kind, entity_id)
        now = _utc_now_iso()
        history = list(current.get("history", []))
        history.append({"recorded_at": now, "evidence": dict(evidence)})
        history = history[-20:]

        preferred_roles = _coerce_string_list(current.get("preferred_roles"))
        preferred_roles.extend(_coerce_string_list(evidence.get("preferred_roles")))
        preferred_skills = _coerce_string_list(current.get("preferred_skills"))
        preferred_skills.extend(_coerce_string_list(evidence.get("preferred_skills")))
        merged_preferences = dict(current.get("preferences", {}))
        if isinstance(evidence.get("preferences"), dict):
            merged_preferences.update(dict(evidence["preferences"]))
        traits = dict(current.get("traits", {}))
        if isinstance(evidence.get("traits"), dict):
            traits.update(dict(evidence["traits"]))

        snapshot = {
            "entity_kind": entity_kind,
            "entity_id": entity_id,
            "update_count": int(current.get("update_count", 0)) + 1,
            "updated_at": now,
            "latest_evidence": dict(evidence),
            "history": history,
            "preferred_roles": sorted(set(preferred_roles)),
            "preferred_skills": sorted(set(preferred_skills)),
            "preferences": merged_preferences,
            "traits": traits,
        }

        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO intelligence_model_snapshots"
                " (entity_kind, entity_id, state_json, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (entity_kind, entity_id, _json_dump(snapshot), now),
            )
            await db.commit()

        summary_bits = []
        if snapshot["preferred_roles"]:
            summary_bits.append(f"preferred_roles={','.join(snapshot['preferred_roles'])}")
        if snapshot["preferred_skills"]:
            summary_bits.append(f"preferred_skills={','.join(snapshot['preferred_skills'])}")
        if not summary_bits:
            summary_bits.append(f"keys={','.join(sorted(evidence.keys()))}")
        await self.memory_plane.write_memory(
            MemoryRecord(
                record_id=self.runtime_state.new_fact_id(),
                kind=f"{entity_kind}_model",
                text=f"{entity_kind.capitalize()} {entity_id} model updated with {'; '.join(summary_bits)}.",
                truth_state=MemoryTruthState.PROMOTED,
                session_id=str(evidence.get("session_id") or ""),
                task_id=str(evidence.get("task_id") or ""),
                agent_id=entity_id if entity_kind == "agent" else "",
                score=1.0,
                metadata={
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                    "update_count": snapshot["update_count"],
                    **dict(evidence),
                },
                provenance={"model_table": "intelligence_model_snapshots"},
            )
        )
        return snapshot

    async def _get_model_snapshot(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        await _ensure_intelligence_schema(self.runtime_state)
        async with aiosqlite.connect(self.runtime_state.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT state_json FROM intelligence_model_snapshots"
                    " WHERE entity_kind = ? AND entity_id = ?",
                    (entity_kind, entity_id),
                )
            ).fetchone()
        if row is None:
            return {}
        payload = _json_load(str(row["state_json"]), {})
        return dict(payload) if isinstance(payload, dict) else {}

    async def _resolve_scope(
        self,
        *,
        session_id: str,
        run_id: str,
        task_id: str,
    ) -> tuple[str, str]:
        resolved_session_id = session_id
        resolved_task_id = task_id
        if run_id:
            run = await self.runtime_state.get_delegation_run(run_id)
            if run is None:
                raise KeyError(f"delegation run {run_id} not found")
            resolved_session_id = resolved_session_id or run.session_id
            resolved_task_id = resolved_task_id or run.task_id
        if resolved_session_id and not resolved_task_id:
            session = await self.runtime_state.get_session(resolved_session_id)
            if session is not None:
                resolved_task_id = session.current_task_id
        return resolved_session_id, resolved_task_id

    async def _task_evidence_text(
        self,
        *,
        session_id: str,
        task_id: str,
        run_id: str,
    ) -> str:
        records = await self.memory_plane.query_memory(
            session_id=session_id or None,
            task_id=task_id or None,
            limit=50,
        )
        artifacts = await self.runtime_state.list_artifacts(
            session_id=session_id or None,
            task_id=task_id or None,
            run_id=run_id or None,
            limit=20,
        )
        evaluations = []
        if task_id:
            evaluations = await self.evaluation_sink.list_evaluations(
                subject_kind="task",
                subject_id=task_id,
                limit=20,
            )

        chunks = [record.text for record in records]
        chunks.extend(artifact.artifact_kind for artifact in artifacts)
        chunks.extend(
            f"{row.metric} {row.score} {' '.join(_coerce_string_list(row.metadata.get('preferred_roles')))}"
            for row in evaluations
        )
        return " ".join(chunk for chunk in chunks if chunk).strip()


__all__ = [
    "SovereignEvaluationSinkAdapter",
    "SovereignLearningEngineAdapter",
    "SovereignMemoryPlaneAdapter",
    "SovereignSkillStoreAdapter",
]
