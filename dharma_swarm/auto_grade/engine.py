"""AutoGrade engine using the canonical Phase 2 evaluation function."""

from __future__ import annotations

from dharma_swarm.auto_research.models import ResearchReport, SourceDocument

from .citations import citation_coverage, citation_precision, has_fabricated_citations
from .contradictions import contradiction_handling, unresolved_high_severity_contradictions
from .coverage import actionability, freshness, novelty, source_diversity, source_quality, structure, topical_coverage
from .efficiency import bounded_efficiency_penalty
from .grounding import groundedness, traceability, unsupported_claim_ratio
from .models import GradeCard, RewardSignal
from .rubrics import clamp01, core_score, promotion_state


class AutoGradeEngine:
    """Minimal deterministic Phase 2 scorer for research reports."""

    def grade(
        self,
        report: ResearchReport,
        sources: list[SourceDocument],
        *,
        latency_ms: int = 0,
        token_cost_usd: float = 0.0,
        total_tokens: int = 0,
        cost_budget_usd: float = 1.0,
        latency_budget_ms: int = 10_000,
        token_budget: int = 10_000,
    ) -> RewardSignal:
        valid_source_ids = {source.source_id for source in sources}
        metrics = {
            "groundedness": groundedness(report.claims),
            "citation_precision": citation_precision(report.claims, valid_source_ids),
            "citation_coverage": citation_coverage(report.claims),
            "source_quality": source_quality(sources),
            "source_diversity": source_diversity(sources),
            "topical_coverage": topical_coverage(report),
            "contradiction_handling": contradiction_handling(report),
            "freshness": freshness(report, sources),
            "structure": structure(report),
            "actionability": actionability(report),
            "novelty": novelty(report, sources),
            "traceability": traceability(report.claims, valid_source_ids),
        }
        unsupported_ratio = unsupported_claim_ratio(report.claims)
        unresolved_high = unresolved_high_severity_contradictions(report)
        fabricated = has_fabricated_citations(report.claims, valid_source_ids)
        source_count_requested = bool(report.brief.metadata.get("sources_requested"))

        gate_failures: list[str] = []
        gate_values = {
            "unsupported_claim_ratio": unsupported_ratio <= 0.02,
            "citation_coverage": metrics["citation_coverage"] >= 0.90,
            "citation_precision": metrics["citation_precision"] >= 0.90,
            "groundedness": metrics["groundedness"] >= 0.85,
            "unresolved_high_severity_contradictions": unresolved_high == 0,
            "freshness": (not report.brief.requires_recency) or metrics["freshness"] >= 0.80,
            "source_count": (not source_count_requested) or len(report.source_ids) >= 3,
            "safety": not fabricated,
        }
        for name, passed in gate_values.items():
            if not passed:
                gate_failures.append(name)

        gate_multiplier = 1.0 if not gate_failures else 0.0
        penalty_total, penalties = bounded_efficiency_penalty(
            token_cost_usd=token_cost_usd,
            latency_ms=latency_ms,
            total_tokens=total_tokens,
            cost_budget_usd=cost_budget_usd,
            latency_budget_ms=latency_budget_ms,
            token_budget=token_budget,
        )
        score = core_score(metrics)
        final_score = clamp01((gate_multiplier * score) - penalty_total)
        grade_card = GradeCard(
            task_id=report.task_id,
            report_id=report.report_id,
            groundedness=metrics["groundedness"],
            citation_precision=metrics["citation_precision"],
            citation_coverage=metrics["citation_coverage"],
            source_quality=metrics["source_quality"],
            source_diversity=metrics["source_diversity"],
            topical_coverage=metrics["topical_coverage"],
            contradiction_handling=metrics["contradiction_handling"],
            freshness=metrics["freshness"],
            structure=metrics["structure"],
            actionability=metrics["actionability"],
            novelty=metrics["novelty"],
            traceability=metrics["traceability"],
            latency_ms=max(0, int(latency_ms)),
            token_cost_usd=max(0.0, float(token_cost_usd)),
            gate_failures=gate_failures,
            final_score=final_score,
            promotion_state=promotion_state(final_score, gate_failures),
            metadata={
                "unsupported_claim_ratio": unsupported_ratio,
                "source_count": len(report.source_ids),
                "unresolved_high_severity_contradictions": unresolved_high,
                "total_tokens": int(total_tokens),
                **penalties,
            },
        )
        return RewardSignal(
            task_id=report.task_id,
            report_id=report.report_id,
            grade_card=grade_card,
            scalar_reward=(2.0 * final_score) - 1.0,
            gate_multiplier=gate_multiplier,
            penalties=penalties,
        )
