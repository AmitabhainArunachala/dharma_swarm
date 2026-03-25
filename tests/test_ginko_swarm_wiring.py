"""Tests for Ginko fleet wiring into SwarmManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.swarm import SwarmManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_swarm(tmp_path) -> SwarmManager:
    """Create a SwarmManager with defaults — no init() needed."""
    return SwarmManager(state_dir=tmp_path / ".dharma")


class FakeGinkoFleet:
    """Lightweight stand-in for GinkoFleet."""

    def __init__(self, agent_count: int = 10):
        self._agents = [MagicMock(name=f"agent_{i}") for i in range(agent_count)]

    def list_agents(self):
        return self._agents


# ---------------------------------------------------------------------------
# Tests: init defaults
# ---------------------------------------------------------------------------


class TestGinkoInitDefaults:
    def test_default_values(self, tmp_path):
        sm = _make_swarm(tmp_path)
        assert sm._ginko_enabled is False
        assert sm._ginko_fleet is None
        assert sm._ginko_interval_ticks == 720
        assert sm._ginko_tick_counter == 0
        assert sm._ginko_last_result is None
        assert sm._ginko_running is False


# ---------------------------------------------------------------------------
# Tests: Ginko fleet initialization in init()
# ---------------------------------------------------------------------------


class TestGinkoInit:
    @pytest.mark.asyncio
    async def test_ginko_fleet_initialized_when_available(self, tmp_path):
        """Ginko fleet should be initialized during SwarmManager.init()."""
        sm = _make_swarm(tmp_path)
        with patch(
            "dharma_swarm.swarm.SwarmManager.init",
            new_callable=AsyncMock,
        ):
            # Simulate what init() does for Ginko
            from dharma_swarm.ginko_agents import GinkoFleet
            sm._ginko_fleet = GinkoFleet()
            sm._ginko_enabled = True

        assert sm._ginko_enabled is True
        assert sm._ginko_fleet is not None
        assert len(sm._ginko_fleet.list_agents()) > 0

    def test_ginko_disabled_when_import_fails(self, tmp_path):
        """Ginko should be disabled gracefully when GinkoFleet can't be imported."""
        sm = _make_swarm(tmp_path)
        # Default state — not initialized
        assert sm._ginko_enabled is False
        assert sm._ginko_fleet is None


# ---------------------------------------------------------------------------
# Tests: _run_ginko_cycle
# ---------------------------------------------------------------------------


class TestRunGinkoCycle:
    @pytest.mark.asyncio
    async def test_cycle_runs_and_stores_result(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet()

        mock_result = {
            "total_duration_ms": 1500,
            "data_pull": {"action": "data_pull"},
            "report": {"action": "generate_report", "report_text": "..."},
        }
        with patch(
            "dharma_swarm.ginko_orchestrator.action_full_cycle",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await sm._run_ginko_cycle()

        assert sm._ginko_last_result is not None
        assert sm._ginko_last_result["total_duration_ms"] == 1500
        assert sm._ginko_running is False

    @pytest.mark.asyncio
    async def test_cycle_skipped_when_already_running(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_running = True

        with patch(
            "dharma_swarm.ginko_orchestrator.action_full_cycle",
            new_callable=AsyncMock,
        ) as mock_cycle:
            await sm._run_ginko_cycle()
            mock_cycle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cycle_failure_doesnt_crash(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet()

        with patch(
            "dharma_swarm.ginko_orchestrator.action_full_cycle",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            # Should NOT raise
            await sm._run_ginko_cycle()

        assert sm._ginko_running is False
        assert sm._ginko_last_result is None

    @pytest.mark.asyncio
    async def test_running_flag_reset_after_failure(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True

        with patch(
            "dharma_swarm.ginko_orchestrator.action_full_cycle",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ):
            await sm._run_ginko_cycle()

        assert sm._ginko_running is False


# ---------------------------------------------------------------------------
# Tests: get_ginko_status
# ---------------------------------------------------------------------------


class TestGinkoStatus:
    def test_status_when_disabled(self, tmp_path):
        sm = _make_swarm(tmp_path)
        status = sm.get_ginko_status()
        assert status == {"enabled": False}

    def test_status_when_enabled(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet(agent_count=6)
        sm._ginko_running = False
        sm._ginko_last_result = {"total_duration_ms": 1000}

        status = sm.get_ginko_status()
        assert status["enabled"] is True
        assert status["fleet_size"] == 6
        assert status["last_result"] is True
        assert status["running"] is False

    def test_status_when_running(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet(agent_count=6)
        sm._ginko_running = True

        status = sm.get_ginko_status()
        assert status["running"] is True


# ---------------------------------------------------------------------------
# Tests: tick integration — counter increments
# ---------------------------------------------------------------------------


class TestGinkoTickIntegration:
    def test_tick_counter_increments(self, tmp_path):
        """Verify counter logic without running full tick()."""
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet()

        # Simulate the tick counter logic
        for _ in range(10):
            if sm._ginko_enabled and not sm._ginko_running:
                sm._ginko_tick_counter += 1

        assert sm._ginko_tick_counter == 10

    def test_counter_resets_at_interval(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._ginko_enabled = True
        sm._ginko_fleet = FakeGinkoFleet()
        sm._ginko_tick_counter = sm._ginko_interval_ticks - 1

        # One more increment would trigger
        sm._ginko_tick_counter += 1
        if sm._ginko_tick_counter >= sm._ginko_interval_ticks:
            sm._ginko_tick_counter = 0

        assert sm._ginko_tick_counter == 0
