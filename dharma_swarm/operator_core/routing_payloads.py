"""JSON-ready routing payload builders for the shared operator core."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .adapters import routing_decision_from_policy

ROUTING_PAYLOAD_VERSION = "v1"
ROUTING_DECISION_DOMAIN = "routing_decision"
AGENT_ROUTES_DOMAIN = "agent_routes"


def build_routing_decision_payload(
    policy: dict[str, Any],
    *,
    reason: str = "selected by current routing policy",
) -> dict[str, Any]:
    """Build a canonical routing payload from bridge model-policy state."""

    decision = routing_decision_from_policy(policy, reason=reason)
    return {
        "version": ROUTING_PAYLOAD_VERSION,
        "domain": ROUTING_DECISION_DOMAIN,
        "decision": asdict(decision),
        "strategies": list(policy.get("strategies", [])),
        "targets": list(policy.get("targets", [])),
        "fallback_targets": list(policy.get("fallback_chain", [])),
    }


def build_agent_routes_payload(routes: dict[str, Any]) -> dict[str, Any]:
    """Build a versioned agent-routes payload from bridge route summaries."""

    return {
        "version": ROUTING_PAYLOAD_VERSION,
        "domain": AGENT_ROUTES_DOMAIN,
        "routes": list(routes.get("routes", [])),
        "openclaw": dict(routes.get("openclaw", {})),
        "subagent_capabilities": list(routes.get("subagent_capabilities", [])),
    }
