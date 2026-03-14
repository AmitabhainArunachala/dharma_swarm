"""Tests for FitnessLandscapeMap — time-series fitness tracking per component."""

from __future__ import annotations

import pytest

from dharma_swarm.landscape import (
    ComponentLandscapeState,
    FitnessLandscapeMap,
    LandscapeEvent,
)


def test_landscape_map_records_and_returns_none_initially() -> None:
    """First record has no prior context — event should be NONE."""
    lmap = FitnessLandscapeMap()
    event = lmap.record(component_type="swarm", score=0.65)
    assert event == LandscapeEvent.NONE
    state = lmap.get_state("swarm")
    assert state is not None
    assert len(state.scores) == 1
    assert state.scores[0] == pytest.approx(0.65)


def test_landscape_map_detects_plateau() -> None:
    """Five consecutive identical scores should trigger a plateau event."""
    lmap = FitnessLandscapeMap(
        plateau_window=5,
        plateau_variance_threshold=0.005,
    )
    for _ in range(5):
        event = lmap.record(component_type="agent", score=0.70)
    assert event == LandscapeEvent.PLATEAU
    state = lmap.get_state("agent")
    assert state is not None
    assert "Plateau" in state.event_detail


def test_landscape_map_detects_regression() -> None:
    """Score dropping >=20% from peak should trigger a regression event."""
    lmap = FitnessLandscapeMap(regression_pct=0.20)
    lmap.record(component_type="evolution", score=0.80)
    lmap.record(component_type="evolution", score=0.82)
    # Drop to 0.60 — that's (0.82-0.60)/0.82 ~ 26.8%, exceeds 20% threshold
    event = lmap.record(component_type="evolution", score=0.60)
    assert event == LandscapeEvent.REGRESSION
    state = lmap.get_state("evolution")
    assert state is not None
    assert "Regression" in state.event_detail
    assert state.peak_score == pytest.approx(0.82)


def test_landscape_map_detects_breakthrough() -> None:
    """Score jumping >=30% above recent mean should trigger a breakthrough."""
    lmap = FitnessLandscapeMap(breakthrough_pct=0.30, plateau_window=3)
    # Establish a low baseline
    for _ in range(3):
        lmap.record(component_type="synthesis", score=0.50)
    # Jump to 0.75 — that's (0.75-0.50)/0.50 = 50%, exceeds 30% threshold
    event = lmap.record(component_type="synthesis", score=0.75)
    assert event == LandscapeEvent.BREAKTHROUGH
    state = lmap.get_state("synthesis")
    assert state is not None
    assert "Breakthrough" in state.event_detail


def test_landscape_summary_returns_all_components() -> None:
    """landscape_summary() should include all recorded component types."""
    lmap = FitnessLandscapeMap()
    lmap.record("swarm", 0.65)
    lmap.record("swarm", 0.70)
    lmap.record("agent", 0.55)
    lmap.record("monitor", 0.80)

    summary = lmap.landscape_summary()
    assert set(summary.keys()) == {"swarm", "agent", "monitor"}

    swarm_entry = summary["swarm"]
    assert swarm_entry["n_records"] == 2
    assert swarm_entry["peak_score"] == pytest.approx(0.70)
    assert "event" in swarm_entry
    assert "event_detail" in swarm_entry
    assert "recent_mean" in swarm_entry


def test_landscape_map_independent_per_component_type() -> None:
    """Each component type has its own independent state."""
    lmap = FitnessLandscapeMap(regression_pct=0.20)
    # Swarm at high fitness
    lmap.record("swarm", 0.90)
    # Agent at low fitness — should NOT trigger regression on swarm
    lmap.record("agent", 0.10)

    swarm_state = lmap.get_state("swarm")
    agent_state = lmap.get_state("agent")
    assert swarm_state is not None
    assert agent_state is not None
    assert swarm_state.event != LandscapeEvent.REGRESSION
    assert swarm_state.peak_score == pytest.approx(0.90)
    assert agent_state.peak_score == pytest.approx(0.10)
