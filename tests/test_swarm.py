"""Tests for dharma_swarm.swarm — integration tests."""

import asyncio
from pathlib import Path

import pytest

from dharma_swarm.engine.conversation_memory import ConversationMemoryStore
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import AgentRole, AgentState, AgentStatus, Message, TaskPriority, TaskStatus
from dharma_swarm.swarm import SwarmCoordinationState, SwarmManager
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
)


# startup_crew auto-spawns agents and seed tasks on init.
# Count is dynamic: skill discovery may override DEFAULT_CREW.
def _expected_agent_count() -> int:
    from dharma_swarm.startup_crew import _crew_from_skills, DEFAULT_CREW
    crew = _crew_from_skills() or DEFAULT_CREW
    return len(crew)


_AUTO_AGENTS = _expected_agent_count()
_AUTO_TASKS = 5


@pytest.fixture
async def swarm(tmp_path):
    s = SwarmManager(state_dir=tmp_path / ".dharma")
    await s.init()
    yield s
    await s.shutdown()


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_init(swarm):
    state = await swarm.status()
    assert state.tasks_pending == _AUTO_TASKS
    assert len(state.agents) >= _AUTO_AGENTS


@pytest.mark.asyncio
async def test_init_falls_back_to_state_local_manifest_when_global_write_is_blocked(
    tmp_path,
    monkeypatch,
):
    import dharma_swarm.ecosystem_bridge as ecosystem_bridge

    state_dir = tmp_path / ".dharma"
    calls: list[Path | None] = []

    def fake_update_manifest(manifest_path=None):
        calls.append(Path(manifest_path) if manifest_path is not None else None)
        if manifest_path is None:
            raise PermissionError("sandbox blocked global manifest")
        return {"ecosystem": {}, "last_scan": "2026-03-11T00:00:00+00:00"}

    monkeypatch.setattr(ecosystem_bridge, "update_manifest", fake_update_manifest)

    swarm = SwarmManager(state_dir=state_dir)
    await swarm.init()
    try:
        assert calls == [None, state_dir / "ecosystem_manifest.json"]
        assert swarm._manifest["ecosystem"] == {}
    finally:
        await swarm.shutdown()


@pytest.mark.asyncio
async def test_spawn_agent(swarm):
    agent = await swarm.spawn_agent("worker-1", role=AgentRole.CODER)
    assert agent.name == "worker-1"
    assert agent.role == AgentRole.CODER

    agents = await swarm.list_agents()
    assert len(agents) >= _AUTO_AGENTS + 1


@pytest.mark.asyncio
async def test_sync_agents_retires_stale_live_contracts(tmp_path, monkeypatch):
    db_path = tmp_path / "runtime.db"
    telemetry = TelemetryPlaneStore(db_path)
    await telemetry.init_db()
    await telemetry.upsert_agent_identity(
        AgentIdentityRecord(
            agent_id="stale-agent",
            codename="stale-agent",
            status="idle",
        )
    )
    await telemetry.record_team_roster(
        TeamRosterRecord(
            roster_id="roster:dharma_swarm:stale-agent",
            team_id="dharma_swarm",
            agent_id="stale-agent",
            role="surgeon",
            active=True,
        )
    )

    class _StaticPool:
        async def list_agents(self) -> list[AgentState]:
            return [
                AgentState(
                    id="agent-live-1",
                    name="live-agent",
                    role=AgentRole.CODER,
                    status=AgentStatus.IDLE,
                )
            ]

    monkeypatch.setenv("DHARMA_RUNTIME_DB", str(db_path))

    swarm = SwarmManager(state_dir=tmp_path / ".dharma")
    swarm._agent_pool = _StaticPool()
    swarm._agent_configs = {}

    results = await swarm.sync_agents()

    retired_identity = await telemetry.get_agent_identity("stale-agent")
    retired_roster = await telemetry.list_team_roster(
        team_id="dharma_swarm",
        agent_id="stale-agent",
        active_only=False,
        limit=10,
    )

    assert len(results) == 1
    assert retired_identity is not None
    assert retired_identity.status == "retired"
    assert retired_roster[0].active is False


