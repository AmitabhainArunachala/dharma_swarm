"""Factory and service entrypoints for sovereign intelligence adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.runtime_state import RuntimeStateStore

from .common import EvaluationRecord, SkillArtifact
from .intelligence_evaluation_services import (
    SovereignEvaluationRecorder,
    SovereignEvaluationRegistrationResult,
    build_sovereign_evaluation_recorder,
)
from .intelligence_kaizenops import (
    evaluation_registration_to_kaizenops_event,
    export_evaluation_registration_to_kaizenops,
)
from .intelligence_telemetry import (
    SovereignEvaluationTelemetryExportResult,
    evaluation_registration_to_telemetry_records,
    export_evaluation_registration_to_telemetry,
)
from .intelligence import EvaluationSink, LearningEngine, MemoryPlane, SkillStore
from .intelligence_adapters import (
    SovereignEvaluationSinkAdapter,
    SovereignLearningEngineAdapter,
    SovereignMemoryPlaneAdapter,
    SovereignSkillStoreAdapter,
)


@dataclass(frozen=True, slots=True)
class SovereignIntelligenceLayer:
    """Bundled sovereign intelligence interfaces sharing one backing store."""

    memory: MemoryPlane
    learning: LearningEngine
    skills: SkillStore
    evaluations: EvaluationSink


@dataclass(frozen=True, slots=True)
class SovereignTaskFeedbackResult:
    """Result of a production-facing task-feedback ingestion slice."""

    evaluation: EvaluationRecord
    saved_skills: tuple[SkillArtifact, ...] = ()
    routing_hints: tuple[dict[str, Any], ...] = ()
    extracted_candidates: tuple[SkillArtifact, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SovereignSkillRoutingRecord:
    """Lightweight skill view compatible with routing code."""

    name: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class SovereignSkillRegistryView:
    """Compatibility view that lets callers route through sovereign skills."""

    def __init__(self, skills: list[SovereignSkillRoutingRecord]) -> None:
        self._skills = list(skills)

    def discover(self) -> dict[str, SovereignSkillRoutingRecord]:
        return {skill.name: skill for skill in self._skills}

    def list_all(self) -> list[SovereignSkillRoutingRecord]:
        return list(self._skills)

    def get(self, name: str) -> SovereignSkillRoutingRecord | None:
        for skill in self._skills:
            if skill.name == name:
                return skill
        return None

    def match(self, query: str, top_k: int = 3) -> list[SovereignSkillRoutingRecord]:
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored: list[tuple[float, SovereignSkillRoutingRecord]] = []

        for skill in self._skills:
            score = 0.0
            if skill.name.lower() in query_lower:
                score += 10.0
            for keyword in skill.keywords:
                if keyword.lower() in query_lower:
                    score += 3.0
            for tag in skill.tags:
                if tag.lower() in query_lower:
                    score += 2.0
            overlap = len(query_words & set(skill.description.lower().split()))
            score += overlap * 0.5
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [skill for _, skill in scored[:top_k]]


def build_sovereign_intelligence_layer(
    *,
    db_path: Path | str | None = None,
    skill_dirs: list[Path] | None = None,
    runtime_state: RuntimeStateStore | None = None,
    event_store: EventMemoryStore | None = None,
) -> SovereignIntelligenceLayer:
    """Build the shared sovereign intelligence adapter stack."""

    resolved_runtime_state = runtime_state or RuntimeStateStore(db_path)
    resolved_event_store = event_store or EventMemoryStore(resolved_runtime_state.db_path)
    memory = SovereignMemoryPlaneAdapter(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
    )
    skills = SovereignSkillStoreAdapter(
        runtime_state=resolved_runtime_state,
        skill_dirs=skill_dirs,
    )
    evaluations = SovereignEvaluationSinkAdapter(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
        memory_plane=memory,
    )
    learning = SovereignLearningEngineAdapter(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
        memory_plane=memory,
        skill_store=skills,
        evaluation_sink=evaluations,
        skill_dirs=skill_dirs,
    )
    return SovereignIntelligenceLayer(
        memory=memory,
        learning=learning,
        skills=skills,
        evaluations=evaluations,
    )


async def load_sovereign_skill_registry_view(
    *,
    layer: SovereignIntelligenceLayer | None = None,
    db_path: Path | str | None = None,
    skill_dirs: list[Path] | None = None,
    runtime_state: RuntimeStateStore | None = None,
    event_store: EventMemoryStore | None = None,
) -> SovereignSkillRegistryView:
    """Materialize a sovereign-backed skill registry compatibility view."""

    resolved_layer = layer or build_sovereign_intelligence_layer(
        db_path=db_path,
        skill_dirs=skill_dirs,
        runtime_state=runtime_state,
        event_store=event_store,
    )
    rows = await resolved_layer.skills.list_skills(limit=500)
    by_name: dict[str, SovereignSkillRoutingRecord] = {}
    for row in rows:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        by_name[row.name] = SovereignSkillRoutingRecord(
            name=row.name,
            description=row.description,
            keywords=tuple(
                str(item).strip()
                for item in metadata.get("keywords", [])
                if str(item).strip()
            ),
            tags=tuple(
                str(item).strip()
                for item in metadata.get("tags", [])
                if str(item).strip()
            ),
            metadata=dict(metadata),
        )
    return SovereignSkillRegistryView(list(by_name.values()))


class SovereignTaskFeedbackService:
    """Production-facing caller path that only targets sovereign interfaces."""

    def __init__(self, layer: SovereignIntelligenceLayer) -> None:
        self._layer = layer

    async def ingest_task_feedback(
        self,
        *,
        evaluation: EvaluationRecord,
        persist_candidates: bool = True,
    ) -> SovereignTaskFeedbackResult:
        stored_evaluation = await self._layer.evaluations.record_evaluation(evaluation)
        candidates = await self._layer.learning.extract_skill_candidates(
            session_id=stored_evaluation.session_id,
            run_id=stored_evaluation.run_id,
            task_id=stored_evaluation.task_id,
        )
        saved_skills: list[SkillArtifact] = []
        if persist_candidates:
            for candidate in candidates:
                saved_skills.append(await self._layer.skills.save_skill(candidate))
        routing_hints = await self._layer.learning.propose_routing_hints(
            task_id=stored_evaluation.task_id,
            session_id=stored_evaluation.session_id,
        )
        return SovereignTaskFeedbackResult(
            evaluation=stored_evaluation,
            saved_skills=tuple(saved_skills),
            routing_hints=tuple(routing_hints),
            extracted_candidates=tuple(candidates),
            metadata={
                "persist_candidates": persist_candidates,
                "session_id": stored_evaluation.session_id,
                "task_id": stored_evaluation.task_id,
            },
        )


def build_sovereign_task_feedback_service(
    *,
    db_path: Path | str | None = None,
    skill_dirs: list[Path] | None = None,
    runtime_state: RuntimeStateStore | None = None,
    event_store: EventMemoryStore | None = None,
) -> SovereignTaskFeedbackService:
    """Convenience entrypoint for the default production-facing feedback slice."""

    return SovereignTaskFeedbackService(
        build_sovereign_intelligence_layer(
            db_path=db_path,
            skill_dirs=skill_dirs,
            runtime_state=runtime_state,
            event_store=event_store,
        )
    )


__all__ = [
    "SovereignEvaluationRecorder",
    "SovereignEvaluationRegistrationResult",
    "SovereignEvaluationTelemetryExportResult",
    "SovereignIntelligenceLayer",
    "SovereignSkillRegistryView",
    "SovereignSkillRoutingRecord",
    "SovereignTaskFeedbackResult",
    "SovereignTaskFeedbackService",
    "build_sovereign_evaluation_recorder",
    "build_sovereign_intelligence_layer",
    "build_sovereign_task_feedback_service",
    "evaluation_registration_to_kaizenops_event",
    "evaluation_registration_to_telemetry_records",
    "export_evaluation_registration_to_kaizenops",
    "export_evaluation_registration_to_telemetry",
    "load_sovereign_skill_registry_view",
]
