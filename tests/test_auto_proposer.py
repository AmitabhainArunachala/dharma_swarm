"""Tests for dharma_swarm.auto_proposer -- AutoProposer autonomy loop."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.auto_proposer import (
    AutoProposer,
    CycleLog,
    Observation,
    ObservationType,
    ProposalRecord,
    ProposalSource,
    _DEFAULT_FITNESS_THRESHOLD,
    _MAX_PROPOSALS_PER_CYCLE,
    _MAX_PROPOSALS_PER_DAY,
)
from dharma_swarm.evolution import CycleResult, DarwinEngine, Proposal
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.monitor import (
    AgentHealth,
    Anomaly,
    HealthReport,
    HealthStatus,
    SystemMonitor,
)
from dharma_swarm.traces import TraceEntry, TraceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_health_report(
    *,
    mean_fitness: float | None = 0.7,
    failure_rate: float = 0.05,
    anomalies: list[Anomaly] | None = None,
    agent_health: list[AgentHealth] | None = None,
) -> HealthReport:
    return HealthReport(
        overall_status=HealthStatus.HEALTHY,
        mean_fitness=mean_fitness,
        failure_rate=failure_rate,
        anomalies=anomalies or [],
        agent_health=agent_health or [],
        total_traces=100,
        traces_last_hour=20,
    )


def _make_proposer(
    tmp_path: Path,
    *,
    health_report: HealthReport | None = None,
    stigmergy: MagicMock | None = None,
    predictor_should_attempt: bool = True,
) -> tuple[AutoProposer, MagicMock, MagicMock, FitnessPredictor]:
    """Build an AutoProposer with mocked dependencies."""
    # Mock DarwinEngine
    engine = MagicMock(spec=DarwinEngine)
    engine.propose = AsyncMock(
        side_effect=lambda **kw: Proposal(
            component=kw["component"],
            change_type=kw["change_type"],
            description=kw["description"],
            predicted_fitness=0.5,
        )
    )
    engine.run_cycle = AsyncMock(
        return_value=CycleResult(proposals_archived=1, best_fitness=0.6)
    )

    # Mock SystemMonitor
    monitor = MagicMock(spec=SystemMonitor)
    report = health_report or _make_health_report()
    monitor.check_health = AsyncMock(return_value=report)

    # Real FitnessPredictor (no history = neutral predictions)
    predictor = FitnessPredictor(history_path=tmp_path / "predictor.jsonl")

    proposer = AutoProposer(
        darwin_engine=engine,
        system_monitor=monitor,
        fitness_predictor=predictor,
        stigmergy=stigmergy,
        log_dir=tmp_path / "auto_proposer",
    )

    return proposer, engine, monitor, predictor


# ---------------------------------------------------------------------------
# Observation tests
# ---------------------------------------------------------------------------


class TestObservation:
    """Test observation collection from various sources."""

    def test_observe_fitness_drop(self, tmp_path):
        """Low mean fitness should produce a FITNESS_DROP observation."""
        report = _make_health_report(mean_fitness=0.2)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        fitness_obs = [o for o in observations if o.observation_type == ObservationType.FITNESS_DROP]
        assert len(fitness_obs) >= 1
        assert "0.200" in fitness_obs[0].description

    def test_observe_no_fitness_drop_when_healthy(self, tmp_path):
        """Normal fitness should not produce FITNESS_DROP."""
        report = _make_health_report(mean_fitness=0.8)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        fitness_obs = [o for o in observations if o.observation_type == ObservationType.FITNESS_DROP]
        assert len(fitness_obs) == 0

    def test_observe_no_fitness_drop_when_none(self, tmp_path):
        """None mean_fitness (no data) should not produce FITNESS_DROP."""
        report = _make_health_report(mean_fitness=None)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        fitness_obs = [o for o in observations if o.observation_type == ObservationType.FITNESS_DROP]
        assert len(fitness_obs) == 0

    def test_observe_failure_pattern_high_rate(self, tmp_path):
        """High failure rate should produce FAILURE_PATTERN observation."""
        report = _make_health_report(failure_rate=0.45)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        failure_obs = [o for o in observations if o.observation_type == ObservationType.FAILURE_PATTERN]
        assert len(failure_obs) >= 1

    def test_observe_failure_pattern_repeated_anomalies(self, tmp_path):
        """Repeated anomalies of same type should produce FAILURE_PATTERN."""
        anomalies = [
            Anomaly(anomaly_type="failure_spike", severity="high", description=f"spike {i}")
            for i in range(4)
        ]
        report = _make_health_report(anomalies=anomalies)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        failure_obs = [o for o in observations if o.observation_type == ObservationType.FAILURE_PATTERN]
        assert len(failure_obs) >= 1
        assert "failure_spike" in failure_obs[0].description

    def test_observe_stigmergy_hotspots(self, tmp_path):
        """Stigmergy hot paths should produce STIGMERGY_HOTSPOT observations."""
        stigmergy = MagicMock()
        stigmergy.hot_paths = AsyncMock(return_value=[
            ("dharma_swarm/swarm.py", 12),
            ("dharma_swarm/evolution.py", 8),
        ])

        proposer, _, _, _ = _make_proposer(tmp_path, stigmergy=stigmergy)

        observations = _run(proposer.observe())

        hotspot_obs = [o for o in observations if o.observation_type == ObservationType.STIGMERGY_HOTSPOT]
        assert len(hotspot_obs) == 2
        assert "swarm.py" in hotspot_obs[0].description

    def test_observe_no_hotspots_without_stigmergy(self, tmp_path):
        """Without stigmergy store, no STIGMERGY_HOTSPOT observations."""
        proposer, _, _, _ = _make_proposer(tmp_path, stigmergy=None)

        observations = _run(proposer.observe())

        hotspot_obs = [o for o in observations if o.observation_type == ObservationType.STIGMERGY_HOTSPOT]
        assert len(hotspot_obs) == 0

    def test_observe_provider_failures(self, tmp_path):
        """Critical agents should produce PROVIDER_FAILURE observation."""
        agents = [
            AgentHealth(
                agent_name="broken_agent",
                total_actions=10,
                failures=8,
                success_rate=0.2,
                status=HealthStatus.CRITICAL,
            ),
        ]
        report = _make_health_report(agent_health=agents)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        provider_obs = [o for o in observations if o.observation_type == ObservationType.PROVIDER_FAILURE]
        assert len(provider_obs) >= 1
        assert "broken_agent" in provider_obs[0].description

    def test_observe_stale_tasks(self, tmp_path):
        """Silent agents should produce STALE_TASKS observation."""
        anomalies = [
            Anomaly(anomaly_type="agent_silent", severity="medium", description="Agent X silent"),
        ]
        report = _make_health_report(anomalies=anomalies)
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        stale_obs = [o for o in observations if o.observation_type == ObservationType.STALE_TASKS]
        assert len(stale_obs) >= 1

    def test_observe_sorts_by_severity(self, tmp_path):
        """Observations should be sorted: high > medium > low."""
        anomalies = [
            Anomaly(anomaly_type="agent_silent", severity="medium", description="Silent"),
            Anomaly(anomaly_type="throughput_drop", severity="low", description="Drop"),
        ]
        report = _make_health_report(mean_fitness=0.1, anomalies=anomalies)  # high severity
        proposer, _, _, _ = _make_proposer(tmp_path, health_report=report)

        observations = _run(proposer.observe())

        if len(observations) >= 2:
            severities = [o.severity for o in observations]
            # High should come before medium/low
            high_idx = [i for i, s in enumerate(severities) if s == "high"]
            low_idx = [i for i, s in enumerate(severities) if s == "low"]
            if high_idx and low_idx:
                assert min(high_idx) < max(low_idx)

    def test_observe_resilient_to_monitor_failure(self, tmp_path):
        """If monitor.check_health() raises, observe should still return."""
        proposer, _, monitor, _ = _make_proposer(tmp_path)
        monitor.check_health = AsyncMock(side_effect=RuntimeError("connection lost"))

        # Should not raise
        observations = _run(proposer.observe())
        assert isinstance(observations, list)


# ---------------------------------------------------------------------------
# Proposal generation tests
# ---------------------------------------------------------------------------


class TestProposalGeneration:
    """Test proposal generation from observations."""

    def test_propose_from_fitness_drop(self, tmp_path):
        """FITNESS_DROP observation should produce a mutation proposal."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.FITNESS_DROP,
                severity="high",
                description="Mean fitness 0.200 below threshold 0.300",
                source_data={"mean_fitness": 0.2, "threshold": 0.3},
            ),
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) == 1
        engine.propose.assert_called_once()
        call_kwargs = engine.propose.call_args.kwargs
        assert call_kwargs["change_type"] == "mutation"
        assert "fitness" in call_kwargs["description"].lower()

    def test_propose_from_failure_pattern(self, tmp_path):
        """FAILURE_PATTERN observation should produce a proposal."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.FAILURE_PATTERN,
                severity="high",
                description="Anomaly failure_spike repeated 4 times",
                source_data={"anomaly_type": "failure_spike", "count": 4},
            ),
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) == 1

    def test_propose_from_hotspot(self, tmp_path):
        """STIGMERGY_HOTSPOT should produce a refactor proposal."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.STIGMERGY_HOTSPOT,
                severity="medium",
                description="File swarm.py has 15 marks",
                source_data={"file_path": "dharma_swarm/swarm.py", "mark_count": 15},
            ),
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) == 1
        call_kwargs = engine.propose.call_args.kwargs
        assert call_kwargs["component"] == "dharma_swarm/swarm.py"

    def test_propose_from_provider_failure(self, tmp_path):
        """PROVIDER_FAILURE should produce a rebalancing proposal."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.PROVIDER_FAILURE,
                severity="high",
                description="2 agents in CRITICAL state",
                source_data={"critical_agents": [{"name": "a", "success_rate": 0.1}]},
            ),
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) == 1
        call_kwargs = engine.propose.call_args.kwargs
        assert "providers" in call_kwargs["component"]

    def test_propose_from_stale_tasks(self, tmp_path):
        """STALE_TASKS should produce a recovery proposal."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.STALE_TASKS,
                severity="medium",
                description="3 agents gone silent",
                source_data={"silent_agents": ["a", "b", "c"]},
            ),
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) == 1
        call_kwargs = engine.propose.call_args.kwargs
        assert "orchestrator" in call_kwargs["component"]


