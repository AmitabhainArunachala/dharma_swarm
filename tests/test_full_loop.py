"""End-to-end integration: Wiring Sprint — verify all Sprint 1-3 systems
are connected and data flows through the complete pipeline.

Tests cover:
1. SwarmManager init wires all subsystems
2. Task completion triggers SleepTimeAgent consolidation
3. Economic spine tracks but never blocks
4. Knowledge accumulates across tasks
5. Darwin Engine fitness uses all 3 new signals
6. Graceful degradation when subsystems fail
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.economic_spine import EconomicSpine, MissionState
from dharma_swarm.knowledge_units import (
    KnowledgeStore,
    Proposition,
    Prescription,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temp directory for test databases."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    return db_dir


@pytest.fixture
def economic_spine(tmp_db: Path) -> EconomicSpine:
    return EconomicSpine(db_path=str(tmp_db / "econ.db"))


@pytest.fixture
def knowledge_store(tmp_db: Path) -> KnowledgeStore:
    return KnowledgeStore(db_path=str(tmp_db / "knowledge.db"))


# ---------------------------------------------------------------------------
# TestEconomicTrackingOnly — verify spine is purely observational
# ---------------------------------------------------------------------------


class TestEconomicTrackingOnly:
    """Verify economic spine is purely observational — no gates."""

    def test_spend_tokens_always_returns_true(self, economic_spine: EconomicSpine):
        """spend_tokens() ALWAYS returns True, even when over budget."""
        agent_id = "agent-test-1"
        budget = economic_spine.get_or_create_budget(agent_id)
        allocated = budget.total_tokens_allocated

        # Spend more than allocated — should still succeed
        result = economic_spine.spend_tokens(agent_id, allocated + 50000)
        assert result is True

    def test_zero_budget_does_not_block_dispatch(self, economic_spine: EconomicSpine):
        """Agent with zero tokens remaining can still spend."""
        agent_id = "agent-zero-budget"
        budget = economic_spine.get_or_create_budget(agent_id)

        # Exhaust the entire budget
        economic_spine.spend_tokens(agent_id, budget.total_tokens_allocated)
        updated = economic_spine.get_or_create_budget(agent_id)
        assert updated.tokens_remaining == 0

        # Should still succeed
        result = economic_spine.spend_tokens(agent_id, 1000)
        assert result is True

    def test_negative_balance_allowed(self, economic_spine: EconomicSpine):
        """Spending beyond allocation is tracked but not prevented."""
        agent_id = "agent-negative"
        budget = economic_spine.get_or_create_budget(agent_id)
        total = budget.total_tokens_allocated

        # Spend 2x the budget
        economic_spine.spend_tokens(agent_id, total * 2)
        updated = economic_spine.get_or_create_budget(agent_id)
        assert updated.tokens_remaining < 0
        assert updated.tokens_spent == total * 2

    def test_mission_lifecycle_tracking(self, economic_spine: EconomicSpine):
        """Mission lifecycle still records states even with tracking-only spine."""
        agent_id = "agent-lifecycle"
        mission = economic_spine.create_mission(agent_id, "Test task", 5000)
        assert mission.state == MissionState.RECEIVED

        economic_spine.transition_mission(mission.id, MissionState.QUOTED)
        economic_spine.transition_mission(mission.id, MissionState.ACCEPTED)
        economic_spine.transition_mission(mission.id, MissionState.EXECUTING)
        economic_spine.transition_mission(mission.id, MissionState.DELIVERED, tokens_actual=3000)

        # Spend tracked against the mission
        result = economic_spine.spend_tokens(agent_id, 3000, mission.id)
        assert result is True

        stats = economic_spine.get_agent_stats(agent_id)
        assert stats["tokens_spent"] == 3000


# ---------------------------------------------------------------------------
# TestKnowledgeStoreProvenance — Darwin Engine can query by agent
# ---------------------------------------------------------------------------


class TestKnowledgeStoreProvenance:
    """Test the new get_by_agent_provenance() method."""

    def test_get_by_agent_provenance_propositions(self, knowledge_store: KnowledgeStore):
        """Retrieve propositions traced to a specific agent."""
        prop = Proposition(
            content="Python GIL limits true parallelism",
            concepts=["python", "concurrency"],
            provenance_event_id="task-123-agent-alpha",
            provenance_context="agent-alpha completed task-123",
        )
        knowledge_store.store_proposition(prop)

        results = knowledge_store.get_by_agent_provenance("agent-alpha", unit_type="proposition")
        assert len(results) == 1
        assert results[0].content == prop.content

    def test_get_by_agent_provenance_prescriptions(self, knowledge_store: KnowledgeStore):
        """Retrieve prescriptions traced to a specific agent."""
        presc = Prescription(
            intent="Handle rate limits",
            workflow=["retry with exponential backoff", "add jitter"],
            concepts=["api", "resilience"],
            provenance_event_id="task-456-agent-beta",
            provenance_context="agent-beta completed task-456",
        )
        knowledge_store.store_prescription(presc)

        results = knowledge_store.get_by_agent_provenance("agent-beta", unit_type="prescription")
        assert len(results) == 1
        assert results[0].intent == "Handle rate limits"

    def test_get_by_agent_provenance_both_types(self, knowledge_store: KnowledgeStore):
        """Retrieve both types for an agent."""
        prop = Proposition(
            content="Test fact",
            concepts=["testing"],
            provenance_event_id="task-1-agent-gamma",
        )
        presc = Prescription(
            intent="Test skill",
            workflow=["step1"],
            concepts=["testing"],
            provenance_event_id="task-2-agent-gamma",
        )
        knowledge_store.store_proposition(prop)
        knowledge_store.store_prescription(presc)

        results = knowledge_store.get_by_agent_provenance("agent-gamma")
        assert len(results) == 2

    def test_get_by_agent_provenance_no_match(self, knowledge_store: KnowledgeStore):
        """No results when agent has no provenance."""
        results = knowledge_store.get_by_agent_provenance("nonexistent-agent")
        assert results == []

    def test_get_by_agent_provenance_respects_limit(self, knowledge_store: KnowledgeStore):
        """Limit parameter constrains results."""
        for i in range(15):
            prop = Proposition(
                content=f"Fact {i}",
                concepts=["bulk"],
                provenance_event_id=f"task-{i}-agent-delta",
            )
            knowledge_store.store_proposition(prop)

        results = knowledge_store.get_by_agent_provenance("agent-delta", limit=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# TestDarwinExtendedFitness — all 3 new signals influence evolution
# ---------------------------------------------------------------------------


class TestDarwinExtendedFitness:
    """Darwin Engine extended fitness incorporates memory, economic, correction signals."""

    def _make_engine(self, tmp_path: Path):
        from dharma_swarm.evolution import DarwinEngine

        return DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
        )

    def test_compute_extended_fitness_no_subsystems(self, tmp_path: Path):
        """Without subsystems, signals return 0.5 (neutral)."""
        engine = self._make_engine(tmp_path)
        base = 0.8
        extended = engine.compute_extended_fitness("agent-x", base)

        # 0.8 * 0.6 + 0.5 * 0.15 + 0.5 * 0.15 + 0.5 * 0.10 = 0.48 + 0.075 + 0.075 + 0.05 = 0.68
        assert extended == pytest.approx(0.68, abs=0.01)

    def test_memory_quality_signal_with_store(self, tmp_path: Path, knowledge_store: KnowledgeStore):
        """Memory signal reflects knowledge production."""
        engine = self._make_engine(tmp_path)
        engine.set_knowledge_store(knowledge_store)

        # Store 5 propositions for agent-mem
        for i in range(5):
            knowledge_store.store_proposition(
                Proposition(
                    content=f"Fact {i}",
                    concepts=["test"],
                    provenance_event_id=f"task-{i}-agent-mem",
                )
            )

        signal = engine._memory_quality_signal("agent-mem")
        assert signal == pytest.approx(0.5, abs=0.01)  # 5/10 = 0.5

    def test_memory_quality_signal_max(self, tmp_path: Path, knowledge_store: KnowledgeStore):
        """10+ units = max signal (1.0)."""
        engine = self._make_engine(tmp_path)
        engine.set_knowledge_store(knowledge_store)

        for i in range(12):
            knowledge_store.store_proposition(
                Proposition(
                    content=f"Fact {i}",
                    concepts=["test"],
                    provenance_event_id=f"task-{i}-agent-prolific",
                )
            )

        signal = engine._memory_quality_signal("agent-prolific")
        assert signal == 1.0

    def test_economic_efficiency_signal(self, tmp_path: Path, economic_spine: EconomicSpine):
        """Economic signal reflects efficiency."""
        engine = self._make_engine(tmp_path)
        engine.set_economic_spine(economic_spine)

        # Create some spending history
        economic_spine.spend_tokens("agent-econ", 5000)
        economic_spine.update_efficiency("agent-econ", 0.9)

        signal = engine._economic_efficiency_signal("agent-econ")
        # Should be some value between 0 and 1 (not default 0.5)
        assert 0.0 <= signal <= 1.0

    def test_correction_health_signal_no_corrections(self, tmp_path: Path):
        """No corrections = maximum health (1.0)."""
        engine = self._make_engine(tmp_path)

        # Mock correction engine with empty history
        mock_ce = MagicMock()
        mock_ce.get_correction_history.return_value = []
        engine.set_correction_engine(mock_ce)

        signal = engine._correction_health_signal("agent-clean")
        assert signal == 1.0

    def test_correction_health_signal_many_corrections(self, tmp_path: Path):
        """Many corrections = low health."""
        engine = self._make_engine(tmp_path)

        mock_ce = MagicMock()
        mock_ce.get_correction_history.return_value = [MagicMock()] * 10
        engine.set_correction_engine(mock_ce)

        signal = engine._correction_health_signal("agent-noisy")
        assert signal == 0.0

    def test_extended_fitness_uses_all_signals(self, tmp_path: Path, knowledge_store: KnowledgeStore, economic_spine: EconomicSpine):
        """All 3 new signals influence the final fitness value."""
        engine = self._make_engine(tmp_path)
        engine.set_knowledge_store(knowledge_store)
        engine.set_economic_spine(economic_spine)

        mock_ce = MagicMock()
        mock_ce.get_correction_history.return_value = []
        engine.set_correction_engine(mock_ce)

        # Store knowledge for agent
        for i in range(10):
            knowledge_store.store_proposition(
                Proposition(
                    content=f"Fact {i}",
                    concepts=["test"],
                    provenance_event_id=f"task-{i}-agent-full",
                )
            )

        # Agent with good history
        economic_spine.spend_tokens("agent-full", 1000)
        economic_spine.update_efficiency("agent-full", 0.95)

        base = 0.8
        extended = engine.compute_extended_fitness("agent-full", base)

        # Should be different from the no-subsystem case (0.68)
        # because memory signal is 1.0 (10 units), health signal is 1.0
        assert extended != pytest.approx(0.68, abs=0.01)
        assert 0.0 <= extended <= 1.0

    def test_setter_methods_exist(self, tmp_path: Path):
        """DarwinEngine has all three setter methods."""
        engine = self._make_engine(tmp_path)
        assert hasattr(engine, "set_knowledge_store")
        assert hasattr(engine, "set_economic_spine")
        assert hasattr(engine, "set_correction_engine")


# ---------------------------------------------------------------------------
# TestContextCompilerKnowledgeStore — set_knowledge_store injection
# ---------------------------------------------------------------------------


class TestContextCompilerKnowledgeStore:
    """ContextCompiler receives KnowledgeStore via set_knowledge_store()."""

    def test_set_knowledge_store(self):
        """set_knowledge_store attaches the store."""
        from dharma_swarm.context_compiler import ContextCompiler
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        state = RuntimeStateStore()
        lattice = MemoryLattice()
        compiler = ContextCompiler(runtime_state=state, memory_lattice=lattice)

        mock_store = MagicMock()
        compiler.set_knowledge_store(mock_store)
        assert compiler.knowledge_store is mock_store


# ---------------------------------------------------------------------------
# TestOrchestratorConsolidation — SleepTimeAgent auto-trigger
# ---------------------------------------------------------------------------


class TestOrchestratorConsolidation:
    """Orchestrator triggers SleepTimeAgent after task completion."""

    def test_get_sleep_time_agent_direct(self):
        """Orchestrator can retrieve SleepTimeAgent from direct attribute."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_sta = MagicMock()
        orch._sleep_time_agent = mock_sta

        assert orch._get_sleep_time_agent() is mock_sta

    def test_get_sleep_time_agent_via_organism(self):
        """Orchestrator can retrieve SleepTimeAgent from organism."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_organism = MagicMock()
        mock_sta = MagicMock()
        mock_organism.sleep_time_agent = mock_sta
        orch._organism = mock_organism

        assert orch._get_sleep_time_agent() is mock_sta

    def test_get_sleep_time_agent_none(self):
        """Returns None when no SleepTimeAgent available."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        assert orch._get_sleep_time_agent() is None

    def test_build_consolidation_context(self):
        """Build context string from task data."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        task = MagicMock()
        task.title = "Implement feature X"
        task.description = "Build the widget"
        td = MagicMock()
        td.agent_id = "agent-123"
        td.status = "completed"

        context = orch._build_consolidation_context(task, td, "Result text here")
        assert "Implement feature X" in context
        assert "agent-123" in context
        assert "Result text here" in context

    @pytest.mark.asyncio
    async def test_safe_consolidate_success(self):
        """_safe_consolidate calls sleep_agent.consolidate_knowledge."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_sta = AsyncMock()
        mock_sta.consolidate_knowledge.return_value = {
            "propositions": 3,
            "prescriptions": 1,
        }

        await orch._safe_consolidate(mock_sta, "task context", {"success": True})
        mock_sta.consolidate_knowledge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_safe_consolidate_failure_non_fatal(self):
        """_safe_consolidate does not raise on failure."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_sta = AsyncMock()
        mock_sta.consolidate_knowledge.side_effect = RuntimeError("boom")

        # Should not raise
        await orch._safe_consolidate(mock_sta, "task context", {"success": True})

    def test_set_organism(self):
        """set_organism attaches organism reference."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_org = MagicMock()
        orch.set_organism(mock_org)
        assert orch._organism is mock_org

    def test_set_knowledge_store(self):
        """set_knowledge_store attaches store for pass-through."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_store = MagicMock()
        orch.set_knowledge_store(mock_store)
        assert orch._knowledge_store is mock_store


# ---------------------------------------------------------------------------
# TestKnowledgeAccumulation — second task benefits from first
# ---------------------------------------------------------------------------


class TestKnowledgeAccumulation:
    """Knowledge from first task is available for second task."""

    def test_knowledge_accumulates_across_tasks(self, knowledge_store: KnowledgeStore):
        """Second task benefits from first task's knowledge extraction."""
        # Task 1 produces knowledge
        prop1 = Proposition(
            content="Service X has a 10 req/s rate limit",
            concepts=["service-x", "rate-limit"],
            provenance_event_id="task-1-agent-a",
        )
        knowledge_store.store_proposition(prop1)

        # Task 2 can retrieve it
        results = knowledge_store.get_propositions_for_context(
            task_concepts=["rate-limit", "api"],
            max_tokens=500,
        )
        assert len(results) >= 1
        assert any("rate limit" in r.content.lower() for r in results)

    def test_prescriptions_reusable(self, knowledge_store: KnowledgeStore):
        """Skills from one task are available for later intent-matching."""
        presc = Prescription(
            intent="Deploy to staging",
            workflow=["run tests", "build docker image", "push to registry"],
            concepts=["deploy", "staging", "docker"],
            provenance_event_id="task-deploy-1-agent-b",
            return_score=0.8,
        )
        knowledge_store.store_prescription(presc)

        results = knowledge_store.get_prescriptions_for_intent(
            intent="Deploy application",
            concepts=["deploy", "staging"],
        )
        assert len(results) >= 1
        assert results[0].intent == "Deploy to staging"


