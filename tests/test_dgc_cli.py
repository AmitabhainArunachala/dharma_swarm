"""Tests for the unified DGC CLI (dgc_cli.py)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_dgc_cli_module_imports():
    """dgc_cli.py can be imported without error."""
    from dharma_swarm import dgc_cli
    assert hasattr(dgc_cli, "main")
    assert hasattr(dgc_cli, "cmd_status")
    assert hasattr(dgc_cli, "cmd_runtime_status")
    assert hasattr(dgc_cli, "cmd_canonical_status")
    assert hasattr(dgc_cli, "cmd_pulse")
    assert hasattr(dgc_cli, "cmd_full_power_probe")
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


def test_dgc_cli_runtime_status_command():
    """main() dispatches `runtime-status` to cmd_runtime_status."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        ["dgc", "runtime-status", "--limit", "7", "--db-path", "/tmp/runtime.db"],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_runtime_status") as mock:
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["limit"] == 7
            assert mock.call_args.kwargs["db_path"] == "/tmp/runtime.db"


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


def test_build_chat_context_snapshot_includes_latent_gold(monkeypatch, tmp_path):
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "  [retrieval:note] recent memory",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_overview",
        lambda **_: "  [idea:orphaned] proposal | latent branch",
        raising=True,
    )
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "DHARMA_STATE", tmp_path / ".dharma")

    snapshot = cli._build_chat_context_snapshot()

    assert "Recent memory:" in snapshot
    assert "Latent gold:" in snapshot
    assert "latent branch" in snapshot


def test_cmd_swarm_status_alias_does_not_run_orchestrator():
    """`dgc swarm status` should not execute orchestrator run()."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.orchestrate.run") as mock_run:
        cmd_swarm(["status"])
        mock_run.assert_not_called()


def test_cmd_swarm_codex_night_start_dispatches_tmux_script():
    """`dgc swarm codex-night start` should invoke the Codex tmux launcher."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.dgc_cli.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Started session"
        mock_run.return_value.stderr = ""

        cmd_swarm(["codex-night", "start", "2"])

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "bash"
    assert Path(cmd[1]).name == "start_codex_overnight_tmux.sh"
    assert cmd[2] == "2"


def test_cmd_swarm_codex_night_yolo_forwards_preset_env():
    """`dgc swarm codex-night yolo` should set the aggressive Codex env."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.dgc_cli.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Started session"
        mock_run.return_value.stderr = ""

        cmd_swarm(
            [
                "codex-night",
                "yolo",
                "2",
                "--mission-file",
                "/tmp/mission.md",
                "--model",
                "gpt-5.4",
                "--max-cycles",
                "3",
                "--label",
                "allnight-yolo",
            ]
        )

    cmd = mock_run.call_args.args[0]
    env = mock_run.call_args.kwargs["env"]
    assert cmd[0] == "bash"
    assert Path(cmd[1]).name == "start_codex_overnight_tmux.sh"
    assert cmd[2] == "2"
    assert env["DGC_CODEX_NIGHT_YOLO"] == "1"
    assert env["DGC_CODEX_NIGHT_MISSION_FILE"] == "/tmp/mission.md"
    assert env["DGC_CODEX_NIGHT_MODEL"] == "gpt-5.4"
    assert env["MAX_CYCLES"] == "3"
    assert env["DGC_CODEX_NIGHT_LABEL"] == "allnight-yolo"


def test_cmd_swarm_yolo_alias_routes_to_codex_lane():
    """`dgc swarm yolo` should use the Codex overnight launcher now."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.dgc_cli.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Started session"
        mock_run.return_value.stderr = ""

        cmd_swarm(["yolo"])

    cmd = mock_run.call_args.args[0]
    env = mock_run.call_args.kwargs["env"]
    assert cmd[0] == "bash"
    assert Path(cmd[1]).name == "start_codex_overnight_tmux.sh"
    assert env["DGC_CODEX_NIGHT_YOLO"] == "1"


