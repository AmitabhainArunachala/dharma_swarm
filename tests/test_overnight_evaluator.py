"""Tests for dharma_swarm.overnight_evaluator -- Overnight Evaluator."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.overnight_evaluator import (
    CycleEvaluation,
    CycleResult,
    NightEvaluation,
    OperatorVerdict,
    OvernightEvaluator,
    VerdictReport,
    compute_verdict,
    _parse_coverage_percent,
    _parse_pytest_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cycle_result(
    *,
    cycle_id: str = "c1",
    task_id: str = "t1",
    tokens_spent: int = 1000,
    files_modified: list[str] | None = None,
    test_results: dict | None = None,
    acceptance_passed: bool = True,
    duration: float = 60.0,
    error: str | None = None,
) -> CycleResult:
    """Build a CycleResult with sensible defaults."""
    now = time.time()
    return CycleResult(
        cycle_id=cycle_id,
        task_id=task_id,
        started_at=now - duration,
        completed_at=now,
        tokens_spent=tokens_spent,
        files_modified=files_modified or [],
        test_results=test_results,
        acceptance_passed=acceptance_passed,
        error=error,
    )


def _mock_subprocess_run_factory(
    stdout: str = "42 passed\n",
    returncode: int = 0,
):
    """Return a function suitable for patching subprocess.run."""

    def _mock_run(*args, **kwargs):
        class _Result:
            pass

        r = _Result()
        r.stdout = stdout
        r.stderr = ""
        r.returncode = returncode
        return r

    return _mock_run


# ---------------------------------------------------------------------------
# Pytest summary parsing
# ---------------------------------------------------------------------------


class TestParsePytestSummary:
    def test_passed_only(self) -> None:
        result = _parse_pytest_summary("42 passed\n")
        assert result == {"passed": 42, "failed": 0}

    def test_passed_and_failed(self) -> None:
        result = _parse_pytest_summary("40 passed, 2 failed\n")
        assert result == {"passed": 40, "failed": 2}

    def test_no_match(self) -> None:
        result = _parse_pytest_summary("no tests ran")
        assert result == {"passed": 0, "failed": 0}

    def test_extra_text(self) -> None:
        output = "===== 100 passed, 3 failed, 2 warnings in 45.2s ====="
        result = _parse_pytest_summary(output)
        assert result["passed"] == 100
        assert result["failed"] == 3


class TestParseCoveragePercent:
    def test_valid_json(self) -> None:
        text = '{"totals": {"percent_covered": 87.5}}'
        assert _parse_coverage_percent(text) == 87.5

    def test_no_match(self) -> None:
        assert _parse_coverage_percent("{}") is None


# ---------------------------------------------------------------------------
# CycleResult dataclass
# ---------------------------------------------------------------------------


class TestCycleResult:
    def test_cycle_result_creation(self) -> None:
        """Dataclass instantiation with all fields."""
        cr = _make_cycle_result(
            cycle_id="test-1",
            task_id="task-a",
            tokens_spent=500,
            files_modified=["a.py", "b.py"],
            acceptance_passed=False,
            error="oops",
        )
        assert cr.cycle_id == "test-1"
        assert cr.task_id == "task-a"
        assert cr.tokens_spent == 500
        assert cr.files_modified == ["a.py", "b.py"]
        assert cr.acceptance_passed is False
        assert cr.error == "oops"
        assert cr.completed_at > cr.started_at

    def test_cycle_result_defaults(self) -> None:
        """Defaults produce a valid object."""
        cr = _make_cycle_result()
        assert cr.cycle_id == "c1"
        assert cr.error is None


# ---------------------------------------------------------------------------
# evaluate_cycle
# ---------------------------------------------------------------------------


class TestEvaluateCycle:
    def test_evaluate_cycle_with_state_changes(self, tmp_path: Path) -> None:
        """Cycle with file changes is not dead."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": 80.0}
        evaluator._last_snapshot = {"passed": 100, "failed": 0}

        result = _make_cycle_result(
            files_modified=["foo.py", "bar.py"],
            test_results={"passed": 103, "failed": 0},
        )
        ev = evaluator.evaluate_cycle("c1", result)

        assert ev.state_changes_count == 2
        assert ev.test_delta == 3
        assert ev.is_dead_cycle is False
        assert ev.verified is True
        assert ev.token_efficiency == 2 / 1000

    def test_evaluate_cycle_dead(self, tmp_path: Path) -> None:
        """Cycle with 0 file changes is dead."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0}
        evaluator._last_snapshot = {"passed": 100, "failed": 0}

        result = _make_cycle_result(
            files_modified=[],
            tokens_spent=5000,
            acceptance_passed=False,
        )
        ev = evaluator.evaluate_cycle("c-dead", result)

        assert ev.state_changes_count == 0
        assert ev.is_dead_cycle is True
        assert ev.verified is False
        assert ev.token_efficiency == 0.0

    def test_cycle_persisted_to_disk(self, tmp_path: Path) -> None:
        """cycle_evals.jsonl is written on evaluate_cycle."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 10, "failed": 0}
        evaluator._last_snapshot = {"passed": 10, "failed": 0}

        result = _make_cycle_result(files_modified=["x.py"])
        evaluator.evaluate_cycle("cx", result)

        jsonl_path = tmp_path / "overnight" / "2026-03-24" / "cycle_evals.jsonl"
        assert jsonl_path.exists()
        line = json.loads(jsonl_path.read_text().strip())
        assert line["cycle_id"] == "cx"


