"""Tests for JK Credibility Gates."""

import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.jk_credibility_gates import (
    ArtifactAudit,
    EvidenceEntry,
    EvidenceRoom,
    GateID,
    GateResult,
    Verdict,
    audit_proof_artifact,
    check_citations_verifiable,
    check_limitations_stated,
    check_no_private_evidence,
    check_submission_claim,
    check_uncertainty_bounded,
    save_audit,
)


# ---------------------------------------------------------------------------
# Gate: no private evidence
# ---------------------------------------------------------------------------


class TestNoPrivateEvidence:
    def test_clean_text_passes(self):
        result = check_no_private_evidence("Carbon data from Verra registry VCS 2250.")
        assert result.verdict == Verdict.PASS

    def test_payment_records_warns(self):
        result = check_no_private_evidence("Source: Eden payment records (2023)")
        assert result.verdict == Verdict.WARN
        assert "payment records" in result.detail.lower()

    def test_salesforce_warns(self):
        result = check_no_private_evidence("Data uploaded to Eden Salesforce CRM within 48h")
        assert result.verdict == Verdict.WARN

    def test_whatsapp_warns(self):
        result = check_no_private_evidence("photographed to shared WhatsApp group")
        assert result.verdict == Verdict.WARN

    def test_payroll_audit_warns(self):
        result = check_no_private_evidence("per payroll audit. 95% local workers.")
        assert result.verdict == Verdict.WARN

    def test_multiple_private_sources(self):
        text = "Eden payment records show... per payroll audit... WhatsApp group"
        result = check_no_private_evidence(text)
        assert result.verdict == Verdict.WARN
        # Should report multiple hits
        assert "3" in result.detail or len(result.detail) > 30


# ---------------------------------------------------------------------------
# Gate: citations verifiable
# ---------------------------------------------------------------------------


class TestCitationsVerifiable:
    def test_clean_text_passes(self):
        result = check_citations_verifiable("Source: https://verra.org/project/2250")
        assert result.verdict == Verdict.PASS

    def test_unverified_marker_flags(self):
        result = check_citations_verifiable("This figure is UNVERIFIED from public sources.")
        assert result.verdict == Verdict.UNVERIFIED

    def test_unverifiable_marker_flags(self):
        result = check_citations_verifiable("The KFS data is unverifiable online.")
        assert result.verdict == Verdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Gate: limitations stated
# ---------------------------------------------------------------------------


class TestLimitationsStated:
    def test_with_limitations_passes(self):
        result = check_limitations_stated("## Assumptions and Limitations\n1. C uses annualised...")
        assert result.verdict == Verdict.PASS

    def test_without_limitations_fails(self):
        result = check_limitations_stated("W = 588.5 wt-CO2e/yr. Perfect score.")
        assert result.verdict == Verdict.FAIL


# ---------------------------------------------------------------------------
# Gate: uncertainty bounded
# ---------------------------------------------------------------------------


class TestUncertaintyBounded:
    def test_with_uncertainty_passes(self):
        result = check_uncertainty_bounded("Sensitivity analysis shows ±15% on C factor")
        assert result.verdict == Verdict.PASS

    def test_with_confidence_interval_passes(self):
        result = check_uncertainty_bounded("95% confidence interval: [520, 660] wt")
        assert result.verdict == Verdict.PASS

    def test_single_point_only_warns(self):
        result = check_uncertainty_bounded("C = 130.24 tCO2e/yr. E = 4.485.")
        assert result.verdict == Verdict.WARN


# ---------------------------------------------------------------------------
# Gate: submission claim
# ---------------------------------------------------------------------------


class TestSubmissionClaim:
    def test_no_claim_passes(self):
        audit = ArtifactAudit(
            artifact_path="test.md", artifact_hash="abc", audited_at="now"
        )
        result = check_submission_claim("Regular text without claims", audit)
        assert result.verdict == Verdict.PASS

    def test_valid_claim_passes(self):
        audit = ArtifactAudit(
            artifact_path="test.md", artifact_hash="abc", audited_at="now"
        )
        # All pass → submission_ready = True
        result = check_submission_claim("SUBMISSION READY", audit)
        assert result.verdict == Verdict.PASS

    def test_false_claim_fails(self):
        audit = ArtifactAudit(
            artifact_path="test.md", artifact_hash="abc", audited_at="now",
            results=[
                GateResult(
                    gate=GateID.CITATION_VERIFIABLE,
                    verdict=Verdict.UNVERIFIED,
                    detail="test",
                )
            ],
        )
        result = check_submission_claim("SUBMISSION READY: All checks passed.", audit)
        assert result.verdict == Verdict.FAIL


