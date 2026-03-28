"""Tests for dharma_swarm.eval_trace — EvalTrace + TraceLog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.eval_trace import EvalTrace, TraceLog, _VALID_SOURCES


# ---------------------------------------------------------------------------
# EvalTrace dataclass
# ---------------------------------------------------------------------------

class TestEvalTrace:
    def test_valid_sources(self):
        assert _VALID_SOURCES == {"eval", "health", "inference", "flywheel", "hook"}

    def test_create_eval_trace(self):
        t = EvalTrace(timestamp=1.0, source="eval", name="test_x", passed=True, value=0.5)
        assert t.source == "eval"
        assert t.passed is True

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="source must be one of"):
            EvalTrace(timestamp=1.0, source="bogus", name="x", passed=None, value=0.0)

    def test_to_jsonl_line(self):
        t = EvalTrace(timestamp=1.0, source="eval", name="t1", passed=True, value=2.0)
        line = t.to_jsonl_line()
        parsed = json.loads(line)
        assert parsed["source"] == "eval"
        assert parsed["name"] == "t1"
        assert parsed["passed"] is True
        assert "\n" not in line

    def test_from_eval_result(self):
        t = EvalTrace.from_eval_result("my_test", passed=True, duration_s=1.5)
        assert t.source == "eval"
        assert t.name == "my_test"
        assert t.passed is True
        assert t.value == 1.5
        assert t.metadata["unit"] == "seconds"

    def test_from_prediction_error(self):
        t = EvalTrace.from_prediction_error("agent_1", error=0.3, free_energy=1.2)
        assert t.source == "inference"
        assert "agent_1" in t.name
        assert t.passed is None
        assert t.value == 0.3
        assert t.metadata["free_energy"] == 1.2

    def test_from_health_anomaly(self):
        t = EvalTrace.from_health_anomaly("high_cpu", severity=0.8)
        assert t.source == "health"
        assert "high_cpu" in t.name
        assert t.passed is False
        assert t.value == 0.8

    def test_metadata_default_empty(self):
        t = EvalTrace(timestamp=1.0, source="hook", name="x", passed=None, value=0.0)
        assert t.metadata == {}


# ---------------------------------------------------------------------------
# TraceLog
# ---------------------------------------------------------------------------

class TestTraceLog:
    def test_append_creates_file(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "traces.jsonl")
        t = EvalTrace(timestamp=1.0, source="eval", name="t1", passed=True, value=0.1)
        log.append(t)
        assert log.path.exists()
        assert log.path.read_text().strip()

    def test_append_multiple(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "traces.jsonl")
        for i in range(5):
            log.append(EvalTrace(timestamp=float(i), source="eval", name=f"t{i}", passed=True, value=0.0))
        lines = log.path.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_recent_returns_last_n(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "traces.jsonl")
        for i in range(10):
            log.append(EvalTrace(timestamp=float(i), source="eval", name=f"t{i}", passed=True, value=0.0))
        recent = log.recent(3)
        assert len(recent) == 3
        assert recent[0].name == "t7"
        assert recent[2].name == "t9"

    def test_recent_empty_file(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "nonexistent.jsonl")
        assert log.recent() == []

    def test_recent_handles_corrupt_lines(self, tmp_path: Path):
        p = tmp_path / "traces.jsonl"
        t = EvalTrace(timestamp=1.0, source="eval", name="good", passed=True, value=0.0)
        p.write_text(t.to_jsonl_line() + "\n" + "NOT JSON\n")
        log = TraceLog(path=p)
        result = log.recent(10)
        assert len(result) == 1
        assert result[0].name == "good"

    def test_summary_counts_by_source(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "traces.jsonl")
        log.append(EvalTrace(timestamp=1.0, source="eval", name="a", passed=True, value=0.0))
        log.append(EvalTrace(timestamp=2.0, source="eval", name="b", passed=False, value=0.0))
        log.append(EvalTrace(timestamp=3.0, source="health", name="c", passed=False, value=0.5))
        s = log.summary()
        assert s["by_source"]["eval"] == 2
        assert s["by_source"]["health"] == 1
        assert s["eval_pass_rate"] == 0.5

    def test_summary_empty(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "empty.jsonl")
        s = log.summary()
        assert s["eval_pass_rate"] is None
        assert s["by_source"] == {}

    def test_summary_all_passed(self, tmp_path: Path):
        log = TraceLog(path=tmp_path / "traces.jsonl")
        for i in range(3):
            log.append(EvalTrace(timestamp=float(i), source="eval", name=f"t{i}", passed=True, value=0.0))
        s = log.summary()
        assert s["eval_pass_rate"] == 1.0

    def test_default_path(self):
        log = TraceLog()
        assert "dharma" in str(log.path)
        assert "evals" in str(log.path)
