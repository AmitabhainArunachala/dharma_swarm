"""Post-hoc causal credit assignment over traces and lineage.

This module keeps attribution separate from capture. JIKOKU spans and lineage
record what happened; this engine estimates which steps most likely mattered.
The heuristics are intentionally simple, deterministic, and normalization-safe
so they can be improved later without entangling the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dharma_swarm.lineage import LineageEdge
from dharma_swarm.traces import TraceEntry


@dataclass(frozen=True)
class CreditAssignment:
    """Normalized credit assigned to a trace step or lineage edge."""

    subject_kind: str
    subject_id: str
    score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CausalCreditEngine:
    """Heuristic causal attribution over recorded execution artifacts."""

    def assign_trace_credit(
        self,
        traces: list[TraceEntry],
        success_score: float = 1.0,
    ) -> list[CreditAssignment]:
        weighted = [
            self._trace_assignment(entry, index=index, total=len(traces))
            for index, entry in enumerate(traces)
        ]
        return self._normalize(weighted, success_score)

    def assign_lineage_credit(
        self,
        edges: list[LineageEdge],
        success_score: float = 1.0,
    ) -> list[CreditAssignment]:
        weighted = [self._lineage_assignment(edge) for edge in edges]
        return self._normalize(weighted, success_score)

    def assign_combined_credit(
        self,
        *,
        traces: list[TraceEntry],
        edges: list[LineageEdge],
        success_score: float = 1.0,
    ) -> list[CreditAssignment]:
        weighted = [
            *[
                self._trace_assignment(entry, index=index, total=len(traces))
                for index, entry in enumerate(traces)
            ],
            *[self._lineage_assignment(edge) for edge in edges],
        ]
        return self._normalize(weighted, success_score)

    def _trace_assignment(
        self,
        entry: TraceEntry,
        *,
        index: int,
        total: int,
    ) -> tuple[CreditAssignment, float]:
        weight = 1.0
        reasons = ["trace observed"]

        if total > 0:
            recency_bonus = (index + 1) / total
            weight += recency_bonus
            reasons.append(f"recency+{recency_bonus:.2f}")

        if entry.fitness is not None:
            fitness_bonus = max(entry.fitness.weighted(), 0.0) * 2.0
            weight += fitness_bonus
            reasons.append(f"fitness+{fitness_bonus:.2f}")

        file_bonus = min(len(entry.files_changed) * 0.1, 0.5)
        if file_bonus:
            weight += file_bonus
            reasons.append(f"files+{file_bonus:.2f}")

        metadata_bonus = 0.0
        if entry.metadata.get("verified"):
            metadata_bonus += 0.5
            reasons.append("verified")
        if entry.metadata.get("files_touched"):
            touched = min(float(entry.metadata["files_touched"]) * 0.05, 0.25)
            metadata_bonus += touched
            reasons.append(f"files_touched+{touched:.2f}")
        weight += metadata_bonus

        assignment = CreditAssignment(
            subject_kind="trace",
            subject_id=entry.id,
            score=0.0,
            reasons=reasons,
            metadata={
                "agent": entry.agent,
                "action": entry.action,
                "state": entry.state,
            },
        )
        return assignment, max(weight, 0.0)

    def _lineage_assignment(self, edge: LineageEdge) -> tuple[CreditAssignment, float]:
        weight = 1.0
        reasons = ["lineage observed"]

        output_bonus = min(len(edge.output_artifacts) * 0.25, 1.0)
        if output_bonus:
            weight += output_bonus
            reasons.append(f"outputs+{output_bonus:.2f}")

        input_bonus = min(len(edge.input_artifacts) * 0.1, 0.5)
        if input_bonus:
            weight += input_bonus
            reasons.append(f"inputs+{input_bonus:.2f}")

        if edge.operation:
            weight += 0.2
            reasons.append("operation_named")

        assignment = CreditAssignment(
            subject_kind="lineage_edge",
            subject_id=edge.edge_id,
            score=0.0,
            reasons=reasons,
            metadata={
                "agent": edge.agent,
                "task_id": edge.task_id,
                "operation": edge.operation,
            },
        )
        return assignment, max(weight, 0.0)

    def _normalize(
        self,
        weighted: list[tuple[CreditAssignment, float]],
        success_score: float,
    ) -> list[CreditAssignment]:
        if not weighted or success_score <= 0:
            return []

        total_weight = sum(weight for _assignment, weight in weighted)
        if total_weight <= 0:
            equal_share = success_score / len(weighted)
            normalized = [
                CreditAssignment(
                    subject_kind=assignment.subject_kind,
                    subject_id=assignment.subject_id,
                    score=equal_share,
                    reasons=assignment.reasons,
                    metadata=assignment.metadata,
                )
                for assignment, _weight in weighted
            ]
        else:
            normalized = [
                CreditAssignment(
                    subject_kind=assignment.subject_kind,
                    subject_id=assignment.subject_id,
                    score=(weight / total_weight) * success_score,
                    reasons=assignment.reasons,
                    metadata=assignment.metadata,
                )
                for assignment, weight in weighted
            ]

        return sorted(normalized, key=lambda item: item.score, reverse=True)
