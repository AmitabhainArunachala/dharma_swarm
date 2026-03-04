"""Tests for dharma_swarm.orchestrator."""

import pytest

from dharma_swarm.models import AgentState, AgentRole, AgentStatus, Task, TopologyType
from dharma_swarm.orchestrator import Orchestrator


class MockTaskBoard:
    def __init__(self):
        self.tasks = []
        self.updates = []

    async def get_ready_tasks(self):
        return [t for t in self.tasks if t.status.value == "pending"]

    async def update_task(self, task_id, **fields):
        self.updates.append((task_id, fields))


class MockAgentPool:
    def __init__(self, agents=None):
        self._agents = agents or []
        self._results = {}
        self._assignments = []

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

    await orch.tick()
    # Should have dispatched
    assert len(pool._assignments) > 0


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