# ---------------------------------------------------------------------------
# Throttling tests
# ---------------------------------------------------------------------------


class TestThrottling:
    """Test per-cycle and per-day throttling."""

    def test_max_per_cycle(self, tmp_path):
        """Should not exceed max_per_cycle proposals."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        # 10 observations, but max_per_cycle defaults to 3
        observations = [
            Observation(
                observation_type=ObservationType.FITNESS_DROP,
                severity="high",
                description=f"Drop {i}",
                source_data={"mean_fitness": 0.1, "threshold": 0.3},
            )
            for i in range(10)
        ]

        proposals = _run(proposer.propose(observations))

        assert len(proposals) <= _MAX_PROPOSALS_PER_CYCLE

    def test_max_per_day(self, tmp_path):
        """Should not exceed max_per_day across multiple cycles."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.FITNESS_DROP,
                severity="high",
                description="Drop",
                source_data={"mean_fitness": 0.1, "threshold": 0.3},
            )
            for _ in range(3)
        ]

        # Run enough cycles to hit daily limit
        total_proposals = 0
        for _ in range(10):
            batch = _run(proposer.propose(observations))
            total_proposals += len(batch)

        assert total_proposals <= _MAX_PROPOSALS_PER_DAY

    def test_daily_count_tracks(self, tmp_path):
        """daily_count should accurately reflect proposals generated."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        assert proposer.daily_count == 0

        observations = [
            Observation(
                observation_type=ObservationType.FITNESS_DROP,
                severity="high",
                description="Drop",
                source_data={"mean_fitness": 0.1, "threshold": 0.3},
            ),
        ]

        _run(proposer.propose(observations))
        assert proposer.daily_count == 1

    def test_daily_remaining_decrements(self, tmp_path):
        """daily_remaining should decrease as proposals are generated."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        initial = proposer.daily_remaining
        assert initial == _MAX_PROPOSALS_PER_DAY

        observations = [
            Observation(
                observation_type=ObservationType.FITNESS_DROP,
                severity="high",
                description="Drop",
                source_data={"mean_fitness": 0.1, "threshold": 0.3},
            ),
        ]

        _run(proposer.propose(observations))
        assert proposer.daily_remaining == initial - 1


