"""Project canonical runtime state into the telemetry plane."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.runtime_state import (
    DelegationRun,
    OperatorAction,
    RuntimeStateStore,
    SessionEventRecord,
    SessionState,
    TaskClaim,
)
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    ExternalOutcomeRecord,
    InterventionOutcomeRecord,
    RoutingDecisionRecord,
    TelemetryPlaneStore,
    WorkflowScoreRecord,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(
        "|".join(str(part) for part in parts if part is not None).encode("utf-8")
    ).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _safe_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


class RuntimeTelemetryProjector:
    """Mirror runtime sessions, claims, runs, actions, and ledger events into telemetry."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        telemetry: TelemetryPlaneStore | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        shared_db = Path(db_path) if db_path is not None else None
        self.runtime_state = runtime_state or RuntimeStateStore(shared_db)
        self.telemetry = telemetry or TelemetryPlaneStore(shared_db)

    async def project_recent(
        self,
        *,
        limit_sessions: int = 50,
        limit_claims: int = 200,
        limit_runs: int = 200,
        limit_actions: int = 300,
        limit_events: int = 300,
    ) -> dict[str, int]:
        await self.runtime_state.init_db()
        await self.telemetry.init_db()

        sessions = self.runtime_state.list_sessions_sync(limit=limit_sessions)
        claims = await self.runtime_state.list_task_claims(limit=limit_claims)
        runs = await self.runtime_state.list_delegation_runs(limit=limit_runs)
        actions = await self.runtime_state.list_operator_actions(limit=limit_actions)
        events = await self.runtime_state.list_session_events(limit=limit_events)

        counts = {
            "sessions": 0,
            "claims": 0,
            "runs": 0,
            "actions": 0,
            "events": 0,
        }

        for session in sessions:
            if await self._project_session(session):
                counts["sessions"] += 1
        for claim in claims:
            if await self._project_claim(claim):
                counts["claims"] += 1
        for run in runs:
            if await self._project_run(run):
                counts["runs"] += 1
        for action in actions:
            if await self._project_action(action):
                counts["actions"] += 1
        for event in events:
            if await self._project_session_event(event):
                counts["events"] += 1
        return counts

    async def _project_session(self, session: SessionState) -> bool:
        created = False
        if session.operator_id:
            await self.telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=session.operator_id,
                    codename=session.operator_id,
                    department="operator",
                    specialization="session_operator",
                    status=session.status,
                    last_active=session.updated_at,
                    metadata={
                        "source": "runtime_session",
                        "session_id": session.session_id,
                        "current_task_id": session.current_task_id,
                    },
                )
            )
        bridge_agent_id = str(session.metadata.get("bridge_agent_id", "") or "")
        if bridge_agent_id:
            await self.telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=bridge_agent_id,
                    codename=bridge_agent_id,
                    department="runtime",
                    specialization="bridge_agent",
                    status="active",
                    last_active=session.updated_at,
                    metadata={"source": "runtime_session", "session_id": session.session_id},
                )
            )

        created = await self._record_external_outcome(
            ExternalOutcomeRecord(
                outcome_id=_stable_id(
                    "runtime_session",
                    session.session_id,
                    session.status,
                    session.updated_at.isoformat(),
                ),
                outcome_kind="runtime_session_state",
                value=1.0,
                unit="session",
                confidence=1.0,
                status=session.status,
                subject_id=session.session_id,
                summary=f"session {session.session_id} is {session.status}",
                session_id=session.session_id,
                task_id=session.current_task_id,
                metadata={
                    "source": "runtime_session",
                    "operator_id": session.operator_id,
                    "active_bundle_id": session.active_bundle_id,
                    "session_metadata": _safe_metadata(session.metadata),
                },
                created_at=session.updated_at,
            )
        ) or created
        return created

    async def _project_claim(self, claim: TaskClaim) -> bool:
        await self.telemetry.upsert_agent_identity(
            AgentIdentityRecord(
                agent_id=claim.agent_id,
                codename=claim.agent_id,
                department="runtime",
                specialization="task_claimant",
                status="active" if claim.status not in {"failed", "recovered"} else claim.status,
                last_active=claim.heartbeat_at or claim.acked_at or claim.claimed_at,
                metadata={"source": "task_claim", "task_id": claim.task_id},
            )
        )
        created = await self._record_external_outcome(
            ExternalOutcomeRecord(
                outcome_id=_stable_id(
                    "task_claim",
                    claim.claim_id,
                    claim.status,
                    (claim.heartbeat_at or claim.acked_at or claim.claimed_at).isoformat(),
                ),
                outcome_kind="task_claim_state",
                value=float(max(1, claim.retry_count + 1)),
                unit="attempts",
                confidence=1.0,
                status=claim.status,
                subject_id=claim.task_id,
                summary=f"{claim.agent_id} {claim.status} {claim.task_id}",
                session_id=claim.session_id,
                task_id=claim.task_id,
                metadata={
                    "source": "task_claim",
                    "claim_id": claim.claim_id,
                    "agent_id": claim.agent_id,
                    "retry_count": claim.retry_count,
                    "claim_metadata": _safe_metadata(claim.metadata),
                },
                created_at=claim.heartbeat_at or claim.acked_at or claim.claimed_at,
            )
        )
        if claim.retry_count > 0:
            created = (
                await self._record_workflow_score(
                    WorkflowScoreRecord(
                        score_id=_stable_id("claim_retry", claim.claim_id),
                        workflow_id=claim.task_id,
                        score_name="claim_retry_count",
                        score_value=float(claim.retry_count),
                        session_id=claim.session_id,
                        task_id=claim.task_id,
                        evidence=[{"claim_id": claim.claim_id}],
                        metadata={"source": "task_claim"},
                        recorded_at=claim.heartbeat_at or claim.acked_at or claim.claimed_at,
                    )
                )
                or created
            )
        return created

    async def _project_run(self, run: DelegationRun) -> bool:
        for agent_id, specialization in (
            (run.assigned_by, "dispatcher"),
            (run.assigned_to, "delegate"),
        ):
            cleaned = str(agent_id or "").strip()
            if not cleaned:
                continue
            await self.telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=cleaned,
                    codename=cleaned,
                    department="runtime",
                    specialization=specialization,
                    status="active",
                    last_active=run.completed_at or run.started_at,
                    metadata={"source": "delegation_run", "run_id": run.run_id},
                )
            )

        metadata = _safe_metadata(run.metadata)
        route_path = str(metadata.get("route_path") or f"{run.assigned_by or 'dispatcher'}->{run.assigned_to}")
        selected_provider = str(metadata.get("selected_provider") or metadata.get("provider") or "")
        selected_model_hint = str(metadata.get("selected_model_hint") or metadata.get("model") or "")
        requires_human = bool(
            metadata.get("requires_human")
            or run.assigned_to.lower() in {"operator", "human", "user"}
        )

        created = await self._record_routing_decision(
            RoutingDecisionRecord(
                decision_id=_stable_id("runtime_route", run.run_id),
                action_name="delegation_run",
                route_path=route_path,
                selected_provider=selected_provider,
                selected_model_hint=selected_model_hint,
                confidence=float(metadata.get("confidence") or 0.5),
                requires_human=requires_human,
                session_id=run.session_id,
                task_id=run.task_id,
                run_id=run.run_id,
                reasons=run.requested_output or [run.status],
                metadata={
                    "source": "delegation_run",
                    "claim_id": run.claim_id,
                    "assigned_by": run.assigned_by,
                    "assigned_to": run.assigned_to,
                    "failure_code": run.failure_code,
                    "run_metadata": metadata,
                },
                created_at=run.started_at,
            )
        )
        created = (
            await self._record_external_outcome(
                ExternalOutcomeRecord(
                    outcome_id=_stable_id(
                        "runtime_run",
                        run.run_id,
                        run.status,
                        (run.completed_at or run.started_at).isoformat(),
                    ),
                    outcome_kind="delegation_run_state",
                    value=1.0 if run.status == "completed" else 0.0,
                    unit="completion",
                    confidence=1.0,
                    status=run.status,
                    subject_id=run.run_id,
                    summary=f"{run.assigned_to} {run.status} on {run.task_id}",
                    session_id=run.session_id,
                    task_id=run.task_id,
                    run_id=run.run_id,
                    metadata={
                        "source": "delegation_run",
                        "assigned_by": run.assigned_by,
                        "assigned_to": run.assigned_to,
                        "failure_code": run.failure_code,
                        "run_metadata": metadata,
                    },
                    created_at=run.completed_at or run.started_at,
                )
            )
            or created
        )
        created = (
            await self._record_workflow_score(
                WorkflowScoreRecord(
                    score_id=_stable_id("runtime_run_score", run.run_id, run.status),
                    workflow_id=run.task_id or run.run_id,
                    score_name="run_completion_score",
                    score_value=1.0 if run.status == "completed" else 0.0,
                    session_id=run.session_id,
                    task_id=run.task_id,
                    run_id=run.run_id,
                    evidence=[{"status": run.status, "failure_code": run.failure_code}],
                    metadata={"source": "delegation_run"},
                    recorded_at=run.completed_at or run.started_at,
                )
            )
            or created
        )
        return created

    async def _project_action(self, action: OperatorAction) -> bool:
        await self.telemetry.upsert_agent_identity(
            AgentIdentityRecord(
                agent_id=action.actor,
                codename=action.actor,
                department="runtime",
                specialization="operator_action_actor",
                status="active",
                last_active=action.created_at,
                metadata={"source": "operator_action", "action_name": action.action_name},
            )
        )
        payload = _safe_metadata(action.payload)
        created = await self._record_external_outcome(
            ExternalOutcomeRecord(
                outcome_id=_stable_id("operator_action", action.action_id),
                outcome_kind=action.action_name,
                value=float(payload.get("progress") or 1.0),
                unit="progress_ratio" if isinstance(payload.get("progress"), (int, float)) else "event",
                confidence=1.0,
                status="recorded",
                subject_id=action.task_id or action.action_id,
                summary=action.reason or action.action_name,
                session_id=action.session_id,
                task_id=action.task_id,
                run_id=action.run_id,
                metadata={"source": "operator_action", "payload": payload},
                created_at=action.created_at,
            )
        )
        progress = payload.get("progress")
        if isinstance(progress, (int, float)):
            created = (
                await self._record_workflow_score(
                    WorkflowScoreRecord(
                        score_id=_stable_id("operator_progress", action.action_id),
                        workflow_id=action.task_id or action.run_id or action.action_id,
                        score_name="operator_action_progress",
                        score_value=float(progress),
                        session_id=action.session_id,
                        task_id=action.task_id,
                        run_id=action.run_id,
                        evidence=[{"action_name": action.action_name}],
                        metadata={"source": "operator_action"},
                        recorded_at=action.created_at,
                    )
                )
                or created
            )
        interventionish = (
            "ack" in action.action_name
            or "approve" in action.action_name
            or "recover" in action.action_name
            or action.actor.lower() == "operator"
        )
        if interventionish:
            created = (
                await self._record_intervention_outcome(
                    InterventionOutcomeRecord(
                        intervention_id=_stable_id("intervention", action.action_id),
                        intervention_type=action.action_name,
                        outcome_status="recorded",
                        impact_score=float(progress) if isinstance(progress, (int, float)) else 0.0,
                        summary=action.reason or action.action_name,
                        operator_id=action.actor,
                        session_id=action.session_id,
                        task_id=action.task_id,
                        run_id=action.run_id,
                        metadata={"source": "operator_action", "payload": payload},
                        created_at=action.created_at,
                    )
                )
                or created
            )
        return created

    async def _project_session_event(self, event: SessionEventRecord) -> bool:
        if event.agent_id:
            await self.telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=event.agent_id,
                    codename=event.agent_id,
                    department="runtime",
                    specialization=f"{event.ledger_kind}_ledger_agent",
                    status="active",
                    last_active=event.created_at,
                    metadata={"source": "session_event", "event_name": event.event_name},
                )
            )
        payload = _safe_metadata(event.payload)
        created = False
        routing_actor = str(
            payload.get("assigned_to")
            or payload.get("agent_id")
            or event.agent_id
            or ""
        ).strip()
        routingish = (
            "dispatch" in event.event_name
            or "claim" in event.event_name
            or bool(routing_actor)
        )
        if routingish:
            created = await self._record_routing_decision(
                RoutingDecisionRecord(
                    decision_id=_stable_id("session_route", event.event_id),
                    action_name=event.event_name,
                    route_path=str(payload.get("route_path") or payload.get("source") or event.ledger_kind),
                    selected_provider=str(payload.get("selected_provider") or payload.get("provider") or ""),
                    selected_model_hint=str(payload.get("selected_model_hint") or payload.get("model") or ""),
                    confidence=float(payload.get("confidence") or 0.5),
                    requires_human=routing_actor.lower() in {"operator", "human", "user"},
                    session_id=event.session_id,
                    task_id=event.task_id,
                    run_id=event.run_id,
                    reasons=[
                        str(item)
                        for item in (
                            payload.get("reason"),
                            payload.get("failure_signature"),
                            payload.get("source"),
                            event.summary,
                        )
                        if str(item or "").strip()
                    ],
                    metadata={
                        "source": "session_event",
                        "agent_id": routing_actor,
                        "ledger_kind": event.ledger_kind,
                        "payload": payload,
                    },
                    created_at=event.created_at,
                )
            )
        created = (
            await self._record_external_outcome(
            ExternalOutcomeRecord(
                outcome_id=_stable_id("session_event", event.event_id),
                outcome_kind=event.event_name,
                value=1.0,
                unit="event",
                confidence=1.0,
                status=str(payload.get("status") or event.ledger_kind),
                subject_id=event.task_id or event.session_id,
                summary=event.summary or event.event_name,
                session_id=event.session_id,
                task_id=event.task_id,
                run_id=event.run_id,
                metadata={
                    "source": "session_event",
                    "ledger_kind": event.ledger_kind,
                    "payload": payload,
                },
                created_at=event.created_at,
            )
            )
            or created
        )
        return created

    async def _record_external_outcome(self, record: ExternalOutcomeRecord) -> bool:
        try:
            await self.telemetry.record_external_outcome(record)
            return True
        except sqlite3.IntegrityError:
            return False

    async def _record_workflow_score(self, record: WorkflowScoreRecord) -> bool:
        try:
            await self.telemetry.record_workflow_score(record)
            return True
        except sqlite3.IntegrityError:
            return False

    async def _record_routing_decision(self, record: RoutingDecisionRecord) -> bool:
        try:
            await self.telemetry.record_routing_decision(record)
            return True
        except sqlite3.IntegrityError:
            return False

    async def _record_intervention_outcome(self, record: InterventionOutcomeRecord) -> bool:
        try:
            await self.telemetry.record_intervention_outcome(record)
            return True
        except sqlite3.IntegrityError:
            return False
