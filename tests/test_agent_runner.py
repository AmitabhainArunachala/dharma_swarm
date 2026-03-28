"""Tests for dharma_swarm.agent_runner."""

import builtins
import json
import re
from pathlib import Path
import sqlite3

import pytest
from unittest.mock import AsyncMock

from dharma_swarm.models import AgentConfig, AgentRole, AgentStatus, LLMResponse, ProviderType, Task
from dharma_swarm.agent_runner import AgentPool, AgentRunner, _build_prompt
from dharma_swarm.lineage import LineageGraph
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore
from dharma_swarm.telic_seam import TelicSeam


@pytest.fixture
def config():
    return AgentConfig(name="test-agent", role=AgentRole.CODER)


def _with_state_dir(config: AgentConfig, tmp_path: Path) -> AgentConfig:
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir(exist_ok=True)
    return config.model_copy(
        update={
            "metadata": {
                **config.metadata,
                "state_dir": str(state_dir),
                "memory_state_dir": str(state_dir),
            }
        }
    )


def _ontology_path(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir(exist_ok=True)
    return state_dir / "ontology.db"


@pytest.mark.asyncio
async def test_runner_start(config):
    runner = AgentRunner(config)
    await runner.start()
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.started_at is not None


@pytest.mark.asyncio
async def test_runner_start_registers_bus_presence_and_topics(config, tmp_path: Path):
    bus = MessageBus(tmp_path / "messages.db")
    await bus.init_db()
    runner = AgentRunner(config, message_bus=bus)

    await runner.start()

    status = await bus.get_agent_status("test-agent")
    with sqlite3.connect(tmp_path / "messages.db") as db:
        subscriptions = db.execute(
            "SELECT topic FROM subscriptions WHERE agent_id = ? ORDER BY topic",
            ("test-agent",),
        ).fetchall()

    assert status is not None
    assert status["metadata"]["runtime_agent_id"] == config.id
    assert [row[0] for row in subscriptions] == [
        "operator.bridge.lifecycle",
        "orchestrator.lifecycle",
    ]


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_runner_mock_task(config, fast_gate, tmp_path: Path):
    runner = AgentRunner(
        _with_state_dir(config, tmp_path),
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()
    task = Task(title="Write tests")
    result = await runner.run_task(task)
    assert "test-agent" in result
    assert "Write tests" in result
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.tasks_completed == 1


@pytest.mark.asyncio
async def test_runner_injects_stigmergy_recall_into_prompt(
    config,
    fast_gate,
    tmp_path: Path,
):
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="done", model="test"))
    isolated_config = _with_state_dir(config, tmp_path)
    state_dir = Path(str(isolated_config.metadata["state_dir"]))
    stig = StigmergyStore(base_path=state_dir / "stigmergy")
    await stig.leave_mark(
        StigmergicMark(
            agent="ginko-scout",
            file_path="core.py",
            action="observe",
            observation="Retry budget guard needs review before the next run.",
            salience=0.9,
        )
    )

    runner = AgentRunner(
        isolated_config,
        provider=provider,
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()

    await runner.run_task(
        Task(
            title="Inspect retry budget",
            description="Review core.py retry budget behavior before execution.",
        )
    )

    request = provider.complete.await_args.args[0]
    content = request.messages[0]["content"]
    assert "## Stigmergy Recall" in content
    assert "core.py" in content
    assert "Retry budget guard" in content

    mark_payload = json.loads((state_dir / "stigmergy" / "marks.jsonl").read_text().splitlines()[0])
    assert mark_payload["access_count"] >= 1


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
    ontology_path = _ontology_path(tmp_path)

    seam = TelicSeam(
        registry=OntologyRegistry.create_dharma_registry(),
        lineage=LineageGraph(db_path=tmp_path / "telic-lineage.db"),
        path=ontology_path,
    )
    old_seam = telic_module._SEAM
    telic_module._SEAM = seam

    try:
        named_config = _with_state_dir(
            config,
            tmp_path,
        ).model_copy(
            update={"name": "display-name", "id": "agent-stable-id"}
        )
        runner = AgentRunner(named_config, provider=provider, ontology_path=ontology_path)
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


def test_build_prompt_uses_active_memory_recall_by_default(config, monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    def _fake_memory(**kwargs):
        recorded.update(kwargs)
        return "No memory database yet."

    monkeypatch.setattr("dharma_swarm.context.read_memory_context", _fake_memory, raising=True)
    monkeypatch.setattr("dharma_swarm.context.read_latent_gold_context", lambda **_: "", raising=True)

    _build_prompt(
        Task(title="Build prompt", description="Use memory carefully"),
        _with_state_dir(config, tmp_path),
    )

    # Default mode is now "active" — semantic search enabled for richer recall
    assert recorded["allow_semantic_search"] is True


def test_build_prompt_prefers_local_state_dir_when_available(config, monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    def _fake_memory(*, state_dir=None, **kwargs):
        recorded["state_dir"] = state_dir
        recorded.update(kwargs)
        return "No memory database yet."

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dharma").mkdir()
    monkeypatch.setattr("dharma_swarm.context.read_memory_context", _fake_memory, raising=True)
    monkeypatch.setattr("dharma_swarm.context.read_latent_gold_context", lambda **_: "", raising=True)

    _build_prompt(Task(title="Build prompt", description="Prefer local state"), config)

    assert recorded["state_dir"] == tmp_path / ".dharma"


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
async def test_runner_without_state_dir_skips_shared_memory_surfaces(
    config,
    fast_gate,
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: pytest.fail("shared prompt memory should not be consulted"),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_context",
        lambda **_: pytest.fail("latent gold should not be consulted without isolated state"),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.engine.conversation_memory.ConversationMemoryStore",
        lambda *_args, **_kwargs: pytest.fail(
            "shared conversation memory should not be initialized without isolated state"
        ),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.engine.retrieval_feedback.RetrievalFeedbackStore",
        lambda *_args, **_kwargs: pytest.fail(
            "shared retrieval feedback should not be initialized without isolated state"
        ),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.agent_registry.get_registry",
        lambda *_args, **_kwargs: pytest.fail(
            "shared agent registry should not be initialized without isolated state"
        ),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.telic_seam.get_seam",
        lambda *_args, **_kwargs: pytest.fail(
            "shared telic seam should not be initialized without isolated state"
        ),
        raising=True,
    )

    runner = AgentRunner(config)
    await runner.start()

    result = await runner.run_task(Task(title="No shared state"))

    assert "No shared state" in result
    assert runner.state.tasks_completed == 1


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_runner_provider_error_string_marks_failure(config, fast_gate, tmp_path: Path):
    isolated_config = _with_state_dir(config, tmp_path)
    for text in ("ERROR: upstream unavailable", "API Error: Unable to connect to API (ENOTFOUND)"):
        provider = AsyncMock()
        provider.complete = AsyncMock(
            return_value=LLMResponse(content=text, model="test"),
        )

        runner = AgentRunner(
            isolated_config,
            provider=provider,
            ontology_path=_ontology_path(tmp_path),
        )
        await runner.start()

        with pytest.raises(RuntimeError, match=re.escape(text)):
            await runner.run_task(Task(title="Failing task"))

        assert runner.state.status == AgentStatus.IDLE
        assert runner.state.tasks_completed == 0
        assert text in (runner.state.error or "")


@pytest.mark.asyncio
async def test_runner_blocks_harmful_task_before_provider_call(config):
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
async def test_runner_fails_closed_for_tooling_task_on_api_only_provider(
    config,
    fast_gate,
    tmp_path: Path,
):
    isolated_config = _with_state_dir(
        config.model_copy(update={"provider": ProviderType.OLLAMA}),
        tmp_path,
    )
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="pretend success", model="test"))
    runner = AgentRunner(
        isolated_config,
        provider=provider,
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()

    with pytest.raises(RuntimeError, match="cannot execute local tooling task"):
        await runner.run_task(
            Task(
                title="Write artifact",
                description="Run pytest and write the report file",
                metadata={"target_file": str(tmp_path / "report.md")},
            )
        )

    provider.complete.assert_not_awaited()
    assert runner.state.tasks_completed == 0


@pytest.mark.asyncio
async def test_runner_auto_executes_tool_loop_for_api_provider_shell_task(
    config,
    fast_gate,
    tmp_path: Path,
):
    isolated_config = _with_state_dir(
        config.model_copy(
            update={
                "provider": ProviderType.OPENROUTER,
                "metadata": {
                    **config.metadata,
                    "working_dir": str(tmp_path),
                },
            }
        ),
        tmp_path,
    )
    target = tmp_path / "report.md"
    provider = AsyncMock()

    async def _complete(request):
        call_index = provider.complete.await_count
        if call_index == 1:
            assert request.tools, "tool-capable API providers should receive tool definitions"
            return LLMResponse(
                content="",
                model="test-openrouter",
                tool_calls=[
                    {
                        "id": "call-shell-1",
                        "name": "shell_exec",
                        "parameters": {
                            "command": f"printf 'hello from api lane\\n' > {target.name}",
                            "timeout": 10,
                        },
                    }
                ],
                stop_reason="tool_calls",
            )

        tool_messages = [msg for msg in request.messages if msg.get("role") == "tool"]
        assert tool_messages, "tool loop should append tool results before the next turn"
        return LLMResponse(
            content="artifact created",
            model="test-openrouter",
            stop_reason="stop",
        )

    provider.complete = AsyncMock(side_effect=_complete)
    runner = AgentRunner(
        isolated_config,
        provider=provider,
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()

    result = await runner.run_task(
        Task(
            title="Write artifact",
            description="Run a shell command and create the report file",
            metadata={"target_file": str(target)},
        )
    )

    assert result == "artifact created"
    assert target.read_text(encoding="utf-8") == "hello from api lane\n"
    assert runner.state.tasks_completed == 1
    assert provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_runner_requires_declared_artifact_before_completion(
    config,
    fast_gate,
    tmp_path: Path,
):
    isolated_config = _with_state_dir(
        config.model_copy(update={"provider": ProviderType.CLAUDE_CODE}),
        tmp_path,
    )
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="done", model="test"))
    runner = AgentRunner(
        isolated_config,
        provider=provider,
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()

    with pytest.raises(RuntimeError, match="Completion contract failed"):
        await runner.run_task(
            Task(
                title="Write artifact",
                description="Create the declared artifact",
                metadata={"target_file": str(tmp_path / "missing.md")},
            )
        )

    provider.complete.assert_awaited_once()
    assert runner.state.tasks_completed == 0


@pytest.mark.asyncio
async def test_runner_accepts_completion_when_declared_artifact_exists(
    config,
    fast_gate,
    tmp_path: Path,
):
    isolated_config = _with_state_dir(
        config.model_copy(update={"provider": ProviderType.CLAUDE_CODE}),
        tmp_path,
    )
    target = tmp_path / "report.md"
    target.write_text("ready", encoding="utf-8")
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="artifact ready", model="test"))
    runner = AgentRunner(
        isolated_config,
        provider=provider,
        ontology_path=_ontology_path(tmp_path),
    )
    await runner.start()

    result = await runner.run_task(
        Task(
            title="Use existing artifact",
            description="Artifact should satisfy completion contract",
            metadata={"target_file": str(target)},
        )
    )

    assert result == "artifact ready"
    assert runner.state.tasks_completed == 1


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
async def test_pool_spawn_registers_runtime_fields(tmp_path: Path):
    pool = AgentPool()
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir()
    config = AgentConfig(
        name="worker-rt",
        role=AgentRole.GENERAL,
        system_prompt="Act carefully.",
        metadata={
            "state_dir": str(state_dir),
            "memory_state_dir": str(state_dir),
            "optimizable_fields": [
                "system_prompt",
                {"name": "style", "path": "metadata['prompt_style']"},
            ],
            "prompt_style": "precise",
        },
    )

    runner = await pool.spawn(config)

    assert runner.runtime_fields.names() == ["system_prompt", "style"]

    manifest_path = state_dir / "ginko" / "agents" / "worker-rt" / "runtime_fields.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [field["name"] for field in manifest["fields"]] == ["system_prompt", "style"]


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
