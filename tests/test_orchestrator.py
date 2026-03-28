"""Tests for dharma_swarm.orchestrator."""

import asyncio
import json
import time
import pytest

from dharma_swarm.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    GateCheckResult,
    GateDecision,
    Message,
    Task,
    TaskStatus,
    TopologyType,
)
from dharma_swarm.orchestrator import Orchestrator


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
            if "assigned_to" in fields:
                task.assigned_to = fields["assigned_to"]
            if "result" in fields:
                task.result = fields["result"]
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
            tasks = [task for task in tasks if task.status == status]
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

    def set_result(self, agent_id, result):
        self._results[agent_id] = result

    async def get(self, agent_id):
        return self._runners.get(agent_id)

    def set_runner(self, agent_id, runner):
        self._runners[agent_id] = runner


class MockEventMemory:
    def __init__(self):
        self.envelopes = []

    async def ingest_envelope(self, envelope):
        self.envelopes.append(envelope)


@pytest.fixture(autouse=True)
def fast_dispatch_gate():
    """Default orchestrator dispatch gates to ALLOW for non-gate tests."""
    from unittest.mock import patch

    from dharma_swarm.telos_gates import ReflectiveGateOutcome

    allow = ReflectiveGateOutcome(
        result=GateCheckResult(
            decision=GateDecision.ALLOW,
            reason="All gates passed (test mock)",
        ),
    )
    with patch(
        "dharma_swarm.orchestrator.check_with_reflective_reroute",
        return_value=allow,
    ):
        yield allow


@pytest.fixture
def agents():
    return [
        AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
        AgentState(id="a2", name="agent-2", role=AgentRole.CODER, status=AgentStatus.IDLE),
    ]


@pytest.fixture
def tasks():
    return [
        Task(id="t1", title="Task 1"),
        Task(id="t2", title="Task 2"),
    ]


@pytest.mark.asyncio
async def test_dispatch_fan_out(agents, tasks):
    pool = MockAgentPool(agents)
    orch = Orchestrator(agent_pool=pool)
    dispatches = await orch.dispatch(tasks[0], topology=TopologyType.FAN_OUT)
    assert len(dispatches) == 2
    assert dispatches[0].agent_id == "a1"
    assert dispatches[1].agent_id == "a2"


@pytest.mark.asyncio
async def test_dispatch_no_agents():
    pool = MockAgentPool([])
    orch = Orchestrator(agent_pool=pool)
    dispatches = await orch.dispatch(Task(title="test"))
    assert len(dispatches) == 0


@pytest.mark.asyncio
async def test_route_next(agents, tasks):
    board = MockTaskBoard()
    board.tasks = tasks
    pool = MockAgentPool(agents)
    orch = Orchestrator(task_board=board, agent_pool=pool)

    dispatches = await orch.route_next()
    assert len(dispatches) == 2


@pytest.mark.asyncio
async def test_route_next_limited_agents(tasks):
    board = MockTaskBoard()
    board.tasks = tasks
    pool = MockAgentPool([
        AgentState(id="a1", name="only-one", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
    ])
    orch = Orchestrator(task_board=board, agent_pool=pool)

    dispatches = await orch.route_next()
    assert len(dispatches) == 1  # Only 1 agent for 2 tasks


@pytest.mark.asyncio
async def test_route_next_prefers_reviewer_for_uncertain_coordination_task():
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-review",
            title="Resolve disagreement",
            metadata={
                "coordination_claim_key": "route-policy",
                "coordination_route": "synthesis_review",
                "coordination_preferred_roles": ["reviewer", "researcher"],
            },
        )
    ]
    pool = MockAgentPool(
        [
            AgentState(
                id="a-general",
                name="agent-general",
                role=AgentRole.GENERAL,
                status=AgentStatus.IDLE,
            ),
            AgentState(
                id="a-review",
                name="agent-review",
                role=AgentRole.REVIEWER,
                status=AgentStatus.IDLE,
            ),
        ]
    )
    orch = Orchestrator(task_board=board, agent_pool=pool)

    dispatches = await orch.route_next()

    assert len(dispatches) == 1
    assert dispatches[0].agent_id == "a-review"


