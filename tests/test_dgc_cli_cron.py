from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_cmd_cron_tick_uses_cron_runner(capsys) -> None:
    import dharma_swarm.dgc_cli as cli
    from dharma_swarm.cron_runner import run_cron_job

    with patch("dharma_swarm.cron_scheduler.tick", return_value=3) as mock_tick:
        cli.cmd_cron("tick")

    out = capsys.readouterr().out
    assert out.strip().endswith("Tick complete: 3 job(s) executed")
    assert mock_tick.call_args.kwargs["verbose"] is True
    assert mock_tick.call_args.kwargs["run_fn"] is run_cron_job


def test_cmd_cron_daemon_forwards_flags(capsys) -> None:
    import dharma_swarm.dgc_cli as cli

    with patch("dharma_swarm.cron_daemon.run_cron_daemon", return_value=5) as mock_daemon:
        cli.cmd_cron(
            "daemon",
            interval_sec=15,
            max_loops=2,
            run_immediately=False,
        )

    out = capsys.readouterr().out
    assert out.strip().endswith("Cron daemon exited: 5 job(s) executed")
    assert mock_daemon.call_args.kwargs == {
        "interval_sec": 15,
        "max_loops": 2,
        "run_immediately": False,
        "tick_verbose": False,
    }


def test_dgc_cli_main_dispatches_cron_daemon_flags() -> None:
    from dharma_swarm.dgc_cli import main

    with patch(
        "sys.argv",
        [
            "dgc",
            "cron",
            "daemon",
            "--interval-sec",
            "45",
            "--max-loops",
            "3",
            "--no-run-immediately",
        ],
    ):
        with patch("dharma_swarm.dgc_cli.cmd_cron") as mock_cmd:
            main()

    assert mock_cmd.call_args.kwargs["cron_cmd"] == "daemon"
    assert mock_cmd.call_args.kwargs["interval_sec"] == 45.0
    assert mock_cmd.call_args.kwargs["max_loops"] == 3
    assert mock_cmd.call_args.kwargs["run_immediately"] is False
