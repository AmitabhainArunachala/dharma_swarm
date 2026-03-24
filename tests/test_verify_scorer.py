"""Tests for dharma_swarm.verify.scorer."""

from __future__ import annotations

import pytest

from dharma_swarm.verify.scorer import DiffScore, score_diff, score_diff_with_llm


# ---------------------------------------------------------------------------
# Realistic unified diffs for testing
# ---------------------------------------------------------------------------

CLEAN_DIFF = (
    "diff --git a/src/utils.py b/src/utils.py\n"
    "+++ b/src/utils.py\n"
    '+"""Utility functions for data processing."""\n'
    "+\n"
    "+from __future__ import annotations\n"
    "+\n"
    "+\n"
    "+def normalize(values: list[float]) -> list[float]:\n"
    '+    """Normalize a list of floats to [0, 1] range."""\n'
    "+    if not values:\n"
    "+        return []\n"
    "+    lo, hi = min(values), max(values)\n"
    "+    if hi == lo:\n"
    "+        return [0.5] * len(values)\n"
    "+    return [(v - lo) / (hi - lo) for v in values]\n"
    "diff --git a/tests/test_utils.py b/tests/test_utils.py\n"
    "+++ b/tests/test_utils.py\n"
    "+import pytest\n"
    "+from src.utils import normalize\n"
    "+\n"
    "+def test_normalize_basic():\n"
    "+    assert normalize([1.0, 2.0, 3.0]) == [0.0, 0.5, 1.0]\n"
    "+\n"
    "+def test_normalize_empty():\n"
    "+    assert normalize([]) == []\n"
)

UNSAFE_DIFF = (
    "diff --git a/src/runner.py b/src/runner.py\n"
    "+++ b/src/runner.py\n"
    "+import os\n"
    "+\n"
    "+def run_user_code(code_str):\n"
    "+    result = eval(code_str)\n"
    "+    return result\n"
    "+\n"
    "+def execute_command(cmd):\n"
    "+    exec(cmd)\n"
    '+    api_key = "sk-abc123def456ghi789jkl012mno345pqr678stu901vwx"\n'
)

NO_TESTS_DIFF = (
    "diff --git a/src/service.py b/src/service.py\n"
    "+++ b/src/service.py\n"
    "+import requests\n"
    "+\n"
    "+def fetch_data(url):\n"
    "+    response = requests.get(url)\n"
    "+    data = response.json()\n"
    "+    items = []\n"
    "+    for item in data:\n"
    "+        for sub in item['children']:\n"
    "+            items.append(sub['value'])\n"
    "+    return items\n"
)

GOVERNANCE_DIFF = (
    "diff --git a/dharma_swarm/telos_gates.py b/dharma_swarm/telos_gates.py\n"
    "+++ b/dharma_swarm/telos_gates.py\n"
    "+def bypass_gate(gate_name: str) -> bool:\n"
    "+    return True\n"
)


