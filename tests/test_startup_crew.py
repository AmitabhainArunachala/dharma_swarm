"""Quality-track tests for dharma_swarm.startup_crew."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

import dharma_swarm.startup_crew as sc
from dharma_swarm.models import AgentRole, ProviderType, TaskPriority, TaskStatus


@dataclass
class _AgentStateStub:
    name: str


class _FakeSwarm:
    def __init__(self, existing_names: list[str] | None = None, pending_tasks: int = 0) -> None:
        self._existing = [_AgentStateStub(name=n) for n in (existing_names or [])]
        self.spawn_calls: list[dict] = []
        self.create_calls: list[dict] = []
        self.create_batch_calls: list[list[dict]] = []
        self._pending_tasks = pending_tasks

    async def list_agents(self):
        return list(self._existing)

    async def spawn_agent(self, **kwargs):
        self.spawn_calls.append(kwargs)
        return _AgentStateStub(name=kwargs["name"])

    async def list_tasks(self, status=None):
        if status == TaskStatus.PENDING:
            return [object()] * self._pending_tasks
        return []

    async def create_task(self, **kwargs):
        self.create_calls.append(kwargs)
        return kwargs

    async def create_task_batch(self, specs):
        self.create_batch_calls.append(list(specs))
        for spec in specs:
            self.create_calls.append(spec)
        return list(specs)


class _ConcurrentSwarm(_FakeSwarm):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()
        self.inflight = 0
        self.max_inflight = 0

    async def spawn_agent(self, **kwargs):
        self.spawn_calls.append(kwargs)
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        await asyncio.sleep(0)
        await self.release.wait()
        self.inflight -= 1
        return _AgentStateStub(name=kwargs["name"])


def _effective_crew() -> list[dict]:
    """Return the crew that spawn_default_crew would actually use."""
    return sc._crew_from_skills() or sc.DEFAULT_CREW


@pytest.mark.asyncio
async def test_spawn_default_crew_spawns_all_when_none_exist():
    swarm = _FakeSwarm(existing_names=[])
    spawned = await sc.spawn_default_crew(swarm)
    expected = len(_effective_crew())

    assert len(spawned) == expected
    assert len(swarm.spawn_calls) == expected


@pytest.mark.asyncio
async def test_spawn_default_crew_skips_existing_names():
    crew = _effective_crew()
    existing = [crew[0]["name"], crew[2]["name"]]
    swarm = _FakeSwarm(existing_names=existing)

    await sc.spawn_default_crew(swarm)
    spawned_names = {c["name"] for c in swarm.spawn_calls}
    assert not spawned_names.intersection(existing)
    assert len(swarm.spawn_calls) == len(crew) - len(existing)


@pytest.mark.asyncio
async def test_spawn_default_crew_passes_provider_and_model_from_spec(monkeypatch):
    monkeypatch.setattr(sc, "_crew_from_skills", lambda: None)
    swarm = _FakeSwarm()
    await sc.spawn_default_crew(swarm)

    first = sc.DEFAULT_CREW[0]
    first_call = next(c for c in swarm.spawn_calls if c["name"] == first["name"])
    assert first_call["provider_type"] == first["provider"]
    assert first_call["model"] == first["model"]
    assert "MEMORY SURVIVAL INSTINCT" in first_call["system_prompt"]


@pytest.mark.asyncio
async def test_spawn_default_crew_defaults_provider_and_model_when_missing(monkeypatch):
    custom = [{"name": "x", "role": AgentRole.GENERAL, "thread": "mechanistic"}]
    monkeypatch.setattr(sc, "DEFAULT_CREW", custom)
    monkeypatch.setattr(sc, "_crew_from_skills", lambda: None)
    swarm = _FakeSwarm()

    await sc.spawn_default_crew(swarm)
    assert len(swarm.spawn_calls) == 1
    assert swarm.spawn_calls[0]["provider_type"] == ProviderType.CLAUDE_CODE
    assert swarm.spawn_calls[0]["model"] == "claude-code"
    assert "MEMORY SURVIVAL INSTINCT" in swarm.spawn_calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_spawn_default_crew_merges_existing_system_prompt(monkeypatch):
    custom = [{
        "name": "x",
        "role": AgentRole.GENERAL,
        "thread": "mechanistic",
        "provider": ProviderType.CLAUDE_CODE,
        "model": "claude-code",
        "system_prompt": "CUSTOM BASE",
    }]
    monkeypatch.setattr(sc, "DEFAULT_CREW", custom)
    monkeypatch.setattr(sc, "_crew_from_skills", lambda: None)
    swarm = _FakeSwarm()

    await sc.spawn_default_crew(swarm)
    prompt = swarm.spawn_calls[0]["system_prompt"]
    assert "CUSTOM BASE" in prompt
    assert "MEMORY SURVIVAL INSTINCT" in prompt


@pytest.mark.asyncio
async def test_spawn_default_crew_spawns_in_parallel(monkeypatch):
    custom = [
        {"name": "a", "role": AgentRole.GENERAL, "thread": "mechanistic"},
        {"name": "b", "role": AgentRole.GENERAL, "thread": "mechanistic"},
        {"name": "c", "role": AgentRole.GENERAL, "thread": "mechanistic"},
    ]
    monkeypatch.setattr(sc, "DEFAULT_CREW", custom)
    monkeypatch.setattr(sc, "_crew_from_skills", lambda: None)
    swarm = _ConcurrentSwarm()

    task = asyncio.create_task(sc.spawn_default_crew(swarm))
    for _ in range(20):
        if swarm.max_inflight > 1:
            break
        await asyncio.sleep(0)

    assert swarm.max_inflight > 1

    swarm.release.set()
    await task


@pytest.mark.asyncio
async def test_spawn_cybernetics_crew_spawns_all_when_none_exist():
    swarm = _FakeSwarm(existing_names=[])

    spawned = await sc.spawn_cybernetics_crew(swarm)

    assert len(spawned) == len(sc.CYBERNETICS_CREW)
    assert len(swarm.spawn_calls) == len(sc.CYBERNETICS_CREW)


@pytest.mark.asyncio
async def test_spawn_cybernetics_crew_skips_existing_names():
    existing = ["cyber-glm5", "cyber-codex"]
    swarm = _FakeSwarm(existing_names=existing)

    await sc.spawn_cybernetics_crew(swarm)

    spawned_names = {call["name"] for call in swarm.spawn_calls}
    assert spawned_names == {"cyber-kimi25", "cyber-opus"}


@pytest.mark.asyncio
async def test_spawn_cybernetics_crew_passes_provider_model_and_prompt():
    swarm = _FakeSwarm(existing_names=[])

    await sc.spawn_cybernetics_crew(swarm)

    glm_call = next(call for call in swarm.spawn_calls if call["name"] == "cyber-glm5")
    kimi_call = next(call for call in swarm.spawn_calls if call["name"] == "cyber-kimi25")
    codex_call = next(call for call in swarm.spawn_calls if call["name"] == "cyber-codex")
    opus_call = next(call for call in swarm.spawn_calls if call["name"] == "cyber-opus")

    assert glm_call["provider_type"] == ProviderType.OLLAMA
    assert glm_call["model"] == "glm-5:cloud"
    assert glm_call["thread"] == "cybernetics"
    assert "Variety Cartographer" in glm_call["system_prompt"]
    assert "MEMORY SURVIVAL INSTINCT" in glm_call["system_prompt"]

    assert kimi_call["provider_type"] == ProviderType.OLLAMA
    assert kimi_call["model"] == "kimi-k2.5:cloud"

    assert codex_call["provider_type"] == ProviderType.OLLAMA
    assert codex_call["model"] == "qwen3-coder:480b-cloud"
    assert "hot-path control improvement" in codex_call["system_prompt"]

    assert opus_call["provider_type"] == ProviderType.OLLAMA
    assert opus_call["model"] == "deepseek-v3.2:cloud"
    assert "identity and architecture seat" in opus_call["system_prompt"]


@pytest.mark.asyncio
async def test_create_seed_tasks_skips_when_pending_exist():
    swarm = _FakeSwarm(pending_tasks=2)
    tasks = await sc.create_seed_tasks(swarm)
    assert tasks == []
    assert swarm.create_calls == []
    assert swarm.create_batch_calls == []


@pytest.mark.asyncio
async def test_create_seed_tasks_creates_all_when_board_empty():
    swarm = _FakeSwarm(pending_tasks=0)
    tasks = await sc.create_seed_tasks(swarm)
    assert len(tasks) == len(sc.SEED_TASKS)
    assert len(swarm.create_batch_calls) == 1
    assert len(swarm.create_calls) == len(sc.SEED_TASKS)


@pytest.mark.asyncio
async def test_create_seed_tasks_replaces_date_placeholder():
    swarm = _FakeSwarm(pending_tasks=0)
    await sc.create_seed_tasks(swarm)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    joined = "\n".join(c["description"] for c in swarm.create_calls)
    assert "{date}" not in joined
    # At least one task in current seed set should contain replaced date.
    assert date_str in joined


@pytest.mark.asyncio
async def test_create_seed_tasks_preserves_priority_values():
    swarm = _FakeSwarm(pending_tasks=0)
    await sc.create_seed_tasks(swarm)

    created_priorities = [c["priority"] for c in swarm.create_calls]
    expected_priorities = [spec["priority"] for spec in sc.SEED_TASKS]
    assert created_priorities == expected_priorities


def test_default_crew_names_are_unique():
    names = [a["name"] for a in sc.DEFAULT_CREW]
    assert len(names) == len(set(names))


def test_default_crew_roles_threads_and_provider_types_present():
    for agent in sc.DEFAULT_CREW:
        assert isinstance(agent["role"], AgentRole)
        assert isinstance(agent["thread"], str) and agent["thread"]
        assert isinstance(agent["provider"], ProviderType)
        assert isinstance(agent["model"], str) and agent["model"]


def test_cybernetics_crew_names_are_unique():
    names = [a["name"] for a in sc.CYBERNETICS_CREW]
    assert len(names) == len(set(names))


def test_cybernetics_crew_roles_threads_and_provider_types_present():
    for agent in sc.CYBERNETICS_CREW:
        assert isinstance(agent["role"], AgentRole)
        assert agent["thread"] == "cybernetics"
        assert isinstance(agent["provider"], ProviderType)
        assert isinstance(agent["model"], str) and agent["model"]
        assert isinstance(agent.get("system_prompt"), str) and agent["system_prompt"]


def test_seed_tasks_include_high_and_normal_priority():
    priorities = {t["priority"] for t in sc.SEED_TASKS}
    assert TaskPriority.HIGH in priorities
    assert TaskPriority.NORMAL in priorities


def test_seed_tasks_have_required_fields():
    for task in sc.SEED_TASKS:
        assert set(task.keys()) == {"title", "description", "priority"}
        assert task["title"]
        assert task["description"]
