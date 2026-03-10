"""Backward-compatible probe target aliases over execution profiles."""

from dharma_swarm.execution_profile import (
    ExecutionProfile as ProbeTarget,
    ExecutionProfileRegistry as ProbeTargetRegistry,
    ResolvedExecutionProfile as ResolvedProbeTarget,
)

__all__ = ["ProbeTarget", "ProbeTargetRegistry", "ResolvedProbeTarget"]
