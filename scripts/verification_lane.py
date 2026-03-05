#!/usr/bin/env python3
"""Non-invasive verification lane for the unified DGC + dharma_swarm stack.

This runner does not mutate code or task routing behavior. It periodically
checks process health, command health, and database state, then writes
machine-readable and human-readable snapshots.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
ROOT = HOME / "dharma_swarm"
DGC_BIN = HOME / "dgc-core" / "bin" / "dgc"
STATE_DIR = HOME / ".dharma"
VERIFY_ROOT = STATE_DIR / "logs" / "verification"

PID_FILE = STATE_DIR / "verification_lane.pid"
RUN_FILE = STATE_DIR / "verification_lane_run_dir.txt"
STOP_FILE = STATE_DIR / "STOP_VERIFICATION_LANE"


@dataclass
class Ctx:
    run_id: str
    run_dir: Path
    log_file: Path
    report_md: Path
    snapshots_jsonl: Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def write_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def pid_alive(pid: int) -> bool:
    try:
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        dur_ms = int((time.time() - start) * 1000)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        first = out.splitlines()[0] if out else (err.splitlines()[0] if err else "")
        return {
            "rc": proc.returncode,
            "duration_ms": dur_ms,
            "first_line": first[:240],
            "stdout_tail": "\n".join(out.splitlines()[-12:])[:4000],
            "stderr_tail": "\n".join(err.splitlines()[-12:])[:2000],
        }
    except subprocess.TimeoutExpired:
        dur_ms = int((time.time() - start) * 1000)
        return {
            "rc": 124,
            "duration_ms": dur_ms,
            "first_line": "timeout",
            "stdout_tail": "",
            "stderr_tail": "",
        }
    except Exception as exc:
        return {
            "rc": 255,
            "duration_ms": int((time.time() - start) * 1000),
            "first_line": f"exception: {exc}",
            "stdout_tail": "",
            "stderr_tail": "",
        }


def tasks_snapshot() -> dict[str, Any]:
    db = STATE_DIR / "db" / "tasks.db"
    payload: dict[str, Any] = {
        "exists": db.exists(),
        "counts": {},
        "latest_updated_at": None,
        "latest_failures": [],
    }
    if not db.exists():
        return payload

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        for status, count in cur.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        ):
            payload["counts"][str(status)] = int(count)

        row = cur.execute("SELECT MAX(updated_at) AS mx FROM tasks").fetchone()
        payload["latest_updated_at"] = row["mx"] if row and row["mx"] else None

        for r in cur.execute(
            "SELECT id, title, updated_at, result FROM tasks "
            "WHERE status='failed' ORDER BY updated_at DESC LIMIT 5"
        ):
            payload["latest_failures"].append(
                {
                    "id": str(r["id"])[:8],
                    "title": str(r["title"]),
                    "updated_at": str(r["updated_at"]),
                    "result_head": (str(r["result"] or "").splitlines()[:1] or [""])[0][:220],
                }
            )
    finally:
        conn.close()
    return payload


def memory_snapshot() -> dict[str, Any]:
    db = STATE_DIR / "db" / "memory.db"
    payload: dict[str, Any] = {
        "exists": db.exists(),
        "count": 0,
        "latest_timestamp": None,
    }
    if not db.exists():
        return payload
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT COUNT(*), MAX(timestamp) FROM memories").fetchone()
        payload["count"] = int(row[0] or 0)
        payload["latest_timestamp"] = row[1]
    finally:
        conn.close()
    return payload


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except Exception:
        return None


def compute_score(snapshot: dict[str, Any]) -> int:
    score = 100
    p = snapshot["process"]
    if not p["daemon"]["alive"]:
        score -= 40
    if not p["overnight"]["alive"]:
        score -= 20
    if not p["sentinel"]["alive"]:
        score -= 10

    for name, result in snapshot["commands"].items():
        if result["rc"] != 0:
            score -= 10
            write_line(
                Path(snapshot["run_dir"]) / "verify.log",
                f"[{ts()}] cmd_failed {name} rc={result['rc']} first={result['first_line']}",
            )

    daemon_age = snapshot["files"].get("daemon_log_age_s")
    if daemon_age is None or daemon_age > 900:
        score -= 10

    counts = snapshot["tasks"].get("counts", {})
    pending = int(counts.get("pending", 0))
    running = int(counts.get("running", 0))
    if pending > 0 and running == 0:
        score -= 5

    return max(0, score)


def append_report_header(ctx: Ctx, args: argparse.Namespace) -> None:
    lines = [
        "# Verification Lane Report",
        f"- Run ID: `{ctx.run_id}`",
        f"- Started (UTC): `{ts()}`",
        f"- Duration target (hours): `{args.hours}`",
        f"- Poll interval (seconds): `{args.interval}`",
        "",
        "## Snapshots",
        "",
    ]
    ctx.report_md.write_text("\n".join(lines), encoding="utf-8")


def append_snapshot_md(ctx: Ctx, snap: dict[str, Any]) -> None:
    counts = snap["tasks"].get("counts", {})
    lines = [
        f"### Loop {snap['loop']} @ {snap['timestamp']}",
        f"- Health score: `{snap['health_score']}` ({snap['health_label']})",
        f"- Processes: overnight={snap['process']['overnight']['alive']} "
        f"daemon={snap['process']['daemon']['alive']} "
        f"sentinel={snap['process']['sentinel']['alive']}",
        f"- Tasks: pending={counts.get('pending', 0)} running={counts.get('running', 0)} "
        f"completed={counts.get('completed', 0)} failed={counts.get('failed', 0)}",
        f"- Memory rows: {snap['memory'].get('count', 0)}",
        f"- Commands:",
    ]
    for name, result in snap["commands"].items():
        lines.append(
            f"  - `{name}` rc={result['rc']} ({result['duration_ms']}ms) "
            f"{result['first_line']}"
        )
    lines.append("")
    write_line(ctx.report_md, "\n".join(lines))


def build_snapshot(ctx: Ctx, loop_idx: int) -> dict[str, Any]:
    process = {}
    for label, file_name in [
        ("overnight", "overnight.pid"),
        ("daemon", "daemon.pid"),
        ("sentinel", "sentinel.pid"),
    ]:
        pid = read_pid(STATE_DIR / file_name)
        process[label] = {"pid": pid, "alive": bool(pid and pid_alive(pid))}

    commands = {
        "dgc_status": run_cmd([str(DGC_BIN), "status"], timeout=40),
        "dgc_swarm_overnight_status": run_cmd(
            [str(DGC_BIN), "swarm", "overnight", "status"], timeout=40
        ),
        "dharma_cli_status": run_cmd(
            [
                sys.executable,
                "-m",
                "dharma_swarm.cli",
                "status",
                "--state-dir",
                str(STATE_DIR),
            ],
            cwd=ROOT,
            timeout=40,
        ),
    }

    run_dir_path = None
    run_file = STATE_DIR / "overnight_run_dir.txt"
    if run_file.exists():
        try:
            run_dir_path = Path(run_file.read_text().strip())
        except Exception:
            run_dir_path = None

    files = {
        "daemon_log_age_s": file_age_seconds(STATE_DIR / "logs" / "daemon.log"),
        "overnight_log_age_s": file_age_seconds(
            run_dir_path / "autopilot.log" if run_dir_path else Path("/nonexistent")
        ),
    }

    snap: dict[str, Any] = {
        "timestamp": ts(),
        "loop": loop_idx,
        "run_dir": str(ctx.run_dir),
        "process": process,
        "commands": commands,
        "tasks": tasks_snapshot(),
        "memory": memory_snapshot(),
        "files": files,
    }
    score = compute_score(snap)
    snap["health_score"] = score
    snap["health_label"] = (
        "healthy" if score >= 80 else "degraded" if score >= 60 else "critical"
    )
    return snap


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only verification lane.")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    run_id = utc_now().strftime("%Y%m%d_%H%M%S")
    run_dir = VERIFY_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ctx = Ctx(
        run_id=run_id,
        run_dir=run_dir,
        log_file=run_dir / "verify.log",
        report_md=run_dir / "report.md",
        snapshots_jsonl=run_dir / "snapshots.jsonl",
    )

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    RUN_FILE.write_text(str(run_dir), encoding="utf-8")
    append_report_header(ctx, args)

    write_line(ctx.log_file, f"[{ts()}] verification lane start pid={os.getpid()}")

    max_seconds = max(60, int(args.hours * 3600))
    started = time.time()
    loop_idx = 0

    while (time.time() - started) < max_seconds:
        if STOP_FILE.exists():
            write_line(ctx.log_file, f"[{ts()}] stop file detected")
            break
        loop_idx += 1
        snap = build_snapshot(ctx, loop_idx)
        write_line(ctx.log_file, f"[{ts()}] snapshot health={snap['health_score']}")
        write_line(ctx.snapshots_jsonl, json.dumps(snap, ensure_ascii=True))
        append_snapshot_md(ctx, snap)
        time.sleep(max(30, args.interval))

    write_line(ctx.log_file, f"[{ts()}] verification lane done")
    write_line(
        ctx.report_md,
        "\n## Completion\n"
        f"- Finished (UTC): `{ts()}`\n"
        f"- Log: `{ctx.log_file}`\n",
    )
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