# ---------------------------------------------------------------------------
# Full cycle tests
# ---------------------------------------------------------------------------


class TestCycle:
    """Test the full observe -> propose -> submit cycle."""

    def test_cycle_healthy_system(self, tmp_path):
        """Healthy system should produce no proposals."""
        report = _make_health_report(mean_fitness=0.8, failure_rate=0.02)
        proposer, engine, _, _ = _make_proposer(tmp_path, health_report=report)

        cycle_log = _run(proposer.cycle())

        assert cycle_log.observations_collected == 0
        assert cycle_log.proposals_generated == 0
        assert cycle_log.proposals_submitted == 0
        engine.run_cycle.assert_not_called()

    def test_cycle_unhealthy_system(self, tmp_path):
        """Unhealthy system should produce and submit proposals."""
        report = _make_health_report(mean_fitness=0.15, failure_rate=0.4)
        proposer, engine, _, _ = _make_proposer(tmp_path, health_report=report)

        cycle_log = _run(proposer.cycle())

        assert cycle_log.observations_collected > 0
        assert cycle_log.proposals_generated > 0
        engine.run_cycle.assert_called_once()

    def test_cycle_logs_to_files(self, tmp_path):
        """Cycle should produce JSONL log files."""
        report = _make_health_report(mean_fitness=0.15)
        proposer, engine, _, _ = _make_proposer(tmp_path, health_report=report)

        _run(proposer.cycle())

        log_dir = tmp_path / "auto_proposer"
        assert log_dir.exists()
        # Check that at least the cycles log exists
        assert (log_dir / "cycles.jsonl").exists()

    def test_cycle_resilient_to_engine_failure(self, tmp_path):
        """If DarwinEngine.run_cycle fails, cycle should still complete."""
        report = _make_health_report(mean_fitness=0.15)
        proposer, engine, _, _ = _make_proposer(tmp_path, health_report=report)
        engine.run_cycle = AsyncMock(side_effect=RuntimeError("engine exploded"))

        cycle_log = _run(proposer.cycle())

        assert len(cycle_log.errors) >= 1
        assert "submit failed" in cycle_log.errors[0]

    def test_cycle_returns_cycle_log(self, tmp_path):
        """cycle() should always return a CycleLog, even on failure."""
        proposer, engine, monitor, _ = _make_proposer(tmp_path)
        monitor.check_health = AsyncMock(side_effect=RuntimeError("monitor down"))

        cycle_log = _run(proposer.cycle())

        assert isinstance(cycle_log, CycleLog)


