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
    assert hasattr(dgc_cli, "cmd_canonical_status")
    assert hasattr(dgc_cli, "cmd_pulse")
    assert hasattr(dgc_cli, "cmd_gates")
    assert hasattr(dgc_cli, "cmd_health")
    assert hasattr(dgc_cli, "cmd_swarm")


def test_dgc_cli_main_no_args_tries_tui():
    """main() with no args attempts to launch TUI, falls back to status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc"]):
        with patch.dict("os.environ", {}, clear=False):
            with patch("dharma_swarm.dgc_cli.cmd_tui") as mock_tui:
                main()
                mock_tui.assert_called_once()


def test_dgc_cli_main_no_args_respects_default_chat_mode():
    """main() with no args and DGC_DEFAULT_MODE=chat launches native chat."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc"]):
        with patch.dict("os.environ", {"DGC_DEFAULT_MODE": "chat"}, clear=False):
            with patch("dharma_swarm.dgc_cli.cmd_chat") as mock_chat:
                main()
                mock_chat.assert_called_once()


def test_dgc_cli_chat_command_dispatch():
    """main() dispatches explicit `chat` command to cmd_chat()."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "chat", "--continue", "--offline"]):
        with patch("dharma_swarm.dgc_cli.cmd_chat") as mock_chat:
            main()
            mock_chat.assert_called_once()


def test_dgc_cli_dashboard_command_dispatch():
    """main() dispatches explicit `dashboard` command to cmd_tui()."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "dashboard"]):
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


def test_dgc_cli_mission_status_command():
    """main() dispatches 'mission-status' to cmd_mission_status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-status"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_status", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["as_json"] is False
            assert mock.call_args.kwargs["strict_core"] is False
            assert mock.call_args.kwargs["require_tracked"] is False
            assert mock.call_args.kwargs["profile"] is None


def test_dgc_cli_mission_status_command_with_flags():
    """mission-status flags should pass through to cmd_mission_status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-status", "--json", "--strict-core", "--require-tracked"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_status", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["as_json"] is True
            assert mock.call_args.kwargs["strict_core"] is True
            assert mock.call_args.kwargs["require_tracked"] is True
            assert mock.call_args.kwargs["profile"] is None


def test_dgc_cli_mission_status_command_with_profile():
    """mission-status profile flag should pass through to cmd_mission_status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-status", "--profile", "workspace_auto"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_status", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["profile"] == "workspace_auto"


def test_dgc_cli_mission_status_nonzero_exits():
    """Non-zero mission-status return should map to process exit."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "mission-status", "--strict-core"]):
        with patch("dharma_swarm.dgc_cli.cmd_mission_status", return_value=2):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 2


def test_dgc_cli_canonical_status_command():
    """main() dispatches 'canonical-status' to cmd_canonical_status."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "canonical-status", "--json"]):
        with patch("dharma_swarm.dgc_cli.cmd_canonical_status", return_value=0) as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["as_json"] is True


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


def test_dgc_cli_rag_health_dispatch():
    """main() dispatches rag health to cmd_rag_health."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "rag", "health", "--service", "ingest"]):
        with patch("dharma_swarm.dgc_cli.cmd_rag_health") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_rag_search_dispatch():
    """main() dispatches rag search to cmd_rag_search."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "rag", "search", "hello world", "--top-k", "3"]):
        with patch("dharma_swarm.dgc_cli.cmd_rag_search") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_flywheel_jobs_dispatch():
    """main() dispatches flywheel jobs to cmd_flywheel_jobs."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "flywheel", "jobs"]):
        with patch("dharma_swarm.dgc_cli.cmd_flywheel_jobs") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_flywheel_start_dispatch():
    """main() dispatches flywheel start to cmd_flywheel_start."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "flywheel",
            "start",
            "--workload-id",
            "w1",
            "--client-id",
            "c1",
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_flywheel_start") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_rag_error_is_user_friendly(capsys):
    """RAG command failures should return concise CLI errors, not tracebacks."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "rag", "health"]):
        with patch("dharma_swarm.dgc_cli.cmd_rag_health", side_effect=RuntimeError("offline")):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 2
    assert "RAG command failed: offline" in capsys.readouterr().out


def test_dgc_cli_flywheel_error_is_user_friendly(capsys):
    """Flywheel command failures should return concise CLI errors, not tracebacks."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "flywheel", "jobs"]):
        with patch("dharma_swarm.dgc_cli.cmd_flywheel_jobs", side_effect=RuntimeError("unreachable")):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 2
    assert "Flywheel command failed: unreachable" in capsys.readouterr().out


def test_cmd_mission_status_formats_gap_report(capsys, monkeypatch):
    """Mission status should show core lane, local-only files, and accelerator state."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(
        cli,
        "_core_mission_checks",
        lambda: {"planner_executor": True, "think_points": False},
    )
    monkeypatch.setattr(
        cli,
        "_tracked_paths",
        lambda _paths: {
            "dharma_swarm/integrations/nvidia_rag.py": True,
            "scripts/allout_autopilot.py": False,
        },
    )
    monkeypatch.setattr(
        cli,
        "_read_openclaw_summary",
        lambda: {"present": True, "readable": True, "agents_count": 3, "providers": ["openai"]},
    )
    def _fake_run(coro):
        try:
            coro.close()
        except Exception:
            pass
        return {
            "rag_health": "PASS",
            "ingest_health": "BLOCKED: offline",
            "flywheel_jobs": "BLOCKED: offline",
        }

    monkeypatch.setattr(cli, "_run", _fake_run)

    rc = cli.cmd_mission_status()
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== DGC MISSION STATUS ===" in out
    assert "Core intelligence lane: 1/2 wired" in out
    assert "[LOCAL-ONLY] scripts/allout_autopilot.py" in out
    assert "[rag_health] PASS" in out


