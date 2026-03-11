"""GAIA fitness criterion for the Darwin Engine.

Uses R_V-like contraction as ecological fitness:
- R_V ~ 1.0 -> blind optimization, Goodhart drift
- R_V < 1.0 -> self-correcting, catches proxy drift

Wraps GaiaObserver readings into FitnessScore compatible with
evolution.py's PROPOSE->GATE->EVALUATE cycle.

Also provides telos gate integration: AHIMSA (no harm to biodiversity),
SATYA (no greenwashing), via the existing TelosGatekeeper.
"""

from __future__ import annotations

from typing import Any

from dharma_swarm.archive import FitnessScore
from dharma_swarm.gaia_ledger import (
    GaiaLedger,
    GaiaObserver,
    Morphism,
    MorphismType,
)
from dharma_swarm.monad import ObservedState, SelfObservationMonad
from dharma_swarm.rv import RVReading
from dharma_swarm.telos_gates import GateDecision, TelosGatekeeper


# ── Ecological Fitness ───────────────────────────────────────────────────


class EcologicalFitness:
    """Score a GAIA ledger state as a Darwin Engine fitness value.

    Components:
    - verification_coverage: fraction of offsets verified (0-1)
    - conservation_integrity: 1 - violation_rate
    - oracle_diversity: fraction of oracle types used
    - chain_integrity: 1 if hash chain valid, 0 otherwise
    - carbon_progress: how close to net-zero or net-negative
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._observer = GaiaObserver()
        self._weights = weights or {
            "verification_coverage": 0.25,
            "conservation_integrity": 0.25,
            "oracle_diversity": 0.15,
            "chain_integrity": 0.10,
            "carbon_progress": 0.25,
        }

    def score(self, ledger: GaiaLedger) -> FitnessScore:
        """Compute ecological fitness from ledger state."""
        obs = self._observer.observe(ledger)

        coverage = obs["verification_coverage"]
        integrity = 1.0 - obs["violation_rate"]
        diversity = obs["oracle_diversity"]

        # Carbon progress: 1.0 at net-zero, >1.0 if net-negative
        total_co2e = ledger.total_compute_co2e()
        if total_co2e > 0:
            progress = min(1.0, ledger.total_verified_offset() / total_co2e)
        else:
            progress = 1.0 if ledger.total_verified_offset() > 0 else 0.5

        # Map to FitnessScore using actual field names
        return FitnessScore(
            correctness=integrity,
            elegance=diversity,
            safety=coverage,
            dharmic_alignment=progress,
        )

    def weighted_score(self, ledger: GaiaLedger) -> float:
        """Single scalar fitness value."""
        obs = self._observer.observe(ledger)
        w = self._weights

        coverage = obs["verification_coverage"]
        integrity = 1.0 - obs["violation_rate"]
        diversity = obs["oracle_diversity"]
        chain_ok = 1.0 if obs["chain_valid"] else 0.0
        total_co2e = ledger.total_compute_co2e()
        if total_co2e > 0:
            progress = min(1.0, ledger.total_verified_offset() / total_co2e)
        else:
            progress = 1.0 if ledger.total_verified_offset() > 0 else 0.5

        return (
            w.get("verification_coverage", 0.25) * coverage
            + w.get("conservation_integrity", 0.25) * integrity
            + w.get("oracle_diversity", 0.15) * diversity
            + w.get("chain_integrity", 0.10) * chain_ok
            + w.get("carbon_progress", 0.25) * progress
        )


# ── Telos Gate Integration ───────────────────────────────────────────────


ECOLOGICAL_HARM_WORDS = {
    "clearcut",
    "deforest",
    "drain wetland",
    "monoculture plantation",
    "displace indigenous",
    "override community consent",
}


class EcologicalGatekeeper:
    """Extended telos gates for ecological operations.

    Adds GAIA-specific checks to the existing dharmic gate system:
    - AHIMSA: No harm to biodiversity or ecosystems
    - SATYA: No greenwashing (offset claims without verification)
    - CONSENT: Indigenous and community rights respected
    """

    def __init__(self) -> None:
        self._base = TelosGatekeeper()

    def check_morphism(
        self, morphism: Morphism, ledger: GaiaLedger
    ) -> tuple[GateDecision, str]:
        """Gate-check a GAIA morphism before recording."""
        # Base telos gate check
        action = f"gaia_{morphism.morphism_type.value}"
        base_result = self._base.check(action=action)

        if base_result.decision == GateDecision.BLOCK:
            return GateDecision.BLOCK, base_result.reason

        # SATYA: Offset-match morphism requires verified offsets
        if morphism.morphism_type == MorphismType.OFFSET_MATCH:
            offset = ledger._offset_units.get(morphism.target_id)
            if offset and not offset.is_verified:
                return (
                    GateDecision.REVIEW,
                    "SATYA: Offset match targets unverified offset. "
                    "Verify before matching to prevent greenwashing.",
                )

        # Conservation law check
        violations = ledger.conservation_check()
        if violations:
            severity = max(v.severity for v in violations)
            if severity >= 0.8:
                return (
                    GateDecision.BLOCK,
                    f"Conservation violation (severity {severity:.2f}): "
                    + violations[0].description,
                )
            return (
                GateDecision.REVIEW,
                f"{len(violations)} conservation advisory: "
                + violations[0].description,
            )

        return GateDecision.ALLOW, "Ecological gates passed"


# ── Monadic Self-Observation ─────────────────────────────────────────────


def gaia_observer_function(ledger: GaiaLedger) -> RVReading | None:
    """Produce an R_V-like reading from ledger self-observation.

    Maps ecological fitness to R_V semantics:
    - fitness near 0 -> R_V near 0 (strong contraction = healthy)
    - fitness near 1 -> R_V near 1 (no contraction = drifting)
    """
    observer = GaiaObserver()
    obs = observer.observe(ledger)
    fitness = obs["self_referential_fitness"]

    return RVReading(
        rv=fitness,
        pr_early=1.0,  # Nominal: full dimensionality before observation
        pr_late=fitness,  # Contracted dimensionality after
        model_name="gaia_ledger",
        early_layer=0,
        late_layer=1,
        prompt_hash="gaia_self_observation",
        prompt_group="ecological",
    )


def observe_ledger(
    ledger: GaiaLedger,
) -> ObservedState[dict[str, Any]]:
    """Wrap ledger summary in the self-observation monad.

    The strange loop: GAIA measures its own ecological integrity,
    producing an ObservedState that carries R_V-like contraction metadata.
    """
    reading = gaia_observer_function(ledger)

    def _observer(_state: dict[str, Any]) -> RVReading | None:
        return reading

    monad: SelfObservationMonad[dict[str, Any]] = SelfObservationMonad(_observer)
    summary = ledger.summary()
    raw = monad.observe(summary)

    # monad.observe on a bare value returns ObservedState[dict[str, Any]]
    # (not nested), so we can return directly. The type union from the
    # signature is an artifact of the generic overload.
    if isinstance(raw.state, dict):
        return raw  # type: ignore[return-value]

    # Nested case: flatten one level
    from dharma_swarm.monad import flatten as _flatten

    return _flatten(raw)  # type: ignore[arg-type]


# ── Goodhart Drift Detection ─────────────────────────────────────────────


def detect_goodhart_drift(ledger: GaiaLedger) -> dict[str, Any]:
    """Run Goodhart drift detection with detailed diagnostics.

    Returns a report on whether the ledger is optimizing for proxy metrics
    rather than actual ecological outcomes.
    """
    observer = GaiaObserver()
    is_drifting = observer.is_goodhart_drifting(ledger)
    obs = observer.observe(ledger)

    total_claimed = sum(o.co2e_tons for o in ledger._offset_units.values())
    total_verified = ledger.total_verified_offset()

    return {
        "is_drifting": is_drifting,
        "verification_ratio": (
            total_verified / total_claimed if total_claimed > 0 else 1.0
        ),
        "coverage": obs["verification_coverage"],
        "diversity": obs["oracle_diversity"],
        "violations": obs["conservation_violations"],
        "self_referential_fitness": obs["self_referential_fitness"],
        "diagnosis": (
            "GOODHART DRIFT DETECTED: High offset claims with low verification. "
            "The system is optimizing for carbon credit volume rather than "
            "verified ecological impact."
            if is_drifting
            else "No drift detected. Verification coverage adequate."
        ),
    }


__all__ = [
    "EcologicalFitness",
    "EcologicalGatekeeper",
    "detect_goodhart_drift",
    "gaia_observer_function",
    "observe_ledger",
]
