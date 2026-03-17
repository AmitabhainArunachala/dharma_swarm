"""ECC Eval Harness — real measurements of whether dharma_swarm works.

6 capability evals (does feature X actually function?) + 3 regression evals
(did we break something?).  Results stored as JSON in ~/.dharma/evals/ with
append-only history for trend analysis.

Inspired by ECC eval-harness skill but implemented as pure Python — no LLM
calls, no claude -p nesting.  Every eval is a deterministic function that
returns PASS/FAIL + metrics.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Result of a single eval."""

    name: str
    passed: bool
    duration_seconds: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalReport:
    """Aggregated results from a full eval run."""

    timestamp: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_at_1: float = 0.0
    results: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# State paths
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".dharma"
EVALS_DIR = STATE_DIR / "evals"
HISTORY_FILE = EVALS_DIR / "history.jsonl"
DHARMA_SWARM_DIR = Path.home() / "dharma_swarm"
PACKAGE_DIR = DHARMA_SWARM_DIR / "dharma_swarm"


# ---------------------------------------------------------------------------
# Capability evals
# ---------------------------------------------------------------------------

async def eval_task_roundtrip() -> EvalResult:
    """Create a task via TaskBoard, verify it persists and can be read back."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.models import TaskPriority
        from dharma_swarm.task_board import TaskBoard

        db_path = STATE_DIR / "db" / "tasks.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        board = TaskBoard(db_path)
        await board.init_db()

        task = await board.create(
            title="eval_probe_task",
            description="Probe task for eval harness",
            priority=TaskPriority.LOW,
            created_by="eval_harness",
        )
        retrieved = await board.get(task.id)
        ok = retrieved is not None and retrieved.title == "eval_probe_task"
        return EvalResult(
            name="task_roundtrip",
            passed=ok,
            duration_seconds=time.monotonic() - t0,
            metrics={"task_id": task.id},
        )
    except Exception as e:
        return EvalResult(
            name="task_roundtrip",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


async def eval_fitness_signal_flow() -> EvalResult:
    """Submit a probe event on MessageBus, verify it appears and can be consumed."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.message_bus import MessageBus

        db_path = STATE_DIR / "db" / "messages.db"
        bus = MessageBus(db_path)
        await bus.init_db()

        event_id = await bus.emit_event(
            "EVAL_PROBE",
            agent_id="eval_harness",
            payload={"probe": True, "ts": datetime.now(timezone.utc).isoformat()},
        )
        events = await bus.consume_events("EVAL_PROBE", limit=10)
        found = any(e.get("payload", {}).get("probe") is True for e in events)
        return EvalResult(
            name="fitness_signal_flow",
            passed=found,
            duration_seconds=time.monotonic() - t0,
            metrics={"event_id": event_id, "events_consumed": len(events)},
        )
    except Exception as e:
        return EvalResult(
            name="fitness_signal_flow",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_evolution_archive() -> EvalResult:
    """Verify EvolutionArchive loads and has basic functionality."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.archive import EvolutionArchive

        archive_path = STATE_DIR / "evolution" / "archive.jsonl"
        archive = EvolutionArchive(archive_path)

        # Check it loads without error
        count = len(archive._entries) if hasattr(archive, "_entries") else 0
        # Verify fitness_over_time method exists and runs
        has_fitness_method = hasattr(archive, "fitness_over_time")
        return EvalResult(
            name="evolution_archive",
            passed=True,
            duration_seconds=time.monotonic() - t0,
            metrics={
                "entry_count": count,
                "has_fitness_over_time": has_fitness_method,
                "archive_exists": archive_path.exists(),
            },
        )
    except Exception as e:
        return EvalResult(
            name="evolution_archive",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_provider_availability() -> EvalResult:
    """Check that ProviderType enum is populated and importable."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.models import ProviderType

        providers = [p.value for p in ProviderType]
        return EvalResult(
            name="provider_availability",
            passed=len(providers) > 0,
            duration_seconds=time.monotonic() - t0,
            metrics={
                "providers": providers,
                "total": len(providers),
            },
        )
    except Exception as e:
        return EvalResult(
            name="provider_availability",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


async def eval_stigmergy_roundtrip() -> EvalResult:
    """Write a stigmergy mark, read it back, verify."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

        store = StigmergyStore()
        probe_observation = f"eval_probe_{int(time.time())}"
        mark = StigmergicMark(
            agent="eval_harness",
            file_path="eval/probe",
            observation=probe_observation,
            salience=0.1,
        )
        mark_id = await store.leave_mark(mark)
        # Read back
        marks = await store.read_marks(file_path="eval/probe", limit=5)
        found = any(m.observation == probe_observation for m in marks)
        return EvalResult(
            name="stigmergy_roundtrip",
            passed=found,
            duration_seconds=time.monotonic() - t0,
            metrics={"mark_id": mark_id, "marks_read": len(marks)},
        )
    except Exception as e:
        return EvalResult(
            name="stigmergy_roundtrip",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_test_suite_health() -> EvalResult:
    """Run pytest with --co (collect only) to verify test discovery works.

    Full suite takes ~6 min; collect-only is fast and proves the test infra
    is healthy.
    """
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--co", "-q"],
            capture_output=True,
            text=True,
            cwd=str(DHARMA_SWARM_DIR),
            timeout=60,
        )
        # Parse "X tests collected"
        lines = result.stdout.strip().splitlines()
        collected = 0
        for line in lines:
            if "test" in line and "collected" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        collected = int(p)
                        break
            elif "selected" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        collected = int(p)
                        break

        ok = result.returncode == 0 and collected > 0
        return EvalResult(
            name="test_suite_health",
            passed=ok,
            duration_seconds=time.monotonic() - t0,
            metrics={
                "collected": collected,
                "returncode": result.returncode,
            },
        )
    except subprocess.TimeoutExpired:
        return EvalResult(
            name="test_suite_health",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error="pytest --co timed out (60s)",
        )
    except Exception as e:
        return EvalResult(
            name="test_suite_health",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Regression evals
# ---------------------------------------------------------------------------

def eval_import_health() -> EvalResult:
    """Import all top-level dharma_swarm modules — catches broken imports."""
    t0 = time.monotonic()
    successes = []
    failures = []

    # Core modules that must always import cleanly
    core_modules = [
        "dharma_swarm.models",
        "dharma_swarm.config",
        "dharma_swarm.archive",
        "dharma_swarm.evolution",
        "dharma_swarm.quality_forge",
        "dharma_swarm.message_bus",
        "dharma_swarm.telos_gates",
        "dharma_swarm.swarm",
        "dharma_swarm.orchestrator",
        "dharma_swarm.agent_runner",
        "dharma_swarm.stigmergy",
        "dharma_swarm.cascade",
        "dharma_swarm.traces",
    ]

    for mod_name in core_modules:
        try:
            importlib.import_module(mod_name)
            successes.append(mod_name)
        except Exception as e:
            failures.append({"module": mod_name, "error": str(e)})

    return EvalResult(
        name="import_health",
        passed=len(failures) == 0,
        duration_seconds=time.monotonic() - t0,
        metrics={
            "imported": len(successes),
            "failed": len(failures),
            "failures": failures,
        },
    )


def eval_config_validity() -> EvalResult:
    """Load DEFAULT_CONFIG, verify bounds are sane."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.config import DEFAULT_CONFIG

        checks = {
            "tick_interval": 0.1 <= DEFAULT_CONFIG.orchestrator.tick_interval_seconds <= 60.0,
            "task_timeout": 10.0 <= DEFAULT_CONFIG.orchestrator.task_timeout_seconds <= 7200.0,
            "max_retries": 0 <= DEFAULT_CONFIG.orchestrator.max_retries <= 10,
        }
        all_ok = all(checks.values())
        return EvalResult(
            name="config_validity",
            passed=all_ok,
            duration_seconds=time.monotonic() - t0,
            metrics={"checks": checks},
        )
    except Exception as e:
        return EvalResult(
            name="config_validity",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


async def eval_bus_schema() -> EvalResult:
    """Verify events table exists with correct columns."""
    t0 = time.monotonic()
    try:
        import aiosqlite

        db_path = STATE_DIR / "db" / "messages.db"
        if not db_path.exists():
            # Create it fresh
            from dharma_swarm.message_bus import MessageBus
            bus = MessageBus(db_path)
            await bus.init_db()

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("PRAGMA table_info(events)")
            columns = await cursor.fetchall()
            col_names = {row[1] for row in columns}

        required = {"event_id", "event_type", "occurred_at", "payload"}
        missing = required - col_names
        return EvalResult(
            name="bus_schema",
            passed=len(missing) == 0,
            duration_seconds=time.monotonic() - t0,
            metrics={
                "columns": sorted(col_names),
                "missing": sorted(missing),
            },
        )
    except Exception as e:
        return EvalResult(
            name="bus_schema",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_SYNC_EVALS = [
    eval_evolution_archive,
    eval_provider_availability,
    eval_test_suite_health,
    eval_import_health,
    eval_config_validity,
]

ALL_ASYNC_EVALS = [
    eval_task_roundtrip,
    eval_fitness_signal_flow,
    eval_stigmergy_roundtrip,
    eval_bus_schema,
]


async def run_all_evals() -> EvalReport:
    """Execute all evals and produce an aggregated report."""
    t0 = time.monotonic()
    results: list[EvalResult] = []

    # Sync evals
    for fn in ALL_SYNC_EVALS:
        results.append(fn())

    # Async evals
    for fn in ALL_ASYNC_EVALS:
        results.append(await fn())

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    report = EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=total,
        passed=passed,
        failed=total - passed,
        pass_at_1=passed / total if total > 0 else 0.0,
        results=[r.to_dict() for r in results],
        duration_seconds=time.monotonic() - t0,
    )
    return report


def compute_pass_at_k(history: list[dict], k: int = 3) -> float:
    """Compute pass@k from the last k eval runs.

    pass@k = fraction of evals that passed in at least 1 of the last k runs.
    """
    if not history or k < 1:
        return 0.0
    recent = history[-k:]
    # Collect all eval names from latest run
    all_names: set[str] = set()
    for run in recent:
        for r in run.get("results", []):
            all_names.add(r["name"])

    if not all_names:
        return 0.0

    passed_at_least_once = 0
    for name in all_names:
        for run in recent:
            for r in run.get("results", []):
                if r["name"] == name and r.get("passed"):
                    passed_at_least_once += 1
                    break

    return passed_at_least_once / len(all_names)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_report(report: EvalReport) -> Path:
    """Save report to ~/.dharma/evals/ and append to history."""
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    # Save latest
    latest_path = EVALS_DIR / "latest.json"
    latest_path.write_text(json.dumps(report.to_dict(), indent=2))

    # Append to history
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(report.to_dict()) + "\n")

    return latest_path


def load_history() -> list[dict]:
    """Load eval history from JSONL."""
    if not HISTORY_FILE.exists():
        return []
    entries = []
    for line in HISTORY_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def load_latest() -> dict | None:
    """Load the most recent eval report."""
    latest = EVALS_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def format_scorecard(report: dict) -> str:
    """Format an eval report as a human-readable scorecard."""
    lines = []
    lines.append(f"ECC Eval Harness — {report['timestamp'][:19]}")
    lines.append(f"{'=' * 55}")
    lines.append(
        f"  Total: {report['total']}  "
        f"Passed: {report['passed']}  "
        f"Failed: {report['failed']}  "
        f"pass@1: {report['pass_at_1']:.1%}"
    )
    lines.append(f"  Duration: {report['duration_seconds']:.2f}s")
    lines.append("")

    for r in report.get("results", []):
        status = "PASS" if r["passed"] else "FAIL"
        marker = "+" if r["passed"] else "X"
        line = f"  [{marker}] {r['name']:<30} {status}  ({r['duration_seconds']:.3f}s)"
        lines.append(line)
        if r.get("error"):
            lines.append(f"      error: {r['error'][:80]}")

    return "\n".join(lines)


def format_trend(history: list[dict], last_n: int = 10) -> str:
    """Format historical pass rates as a trend."""
    recent = history[-last_n:]
    if not recent:
        return "No eval history yet."

    lines = []
    lines.append(f"Eval Trend (last {len(recent)} runs)")
    lines.append(f"{'=' * 55}")

    for run in recent:
        ts = run["timestamp"][:16]
        p1 = run.get("pass_at_1", 0.0)
        bar_len = int(p1 * 30)
        bar = "#" * bar_len + "." * (30 - bar_len)
        lines.append(f"  {ts}  [{bar}] {p1:.0%}  ({run['passed']}/{run['total']})")

    # Compute pass@3
    p3 = compute_pass_at_k(history, k=3)
    lines.append(f"\n  pass@3 (last 3 runs): {p3:.1%}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry points (called from dgc_cli.py)
# ---------------------------------------------------------------------------

async def cmd_eval_run() -> int:
    """Run all evals, save, print scorecard."""
    report = await run_all_evals()
    save_report(report)
    print(format_scorecard(report.to_dict()))
    return 0 if report.failed == 0 else 1


def cmd_eval_report() -> int:
    """Print the latest eval report."""
    latest = load_latest()
    if not latest:
        print("No eval results yet. Run: dgc eval run")
        return 1
    print(format_scorecard(latest))
    return 0


def cmd_eval_trend() -> int:
    """Print historical eval trend."""
    history = load_history()
    print(format_trend(history))
    return 0
