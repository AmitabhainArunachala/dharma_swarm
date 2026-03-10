"""Comprehensive tests for GAIA modules: ledger, verification, fitness.

Covers:
- gaia_ledger.py: units, hash chain, conservation laws, morphisms, queries
- gaia_verification.py: sessions, 3-of-5 threshold, sheaf integration
- gaia_fitness.py: ecological fitness, gatekeeper, observer, drift detection
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from dharma_swarm.gaia_ledger import (
    ComputeUnit,
    ConservationLawChecker,
    FundingUnit,
    GaiaLedger,
    GaiaObserver,
    LaborUnit,
    LedgerEntry,
    Morphism,
    MorphismType,
    OffsetUnit,
    UnitType,
    VerificationUnit,
)
from dharma_swarm.gaia_verification import (
    ORACLE_TYPES,
    VERIFICATION_THRESHOLD,
    OracleVerdict,
    VerificationOracle,
    VerificationSession,
    verify_offset,
)
from dharma_swarm.gaia_fitness import (
    EcologicalFitness,
    EcologicalGatekeeper,
    detect_goodhart_drift,
    gaia_observer_function,
    observe_ledger,
)
from dharma_swarm.archive import FitnessScore
from dharma_swarm.monad import ObservedState
from dharma_swarm.rv import RVReading
from dharma_swarm.models import GateDecision
from dharma_swarm.sheaf import CoordinationResult


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_compute(provider: str = "runpod", energy_mwh: float = 1.0,
                  carbon_intensity: float = 0.5) -> ComputeUnit:
    return ComputeUnit(
        provider=provider,
        energy_mwh=energy_mwh,
        carbon_intensity=carbon_intensity,
    )


def _make_offset(project_id: str = "proj-1", co2e_tons: float = 10.0,
                 confidence: float = 0.0, is_verified: bool = False,
                 **kwargs) -> OffsetUnit:
    return OffsetUnit(
        project_id=project_id,
        co2e_tons=co2e_tons,
        confidence=confidence,
        is_verified=is_verified,
        **kwargs,
    )


def _make_funding(amount_usd: float = 1000.0, source: str = "grant",
                  destination: str = "project") -> FundingUnit:
    return FundingUnit(
        amount_usd=amount_usd,
        source=source,
        destination=destination,
    )


def _make_labor(worker_id: str = "w1", project_id: str = "proj-1",
                hours: float = 8.0) -> LaborUnit:
    return LaborUnit(
        worker_id=worker_id,
        project_id=project_id,
        hours=hours,
    )


def _make_verification(oracle_type: str = "satellite",
                       target_id: str = "off-1",
                       confidence: float = 0.9) -> VerificationUnit:
    return VerificationUnit(
        oracle_type=oracle_type,
        target_id=target_id,
        target_type=UnitType.OFFSET,
        confidence=confidence,
    )


def _make_verdict(oracle_type: str, target_id: str = "off-1",
                  confidence: float = 0.9,
                  agrees: bool = True) -> OracleVerdict:
    return OracleVerdict(
        oracle_type=oracle_type,
        target_id=target_id,
        confidence=confidence,
        agrees_with_claim=agrees,
    )


def _ledger_with_verified_offset(tmp_path, confidence: float = 0.9
                                  ) -> tuple[GaiaLedger, OffsetUnit]:
    """Return a ledger with one offset verified by 3 distinct oracle types."""
    ledger = GaiaLedger(data_dir=tmp_path / "ledger")
    offset = _make_offset()
    ledger.record_offset(offset)
    for otype in ["satellite", "iot_sensor", "human_auditor"]:
        v = _make_verification(oracle_type=otype, target_id=offset.id,
                               confidence=confidence)
        ledger.record_verification(v)
    return ledger, offset


# =========================================================================
#  GAIA LEDGER TESTS
# =========================================================================


class TestUnitCreation:
    """Create and record all five unit types."""

    def test_compute_unit_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        unit = _make_compute(energy_mwh=2.0, carbon_intensity=0.4)
        entry = ledger.record_compute(unit)
        assert entry.entry_type == "compute"
        assert ledger.entry_count == 1
        assert abs(unit.co2e_tons - 0.8) < 1e-9

    def test_offset_unit_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        unit = _make_offset(co2e_tons=5.0)
        entry = ledger.record_offset(unit)
        assert entry.entry_type == "offset"
        assert ledger.entry_count == 1

    def test_funding_unit_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        unit = _make_funding(amount_usd=500.0)
        entry = ledger.record_funding(unit)
        assert entry.entry_type == "funding"
        assert ledger.entry_count == 1

    def test_labor_unit_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        unit = _make_labor(hours=4.0)
        entry = ledger.record_labor(unit)
        assert entry.entry_type == "labor"
        assert ledger.entry_count == 1

    def test_verification_unit_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        unit = _make_verification()
        entry = ledger.record_verification(unit)
        assert entry.entry_type == "verification"
        assert ledger.entry_count == 1

    def test_all_five_unit_types(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        ledger.record_offset(_make_offset())
        ledger.record_funding(_make_funding())
        ledger.record_labor(_make_labor())
        ledger.record_verification(_make_verification())
        assert ledger.entry_count == 5


class TestHashChain:
    """Hash chain integrity: record entries, verify chain, tamper detection."""

    def test_empty_chain_valid(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        assert ledger.verify_chain_integrity() is True

    def test_single_entry_chain(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        assert ledger.verify_chain_integrity() is True

    def test_multiple_entries_chain(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        ledger.record_offset(_make_offset())
        ledger.record_funding(_make_funding())
        ledger.record_labor(_make_labor())
        assert ledger.verify_chain_integrity() is True

    def test_tamper_detection(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        ledger.record_offset(_make_offset())
        ledger.record_funding(_make_funding())
        # Tamper: overwrite prev_hash of second entry
        ledger._entries[1].prev_hash = "tampered_hash_value"
        assert ledger.verify_chain_integrity() is False

    def test_chain_head_empty_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        assert ledger.chain_head == ""

    def test_chain_head_nonempty(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        head = ledger.chain_head
        assert isinstance(head, str)
        assert len(head) == 32  # BLAKE2b 16-byte digest -> 32 hex chars

    def test_first_entry_prev_hash_is_empty(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        assert ledger._entries[0].prev_hash == ""

    def test_second_entry_prev_hash_links_to_first(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        first_hash = ledger._entries[0].compute_hash()
        ledger.record_offset(_make_offset())
        assert ledger._entries[1].prev_hash == first_hash


class TestConservationLaws:
    """Conservation law checker: five algebraic invariants."""

    def setup_method(self):
        self.checker = ConservationLawChecker()

    def test_no_creation_ex_nihilo_pass(self):
        verified = [_make_offset(co2e_tons=10.0, confidence=1.0,
                                 is_verified=True)]
        claimed = [_make_offset(co2e_tons=10.0)]
        result = self.checker.check_no_creation_ex_nihilo(claimed, verified)
        assert result is None

    def test_no_creation_ex_nihilo_violation(self):
        verified = [_make_offset(co2e_tons=5.0, confidence=1.0,
                                 is_verified=True)]
        claimed = [_make_offset(co2e_tons=20.0)]
        result = self.checker.check_no_creation_ex_nihilo(claimed, verified)
        assert result is not None
        assert result.law == "no_creation_ex_nihilo"
        assert result.evidence["total_claimed"] == 20.0
        assert result.evidence["total_verified"] == 5.0

    def test_no_double_counting_pass(self):
        verifications = [
            _make_verification(oracle_type="satellite", target_id="a"),
            _make_verification(oracle_type="iot_sensor", target_id="a"),
        ]
        result = self.checker.check_no_double_counting(verifications)
        assert result is None

    def test_no_double_counting_violation(self):
        v1 = _make_verification(oracle_type="satellite", target_id="a")
        v2 = _make_verification(oracle_type="satellite", target_id="a")
        result = self.checker.check_no_double_counting([v1, v2])
        assert result is not None
        assert result.law == "no_double_counting"

    def test_additionality_pass(self):
        offset = _make_offset(co2e_tons=15.0)
        result = self.checker.check_additionality(offset, baseline_co2e=10.0)
        assert result is None

    def test_additionality_violation(self):
        offset = _make_offset(co2e_tons=5.0)
        result = self.checker.check_additionality(offset, baseline_co2e=10.0)
        assert result is not None
        assert result.law == "additionality"

    def test_additionality_equal_to_baseline_violates(self):
        offset = _make_offset(co2e_tons=10.0)
        result = self.checker.check_additionality(offset, baseline_co2e=10.0)
        assert result is not None
        assert result.law == "additionality"

    def test_temporal_coherence_unverified_offset(self):
        offset = _make_offset(co2e_tons=5.0, is_verified=False)
        result = self.checker.check_temporal_coherence(offset)
        assert result is not None
        assert result.law == "temporal_coherence"

    def test_temporal_coherence_verified_offset_pass(self):
        offset = _make_offset(co2e_tons=5.0, is_verified=True)
        result = self.checker.check_temporal_coherence(offset)
        assert result is None

    def test_temporal_coherence_future_vintage(self):
        future = datetime.now(timezone.utc) + timedelta(days=365)
        offset = _make_offset(co2e_tons=5.0, is_verified=True)
        offset.vintage_start = future
        past = datetime.now(timezone.utc) - timedelta(days=30)
        result = self.checker.check_temporal_coherence(offset,
                                                       measurement_date=past)
        assert result is not None
        assert result.law == "temporal_coherence"

    def test_compositional_integrity_pass(self):
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="c1",
            target_id="o1",
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        result = self.checker.check_compositional_integrity([morphism])
        assert result is None

    def test_compositional_integrity_violation(self):
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="c1",
            target_id="o1",
            source_type=UnitType.FUNDING,  # wrong: should be COMPUTE
            target_type=UnitType.OFFSET,
        )
        result = self.checker.check_compositional_integrity([morphism])
        assert result is not None
        assert result.law == "compositional_integrity"

    def test_check_all_returns_multiple_violations(self):
        # Create conditions for multiple violations
        claimed = [_make_offset(co2e_tons=100.0)]
        verified = [_make_offset(co2e_tons=1.0, confidence=1.0,
                                 is_verified=True)]
        v1 = _make_verification(oracle_type="satellite", target_id="x")
        v2 = _make_verification(oracle_type="satellite", target_id="x")
        bad_morphism = Morphism(
            morphism_type=MorphismType.FUND,
            source_id="a",
            target_id="b",
            source_type=UnitType.COMPUTE,  # wrong
            target_type=UnitType.OFFSET,   # wrong
        )
        violations = self.checker.check_all(
            claimed_offsets=claimed,
            verified_offsets=verified,
            verifications=[v1, v2],
            morphisms=[bad_morphism],
        )
        laws = {v.law for v in violations}
        assert "no_creation_ex_nihilo" in laws
        assert "no_double_counting" in laws
        assert "compositional_integrity" in laws


class TestThreeOfFiveAutoVerify:
    """3-of-5 verification threshold via ledger record_verification."""

    def test_two_oracles_not_enough(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)
        for otype in ["satellite", "iot_sensor"]:
            v = _make_verification(oracle_type=otype, target_id=offset.id,
                                   confidence=0.8)
            ledger.record_verification(v)
        assert ledger._offset_units[offset.id].is_verified is False

    def test_three_oracles_trigger_verification(self, tmp_path):
        ledger, offset = _ledger_with_verified_offset(tmp_path)
        stored = ledger._offset_units[offset.id]
        assert stored.is_verified is True
        assert abs(stored.confidence - 0.9) < 1e-9

    def test_four_oracles_still_verified(self, tmp_path):
        ledger, offset = _ledger_with_verified_offset(tmp_path)
        v = _make_verification(oracle_type="community", target_id=offset.id,
                               confidence=0.7)
        ledger.record_verification(v)
        stored = ledger._offset_units[offset.id]
        assert stored.is_verified is True
        # Confidence is average of all 4 verification confidences
        assert abs(stored.confidence - (0.9 * 3 + 0.7) / 4) < 1e-9

    def test_duplicate_oracle_type_still_counts_as_one(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)
        # 3 verifications but only 2 distinct oracle types
        for otype in ["satellite", "satellite", "iot_sensor"]:
            v = _make_verification(oracle_type=otype, target_id=offset.id,
                                   confidence=0.8)
            ledger.record_verification(v)
        assert ledger._offset_units[offset.id].is_verified is False


class TestMorphismRecording:
    """Morphism recording with conservation checks."""

    def test_valid_morphism_no_violations(self, tmp_path):
        ledger, offset = _ledger_with_verified_offset(tmp_path)
        compute = _make_compute()
        ledger.record_compute(compute)
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id=compute.id,
            target_id=offset.id,
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        entry, violations = ledger.record_morphism(morphism)
        assert entry.entry_type == "morphism"
        # Verified offset covers compute emissions so no ex_nihilo violation
        # (depends on amounts, but with 10 tons offset vs 0.5 tons compute)
        type_violations = [v for v in violations
                           if v.law == "compositional_integrity"]
        assert len(type_violations) == 0

    def test_mistyped_morphism_produces_violation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="a",
            target_id="b",
            source_type=UnitType.FUNDING,  # wrong
            target_type=UnitType.OFFSET,
        )
        _entry, violations = ledger.record_morphism(morphism)
        assert any(v.law == "compositional_integrity" for v in violations)


class TestQueries:
    """Query methods: total_compute_co2e, total_verified_offset, etc."""

    def test_total_compute_co2e(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute(energy_mwh=2.0,
                                            carbon_intensity=0.5))
        ledger.record_compute(_make_compute(energy_mwh=3.0,
                                            carbon_intensity=0.4))
        assert abs(ledger.total_compute_co2e() - (1.0 + 1.2)) < 1e-9

    def test_total_verified_offset(self, tmp_path):
        ledger, offset = _ledger_with_verified_offset(tmp_path)
        # offset is 10 tons, confidence 0.9 -> verified = 9.0
        assert abs(ledger.total_verified_offset() - 9.0) < 1e-9

    def test_total_verified_offset_empty(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        assert ledger.total_verified_offset() == 0.0

    def test_net_carbon_position_positive(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute(energy_mwh=100.0,
                                            carbon_intensity=1.0))
        # 100 tons emitted, 0 offset -> positive (still emitting)
        assert ledger.net_carbon_position() > 0

    def test_net_carbon_position_negative(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        ledger.record_compute(_make_compute(energy_mwh=1.0,
                                            carbon_intensity=0.1))
        # 0.1 tons emitted, 9.0 tons offset -> negative (net-negative)
        assert ledger.net_carbon_position() < 0

    def test_worker_count(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_labor(_make_labor(worker_id="alice"))
        ledger.record_labor(_make_labor(worker_id="bob"))
        ledger.record_labor(_make_labor(worker_id="alice"))  # duplicate
        assert ledger.worker_count() == 2

    def test_total_labor_hours(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_labor(_make_labor(hours=5.0))
        ledger.record_labor(_make_labor(worker_id="w2", hours=3.0))
        assert abs(ledger.total_labor_hours() - 8.0) < 1e-9

    def test_total_funding_usd(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_funding(_make_funding(amount_usd=1000.0))
        ledger.record_funding(_make_funding(amount_usd=2500.0))
        assert abs(ledger.total_funding_usd() - 3500.0) < 1e-9


class TestLedgerSummary:
    """Ledger summary returns correct structure."""

    def test_summary_keys(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        summary = ledger.summary()
        expected_keys = {
            "entries", "chain_valid", "compute_units", "offset_units",
            "funding_units", "labor_units", "verification_units",
            "morphisms", "total_compute_co2e", "total_verified_offset",
            "net_carbon_position", "total_labor_hours", "total_funding_usd",
            "worker_count", "conservation_violations", "violations",
        }
        assert expected_keys <= set(summary.keys())

    def test_summary_counts(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        ledger.record_offset(_make_offset())
        summary = ledger.summary()
        assert summary["compute_units"] == 1
        assert summary["offset_units"] == 1
        assert summary["entries"] == 2
        assert summary["chain_valid"] is True


class TestValidation:
    """Pydantic validation: negative energy, negative CO2e, zero funding."""

    def test_negative_energy_rejected(self):
        with pytest.raises(ValidationError):
            ComputeUnit(provider="test", energy_mwh=-1.0,
                        carbon_intensity=0.5)

    def test_negative_co2e_rejected(self):
        with pytest.raises(ValidationError):
            OffsetUnit(project_id="test", co2e_tons=-1.0)

    def test_zero_funding_rejected(self):
        with pytest.raises(ValidationError):
            FundingUnit(amount_usd=0.0, source="x", destination="y")

    def test_negative_funding_rejected(self):
        with pytest.raises(ValidationError):
            FundingUnit(amount_usd=-100.0, source="x", destination="y")

    def test_negative_hours_rejected(self):
        with pytest.raises(ValidationError):
            LaborUnit(worker_id="w", project_id="p", hours=-1.0)

    def test_confidence_clamped_to_bounds(self):
        offset = OffsetUnit(project_id="p", co2e_tons=1.0, confidence=1.5)
        assert offset.confidence <= 1.0
        offset2 = OffsetUnit(project_id="p", co2e_tons=1.0, confidence=-0.5)
        assert offset2.confidence >= 0.0


class TestLedgerPersistence:
    """Save and load round-trip."""

    def test_save_and_load(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute(energy_mwh=3.0,
                                            carbon_intensity=0.5))
        ledger.record_offset(_make_offset(co2e_tons=7.0))
        path = ledger.save()
        assert path.exists()

        ledger2 = GaiaLedger(data_dir=tmp_path / "ledger")
        count = ledger2.load()
        assert count == 2
        assert ledger2.entry_count == 2

    def test_load_nonexistent_returns_zero(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "no_such_dir")
        assert ledger.load() == 0


# =========================================================================
#  GAIA VERIFICATION TESTS
# =========================================================================


class TestVerificationSession:
    """VerificationSession creation, verdict submission, finalization."""

    def test_session_creation(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        assert session.offset_id == "off-1"
        assert session.is_complete is False
        assert session.oracle_count == 0

    def test_submit_verdicts(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        oracle.submit_verdict(session.id, _make_verdict("iot_sensor"))
        assert session.oracle_count == 2

    def test_finalize_session(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        oracle.submit_verdict(session.id, _make_verdict("iot_sensor"))
        oracle.submit_verdict(session.id, _make_verdict("human_auditor"))
        result = oracle.finalize_session(session.id)
        assert result.is_complete is True
        assert result.meets_threshold is True
        assert len(result.agreeing_oracles) == 3

    def test_finalize_computes_confidence(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id,
                              _make_verdict("satellite", confidence=0.8))
        oracle.submit_verdict(session.id,
                              _make_verdict("iot_sensor", confidence=0.9))
        oracle.submit_verdict(session.id,
                              _make_verdict("human_auditor", confidence=1.0))
        result = oracle.finalize_session(session.id)
        expected = (0.8 + 0.9 + 1.0) / 3
        assert abs(result.final_confidence - expected) < 1e-9


class TestThresholdMetOrNot:
    """3-of-5 threshold met vs not met."""

    def test_threshold_met_with_3_agrees(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        for otype in ["satellite", "iot_sensor", "human_auditor"]:
            oracle.submit_verdict(session.id, _make_verdict(otype))
        oracle.finalize_session(session.id)
        assert session.meets_threshold is True

    def test_threshold_not_met_with_2_agrees(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        oracle.submit_verdict(session.id, _make_verdict("iot_sensor"))
        oracle.submit_verdict(session.id,
                              _make_verdict("human_auditor", agrees=False))
        oracle.finalize_session(session.id)
        assert session.meets_threshold is False

    def test_threshold_met_with_mixed_agrees_dissents(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        oracle.submit_verdict(session.id, _make_verdict("iot_sensor"))
        oracle.submit_verdict(session.id,
                              _make_verdict("human_auditor", agrees=False))
        oracle.submit_verdict(session.id, _make_verdict("community"))
        oracle.finalize_session(session.id)
        # 3 agrees (satellite, iot_sensor, community), 1 dissent
        assert session.meets_threshold is True
        assert "human_auditor" in session.dissenting_oracles

    def test_threshold_constant(self):
        assert VERIFICATION_THRESHOLD == 3

    def test_oracle_types_constant(self):
        assert len(ORACLE_TYPES) == 5
        assert "satellite" in ORACLE_TYPES


class TestDuplicateOracleRejection:
    """Duplicate oracle type rejection."""

    def test_duplicate_oracle_type_raises(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        with pytest.raises(ValueError, match="already submitted"):
            oracle.submit_verdict(session.id, _make_verdict("satellite"))


class TestFinalizedSessionRejection:
    """Already-finalized session rejection."""

    def test_submit_to_finalized_session_raises(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id, _make_verdict("satellite"))
        oracle.finalize_session(session.id)
        with pytest.raises(ValueError, match="already finalized"):
            oracle.submit_verdict(session.id, _make_verdict("iot_sensor"))


class TestSheafIntegration:
    """to_sheaf_coordination produces CoordinationResult."""

    def test_sheaf_coordination_result(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        oracle.submit_verdict(session.id,
                              _make_verdict("satellite", confidence=0.9))
        oracle.submit_verdict(session.id,
                              _make_verdict("iot_sensor", confidence=0.8))
        oracle.submit_verdict(session.id,
                              _make_verdict("human_auditor", confidence=0.85))
        oracle.finalize_session(session.id)

        result = oracle.to_sheaf_coordination(session.id)
        assert result is not None
        assert isinstance(result, CoordinationResult)

    def test_sheaf_coordination_empty_session_returns_none(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off-1")
        # No verdicts submitted
        result = oracle.to_sheaf_coordination(session.id)
        assert result is None

    def test_sheaf_coordination_nonexistent_session_returns_none(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        oracle = VerificationOracle(ledger)
        result = oracle.to_sheaf_coordination("nonexistent-id")
        assert result is None


class TestVerifyOffsetConvenience:
    """verify_offset convenience function."""

    def test_verify_offset_full_pipeline(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)

        verdicts = [
            _make_verdict("satellite", target_id=offset.id, confidence=0.9),
            _make_verdict("iot_sensor", target_id=offset.id, confidence=0.85),
            _make_verdict("human_auditor", target_id=offset.id,
                          confidence=0.95),
        ]
        session, coordination = verify_offset(ledger, offset.id, verdicts)

        assert session.is_complete is True
        assert session.meets_threshold is True
        assert coordination is not None
        assert isinstance(coordination, CoordinationResult)

    def test_verify_offset_below_threshold(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)

        verdicts = [
            _make_verdict("satellite", target_id=offset.id, agrees=True),
            _make_verdict("iot_sensor", target_id=offset.id, agrees=False),
            _make_verdict("human_auditor", target_id=offset.id, agrees=False),
        ]
        session, coordination = verify_offset(ledger, offset.id, verdicts)

        assert session.is_complete is True
        assert session.meets_threshold is False


class TestFinalizeLedgerRecording:
    """Finalization records verifications to ledger when threshold met."""

    def test_finalize_records_to_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)
        initial_count = ledger.entry_count

        oracle = VerificationOracle(ledger)
        session = oracle.start_session(offset.id)
        oracle.submit_verdict(session.id,
                              _make_verdict("satellite", target_id=offset.id))
        oracle.submit_verdict(session.id,
                              _make_verdict("iot_sensor", target_id=offset.id))
        oracle.submit_verdict(session.id,
                              _make_verdict("human_auditor",
                                            target_id=offset.id))
        oracle.finalize_session(session.id)

        # 3 agreeing verdicts should produce 3 verification entries
        assert ledger.entry_count == initial_count + 3

    def test_finalize_does_not_record_when_below_threshold(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)
        initial_count = ledger.entry_count

        oracle = VerificationOracle(ledger)
        session = oracle.start_session(offset.id)
        oracle.submit_verdict(session.id,
                              _make_verdict("satellite", target_id=offset.id,
                                            agrees=True))
        oracle.submit_verdict(session.id,
                              _make_verdict("iot_sensor", target_id=offset.id,
                                            agrees=False))
        oracle.finalize_session(session.id)

        # Below threshold: nothing recorded
        assert ledger.entry_count == initial_count


# =========================================================================
#  GAIA FITNESS TESTS
# =========================================================================


class TestEcologicalFitnessScore:
    """EcologicalFitness.score() returns valid FitnessScore."""

    def test_score_returns_fitness_score(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        fitness = EcologicalFitness()
        result = fitness.score(ledger)
        assert isinstance(result, FitnessScore)

    def test_score_fields_bounded(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        ledger.record_compute(_make_compute())
        fitness = EcologicalFitness()
        result = fitness.score(ledger)
        assert 0.0 <= result.correctness <= 1.0
        assert 0.0 <= result.elegance <= 1.0
        assert 0.0 <= result.safety <= 1.0
        assert 0.0 <= result.dharmic_alignment <= 1.0

    def test_score_with_verified_offsets_has_high_safety(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        fitness = EcologicalFitness()
        result = fitness.score(ledger)
        # safety = verification_coverage, which should be 1.0 (1/1 verified)
        assert result.safety == 1.0

    def test_score_empty_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        fitness = EcologicalFitness()
        result = fitness.score(ledger)
        # Empty ledger: correctness=1 (no violations), safety=0 (no coverage)
        assert result.correctness == 1.0
        assert result.safety == 0.0


class TestWeightedScore:
    """EcologicalFitness.weighted_score() returns float in [0,1]."""

    def test_weighted_score_returns_float(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        fitness = EcologicalFitness()
        result = fitness.weighted_score(ledger)
        assert isinstance(result, float)

    def test_weighted_score_in_range(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        ledger.record_compute(_make_compute())
        fitness = EcologicalFitness()
        result = fitness.weighted_score(ledger)
        assert 0.0 <= result <= 1.0

    def test_weighted_score_custom_weights(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        weights = {
            "verification_coverage": 0.5,
            "conservation_integrity": 0.2,
            "oracle_diversity": 0.1,
            "chain_integrity": 0.1,
            "carbon_progress": 0.1,
        }
        fitness = EcologicalFitness(weights=weights)
        result = fitness.weighted_score(ledger)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_weighted_score_empty_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        fitness = EcologicalFitness()
        result = fitness.weighted_score(ledger)
        # Empty: integrity=1, chain_ok=1, coverage=0, diversity=0, progress=0.5
        # = 0.25*0 + 0.25*1 + 0.15*0 + 0.10*1 + 0.25*0.5 = 0.475
        assert abs(result - 0.475) < 1e-9


class TestEcologicalGatekeeper:
    """EcologicalGatekeeper.check_morphism behavior."""

    def test_good_morphism_allowed(self, tmp_path):
        # Use confidence=1.0 so claimed==verified (no conservation advisory)
        ledger, offset = _ledger_with_verified_offset(tmp_path,
                                                       confidence=1.0)
        compute = _make_compute()
        ledger.record_compute(compute)
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id=compute.id,
            target_id=offset.id,
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        gatekeeper = EcologicalGatekeeper()
        decision, reason = gatekeeper.check_morphism(morphism, ledger)
        assert decision == GateDecision.ALLOW
        assert "passed" in reason.lower()

    def test_unverified_offset_match_returns_review(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        offset = _make_offset()
        ledger.record_offset(offset)
        compute = _make_compute()
        ledger.record_compute(compute)
        morphism = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id=compute.id,
            target_id=offset.id,
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        gatekeeper = EcologicalGatekeeper()
        decision, reason = gatekeeper.check_morphism(morphism, ledger)
        assert decision == GateDecision.REVIEW
        assert "SATYA" in reason

    def test_fund_morphism_allowed(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        morphism = Morphism(
            morphism_type=MorphismType.FUND,
            source_id="f1",
            target_id="l1",
            source_type=UnitType.FUNDING,
            target_type=UnitType.LABOR,
        )
        gatekeeper = EcologicalGatekeeper()
        decision, _reason = gatekeeper.check_morphism(morphism, ledger)
        assert decision == GateDecision.ALLOW


class TestObserveLedger:
    """observe_ledger() returns ObservedState with R_V reading."""

    def test_observe_ledger_returns_observed_state(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        result = observe_ledger(ledger)
        assert isinstance(result, ObservedState)

    def test_observe_ledger_has_rv_reading(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        result = observe_ledger(ledger)
        assert result.rv_reading is not None
        assert isinstance(result.rv_reading, RVReading)

    def test_observe_ledger_state_is_summary(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        ledger.record_compute(_make_compute())
        result = observe_ledger(ledger)
        state = result.state
        assert isinstance(state, dict)
        assert "entries" in state
        assert "chain_valid" in state


class TestGaiaObserverFunction:
    """gaia_observer_function() returns RVReading."""

    def test_returns_rv_reading(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        reading = gaia_observer_function(ledger)
        assert reading is not None
        assert isinstance(reading, RVReading)

    def test_rv_reading_model_name(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        reading = gaia_observer_function(ledger)
        assert reading.model_name == "gaia_ledger"

    def test_rv_reading_prompt_group(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        reading = gaia_observer_function(ledger)
        assert reading.prompt_group == "ecological"

    def test_rv_value_matches_self_referential_fitness(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        ledger.record_compute(_make_compute())
        observer = GaiaObserver()
        obs = observer.observe(ledger)
        reading = gaia_observer_function(ledger)
        assert abs(reading.rv - obs["self_referential_fitness"]) < 1e-9


class TestGoodhartDriftDetection:
    """detect_goodhart_drift() detects and reports drift."""

    def test_drift_detected_when_unverified(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        # Large offset claims, zero verification
        ledger.record_offset(_make_offset(co2e_tons=100.0))
        result = detect_goodhart_drift(ledger)
        assert result["is_drifting"] is True
        assert "GOODHART DRIFT DETECTED" in result["diagnosis"]
        assert result["verification_ratio"] == 0.0

    def test_no_drift_when_verified(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        result = detect_goodhart_drift(ledger)
        assert result["is_drifting"] is False
        assert "No drift" in result["diagnosis"]
        assert result["verification_ratio"] >= 0.5

    def test_no_drift_empty_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        result = detect_goodhart_drift(ledger)
        assert result["is_drifting"] is False

    def test_drift_report_keys(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        result = detect_goodhart_drift(ledger)
        expected_keys = {
            "is_drifting", "verification_ratio", "coverage",
            "diversity", "violations", "self_referential_fitness",
            "diagnosis",
        }
        assert expected_keys <= set(result.keys())

    def test_drift_partial_verification(self, tmp_path):
        """Verification ratio below 0.5 triggers drift."""
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        # 100 tons unverified, 10 tons verified
        ledger.record_offset(_make_offset(co2e_tons=100.0))
        offset2 = _make_offset(co2e_tons=10.0, confidence=0.9,
                               is_verified=True)
        ledger.record_offset(offset2)
        # Total claimed = 110, total verified = 10*0.9 = 9.0
        # Ratio = 9.0/110.0 ~ 0.082 < 0.5
        result = detect_goodhart_drift(ledger)
        assert result["is_drifting"] is True


class TestGaiaObserver:
    """GaiaObserver.observe() and is_goodhart_drifting()."""

    def test_observe_returns_expected_keys(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        observer = GaiaObserver()
        result = observer.observe(ledger)
        expected_keys = {
            "chain_valid", "conservation_violations",
            "verification_coverage", "oracle_diversity",
            "violation_rate", "self_referential_fitness",
            "net_carbon_position",
        }
        assert expected_keys <= set(result.keys())

    def test_observe_empty_ledger(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path / "ledger")
        observer = GaiaObserver()
        result = observer.observe(ledger)
        assert result["chain_valid"] is True
        assert result["verification_coverage"] == 0.0
        assert result["conservation_violations"] == 0

    def test_observe_with_data(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        observer = GaiaObserver()
        result = observer.observe(ledger)
        assert result["verification_coverage"] == 1.0
        assert result["chain_valid"] is True

    def test_self_referential_fitness_range(self, tmp_path):
        ledger, _offset = _ledger_with_verified_offset(tmp_path)
        observer = GaiaObserver()
        result = observer.observe(ledger)
        fitness = result["self_referential_fitness"]
        assert 0.0 <= fitness <= 1.0
