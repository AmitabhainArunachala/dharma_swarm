from __future__ import annotations

import pytest

from dharma_swarm.cohomology_cechcohomology_to_sheaf_coord import (
    LocalClaimAssessment,
    build_complete_overlap_site,
    to_sheaf_coordination,
)
from dharma_swarm.gaia_ledger import GaiaLedger
from dharma_swarm.gaia_verification import OracleVerdict, VerificationOracle


def _assessment(
    source_id: str,
    *,
    target_id: str = "offset-1",
    agrees_with_claim: bool = True,
    confidence: float = 0.8,
) -> LocalClaimAssessment:
    return LocalClaimAssessment(
        source_id=source_id,
        target_id=target_id,
        claim_name="valid",
        agrees_with_claim=agrees_with_claim,
        confidence=confidence,
        evidence_refs=[f"hash:{source_id}"],
        evidence_summary=f"{source_id} assessed the offset",
    )


def test_build_complete_overlap_site_creates_pairwise_channels() -> None:
    site = build_complete_overlap_site(
        [
            _assessment("satellite"),
            _assessment("iot_sensor"),
            _assessment("human_auditor"),
        ]
    )

    assert site.has_overlap("satellite", "iot_sensor") is True
    assert site.has_overlap("satellite", "human_auditor") is True
    assert site.has_overlap("iot_sensor", "human_auditor") is True
    assert len(site.channels) == 3


def test_to_sheaf_coordination_glues_agreement_despite_confidence_differences() -> None:
    result = to_sheaf_coordination(
        [
            _assessment("satellite", confidence=0.91),
            _assessment("iot_sensor", confidence=0.77),
            _assessment("human_auditor", confidence=0.84),
        ]
    )

    assert result is not None
    assert result.is_globally_coherent is True
    assert result.productive_disagreements == []
    assert len(result.global_truths) == 1
    assert result.global_truths[0].content == "valid:true"
    assert result.global_truths[0].confidence == pytest.approx(
        (0.91 + 0.77 + 0.84) / 3
    )


def test_to_sheaf_coordination_surfaces_h1_for_conflicting_verdicts() -> None:
    result = to_sheaf_coordination(
        [
            _assessment("satellite", agrees_with_claim=True),
            _assessment("iot_sensor", agrees_with_claim=False),
            _assessment("human_auditor", agrees_with_claim=True),
        ]
    )

    assert result is not None
    assert result.is_globally_coherent is False
    assert result.global_truths == []
    assert len(result.productive_disagreements) == 1
    assert result.productive_disagreements[0].claim_key == "target_offset_1_valid"


def test_to_sheaf_coordination_returns_none_for_empty_input() -> None:
    assert to_sheaf_coordination([]) is None


def test_gaia_verification_oracle_delegates_to_bridge(tmp_path) -> None:
    ledger = GaiaLedger(data_dir=tmp_path / "ledger")
    oracle = VerificationOracle(ledger)
    session = oracle.start_session("off-1")
    oracle.submit_verdict(
        session.id,
        OracleVerdict(
            oracle_type="satellite",
            target_id="off-1",
            confidence=0.91,
            agrees_with_claim=True,
            evidence_hash="sat-hash",
        ),
    )
    oracle.submit_verdict(
        session.id,
        OracleVerdict(
            oracle_type="iot_sensor",
            target_id="off-1",
            confidence=0.76,
            agrees_with_claim=True,
            evidence_hash="iot-hash",
        ),
    )
    oracle.submit_verdict(
        session.id,
        OracleVerdict(
            oracle_type="human_auditor",
            target_id="off-1",
            confidence=0.88,
            agrees_with_claim=True,
            evidence_hash="human-hash",
        ),
    )

    result = oracle.to_sheaf_coordination(session.id)

    assert result is not None
    assert result.is_globally_coherent is True
    assert len(result.global_truths) == 1
    assert result.global_truths[0].content == "valid:true"
