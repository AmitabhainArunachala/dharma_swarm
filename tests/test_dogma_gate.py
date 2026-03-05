"""Tests for the Dogma Drift gate (Axiom 2: Epistemic Humility)."""

from dharma_swarm.dogma_gate import (
    DogmaDriftCheck,
    DogmaDriftResult,
    check_dogma_drift,
)
from dharma_swarm.models import GateResult


def test_no_change_passes() -> None:
    """Same confidence, same evidence -> PASS."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.5,
        evidence_count_before=3, evidence_count_after=3,
    ))
    assert result.gate_result == GateResult.PASS


def test_confidence_up_with_evidence_passes() -> None:
    """Both confidence and evidence increase -> PASS."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.8,
        evidence_count_before=3, evidence_count_after=10,
    ))
    assert result.gate_result == GateResult.PASS


def test_confidence_up_no_evidence_fail() -> None:
    """Confidence delta > 0.1 with no new evidence -> FAIL."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.7,
        evidence_count_before=3, evidence_count_after=3,
    ))
    assert result.gate_result == GateResult.FAIL
    assert "without new evidence" in result.reason


def test_confidence_up_small_no_evidence_warn() -> None:
    """0.05 < confidence delta <= 0.1 with no new evidence -> WARN."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.57,
        evidence_count_before=5, evidence_count_after=5,
    ))
    assert result.gate_result == GateResult.WARN
    assert "drifting upward" in result.reason


def test_confidence_down_passes() -> None:
    """Confidence decreased -> PASS (humility is fine)."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.8, confidence_after=0.4,
        evidence_count_before=5, evidence_count_after=5,
    ))
    assert result.gate_result == GateResult.PASS


def test_dogma_ratio_high_warns() -> None:
    """hard_coded_rules > 30% of total_rules -> WARN."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.5,
        evidence_count_before=3, evidence_count_after=3,
        hard_coded_rules=4, total_rules=10,
    ))
    assert result.gate_result == GateResult.WARN
    assert "dogma ratio" in result.reason
    assert "30%" in result.reason


def test_dogma_ratio_low_passes() -> None:
    """hard_coded_rules < 30% of total -> no warning from ratio."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.5,
        evidence_count_before=3, evidence_count_after=3,
        hard_coded_rules=2, total_rules=10,
    ))
    assert result.gate_result == GateResult.PASS
    assert "dogma ratio" not in result.reason


def test_combined_confidence_and_dogma() -> None:
    """Both confidence drift FAIL and high dogma ratio trigger."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.3, confidence_after=0.5,
        evidence_count_before=2, evidence_count_after=2,
        hard_coded_rules=5, total_rules=10,
    ))
    assert result.gate_result == GateResult.FAIL
    assert "without new evidence" in result.reason
    assert "dogma ratio" in result.reason


def test_zero_total_rules() -> None:
    """total_rules=0 -> dogma_ratio=0.0, no crash."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.5, confidence_after=0.5,
        evidence_count_before=1, evidence_count_after=1,
        hard_coded_rules=3, total_rules=0,
    ))
    assert result.dogma_ratio == 0.0
    assert result.gate_result == GateResult.PASS


def test_result_values_correct() -> None:
    """Verify computed delta values in the result object."""
    result = check_dogma_drift(DogmaDriftCheck(
        confidence_before=0.2, confidence_after=0.9,
        evidence_count_before=1, evidence_count_after=4,
        hard_coded_rules=1, total_rules=5,
    ))
    assert abs(result.confidence_delta - 0.7) < 1e-9
    assert result.evidence_delta == 3
    assert abs(result.dogma_ratio - 0.2) < 1e-9
    assert result.gate_result == GateResult.PASS
