"""Tests for the unified DGC CLI (dgc_cli.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_dgc_cli_module_imports():
    """dgc_cli.py can be imported without error."""
    from dharma_swarm import dgc_cli
    assert hasattr(dgc_cli, "main")
    assert hasattr(dgc_cli, "cmd_status")
    assert hasattr(dgc_cli, "cmd_pulse")
    assert hasattr(dgc_cli, "cmd_gates")
    assert hasattr(dgc_cli, "cmd_health")
    assert hasattr(dgc_cli, "cmd_swarm")


def test_dgc_cli_main_no_args_tries_tui():
    """main() with no args attempts to launch TUI, falls back to status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc"]):
        with patch("dharma_swarm.dgc_cli.cmd_tui") as mock_tui:
            main()
            mock_tui.assert_called_once()


def test_dgc_cli_legacy_tui_arg_routes_to_tui():
    """main() with legacy `tui` arg should launch canonical TUI."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "tui"]):
        with patch("dharma_swarm.dgc_cli.cmd_tui") as mock_tui:
            main()
            mock_tui.assert_called_once()


def test_dgc_cli_status_command():
    """main() dispatches 'status' to cmd_status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "status"]):
        with patch("dharma_swarm.dgc_cli.cmd_status") as mock:
            main()
            mock.assert_called_once()


def test_dgc_cli_health_command():
    """main() dispatches 'health' to cmd_health."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "health"]):
        with patch("dharma_swarm.dgc_cli.cmd_health") as mock:
            main()
            mock.assert_called_once()


def test_dgc_cli_pulse_command():
    """main() dispatches 'pulse' to cmd_pulse."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "pulse"]):
        with patch("dharma_swarm.dgc_cli.cmd_pulse") as mock:
            main()
            mock.assert_called_once()


def test_dgc_cli_memory_command():
    """main() dispatches 'memory' to cmd_memory."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "memory"]):
        with patch("dharma_swarm.dgc_cli.cmd_memory") as mock:
            main()
            mock.assert_called_once()


def test_cmd_swarm_status_alias_does_not_run_orchestrator():
    """`dgc swarm status` should not execute orchestrator run()."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.orchestrate.run") as mock_run:
        cmd_swarm(["status"])
        mock_run.assert_not_called()
