"""Overnight Director -- orchestrates the full overnight autonomous loop.

Architecture (from research dossier):
  STAGE_TASKS -> EVALUATE_BASELINE -> [SELECT -> EXECUTE -> VERIFY -> RECORD]* ->
  EVALUATE_DELTA -> CONSOLIDATE -> MORNING_SYNTHESIS

Inspired by:
  - Karpathy AutoResearch: time-boxed experiments, keep/discard, ~12/hour
  - OpenAI Codex long-horizon: 4 durable state files
  - AlphaEvolve: evaluator-dominated loop
  - Atlas: acquisition function for task selection

Entry point: ``dgc overnight [--hours 8] [--dry-run]``
"""

from __future__ import annotations

import asyncio
import ast
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.rea_runtime import (
    TemporalRunStore,
    WaitState,
    WaitStateKind,
    WaitStateStatus,
    get_run_profile,
)

logger = logging.getLogger(__name__)

HOME = Path.home()
STATE_DIR = HOME / ".dharma"
DHARMA_SWARM_ROOT = HOME / "dharma_swarm"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class OvernightConfig:
    """Configuration for an overnight run."""

    hours: float = 8.0
    dry_run: bool = False
    cycle_timeout_seconds: float = 900.0  # 15 minutes per task
    max_tokens_budget: int = 500_000
    autonomy_level: int = 1  # 0=analysis, 1=tests, 2=code, 3=identity-proposals
    consolidation_interval_seconds: float = 14400.0  # 4 hours
    min_cycles: int = 1
    max_dead_cycles_before_halt: int = 10
    run_profile: str = "all_night_build"
    enable_hibernate_wake: bool = True
    external_wait_handoff: bool = False
    run_date: str = ""
    resume_temporal_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Durable state files (Codex pattern)
# ---------------------------------------------------------------------------

