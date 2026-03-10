from __future__ import annotations

import pytest

from dharma_swarm.models import AgentRole, ProviderType
from dharma_swarm.providers import ModelRouter
from dharma_swarm.swarm import SwarmManager


@pytest.mark.asyncio
async def test_spawn_agent_uses_shared_model_router(tmp_path) -> None:
    swarm = SwarmManager(state_dir=tmp_path / ".dharma")
    await swarm.init()
    try:
        state = await swarm.spawn_agent(
            "router-worker",
            role=AgentRole.CODER,
            model="gpt-4.1",
            provider_type=ProviderType.OPENAI,
        )
        runner = await swarm._agent_pool.get(state.id)

        assert runner is not None
        assert isinstance(runner._provider, ModelRouter)
        assert runner._config.provider == ProviderType.OPENAI
    finally:
        await swarm.shutdown()
