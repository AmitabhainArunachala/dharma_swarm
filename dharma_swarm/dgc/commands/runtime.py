"""Runtime-oriented command pack for the modular DGC CLI."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys


def cmd_up(*, background: bool = False) -> None:
    """Start the daemon through the modular runtime pack."""
    from dharma_swarm import dgc_cli

    pid_file = dgc_cli.DHARMA_STATE / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"Daemon already running (PID {pid})")
            return
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)

    live_process = dgc_cli._first_daemon_like_process()
    if live_process is not None:
        pid, _command = live_process
        print(f"Daemon already running (PID {pid})")
        return

    repo_root = dgc_cli.Path(__file__).resolve().parents[3]
    daemon_script = repo_root / "run_daemon.sh"
    env = os.environ.copy()
    env["MISSION_PREFLIGHT"] = "0"

    if background:
        proc = subprocess.Popen(
            ["bash", str(daemon_script)],
            env=env,
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Daemon started in background (PID {proc.pid})")
    else:
        os.execvpe("bash", ["bash", str(daemon_script)], env)


def cmd_down() -> None:
    """Stop the daemon."""
    import signal

    from dharma_swarm import dgc_cli

    pid_file = dgc_cli.DHARMA_STATE / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            print("Corrupted PID file, removing")
            pid_file.unlink()
            return
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to daemon (PID {pid})")
        except OSError:
            print(f"Daemon PID {pid} not found (stale)")
            pid_file.unlink()
    else:
        print("Daemon not running (no PID file)")


def cmd_daemon_status() -> None:
    """Show daemon status and the freshest pulse source."""
    from dharma_swarm import dgc_cli

    pid_file = dgc_cli.DHARMA_STATE / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"  status: running (PID {pid})")
        except (ValueError, OSError):
            print("  status: stale PID file")
    else:
        print("  status: not running")
    pulse_count, last_pulse, pulse_source = dgc_cli._canonical_pulse_summary()
    if last_pulse and pulse_source is not None:
        print(f"  pulse_log: {pulse_count} logged via {pulse_source}, last: {last_pulse}")
        for line in dgc_cli._tail(pulse_source, lines=5).splitlines():
            print(f"    {line[:120]}")
    else:
        print("  pulse_log: no entries")


def cmd_pulse() -> None:
    """Run one heartbeat pulse."""
    from dharma_swarm.pulse import pulse

    response = pulse()
    print(response)


def cmd_orchestrate_live(*, background: bool = False) -> None:
    """Run all DGC systems concurrently."""
    from dharma_swarm import dgc_cli

    pid_file = dgc_cli.DHARMA_STATE / "daemon.pid"
    legacy_pid_file = dgc_cli.DHARMA_STATE / "orchestrator.pid"
    for candidate in (pid_file, legacy_pid_file):
        if not candidate.exists():
            continue
        try:
            pid = int(candidate.read_text().strip())
            os.kill(pid, 0)
            print(f"Orchestrator already running (PID {pid})")
            return
        except (ValueError, OSError):
            candidate.unlink(missing_ok=True)

    live_process = dgc_cli._first_daemon_like_process()
    if live_process is not None:
        pid, _command = live_process
        print(f"Orchestrator already running (PID {pid})")
        return

    if background:
        legacy_pid_file.unlink(missing_ok=True)
        proc = subprocess.Popen(
            [sys.executable, "-m", "dharma_swarm.orchestrate_live", "--background"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Orchestrator started in background (PID {proc.pid})")
    else:
        from dharma_swarm.orchestrate_live import orchestrate

        asyncio.run(orchestrate())