# ---------------------------------------------------------------------------
# Gate integration tests
# ---------------------------------------------------------------------------


class TestGateIntegration:
    """Test that proposals go through the Darwin Engine's gate pipeline."""

    def test_proposals_submitted_via_run_cycle(self, tmp_path):
        """Proposals should be submitted via engine.run_cycle which includes gate_check."""
        report = _make_health_report(mean_fitness=0.1)
        proposer, engine, _, _ = _make_proposer(tmp_path, health_report=report)

        _run(proposer.cycle())

        # run_cycle internally calls gate_check for each proposal
        engine.run_cycle.assert_called_once()
        submitted_proposals = engine.run_cycle.call_args[0][0]
        assert len(submitted_proposals) > 0
        assert all(isinstance(p, Proposal) for p in submitted_proposals)

    def test_engine_propose_called_with_correct_params(self, tmp_path):
        """Engine.propose should receive proper component and change_type."""
        proposer, engine, _, _ = _make_proposer(tmp_path)

        observations = [
            Observation(
                observation_type=ObservationType.PROVIDER_FAILURE,
                severity="high",
                description="Agent X critical",
                source_data={"critical_agents": [{"name": "x", "success_rate": 0.1}]},
            ),
        ]

        _run(proposer.propose(observations))

        call_kwargs = engine.propose.call_args.kwargs
        assert "component" in call_kwargs
        assert "change_type" in call_kwargs
        assert "description" in call_kwargs


# ---------------------------------------------------------------------------
# Status and introspection tests
# ---------------------------------------------------------------------------


class TestStatus:
    """Test the status() introspection method."""

    def test_status_returns_expected_fields(self, tmp_path):
        """status() should include all configuration fields."""
        proposer, _, _, _ = _make_proposer(tmp_path)
        st = proposer.status()

        assert "daily_count" in st
        assert "daily_remaining" in st
        assert "max_per_cycle" in st
        assert "max_per_day" in st
        assert "fitness_threshold" in st
        assert "has_stigmergy" in st
        assert "log_dir" in st

    def test_status_reflects_stigmergy_presence(self, tmp_path):
        """has_stigmergy should reflect whether a stigmergy store is wired."""
        proposer_no, _, _, _ = _make_proposer(tmp_path, stigmergy=None)
        assert proposer_no.status()["has_stigmergy"] is False

        stigmergy = MagicMock()
        stigmergy.hot_paths = AsyncMock(return_value=[])
        proposer_yes, _, _, _ = _make_proposer(tmp_path, stigmergy=stigmergy)
        assert proposer_yes.status()["has_stigmergy"] is True


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    """Test the Pydantic data models."""

    def test_observation_serialization(self):
        obs = Observation(
            observation_type=ObservationType.FITNESS_DROP,
            severity="high",
            description="test",
        )
        data = obs.model_dump_json()
        restored = Observation.model_validate_json(data)
        assert restored.observation_type == ObservationType.FITNESS_DROP
        assert restored.severity == "high"

    def test_proposal_record_serialization(self):
        rec = ProposalRecord(
            observation_id="abc123",
            observation_type="fitness_drop",
            component="test.py",
            change_type="mutation",
            description="test proposal",
            source=ProposalSource.AUTO_FITNESS,
        )
        data = rec.model_dump_json()
        restored = ProposalRecord.model_validate_json(data)
        assert restored.source == ProposalSource.AUTO_FITNESS

    def test_cycle_log_serialization(self):
        log = CycleLog(
            observations_collected=5,
            proposals_generated=2,
            proposals_submitted=1,
        )
        data = log.model_dump_json()
        restored = CycleLog.model_validate_json(data)
        assert restored.observations_collected == 5
        assert restored.proposals_submitted == 1
