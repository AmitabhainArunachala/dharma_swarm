from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from dharma_swarm.ai_reciprocity_ledger import (
    AIActor,
    AIReciprocityLedger,
    ActivityRecord,
    ActorType,
    AuditRecord,
    AuditScope,
    AuditStatus,
    ConfidenceLevel,
    DisclosureLevel,
    EvidenceRecord,
    EvidenceSubjectType,
    EvidenceType,
    ExposureClass,
    IntegrityClass,
    LivelihoodMode,
    LivelihoodRecord,
    ObligationBasis,
    ObligationRecord,
    ObligationStatus,
    ObligationType,
    OutcomeRecord,
    OutcomeStatus,
    OutcomeType,
    ProjectRecord,
    ProjectType,
    QuantityUnit,
    RoutingRecord,
)


def _make_actor() -> AIActor:
    return AIActor(
        actor_name="Anthropic",
        actor_type=ActorType.LAB,
        jurisdiction="US",
        disclosure_level=DisclosureLevel.PARTIAL,
    )


def _make_activity(actor_id: str) -> ActivityRecord:
    return ActivityRecord(
        actor_id=actor_id,
        workload_label="claude-inference-west",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 7),
        exposure_class=ExposureClass.INFERENCE,
        energy_mwh=12.5,
        emissions_tco2e=4.25,
        methodology_ref="metering-v0",
    )


def _make_project(integrity_class: IntegrityClass = IntegrityClass.HIGH_INTEGRITY) -> ProjectRecord:
    return ProjectRecord(
        project_name="Louisiana Mangrove Worker Cooperative",
        project_type=ProjectType.MIXED,
        location="Louisiana, US",
        operator_name="Delta Restoration Coop",
        integrity_class=integrity_class,
        methodology_ref="mrv-v1",
    )


def test_recording_and_summary_counts(tmp_path):
    ledger = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    actor = _make_actor()
    activity = _make_activity(actor.actor_id)
    project = _make_project()
    obligation = ObligationRecord(
        activity_id=activity.activity_id,
        obligation_type=ObligationType.MIXED,
        obligation_basis=ObligationBasis.PILOT_RULE,
        obligation_quantity=25000,
        obligation_unit=QuantityUnit.USD,
        status=ObligationStatus.ACTIVE,
    )
    routing = RoutingRecord(
        obligation_id=obligation.obligation_id,
        project_id=project.project_id,
        routed_value=5000,
        routed_unit=QuantityUnit.USD,
    )

    ledger.record_actor(actor)
    ledger.record_activity(activity)
    ledger.record_project(project)
    ledger.record_obligation(obligation)
    ledger.record_routing(routing)

    summary = ledger.summary()
    assert summary["entries"] == 5
    assert summary["actors"] == 1
    assert summary["activities"] == 1
    assert summary["projects"] == 1
    assert summary["obligations"] == 1
    assert summary["routings"] == 1
    assert summary["total_obligation_usd"] == 25000
    assert summary["total_routed_usd"] == 5000
    assert summary["chain_valid"] is True


def test_routing_missing_project_is_flagged(tmp_path):
    ledger = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    actor = _make_actor()
    activity = _make_activity(actor.actor_id)
    obligation = ObligationRecord(
        activity_id=activity.activity_id,
        obligation_type=ObligationType.ECOLOGY,
        obligation_basis=ObligationBasis.FORMULA,
        obligation_quantity=1000,
        obligation_unit=QuantityUnit.USD,
    )
    routing = RoutingRecord(
        obligation_id=obligation.obligation_id,
        project_id="missing-project",
        routed_value=1000,
        routed_unit=QuantityUnit.USD,
    )

    ledger.record_actor(actor)
    ledger.record_activity(activity)
    ledger.record_obligation(obligation)
    ledger.record_routing(routing)

    codes = {issue.code for issue in ledger.invariant_issues()}
    assert "routing_missing_project" in codes