def test_cmd_swarm_codex_night_status_dispatches_status_script():
    """`dgc swarm codex-night status` should invoke the status helper."""
    from dharma_swarm.dgc_cli import cmd_swarm

    with patch("dharma_swarm.dgc_cli.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Session running"
        mock_run.return_value.stderr = ""

        cmd_swarm(["codex-night", "status"])

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "bash"
    assert Path(cmd[1]).name == "status_codex_overnight_tmux.sh"


def test_cmd_swarm_codex_night_report_reads_run_artifacts(tmp_path, capsys):
    """`dgc swarm codex-night report` should show report and latest summary."""
    import dharma_swarm.dgc_cli as cli

    run_dir = tmp_path / "logs" / "codex_overnight" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text('{"label":"allnight-yolo"}\n', encoding="utf-8")
    (run_dir / "report.md").write_text("# report\ncycle ok\n", encoding="utf-8")
    (run_dir / "latest_last_message.txt").write_text("RESULT: done\n", encoding="utf-8")
    (run_dir / "morning_handoff.md").write_text("# handoff\nshipped\n", encoding="utf-8")
    run_file = tmp_path / "codex_overnight_run_dir.txt"
    run_file.write_text(str(run_dir), encoding="utf-8")

    with patch.object(cli, "DHARMA_STATE", tmp_path):
        cli.cmd_swarm(["codex-night", "report"])

    out = capsys.readouterr().out
    assert "run_dir:" in out
    assert "allnight-yolo" in out
    assert "cycle ok" in out
    assert "RESULT: done" in out
    assert "shipped" in out


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


def test_dgc_cli_flywheel_export_dispatch():
    """main() dispatches flywheel export to cmd_flywheel_export."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "flywheel",
            "export",
            "--run-id",
            "run-1",
            "--workload-id",
            "w1",
            "--client-id",
            "c1",
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_flywheel_export") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_flywheel_record_dispatch():
    """main() dispatches flywheel record to cmd_flywheel_record."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "flywheel", "record", "job-1", "--run-id", "run-1"]):
        with patch("dharma_swarm.dgc_cli.cmd_flywheel_record") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_reciprocity_summary_dispatch():
    """main() dispatches reciprocity summary to cmd_reciprocity_summary."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "reciprocity", "summary"]):
        with patch("dharma_swarm.dgc_cli.cmd_reciprocity_summary") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_reciprocity_record_dispatch():
    """main() dispatches reciprocity record to cmd_reciprocity_record."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "reciprocity", "record", "--run-id", "run-1"]):
        with patch("dharma_swarm.dgc_cli.cmd_reciprocity_record") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_reciprocity_record_inline_payload_dispatch():
    """main() forwards inline reciprocity payloads to cmd_reciprocity_record."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        ["dgc", "reciprocity", "record", "--run-id", "run-1", "--json", '{"actors":2}'],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_reciprocity_record") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            assert mock_cmd.call_args.kwargs["json_payload"] == '{"actors":2}'
            assert mock_cmd.call_args.kwargs["file_path"] is None


def test_dgc_cli_reciprocity_publish_dispatch():
    """main() dispatches reciprocity publish to cmd_reciprocity_publish."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        ["dgc", "reciprocity", "publish", "activity", "--json", '{"activity_id":"a1"}'],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_reciprocity_publish") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


def test_dgc_cli_ouroboros_connections_dispatch():
    """main() dispatches ouroboros connections to cmd_ouroboros_connections."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        ["dgc", "ouroboros", "connections", "--json", "--limit", "7"],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_ouroboros_connections") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            assert mock_cmd.call_args.kwargs["as_json"] is True
            assert mock_cmd.call_args.kwargs["limit"] == 7


def test_dgc_cli_ouroboros_record_dispatch():
    """main() dispatches ouroboros record to cmd_ouroboros_record."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        ["dgc", "ouroboros", "record", "--run-id", "run-1", "--cycle-id", "cycle-9"],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_ouroboros_record") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            assert mock_cmd.call_args.kwargs["run_id"] == "run-1"
            assert mock_cmd.call_args.kwargs["cycle_id"] == "cycle-9"


