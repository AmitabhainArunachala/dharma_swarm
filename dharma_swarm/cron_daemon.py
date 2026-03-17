"""Standalone daemon loop for cron jobs."""

from __future__ import annotations

import logging
import os
import signal
import threading
from typing import Any, Callable

from dharma_swarm import cron_scheduler
from dharma_swarm.cron_runner import run_cron_job

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 60.0


def _as_interval_sec(value: Any, default: float = DEFAULT_INTERVAL_SEC) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _pid_file() -> Any:
    return cron_scheduler.CRON_DIR / "daemon.pid"


def _write_pid_file() -> None:
    cron_scheduler.CRON_DIR.mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(f"{os.getpid()}\n", encoding="utf-8")


def _clear_pid_file() -> None:
    pid_file = _pid_file()
    if not pid_file.exists():
        return
    try:
        if pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            pid_file.unlink()
    except OSError:
        logger.debug("Unable to clear cron daemon pid file", exc_info=True)


def _install_signal_handlers(
    stop_event: threading.Event,
) -> list[tuple[int, Any]]:
    if threading.current_thread() is not threading.main_thread():
        return []

    previous_handlers: list[tuple[int, Any]] = []

    def _handle_signal(signum: int, _frame: Any) -> None:
        logger.info("Cron daemon received signal %s; stopping", signum)
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_handlers.append((signum, signal.getsignal(signum)))
            signal.signal(signum, _handle_signal)
        except (OSError, RuntimeError, ValueError):
            continue
    return previous_handlers


def _restore_signal_handlers(previous_handlers: list[tuple[int, Any]]) -> None:
    for signum, handler in previous_handlers:
        try:
            signal.signal(signum, handler)
        except (OSError, RuntimeError, ValueError):
            continue


def run_cron_daemon(
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    *,
    run_fn: Callable[[dict[str, Any]], tuple[bool, str, str | None]] = run_cron_job,
    stop_event: threading.Event | None = None,
    max_loops: int | None = None,
    run_immediately: bool = True,
    tick_verbose: bool = False,
) -> int:
    """Run the cron scheduler in a persistent loop."""

    interval = _as_interval_sec(interval_sec)
    loop_limit = _as_positive_int_or_none(max_loops)
    stop = stop_event or threading.Event()
    previous_handlers = _install_signal_handlers(stop)
    loops = 0
    executed_total = 0

    _write_pid_file()
    print(
        "Cron daemon starting "
        f"(pid={os.getpid()}, interval={interval:.1f}s, immediate={run_immediately})"
    )

    try:
        if not run_immediately and stop.wait(timeout=interval):
            return 0

        while not stop.is_set():
            try:
                executed_total += cron_scheduler.tick(
                    verbose=tick_verbose,
                    run_fn=run_fn,
                )
            except Exception:
                logger.exception("Cron daemon tick failed")

            loops += 1
            if loop_limit is not None and loops >= loop_limit:
                break
            if stop.wait(timeout=interval):
                break
    except KeyboardInterrupt:
        stop.set()
    finally:
        _restore_signal_handlers(previous_handlers)
        _clear_pid_file()
        print(
            "Cron daemon stopped "
            f"(loops={loops}, jobs_executed={executed_total})"
        )

    return executed_total