# ---------------------------------------------------------------------------
# evaluate_night
# ---------------------------------------------------------------------------


class TestEvaluateNight:
    def test_evaluate_night_aggregation(self, tmp_path: Path) -> None:
        """Multiple cycles aggregate correctly."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": 80.0}
        evaluator._last_snapshot = {"passed": 100, "failed": 0, "coverage_percent": 80.0}

        # Cycle 1: 2 changes, +3 tests, verified
        r1 = _make_cycle_result(
            cycle_id="c1",
            files_modified=["a.py", "b.py"],
            test_results={"passed": 103, "failed": 0, "coverage_percent": 82.0},
            tokens_spent=1000,
            acceptance_passed=True,
            duration=120.0,
        )
        evaluator.evaluate_cycle("c1", r1)

        # Cycle 2: 0 changes, dead, not verified
        r2 = _make_cycle_result(
            cycle_id="c2",
            files_modified=[],
            test_results={"passed": 103, "failed": 0},
            tokens_spent=2000,
            acceptance_passed=False,
            duration=60.0,
        )
        evaluator.evaluate_cycle("c2", r2)

        # Cycle 3: 1 change, +2 tests, verified
        r3 = _make_cycle_result(
            cycle_id="c3",
            files_modified=["c.py"],
            test_results={"passed": 105, "failed": 0, "coverage_percent": 83.0},
            tokens_spent=1500,
            acceptance_passed=True,
            duration=90.0,
        )
        evaluator.evaluate_cycle("c3", r3)

        night = evaluator.evaluate_night()

        assert night.date == "2026-03-24"
        assert night.total_cycles == 3
        assert night.verified_completions == 2
        assert night.total_state_changes == 3  # 2 + 0 + 1
        assert night.test_delta == 5  # 3 + 0 + 2
        assert night.total_tokens_spent == 4500
        assert night.dead_loop_time == 60.0
        assert night.total_time == 270.0
        assert night.dead_loop_ratio == pytest.approx(60.0 / 270.0)

    def test_evaluate_night_empty(self, tmp_path: Path) -> None:
        """Night with zero cycles produces safe defaults."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        night = evaluator.evaluate_night()

        assert night.total_cycles == 0
        assert night.verified_completions == 0
        assert night.dead_loop_ratio == 0.0
        assert night.morning_capability_delta == pytest.approx(0.2)  # low dead_loop_ratio bonus