@pytest.mark.asyncio
async def test_route_next_prefers_director_named_agent_over_role_match():
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-cyber",
            title="Wire cybernetics lever",
            metadata={
                "director_preferred_agents": ["cyber-codex", "cyber-opus"],
                "coordination_preferred_roles": ["architect"],
            },
        )
    ]
    pool = MockAgentPool(
        [
            AgentState(
                id="a-opus-legacy",
                name="opus-primus",
                role=AgentRole.ARCHITECT,
                status=AgentStatus.IDLE,
            ),
            AgentState(
                id="a-cyber-codex",
                name="cyber-codex",
                role=AgentRole.SURGEON,
                status=AgentStatus.IDLE,
            ),
        ]
    )
    orch = Orchestrator(task_board=board, agent_pool=pool)

    dispatches = await orch.route_next()

    assert len(dispatches) == 1
    assert dispatches[0].agent_id == "a-cyber-codex"


@pytest.mark.asyncio
async def test_fan_in(agents):
    pool = MockAgentPool(agents)
    pool.set_result("a1", "result from agent 1")
    pool.set_result("a2", "result from agent 2")
    orch = Orchestrator(agent_pool=pool)

    from dharma_swarm.models import TaskDispatch
    dispatches = [
        TaskDispatch(task_id="t1", agent_id="a1"),
        TaskDispatch(task_id="t2", agent_id="a2"),
    ]
    combined = await orch.fan_in(dispatches)
    assert "result from agent 1" in combined
    assert "result from agent 2" in combined


@pytest.mark.asyncio
async def test_tick(agents, tasks):
    board = MockTaskBoard()
    board.tasks = tasks
    pool = MockAgentPool(agents)
    orch = Orchestrator(task_board=board, agent_pool=pool)

    activity = await orch.tick()
    # Should have dispatched
    assert len(pool._assignments) > 0
    assert activity["dispatched"] == 2


@pytest.mark.asyncio
async def test_tick_emits_runtime_event_with_coordination_summary(agents, tasks, monkeypatch):
    board = MockTaskBoard()
    board.tasks = [tasks[0]]
    pool = MockAgentPool([agents[0]])
    event_memory = MockEventMemory()
    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        event_memory=event_memory,
        session_id="sess-tick",
    )

    async def fake_refresh():
        return {"global_truths": 3, "productive_disagreements": 1}

    monkeypatch.setattr(orch, "_refresh_coordination_state", fake_refresh)

    activity = await orch.tick()

    assert activity["dispatched"] == 1
    assert activity["coordination_global_truths"] == 3
    assert activity["coordination_disagreements"] == 1
    tick_events = [
        envelope
        for envelope in event_memory.envelopes
        if envelope.payload.get("action_name") == "tick_summary"
    ]
    assert len(tick_events) == 1
    envelope = tick_events[0]
    assert envelope.source == "orchestrator.tick"
    assert envelope.session_id == "sess-tick"
    assert envelope.payload["action_name"] == "tick_summary"
    assert envelope.payload["dispatched_count"] == 1
    assert envelope.payload["dispatched_task_ids"] == ["t1"]
    assert envelope.payload["coordination_global_truths"] == 3
    assert envelope.payload["coordination_disagreements"] == 1


@pytest.mark.asyncio
async def test_stop():
    orch = Orchestrator()
    orch._running = True
    orch.stop()
    assert not orch._running


@pytest.mark.asyncio
async def test_no_deps():
    orch = Orchestrator()
    dispatches = await orch.route_next()
    assert dispatches == []


# ---------------------------------------------------------------------------
# MockMessageBus for bus-related tests
# ---------------------------------------------------------------------------

class MockMessageBus:
    """Simple mock for the message bus duck-type contract."""

    def __init__(self):
        self.sent: list = []
        self.published: list = []
        self._messages: list[Message] = []

    async def send(self, message):
        self.sent.append(message)
        self._messages.append(message)
        return message.id

    async def publish(self, topic, message):
        self.published.append((topic, message))
        self._messages.append(message)
        return [message.id]

    async def list_messages(self, limit=200, agent_id=None):
        messages = list(self._messages)
        if agent_id:
            messages = [
                message
                for message in messages
                if message.from_agent == agent_id or message.to_agent == agent_id
            ]
        return messages[-limit:]

    def seed_message(self, message: Message) -> None:
        self._messages.append(message)


