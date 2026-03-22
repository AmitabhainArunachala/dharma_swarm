"""Tests for gaia_verification.py — 3-of-5 oracle verification protocol."""

from __future__ import annotations

import pytest

from dharma_swarm.gaia_ledger import GaiaLedger, OffsetUnit, UnitType
from dharma_swarm.gaia_verification import (
    ORACLE_TYPES,
    VERIFICATION_THRESHOLD,
    OracleVerdict,
    VerificationOracle,
    VerificationSession,
    verify_offset,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_oracle_types(self):
        assert len(ORACLE_TYPES) == 5
        assert "satellite" in ORACLE_TYPES
        assert "human_auditor" in ORACLE_TYPES
        assert "community" in ORACLE_TYPES

    def test_threshold(self):
        assert VERIFICATION_THRESHOLD == 3


# ---------------------------------------------------------------------------
# OracleVerdict
# ---------------------------------------------------------------------------


class TestOracleVerdict:
    def test_construction(self):
        v = OracleVerdict(oracle_type="satellite", target_id="off1")
        assert v.oracle_type == "satellite"
        assert v.target_id == "off1"
        assert v.confidence == 0.0
        assert v.agrees_with_claim is True
        assert v.metadata == {}

    def test_full_construction(self):
        v = OracleVerdict(
            oracle_type="iot_sensor",
            target_id="off1",
            confidence=0.95,
            evidence_summary="NDVI measurement confirms reforestation",
            evidence_hash="abc123",
            agrees_with_claim=True,
            metadata={"sensor_id": "S42"},
        )
        assert v.confidence == 0.95
        assert v.evidence_hash == "abc123"
        assert v.metadata["sensor_id"] == "S42"

    def test_dissenting_verdict(self):
        v = OracleVerdict(
            oracle_type="statistical_model",
            target_id="off1",
            confidence=0.3,
            agrees_with_claim=False,
        )
        assert v.agrees_with_claim is False


# ---------------------------------------------------------------------------
# VerificationSession
# ---------------------------------------------------------------------------


class TestVerificationSession:
    def test_construction(self):
        s = VerificationSession(offset_id="off1")
        assert s.offset_id == "off1"
        assert s.verdicts == []
        assert s.threshold == 3
        assert s.is_complete is False
        assert s.oracle_count == 0
        assert s.agreement_count == 0
        assert s.meets_threshold is False

    def test_oracle_count(self):
        s = VerificationSession(offset_id="off1")
        s.verdicts.append(OracleVerdict(oracle_type="satellite", target_id="off1"))
        s.verdicts.append(OracleVerdict(oracle_type="iot_sensor", target_id="off1"))
        assert s.oracle_count == 2

    def test_agreement_count(self):
        s = VerificationSession(offset_id="off1")
        s.verdicts.append(
            OracleVerdict(oracle_type="satellite", target_id="off1", agrees_with_claim=True)
        )
        s.verdicts.append(
            OracleVerdict(oracle_type="iot_sensor", target_id="off1", agrees_with_claim=False)
        )
        assert s.agreement_count == 1

    def test_meets_threshold_false(self):
        s = VerificationSession(offset_id="off1")
        s.verdicts.append(
            OracleVerdict(oracle_type="satellite", target_id="off1", agrees_with_claim=True)
        )
        assert s.meets_threshold is False

    def test_meets_threshold_true(self):
        s = VerificationSession(offset_id="off1")
        for otype in ["satellite", "iot_sensor", "human_auditor"]:
            s.verdicts.append(
                OracleVerdict(oracle_type=otype, target_id="off1", agrees_with_claim=True)
            )
        assert s.meets_threshold is True

    def test_finalize_agreeing(self):
        s = VerificationSession(offset_id="off1")
        for otype in ["satellite", "iot_sensor", "human_auditor"]:
            s.verdicts.append(
                OracleVerdict(
                    oracle_type=otype, target_id="off1",
                    confidence=0.9, agrees_with_claim=True,
                )
            )
        s.verdicts.append(
            OracleVerdict(
                oracle_type="community", target_id="off1",
                confidence=0.4, agrees_with_claim=False,
            )
        )
        s.finalize()
        assert s.is_complete is True
        assert s.agreeing_oracles == ["satellite", "iot_sensor", "human_auditor"]
        assert s.dissenting_oracles == ["community"]
        assert s.final_confidence == pytest.approx(0.9)

    def test_finalize_no_agreement(self):
        s = VerificationSession(offset_id="off1")
        s.verdicts.append(
            OracleVerdict(
                oracle_type="satellite", target_id="off1",
                confidence=0.3, agrees_with_claim=False,
            )
        )
        s.finalize()
        assert s.is_complete is True
        assert s.agreeing_oracles == []
        assert s.final_confidence == 0.0

    def test_custom_threshold(self):
        s = VerificationSession(offset_id="off1", threshold=2)
        for otype in ["satellite", "iot_sensor"]:
            s.verdicts.append(
                OracleVerdict(oracle_type=otype, target_id="off1", agrees_with_claim=True)
            )
        assert s.meets_threshold is True


# ---------------------------------------------------------------------------
# VerificationOracle
# ---------------------------------------------------------------------------


def _make_ledger_with_offset():
    ledger = GaiaLedger()
    offset = OffsetUnit(id="off1", project_id="p1", co2e_tons=10.0)
    ledger.record_offset(offset)
    return ledger


class TestVerificationOracle:
    def test_start_session(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        assert session.offset_id == "off1"
        assert session.is_complete is False

    def test_submit_verdict(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        verdict = OracleVerdict(
            oracle_type="satellite", target_id="off1", confidence=0.85,
        )
        updated = oracle.submit_verdict(session.id, verdict)
        assert updated.oracle_count == 1

    def test_duplicate_oracle_type_rejected(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        v1 = OracleVerdict(oracle_type="satellite", target_id="off1", confidence=0.8)
        oracle.submit_verdict(session.id, v1)
        v2 = OracleVerdict(oracle_type="satellite", target_id="off1", confidence=0.9)
        with pytest.raises(ValueError, match="already submitted"):
            oracle.submit_verdict(session.id, v2)

    def test_submit_after_finalize_rejected(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        oracle.finalize_session(session.id)
        v = OracleVerdict(oracle_type="satellite", target_id="off1")
        with pytest.raises(ValueError, match="already finalized"):
            oracle.submit_verdict(session.id, v)

    def test_finalize_records_to_ledger(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        for otype in ["satellite", "iot_sensor", "human_auditor"]:
            oracle.submit_verdict(
                session.id,
                OracleVerdict(
                    oracle_type=otype, target_id="off1",
                    confidence=0.85, agrees_with_claim=True,
                ),
            )
        result = oracle.finalize_session(session.id)
        assert result.meets_threshold is True
        # Ledger should have 3 verification units recorded
        assert len(ledger._verification_units) == 3

    def test_finalize_below_threshold_no_ledger_record(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        # Only 1 agreeing, 2 dissenting
        oracle.submit_verdict(
            session.id,
            OracleVerdict(
                oracle_type="satellite", target_id="off1",
                confidence=0.8, agrees_with_claim=True,
            ),
        )
        oracle.submit_verdict(
            session.id,
            OracleVerdict(
                oracle_type="iot_sensor", target_id="off1",
                confidence=0.3, agrees_with_claim=False,
            ),
        )
        oracle.submit_verdict(
            session.id,
            OracleVerdict(
                oracle_type="community", target_id="off1",
                confidence=0.2, agrees_with_claim=False,
            ),
        )
        result = oracle.finalize_session(session.id)
        assert result.meets_threshold is False
        # Ledger should NOT have verification units
        assert len(ledger._verification_units) == 0

    def test_get_session(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        retrieved = oracle.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    def test_get_session_missing(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        assert oracle.get_session("nonexistent") is None

    def test_sheaf_coordination(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        for otype in ["satellite", "iot_sensor", "human_auditor"]:
            oracle.submit_verdict(
                session.id,
                OracleVerdict(
                    oracle_type=otype, target_id="off1",
                    confidence=0.9, agrees_with_claim=True,
                    evidence_summary=f"{otype} confirms reforestation",
                ),
            )
        coordination = oracle.to_sheaf_coordination(session.id)
        assert coordination is not None

    def test_sheaf_coordination_empty_session(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        session = oracle.start_session("off1")
        coordination = oracle.to_sheaf_coordination(session.id)
        assert coordination is None

    def test_sheaf_coordination_missing_session(self):
        ledger = _make_ledger_with_offset()
        oracle = VerificationOracle(ledger)
        assert oracle.to_sheaf_coordination("nonexistent") is None


# ---------------------------------------------------------------------------
# verify_offset convenience function
# ---------------------------------------------------------------------------


class TestVerifyOffset:
    def test_full_pipeline(self):
        ledger = _make_ledger_with_offset()
        verdicts = [
            OracleVerdict(
                oracle_type=otype, target_id="off1",
                confidence=0.85, agrees_with_claim=True,
            )
            for otype in ["satellite", "iot_sensor", "human_auditor"]
        ]
        session, coordination = verify_offset(ledger, "off1", verdicts)
        assert session.is_complete is True
        assert session.meets_threshold is True
        assert coordination is not None

    def test_below_threshold(self):
        ledger = _make_ledger_with_offset()
        verdicts = [
            OracleVerdict(
                oracle_type="satellite", target_id="off1",
                confidence=0.8, agrees_with_claim=True,
            ),
            OracleVerdict(
                oracle_type="iot_sensor", target_id="off1",
                confidence=0.3, agrees_with_claim=False,
            ),
        ]
        session, coordination = verify_offset(ledger, "off1", verdicts)
        assert session.is_complete is True
        assert session.meets_threshold is False

    def test_all_five_oracles(self):
        ledger = _make_ledger_with_offset()
        verdicts = [
            OracleVerdict(
                oracle_type=otype, target_id="off1",
                confidence=0.8 + i * 0.03,
                agrees_with_claim=(i < 4),  # 4 agree, 1 dissents
            )
            for i, otype in enumerate(ORACLE_TYPES)
        ]
        session, coordination = verify_offset(ledger, "off1", verdicts)
        assert session.is_complete is True
        assert session.meets_threshold is True
        assert len(session.agreeing_oracles) == 4
        assert len(session.dissenting_oracles) == 1

    def test_returns_coordination_result(self):
        ledger = _make_ledger_with_offset()
        verdicts = [
            OracleVerdict(
                oracle_type=otype, target_id="off1",
                confidence=0.9, agrees_with_claim=True,
            )
            for otype in ORACLE_TYPES[:3]
        ]
        session, coordination = verify_offset(ledger, "off1", verdicts)
        assert coordination is not None
