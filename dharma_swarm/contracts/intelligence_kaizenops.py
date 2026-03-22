"""Minimal opt-in bridge from sovereign evaluation receipts to KaizenOps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dharma_swarm.integrations import KaizenOpsClient

from .intelligence_evaluation_services import SovereignEvaluationRegistrationResult


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluation_registration_to_kaizenops_event(
    result: SovereignEvaluationRegistrationResult,
) -> dict[str, Any]:
    """Project a sovereign evaluation receipt into one KaizenOps ingest event."""

    evaluation = result.evaluation
    if evaluation is None:
        raise ValueError("evaluation registration result is missing evaluation data")
    if not evaluation.session_id:
        raise ValueError("session_id is required to export evaluation registration")

    receipt = result.receipt if isinstance(result.receipt, dict) else {}
    summary = result.summary if isinstance(result.summary, dict) else {}
    fact_ids = [
        str(getattr(fact, "fact_id", "") or "")
        for fact in result.facts
        if getattr(fact, "fact_id", None)
    ]
    deliverables = [result.artifact.artifact_id, *fact_ids]

    trace_id = (
        (evaluation.run_id or "").strip()
        or str(receipt.get("trace_id", "")).strip()
        or str(summary.get("receipt_event_id", "")).strip()
        or evaluation.evaluation_id
    )
    task_id = evaluation.task_id.strip() or None

    return {
        "agent_id": evaluation.evaluator,
        "session_id": evaluation.session_id,
        "trace_id": trace_id or None,
        "task_id": task_id,
        "category": "evaluation",
        "intent": "record_evaluation",
        "timestamp": str(receipt.get("emitted_at") or _utc_now_iso()),
        "duration_sec": 0.0,
        "estimated_cost_usd": 0.0,
        "source_format": "canonical",
        "deliverables": deliverables,
        "metadata": {
            "evaluation_id": evaluation.evaluation_id,
            "subject_kind": evaluation.subject_kind,
            "subject_id": evaluation.subject_id,
            "metric": evaluation.metric,
            "score": float(evaluation.score),
            "artifact_id": result.artifact.artifact_id,
            "fact_ids": fact_ids,
            "receipt_event_id": str(receipt.get("event_id", "")),
            "manifest_path": str(result.manifest_path),
        },
        "raw_payload": {
            "evaluation": {
                "evaluation_id": evaluation.evaluation_id,
                "subject_kind": evaluation.subject_kind,
                "subject_id": evaluation.subject_id,
                "evaluator": evaluation.evaluator,
                "metric": evaluation.metric,
                "score": float(evaluation.score),
                "session_id": evaluation.session_id,
                "task_id": evaluation.task_id,
                "run_id": evaluation.run_id,
                "evidence_refs": list(evaluation.evidence_refs),
                "metadata": dict(evaluation.metadata),
            },
            "summary": dict(summary),
            "receipt": dict(receipt),
        },
    }


async def export_evaluation_registration_to_kaizenops(
    result: SovereignEvaluationRegistrationResult,
    *,
    client: KaizenOpsClient | None = None,
) -> dict[str, Any]:
    """Send one sovereign evaluation registration to KaizenOps."""

    resolved_client = client or KaizenOpsClient()
    event = evaluation_registration_to_kaizenops_event(result)
    return await resolved_client.ingest_events([event])


__all__ = [
    "evaluation_registration_to_kaizenops_event",
    "export_evaluation_registration_to_kaizenops",
]
