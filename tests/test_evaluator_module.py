"""Tests for dharma_swarm.evaluator (OutputEvaluator, OutputEvaluation, helpers)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import pytest_asyncio

from dharma_swarm.evaluator import (
    AgentScore,
    ModelScore,
    OutputEvaluation,
    OutputEvaluator,
    _clamp01,
    _has_structured_output,
    _infer_task_type,
    _line_repetition_penalty,
    _looks_like_failure,
    _normalize_provider,
    _tokenize,
    _keyword_set,
)
from dharma_swarm.models import ProviderType, Task


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

class TestClamp01:
    def test_below_zero(self) -> None:
        assert _clamp01(-1.0) == 0.0

    def test_above_one(self) -> None:
        assert _clamp01(2.5) == 1.0

    def test_midpoint(self) -> None:
        assert _clamp01(0.5) == 0.5


class TestLooksLikeFailure:
    def test_empty_string_is_failure(self) -> None:
        assert _looks_like_failure("") is True

    def test_error_marker(self) -> None:
        assert _looks_like_failure("error: something went wrong") is True

    def test_i_cannot_marker(self) -> None:
        assert _looks_like_failure("I cannot process this request") is True

    def test_normal_output_not_failure(self) -> None:
        assert _looks_like_failure("The tests all passed successfully.") is False

    def test_timeout_marker(self) -> None:
        # The marker is "timeout" (not "timed out") — check exact match
        assert _looks_like_failure("the operation hit a timeout limit") is True


class TestInferTaskType:
    def _task(self, title: str, desc: str = "") -> Task:
        return Task(title=title, description=desc)

    def test_code_task(self) -> None:
        assert _infer_task_type(self._task("fix bug in providers")) == "code"

    def test_research_task(self) -> None:
        assert _infer_task_type(self._task("research routing patterns")) == "research"

    def test_ops_task(self) -> None:
        assert _infer_task_type(self._task("check health of system")) == "ops"

    def test_general_task(self) -> None:
        assert _infer_task_type(self._task("update documentation")) == "general"

    def test_explicit_task_type_in_metadata(self) -> None:
        task = Task(title="something", description="", metadata={"task_type": "custom"})
        assert _infer_task_type(task) == "custom"


class TestLineRepetitionPenalty:
    def test_no_repetition(self) -> None:
        text = "line one\nline two\nline three\nline four"
        penalty = _line_repetition_penalty(text)
        assert penalty == 0.0

    def test_all_identical_lines(self) -> None:
        text = "same\nsame\nsame\nsame\nsame"
        penalty = _line_repetition_penalty(text)
        assert penalty > 0.5

    def test_short_text_no_penalty(self) -> None:
        text = "one line"
        assert _line_repetition_penalty(text) == 0.0


class TestHasStructuredOutput:
    def test_code_block(self) -> None:
        assert _has_structured_output("```python\nprint('hello')\n```") is True

    def test_bullet_list(self) -> None:
        assert _has_structured_output("- item 1\n- item 2") is True

    def test_numbered_list(self) -> None:
        assert _has_structured_output("1. first\n2. second") is True

    def test_plain_prose(self) -> None:
        assert _has_structured_output("This is just a sentence.") is False

    def test_file_path_reference(self) -> None:
        assert _has_structured_output("See dharma_swarm/providers.py for details") is True


class TestNormalizeProvider:
    def test_provider_type_enum(self) -> None:
        result = _normalize_provider(ProviderType.OPENAI)
        assert isinstance(result, str)
        assert result == ProviderType.OPENAI.value

    def test_string_lowercased(self) -> None:
        assert _normalize_provider("  OpenAI  ") == "openai"

    def test_empty_string_becomes_unknown(self) -> None:
        assert _normalize_provider("") == "unknown"


# ---------------------------------------------------------------------------
# OutputEvaluation dataclass
# ---------------------------------------------------------------------------

class TestOutputEvaluation:
    def _eval(self, **kwargs) -> OutputEvaluation:
        defaults = dict(
            task_id="t1", task_title="test task", task_type="code",
            agent_name="coder", provider="openai", model="gpt-4o",
            relevance=0.8, correctness=0.7, completeness=0.75,
            conciseness=0.85, actionability=0.6,
            grounding_score=1.0, issue_count=0, issue_kinds=[],
            failure_class="", token_count=100, latency_ms=500,
            estimated_cost_usd=0.01, success=True, judge_provider="ollama",
        )
        defaults.update(kwargs)
        return OutputEvaluation(**defaults)  # type: ignore[arg-type]

    def test_quality_score_within_bounds(self) -> None:
        e = self._eval()
        assert 0.0 <= e.quality_score <= 1.0

    def test_quality_score_uses_all_dimensions(self) -> None:
        high = self._eval(relevance=1.0, correctness=1.0, completeness=1.0, conciseness=1.0, actionability=1.0)
        low = self._eval(relevance=0.0, correctness=0.0, completeness=0.0, conciseness=0.0, actionability=0.0)
        assert high.quality_score > low.quality_score

    def test_efficiency_higher_with_lower_cost(self) -> None:
        cheap = self._eval(estimated_cost_usd=0.001)
        expensive = self._eval(estimated_cost_usd=10.0)
        assert cheap.efficiency > expensive.efficiency

    def test_to_record_roundtrip(self) -> None:
        e = self._eval()
        record = e.to_record()
        assert "quality_score" in record
        assert "efficiency" in record
        e2 = OutputEvaluation.from_record(record)
        assert abs(e.quality_score - e2.quality_score) < 1e-6

    def test_from_record_handles_missing_fields(self) -> None:
        # Minimal record — should not raise
        e = OutputEvaluation.from_record({"task_id": "x"})
        assert e.task_id == "x"
        assert e.provider == "unknown"

    def test_from_record_clamps_values(self) -> None:
        e = OutputEvaluation.from_record({"relevance": 999.0, "correctness": -5.0})
        assert e.relevance == 1.0
        assert e.correctness == 0.0


# ---------------------------------------------------------------------------
# OutputEvaluator (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOutputEvaluator:
    async def test_evaluate_returns_evaluation(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="fix bug in providers", description="providers.py crashes on import")
        eval_result = await evaluator.evaluate(
            task,
            "The bug was in the import order. Fixed providers.py and all tests pass now.",
            agent_name="coder",
            provider=ProviderType.OPENAI,
            model="gpt-4o",
            latency_ms=400.0,
            estimated_cost_usd=0.005,
            success=True,
        )
        assert isinstance(eval_result, OutputEvaluation)
        assert eval_result.success is True
        assert 0.0 <= eval_result.quality_score <= 1.0

    async def test_evaluate_writes_to_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="research routing", description="analyze provider routing behavior")
        await evaluator.evaluate(
            task, "Found that OpenRouter provides the best cost-to-quality ratio.",
            agent_name="researcher", provider="openrouter", model="llama-3.3-70b",
        )
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_name"] == "researcher"

    async def test_evaluate_empty_output_marks_failure(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="run task", description="do something")
        result = await evaluator.evaluate(
            task, "",
            agent_name="agent", provider="openai", model="gpt-4o",
            success=True,
        )
        # Empty output should be treated as failure regardless of passed success flag
        assert result.success is False

    async def test_read_all_empty_when_no_file(self, tmp_path: Path) -> None:
        path = tmp_path / "no_evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        records = await evaluator.read_all()
        assert records == []

    async def test_read_all_returns_all_evaluations(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="code test", description="write tests for module")
        for i in range(3):
            await evaluator.evaluate(
                task,
                f"Test {i}: implemented tests and all pass",
                agent_name=f"agent{i}",
                provider="openai",
                model="gpt-4o",
            )
        records = await evaluator.read_all()
        assert len(records) == 3

    async def test_leaderboard_aggregates_by_agent(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="code fix", description="fix providers")
        for agent in ("alpha", "alpha", "beta"):
            await evaluator.evaluate(
                task,
                "Fixed the issue, tests pass now.",
                agent_name=agent,
                provider="openai",
                model="gpt-4o",
            )
        board = await evaluator.leaderboard()
        assert len(board) == 2
        assert all(isinstance(s, AgentScore) for s in board)
        alpha_score = next(s for s in board if s.agent_name == "alpha")
        assert alpha_score.runs == 2

    async def test_compare_models_returns_model_scores(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="research patterns", description="analyze system")
        for model in ("gpt-4o", "gpt-4o", "claude-sonnet-4-6"):
            await evaluator.evaluate(
                task,
                "Research complete. Found interesting patterns in the data.",
                agent_name="researcher",
                provider="openai",
                model=model,
            )
        scores = await evaluator.compare_models()
        assert len(scores) == 2
        assert all(isinstance(s, ModelScore) for s in scores)

    async def test_compare_models_filter_by_task_type(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        code_task = Task(title="fix bug in code", description="debug the code")
        research_task = Task(title="research analysis", description="investigate behavior")
        await evaluator.evaluate(code_task, "Fixed the code bug in providers module", agent_name="a", provider="openai", model="gpt-4o")
        await evaluator.evaluate(research_task, "Research complete, found patterns", agent_name="a", provider="openai", model="claude-sonnet")
        code_scores = await evaluator.compare_models(task_type="code")
        research_scores = await evaluator.compare_models(task_type="research")
        assert all(s.model == "gpt-4o" for s in code_scores)
        assert all(s.model == "claude-sonnet" for s in research_scores)

    async def test_model_comparison_returns_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "evals.jsonl"
        evaluator = OutputEvaluator(evaluations_path=path)
        task = Task(title="fix code bug", description="debug")
        await evaluator.evaluate(task, "Fixed bug, tests pass", agent_name="a", provider="openai", model="gpt-4o")
        result = await evaluator.model_comparison()
        assert isinstance(result, dict)
        assert "gpt-4o" in result
