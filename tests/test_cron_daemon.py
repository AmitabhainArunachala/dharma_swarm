from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from dharma_swarm import cron_scheduler
from dharma_swarm.cron_daemon import run_cron_daemon
from dharma_swarm.cron_runner import run_cron_job


def test_run_cron_daemon_runs_tick_and_cleans_pid(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    cron_dir = tmp_path / "cron"
    monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)

    calls: list[tuple[bool, object]] = []

    def fake_tick(*, verbose: bool, run_fn: object) -> int:
        calls.append((verbose, run_fn))
        return 2

    with patch("dharma_swarm.cron_daemon.cron_scheduler.tick", side_effect=fake_tick):
        executed = run_cron_daemon(interval_sec=0, max_loops=2, tick_verbose=True)

    out = capsys.readouterr().out
    assert executed == 4
    assert calls == [(True, run_cron_job), (True, run_cron_job)]
    assert not (cron_dir / "daemon.pid").exists()
    assert "Cron daemon starting" in out
    assert "Cron daemon stopped" in out


def test_run_cron_daemon_can_skip_initial_tick(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cron_dir = tmp_path / "cron"
    monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)

    class FakeStopEvent:
        def is_set(self) -> bool:
            return False

        def set(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> bool:
            return True

    stop_event = FakeStopEvent()

    with patch("dharma_swarm.cron_daemon.cron_scheduler.tick") as mock_tick:
        executed = run_cron_daemon(
            interval_sec=30,
            run_immediately=False,
            stop_event=stop_event,  # type: ignore[arg-type]
        )

    assert executed == 0
    mock_tick.assert_not_called()
