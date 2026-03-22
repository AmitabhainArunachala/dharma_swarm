"""Compatibility services for sovereign evaluation-side caller adoption."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any
from uuid import uuid4

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.engine.provenance import ProvenanceEntry, ProvenanceLogger
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import ArtifactRecord, DelegationRun, MemoryFact, RuntimeStateStore

from .common import EvaluationRecord, MemoryRecord, MemoryTruthState
from .intelligence import EvaluationSink, MemoryPlane
from .intelligence_adapters import SovereignEvaluationSinkAdapter, SovereignMemoryPlaneAdapter


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _json_render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, indent=2)


def _coerce_text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(float(text))
        except ValueError:
            return default
    return default


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


@dataclass(frozen=True, slots=True)
class SovereignEvaluationRegistrationResult:
    """Registry-compatible receipt shape backed by sovereign contracts."""

    artifact: ArtifactRecord
    manifest_path: Path
    facts: tuple[MemoryFact, ...]
    receipt: dict[str, Any]
    summary: dict[str, Any] = field(default_factory=dict)
    evaluation: EvaluationRecord | None = None


@dataclass(frozen=True, slots=True)
class _ResolvedBinding:
    run_id: str
    session_id: str
    task_id: str
    trace_id: str
    run: DelegationRun | None = None


class SovereignEvaluationRecorder:
    """Compatibility recorder that persists through sovereign contracts."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        event_store: EventMemoryStore | None = None,
        memory_plane: MemoryPlane | None = None,
        evaluation_sink: EvaluationSink | None = None,
        artifact_store: RuntimeArtifactStore | None = None,
        provenance: ProvenanceLogger | None = None,
    ) -> None:
        self.runtime_state = runtime_state or RuntimeStateStore()
        self.event_store = event_store or EventMemoryStore(self.runtime_state.db_path)
        self.memory_plane = memory_plane or SovereignMemoryPlaneAdapter(
            runtime_state=self.runtime_state,
            event_store=self.event_store,
        )
        self.evaluation_sink = evaluation_sink or SovereignEvaluationSinkAdapter(
            runtime_state=self.runtime_state,
            event_store=self.event_store,
            memory_plane=self.memory_plane,
        )
        self.artifact_store = artifact_store or RuntimeArtifactStore(
            runtime_state=self.runtime_state,
        )
        self.provenance = provenance

    async def record_flywheel_job(
        self,
        job_payload: dict[str, Any],
        *,
        job_id: str | None = None,
        workload_id: str | None = None,
        client_id: str | None = None,
        run_id: str = "",
        session_id: str = "",
        task_id: str = "",
        trace_id: str | None = None,
        created_by: str = "contracts.intelligence",
        promotion_state: str = "shared",
    ) -> SovereignEvaluationRegistrationResult:
        del promotion_state

        resolved_job_id = _coerce_text(job_id or job_payload.get("id") or job_payload.get("job_id"))
        if not resolved_job_id:
            raise ValueError("job payload missing id/job_id")
        resolved_workload_id = _coerce_text(workload_id or job_payload.get("workload_id"))
        resolved_client_id = _coerce_text(client_id or job_payload.get("client_id"))
        status = _coerce_text(job_payload.get("status"), default="unknown")
        binding = await self._resolve_binding(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            payload=job_payload,
            fallback_trace_id=resolved_job_id,
        )
        receipt_event_id = _new_id("evt")

        stored = await self.artifact_store.create_text_artifact_async(
            session_id=binding.session_id,
            artifact_type="evaluations",
            artifact_kind="flywheel_job_result",
            content=_json_render(job_payload),
            created_by=created_by,
            extension="json",
            task_id=binding.task_id,
            run_id=binding.run_id,
            trace_id=binding.trace_id,
            promotion_state="shared",
            provenance={
                "source": "data_flywheel",
                "job_id": resolved_job_id,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
            },
            metadata={
                "source": "data_flywheel",
                "job_id": resolved_job_id,
                "status": status,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
            },
        )
        artifact = stored.record

        evaluation = await self.evaluation_sink.record_evaluation(
            EvaluationRecord(
                evaluation_id="",
                subject_kind="flywheel_job",
                subject_id=resolved_job_id,
                evaluator=created_by,
                metric="job_health",
                score=self._flywheel_score(status),
                session_id=binding.session_id,
                task_id=binding.task_id,
                run_id=binding.run_id,
                evidence_refs=(artifact.artifact_id,),
                metadata={
                    "artifact_id": artifact.artifact_id,
                    "job_id": resolved_job_id,
                    "status": status,
                    "workload_id": resolved_workload_id,
                    "client_id": resolved_client_id,
                    "receipt_event_id": receipt_event_id,
                },
            )
        )

        facts: list[MemoryFact] = []
        facts.append(
            await self._write_fact(
                kind="evaluation_status",
                text=self._flywheel_status_text(
                    job_id=resolved_job_id,
                    workload_id=resolved_workload_id,
                    status=status,
                ),
                truth_state=MemoryTruthState.PROMOTED,
                score=self._flywheel_score(status),
                session_id=binding.session_id,
                task_id=binding.task_id,
                agent_id=created_by,
                metadata={
                    "job_id": resolved_job_id,
                    "status": status,
                    "workload_id": resolved_workload_id,
                    "client_id": resolved_client_id,
                    "source": "data_flywheel",
                },
                provenance={
                    "source_artifact_id": artifact.artifact_id,
                    "source_event_id": receipt_event_id,
                    "run_id": binding.run_id,
                },
            )
        )
        for recommendation in self._flywheel_recommendations(
            job_payload,
            workload_id=resolved_workload_id,
            client_id=resolved_client_id,
        ):
            facts.append(
                await self._write_fact(
                    kind="provider_recommendation",
                    text=str(recommendation["text"]),
                    truth_state=MemoryTruthState.CANDIDATE,
                    score=float(recommendation["confidence"]),
                    session_id=binding.session_id,
                    task_id=binding.task_id,
                    agent_id=created_by,
                    metadata=dict(recommendation["metadata"]),
                    provenance={
                        "source_artifact_id": artifact.artifact_id,
                        "source_event_id": receipt_event_id,
                        "run_id": binding.run_id,
                    },
                )
            )

        summary = {
            "job_id": resolved_job_id,
            "workload_id": resolved_workload_id,
            "client_id": resolved_client_id,
            "status": status,
            "artifact_id": artifact.artifact_id,
            "fact_ids": [fact.fact_id for fact in facts],
            "receipt_event_id": receipt_event_id,
        }
        receipt = await self._emit_receipt(
            event_id=receipt_event_id,
            action_name="record_flywheel_job_result",
            session_id=binding.session_id,
            trace_id=binding.trace_id,
            agent_id=created_by,
            payload={
                "job_id": resolved_job_id,
                "artifact_id": artifact.artifact_id,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
                "status": status,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
                "evaluation_id": evaluation.evaluation_id,
                "fact_ids": summary["fact_ids"],
            },
        )
        self._append_provenance(
            event="flywheel_job_recorded",
            artifact_id=artifact.artifact_id,
            agent=created_by,
            session_id=binding.session_id,
            inputs=[resolved_job_id],
            outputs=[artifact.artifact_id, evaluation.evaluation_id, *summary["fact_ids"]],
            confidence=self._flywheel_score(status),
            metadata={
                "job_id": resolved_job_id,
                "status": status,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
            },
        )
        return SovereignEvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=tuple(facts),
            receipt=receipt,
            summary=summary,
            evaluation=evaluation,
        )

    async def record_reciprocity_summary(
        self,
        summary_payload: dict[str, Any],
        *,
        run_id: str = "",
        session_id: str = "",
        task_id: str = "",
        trace_id: str | None = None,
        created_by: str = "contracts.intelligence",
        promotion_state: str = "shared",
    ) -> SovereignEvaluationRegistrationResult:
        del promotion_state

        service = _coerce_text(
            summary_payload.get("service") or summary_payload.get("source"),
            default="reciprocity_commons",
        )
        summary_type = _coerce_text(summary_payload.get("summary_type"), default="ledger_summary")
        actors = _coerce_int(summary_payload.get("actors"))
        activities = _coerce_int(summary_payload.get("activities"))
        projects = _coerce_int(summary_payload.get("projects"))
        obligations = _coerce_int(summary_payload.get("obligations"))
        active_obligations = _coerce_int(summary_payload.get("active_obligations"))
        challenged_claims = _coerce_int(summary_payload.get("challenged_claims"))
        invariant_issues = _coerce_int(summary_payload.get("invariant_issues"))
        chain_valid = _coerce_bool(summary_payload.get("chain_valid"), default=True)
        total_obligation_usd = _coerce_float(summary_payload.get("total_obligation_usd"))
        total_routed_usd = _coerce_float(summary_payload.get("total_routed_usd"))
        issue_codes = self._issue_codes(summary_payload)
        binding = await self._resolve_binding(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            payload=summary_payload,
            fallback_trace_id=f"{service}:{summary_type}",
        )
        receipt_event_id = _new_id("evt")

        normalized_payload = {
            "source": service,
            "summary_type": summary_type,
            "actors": actors,
            "activities": activities,
            "projects": projects,
            "obligations": obligations,
            "active_obligations": active_obligations,
            "challenged_claims": challenged_claims,
            "invariant_issues": invariant_issues,
            "chain_valid": chain_valid,
            "total_obligation_usd": total_obligation_usd,
            "total_routed_usd": total_routed_usd,
            "issue_codes": issue_codes,
        }
        stored = await self.artifact_store.create_text_artifact_async(
            session_id=binding.session_id,
            artifact_type="evaluations",
            artifact_kind="reciprocity_ledger_summary",
            content=_json_render(normalized_payload),
            created_by=created_by,
            extension="json",
            task_id=binding.task_id,
            run_id=binding.run_id,
            trace_id=binding.trace_id,
            promotion_state="shared",
            provenance={
                "source": service,
                "summary_type": summary_type,
            },
            metadata=dict(normalized_payload),
        )
        artifact = stored.record

        integrity_score = self._reciprocity_score(
            chain_valid=chain_valid,
            challenged_claims=challenged_claims,
            invariant_issues=invariant_issues,
        )
        evaluation = await self.evaluation_sink.record_evaluation(
            EvaluationRecord(
                evaluation_id="",
                subject_kind="reciprocity_summary",
                subject_id=f"{service}:{summary_type}",
                evaluator=created_by,
                metric="integrity",
                score=integrity_score,
                session_id=binding.session_id,
                task_id=binding.task_id,
                run_id=binding.run_id,
                evidence_refs=(artifact.artifact_id,),
                metadata={
                    **normalized_payload,
                    "artifact_id": artifact.artifact_id,
                    "receipt_event_id": receipt_event_id,
                },
            )
        )

        facts: list[MemoryFact] = []
        facts.append(
            await self._write_fact(
                kind="reciprocity_summary",
                text=self._reciprocity_summary_text(
                    actors=actors,
                    activities=activities,
                    projects=projects,
                    obligations=obligations,
                    active_obligations=active_obligations,
                    challenged_claims=challenged_claims,
                    total_obligation_usd=total_obligation_usd,
                    total_routed_usd=total_routed_usd,
                    chain_valid=chain_valid,
                ),
                truth_state=MemoryTruthState.PROMOTED,
                score=integrity_score,
                session_id=binding.session_id,
                task_id=binding.task_id,
                agent_id=created_by,
                metadata=dict(normalized_payload),
                provenance={
                    "source_artifact_id": artifact.artifact_id,
                    "source_event_id": receipt_event_id,
                    "run_id": binding.run_id,
                },
            )
        )
        if issue_codes or challenged_claims or invariant_issues or not chain_valid:
            facts.append(
                await self._write_fact(
                    kind="reciprocity_issue",
                    text=self._reciprocity_issue_text(
                        chain_valid=chain_valid,
                        invariant_issues=invariant_issues,
                        challenged_claims=challenged_claims,
                        issue_codes=issue_codes,
                    ),
                    truth_state=MemoryTruthState.CANDIDATE,
                    score=max(0.2, 1.0 - integrity_score),
                    session_id=binding.session_id,
                    task_id=binding.task_id,
                    agent_id=created_by,
                    metadata=dict(normalized_payload),
                    provenance={
                        "source_artifact_id": artifact.artifact_id,
                        "source_event_id": receipt_event_id,
                        "run_id": binding.run_id,
                    },
                )
            )

        summary = {
            "source": service,
            "summary_type": summary_type,
            "artifact_id": artifact.artifact_id,
            "fact_ids": [fact.fact_id for fact in facts],
            "receipt_event_id": receipt_event_id,
            "chain_valid": chain_valid,
            "invariant_issues": invariant_issues,
            "challenged_claims": challenged_claims,
        }
        receipt = await self._emit_receipt(
            event_id=receipt_event_id,
            action_name="record_reciprocity_summary",
            session_id=binding.session_id,
            trace_id=binding.trace_id,
            agent_id=created_by,
            payload={
                "source": service,
                "summary_type": summary_type,
                "artifact_id": artifact.artifact_id,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
                "evaluation_id": evaluation.evaluation_id,
                "chain_valid": chain_valid,
                "invariant_issues": invariant_issues,
                "challenged_claims": challenged_claims,
                "fact_ids": summary["fact_ids"],
            },
        )
        self._append_provenance(
            event="reciprocity_summary_recorded",
            artifact_id=artifact.artifact_id,
            agent=created_by,
            session_id=binding.session_id,
            inputs=[summary_type],
            outputs=[artifact.artifact_id, evaluation.evaluation_id, *summary["fact_ids"]],
            confidence=integrity_score,
            metadata={
                "source": service,
                "summary_type": summary_type,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
                "chain_valid": chain_valid,
                "invariant_issues": invariant_issues,
                "challenged_claims": challenged_claims,
            },
        )
        return SovereignEvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=tuple(facts),
            receipt=receipt,
            summary=summary,
            evaluation=evaluation,
        )

    async def record_ouroboros_observation(
        self,
        observation_payload: dict[str, Any],
        *,
        run_id: str = "",
        session_id: str = "",
        task_id: str = "",
        trace_id: str | None = None,
        created_by: str = "contracts.intelligence",
        promotion_state: str = "shared",
    ) -> SovereignEvaluationRegistrationResult:
        del promotion_state

        signature = observation_payload.get("signature")
        if not isinstance(signature, dict):
            signature = {}
        modifiers = observation_payload.get("modifiers")
        if not isinstance(modifiers, dict):
            modifiers = {}

        source = _coerce_text(observation_payload.get("source"), default="ouroboros")
        cycle_id = _coerce_text(observation_payload.get("cycle_id"))
        recognition_type = _coerce_text(signature.get("recognition_type"), default="unknown")
        entropy = _clamp_score(_coerce_float(signature.get("entropy")))
        swabhaav_ratio = _clamp_score(_coerce_float(signature.get("swabhaav_ratio")))
        quality = _clamp_score(_coerce_float(modifiers.get("quality"), default=swabhaav_ratio))
        mimicry_penalty = _coerce_float(modifiers.get("mimicry_penalty"), default=1.0)
        recognition_bonus = _coerce_float(modifiers.get("recognition_bonus"), default=1.0)
        witness_score = _clamp_score(
            _coerce_float(modifiers.get("witness_score"), default=swabhaav_ratio)
        )
        is_mimicry = _coerce_bool(
            observation_payload.get("is_mimicry"),
            default=mimicry_penalty < 1.0,
        )
        is_genuine = _coerce_bool(
            observation_payload.get("is_genuine"),
            default=recognition_type.upper() == "GENUINE",
        )
        binding = await self._resolve_binding(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            payload=observation_payload,
            fallback_trace_id=f"{source}:{cycle_id or recognition_type or 'latest'}",
        )
        receipt_event_id = _new_id("evt")

        stored = await self.artifact_store.create_text_artifact_async(
            session_id=binding.session_id,
            artifact_type="evaluations",
            artifact_kind="ouroboros_behavioral_observation",
            content=_json_render(observation_payload),
            created_by=created_by,
            extension="json",
            task_id=binding.task_id,
            run_id=binding.run_id,
            trace_id=binding.trace_id,
            promotion_state="shared",
            provenance={
                "source": source,
                "cycle_id": cycle_id,
                "recognition_type": recognition_type,
            },
            metadata={
                "source": source,
                "cycle_id": cycle_id,
                "recognition_type": recognition_type,
                "entropy": entropy,
                "swabhaav_ratio": swabhaav_ratio,
                "quality": quality,
                "mimicry_penalty": mimicry_penalty,
                "recognition_bonus": recognition_bonus,
                "witness_score": witness_score,
                "is_mimicry": is_mimicry,
                "is_genuine": is_genuine,
            },
        )
        artifact = stored.record

        behavioral_score = self._ouroboros_score(
            quality=quality,
            witness_score=witness_score,
            is_mimicry=is_mimicry,
            is_genuine=is_genuine,
        )
        evaluation = await self.evaluation_sink.record_evaluation(
            EvaluationRecord(
                evaluation_id="",
                subject_kind="ouroboros_observation",
                subject_id=cycle_id or source,
                evaluator=created_by,
                metric="behavioral_quality",
                score=behavioral_score,
                session_id=binding.session_id,
                task_id=binding.task_id,
                run_id=binding.run_id,
                evidence_refs=(artifact.artifact_id,),
                metadata={
                    "artifact_id": artifact.artifact_id,
                    "source": source,
                    "cycle_id": cycle_id,
                    "recognition_type": recognition_type,
                    "entropy": entropy,
                    "swabhaav_ratio": swabhaav_ratio,
                    "quality": quality,
                    "mimicry_penalty": mimicry_penalty,
                    "recognition_bonus": recognition_bonus,
                    "witness_score": witness_score,
                    "is_mimicry": is_mimicry,
                    "is_genuine": is_genuine,
                    "receipt_event_id": receipt_event_id,
                },
            )
        )

        facts: list[MemoryFact] = []
        facts.append(
            await self._write_fact(
                kind="ouroboros_behavioral_summary",
                text=self._ouroboros_summary_text(
                    cycle_id=cycle_id,
                    source=source,
                    recognition_type=recognition_type,
                    entropy=entropy,
                    swabhaav_ratio=swabhaav_ratio,
                    quality=quality,
                    is_mimicry=is_mimicry,
                    is_genuine=is_genuine,
                ),
                truth_state=MemoryTruthState.PROMOTED,
                score=behavioral_score,
                session_id=binding.session_id,
                task_id=binding.task_id,
                agent_id=created_by,
                metadata={
                    "source": source,
                    "cycle_id": cycle_id,
                    "recognition_type": recognition_type,
                    "witness_score": witness_score,
                    "quality": quality,
                    "is_mimicry": is_mimicry,
                    "is_genuine": is_genuine,
                },
                provenance={
                    "source_artifact_id": artifact.artifact_id,
                    "source_event_id": receipt_event_id,
                    "run_id": binding.run_id,
                },
            )
        )
        if is_mimicry or is_genuine:
            facts.append(
                await self._write_fact(
                    kind="ouroboros_behavioral_flag",
                    text=self._ouroboros_flag_text(
                        cycle_id=cycle_id,
                        recognition_type=recognition_type,
                        is_mimicry=is_mimicry,
                        is_genuine=is_genuine,
                    ),
                    truth_state=MemoryTruthState.CANDIDATE,
                    score=max(0.2, 1.0 - behavioral_score) if is_mimicry else behavioral_score,
                    session_id=binding.session_id,
                    task_id=binding.task_id,
                    agent_id=created_by,
                    metadata={
                        "source": source,
                        "cycle_id": cycle_id,
                        "recognition_type": recognition_type,
                        "is_mimicry": is_mimicry,
                        "is_genuine": is_genuine,
                    },
                    provenance={
                        "source_artifact_id": artifact.artifact_id,
                        "source_event_id": receipt_event_id,
                        "run_id": binding.run_id,
                    },
                )
            )

        summary = {
            "source": source,
            "cycle_id": cycle_id,
            "artifact_id": artifact.artifact_id,
            "fact_ids": [fact.fact_id for fact in facts],
            "receipt_event_id": receipt_event_id,
            "recognition_type": recognition_type,
            "is_mimicry": is_mimicry,
            "is_genuine": is_genuine,
        }
        receipt = await self._emit_receipt(
            event_id=receipt_event_id,
            action_name="record_ouroboros_observation",
            session_id=binding.session_id,
            trace_id=binding.trace_id,
            agent_id=created_by,
            payload={
                "source": source,
                "cycle_id": cycle_id,
                "artifact_id": artifact.artifact_id,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
                "evaluation_id": evaluation.evaluation_id,
                "recognition_type": recognition_type,
                "is_mimicry": is_mimicry,
                "is_genuine": is_genuine,
                "fact_ids": summary["fact_ids"],
            },
        )
        self._append_provenance(
            event="ouroboros_observation_recorded",
            artifact_id=artifact.artifact_id,
            agent=created_by,
            session_id=binding.session_id,
            inputs=[cycle_id or recognition_type or source],
            outputs=[artifact.artifact_id, evaluation.evaluation_id, *summary["fact_ids"]],
            confidence=behavioral_score,
            metadata={
                "source": source,
                "cycle_id": cycle_id,
                "run_id": binding.run_id,
                "task_id": binding.task_id,
                "recognition_type": recognition_type,
                "is_mimicry": is_mimicry,
                "is_genuine": is_genuine,
            },
        )
        return SovereignEvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=tuple(facts),
            receipt=receipt,
            summary=summary,
            evaluation=evaluation,
        )

    async def _resolve_binding(
        self,
        *,
        run_id: str,
        session_id: str,
        task_id: str,
        trace_id: str | None,
        payload: dict[str, Any],
        fallback_trace_id: str,
    ) -> _ResolvedBinding:
        normalized_run_id = _coerce_text(run_id)
        normalized_session_id = _coerce_text(session_id)
        normalized_task_id = _coerce_text(task_id)
        normalized_trace_id = _coerce_text(trace_id)

        run: DelegationRun | None = None
        if normalized_run_id:
            run = await self.runtime_state.get_delegation_run(normalized_run_id)
            if run is None:
                raise KeyError(f"delegation run {normalized_run_id} not found")

        resolved_session_id = normalized_session_id or (run.session_id if run else "")
        resolved_task_id = normalized_task_id or (run.task_id if run else "")
        resolved_trace_id = (
            normalized_trace_id
            or _coerce_text((run.metadata if run else {}).get("trace_id"))
            or _coerce_text(payload.get("trace_id"))
            or _coerce_text(fallback_trace_id)
        )
        if not resolved_session_id:
            raise ValueError("session_id or run_id is required to record evaluation outputs canonically")
        return _ResolvedBinding(
            run_id=normalized_run_id,
            session_id=resolved_session_id,
            task_id=resolved_task_id,
            trace_id=resolved_trace_id,
            run=run,
        )

    async def _write_fact(
        self,
        *,
        kind: str,
        text: str,
        truth_state: MemoryTruthState,
        score: float,
        session_id: str,
        task_id: str,
        agent_id: str,
        metadata: dict[str, Any],
        provenance: dict[str, Any],
    ) -> MemoryFact:
        record = await self.memory_plane.write_memory(
            MemoryRecord(
                record_id=self.runtime_state.new_fact_id(),
                kind=kind,
                text=text,
                truth_state=truth_state,
                session_id=session_id,
                task_id=task_id,
                agent_id=agent_id,
                score=_clamp_score(score),
                metadata=dict(metadata),
                provenance=dict(provenance),
            )
        )
        return MemoryFact(
            fact_id=record.record_id,
            fact_kind=record.kind,
            truth_state=record.truth_state.value,
            text=record.text,
            confidence=float(record.score),
            session_id=record.session_id,
            task_id=record.task_id,
            source_event_id=str(record.provenance.get("source_event_id", "")),
            source_artifact_id=str(record.provenance.get("source_artifact_id", "")),
            provenance=dict(record.provenance),
            metadata=dict(record.metadata),
        )

    async def _emit_receipt(
        self,
        *,
        event_id: str,
        action_name: str,
        session_id: str,
        trace_id: str,
        agent_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        envelope = RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="contracts.intelligence.evaluation",
            agent_id=agent_id,
            session_id=session_id,
            trace_id=trace_id,
            event_id=event_id,
            payload={
                "action_name": action_name,
                "decision": "recorded",
                "confidence": _clamp_score(_coerce_float(payload.get("confidence"), default=1.0)),
                **payload,
            },
        )
        await self.event_store.ingest_envelope(envelope)
        return envelope.as_dict()

    def _append_provenance(
        self,
        *,
        event: str,
        artifact_id: str,
        agent: str,
        session_id: str,
        inputs: list[str],
        outputs: list[str],
        confidence: float,
        metadata: dict[str, Any],
    ) -> None:
        if self.provenance is None:
            return
        self.provenance.append(
            ProvenanceEntry(
                event=event,
                artifact_id=artifact_id,
                agent=agent,
                session_id=session_id,
                inputs=inputs,
                outputs=outputs,
                confidence=_clamp_score(confidence),
                metadata=metadata,
            )
        )

    def _flywheel_score(self, status: str) -> float:
        normalized = _coerce_text(status, default="unknown").lower()
        return {
            "completed": 1.0,
            "succeeded": 1.0,
            "running": 0.7,
            "in_progress": 0.7,
            "queued": 0.5,
            "pending": 0.5,
            "failed": 0.0,
            "cancelled": 0.0,
        }.get(normalized, 0.4)

    def _flywheel_status_text(
        self,
        *,
        job_id: str,
        workload_id: str,
        status: str,
    ) -> str:
        scope = f" for workload {workload_id}" if workload_id else ""
        return f"Data Flywheel job {job_id}{scope} is {status}."

    def _flywheel_recommendations(
        self,
        job_payload: dict[str, Any],
        *,
        workload_id: str,
        client_id: str,
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _append(
            text: str,
            *,
            confidence: float = 0.75,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            normalized = _coerce_text(text)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            recommendations.append(
                {
                    "text": normalized,
                    "confidence": _clamp_score(confidence),
                    "metadata": dict(metadata or {}),
                }
            )

        direct_model = _coerce_text(
            job_payload.get("recommended_model")
            or job_payload.get("best_model")
            or job_payload.get("winning_model")
        )
        if direct_model:
            _append(
                self._recommendation_text(
                    model=direct_model,
                    provider="",
                    workload_id=workload_id,
                    client_id=client_id,
                ),
                metadata={"recommended_model": direct_model, "source": "data_flywheel"},
            )

        recommendation = job_payload.get("recommendation")
        if isinstance(recommendation, str):
            _append(
                recommendation,
                metadata={"source": "data_flywheel", "kind": "text_recommendation"},
            )
        elif isinstance(recommendation, dict):
            model = _coerce_text(
                recommendation.get("model") or recommendation.get("recommended_model")
            )
            provider = _coerce_text(
                recommendation.get("provider")
                or recommendation.get("recommended_provider")
            )
            confidence = _clamp_score(
                _coerce_float(recommendation.get("score"), default=0.75)
            )
            if model:
                _append(
                    self._recommendation_text(
                        model=model,
                        provider=provider,
                        workload_id=workload_id,
                        client_id=client_id,
                    ),
                    confidence=confidence,
                    metadata={
                        "recommended_model": model,
                        "recommended_provider": provider,
                        "source": "data_flywheel",
                    },
                )
        return recommendations

    def _recommendation_text(
        self,
        *,
        model: str,
        provider: str,
        workload_id: str,
        client_id: str,
    ) -> str:
        provider_prefix = f"{provider}/" if provider else ""
        scope_parts = [part for part in (workload_id, client_id) if part]
        scope = f" for {'/'.join(scope_parts)}" if scope_parts else ""
        return f"Prefer {provider_prefix}{model}{scope}."

    def _reciprocity_score(
        self,
        *,
        chain_valid: bool,
        challenged_claims: int,
        invariant_issues: int,
    ) -> float:
        score = 1.0
        if not chain_valid:
            score -= 0.4
        score -= challenged_claims * 0.08
        score -= invariant_issues * 0.12
        return _clamp_score(score)

    def _reciprocity_summary_text(
        self,
        *,
        actors: int,
        activities: int,
        projects: int,
        obligations: int,
        active_obligations: int,
        challenged_claims: int,
        total_obligation_usd: float,
        total_routed_usd: float,
        chain_valid: bool,
    ) -> str:
        chain_text = "valid" if chain_valid else "invalid"
        return (
            "Reciprocity summary reports "
            f"{actors} actors, {activities} activities, {projects} projects, "
            f"{obligations} obligations ({active_obligations} active), "
            f"{challenged_claims} challenged claims, "
            f"${total_obligation_usd:,.0f} obligations and "
            f"${total_routed_usd:,.0f} routed; chain is {chain_text}."
        )

    def _reciprocity_issue_text(
        self,
        *,
        chain_valid: bool,
        invariant_issues: int,
        challenged_claims: int,
        issue_codes: list[str],
    ) -> str:
        parts: list[str] = []
        if not chain_valid:
            parts.append("chain validity failed")
        if invariant_issues:
            parts.append(f"{invariant_issues} invariant issues")
        if challenged_claims:
            parts.append(f"{challenged_claims} challenged claims")
        if issue_codes:
            parts.append(f"issue codes: {', '.join(issue_codes)}")
        return "Reciprocity issues observed: " + ", ".join(parts) + "."

    def _issue_codes(self, payload: dict[str, Any]) -> list[str]:
        issues = payload.get("issues")
        if not isinstance(issues, list):
            return []
        codes: list[str] = []
        for issue in issues:
            if isinstance(issue, dict):
                code = _coerce_text(issue.get("code"))
            else:
                code = _coerce_text(issue)
            if code:
                codes.append(code)
        return codes

    def _ouroboros_score(
        self,
        *,
        quality: float,
        witness_score: float,
        is_mimicry: bool,
        is_genuine: bool,
    ) -> float:
        score = (quality + witness_score) / 2.0
        if is_genuine:
            score += 0.1
        if is_mimicry:
            score -= 0.25
        return _clamp_score(score)

    def _ouroboros_summary_text(
        self,
        *,
        cycle_id: str,
        source: str,
        recognition_type: str,
        entropy: float,
        swabhaav_ratio: float,
        quality: float,
        is_mimicry: bool,
        is_genuine: bool,
    ) -> str:
        cycle_text = cycle_id or "latest cycle"
        return (
            f"Ouroboros observation {cycle_text} from {source} saw "
            f"{recognition_type} recognition with entropy {entropy:.2f}, "
            f"swabhaav ratio {swabhaav_ratio:.2f}, quality {quality:.2f}, "
            f"mimicry={str(is_mimicry).lower()}, genuine={str(is_genuine).lower()}."
        )

    def _ouroboros_flag_text(
        self,
        *,
        cycle_id: str,
        recognition_type: str,
        is_mimicry: bool,
        is_genuine: bool,
    ) -> str:
        cycle_text = cycle_id or "latest cycle"
        return (
            f"Ouroboros flag for {cycle_text}: recognition={recognition_type}, "
            f"mimicry={str(is_mimicry).lower()}, genuine={str(is_genuine).lower()}."
        )


def build_sovereign_evaluation_recorder(
    *,
    db_path: Path | str | None = None,
    event_log_dir: Path | str | None = None,
    workspace_root: Path | str | None = None,
    provenance_root: Path | str | None = None,
    runtime_state: RuntimeStateStore | None = None,
    event_store: EventMemoryStore | None = None,
    memory_plane: MemoryPlane | None = None,
    evaluation_sink: EvaluationSink | None = None,
) -> SovereignEvaluationRecorder:
    """Build the sovereign evaluation-side compatibility recorder."""

    del event_log_dir

    resolved_runtime_state = runtime_state or RuntimeStateStore(db_path)
    resolved_event_store = event_store or EventMemoryStore(resolved_runtime_state.db_path)
    resolved_memory_plane = memory_plane or SovereignMemoryPlaneAdapter(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
    )
    resolved_evaluation_sink = evaluation_sink or SovereignEvaluationSinkAdapter(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
        memory_plane=resolved_memory_plane,
    )
    artifact_store = RuntimeArtifactStore(
        base_dir=Path(workspace_root) if workspace_root is not None else None,
        runtime_state=resolved_runtime_state,
    )
    provenance = ProvenanceLogger(
        base_dir=Path(provenance_root) if provenance_root is not None else artifact_store.base_dir,
    )
    return SovereignEvaluationRecorder(
        runtime_state=resolved_runtime_state,
        event_store=resolved_event_store,
        memory_plane=resolved_memory_plane,
        evaluation_sink=resolved_evaluation_sink,
        artifact_store=artifact_store,
        provenance=provenance,
    )


__all__ = [
    "SovereignEvaluationRecorder",
    "SovereignEvaluationRegistrationResult",
    "build_sovereign_evaluation_recorder",
]
