"""telos-gatekeeper: dharmic constraint enforcement for autonomous AI agents.

This is the standalone pip-installable extraction of the TelosGatekeeper
from DHARMA SWARM. It provides the same 11 dharmic gates, reflective
rerouting, and GateCheckResult infrastructure — without the full swarm.

Full implementation: dharma_swarm/telos_gates.py in the parent repo.
This package re-exports the public interface.
"""
from __future__ import annotations

# Re-export public interface
# When installed as part of dharma_swarm, pull from there.
# When installed standalone, use bundled implementation.
try:
    from dharma_swarm.telos_gates import (
        TelosGatekeeper,
        GateProposal,
        GateCheckResult,
        GateRegistry,
        ReflectiveGateOutcome,
        check_action,
        check_with_reflective_reroute,
    )
except ImportError:
    from telos_gatekeeper._standalone import (  # type: ignore[no-redef]
        TelosGatekeeper,
        GateProposal,
        GateCheckResult,
        GateRegistry,
        ReflectiveGateOutcome,
        check_action,
        check_with_reflective_reroute,
    )

__all__ = [
    "TelosGatekeeper",
    "GateProposal",
    "GateCheckResult",
    "GateRegistry",
    "ReflectiveGateOutcome",
    "check_action",
    "check_with_reflective_reroute",
]

__version__ = "0.1.0"
