"""Tests for dharma_swarm.evaluator — output quality evaluation."""

import pytest

from dharma_swarm.evaluator import (
    OutputEvaluation,
    _clamp01,
    _has_structured_output,
    _infer_task_type,
    _keyword_set,
    _line_repetition_penalty,
    _looks_like_failure,
    _normalize_provider,
    _tokenize,
)
from dharma_swarm.models import ProviderType, Task


# === Helper functions ===


def test_clamp01_bounds():
    assert _clamp01(-0.5) == 0.0
    assert _clamp01(1.5) == 1.0
    assert _clamp01(0.5) == 0.5


def test_clamp01_edge():
    assert _clamp01(0.0) == 0.0
    assert _clamp01(1.0) == 1.0


def test_normalize_provider_enum():
    assert _normalize_provider(ProviderType.OPENROUTER) == "openrouter"


def test_normalize_provider_string():
    assert _normalize_provider("  OpenAI  ") == "openai"


def test_normalize_provider_empty():
    assert _normalize_provider("") == "unknown"


def test_tokenize_basic():
    tokens = _tokenize("Hello world, this is a test!")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens


def test_tokenize_code():
    tokens = _tokenize("def foo_bar(x): return x.baz")
    assert "def" in tokens
    assert "foo_bar" in tokens


def test_keyword_set_filters_stopwords():
    kw = _keyword_set("this is a test of the keyword extraction")
    assert "this" not in kw
    assert "the" not in kw
    assert "test" in kw
    assert "keyword" in kw
    assert "extraction" in kw


def test_keyword_set_filters_short():
    kw = _keyword_set("a b c de fg hij")
    assert "hij" in kw
    assert "de" not in kw  # < 3 chars


# === Failure detection ===


def test_looks_like_failure_empty():
    assert _looks_like_failure("") is True
    assert _looks_like_failure("   ") is True


def test_looks_like_failure_markers():
    assert _looks_like_failure("Error: something went wrong") is True
    assert _looks_like_failure("I cannot do that") is True
    assert _looks_like_failure("Unable to complete") is True


def test_looks_like_failure_clean():
    assert _looks_like_failure("Here is the solution: def foo(): pass") is False


# === Task type inference ===


def _make_task(title: str = "", description: str = "", metadata: dict | None = None) -> Task:
    return Task(title=title, description=description, metadata=metadata or {})


def test_infer_task_type_code():
    task = _make_task("Fix bug in module", "Edit the file to resolve crash")
    assert _infer_task_type(task) == "code"


def test_infer_task_type_research():
    task = _make_task("Analyze R_V results", "Investigate the paper claims")
    assert _infer_task_type(task) == "research"


def test_infer_task_type_ops():
    task = _make_task("Check health", "Monitor the deploy status")
    assert _infer_task_type(task) == "ops"


def test_infer_task_type_explicit_metadata():
    task = _make_task("Whatever", "Stuff", metadata={"task_type": "custom"})
    assert _infer_task_type(task) == "custom"


def test_infer_task_type_general():
    task = _make_task("Think about things", "Contemplate deeply")
    assert _infer_task_type(task) == "general"


# === Line repetition penalty ===


def test_line_repetition_no_repeat():
    text = "line one\nline two\nline three\nline four"
    penalty = _line_repetition_penalty(text)
    assert penalty == 0.0


def test_line_repetition_all_same():
    text = "same\nsame\nsame\nsame"
    penalty = _line_repetition_penalty(text)
    assert penalty == pytest.approx(0.75, abs=0.01)


def test_line_repetition_short():
    text = "one\ntwo"
    assert _line_repetition_penalty(text) == 0.0


# === Structured output detection ===


def test_has_structured_code_block():
    assert _has_structured_output("Here:\n```python\ndef foo(): pass\n```") is True


def test_has_structured_bullet_list():
    assert _has_structured_output("Steps:\n- First\n- Second") is True


def test_has_structured_file_ref():
    assert _has_structured_output("See dharma_swarm/context.py for details") is True


def test_has_structured_plain():
    assert _has_structured_output("Just some plain text here") is False


# === OutputEvaluation dataclass ===


def _make_eval(**overrides) -> OutputEvaluation:
    defaults = dict(
        task_id="t-1",
        task_title="Test",
        task_type="general",
        agent_name="test-agent",
        provider="openrouter",
        model="llama-70b",
        relevance=0.8,
        correctness=0.7,
        completeness=0.6,
        conciseness=0.9,
        actionability=0.5,
        grounding_score=1.0,
        issue_count=0,
        issue_kinds=[],
        failure_class="",
        token_count=100,
        latency_ms=500,
        estimated_cost_usd=0.01,
        success=True,
        judge_provider="ollama",
    )
    defaults.update(overrides)
    return OutputEvaluation(**defaults)


def test_quality_score_weighted():
    ev = _make_eval(relevance=1.0, correctness=1.0, completeness=1.0, conciseness=1.0, actionability=1.0)
    assert ev.quality_score == pytest.approx(1.0, abs=0.01)


def test_quality_score_zero():
    ev = _make_eval(relevance=0, correctness=0, completeness=0, conciseness=0, actionability=0)
    assert ev.quality_score == 0.0


def test_quality_score_partial():
    ev = _make_eval(relevance=0.5, correctness=0.5, completeness=0.5, conciseness=0.5, actionability=0.5)
    assert ev.quality_score == pytest.approx(0.5, abs=0.01)


def test_efficiency():
    ev = _make_eval(relevance=1.0, correctness=1.0, completeness=1.0,
                    conciseness=1.0, actionability=1.0, estimated_cost_usd=0.01)
    assert ev.efficiency == pytest.approx(100.0, abs=1.0)


def test_efficiency_zero_cost():
    ev = _make_eval(estimated_cost_usd=0.0)
    # Should not crash — division by max(cost, 0.001)
    assert ev.efficiency > 0


def test_to_record_and_from_record_roundtrip():
    ev = _make_eval()
    record = ev.to_record()
    restored = OutputEvaluation.from_record(record)
    assert restored.task_id == ev.task_id
    assert restored.relevance == ev.relevance
    assert restored.quality_score == pytest.approx(ev.quality_score, abs=0.001)
    assert restored.success == ev.success


def test_from_record_missing_fields():
    """from_record should handle missing/malformed data gracefully."""
    ev = OutputEvaluation.from_record({})
    assert ev.task_id == ""
    assert ev.provider == "unknown"
    assert ev.relevance == 0.0
    assert ev.success is False


def test_from_record_clamps_values():
    ev = OutputEvaluation.from_record({"relevance": 5.0, "correctness": -1.0})
    assert ev.relevance == 1.0
    assert ev.correctness == 0.0