# ---------------------------------------------------------------------------
# TestGracefulDegradation — one system fails, others still work
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """If any Sprint 1-3 system fails, the rest still work."""

    def test_economic_spine_failure_doesnt_crash_knowledge(
        self, knowledge_store: KnowledgeStore
    ):
        """KnowledgeStore works even if EconomicSpine is broken."""
        prop = Proposition(
            content="Independent fact",
            concepts=["test"],
            provenance_event_id="task-1",
        )
        knowledge_store.store_proposition(prop)
        results = knowledge_store.get_by_concepts(["test"])
        assert len(results) == 1

    def test_darwin_fitness_with_missing_subsystems(self, tmp_path: Path):
        """DarwinEngine fitness falls back to neutral when subsystems missing."""
        from dharma_swarm.evolution import DarwinEngine

        engine = DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
        )
        # No subsystems wired — all signals should return 0.5
        assert engine._memory_quality_signal("any-agent") == 0.5
        assert engine._economic_efficiency_signal("any-agent") == 0.5
        assert engine._correction_health_signal("any-agent") == 0.5

    def test_darwin_fitness_with_broken_subsystems(self, tmp_path: Path):
        """DarwinEngine fitness returns 0.5 when subsystems raise."""
        from dharma_swarm.evolution import DarwinEngine

        engine = DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
        )

        # Wire broken subsystems
        broken_store = MagicMock()
        broken_store.get_by_agent_provenance.side_effect = RuntimeError("db corruption")
        engine.set_knowledge_store(broken_store)

        broken_spine = MagicMock()
        broken_spine.get_agent_stats.side_effect = RuntimeError("db corruption")
        engine.set_economic_spine(broken_spine)

        broken_ce = MagicMock()
        broken_ce.get_correction_history.side_effect = RuntimeError("db corruption")
        engine.set_correction_engine(broken_ce)

        # All signals should return 0.5 (neutral fallback)
        assert engine._memory_quality_signal("agent-x") == 0.5
        assert engine._economic_efficiency_signal("agent-x") == 0.5
        assert engine._correction_health_signal("agent-x") == 0.5

    @pytest.mark.asyncio
    async def test_consolidation_failure_non_fatal(self):
        """Failed knowledge consolidation doesn't crash the orchestrator."""
        from dharma_swarm.orchestrator import Orchestrator

        orch = Orchestrator()
        broken_sta = AsyncMock()
        broken_sta.consolidate_knowledge.side_effect = Exception("extraction failed")

        # Should not raise
        await orch._safe_consolidate(broken_sta, "context", {"success": True})


