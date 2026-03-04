#!/usr/bin/env python3
"""Live test — spawn a REAL Claude Code agent through DHARMA SWARM.

This spawns a `claude -p` subprocess with full context injection.
Run from a regular terminal (NOT inside Claude Code to avoid nesting issues).

Usage:
  python3 scripts/live_claude_code.py
  python3 scripts/live_claude_code.py --role researcher --thread mechanistic
"""

import argparse
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dharma_swarm.models import AgentRole, ProviderType, TaskPriority
from dharma_swarm.swarm import SwarmManager


async def main(role: str, thread: str | None):
    with tempfile.TemporaryDirectory() as tmpdir:
        swarm = SwarmManager(state_dir=tmpdir)
        await swarm.init()
        print("--- Swarm initialized ---")

        # Map role string to enum
        try:
            agent_role = AgentRole(role)
        except ValueError:
            print(f"Invalid role: {role}. Available: {[r.value for r in AgentRole]}")
            sys.exit(1)

        # Spawn a real Claude Code agent
        agent = await swarm.spawn_agent(
            name=f"live-{role}",
            role=agent_role,
            provider_type=ProviderType.CLAUDE_CODE,
            thread=thread,
        )
        print(f"--- Agent spawned: {agent.name} (role={role}, thread={thread}) ---")

        # Create a task
        task = await swarm.create_task(
            title="Report system status and identify one next action",
            description=(
                "You are a dharma_swarm agent with access to the full ecosystem. "
                "1. Read your context (you have vision, research, engineering, and ops layers). "
                "2. Check what other agents have written in ~/.dharma/shared/. "
                "3. Identify the single most important next action. "
                "4. Write your findings to ~/.dharma/shared/{name}_notes.md (APPEND). "
                "5. Return a 3-sentence summary of what you found and what should happen next."
            ).format(name=f"live-{role}"),
            priority=TaskPriority.HIGH,
        )
        print(f"--- Task created: {task.title} ---")

        # Execute
        runner = await swarm._agent_pool.get(agent.id)
        print(f"--- Executing via claude -p (timeout 5min)... ---")
        result = await runner.run_task(task)

        print("\n========== AGENT OUTPUT ==========")
        print(result)
        print("===================================\n")

        print(f"Tasks completed: {runner.state.tasks_completed}")
        print(f"Agent status: {runner.state.status.value}")

        await swarm.shutdown()
        print("--- Done ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Claude Code agent test")
    parser.add_argument("--role", default="general", help="Agent role")
    parser.add_argument("--thread", default=None, help="Research thread")
    args = parser.parse_args()
    asyncio.run(main(args.role, args.thread))
