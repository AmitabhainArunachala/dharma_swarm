"""Tests for dharma_swarm.self_research."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.evaluator import OutputEvaluation, OutputEvaluator
from dharma_swarm.self_research import (
    ConfigChange,
    Experiment,
    ExperimentResult,
    Hypothesis,
    SelfResearcher,
    RESEARCH_QUESTIONS,
)


# ---------------------------------------------------------------------------
# Helpers — build synthetic OutputEvaluation records
# ---------------------------------------------------------------------------

def _make_eval(
    *,
    model: str = "gpt-4o",
    agent_name: str = "agent",
    task_type: str = "code",
    quality_score_target: float = 0.7,
    token_count: int = 150,
    success: bool = True,
    completeness: float = 0.7,
) -> OutputEvaluation:
    # Back-calculate individual dimensions to hit the target quality_score
    # quality = relevance*0.24 + correctness*0.26 + completeness*0.20 + conciseness*0.12 + actionability*0.18
    dim = quality_score_target
    return OutputEvaluation(
        task_id="t1",
        task_title="test task",
        task_type=task_type,
        agent_name=agent_name,
        provider="openai",
        model=model,
        relevance=dim,
        correctness=dim,
        completeness=completeness,
        conciseness=dim,
        actionability=dim,
        grounding_score=1.0,
        issue_count=0,
        issue_kinds=[],
        failure_class="",
        token_count=token_count,
        latency_ms=300,
        estimated_cost_usd=0.001,
        success=success,
        judge_provider="ollama",
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestResearchQuestions:
    def test_research_questions_is_nonempty(self) -> None:
        assert len(RESEARCH_QUESTIONS) >= 3

    def test_all_questions_are_strings(self) -> None:
        assert all(isinstance(q, str) for q in RESEARCH_QUESTIONS)


# ---------------------------------------------------------------------------
# SelfResearcher.generate_hypotheses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGenerateHypotheses:
    async def test_empty_evaluations_returns_empty(self) -> None:
        sr = SelfResearcher()
        hypotheses = await sr.generate_hypotheses([])
        assert hypotheses == []

    async def test_generates_hypothesis_when_clear_winner(self) -> None:
        # model_a consistently scores 0.8, model_b consistently scores 0.6
        evals = (
            [_make_eval(model="model_a", quality_score_target=0.8, task_type="code")] * 5
            + [_make_eval(model="model_b", quality_score_target=0.6, task_type="code")] * 5
        )
        sr = SelfResearcher()
        hypotheses = await sr.generate_hypotheses(evals)
        assert len(hypotheses) >= 1
        assert any("model_a" in h.question for h in hypotheses)

    async def test_no_hypothesis_when_delta_too_small(self) -> None:
        # model_a and model_b score almost identically
        evals = (
            [_make_eval(model="model_a", quality_score_target=0.70)] * 4
            + [_make_eval(model="model_b", quality_score_target=0.72)] * 4
        )
        sr = SelfResearcher()
        hypotheses = await sr.generate_hypotheses(evals)
        # Delta < 0.05 → no model-comparison hypothesis
        model_hyps = [h for h in hypotheses if "model_a" in h.question or "model_b" in h.question]
        assert model_hyps == []

    async def test_generates_length_hypothesis(self) -> None:
        # short vs long outputs with different quality
        short = [_make_eval(token_count=50, quality_score_target=0.8)] * 5
        long_ = [_make_eval(token_count=300, quality_score_target=0.5)] * 5
        sr = SelfResearcher()
        hypotheses = await sr.generate_hypotheses(short + long_)
        assert any("Longer outputs" in h.question for h in hypotheses)

    async def test_hypotheses_have_required_fields(self) -> None:
        evals = (
            [_make_eval(model="alpha", quality_score_target=0.85, task_type="research")] * 4
            + [_make_eval(model="beta", quality_score_target=0.60, task_type="research")] * 4
        )
        sr = SelfResearcher()
        hypotheses = await sr.generate_hypotheses(evals)
        for h in hypotheses:
            assert isinstance(h, Hypothesis)
            assert isinstance(h.id, str) and h.id
            assert isinstance(h.question, str) and h.question
            assert isinstance(h.rationale, str) and h.rationale


# ---------------------------------------------------------------------------
# SelfResearcher.design_experiment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDesignExperiment:
    async def test_experiment_maps_from_hypothesis(self) -> None:
        hyp = Hypothesis(
            id="abc123",
            question="model_a outperforms model_b for code tasks.",
            rationale="Historical delta 0.10 over 6 runs.",
            task_type="code",
            models=("model_a", "model_b"),
            expected_winner="model_a",
            evidence_count=6,
        )
        sr = SelfResearcher()
        exp = await sr.design_experiment(hyp)
        assert isinstance(exp, Experiment)
        assert exp.hypothesis_id == "abc123"
        assert exp.candidate_model == "model_a"
        assert exp.control_model == "model_b"
        assert exp.task_type == "code"
        assert exp.metric == "quality_score"

    async def test_sample_size_bounded(self) -> None:
        hyp = Hypothesis(
            id="x1",
            question="huge data test",
            rationale="many samples",
            task_type="general",
            models=("a", "b"),
            expected_winner="a",
            evidence_count=10_000,
        )
        sr = SelfResearcher()
        exp = await sr.design_experiment(hyp)
        assert exp.sample_size <= 20

    async def test_min_sample_size_is_4(self) -> None:
        hyp = Hypothesis(
            id="x2",
            question="tiny test",
            rationale="few samples",
            task_type="general",
            models=("a",),
            expected_winner="a",
            evidence_count=1,
        )
        sr = SelfResearcher()
        exp = await sr.design_experiment(hyp)
        assert exp.sample_size >= 4

    async def test_no_models_gives_none_candidates(self) -> None:
        hyp = Hypothesis(
            id="x3",
            question="general hypothesis",
            rationale="no models specified",
            task_type="general",
            models=(),
            expected_winner=None,
            evidence_count=5,
        )
        sr = SelfResearcher()
        exp = await sr.design_experiment(hyp)
        assert exp.candidate_model is None
        assert exp.control_model is None


# ---------------------------------------------------------------------------
# SelfResearcher.run_experiment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRunExperiment:
    async def test_winner_is_best_model(self) -> None:
        evals = (
            [_make_eval(model="good_model", quality_score_target=0.9, task_type="code")] * 5
            + [_make_eval(model="bad_model", quality_score_target=0.4, task_type="code")] * 5
        )
        exp = Experiment(
            id="e1",
            hypothesis_id="h1",
            question="good_model outperforms bad_model?",
            task_type="code",
            metric="quality_score",
            control_model="bad_model",
            candidate_model="good_model",
            sample_size=5,
            methodology="historical retrospective",
        )
        sr = SelfResearcher()
        result = await sr.run_experiment(exp, evaluations=evals)
        assert isinstance(result, ExperimentResult)
        assert result.winner == "good_model"
        assert result.delta > 0

    async def test_no_evaluations_gives_zero_delta(self) -> None:
        exp = Experiment(
            id="e2",
            hypothesis_id="h2",
            question="test with empty data",
            task_type="code",
            metric="quality_score",
            control_model="model_b",
            candidate_model="model_a",
            sample_size=5,
            methodology="retrospective",
        )
        sr = SelfResearcher()
        result = await sr.run_experiment(exp, evaluations=[])
        assert result.delta == 0.0

    async def test_confidence_scales_with_sample_count(self) -> None:
        small_evals = [_make_eval(model="m", task_type="general")] * 2
        large_evals = [_make_eval(model="m", task_type="general")] * 20
        exp = Experiment(
            id="e3", hypothesis_id="h3", question="q", task_type="general",
            metric="quality_score", control_model=None, candidate_model="m",
            sample_size=10, methodology="x",
        )
        sr = SelfResearcher()
        small_result = await sr.run_experiment(exp, evaluations=small_evals)
        large_result = await sr.run_experiment(exp, evaluations=large_evals)
        assert large_result.confidence >= small_result.confidence

    async def test_conclusion_is_string(self) -> None:
        evals = [_make_eval(model="m", task_type="ops")] * 3
        exp = Experiment(
            id="e4", hypothesis_id="h4", question="q?", task_type="ops",
            metric="quality_score", control_model=None, candidate_model="m",
            sample_size=3, methodology="x",
        )
        sr = SelfResearcher()
        result = await sr.run_experiment(exp, evaluations=evals)
        assert isinstance(result.conclusion, str) and result.conclusion


# ---------------------------------------------------------------------------
# SelfResearcher.apply_learnings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestApplyLearnings:
    async def test_low_confidence_returns_no_changes(self) -> None:
        result = ExperimentResult(
            hypothesis_id="h1",
            question="test",
            winner="model_a",
            delta=0.2,
            confidence=0.3,  # below threshold
            conclusion="low confidence",
        )
        sr = SelfResearcher()
        changes = await sr.apply_learnings(result)
        assert changes == []

    async def test_no_winner_returns_no_changes(self) -> None:
        result = ExperimentResult(
            hypothesis_id="h1",
            question="test",
            winner=None,
            delta=0.0,
            confidence=0.9,
            conclusion="no winner",
        )
        sr = SelfResearcher()
        changes = await sr.apply_learnings(result)
        assert changes == []

    async def test_high_confidence_winner_returns_change(self) -> None:
        result = ExperimentResult(
            hypothesis_id="h1",
            question="model_a outperforms model_b for code tasks.",
            winner="model_a",
            delta=0.15,
            confidence=0.8,
            conclusion="model_a leads by 0.15 quality points",
        )
        sr = SelfResearcher()
        changes = await sr.apply_learnings(result)
        assert len(changes) == 1
        change = changes[0]
        assert isinstance(change, ConfigChange)
        assert change.value == "model_a"
        assert change.target == "routing_preferences"
        assert change.key == "preferred_model"
        assert "model_a" in change.reason

    async def test_config_change_reason_includes_delta(self) -> None:
        result = ExperimentResult(
            hypothesis_id="h2",
            question="alpha is better",
            winner="alpha",
            delta=0.22,
            confidence=0.75,
            conclusion="alpha wins",
        )
        sr = SelfResearcher()
        changes = await sr.apply_learnings(result)
        assert "+0.220" in changes[0].reason or "0.22" in changes[0].reason


# ---------------------------------------------------------------------------
# SelfResearcher.load_evaluations (integration with file)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLoadEvaluations:
    async def test_load_evaluations_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        sr = SelfResearcher(evaluations_path=tmp_path / "evals.jsonl")
        evals = await sr.load_evaluations()
        assert evals == []

    async def test_load_evaluations_reads_written_records(self, tmp_path: Path) -> None:
        evals_path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=evals_path)
        from dharma_swarm.models import Task
        task = Task(title="fix code bug", description="debug providers")
        await evaluator.evaluate(
            task,
            "Fixed the bug. Tests pass.",
            agent_name="coder",
            provider="openai",
            model="gpt-4o",
        )
        sr = SelfResearcher(evaluations_path=evals_path)
        loaded = await sr.load_evaluations()
        assert len(loaded) == 1
        assert loaded[0].model == "gpt-4o"
