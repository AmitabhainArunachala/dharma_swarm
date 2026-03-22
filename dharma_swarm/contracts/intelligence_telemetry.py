"""Opt-in projections from sovereign evaluation receipts into telemetry records."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

from dharma_swarm.telemetry_plane import (
    ExternalOutcomeRecord,
    TelemetryPlaneStore,
    WorkflowScoreRecord,
)

from .intelligence_evaluation_services import SovereignEvaluationRegistrationResult


@dataclass(frozen=True, slots=True)
class SovereignEvaluationTelemetryExportResult:
    """Telemetry records materialized from one sovereign evaluation receipt."""

    workflow_score: WorkflowScoreRecord
    external_outcome: ExternalOutcomeRecord


def evaluation_registration_to_telemetry_records(
    result: SovereignEvaluationRegistrationResult,
    *,
    workflow_id: str | None = None,
    outcome_kind: str | None = None,
) -> SovereignEvaluationTelemetryExportResult:
    """Project one evaluation registration into canonical telemetry records."""

    evaluation = result.evaluation
    if evaluation is None:
        raise ValueError("evaluation registration result is missing evaluation data")

    resolved_workflow_id = workflow_id or _default_workflow_id(evaluation)
    resolved_outcome_kind = outcome_kind or f"evaluation:{evaluation.metric}"
    fact_ids = [
        str(getattr(fact, "fact_id", "") or "")
        for fact in result.facts
        if getattr(fact, "fact_id", None)
    ]
    evidence = [
        {
            "kind": "sovereign_evaluation",
            "evaluation_id": evaluation.evaluation_id,
            "artifact_id": result.artifact.artifact_id,
            "receipt_event_id": str((result.receipt or {}).get("event_id", "")),
            "fact_ids": fact_ids,
        }
    ]
    shared_metadata = {
        "evaluation_id": evaluation.evaluation_id,
        "subject_kind": evaluation.subject_kind,
        "subject_id": evaluation.subject_id,
        "metric": evaluation.metric,
        "artifact_id": result.artifact.artifact_id,
        "fact_ids": fact_ids,
        "manifest_path": str(result.manifest_path),
        "summary": dict(result.summary),
        "source": "contracts.intelligence.telemetry",
    }
    workflow_score = WorkflowScoreRecord(
        score_id=f"score_{evaluation.evaluation_id}",
        workflow_id=resolved_workflow_id,
        score_name=evaluation.metric,
        score_value=float(evaluation.score),
        session_id=evaluation.session_id,
        task_id=evaluation.task_id,
        run_id=evaluation.run_id,
        evidence=evidence,
        metadata={
            **shared_metadata,
            "evaluator": evaluation.evaluator,
        },
    )
    external_outcome = ExternalOutcomeRecord(
        outcome_id=f"outcome_{evaluation.evaluation_id}",
        outcome_kind=resolved_outcome_kind,
        value=float(evaluation.score),
        unit="score",
        confidence=1.0,
        status="measured",
        subject_id=evaluation.subject_id,
        summary=_outcome_summary(evaluation),
        session_id=evaluation.session_id,
        task_id=evaluation.task_id,
        run_id=evaluation.run_id,
        metadata={
            **shared_metadata,
            "evaluator": evaluation.evaluator,
        },
    )
    return SovereignEvaluationTelemetryExportResult(
        workflow_score=workflow_score,
        external_outcome=external_outcome,
    )


async def export_evaluation_registration_to_telemetry(
    result: SovereignEvaluationRegistrationResult,
    *,
    telemetry: TelemetryPlaneStore | None = None,
    workflow_id: str | None = None,
    outcome_kind: str | None = None,
) -> SovereignEvaluationTelemetryExportResult:
    """Persist one evaluation registration into the canonical telemetry plane."""

    records = evaluation_registration_to_telemetry_records(
        result,
        workflow_id=workflow_id,
        outcome_kind=outcome_kind,
    )
    store = telemetry or TelemetryPlaneStore()
    try:
        workflow_score = await store.record_workflow_score(records.workflow_score)
    except (sqlite3.IntegrityError, Exception) as exc:
        if "UNIQUE" in str(exc) or "IntegrityError" in type(exc).__name__:
            logger.debug("Workflow score %s already exists (idempotent skip)", records.workflow_score.score_id)
            workflow_score = records.workflow_score
        else:
            raise
    try:
        external_outcome = await store.record_external_outcome(records.external_outcome)
    except (sqlite3.IntegrityError, Exception) as exc:
        if "UNIQUE" in str(exc) or "IntegrityError" in type(exc).__name__:
            logger.debug("External outcome %s already exists (idempotent skip)", records.external_outcome.outcome_id)
            external_outcome = records.external_outcome
        else:
            raise
    return SovereignEvaluationTelemetryExportResult(
        workflow_score=workflow_score,
        external_outcome=external_outcome,
    )


def _default_workflow_id(evaluation: Any) -> str:
    if str(getattr(evaluation, "task_id", "") or "").strip():
        return f"task:{str(evaluation.task_id).strip()}"
    if str(getattr(evaluation, "run_id", "") or "").strip():
        return f"run:{str(evaluation.run_id).strip()}"
    subject_kind = str(getattr(evaluation, "subject_kind", "") or "").strip()
    subject_id = str(getattr(evaluation, "subject_id", "") or "").strip()
    if subject_kind and subject_id:
        return f"{subject_kind}:{subject_id}"
    return str(getattr(evaluation, "evaluation_id", "") or "evaluation:unknown")


def _outcome_summary(evaluation: Any) -> str:
    return (
        f"Evaluation {evaluation.metric} for {evaluation.subject_kind} "
        f"{evaluation.subject_id} scored {float(evaluation.score):.3f}."
    )


__all__ = [
    "SovereignEvaluationTelemetryExportResult",
    "evaluation_registration_to_telemetry_records",
    "export_evaluation_registration_to_telemetry",
]
