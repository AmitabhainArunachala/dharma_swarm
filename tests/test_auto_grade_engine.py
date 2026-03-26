from __future__ import annotations

import importlib

import pytest


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in red phase
        pytest.fail(f"expected module {name!r} to exist: {exc}")


def _supported_report():
    research_models = _load_module("dharma_swarm.auto_research.models")

    brief = research_models.ResearchBrief(
        task_id="task-pass",
        topic="Evaluation design",
        question="How should research reports be graded?",
        requires_recency=True,
        metadata={"sources_requested": True},
    )
    sources = [
        research_models.SourceDocument(
            source_id="src-1",
            url="https://docs.example.org/spec",
            title="Spec",
            authority_score=0.95,
            freshness_score=0.92,
            source_type="docs",
        ),
        research_models.SourceDocument(
            source_id="src-2",
            url="https://research.example.com/paper",
            title="Paper",
            authority_score=0.90,
            freshness_score=0.87,
            source_type="paper",
        ),
        research_models.SourceDocument(
            source_id="src-3",
            url="https://ops.example.net/report",
            title="Report",
            authority_score=0.88,
            freshness_score=0.85,
            source_type="web",
        ),
    ]
    claims = [
        research_models.ClaimRecord(
            claim_id="claim-1",
            text="Grounded grading must enforce citation gates.",
            support_level="supported",
            supporting_source_ids=["src-1"],
            citations=["[src-1]"],
            confidence=0.95,
        ),
        research_models.ClaimRecord(
            claim_id="claim-2",
            text="Diverse sources improve contradiction handling.",
            support_level="supported",
            supporting_source_ids=["src-2", "src-3"],
            citations=["[src-2]", "[src-3]"],
            confidence=0.88,
        ),
    ]
    report = research_models.ResearchReport(
        report_id="report-task-pass",
        task_id="task-pass",
        brief=brief,
        summary="Research grading summary.",
        body="- Grounded grading must enforce citation gates. [src-1]\n- Diverse sources improve contradiction handling. [src-2] [src-3]\nRecommended next step: promote trustworthy graders first.",
        claims=claims,
        source_ids=["src-1", "src-2", "src-3"],
        metadata={"topical_coverage": 0.93, "novelty": 0.72},
    )
    return report, sources


def _failing_report():
    research_models = _load_module("dharma_swarm.auto_research.models")

    brief = research_models.ResearchBrief(
        task_id="task-fail",
        topic="Breaking reports",
        question="What should be rejected?",
        requires_recency=True,
        metadata={"sources_requested": True},
    )
    sources = [
        research_models.SourceDocument(
            source_id="src-stale",
            url="https://stale.example.com/post",
            title="Stale Post",
            authority_score=0.25,
            freshness_score=0.40,
        ),
    ]
    claims = [
        research_models.ClaimRecord(
            claim_id="claim-bad",
            text="This unsupported claim should fail.",
            support_level="inferred",
            confidence=0.20,
        ),
    ]
    report = research_models.ResearchReport(
        report_id="report-task-fail",
        task_id="task-fail",
        brief=brief,
        summary="Weak report.",
        body="This unsupported claim should fail.",
        claims=claims,
        source_ids=["src-stale"],
        contradictions=[
            {"claim_id": "claim-bad", "severity": "high", "status": "unresolved"},
        ],
        metadata={"topical_coverage": 0.30, "novelty": 0.20},
    )
    return report, sources


def test_auto_grade_engine_scores_promotable_report() -> None:
    engine_module = _load_module("dharma_swarm.auto_grade.engine")

    report, sources = _supported_report()
    reward = engine_module.AutoGradeEngine().grade(
        report,
        sources,
        latency_ms=1800,
        token_cost_usd=0.08,
        total_tokens=2200,
        cost_budget_usd=1.0,
        latency_budget_ms=6000,
        token_budget=6000,
    )

    card = reward.grade_card
    assert card.gate_failures == []
    assert card.citation_coverage == pytest.approx(1.0)
    assert card.citation_precision == pytest.approx(1.0)
    assert card.groundedness >= 0.85
    assert card.freshness >= 0.80
    assert card.final_score >= 0.82
    assert card.promotion_state == "promotable"
    assert reward.gate_multiplier == pytest.approx(1.0)
    assert reward.scalar_reward == pytest.approx((2.0 * card.final_score) - 1.0)


def test_auto_grade_engine_hard_fails_unsupported_report() -> None:
    engine_module = _load_module("dharma_swarm.auto_grade.engine")

    report, sources = _failing_report()
    reward = engine_module.AutoGradeEngine().grade(
        report,
        sources,
        latency_ms=9000,
        token_cost_usd=1.2,
        total_tokens=12000,
        cost_budget_usd=1.0,
        latency_budget_ms=6000,
        token_budget=6000,
    )

    card = reward.grade_card
    assert "unsupported_claim_ratio" in card.gate_failures
    assert "citation_coverage" in card.gate_failures
    assert "citation_precision" in card.gate_failures
    assert "groundedness" in card.gate_failures
    assert "freshness" in card.gate_failures
    assert "source_count" in card.gate_failures
    assert "unresolved_high_severity_contradictions" in card.gate_failures
    assert reward.gate_multiplier == pytest.approx(0.0)
    assert card.final_score == pytest.approx(0.0)
    assert card.promotion_state == "rollback_or_revise"
    assert reward.scalar_reward == pytest.approx(-1.0)
