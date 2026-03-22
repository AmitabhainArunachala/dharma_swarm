"""Tests for gaia_fitness.py — GAIA ecological fitness criterion."""

from __future__ import annotations

import pytest

from dharma_swarm.gaia_ledger import (
    ComputeUnit,
    GaiaLedger,
    Morphism,
    MorphismType,
    OffsetUnit,
    UnitType,
    VerificationUnit,
)
from dharma_swarm.gaia_fitness import (
    ECOLOGICAL_HARM_WORDS,
    EcologicalFitness,
    EcologicalGatekeeper,
    detect_goodhart_drift,
    gaia_observer_function,
    observe_ledger,
)
from dharma_swarm.telos_gates import GateDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ledger_with_verified_offset():
    """Create a ledger with verified offset for reuse."""
    ledger = GaiaLedger()
    ledger.record_compute(ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5))
    offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=1.0)
    ledger.record_offset(offset)
    for oracle in ["satellite", "iot_sensor", "human_auditor"]:
        ledger.record_verification(
            VerificationUnit(
                oracle_type=oracle,
                target_id="off1",
                target_type=UnitType.OFFSET,
                confidence=0.8,
            )
        )
    return ledger


# ---------------------------------------------------------------------------
# EcologicalFitness
# ---------------------------------------------------------------------------


class TestEcologicalFitness:
    def test_score_empty_ledger(self):
        ef = EcologicalFitness()
        ledger = GaiaLedger()
        score = ef.score(ledger)
        assert score.correctness >= 0
        assert score.safety >= 0

    def test_score_with_data(self):
        ef = EcologicalFitness()
        ledger = _make_ledger_with_verified_offset()
        score = ef.score(ledger)
        # With verified offsets, coverage should be > 0
        assert score.safety > 0  # safety = verification coverage

    def test_weighted_score_empty(self):
        ef = EcologicalFitness()
        ledger = GaiaLedger()
        ws = ef.weighted_score(ledger)
        assert 0.0 <= ws <= 1.0

    def test_weighted_score_healthy_ledger(self):
        ef = EcologicalFitness()
        ledger = _make_ledger_with_verified_offset()
        ws = ef.weighted_score(ledger)
        # Should be higher than empty ledger
        ws_empty = ef.weighted_score(GaiaLedger())
        assert ws >= ws_empty

    def test_custom_weights(self):
        ef = EcologicalFitness(weights={
            "verification_coverage": 1.0,
            "conservation_integrity": 0.0,
            "oracle_diversity": 0.0,
            "chain_integrity": 0.0,
            "carbon_progress": 0.0,
        })
        ledger = _make_ledger_with_verified_offset()
        ws = ef.weighted_score(ledger)
        # Dominated by verification_coverage = 1.0 (all offsets verified)
        assert ws > 0.5

    def test_weighted_score_bounded(self):
        ef = EcologicalFitness()
        ledger = _make_ledger_with_verified_offset()
        ws = ef.weighted_score(ledger)
        assert 0.0 <= ws <= 1.0

    def test_carbon_progress_no_compute(self):
        ef = EcologicalFitness()
        ledger = GaiaLedger()
        # No compute → carbon_progress should be 0.5 (neutral)
        ws = ef.weighted_score(ledger)
        assert ws > 0


# ---------------------------------------------------------------------------
# EcologicalGatekeeper
# ---------------------------------------------------------------------------


class TestEcologicalGatekeeper:
    def test_valid_morphism_passes(self):
        gk = EcologicalGatekeeper()
        ledger = _make_ledger_with_verified_offset()
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="c1",
            target_id="off1",
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        decision, reason = gk.check_morphism(m, ledger)
        # Should pass or allow (not block)
        assert decision in (GateDecision.ALLOW, GateDecision.REVIEW)

    def test_unverified_offset_gets_review(self):
        gk = EcologicalGatekeeper()
        ledger = GaiaLedger()
        offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=10.0)
        ledger.record_offset(offset)
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="c1",
            target_id="off1",
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        decision, reason = gk.check_morphism(m, ledger)
        assert decision == GateDecision.REVIEW
        assert "SATYA" in reason


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_harm_words(self):
        assert len(ECOLOGICAL_HARM_WORDS) >= 5
        assert "clearcut" in ECOLOGICAL_HARM_WORDS
        assert "deforest" in ECOLOGICAL_HARM_WORDS


# ---------------------------------------------------------------------------
# Observer function
# ---------------------------------------------------------------------------


class TestGaiaObserverFunction:
    def test_returns_rv_reading(self):
        ledger = GaiaLedger()
        reading = gaia_observer_function(ledger)
        assert reading is not None
        assert reading.model_name == "gaia_ledger"
        assert 0.0 <= reading.rv <= 1.0

    def test_with_data(self):
        ledger = _make_ledger_with_verified_offset()
        reading = gaia_observer_function(ledger)
        assert reading is not None


# ---------------------------------------------------------------------------
# observe_ledger (monadic)
# ---------------------------------------------------------------------------


class TestObserveLedger:
    def test_returns_observed_state(self):
        ledger = GaiaLedger()
        obs = observe_ledger(ledger)
        assert obs is not None
        # ObservedState has .state
        assert hasattr(obs, "state")
        assert isinstance(obs.state, dict)

    def test_with_data(self):
        ledger = _make_ledger_with_verified_offset()
        obs = observe_ledger(ledger)
        assert obs.state["entries"] > 0


# ---------------------------------------------------------------------------
# detect_goodhart_drift
# ---------------------------------------------------------------------------


class TestDetectGoodhartDrift:
    def test_no_drift_empty(self):
        ledger = GaiaLedger()
        report = detect_goodhart_drift(ledger)
        assert report["is_drifting"] is False
        assert "No drift" in report["diagnosis"]

    def test_drift_detected(self):
        ledger = GaiaLedger()
        # Large claimed offset, no verification
        for i in range(5):
            ledger.record_offset(OffsetUnit(project_id=f"p{i}", co2e_tons=100.0))
        report = detect_goodhart_drift(ledger)
        assert report["is_drifting"] is True
        assert "GOODHART DRIFT" in report["diagnosis"]
        assert report["verification_ratio"] < 0.5

    def test_no_drift_with_verification(self):
        ledger = _make_ledger_with_verified_offset()
        report = detect_goodhart_drift(ledger)
        assert report["is_drifting"] is False

    def test_report_fields(self):
        ledger = GaiaLedger()
        report = detect_goodhart_drift(ledger)
        assert "coverage" in report
        assert "diversity" in report
        assert "violations" in report
        assert "self_referential_fitness" in report
