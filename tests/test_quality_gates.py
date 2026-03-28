"""Tests for dharma_swarm.quality_gates."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.model_hierarchy import default_model
from dharma_swarm.models import ProviderType
from dharma_swarm.quality_gates import (
    CodeQualityGate,
    ContentQualityGate,
    DimensionScore,
    ProposalQualityGate,
    QualityDomain,
    QualityGateResult,
    QualityScore,
    QualityVerdict,
    ResearchQualityGate,
    _content_hash,
    _load_cached,
    _parse_llm_response,
    _save_cache,
    _structural_code_score,
    _structural_proposal_score,
    _verdict_from_score,
    run_quality_gate,
)


# === Fixtures ===


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    """Override the cache directory to a temporary location."""
    monkeypatch.setattr("dharma_swarm.quality_gates._CACHE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def clean_python_code():
    """Sample clean Python code for testing."""
    return '''"""Module docstring."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b


class Calculator:
    """A simple calculator."""

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b
'''


@pytest.fixture
def bad_python_code():
    """Sample code with issues."""
    return '''
import os
x = eval(input())
password = "hunter2"
os.system("rm -rf /")
'''


@pytest.fixture
def research_text():
    """Sample research artifact."""
    return (
        "We propose a novel approach to measuring self-referential processing "
        "in transformer architectures. Our method uses participation ratio contraction "
        "as a geometric signature (R_V = PR_late / PR_early). "
        "In our experiments (n = 754 prompts), we find significant contraction "
        "(Hedges' g = -1.47, p < 0.001) in self-referential conditions. "
        "However, we note several limitations: the current analysis is limited "
        "to Mistral-7B, and future work should validate across model families. "
        "Unlike prior approaches [1, 2, 3], our metric operates entirely in "
        "representation space without requiring behavioral probes."
    )


@pytest.fixture
def proposal_description():
    """Sample evolution proposal description."""
    return (
        "Refactor the fitness scoring pipeline to support weighted multi-dimensional "
        "evaluation. This change adds a new QualityGate class that evaluates proposals "
        "against domain-specific rubrics before archiving. The expected impact is reduced "
        "noise in the evolution archive, as low-quality proposals will be filtered before "
        "they can accumulate fitness. Tests are included for all evaluator types."
    )


# === Model tests ===


def test_quality_score_defaults():
    score = QualityScore(domain=QualityDomain.CODE, overall=75.0)
    assert score.verdict == QualityVerdict.FAIL  # default, not auto-set
    assert score.evaluator == "lightweight"
    assert score.dimensions == []


def test_quality_score_bounds():
    score = QualityScore(domain=QualityDomain.CODE, overall=0.0)
    assert score.overall == 0.0
    score = QualityScore(domain=QualityDomain.CODE, overall=100.0)
    assert score.overall == 100.0


def test_dimension_score_bounds():
    d = DimensionScore(name="test", score=50.0)
    assert d.weight == 1.0
    assert d.feedback == ""


def test_quality_gate_result():
    score = QualityScore(domain=QualityDomain.PROPOSAL, overall=70.0)
    result = QualityGateResult(passed=True, score=score, threshold=60.0)
    assert result.passed is True
    assert result.reason == ""


# === Verdict tests ===


def test_verdict_pass():
    assert _verdict_from_score(80.0) == QualityVerdict.PASS


def test_verdict_warn():
    # Default threshold=60, warn threshold = 60 * 0.75 = 45
    assert _verdict_from_score(50.0) == QualityVerdict.WARN


def test_verdict_fail():
    assert _verdict_from_score(30.0) == QualityVerdict.FAIL


def test_verdict_custom_threshold():
    assert _verdict_from_score(75.0, threshold=80.0) == QualityVerdict.WARN
    assert _verdict_from_score(50.0, threshold=80.0) == QualityVerdict.FAIL
    assert _verdict_from_score(85.0, threshold=80.0) == QualityVerdict.PASS


# === Content hash tests ===


def test_content_hash_deterministic():
    h1 = _content_hash("hello world")
    h2 = _content_hash("hello world")
    assert h1 == h2


def test_content_hash_different_inputs():
    h1 = _content_hash("hello")
    h2 = _content_hash("world")
    assert h1 != h2


def test_content_hash_length():
    h = _content_hash("test")
    assert len(h) == 16


# === Cache tests ===


def test_cache_roundtrip(tmp_cache_dir):
    score = QualityScore(
        domain=QualityDomain.CODE,
        overall=75.0,
        verdict=QualityVerdict.PASS,
        artifact_hash="abc123def456aaaa",
        dimensions=[DimensionScore(name="test", score=75.0, feedback="ok")],
    )
    _save_cache(score)
    loaded = _load_cached(QualityDomain.CODE, "abc123def456aaaa")
    assert loaded is not None
    assert loaded.overall == 75.0
    assert loaded.artifact_hash == "abc123def456aaaa"
    assert len(loaded.dimensions) == 1


def test_cache_miss(tmp_cache_dir):
    result = _load_cached(QualityDomain.CODE, "nonexistent_hash_")
    assert result is None


def test_cache_corrupt_file(tmp_cache_dir):
    path = tmp_cache_dir / "code" / "corrupted_hash_ab.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{{{")
    result = _load_cached(QualityDomain.CODE, "corrupted_hash_ab")
    assert result is None


# === Structural code evaluator tests ===


def test_structural_code_clean(clean_python_code):
    score = _structural_code_score(clean_python_code)
    assert score.domain == QualityDomain.CODE
    assert score.evaluator == "structural"
    assert score.overall >= 60.0  # Clean code should pass default threshold
    dims = {d.name: d.score for d in score.dimensions}
    assert "correctness" in dims
    assert "style" in dims
    assert "security" in dims
    assert "maintainability" in dims
    assert dims["correctness"] >= 70.0  # Should parse cleanly
    assert dims["security"] >= 90.0  # No security flags


def test_structural_code_bad(bad_python_code):
    score = _structural_code_score(bad_python_code)
    dims = {d.name: d.score for d in score.dimensions}
    assert dims["security"] < 70.0  # eval(), hardcoded password, os.system


def test_structural_code_syntax_error():
    score = _structural_code_score("def broken(:\n    pass")
    dims = {d.name: d.score for d in score.dimensions}
    assert dims["correctness"] < 50.0


def test_structural_code_with_tests():
    code = '''
