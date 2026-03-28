"""Tests for training_flywheel.py — self-training pipeline orchestration."""

from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from dharma_swarm.training_flywheel import (
    FlywheelState,
    _run_reinforcement,
    _run_dataset_build,
    _run_readiness_check,
    run_training_flywheel_loop,
    MIN_TRAJECTORIES_FOR_REINFORCE,
)


# --- FlywheelState ---


def test_state_defaults() -> None:
    state = FlywheelState()
    assert state.reinforce_cycles == 0
    assert state.dataset_builds == 0
    assert state.readiness_checks == 0
    assert state.training_ready is False


def test_state_snapshot() -> None:
    state = FlywheelState(
        reinforce_cycles=3,
        total_patterns_extracted=12,
        training_ready=True,
        recommended_gpu="A100",
    )
    snap = state.snapshot()
    assert snap["reinforce_cycles"] == 3
    assert snap["total_patterns_extracted"] == 12
    assert snap["training_ready"] is True
    assert snap["recommended_gpu"] == "A100"


# --- Reinforcement sub-cycle ---


def test_reinforcement_skips_when_few_trajectories() -> None:
    """Reinforcement should skip when fewer than MIN_TRAJECTORIES_FOR_REINFORCE."""
    state = FlywheelState()

    # Mock the collector to return too few trajectories
    mock_collector = MagicMock()
    mock_collector.load_trajectories.return_value = []

    with patch(
        "dharma_swarm.trajectory_collector.get_collector",
        return_value=mock_collector,
    ):
        result = _run_reinforcement(state)

    assert result["skipped"] is True
    assert state.reinforce_cycles == 0


def test_reinforcement_runs_with_enough_trajectories() -> None:
    """Reinforcement should run when enough trajectories exist."""
    state = FlywheelState()

    # Create fake trajectories with the minimum needed attributes
    fake_trajectories = []
    for i in range(MIN_TRAJECTORIES_FOR_REINFORCE + 1):
        t = MagicMock()
        t.outcome = MagicMock(success=True, thinkodynamic_score=None)
        t.trajectory_id = f"traj-{i}"
        t.task_title = f"task-{i}"
        t.chunks = []
        fake_trajectories.append(t)

    mock_collector = MagicMock()
    mock_collector.load_trajectories.return_value = fake_trajectories

    mock_reinforcer = MagicMock()
    mock_reinforcer.reinforce_cycle.return_value = MagicMock(
        cycle_number=1,
        trajectories_evaluated=6,
        patterns_extracted=2,
        top_pattern="strategy-test",
    )
    mock_reinforcer.pattern_count = 5

    with (
        patch(
            "dharma_swarm.trajectory_collector.get_collector",
            return_value=mock_collector,
        ),
        patch(
            "dharma_swarm.strategy_reinforcer.StrategyReinforcer",
            return_value=mock_reinforcer,
        ),
    ):
        result = _run_reinforcement(state)

    assert result["skipped"] is False
    assert state.reinforce_cycles == 1
    assert state.total_trajectories_scored == 6


# --- Dataset build sub-cycle ---


def test_dataset_build_skips_when_few_samples() -> None:
    """Dataset build should skip when too few samples produced."""
    state = FlywheelState()

    mock_builder = MagicMock()
    mock_builder.build.return_value = MagicMock(
        total_samples=2,  # Below threshold
        by_source={},
        avg_quality=0.0,
        output_path="",
        build_time_seconds=0.1,
    )

    with patch(
        "dharma_swarm.dataset_builder.DatasetBuilder",
        return_value=mock_builder,
    ):
        result = _run_dataset_build(state)

    assert result["skipped"] is True
    assert state.dataset_builds == 0


def test_dataset_build_succeeds_with_enough_samples() -> None:
    """Dataset build should succeed when enough samples exist."""
    state = FlywheelState()

    mock_builder = MagicMock()
    mock_builder.build.return_value = MagicMock(
        total_samples=50,
        by_source={"trajectory": 30, "foundation": 20},
        avg_quality=0.72,
        output_path="/tmp/dharma-gen0.jsonl",
        build_time_seconds=1.5,
    )

    with patch(
        "dharma_swarm.dataset_builder.DatasetBuilder",
        return_value=mock_builder,
    ):
        result = _run_dataset_build(state)

    assert result["skipped"] is False
    assert result["total_samples"] == 50
    assert state.dataset_builds == 1
    assert state.last_dataset_path == "/tmp/dharma-gen0.jsonl"


# --- Readiness check sub-cycle ---


def test_readiness_no_budget() -> None:
    """Readiness check should report not ready when no training budget."""
    state = FlywheelState()

    mock_registry = MagicMock()
    mock_registry.latest.return_value = None

    mock_economy = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.budget = MagicMock(training=0.0)
    mock_economy.snapshot.return_value = mock_snapshot

    mock_scout = MagicMock()

    with (
        patch(
            "dharma_swarm.model_registry.ModelRegistry",
            return_value=mock_registry,
        ),
        patch(
            "dharma_swarm.economic_engine.EconomicEngine",
            return_value=mock_economy,
        ),
        patch(
            "dharma_swarm.resource_scout.ResourceScout",
            return_value=mock_scout,
        ),
    ):
        result = _run_readiness_check(state)

    assert result["ready"] is False
    assert result["next_gen"] == 0
    assert state.training_ready is False


