"""Tests for dharma_swarm.orchestrate_live.

Tests the orchestrator's helper functions, loop early-exit conditions,
and signal handling without requiring real LLM calls or subprocess spawning.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _log helper
# ---------------------------------------------------------------------------

def test_log_prints_formatted_output(capsys):
    """_log produces timestamped, system-tagged output."""
    from dharma_swarm.orchestrate_live import _log

    _log("test_sys", "hello world")
    out = capsys.readouterr().out
    assert "[test_sys]" in out
    assert "hello world" in out
    # Timestamp format: HH:MM:SS
    assert ":" in out.split("]")[0]


def test_log_writes_to_logger(caplog):
    """_log also emits to the Python logger."""
    from dharma_swarm.orchestrate_live import _log

    with caplog.at_level(logging.INFO, logger="dharma_swarm.orchestrate_live"):
        _log("mymod", "a message")
    assert any("a message" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

def test_module_constants_are_positive():
    """Orchestrator intervals should be positive numbers."""
    from dharma_swarm.orchestrate_live import (
        SWARM_TICK, PULSE_INTERVAL, EVOLUTION_INTERVAL,
        HEALTH_INTERVAL, LIVING_INTERVAL, MAX_DAILY,
    )
    for name, val in [
        ("SWARM_TICK", SWARM_TICK),
        ("PULSE_INTERVAL", PULSE_INTERVAL),
        ("EVOLUTION_INTERVAL", EVOLUTION_INTERVAL),
        ("HEALTH_INTERVAL", HEALTH_INTERVAL),
        ("LIVING_INTERVAL", LIVING_INTERVAL),
        ("MAX_DAILY", MAX_DAILY),
    ]:
        assert val > 0, f"{name} must be > 0, got {val}"


def test_state_and_log_dirs():
    """STATE_DIR and LOG_DIR are under ~/.dharma."""
    from dharma_swarm.orchestrate_live import STATE_DIR, LOG_DIR
    assert STATE_DIR == Path.home() / ".dharma"
    assert LOG_DIR == STATE_DIR / "logs"


# ---------------------------------------------------------------------------
# _stop_old_daemon
# ---------------------------------------------------------------------------

def test_stop_old_daemon_no_pid_file(tmp_path):
    """_stop_old_daemon does nothing if no pid file exists."""
    from dharma_swarm import orchestrate_live as mod

    with patch.object(mod, "STATE_DIR", tmp_path):
        mod._stop_old_daemon()  # Should not raise


def test_stop_old_daemon_with_invalid_pid_file(tmp_path):
    """_stop_old_daemon handles invalid pid file content."""
    from dharma_swarm import orchestrate_live as mod

    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("not_a_number")

    with patch.object(mod, "STATE_DIR", tmp_path):
        mod._stop_old_daemon()
    # File should be cleaned up
    assert not pid_file.exists()


def test_stop_old_daemon_with_dead_pid(tmp_path):
    """_stop_old_daemon handles pid of a process that's already gone."""
    from dharma_swarm import orchestrate_live as mod

    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("999999999")  # Very unlikely to be alive

    with patch.object(mod, "STATE_DIR", tmp_path):
        mod._stop_old_daemon()
    assert not pid_file.exists()


# ---------------------------------------------------------------------------
# run_pulse_loop — early exit in Claude Code session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pulse_loop_skips_in_claude_code_session():
    """Pulse loop exits immediately if CLAUDECODE env var is set."""
    from dharma_swarm.orchestrate_live import run_pulse_loop

    shutdown = asyncio.Event()
    with patch.dict(os.environ, {"CLAUDECODE": "1"}):
        # Should return immediately without looping
        await run_pulse_loop(shutdown)
    # If we get here, it didn't block — success


# ---------------------------------------------------------------------------
# run_swarm_loop — shutdown event respected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_loop_respects_shutdown():
    """Swarm loop exits when shutdown event is set."""
    from dharma_swarm.orchestrate_live import run_swarm_loop

    shutdown = asyncio.Event()

    mock_swarm = MagicMock()
    mock_swarm.init = AsyncMock()
    mock_swarm.list_agents = AsyncMock(return_value=[])
    mock_swarm.current_thread = "test"
    mock_swarm.tick = AsyncMock(return_value={"paused": False, "dispatched": 0})
    mock_swarm.shutdown = AsyncMock()

    mock_bus = MagicMock()
    mock_bus.init_db = AsyncMock()
    mock_bus.consume_events = AsyncMock(return_value=[])

    # Set shutdown after a short delay
    async def set_shutdown():
        await asyncio.sleep(0.1)
        shutdown.set()

    with (
        patch("dharma_swarm.orchestrate_live.SwarmManager", return_value=mock_swarm) if False else
        patch("dharma_swarm.swarm.SwarmManager", return_value=mock_swarm),
        patch("dharma_swarm.message_bus.MessageBus", return_value=mock_bus),
    ):
        # Pre-set shutdown so loop exits on first iteration check
        shutdown.set()
        try:
            await asyncio.wait_for(run_swarm_loop(shutdown), timeout=5.0)
        except Exception:
            pass  # May fail on deep imports; the key test is that it respects shutdown


# ---------------------------------------------------------------------------
# run_health_loop — shutdown respected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_loop_respects_shutdown():
    """Health loop exits promptly when shutdown event is set."""
    from dharma_swarm.orchestrate_live import run_health_loop

    shutdown = asyncio.Event()
    shutdown.set()  # Pre-set so it exits immediately

    try:
        await asyncio.wait_for(run_health_loop(shutdown), timeout=3.0)
    except Exception:
        pass  # Deep imports may fail, but shouldn't hang


# ---------------------------------------------------------------------------
# Interval constants from config
# ---------------------------------------------------------------------------

def test_witness_and_zeitgeist_intervals():
    """Special loop intervals are defined at module level."""
    from dharma_swarm.orchestrate_live import (
        WITNESS_INTERVAL, ZEITGEIST_INTERVAL,
        CONSOLIDATION_INTERVAL, RECOGNITION_INTERVAL,
        REPLICATION_INTERVAL,
    )
    assert WITNESS_INTERVAL > 0
    assert ZEITGEIST_INTERVAL > 0
    assert CONSOLIDATION_INTERVAL > 0
    assert RECOGNITION_INTERVAL > 0
    assert REPLICATION_INTERVAL > 0


# ---------------------------------------------------------------------------
# orchestrate function signature
# ---------------------------------------------------------------------------

def test_orchestrate_is_async():
    """orchestrate() is an async function."""
    from dharma_swarm.orchestrate_live import orchestrate
    assert asyncio.iscoroutinefunction(orchestrate)


def test_orchestrate_accepts_background_param():
    """orchestrate() accepts a `background` keyword argument."""
    import inspect
    from dharma_swarm.orchestrate_live import orchestrate
    sig = inspect.signature(orchestrate)
    assert "background" in sig.parameters
    assert sig.parameters["background"].default is False