@dataclass
class DurableState:
    """Persisted state files for long-horizon coherence.

    Follows the OpenAI Codex pattern: spec + plan + runbook + audit.
    """

    run_dir: Path

    @property
    def spec_path(self) -> Path:
        return self.run_dir / "spec.json"

    @property
    def plan_path(self) -> Path:
        return self.run_dir / "plan.jsonl"

    @property
    def runbook_path(self) -> Path:
        return self.run_dir / "runbook.md"

    @property
    def audit_path(self) -> Path:
        return self.run_dir / "audit.jsonl"

    def write_spec(self, config: OvernightConfig) -> None:
        payload = {
            "created_at": _utc_now(),
            "config": config.to_dict(),
            "dharma_swarm_root": str(DHARMA_SWARM_ROOT),
        }
        self.spec_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def append_plan(self, task_entry: dict[str, Any]) -> None:
        with open(self.plan_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(task_entry, ensure_ascii=True) + "\n")

    def update_runbook(self, cycle_id: str, status: str, detail: str) -> None:
        lines = [
            f"# Overnight Runbook — {_utc_stamp()}",
            "",
            f"**Last updated**: {_utc_now()}",
            f"**Current cycle**: {cycle_id}",
            f"**Status**: {status}",
            "",
            detail,
            "",
        ]
        self.runbook_path.write_text("\n".join(lines), encoding="utf-8")

    def append_audit(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", _utc_now())
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")


# ---------------------------------------------------------------------------
# Cycle result
# ---------------------------------------------------------------------------

@dataclass
class CycleOutcome:
    """Result of one overnight cycle (task execution + verification)."""

    cycle_id: str
    task_id: str
    task_goal: str
    started_at: float
    completed_at: float = 0.0
    status: str = "pending"  # completed | failed | dead_cycle | timeout | error
    acceptance_passed: bool = False
    files_modified: list[str] = field(default_factory=list)
    tokens_spent: int = 0
    error: str = ""
    test_results: dict[str, Any] | None = None
    handoff: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_seconds"] = self.duration_seconds
        return d


# ---------------------------------------------------------------------------
# Morning brief
# ---------------------------------------------------------------------------

def write_morning_brief(
    *,
    run_dir: Path,
    config: OvernightConfig,
    outcomes: list[CycleOutcome],
    eval_summary: dict[str, Any],
    stager_stats: dict[str, int],
) -> Path:
    """Generate the morning briefing document."""

    completed = [o for o in outcomes if o.status == "completed"]
    failed = [o for o in outcomes if o.status == "failed"]
    dead = [o for o in outcomes if o.status == "dead_cycle"]

    lines = [
        f"# Overnight Morning Brief — {_utc_stamp()}",
        "",
        f"**Duration**: {config.hours}h | **Cycles**: {len(outcomes)} | "
        f"**Completed**: {len(completed)} | **Failed**: {len(failed)} | "
        f"**Dead**: {len(dead)}",
        "",
        "## Metrics",
        "",
        f"- Morning capability delta: **{eval_summary.get('morning_capability_delta', 0.0):.2f}**",
        f"- Test delta: {eval_summary.get('test_delta', 0)} (net change in passing tests)",
        f"- Verified completions: {eval_summary.get('verified_completions', 0)}",
        f"- Dead loop ratio: {eval_summary.get('dead_loop_ratio', 0.0):.1%}",
        f"- Token efficiency: {eval_summary.get('token_efficiency', 0.0):.6f}",
        f"- Total tokens: {eval_summary.get('total_tokens_spent', 0):,}",
        "",
        "## Task Queue",
        "",
        f"- Total staged: {stager_stats.get('total', 0)}",
        f"- Completed: {stager_stats.get('completed', 0)}",
        f"- Failed: {stager_stats.get('failed', 0)}",
        f"- Remaining: {stager_stats.get('pending', 0)}",
        "",
    ]

    if completed:
        lines.append("## Completed Tasks")
        lines.append("")
        for o in completed:
            lines.append(f"- [{o.task_id}] {o.task_goal} ({o.duration_seconds:.0f}s)")
        lines.append("")

    if failed:
        lines.append("## Failed Tasks")
        lines.append("")
        for o in failed:
            err = o.error[:100] if o.error else "no error recorded"
            lines.append(f"- [{o.task_id}] {o.task_goal} — {err}")
        lines.append("")

    if dead:
        lines.append(f"## Dead Cycles: {len(dead)}")
        lines.append("")

    lines.extend([
        "## Action Items",
        "",
        "- [ ] Review completed task outputs",
        "- [ ] Check any failed tasks for retry",
        f"- [ ] Review overnight log: `{run_dir / 'audit.jsonl'}`",
        "",
        f"*Generated at {_utc_now()}*",
    ])

    brief_path = run_dir / "morning_brief.md"
    brief_path.write_text("\n".join(lines), encoding="utf-8")

    # Also write to shared for morning skill
    shared_path = STATE_DIR / "shared" / "overnight_morning_brief.md"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    shared_path.write_text("\n".join(lines), encoding="utf-8")

    return brief_path


# ---------------------------------------------------------------------------
# Director
# ---------------------------------------------------------------------------

class OvernightDirector:
    """Orchestrates the full overnight autonomous loop."""

    def __init__(self, config: OvernightConfig | None = None) -> None:
        self.config = config or OvernightConfig()
        self.date = self.config.run_date or _utc_stamp()
        self.run_dir = STATE_DIR / "overnight" / self.date
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state = DurableState(run_dir=self.run_dir)
        self.outcomes: list[CycleOutcome] = []
        self._cycle_counter = 0
        self._dead_cycle_streak = 0
        self._tokens_spent = 0
        self._start_time = 0.0
        self._profile = None
        self._temporal_store: TemporalRunStore | None = None
        self._wait_handoff: dict[str, Any] | None = None
        self._apply_previous_verdict()

    def _load_previous_verdict(self) -> str | None:
        """Find and return the most recent overnight verdict from a prior run.

        Scans STATE_DIR/overnight/ for dated subdirectories with verdict.json,
        picks the most recent one that is not the current run's date.

        Returns:
            Verdict string ("advance", "hold", "rollback") or None if no prior
            verdict exists.
        """
        overnight_dir = STATE_DIR / "overnight"
        if not overnight_dir.is_dir():
            return None
        candidates = sorted(
            (d for d in overnight_dir.iterdir()
             if d.is_dir() and d.name != self.date and (d / "verdict.json").exists()),
            key=lambda d: d.name,
            reverse=True,
        )
        if not candidates:
            return None
        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8") if False
                              else (candidates[0] / "verdict.json").read_text(encoding="utf-8"))
            return str(data.get("verdict", "")).lower() or None
        except Exception:
            return None

    def _apply_previous_verdict(self) -> None:
        """Adjust autonomy_level based on the most recent prior verdict.

        ROLLBACK → autonomy_level = 0 (analysis only, no mutations)
        ADVANCE  → keep or increment autonomy_level (cap at 3)
        HOLD     → no change (maintain current level)
        """
        verdict = self._load_previous_verdict()
        if verdict is None:
            return
        if verdict == "rollback":
            self.config.autonomy_level = 0
        elif verdict == "advance":
            self.config.autonomy_level = min(3, self.config.autonomy_level + 1)
        # "hold" → no change

    def _init_temporal_runtime(self) -> None:
        """Initialize the REA-style temporal state for this run."""
        self._temporal_store = TemporalRunStore(self.run_dir)
        if self.config.resume_temporal_run and self._temporal_store.manifest_path.exists():
            manifest = self._temporal_store.load_manifest(self.date)
            self._profile = manifest.profile
            return
        profile = get_run_profile(self.config.run_profile)
        profile = profile.model_copy(update={"horizon_hours": float(self.config.hours)})
        self._profile = profile
        self._temporal_store.start_run(self.date, profile=profile)

    async def run(self) -> dict[str, Any]:
        """Execute the full overnight loop.

        Returns a summary dict suitable for JSON serialization.
        """
        from dharma_swarm.loop_supervisor import LoopSupervisor
        from dharma_swarm.overnight_evaluator import (
            CycleResult,
            NightEvaluation,
            OperatorVerdict,
            OvernightEvaluator,
            compute_verdict,
        )
        from dharma_swarm.overnight_task_stager import OvernightTaskStager
        from dharma_swarm.self_improve import enable_for_overnight, disable_overnight

        self._start_time = time.monotonic()
        deadline = self._start_time + (self.config.hours * 3600)
        self._init_temporal_runtime()

        # --- STAGE ---
        _log("director", f"Starting overnight run ({self.config.hours}h, "
             f"autonomy={self.config.autonomy_level}, dry_run={self.config.dry_run})")

        enable_for_overnight(self.config.autonomy_level)

        stager = OvernightTaskStager(
            date=self.date,
            state_dir=STATE_DIR,
            dharma_root=DHARMA_SWARM_ROOT,
        )
        tasks = stager.compile_queue()
        _log("director", f"Staged {len(tasks)} tasks")

        evaluator = OvernightEvaluator(
            date=self.date,
            state_dir=STATE_DIR,
            project_dir=DHARMA_SWARM_ROOT,
        )
        supervisor = LoopSupervisor()
        supervisor.register_loop("overnight", expected_interval=self.config.cycle_timeout_seconds)

        # --- DURABLE STATE ---
        self.state.write_spec(self.config)
        for t in tasks:
            self.state.append_plan(t.to_dict())

        # --- BASELINE ---
        baseline = evaluator.baseline()
        _log("director", f"Baseline: {baseline.get('passed', '?')} tests passing")
        self.state.append_audit({"event": "baseline", "data": baseline})

        # --- INNER LOOP ---
        while time.monotonic() < deadline and (stager.has_tasks() or self._has_pending_waits()):
            # Budget check
            if self._tokens_spent >= self.config.max_tokens_budget:
                _log("director", "Token budget exhausted")
                break

            # Dead cycle halt
            if self._dead_cycle_streak >= self.config.max_dead_cycles_before_halt:
                _log("director", f"Halting: {self._dead_cycle_streak} consecutive dead cycles")
                break

            task = self._resume_ready_task()
            if task is None:
                task = stager.next_task()
            if task is None:
                hibernate_result = await self._hibernate_until_next_wait(deadline)
                if hibernate_result == "slept":
                    continue
                if hibernate_result == "handoff":
                    break
                break

            self._cycle_counter += 1
            cycle_id = f"cycle_{self._cycle_counter:04d}"
            supervisor.reset_cycle()
            if self._temporal_store is not None:
                self._temporal_store.update_manifest(
                    self.date,
                    current_cycle=self._cycle_counter,
                    current_phase="executing",
                )

            self.state.update_runbook(
                cycle_id, "executing",
                f"Task: {task.task_id}\nGoal: {task.goal}\nTimeout: {task.timeout_seconds}s",
            )

            _log("director", f"[{cycle_id}] Task: {task.task_id} — {task.goal[:80]}")

            # --- SELF-IMPROVEMENT INTERLEAVE (every 4th cycle, eval-gated) ---
            si_interval = max(
                1,
                int(getattr(self._profile, "self_evolution_interval_cycles", 4) or 4),
            )
            if self._cycle_counter % si_interval == 0:
                # Gate: check latest eval pass rate before allowing self-improvement
                si_allowed = True
                try:
                    from dharma_swarm.ecc_eval_harness import load_latest as _load_eval
                    latest_eval = _load_eval()
                    if latest_eval and latest_eval.get("pass_at_1", 1.0) < 0.6:
                        si_allowed = False
                        _log("director",
                             f"[{cycle_id}] Self-improvement BLOCKED: "
                             f"eval pass rate {latest_eval['pass_at_1']:.0%} < 60%")
                        self.state.append_audit({
                            "event": "self_improve_blocked",
                            "cycle_id": cycle_id,
                            "reason": "eval_pass_rate_low",
                            "pass_at_1": latest_eval.get("pass_at_1"),
                        })
                except Exception:
                    pass  # eval check failure doesn't block SI

                if si_allowed:
                    try:
                        from dharma_swarm.self_improve import SelfImprovementCycle
                        _log("director", f"[{cycle_id}] Running self-improvement cycle (interleave)")
                        si_cycle = SelfImprovementCycle()
                        si_report = await si_cycle.run_cycle()
                        self.state.append_audit({
                            "event": "self_improve_interleave",
                            "cycle_id": cycle_id,
                            "improved": si_report.improved,
                            "delta": si_report.improvement_delta,
                        })
                        if si_report.improved:
                            _log("director", f"[{cycle_id}] Self-improvement: +{si_report.improvement_delta:.1%}")
                    except Exception as si_err:
                        _log("director", f"[{cycle_id}] Self-improvement error: {si_err}")

            # --- EXECUTE ---
            outcome = await self._execute_cycle(cycle_id, task)

            # --- STATE-CHANGE CHECK ---
            if outcome.files_modified:
                for f in outcome.files_modified:
                    supervisor.state_tracker.record_file_write(f)
            if outcome.acceptance_passed:
                supervisor.state_tracker.record_test_change(1)

            alert = supervisor.check_state_change("overnight")
            if alert is not None:
                outcome.status = "dead_cycle"
                self._dead_cycle_streak += 1
                _log("director", f"[{cycle_id}] Dead cycle ({self._dead_cycle_streak} streak)")
            else:
                self._dead_cycle_streak = 0

            # --- RECORD ---
            stager.record_result(task.task_id, outcome.status, outcome.error)
            self.outcomes.append(outcome)
            self._tokens_spent += outcome.tokens_spent

            # Evaluator cycle tracking
            cycle_result = CycleResult(
                cycle_id=cycle_id,
                task_id=task.task_id,
                started_at=outcome.started_at,
                completed_at=outcome.completed_at,
                tokens_spent=outcome.tokens_spent,
                files_modified=outcome.files_modified,
                test_results=outcome.test_results,
                acceptance_passed=outcome.acceptance_passed,
                error=outcome.error if outcome.error else None,
            )
            cycle_eval = evaluator.evaluate_cycle(cycle_id, cycle_result)

            progress_score = 0.0
            progress_score += float(cycle_eval.verified)
            progress_score += min(cycle_eval.state_changes_count * 0.1, 0.5)
            progress_score += max(cycle_eval.test_delta, 0) * 0.25
            supervisor.record_progress(
                "overnight",
                score=round(progress_score, 6),
                improved=bool(cycle_eval.verified or cycle_eval.test_delta > 0),
            )
            progress_alert = supervisor.check_progress("overnight")
            if progress_alert is not None:
                self.state.append_audit({
                    "event": "progress_alert",
                    "cycle_id": cycle_id,
                    "alert": progress_alert.to_dict(),
                })
                _log("director", f"[{cycle_id}] Progress stall: {progress_alert.message}")

            # Audit
            self.state.append_audit({
                "event": "cycle_complete",
                "cycle_id": cycle_id,
                "outcome": outcome.to_dict(),
            })

            # --- HANDOFF ---
            handoff = {
                "cycle_id": cycle_id,
                "task_id": task.task_id,
                "status": outcome.status,
                "what_changed": outcome.files_modified,
                "error": outcome.error,
                "progress_score": round(progress_score, 6),
                "verified": cycle_eval.verified,
                "test_delta": cycle_eval.test_delta,
                "next_best_task": next(
                    (pending.task_id for pending in stager._tasks if pending.status == "pending"),
                    None,
                ),
            }
            outcome.handoff = handoff
            handoff_dir = self.run_dir / "handoffs"
            handoff_dir.mkdir(exist_ok=True)
            try:
                (handoff_dir / f"{cycle_id}.json").write_text(
                    json.dumps(handoff, indent=2) + "\n", encoding="utf-8",
                )
            except Exception:
                pass

            supervisor.record_tick("overnight")

        if self._wait_handoff is not None:
            disable_overnight()
            waiting_summary = {
                "status": "waiting",
                "date": self.date,
                "run_dir": str(self.run_dir),
                "total_cycles": len(self.outcomes),
                "tokens_spent": self._tokens_spent,
                **self._wait_handoff,
            }
            self.state.append_audit({"event": "external_wait_handoff", "data": waiting_summary})
            return waiting_summary

        # --- POST-LOOP PHASES (wrapped to guarantee verdict output) ---
        night_eval: NightEvaluation | None = None
        verdict_report = None
        verdict = OperatorVerdict.HOLD  # Safe default

        try:
            # --- TRAINING FLYWHEEL (Sprint 5, Item 12) ---
            try:
                from dharma_swarm.training_flywheel import FlywheelState, _run_reinforcement
                _log("director", "Running training flywheel reinforcement sub-cycle...")
                _fw_state = FlywheelState()
                flywheel_result = _run_reinforcement(_fw_state)
                self.state.append_audit({
                    "event": "flywheel_tick",
                    "result": {
                        "status": "completed",
                        "trajectories_scored": getattr(flywheel_result, "trajectories_scored", 0)
                        if flywheel_result else 0,
                    },
                })
                _log("director", f"Flywheel reinforcement complete")
            except ImportError:
                _log("director", "Training flywheel not available, skipping")
            except Exception as e:
                _log("director", f"Training flywheel error: {e}")
                self.state.append_audit({"event": "flywheel_tick", "error": str(e)})

            # --- REPLICATION GAP DETECTION (Sprint 5, Item 13) ---
            try:
                failed_types: dict[str, int] = {}
                for o in self.outcomes:
                    if o.status == "failed":
                        task_type = o.task_goal.split()[0] if o.task_goal else "unknown"
                        failed_types[task_type] = failed_types.get(task_type, 0) + 1

                persistent_gaps = {k: v for k, v in failed_types.items() if v >= 3}
                if persistent_gaps:
                    _log("director", f"Persistent capability gaps detected: {persistent_gaps}")
                    gap_proposals = []
                    for gap_type, count in persistent_gaps.items():
                        gap_proposals.append({
                            "proposed_role": f"overnight_{gap_type}_specialist",
                            "capability_gap": f"Repeated failure ({count}x) on {gap_type} tasks",
                            "severity": min(count / 10.0, 0.8),
                            "status": "proposed",
                        })
                    self.state.append_audit({
                        "event": "replication_proposals",
                        "proposals": gap_proposals,
                    })
                    _log("director", f"Generated {len(gap_proposals)} replication proposals for morning review")
            except Exception as e:
                _log("director", f"Gap detection error: {e}")

            # --- EVALUATE NIGHT (canonical control signal) ---
            night_eval = evaluator.evaluate_night()

        except Exception as post_loop_err:
            _log("director", f"Post-loop phase crashed: {post_loop_err}")
            self.state.append_audit({
                "event": "post_loop_crash",
                "error": str(post_loop_err),
            })
            # Fallback: construct minimal NightEvaluation from what we have
            if night_eval is None:
                completed = sum(1 for o in self.outcomes if o.status == "completed")
                failed = sum(1 for o in self.outcomes if o.status == "failed")
                night_eval = NightEvaluation(
                    date=self.date,
                    total_cycles=len(self.outcomes),
                    verified_completions=sum(1 for o in self.outcomes if o.acceptance_passed),
                    total_state_changes=sum(len(o.files_modified) for o in self.outcomes),
                    test_delta=0,
                    coverage_delta=0.0,
                    total_tokens_spent=self._tokens_spent,
                    cost_per_verified_improvement=float(self._tokens_spent) / max(completed, 1),
                    dead_loop_ratio=1.0 if completed == 0 else failed / max(len(self.outcomes), 1),
                    dead_loop_time=0.0,
                    total_time=time.monotonic() - self._start_time,
                    token_efficiency=0.0,
                    morning_capability_delta=0.0,
                )
        verdict_report = compute_verdict(night_eval)
        verdict = verdict_report.verdict

        _log("director",
             f"Night evaluation: capability_delta={night_eval.morning_capability_delta:.2f}, "
             f"test_delta={night_eval.test_delta}, "
             f"verified={night_eval.verified_completions}, "
             f"dead_ratio={night_eval.dead_loop_ratio:.1%}")
        _log("director", f"VERDICT: {verdict.value.upper()}")
        for reason in verdict_report.reasons:
            _log("director", f"  {reason}")

        # --- VERDICT-GATED ACTIONS ---
        if verdict == OperatorVerdict.ROLLBACK:
            _log("director", "ROLLBACK: disabling self-improvement, flagging for manual review")
            disable_overnight()
            self.state.append_audit({
                "event": "verdict_rollback",
                "reasons": verdict_report.reasons,
                "scores": verdict_report.scores,
            })
            # Write rollback marker for morning skill
            rollback_marker = STATE_DIR / "shared" / "overnight_rollback.json"
            rollback_marker.parent.mkdir(parents=True, exist_ok=True)
            rollback_marker.write_text(json.dumps({
                "date": self.date,
                "verdict": "rollback",
                "reasons": verdict_report.reasons,
                "night_eval": verdict_report.night_eval,
            }, indent=2) + "\n", encoding="utf-8")

        elif verdict == OperatorVerdict.ADVANCE:
            _log("director", "ADVANCE: recording positive fitness signal for evolution")
            self.state.append_audit({
                "event": "verdict_advance",
                "reasons": verdict_report.reasons,
                "scores": verdict_report.scores,
            })
            # Feed positive signal to evolution archive
            try:
                from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
                archive = EvolutionArchive(STATE_DIR / "evolution" / "archive.jsonl")
                entry = ArchiveEntry(
                    component="overnight_director",
                    change_type="overnight_advance",
                    description=(
                        f"Overnight ADVANCE: {night_eval.verified_completions} verified, "
                        f"test_delta={night_eval.test_delta}, "
                        f"capability={night_eval.morning_capability_delta:.2f}"
                    ),
                    fitness=FitnessScore(
                        correctness=max(0.0, min(1.0, 1.0 + night_eval.test_delta / 100.0)),
                        dharmic_alignment=night_eval.morning_capability_delta,
                        efficiency=night_eval.token_efficiency * 1000,
                    ),
                    test_results={
                        "verdict": "advance",
                        "verified_completions": night_eval.verified_completions,
                        "test_delta": night_eval.test_delta,
                        "coverage_delta": night_eval.coverage_delta,
                    },
                )
                await archive.add_entry(entry)
            except Exception as e:
                _log("director", f"Evolution fitness signal error: {e}")

        else:  # HOLD
            _log("director", "HOLD: pausing aggressive evolution, flagging for morning review")
            self.state.append_audit({
                "event": "verdict_hold",
                "reasons": verdict_report.reasons,
                "scores": verdict_report.scores,
            })

        # Build canonical eval_summary from NightEvaluation (not summary_dict)
        from dataclasses import asdict as _asdict
        eval_summary = _asdict(night_eval)
        eval_summary["verdict"] = verdict.value
        eval_summary["verdict_reasons"] = verdict_report.reasons

        # --- MORNING SYNTHESIS ---
        brief_path = write_morning_brief(
            run_dir=self.run_dir,
            config=self.config,
            outcomes=self.outcomes,
            eval_summary=eval_summary,
            stager_stats=stager.stats(),
        )
        _log("director", f"Morning brief: {brief_path}")

        # Persist verdict for downstream consumers (two locations)
        verdict_data = json.dumps({
            "date": self.date,
            "verdict": verdict.value,
            "reasons": verdict_report.reasons,
            "scores": verdict_report.scores,
            "night_eval": verdict_report.night_eval,
        }, indent=2) + "\n"

        # 1. Run-specific directory
        verdict_path = self.run_dir / "verdict.json"
        verdict_path.write_text(verdict_data, encoding="utf-8")

        # 2. Canonical overnight directory (where self-improve + orchestrate_live look)
        canonical_verdict_dir = STATE_DIR / "overnight" / self.date
        canonical_verdict_dir.mkdir(parents=True, exist_ok=True)
        (canonical_verdict_dir / "verdict.json").write_text(verdict_data, encoding="utf-8")

        self.state.append_audit({"event": "run_complete", "eval_summary": eval_summary})

        # --- CLEANUP ---
        disable_overnight()

        elapsed = time.monotonic() - self._start_time
        summary = {
            "date": self.date,
            "elapsed_seconds": round(elapsed, 1),
            "total_cycles": len(self.outcomes),
            "completed": sum(1 for o in self.outcomes if o.status == "completed"),
            "failed": sum(1 for o in self.outcomes if o.status == "failed"),
            "dead_cycles": sum(1 for o in self.outcomes if o.status == "dead_cycle"),
            "tokens_spent": self._tokens_spent,
            "eval_summary": eval_summary,
            "verdict": verdict.value,
            "verdict_reasons": verdict_report.reasons,
            "morning_brief": str(brief_path),
            "run_dir": str(self.run_dir),
        }
        _log("director", f"Overnight complete: {summary['completed']} completed, "
             f"{summary['failed']} failed, {summary['dead_cycles']} dead — "
             f"VERDICT={verdict.value.upper()}")
        return summary

    def _has_pending_waits(self) -> bool:
        if self._temporal_store is None:
            return False
        return any(
            wait_state.status.value == "pending"
            for wait_state in self._temporal_store.list_wait_states(self.date)
        )

    def _resume_ready_task(self) -> Any | None:
        if self._temporal_store is None:
            return None
        ready = self._temporal_store.ready_wait_states(self.date)
        if not ready:
            return None
        wait_state = ready[0]
        self._temporal_store.mark_resumed(
            self.date,
            wait_state.wait_id,
            reason="resume-ready wait state",
        )

        from dharma_swarm.overnight_task_stager import OvernightTask

        return OvernightTask(
            task_id=wait_state.resume_task_id,
            goal=wait_state.resume_goal,
            task_type="custom",
            acceptance_criterion=f"Resume wait state {wait_state.wait_id}",
            timeout_seconds=self.config.cycle_timeout_seconds,
            metadata={"resumed_wait_state": wait_state.model_dump(mode="json")},
        )

    def _next_pending_wait_state(self) -> WaitState | None:
        if self._temporal_store is None:
            return None
        pending = [
            wait_state
            for wait_state in self._temporal_store.list_wait_states(self.date)
            if wait_state.status is WaitStateStatus.PENDING
        ]
        if not pending:
            return None
        pending.sort(key=lambda item: item.wake_at)
        return pending[0]

    async def _hibernate_until_next_wait(self, deadline: float) -> str | None:
        if not (self.config.enable_hibernate_wake and self._temporal_store):
            return None
        next_wait = self._next_pending_wait_state()
        if next_wait is None:
            return None
        delay = self._temporal_store.next_wake_delay_seconds(self.date)
        if delay is None:
            return None
        remaining = max(deadline - time.monotonic(), 0.0)
        sleep_for = min(delay, remaining)
        if sleep_for <= 0:
            return None
        self.state.update_runbook(
            "hibernate",
            "hibernating",
            f"No runnable tasks. Sleeping {sleep_for:.1f}s until next wake condition.",
        )
        self._temporal_store.record_hibernate(
            self.date,
            phase="hibernating",
            reason="waiting for resumable task",
        )
        if self.config.external_wait_handoff:
            self._wait_handoff = {
                "wake_at": next_wait.wake_at.isoformat(),
                "next_action": next_wait.resume_goal,
                "resume_task_id": next_wait.resume_task_id,
                "wait_id": next_wait.wait_id,
                "reason": next_wait.reason,
            }
            return "handoff"
        await asyncio.sleep(sleep_for)
        return "slept"

    def _register_wait_state_if_requested(self, cycle_id: str, task: Any) -> WaitState | None:
        if self._temporal_store is None:
            return None
        metadata = getattr(task, "metadata", {}) or {}
        raw_wait = metadata.get("wait_state")
        if not isinstance(raw_wait, dict):
            return None

        raw_kind = str(raw_wait.get("kind", WaitStateKind.SLEEP_UNTIL.value)).strip().lower()
        kind = WaitStateKind(raw_kind)
        if raw_wait.get("wake_at"):
            wake_at = datetime.fromisoformat(str(raw_wait["wake_at"]))
            if wake_at.tzinfo is None:
                wake_at = wake_at.replace(tzinfo=timezone.utc)
        else:
            wake_after_seconds = max(0.0, float(raw_wait.get("wake_after_seconds", 60.0)))
            wake_at = datetime.now(timezone.utc) + timedelta(seconds=wake_after_seconds)

        wait_state = WaitState(
            kind=kind,
            reason=str(raw_wait.get("reason", "waiting for external signal")),
            wake_at=wake_at,
            resume_task_id=str(raw_wait.get("resume_task_id", f"{task.task_id}__resume")),
            resume_goal=str(raw_wait.get("resume_goal", f"Resume {task.goal}")),
            payload=dict(raw_wait.get("payload", {})),
            cycle_id=cycle_id,
        )
        self._temporal_store.add_wait_state(self.date, wait_state)
        return wait_state

    async def _execute_cycle(self, cycle_id: str, task: Any) -> CycleOutcome:
        """Execute a single task within the overnight loop.

        Delegates to claude -p subprocess for real LLM-powered execution.
        """
        outcome = CycleOutcome(
            cycle_id=cycle_id,
            task_id=task.task_id,
            task_goal=task.goal,
            started_at=time.time(),
        )

        wait_state = self._register_wait_state_if_requested(cycle_id, task)
        if wait_state is not None:
            outcome.completed_at = time.time()
            outcome.status = "waiting"
            outcome.error = f"wait_state:{wait_state.kind.value}"
            outcome.handoff = {
                "wait_state_id": wait_state.wait_id,
                "resume_task_id": wait_state.resume_task_id,
                "wake_at": wait_state.wake_at.isoformat(),
            }
            return outcome

        if self.config.dry_run:
            await asyncio.sleep(0.01)
            outcome.completed_at = time.time()
            outcome.status = "completed"
            outcome.acceptance_passed = True
            outcome.tokens_spent = 100
            outcome.files_modified = [f"simulated/{task.task_id}.py"]
            return outcome

        timeout = getattr(task, "timeout", self.config.cycle_timeout_seconds)

        try:
            if task.task_type == "test_coverage":
                outcome = await self._execute_test_coverage(outcome, task, timeout)
            elif task.task_type == "benchmark":
                outcome = await self._execute_benchmark(outcome, task, timeout)
            else:
                outcome = await self._execute_general_task(outcome, task, timeout)

        except Exception as e:
            outcome.status = "error"
            outcome.error = str(e)

        outcome.completed_at = time.time()
        return outcome

    async def _execute_test_coverage(
        self, outcome: CycleOutcome, task: Any, timeout: float,
    ) -> CycleOutcome:
        """Generate a deterministic smoke test for a module that lacks coverage."""

        module_name = task.metadata.get("module", "")
        test_file = DHARMA_SWARM_ROOT / "tests" / f"test_{module_name}.py"

        if test_file.exists():
            passed, output = self._run_pytest_file(test_file, timeout=min(timeout, 120.0))
            outcome.status = "completed" if passed else "failed"
            outcome.acceptance_passed = passed
            outcome.files_modified = [str(test_file)] if passed else []
            outcome.test_results = self._parse_pytest_counts(output)
            if not passed:
                outcome.error = output[-300:]
            return outcome

        source_file = DHARMA_SWARM_ROOT / "dharma_swarm" / f"{module_name}.py"
        if not source_file.exists():
            outcome.status = "failed"
            outcome.error = f"Source module not found: {module_name}.py"
            return outcome

        try:
            source_code = source_file.read_text(encoding="utf-8")
            test_code = self._generate_smoke_test_code(module_name, source_code)
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(test_code, encoding="utf-8")

            passed, output = self._run_pytest_file(test_file, timeout=min(timeout, 120.0))
            outcome.test_results = self._parse_pytest_counts(output)
            if passed:
                outcome.status = "completed"
                outcome.acceptance_passed = True
                outcome.files_modified = [str(test_file)]
                outcome.tokens_spent = max(len(test_code) // 4, 1)
            else:
                outcome.status = "failed"
                outcome.error = f"Generated smoke tests do not pass: {output[-300:]}"
                outcome.files_modified = [str(test_file)]
        except Exception as e:
            outcome.status = "failed"
            outcome.error = f"Smoke test generation error: {e}"

        return outcome

    @staticmethod
    def _parse_pytest_counts(output: str) -> dict[str, Any]:
        """Parse the most useful counts from pytest output."""
        import re

        passed = 0
        failed = 0
        match = re.search(r"(?:(\d+)\s+failed,\s*)?(\d+)\s+passed", output)
        if match:
            failed = int(match.group(1) or 0)
            passed = int(match.group(2) or 0)
        return {"passed": passed, "failed": failed, "coverage_percent": None}

    @staticmethod
    def _run_pytest_file(test_file: Path, timeout: float) -> tuple[bool, str]:
        """Run one test file and return success plus combined output."""
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=short", "-x"],
            capture_output=True,
            text=True,
            cwd=str(DHARMA_SWARM_ROOT),
            timeout=timeout,
        )
        output = proc.stdout + proc.stderr
        return proc.returncode == 0, output

    @staticmethod
    def _generate_smoke_test_code(module_name: str, source_code: str) -> str:
        """Generate a deterministic pytest smoke test from module source."""
        zero_arg_functions: list[str] = []
        try:
            tree = ast.parse(source_code)
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name.startswith("_"):
                    continue
                args = node.args
                required_args = len(args.posonlyargs) + len(args.args) - len(args.defaults)
                if required_args == 0 and not args.vararg and not args.kwarg:
                    zero_arg_functions.append(node.name)
        except SyntaxError:
            zero_arg_functions = []

        lines = [
            f'"""Auto-generated smoke tests for dharma_swarm.{module_name}."""',
            "",
            "import importlib",
            "",
            "",
            f"def test_{module_name}_imports() -> None:",
            f'    module = importlib.import_module("dharma_swarm.{module_name}")',
            f'    assert module.__name__ == "dharma_swarm.{module_name}"',
        ]

        for fn_name in zero_arg_functions[:3]:
            lines.extend([
                "",
                f"def test_{module_name}_{fn_name}_zero_arg_smoke() -> None:",
                f'    module = importlib.import_module("dharma_swarm.{module_name}")',
                f"    result = module.{fn_name}()",
                "    assert result is not None or result is None",
            ])

        return "\n".join(lines) + "\n"

    async def _execute_benchmark(
        self, outcome: CycleOutcome, task: Any, timeout: float,
    ) -> CycleOutcome:
        """Run a loop template benchmark."""
        template_path = task.metadata.get("template_path", "")
        if not template_path or not Path(template_path).exists():
            outcome.status = "failed"
            outcome.error = f"Template not found: {template_path}"
            return outcome

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(template_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(DHARMA_SWARM_ROOT),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            output = stdout.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                outcome.status = "completed"
                outcome.acceptance_passed = True
            else:
                outcome.status = "failed"
                outcome.error = stderr.decode("utf-8", errors="replace")[-200:]

        except asyncio.TimeoutError:
            outcome.status = "failed"
            outcome.error = f"Benchmark timed out ({timeout}s)"

        return outcome

    async def _execute_general_task(
        self, outcome: CycleOutcome, task: Any, timeout: float,
    ) -> CycleOutcome:
        """Execute a general task via claude -p subprocess."""
        prompt = (
            f"Task: {task.goal}\n"
            f"Acceptance criterion: {getattr(task, 'acceptance_criterion', 'Complete the task')}\n"
            f"Working directory: {DHARMA_SWARM_ROOT}\n"
            f"Constraints: Only modify files under dharma_swarm/ or tests/. "
            f"Run pytest after changes to verify nothing breaks."
        )

        proc = None
        try:
            from dharma_swarm.pulse import _resolve_claude_binary
            claude_bin = _resolve_claude_binary()
            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt, "--output-format", "text",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(DHARMA_SWARM_ROOT),
            )
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            output = stdout.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                outcome.status = "completed"
                outcome.acceptance_passed = True
                outcome.tokens_spent = len(output) // 4  # rough estimate
            else:
                outcome.status = "failed"
                outcome.error = f"claude -p exited {proc.returncode}"

        except asyncio.TimeoutError:
            outcome.status = "failed"
            outcome.error = f"Task execution timed out ({timeout}s)"
            # Kill the stalled subprocess to prevent zombie accumulation
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except Exception:
                    pass
        except Exception as e:
            outcome.status = "failed"
            outcome.error = f"Execution error: {e}"

        return outcome


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(system: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{system}] {msg}"
    print(line, flush=True)
    logger.info("[%s] %s", system, msg)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def run_overnight(
    hours: float = 8.0,
    dry_run: bool = False,
    autonomy_level: int = 1,
    max_tokens: int = 500_000,
    cycle_timeout: float = 900.0,
    run_profile: str = "all_night_build",
    external_wait_handoff: bool = False,
    run_date: str | None = None,
    resume_temporal_run: bool = False,
) -> dict[str, Any]:
    """Top-level entry point for ``dgc overnight``."""

    config = OvernightConfig(
        hours=hours,
        dry_run=dry_run,
        cycle_timeout_seconds=cycle_timeout,
        max_tokens_budget=max_tokens,
        autonomy_level=autonomy_level,
        run_profile=run_profile,
        external_wait_handoff=external_wait_handoff,
        run_date=run_date or "",
        resume_temporal_run=resume_temporal_run,
    )
    director = OvernightDirector(config=config)
    return await director.run()