class DummyRunner:
    """Tiny runner shim to drive _execute_task paths in tests."""

    def __init__(
        self,
        result: str | None = None,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
    ):
        self._result = result or "ok"
        self._error = error
        self._delay_seconds = delay_seconds
        self._config = None

    async def run_task(self, task):
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._error:
            raise self._error
        return self._result


# ---------------------------------------------------------------------------
# New tests — coverage expansion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_pipeline_assigns_first_idle_only(agents, tasks):
    """PIPELINE topology should assign the task to exactly the first idle agent."""
    pool = MockAgentPool(agents)
    orch = Orchestrator(agent_pool=pool)

    dispatches = await orch.dispatch(tasks[0], topology=TopologyType.PIPELINE)

    assert len(dispatches) == 1
    assert dispatches[0].agent_id == "a1"
    assert dispatches[0].topology == TopologyType.PIPELINE
    # Only one assignment should have been made
    assert len(pool._assignments) == 1
    assert pool._assignments[0] == ("a1", "t1")


@pytest.mark.asyncio
async def test_dispatch_no_pool_returns_empty(tasks):
    """dispatch with pool=None should return an empty list immediately."""
    orch = Orchestrator(agent_pool=None)
    dispatches = await orch.dispatch(tasks[0])
    assert dispatches == []


@pytest.mark.asyncio
async def test_fan_in_no_pool_returns_empty():
    """fan_in with pool=None should return an empty string."""
    from dharma_swarm.models import TaskDispatch

    orch = Orchestrator(agent_pool=None)
    dispatches = [
        TaskDispatch(task_id="t1", agent_id="a1"),
        TaskDispatch(task_id="t2", agent_id="a2"),
    ]
    result = await orch.fan_in(dispatches)
    assert result == ""


@pytest.mark.asyncio
async def test_fan_in_skips_none_results(agents):
    """fan_in should collect only non-None results, skipping agents that returned None."""
    from dharma_swarm.models import TaskDispatch

    pool = MockAgentPool(agents)
    pool.set_result("a1", "good result")
    # a2 has no result set -> get_result returns None
    orch = Orchestrator(agent_pool=pool)

    dispatches = [
        TaskDispatch(task_id="t1", agent_id="a1"),
        TaskDispatch(task_id="t2", agent_id="a2"),
    ]
    combined = await orch.fan_in(dispatches)

    assert "good result" in combined
    # The combined string should NOT contain "None" as a literal
    assert "None" not in combined
    # Only one fragment was collected
    assert combined == "good result"


@pytest.mark.asyncio
async def test_collect_completed_cleans_done_tasks():
    """_collect_completed should remove finished asyncio tasks from _running_tasks."""
    import asyncio

    orch = Orchestrator()

    # Create a coroutine that completes immediately
    async def _noop():
        return "done"

    done_task = asyncio.create_task(_noop())
    # Allow the task to finish
    await done_task

    orch._running_tasks["task-done"] = done_task
    # Also add a still-pending task to verify it is NOT removed
    pending_future: asyncio.Future = asyncio.get_event_loop().create_future()
    orch._running_tasks["task-pending"] = pending_future  # type: ignore[assignment]

    await orch._collect_completed()

    assert "task-done" not in orch._running_tasks
    assert "task-pending" in orch._running_tasks

    # Clean up the pending future so asyncio doesn't complain
    pending_future.cancel()


@pytest.mark.asyncio
async def test_assign_dispatch_calls_message_bus(agents, tasks):
    """_assign_dispatch should call bus.send when a message_bus is provided."""
    from dharma_swarm.models import TaskDispatch

    pool = MockAgentPool(agents)
    board = MockTaskBoard()
    bus = MockMessageBus()
    orch = Orchestrator(task_board=board, agent_pool=pool, message_bus=bus)

    td = TaskDispatch(task_id="t1", agent_id="a1")
    await orch._assign_dispatch(td)

    assert len(bus.sent) == 1
    msg = bus.sent[0]
    assert msg.from_agent == "orchestrator"
    assert msg.to_agent == "a1"
    assert "t1" in msg.subject
    assert "t1" in msg.body


