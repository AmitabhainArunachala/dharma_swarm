"""Guarded textual-gradient adapter."""

from __future__ import annotations

from importlib.util import find_spec

from dharma_swarm.optimizer_bridge import OptimizerAdapterAvailability


def get_textgrad_adapter() -> OptimizerAdapterAvailability:
    available = find_spec("textgrad") is not None
    if available:
        return OptimizerAdapterAvailability(
            name="textgrad",
            available=True,
            supports_prompt_only=True,
        )
    return OptimizerAdapterAvailability(
        name="textgrad",
        available=False,
        reason="Optional dependency 'textgrad' is not installed.",
        supports_prompt_only=True,
    )
