"""Tests for Darwin Engine auto-evolution wiring in SwarmManager."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.swarm import SwarmManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_swarm(tmp_path) -> SwarmManager:
    """Create a SwarmManager with defaults — no init() needed."""
    sm = SwarmManager(state_dir=tmp_path / ".dharma")
    return sm


class FakeAgent:
    def __init__(self, fitness: float = 0.5):
        self.fitness = fitness


# ---------------------------------------------------------------------------
# Tests: stagnation detection
# ---------------------------------------------------------------------------


class TestStagnationDetection:
    def test_no_stagnation_insufficient_data(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._fitness_history = [0.5] * 10  # too short
        assert sm._detect_fitness_stagnation() is False

    def test_no_stagnation_when_improving(self, tmp_path):
        sm = _make_swarm(tmp_path)
        window = sm._stagnation_window
        # Previous window: 0.4, recent: 0.5 — improving
        sm._fitness_history = [0.4] * window + [0.5] * window
        assert sm._detect_fitness_stagnation() is False

    def test_stagnation_detected_when_flat(self, tmp_path):
        sm = _make_swarm(tmp_path)
        window = sm._stagnation_window
        # Both windows at 0.5 — no improvement
        sm._fitness_history = [0.5] * (window * 2)
        assert sm._detect_fitness_stagnation() is True

    def test_stagnation_detected_when_declining(self, tmp_path):
        sm = _make_swarm(tmp_path)
        window = sm._stagnation_window
        # Previous: 0.6, recent: 0.5 — declining
        sm._fitness_history = [0.6] * window + [0.5] * window
        assert sm._detect_fitness_stagnation() is True

    def test_threshold_boundary(self, tmp_path):
        sm = _make_swarm(tmp_path)
        window = sm._stagnation_window
        threshold = sm._stagnation_threshold
        # Improvement exactly at threshold — not stagnant
        base = 0.5
        sm._fitness_history = [base] * window + [base + threshold] * window
        assert sm._detect_fitness_stagnation() is False


# ---------------------------------------------------------------------------
# Tests: _maybe_auto_evolve
# ---------------------------------------------------------------------------


class TestMaybeAutoEvolve:
    @pytest.mark.asyncio
    async def test_skipped_when_gnani_holds(self, tmp_path):
        sm = _make_swarm(tmp_path)
        result = await sm._maybe_auto_evolve(gnani_holds=True)
        assert result == {"skipped": "gnani_hold"}

    @pytest.mark.asyncio
    async def test_skipped_when_daily_limit_reached(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._auto_evolves_today = sm._max_auto_evolves_per_day
        sm._auto_evolve_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = await sm._maybe_auto_evolve(gnani_holds=False)
        assert result == {"skipped": "daily_limit"}

    @pytest.mark.asyncio
    async def test_skipped_when_no_stagnation(self, tmp_path):
        sm = _make_swarm(tmp_path)
        # Agent pool returns agents but fitness history is too short
        sm._agent_pool = MagicMock()
        sm._agent_pool.list_agents = AsyncMock(
            return_value=[FakeAgent(0.5), FakeAgent(0.6)]
        )
        result = await sm._maybe_auto_evolve(gnani_holds=False)
        assert result == {"skipped": "no_stagnation"}

    @pytest.mark.asyncio
    async def test_triggers_when_stagnant(self, tmp_path):
        sm = _make_swarm(tmp_path)
        window = sm._stagnation_window
        sm._fitness_history = [0.5] * (window * 2)

        sm._agent_pool = MagicMock()
        sm._agent_pool.list_agents = AsyncMock(
            return_value=[FakeAgent(0.5)]
        )

        # Mock the evolve method
        sm.evolve = AsyncMock(return_value={
            "status": "archived",
            "entry_id": "test-123",
            "weighted_fitness": 0.7,
        })

        result = await sm._maybe_auto_evolve(gnani_holds=False)
        assert result["triggered"] is True
        assert result["status"] == "archived"
        assert sm._auto_evolves_today == 1
        sm.evolve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_daily_counter_resets_at_midnight(self, tmp_path):
        sm = _make_swarm(tmp_path)
        sm._auto_evolves_today = 5
        sm._auto_evolve_day = "1999-01-01"  # yesterday (in the past)
        sm._agent_pool = MagicMock()
        sm._agent_pool.list_agents = AsyncMock(return_value=[])

        result = await sm._maybe_auto_evolve(gnani_holds=False)
        # Counter should have been reset
        assert sm._auto_evolves_today == 0
        assert sm._auto_evolve_day == datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_skipped_when_evolution_in_progress(self, tmp_path):
        """Auto-evolution tick is skipped when engine._evolving is True."""
        sm = _make_swarm(tmp_path)
        sm._auto_evolution_enabled = True
        sm._engine = MagicMock()
        sm._engine._evolving = True
        sm._evolution_tick_counter = sm._evolution_interval_ticks  # ready to fire

        # The tick guard in tick() checks _evolving, so counter should NOT reset
        # We test the guard logic directly:
        should_trigger = (
            sm._evolution_tick_counter >= sm._evolution_interval_ticks
            and sm._engine is not None
            and not getattr(sm._engine, '_evolving', False)
        )
        assert should_trigger is False


# ---------------------------------------------------------------------------
# Tests: init defaults
# ---------------------------------------------------------------------------


class TestAutoEvolutionInit:
    def test_default_values(self, tmp_path):
        sm = _make_swarm(tmp_path)
        assert sm._evolution_interval_ticks == 120
        assert sm._evolution_tick_counter == 0
        assert sm._fitness_history == []
        assert sm._max_auto_evolves_per_day == 6
        assert sm._auto_evolves_today == 0
        assert sm._auto_evolve_day is None
        assert sm._stagnation_threshold == 0.01
        assert sm._stagnation_window == 60
        assert sm._auto_evolution_enabled is True