def test_verified_ecological_claim_requires_evidence_and_audit(tmp_path):
    ledger = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    project = _make_project()
    outcome = OutcomeRecord(
        project_id=project.project_id,
        outcome_type=OutcomeType.CARBON,
        quantity=42.0,
        unit="tco2e",
        status=OutcomeStatus.VERIFIED,
    )

    ledger.record_project(project)
    ledger.record_outcome(outcome)

    codes = {issue.code for issue in ledger.invariant_issues()}
    assert "verified_ecology_missing_evidence" in codes
    assert "verified_ecology_missing_audit" in codes


def test_projection_to_gaia_ledger_builds_compute_funding_and_verified_offset(tmp_path):
    ledger = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    actor = _make_actor()
    activity = _make_activity(actor.actor_id)
    project = _make_project()
    obligation = ObligationRecord(
        activity_id=activity.activity_id,
        obligation_type=ObligationType.MIXED,
        obligation_basis=ObligationBasis.PILOT_RULE,
        obligation_quantity=10000,
        obligation_unit=QuantityUnit.USD,
        status=ObligationStatus.ACTIVE,
    )
    routing = RoutingRecord(
        obligation_id=obligation.obligation_id,
        project_id=project.project_id,
        routed_value=6000,
        routed_unit=QuantityUnit.USD,
    )
    livelihood = LivelihoodRecord(
        project_id=project.project_id,
        participant_count=12,
        livelihood_mode=LivelihoodMode.COOPERATIVE,
        transition_target_group="displaced coastal workers",
        person_hours=320.0,
        median_compensation_local=28.0,
    )
    outcome = OutcomeRecord(
        project_id=project.project_id,
        outcome_type=OutcomeType.CARBON,
        quantity=18.0,
        unit="tco2e",
        status=OutcomeStatus.VERIFIED,
    )
    satellite = EvidenceRecord(
        subject_type=EvidenceSubjectType.OUTCOME,
        subject_id=outcome.outcome_id,
        evidence_type=EvidenceType.SATELLITE,
        source_ref="sentinel-batch-1",
        confidence=ConfidenceLevel.HIGH,
    )
    sensor = EvidenceRecord(
        subject_type=EvidenceSubjectType.OUTCOME,
        subject_id=outcome.outcome_id,
        evidence_type=EvidenceType.SENSOR,
        source_ref="sensor-mesh-7",
        confidence=ConfidenceLevel.MEDIUM,
    )
    audit = AuditRecord(
        scope=AuditScope.OUTCOME,
        scope_id=outcome.outcome_id,
        audit_status=AuditStatus.PASSED,
        auditor="Indie Audit Lab",
    )

    ledger.record_actor(actor)
    ledger.record_activity(activity)
    ledger.record_project(project)
    ledger.record_obligation(obligation)
    ledger.record_routing(routing)
    ledger.record_livelihood(livelihood)
    ledger.record_outcome(outcome)
    ledger.record_evidence(satellite)
    ledger.record_evidence(sensor)
    ledger.record_audit(audit)

    gaia, warnings = ledger.to_gaia_ledger(data_dir=tmp_path / "gaia")

    assert warnings == []
    assert gaia.summary()["compute_units"] == 1
    assert gaia.summary()["funding_units"] == 1
    assert gaia.summary()["labor_units"] == 1
    assert gaia.summary()["offset_units"] == 1
    assert gaia.summary()["verification_units"] == 3
    assert gaia.total_verified_offset() > 0.0


def test_save_and_load_round_trip(tmp_path):
    ledger = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    actor = _make_actor()
    ledger.record_actor(actor)
    path = ledger.save()

    restored = AIReciprocityLedger(data_dir=tmp_path / "reciprocity")
    count = restored.load()

    assert path.exists()
    assert count == 1
    assert restored.summary()["actors"] == 1


def test_validation_rejects_invalid_ownership_share():
    with pytest.raises(ValidationError):
        LivelihoodRecord(
            project_id="proj-1",
            participant_count=3,
            livelihood_mode=LivelihoodMode.TRAINING,
            transition_target_group="clerical workers",
            local_ownership_share=1.5,
        )
