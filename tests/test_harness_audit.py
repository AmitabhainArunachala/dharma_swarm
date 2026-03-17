"""Tests for the Harness Audit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from dharma_swarm.harness_audit import (
    AuditScore,
    AuditReport,
    run_audit,
    save_audit,
    load_audit_history,
    load_latest_audit,
    format_scorecard,
    format_audit_trend,
    cmd_audit,
    cmd_audit_trend,
    _score_tool_coverage,
    _score_context_efficiency,
    _score_eval_coverage,
    _score_cost_efficiency,
)


class TestAuditScore:
    def test_defaults(self):
        s = AuditScore(name="test")
        assert s.name == "test"
        assert s.score == 0.0
        assert s.max_score == 10.0

    def test_to_dict(self):
        s = AuditScore(name="foo", score=7.5, details={"k": "v"})
        d = s.to_dict()
        assert d["name"] == "foo"
        assert d["score"] == 7.5
        assert d["details"]["k"] == "v"


class TestAuditReport:
    def test_defaults(self):
        r = AuditReport()
        assert r.overall_score == 0.0
        assert r.categories == []

    def test_to_dict(self):
        r = AuditReport(overall_score=6.5, timestamp="2026-03-17T00:00:00")
        d = r.to_dict()
        assert d["overall_score"] == 6.5


class TestScorers:
    def test_tool_coverage(self):
        result = _score_tool_coverage()
        assert result.name == "tool_coverage"
        assert 0.0 <= result.score <= 10.0
        assert "total_modules" in result.details

    def test_context_efficiency(self):
        result = _score_context_efficiency()
        assert result.name == "context_efficiency"
        assert 0.0 <= result.score <= 10.0

    def test_eval_coverage_no_data(self, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.ecc_eval_harness.load_latest",
            lambda: None,
        )
        result = _score_eval_coverage()
        assert result.name == "eval_coverage"
        assert result.score == 0.0

    def test_eval_coverage_with_data(self, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.ecc_eval_harness.load_latest",
            lambda: {"total": 9, "passed": 8, "failed": 1},
        )
        result = _score_eval_coverage()
        assert result.name == "eval_coverage"
        assert result.score > 0.0

    def test_cost_efficiency_no_archive(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.STATE_DIR", tmp_path)
        result = _score_cost_efficiency()
        assert result.name == "cost_efficiency"


class TestRunAudit:
    def test_produces_7_categories(self):
        report = run_audit()
        assert len(report.categories) == 7
        assert report.overall_score >= 0.0
        assert report.timestamp != ""

    def test_all_categories_named(self):
        report = run_audit()
        names = {c["name"] for c in report.categories}
        expected = {
            "tool_coverage", "context_efficiency", "quality_gates",
            "memory_persistence", "eval_coverage", "security_guardrails",
            "cost_efficiency",
        }
        assert names == expected


class TestPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDITS_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDIT_HISTORY",
                            tmp_path / "history.jsonl")

        report = AuditReport(
            timestamp="2026-03-17T00:00:00",
            overall_score=7.0,
            categories=[{"name": "test", "score": 7.0, "max_score": 10.0, "details": {}}],
        )
        save_audit(report)

        latest = json.loads((tmp_path / "latest.json").read_text())
        assert latest["overall_score"] == 7.0

        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1

    def test_load_history_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDIT_HISTORY",
                            tmp_path / "nope.jsonl")
        assert load_audit_history() == []

    def test_load_latest_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDITS_DIR", tmp_path)
        assert load_latest_audit() is None


class TestFormatting:
    def test_scorecard(self):
        report = {
            "timestamp": "2026-03-17T04:30:00",
            "overall_score": 6.5,
            "duration_seconds": 1.0,
            "categories": [
                {"name": "tool_coverage", "score": 7.0, "max_score": 10.0,
                 "details": {}},
                {"name": "quality_gates", "score": 5.0, "max_score": 10.0,
                 "details": {"error": "gate load failed"}},
            ],
        }
        text = format_scorecard(report)
        assert "6.5/10" in text
        assert "tool_coverage" in text
        assert "gate load failed" in text

    def test_trend_empty(self):
        text = format_audit_trend([])
        assert "No audit history" in text

    def test_trend_with_data(self):
        history = [
            {"timestamp": "2026-03-17T00:00:00", "overall_score": 6.0},
        ]
        text = format_audit_trend(history)
        assert "Audit Trend" in text
        assert "6.0/10" in text


class TestCLI:
    def test_cmd_audit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDITS_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDIT_HISTORY",
                            tmp_path / "history.jsonl")
        rc = cmd_audit()
        assert rc == 0
        assert (tmp_path / "latest.json").exists()

    def test_cmd_audit_trend(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.harness_audit.AUDIT_HISTORY",
                            tmp_path / "nope.jsonl")
        rc = cmd_audit_trend()
        assert rc == 0