# ---------------------------------------------------------------------------
# morning_capability_delta scoring
# ---------------------------------------------------------------------------


class TestMorningCapabilityDelta:
    def test_zero_progress(self) -> None:
        """No progress, high dead loop ratio -> minimal score."""
        night = NightEvaluation(
            date="2026-03-24",
            total_cycles=5,
            verified_completions=0,
            total_state_changes=0,
            test_delta=0,
            coverage_delta=0.0,
            total_tokens_spent=10000,
            cost_per_verified_improvement=10000.0,
            dead_loop_ratio=0.8,
            dead_loop_time=400.0,
            total_time=500.0,
            token_efficiency=0.0,
            morning_capability_delta=0.0,
        )
        score = OvernightEvaluator._compute_capability_delta(night)
        assert score == 0.0

    def test_maximum_progress(self) -> None:
        """All metrics maxed -> capped at 1.0."""
        night = NightEvaluation(
            date="2026-03-24",
            total_cycles=10,
            verified_completions=10,
            total_state_changes=50,
            test_delta=20,
            coverage_delta=5.0,
            total_tokens_spent=5000,
            cost_per_verified_improvement=500.0,
            dead_loop_ratio=0.0,
            dead_loop_time=0.0,
            total_time=3600.0,
            token_efficiency=0.01,
            morning_capability_delta=0.0,
        )
        score = OvernightEvaluator._compute_capability_delta(night)
        assert score == pytest.approx(1.0)

    def test_partial_progress(self) -> None:
        """Some tests gained, one verified task, low waste."""
        night = NightEvaluation(
            date="2026-03-24",
            total_cycles=3,
            verified_completions=1,
            total_state_changes=5,
            test_delta=5,
            coverage_delta=1.0,
            total_tokens_spent=3000,
            cost_per_verified_improvement=3000.0,
            dead_loop_ratio=0.1,
            dead_loop_time=30.0,
            total_time=300.0,
            token_efficiency=0.001,
            morning_capability_delta=0.0,
        )
        score = OvernightEvaluator._compute_capability_delta(night)
        # test_delta=5 -> min(5/10, 0.4) = min(0.5, 0.4) = 0.4
        # verified=1 -> min(1/5, 0.3) = 0.2
        # dead_loop_ratio=0.1 < 0.2 -> 0.2
        # state_changes > 0 -> 0.1
        assert score == pytest.approx(0.9)

    def test_only_dead_loop_bonus(self) -> None:
        """Zero progress but low dead loop ratio still gets 0.2."""
        night = NightEvaluation(
            date="2026-03-24",
            total_cycles=1,
            verified_completions=0,
            total_state_changes=0,
            test_delta=0,
            coverage_delta=0.0,
            total_tokens_spent=100,
            cost_per_verified_improvement=100.0,
            dead_loop_ratio=0.1,
            dead_loop_time=5.0,
            total_time=50.0,
            token_efficiency=0.0,
            morning_capability_delta=0.0,
        )
        score = OvernightEvaluator._compute_capability_delta(night)
        assert score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# token_efficiency edge case
# ---------------------------------------------------------------------------


class TestTokenEfficiency:
    def test_division_by_zero(self, tmp_path: Path) -> None:
        """0 tokens spent -> efficiency = 0.0, no crash."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 10, "failed": 0}
        evaluator._last_snapshot = {"passed": 10, "failed": 0}

        result = _make_cycle_result(
            files_modified=["a.py"],
            tokens_spent=0,
        )
        ev = evaluator.evaluate_cycle("c0", result)
        # 1 / max(0, 1) = 1.0
        assert ev.token_efficiency == 1.0

    def test_zero_changes_zero_tokens(self, tmp_path: Path) -> None:
        """0 changes and 0 tokens -> efficiency = 0.0."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 10, "failed": 0}
        evaluator._last_snapshot = {"passed": 10, "failed": 0}

        result = _make_cycle_result(
            files_modified=[],
            tokens_spent=0,
        )
        ev = evaluator.evaluate_cycle("c0", result)
        assert ev.token_efficiency == 0.0


