"""Tests for dharma_swarm.sleep_cycle -- sleep-time memory consolidation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.sleep_cycle import SleepCycle, SleepPhase, SleepReport


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _mock_stigmergy(
    decay_count: int = 5,
    hot: list[tuple[str, int]] | None = None,
    high_sal: list[Any] | None = None,
) -> AsyncMock:
    """Build a mock StigmergyStore with sensible defaults."""
    store = AsyncMock()
    store.decay = AsyncMock(return_value=decay_count)
    store.hot_paths = AsyncMock(return_value=hot or [("src/models.py", 7)])
    # High salience returns mark-like objects with .observation
    marks = []
    for obs in (high_sal or ["R_V contraction at L27"]):
        m = MagicMock()
        m.observation = obs
        marks.append(m)
    store.high_salience = AsyncMock(return_value=marks)
    return store


def _mock_subconscious(
    should: bool = True, dream_count: int = 3
) -> AsyncMock:
    """Build a mock SubconsciousStream."""
    stream = AsyncMock()
    stream.should_wake = AsyncMock(return_value=should)
    associations = [MagicMock() for _ in range(dream_count)]
    stream.dream = AsyncMock(return_value=associations)
    return stream


@pytest.fixture
def cycle(tmp_path: Path) -> SleepCycle:
    """SleepCycle with tmp dirs and mocked subsystems."""
    mem_dir = tmp_path / "agent_memory"
    mem_dir.mkdir()
    reports = tmp_path / "reports"
    return SleepCycle(
        agent_memory_dir=mem_dir,
        stigmergy_store=_mock_stigmergy(),
        subconscious_stream=_mock_subconscious(),
        reports_dir=reports,
    )


def _seed_agent_memory(mem_dir: Path, agent_name: str) -> None:
    """Write a minimal working-memory JSON file for an agent."""
    agent_dir = mem_dir / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "scratch": {
            "key": "scratch",
            "value": "temp note",
            "category": "working",
            "importance": 0.1,
            "access_count": 0,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
            "expires_at": None,
            "source": "",
        }
    }
    (agent_dir / "working.json").write_text(json.dumps(entry))
    (agent_dir / "archival.json").write_text("{}")
    (agent_dir / "persona.json").write_text("{}")


# ---------------------------------------------------------------------------
# 1. Full cycle completes all 4 phases
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_run_full_cycle_completes_all_phases(cycle: SleepCycle) -> None:
    report = await cycle.run_full_cycle()
    assert report.phases_completed == ["light", "deep", "rem", "semantic", "wake"]
    assert report.ended_at is not None
    assert report.started_at <= report.ended_at


# ---------------------------------------------------------------------------
# 2. Light sleep decays stigmergy marks
# ---------------------------------------------------------------------------


async def test_light_sleep_decays_marks(cycle: SleepCycle) -> None:
    result = await cycle.run_phase(SleepPhase.LIGHT)
    assert result["marks_decayed"] == 5
    assert "src/models.py" in result["hot_paths"]


# ---------------------------------------------------------------------------
# 3. Deep sleep consolidates agent memories
# ---------------------------------------------------------------------------


async def test_deep_sleep_consolidates(tmp_path: Path) -> None:
    mem_dir = tmp_path / "agent_memory"
    mem_dir.mkdir()
    _seed_agent_memory(mem_dir, "cartographer")
    _seed_agent_memory(mem_dir, "surgeon")

    cycle = SleepCycle(
        agent_memory_dir=mem_dir, reports_dir=tmp_path / "reports"
    )
    result = await cycle.run_phase(SleepPhase.DEEP)
    assert result["agents_processed"] == 2
    assert isinstance(result["total_consolidated"], int)


# ---------------------------------------------------------------------------
# 4. REM sleep triggers dreaming when threshold met
# ---------------------------------------------------------------------------


async def test_rem_sleep_dreams_when_threshold(cycle: SleepCycle) -> None:
    result = await cycle.run_phase(SleepPhase.REM)
    assert result["dreams"] == 3
    assert len(result["high_salience"]) >= 1


# ---------------------------------------------------------------------------
# 5. Wake writes sleep report JSON
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_wake_writes_report(cycle: SleepCycle, tmp_path: Path) -> None:
    report = await cycle.run_full_cycle()
    reports_dir = tmp_path / "reports"
    assert reports_dir.exists()
    files = list(reports_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert "phases_completed" in data
    assert "started_at" in data


# ---------------------------------------------------------------------------
# 6. is_quiet_hours returns True during quiet hours
# ---------------------------------------------------------------------------


async def test_is_quiet_hours_true() -> None:
    fake_now = datetime(2026, 3, 8, 3, 15)  # 3:15 AM -- quiet
    with patch("dharma_swarm.sleep_cycle.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert SleepCycle.is_quiet_hours() is True


# ---------------------------------------------------------------------------
# 7. is_quiet_hours returns False outside quiet hours
# ---------------------------------------------------------------------------


async def test_is_quiet_hours_false() -> None:
    fake_now = datetime(2026, 3, 8, 10, 0)  # 10 AM -- not quiet
    with patch("dharma_swarm.sleep_cycle.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert SleepCycle.is_quiet_hours() is False


# ---------------------------------------------------------------------------
# 8. Sleep report has correct phase list
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_report_phase_list(cycle: SleepCycle) -> None:
    report = await cycle.run_full_cycle()
    assert "light" in report.phases_completed
    assert "deep" in report.phases_completed
    assert "rem" in report.phases_completed
    assert "wake" in report.phases_completed


# ---------------------------------------------------------------------------
# 9. Errors in one phase don't block other phases
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_error_isolation(tmp_path: Path) -> None:
    bad_stigmergy = AsyncMock()
    bad_stigmergy.decay = AsyncMock(side_effect=RuntimeError("disk full"))
    bad_stigmergy.hot_paths = AsyncMock(side_effect=RuntimeError("disk full"))

    cycle = SleepCycle(
        agent_memory_dir=tmp_path / "agent_memory",
        stigmergy_store=bad_stigmergy,
        subconscious_stream=_mock_subconscious(),
        reports_dir=tmp_path / "reports",
    )
    (tmp_path / "agent_memory").mkdir()

    report = await cycle.run_full_cycle()
    # Light failed, but deep + rem + wake should still complete
    assert "light" not in report.phases_completed
    assert "deep" in report.phases_completed
    assert "rem" in report.phases_completed
    assert "wake" in report.phases_completed
    assert any("light" in e for e in report.errors)


# ---------------------------------------------------------------------------
# 10. Empty agent_memory_dir handled gracefully
# ---------------------------------------------------------------------------


async def test_empty_memory_dir(tmp_path: Path) -> None:
    mem_dir = tmp_path / "agent_memory"
    mem_dir.mkdir()

    cycle = SleepCycle(
        agent_memory_dir=mem_dir, reports_dir=tmp_path / "reports"
    )
    result = await cycle.run_phase(SleepPhase.DEEP)
    assert result["agents_processed"] == 0
    assert result["total_consolidated"] == 0


# ---------------------------------------------------------------------------
# 11. Graceful degradation without stigmergy/subconscious
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_graceful_degradation(tmp_path: Path) -> None:
    cycle = SleepCycle(
        agent_memory_dir=tmp_path / "agent_memory",
        stigmergy_store=None,
        subconscious_stream=None,
        reports_dir=tmp_path / "reports",
    )
    (tmp_path / "agent_memory").mkdir()

    report = await cycle.run_full_cycle()
    # All phases should complete, just with zero-count metrics
    assert report.phases_completed == ["light", "deep", "rem", "semantic", "wake"]
    assert report.marks_decayed == 0
    assert report.dreams_generated == 0
    assert report.errors == []


# ---------------------------------------------------------------------------
# 12. SleepReport serializes to JSON
# ---------------------------------------------------------------------------


async def test_sleep_report_json_serialization() -> None:
    report = SleepReport(
        started_at=datetime(2026, 3, 8, 2, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 8, 2, 30, tzinfo=timezone.utc),
        phases_completed=["light", "deep", "rem", "wake"],
        marks_decayed=12,
        memories_consolidated=4,
        dreams_generated=7,
        hot_paths_found=["src/models.py"],
        high_salience_observations=["R_V contraction detected"],
        errors=[],
    )
    data = json.loads(report.model_dump_json())
    assert data["marks_decayed"] == 12
    assert data["dreams_generated"] == 7
    assert isinstance(data["phases_completed"], list)
    assert data["hot_paths_found"] == ["src/models.py"]
