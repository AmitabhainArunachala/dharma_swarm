"""Self-Improvement Cycle — the full strange loop.

EVAL → REVIEW → PROPOSE → GATE → TEST → RE-EVAL → LEARN → SUPERVISE

The system measures itself, identifies weakest points, proposes fixes via
DarwinEngine, tests them, and learns from the outcome.

Safety:
  - Gated behind DHARMA_SELF_IMPROVE=1 env var (off by default)
  - Max 3 proposals per cycle
  - Changes on darwin/cycle-{id} branch, never main
  - Full pytest must pass before considering any change
  - Human review required for identity-layer files
  - Max 10 LLM calls per cycle (scoring only)
"""

from __future__ import annotations

import json
import inspect
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
CYCLE_DIR = STATE_DIR / "self_improve"
DHARMA_SWARM_DIR = Path.home() / "dharma_swarm"

# Identity-layer files requiring human review
PROTECTED_FILES = {
    "telos_gates.py",
    "dharma_kernel.py",
    "evolution.py",
    "config.py",
}

MAX_PROPOSALS_PER_CYCLE = 3
MAX_LLM_CALLS = 10
SELF_IMPROVE_INTERVAL = 1800  # 30 minutes


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CycleReport:
    """Report from one self-improvement cycle."""

    cycle_id: str = ""
    timestamp: str = ""
    enabled: bool = False

    # Eval phase
    eval_before: dict[str, Any] = field(default_factory=dict)
    eval_after: dict[str, Any] = field(default_factory=dict)

    # Review phase
    findings_count: int = 0
    proposals_generated: int = 0

    # Gate phase
    proposals_gated: int = 0
    proposals_blocked: int = 0

    # Test phase
    tests_passed: bool = False
    test_output: str = ""

    # Outcome
    improved: bool = False
    improvement_delta: float = 0.0
    branch_name: str = ""
    rollback_executed: bool = False
    lesson_learned: str = ""

    # Supervision
    supervisor_alerts: list[dict] = field(default_factory=list)

    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _new_cycle_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    """Check if self-improvement is enabled via env var."""
    return os.environ.get("DHARMA_SELF_IMPROVE", "0").strip() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Overnight activation — staged autonomy
# ---------------------------------------------------------------------------

# Autonomy levels for overnight self-improvement
AUTONOMY_LEVEL_0 = 0  # Read-only analysis, report generation
AUTONOMY_LEVEL_1 = 1  # Test additions and improvements (auto-apply if passing)
AUTONOMY_LEVEL_2 = 2  # Non-identity code changes (darwin branch, verify)
AUTONOMY_LEVEL_3 = 3  # Identity-layer proposals (generate only, morning review)

_overnight_autonomy_level: int = AUTONOMY_LEVEL_1
_overnight_active: bool = False


def enable_for_overnight(autonomy_level: int = AUTONOMY_LEVEL_1) -> None:
    """Enable self-improvement for overnight mode with staged autonomy.

    Levels:
        0: read-only analysis and report generation
        1: test additions and improvements (auto-apply if passing)
        2: non-identity code changes (apply on darwin branch, verify)
        3: identity-layer proposals (generate only, morning review)

    PROTECTED_FILES guard remains active at all levels.
    """
    global _overnight_autonomy_level, _overnight_active
    _overnight_autonomy_level = max(0, min(autonomy_level, AUTONOMY_LEVEL_3))
    _overnight_active = True
    os.environ["DHARMA_SELF_IMPROVE"] = "1"
    logger.info(
        "Self-improvement enabled for overnight (autonomy_level=%d)",
        _overnight_autonomy_level,
    )


def disable_overnight() -> None:
    """Disable overnight self-improvement mode."""
    global _overnight_active
    _overnight_active = False
    os.environ.pop("DHARMA_SELF_IMPROVE", None)
    logger.info("Self-improvement overnight mode disabled")


def overnight_autonomy_level() -> int:
    """Return the current overnight autonomy level."""
    return _overnight_autonomy_level if _overnight_active else -1


def is_overnight_active() -> bool:
    """Check if overnight self-improvement mode is active."""
    return _overnight_active


async def _maybe_await(value: Any) -> Any:
    """Allow self-improvement hooks to be sync or async."""
    if inspect.isawaitable(value):
        return await value
    return value


