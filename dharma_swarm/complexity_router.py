"""Complexity router — fast path for the 80%, slow path for the 20%.

Not every decision needs full S3-S4-S5 deliberation. Klein's RPD research
shows 80% of expert decisions use the first viable option. The complexity
router classifies actions BEFORE any expensive processing:

  - FAST: routine, single-domain, reversible → 2-3 gates, pattern match, commit
  - SLOW: novel, cross-domain, irreversible → full deliberation with S3-S4-S5

Four orthogonal dimensions:
  1. Correlation strength — how many systems does this touch?
  2. Domain crossings — how many domains (code, skill, product, research, meta)?
  3. Stakeholder multiplicity — how many agents/humans affected?
  4. Uncertainty level — how novel is this action?

Grounded in: SYNTHESIS.md P0 #2, Principle #1 (simplicity beats sophistication)
Sources: CDR paper (34% token reduction, 2.5% accuracy gain), Klein RPD
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any  # noqa: F401 — used in type hints below

logger = logging.getLogger(__name__)


class ComplexityRoute(str, Enum):
    """Where to route based on complexity classification."""
    FAST = "fast"  # 2-3 gates, pattern match, immediate commit
    SLOW = "slow"  # Full S3-S4-S5 deliberation


class Domain(str, Enum):
    """The 5 cascade domains (from cascade.py)."""
    CODE = "code"
    SKILL = "skill"
    PRODUCT = "product"
    RESEARCH = "research"
    META = "meta"


@dataclass
class ComplexityScore:
    """Scored complexity across 4 dimensions."""
    correlation: float = 0.0    # [0,1] — how many systems touched
    domain_crossings: float = 0.0  # [0,1] — how many domains
    stakeholders: float = 0.0   # [0,1] — how many affected parties
    uncertainty: float = 0.0    # [0,1] — how novel

    @property
    def weighted_total(self) -> float:
        """Weighted sum. Uncertainty weighs most — novel actions need more thought."""
        return (
            0.2 * self.correlation
            + 0.2 * self.domain_crossings
            + 0.2 * self.stakeholders
            + 0.4 * self.uncertainty
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "correlation": round(self.correlation, 3),
            "domain_crossings": round(self.domain_crossings, 3),
            "stakeholders": round(self.stakeholders, 3),
            "uncertainty": round(self.uncertainty, 3),
            "weighted_total": round(self.weighted_total, 3),
        }


@dataclass
class ComplexityClassification:
    """Result of complexity classification."""
    route: ComplexityRoute
    score: ComplexityScore
    threshold: float
    reason: str = ""
    fast_gates: list[str] = field(default_factory=list)  # Which gates to run if FAST

    @property
    def is_fast(self) -> bool:
        return self.route == ComplexityRoute.FAST


# Known system touchpoints for correlation scoring
SYSTEM_TOUCHPOINTS: dict[str, list[str]] = {
    "dharma_swarm": ["daemon", "agents", "stigmergy", "evolution", "gates"],
    "agni": ["vps", "openclaw", "skills", "crons"],
    "mech_interp": ["paper", "scripts", "geometric_lens", "prompts"],
    "jagat_kalyan": ["matching", "grants", "carbon"],
    "infrastructure": ["ssh", "rsync", "cron", "launchd"],
    "claude_code": ["hooks", "settings", "skills", "memory"],
}

# Known action patterns for uncertainty scoring
KNOWN_PATTERNS: set[str] = {
    "write_file", "edit_file", "run_tests", "git_commit",
    "read_file", "search_code", "restart_daemon", "check_health",
    "leave_mark", "decay_marks", "run_evolution", "dispatch_task",
    "gate_check", "send_signal", "update_config",
}


class ComplexityRouter:
    """Classify action complexity and route to fast or slow path.

    The router is intentionally cheap — no LLM calls, no file I/O.
    Pure in-memory classification based on action metadata.

    Usage::

        router = ComplexityRouter()
        classification = router.classify(
            action_type="write_file",
            target="/Users/dhyana/dharma_swarm/dharma_swarm/foo.py",
            domains=["code"],
            affected_agents=["agent_1"],
        )

        if classification.is_fast:
            # Run only fast_gates, then commit
            for gate in classification.fast_gates:
                ...
        else:
            # Full S3-S4-S5 deliberation
            ...
    """

    def __init__(
        self,
        threshold: float = 0.45,
        fast_gates: list[str] | None = None,
    ) -> None:
        """
        Args:
            threshold: Weighted complexity below this → FAST path.
                       Default 0.45 routes ~80% to fast path (based on
                       typical dharma_swarm action distribution).
            fast_gates: Which gates to run on the fast path.
                        Default: ahimsa (non-harm), kernel_integrity, reversibility.
        """
        self.threshold = threshold
        self.fast_gates = fast_gates or ["ahimsa", "kernel_integrity", "reversibility"]

    def classify(
        self,
        action_type: str,
        target: str = "",
        domains: list[str] | None = None,
        affected_agents: list[str] | None = None,
        affected_systems: list[str] | None = None,
        is_novel: bool | None = None,
    ) -> ComplexityClassification:
        """Classify an action's complexity.

        All parameters except action_type are optional — the router
        infers what it can from the action type and target.
        """
        domains = domains or []
        affected_agents = affected_agents or []
        affected_systems = affected_systems or []

        # Dimension 1: Correlation — how many systems does this touch?
        correlation = self._score_correlation(target, affected_systems)

        # Dimension 2: Domain crossings
        domain_crossings = self._score_domain_crossings(domains)

        # Dimension 3: Stakeholder multiplicity
        stakeholders = self._score_stakeholders(affected_agents)

        # Dimension 4: Uncertainty
        uncertainty = self._score_uncertainty(action_type, is_novel)

        score = ComplexityScore(
            correlation=correlation,
            domain_crossings=domain_crossings,
            stakeholders=stakeholders,
            uncertainty=uncertainty,
        )

        total = score.weighted_total
        route = ComplexityRoute.FAST if total < self.threshold else ComplexityRoute.SLOW

        reason = ""
        if route == ComplexityRoute.FAST:
            reason = f"Routine action (score {total:.3f} < threshold {self.threshold})"
        else:
            # Explain what pushed it to slow path
            high_dims = []
            if correlation > 0.5:
                high_dims.append(f"correlation={correlation:.2f}")
            if domain_crossings > 0.5:
                high_dims.append(f"domains={domain_crossings:.2f}")
            if stakeholders > 0.5:
                high_dims.append(f"stakeholders={stakeholders:.2f}")
            if uncertainty > 0.5:
                high_dims.append(f"uncertainty={uncertainty:.2f}")
            reason = f"Complex action (score {total:.3f}): {', '.join(high_dims)}"

        logger.debug(
            "Complexity: %s → %s (%.3f) %s",
            action_type, route.value, total, score.to_dict(),
        )

        return ComplexityClassification(
            route=route,
            score=score,
            threshold=self.threshold,
            reason=reason,
            fast_gates=self.fast_gates if route == ComplexityRoute.FAST else [],
        )

    # ---- Dimension scorers ----

    def _score_correlation(self, target: str, affected_systems: list[str]) -> float:
        """How many systems does this action touch?"""
        touched = set(affected_systems)

        # Infer from target path
        if target:
            target_lower = target.lower()
            for system, keywords in SYSTEM_TOUCHPOINTS.items():
                if any(kw in target_lower for kw in keywords):
                    touched.add(system)

        n = len(touched)
        if n <= 1:
            return 0.0
        elif n == 2:
            return 0.3
        elif n == 3:
            return 0.6
        else:
            return min(1.0, 0.2 * n)

    def _score_domain_crossings(self, domains: list[str]) -> float:
        """How many domains does this cross?"""
        n = len(set(domains))
        if n <= 1:
            return 0.0
        elif n == 2:
            return 0.4
        elif n == 3:
            return 0.7
        else:
            return 1.0

    def _score_stakeholders(self, affected_agents: list[str]) -> float:
        """How many agents/humans are affected?"""
        n = len(set(affected_agents))
        if n <= 1:
            return 0.0
        elif n <= 3:
            return 0.3
        elif n <= 5:
            return 0.6
        else:
            return min(1.0, 0.1 * n)

    def _score_uncertainty(self, action_type: str, is_novel: bool | None) -> float:
        """How novel is this action?"""
        if is_novel is not None:
            return 1.0 if is_novel else 0.1

        # Check if action type is in known patterns
        action_lower = action_type.lower().replace(" ", "_").replace("-", "_")
        if action_lower in KNOWN_PATTERNS:
            return 0.1  # Known pattern → low uncertainty
        elif any(p in action_lower for p in KNOWN_PATTERNS):
            return 0.3  # Partial match → moderate uncertainty

        return 0.7  # Unknown pattern → high uncertainty
