"""Mathematical elegance bridges — making the math load-bearing.

Hofstadter's strange loops: the math should BE the architecture.

This module provides thin integration bridges that connect the
category theory modules (sheaf, monad, coalgebra, info_geometry)
to the runtime systems (orchestrator, agent_runner, evolution, routing).

Each bridge is a pure function or small class, tested independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge 1: Monadic Task Composition
# Task.bind(f).bind(g) instead of nested try/except
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    """Monadic wrapper for task pipeline results.

    Provides bind() for composing task steps without nested try/except.
    Failed steps short-circuit the chain (like Either monad).
    """

    value: Any = None
    error: str | None = None
    steps: list[str] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return self.error is None

    def bind(self, fn: Callable[[Any], "TaskResult"], label: str = "") -> "TaskResult":
        """Kleisli composition: if this result is ok, apply fn to the value.

        If this result is an error, propagate it (short-circuit).
        This is the monadic bind (>>=) operation.
        """
        if not self.is_ok:
            return self
        try:
            result = fn(self.value)
            result.steps = self.steps + [label or fn.__name__]
            return result
        except Exception as exc:
            return TaskResult(
                error=f"{label or fn.__name__}: {exc}",
                steps=self.steps + [f"{label or fn.__name__} (FAILED)"],
            )

    @classmethod
    def pure(cls, value: Any) -> "TaskResult":
        """Unit/return: lift a value into the monad."""
        return cls(value=value)

    @classmethod
    def fail(cls, error: str) -> "TaskResult":
        """Create a failed result."""
        return cls(error=error)


# ---------------------------------------------------------------------------
# Bridge 2: Coalgebraic Agent Lifecycle
# unfold: State -> (Output, State)  — agent as a coalgebraic machine
# ---------------------------------------------------------------------------

@dataclass
class AgentObservation:
    """F(S) — the observable output of one agent lifecycle step."""

    output: str
    next_status: str  # "idle", "busy", "stopping", "dead"
    fitness: float = 0.0
    tasks_completed: int = 0


def unfold_agent_step(
    status: str,
    *,
    task_result: str | None = None,
    error: str | None = None,
    fitness: float = 0.0,
) -> AgentObservation:
    """Coalgebraic unfold: current state → (observation, next_state).

    Agent lifecycle as an F-coalgebra where alpha: S -> F(S)
    decomposes agent state into observable components.
    """
    if error:
        return AgentObservation(
            output=f"error: {error}",
            next_status="idle" if status == "busy" else status,
            fitness=max(0.0, fitness - 0.1),
        )

    if status == "busy" and task_result:
        return AgentObservation(
            output=task_result,
            next_status="idle",
            fitness=fitness,
            tasks_completed=1,
        )

    if status == "stopping":
        return AgentObservation(
            output="shutting down",
            next_status="dead",
            fitness=fitness,
        )

    return AgentObservation(
        output="waiting",
        next_status=status,
        fitness=fitness,
    )


# ---------------------------------------------------------------------------
# Bridge 3: Sheaf Consistency Check
# Quick check: do overlapping agents agree on shared state?
# ---------------------------------------------------------------------------

def check_sheaf_consistency(
    agent_claims: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Check the sheaf condition on agent-published claims.

    Sheaf condition: for overlapping agents (sharing claim keys),
    their values must agree.  Disagreements are H^1 obstructions.

    Args:
        agent_claims: {agent_id: {claim_key: claim_value, ...}, ...}

    Returns:
        {"consistent": bool, "agreements": int, "obstructions": list}
    """
    # Build claim_key -> list of (agent_id, value)
    claim_index: dict[str, list[tuple[str, Any]]] = {}
    for agent_id, claims in agent_claims.items():
        for key, value in claims.items():
            claim_index.setdefault(key, []).append((agent_id, value))

    agreements = 0
    obstructions: list[dict[str, Any]] = []

    for claim_key, entries in claim_index.items():
        if len(entries) < 2:
            continue  # No overlap to check

        # Check if all values agree
        values = [v for _, v in entries]
        if all(v == values[0] for v in values[1:]):
            agreements += 1
        else:
            obstructions.append({
                "claim_key": claim_key,
                "agents": [a for a, _ in entries],
                "values": values,
            })

    return {
        "consistent": len(obstructions) == 0,
        "agreements": agreements,
        "obstructions": obstructions,
    }


# ---------------------------------------------------------------------------
# Bridge 4: Fisher Metric for Provider Routing
# Performance distribution → natural gradient → better routing decisions
# ---------------------------------------------------------------------------

@dataclass
class ProviderPerformance:
    """Summary statistics for a provider's recent performance.

    These form a point on the statistical manifold of provider behaviors.
    """

    provider_name: str
    mean_latency_ms: float = 0.0
    success_rate: float = 1.0
    mean_tokens_per_second: float = 0.0
    sample_count: int = 0

    @property
    def quality_score(self) -> float:
        """Scalar quality metric combining all dimensions.

        This is the inner product <theta, w> where w are importance weights.
        Higher is better.
        """
        if self.sample_count == 0:
            return 0.0
        # Weighted combination: success rate matters most, then throughput, then latency
        latency_score = max(0.0, 1.0 - self.mean_latency_ms / 10000.0)
        return (
            0.5 * self.success_rate
            + 0.3 * min(1.0, self.mean_tokens_per_second / 100.0)
            + 0.2 * latency_score
        )


def rank_providers_by_geometry(
    performances: list[ProviderPerformance],
) -> list[str]:
    """Rank providers using their quality scores on the statistical manifold.

    This is a simplified Fisher metric ranking — the full natural gradient
    is in info_geometry.py.  This bridge makes the ranking available to
    the routing layer without requiring numpy.
    """
    scored = sorted(performances, key=lambda p: p.quality_score, reverse=True)
    return [p.provider_name for p in scored]
