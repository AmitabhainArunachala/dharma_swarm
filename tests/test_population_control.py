"""Tests for PopulationController -- caps, culling, apoptosis, probation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.population_control import (
    ApoptosisResult,
    PROTECTED_AGENTS,
    PopulationAssessment,
    PopulationController,
    ProbationStatus,
)


# ---------------------------------------------------------------------------
# Population assessment
# ---------------------------------------------------------------------------


class TestCanAddAgent:
    def test_can_add_below_cap(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, max_population=8)
        agents = ["operator", "witness", "archivist", "research_director", "systems_architect", "strategist"]
        result = ctrl.can_add_agent(agents)
        assert result.can_add is True
        assert result.cull_candidate is None
        assert result.current_population == 6

    def test_can_add_at_cap_with_cull(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, max_population=8)
        agents = [
            "operator", "witness", "archivist", "research_director",
            "systems_architect", "strategist", "dynamic_a", "dynamic_b",
        ]
        # Provide a fitness function where dynamic_b is very low fitness
        fitness_fn = lambda name: 0.1 if name == "dynamic_b" else 0.8
        result = ctrl.can_add_agent(agents, fitness_fn=fitness_fn)
        assert result.can_add is True
        assert result.cull_candidate == "dynamic_b"
        assert result.cull_fitness is not None
        assert result.cull_fitness < 0.4

    def test_can_add_at_cap_all_healthy(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, max_population=8)
        agents = [
            "operator", "witness", "archivist", "research_director",
            "systems_architect", "strategist", "dynamic_a", "dynamic_b",
        ]
        fitness_fn = lambda name: 0.9  # All healthy
        result = ctrl.can_add_agent(agents, fitness_fn=fitness_fn)
        assert result.can_add is False
        assert result.cull_candidate is None

    def test_protected_agents_never_culled(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, max_population=3)
        agents = ["operator", "witness", "dynamic_a"]
        # operator and witness have lowest fitness, but are protected
        fitness_fn = lambda name: 0.01 if name in PROTECTED_AGENTS else 0.8
        result = ctrl.can_add_agent(agents, fitness_fn=fitness_fn)
        # dynamic_a is healthy (0.8 >= 0.4), so no cull candidate
        assert result.can_add is False


# ---------------------------------------------------------------------------
# Apoptosis
# ---------------------------------------------------------------------------


class TestApoptosis:
    def test_apoptosis_triggers(self, tmp_path: Path) -> None:
        ctrl = PopulationController(
            state_dir=tmp_path,
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        # 5 consecutive scores below 0.2
        scores = [0.1, 0.15, 0.05, 0.19, 0.1]
        assert ctrl.check_apoptosis("dynamic_a", scores) is True

    def test_apoptosis_not_enough_cycles(self, tmp_path: Path) -> None:
        ctrl = PopulationController(
            state_dir=tmp_path,
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        # Only 3 scores (below required 5)
        scores = [0.1, 0.1, 0.1]
        assert ctrl.check_apoptosis("dynamic_a", scores) is False

    def test_apoptosis_protected(self, tmp_path: Path) -> None:
        ctrl = PopulationController(
            state_dir=tmp_path,
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        scores = [0.01] * 10
        assert ctrl.check_apoptosis("operator", scores) is False
        assert ctrl.check_apoptosis("witness", scores) is False

    def test_apoptosis_mixed_scores(self, tmp_path: Path) -> None:
        """One good score in the last N breaks the apoptosis trigger."""
        ctrl = PopulationController(
            state_dir=tmp_path,
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        scores = [0.1, 0.1, 0.5, 0.1, 0.1]  # 3rd score above threshold
        assert ctrl.check_apoptosis("dynamic_a", scores) is False

    def test_execute_apoptosis(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path)
        # Create some fake agent memory to archive
        mem_dir = tmp_path / "agent_memory" / "doomed_agent"
        mem_dir.mkdir(parents=True)
        (mem_dir / "working.json").write_text("{}")

        result = ctrl.execute_apoptosis(
            agent_name="doomed_agent",
            reason="Sustained low fitness",
            fitness_history=[0.1, 0.05, 0.15, 0.08],
        )
        assert isinstance(result, ApoptosisResult)
        assert result.agent_name == "doomed_agent"
        assert "doomed_agent" in result.memory_archived_to

        # Archive directory should exist with memory copied
        archive_path = tmp_path / "archive" / "doomed_agent" / "memory"
        assert archive_path.exists()

        # Apoptosis log should have an entry
        log_path = tmp_path / "replication" / "apoptosis.jsonl"
        assert log_path.exists()
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 1
        assert entries[0]["agent_name"] == "doomed_agent"

    def test_execute_apoptosis_protected_raises(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Cannot apoptose protected agent"):
            ctrl.execute_apoptosis(
                agent_name="operator",
                reason="should not work",
                fitness_history=[],
            )


# ---------------------------------------------------------------------------
# Probation
# ---------------------------------------------------------------------------


class TestProbation:
    def test_start_probation(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, probation_cycles=10)
        status = ctrl.start_probation("new_agent", start_cycle=0)
        assert isinstance(status, ProbationStatus)
        assert status.agent_name == "new_agent"
        assert status.required_cycles == 10
        assert status.graduated is False
        assert status.terminated is False
        assert ctrl.is_in_probation("new_agent") is True

    def test_probation_graduation(self, tmp_path: Path) -> None:
        ctrl = PopulationController(
            state_dir=tmp_path,
            probation_cycles=3,
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        ctrl.start_probation("grad_agent", start_cycle=0)
        # Simulate 3 healthy cycles
        for cycle in range(1, 4):
            status = ctrl.update_probation("grad_agent", cycle=cycle, fitness=0.8)
        assert status.graduated is True
        assert status.terminated is False
        assert ctrl.is_in_probation("grad_agent") is False  # is_complete = True

    def test_probation_termination(self, tmp_path: Path) -> None:
        ctrl = PopulationController(
            state_dir=tmp_path,
            probation_cycles=20,  # Long enough to not graduate
            apoptosis_fitness_threshold=0.2,
            apoptosis_cycle_count=5,
        )
        ctrl.start_probation("bad_agent", start_cycle=0)
        # Simulate 5 low-fitness cycles (enough to trigger apoptosis)
        for cycle in range(1, 6):
            status = ctrl.update_probation("bad_agent", cycle=cycle, fitness=0.05)
        assert status.terminated is True
        assert status.graduated is False

    def test_probation_persistence(self, tmp_path: Path) -> None:
        ctrl1 = PopulationController(state_dir=tmp_path, probation_cycles=10)
        ctrl1.start_probation("persistent_agent", start_cycle=0)
        # New controller from same directory should find the probation
        ctrl2 = PopulationController(state_dir=tmp_path, probation_cycles=10)
        status = ctrl2.get_probation_status("persistent_agent")
        assert status is not None
        assert status.agent_name == "persistent_agent"
        assert status.required_cycles == 10


# ---------------------------------------------------------------------------
# Resource budget
# ---------------------------------------------------------------------------


class TestResourceBudget:
    def test_resource_budget_ok(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, daily_token_budget=500_000)
        ok, reason = ctrl.check_resource_budget(current_daily_tokens=100_000)
        assert ok is True
        assert "OK" in reason

    def test_resource_budget_exceeded(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, daily_token_budget=500_000)
        ok, reason = ctrl.check_resource_budget(current_daily_tokens=500_000)
        assert ok is False
        assert "exhausted" in reason

    def test_resource_budget_nearly_exhausted(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, daily_token_budget=500_000)
        ok, reason = ctrl.check_resource_budget(current_daily_tokens=499_000)
        assert ok is False
        assert "nearly exhausted" in reason


# ---------------------------------------------------------------------------
# Health report
# ---------------------------------------------------------------------------


class TestHealthReport:
    def test_health_report_structure(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path, max_population=8)
        agents = ["operator", "witness", "archivist"]
        report = ctrl.health_report(agents)
        assert report["total_population"] == 3
        assert report["max_population"] == 8
        assert report["headroom"] == 5
        assert "operator" in report["protected"]
        assert "witness" in report["protected"]

    def test_health_report_with_fitness(self, tmp_path: Path) -> None:
        ctrl = PopulationController(state_dir=tmp_path)
        agents = ["operator", "witness"]
        fitness_fn = lambda name: 0.75
        report = ctrl.health_report(agents, fitness_fn=fitness_fn)
        assert "fitness_map" in report
        assert report["mean_fitness"] == 0.75
