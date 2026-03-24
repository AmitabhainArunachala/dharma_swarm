"""Tests for dharma_verify scoring engine."""

from __future__ import annotations

from dharma_swarm.verify.scorer import DiffScore, score_diff


class TestScoreDiff:
    def test_empty_diff(self):
        result = score_diff("")
        assert isinstance(result, DiffScore)
        assert result.overall == 0.0

    def test_simple_code(self):
        diff = (
            "diff --git a/app.py b/app.py\n"
            "+++ b/app.py\n"
            "+def hello():\n"
            "+    return 'world'\n"
        )
        result = score_diff(diff)
        assert result.overall > 0.0
        assert "correctness" in result.dimensions

    def test_detects_secrets(self):
        diff = (
            "diff --git a/bad.py b/bad.py\n"
            "+++ b/bad.py\n"
            "+api_key = 'sk-SUPERSECRETKEY1234567890abcdef'\n"
        )
        result = score_diff(diff)
        assert any("CRITICAL" in i for i in result.issues)
        assert result.dimensions.get("safety", 1.0) < 1.0

    def test_detects_eval(self):
        diff = (
            "diff --git a/evil.py b/evil.py\n"
            "+++ b/evil.py\n"
            "+result = eval(user_input)\n"
        )
        result = score_diff(diff)
        assert any("eval" in i.lower() for i in result.issues)

    def test_detects_no_tests(self):
        diff = (
            "diff --git a/feature.py b/feature.py\n"
            "+++ b/feature.py\n"
            "+def complex_function(x, y):\n"
            "+    return x * y + 1\n"
        )
        result = score_diff(diff)
        assert result.dimensions.get("correctness", 1.0) < 0.8

    def test_governance_protected_files(self):
        diff = (
            "diff --git a/telos_gates.py b/telos_gates.py\n"
            "+++ b/telos_gates.py\n"
            "+# Modified protected file\n"
        )
        result = score_diff(diff)
        assert result.dimensions.get("governance", 1.0) < 1.0
        assert any("protected" in i.lower() for i in result.issues)

    def test_dimensions_present(self):
        diff = (
            "diff --git a/x.py b/x.py\n"
            "+++ b/x.py\n"
            "+x = 1\n"
        )
        result = score_diff(diff)
        expected_dims = {"correctness", "clarity", "safety", "completeness", "efficiency", "governance"}
        assert expected_dims.issubset(set(result.dimensions.keys()))

    def test_score_bounded(self):
        diff = (
            "diff --git a/x.py b/x.py\n"
            "+++ b/x.py\n"
            "+x = 1\n"
        )
        result = score_diff(diff)
        assert 0.0 <= result.overall <= 1.0
        for v in result.dimensions.values():
            assert 0.0 <= v <= 1.0