def test_dgc_cli_ouroboros_record_inline_payload_dispatch():
    """main() forwards inline ouroboros payloads to cmd_ouroboros_record."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "ouroboros",
            "record",
            "--run-id",
            "run-1",
            "--json",
            '{"cycle_id":"cycle-9"}',
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_ouroboros_record") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            assert mock_cmd.call_args.kwargs["json_payload"] == '{"cycle_id":"cycle-9"}'
            assert mock_cmd.call_args.kwargs["file_path"] is None


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


def test_dgc_cli_reciprocity_error_is_user_friendly(capsys):
    """Reciprocity command failures should return concise CLI errors, not tracebacks."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "reciprocity", "summary"]):
        with patch(
            "dharma_swarm.dgc_cli.cmd_reciprocity_summary",
            side_effect=RuntimeError("offline"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 2
    assert "Reciprocity command failed: offline" in capsys.readouterr().out


def test_dgc_cli_reciprocity_publish_invalid_json_is_user_friendly(capsys):
    """Reciprocity publish should fail cleanly when payload is not a JSON object."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "reciprocity", "publish", "activity", "--json", "[]"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 2
    assert (
        "Reciprocity command failed: reciprocity publish payload must decode to a JSON object"
        in capsys.readouterr().out
    )


def test_dgc_cli_ouroboros_error_is_user_friendly(capsys):
    """Ouroboros command failures should return concise CLI errors, not tracebacks."""
    from dharma_swarm.dgc_cli import main

    with patch("sys.argv", ["dgc", "ouroboros", "connections"]):
        with patch(
            "dharma_swarm.dgc_cli.cmd_ouroboros_connections",
            side_effect=RuntimeError("bad profile"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
    assert exc.value.code == 2
    assert "Ouroboros command failed: bad profile" in capsys.readouterr().out


def test_cmd_flywheel_export_prints_canonical_export(capsys, monkeypatch):
    """flywheel export should print the canonical local export payload."""
    import dharma_swarm.dgc_cli as cli

    async def _fake_export(**kwargs):
        assert kwargs["run_id"] == "run-123"
        assert kwargs["workload_id"] == "canonical"
        return {
            "export_id": "flyexp_run-123",
            "artifact_id": "flyexp_run-123",
            "run_id": "run-123",
            "workload_id": "canonical",
            "client_id": "operator",
            "export_path": "/tmp/flyexp.json",
        }

    monkeypatch.setattr(cli, "_flywheel_export_payload", _fake_export)

    cli.cmd_flywheel_export(
        run_id="run-123",
        workload_id="canonical",
        client_id="operator",
    )

    out = capsys.readouterr().out
    assert '"export_id": "flyexp_run-123"' in out
    assert '"export_path": "/tmp/flyexp.json"' in out


def test_cmd_flywheel_start_includes_local_export_when_run_id_provided(capsys, monkeypatch):
    """flywheel start should create a canonical export first when run_id is provided."""
    import dharma_swarm.dgc_cli as cli

    export_mock = AsyncMock(
        return_value={
            "export_id": "flyexp_run-9",
            "artifact_id": "flyexp_run-9",
            "run_id": "run-9",
            "workload_id": "canonical",
            "client_id": "operator",
            "export_path": "/tmp/flyexp_run-9.json",
        }
    )
    monkeypatch.setattr(cli, "_flywheel_export_payload", export_mock)

    class _FakeClient:
        async def create_job(self, *, workload_id, client_id, data_split_config=None):
            assert workload_id == "canonical"
            assert client_id == "operator"
            assert data_split_config["eval_size"] == 8
            return {"id": "job-1", "status": "queued"}

    monkeypatch.setattr("dharma_swarm.integrations.DataFlywheelClient", _FakeClient)

    cli.cmd_flywheel_start(
        workload_id="canonical",
        client_id="operator",
        eval_size=8,
        val_ratio=0.2,
        min_total_records=30,
        limit=400,
        run_id="run-9",
    )

    out = capsys.readouterr().out
    export_mock.assert_awaited_once()
    assert '"local_export"' in out
    assert '"id": "job-1"' in out


def test_cmd_flywheel_record_prints_registry_binding(capsys, monkeypatch):
    """flywheel record should print fetched job data plus canonical registry binding."""
    import dharma_swarm.dgc_cli as cli

    async def _fake_record(**kwargs):
        assert kwargs["job_id"] == "job-88"
        assert kwargs["run_id"] == "run-88"
        return {
            "job": {"id": "job-88", "status": "completed"},
            "registry": {
                "artifact_id": "art-88",
                "summary": {"job_id": "job-88"},
                "fact_ids": ["fact-1", "fact-2"],
            },
        }

    monkeypatch.setattr(cli, "_flywheel_record_payload", _fake_record)

    cli.cmd_flywheel_record(job_id="job-88", run_id="run-88")

    out = capsys.readouterr().out
    assert '"job-88"' in out
    assert '"artifact_id": "art-88"' in out


def test_cmd_runtime_status_prints_runtime_control_plane(capsys, monkeypatch):
    """runtime-status should print the helper-rendered control-plane summary."""
    import dharma_swarm.dgc_cli as cli

    def _fake_build_runtime_status_text(*, limit, runtime_db_path):
        assert limit == 3
        assert runtime_db_path == Path("/tmp/runtime.db")
        return "Runtime Control Plane\nSessions=2"

    monkeypatch.setattr(
        "dharma_swarm.tui_helpers.build_runtime_status_text",
        _fake_build_runtime_status_text,
    )

    cli.cmd_runtime_status(limit=3, db_path="/tmp/runtime.db")

    out = capsys.readouterr().out
    assert "Runtime Control Plane" in out
    assert "Sessions=2" in out


def test_cmd_reciprocity_summary_prints_ledger_summary(capsys, monkeypatch):
    """reciprocity summary should print the fetched ledger summary payload."""
    import dharma_swarm.dgc_cli as cli

    class _FakeClient:
        async def ledger_summary(self):
            return {"actors": 2, "obligations": 4, "chain_valid": True}

    monkeypatch.setattr("dharma_swarm.integrations.ReciprocityCommonsClient", _FakeClient)

    cli.cmd_reciprocity_summary()

    out = capsys.readouterr().out
    assert '"actors": 2' in out
    assert '"obligations": 4' in out


def test_cmd_reciprocity_record_prints_registry_binding(capsys, monkeypatch):
    """reciprocity record should print fetched summary plus canonical registry binding."""
    import dharma_swarm.dgc_cli as cli

    async def _fake_record(**kwargs):
        assert kwargs["run_id"] == "run-recip"
        assert kwargs["summary_type"] == "ledger_summary"
        return {
            "summary": {"actors": 3, "obligations": 5},
            "registry": {
                "artifact_id": "art-recip",
                "summary": {"source": "reciprocity_commons"},
                "fact_ids": ["fact-r1"],
            },
        }

    monkeypatch.setattr(cli, "_reciprocity_record_payload", _fake_record)

    cli.cmd_reciprocity_record(run_id="run-recip")

    out = capsys.readouterr().out
    assert '"actors": 3' in out
    assert '"artifact_id": "art-recip"' in out


@pytest.mark.asyncio
async def test_reciprocity_record_payload_requires_binding_before_fetch(monkeypatch):
    """reciprocity record should fail before contacting the service without a canonical binding."""
    import dharma_swarm.dgc_cli as cli

    calls = {"constructed": 0, "summary": 0}

    class _FakeClient:
        def __init__(self):
            calls["constructed"] += 1

        async def ledger_summary(self):
            calls["summary"] += 1
            return {"actors": 1}

    monkeypatch.setattr("dharma_swarm.integrations.ReciprocityCommonsClient", _FakeClient)

    with pytest.raises(ValueError, match="session_id or run_id"):
        await cli._reciprocity_record_payload()

    assert calls == {"constructed": 0, "summary": 0}


@pytest.mark.asyncio
async def test_reciprocity_record_payload_normalizes_direct_session_binding(monkeypatch):
    """reciprocity record helper should normalize direct session inputs before registry write."""
    import dharma_swarm.dgc_cli as cli

    seen: dict[str, object] = {}

    class _FakeClient:
        async def ledger_summary(self):
            return {"actors": "4", "chain_valid": "true"}

    class _FakeRuntimeState:
        def __init__(self, db_path):
            seen["runtime_db_path"] = db_path
            self.db_path = db_path or Path("/tmp/default-runtime.db")

    class _FakeMemoryLattice:
        def __init__(self, *, db_path, event_log_dir=None):
            seen["memory_db_path"] = db_path
            seen["event_log_dir"] = event_log_dir
            self.closed = False

        async def close(self):
            self.closed = True
            seen["closed"] = True

    class _FakeArtifact:
        artifact_id = "art-direct"

    class _FakeFact:
        fact_id = "fact-direct"

    class _FakeResult:
        artifact = _FakeArtifact()
        manifest_path = Path("/tmp/reciprocity-manifest.json")
        summary = {"source": "reciprocity_commons", "summary_type": "ledger_summary"}
        facts = [_FakeFact()]
        receipt = {"event_id": "evt-direct"}

    class _FakeRegistry:
        def __init__(
            self,
            *,
            runtime_state,
            memory_lattice,
            workspace_root=None,
            provenance_root=None,
        ):
            seen["workspace_root"] = workspace_root
            seen["provenance_root"] = provenance_root
            seen["runtime_state"] = runtime_state
            seen["memory_lattice"] = memory_lattice

        async def record_reciprocity_summary(self, payload, **kwargs):
            seen["record_payload"] = payload
            seen["record_kwargs"] = kwargs
            return _FakeResult()

    monkeypatch.setattr("dharma_swarm.integrations.ReciprocityCommonsClient", _FakeClient)
    monkeypatch.setattr("dharma_swarm.runtime_state.RuntimeStateStore", _FakeRuntimeState)
    monkeypatch.setattr("dharma_swarm.memory_lattice.MemoryLattice", _FakeMemoryLattice)
    monkeypatch.setattr("dharma_swarm.evaluation_registry.EvaluationRegistry", _FakeRegistry)

    out = await cli._reciprocity_record_payload(
        session_id="  sess-direct  ",
        task_id="   ",
        trace_id="   ",
        summary_type="   ",
        db_path="/tmp/runtime.db",
        event_log_dir="/tmp/events",
        workspace_root="/tmp/workspace",
        provenance_root="/tmp/provenance",
    )

    assert seen["runtime_db_path"] == Path("/tmp/runtime.db")
    assert seen["memory_db_path"] == Path("/tmp/runtime.db")
    assert seen["event_log_dir"] == Path("/tmp/events")
    assert seen["workspace_root"] == Path("/tmp/workspace")
    assert seen["provenance_root"] == Path("/tmp/provenance")
    assert seen["record_payload"] == {
        "actors": "4",
        "chain_valid": "true",
        "service": "reciprocity_commons",
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
    }
    assert seen["record_kwargs"] == {
        "run_id": "",
        "session_id": "sess-direct",
        "task_id": "",
        "trace_id": None,
        "created_by": "dgc_cli",
    }
    assert seen["closed"] is True
    assert out["registry"]["artifact_id"] == "art-direct"
    assert out["registry"]["receipt_event_id"] == "evt-direct"


@pytest.mark.asyncio
async def test_reciprocity_record_payload_uses_file_payload_without_live_fetch(
    monkeypatch,
    tmp_path,
):
    """reciprocity record helper should accept archived JSON without contacting the service."""
    import dharma_swarm.dgc_cli as cli

    seen: dict[str, object] = {}
    payload_path = tmp_path / "reciprocity-summary.json"
    payload_path.write_text('{"actors":9,"chain_valid":false}', encoding="utf-8")

    class _UnexpectedClient:
        def __init__(self):
            raise AssertionError("live service fetch should be skipped for file payloads")

    class _FakeRuntimeState:
        def __init__(self, db_path):
            self.db_path = db_path or Path("/tmp/default-runtime.db")

    class _FakeMemoryLattice:
        def __init__(self, *, db_path, event_log_dir=None):
            seen["memory_db_path"] = db_path
            seen["event_log_dir"] = event_log_dir

        async def close(self):
            seen["closed"] = True

    class _FakeArtifact:
        artifact_id = "art-file"

    class _FakeFact:
        fact_id = "fact-file"

    class _FakeResult:
        artifact = _FakeArtifact()
        manifest_path = Path("/tmp/reciprocity-manifest-file.json")
        summary = {"source": "reciprocity_commons", "summary_type": "ledger_summary"}
        facts = [_FakeFact()]
        receipt = {"event_id": "evt-file"}

    class _FakeRegistry:
        def __init__(
            self,
            *,
            runtime_state,
            memory_lattice,
            workspace_root=None,
            provenance_root=None,
        ):
            seen["workspace_root"] = workspace_root
            seen["provenance_root"] = provenance_root

        async def record_reciprocity_summary(self, payload, **kwargs):
            seen["record_payload"] = payload
            seen["record_kwargs"] = kwargs
            return _FakeResult()

    monkeypatch.setattr("dharma_swarm.integrations.ReciprocityCommonsClient", _UnexpectedClient)
    monkeypatch.setattr("dharma_swarm.runtime_state.RuntimeStateStore", _FakeRuntimeState)
    monkeypatch.setattr("dharma_swarm.memory_lattice.MemoryLattice", _FakeMemoryLattice)
    monkeypatch.setattr("dharma_swarm.evaluation_registry.EvaluationRegistry", _FakeRegistry)

    out = await cli._reciprocity_record_payload(
        session_id="sess-file",
        file_path=str(payload_path),
        event_log_dir="/tmp/events",
        workspace_root="/tmp/workspace",
        provenance_root="/tmp/provenance",
    )

    assert seen["record_payload"] == {
        "actors": 9,
        "chain_valid": False,
        "service": "reciprocity_commons",
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
    }
    assert seen["record_kwargs"] == {
        "run_id": "",
        "session_id": "sess-file",
        "task_id": "",
        "trace_id": None,
        "created_by": "dgc_cli",
    }
    assert seen["closed"] is True
    assert out["registry"]["artifact_id"] == "art-file"


def test_cmd_reciprocity_publish_prints_service_response(capsys, monkeypatch):
    """reciprocity publish should print the submitted record plus service response."""
    import dharma_swarm.dgc_cli as cli

    async def _fake_publish(**kwargs):
        assert kwargs["record_type"] == "project"
        assert kwargs["payload"] == {
            "project_id": "proj-1",
            "project_type": "mangrove_restoration",
        }
        return {
            "record_type": "project",
            "record": kwargs["payload"],
            "response": {"accepted": True, "id": "proj-1"},
        }

    monkeypatch.setattr(cli, "_reciprocity_publish_payload", _fake_publish)

    cli.cmd_reciprocity_publish(
        record_type="project",
        json_payload='{"project_id":"proj-1","project_type":"mangrove_restoration"}',
    )

    out = capsys.readouterr().out
    assert '"record_type": "project"' in out
    assert '"accepted": true' in out


def test_cmd_reciprocity_publish_reads_json_file(capsys, monkeypatch, tmp_path):
    """reciprocity publish should load a JSON object payload from disk."""
    import dharma_swarm.dgc_cli as cli

    payload_path = tmp_path / "activity.json"
    payload_path.write_text('{"activity_id":"a-file","energy_mwh":12.5}', encoding="utf-8")

    async def _fake_publish(**kwargs):
        assert kwargs["record_type"] == "activity"
        assert kwargs["payload"] == {"activity_id": "a-file", "energy_mwh": 12.5}
        return {
            "record_type": "activity",
            "record": kwargs["payload"],
            "response": {"accepted": True},
        }

    monkeypatch.setattr(cli, "_reciprocity_publish_payload", _fake_publish)

    cli.cmd_reciprocity_publish(
        record_type="activity",
        file_path=str(payload_path),
    )

    out = capsys.readouterr().out
    assert '"activity_id": "a-file"' in out
    assert '"accepted": true' in out


def test_cmd_ouroboros_connections_prints_summary(capsys, tmp_path):
    """ouroboros connections should render profile, H0, and H1 sections."""
    import dharma_swarm.dgc_cli as cli

    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "alpha.py").write_text(
        '''"""Alpha observes recursive witness loops across shared state.
This description is long enough to clear the profiling filter cleanly."""
''',
        encoding="utf-8",
    )
    (package_dir / "beta.py").write_text(
        '''"""Beta observes recursive witness loops across shared state.
This description is long enough to clear the profiling filter cleanly."""
''',
        encoding="utf-8",
    )
    (package_dir / "gamma.py").write_text(
        '''"""Gamma claims a profound revolutionary awakening of cosmic scale.
This intentionally performative language should diverge from witness-heavy modules."""
''',
        encoding="utf-8",
    )

    cli.cmd_ouroboros_connections(package_dir=str(package_dir), min_text_length=40)

    out = capsys.readouterr().out
    assert "H0: STRUCTURAL CONNECTIONS" in out
    assert "H1: PRODUCTIVE DISAGREEMENTS" in out
    assert "alpha" in out
    assert "beta" in out
    assert "gamma" in out
    assert "Modules profiled: 3" in out


def test_cmd_ouroboros_connections_json_output(capsys, tmp_path):
    """ouroboros connections should support structured JSON output."""
    import dharma_swarm.dgc_cli as cli

    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "alpha.py").write_text(
        '''"""Alpha observes recursive witness loops across shared state.
This description is long enough to clear the profiling filter cleanly."""
''',
        encoding="utf-8",
    )
    (package_dir / "beta.py").write_text(
        '''"""Beta observes recursive witness loops across shared state.
This description is long enough to clear the profiling filter cleanly."""
''',
        encoding="utf-8",
    )
    (package_dir / "gamma.py").write_text(
        '''"""Gamma claims a profound revolutionary awakening of cosmic scale.
This intentionally performative language should diverge from witness-heavy modules."""
''',
        encoding="utf-8",
    )

    cli.cmd_ouroboros_connections(
        package_dir=str(package_dir),
        min_text_length=40,
        as_json=True,
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["modules_profiled"] == 3
    assert payload["summary"]["connections"] >= 1
    assert any(row["module"] == "alpha" for row in payload["profiles"])


def test_cmd_ouroboros_record_prints_registry_binding(capsys, monkeypatch):
    """ouroboros record should print the selected observation plus registry binding."""
    import dharma_swarm.dgc_cli as cli

    async def _fake_record(**kwargs):
        assert kwargs["run_id"] == "run-ouro"
        assert kwargs["cycle_id"] == "cycle-7"
        return {
            "observation": {
                "cycle_id": "cycle-7",
                "signature": {"recognition_type": "GENUINE"},
            },
            "registry": {
                "artifact_id": "art-ouro",
                "summary": {"cycle_id": "cycle-7"},
                "fact_ids": ["fact-o1"],
            },
        }

    monkeypatch.setattr(cli, "_ouroboros_record_payload", _fake_record)

    cli.cmd_ouroboros_record(run_id="run-ouro", cycle_id="cycle-7")

    out = capsys.readouterr().out
    assert '"cycle_id": "cycle-7"' in out
    assert '"artifact_id": "art-ouro"' in out


@pytest.mark.asyncio
async def test_ouroboros_record_payload_requires_binding_before_log_read(monkeypatch, tmp_path):
    """ouroboros record should fail before reading disk without a canonical binding."""
    import dharma_swarm.dgc_cli as cli

    log_path = tmp_path / "ouroboros_log.jsonl"
    log_path.write_text('{"cycle_id":"cycle-1"}\n', encoding="utf-8")

    calls = {"reads": 0}
    original = cli._load_ouroboros_observation

    def _tracked_loader(**kwargs):
        calls["reads"] += 1
        return original(**kwargs)

    monkeypatch.setattr(cli, "_load_ouroboros_observation", _tracked_loader)

    with pytest.raises(ValueError, match="session_id or run_id"):
        await cli._ouroboros_record_payload(log_path=str(log_path))

    assert calls["reads"] == 0


@pytest.mark.asyncio
async def test_ouroboros_record_payload_reads_selected_log_record(monkeypatch, tmp_path):
    """ouroboros record helper should select a cycle from JSONL and normalize binding inputs."""
    import dharma_swarm.dgc_cli as cli

    log_path = tmp_path / "ouroboros_log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "cycle_id": "cycle-1",
                        "source": "dse_integration",
                        "signature": {"recognition_type": "NONE", "swabhaav_ratio": 0.2},
                    }
                ),
                json.dumps(
                    {
                        "cycle_id": "cycle-2",
                        "source": "dse_integration",
                        "signature": {"recognition_type": "GENUINE", "swabhaav_ratio": 0.8},
                        "modifiers": {
                            "quality": 0.85,
                            "mimicry_penalty": 1.0,
                            "recognition_bonus": 1.15,
                            "witness_score": 0.8,
                        },
                        "is_genuine": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class _FakeRuntimeState:
        def __init__(self, db_path):
            seen["runtime_db_path"] = db_path
            self.db_path = db_path or Path("/tmp/default-runtime.db")

    class _FakeMemoryLattice:
        def __init__(self, *, db_path, event_log_dir=None):
            seen["memory_db_path"] = db_path
            seen["event_log_dir"] = event_log_dir

        async def close(self):
            seen["closed"] = True

    class _FakeArtifact:
        artifact_id = "art-ouro-direct"

    class _FakeFact:
        fact_id = "fact-ouro-direct"

    class _FakeResult:
        artifact = _FakeArtifact()
        manifest_path = Path("/tmp/ouroboros-manifest.json")
        summary = {"cycle_id": "cycle-2", "recognition_type": "GENUINE"}
        facts = [_FakeFact()]
        receipt = {"event_id": "evt-ouro-direct"}

    class _FakeRegistry:
        def __init__(
            self,
            *,
            runtime_state,
            memory_lattice,
            workspace_root=None,
            provenance_root=None,
        ):
            seen["workspace_root"] = workspace_root
            seen["provenance_root"] = provenance_root
            seen["runtime_state"] = runtime_state
            seen["memory_lattice"] = memory_lattice

        async def record_ouroboros_observation(self, payload, **kwargs):
            seen["record_payload"] = payload
            seen["record_kwargs"] = kwargs
            return _FakeResult()

    monkeypatch.setattr("dharma_swarm.runtime_state.RuntimeStateStore", _FakeRuntimeState)
    monkeypatch.setattr("dharma_swarm.memory_lattice.MemoryLattice", _FakeMemoryLattice)
    monkeypatch.setattr("dharma_swarm.evaluation_registry.EvaluationRegistry", _FakeRegistry)

    out = await cli._ouroboros_record_payload(
        session_id="  sess-ouro  ",
        task_id="   ",
        trace_id="   ",
        cycle_id=" cycle-2 ",
        log_path=str(log_path),
        db_path="/tmp/runtime.db",
        event_log_dir="/tmp/events",
        workspace_root="/tmp/workspace",
        provenance_root="/tmp/provenance",
    )

    assert seen["runtime_db_path"] == Path("/tmp/runtime.db")
    assert seen["memory_db_path"] == Path("/tmp/runtime.db")
    assert seen["event_log_dir"] == Path("/tmp/events")
    assert seen["workspace_root"] == Path("/tmp/workspace")
    assert seen["provenance_root"] == Path("/tmp/provenance")
    assert seen["record_payload"]["cycle_id"] == "cycle-2"
    assert seen["record_payload"]["signature"]["recognition_type"] == "GENUINE"
    assert seen["record_kwargs"] == {
        "run_id": "",
        "session_id": "sess-ouro",
        "task_id": "",
        "trace_id": None,
        "created_by": "dgc_cli",
    }
    assert seen["closed"] is True
    assert out["registry"]["artifact_id"] == "art-ouro-direct"
    assert out["registry"]["receipt_event_id"] == "evt-ouro-direct"
    assert out["log_path"] == str(log_path)


@pytest.mark.asyncio
async def test_ouroboros_record_payload_uses_inline_json_without_log_read(monkeypatch):
    """ouroboros record helper should accept archived JSON without reading the log."""
    import dharma_swarm.dgc_cli as cli

    seen: dict[str, object] = {}

    def _unexpected_loader(**kwargs):
        raise AssertionError("log loading should be skipped for inline ouroboros payloads")

    class _FakeRuntimeState:
        def __init__(self, db_path):
            self.db_path = db_path or Path("/tmp/default-runtime.db")

    class _FakeMemoryLattice:
        def __init__(self, *, db_path, event_log_dir=None):
            seen["memory_db_path"] = db_path
            seen["event_log_dir"] = event_log_dir

        async def close(self):
            seen["closed"] = True

    class _FakeArtifact:
        artifact_id = "art-ouro-inline"

    class _FakeFact:
        fact_id = "fact-ouro-inline"

    class _FakeResult:
        artifact = _FakeArtifact()
        manifest_path = Path("/tmp/ouroboros-manifest-inline.json")
        summary = {"cycle_id": "cycle-inline", "recognition_type": "GENUINE"}
        facts = [_FakeFact()]
        receipt = {"event_id": "evt-ouro-inline"}

    class _FakeRegistry:
        def __init__(
            self,
            *,
            runtime_state,
            memory_lattice,
            workspace_root=None,
            provenance_root=None,
        ):
            seen["workspace_root"] = workspace_root
            seen["provenance_root"] = provenance_root

        async def record_ouroboros_observation(self, payload, **kwargs):
            seen["record_payload"] = payload
            seen["record_kwargs"] = kwargs
            return _FakeResult()

    monkeypatch.setattr(cli, "_load_ouroboros_observation", _unexpected_loader)
    monkeypatch.setattr("dharma_swarm.runtime_state.RuntimeStateStore", _FakeRuntimeState)
    monkeypatch.setattr("dharma_swarm.memory_lattice.MemoryLattice", _FakeMemoryLattice)
    monkeypatch.setattr("dharma_swarm.evaluation_registry.EvaluationRegistry", _FakeRegistry)

    out = await cli._ouroboros_record_payload(
        session_id="sess-inline",
        json_payload='{"cycle_id":"cycle-inline","signature":{"recognition_type":"GENUINE"}}',
        event_log_dir="/tmp/events",
        workspace_root="/tmp/workspace",
        provenance_root="/tmp/provenance",
    )

    assert seen["record_payload"] == {
        "cycle_id": "cycle-inline",
        "signature": {"recognition_type": "GENUINE"},
    }
    assert seen["record_kwargs"] == {
        "run_id": "",
        "session_id": "sess-inline",
        "task_id": "",
        "trace_id": None,
        "created_by": "dgc_cli",
    }
    assert seen["closed"] is True
    assert out["log_path"] is None
    assert out["registry"]["artifact_id"] == "art-ouro-inline"


@pytest.mark.asyncio
async def test_ouroboros_record_payload_rejects_mixed_inline_and_log_sources(
    monkeypatch,
    tmp_path,
):
    """ouroboros record helper should reject ambiguous input source selection."""
    import dharma_swarm.dgc_cli as cli

    calls = {"reads": 0}
    log_path = tmp_path / "ouroboros.jsonl"
    log_path.write_text('{"cycle_id":"cycle-1"}\n', encoding="utf-8")

    def _tracked_loader(**kwargs):
        calls["reads"] += 1
        raise AssertionError("loader should not run for invalid mixed-source inputs")

    monkeypatch.setattr(cli, "_load_ouroboros_observation", _tracked_loader)

    with pytest.raises(
        ValueError,
        match="ouroboros record accepts either --json/--file or --log-path/--cycle-id, not both",
    ):
        await cli._ouroboros_record_payload(
            session_id="sess-inline",
            json_payload='{"cycle_id":"cycle-inline"}',
            log_path=str(log_path),
        )

    assert calls["reads"] == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"threshold": -0.01}, "threshold must be >= 0"),
        (
            {"disagreement_threshold": -0.01},
            "disagreement_threshold must be >= 0",
        ),
    ],
)
def test_cmd_ouroboros_connections_rejects_negative_thresholds(
    monkeypatch,
    kwargs,
    message,
):
    import dharma_swarm.dgc_cli as cli

    called = False

    def _unexpected_profile(*args, **inner_kwargs):
        nonlocal called
        called = True
        raise AssertionError("profile_python_modules should not be called")

    monkeypatch.setattr(
        "dharma_swarm.ouroboros.profile_python_modules",
        _unexpected_profile,
    )

    with pytest.raises(ValueError, match=message):
        cli.cmd_ouroboros_connections(**kwargs)

    assert called is False


def test_cmd_mission_status_formats_gap_report(capsys, monkeypatch):
    """Mission status should show core lane, local-only files, and accelerator state."""
    import dharma_swarm.dgc_cli as cli

    seen_paths: list[str] = []

    monkeypatch.setattr(
        cli,
        "_core_mission_checks",
        lambda: {"planner_executor": True, "think_points": False},
    )
    monkeypatch.setattr(
        cli,
        "_tracked_paths",
        lambda paths: seen_paths.extend(paths) or {
            "dharma_swarm/integrations/nvidia_rag.py": True,
            "dharma_swarm/integrations/reciprocity_commons.py": True,
            "scripts/thinkodynamic_director.py": False,
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
            "reciprocity_health": "PASS",
        }

    monkeypatch.setattr(cli, "_run", _fake_run)

    rc = cli.cmd_mission_status()
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== DGC MISSION STATUS ===" in out
    assert "Core intelligence lane: 1/2 wired" in out
    assert "[LOCAL-ONLY] scripts/thinkodynamic_director.py" in out
    assert "[rag_health] PASS" in out
    assert "[reciprocity_health] PASS" in out
    assert "dharma_swarm/evaluation_registry.py" in seen_paths
    assert "dharma_swarm/ouroboros.py" in seen_paths
    assert "scripts/connection_finder.py" in seen_paths
    assert "scripts/ouroboros_experiment.py" in seen_paths
    assert "tests/test_evaluation_registry.py" in seen_paths
    assert "tests/test_ouroboros.py" in seen_paths
    assert "dharma_swarm/integrations/reciprocity_commons.py" in seen_paths
    assert "tests/test_integrations_reciprocity_commons.py" in seen_paths


def test_mission_tracked_paths_include_behavioral_registry_lane():
    """mission-status should watch the canonical registry and ouroboros lane files."""
    import dharma_swarm.dgc_cli as cli

    tracked = set(cli.MISSION_TRACKED_PATHS)

    assert "dharma_swarm/evaluation_registry.py" in tracked
    assert "dharma_swarm/ouroboros.py" in tracked
    assert "scripts/connection_finder.py" in tracked
    assert "scripts/ouroboros_experiment.py" in tracked
    assert "tests/test_evaluation_registry.py" in tracked
    assert "tests/test_ouroboros.py" in tracked


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
        return {
            "rag_health": "BLOCKED",
            "ingest_health": "BLOCKED",
            "flywheel_jobs": "BLOCKED",
            "reciprocity_health": "BLOCKED",
        }

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
        return {
            "rag_health": "PASS",
            "ingest_health": "PASS",
            "flywheel_jobs": "PASS",
            "reciprocity_health": "PASS",
        }

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
        return {
            "rag_health": "PASS",
            "ingest_health": "PASS",
            "flywheel_jobs": "PASS",
            "reciprocity_health": "PASS",
        }

    monkeypatch.setattr(cli, "_run", _fake_run)
    rc = cli.cmd_mission_status(profile="workspace_auto")
    assert rc == 2
    out = capsys.readouterr().out
    assert "Autonomy profile: workspace_auto" in out


def test_cmd_mission_status_marks_accelerators_dormant(monkeypatch, capsys):
    """Dormant accelerator mode should skip live probes cleanly."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(cli, "_core_mission_checks", lambda: {"a": True})
    monkeypatch.setattr(cli, "_tracked_paths", lambda _paths: {"x": True})
    monkeypatch.setattr(cli, "_read_openclaw_summary", lambda: {"present": True, "readable": True})

    with patch.dict("os.environ", {"DGC_ACCELERATOR_MODE": "dormant"}, clear=False):
        rc = cli.cmd_mission_status(as_json=True)

    assert rc == 0
    out = capsys.readouterr().out
    assert '"rag_health": "DORMANT"' in out
    assert '"flywheel_jobs": "DORMANT"' in out
    assert '"reciprocity_health": "DORMANT"' in out


def test_accelerator_mode_enables_when_reciprocity_url_present():
    """Reciprocity URL alone should wake the optional accelerator lane."""
    import dharma_swarm.dgc_cli as cli

    with patch.dict(
        "os.environ",
        {
            "DGC_NVIDIA_RAG_URL": "",
            "DGC_NVIDIA_INGEST_URL": "",
            "DGC_DATA_FLYWHEEL_URL": "",
            "DGC_RECIPROCITY_COMMONS_URL": "http://commons.local/v1",
            "DGC_ACCELERATOR_MODE": "",
        },
        clear=False,
    ):
        assert cli._accelerator_mode() == "enabled"


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


def test_dgc_cli_full_power_probe_dispatch():
    """main() dispatches full-power-probe flags to cmd_full_power_probe."""
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "full-power-probe",
            "--skip-stress",
            "--skip-pytest",
            "--skip-sprint-probe",
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_full_power_probe") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            kwargs = mock_cmd.call_args.kwargs
            assert kwargs["skip_stress"] is True
            assert kwargs["skip_pytest"] is True
            assert kwargs["skip_sprint_probe"] is True


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


def test_cmd_full_power_probe_invokes_runner(capsys):
    """cmd_full_power_probe should call the reusable probe module."""
    import dharma_swarm.dgc_cli as cli

    payload = {
        "report_markdown_path": "/tmp/probe.md",
        "report_json_path": "/tmp/probe.json",
    }
    with patch("dharma_swarm.full_power_probe.run_full_power_probe", return_value=payload) as mock_run:
        cli.cmd_full_power_probe(
            route_task="route me",
            context_search_query="find me",
            compose_task="compose me",
            autonomy_action="approve me",
            skip_sprint_probe=True,
            skip_stress=True,
            skip_pytest=True,
        )
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["python_executable"] == sys.executable
        assert kwargs["include_sprint_probe"] is False
        assert kwargs["run_stress"] is False
        assert kwargs["run_pytest"] is False

    out = capsys.readouterr().out
    assert "/tmp/probe.md" in out
    assert "/tmp/probe.json" in out


def test_cmd_sprint_falls_back_to_local_on_non_runtime_error(
    tmp_path,
    monkeypatch,
    capsys,
):
    """cmd_sprint should fall back locally for network/transport failures too."""
    import dharma_swarm.dgc_cli as cli

    monkeypatch.setattr(
        "dharma_swarm.master_prompt_engineer.gather_system_state",
        lambda: {
            "live_signals": {
                "morning_brief": "brief",
                "dream_seeds": "dreams",
                "sprint_handoff": "handoff",
            }
        },
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.master_prompt_engineer._days_to_colm",
        lambda: (14, 19),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.master_prompt_engineer.generate_local_prompt",
        lambda **_: "LOCAL SPRINT",
        raising=True,
    )

    async def _boom(**_: object) -> str:
        raise ValueError("network blocked")

    monkeypatch.setattr(
        "dharma_swarm.master_prompt_engineer.generate_evolved_prompt",
        _boom,
        raising=True,
    )

    output = tmp_path / "SPRINT.md"
    cli.cmd_sprint(output=str(output))

    out = capsys.readouterr().out
    assert "network blocked" in out
    assert "using local mode" in out

    contents = output.read_text()
    assert "Mode**: local (fallback)" in contents
    assert "LOCAL SPRINT" in contents
