"""Canonical registry for external evaluation outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
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
