"""Tests for Phase 3 eval plane modules: eval_trace, benchmark_registry,
new evals, and eval dashboard."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest


# ── eval_trace.py ──────────────────────────────────────────────────────

class TestEvalTrace:
    def test_valid_sources(self):
        from dharma_swarm.eval_trace import EvalTrace
        for src in ("eval", "health", "inference", "flywheel", "hook"):
            t = EvalTrace(timestamp=time.time(), source=src, name="x", passed=True, value=0.0)
            assert t.source == src

    def test_invalid_source_raises(self):
        from dharma_swarm.eval_trace import EvalTrace
        with pytest.raises(ValueError, match="source must be one of"):
            EvalTrace(timestamp=time.time(), source="bogus", name="x", passed=True, value=0.0)

    def test_to_jsonl_line_roundtrips(self):
        from dharma_swarm.eval_trace import EvalTrace
        t = EvalTrace(timestamp=1.0, source="eval", name="test", passed=True, value=0.5)
        line = t.to_jsonl_line()
        parsed = json.loads(line)
        assert parsed["source"] == "eval"
        assert parsed["value"] == 0.5

    def test_from_eval_result(self):
        from dharma_swarm.eval_trace import EvalTrace
        t = EvalTrace.from_eval_result("my_eval", passed=True, duration_s=1.23)
        assert t.source == "eval"
        assert t.name == "my_eval"
        assert t.passed is True
        assert t.value == 1.23

    def test_from_prediction_error(self):
        from dharma_swarm.eval_trace import EvalTrace
        t = EvalTrace.from_prediction_error(agent="alpha", error=0.42, free_energy=1.0)
        assert t.source == "inference"
        assert "alpha" in t.name
        assert t.passed is None

    def test_from_health_anomaly(self):
        from dharma_swarm.eval_trace import EvalTrace
        t = EvalTrace.from_health_anomaly(anomaly_type="drift", severity=0.8)
        assert t.source == "health"
        assert t.passed is False
        assert t.value == 0.8


class TestTraceLog:
    def test_append_and_recent(self, tmp_path):
        from dharma_swarm.eval_trace import EvalTrace, TraceLog
        log = TraceLog(path=tmp_path / "traces.jsonl")
        t1 = EvalTrace.from_eval_result("e1", True, 0.1)
        t2 = EvalTrace.from_eval_result("e2", False, 0.2)
        log.append(t1)
        log.append(t2)
        recent = log.recent(10)
        assert len(recent) == 2
        assert recent[0].name == "e1"
        assert recent[1].name == "e2"

    def test_recent_empty(self, tmp_path):
        from dharma_swarm.eval_trace import TraceLog
        log = TraceLog(path=tmp_path / "nonexistent.jsonl")
        assert log.recent() == []

    def test_summary_counts(self, tmp_path):
        from dharma_swarm.eval_trace import EvalTrace, TraceLog
        log = TraceLog(path=tmp_path / "traces.jsonl")
        log.append(EvalTrace.from_eval_result("a", True, 0.1))
        log.append(EvalTrace.from_eval_result("b", False, 0.1))
        log.append(EvalTrace.from_health_anomaly("drift", 0.5))
        s = log.summary()
        assert s["by_source"]["eval"] == 2
        assert s["by_source"]["health"] == 1
        assert s["eval_pass_rate"] == 0.5


# ── benchmark_registry.py ─────────────────────────────────────────────

class TestBenchmarkRegistry:
    def test_default_benchmarks_seeded(self, tmp_path):
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        reg = BenchmarkRegistry(path=tmp_path / "bm.json")
        assert len(reg) == 4
        assert "gate_pass_rate" in reg
        assert "eval_pass_rate" in reg

    def test_register_and_check(self, tmp_path):
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        reg = BenchmarkRegistry(path=tmp_path / "bm.json")
        reg.register("custom", "ratio", baseline=0.9, threshold=0.8)
        assert reg.check("custom", 0.85) is True
        assert reg.check("custom", 0.75) is False

    def test_update_and_report(self, tmp_path):
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        reg = BenchmarkRegistry(path=tmp_path / "bm.json")
        reg.update("gate_pass_rate", 0.6)
        report = reg.report()
        gpr = [r for r in report if r["name"] == "gate_pass_rate"][0]
        assert gpr["status"] == "regression"
        assert gpr["last_value"] == 0.6

    def test_persistence_roundtrip(self, tmp_path):
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        path = tmp_path / "bm.json"
        reg1 = BenchmarkRegistry(path=path)
        reg1.register("new_bm", "count", baseline=100, threshold=80)
        # Reload from disk
        reg2 = BenchmarkRegistry(path=path)
        assert "new_bm" in reg2
        assert len(reg2) == 5  # 4 defaults + 1 custom

    def test_check_unknown_raises(self, tmp_path):
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        reg = BenchmarkRegistry(path=tmp_path / "bm.json")
        with pytest.raises(KeyError):
            reg.check("nonexistent", 1.0)


# ── New feedback-loop evals ───────────────────────────────────────────

class TestFeedbackLoopEvals:
    def test_health_monitoring_eval(self):
        from dharma_swarm.ecc_eval_harness import eval_health_monitoring
        r = eval_health_monitoring()
        assert r.name == "health_monitoring"
        assert r.passed is True

    def test_signal_bus_eval(self):
        from dharma_swarm.ecc_eval_harness import eval_signal_bus_flow
        r = eval_signal_bus_flow()
        assert r.name == "signal_bus_flow"
        assert r.passed is True

    def test_hook_bridge_eval(self):
        from dharma_swarm.ecc_eval_harness import eval_hook_bridge
        r = eval_hook_bridge()
        assert r.name == "hook_bridge"
        assert r.passed is True

    def test_training_flywheel_eval(self):
        from dharma_swarm.ecc_eval_harness import eval_training_flywheel_imports
        r = eval_training_flywheel_imports()
        assert r.name == "training_flywheel_imports"
        # May or may not pass depending on environment; just check it runs
        assert isinstance(r.passed, bool)

    def test_active_inference_eval(self):
        from dharma_swarm.ecc_eval_harness import eval_active_inference_flow
        r = eval_active_inference_flow()
        assert r.name == "active_inference_flow"
        assert isinstance(r.passed, bool)


# ── Dashboard ─────────────────────────────────────────────────────────

class TestDashboard:
    def test_dashboard_returns_zero(self):
        from dharma_swarm.ecc_eval_harness import cmd_eval_dashboard
        rc = cmd_eval_dashboard()
        assert rc == 0

    def test_format_scorecard(self):
        from dharma_swarm.ecc_eval_harness import format_scorecard
        report = {
            "timestamp": "2026-01-01T00:00:00",
            "total": 2,
            "passed": 1,
            "failed": 1,
            "pass_at_1": 0.5,
            "duration_seconds": 1.0,
            "results": [
                {"name": "a", "passed": True, "duration_seconds": 0.1, "error": ""},
                {"name": "b", "passed": False, "duration_seconds": 0.2, "error": "boom"},
            ],
        }
        text = format_scorecard(report)
        assert "PASS" in text
        assert "FAIL" in text
        assert "boom" in text