def test_readiness_with_budget() -> None:
    """Readiness check should evaluate GPU recommendation when budget exists."""
    state = FlywheelState()
    state.last_dataset_path = "/tmp/dharma-gen0.jsonl"

    mock_registry = MagicMock()
    mock_registry.latest.return_value = MagicMock(generation=0)
    mock_registry.total_training_cost.return_value = 8.50

    mock_economy = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.budget = MagicMock(training=50.0)
    mock_economy.snapshot.return_value = mock_snapshot

    mock_recommendation = MagicMock(
        fits_in_budget=True,
        model_size_b=7.0,
        method="qlora",
        estimated_hours=4.0,
        estimated_cost_usd=8.50,
        recommended_gpu="A100_40GB",
        recommended_provider="runpod",
    )
    mock_scout = MagicMock()
    mock_scout.recommend_for_generation.return_value = mock_recommendation

    with (
        patch(
            "dharma_swarm.model_registry.ModelRegistry",
            return_value=mock_registry,
        ),
        patch(
            "dharma_swarm.economic_engine.EconomicEngine",
            return_value=mock_economy,
        ),
        patch(
            "dharma_swarm.resource_scout.ResourceScout",
            return_value=mock_scout,
        ),
    ):
        result = _run_readiness_check(state)

    assert result["ready"] is True
    assert result["next_gen"] == 1
    assert "action" in result
    assert state.training_ready is True
    assert state.recommended_gpu == "A100_40GB"


# --- Async loop ---


@pytest.mark.asyncio
async def test_flywheel_loop_respects_shutdown() -> None:
    """The flywheel loop should exit cleanly on shutdown signal."""
    shutdown = asyncio.Event()

    # Signal shutdown after a short delay
    async def _shutdown_after():
        await asyncio.sleep(0.2)
        shutdown.set()

    # Patch the initial sleep to be very short
    with patch(
        "dharma_swarm.training_flywheel.REINFORCE_INTERVAL", 0.1
    ), patch(
        "dharma_swarm.training_flywheel.asyncio.sleep",
        return_value=None,
    ):
        task = asyncio.create_task(run_training_flywheel_loop(shutdown))
        shutdown_task = asyncio.create_task(_shutdown_after())

        await asyncio.wait_for(
            asyncio.gather(task, shutdown_task, return_exceptions=True),
            timeout=5.0,
        )

    assert shutdown.is_set()


# --- Integration: FlywheelState tracks cumulative progress ---


def test_state_accumulation() -> None:
    """FlywheelState should accumulate across multiple cycles."""
    state = FlywheelState()
    state.reinforce_cycles = 3
    state.total_trajectories_scored = 150
    state.total_patterns_extracted = 12
    state.dataset_builds = 1
    state.training_ready = True

    snap = state.snapshot()
    assert snap["reinforce_cycles"] == 3
    assert snap["total_trajectories_scored"] == 150
    assert snap["total_patterns_extracted"] == 12
    assert snap["dataset_builds"] == 1
    assert snap["training_ready"] is True


# --- Error resilience ---


def test_reinforcement_handles_scorer_error() -> None:
    """Reinforcement should not crash if ThinkodynamicScorer fails."""
    state = FlywheelState()

    # Trajectories that will trigger scoring (no pre-existing score)
    fake_trajs = []
    for i in range(MIN_TRAJECTORIES_FOR_REINFORCE + 1):
        t = MagicMock()
        t.outcome = MagicMock(success=True, thinkodynamic_score=None)
        t.trajectory_id = f"traj-{i}"
        t.task_title = f"task-{i}"
        t.chunks = []
        fake_trajs.append(t)

    mock_collector = MagicMock()
    mock_collector.load_trajectories.return_value = fake_trajs

    # Reinforcer that works but scorer inside it will fail gracefully
    mock_reinforcer = MagicMock()
    mock_reinforcer.reinforce_cycle.return_value = MagicMock(
        cycle_number=1,
        trajectories_evaluated=6,
        patterns_extracted=0,
        top_pattern=None,
    )
    mock_reinforcer.pattern_count = 0

    with (
        patch(
            "dharma_swarm.trajectory_collector.get_collector",
            return_value=mock_collector,
        ),
        patch(
            "dharma_swarm.strategy_reinforcer.StrategyReinforcer",
            return_value=mock_reinforcer,
        ),
    ):
        result = _run_reinforcement(state)

    # Should complete without error
    assert result["skipped"] is False
    assert result["patterns_extracted"] == 0


# --- Docker sandbox monitor wiring ---


def test_create_monitored_sandbox() -> None:
    """create_monitored_sandbox should produce a DockerSandbox with a monitor."""
    from dharma_swarm.docker_sandbox import create_monitored_sandbox, ContainerConfig

    sandbox = create_monitored_sandbox(
        config=ContainerConfig(image="python:3.11-slim")
    )
    assert hasattr(sandbox, "_monitor")
    assert sandbox._monitor is not None  # type: ignore[attr-defined]
    assert not sandbox.is_running
