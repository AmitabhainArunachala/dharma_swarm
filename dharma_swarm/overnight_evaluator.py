"""Overnight Evaluator -- distinguishes activity from progress.

Computes per-cycle and per-night metrics that answer:
"Did this cycle make the system measurably better?"

Six metrics:
  1. state_changes_count -- files/tests/metrics changed
  2. test_delta -- pytest pass count before vs after
  3. coverage_delta -- coverage % before vs after
  4. verified_completions -- tasks where acceptance criterion passed
  5. token_efficiency -- state_changes / tokens_spent
  6. dead_loop_time -- cumulative time in zero-change cycles

Writes:
  ~/.dharma/overnight/{date}/eval_summary.json   (night aggregate)
  ~/.dharma/overnight/{date}/cycle_evals.jsonl    (per-cycle append)
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CycleResult:
    """Raw output from a single overnight cycle."""

    cycle_id: str
    task_id: str
    started_at: float
    completed_at: float
    tokens_spent: int
    files_modified: list[str]
    test_results: dict[str, Any] | None  # pytest output parsed
    acceptance_passed: bool
    error: str | None


@dataclass(slots=True)
class CycleEvaluation:
    """Computed evaluation for a single cycle."""

    cycle_id: str
    state_changes_count: int
    test_delta: int  # tests passing now - tests passing before
    verified: bool  # acceptance criterion passed
    tokens_spent: int
    token_efficiency: float  # state_changes / max(tokens_spent, 1)
    is_dead_cycle: bool  # zero state changes
    duration_seconds: float


@dataclass(slots=True)
class NightEvaluation:
    """Aggregate evaluation for the entire overnight run."""

    date: str
    total_cycles: int
    verified_completions: int
    total_state_changes: int
    test_delta: int  # net change in passing tests
    coverage_delta: float  # net change in coverage %
    total_tokens_spent: int
    cost_per_verified_improvement: float
    dead_loop_ratio: float  # dead_loop_time / total_time
    dead_loop_time: float
    total_time: float
    token_efficiency: float
    morning_capability_delta: float  # aggregate score 0.0-1.0


# ---------------------------------------------------------------------------
# Operator Verdict — the control signal
# ---------------------------------------------------------------------------


class OperatorVerdict(str, Enum):
    """Control signal computed from NightEvaluation.

    ADVANCE: Night was productive — promote changes, feed positive signal to
             DarwinEngine, allow self-improvement to continue.
    HOLD:    Night was inconclusive — keep changes but pause aggressive evolution,
             flag for morning review.
    ROLLBACK: Night degraded the system — revert uncommitted changes, disable
              self-improvement, halt evolution until human review.
    """

    ADVANCE = "advance"
    HOLD = "hold"
    ROLLBACK = "rollback"


@dataclass(slots=True)
class VerdictReport:
    """Detailed breakdown of how the verdict was computed."""

    verdict: OperatorVerdict
    reasons: list[str]
    scores: dict[str, float]
    night_eval: dict[str, Any]


def compute_verdict(
    night: NightEvaluation,
    *,
    rollback_test_delta: int = -5,
    rollback_dead_ratio: float = 0.8,
    hold_dead_ratio: float = 0.5,
    hold_capability_delta: float = 0.05,
    advance_capability_delta: float = 0.15,
    advance_verified_min: int = 1,
) -> VerdictReport:
    """Compute an operator verdict from aggregate night metrics.

    Thresholds (all tunable):
        ROLLBACK if:
            - test_delta <= rollback_test_delta (lost 5+ tests)
            - dead_loop_ratio >= rollback_dead_ratio (80%+ wasted)
            - zero verified completions AND test_delta < 0
        ADVANCE if:
            - morning_capability_delta >= advance_capability_delta
            - verified_completions >= advance_verified_min
            - test_delta >= 0 (no regressions)
        HOLD otherwise.
    """
    reasons: list[str] = []
    scores = {
        "test_delta": float(night.test_delta),
        "dead_loop_ratio": night.dead_loop_ratio,
        "capability_delta": night.morning_capability_delta,
        "verified_completions": float(night.verified_completions),
        "coverage_delta": night.coverage_delta,
        "token_efficiency": night.token_efficiency,
    }

    # --- ROLLBACK checks (any one triggers) ---
    rollback = False

    if night.test_delta <= rollback_test_delta:
        reasons.append(
            f"ROLLBACK: test regression ({night.test_delta} tests lost, "
            f"threshold={rollback_test_delta})"
        )
        rollback = True

    if night.dead_loop_ratio >= rollback_dead_ratio:
        reasons.append(
            f"ROLLBACK: excessive dead loops ({night.dead_loop_ratio:.0%} wasted, "
            f"threshold={rollback_dead_ratio:.0%})"
        )
        rollback = True

    if night.verified_completions == 0 and night.test_delta < 0:
        reasons.append(
            "ROLLBACK: zero verified completions with test regression"
        )
        rollback = True

    if rollback:
        return VerdictReport(
            verdict=OperatorVerdict.ROLLBACK,
            reasons=reasons,
            scores=scores,
            night_eval=asdict(night),
        )

    # --- ADVANCE checks (all must pass) ---
    advance_checks = []

    if night.morning_capability_delta >= advance_capability_delta:
        advance_checks.append(
            f"capability_delta={night.morning_capability_delta:.2f} >= {advance_capability_delta}"
        )
    if night.verified_completions >= advance_verified_min:
        advance_checks.append(
            f"verified={night.verified_completions} >= {advance_verified_min}"
        )
    if night.test_delta >= 0:
        advance_checks.append(f"test_delta={night.test_delta} >= 0")

    if len(advance_checks) == 3:
        reasons.append("ADVANCE: " + "; ".join(advance_checks))
        return VerdictReport(
            verdict=OperatorVerdict.ADVANCE,
            reasons=reasons,
            scores=scores,
            night_eval=asdict(night),
        )

    # --- HOLD (default) ---
    if night.dead_loop_ratio >= hold_dead_ratio:
        reasons.append(
            f"HOLD: high dead loop ratio ({night.dead_loop_ratio:.0%})"
        )
    if night.morning_capability_delta < hold_capability_delta:
        reasons.append(
            f"HOLD: low capability delta ({night.morning_capability_delta:.2f})"
        )
    if night.verified_completions == 0:
        reasons.append("HOLD: no verified completions")
    if not reasons:
        reasons.append("HOLD: insufficient evidence for ADVANCE")

    return VerdictReport(
        verdict=OperatorVerdict.HOLD,
        reasons=reasons,
        scores=scores,
        night_eval=asdict(night),
    )


# ---------------------------------------------------------------------------
# Pytest output parsing
# ---------------------------------------------------------------------------

_PYTEST_SUMMARY_RE = re.compile(
    r"(\d+)\s+passed(?:.*?(\d+)\s+failed)?",
)

_COVERAGE_TOTAL_RE = re.compile(r'"totals":\s*\{[^}]*"percent_covered":\s*([\d.]+)')


def _parse_pytest_summary(output: str) -> dict[str, int]:
    """Extract passed/failed counts from pytest -q output.

    Returns dict with keys 'passed' and 'failed' (both default to 0).
    """
    result = {"passed": 0, "failed": 0}
    m = _PYTEST_SUMMARY_RE.search(output)
    if m:
        result["passed"] = int(m.group(1))
        if m.group(2):
            result["failed"] = int(m.group(2))
    return result


def _parse_coverage_percent(json_text: str) -> float | None:
    """Extract total coverage % from pytest-cov JSON report."""
    m = _COVERAGE_TOTAL_RE.search(json_text)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class OvernightEvaluator:
    """Measures whether overnight cycles produced real progress or just activity.

    Attributes:
        date: Date string (YYYY-MM-DD) for the evaluation period.
        state_dir: Root of the .dharma state directory.
    """

    def __init__(
        self,
        date: str | None = None,
        state_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.state_dir = Path(state_dir) if state_dir is not None else Path.home() / ".dharma"
        self.project_dir = Path(project_dir) if project_dir is not None else Path.home() / "dharma_swarm"

        self._baseline: dict[str, Any] | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._cycle_evals: list[CycleEvaluation] = []
        self._dead_loop_time: float = 0.0
        self._total_time: float = 0.0

    # ----- disk helpers (never crash the overnight loop) -----

    def _output_dir(self) -> Path:
        return self.state_dir / "overnight" / self.date

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON to disk. Swallow errors -- evaluation must not crash."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=True, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to write %s", path)

    def _append_jsonl(self, path: Path, data: dict[str, Any]) -> None:
        """Append a single JSON line to a file. Swallow errors."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(data, ensure_ascii=True, default=str) + "\n")
        except Exception:
            logger.exception("Failed to append to %s", path)

    # ----- pytest runner -----

    def _run_pytest(self, *, with_coverage: bool = False) -> dict[str, Any]:
        """Run pytest non-destructively and parse results.

        Returns dict with 'passed', 'failed', and optionally 'coverage_percent'.
        Never raises -- returns zeros on any failure.
        """
        result: dict[str, Any] = {"passed": 0, "failed": 0, "coverage_percent": None}

        cmd = ["python3", "-m", "pytest", "tests/", "-q", "--tb=no", "--no-header"]
        if with_coverage:
            cmd.extend(["--cov=dharma_swarm", "--cov-report=json"])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.project_dir),
            )
            combined_output = proc.stdout + proc.stderr

            if (
                with_coverage
                and proc.returncode != 0
                and "unrecognized arguments" in combined_output
                and "--cov" in combined_output
            ):
                logger.info("pytest-cov unavailable; retrying baseline without coverage")
                proc = subprocess.run(
                    ["python3", "-m", "pytest", "tests/", "-q", "--tb=no", "--no-header"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(self.project_dir),
                )
                combined_output = proc.stdout + proc.stderr

            parsed = _parse_pytest_summary(combined_output)
            result["passed"] = parsed["passed"]
            result["failed"] = parsed["failed"]

            if with_coverage and proc.returncode == 0:
                cov_json_path = self.project_dir / "coverage.json"
                if cov_json_path.exists():
                    try:
                        cov_text = cov_json_path.read_text(encoding="utf-8")
                        pct = _parse_coverage_percent(cov_text)
                        if pct is not None:
                            result["coverage_percent"] = pct
                    except Exception:
                        logger.debug("Could not parse coverage.json")
        except FileNotFoundError:
            logger.warning("pytest not found -- cannot capture test baseline")
        except subprocess.TimeoutExpired:
            logger.warning("pytest timed out after 300s")
        except Exception:
            logger.exception("Unexpected error running pytest")

        return result

    # ----- public API -----

    def baseline(self) -> dict[str, Any]:
        """Capture baseline metrics before overnight work begins.

        Runs pytest to count passing/failing tests and optionally captures
        coverage.  Stores result as ``self._baseline``.

        Returns:
            Dict with 'passed', 'failed', 'coverage_percent' keys.
        """
        self._baseline = self._run_pytest(with_coverage=True)
        self._last_snapshot = dict(self._baseline)
        logger.info(
            "Baseline captured: %d passed, %d failed, coverage=%s",
            self._baseline["passed"],
            self._baseline["failed"],
            self._baseline.get("coverage_percent"),
        )
        return dict(self._baseline)

    def snapshot(self) -> dict[str, Any]:
        """Capture current state for mid-cycle comparison.

        Same as :meth:`baseline` but does not overwrite the baseline.
        Updates ``self._last_snapshot``.

        Returns:
            Dict with 'passed', 'failed', 'coverage_percent' keys.
        """
        snap = self._run_pytest(with_coverage=False)
        self._last_snapshot = snap
        return dict(snap)

    def evaluate_cycle(self, cycle_id: str, result: CycleResult) -> CycleEvaluation:
        """Compute evaluation metrics for a single cycle.

        Args:
            cycle_id: Unique identifier for this cycle.
            result: The raw cycle output to evaluate.

        Returns:
            CycleEvaluation with computed deltas and efficiency metrics.
        """
        state_changes = len(result.files_modified)
        duration = max(result.completed_at - result.started_at, 0.0)

        # Test delta: compare against last snapshot or baseline
        test_delta = 0
        if result.test_results and self._last_snapshot:
            current_passed = result.test_results.get("passed", 0)
            previous_passed = self._last_snapshot.get("passed", 0)
            test_delta = current_passed - previous_passed

        token_efficiency = state_changes / max(result.tokens_spent, 1)
        is_dead = state_changes == 0

        evaluation = CycleEvaluation(
            cycle_id=cycle_id,
            state_changes_count=state_changes,
            test_delta=test_delta,
            verified=result.acceptance_passed,
            tokens_spent=result.tokens_spent,
            token_efficiency=token_efficiency,
            is_dead_cycle=is_dead,
            duration_seconds=duration,
        )

        # Update running totals
        self._cycle_evals.append(evaluation)
        self._total_time += duration
        if is_dead:
            self._dead_loop_time += duration

        # Update last snapshot if we have test results
        if result.test_results:
            self._last_snapshot = result.test_results

        # Persist to disk
        self._append_jsonl(
            self._output_dir() / "cycle_evals.jsonl",
            asdict(evaluation),
        )

        return evaluation

    def evaluate_night(self) -> NightEvaluation:
        """Compute aggregate metrics for the entire overnight run.

        Writes eval_summary.json to disk and returns the evaluation.

        Returns:
            NightEvaluation with all aggregate metrics.
        """
        total_cycles = len(self._cycle_evals)
        verified_completions = sum(1 for e in self._cycle_evals if e.verified)
        total_state_changes = sum(e.state_changes_count for e in self._cycle_evals)
        total_tokens = sum(e.tokens_spent for e in self._cycle_evals)
        net_test_delta = sum(e.test_delta for e in self._cycle_evals)

        # Coverage delta: compare final vs baseline
        coverage_delta = 0.0
        if self._baseline and self._last_snapshot:
            baseline_cov = self._baseline.get("coverage_percent")
            current_cov = self._last_snapshot.get("coverage_percent")
            if baseline_cov is not None and current_cov is not None:
                coverage_delta = current_cov - baseline_cov

        total_time = self._total_time if self._total_time > 0 else 1.0
        dead_loop_ratio = self._dead_loop_time / total_time

        cost_per_verified = (
            total_tokens / max(verified_completions, 1)
            if verified_completions > 0
            else float(total_tokens)
        )

        token_efficiency = total_state_changes / max(total_tokens, 1)

        night = NightEvaluation(
            date=self.date,
            total_cycles=total_cycles,
            verified_completions=verified_completions,
            total_state_changes=total_state_changes,
            test_delta=net_test_delta,
            coverage_delta=coverage_delta,
            total_tokens_spent=total_tokens,
            cost_per_verified_improvement=cost_per_verified,
            dead_loop_ratio=dead_loop_ratio,
            dead_loop_time=self._dead_loop_time,
            total_time=self._total_time,
            token_efficiency=token_efficiency,
            morning_capability_delta=0.0,  # placeholder, computed below
        )

        # Compute morning_capability_delta using the night evaluation
        night = NightEvaluation(
            **{
                **asdict(night),
                "morning_capability_delta": self._compute_capability_delta(night),
            }
        )

        # Write to disk
        self._write_json(
            self._output_dir() / "eval_summary.json",
            asdict(night),
        )

        return night

    def summary_dict(self) -> dict[str, Any]:
        """Return all metrics as a plain dict for JSON serialization.

        Returns:
            Dict containing cycle evaluations, running totals, and baseline.
        """
        return {
            "date": self.date,
            "baseline": self._baseline,
            "last_snapshot": self._last_snapshot,
            "total_time": self._total_time,
            "dead_loop_time": self._dead_loop_time,
            "cycles": [asdict(e) for e in self._cycle_evals],
        }

    # ----- internal -----

    @staticmethod
    def _compute_capability_delta(night: NightEvaluation) -> float:
        """Compute aggregate improvement score.

        Returns:
            Float in [0.0, 1.0] where 0.0 = nothing improved,
            1.0 = maximum improvement detected.
        """
        score = 0.0
        if night.test_delta > 0:
            score += min(night.test_delta / 10.0, 0.4)  # up to 0.4 for test gains
        if night.verified_completions > 0:
            score += min(night.verified_completions / 5.0, 0.3)  # up to 0.3
        if night.dead_loop_ratio < 0.2:
            score += 0.2  # bonus for low waste
        if night.total_state_changes > 0:
            score += 0.1  # any state change is progress
        return min(score, 1.0)
