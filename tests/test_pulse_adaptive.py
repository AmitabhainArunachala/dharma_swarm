"""Tests for AdaptiveQuietHours — activity-aware quiet hour computation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.daemon_config import AdaptiveQuietHours, DaemonConfig


def _write_activity(log_path: Path, timestamps: list[datetime]) -> None:
    """Write activity timestamps to log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"ts": dt.isoformat()}) for dt in timestamps]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_adaptive_quiet_hours_returns_static_floor_when_no_activity(
    tmp_path: Path,
) -> None:
    """With no recorded activity the result is just the static floor."""
    state_dir = tmp_path / ".dharma"
    aqh = AdaptiveQuietHours(state_dir=state_dir, static_floor=[2, 3, 4, 5])
    quiet = aqh.compute_quiet_hours()
    assert quiet == [2, 3, 4, 5]


def test_adaptive_quiet_hours_includes_active_work_hours(
    tmp_path: Path,
) -> None:
    """Hours with >= threshold activity events should be added as quiet hours."""
    state_dir = tmp_path / ".dharma"
    now = datetime.now(timezone.utc)
    # Simulate 5 activity events at hour 10 within the last 14 days
    timestamps = [now.replace(hour=10, minute=i * 10) for i in range(5)]
    log_path = state_dir / "activity_log.jsonl"
    _write_activity(log_path, timestamps)

    aqh = AdaptiveQuietHours(
        state_dir=state_dir,
        activity_threshold=3,
        static_floor=[2, 3, 4, 5],
    )
    quiet = aqh.compute_quiet_hours()
    # Hour 10 should appear (5 events >= threshold 3)
    assert 10 in quiet
    # Static floor still present
    assert all(h in quiet for h in [2, 3, 4, 5])


def test_adaptive_quiet_hours_prunes_stale_entries(
    tmp_path: Path,
) -> None:
    """Events older than window_days should not count toward active hours."""
    state_dir = tmp_path / ".dharma"
    now = datetime.now(timezone.utc)
    old_ts = now - timedelta(days=20)  # outside 14-day window
    # Write 5 old events at hour 14 + 1 recent event at a different hour
    timestamps = [old_ts.replace(hour=14) for _ in range(5)]
    timestamps.append(now.replace(hour=8))
    log_path = state_dir / "activity_log.jsonl"
    _write_activity(log_path, timestamps)

    aqh = AdaptiveQuietHours(
        state_dir=state_dir,
        window_days=14,
        activity_threshold=3,
        static_floor=[2, 3, 4, 5],
    )
    # Hour 14 events are too old — should NOT be in quiet hours
    active = aqh.active_hours()
    assert 14 not in active


def test_adaptive_quiet_hours_update_config_mutates_in_place(
    tmp_path: Path,
) -> None:
    """update_config should overwrite config.quiet_hours with adaptive values."""
    state_dir = tmp_path / ".dharma"
    now = datetime.now(timezone.utc)
    # 4 events at hour 9 — should trigger addition to quiet hours
    timestamps = [now.replace(hour=9, minute=i * 5) for i in range(4)]
    log_path = state_dir / "activity_log.jsonl"
    _write_activity(log_path, timestamps)

    config = DaemonConfig()
    original_quiet = list(config.quiet_hours)

    aqh = AdaptiveQuietHours(
        state_dir=state_dir,
        activity_threshold=3,
        static_floor=[2, 3, 4, 5],
    )
    aqh.update_config(config)

    # config.quiet_hours is now adaptive — includes both static floor and hour 9
    assert 9 in config.quiet_hours
    assert all(h in config.quiet_hours for h in [2, 3, 4, 5])
    # It changed from the original (which only had [2,3,4,5] without hour 9)
    assert config.quiet_hours != original_quiet or 9 in original_quiet