class TestScoreDiff:
    """Tests for the heuristic diff scorer."""

    def test_returns_diff_score(self) -> None:
        result = score_diff(CLEAN_DIFF)
        assert isinstance(result, DiffScore)

    def test_clean_code_scores_above_half(self) -> None:
        result = score_diff(CLEAN_DIFF)
        assert result.overall >= 0.5

    def test_clean_code_safety_high(self) -> None:
        result = score_diff(CLEAN_DIFF)
        assert result.dimensions["safety"] >= 0.8

    def test_unsafe_code_safety_penalty(self) -> None:
        result = score_diff(UNSAFE_DIFF)
        assert result.dimensions["safety"] < 0.5

    def test_eval_detected_in_issues(self) -> None:
        result = score_diff(UNSAFE_DIFF)
        assert any("eval" in i.lower() for i in result.issues)

    def test_exec_detected_in_issues(self) -> None:
        result = score_diff(UNSAFE_DIFF)
        assert any("exec" in i.lower() for i in result.issues)

    def test_hardcoded_secret_detected(self) -> None:
        result = score_diff(UNSAFE_DIFF)
        assert any("secret" in i.lower() or "key" in i.lower() for i in result.issues)

    def test_no_tests_correctness_penalty(self) -> None:
        result = score_diff(NO_TESTS_DIFF)
        assert result.dimensions["correctness"] < 0.5

    def test_no_tests_suggests_adding_tests(self) -> None:
        result = score_diff(NO_TESTS_DIFF)
        assert any("test" in s.lower() for s in result.suggestions)

    def test_governance_protected_file(self) -> None:
        result = score_diff(GOVERNANCE_DIFF)
        assert result.dimensions["governance"] < 0.5

    def test_governance_issue_raised(self) -> None:
        result = score_diff(GOVERNANCE_DIFF)
        assert any("protected" in i.lower() or "governance" in i.lower() for i in result.issues)

    def test_empty_diff_returns_zero(self) -> None:
        result = score_diff("")
        assert result.overall == 0.0
        assert any("empty" in i.lower() for i in result.issues)

    def test_overall_is_weighted_average(self) -> None:
        result = score_diff(CLEAN_DIFF)
        weights = {
            "correctness": 0.25, "clarity": 0.15, "safety": 0.20,
            "completeness": 0.15, "efficiency": 0.10, "governance": 0.15,
        }
        expected = sum(result.dimensions[d] * w for d, w in weights.items())
        assert abs(result.overall - round(expected, 4)) < 0.001

    def test_all_six_dimensions_present(self) -> None:
        result = score_diff(CLEAN_DIFF)
        expected = {"correctness", "clarity", "safety", "completeness", "efficiency", "governance"}
        assert set(result.dimensions.keys()) == expected

    def test_all_scores_bounded(self) -> None:
        for diff in [CLEAN_DIFF, UNSAFE_DIFF, NO_TESTS_DIFF, GOVERNANCE_DIFF]:
            result = score_diff(diff)
            assert 0.0 <= result.overall <= 1.0
            for v in result.dimensions.values():
                assert 0.0 <= v <= 1.0

    def test_context_parameter_accepted(self) -> None:
        result = score_diff(CLEAN_DIFF, context="Feature: normalize utility")
        assert isinstance(result, DiffScore)


class TestScoreDiffWithLLM:
    """Tests for the LLM-enhanced scorer."""

    def test_successful_llm_parse(self) -> None:
        def mock_llm(prompt: str) -> str:
            return (
                "correctness: 0.9\n"
                "clarity: 0.85\n"
                "safety: 0.95\n"
                "completeness: 0.8\n"
                "efficiency: 0.7\n"
                "governance: 1.0\n"
                "issues: Minor naming concern\n"
                "suggestions: Consider adding logging\n"
            )

        result = score_diff_with_llm(CLEAN_DIFF, "context", mock_llm)
        assert result.dimensions["correctness"] == 0.9
        assert result.dimensions["safety"] == 0.95
        assert "Minor naming concern" in result.issues
        assert "Consider adding logging" in result.suggestions

    def test_llm_failure_falls_back_to_heuristic(self) -> None:
        def failing_llm(prompt: str) -> str:
            raise RuntimeError("LLM unavailable")

        result = score_diff_with_llm(CLEAN_DIFF, "", failing_llm)
        assert isinstance(result, DiffScore)
        assert 0.0 <= result.overall <= 1.0
        assert len(result.dimensions) == 6

    def test_partial_llm_response_fills_defaults(self) -> None:
        def partial_llm(prompt: str) -> str:
            return "correctness: 0.7\nsafety: 0.3\n"

        result = score_diff_with_llm(CLEAN_DIFF, "", partial_llm)
        assert result.dimensions["correctness"] == 0.7
        assert result.dimensions["safety"] == 0.3
        assert result.dimensions["clarity"] == 0.5  # default fill
