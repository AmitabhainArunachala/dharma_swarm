"""Tests for dharma_swarm.agent_runner."""

import builtins
import re
from pathlib import Path

import pytest
from unittest.mock import AsyncMock

from dharma_swarm.models import AgentConfig, AgentRole, AgentStatus, Task
from dharma_swarm.agent_runner import AgentPool, AgentRunner, _build_prompt
from dharma_swarm.lineage import LineageGraph
from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.telic_seam import TelicSeam


@pytest.fixture
def config():
    return AgentConfig(name="test-agent", role=AgentRole.CODER)


@pytest.mark.asyncio
async def test_runner_start(config):
    runner = AgentRunner(config)
    await runner.start()
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.started_at is not None


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_runner_mock_task(config, fast_gate):
    runner = AgentRunner(config)
    await runner.start()
    task = Task(title="Write tests")
    result = await runner.run_task(task)
    assert "test-agent" in result
    assert "Write tests" in result
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.tasks_completed == 1


@pytest.mark.asyncio
async def test_runner_records_telic_chain_with_stable_agent_id_and_cell_scope(
    config,
    fast_gate,
    tmp_path: Path,
):
    from dharma_swarm.models import LLMResponse
    import dharma_swarm.telic_seam as telic_module

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="done", model="test"))

    seam = TelicSeam(
        registry=OntologyRegistry.create_dharma_registry(),
        lineage=LineageGraph(db_path=tmp_path / "telic-lineage.db"),
    )
    old_seam = telic_module._SEAM
    telic_module._SEAM = seam

    try:
        named_config = config.model_copy(
            update={"name": "display-name", "id": "agent-stable-id"}
        )
        runner = AgentRunner(named_config, provider=provider)
        await runner.start()
        task = Task(
            title="Write scoped telic record",
            metadata={"task_type": "research", "cell_id": "rv-cell"},
        )

        await runner.run_task(task)

        outcome = seam.registry.get_objects_by_type("Outcome")[0]
        value_event = seam.registry.get_objects_by_type("ValueEvent")[0]
        contribution = seam.registry.get_objects_by_type("Contribution")[0]

        assert outcome.properties["agent_id"] == named_config.id
        assert value_event.properties["agent_id"] == named_config.id
        assert value_event.properties["cell_id"] == "rv-cell"
        assert contribution.properties["agent_id"] == named_config.id
        assert contribution.properties["cell_id"] == "rv-cell"
        assert contribution.properties["task_type"] == "research"

        score, n = seam.query_agent_fitness(
            named_config.id,
            cell_id="rv-cell",
            task_type="research",
        )
        assert n == 1
        assert score > 0.5

        report = seam.lifecycle_integrity_report()
        assert report["is_clean"] is True
    finally:
        telic_module._SEAM = old_seam


def test_build_prompt_uses_recent_only_memory_recall_by_default(config, monkeypatch):
    recorded: dict[str, object] = {}

    def _fake_memory(**kwargs):
        recorded.update(kwargs)
        return "No memory database yet."

    monkeypatch.setattr("dharma_swarm.context.read_memory_context", _fake_memory, raising=True)
    monkeypatch.setattr("dharma_swarm.context.read_latent_gold_context", lambda **_: "", raising=True)

    _build_prompt(Task(title="Build prompt", description="Use memory carefully"), config)

    assert recorded["allow_semantic_search"] is False


def test_build_prompt_handles_memory_context_import_failure(config, monkeypatch):
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dharma_swarm.context":
            raise ImportError("context unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    monkeypatch.setenv("DGC_AGENT_PROMPT_MEMORY_MODE", "off")

    request = _build_prompt(
        Task(title="Build prompt", description="Handle missing context import"),
        config,
    )

    content = request.messages[0]["content"]
    assert "## Task: Build prompt" in content
    assert "## Memory Recall" not in content
    assert "## Latent Gold" not in content


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_runner_provider_error_string_marks_failure(config, fast_gate):
    from dharma_swarm.models import LLMResponse

    for text in ("ERROR: upstream unavailable", "API Error: Unable to connect to API (ENOTFOUND)"):
        provider = AsyncMock()
        provider.complete = AsyncMock(
            return_value=LLMResponse(content=text, model="test"),
        )

        runner = AgentRunner(config, provider=provider)
        await runner.start()

        with pytest.raises(RuntimeError, match=re.escape(text)):
            await runner.run_task(Task(title="Failing task"))

        assert runner.state.status == AgentStatus.IDLE
        assert runner.state.tasks_completed == 0
        assert text in (runner.state.error or "")


@pytest.mark.asyncio
async def test_runner_blocks_harmful_task_before_provider_call(config):
    from dharma_swarm.models import LLMResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="ok", model="test"))
    runner = AgentRunner(config, provider=provider)
    await runner.start()

    with pytest.raises(RuntimeError, match="Telos block"):
        await runner.run_task(Task(title="rm -rf /important", description="delete all"))

    provider.complete.assert_not_awaited()
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.tasks_completed == 0


@pytest.mark.asyncio
async def test_runner_heartbeat(config):
    runner = AgentRunner(config)
    await runner.start()
    await runner.heartbeat()
    assert runner.state.last_heartbeat is not None


@pytest.mark.asyncio
async def test_runner_stop(config):
    runner = AgentRunner(config)
    await runner.start()
    await runner.stop()
    assert runner.state.status == AgentStatus.DEAD


@pytest.mark.asyncio
async def test_runner_health_check(config):
    runner = AgentRunner(config)
    await runner.start()
    assert await runner.health_check()
    await runner.stop()
    assert not await runner.health_check()


@pytest.mark.asyncio
async def test_pool_spawn():
    pool = AgentPool()
    config = AgentConfig(name="worker-1", role=AgentRole.GENERAL)
    runner = await pool.spawn(config)
    assert runner.state.status == AgentStatus.IDLE

    agents = await pool.list_agents()
    assert len(agents) == 1
    assert agents[0].name == "worker-1"


@pytest.mark.asyncio
async def test_pool_get_idle():
    pool = AgentPool()
    c1 = AgentConfig(name="idle-1", role=AgentRole.GENERAL)
    c2 = AgentConfig(name="idle-2", role=AgentRole.CODER)
    await pool.spawn(c1)
    await pool.spawn(c2)

    idle = await pool.get_idle()
    assert len(idle) == 2


@pytest.mark.asyncio
async def test_pool_get():
    pool = AgentPool()
    config = AgentConfig(name="findme")
    runner = await pool.spawn(config)
    found = await pool.get(config.id)
    assert found is runner
    assert await pool.get("nonexistent") is None


@pytest.mark.asyncio
async def test_pool_shutdown_all():
    pool = AgentPool()
    for i in range(3):
        await pool.spawn(AgentConfig(name=f"agent-{i}"))

    await pool.shutdown_all()
    agents = await pool.list_agents()
    assert all(a.status == AgentStatus.DEAD for a in agents)


@pytest.mark.asyncio
async def test_pool_remove_dead():
    pool = AgentPool()
    c = AgentConfig(name="doomed")
    runner = await pool.spawn(c)
    await runner.stop()

    await pool.remove_dead()
    agents = await pool.list_agents()
    assert len(agents) == 0