# ---------------------------------------------------------------------------
# summary_dict serialization
# ---------------------------------------------------------------------------


class TestSummaryDict:
    def test_summary_dict_serializable(self, tmp_path: Path) -> None:
        """Output of summary_dict() is JSON-serializable."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 50, "failed": 2}
        evaluator._last_snapshot = {"passed": 50, "failed": 2}

        r1 = _make_cycle_result(files_modified=["a.py"])
        evaluator.evaluate_cycle("c1", r1)

        d = evaluator.summary_dict()
        serialized = json.dumps(d)  # should not raise
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["date"] == "2026-03-24"
        assert len(parsed["cycles"]) == 1


# ---------------------------------------------------------------------------
# Disk persistence
# ---------------------------------------------------------------------------


class TestDiskPersistence:
    def test_eval_summary_written_to_disk(self, tmp_path: Path) -> None:
        """eval_summary.json exists after evaluate_night()."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 10, "failed": 0, "coverage_percent": 75.0}
        evaluator._last_snapshot = {"passed": 12, "failed": 0, "coverage_percent": 77.0}

        r1 = _make_cycle_result(files_modified=["x.py"], acceptance_passed=True)
        evaluator.evaluate_cycle("c1", r1)

        night = evaluator.evaluate_night()

        summary_path = tmp_path / "overnight" / "2026-03-24" / "eval_summary.json"
        assert summary_path.exists()

        data = json.loads(summary_path.read_text())
        assert data["date"] == "2026-03-24"
        assert data["total_cycles"] == 1
        assert data["verified_completions"] == 1

    def test_write_json_error_swallowed(self, tmp_path: Path) -> None:
        """If disk write fails, no exception propagates."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        # Force a write error by making the path a file instead of a directory
        bad_path = tmp_path / "overnight" / "2026-03-24"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text("not a directory")

        # Should not raise
        evaluator._write_json(bad_path / "eval_summary.json", {"test": True})


# ---------------------------------------------------------------------------
# Baseline / snapshot with mocked subprocess
# ---------------------------------------------------------------------------


class TestBaselineSnapshot:
    @patch("dharma_swarm.overnight_evaluator.subprocess.run")
    def test_baseline_captures_pass_count(self, mock_run, tmp_path: Path) -> None:
        """baseline() parses pytest output correctly."""
        mock_run.return_value = type(
            "_R", (), {"stdout": "150 passed, 3 failed\n", "stderr": "", "returncode": 1}
        )()

        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        b = evaluator.baseline()

        assert b["passed"] == 150
        assert b["failed"] == 3
        assert evaluator._baseline is not None
        assert evaluator._baseline["passed"] == 150

    @patch("dharma_swarm.overnight_evaluator.subprocess.run")
    def test_snapshot_does_not_overwrite_baseline(self, mock_run, tmp_path: Path) -> None:
        """snapshot() updates last_snapshot but leaves baseline intact."""
        mock_run.return_value = type(
            "_R", (), {"stdout": "200 passed\n", "stderr": "", "returncode": 0}
        )()

        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": None}
        evaluator.snapshot()

        assert evaluator._baseline["passed"] == 100  # unchanged
        assert evaluator._last_snapshot is not None
        assert evaluator._last_snapshot["passed"] == 200

    @patch(
        "dharma_swarm.overnight_evaluator.subprocess.run",
        side_effect=FileNotFoundError("pytest not found"),
    )
    def test_baseline_without_pytest(self, mock_run, tmp_path: Path) -> None:
        """Graceful failure if pytest is unavailable."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        b = evaluator.baseline()

        assert b["passed"] == 0
        assert b["failed"] == 0
        assert b["coverage_percent"] is None

    @patch(
        "dharma_swarm.overnight_evaluator.subprocess.run",
        side_effect=__import__("subprocess").TimeoutExpired(cmd="pytest", timeout=300),
    )
    def test_baseline_timeout(self, mock_run, tmp_path: Path) -> None:
        """Graceful handling when pytest times out."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        b = evaluator.baseline()

        assert b["passed"] == 0
        assert b["failed"] == 0

    @patch("dharma_swarm.overnight_evaluator.subprocess.run")
    def test_baseline_falls_back_when_pytest_cov_is_unavailable(self, mock_run, tmp_path: Path) -> None:
        """Coverage flag failure should retry without coverage and keep pass counts."""

        def _side_effect(cmd, *args, **kwargs):
            if "--cov=dharma_swarm" in cmd:
                return type(
                    "_R",
                    (),
                    {
                        "stdout": "",
                        "stderr": (
                            "python -m pytest: error: unrecognized arguments: "
                            "--cov=dharma_swarm --cov-report=json"
                        ),
                        "returncode": 4,
                    },
                )()
            return type(
                "_R",
                (),
                {"stdout": "12 passed\n", "stderr": "", "returncode": 0},
            )()

        mock_run.side_effect = _side_effect

        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        b = evaluator.baseline()

        assert mock_run.call_count == 2
        assert b["passed"] == 12
        assert b["failed"] == 0
        assert b["coverage_percent"] is None


# ---------------------------------------------------------------------------
# NightEvaluation coverage delta
# ---------------------------------------------------------------------------


class TestCoverageDelta:
    def test_coverage_delta_computed(self, tmp_path: Path) -> None:
        """Coverage delta = final snapshot coverage - baseline coverage."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": 80.0}
        evaluator._last_snapshot = {"passed": 105, "failed": 0, "coverage_percent": 83.5}

        # Add one cycle so total_cycles > 0
        r1 = _make_cycle_result(files_modified=["a.py"], test_results={"passed": 105, "failed": 0, "coverage_percent": 83.5})
        evaluator.evaluate_cycle("c1", r1)

        night = evaluator.evaluate_night()
        assert night.coverage_delta == pytest.approx(3.5)

    def test_coverage_delta_none_graceful(self, tmp_path: Path) -> None:
        """No coverage data -> delta = 0.0."""
        evaluator = OvernightEvaluator(
            date="2026-03-24", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": None}
        evaluator._last_snapshot = {"passed": 100, "failed": 0, "coverage_percent": None}

        night = evaluator.evaluate_night()
        assert night.coverage_delta == 0.0


# ---------------------------------------------------------------------------
# OperatorVerdict + compute_verdict
# ---------------------------------------------------------------------------


def _make_night(
    *,
    test_delta: int = 0,
    dead_loop_ratio: float = 0.0,
    morning_capability_delta: float = 0.0,
    verified_completions: int = 0,
    coverage_delta: float = 0.0,
    total_tokens_spent: int = 1000,
    total_cycles: int = 5,
) -> NightEvaluation:
    """Build a NightEvaluation with sensible defaults."""
    return NightEvaluation(
        date="2026-03-25",
        total_cycles=total_cycles,
        verified_completions=verified_completions,
        total_state_changes=max(verified_completions, 1),
        test_delta=test_delta,
        coverage_delta=coverage_delta,
        total_tokens_spent=total_tokens_spent,
        cost_per_verified_improvement=(
            total_tokens_spent / max(verified_completions, 1)
        ),
        dead_loop_ratio=dead_loop_ratio,
        dead_loop_time=dead_loop_ratio * 3600.0,
        total_time=3600.0,
        token_efficiency=0.001,
        morning_capability_delta=morning_capability_delta,
    )


class TestOperatorVerdict:
    def test_enum_values(self) -> None:
        assert OperatorVerdict.ADVANCE.value == "advance"
        assert OperatorVerdict.HOLD.value == "hold"
        assert OperatorVerdict.ROLLBACK.value == "rollback"

    def test_enum_is_string(self) -> None:
        """OperatorVerdict serializes as plain string."""
        assert str(OperatorVerdict.ADVANCE) == "OperatorVerdict.ADVANCE"
        assert OperatorVerdict.ADVANCE == "advance"


class TestComputeVerdict:
    # --- ROLLBACK cases ---

    def test_rollback_on_test_regression(self) -> None:
        """Losing 5+ tests triggers ROLLBACK."""
        night = _make_night(test_delta=-6)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ROLLBACK
        assert any("test regression" in r for r in report.reasons)

    def test_rollback_on_excessive_dead_loops(self) -> None:
        """80%+ dead loop ratio triggers ROLLBACK."""
        night = _make_night(dead_loop_ratio=0.85)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ROLLBACK
        assert any("dead loops" in r for r in report.reasons)

    def test_rollback_on_zero_verified_with_regression(self) -> None:
        """Zero verified + any test regression triggers ROLLBACK."""
        night = _make_night(verified_completions=0, test_delta=-1)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ROLLBACK
        assert any("zero verified" in r.lower() for r in report.reasons)

    def test_rollback_multiple_reasons(self) -> None:
        """Multiple rollback conditions all appear in reasons."""
        night = _make_night(test_delta=-10, dead_loop_ratio=0.9)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ROLLBACK
        assert len(report.reasons) >= 2

    # --- ADVANCE cases ---

    def test_advance_on_good_night(self) -> None:
        """High capability delta + verified + no regression -> ADVANCE."""
        night = _make_night(
            morning_capability_delta=0.3,
            verified_completions=3,
            test_delta=5,
        )
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ADVANCE
        assert any("ADVANCE" in r for r in report.reasons)

    def test_advance_requires_all_three_checks(self) -> None:
        """Missing any one advance check -> not ADVANCE."""
        # Good capability and verified, but test regression
        night = _make_night(
            morning_capability_delta=0.3,
            verified_completions=2,
            test_delta=-1,
        )
        report = compute_verdict(night)
        # test_delta=-1 also triggers rollback (zero verified + regression)
        # Actually -1 with verified=2, let's check: no, verified=2 so
        # the rollback check (zero verified AND regression) doesn't trigger
        # But advance requires test_delta >= 0, so it's HOLD
        assert report.verdict == OperatorVerdict.HOLD

    # --- HOLD cases ---

    def test_hold_on_mediocre_night(self) -> None:
        """Some progress but not enough for ADVANCE."""
        night = _make_night(
            morning_capability_delta=0.1,
            verified_completions=1,
            test_delta=2,
        )
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.HOLD

    def test_hold_high_dead_ratio_below_rollback(self) -> None:
        """50-80% dead ratio -> HOLD, not ROLLBACK."""
        night = _make_night(dead_loop_ratio=0.6)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.HOLD
        assert any("dead loop ratio" in r.lower() for r in report.reasons)

    def test_hold_zero_verified_no_regression(self) -> None:
        """Zero verified but no test regression -> HOLD (not ROLLBACK)."""
        night = _make_night(verified_completions=0, test_delta=0)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.HOLD

    # --- VerdictReport structure ---

    def test_verdict_report_has_scores(self) -> None:
        night = _make_night(test_delta=3, verified_completions=2)
        report = compute_verdict(night)
        assert "test_delta" in report.scores
        assert "dead_loop_ratio" in report.scores
        assert "capability_delta" in report.scores
        assert "verified_completions" in report.scores

    def test_verdict_report_has_night_eval(self) -> None:
        night = _make_night()
        report = compute_verdict(night)
        assert report.night_eval["date"] == "2026-03-25"
        assert isinstance(report.night_eval, dict)

    # --- Custom thresholds ---

    def test_custom_rollback_threshold(self) -> None:
        """Stricter rollback threshold catches smaller regressions."""
        # Use verified_completions=1 so the "zero verified + regression" check doesn't fire
        night = _make_night(test_delta=-2, verified_completions=1)
        # Default threshold is -5, so -2 would be HOLD
        report_default = compute_verdict(night)
        assert report_default.verdict != OperatorVerdict.ROLLBACK

        # Custom threshold of -1 catches it
        report_strict = compute_verdict(night, rollback_test_delta=-1)
        assert report_strict.verdict == OperatorVerdict.ROLLBACK

    def test_custom_advance_threshold(self) -> None:
        """Lower advance threshold allows easier promotion."""
        night = _make_night(
            morning_capability_delta=0.1,
            verified_completions=1,
            test_delta=0,
        )
        # Default advance_capability_delta=0.15, so 0.1 < 0.15 -> HOLD
        report_default = compute_verdict(night)
        assert report_default.verdict == OperatorVerdict.HOLD

        # Lower threshold allows ADVANCE
        report_easy = compute_verdict(night, advance_capability_delta=0.05)
        assert report_easy.verdict == OperatorVerdict.ADVANCE

    # --- Edge cases ---

    def test_empty_night_is_hold(self) -> None:
        """Zero-cycle night -> HOLD (not crash)."""
        night = _make_night(total_cycles=0, verified_completions=0, test_delta=0)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.HOLD

    def test_boundary_rollback_dead_ratio(self) -> None:
        """Exactly at rollback threshold -> ROLLBACK."""
        night = _make_night(dead_loop_ratio=0.8)
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ROLLBACK

    def test_boundary_advance_all_minimums(self) -> None:
        """Exactly at all advance thresholds -> ADVANCE."""
        night = _make_night(
            morning_capability_delta=0.15,
            verified_completions=1,
            test_delta=0,
        )
        report = compute_verdict(night)
        assert report.verdict == OperatorVerdict.ADVANCE


# ---------------------------------------------------------------------------
# Integration: evaluate_night -> compute_verdict pipeline
# ---------------------------------------------------------------------------


class TestEvalVerdictPipeline:
    def test_evaluate_night_then_verdict(self, tmp_path: Path) -> None:
        """Full pipeline: evaluator -> NightEvaluation -> compute_verdict."""
        evaluator = OvernightEvaluator(
            date="2026-03-25", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0, "coverage_percent": 80.0}
        evaluator._last_snapshot = {"passed": 100, "failed": 0, "coverage_percent": 80.0}

        # Simulate 3 productive cycles
        for i in range(3):
            r = _make_cycle_result(
                cycle_id=f"c{i}",
                files_modified=[f"mod_{i}.py"],
                test_results={"passed": 100 + (i + 1) * 3, "failed": 0},
                tokens_spent=1000,
                acceptance_passed=True,
            )
            evaluator.evaluate_cycle(f"c{i}", r)

        night = evaluator.evaluate_night()
        report = compute_verdict(night)

        # 3 verified, positive test delta, capability > 0
        assert night.verified_completions == 3
        assert night.test_delta > 0
        assert report.verdict == OperatorVerdict.ADVANCE

    def test_degraded_night_produces_rollback(self, tmp_path: Path) -> None:
        """Night with all dead cycles + test regression -> ROLLBACK."""
        evaluator = OvernightEvaluator(
            date="2026-03-25", state_dir=tmp_path, project_dir=tmp_path
        )
        evaluator._baseline = {"passed": 100, "failed": 0}
        evaluator._last_snapshot = {"passed": 100, "failed": 0}

        # Simulate 5 dead cycles with test regression
        for i in range(5):
            r = _make_cycle_result(
                cycle_id=f"c{i}",
                files_modified=[],
                test_results={"passed": 100 - i * 2, "failed": i * 2},
                tokens_spent=2000,
                acceptance_passed=False,
            )
            evaluator.evaluate_cycle(f"c{i}", r)

        night = evaluator.evaluate_night()
        report = compute_verdict(night)

        assert night.verified_completions == 0
        assert night.dead_loop_ratio == 1.0  # all dead
        assert report.verdict == OperatorVerdict.ROLLBACK
