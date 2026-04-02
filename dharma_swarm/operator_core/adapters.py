"""Adapters from legacy TUI/bridge shapes into shell-neutral operator-core contracts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any
from uuid import uuid4

from dharma_swarm.tui.engine.events import CanonicalEvent as LegacyCanonicalEvent
from dharma_swarm.tui.engine.events import ToolCallComplete

from .contracts import (
    CanonicalEventEnvelope,
    CanonicalPermissionDecision,
    CanonicalRoutingDecision,
    CanonicalRuntimeSnapshot,
    CanonicalSession,
    EventAudience,
    EventSource,
    EventTransport,
    PermissionDecisionKind,
    PermissionRisk,
    RuntimeHealth,
)
from .permissions import GovernancePolicy


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_to_iso(value: float | int | None) -> str:
    if value is None:
        return _now_iso()
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_runtime_health(snapshot: dict[str, Any]) -> RuntimeHealth:
    error = str(snapshot.get("error", "") or "").strip()
    if error:
        return RuntimeHealth.CRITICAL

    overview = snapshot.get("overview", {})
    if not isinstance(overview, dict):
        return RuntimeHealth.UNKNOWN

    active_runs = _coerce_int(overview.get("active_runs"))
    runs = _coerce_int(overview.get("runs"))
    sessions = _coerce_int(overview.get("sessions"))
    if runs > 0 and active_runs == 0 and sessions == 0:
        return RuntimeHealth.DEGRADED
    return RuntimeHealth.OK


def _preview_string(preview: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(preview, dict):
        return None
    for key in keys:
        value = preview.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _tool_risk(tool_name: str, arguments: str) -> PermissionRisk:
    normalized = tool_name.strip()
    if normalized in {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}:
        return PermissionRisk.SAFE_READ
    if normalized in {"Write", "Edit", "NotebookEdit"}:
        return PermissionRisk.WORKSPACE_MUTATION
    if normalized == "Bash":
        lowered = arguments.lower()
        if any(token in lowered for token in ("rm -", "git reset --hard", "git checkout --", "sudo ")):
            return PermissionRisk.DESTRUCTIVE
        return PermissionRisk.SHELL_OR_NETWORK
    return PermissionRisk.CROSS_BOUNDARY_MUTATION


def event_envelope_from_legacy_event(
    event: LegacyCanonicalEvent,
    *,
    audience: EventAudience = EventAudience.ALL,
    transport: EventTransport = EventTransport.LOCAL,
) -> CanonicalEventEnvelope:
    """Map the existing provider-agnostic TUI event into the shared shell-neutral envelope."""

    payload = asdict(event)
    event_type = str(payload.pop("type", event.type))
    session_id = str(payload.get("session_id", "") or "").strip() or None
    return CanonicalEventEnvelope(
        event_id=f"evt-{uuid4()}",
        event_type=event_type,
        source=EventSource.PROVIDER,
        audience=audience,
        transport=transport,
        session_id=session_id,
        created_at=_timestamp_to_iso(getattr(event, "timestamp", None)),
        payload=payload,
        raw=payload.get("raw"),
    )


def session_from_meta(meta: dict[str, Any]) -> CanonicalSession:
    """Normalize persisted session metadata from the legacy TUI store."""

    return CanonicalSession(
        session_id=str(meta.get("session_id", "") or ""),
        provider_id=str(meta.get("provider_id", "") or ""),
        model_id=str(meta.get("model_id", "") or ""),
        cwd=str(meta.get("cwd", "") or ""),
        created_at=str(meta.get("created_at", "") or _now_iso()),
        updated_at=str(meta.get("updated_at", "") or _now_iso()),
        status=str(meta.get("status", "") or "unknown"),
        parent_session_id=str(meta.get("parent_session_id", "") or "").strip() or None,
        branch_label=str(meta.get("git_branch", "") or "").strip() or None,
        worktree_path=str(meta.get("cwd", "") or "").strip() or None,
        summary=str(meta.get("title", "") or "").strip() or None,
        metadata={
            "provider_session_id": meta.get("provider_session_id"),
            "total_cost_usd": meta.get("total_cost_usd"),
            "total_turns": meta.get("total_turns"),
            "total_input_tokens": meta.get("total_input_tokens"),
            "total_output_tokens": meta.get("total_output_tokens"),
            "tags": meta.get("tags", []),
            "forked_from": meta.get("forked_from"),
        },
    )


def routing_decision_from_policy(
    policy: dict[str, Any],
    *,
    reason: str = "selected by current routing policy",
) -> CanonicalRoutingDecision:
    """Map terminal bridge model policy summaries into the shared routing contract."""

    fallback_chain = []
    for item in policy.get("fallback_chain", []):
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider", "") or "").strip()
        model = str(item.get("model", "") or "").strip()
        if provider and model:
            fallback_chain.append(f"{provider}:{model}")

    return CanonicalRoutingDecision(
        route_id=str(policy.get("selected_route", "") or "unknown"),
        provider_id=str(policy.get("selected_provider", "") or ""),
        model_id=str(policy.get("selected_model", "") or ""),
        strategy=str(policy.get("strategy", "") or "responsive"),
        reason=reason,
        fallback_chain=fallback_chain,
        degraded=not bool(policy.get("targets")),
        metadata={
            "active_label": policy.get("active_label"),
            "default_route": policy.get("default_route"),
            "targets": policy.get("targets", []),
        },
    )


def runtime_snapshot_from_operator_snapshot(
    snapshot: dict[str, Any],
    *,
    repo_root: str,
    bridge_status: str,
    supervisor_preview: dict[str, Any] | None = None,
) -> CanonicalRuntimeSnapshot:
    """Map operator snapshot payloads into the shared runtime truth contract."""

    overview = snapshot.get("overview", {})
    if not isinstance(overview, dict):
        overview = {}

    warnings: list[str] = []
    error = str(snapshot.get("error", "") or "").strip()
    if error:
        warnings.append(error)

    runs = snapshot.get("runs", [])
    if isinstance(runs, list):
        failed = [
            run for run in runs if isinstance(run, dict) and str(run.get("failure_code", "") or "").strip()
        ]
        if failed:
            warnings.append(f"{len(failed)} active runs report failure codes")

    verification_status = (
        _preview_string(supervisor_preview, "Verification status", "verification_status")
        or "unknown"
    )
    next_task = _preview_string(supervisor_preview, "Next task", "next_task")
    active_task = _preview_string(supervisor_preview, "Active task", "active_task")

    summary = (
        f"{_coerce_int(overview.get('active_runs'))} active runs, "
        f"{_coerce_int(overview.get('context_bundles'))} context bundles, "
        f"{_coerce_int(overview.get('artifacts'))} artifacts"
    )
    return CanonicalRuntimeSnapshot(
        snapshot_id=f"runtime-{uuid4()}",
        created_at=_now_iso(),
        repo_root=repo_root,
        runtime_db=str(snapshot.get("runtime_db", "") or "") or None,
        health=_coerce_runtime_health(snapshot),
        bridge_status=bridge_status,
        active_session_count=_coerce_int(overview.get("sessions")),
        active_run_count=_coerce_int(overview.get("active_runs")),
        artifact_count=_coerce_int(overview.get("artifacts")),
        context_bundle_count=_coerce_int(overview.get("context_bundles")),
        anomaly_count=len(warnings),
        verification_status=verification_status,
        next_task=next_task,
        active_task=active_task,
        summary=summary,
        warnings=warnings,
        metrics={
            "claims": str(_coerce_int(overview.get("claims"))),
            "active_claims": str(_coerce_int(overview.get("active_claims"))),
            "acknowledged_claims": str(_coerce_int(overview.get("acknowledged_claims"))),
            "operator_actions": str(_coerce_int(overview.get("operator_actions"))),
            "promoted_facts": str(_coerce_int(overview.get("promoted_facts"))),
        },
        metadata={
            "overview": overview,
            "runs": runs if isinstance(runs, list) else [],
            "actions": snapshot.get("actions", []),
            "supervisor_preview": supervisor_preview or {},
        },
    )


def permission_decision_from_tool_call(
    event: ToolCallComplete,
    *,
    policy: GovernancePolicy | None = None,
    policy_source: str = "legacy-governance",
) -> CanonicalPermissionDecision:
    """Map legacy governance/tool-call state into the shared permission decision contract."""

    active_policy = policy or GovernancePolicy()
    tool_name = str(event.tool_name or "").strip() or "unknown"
    arguments = str(event.arguments or "")
    risk = _tool_risk(tool_name, arguments)

    if tool_name in active_policy.blocked_tools:
        decision = PermissionDecisionKind.DENY
        rationale = f"{tool_name} is blocked by governance policy"
        requires_confirmation = False
    elif tool_name in active_policy.gated_tools or bool(event.provider_options.get("requires_confirmation")):
        decision = PermissionDecisionKind.REQUIRE_APPROVAL
        rationale = f"{tool_name} is gated and requires operator confirmation"
        requires_confirmation = True
    elif tool_name in active_policy.auto_approved_tools:
        decision = PermissionDecisionKind.ALLOW
        rationale = f"{tool_name} is auto-approved under current governance policy"
        requires_confirmation = False
    else:
        decision = PermissionDecisionKind.REQUIRE_APPROVAL
        rationale = f"{tool_name} is not classified as safe and remains operator-gated"
        requires_confirmation = True

    action_basis = f"{tool_name}:{arguments}".encode("utf-8", errors="ignore")
    return CanonicalPermissionDecision(
        action_id=f"perm-{sha1(action_basis).hexdigest()[:12]}",
        tool_name=tool_name,
        risk=risk,
        decision=decision,
        rationale=rationale,
        policy_source=policy_source,
        requires_confirmation=requires_confirmation,
        command_prefix=arguments[:120].strip() or None,
        metadata={
            "tool_call_id": event.tool_call_id,
            "provider_options": dict(event.provider_options),
            "provider_id": event.provider_id,
            "session_id": event.session_id,
        },
    )
