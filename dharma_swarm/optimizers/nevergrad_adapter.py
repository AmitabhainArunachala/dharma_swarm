"""Guarded Nevergrad adapter."""

from __future__ import annotations

from importlib.util import find_spec

from dharma_swarm.optimizer_bridge import OptimizerAdapterAvailability


def get_nevergrad_adapter() -> OptimizerAdapterAvailability:
    available = find_spec("nevergrad") is not None
    if available:
        return OptimizerAdapterAvailability(name="nevergrad", available=True)
    return OptimizerAdapterAvailability(
        name="nevergrad",
        available=False,
        reason="Optional dependency 'nevergrad' is not installed.",
    )
