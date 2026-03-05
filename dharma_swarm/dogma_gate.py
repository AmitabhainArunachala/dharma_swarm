"""Dogma Drift gate — Axiom 2: Epistemic Humility.

Detects when confidence increases without corresponding evidence increase.
If you're getting more certain but not learning anything new, that's dogma.
"""

from __future__ import annotations

from pydantic import BaseModel

from dharma_swarm.models import GateResult


class DogmaDriftCheck(BaseModel):
    """Input for a dogma drift evaluation."""

    confidence_before: float
    confidence_after: float
    evidence_count_before: int
    evidence_count_after: int
    hard_coded_rules: int = 0
    total_rules: int = 0


class DogmaDriftResult(BaseModel):
    """Output of a dogma drift evaluation."""

    gate_result: GateResult
    confidence_delta: float
    evidence_delta: int
    dogma_ratio: float
    reason: str


def check_dogma_drift(check: DogmaDriftCheck) -> DogmaDriftResult:
    """Evaluate whether confidence is drifting without evidentiary support.

    Decision logic:
        - confidence_delta > 0.1  and evidence_delta <= 0 -> FAIL
        - confidence_delta > 0.05 and evidence_delta <= 0 -> WARN
        - dogma_ratio > 0.30 -> append WARN about hard-coded rule ratio
        - otherwise -> PASS
    """
    confidence_delta = check.confidence_after - check.confidence_before
    evidence_delta = check.evidence_count_after - check.evidence_count_before
    dogma_ratio = (
        check.hard_coded_rules / check.total_rules
        if check.total_rules > 0
        else 0.0
    )

    # --- primary confidence/evidence check ---
    if confidence_delta > 0.1 and evidence_delta <= 0:
        gate_result = GateResult.FAIL
        reason = (
            f"Confidence increased by {confidence_delta:.2f} "
            "without new evidence"
        )
    elif confidence_delta > 0.05 and evidence_delta <= 0:
        gate_result = GateResult.WARN
        reason = "Confidence drifting upward without evidence support"
    else:
        gate_result = GateResult.PASS
        reason = "No dogma drift detected"

    # --- secondary dogma-ratio check (can escalate PASS to WARN) ---
    if dogma_ratio > 0.30:
        if gate_result == GateResult.PASS:
            gate_result = GateResult.WARN
        reason += f"; dogma ratio {dogma_ratio:.0%} exceeds 30% threshold"

    return DogmaDriftResult(
        gate_result=gate_result,
        confidence_delta=confidence_delta,
        evidence_delta=evidence_delta,
        dogma_ratio=dogma_ratio,
        reason=reason,
    )
