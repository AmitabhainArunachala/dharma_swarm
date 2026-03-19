"""Tests for v0.7.0 Palantir Operational Intelligence wiring.

Covers C1 (Live Object Graph), C2 (Semantic Task Routing),
C3 (Cross-Agent Truth Fusion), C4 (Operational Dashboard).
"""

import json
import os
import time
import pytest
from unittest.mock import patch, MagicMock

from dharma_swarm.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    Task,
    TaskStatus,
    TopologyType,
)
from dharma_swarm.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Shared mocks (mirrors test_orchestrator.py)
# ---------------------------------------------------------------------------

class MockTaskBoard:
    def __init__(self):
        self.tasks = []
        self.updates = []

    async def get_ready_tasks(self):
        return [t for t in self.tasks if t.status.value == "pending"]

    async def update_task(self, task_id, **fields):
        self.updates.append((task_id, fields))
        for task in self.tasks:
            if task.id != task_id:
                continue
            if "status" in fields:
                task.status = fields["status"]
            if "metadata" in fields and isinstance(fields["metadata"], dict):
                task.metadata = dict(fields["metadata"])
            break

    async def get(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    async def list_tasks(self, status=None, limit=100):
        tasks = list(self.tasks)
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks[:limit]


class MockAgentPool:
    def __init__(self, agents=None):
        self._agents = agents or []
        self._results = {}
        self._assignments = []
        self._runners = {}

    async def list_agents(self):
        return list(self._agents)

    async def get_idle_agents(self):
        return self._agents

    async def assign(self, agent_id, task_id):
        self._assignments.append((agent_id, task_id))

    async def release(self, agent_id):
        pass

    async def get_result(self, agent_id):
        return self._results.get(agent_id)

    async def get(self, agent_id):
        return self._runners.get(agent_id)


class MockEventMemory:
    def __init__(self):
        self.envelopes = []

    async def ingest_envelope(self, envelope):
        self.envelopes.append(envelope)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agents():
    return [
        AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
        AgentState(id="a2", name="agent-2", role=AgentRole.CODER, status=AgentStatus.IDLE),
    ]


@pytest.fixture
def orch():
    """Basic orchestrator with no seam (FIFO fallback)."""
    return Orchestrator(
        task_board=MockTaskBoard(),
        agent_pool=MockAgentPool(),
        event_memory=MockEventMemory(),
    )


# =========================================================================
# C1: Live Object Graph
# =========================================================================

class TestC1_LiveObjectGraph:
    def test_set_seam_installs_singleton(self):
        """_set_seam() makes get_seam() return the installed instance."""
        from dharma_swarm.telic_seam import TelicSeam, get_seam, _set_seam, reset_seam

        reset_seam()  # ensure clean state
        custom = TelicSeam()
        _set_seam(custom)
        assert get_seam() is custom
        reset_seam()  # cleanup

    def test_orchestrator_accepts_telic_seam(self):
        """Orchestrator.__init__ stores telic_seam param."""
        sentinel = object()
        orch = Orchestrator(telic_seam=sentinel)
        assert orch._telic_seam is sentinel

    def test_orchestrator_uses_passed_seam_in_fitness(self):
        """_fitness_biased_pick uses self._telic_seam, not a fresh singleton."""
        from dharma_swarm.telic_seam import TelicSeam, reset_seam

        reset_seam()
        seam = TelicSeam()
        orch = Orchestrator(telic_seam=seam)
        agents = [
            AgentState(id="a1", name="a1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
            AgentState(id="a2", name="a2", role=AgentRole.CODER, status=AgentStatus.IDLE),
        ]

        # With ENABLE_FITNESS_ROUTING=auto and no data, should return None (FIFO)
        with patch.dict(os.environ, {"ENABLE_FITNESS_ROUTING": "auto"}):
            result = orch._fitness_biased_pick(agents, None)
            assert result is None  # No fitness data → FIFO

        reset_seam()

    def test_fitness_stays_fifo_when_disabled(self):
        """ENABLE_FITNESS_ROUTING=0 forces FIFO regardless of data."""
        orch = Orchestrator()
        agents = [
            AgentState(id="a1", name="a1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
            AgentState(id="a2", name="a2", role=AgentRole.CODER, status=AgentStatus.IDLE),
        ]
        with patch.dict(os.environ, {"ENABLE_FITNESS_ROUTING": "0"}):
            assert orch._fitness_biased_pick(agents, None) is None

    def test_fitness_auto_enables_with_contributions(self):
        """When fitness data exists, auto mode enables competence routing."""
        from dharma_swarm.telic_seam import TelicSeam

        seam = TelicSeam()
        # Record some contributions so there's fitness data
        from dharma_swarm.ontology import OntologyRegistry
        registry = OntologyRegistry.create_dharma_registry()
        seam._registry = registry
        # Manually inject a contribution object with all required fields
        obj, errors = registry.create_object(
            "Contribution",
            properties={
                "agent_id": "a1",
                "value_event_id": "ve_test_1",
                "task_type": "",
                "cell_id": "",
                "credit_share": 1.0,
                "attributed_value": 0.8,
            },
        )
        assert obj is not None, f"Failed to create Contribution: {errors}"

        orch = Orchestrator(telic_seam=seam)
        agents = [
            AgentState(id="a1", name="a1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
            AgentState(id="a2", name="a2", role=AgentRole.CODER, status=AgentStatus.IDLE),
        ]
        with patch.dict(os.environ, {"ENABLE_FITNESS_ROUTING": "auto"}):
            result = orch._fitness_biased_pick(agents, None)
            # Should return an agent (not None) since data exists
            assert result is not None


# =========================================================================
# C2: Semantic Task Routing
# =========================================================================

class TestC2_SemanticRouting:
    def test_intent_enriches_task_metadata(self):
        """_enrich_task_with_intent sets intent_* fields on task metadata."""
        orch = Orchestrator()
        task = Task(id="t1", title="Fix broken test in monitor.py")
        orch._enrich_task_with_intent(task)
        meta = task.metadata
        assert meta.get("intent_analyzed") is True
        assert "intent_skill" in meta
        assert "intent_confidence" in meta
        assert "intent_complexity" in meta
        assert "intent_risk" in meta

    def test_intent_sets_preferred_roles(self):
        """Intent analysis injects coordination_preferred_roles for known skills."""
        orch = Orchestrator()
        task = Task(id="t2", title="Build new API endpoint for user service")
        orch._enrich_task_with_intent(task)
        meta = task.metadata
        # Should detect builder skill → coder role
        if meta.get("intent_skill") == "builder":
            assert meta.get("coordination_preferred_roles") == ["coder"]

    def test_intent_idempotent(self):
        """Calling _enrich_task_with_intent twice doesn't overwrite."""
        orch = Orchestrator()
        task = Task(id="t3", title="Research new approaches")
        orch._enrich_task_with_intent(task)
        first_skill = task.metadata.get("intent_skill")
        # Overwrite to test idempotency
        task.metadata["intent_skill"] = "CHANGED"
        orch._enrich_task_with_intent(task)
        # Should not overwrite since intent_analyzed is True
        assert task.metadata.get("intent_skill") == "CHANGED"

    @pytest.mark.asyncio
    async def test_intent_routing_feature_flag_off(self, agents, monkeypatch):
        """ENABLE_INTENT_ROUTING=0 skips enrichment in route_next."""
        monkeypatch.setenv("ENABLE_INTENT_ROUTING", "0")
        board = MockTaskBoard()
        pool = MockAgentPool(agents)
        orch = Orchestrator(task_board=board, agent_pool=pool, event_memory=MockEventMemory())
        task = Task(id="t4", title="Build something")
        board.tasks.append(task)

        await orch.route_next()
        # With routing disabled, intent_analyzed should not be set
        meta = task.metadata if isinstance(task.metadata, dict) else {}
        assert meta.get("intent_analyzed") is not True

    def test_skill_to_role_mapping(self):
        """All _SKILL_TO_ROLE values are valid role-like strings."""
        mapping = Orchestrator._SKILL_TO_ROLE
        assert len(mapping) >= 8
        for skill, role in mapping.items():
            assert isinstance(skill, str)
            assert isinstance(role, str)
            assert role  # Not empty


# =========================================================================
# C3: Cross-Agent Truth Fusion
# =========================================================================

class TestC3_TruthFusion:
    def test_coordination_context_injected(self):
        """When coordination result exists, _prepare_claim injects context."""
        from dharma_swarm.sheaf import CoordinationResult, Discovery

        orch = Orchestrator()
        # Build a fake coordination result
        truth = Discovery(
            agent_id="a1",
            claim_key="shared_truth",
            content="Both agents agree on architecture",
            confidence=0.9,
        )
        result = MagicMock()
        result.global_truths = [truth]
        result.productive_disagreements = []
        result.is_globally_coherent = True
        orch._last_coordination_result = result

        from dharma_swarm.models import TaskDispatch
        task = Task(id="t1", title="Test task")
        td = TaskDispatch(
            task_id="t1",
            agent_id="a1",
            topology=TopologyType.FAN_OUT,
        )
        meta = orch._prepare_claim(task, td)
        assert "coordination_context" in meta
        assert "Agreed:" in meta["coordination_context"]
        assert meta.get("coordination_coherent") is True

    def test_coordination_context_absent_without_data(self):
        """Without coordination result, no context is injected."""
        orch = Orchestrator()
        from dharma_swarm.models import TaskDispatch
        task = Task(id="t2", title="Test task 2")
        td = TaskDispatch(
            task_id="t2",
            agent_id="a1",
            topology=TopologyType.FAN_OUT,
        )
        meta = orch._prepare_claim(task, td)
        assert "coordination_context" not in meta

    @pytest.mark.asyncio
    async def test_operational_picture_written(self, tmp_path):
        """_tick_living_layers writes operational_picture.json."""
        from dharma_swarm.swarm import SwarmManager

        sm = SwarmManager.__new__(SwarmManager)
        sm.state_dir = tmp_path
        sm._stigmergy = None
        sm._ontology_registry = None
        sm._telic_seam = None
        sm._tick_count = 5
        sm._orchestrator = None
        sm._engine = None

        await sm._tick_living_layers()

        picture_path = tmp_path / "operational_picture.json"
        assert picture_path.exists()
        data = json.loads(picture_path.read_text())
        assert data["tick_count"] == 5
        assert "timestamp" in data


# =========================================================================
# C4: Operational Dashboard
# =========================================================================

class TestC4_Dashboard:
    @pytest.mark.asyncio
    async def test_operational_snapshot_shape(self, tmp_path):
        """operational_snapshot returns dict with all expected sections."""
        from dharma_swarm.swarm import SwarmManager

        sm = SwarmManager.__new__(SwarmManager)
        sm.state_dir = tmp_path
        sm._stigmergy = None
        sm._ontology_registry = None
        sm._telic_seam = None
        sm._tick_count = 10
        sm._start_time = time.monotonic() - 60
        sm._orchestrator = None
        sm._engine = None
        sm._initialized = {"core", "ontology"}

        # Mock status() and coordination_status()
        async def mock_status():
            m = MagicMock()
            m.model_dump.return_value = {"agents": 2}
            return m

        async def mock_coord(refresh=False):
            m = MagicMock()
            m.model_dump.return_value = {"coherent": True}
            return m

        sm.status = mock_status
        sm.coordination_status = mock_coord

        snap = await sm.operational_snapshot()
        assert "timestamp" in snap
        assert snap["tick_count"] == 10
        assert snap["uptime_seconds"] >= 59
        assert snap["swarm"] == {"agents": 2}
        assert snap["coordination"] == {"coherent": True}
        assert "ontology" in snap
        assert "telic_seam" in snap
        assert "stigmergy" in snap
        assert "subsystems" in snap

    @pytest.mark.asyncio
    async def test_snapshot_graceful_without_subsystems(self, tmp_path):
        """Snapshot works with all subsystems as None."""
        from dharma_swarm.swarm import SwarmManager

        sm = SwarmManager.__new__(SwarmManager)
        sm.state_dir = tmp_path
        sm._stigmergy = None
        sm._ontology_registry = None
        sm._telic_seam = None
        sm._tick_count = 0
        sm._start_time = time.monotonic()
        sm._orchestrator = None
        sm._engine = None
        sm._initialized = set()

        async def mock_status():
            m = MagicMock()
            m.model_dump.return_value = {}
            return m

        async def mock_coord(refresh=False):
            m = MagicMock()
            m.model_dump.return_value = {}
            return m

        sm.status = mock_status
        sm.coordination_status = mock_coord

        snap = await sm.operational_snapshot()
        assert snap["ontology"] == {}
        assert snap["telic_seam"] == {}
        assert snap["stigmergy"]["density"] == 0

    def test_cmd_ops_reads_picture(self, tmp_path, monkeypatch, capsys):
        """cmd_ops reads and formats operational_picture.json."""
        from dharma_swarm.dgc_cli import cmd_ops, DHARMA_STATE

        picture = {
            "timestamp": "2026-03-18T22:30:00Z",
            "tick_count": 47,
            "ontology": {"total_objects": 89},
            "telic_seam": {"proposals": 23, "outcomes": 19},
            "coordination": {"global_truths": 3, "is_globally_coherent": True},
            "stigmergy_density": 1573,
        }
        picture_path = DHARMA_STATE / "operational_picture.json"
        picture_path.parent.mkdir(parents=True, exist_ok=True)
        picture_path.write_text(json.dumps(picture))

        cmd_ops()
        out = capsys.readouterr().out
        assert "OPERATIONAL PICTURE" in out
        assert "47" in out
        assert "1573" in out

    def test_cmd_ops_no_picture(self, tmp_path, monkeypatch, capsys):
        """cmd_ops handles missing picture gracefully."""
        from dharma_swarm.dgc_cli import cmd_ops, DHARMA_STATE

        # Remove picture if it exists
        picture_path = DHARMA_STATE / "operational_picture.json"
        if picture_path.exists():
            picture_path.unlink()

        cmd_ops()
        out = capsys.readouterr().out
        assert "No operational picture" in out or "OPERATIONAL PICTURE" in out


# =========================================================================
# Integration: Closed-loop smoke test
# =========================================================================

class TestIntegration:
    def test_seam_singleton_survives_reset_and_set(self):
        """Full cycle: reset → set → get returns same."""
        from dharma_swarm.telic_seam import TelicSeam, get_seam, _set_seam, reset_seam

        reset_seam()
        a = get_seam()  # creates fresh
        reset_seam()
        b = TelicSeam()
        _set_seam(b)
        assert get_seam() is b
        assert get_seam() is not a
        reset_seam()

    def test_orchestrator_seam_fallback(self):
        """Orchestrator without passed seam falls back to module singleton."""
        from dharma_swarm.telic_seam import TelicSeam, _set_seam, reset_seam, get_seam

        reset_seam()
        global_seam = TelicSeam()
        _set_seam(global_seam)

        orch = Orchestrator()  # No telic_seam passed
        assert orch._telic_seam is None
        # _fitness_biased_pick should use the global singleton
        # (tested by the fact that it doesn't crash with auto mode)
        agents = [
            AgentState(id="a1", name="a1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
            AgentState(id="a2", name="a2", role=AgentRole.CODER, status=AgentStatus.IDLE),
        ]
        with patch.dict(os.environ, {"ENABLE_FITNESS_ROUTING": "auto"}):
            result = orch._fitness_biased_pick(agents, None)
            # No data in singleton → FIFO → None
            assert result is None

        reset_seam()
