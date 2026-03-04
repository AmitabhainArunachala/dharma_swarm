#!/usr/bin/env python3
"""Live integration test — real LLM call through DHARMA SWARM.

Spawns an agent via OpenRouter, creates a task, dispatches it, prints the result.
Requires OPENROUTER_API_KEY to be set.
"""

import asyncio
import os
import sys
import tempfile

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dharma_swarm.models import AgentRole, ProviderType, TaskPriority
from dharma_swarm.swarm import SwarmManager


async def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Use a temp directory so we don't pollute anything
    with tempfile.TemporaryDirectory() as tmpdir:
        swarm = SwarmManager(state_dir=tmpdir)
        await swarm.init()
        print("--- Swarm initialized ---")

        # Spawn a real agent with OpenRouter provider
        agent = await swarm.spawn_agent(
            name="dharma-1",
            role=AgentRole.CODER,
            model="anthropic/claude-sonnet-4",
            provider_type=ProviderType.OPENROUTER,
        )
        print(f"--- Agent spawned: {agent.name} ({agent.id[:8]}) ---")

        # Create a task
        task = await swarm.create_task(
            title="Write a haiku about self-evolving AI",
            description="Write a single haiku (5-7-5) about an AI that improves itself. Return only the haiku.",
            priority=TaskPriority.NORMAL,
        )
        print(f"--- Task created: {task.title} ({task.id[:8]}) ---")

        # Get the runner and execute directly
        runner = await swarm._agent_pool.get(agent.id)
        print("--- Calling LLM via OpenRouter... ---")
        result = await runner.run_task(task)

        print("\n========== LLM RESPONSE ==========")
        print(result)
        print("===================================\n")

        # Show final status
        status = await swarm.status()
        print(f"Tasks completed: {runner.state.tasks_completed}")
        print(f"Agent status: {runner.state.status.value}")

        await swarm.shutdown()
        print("--- Swarm shut down ---")


if __name__ == "__main__":
    asyncio.run(main())