@pytest.mark.asyncio
async def test_route_next_skips_running_tasks(agents, tasks):
    """route_next should skip tasks whose IDs are already in _running_tasks."""
    import asyncio

    board = MockTaskBoard()
    board.tasks = tasks  # t1 and t2 both pending
    pool = MockAgentPool(agents)
    orch = Orchestrator(task_board=board, agent_pool=pool)

    # Simulate t1 already running by placing a dummy task in _running_tasks
    pending_future: asyncio.Future = asyncio.get_event_loop().create_future()
    orch._running_tasks["t1"] = pending_future  # type: ignore[assignment]

    dispatches = await orch.route_next()

    # Only t2 should have been dispatched (t1 is already running)
    assert len(dispatches) == 1
    assert dispatches[0].task_id == "t2"
    assert dispatches[0].agent_id == "a1"

    # Clean up
    pending_future.cancel()


@pytest.mark.asyncio
async def test_assign_dispatch_telos_block_marks_failed_and_skips_assignment(agents, monkeypatch):
    """Harmful dispatch should fail fast before pool assignment."""
    from dharma_swarm.models import TaskDispatch
    from dharma_swarm.telos_gates import ReflectiveGateOutcome

    monkeypatch.setattr(
        "dharma_swarm.orchestrator.check_with_reflective_reroute",
        lambda **_: ReflectiveGateOutcome(
            result=GateCheckResult(
                decision=GateDecision.BLOCK,
                reason="Mock telos block",
            ),
        ),
        raising=True,
    )

    board = MockTaskBoard()
    board.tasks = [
        Task(id="harm1", title="rm -rf /important", description="delete all"),
    ]
    pool = MockAgentPool(agents)
    orch = Orchestrator(task_board=board, agent_pool=pool)

    td = TaskDispatch(task_id="harm1", agent_id="a1")
    await orch._assign_dispatch(td)

    assert pool._assignments == []
    assert any(
        task_id == "harm1"
        and fields.get("status") == TaskStatus.FAILED
        and "TELOS BLOCK (dispatch)" in str(fields.get("result", ""))
        for task_id, fields in board.updates
    )


@pytest.mark.asyncio
async def test_orchestrator_writes_task_and_progress_ledgers(tmp_path):
    """Successful execution should write both task and progress ledgers."""
    board = MockTaskBoard()
    board.tasks = [Task(id="t-ledger", title="Ledger task", description="safe")]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(result="ledger ok"))
    bus = MockMessageBus()

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        message_bus=bus,
        ledger_dir=tmp_path,
        session_id="sess_test",
    )

    await orch.route_next()
    for _ in range(50):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    task_path = tmp_path / "sess_test" / "task_ledger.jsonl"
    progress_path = tmp_path / "sess_test" / "progress_ledger.jsonl"
    assert task_path.exists()
    assert progress_path.exists()

    task_events = [json.loads(line)["event"] for line in task_path.read_text().splitlines() if line.strip()]
    progress_events = [json.loads(line)["event"] for line in progress_path.read_text().splitlines() if line.strip()]

    assert "dispatch_assigned" in task_events
    assert "result_persisted" in task_events
    assert "task_started" in progress_events
    assert "task_completed" in progress_events
    assert any(topic == "orchestrator.lifecycle" for topic, _ in bus.published)


@pytest.mark.asyncio
async def test_orchestrator_fail_closes_when_honors_checkpoint_missing(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-honors-missing",
            title="Defended analysis",
            description="safe",
            metadata={
                "max_retries": 0,
                "completion_contract": {
                    "mode": "honors",
                    "minimum_file_references": 1,
                },
            },
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(result="Looks polished but carried no checkpoint packet."))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_honors_missing",
    )

    await orch.route_next()
    for _ in range(50):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    assert any(
        task_id == "t-honors-missing"
        and fields.get("status") == TaskStatus.FAILED
        and "honors checkpoint" in str(fields.get("result", "")).lower()
        for task_id, fields in board.updates
    )