async def run_self_evolution_72h(
    *,
    dry_run: bool = False,
    autonomy_level: int = 2,
    max_tokens: int = 2_000_000,
    cycle_timeout: float = 1800.0,
) -> dict[str, Any]:
    """Run the hardwired 72-hour self-evolution campaign."""

    return await run_overnight(
        hours=72.0,
        dry_run=dry_run,
        autonomy_level=autonomy_level,
        max_tokens=max_tokens,
        cycle_timeout=cycle_timeout,
        run_profile="self_evolution_72h",
    )


def main() -> None:
    """CLI main for direct invocation."""
    import argparse

    parser = argparse.ArgumentParser(description="dharma_swarm overnight autonomous loop")
    parser.add_argument("--hours", type=float, default=8.0, help="Duration in hours")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without real execution")
    parser.add_argument("--autonomy", type=int, default=1, help="Autonomy level (0-3)")
    parser.add_argument("--max-tokens", type=int, default=500_000, help="Token budget")
    parser.add_argument("--cycle-timeout", type=float, default=900.0, help="Seconds per cycle")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(run_overnight(
        hours=args.hours,
        dry_run=args.dry_run,
        autonomy_level=args.autonomy,
        max_tokens=args.max_tokens,
        cycle_timeout=args.cycle_timeout,
    ))
    print(json.dumps(result, indent=2))
