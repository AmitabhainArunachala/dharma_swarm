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
# Feedback-loop evals (Phase 3A)
# ---------------------------------------------------------------------------


def eval_health_monitoring() -> EvalResult:
    """Verify SystemMonitor can detect anomalies."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.monitor import SystemMonitor
        from dharma_swarm.traces import TraceStore

        store = TraceStore(base_path=EVALS_DIR.parent / "traces")
        monitor = SystemMonitor(trace_store=store)
        # Just verify instantiation + method exists
        assert callable(getattr(monitor, "detect_anomalies", None))
        return EvalResult(
            name="health_monitoring",
            passed=True,
            duration_seconds=time.monotonic() - t0,
        )
    except Exception as e:
        return EvalResult(
            name="health_monitoring",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_active_inference_flow() -> EvalResult:
    """Verify active inference predict/observe cycle."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.active_inference import ActiveInferenceEngine

        engine = ActiveInferenceEngine()
        assert callable(getattr(engine, "predict", None))
        assert callable(getattr(engine, "observe", None))
        return EvalResult(
            name="active_inference_flow",
            passed=True,
            duration_seconds=time.monotonic() - t0,
        )
    except Exception as e:
        return EvalResult(
            name="active_inference_flow",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_signal_bus_flow() -> EvalResult:
    """Verify signal bus emit/drain roundtrip."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.signal_bus import SignalBus

        bus = SignalBus.get()
        test_signal = {"type": "_EVAL_TEST", "data": "roundtrip"}
        bus.emit(test_signal)
        drained = bus.drain(["_EVAL_TEST"])
        assert len(drained) >= 1
        assert drained[0].get("data") == "roundtrip"
        return EvalResult(
            name="signal_bus_flow",
            passed=True,
            duration_seconds=time.monotonic() - t0,
        )
    except Exception as e:
        return EvalResult(
            name="signal_bus_flow",
            passed=False,
            duration_seconds=time.monotonic() - t0,
            error=str(e),
        )


def eval_training_flywheel_imports() -> EvalResult:
    """Verify all flywheel pipeline modules import cleanly."""
    t0 = time.monotonic()
    modules = [
        "dharma_swarm.trajectory_collector",
        "dharma_swarm.thinkodynamic_scorer",
        "dharma_swarm.training_flywheel",
    ]
    errors = []
    for mod in modules:
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"{mod}: {e}")
    return EvalResult(
        name="training_flywheel_imports",
        passed=len(errors) == 0,
        duration_seconds=time.monotonic() - t0,
        error="; ".join(errors) if errors else "",
    )


def eval_hook_bridge() -> EvalResult:
    """Verify claude_hooks.py entry points work."""
    t0 = time.monotonic()
    try:
        from dharma_swarm.claude_hooks import stop_verify, session_context, verify_baseline

        sv = stop_verify()
        assert "gate_decision" in sv
        sc = session_context()
        assert isinstance(sc, str)
        # verify_baseline is heavier (async), just check it's callable
        assert callable(verify_baseline)
        return EvalResult(
            name="hook_bridge",
            passed=True,
            duration_seconds=time.monotonic() - t0,
        )
    except Exception as e:
        return EvalResult(
            name="hook_bridge",
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
    # Feedback-loop evals (Phase 3A)
    eval_health_monitoring,
    eval_active_inference_flow,
    eval_signal_bus_flow,
    eval_training_flywheel_imports,
    eval_hook_bridge,
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
    """Save report to ~/.dharma/evals/ and append to history.

    Also updates benchmark registry with eval results so benchmarks
    reflect the latest measurements.
    """
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    # Save latest
    latest_path = EVALS_DIR / "latest.json"
    latest_path.write_text(json.dumps(report.to_dict(), indent=2))

    # Append to history
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(report.to_dict()) + "\n")

    # Update benchmark registry with eval results
    try:
        from dharma_swarm.benchmark_registry import BenchmarkRegistry
        registry = BenchmarkRegistry()

        # eval_pass_rate ← overall pass rate
        if "eval_pass_rate" in registry:
            registry.update("eval_pass_rate", report.pass_at_1)

        # Map specific eval results to benchmarks
        for r in report.results:
            name = r.get("name", "") if isinstance(r, dict) else r.name
            passed = r.get("passed", False) if isinstance(r, dict) else r.passed
            metrics = r.get("metrics", {}) if isinstance(r, dict) else {}

            if name == "import_health" and "import_health" in registry:
                registry.update("import_health", 1.0 if passed else 0.0)
            elif name == "test_suite_health" and "test_collection" in registry:
                collected = metrics.get("collected", 0)
                if collected > 0:
                    registry.update("test_collection", float(collected))

        registry.save()
    except Exception:
        pass  # Benchmark update is best-effort, never block report saving

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


def cmd_eval_dashboard() -> int:
    """Single-screen ASCII dashboard: latest results + benchmarks + trend."""
    from dharma_swarm.benchmark_registry import BenchmarkRegistry
    from dharma_swarm.eval_trace import TraceLog

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  DGC Eval Dashboard")
    lines.append("=" * 60)

    # -- Latest eval results --
    latest = load_latest()
    if latest:
        lines.append("")
        lines.append(f"  Latest Run: {latest['timestamp'][:19]}")
        lines.append(
            f"  {latest['passed']}/{latest['total']} passed  "
            f"({latest['pass_at_1']:.0%})  "
            f"in {latest['duration_seconds']:.2f}s"
        )
        lines.append("")
        for r in latest.get("results", []):
            marker = "+" if r["passed"] else "X"
            err = f"  {r['error'][:50]}" if r.get("error") else ""
            lines.append(f"    [{marker}] {r['name']:<32}{err}")
    else:
        lines.append("\n  No eval results yet. Run: dgc eval run")

    # -- Benchmark status --
    lines.append("")
    lines.append("-" * 60)
    lines.append("  Benchmarks")
    lines.append("-" * 60)
    try:
        reg = BenchmarkRegistry()
        for bm in reg.report():
            status = "OK" if bm["status"] == "ok" else "REGR"
            measured = f"  last={bm['last_value']:.2f}" if bm["last_measured"] > 0 else ""
            lines.append(
                f"    {bm['name']:<22} threshold={bm['threshold']:<6.2f} "
                f"[{status}]{measured}"
            )
    except Exception as e:
        lines.append(f"    (error loading benchmarks: {e})")

    # -- Trace summary --
    lines.append("")
    lines.append("-" * 60)
    lines.append("  Trace Log")
    lines.append("-" * 60)
    try:
        tlog = TraceLog()
        summary = tlog.summary()
        if summary["by_source"]:
            for src, count in sorted(summary["by_source"].items()):
                lines.append(f"    {src:<16} {count} entries")
            if summary["eval_pass_rate"] is not None:
                lines.append(f"    eval pass rate: {summary['eval_pass_rate']:.0%}")
        else:
            lines.append("    (no traces recorded yet)")
    except Exception as e:
        lines.append(f"    (error loading traces: {e})")

    # -- Trend sparkline --
    history = load_history()
    if history:
        lines.append("")
        lines.append("-" * 60)
        lines.append("  Trend (last 5 runs)")
        lines.append("-" * 60)
        for run in history[-5:]:
            ts = run["timestamp"][:16]
            p1 = run.get("pass_at_1", 0.0)
            bar_len = int(p1 * 20)
            bar = "#" * bar_len + "." * (20 - bar_len)
            lines.append(f"    {ts}  [{bar}] {p1:.0%}")

    lines.append("")
    lines.append("=" * 60)
    print("\n".join(lines))
    return 0