def test_cmd_mission_status_strict_modes_return_codes(monkeypatch, capsys):
    """Strict mode return codes should reflect core/tracking failures."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(cli, "_core_mission_checks", lambda: {"a": True, "b": False})
    monkeypatch.setattr(cli, "_tracked_paths", lambda _paths: {"x": True, "y": False})
    monkeypatch.setattr(cli, "_read_openclaw_summary", lambda: {"present": False})

    def _fake_run(coro):
        try:
            coro.close()
        except Exception:
            pass
        return {"rag_health": "BLOCKED", "ingest_health": "BLOCKED", "flywheel_jobs": "BLOCKED"}

    monkeypatch.setattr(cli, "_run", _fake_run)
    rc_core = cli.cmd_mission_status(strict_core=True)
    assert rc_core == 2
    _ = capsys.readouterr()
    rc_tracked = cli.cmd_mission_status(require_tracked=True)
    assert rc_tracked == 3


def test_cmd_mission_status_json_output(monkeypatch, capsys):
    """JSON mode should print structured report."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(cli, "_core_mission_checks", lambda: {"a": True})
    monkeypatch.setattr(cli, "_tracked_paths", lambda _paths: {"x": True})
    monkeypatch.setattr(cli, "_read_openclaw_summary", lambda: {"present": True, "readable": True})

    def _fake_run(coro):
        try:
            coro.close()
        except Exception:
            pass
        return {"rag_health": "PASS", "ingest_health": "PASS", "flywheel_jobs": "PASS"}

    monkeypatch.setattr(cli, "_run", _fake_run)
    rc = cli.cmd_mission_status(as_json=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert '"core"' in out
    assert '"accelerators"' in out


def test_cmd_mission_status_profile_enables_strict_checks(monkeypatch, capsys):
    """Profile defaults should activate strict/require-tracked checks."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(cli, "_core_mission_checks", lambda: {"a": True, "b": False})
    monkeypatch.setattr(cli, "_tracked_paths", lambda _paths: {"x": True, "y": False})
    monkeypatch.setattr(cli, "_read_openclaw_summary", lambda: {"present": True, "readable": True})

    def _fake_run(coro):
        try:
            coro.close()
        except Exception:
            pass
        return {"rag_health": "PASS", "ingest_health": "PASS", "flywheel_jobs": "PASS"}

    monkeypatch.setattr(cli, "_run", _fake_run)
    rc = cli.cmd_mission_status(profile="workspace_auto")
    assert rc == 2
    out = capsys.readouterr().out
    assert "Autonomy profile: workspace_auto" in out


def test_cmd_mission_status_unknown_profile_json(capsys):
    """Unknown profile should return code 4 with a structured error in JSON mode."""
    import dharma_swarm.dgc_cli as cli

    rc = cli.cmd_mission_status(as_json=True, profile="not_real")
    assert rc == 4
    out = capsys.readouterr().out
    assert '"valid_profiles"' in out


def test_dgc_cli_stress_dispatch():
    """main() dispatches stress command to cmd_stress with parsed args."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "stress",
            "--profile",
            "quick",
            "--provider-mode",
            "mock",
            "--agents",
            "4",
            "--external-research",
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_stress") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            kwargs = mock_cmd.call_args.kwargs
            assert kwargs["profile"] == "quick"
            assert kwargs["provider_mode"] == "mock"
            assert kwargs["agents"] == 4
            assert kwargs["external_research"] is True
            assert kwargs["external_timeout_sec"] == 120


def test_cmd_stress_invokes_harness_subprocess(tmp_path):
    """cmd_stress should execute scripts/dgc_max_stress.py with forwarded args."""
    import dharma_swarm.dgc_cli as cli

    fake_root = tmp_path / "repo"
    harness = fake_root / "scripts" / "dgc_max_stress.py"
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/usr/bin/env python3\n")

    with patch.object(cli, "DHARMA_SWARM", fake_root):
        with patch("dharma_swarm.dgc_cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            cli.cmd_stress(
                profile="quick",
                state_dir="/tmp/dgc-stress",
                provider_mode="mock",
                agents=2,
                tasks=3,
                evolutions=4,
                evolution_concurrency=1,
                cli_rounds=1,
                cli_concurrency=2,
                orchestration_timeout_sec=30,
                external_research=True,
                external_timeout_sec=45,
            )
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            assert str(harness) in cmd
            assert "--profile" in cmd
            assert "quick" in cmd
            assert "--provider-mode" in cmd
            assert "mock" in cmd
            assert "--external-research" in cmd
            assert "--external-timeout-sec" in cmd
            assert "45" in cmd
