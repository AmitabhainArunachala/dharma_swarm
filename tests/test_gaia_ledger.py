"""Tests for gaia_ledger.py — categorical accounting ledger for GAIA ecological coordination."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from dharma_swarm.gaia_ledger import (
    ComputeUnit,
    ConservationLawChecker,
    ConservationViolation,
    FundingUnit,
    GaiaLedger,
    GaiaObserver,
    LaborUnit,
    LedgerEntry,
    Morphism,
    MorphismType,
    MORPHISM_TYPES,
    OffsetUnit,
    UnitType,
    VerificationUnit,
    _blake2b,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestBlake2b:
    def test_deterministic(self):
        assert _blake2b("hello") == _blake2b("hello")

    def test_different_inputs(self):
        assert _blake2b("a") != _blake2b("b")

    def test_returns_hex_string(self):
        h = _blake2b("test")
        assert isinstance(h, str)
        assert len(h) == 32  # 16-byte digest = 32 hex chars


# ---------------------------------------------------------------------------
# Unit models
# ---------------------------------------------------------------------------


class TestComputeUnit:
    def test_construction(self):
        u = ComputeUnit(provider="aws", energy_mwh=1.5, carbon_intensity=0.4)
        assert u.provider == "aws"
        assert u.energy_mwh == 1.5

    def test_co2e_tons(self):
        u = ComputeUnit(provider="aws", energy_mwh=2.0, carbon_intensity=0.5)
        assert abs(u.co2e_tons - 1.0) < 0.001

    def test_negative_energy_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            ComputeUnit(provider="aws", energy_mwh=-1.0, carbon_intensity=0.5)

    def test_zero_energy_allowed(self):
        u = ComputeUnit(provider="aws", energy_mwh=0.0, carbon_intensity=0.5)
        assert u.co2e_tons == 0.0

    def test_has_id_and_timestamp(self):
        u = ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.4)
        assert u.id
        assert u.timestamp


class TestOffsetUnit:
    def test_construction(self):
        u = OffsetUnit(project_id="proj1", co2e_tons=10.0)
        assert u.project_id == "proj1"
        assert u.is_verified is False

    def test_negative_co2e_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            OffsetUnit(project_id="p", co2e_tons=-5.0)

    def test_confidence_clamped(self):
        u = OffsetUnit(project_id="p", co2e_tons=1.0, confidence=1.5)
        assert u.confidence == 1.0
        u2 = OffsetUnit(project_id="p", co2e_tons=1.0, confidence=-0.5)
        assert u2.confidence == 0.0


class TestFundingUnit:
    def test_construction(self):
        u = FundingUnit(amount_usd=1000.0, source="donor", destination="project")
        assert u.amount_usd == 1000.0

    def test_zero_amount_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            FundingUnit(amount_usd=0.0, source="a", destination="b")

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            FundingUnit(amount_usd=-100.0, source="a", destination="b")


class TestLaborUnit:
    def test_construction(self):
        u = LaborUnit(worker_id="w1", project_id="p1", hours=8.0)
        assert u.hours == 8.0

    def test_negative_hours_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            LaborUnit(worker_id="w1", project_id="p1", hours=-1.0)


class TestVerificationUnit:
    def test_construction(self):
        u = VerificationUnit(
            oracle_type="satellite", target_id="o1", target_type=UnitType.OFFSET
        )
        assert u.oracle_type == "satellite"

    def test_confidence_clamped(self):
        u = VerificationUnit(
            oracle_type="satellite",
            target_id="o1",
            target_type=UnitType.OFFSET,
            confidence=2.0,
        )
        assert u.confidence == 1.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_unit_types(self):
        assert UnitType.COMPUTE.value == "compute"
        assert UnitType.VERIFICATION.value == "verification"

    def test_morphism_types(self):
        assert MorphismType.OFFSET_MATCH.value == "offset_match"
        assert MorphismType.VERIFY.value == "verify"

    def test_morphism_type_constraints(self):
        assert MORPHISM_TYPES[MorphismType.OFFSET_MATCH] == (
            UnitType.COMPUTE,
            UnitType.OFFSET,
        )
        assert MORPHISM_TYPES[MorphismType.VERIFY] == (
            UnitType.OFFSET,
            UnitType.VERIFICATION,
        )


# ---------------------------------------------------------------------------
# Conservation Law Checker
# ---------------------------------------------------------------------------


class TestConservationLawChecker:
    def setup_method(self):
        self.checker = ConservationLawChecker()

    def test_no_creation_ex_nihilo_passes(self):
        claimed = [OffsetUnit(project_id="p", co2e_tons=5.0)]
        verified = [
            OffsetUnit(project_id="p", co2e_tons=10.0, is_verified=True, confidence=0.9)
        ]
        assert self.checker.check_no_creation_ex_nihilo(claimed, verified) is None

    def test_no_creation_ex_nihilo_fails(self):
        claimed = [OffsetUnit(project_id="p", co2e_tons=20.0)]
        verified = [
            OffsetUnit(project_id="p", co2e_tons=5.0, is_verified=True, confidence=0.8)
        ]
        v = self.checker.check_no_creation_ex_nihilo(claimed, verified)
        assert v is not None
        assert v.law == "no_creation_ex_nihilo"
        assert v.severity > 0

    def test_no_double_counting_passes(self):
        verifs = [
            VerificationUnit(
                oracle_type="satellite", target_id="o1", target_type=UnitType.OFFSET
            ),
            VerificationUnit(
                oracle_type="iot_sensor", target_id="o1", target_type=UnitType.OFFSET
            ),
        ]
        assert self.checker.check_no_double_counting(verifs) is None

    def test_no_double_counting_fails(self):
        verifs = [
            VerificationUnit(
                oracle_type="satellite", target_id="o1", target_type=UnitType.OFFSET
            ),
            VerificationUnit(
                oracle_type="satellite", target_id="o1", target_type=UnitType.OFFSET
            ),
        ]
        v = self.checker.check_no_double_counting(verifs)
        assert v is not None
        assert v.law == "no_double_counting"

    def test_additionality_passes(self):
        offset = OffsetUnit(project_id="p", co2e_tons=10.0)
        assert self.checker.check_additionality(offset, baseline_co2e=5.0) is None

    def test_additionality_fails(self):
        offset = OffsetUnit(project_id="p", co2e_tons=3.0)
        v = self.checker.check_additionality(offset, baseline_co2e=5.0)
        assert v is not None
        assert v.law == "additionality"

    def test_temporal_coherence_unverified(self):
        offset = OffsetUnit(project_id="p", co2e_tons=5.0, is_verified=False)
        v = self.checker.check_temporal_coherence(offset)
        assert v is not None
        assert v.law == "temporal_coherence"

    def test_temporal_coherence_verified(self):
        offset = OffsetUnit(project_id="p", co2e_tons=5.0, is_verified=True)
        assert self.checker.check_temporal_coherence(offset) is None

    def test_compositional_integrity_passes(self):
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="s1",
            target_id="t1",
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        assert self.checker.check_compositional_integrity([m]) is None

    def test_compositional_integrity_fails(self):
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="s1",
            target_id="t1",
            source_type=UnitType.FUNDING,  # wrong type
            target_type=UnitType.OFFSET,
        )
        v = self.checker.check_compositional_integrity([m])
        assert v is not None
        assert v.law == "compositional_integrity"

    def test_check_all_aggregates(self):
        violations = self.checker.check_all()
        assert violations == []


# ---------------------------------------------------------------------------
# LedgerEntry
# ---------------------------------------------------------------------------


class TestLedgerEntry:
    def test_compute_hash_deterministic(self):
        e = LedgerEntry(
            sequence=0,
            entry_type="compute",
            payload={"test": True},
            payload_hash="abc",
            prev_hash="",
        )
        h1 = e.compute_hash()
        h2 = e.compute_hash()
        assert h1 == h2

    def test_different_entries_different_hashes(self):
        e1 = LedgerEntry(sequence=0, entry_type="compute", payload_hash="a", prev_hash="")
        e2 = LedgerEntry(sequence=1, entry_type="offset", payload_hash="b", prev_hash="x")
        assert e1.compute_hash() != e2.compute_hash()


# ---------------------------------------------------------------------------
# GaiaLedger
# ---------------------------------------------------------------------------


class TestGaiaLedger:
    def test_empty_ledger(self):
        ledger = GaiaLedger()
        assert ledger.entry_count == 0
        assert ledger.chain_head == ""

    def test_record_compute(self):
        ledger = GaiaLedger()
        u = ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5)
        entry = ledger.record_compute(u)
        assert ledger.entry_count == 1
        assert entry.entry_type == "compute"
        assert ledger.total_compute_co2e() == 0.5

    def test_record_offset(self):
        ledger = GaiaLedger()
        u = OffsetUnit(project_id="p1", co2e_tons=10.0)
        ledger.record_offset(u)
        assert ledger.entry_count == 1

    def test_record_funding(self):
        ledger = GaiaLedger()
        u = FundingUnit(amount_usd=5000.0, source="donor", destination="project")
        ledger.record_funding(u)
        assert ledger.total_funding_usd() == 5000.0

    def test_record_labor(self):
        ledger = GaiaLedger()
        u = LaborUnit(worker_id="w1", project_id="p1", hours=8.0)
        ledger.record_labor(u)
        assert ledger.total_labor_hours() == 8.0
        assert ledger.worker_count() == 1

    def test_multiple_workers(self):
        ledger = GaiaLedger()
        ledger.record_labor(LaborUnit(worker_id="w1", project_id="p1", hours=4.0))
        ledger.record_labor(LaborUnit(worker_id="w2", project_id="p1", hours=6.0))
        assert ledger.worker_count() == 2
        assert ledger.total_labor_hours() == 10.0

    def test_chain_integrity_valid(self):
        ledger = GaiaLedger()
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5)
        )
        ledger.record_compute(
            ComputeUnit(provider="gcp", energy_mwh=2.0, carbon_intensity=0.3)
        )
        assert ledger.verify_chain_integrity() is True

    def test_chain_integrity_empty(self):
        assert GaiaLedger().verify_chain_integrity() is True

    def test_net_carbon_position(self):
        ledger = GaiaLedger()
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=10.0, carbon_intensity=0.5)
        )
        # 5.0 tons emitted, no offsets verified
        assert ledger.net_carbon_position() == 5.0

    def test_verification_3_of_5_threshold(self):
        ledger = GaiaLedger()
        offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=10.0)
        ledger.record_offset(offset)

        # Add 3 verifications from different oracle types
        for oracle in ["satellite", "iot_sensor", "human_auditor"]:
            v = VerificationUnit(
                oracle_type=oracle,
                target_id="off1",
                target_type=UnitType.OFFSET,
                confidence=0.8,
            )
            ledger.record_verification(v)

        # After 3 distinct oracle types, offset should be verified
        stored_offset = ledger._offset_units["off1"]
        assert stored_offset.is_verified is True
        assert abs(stored_offset.confidence - 0.8) < 0.01

    def test_verification_2_oracles_not_enough(self):
        ledger = GaiaLedger()
        offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=10.0)
        ledger.record_offset(offset)

        for oracle in ["satellite", "iot_sensor"]:
            v = VerificationUnit(
                oracle_type=oracle,
                target_id="off1",
                target_type=UnitType.OFFSET,
                confidence=0.9,
            )
            ledger.record_verification(v)

        assert ledger._offset_units["off1"].is_verified is False

    def test_record_morphism_returns_violations(self):
        ledger = GaiaLedger()
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="s1",
            target_id="t1",
            source_type=UnitType.FUNDING,  # wrong
            target_type=UnitType.OFFSET,
        )
        entry, violations = ledger.record_morphism(m)
        assert entry.entry_type == "morphism"
        assert any(v.law == "compositional_integrity" for v in violations)

    def test_record_morphism_valid(self):
        ledger = GaiaLedger()
        m = Morphism(
            morphism_type=MorphismType.OFFSET_MATCH,
            source_id="s1",
            target_id="t1",
            source_type=UnitType.COMPUTE,
            target_type=UnitType.OFFSET,
        )
        entry, violations = ledger.record_morphism(m)
        # No compositional integrity violation
        assert not any(v.law == "compositional_integrity" for v in violations)

    def test_conservation_check(self):
        ledger = GaiaLedger()
        # No data = no violations
        assert ledger.conservation_check() == []

    def test_summary(self):
        ledger = GaiaLedger()
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5)
        )
        s = ledger.summary()
        assert s["entries"] == 1
        assert s["chain_valid"] is True
        assert s["compute_units"] == 1
        assert s["total_compute_co2e"] == 0.5


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestGaiaLedgerPersistence:
    def test_save_and_load(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path)
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5)
        )
        ledger.record_funding(
            FundingUnit(amount_usd=1000.0, source="donor", destination="project")
        )
        path = ledger.save()
        assert path.exists()

        ledger2 = GaiaLedger(data_dir=tmp_path)
        count = ledger2.load()
        assert count == 2
        assert ledger2.entry_count == 2

    def test_load_nonexistent(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path)
        assert ledger.load() == 0

    def test_load_rebuilds_units(self, tmp_path):
        ledger = GaiaLedger(data_dir=tmp_path)
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=2.0, carbon_intensity=0.3)
        )
        ledger.record_labor(
            LaborUnit(worker_id="w1", project_id="p1", hours=8.0)
        )
        ledger.save()

        ledger2 = GaiaLedger(data_dir=tmp_path)
        ledger2.load()
        assert ledger2.total_compute_co2e() == pytest.approx(0.6, abs=0.001)
        assert ledger2.total_labor_hours() == 8.0


# ---------------------------------------------------------------------------
# GaiaObserver
# ---------------------------------------------------------------------------


class TestGaiaObserver:
    def test_observe_empty(self):
        ledger = GaiaLedger()
        observer = GaiaObserver()
        obs = observer.observe(ledger)
        assert obs["chain_valid"] is True
        assert obs["conservation_violations"] == 0
        assert obs["verification_coverage"] == 0.0

    def test_observe_with_data(self):
        ledger = GaiaLedger()
        ledger.record_compute(
            ComputeUnit(provider="aws", energy_mwh=1.0, carbon_intensity=0.5)
        )
        offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=5.0)
        ledger.record_offset(offset)

        observer = GaiaObserver()
        obs = observer.observe(ledger)
        assert "self_referential_fitness" in obs
        assert 0.0 <= obs["self_referential_fitness"] <= 1.0

    def test_goodhart_drifting_false(self):
        ledger = GaiaLedger()
        observer = GaiaObserver()
        assert observer.is_goodhart_drifting(ledger) is False

    def test_goodhart_drifting_true(self):
        ledger = GaiaLedger()
        # Large claimed offset, no verification
        offset = OffsetUnit(project_id="p1", co2e_tons=100.0)
        ledger.record_offset(offset)
        observer = GaiaObserver()
        assert observer.is_goodhart_drifting(ledger) is True

    def test_oracle_diversity(self):
        ledger = GaiaLedger()
        offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=10.0)
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

        observer = GaiaObserver()
        obs = observer.observe(ledger)
        assert obs["oracle_diversity"] == 3 / 5  # 3 of 5 oracle types
        assert obs["verification_coverage"] == 1.0  # 1 of 1 offsets verified