@pytest.mark.asyncio
async def test_orchestrator_failure_records_signature(tmp_path):
    """Failure path should emit a normalized failure signature in progress ledger."""
    board = MockTaskBoard()
    board.tasks = [Task(id="t-fail", title="Fail task", description="safe")]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(error=RuntimeError("Timeout while reading provider stream 1234567890abcdef")))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_fail",
    )

    await orch.route_next()
    for _ in range(50):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    progress_path = tmp_path / "sess_fail" / "progress_ledger.jsonl"
    assert progress_path.exists()
    rows = [json.loads(line) for line in progress_path.read_text().splitlines() if line.strip()]
    failed = [
        r
        for r in rows
        if r.get("event") in {"task_failed", "task_retry_scheduled"}
    ]
    assert failed, "Expected failure or retry event in progress ledger"
    sig = failed[0].get("failure_signature", "")
    assert "timeout while reading provider stream" in sig
    assert "<id>" in sig


@pytest.mark.asyncio
async def test_orchestrator_timeout_marks_failed_without_retry(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-timeout",
            title="Slow task",
            description="safe",
            metadata={"timeout_seconds": 0.01, "max_retries": 0},
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(result="late", delay_seconds=0.05))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_timeout",
    )

    await orch.route_next()
    for _ in range(80):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    assert any(
        task_id == "t-timeout"
        and fields.get("status") == TaskStatus.FAILED
        and "timed out" in str(fields.get("result", "")).lower()
        for task_id, fields in board.updates
    )


@pytest.mark.asyncio
async def test_orchestrator_timeout_requeues_with_retry_budget(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-timeout-retry",
            title="Slow retriable task",
            description="safe",
            metadata={"timeout_seconds": 0.01, "max_retries": 1},
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(result="late", delay_seconds=0.05))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_timeout_retry",
    )

    await orch.route_next()
    for _ in range(80):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    failed_seen = any(
        task_id == "t-timeout-retry" and fields.get("status") == TaskStatus.FAILED
        for task_id, fields in board.updates
    )
    pending_seen = any(
        task_id == "t-timeout-retry" and fields.get("status") == TaskStatus.PENDING
        for task_id, fields in board.updates
    )
    assert failed_seen
    assert pending_seen


@pytest.mark.asyncio
async def test_orchestrator_connection_error_auto_requeues_transient_failure(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-conn-retry",
            title="Transient provider failure",
            description="safe",
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(error=RuntimeError("Connection error.")))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_conn_retry",
    )

    await orch.route_next()
    for _ in range(80):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    assert any(
        task_id == "t-conn-retry" and fields.get("status") == TaskStatus.PENDING
        for task_id, fields in board.updates
    )
    task = await board.get("t-conn-retry")
    assert task is not None
    assert task.metadata["retry_count"] == 1
    assert task.metadata["max_retries"] >= 2
    assert task.metadata["last_failure_class"] == "connection_transient"
    assert task.metadata["retry_backoff_seconds"] >= 30.0


@pytest.mark.asyncio
async def test_orchestrator_long_timeout_auto_requeues_and_expands_timeout(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-long-timeout",
            title="Long timeout task",
            description="safe",
            metadata={"timeout_seconds": 0.01},
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    pool.set_runner("a1", DummyRunner(result="late", delay_seconds=0.05))

    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_long_timeout_retry",
    )
    orch._long_timeout_retry_threshold_seconds = 0.0

    await orch.route_next()
    for _ in range(80):
        if not orch._running_tasks:
            break
        await orch._collect_completed()
        await asyncio.sleep(0.01)
    await orch._collect_completed()

    assert any(
        task_id == "t-long-timeout" and fields.get("status") == TaskStatus.PENDING
        for task_id, fields in board.updates
    )
    task = await board.get("t-long-timeout")
    assert task is not None
    assert task.metadata["retry_count"] == 1
    assert task.metadata["max_retries"] >= 1
    assert task.metadata["last_failure_class"] == "long_timeout"
    assert float(task.metadata["timeout_seconds"]) > 0.01
    assert task.metadata["retry_backoff_seconds"] >= 15.0


