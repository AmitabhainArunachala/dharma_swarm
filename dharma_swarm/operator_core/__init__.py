"""Shared operator-core contracts for the DGC shells.

This package is the shell-neutral foundation for the Bun TUI and dashboard UI.
It does not own rendering concerns. It owns the canonical shapes that both
shells must agree on when they talk about sessions, runtime truth, entities,
permissions, and orchestration state.
"""

from .adapters import (
    event_envelope_from_legacy_event,
    permission_decision_from_tool_call,
    routing_decision_from_policy,
    runtime_snapshot_from_operator_snapshot,
    session_from_meta,
)
from .permissions import GovernanceFilter, GovernancePolicy
from .permission_payloads import (
    build_permission_decision_payload,
    build_permission_history_payload,
    build_permission_outcome_payload,
    build_permission_resolution_payload,
    permission_decision_payload_from_decision,
    permission_outcome_payload_from_outcome,
    permission_resolution_payload_from_resolution,
)
from .routing_payloads import build_agent_routes_payload, build_routing_decision_payload
from .runtime_payloads import build_runtime_snapshot_payload
from .workspace_payloads import build_workspace_snapshot_payload
from .session_payloads import build_session_catalog_payload, build_session_detail_payload
from .session_store import SessionStore, cwd_matches
from .session_views import build_session_catalog, build_session_detail
from .contracts import (
    CanonicalEntity,
    CanonicalEventEnvelope,
    CanonicalPermissionDecision,
    CanonicalPermissionResolution,
    CanonicalRelation,
    CanonicalRoutingDecision,
    CanonicalRuntimeSnapshot,
    CanonicalSession,
    CanonicalWorkflowState,
    EntityBadge,
    EntityRef,
    EventAudience,
    EventSource,
    EventTransport,
    PermissionDecisionKind,
    PermissionResolutionKind,
    PermissionRisk,
    RuntimeHealth,
    WorkflowExecutionMode,
)

__all__ = [
    "CanonicalEntity",
    "CanonicalEventEnvelope",
    "CanonicalPermissionDecision",
    "CanonicalPermissionResolution",
    "CanonicalRelation",
    "CanonicalRoutingDecision",
    "CanonicalRuntimeSnapshot",
    "CanonicalSession",
    "CanonicalWorkflowState",
    "EntityBadge",
    "EntityRef",
    "EventAudience",
    "EventSource",
    "EventTransport",
    "GovernanceFilter",
    "GovernancePolicy",
    "build_permission_decision_payload",
    "build_permission_history_payload",
    "build_permission_outcome_payload",
    "build_permission_resolution_payload",
    "build_agent_routes_payload",
    "build_routing_decision_payload",
    "build_runtime_snapshot_payload",
    "build_workspace_snapshot_payload",
    "PermissionDecisionKind",
    "PermissionResolutionKind",
    "PermissionRisk",
    "RuntimeHealth",
    "SessionStore",
    "WorkflowExecutionMode",
    "build_session_catalog",
    "build_session_catalog_payload",
    "build_session_detail",
    "build_session_detail_payload",
    "cwd_matches",
    "event_envelope_from_legacy_event",
    "permission_decision_from_tool_call",
    "permission_decision_payload_from_decision",
    "permission_outcome_payload_from_outcome",
    "permission_resolution_payload_from_resolution",
    "routing_decision_from_policy",
    "runtime_snapshot_from_operator_snapshot",
    "session_from_meta",
]