@pytest.mark.asyncio
async def test_sync_agents_preserves_bus_readiness_for_live_agents(tmp_path, monkeypatch):
    db_path = tmp_path / "runtime.db"
    bus = MessageBus(tmp_path / "message_bus.db")
    await bus.init_db()
    await bus.subscribe("live-agent", "orchestrator.lifecycle")
    await bus.subscribe("live-agent", "operator.bridge.lifecycle")
    await bus.heartbeat("live-agent", metadata={"role": "coder"})

    class _StaticPool:
        async def list_agents(self) -> list[AgentState]:
            return [
                AgentState(
                    id="agent-live-1",
                    name="live-agent",
                    role=AgentRole.CODER,
                    status=AgentStatus.IDLE,
                )
            ]

    monkeypatch.setenv("DHARMA_RUNTIME_DB", str(db_path))

    telemetry = TelemetryPlaneStore(db_path)
    await telemetry.init_db()

    swarm = SwarmManager(state_dir=tmp_path / ".dharma")
    swarm._agent_pool = _StaticPool()
    swarm._agent_configs = {}
    swarm._message_bus = bus

    results = await swarm.sync_agents()
    identity = await telemetry.get_agent_identity("live-agent")

    assert len(results) == 1
    assert results[0]["communication_ready"] is True
    assert results[0]["bus_status"] == "online"
    assert results[0]["missing_topics"] == []
    assert identity is not None
    assert identity.metadata["communication_ready"] is True
    assert identity.metadata["bus_status"] == "online"


