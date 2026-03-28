"""Thin bridge from Claude Code hooks into dharma_swarm governance.

This module is the ONLY integration point between the IDE layer (Claude Code
hooks, settings.json) and the runtime governance layer (telos_gates, monitor,
context engine). It does NOT duplicate governance logic — it delegates.

Three entry points, callable from shell (hook commands):
  1. stop_verify   — run telos gates + system health on session stop
  2. session_context — assemble DGC context snapshot for session start
  3. verify_baseline — full baseline verification (CLI: dgc verify-baseline)

Design principle: the best harness is the thinnest one that connects the
IDE layer to the runtime governance layer.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".dharma"


def stop_verify() -> dict:
    """Run telos gates on session-end to catch governance drift.

    Returns a dict with gate results and optional health summary.
    Called from the Stop hook in settings.json.
    """
    from dharma_swarm.telos_gates import check_action

    result = check_action(
        action="claude_code_session_stop",
        content="session ending, verifying governance integrity",
    )

    report = {
        "gate_decision": result.decision,
        "gate_reason": result.reason,
        "gates_passed": len([
            g for g, (outcome, _) in result.gate_results.items()
            if outcome.name in ("PASS", "ADVISORY")
        ]),
        "gates_total": len(result.gate_results),
    }

    # Append to session audit trail
    audit_dir = STATE_DIR / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "claude_sessions.jsonl"
    try:
        import time
        entry = {
            "timestamp": time.time(),
            "event": "session_stop",
            **report,
        }
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # audit is best-effort

    return report


def session_context() -> str:
    """Assemble DGC context snapshot for Claude Code session start.

    Returns a compact string suitable for injection into the session
    start hook output. Uses the existing context engine.
    """
    parts = []

    # DGC mission-control context snapshot. Treat as hints and verify.
    parts.append("DGC mission-control context snapshot. Treat as hints and verify.")

    # Active thread from state
    thread_file = STATE_DIR / "active_thread.txt"
    if thread_file.exists():
        thread = thread_file.read_text().strip()
        parts.append(f"\nActive thread: {thread}")

    # Recent session memory (last 5 entries)
    memory_db = STATE_DIR / "memory.db"
    if memory_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(memory_db))
            rows = conn.execute(
                "SELECT content FROM memories ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            conn.close()
            if rows:
                parts.append("Recent memory:")
                for (content,) in rows:
                    parts.append(f"  {content[:120]}")
        except Exception:
            pass

    # Latent gold (high-salience orphaned ideas)
    ideas_dir = STATE_DIR / "ideas"
    if ideas_dir.exists():
        try:
            idea_files = sorted(ideas_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            if idea_files:
                parts.append("Latent gold:")
                for f in idea_files:
                    data = json.loads(f.read_text())
                    salience = data.get("salience", "?")
                    content = data.get("content", str(data))[:120]
                    parts.append(f"  [idea:orphaned] insight | salience={salience} | {content}")
        except Exception:
            pass

    # Ecosystem status (lightweight)
    try:
        from dharma_swarm.startup_crew import DEFAULT_CREW
        alive = len(DEFAULT_CREW)
        parts.append(f"Ecosystem: {alive}/15 alive")
    except Exception:
        pass

    return "\n".join(parts)


def verify_baseline() -> dict:
    """Full baseline verification using SystemMonitor + telos gates.

    This is the CLI entry point for `dgc verify-baseline`.
    Runs health check + gate sweep and returns combined report.
    """
    from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER

    report: dict = {
        "gates": {},
        "health": None,
    }

    # Gate sweep — check all 11 core gates
    gate_result = DEFAULT_GATEKEEPER.check(
        action="baseline_verification",
        content="full system baseline check",
    )
    report["gates"] = {
        "decision": gate_result.decision,
        "reason": gate_result.reason,
        "passed": len([
            g for g, (outcome, _) in gate_result.gate_results.items()
            if outcome.name in ("PASS", "ADVISORY")
        ]),
        "total": len(gate_result.gate_results),
    }

    # Health check via SystemMonitor (async)
    try:
        from dharma_swarm.traces import TraceStore
        from dharma_swarm.monitor import SystemMonitor

        store = TraceStore(STATE_DIR / "traces")
        monitor = SystemMonitor(store)

        async def _run_health():
            return await monitor.check_health()

        health = asyncio.run(_run_health())
        report["health"] = {
            "status": health.overall_status.value if hasattr(health.overall_status, 'value') else str(health.overall_status),
            "anomaly_count": len(health.anomalies) if health.anomalies else 0,
            "mean_fitness": health.mean_fitness,
        }
    except Exception as e:
        report["health"] = {"error": str(e)}

    return report


def post_edit(payload_json: str = "") -> None:
    """Called by PostToolUse hook on Write|Edit. Quality check on Python files.

    Reads JSON payload from stdin. Extracts file_path. Runs ruff with
    fatal-only selectors (E9, F63, F7, F82). Warns on stderr but does
    NOT block (exit 0 always) — blocking writes creates more friction
    than the quality gain warrants.
    """
    import subprocess

    if not payload_json:
        payload_json = sys.stdin.read()

    try:
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        return

    if not Path(file_path).exists():
        return

    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "E9,F63,F7,F82", file_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 and result.stdout.strip():
            print(f"Quality: {result.stdout.strip()}", file=sys.stderr)
    except FileNotFoundError:
        # ruff not installed — fallback to py_compile
        try:
            import py_compile
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"Syntax error: {exc}", file=sys.stderr)
    except (subprocess.TimeoutExpired, Exception):
        pass


# ── CLI entry point ─────────────────────────────────────────────────

def main():
    """CLI dispatcher for hook invocations."""
    if len(sys.argv) < 2:
        print("Usage: python -m dharma_swarm.claude_hooks <command>")
        print("Commands: stop_verify, session_context, verify_baseline, post_edit")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stop_verify":
        result = stop_verify()
        print(json.dumps(result, indent=2))
    elif cmd == "session_context":
        print(session_context())
    elif cmd == "verify_baseline":
        result = verify_baseline()
        print(json.dumps(result, indent=2))
        if result["gates"].get("decision") == "BLOCK":
            sys.exit(1)
    elif cmd == "post_edit":
        post_edit()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
