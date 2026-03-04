#!/usr/bin/env python3
"""Live fan-out test — 3 agents, 3 tasks, parallel execution via OpenRouter."""

import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dharma_swarm.models import AgentRole, ProviderType, TaskPriority
from dharma_swarm.swarm import SwarmManager


async def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        swarm = SwarmManager(state_dir=tmpdir)
        await swarm.init()

        # Spawn 3 agents
        agents = []
        for name, role in [
            ("coder-1", AgentRole.CODER),
            ("reviewer-1", AgentRole.REVIEWER),
            ("researcher-1", AgentRole.RESEARCHER),
        ]:
            a = await swarm.spawn_agent(
                name=name, role=role,
                model="anthropic/claude-sonnet-4",
                provider_type=ProviderType.OPENROUTER,
            )
            agents.append(a)
            print(f"Spawned: {a.name} ({a.role.value})")

        # Create 3 tasks
        tasks = []
        for title, desc in [
            ("Explain recursion", "In exactly 2 sentences, explain recursion to a 10-year-old."),
            ("Name 3 dharmic principles", "List exactly 3 dharmic principles. One line each."),
            ("Write a function signature", "Write a Python function signature (just the def line) for an async function that checks if an agent is healthy."),
        ]:
            t = await swarm.create_task(title=title, description=desc)
            tasks.append(t)
            print(f"Task: {t.title}")

        # Fan out: assign each task to each agent, run in parallel
        print("\n--- Fan-out: 3 agents x 3 tasks in parallel ---")
        t0 = time.monotonic()

        async def run_one(agent_state, task):
            runner = await swarm._agent_pool.get(agent_state.id)
            return await runner.run_task(task)

        results = await asyncio.gather(
            run_one(agents[0], tasks[0]),
            run_one(agents[1], tasks[1]),
            run_one(agents[2], tasks[2]),
        )

        elapsed = time.monotonic() - t0
        print(f"\n--- All 3 completed in {elapsed:.1f}s ---\n")

        for agent, task, result in zip(agents, tasks, results):
            print(f"[{agent.name}] {task.title}:")
            print(f"  {result.strip()}\n")

        # Store results in memory
        await swarm.remember(f"Fan-out test completed: 3 tasks in {elapsed:.1f}s")
        memories = await swarm.recall(limit=5)
        print(f"Memories stored: {len(memories)}")

        await swarm.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