@pytest.mark.asyncio
async def test_list_agents_retires_stale_live_contracts_when_pool_is_empty(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "runtime.db"
    telemetry = TelemetryPlaneStore(db_path)
    await telemetry.init_db()
    await telemetry.upsert_agent_identity(
        AgentIdentityRecord(
            agent_id="stale-agent",
            codename="stale-agent",
            status="idle",
        )
    )
    await telemetry.record_team_roster(
        TeamRosterRecord(
            roster_id="roster:dharma_swarm:stale-agent",
            team_id="dharma_swarm",
            agent_id="stale-agent",
            role="surgeon",
            active=True,
        )
    )

    class _StaticPool:
        async def list_agents(self) -> list[AgentState]:
            return []

    monkeypatch.setenv("DHARMA_RUNTIME_DB", str(db_path))

    swarm = SwarmManager(state_dir=tmp_path / ".dharma")
    swarm._agent_pool = _StaticPool()
    swarm._agent_configs = {}

    agents = await swarm.list_agents()
    retired_identity = await telemetry.get_agent_identity("stale-agent")
    retired_roster = await telemetry.list_team_roster(
        team_id="dharma_swarm",
        agent_id="stale-agent",
        active_only=False,
        limit=10,
    )

    assert agents == []
    assert retired_identity is not None
    assert retired_identity.status == "retired"
    assert retired_roster[0].active is False


@pytest.mark.asyncio
async def test_create_task(swarm):
    task = await swarm.create_task("Build module", priority=TaskPriority.HIGH)
    assert task.title == "Build module"
    assert task.priority == TaskPriority.HIGH
    assert task.metadata.get("trace_id", "").startswith("trc_")
    assert task.metadata.get("created_via") == "swarm.create_task"


@pytest.mark.asyncio
async def test_create_task_normalizes_coordination_metadata(swarm):
    task = await swarm.create_task(
        "Route policy review",
        metadata={
            "claim_key": "route-policy",
            "uncertainty": 0.7,
            "coordination_shared_context": "Existing disagreement context",
        },
    )

    assert task.metadata["coordination_claim_key"] == "route-policy"
    assert task.metadata["coordination_topic"] == "route-policy"
    assert task.metadata["coordination_uncertainty"] == pytest.approx(0.7)
    assert task.metadata["coordination_state"] == "uncertain"
    assert task.metadata["coordination_route"] == "synthesis_review"
    assert "reviewer" in task.metadata["coordination_preferred_roles"]


@pytest.mark.asyncio
async def test_create_task_blocked(swarm):
    with pytest.raises(ValueError, match="Telos gate blocked"):
        await swarm.create_task("rm -rf /everything")


@pytest.mark.asyncio
async def test_create_task_blocks_self_referential_heartbeat_task(swarm):
    with pytest.raises(ValueError, match="Self-referential heartbeat task blocked"):
        await swarm.create_task(
            "Parse heartbeat.md",
            description="Create a task about heartbeat.md and summarize heartbeat loops",
            metadata={"source": "heartbeat"},
        )


@pytest.mark.asyncio
async def test_list_tasks(swarm):
    await swarm.create_task("Task 1")
    await swarm.create_task("Task 2")
    tasks = await swarm.list_tasks()
    assert len(tasks) == _AUTO_TASKS + 2


@pytest.mark.asyncio
async def test_get_task(swarm):
    task = await swarm.create_task("Findable")
    found = await swarm.get_task(task.id)
    assert found is not None
    assert found.title == "Findable"


@pytest.mark.asyncio
async def test_memory(swarm):
    await swarm.remember("test memory entry")
    entries = await swarm.recall(limit=5)
    assert len(entries) >= 1


@pytest.mark.asyncio
async def test_spawn_latent_gold_tasks_reopens_orphaned_branches(swarm):
    store = ConversationMemoryStore(swarm.state_dir / "db" / "memory_plane.db")
    store.record_turn(
        session_id="sess-latent",
        task_id="task-source",
        role="user",
        content=(
            "We could build a memory palace index for task recall.\n"
            "Maybe preserve abandoned branches from the conversation."
        ),
        turn_index=1,
    )
    store.mark_task_outcome("task-source", outcome="success")

    created = await swarm.spawn_latent_gold_tasks(
        limit=2,
        max_pending=100,
        min_salience=0.0,
    )

    assert created
    assert created[0].metadata["latent_gold_reopened"] is True
    assert created[0].metadata["latent_gold_shard_id"].startswith("shd_")

    second = await swarm.spawn_latent_gold_tasks(
        limit=2,
        max_pending=100,
        min_salience=0.0,
    )
    assert second == []


@pytest.mark.asyncio
async def test_run_dispatches_pending_work_even_when_generation_rate_limited(
    swarm,
    monkeypatch,
):
    calls = {"spawn": 0, "tick": 0}

    async def fake_spawn(*args, **kwargs):
        calls["spawn"] += 1
        return []

    async def fake_tick():
        calls["tick"] += 1
        swarm._running = False
        return {"dispatched": 1, "settled": 0, "recovered": 0}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(swarm, "spawn_latent_gold_tasks", fake_spawn)
    monkeypatch.setattr(swarm, "_contribution_allowed", lambda: False)
    monkeypatch.setattr(swarm, "_in_quiet_hours", lambda: True)
    monkeypatch.setattr(swarm._orchestrator, "tick", fake_tick)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    swarm._running = True
    await swarm.run(interval=0.0)

    assert calls["spawn"] == 0
    assert calls["tick"] == 1
    assert swarm._daily_contributions == 1


@pytest.mark.asyncio
async def test_run_does_not_consume_contribution_budget_without_work(
    swarm,
    monkeypatch,
):
    calls = {"spawn": 0, "tick": 0}

    async def fake_spawn(*args, **kwargs):
        calls["spawn"] += 1
        return []

    async def fake_tick():
        calls["tick"] += 1
        swarm._running = False
        return {"dispatched": 0, "settled": 0, "recovered": 0}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(swarm, "spawn_latent_gold_tasks", fake_spawn)
    monkeypatch.setattr(swarm, "_contribution_allowed", lambda: True)
    monkeypatch.setattr(swarm, "_in_quiet_hours", lambda: False)
    monkeypatch.setattr(swarm._orchestrator, "tick", fake_tick)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    swarm._running = True
    swarm._daily_contributions = 0
    swarm._last_contribution = None
    await swarm.run(interval=0.0)

    assert calls["spawn"] == 1
    assert calls["tick"] == 1
    assert swarm._daily_contributions == 0
    assert swarm._last_contribution is None


@pytest.mark.asyncio
async def test_rescue_recent_failures_requeues_transient_failure(swarm):
    task = await swarm.create_task("Transient rescue target")
    await swarm._task_board.assign(task.id, "agent-1")
    await swarm._task_board.start(task.id)
    await swarm._task_board.fail(
        task.id,
        "Connection error.",
        metadata={"last_failure_source": "execution_error"},
    )

    rescued = await swarm.rescue_recent_failures(limit=4)

    assert rescued
    refreshed = await swarm.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.PENDING
    assert refreshed.metadata["auto_rescue_count"] == 1
    assert refreshed.metadata["last_failure_class"] == "connection_transient"


@pytest.mark.asyncio
async def test_rescue_recent_failures_skips_duplicate_active_title(swarm):
    failed = await swarm.create_task("Duplicate rescue title")
    await swarm._task_board.assign(failed.id, "agent-1")
    await swarm._task_board.start(failed.id)
    await swarm._task_board.fail(
        failed.id,
        "Task execution timed out after 300.0s",
        metadata={"last_failure_source": "timeout", "timeout_seconds": 300.0},
    )

    active = await swarm.create_task("Duplicate rescue title")
    assert active.status == TaskStatus.PENDING

    rescued = await swarm.rescue_recent_failures(limit=4)

    assert rescued == []
    refreshed = await swarm.get_task(failed.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_status(swarm):
    await swarm.spawn_agent("a1")
    await swarm.create_task("t1")
    state = await swarm.status()
    assert len(state.agents) >= _AUTO_AGENTS + 1
    assert state.tasks_pending == _AUTO_TASKS + 1
    assert state.uptime_seconds > 0


@pytest.mark.asyncio
async def test_coordination_status_reports_global_truth(swarm):
    agents = await swarm.list_agents()
    left, right = agents[0], agents[1]
    await swarm._message_bus.send(
        Message(
            id="coord-msg-1",
            from_agent=left.id,
            to_agent=right.id,
            subject="route-policy",
            body="Mechanism, witness, ecosystem all agree.",
            metadata={"topic": "route-policy"},
        )
    )
    await swarm._message_bus.send(
        Message(
            id="coord-msg-2",
            from_agent=right.id,
            to_agent=left.id,
            subject="route-policy",
            body="Mechanism, witness, ecosystem all agree.",
            metadata={"topic": "route-policy"},
        )
    )

    coordination = await swarm.coordination_status(refresh=True)

    assert isinstance(coordination, SwarmCoordinationState)
    assert coordination.agent_count >= 2
    assert coordination.message_count >= 2
    assert coordination.global_truths >= 1
    assert coordination.productive_disagreements == 0
    assert coordination.is_globally_coherent is True
    assert "route-policy" in coordination.global_truth_claim_keys


@pytest.mark.asyncio
async def test_coordination_status_reports_productive_disagreement(swarm):
    agents = await swarm.list_agents()
    left, right = agents[0], agents[1]
    await swarm._message_bus.send(
        Message(
            id="coord-msg-3",
            from_agent=left.id,
            to_agent=right.id,
            subject="route-policy",
            body="Mechanism and architecture dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )
    await swarm._message_bus.send(
        Message(
            id="coord-msg-4",
            from_agent=right.id,
            to_agent=left.id,
            subject="route-policy",
            body="Witness awareness and introspection dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )

    coordination = await swarm.coordination_status(refresh=True)

    assert coordination.global_truths == 0
    assert coordination.productive_disagreements >= 1
    assert coordination.is_globally_coherent is False
    assert "route-policy" in coordination.productive_disagreement_claim_keys


@pytest.mark.asyncio
async def test_spawn_coordination_tasks_creates_synthesis_task(swarm):
    agents = await swarm.list_agents()
    left, right = agents[0], agents[1]
    await swarm._message_bus.send(
        Message(
            id="coord-msg-5",
            from_agent=left.id,
            to_agent=right.id,
            subject="route-policy",
            body="Mechanism and architecture dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )
    await swarm._message_bus.send(
        Message(
            id="coord-msg-6",
            from_agent=right.id,
            to_agent=left.id,
            subject="route-policy",
            body="Witness awareness and introspection dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )

    coordination = await swarm.coordination_status(refresh=True)
    created = await swarm.spawn_coordination_tasks(coordination=coordination, limit=2)

    assert created
    task = created[0]
    assert task.metadata["coordination_origin"] == "sheaf_disagreement"
    assert task.metadata["coordination_claim_key"] == "route-policy"
    assert task.metadata["coordination_route"] == "synthesis_review"
    assert task.priority == TaskPriority.HIGH


# --- Gödel Claw v0.3.0 tests ---


@pytest.mark.asyncio
async def test_dharma_status(swarm):
    """dharma_status returns subsystem state."""
    status = await swarm.dharma_status()
    assert status["kernel"] is True
    assert status["kernel_axioms"] == 25
    assert status["kernel_integrity"] is True
    assert status["corpus"] is True
    assert status["compiler"] is True
    assert status["canary"] is True


@pytest.mark.asyncio
async def test_propose_claim(swarm):
    """propose_claim creates a claim with DC-ID."""
    result = await swarm.propose_claim("Test safety claim", category="safety")
    assert result["id"].startswith("DC-")
    assert result["status"] == "proposed"


@pytest.mark.asyncio
async def test_review_claim(swarm):
    """review_claim adds a review record."""
    claim = await swarm.propose_claim("Review test claim", category="operational")
    result = await swarm.review_claim(
        claim["id"], reviewer="test", action="review", comment="looks good"
    )
    assert result["status"] == "under_review"
    assert result["reviews"] == 1


@pytest.mark.asyncio
async def test_promote_claim(swarm):
    """promote_claim changes status to accepted."""
    claim = await swarm.propose_claim("Promote test", category="ethics")
    result = await swarm.promote_claim(claim["id"])
    assert result["status"] == "accepted"


@pytest.mark.asyncio
async def test_compile_policy(swarm):
    """compile_policy produces rules from kernel."""
    result = await swarm.compile_policy(context="test")
    assert result["immutable"] == 25  # kernel axioms
    assert result["context"] == "test"


@pytest.mark.asyncio
async def test_compile_policy_with_claims(swarm):
    """compile_policy includes accepted claims."""
    claim = await swarm.propose_claim(
        "Policy test claim", category="safety", confidence=0.8
    )
    await swarm.promote_claim(claim["id"])
    result = await swarm.compile_policy()
    assert result["mutable"] >= 1


@pytest.mark.asyncio
async def test_kernel_integrity_on_init(swarm):
    """Kernel should be valid after init."""
    status = await swarm.dharma_status()
    assert status["kernel_integrity"] is True


@pytest.mark.asyncio
async def test_corpus_claims_count(swarm):
    """Corpus claim count tracks proposals."""
    s1 = await swarm.dharma_status()
    initial = s1.get("corpus_claims", 0)
    await swarm.propose_claim("Counting test", category="operational")
    s2 = await swarm.dharma_status()
    assert s2["corpus_claims"] == initial + 1


# ---------------------------------------------------------------------------
# Algedonic channel (Beer S5 bypass)
# ---------------------------------------------------------------------------


def test_algedonic_handler_writes_signal_log(tmp_path):
    """_algedonic_handler writes JSONL entry to algedonic_signals.jsonl."""
    import json

    sm = SwarmManager.__new__(SwarmManager)
    sm.state_dir = tmp_path

    # Simulate a critical AlgedonicSignal via a simple namespace
    class FakeSignal:
        kind = "telos_drift"
        severity = "critical"
        action = "gnani_checkpoint"
        value = 0.28
        timestamp = 1234567890.0

    sm._algedonic_handler(FakeSignal())

    log_path = tmp_path / "algedonic_signals.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip())
    assert entry["kind"] == "telos_drift"
    assert entry["severity"] == "critical"
    assert entry["value"] == 0.28


def test_algedonic_critical_creates_emergency_hold(tmp_path):
    """Critical signal writes EMERGENCY_HOLD marker file."""
    sm = SwarmManager.__new__(SwarmManager)
    sm.state_dir = tmp_path

    class FakeSignal:
        kind = "telos_drift"
        severity = "critical"
        action = "gnani_checkpoint"
        value = 0.15
        timestamp = 0.0

    sm._algedonic_handler(FakeSignal())

    hold_path = tmp_path / "EMERGENCY_HOLD"
    assert hold_path.exists()
    assert "telos_drift" in hold_path.read_text()


def test_algedonic_noncritical_no_emergency_hold(tmp_path):
    """Non-critical signal does NOT write EMERGENCY_HOLD."""
    sm = SwarmManager.__new__(SwarmManager)
    sm.state_dir = tmp_path

    class FakeSignal:
        kind = "omega_divergence"
        severity = "medium"
        action = "rebalance_priorities"
        value = 0.55
        timestamp = 0.0

    sm._algedonic_handler(FakeSignal())

    # Log file should exist, but not the emergency hold
    assert (tmp_path / "algedonic_signals.jsonl").exists()
    assert not (tmp_path / "EMERGENCY_HOLD").exists()


def test_emergency_hold_pauses_dispatch(tmp_path):
    """EMERGENCY_HOLD marker causes _check_human_overrides to report paused."""
    import types

    sm = SwarmManager.__new__(SwarmManager)
    sm.state_dir = tmp_path
    # Minimal daemon stub with pause_file attribute
    sm._daemon = types.SimpleNamespace(pause_file=".PAUSE")
    sm._thread_mgr = None

    # No hold → not paused
    result = sm._check_human_overrides()
    assert result["paused"] is False

    # Create hold marker → paused
    (tmp_path / "EMERGENCY_HOLD").write_text("telos_drift: value=0.15\n")
    result = sm._check_human_overrides()
    assert result["paused"] is True
