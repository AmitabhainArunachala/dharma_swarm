"""Translate diagnoses into bounded prescriptions."""

from __future__ import annotations

from dharma_swarm.claim_graph import Prescription
from dharma_swarm.postmortem_reader import PostmortemDiagnosis


class PrescriptionTranslationError(ValueError):
    """Raised when a diagnosis cannot be translated into a bounded prescription."""


_HIGH_RISK_SURFACES = {
    "policy_compiler",
    "telos_gates",
    "orchestrator",
    "provider_policy",
    "dharma_kernel",
}


def _bounded_change_for(failure_mode: str, target_surface: str) -> tuple[str, str]:
    if target_surface == "policy_compiler":
        return (
            "patch_policy_rule",
            "Add or tighten one deterministic policy predicate or threshold tied to the cited diagnosis.",
        )
    if target_surface == "orchestrator":
        return (
            "patch_routing_rule",
            "Introduce one bounded routing guard or reroute condition tied to the failure signature.",
        )
    if target_surface == "telos_gates":
        return (
            "patch_gate_rule",
            "Add or refine one gate check with explicit provenance and review path.",
        )
    if target_surface == "orientation_packet":
        return (
            "patch_orientation",
            "Adjust one orientation packet field, selection rule, or freshness marker relevant to the stale-context failure.",
        )
    if target_surface == "claim_graph":
        return (
            "patch_claim_substrate",
            "Add one missing citation, contradiction, or claim-ingestion rule needed to prevent the observed failure.",
        )
    if target_surface == "runtime_bridge":
        return (
            "patch_bridge_contract",
            "Tighten one bridge envelope field or provenance requirement without widening runtime disclosure.",
        )
    if failure_mode == "unknown_failure_mode":
        return (
            "advisory_review",
            "Escalate to a human review packet because the diagnosis does not support an automatic bounded patch.",
        )
    return (
        "patch_runtime_behavior",
        "Apply one bounded behavioral guard tied to the diagnosed failure mode.",
    )


class PrescriptionTranslator:
    """Convert diagnoses into actionable, reviewable prescriptions."""

    def translate(
        self,
        diagnosis: PostmortemDiagnosis,
        *,
        preferred_surface: str | None = None,
    ) -> Prescription:
        target_surface = preferred_surface or diagnosis.recommended_surface
        if not target_surface:
            raise PrescriptionTranslationError("diagnosis has no target surface")

        prescription_type, bounded_change = _bounded_change_for(diagnosis.failure_mode, target_surface)
        if not bounded_change.strip():
            raise PrescriptionTranslationError("translator produced an empty bounded change")

        contradiction_ids = [contradiction.contradiction_id for contradiction in diagnosis.contradictions]
        supporting_claim_ids = [claim.claim_id for claim in diagnosis.relevant_claims if claim.matched]
        human_review_required = (
            target_surface in _HIGH_RISK_SURFACES
            or bool(contradiction_ids)
            or diagnosis.failure_mode in {"unsafe_action", "provenance_gap", "unknown_failure_mode"}
        )

        rollback_plan = (
            f"Revert the {target_surface} change and restore the previous governance snapshot if the prescription degrades behavior."
        )

        provenance = list(diagnosis.provenance)
        provenance.append(f"diagnosis:{diagnosis.diagnosis_id}")

        return Prescription(
            source_finding_id=diagnosis.finding_id,
            target_surface=target_surface,
            prescription_type=prescription_type,
            bounded_change=bounded_change,
            supporting_claim_ids=supporting_claim_ids,
            contradiction_ids=contradiction_ids,
            human_review_required=human_review_required,
            rollback_plan=rollback_plan,
            provenance=sorted(set(provenance)),
        )
