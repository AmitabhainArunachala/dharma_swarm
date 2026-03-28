"""Curriculum proposal engine for frontier-task derivation."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex[:12]


class FrontierTask(BaseModel):
    """A proposed frontier task derived from existing runtime artifacts."""

    frontier_id: str = Field(default_factory=_new_id)
    title: str
    description: str
    source: str
    verifier_type: str
    difficulty: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumEngine:
    """Derive explicit next-step tasks from poor or uncertain research outcomes."""

    def derive_frontier_tasks(
        self,
        *,
        report: Any,
        reward_signal: Any,
    ) -> list[FrontierTask]:
        payload = (
            reward_signal.model_dump()
            if hasattr(reward_signal, "model_dump")
            else dict(reward_signal)
        )
        grade_card = dict(payload.get("grade_card") or {})
        report_id = str(getattr(report, "report_id", "") or "")
        task_id = str(getattr(report, "task_id", "") or "")
        final_score = float(grade_card.get("final_score", 0.0) or 0.0)
        tasks: list[FrontierTask] = []

        for gate_failure in list(grade_card.get("gate_failures") or []):
            tasks.append(
                FrontierTask(
                    title=f"Resolve gate failure: {gate_failure}",
                    description=f"Produce evidence that clears the {gate_failure} gate.",
                    source="gate_failure",
                    verifier_type="research_grade",
                    difficulty=self._difficulty_for_gate_failure(gate_failure, final_score),
                    provenance={
                        "report_id": report_id,
                        "task_id": task_id,
                        "gate_failure": gate_failure,
                    },
                    metadata={"seed_kind": "gate_failure"},
                )
            )

        for contradiction in list(getattr(report, "contradictions", []) or []):
            if str(contradiction.get("status", "")).lower() != "unresolved":
                continue
            tasks.append(
                FrontierTask(
                    title="Resolve unresolved contradiction",
                    description="Investigate and reconcile the unresolved contradiction.",
                    source="contradiction",
                    verifier_type="contradiction_review",
                    difficulty="high",
                    provenance={
                        "report_id": report_id,
                        "task_id": task_id,
                        "claim_id": str(contradiction.get("claim_id", "") or ""),
                    },
                    metadata={"seed_kind": "contradiction"},
                )
            )

        freshness = float(grade_card.get("freshness", 0.0) or 0.0)
        brief = getattr(report, "brief", None)
        if getattr(brief, "requires_recency", False) and freshness < 0.8:
            tasks.append(
                FrontierTask(
                    title="Refresh stale capability evidence",
                    description="Repeat retrieval with stronger recency constraints.",
                    source="staleness",
                    verifier_type="freshness_probe",
                    difficulty="medium",
                    provenance={
                        "report_id": report_id,
                        "task_id": task_id,
                        "freshness": freshness,
                    },
                    metadata={"seed_kind": "freshness"},
                )
            )

        for claim in list(getattr(report, "claims", []) or []):
            confidence = float(getattr(claim, "confidence", 0.0) or 0.0)
            if confidence >= 0.5:
                continue
            tasks.append(
                FrontierTask(
                    title="Reduce claim uncertainty",
                    description="Collect stronger evidence for the low-confidence claim.",
                    source="uncertainty",
                    verifier_type="claim_audit",
                    difficulty="medium" if confidence >= 0.3 else "high",
                    provenance={
                        "report_id": report_id,
                        "task_id": task_id,
                        "claim_id": str(getattr(claim, "claim_id", "") or ""),
                    },
                    metadata={"seed_kind": "uncertainty", "confidence": confidence},
                )
            )

        return tasks

    @staticmethod
    def _difficulty_for_gate_failure(gate_failure: str, final_score: float) -> str:
        severe = {
            "unresolved_high_severity_contradictions",
            "unsupported_claim_ratio",
            "freshness",
        }
        if gate_failure in severe or final_score < 0.4:
            return "high"
        if final_score < 0.7:
            return "medium"
        return "low"


__all__ = ["CurriculumEngine", "FrontierTask"]