# ---------------------------------------------------------------------------
# Full proof audit
# ---------------------------------------------------------------------------


class TestAuditProofArtifact:
    def test_audit_eden_proof(self, tmp_path):
        proof = tmp_path / "proof.md"
        proof.write_text(
            "W = 588.5 wt-CO2e/yr\n"
            "Source: Eden payment records (2023)\n"
            "Source: per payroll audit\n"
            "This figure is UNVERIFIED from public sources.\n"
            "## Assumptions and Limitations\n"
            "1. C uses annualised rate\n"
            "SUBMISSION READY\n"
        )
        audit = audit_proof_artifact(proof)
        assert not audit.submission_ready  # has unverified citations
        assert len(audit.failures) >= 1  # false submission claim
        assert len(audit.warnings) >= 1  # private evidence

    def test_audit_nonexistent_file(self, tmp_path):
        audit = audit_proof_artifact(tmp_path / "nonexistent.md")
        # Should not crash, but should flag issues
        assert audit.artifact_hash == "FILE_NOT_FOUND"

    def test_audit_clean_proof(self, tmp_path):
        proof = tmp_path / "clean.md"
        proof.write_text(
            "W = 588.5 wt-CO2e/yr\n"
            "Source: https://verra.org/project/2250 (doi:10.1234/test)\n"
            "## Assumptions and Limitations\n"
            "1. Uncertainty bounds: ±15% on C factor\n"
            "Sensitivity analysis performed.\n"
        )
        audit = audit_proof_artifact(proof)
        assert audit.passed
        assert audit.submission_ready


# ---------------------------------------------------------------------------
# Evidence Room
# ---------------------------------------------------------------------------


class TestEvidenceRoom:
    def test_add_and_retrieve(self, tmp_path):
        room = EvidenceRoom(tmp_path / "evidence")
        entry = EvidenceEntry(
            citation_key="KFS_2023",
            claimed_fact="deforestation rate 3.8%/yr",
            source_url=None,
            source_type="unverifiable",
        )
        room.add(entry)
        retrieved = room.get("KFS_2023")
        assert retrieved is not None
        assert retrieved.claimed_fact == "deforestation rate 3.8%/yr"
        assert not retrieved.verified

    def test_unverified_filter(self, tmp_path):
        room = EvidenceRoom(tmp_path / "evidence")
        room.add(EvidenceEntry("A", "fact A", verified=True, source_type="public_url"))
        room.add(EvidenceEntry("B", "fact B", verified=False, source_type="private"))
        room.add(EvidenceEntry("C", "fact C", verified=False, source_type="unverifiable"))
        assert len(room.unverified()) == 2

    def test_stats(self, tmp_path):
        room = EvidenceRoom(tmp_path / "evidence")
        room.add(EvidenceEntry("A", "fact A", source_url="https://x.org", source_type="public_url", verified=True))
        room.add(EvidenceEntry("B", "fact B", source_type="private", verified=False))
        stats = room.stats()
        assert stats["total_citations"] == 2
        assert stats["verified"] == 1
        assert stats["public_sources"] == 1
        assert stats["verification_rate"] == 0.5

    def test_persistence(self, tmp_path):
        room_dir = tmp_path / "evidence"
        room1 = EvidenceRoom(room_dir)
        room1.add(EvidenceEntry("X", "fact X", source_type="public_report"))
        # New instance should load persisted data
        room2 = EvidenceRoom(room_dir)
        assert room2.get("X") is not None
        assert room2.get("X").claimed_fact == "fact X"


# ---------------------------------------------------------------------------
# Save audit
# ---------------------------------------------------------------------------


class TestSaveAudit:
    def test_save_and_load(self, tmp_path):
        audit = ArtifactAudit(
            artifact_path="test.md",
            artifact_hash="abc123",
            audited_at="2026-03-21T00:00:00Z",
            results=[
                GateResult(gate=GateID.LIMITATIONS_STATED, verdict=Verdict.PASS, detail="ok"),
            ],
        )
        out = save_audit(audit, tmp_path / "audits")
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 0