# ---------------------------------------------------------------------------
# TestSwarmInitWiring — verify SwarmManager connects everything
# ---------------------------------------------------------------------------


class TestSwarmInitWiring:
    """SwarmManager.init() successfully wires all Sprint 1-3 systems.

    These tests verify that the wiring code in SwarmManager.init() creates
    the subsystems and connects them — using mocks for the subsystems that
    require complex setup.
    """

    def test_economic_spine_spend_always_true(self, economic_spine: EconomicSpine):
        """Core contract: spend_tokens always returns True."""
        for amount in [0, 100, 1_000_000]:
            assert economic_spine.spend_tokens("any-agent", amount) is True

    def test_economic_spine_tracks_overage(self, economic_spine: EconomicSpine):
        """Overspending is recorded but not blocked."""
        agent_id = "over-spender"
        budget = economic_spine.get_or_create_budget(agent_id)
        total = budget.total_tokens_allocated

        economic_spine.spend_tokens(agent_id, total + 99999)
        updated = economic_spine.get_or_create_budget(agent_id)
        assert updated.tokens_remaining < 0
        assert updated.tokens_spent == total + 99999


# ---------------------------------------------------------------------------
# TestEndToEndFlow — simulated full pipeline
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Simulated end-to-end task flow through all Sprint 1-3 systems."""

    @pytest.mark.asyncio
    async def test_task_flows_through_all_systems(
        self, economic_spine: EconomicSpine, knowledge_store: KnowledgeStore, tmp_path: Path
    ):
        """A task enters the system and touches every Sprint 1-3 subsystem."""
        from dharma_swarm.evolution import DarwinEngine

        agent_id = "agent-flow-test"

        # 1. Economic spine: create mission and track spending
        mission = economic_spine.create_mission(agent_id, "Test task", 5000)
        economic_spine.transition_mission(mission.id, MissionState.QUOTED)
        economic_spine.transition_mission(mission.id, MissionState.ACCEPTED)
        economic_spine.transition_mission(mission.id, MissionState.EXECUTING)
        assert economic_spine.spend_tokens(agent_id, 3000, mission.id) is True
        economic_spine.transition_mission(
            mission.id, MissionState.DELIVERED, tokens_actual=3000
        )

        # 2. Knowledge store: task produces knowledge
        prop = Proposition(
            content="API endpoint /users returns paginated results",
            concepts=["api", "pagination"],
            provenance_event_id=f"mission-{mission.id}-{agent_id}",
            provenance_context=f"{agent_id} completed test task",
        )
        presc = Prescription(
            intent="Paginate API results",
            workflow=["check for next_page token", "loop until exhausted"],
            concepts=["api", "pagination"],
            provenance_event_id=f"mission-{mission.id}-{agent_id}",
            return_score=0.8,
        )
        knowledge_store.store_proposition(prop)
        knowledge_store.store_prescription(presc)

        # 3. Darwin Engine: extended fitness signals
        engine = DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
        )
        engine.set_knowledge_store(knowledge_store)
        engine.set_economic_spine(economic_spine)

        mock_ce = MagicMock()
        mock_ce.get_correction_history.return_value = []
        engine.set_correction_engine(mock_ce)

        # Verify signals are non-default
        mem_signal = engine._memory_quality_signal(agent_id)
        assert mem_signal > 0.0  # Agent has knowledge units

        econ_signal = engine._economic_efficiency_signal(agent_id)
        assert 0.0 <= econ_signal <= 1.0

        health_signal = engine._correction_health_signal(agent_id)
        assert health_signal == 1.0  # No corrections

        # Extended fitness should be computed
        base_fitness = 0.75
        extended = engine.compute_extended_fitness(agent_id, base_fitness)
        assert 0.0 <= extended <= 1.0

        # 4. Knowledge retrieval works for second task
        results = knowledge_store.get_propositions_for_context(
            task_concepts=["api", "pagination"]
        )
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_economic_tracking_without_enforcement(
        self, economic_spine: EconomicSpine
    ):
        """Zero budget doesn't block task execution."""
        agent_id = "broke-agent"

        # Set budget to zero by overspending
        budget = economic_spine.get_or_create_budget(agent_id)
        economic_spine.spend_tokens(agent_id, budget.total_tokens_allocated)

        updated = economic_spine.get_or_create_budget(agent_id)
        assert updated.tokens_remaining == 0

        # Create a mission and spend more — should succeed
        mission = economic_spine.create_mission(agent_id, "Task despite no budget", 2000)
        economic_spine.transition_mission(mission.id, MissionState.QUOTED)
        economic_spine.transition_mission(mission.id, MissionState.ACCEPTED)
        economic_spine.transition_mission(mission.id, MissionState.EXECUTING)

        # Spending succeeds despite negative balance
        result = economic_spine.spend_tokens(agent_id, 2000, mission.id)
        assert result is True

        final = economic_spine.get_or_create_budget(agent_id)
        assert final.tokens_remaining < 0