def test_addition():
    assert 1 + 1 == 2

def test_subtraction():
    assert 3 - 1 == 2
'''
    score = _structural_code_score(code)
    dims = {d.name: d.score for d in score.dimensions}
    assert dims["test_coverage"] >= 60.0


def test_structural_code_empty():
    score = _structural_code_score("")
    assert score.overall >= 0.0


# === Structural proposal evaluator tests ===


def test_structural_proposal_good(proposal_description):
    score = _structural_proposal_score(
        description=proposal_description,
        diff="+ added code\n+ more code\n- removed line",
        component="dharma_swarm/evolution.py",
    )
    assert score.domain == QualityDomain.PROPOSAL
    assert score.overall >= 50.0
    dims = {d.name: d.score for d in score.dimensions}
    assert "specificity" in dims
    assert "feasibility" in dims
    assert "impact" in dims
    assert "risk" in dims
    assert "alignment" in dims


def test_structural_proposal_minimal():
    score = _structural_proposal_score(
        description="fix bug",
        diff="",
        component="",
    )
    assert score.overall < 60.0  # Too vague to pass


def test_structural_proposal_huge_diff():
    big_diff = "\n".join([f"+ line {i}" for i in range(600)])
    score = _structural_proposal_score(
        description="Major refactoring of the entire codebase",
        diff=big_diff,
        component="dharma_swarm/models.py",
    )
    dims = {d.name: d.score for d in score.dimensions}
    assert dims["risk"] < 50.0  # Large diff = high risk


# === LLM response parsing tests ===


def test_parse_llm_response_valid():
    raw = json.dumps({
        "dimensions": [
            {"name": "correctness", "score": 80, "feedback": "Good"},
            {"name": "style", "score": 70, "feedback": "Decent"},
        ],
        "overall": 75,
        "feedback": "Solid code",
        "suggestions": ["Add more tests"],
    })
    score = _parse_llm_response(raw, QualityDomain.CODE)
    assert score is not None
    assert score.overall == 75.0
    assert len(score.dimensions) == 2
    assert score.improvement_suggestions == ["Add more tests"]


def test_parse_llm_response_with_fences():
    raw = "```json\n" + json.dumps({
        "dimensions": [{"name": "test", "score": 60, "feedback": "ok"}],
        "overall": 60,
        "feedback": "Acceptable",
        "suggestions": [],
    }) + "\n```"
    score = _parse_llm_response(raw, QualityDomain.CODE)
    assert score is not None
    assert score.overall == 60.0


def test_parse_llm_response_invalid():
    result = _parse_llm_response("not json at all", QualityDomain.CODE)
    assert result is None


def test_parse_llm_response_clamps_scores():
    raw = json.dumps({
        "dimensions": [{"name": "x", "score": 150, "feedback": "over"}],
        "overall": -10,
        "feedback": "bad",
    })
    score = _parse_llm_response(raw, QualityDomain.CODE)
    assert score is not None
    assert score.overall == 0.0
    assert score.dimensions[0].score == 100.0


def test_parse_llm_response_suggestions_as_string():
    raw = json.dumps({
        "dimensions": [],
        "overall": 50,
        "feedback": "ok",
        "suggestions": "just one suggestion",
    })
    score = _parse_llm_response(raw, QualityDomain.CODE)
    assert score is not None
    assert score.improvement_suggestions == ["just one suggestion"]


# === Quality gate class tests ===


@pytest.mark.asyncio
async def test_code_quality_gate_structural(tmp_cache_dir, clean_python_code):
    gate = CodeQualityGate(threshold=60.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(clean_python_code)
    assert isinstance(result, QualityGateResult)
    assert result.passed is True
    assert result.score.domain == QualityDomain.CODE


@pytest.mark.asyncio
async def test_code_quality_gate_rejects_bad(tmp_cache_dir, bad_python_code):
    gate = CodeQualityGate(threshold=80.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(bad_python_code)
    # With high threshold and bad code, should fail or be marginal
    assert isinstance(result, QualityGateResult)
    assert result.score.overall < 90.0  # Definitely not excellent


@pytest.mark.asyncio
async def test_proposal_quality_gate_structural(tmp_cache_dir, proposal_description):
    gate = ProposalQualityGate(threshold=50.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(
        proposal_description,
        context={
            "component": "dharma_swarm/evolution.py",
            "change_type": "mutation",
            "diff_preview": "+ added line\n+ another line",
        },
    )
    assert isinstance(result, QualityGateResult)
    assert result.score.domain == QualityDomain.PROPOSAL


@pytest.mark.asyncio
async def test_research_quality_gate_structural(tmp_cache_dir, research_text):
    gate = ResearchQualityGate(threshold=50.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(research_text)
    assert isinstance(result, QualityGateResult)
    assert result.score.domain == QualityDomain.RESEARCH
    # Research text has citations, methodology, hedging -- should score well
    assert result.score.overall >= 50.0


@pytest.mark.asyncio
async def test_content_quality_gate_structural(tmp_cache_dir):
    content = (
        "Imagine building an AI system that evolves itself. Here's why this matters: "
        "autonomous agents need quality gates to prevent drift. In our system, "
        "we use LLM-as-judge evaluation to score proposals on 5 dimensions. "
        "Try implementing this in your own pipeline. First, define your rubric. "
        "Next, build the structural evaluator. Then add the LLM judge layer. "
        "Your agents will produce 35% fewer low-quality mutations."
    )
    gate = ContentQualityGate(threshold=50.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(content)
    assert isinstance(result, QualityGateResult)
    assert result.score.domain == QualityDomain.CONTENT
    assert result.score.overall >= 40.0


@pytest.mark.asyncio
async def test_gate_caching(tmp_cache_dir, clean_python_code):
    gate = CodeQualityGate(threshold=60.0, use_llm=False, cache_enabled=True)
    result1 = await gate.evaluate(clean_python_code)
    result2 = await gate.evaluate(clean_python_code)
    # Second call should use cache
    assert result1.score.overall == result2.score.overall
    assert result2.reason == "cached evaluation"


@pytest.mark.asyncio
async def test_gate_cache_disabled(tmp_cache_dir, clean_python_code):
    gate = CodeQualityGate(threshold=60.0, use_llm=False, cache_enabled=False)
    result1 = await gate.evaluate(clean_python_code)
    result2 = await gate.evaluate(clean_python_code)
    assert result1.score.overall == result2.score.overall
    assert result2.reason != "cached evaluation"


# === Threshold gating tests ===


@pytest.mark.asyncio
async def test_threshold_gating_pass(tmp_cache_dir, clean_python_code):
    gate = CodeQualityGate(threshold=40.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(clean_python_code)
    assert result.passed is True


@pytest.mark.asyncio
async def test_threshold_gating_fail(tmp_cache_dir):
    gate = ProposalQualityGate(threshold=95.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate("fix", context={"component": "", "diff_preview": ""})
    assert result.passed is False
    assert result.reason  # Should have a reason


# === Feedback generation tests ===


@pytest.mark.asyncio
async def test_feedback_on_failure(tmp_cache_dir):
    gate = CodeQualityGate(threshold=95.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate("x = 1")
    if not result.passed:
        assert result.reason != ""
        assert "score" in result.reason.lower() or "dimension" in result.reason.lower() or "failed" in result.reason.lower()


@pytest.mark.asyncio
async def test_dimensions_present_in_score(tmp_cache_dir, clean_python_code):
    gate = CodeQualityGate(threshold=60.0, use_llm=False, cache_enabled=False)
    result = await gate.evaluate(clean_python_code)
    assert len(result.score.dimensions) >= 4  # code gate has 5 dimensions


# === run_quality_gate convenience function tests ===


@pytest.mark.asyncio
async def test_run_quality_gate_auto_proposal(tmp_cache_dir):
    result = await run_quality_gate(
        proposal_description="Refactor the scoring pipeline to add quality gates.",
        proposal_diff="+ new line\n+ another",
        proposal_component="dharma_swarm/evolution.py",
        use_llm=False,
        cache_enabled=False,
    )
    assert isinstance(result, QualityGateResult)
    assert result.score.domain == QualityDomain.PROPOSAL


@pytest.mark.asyncio
async def test_run_quality_gate_auto_code(tmp_cache_dir, clean_python_code):
    result = await run_quality_gate(
        proposal_description="Add calculator module",
        code=clean_python_code,
        use_llm=False,
        cache_enabled=False,
    )
    assert isinstance(result, QualityGateResult)
    assert result.score.domain == QualityDomain.CODE


@pytest.mark.asyncio
async def test_run_quality_gate_explicit_domain(tmp_cache_dir, research_text):
    result = await run_quality_gate(
        proposal_description=research_text,
        domain=QualityDomain.RESEARCH,
        use_llm=False,
        cache_enabled=False,
    )
    assert result.score.domain == QualityDomain.RESEARCH


# === LLM evaluation tests (mocked) ===


@pytest.mark.asyncio
async def test_llm_evaluation_success(tmp_cache_dir):
    """Test LLM-as-judge path with mocked provider."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "dimensions": [
            {"name": "correctness", "score": 85, "feedback": "Good logic"},
            {"name": "style", "score": 80, "feedback": "Clean"},
        ],
        "overall": 82,
        "feedback": "Well-structured code",
        "suggestions": ["Add type hints"],
    })
    mock_response.model = "test-model"

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=mock_response)

    gate = CodeQualityGate(
        threshold=60.0,
        use_llm=True,
        provider=mock_provider,
        cache_enabled=False,
    )
    result = await gate.evaluate("def hello(): pass")
    assert result.passed is True
    assert result.score.evaluator == "llm"
    assert result.score.overall == 82.0


@pytest.mark.asyncio
async def test_llm_evaluation_uses_canonical_openrouter_free_default_model(tmp_cache_dir):
    captured: dict[str, object] = {}
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "dharma_swarm.quality_gates.canonical_default_model",
        lambda provider: "judge-model-from-helper",
    )

    async def _complete(request):
        captured["model"] = request.model
        return MagicMock(
            content=json.dumps({
                "dimensions": [{"name": "correctness", "score": 85, "feedback": "Good"}],
                "overall": 82,
                "feedback": "Well-structured code",
                "suggestions": [],
            }),
            model="judge-model",
        )

    mock_provider = MagicMock()
    mock_provider.complete = _complete

    gate = CodeQualityGate(
        threshold=60.0,
        use_llm=True,
        provider=mock_provider,
        cache_enabled=False,
    )

    result = await gate.evaluate("def hello(): pass")

    assert result.score.evaluator == "llm"
    assert captured["model"] == "judge-model-from-helper"
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_llm_evaluation_fallback_on_failure(tmp_cache_dir):
    """When LLM call fails, fall back to structural evaluation."""
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=RuntimeError("API down"))

    gate = CodeQualityGate(
        threshold=60.0,
        use_llm=True,
        provider=mock_provider,
        cache_enabled=False,
    )
    result = await gate.evaluate("def hello(): pass")
    assert result.score.evaluator == "structural"


@pytest.mark.asyncio
async def test_llm_no_provider_uses_structural(tmp_cache_dir):
    """When no provider is given, use structural evaluation."""
    gate = CodeQualityGate(
        threshold=60.0,
        use_llm=True,
        provider=None,
        cache_enabled=False,
    )
    result = await gate.evaluate("def hello(): pass")
    assert result.score.evaluator == "structural"


# === Darwin Engine integration tests ===


@pytest.mark.asyncio
async def test_darwin_engine_quality_gate_integration(tmp_path):
    """Test that quality gate integrates with DarwinEngine.evaluate flow."""
    from dharma_swarm.evolution import DarwinEngine, EvolutionStatus, Proposal

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
        quality_gate_threshold=60.0,
        quality_gate_enabled=True,
        quality_gate_use_llm=False,
    )

    # Create a proposal with decent description
    proposal = Proposal(
        component="dharma_swarm/models.py",
        change_type="mutation",
        description=(
            "Add type validation to the LLMRequest model to catch malformed "
            "messages before they reach the provider layer. This improves "
            "error reporting and prevents silent failures in the completion "
            "pipeline. Includes tests for all validation paths."
        ),
        diff="+ from pydantic import validator\n+ @validator('messages')\n+ def check_messages(cls, v):\n+     return v",
    )

    # Run quality gate directly
    result = await engine._run_quality_gate(proposal)
    assert isinstance(result, QualityGateResult)
    assert result.score.overall > 0.0


@pytest.mark.asyncio
async def test_darwin_engine_quality_gate_disabled(tmp_path):
    """Quality gate should be skippable via config."""
    from dharma_swarm.evolution import DarwinEngine

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
        quality_gate_enabled=False,
    )
    assert engine._quality_gate_enabled is False


# === Evaluation logging tests ===


def test_evaluation_log_written(tmp_cache_dir):
    """Verify evaluation log is persisted."""
    from dharma_swarm.quality_gates import _log_evaluation

    score = QualityScore(
        domain=QualityDomain.CODE,
        overall=75.0,
        verdict=QualityVerdict.PASS,
        artifact_hash="test_hash_1234__",
        dimensions=[DimensionScore(name="test", score=75.0)],
    )
    _log_evaluation(score, 60.0)

    log_file = tmp_cache_dir / "log" / "evaluations.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["overall"] == 75.0
    assert entry["verdict"] == "pass"
    assert entry["domain"] == "code"