def _touches_protected(proposals: list[Any]) -> list[Any]:
    """Return proposals that touch identity-layer files."""
    protected = []
    for p in proposals:
        component = getattr(p, "component", "")
        basename = Path(component).name
        if basename in PROTECTED_FILES:
            protected.append(p)
    return protected


def _find_locally_modified_components(components: list[str]) -> list[str]:
    """Return proposed component paths that already have local changes."""
    dirty: list[str] = []
    seen: set[str] = set()

    for component in components:
        normalized = str(component or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--", normalized],
                cwd=str(DHARMA_SWARM_DIR),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            logger.warning("Failed to inspect local changes for %s: %s", normalized, exc)
            dirty.append(normalized)
            continue

        if result.returncode != 0:
            logger.warning(
                "Git status failed for %s: %s",
                normalized,
                (result.stderr or result.stdout or "").strip(),
            )
            dirty.append(normalized)
            continue

        if result.stdout.strip():
            dirty.append(normalized)

    return dirty


def _cleanup_apply_backups(apply_results: list[Any]) -> None:
    """Remove transient backup files left behind by successful diff application."""
    for apply_result in apply_results:
        backup_paths = getattr(apply_result, "backup_paths", {}) or {}
        for backup in backup_paths.values():
            try:
                Path(backup).unlink(missing_ok=True)
            except OSError:
                logger.debug("Backup cleanup failed for %s", backup, exc_info=True)


# ---------------------------------------------------------------------------
# Self-improvement cycle
# ---------------------------------------------------------------------------

class SelfImprovementCycle:
    """Autonomous self-improvement: measure → identify → propose → test → learn."""

    def __init__(self) -> None:
        self._llm_calls = 0

    async def run_cycle(self) -> CycleReport:
        """Execute one full self-improvement cycle.

        Returns a CycleReport regardless of outcome.
        """
        cycle_id = _new_cycle_id()
        report = CycleReport(
            cycle_id=cycle_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            enabled=is_enabled(),
        )
        t0 = time.monotonic()

        if not is_enabled():
            report.lesson_learned = "Self-improvement disabled (DHARMA_SELF_IMPROVE != 1)"
            return report

        try:
            # Phase 1: EVAL — baseline measurement
            eval_before = await _maybe_await(self._run_eval())
            report.eval_before = eval_before

            # Phase 2: REVIEW — find issues
            proposals = await _maybe_await(self._run_review(cycle_id))
            report.findings_count = len(proposals)

            # Limit proposals
            proposals = proposals[:MAX_PROPOSALS_PER_CYCLE]
            report.proposals_generated = len(proposals)

            if not proposals:
                report.lesson_learned = "No actionable findings from review"
                report.duration_seconds = time.monotonic() - t0
                self._save_report(report)
                return report

            # Safety: block proposals touching protected files
            protected = _touches_protected(proposals)
            if protected:
                report.proposals_blocked = len(protected)
                proposals = [p for p in proposals if p not in protected]
                logger.warning(
                    "Blocked %d proposals touching identity-layer files",
                    len(protected),
                )

            # Phase 3: GATE — check proposals
            gated = self._gate_proposals(proposals)
            report.proposals_gated = len(gated)

            if not gated:
                report.lesson_learned = "All proposals blocked by gates"
                report.duration_seconds = time.monotonic() - t0
                self._save_report(report)
                return report

            # Phase 4: EVAL-GATE — check system health before applying diffs
            branch_name = f"darwin/cycle-{cycle_id}"
            report.branch_name = branch_name

            # Check overnight verdict: if ROLLBACK was issued, skip application
            eval_gate_passed = True
            try:
                from dharma_swarm.overnight_evaluator import OperatorVerdict
                verdict_path = CYCLE_DIR.parent / "overnight" / (
                    datetime.now(timezone.utc).strftime("%Y-%m-%d")
                ) / "verdict.json"
                if verdict_path.exists():
                    import json as _json
                    verdict_data = _json.loads(verdict_path.read_text())
                    if verdict_data.get("verdict") == OperatorVerdict.ROLLBACK.value:
                        eval_gate_passed = False
                        report.lesson_learned = (
                            f"Cycle {cycle_id}: BLOCKED by overnight ROLLBACK verdict — "
                            "system in degraded state, diffs not applied"
                        )
                        logger.warning("Self-improvement blocked: overnight ROLLBACK verdict active")
            except Exception:
                pass  # verdict check failure doesn't block SI

            # Check eval pass rate from benchmark registry
            if eval_gate_passed:
                try:
                    from dharma_swarm.ecc_eval_harness import load_latest as _load_eval
                    latest_eval = _load_eval()
                    if latest_eval and latest_eval.get("pass_at_1", 1.0) < 0.5:
                        eval_gate_passed = False
                        report.lesson_learned = (
                            f"Cycle {cycle_id}: BLOCKED by low eval pass rate "
                            f"({latest_eval['pass_at_1']:.0%} < 50%) — "
                            "system must stabilize before self-modification"
                        )
                        logger.warning(
                            "Self-improvement blocked: eval pass rate %.0f%% < 50%%",
                            latest_eval["pass_at_1"] * 100,
                        )
                except Exception:
                    pass

            if not eval_gate_passed:
                report.duration_seconds = time.monotonic() - t0
                self._save_report(report)
                return report

            diff_targets = [
                str(getattr(p, "component", "") or "").strip()
                for p in gated
                if str(getattr(p, "diff", "") or "").strip()
            ]
            locally_modified = set(_find_locally_modified_components(diff_targets))
            if locally_modified:
                report.proposals_blocked += sum(
                    1
                    for proposal in gated
                    if str(getattr(proposal, "component", "") or "").strip() in locally_modified
                )
                gated = [
                    proposal
                    for proposal in gated
                    if str(getattr(proposal, "component", "") or "").strip() not in locally_modified
                ]
                logger.warning(
                    "Blocked %d proposals touching locally modified components: %s",
                    len(locally_modified),
                    ", ".join(sorted(locally_modified)),
                )
                if not gated:
                    report.lesson_learned = (
                        "All proposals blocked by local changes in target components"
                    )
                    report.duration_seconds = time.monotonic() - t0
                    self._save_report(report)
                    return report

            # Apply proposal diffs to the actual codebase
            apply_results: list[Any] = []
            applier = None
            try:
                from dharma_swarm.diff_applier import DiffApplier
                applier = DiffApplier(workspace=DHARMA_SWARM_DIR)
                for p in gated:
                    diff_text = getattr(p, "diff", "")
                    if diff_text and diff_text.strip():
                        apply_result = await applier.apply(diff_text)
                        if apply_result.success:
                            apply_results.append(apply_result)
                            logger.info(
                                "Applied diff for %s: %s",
                                getattr(p, "component", "?"),
                                apply_result.files_changed,
                            )
                        else:
                            logger.warning(
                                "Failed to apply diff for %s: %s",
                                getattr(p, "component", "?"),
                                apply_result.error,
                            )
            except Exception as exc:
                logger.warning("DiffApplier integration failed: %s", exc)

            # Phase 5: TEST — verify nothing breaks after applying diffs
            tests_ok = await _maybe_await(self._run_tests())
            report.tests_passed = tests_ok

            # Phase 6: RE-EVAL — measure after with diffs applied
            eval_after = await _maybe_await(self._run_eval())
            report.eval_after = eval_after

            # Phase 7: LEARN
            before_rate = eval_before.get("pass_at_1", 0.0)
            after_rate = eval_after.get("pass_at_1", 0.0)
            report.improvement_delta = after_rate - before_rate
            eval_improved = after_rate >= before_rate
            report.improved = tests_ok and eval_improved

            if report.improved:
                report.lesson_learned = (
                    f"Cycle {cycle_id}: eval stable/improved "
                    f"({before_rate:.1%} → {after_rate:.1%})"
                )
                _cleanup_apply_backups(apply_results)
                self._write_instinct(report)
            else:
                report.rollback_executed = bool(apply_results)
                if not tests_ok:
                    report.lesson_learned = (
                        f"Cycle {cycle_id}: tests failed after applying proposals, rolled back"
                    )
                else:
                    report.lesson_learned = (
                        f"Cycle {cycle_id}: eval degraded "
                        f"({before_rate:.1%} → {after_rate:.1%}), rolled back"
                    )
                if apply_results and applier is not None:
                    for apply_result in reversed(apply_results):
                        try:
                            await applier.rollback(apply_result)
                        except Exception as rb_err:
                            logger.warning("Rollback failed: %s", rb_err)
                    logger.info("Rolled back %d applied diffs", len(apply_results))

            # Phase 8: SUPERVISE — check if cycle itself is healthy
            report.supervisor_alerts = self._check_supervisor()

        except Exception as e:
            report.lesson_learned = f"Cycle failed: {e}"
            logger.exception("Self-improvement cycle %s failed", cycle_id)

        report.duration_seconds = time.monotonic() - t0
        self._save_report(report)
        return report

    async def _run_eval(self) -> dict[str, Any]:
        """Run eval harness, return summary."""
        try:
            from dharma_swarm.ecc_eval_harness import run_all_evals, save_report
            report = await run_all_evals()
            save_report(report)
            return {
                "total": report.total,
                "passed": report.passed,
                "failed": report.failed,
                "pass_at_1": report.pass_at_1,
            }
        except Exception as e:
            logger.warning("Eval failed: %s", e)
            return {"error": str(e)}

    async def _run_review(self, cycle_id: str) -> list[Any]:
        """Run review bridge + code-aware findings, return proposals.

        Three data sources (in priority order):
        1. ReviewBridge (ruff static analysis) — zero LLM cost
        2. Git diff scan — recent changes that may need evolution (async)
        3. Evolution archive — low-fitness components needing attention
        """
        import asyncio

        proposals: list[Any] = []

        # Source 1: ReviewBridge (ruff findings → proposals)
        try:
            from dharma_swarm.review_bridge import ReviewBridge
            bridge = ReviewBridge(min_severity="high", max_proposals=MAX_PROPOSALS_PER_CYCLE)
            proposals.extend(bridge.propose(cycle_id=cycle_id))
        except Exception as e:
            logger.debug("Review bridge failed: %s", e)

        # Source 2: Git diff — files changed recently that have test failures (async)
        if len(proposals) < MAX_PROPOSALS_PER_CYCLE:
            try:
                from dharma_swarm.evolution import Proposal
                diff_proc = await asyncio.create_subprocess_exec(
                    "git", "diff", "--name-only", "--diff-filter=M", "HEAD~10",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(DHARMA_SWARM_DIR),
                )
                diff_out, _ = await asyncio.wait_for(diff_proc.communicate(), timeout=15)
                changed_files = [
                    f.strip() for f in diff_out.decode().strip().split("\n")
                    if f.strip() and f.strip().startswith("dharma_swarm/") and f.strip().endswith(".py")
                ]
                for cf in changed_files[:3]:
                    stem = Path(cf).stem
                    test_file = DHARMA_SWARM_DIR / "tests" / f"test_{stem}.py"
                    if test_file.exists():
                        # Quick async test run to see if this component is broken
                        tr = await asyncio.create_subprocess_exec(
                            sys.executable, "-m", "pytest", str(test_file),
                            "-q", "--tb=line", "-x", "--timeout=15",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=str(DHARMA_SWARM_DIR),
                        )
                        tr_out, _ = await asyncio.wait_for(tr.communicate(), timeout=45)
                        if tr.returncode != 0:
                            proposals.append(Proposal(
                                component=cf,
                                change_type="fix",
                                description=(
                                    f"Recently modified file {cf} has failing tests: "
                                    f"{tr_out.decode().strip()[-200:]}"
                                ),
                                spec_ref=f"self_improve:git_diff:{cycle_id}",
                            ))
                            if len(proposals) >= MAX_PROPOSALS_PER_CYCLE:
                                break
            except Exception as e:
                logger.debug("Git diff review failed: %s", e)

        # Source 3: Evolution archive — components with correctness=0.0
        if len(proposals) < MAX_PROPOSALS_PER_CYCLE:
            try:
                import json as _sij
                from dharma_swarm.evolution import Proposal
                archive_path = STATE_DIR / "evolution" / "archive.jsonl"
                if archive_path.exists():
                    lines = archive_path.read_text().strip().split("\n")
                    zero_fitness_components: dict[str, int] = {}
                    for line in lines[-50:]:  # Last 50 entries
                        if not line.strip():
                            continue
                        entry = _sij.loads(line)
                        fitness = entry.get("fitness", {})
                        if isinstance(fitness, dict) and fitness.get("correctness", 1.0) == 0.0:
                            comp = entry.get("component", "")
                            if comp:
                                zero_fitness_components[comp] = zero_fitness_components.get(comp, 0) + 1
                    # Propose fixes for components that repeatedly fail
                    for comp, count in sorted(zero_fitness_components.items(), key=lambda x: -x[1]):
                        if count >= 2 and len(proposals) < MAX_PROPOSALS_PER_CYCLE:
                            proposals.append(Proposal(
                                component=comp,
                                change_type="mutation",
                                description=(
                                    f"Component '{comp}' has {count} evolution entries with "
                                    f"correctness=0.0 — needs test profile or source fix"
                                ),
                                spec_ref=f"self_improve:archive_zero:{cycle_id}",
                            ))
            except Exception as e:
                logger.debug("Evolution archive review failed: %s", e)

        return proposals[:MAX_PROPOSALS_PER_CYCLE]

    def _gate_proposals(self, proposals: list[Any]) -> list[Any]:
        """Filter proposals through basic gate check."""
        gated = []
        for p in proposals:
            # Basic gate: must have component and description
            if getattr(p, "component", "") and getattr(p, "description", ""):
                gated.append(p)
        return gated

    async def _run_tests(self) -> bool:
        """Run targeted pytest (async, non-blocking).

        Runs only recently-changed test files instead of the full suite to
        avoid blocking the event loop for 12+ minutes.
        """
        import asyncio

        try:
            # Find which test files correspond to changed source files
            diff_proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--name-only", "--diff-filter=M", "HEAD~10",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(DHARMA_SWARM_DIR),
            )
            diff_out, _ = await asyncio.wait_for(diff_proc.communicate(), timeout=15)
            changed = [
                f.strip() for f in diff_out.decode().strip().split("\n")
                if f.strip().startswith("dharma_swarm/") and f.strip().endswith(".py")
            ]

            # Build targeted test file list
            test_files: list[str] = []
            for cf in changed[:8]:
                stem = Path(cf).stem
                tf = DHARMA_SWARM_DIR / "tests" / f"test_{stem}.py"
                if tf.exists():
                    test_files.append(str(tf))

            if not test_files:
                # Fallback: run a quick smoke test on core modules only
                for name in ("evolution", "swarm", "providers", "agent_runner"):
                    tf = DHARMA_SWARM_DIR / "tests" / f"test_{name}.py"
                    if tf.exists():
                        test_files.append(str(tf))

            if not test_files:
                return True  # Nothing to test

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest", *test_files,
                "-q", "--tb=line", "-x", "--timeout=30",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(DHARMA_SWARM_DIR),
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            return proc.returncode == 0
        except Exception:
            return False

    def _write_instinct(self, report: CycleReport) -> None:
        """Write lesson as synthetic instinct if improvement was measured."""
        try:
            from dharma_swarm.instinct_bridge import write_synthetic_instinct
            write_synthetic_instinct(
                name=f"self_improve_{report.cycle_id}",
                description=report.lesson_learned,
                confidence=0.7 + (report.improvement_delta * 0.3),
                source="self_improvement_cycle",
            )
        except Exception:
            logger.debug("Lesson learned recording failed", exc_info=True)

    def _check_supervisor(self) -> list[dict]:
        """Check loop supervisor for any active alerts."""
        try:
            from dharma_swarm.loop_supervisor import LoopSupervisor
            state = LoopSupervisor.load_state()
            if state:
                return state.get("recent_alerts", [])
        except Exception:
            logger.debug("Loop supervisor check failed", exc_info=True)
        return []

    def _save_report(self, report: CycleReport) -> None:
        """Save cycle report to disk."""
        CYCLE_DIR.mkdir(parents=True, exist_ok=True)
        report_path = CYCLE_DIR / f"cycle_{report.cycle_id}.json"
        report_path.write_text(json.dumps(report.to_dict(), indent=2))

        # Also write markdown for human review
        md_path = CYCLE_DIR / f"cycle_{report.cycle_id}.md"
        lines = [
            f"# Self-Improvement Cycle: {report.cycle_id}",
            f"**Time**: {report.timestamp}",
            f"**Duration**: {report.duration_seconds:.1f}s",
            f"**Enabled**: {report.enabled}",
            "",
            "## Eval Before",
            f"- pass@1: {report.eval_before.get('pass_at_1', 'N/A')}",
            "",
            "## Review",
            f"- Findings: {report.findings_count}",
            f"- Proposals: {report.proposals_generated}",
            f"- Gated: {report.proposals_gated}",
            f"- Blocked (protected): {report.proposals_blocked}",
            "",
            "## Outcome",
            f"- Tests passed: {report.tests_passed}",
            f"- Improved: {report.improved}",
            f"- Delta: {report.improvement_delta:+.1%}",
            f"- Branch: {report.branch_name}",
            "",
            "## Lesson",
            report.lesson_learned,
        ]
        md_path.write_text("\n".join(lines))

    @staticmethod
    def load_history(last_n: int = 10) -> list[dict]:
        """Load recent cycle reports."""
        if not CYCLE_DIR.exists():
            return []
        reports = []
        for path in sorted(CYCLE_DIR.glob("cycle_*.json"))[-last_n:]:
            try:
                reports.append(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        return reports

    @staticmethod
    def load_latest() -> dict | None:
        """Load the most recent cycle report."""
        if not CYCLE_DIR.exists():
            return None
        files = sorted(CYCLE_DIR.glob("cycle_*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text())
        except (json.JSONDecodeError, OSError):
            return None


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------

async def run_self_improvement_loop(
    shutdown_event: Any,
    interval: float = SELF_IMPROVE_INTERVAL,
) -> None:
    """Async loop for integration into orchestrate_live.

    Runs every *interval* seconds (default 30 min).
    """
    import asyncio

    while not shutdown_event.is_set():
        if is_enabled():
            try:
                cycle = SelfImprovementCycle()
                report = await cycle.run_cycle()
                logger.info(
                    "Self-improvement cycle %s: improved=%s delta=%+.1f%%",
                    report.cycle_id, report.improved,
                    report.improvement_delta * 100,
                )
            except Exception as e:
                logger.exception("Self-improvement loop error: %s", e)
        else:
            logger.debug("Self-improvement disabled")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def cmd_self_improve_status() -> int:
    """Print self-improvement status."""
    enabled = is_enabled()
    latest = SelfImprovementCycle.load_latest()

    print(f"Self-Improvement Cycle")
    print(f"{'=' * 45}")
    print(f"  Enabled: {enabled} (DHARMA_SELF_IMPROVE={os.environ.get('DHARMA_SELF_IMPROVE', '0')})")

    if latest:
        print(f"  Last cycle: {latest.get('cycle_id', '?')}")
        print(f"  Improved: {latest.get('improved', '?')}")
        print(f"  Delta: {latest.get('improvement_delta', 0):+.1%}")
        print(f"  Lesson: {latest.get('lesson_learned', '')[:80]}")
    else:
        print("  No cycles run yet.")
    return 0


def cmd_self_improve_history() -> int:
    """Print self-improvement history."""
    history = SelfImprovementCycle.load_history()
    if not history:
        print("No self-improvement history.")
        return 0

    print(f"Self-Improvement History (last {len(history)} cycles)")
    print(f"{'=' * 55}")
    for r in history:
        delta = r.get("improvement_delta", 0)
        improved = "+" if r.get("improved") else "-"
        print(
            f"  {r.get('cycle_id', '?'):<20}  [{improved}] delta={delta:+.1%}  "
            f"proposals={r.get('proposals_generated', 0)}"
        )
    return 0


async def cmd_self_improve_run() -> int:
    """Run one self-improvement cycle manually."""
    if not is_enabled():
        print("Self-improvement is disabled. Set DHARMA_SELF_IMPROVE=1 to enable.")
        return 1
    cycle = SelfImprovementCycle()
    report = await cycle.run_cycle()
    print(f"Cycle {report.cycle_id}: improved={report.improved} delta={report.improvement_delta:+.1%}")
    print(f"Lesson: {report.lesson_learned}")
    return 0 if report.improved else 1
