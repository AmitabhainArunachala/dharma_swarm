"""Canonical registry for evaluation outputs and behavioral observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.engine.provenance import ProvenanceEntry, ProvenanceLogger
from dharma_swarm.event_log import EventLog
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import ArtifactRecord, DelegationRun, MemoryFact, RuntimeStateStore


@dataclass(frozen=True, slots=True)
class EvaluationRegistrationResult:
    artifact: ArtifactRecord
    manifest_path: Path
    facts: list[MemoryFact]
    receipt: dict[str, Any]
    summary: dict[str, Any] = field(default_factory=dict)


class EvaluationRegistry:
    """Bind external evaluation outputs back into canonical runtime truth."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        memory_lattice: MemoryLattice | None = None,
        event_log: EventLog | None = None,
        artifact_store: RuntimeArtifactStore | None = None,
        provenance: ProvenanceLogger | None = None,
        workspace_root: Path | str | None = None,
        provenance_root: Path | str | None = None,
    ) -> None:
        if runtime_state is None and memory_lattice is None:
            raise ValueError("evaluation registry requires runtime_state or memory_lattice")
        self.memory_lattice = memory_lattice or MemoryLattice(
            db_path=runtime_state.db_path if runtime_state is not None else None,
            event_log_dir=event_log.base_dir if event_log is not None else None,
        )
        self.runtime_state = runtime_state or self.memory_lattice.runtime_state
        self.event_log = event_log or self.memory_lattice.event_log
        self.artifact_store = artifact_store or RuntimeArtifactStore(
            base_dir=workspace_root,
            runtime_state=self.runtime_state,
        )
        self.provenance = provenance or ProvenanceLogger(
            base_dir=Path(provenance_root) if provenance_root is not None else self.artifact_store.base_dir,
        )

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
        created_by: str = "evaluation.registry",
        promotion_state: str = "shared",
    ) -> EvaluationRegistrationResult:
        await self.runtime_state.init_db()
        await self.memory_lattice.init_db()

        resolved_run = await self._resolve_run(run_id)
        resolved_session_id = session_id or (resolved_run.session_id if resolved_run else "")
        resolved_task_id = task_id or (resolved_run.task_id if resolved_run else "")
        resolved_trace_id = trace_id or self._resolve_trace_id(job_payload, resolved_run)
        if not resolved_session_id:
            raise ValueError("session_id or run_id is required to record evaluation outputs canonically")

        resolved_job_id = str(job_id or job_payload.get("id") or job_payload.get("job_id") or "").strip()
        if not resolved_job_id:
            raise ValueError("job payload missing id/job_id")
        resolved_workload_id = str(workload_id or job_payload.get("workload_id") or "").strip()
        resolved_client_id = str(client_id or job_payload.get("client_id") or "").strip()
        status = str(job_payload.get("status") or "unknown").strip() or "unknown"

        stored = await self.artifact_store.create_text_artifact_async(
            session_id=resolved_session_id,
            artifact_type="evaluations",
            artifact_kind="flywheel_job_result",
            content=self._render_job_payload(job_payload),
            created_by=created_by,
            extension="json",
            task_id=resolved_task_id,
            run_id=run_id,
            trace_id=resolved_trace_id,
            promotion_state=promotion_state,
            provenance={
                "source": "data_flywheel",
                "job_id": resolved_job_id,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
            },
            metadata={
                "job_id": resolved_job_id,
                "status": status,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
                "source": "data_flywheel",
            },
        )
        artifact = stored.record

        facts: list[MemoryFact] = []
        facts.append(
            await self.memory_lattice.record_fact(
                self._status_fact_text(
                    job_id=resolved_job_id,
                    workload_id=resolved_workload_id,
                    status=status,
                ),
                fact_kind="evaluation_status",
                truth_state="promoted",
                confidence=1.0,
                session_id=resolved_session_id,
                task_id=resolved_task_id,
                source_artifact_id=artifact.artifact_id,
                metadata={
                    "job_id": resolved_job_id,
                    "status": status,
                    "workload_id": resolved_workload_id,
                    "client_id": resolved_client_id,
                    "source": "data_flywheel",
                },
                provenance={
                    "artifact_id": artifact.artifact_id,
                    "source": "data_flywheel",
                },
            )
        )
        recommendations = self._extract_recommendations(
            job_payload,
            workload_id=resolved_workload_id,
            client_id=resolved_client_id,
        )
        for recommendation in recommendations:
            facts.append(
                await self.memory_lattice.record_fact(
                    recommendation["text"],
                    fact_kind="provider_recommendation",
                    truth_state="candidate",
                    confidence=float(recommendation["confidence"]),
                    session_id=resolved_session_id,
                    task_id=resolved_task_id,
                    source_artifact_id=artifact.artifact_id,
                    metadata=dict(recommendation["metadata"]),
                    provenance={
                        "artifact_id": artifact.artifact_id,
                        "source": "data_flywheel",
                    },
                )
            )

        self.provenance.append(
            ProvenanceEntry(
                event="flywheel_job_recorded",
                artifact_id=artifact.artifact_id,
                agent=created_by,
                session_id=resolved_session_id,
                inputs=[resolved_job_id],
                outputs=[artifact.artifact_id, *[fact.fact_id for fact in facts]],
                confidence=1.0,
                metadata={
                    "job_id": resolved_job_id,
                    "status": status,
                    "workload_id": resolved_workload_id,
                    "client_id": resolved_client_id,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "recommendation_count": len(recommendations),
                },
            )
        )

        receipt = self.event_log.append_envelope(
            RuntimeEnvelope.create(
                event_type=RuntimeEventType.ACTION_EVENT,
                source="evaluation.registry",
                agent_id=created_by,
                session_id=resolved_session_id,
                trace_id=resolved_trace_id or resolved_job_id,
                payload={
                    "action_name": "record_flywheel_job_result",
                    "decision": "recorded",
                    "confidence": 1.0,
                    "job_id": resolved_job_id,
                    "artifact_id": artifact.artifact_id,
                    "workload_id": resolved_workload_id,
                    "client_id": resolved_client_id,
                    "status": status,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "recommendation_count": len(recommendations),
                },
            ),
            stream="flywheel_evaluations",
        )
        return EvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=facts,
            receipt=receipt,
            summary={
                "job_id": resolved_job_id,
                "workload_id": resolved_workload_id,
                "client_id": resolved_client_id,
                "status": status,
                "artifact_id": artifact.artifact_id,
                "fact_ids": [fact.fact_id for fact in facts],
                "receipt_event_id": str(receipt.get("event_id", "")),
            },
        )

    async def record_reciprocity_summary(
        self,
        summary_payload: dict[str, Any],
        *,
        run_id: str = "",
        session_id: str = "",
        task_id: str = "",
        trace_id: str | None = None,
        created_by: str = "evaluation.registry",
        promotion_state: str = "shared",
    ) -> EvaluationRegistrationResult:
        await self.runtime_state.init_db()
        await self.memory_lattice.init_db()

        resolved_run = await self._resolve_run(run_id)
        resolved_session_id = session_id or (resolved_run.session_id if resolved_run else "")
        resolved_task_id = task_id or (resolved_run.task_id if resolved_run else "")
        resolved_trace_id = trace_id or self._resolve_trace_id(summary_payload, resolved_run)
        if not resolved_session_id:
            raise ValueError("session_id or run_id is required to record evaluation outputs canonically")

        service = (
            str(
                summary_payload.get("service")
                or summary_payload.get("source")
                or "reciprocity_commons"
            ).strip()
            or "reciprocity_commons"
        )
        summary_type = (
            str(summary_payload.get("summary_type") or "ledger_summary").strip()
            or "ledger_summary"
        )
        if not resolved_trace_id:
            resolved_trace_id = f"{service}:{summary_type}"
        actors = self._metric_int(summary_payload, "actors")
        activities = self._metric_int(summary_payload, "activities")
        projects = self._metric_int(summary_payload, "projects")
        obligations = self._metric_int(summary_payload, "obligations")
        active_obligations = self._metric_int(summary_payload, "active_obligations")
        challenged_claims = self._metric_int(summary_payload, "challenged_claims")
        invariant_issues = self._metric_int(summary_payload, "invariant_issues")
        chain_valid = self._metric_bool(summary_payload, "chain_valid", default=True)
        total_obligation_usd = self._metric_float(summary_payload, "total_obligation_usd")
        total_routed_usd = self._metric_float(summary_payload, "total_routed_usd")
        issue_codes = self._reciprocity_issue_codes(summary_payload)

        stored = await self.artifact_store.create_text_artifact_async(
            session_id=resolved_session_id,
            artifact_type="evaluations",
            artifact_kind="reciprocity_ledger_summary",
            content=self._render_job_payload(summary_payload),
            created_by=created_by,
            extension="json",
            task_id=resolved_task_id,
            run_id=run_id,
            trace_id=resolved_trace_id,
            promotion_state=promotion_state,
            provenance={
                "source": service,
                "summary_type": summary_type,
            },
            metadata={
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
            },
        )
        artifact = stored.record

        facts: list[MemoryFact] = []
        facts.append(
            await self.memory_lattice.record_fact(
                self._reciprocity_summary_fact_text(
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
                fact_kind="reciprocity_summary",
                truth_state="promoted",
                confidence=1.0 if chain_valid else 0.9,
                session_id=resolved_session_id,
                task_id=resolved_task_id,
                source_artifact_id=artifact.artifact_id,
                metadata={
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
                },
                provenance={
                    "artifact_id": artifact.artifact_id,
                    "source": service,
                },
            )
        )
        findings = self._extract_reciprocity_findings(
            chain_valid=chain_valid,
            invariant_issues=invariant_issues,
            challenged_claims=challenged_claims,
            issue_codes=issue_codes,
            service=service,
            summary_type=summary_type,
        )
        for finding in findings:
            facts.append(
                await self.memory_lattice.record_fact(
                    finding["text"],
                    fact_kind=str(finding["fact_kind"]),
                    truth_state=str(finding["truth_state"]),
                    confidence=float(finding["confidence"]),
                    session_id=resolved_session_id,
                    task_id=resolved_task_id,
                    source_artifact_id=artifact.artifact_id,
                    metadata=dict(finding["metadata"]),
                    provenance={
                        "artifact_id": artifact.artifact_id,
                        "source": service,
                    },
                )
            )

        self.provenance.append(
            ProvenanceEntry(
                event="reciprocity_summary_recorded",
                artifact_id=artifact.artifact_id,
                agent=created_by,
                session_id=resolved_session_id,
                inputs=[summary_type],
                outputs=[artifact.artifact_id, *[fact.fact_id for fact in facts]],
                confidence=1.0,
                metadata={
                    "source": service,
                    "summary_type": summary_type,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "chain_valid": chain_valid,
                    "invariant_issues": invariant_issues,
                    "challenged_claims": challenged_claims,
                    "finding_count": len(findings),
                },
            )
        )

        receipt = self.event_log.append_envelope(
            RuntimeEnvelope.create(
                event_type=RuntimeEventType.ACTION_EVENT,
                source="evaluation.registry",
                agent_id=created_by,
                session_id=resolved_session_id,
                trace_id=resolved_trace_id or f"{service}:{summary_type}",
                payload={
                    "action_name": "record_reciprocity_summary",
                    "decision": "recorded",
                    "confidence": 1.0,
                    "source": service,
                    "summary_type": summary_type,
                    "artifact_id": artifact.artifact_id,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "chain_valid": chain_valid,
                    "invariant_issues": invariant_issues,
                    "challenged_claims": challenged_claims,
                },
            ),
            stream="reciprocity_evaluations",
        )
        return EvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=facts,
            receipt=receipt,
            summary={
                "source": service,
                "summary_type": summary_type,
                "artifact_id": artifact.artifact_id,
                "fact_ids": [fact.fact_id for fact in facts],
                "receipt_event_id": str(receipt.get("event_id", "")),
                "chain_valid": chain_valid,
                "invariant_issues": invariant_issues,
                "challenged_claims": challenged_claims,
            },
        )

    async def record_ouroboros_observation(
        self,
        observation_payload: dict[str, Any],
        *,
        run_id: str = "",
        session_id: str = "",
        task_id: str = "",
        trace_id: str | None = None,
        created_by: str = "evaluation.registry",
        promotion_state: str = "shared",
    ) -> EvaluationRegistrationResult:
        await self.runtime_state.init_db()
        await self.memory_lattice.init_db()

        resolved_run = await self._resolve_run(run_id)
        resolved_session_id = session_id or (resolved_run.session_id if resolved_run else "")
        resolved_task_id = task_id or (resolved_run.task_id if resolved_run else "")
        resolved_trace_id = trace_id or self._resolve_trace_id(observation_payload, resolved_run)
        if not resolved_session_id:
            raise ValueError("session_id or run_id is required to record evaluation outputs canonically")

        signature_payload = self._ouroboros_signature_payload(observation_payload)
        modifiers_payload = self._ouroboros_modifiers_payload(observation_payload)

        source = self._metric_text(
            observation_payload,
            "source",
            default="ouroboros",
        )
        cycle_id = self._metric_text(observation_payload, "cycle_id")
        timestamp = self._metric_text(observation_payload, "timestamp")
        recognition_type = self._metric_text(
            signature_payload,
            "recognition_type",
            default="unknown",
        )
        entropy = self._metric_ratio(signature_payload, "entropy")
        complexity = self._metric_ratio(signature_payload, "complexity")
        self_reference_density = self._metric_ratio(
            signature_payload,
            "self_reference_density",
        )
        identity_stability = self._metric_ratio(signature_payload, "identity_stability")
        paradox_tolerance = self._metric_ratio(signature_payload, "paradox_tolerance")
        swabhaav_ratio = self._metric_ratio(signature_payload, "swabhaav_ratio")
        word_count = self._metric_int(signature_payload, "word_count")
        quality = self._metric_ratio(modifiers_payload, "quality")
        mimicry_penalty = self._metric_float(modifiers_payload, "mimicry_penalty")
        recognition_bonus = self._metric_float(modifiers_payload, "recognition_bonus")
        witness_score = self._metric_ratio(
            modifiers_payload,
            "witness_score",
            default=swabhaav_ratio,
        )
        is_mimicry = self._metric_bool(
            observation_payload,
            "is_mimicry",
            default=mimicry_penalty < 1.0,
        )
        is_genuine = self._metric_bool(
            observation_payload,
            "is_genuine",
            default=recognition_type.upper() == "GENUINE",
        )

        if not resolved_trace_id:
            trace_suffix = cycle_id or recognition_type or "latest"
            resolved_trace_id = f"{source}:{trace_suffix}"

        stored = await self.artifact_store.create_text_artifact_async(
            session_id=resolved_session_id,
            artifact_type="evaluations",
            artifact_kind="ouroboros_behavioral_observation",
            content=self._render_job_payload(observation_payload),
            created_by=created_by,
            extension="json",
            task_id=resolved_task_id,
            run_id=run_id,
            trace_id=resolved_trace_id,
            promotion_state=promotion_state,
            provenance={
                "source": source,
                "cycle_id": cycle_id,
                "recognition_type": recognition_type,
            },
            metadata={
                "source": source,
                "cycle_id": cycle_id,
                "timestamp": timestamp,
                "recognition_type": recognition_type,
                "entropy": entropy,
                "complexity": complexity,
                "self_reference_density": self_reference_density,
                "identity_stability": identity_stability,
                "paradox_tolerance": paradox_tolerance,
                "swabhaav_ratio": swabhaav_ratio,
                "word_count": word_count,
                "quality": quality,
                "mimicry_penalty": mimicry_penalty,
                "recognition_bonus": recognition_bonus,
                "witness_score": witness_score,
                "is_mimicry": is_mimicry,
                "is_genuine": is_genuine,
            },
        )
        artifact = stored.record

        facts: list[MemoryFact] = []
        facts.append(
            await self.memory_lattice.record_fact(
                self._ouroboros_summary_fact_text(
                    cycle_id=cycle_id,
                    source=source,
                    recognition_type=recognition_type,
                    entropy=entropy,
                    swabhaav_ratio=swabhaav_ratio,
                    quality=quality,
                    is_mimicry=is_mimicry,
                    is_genuine=is_genuine,
                ),
                fact_kind="ouroboros_behavioral_summary",
                truth_state="promoted",
                confidence=1.0,
                session_id=resolved_session_id,
                task_id=resolved_task_id,
                source_artifact_id=artifact.artifact_id,
                metadata={
                    "source": source,
                    "cycle_id": cycle_id,
                    "recognition_type": recognition_type,
                    "swabhaav_ratio": swabhaav_ratio,
                    "quality": quality,
                    "is_mimicry": is_mimicry,
                    "is_genuine": is_genuine,
                },
                provenance={
                    "artifact_id": artifact.artifact_id,
                    "source": source,
                },
            )
        )
        findings = self._extract_ouroboros_findings(
            source=source,
            cycle_id=cycle_id,
            recognition_type=recognition_type,
            swabhaav_ratio=swabhaav_ratio,
            quality=quality,
            mimicry_penalty=mimicry_penalty,
            recognition_bonus=recognition_bonus,
            witness_score=witness_score,
            is_mimicry=is_mimicry,
            is_genuine=is_genuine,
        )
        for finding in findings:
            facts.append(
                await self.memory_lattice.record_fact(
                    finding["text"],
                    fact_kind=str(finding["fact_kind"]),
                    truth_state=str(finding["truth_state"]),
                    confidence=float(finding["confidence"]),
                    session_id=resolved_session_id,
                    task_id=resolved_task_id,
                    source_artifact_id=artifact.artifact_id,
                    metadata=dict(finding["metadata"]),
                    provenance={
                        "artifact_id": artifact.artifact_id,
                        "source": source,
                    },
                )
            )

        self.provenance.append(
            ProvenanceEntry(
                event="ouroboros_observation_recorded",
                artifact_id=artifact.artifact_id,
                agent=created_by,
                session_id=resolved_session_id,
                inputs=[cycle_id or recognition_type or source],
                outputs=[artifact.artifact_id, *[fact.fact_id for fact in facts]],
                confidence=1.0,
                metadata={
                    "source": source,
                    "cycle_id": cycle_id,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "recognition_type": recognition_type,
                    "is_mimicry": is_mimicry,
                    "is_genuine": is_genuine,
                    "finding_count": len(findings),
                },
            )
        )

        receipt = self.event_log.append_envelope(
            RuntimeEnvelope.create(
                event_type=RuntimeEventType.ACTION_EVENT,
                source="evaluation.registry",
                agent_id=created_by,
                session_id=resolved_session_id,
                trace_id=resolved_trace_id,
                payload={
                    "action_name": "record_ouroboros_observation",
                    "decision": "recorded",
                    "confidence": 1.0,
                    "source": source,
                    "cycle_id": cycle_id,
                    "artifact_id": artifact.artifact_id,
                    "run_id": run_id,
                    "task_id": resolved_task_id,
                    "recognition_type": recognition_type,
                    "is_mimicry": is_mimicry,
                    "is_genuine": is_genuine,
                },
            ),
            stream="ouroboros_evaluations",
        )
        return EvaluationRegistrationResult(
            artifact=artifact,
            manifest_path=stored.manifest_path,
            facts=facts,
            receipt=receipt,
            summary={
                "source": source,
                "cycle_id": cycle_id,
                "artifact_id": artifact.artifact_id,
                "fact_ids": [fact.fact_id for fact in facts],
                "receipt_event_id": str(receipt.get("event_id", "")),
                "recognition_type": recognition_type,
                "is_mimicry": is_mimicry,
                "is_genuine": is_genuine,
            },
        )

    async def _resolve_run(self, run_id: str) -> DelegationRun | None:
        if not run_id:
            return None
        run = await self.runtime_state.get_delegation_run(run_id)
        if run is None:
            raise KeyError(f"delegation run {run_id} not found")
        return run

    def _resolve_trace_id(
        self,
        job_payload: dict[str, Any],
        run: DelegationRun | None,
    ) -> str:
        if run is not None:
            trace = str(run.metadata.get("trace_id", "")).strip()
            if trace:
                return trace
        return str(job_payload.get("trace_id") or "").strip()

    def _render_job_payload(self, job_payload: dict[str, Any]) -> str:
        return json.dumps(job_payload, sort_keys=True, ensure_ascii=True, indent=2)

    def _status_fact_text(
        self,
        *,
        job_id: str,
        workload_id: str,
        status: str,
    ) -> str:
        scope = f" for workload {workload_id}" if workload_id else ""
        return f"Data Flywheel job {job_id}{scope} is {status}."

    def _extract_recommendations(
        self,
        job_payload: dict[str, Any],
        *,
        workload_id: str,
        client_id: str,
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _append(text: str, *, confidence: float = 0.7, metadata: dict[str, Any] | None = None) -> None:
            normalized = text.strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            recommendations.append(
                {
                    "text": normalized,
                    "confidence": max(0.0, min(float(confidence), 1.0)),
                    "metadata": dict(metadata or {}),
                }
            )

        direct_model = (
            job_payload.get("recommended_model")
            or job_payload.get("best_model")
            or job_payload.get("winning_model")
        )
        if isinstance(direct_model, str) and direct_model.strip():
            _append(
                self._recommendation_text(
                    model=direct_model.strip(),
                    workload_id=workload_id,
                    client_id=client_id,
                ),
                metadata={"recommended_model": direct_model.strip(), "source": "data_flywheel"},
            )

        recommendation = job_payload.get("recommendation")
        if isinstance(recommendation, str) and recommendation.strip():
            _append(
                recommendation.strip(),
                metadata={"source": "data_flywheel", "kind": "text_recommendation"},
            )
        elif isinstance(recommendation, dict):
            model = str(recommendation.get("model") or recommendation.get("recommended_model") or "").strip()
            provider = str(recommendation.get("provider") or recommendation.get("recommended_provider") or "").strip()
            score = recommendation.get("score")
            confidence = float(score) if isinstance(score, (int, float)) and 0.0 <= float(score) <= 1.0 else 0.75
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

        leaderboard = job_payload.get("leaderboard")
        if isinstance(leaderboard, list) and leaderboard:
            top = leaderboard[0]
            if isinstance(top, dict):
                model = str(top.get("model") or top.get("candidate") or "").strip()
                provider = str(top.get("provider") or "").strip()
                score = top.get("score")
                confidence = float(score) if isinstance(score, (int, float)) and 0.0 <= float(score) <= 1.0 else 0.7
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
                            "leaderboard_rank": 1,
                        },
                    )
        return recommendations

    def _recommendation_text(
        self,
        *,
        model: str,
        provider: str = "",
        workload_id: str,
        client_id: str,
    ) -> str:
        clauses = [f"Prefer model {model}"]
        if provider:
            clauses.append(f"from provider {provider}")
        if workload_id:
            clauses.append(f"for workload {workload_id}")
        if client_id:
            clauses.append(f"for client {client_id}")
        return " ".join(clauses) + "."

    def _metric_text(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        default: str = "",
    ) -> str:
        value = payload.get(key, default)
        if value is None:
            return default
        return str(value).strip() or default

    def _metric_int(self, payload: dict[str, Any], key: str) -> int:
        value = payload.get(key, 0)
        if value is None:
            return 0
        if isinstance(value, bool):
            raise ValueError(f"{key} must be an integer >= 0")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            try:
                parsed_float = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be an integer >= 0") from exc
            if not math.isfinite(parsed_float) or not parsed_float.is_integer():
                raise ValueError(f"{key} must be an integer >= 0")
            parsed = int(parsed_float)
        if parsed < 0:
            raise ValueError(f"{key} must be an integer >= 0")
        return parsed

    def _metric_float(self, payload: dict[str, Any], key: str) -> float:
        value = payload.get(key, 0.0)
        if value is None:
            return 0.0
        if isinstance(value, bool):
            raise ValueError(f"{key} must be a finite number >= 0")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a finite number >= 0") from exc
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(f"{key} must be a finite number >= 0")
        return parsed

    def _metric_ratio(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        default: float = 0.0,
    ) -> float:
        if key not in payload or payload.get(key) is None:
            return default
        parsed = self._metric_float(payload, key)
        if parsed > 1.0:
            raise ValueError(f"{key} must be a finite number between 0 and 1")
        return parsed

    def _metric_bool(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        default: bool,
    ) -> bool:
        if key not in payload or payload.get(key) is None:
            return default

        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)) or value not in (0, 1):
                raise ValueError(f"{key} must be a boolean")
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"{key} must be a boolean")

    def _reciprocity_issue_codes(self, summary_payload: dict[str, Any]) -> list[str]:
        raw_issues = summary_payload.get("issues")
        if not isinstance(raw_issues, list):
            return []
        codes: list[str] = []
        for issue in raw_issues:
            code = ""
            if isinstance(issue, dict):
                code = str(issue.get("code") or "").strip()
            elif isinstance(issue, str):
                code = issue.strip()
            if code and code not in codes:
                codes.append(code)
        return codes

    def _ouroboros_signature_payload(
        self,
        observation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_signature = observation_payload.get("signature")
        if isinstance(raw_signature, dict):
            return raw_signature

        signature = {
            key: observation_payload.get(key)
            for key in (
                "entropy",
                "complexity",
                "self_reference_density",
                "identity_stability",
                "paradox_tolerance",
                "swabhaav_ratio",
                "word_count",
                "recognition_type",
            )
            if key in observation_payload
        }
        if signature:
            return signature
        raise ValueError("ouroboros observation missing behavioral signature")

    def _ouroboros_modifiers_payload(
        self,
        observation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_modifiers = observation_payload.get("modifiers")
        if isinstance(raw_modifiers, dict):
            return raw_modifiers
        return {
            key: observation_payload.get(key)
            for key in (
                "quality",
                "mimicry_penalty",
                "recognition_bonus",
                "witness_score",
            )
            if key in observation_payload
        }

    def _reciprocity_summary_fact_text(
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
        return (
            "Reciprocity Commons summary reports "
            f"actors={actors}, activities={activities}, projects={projects}, "
            f"obligations={obligations}, active_obligations={active_obligations}, "
            f"challenged_claims={challenged_claims}, "
            f"total_routed_usd={total_routed_usd:.2f}, "
            f"total_obligation_usd={total_obligation_usd:.2f}, "
            f"chain_valid={chain_valid}."
        )

    def _extract_reciprocity_findings(
        self,
        *,
        chain_valid: bool,
        invariant_issues: int,
        challenged_claims: int,
        issue_codes: list[str],
        service: str,
        summary_type: str,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if not chain_valid or invariant_issues > 0:
            findings.append(
                {
                    "text": (
                        "Reciprocity Commons integrity alert: "
                        f"chain_valid={chain_valid} "
                        f"invariant_issues={invariant_issues} "
                        f"issue_codes={','.join(issue_codes) or 'none'}."
                    ),
                    "fact_kind": "reciprocity_integrity_alert",
                    "truth_state": "candidate",
                    "confidence": 0.95,
                    "metadata": {
                        "source": service,
                        "summary_type": summary_type,
                        "chain_valid": chain_valid,
                        "invariant_issues": invariant_issues,
                        "issue_codes": list(issue_codes),
                    },
                }
            )
        if challenged_claims > 0:
            findings.append(
                {
                    "text": (
                        "Reciprocity Commons claim watch: "
                        f"challenged_claims={challenged_claims}."
                    ),
                    "fact_kind": "reciprocity_claim_watch",
                    "truth_state": "candidate",
                    "confidence": 0.9,
                    "metadata": {
                        "source": service,
                        "summary_type": summary_type,
                        "challenged_claims": challenged_claims,
                    },
                }
            )
        return findings

    def _ouroboros_summary_fact_text(
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
        cycle_clause = f" for cycle {cycle_id}" if cycle_id else ""
        return (
            f"Ouroboros observation{cycle_clause} from {source} reports "
            f"recognition={recognition_type}, entropy={entropy:.3f}, "
            f"swabhaav_ratio={swabhaav_ratio:.3f}, quality={quality:.3f}, "
            f"is_mimicry={is_mimicry}, is_genuine={is_genuine}."
        )

    def _extract_ouroboros_findings(
        self,
        *,
        source: str,
        cycle_id: str,
        recognition_type: str,
        swabhaav_ratio: float,
        quality: float,
        mimicry_penalty: float,
        recognition_bonus: float,
        witness_score: float,
        is_mimicry: bool,
        is_genuine: bool,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if is_mimicry or quality < 0.45 or witness_score < 0.35:
            findings.append(
                {
                    "text": (
                        "Ouroboros behavioral alert: "
                        f"cycle_id={cycle_id or 'unknown'} "
                        f"quality={quality:.3f} "
                        f"witness_score={witness_score:.3f} "
                        f"mimicry_penalty={mimicry_penalty:.3f}."
                    ),
                    "fact_kind": "ouroboros_behavioral_alert",
                    "truth_state": "candidate",
                    "confidence": 0.95 if is_mimicry else 0.85,
                    "metadata": {
                        "source": source,
                        "cycle_id": cycle_id,
                        "recognition_type": recognition_type,
                        "quality": quality,
                        "witness_score": witness_score,
                        "mimicry_penalty": mimicry_penalty,
                        "is_mimicry": is_mimicry,
                    },
                }
            )
        if is_genuine or recognition_type.upper() == "GENUINE" or recognition_bonus > 1.0:
            findings.append(
                {
                    "text": (
                        "Ouroboros behavioral alignment: "
                        f"cycle_id={cycle_id or 'unknown'} "
                        f"recognition={recognition_type} "
                        f"swabhaav_ratio={swabhaav_ratio:.3f}."
                    ),
                    "fact_kind": "ouroboros_behavioral_alignment",
                    "truth_state": "candidate",
                    "confidence": 0.9,
                    "metadata": {
                        "source": source,
                        "cycle_id": cycle_id,
                        "recognition_type": recognition_type,
                        "swabhaav_ratio": swabhaav_ratio,
                        "recognition_bonus": recognition_bonus,
                        "is_genuine": is_genuine,
                    },
                }
            )
        return findings