@pytest.mark.asyncio
async def test_orchestrator_coordination_summary_detects_global_truth(tmp_path):
    agents = [
        AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
        AgentState(id="a2", name="agent-2", role=AgentRole.RESEARCHER, status=AgentStatus.IDLE),
    ]
    board = MockTaskBoard()
    pool = MockAgentPool(agents)
    bus = MockMessageBus()
    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        message_bus=bus,
        ledger_dir=tmp_path,
        session_id="sess_coord_truth",
    )
    bus.seed_message(
        Message(
            id="m1",
            from_agent="a1",
            to_agent="a2",
            subject="route-policy",
            body="Mechanism, witness, ecosystem all agree.",
            metadata={"topic": "route-policy"},
        )
    )
    bus.seed_message(
        Message(
            id="m2",
            from_agent="a2",
            to_agent="a1",
            subject="route-policy",
            body="Mechanism, witness, ecosystem all agree.",
            metadata={"topic": "route-policy"},
        )
    )

    summary = await orch.get_coordination_summary(refresh=True)

    assert summary["agent_count"] == 2
    assert summary["message_count"] == 2
    assert summary["global_truths"] == 1
    assert summary["productive_disagreements"] == 0
    assert summary["is_globally_coherent"] is True
    assert summary["global_truth_claim_keys"] == ["route-policy"]

    progress_path = tmp_path / "sess_coord_truth" / "progress_ledger.jsonl"
    rows = [json.loads(line) for line in progress_path.read_text().splitlines() if line.strip()]
    assert any(row.get("event") == "coordination_snapshot" for row in rows)


@pytest.mark.asyncio
async def test_orchestrator_coordination_summary_detects_productive_disagreement(tmp_path):
    agents = [
        AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
        AgentState(id="a2", name="agent-2", role=AgentRole.RESEARCHER, status=AgentStatus.IDLE),
    ]
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-route",
            title="route-policy",
            assigned_to="a1",
            status=TaskStatus.ASSIGNED,
            metadata={"coordination_claim_key": "route-policy"},
        )
    ]
    pool = MockAgentPool(agents)
    bus = MockMessageBus()
    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        message_bus=bus,
        ledger_dir=tmp_path,
        session_id="sess_coord_conflict",
    )
    bus.seed_message(
        Message(
            id="m1",
            from_agent="a1",
            to_agent="a2",
            subject="route-policy",
            body="Mechanism and architecture dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )
    bus.seed_message(
        Message(
            id="m2",
            from_agent="a2",
            to_agent="a1",
            subject="route-policy",
            body="Witness awareness and introspection dominate this route.",
            metadata={"topic": "route-policy"},
        )
    )

    summary = await orch.get_coordination_summary(refresh=True)

    assert summary["global_truths"] == 0
    assert summary["productive_disagreements"] == 1
    assert summary["is_globally_coherent"] is False
    assert summary["productive_disagreement_claim_keys"] == ["route-policy"]
    updated = await board.get("t-route")
    assert updated is not None
    assert updated.metadata["coordination_state"] == "uncertain"
    assert updated.metadata["coordination_review_required"] is True
    assert updated.metadata["coordination_route"] == "synthesis_review"

    progress_path = tmp_path / "sess_coord_conflict" / "progress_ledger.jsonl"
    rows = [json.loads(line) for line in progress_path.read_text().splitlines() if line.strip()]
    assert any(row.get("event") == "coordination_disagreement" for row in rows)


@pytest.mark.asyncio
async def test_route_next_skips_retry_backoff_tasks(agents):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-backoff",
            title="Wait",
            metadata={"retry_not_before_epoch": time.time() + 60},
        ),
        Task(id="t-ready", title="Ready now"),
    ]
    pool = MockAgentPool(agents[:1])
    orch = Orchestrator(task_board=board, agent_pool=pool)

    dispatches = await orch.route_next()
    assert len(dispatches) == 1
    assert dispatches[0].task_id == "t-ready"


@pytest.mark.asyncio
async def test_dispatch_dropoff_requeues_once_when_runner_missing(tmp_path):
    board = MockTaskBoard()
    board.tasks = [
        Task(
            id="t-dropoff",
            title="No runner",
            metadata={"max_retries": 1},
        )
    ]
    pool = MockAgentPool(
        [AgentState(id="a1", name="agent-1", role=AgentRole.GENERAL, status=AgentStatus.IDLE)]
    )
    orch = Orchestrator(
        task_board=board,
        agent_pool=pool,
        ledger_dir=tmp_path,
        session_id="sess_dropoff",
    )

    await orch.route_next()
    await orch._collect_completed()

    assert any(
        task_id == "t-dropoff" and fields.get("status") == TaskStatus.PENDING
        for task_id, fields in board.updates
    )
