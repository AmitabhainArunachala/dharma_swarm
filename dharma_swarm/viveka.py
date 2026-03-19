"""Viveka Gate — discriminative wisdom for autonomous agents.

Sanskrit viveka: the capacity to distinguish the real from the unreal,
the essential from the inessential. Not a module — an emergent property
of four interacting mechanisms:

  1. Precision (dynamic, context-sensitive confidence)
  2. Expected Free Energy (risk + ambiguity - novelty)
  3. Telos Alignment (S5 identity check)
  4. Experience Base (outcome-validated patterns)

Together they answer: "Given what I perceive, what I know, who I am,
and what I've experienced — is this action worth taking RIGHT NOW?"

The decision is a NEGATIVE test: commit unless a disqualifying condition
is found. This is Klein's RPD, not classical optimization. Experts don't
search — they recognize, simulate, and commit unless a fatal flaw appears.

Grounded in: SYNTHESIS.md Part 4, Principles #1 #4 #11
Sources: Klein RPD (30 years), Friston active inference, Beer VSM S3-S4-S5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from dharma_swarm.complexity_router import ComplexityRoute, ComplexityRouter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class VivekaDecision(str, Enum):
    """What the viveka gate recommends."""
    COMMIT = "commit"       # All negative tests passed. Act now.
    WAIT = "wait"           # Acting is not clearly better than waiting.
    EXPLORE = "explore"     # Information gathering would be more valuable.
    ESCALATE = "escalate"   # Fatal flaw found — needs human judgment.


@dataclass
class VivekaResult:
    """Full result from a viveka evaluation."""
    decision: VivekaDecision
    action_id: str = ""
    precision: float = 0.5
    expected_free_energy: float = 0.0
    telos_aligned: bool = True
    experience_match_confidence: float = 0.0
    fatal_flaws: list[str] = field(default_factory=list)
    reason: str = ""
    evaluation_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def should_act(self) -> bool:
        return self.decision == VivekaDecision.COMMIT


# ---------------------------------------------------------------------------
# Experience base
# ---------------------------------------------------------------------------

@dataclass
class ExperienceRecord:
    """An outcome-validated situation-action pair.

    Populated from Darwin Engine fitness archive + stigmergy marks.
    NOT from the model's own predictions — from OBSERVED OUTCOMES.
    """
    situation_hash: str = ""  # Hash of the situation context
    action_type: str = ""
    target: str = ""
    outcome: str = ""  # "success", "failure", "partial"
    fitness_score: float = 0.0
    timestamp: str = ""
    observation: str = ""


class ExperienceBase:
    """Outcome-validated situation-action patterns.

    The experience base earns trust the same way agents earn autonomy —
    through demonstrated accuracy over time. NOT from the model's own
    predictions, but from observed outcomes.
    """

    def __init__(self) -> None:
        self._records: list[ExperienceRecord] = []
        self._system_avg_fitness: float = 0.5

    def add(self, record: ExperienceRecord) -> None:
        """Add an outcome-validated record."""
        self._records.append(record)
        self._update_system_average()

    def best_match(self, situation_hash: str) -> ExperienceRecord | None:
        """Find the best matching experience for a situation."""
        matches = [r for r in self._records if r.situation_hash == situation_hash]
        if not matches:
            return None
        return max(matches, key=lambda r: r.fitness_score)

    def confidence_for(self, action_type: str) -> float:
        """Confidence level for a given action type, based on past outcomes."""
        relevant = [r for r in self._records if r.action_type == action_type]
        if not relevant:
            return 0.0

        successes = sum(1 for r in relevant if r.outcome == "success")
        return successes / len(relevant)

    def marginal_value(self, action_type: str) -> float:
        """Marginal value of taking this action vs system average.

        From Charnov's Marginal Value Theorem: switch patches when
        marginal return drops below system average.
        """
        confidence = self.confidence_for(action_type)
        return confidence - self._system_avg_fitness

    def system_average(self) -> float:
        """System-wide average fitness score."""
        return self._system_avg_fitness

    def _update_system_average(self) -> None:
        if self._records:
            self._system_avg_fitness = sum(
                r.fitness_score for r in self._records
            ) / len(self._records)


# ---------------------------------------------------------------------------
# The Gate
# ---------------------------------------------------------------------------

class VivekaGate:
    """The discernment function.

    Not a monolithic decision maker — an integration point where
    four independent mechanisms vote on whether to act:

    1. Complexity Router: is this routine or novel?
    2. Expected Free Energy: is acting better than waiting?
    3. Telos Check: does this serve who we are?
    4. Experience Base: have we succeeded at this before?

    The gate uses Klein's RPD: generate one candidate, check for
    fatal flaws. If none, commit. No optimization, no search.
    """

    def __init__(
        self,
        complexity_router: ComplexityRouter | None = None,
        experience_base: ExperienceBase | None = None,
        precision: float = 0.5,
        base_threshold: float = 0.3,
    ) -> None:
        self.router = complexity_router or ComplexityRouter()
        self.experience = experience_base or ExperienceBase()
        self.precision = precision
        self.base_threshold = base_threshold

    @property
    def precision_threshold(self) -> float:
        """Dynamic threshold.

        High precision (good predictions) → low threshold → act faster.
        Low precision (surprised often) → high threshold → deliberate more.
        """
        return self.base_threshold / max(self.precision, 0.05)

    def evaluate(
        self,
        action_type: str,
        target: str = "",
        situation_hash: str = "",
        domains: list[str] | None = None,
        affected_agents: list[str] | None = None,
        telos_aligned: bool = True,
        fatal_flaws: list[str] | None = None,
    ) -> VivekaResult:
        """Evaluate whether to act.

        The evaluation is a NEGATIVE test:
        1. If complexity is LOW and experience is GOOD → FAST COMMIT
        2. If expected free energy of action >= inaction → WAIT or EXPLORE
        3. If fatal flaw found → ESCALATE
        4. If telos misaligned → WAIT
        5. If marginal value below average → WAIT
        6. All tests passed → COMMIT

        This is NOT optimization. It's satisficing with fatal-flaw checking.
        """
        import time
        start = time.monotonic()

        fatal_flaws = fatal_flaws or []

        # Step 0: COMPLEXITY ROUTE — is this routine?
        classification = self.router.classify(
            action_type=action_type,
            target=target,
            domains=domains,
            affected_agents=affected_agents,
        )

        if classification.route == ComplexityRoute.FAST:
            # FAST PATH: check experience, then commit
            match = self.experience.best_match(situation_hash)
            if match and match.fitness_score > 0.7:
                # Known situation, good outcomes → commit immediately
                elapsed = (time.monotonic() - start) * 1000
                return VivekaResult(
                    decision=VivekaDecision.COMMIT,
                    action_id=f"viveka_{action_type}",
                    precision=self.precision,
                    experience_match_confidence=match.fitness_score,
                    reason=f"Fast path: known pattern, confidence {match.fitness_score:.2f}",
                    evaluation_ms=elapsed,
                )

        # Step 1: HARD VETOES — checked before any soft scoring
        # Fatal flaws and telos misalignment are absolute. No EFE
        # calculation overrides "this will destroy data" or "this
        # violates who we are."

        # 1a: FATAL FLAW CHECK — mental simulation (RPD Level 3)
        if fatal_flaws:
            elapsed = (time.monotonic() - start) * 1000
            return VivekaResult(
                decision=VivekaDecision.ESCALATE,
                action_id=f"viveka_{action_type}",
                precision=self.precision,
                fatal_flaws=fatal_flaws,
                reason=f"Fatal flaws found: {', '.join(fatal_flaws[:3])}",
                evaluation_ms=elapsed,
            )

        # 1b: TELOS ALIGNMENT — S5 identity check
        if not telos_aligned:
            elapsed = (time.monotonic() - start) * 1000
            return VivekaResult(
                decision=VivekaDecision.WAIT,
                action_id=f"viveka_{action_type}",
                precision=self.precision,
                telos_aligned=False,
                reason="Action is not telos-aligned (S5 identity check failed)",
                evaluation_ms=elapsed,
            )

        # Step 2: EXPECTED FREE ENERGY — is acting better than waiting?
        # Simplified: risk = 1 - experience confidence, ambiguity = 1 - precision
        exp_confidence = self.experience.confidence_for(action_type)
        risk = 1.0 - exp_confidence
        ambiguity = 1.0 - self.precision
        novelty = 0.3 if classification.route == ComplexityRoute.SLOW else 0.1
        efe_action = risk + ambiguity - novelty
        efe_wait = 0.5  # Base cost of inaction

        if efe_action >= efe_wait + self.precision_threshold:
            # Acting is not clearly better
            elapsed = (time.monotonic() - start) * 1000
            # Would exploration help?
            efe_explore = efe_action * 0.7  # Exploration typically reduces uncertainty
            if efe_explore < efe_action:
                return VivekaResult(
                    decision=VivekaDecision.EXPLORE,
                    action_id=f"viveka_{action_type}",
                    precision=self.precision,
                    expected_free_energy=efe_action,
                    reason=f"EFE action ({efe_action:.2f}) >= wait ({efe_wait:.2f}) + threshold ({self.precision_threshold:.2f}). Explore first.",
                    evaluation_ms=elapsed,
                )
            return VivekaResult(
                decision=VivekaDecision.WAIT,
                action_id=f"viveka_{action_type}",
                precision=self.precision,
                expected_free_energy=efe_action,
                reason=f"EFE action ({efe_action:.2f}) >= wait ({efe_wait:.2f}) + threshold ({self.precision_threshold:.2f})",
                evaluation_ms=elapsed,
            )

        # Step 4: MARGINAL VALUE — worth doing vs alternatives?
        marginal = self.experience.marginal_value(action_type)
        if marginal < -0.2:  # Significantly below average
            elapsed = (time.monotonic() - start) * 1000
            return VivekaResult(
                decision=VivekaDecision.WAIT,
                action_id=f"viveka_{action_type}",
                precision=self.precision,
                reason=f"Marginal value ({marginal:.2f}) below system average. Switch patches.",
                evaluation_ms=elapsed,
            )

        # Step 5: ALL NEGATIVE TESTS PASSED → COMMIT
        elapsed = (time.monotonic() - start) * 1000
        return VivekaResult(
            decision=VivekaDecision.COMMIT,
            action_id=f"viveka_{action_type}",
            precision=self.precision,
            expected_free_energy=efe_action,
            telos_aligned=True,
            experience_match_confidence=exp_confidence,
            reason="All negative tests passed. No disqualifying conditions found.",
            evaluation_ms=elapsed,
        )

    def update_precision(self, prediction_error: float) -> None:
        """Update precision based on prediction error.

        Called after VERIFY phase. Small errors → higher precision.
        Asymmetric alpha: fast reaction to surprise (0.3), slow calm-down (0.05).
        Linear target: error=0.9 → target=0.1 (hard drop on surprise).
        """
        alpha = 0.3 if prediction_error > 0.3 else 0.05
        target = max(0.05, 1.0 - prediction_error)
        self.precision = (1 - alpha) * self.precision + alpha * target
        self.precision = max(0.05, min(0.95, self.precision))
