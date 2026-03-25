"""Assurance Mesh — continuous discrepancy detection.

Deterministic scanners produce facts.
Agents interpret, prioritize, and patch.
"""

__version__ = "0.1.0"

from dharma_swarm.assurance.agents import (
    ALL_AGENTS,
    DIFF_SCOUT_CONFIG,
    JUDGE_CONFIG,
    RUNTIME_SCOUT_CONFIG,
    SURGEON_CONFIG,
)

__all__ = [
    "ALL_AGENTS",
    "DIFF_SCOUT_CONFIG",
    "RUNTIME_SCOUT_CONFIG",
    "SURGEON_CONFIG",
    "JUDGE_CONFIG",
]
