#!/usr/bin/env python3
"""Overnight supervisor for dharma_swarm.

Runs unattended for N hours:
- ensures daemon + test sentinel are running
- keeps the task board fed with high-value tasks
- records periodic status snapshots
- runs quality gates on a schedule
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.home() / "dharma_swarm"
STATE_DIR = Path.home() / ".dharma"
DB_TASKS = STATE_DIR / "db" / "tasks.db"
LOG_ROOT = STATE_DIR / "logs" / "overnight"
STOP_FILE = STATE_DIR / "STOP_OVERNIGHT"
GLOBAL_PID_FILE = STATE_DIR / "overnight.pid"
GLOBAL_RUN_FILE = STATE_DIR / "overnight_run_dir.txt"


TASK_QUEUE: list[dict[str, str]] = [
    {
        "title": "Surgeon: harden provider failure classification",
        "description": (
            "Inspect dharma_swarm/providers.py and agent_runner.py for false-negative and "
            "false-positive failure detection. Add or update tests. Write findings and exact "
            "patch notes to ~/.dharma/shared/surgeon_notes.md."
        ),
    },
    {
        "title": "Architect: simplify startup crew by runtime provider health",
        "description": (
            "Design provider selection that prefers healthy authenticated providers at runtime. "
            "Document a concrete refactor plan and migration risks in "
            "~/.dharma/shared/architect_notes.md."
        ),
    },
    {
        "title": "Validator: verify every CLI command and report drift",
        "description": (
            "Run dharma_swarm CLI command families (status/task/memory/context/run) and report "
            "which options work, fail, or have misleading output. Write to "
            "~/.dharma/shared/validation.md."
        ),
    },
    {
        "title": "Cartographer: map untracked modules and integration path",
        "description": (
            "Audit untracked modules in dharma_swarm/ (archive, selector, metrics, traces, etc). "
            "Propose target package layout and import contracts. Write to "
            "~/.dharma/shared/cartographer_notes.md."
        ),
    },
    {
        "title": "Researcher: synthesize overnight constraints into action plan",
        "description": (
            "Read current daemon logs, shared notes, and FIRST_LIVE_RUN_REPORT.md. Produce a "
            "tight plan of next 10 implementation moves with acceptance tests in "
            "~/.dharma/shared/researcher_notes.md."
        ),
    },
    {
        "title": "Archeologist: recover lineage of DHARMA swarm architecture",
        "description": (
            "Trace architecture lineage from docs and local repo history. Identify what was "
            "promised vs actually built. Write the delta matrix to "
            "~/.dharma/shared/archeologist_notes.md."
        ),
    },
    {
        "title": "Builder: implement one small high-confidence improvement",
        "description": (
            "Pick one low-risk improvement that can be completed with tests in one pass. "
            "Implement, test, and summarize change + evidence to ~/.dharma/shared/builder_notes.md."
        ),
    },
    {
        "title": "Critic: adversarial review of overnight claims",
        "description": (
            "Read all notes in ~/.dharma/shared and challenge unsupported claims. Separate facts "
            "from assumptions, include evidence paths, and write to ~/.dharma/shared/critique.md."
        ),
    },
]


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    log_file: Path
    report_md: Path
    report_jsonl: Path
    pid_file: Path
    daemon_launcher_log: Path
    sentinel_launcher_log: Path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ts() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def write_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=os.environ.copy(),
    )


def pid_is_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def ensure_daemon(ctx: RunContext, interval: int) -> dict[str, Any]:
    pid_file = STATE_DIR / "daemon.pid"
    pid = read_pid(pid_file) if pid_file.exists() else None
    if pid and pid_is_alive(pid):
        return {"status": "already_running", "pid": pid}

    proc = subprocess.Popen(
        ["bash", str(ROOT / "run_daemon.sh")],
        cwd=str(ROOT),
        env={**os.environ, "DHARMA_INTERVAL": str(interval)},
        stdout=open(ctx.daemon_launcher_log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(1.5)
    running_pid = proc.pid if pid_is_alive(proc.pid) else None
    return {"status": "started", "pid": running_pid}


def ensure_sentinel(ctx: RunContext) -> dict[str, Any]:
    pid_file = STATE_DIR / "sentinel.pid"
    pid = read_pid(pid_file) if pid_file.exists() else None
    if pid and pid_is_alive(pid):
        return {"status": "already_running", "pid": pid}

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "test_sentinel.py")],
        cwd=str(ROOT),
        stdout=open(ctx.sentinel_launcher_log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (STATE_DIR / "sentinel.pid").write_text(str(proc.pid), encoding="utf-8")
    time.sleep(1.0)
    running_pid = proc.pid if pid_is_alive(proc.pid) else None
    return {"status": "started", "pid": running_pid}


def get_task_counts() -> dict[str, int]:
    counts = {
        "pending": 0,
        "assigned": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    if not DB_TASKS.exists():
        return counts

    conn = sqlite3.connect(str(DB_TASKS))
    try:
        cur = conn.cursor()
        for status, count in cur.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        ):
            key = str(status).lower()
            counts[key] = int(count)
    finally:
        conn.close()
    return counts


def get_recent_task_rows(limit: int = 6) -> list[dict[str, str]]:
    if not DB_TASKS.exists():
        return []
    conn = sqlite3.connect(str(DB_TASKS))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, status, updated_at FROM tasks "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"][:8],
                "title": r["title"],
                "status": r["status"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def enqueue_task(item: dict[str, str], priority: str = "normal") -> subprocess.CompletedProcess[str]:
    return run_cmd(
        [
            sys.executable,
            "-m",
            "dharma_swarm.cli",
            "task",
            "create",
            item["title"],
            "--description",
            item["description"],
            "--priority",
            priority,
            "--state-dir",
            str(STATE_DIR),
        ],
        cwd=ROOT,
        timeout=120,
    )


def append_report_header(ctx: RunContext, args: argparse.Namespace) -> None:
    header = [
        "# Overnight Autopilot Report",
        f"- Run ID: `{ctx.run_id}`",
        f"- Started (UTC): `{ts()}`",
        f"- Duration target (hours): `{args.hours}`",
        f"- Poll interval (seconds): `{args.poll_seconds}`",
        f"- Pending floor: `{args.min_pending}`",
        "",
        "## Loop Snapshots",
        "",
    ]
    ctx.report_md.write_text("\n".join(header), encoding="utf-8")


def append_snapshot_md(ctx: RunContext, loop_idx: int, snapshot: dict[str, Any]) -> None:
    counts = snapshot["counts"]
    lines = [
        f"### Loop {loop_idx} @ {snapshot['timestamp']}",
        f"- Counts: pending={counts.get('pending', 0)} assigned={counts.get('assigned', 0)} "
        f"running={counts.get('running', 0)} completed={counts.get('completed', 0)} "
        f"failed={counts.get('failed', 0)}",
        f"- Daemon: {snapshot['daemon_status']}",
        f"- Sentinel: {snapshot['sentinel_status']}",
        f"- Added tasks: {snapshot['tasks_added']}",
    ]
    if snapshot.get("quality_gate_rc") is not None:
        lines.append(f"- Quality gates rc: {snapshot['quality_gate_rc']}")
    lines.append("- Recent tasks:")
    for row in snapshot["recent_tasks"]:
        lines.append(
            f"  - `{row['id']}` [{row['status']}] {row['title']} ({row['updated_at']})"
        )
    lines.append("")
    write_line(ctx.report_md, "\n".join(lines))


def run_quality_gates(ctx: RunContext) -> int:
    proc = run_cmd(["bash", "scripts/quality_gates.sh"], cwd=ROOT, timeout=1200)
    write_line(ctx.log_file, f"[{ts()}] quality_gates rc={proc.returncode}")
    if proc.stdout:
        write_line(ctx.log_file, proc.stdout[-8000:])
    if proc.stderr:
        write_line(ctx.log_file, proc.stderr[-4000:])
    return proc.returncode


def run_context_snapshots(ctx: RunContext) -> None:
    matrix = [
        ("surgeon", "mechanistic"),
        ("architect", "architectural"),
        ("researcher", "phenomenological"),
    ]
    for role, thread in matrix:
        out_file = ctx.run_dir / f"context_{role}_{thread}.md"
        proc = run_cmd(
            [
                sys.executable,
                "-m",
                "dharma_swarm.cli",
                "context",
                "--role",
                role,
                "--thread",
                thread,
            ],
            cwd=ROOT,
            timeout=240,
        )
        content = proc.stdout if proc.stdout else proc.stderr
        out_file.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run overnight dharma_swarm supervision.")
    parser.add_argument("--hours", type=float, default=8.0, help="How long to run.")
    parser.add_argument("--poll-seconds", type=int, default=600, help="Loop sleep.")
    parser.add_argument(
        "--min-pending",
        type=int,
        default=6,
        help="Keep at least this many pending tasks.",
    )
    parser.add_argument(
        "--tasks-per-loop",
        type=int,
        default=3,
        help="Max tasks to enqueue per loop when pending is low.",
    )
    parser.add_argument(
        "--daemon-interval",
        type=int,
        default=60,
        help="Tick interval if daemon must be started.",
    )
    parser.add_argument(
        "--quality-every-loops",
        type=int,
        default=6,
        help="Run quality gates every N loops.",
    )
    args = parser.parse_args()

    run_id = now_utc().strftime("%Y%m%d_%H%M%S")
    run_dir = LOG_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ctx = RunContext(
        run_id=run_id,
        run_dir=run_dir,
        log_file=run_dir / "autopilot.log",
        report_md=run_dir / "report.md",
        report_jsonl=run_dir / "snapshots.jsonl",
        pid_file=run_dir / "autopilot.pid",
        daemon_launcher_log=run_dir / "daemon_launcher.log",
        sentinel_launcher_log=run_dir / "sentinel_launcher.log",
    )

    ctx.pid_file.write_text(str(os.getpid()), encoding="utf-8")
    GLOBAL_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    GLOBAL_RUN_FILE.write_text(str(run_dir), encoding="utf-8")

    append_report_header(ctx, args)
    write_line(ctx.log_file, f"[{ts()}] autopilot start pid={os.getpid()} run_id={run_id}")

    daemon_result = ensure_daemon(ctx, args.daemon_interval)
    sentinel_result = ensure_sentinel(ctx)
    write_line(ctx.log_file, f"[{ts()}] daemon={daemon_result}")
    write_line(ctx.log_file, f"[{ts()}] sentinel={sentinel_result}")

    try:
        run_context_snapshots(ctx)
    except Exception:
        write_line(ctx.log_file, f"[{ts()}] context_snapshot_exception")
        write_line(ctx.log_file, traceback.format_exc())

    start = time.time()
    max_seconds = max(60, int(args.hours * 3600))
    loop_idx = 0
    task_cursor = 0

    while (time.time() - start) < max_seconds:
        if STOP_FILE.exists():
            write_line(ctx.log_file, f"[{ts()}] stop file detected: {STOP_FILE}")
            break

        try:
            loop_idx += 1
            snapshot: dict[str, Any] = {
                "timestamp": ts(),
                "loop": loop_idx,
                "counts": get_task_counts(),
                "daemon_status": "ok" if pid_is_alive(read_pid(STATE_DIR / "daemon.pid") or -1) else "missing",
                "sentinel_status": "ok" if pid_is_alive(read_pid(STATE_DIR / "sentinel.pid") or -1) else "missing",
                "tasks_added": 0,
                "recent_tasks": [],
            }

            if snapshot["daemon_status"] != "ok":
                restarted = ensure_daemon(ctx, args.daemon_interval)
                snapshot["daemon_status"] = f"restarted:{restarted}"
            if snapshot["sentinel_status"] != "ok":
                restarted = ensure_sentinel(ctx)
                snapshot["sentinel_status"] = f"restarted:{restarted}"

            pending = int(snapshot["counts"].get("pending", 0))
            needed = max(0, args.min_pending - pending)
            enqueue_count = min(args.tasks_per_loop, needed)
            for _ in range(enqueue_count):
                item = TASK_QUEUE[task_cursor % len(TASK_QUEUE)]
                task_cursor += 1
                priority = "high" if (task_cursor % 3 == 0) else "normal"
                proc = enqueue_task(item, priority=priority)
                if proc.returncode == 0:
                    snapshot["tasks_added"] += 1
                else:
                    write_line(
                        ctx.log_file,
                        f"[{ts()}] enqueue_failed rc={proc.returncode} stdout={proc.stdout[-300:]} stderr={proc.stderr[-300:]}",
                    )

            if args.quality_every_loops > 0 and loop_idx % args.quality_every_loops == 0:
                snapshot["quality_gate_rc"] = run_quality_gates(ctx)

            snapshot["counts"] = get_task_counts()
            snapshot["recent_tasks"] = get_recent_task_rows(limit=8)

            write_line(ctx.log_file, f"[{ts()}] snapshot={json.dumps(snapshot, ensure_ascii=True)}")
            write_line(ctx.report_jsonl, json.dumps(snapshot, ensure_ascii=True))
            append_snapshot_md(ctx, loop_idx, snapshot)
        except Exception:
            write_line(ctx.log_file, f"[{ts()}] loop_exception loop={loop_idx}")
            write_line(ctx.log_file, traceback.format_exc())

        time.sleep(max(10, args.poll_seconds))

    morning = run_cmd(["bash", "scripts/morning_check.sh"], cwd=ROOT, timeout=180)
    write_line(ctx.log_file, f"[{ts()}] morning_check rc={morning.returncode}")
    if morning.stdout:
        write_line(ctx.log_file, morning.stdout[-8000:])
    if morning.stderr:
        write_line(ctx.log_file, morning.stderr[-4000:])

    write_line(ctx.log_file, f"[{ts()}] autopilot done run_id={run_id}")
    write_line(
        ctx.report_md,
        "\n## Completion\n"
        f"- Finished (UTC): `{ts()}`\n"
        f"- Logs: `{ctx.log_file}`\n"
        f"- Snapshots: `{ctx.report_jsonl}`\n",
    )
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        raise SystemExit(main())
    except Exception:
        run_dir = None
        if GLOBAL_RUN_FILE.exists():
            try:
                run_dir = Path(GLOBAL_RUN_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                run_dir = None
        if run_dir:
            write_line(run_dir / "autopilot.log", f"[{ts()}] fatal_exception")
            write_line(run_dir / "autopilot.log", traceback.format_exc())
        raise
