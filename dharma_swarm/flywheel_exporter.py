"""Canonical workload exporter for the optional NVIDIA Data Flywheel lane.

This module does not upload data directly. It assembles a provenance-rich local
export from the canonical runtime seams, records the export as an artifact, and
emits an audited receipt so remote job creation can layer on later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from dharma_swarm.artifact_manifest import ArtifactManifestStore
from dharma_swarm.engine.artifacts import ArtifactRef
from dharma_swarm.event_log import EventLog
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import (
    ArtifactRecord,
    ContextBundleRecord,
    DelegationRun,
    MemoryFact,
    OperatorAction,
    RuntimeStateStore,
    SessionState,
    WorkspaceLease,
)


DEFAULT_FLYWHEEL_EXPORT_ROOT = Path.home() / ".dharma" / "exports" / "flywheel"
FLYWHEEL_EXPORT_SCHEMA_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _duration_seconds(started_at: datetime, completed_at: datetime | None) -> float | None:
    if completed_at is None:
        return None
    return round(max((completed_at - started_at).total_seconds(), 0.0), 3)


@dataclass(frozen=True, slots=True)
class FlywheelWorkloadRecord:
    export_id: str
    workload_id: str
    client_id: str
    run_id: str
    task_id: str
    session_id: str
    trace_id: str
    status: str
    assigned_to: str
    assigned_by: str
    requested_output: list[str]
    artifact_id: str
    run: dict[str, Any]
    session: dict[str, Any] | None
    artifacts: list[dict[str, Any]]
    memory_facts: list[dict[str, Any]]
    context_bundles: list[dict[str, Any]]
    operator_actions: list[dict[str, Any]]
    workspace_leases: list[dict[str, Any]]
    events: list[dict[str, Any]]
    metrics: dict[str, Any] = field(default_factory=dict)
    job_request: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    exported_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = FLYWHEEL_EXPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "export_id": self.export_id,
            "artifact_id": self.artifact_id,
            "workload_id": self.workload_id,
            "client_id": self.client_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "assigned_by": self.assigned_by,
            "requested_output": list(self.requested_output),
            "run": dict(self.run),
            "session": dict(self.session) if self.session is not None else None,
            "artifacts": list(self.artifacts),
            "memory_facts": list(self.memory_facts),
            "context_bundles": list(self.context_bundles),
            "operator_actions": list(self.operator_actions),
            "workspace_leases": list(self.workspace_leases),
            "events": list(self.events),
            "metrics": dict(self.metrics),
            "job_request": dict(self.job_request),
            "metadata": dict(self.metadata),
            "exported_at": self.exported_at,
        }


@dataclass(frozen=True, slots=True)
class FlywheelExportResult:
    record: FlywheelWorkloadRecord
    export_path: Path
    manifest_path: Path
    artifact: ArtifactRecord
    receipt: dict[str, Any]


class FlywheelExporter:
    """Materialize flywheel-ready workload exports from canonical runtime truth."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore | None = None,
        memory_lattice: MemoryLattice | None = None,
        event_log: EventLog | None = None,
        export_root: Path | str | None = None,
    ) -> None:
        if runtime_state is None and memory_lattice is None:
            raise ValueError("flywheel exporter requires runtime_state or memory_lattice")
        self.memory_lattice = memory_lattice or MemoryLattice(
            db_path=runtime_state.db_path if runtime_state is not None else None,
            event_log_dir=event_log.base_dir if event_log is not None else None,
        )
        self.runtime_state = runtime_state or self.memory_lattice.runtime_state
        self.event_log = event_log or self.memory_lattice.event_log
        self.export_root = Path(export_root or DEFAULT_FLYWHEEL_EXPORT_ROOT)
        self._manifest_store = ArtifactManifestStore()

    async def export_run(
        self,
        *,
        run_id: str,
        workload_id: str,
        client_id: str,
        trace_id: str | None = None,
        created_by: str = "flywheel.exporter",
        promotion_state: str = "shared",
        data_split_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        included_truth_states: tuple[str, ...] = ("promoted", "accepted", "confirmed"),
        artifact_limit: int = 50,
        fact_limit: int = 50,
        context_limit: int = 20,
        operator_action_limit: int = 50,
        event_limit: int = 200,
        workspace_lease_limit: int = 20,
    ) -> FlywheelExportResult:
        await self.runtime_state.init_db()
        await self.memory_lattice.init_db()

        run = await self.runtime_state.get_delegation_run(run_id)
        if run is None:
            raise KeyError(f"delegation run {run_id} not found")

        session = await self._load_session(run.session_id)
        artifacts = await self.runtime_state.list_artifacts(run_id=run.run_id, limit=max(1, artifact_limit))
        resolved_trace_id = self._resolve_trace_id(trace_id=trace_id, run=run, artifacts=artifacts)
        events, event_scope = await self._collect_events(
            run,
            artifacts=artifacts,
            trace_id=resolved_trace_id,
            limit=max(1, event_limit),
        )
        event_ids = {str(item.get("event_id", "")) for item in events if item.get("event_id")}

        facts = await self._collect_memory_facts(
            run,
            artifacts=artifacts,
            event_ids=event_ids,
            included_truth_states={state for state in included_truth_states},
            limit=max(1, fact_limit),
        )
        bundles = await self.runtime_state.list_context_bundles(
            session_id=run.session_id or None,
            task_id=run.task_id or None,
            run_id=run.run_id or None,
            limit=max(1, context_limit),
        )
        actions = await self._collect_operator_actions(run, limit=max(1, operator_action_limit))
        leases = await self.runtime_state.list_workspace_leases(
            holder_run_id=run.run_id,
            active_only=False,
            limit=max(1, workspace_lease_limit),
        )

        export_id = run.metadata.get("flywheel_export_id") or f"flyexp_{run.run_id}"
        export_artifact_id = str(export_id)
        job_request: dict[str, Any] = {
            "workload_id": workload_id,
            "client_id": client_id,
        }
        if data_split_config:
            job_request["data_split_config"] = dict(data_split_config)

        record = FlywheelWorkloadRecord(
            export_id=str(export_id),
            artifact_id=export_artifact_id,
            workload_id=workload_id,
            client_id=client_id,
            run_id=run.run_id,
            task_id=run.task_id,
            session_id=run.session_id,
            trace_id=resolved_trace_id,
            status=run.status,
            assigned_to=run.assigned_to,
            assigned_by=run.assigned_by,
            requested_output=list(run.requested_output),
            run=self._serialize_run(run),
            session=self._serialize_session(session) if session is not None else None,
            artifacts=[self._serialize_artifact(artifact) for artifact in artifacts],
            memory_facts=[self._serialize_fact(fact) for fact in facts],
            context_bundles=[self._serialize_context_bundle(bundle) for bundle in bundles],
            operator_actions=[self._serialize_operator_action(action) for action in actions],
            workspace_leases=[self._serialize_workspace_lease(lease) for lease in leases],
            events=events,
            metrics=self._build_metrics(
                run,
                artifacts=artifacts,
                facts=facts,
                bundles=bundles,
                actions=actions,
                leases=leases,
                events=events,
            ),
            job_request=job_request,
            metadata={
                "event_scope": event_scope,
                "included_truth_states": sorted({state for state in included_truth_states}),
                **dict(metadata or {}),
            },
        )
        export_path = self._write_record(record)
        artifact, manifest_path = await self._record_export_artifact(
            record,
            export_path=export_path,
            created_by=created_by,
            promotion_state=promotion_state,
        )
        receipt = self._append_receipt(
            record,
            artifact=artifact,
            export_path=export_path,
            created_by=created_by,
        )
        return FlywheelExportResult(
            record=record,
            export_path=export_path,
            manifest_path=manifest_path,
            artifact=artifact,
            receipt=receipt,
        )

    async def _load_session(self, session_id: str) -> SessionState | None:
        if not session_id:
            return None
        return await self.runtime_state.get_session(session_id)

    def _resolve_trace_id(
        self,
        *,
        trace_id: str | None,
        run: DelegationRun,
        artifacts: list[ArtifactRecord],
    ) -> str:
        if trace_id:
            return trace_id
        run_trace = str(run.metadata.get("trace_id", "")).strip()
        if run_trace:
            return run_trace
        current_artifact_trace = self._artifact_trace_id(
            run.current_artifact_id,
            artifacts=artifacts,
        )
        if current_artifact_trace:
            return current_artifact_trace
        for artifact in artifacts:
            manifest_trace = self._artifact_trace_id(artifact.artifact_id, artifacts=[artifact])
            if manifest_trace:
                return manifest_trace
        return ""

    async def _collect_events(
        self,
        run: DelegationRun,
        *,
        artifacts: list[ArtifactRecord],
        trace_id: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str]:
        if trace_id:
            rows = await self.memory_lattice.replay_trace(trace_id, limit=limit)
            return ([self._serialize_event(event) for event in rows], "trace")
        if not run.session_id:
            return ([], "none")
        raw_events = await self.memory_lattice.replay_session(
            run.session_id,
            limit=max(limit * 4, limit),
        )
        artifact_ids = {artifact.artifact_id for artifact in artifacts}
        filtered = [
            self._serialize_event(event)
            for event in raw_events
            if self._event_matches_run(event, run=run, artifact_ids=artifact_ids)
        ]
        return (filtered[:limit], "session_filtered")

    async def _collect_memory_facts(
        self,
        run: DelegationRun,
        *,
        artifacts: list[ArtifactRecord],
        event_ids: set[str],
        included_truth_states: set[str],
        limit: int,
    ) -> list[MemoryFact]:
        candidates: list[MemoryFact] = []
        seen: set[str] = set()
        if run.task_id:
            for fact in await self.runtime_state.list_memory_facts(task_id=run.task_id, limit=max(limit * 2, limit)):
                if fact.fact_id not in seen:
                    candidates.append(fact)
                    seen.add(fact.fact_id)
        if run.session_id and len(candidates) < limit:
            for fact in await self.runtime_state.list_memory_facts(session_id=run.session_id, limit=max(limit * 2, limit)):
                if fact.fact_id not in seen:
                    candidates.append(fact)
                    seen.add(fact.fact_id)
        artifact_ids = {artifact.artifact_id for artifact in artifacts}
        selected = [
            fact
            for fact in candidates
            if fact.truth_state in included_truth_states
            and self._fact_matches_run(fact, run=run, artifact_ids=artifact_ids, event_ids=event_ids)
        ]
        return selected[:limit]

    async def _collect_operator_actions(
        self,
        run: DelegationRun,
        *,
        limit: int,
    ) -> list[OperatorAction]:
        actions = await self.runtime_state.list_operator_actions(
            session_id=run.session_id or None,
            task_id=run.task_id or None,
            limit=max(limit * 3, limit),
        )
        selected = [
            action
            for action in actions
            if self._operator_action_matches_run(action, run=run)
        ]
        return selected[:limit]

    def _write_record(self, record: FlywheelWorkloadRecord) -> Path:
        path = self.export_root / record.workload_id / f"{record.run_id}_{record.export_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    async def _record_export_artifact(
        self,
        record: FlywheelWorkloadRecord,
        *,
        export_path: Path,
        created_by: str,
        promotion_state: str,
    ) -> tuple[ArtifactRecord, Path]:
        ref = ArtifactRef(
            artifact_id=record.artifact_id,
            artifact_type="evaluations",
            path=str(export_path),
            created_by=created_by,
            session_id=record.session_id,
            version=1,
            depends_on=[artifact["artifact_id"] for artifact in record.artifacts],
            metadata={
                "export_id": record.export_id,
                "workload_id": record.workload_id,
                "client_id": record.client_id,
                "schema_version": record.schema_version,
                "trace_id": record.trace_id,
            },
        )
        manifest, manifest_path = self._manifest_store.record_manifest(
            ref,
            artifact_kind="flywheel_export",
            task_id=record.task_id,
            run_id=record.run_id,
            trace_id=record.trace_id,
            promotion_state=promotion_state,
            provenance={
                "export_id": record.export_id,
                "workload_id": record.workload_id,
                "client_id": record.client_id,
            },
            metadata={
                "artifact_count": len(record.artifacts),
                "fact_count": len(record.memory_facts),
                "event_count": len(record.events),
            },
        )
        artifact = self._manifest_store.to_artifact_record(
            manifest,
            manifest_path=manifest_path,
        )
        return (await self.runtime_state.record_artifact(artifact), manifest_path)

    def _append_receipt(
        self,
        record: FlywheelWorkloadRecord,
        *,
        artifact: ArtifactRecord,
        export_path: Path,
        created_by: str,
    ) -> dict[str, Any]:
        envelope = RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="flywheel.exporter",
            agent_id=created_by,
            session_id=record.session_id or "system",
            trace_id=record.trace_id or record.export_id,
            payload={
                "action_name": "flywheel_export",
                "decision": "recorded",
                "confidence": 1.0,
                "export_id": record.export_id,
                "artifact_id": artifact.artifact_id,
                "run_id": record.run_id,
                "workload_id": record.workload_id,
                "client_id": record.client_id,
                "export_path": str(export_path),
                "artifact_count": len(record.artifacts),
                "fact_count": len(record.memory_facts),
                "event_count": len(record.events),
            },
        )
        return self.event_log.append_envelope(envelope, stream="flywheel_exports")

    def _artifact_trace_id(
        self,
        artifact_id: str,
        *,
        artifacts: list[ArtifactRecord],
    ) -> str:
        if not artifact_id:
            return ""
        for artifact in artifacts:
            if artifact.artifact_id != artifact_id:
                continue
            trace = str(artifact.metadata.get("trace_id", "")).strip()
            if trace:
                return trace
            manifest = self._read_manifest(artifact.manifest_path)
            if manifest is not None:
                manifest_trace = str(manifest.get("trace_id", "")).strip()
                if manifest_trace:
                    return manifest_trace
        return ""

    def _read_manifest(self, manifest_path: str) -> dict[str, Any] | None:
        if not manifest_path:
            return None
        path = Path(manifest_path)
        if not path.exists():
            return None
        try:
            return self._manifest_store.read_manifest(path).to_dict()
        except Exception:
            return None

    def _serialize_run(self, run: DelegationRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "task_id": run.task_id,
            "session_id": run.session_id,
            "claim_id": run.claim_id,
            "parent_run_id": run.parent_run_id,
            "assigned_by": run.assigned_by,
            "assigned_to": run.assigned_to,
            "status": run.status,
            "requested_output": list(run.requested_output),
            "current_artifact_id": run.current_artifact_id,
            "failure_code": run.failure_code,
            "started_at": _dt_iso(run.started_at),
            "completed_at": _dt_iso(run.completed_at),
            "metadata": dict(run.metadata),
        }

    def _serialize_session(self, session: SessionState) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "operator_id": session.operator_id,
            "status": session.status,
            "current_task_id": session.current_task_id,
            "active_bundle_id": session.active_bundle_id,
            "created_at": _dt_iso(session.created_at),
            "updated_at": _dt_iso(session.updated_at),
            "metadata": dict(session.metadata),
        }

    def _serialize_artifact(self, artifact: ArtifactRecord) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_kind": artifact.artifact_kind,
            "session_id": artifact.session_id,
            "task_id": artifact.task_id,
            "run_id": artifact.run_id,
            "manifest_path": artifact.manifest_path,
            "payload_path": artifact.payload_path,
            "checksum": artifact.checksum,
            "parent_artifact_id": artifact.parent_artifact_id,
            "promotion_state": artifact.promotion_state,
            "created_at": _dt_iso(artifact.created_at),
            "metadata": dict(artifact.metadata),
            "manifest": self._read_manifest(artifact.manifest_path),
        }

    def _serialize_fact(self, fact: MemoryFact) -> dict[str, Any]:
        return {
            "fact_id": fact.fact_id,
            "fact_kind": fact.fact_kind,
            "truth_state": fact.truth_state,
            "text": fact.text,
            "confidence": fact.confidence,
            "session_id": fact.session_id,
            "task_id": fact.task_id,
            "valid_from": _dt_iso(fact.valid_from),
            "valid_to": _dt_iso(fact.valid_to),
            "source_event_id": fact.source_event_id,
            "source_artifact_id": fact.source_artifact_id,
            "provenance": dict(fact.provenance),
            "metadata": dict(fact.metadata),
            "created_at": _dt_iso(fact.created_at),
            "updated_at": _dt_iso(fact.updated_at),
        }

    def _serialize_context_bundle(self, bundle: ContextBundleRecord) -> dict[str, Any]:
        return {
            "bundle_id": bundle.bundle_id,
            "session_id": bundle.session_id,
            "task_id": bundle.task_id,
            "run_id": bundle.run_id,
            "token_budget": bundle.token_budget,
            "rendered_text": bundle.rendered_text,
            "sections": list(bundle.sections),
            "source_refs": list(bundle.source_refs),
            "checksum": bundle.checksum,
            "created_at": _dt_iso(bundle.created_at),
            "metadata": dict(bundle.metadata),
        }

    def _serialize_operator_action(self, action: OperatorAction) -> dict[str, Any]:
        return {
            "action_id": action.action_id,
            "action_name": action.action_name,
            "actor": action.actor,
            "session_id": action.session_id,
            "task_id": action.task_id,
            "run_id": action.run_id,
            "reason": action.reason,
            "payload": dict(action.payload),
            "created_at": _dt_iso(action.created_at),
        }

    def _serialize_workspace_lease(self, lease: WorkspaceLease) -> dict[str, Any]:
        return {
            "lease_id": lease.lease_id,
            "zone_path": lease.zone_path,
            "holder_run_id": lease.holder_run_id,
            "mode": lease.mode,
            "base_hash": lease.base_hash,
            "acquired_at": _dt_iso(lease.acquired_at),
            "expires_at": _dt_iso(lease.expires_at),
            "released_at": _dt_iso(lease.released_at),
            "metadata": dict(lease.metadata),
        }

    def _serialize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": str(event.get("event_id", "")),
            "session_id": str(event.get("session_id", "")),
            "trace_id": str(event.get("trace_id", "")),
            "event_type": str(event.get("event_type", "")),
            "source": str(event.get("source", "")),
            "agent_id": str(event.get("agent_id", "")),
            "emitted_at": str(event.get("emitted_at", "")),
            "payload": dict(event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}),
            "checksum": str(event.get("checksum", "")),
        }

    def _build_metrics(
        self,
        run: DelegationRun,
        *,
        artifacts: list[ArtifactRecord],
        facts: list[MemoryFact],
        bundles: list[ContextBundleRecord],
        actions: list[OperatorAction],
        leases: list[WorkspaceLease],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "artifact_count": len(artifacts),
            "fact_count": len(facts),
            "context_bundle_count": len(bundles),
            "operator_action_count": len(actions),
            "workspace_lease_count": len(leases),
            "event_count": len(events),
            "duration_seconds": _duration_seconds(run.started_at, run.completed_at),
        }

    def _event_matches_run(
        self,
        event: dict[str, Any],
        *,
        run: DelegationRun,
        artifact_ids: set[str],
    ) -> bool:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        if str(payload.get("run_id", "")) == run.run_id:
            return True
        if str(payload.get("task_id", "")) == run.task_id:
            return True
        if str(payload.get("bridge_task_id", "")) == run.task_id:
            return True
        if str(payload.get("holder_run_id", "")) == run.run_id:
            return True
        current_artifact_id = str(payload.get("current_artifact_id", ""))
        if current_artifact_id and current_artifact_id in artifact_ids:
            return True
        payload_artifact_ids = payload.get("artifact_ids")
        if isinstance(payload_artifact_ids, list):
            if artifact_ids.intersection({str(value) for value in payload_artifact_ids}):
                return True
        nested = payload.get("metadata")
        if isinstance(nested, dict):
            if str(nested.get("run_id", "")) == run.run_id:
                return True
            if str(nested.get("task_id", "")) == run.task_id:
                return True
        return False

    def _fact_matches_run(
        self,
        fact: MemoryFact,
        *,
        run: DelegationRun,
        artifact_ids: set[str],
        event_ids: set[str],
    ) -> bool:
        if fact.task_id and fact.task_id == run.task_id:
            return True
        if fact.source_artifact_id and fact.source_artifact_id in artifact_ids:
            return True
        if fact.source_event_id and fact.source_event_id in event_ids:
            return True
        return False

    def _operator_action_matches_run(
        self,
        action: OperatorAction,
        *,
        run: DelegationRun,
    ) -> bool:
        if action.run_id and action.run_id != run.run_id:
            return False
        if action.task_id and action.task_id != run.task_id:
            return False
        if action.session_id and run.session_id and action.session_id != run.session_id:
            return False
        return True
