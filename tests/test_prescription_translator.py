import pytest

from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.postmortem_reader import PostmortemDiagnosis
from dharma_swarm.prescription_translator import (
    PrescriptionTranslationError,
    PrescriptionTranslator,
)
from dharma_swarm.semantic_governance import ClaimScore


def test_translate_produces_bounded_prescription():
    diagnosis = PostmortemDiagnosis(
        finding_id="finding-1",
        failure_mode="routing_conflict",
        summary="routing conflict affecting orchestrator",
        candidate_surfaces=["orchestrator"],
        recommended_surface="orchestrator",
        relevant_claims=[
            ClaimScore(
                claim_id="DC-2026-0001",
                statement="routing conflicts require explicit reroute guard",
                score=0.8,
                confidence=0.9,
                enforcement="warn",
                matched=True,
            )
        ],
    )
    prescription = PrescriptionTranslator().translate(diagnosis)
    assert prescription.target_surface == "orchestrator"
    assert prescription.prescription_type == "patch_routing_rule"
    assert "bounded" in prescription.bounded_change.lower()


def test_translate_requires_target_surface():
    diagnosis = PostmortemDiagnosis(
        finding_id="finding-1",
        failure_mode="unknown_failure_mode",
        summary="unknown issue",
    )
    with pytest.raises(PrescriptionTranslationError):
        PrescriptionTranslator().translate(diagnosis)


def test_high_risk_or_contradiction_requires_human_review():
    diagnosis = PostmortemDiagnosis(
        finding_id="finding-1",
        failure_mode="policy_mismatch",
        summary="policy issue",
        candidate_surfaces=["policy_compiler"],
        recommended_surface="policy_compiler",
        contradictions=[
            Contradiction(
                contradiction_id="ctr-1",
                claim_ids=["DC-2026-0001", "DC-2026-0002"],
                reason="declared",
            )
        ],
    )
    prescription = PrescriptionTranslator().translate(diagnosis)
    assert prescription.human_review_required is True
