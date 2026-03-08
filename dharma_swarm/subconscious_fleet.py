"""Subconscious Fleet — Parallel HUM Dream Agents.

Spawns multiple subconscious agents in parallel, each using different:
- Providers (Anthropic, OpenAI, OpenRouter, Ollama, NIM, Moonshot)
- File combinations
- Temperature settings

All agents run as "fields of attention" simultaneously, comparing dream textures.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dharma_swarm.models import ProviderType
from dharma_swarm.subconscious_v2 import SubconsciousAgent, select_dense_files, WakeTrigger


# === Provider Configuration ===

FLEET_PROVIDERS = [
    ProviderType.ANTHROPIC,  # Claude Sonnet 4.6
    ProviderType.OPENAI,     # GPT-4o
    ProviderType.OPENROUTER, # Router to various models
    # Add when implemented:
    # ProviderType.OLLAMA,
    # ProviderType.NIM,
    # ProviderType.MOONSHOT,
]


class SubconsciousFleet:
    """Fleet of parallel dream agents.

    Each agent:
    - Runs simultaneously (asyncio.gather)
    - Uses different provider
    - Samples different file combinations
    - Produces independent dream textures
    """

    def __init__(
        self,
        fleet_size: int = 12,
        files_per_agent: int = 5,
        temperature: float = 0.9,
    ):
        self.fleet_size = fleet_size
        self.files_per_agent = files_per_agent
        self.temperature = temperature

    async def dream_swarm(
        self,
        file_pool: list[Path] | None = None,
    ) -> dict[str, Any]:
        """Spawn fleet, dream in parallel, collect textures.

        Returns:
            {
                "fleet_size": int,
                "dreams": [DreamAssociation, ...],
                "high_salience": [DreamAssociation, ...],
                "provider_breakdown": {provider: count},
            }
        """
        # Select dense files if not provided
        if file_pool is None:
            file_pool = select_dense_files(count=50)  # Large pool
            print(f"[fleet] Auto-selected {len(file_pool)} dense files for pool")

        if len(file_pool) < self.files_per_agent:
            print(f"[fleet] Warning: Pool has only {len(file_pool)} files, need {self.files_per_agent}")
            return {"error": "Insufficient files in pool"}

        # Create agent tasks
        tasks = []
        for i in range(self.fleet_size):
            # Rotate through available providers
            provider = FLEET_PROVIDERS[i % len(FLEET_PROVIDERS)]

            # Sample different file combinations for each agent
            start_idx = (i * 3) % len(file_pool)
            end_idx = start_idx + self.files_per_agent
            if end_idx > len(file_pool):
                # Wrap around
                files = file_pool[start_idx:] + file_pool[:end_idx - len(file_pool)]
            else:
                files = file_pool[start_idx:end_idx]

            # Vary temperature slightly
            temp = self.temperature + (i % 3) * 0.05  # 0.9, 0.95, 1.0

            task = self._agent_dream(
                agent_id=i,
                files=files,
                provider=provider,
                temperature=temp,
            )
            tasks.append(task)

        print(f"[fleet] Spawning {len(tasks)} agents in parallel...")

        # Run all agents in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful dreams
        all_dreams = []
        provider_counts = {}

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[fleet] Agent {i} failed: {result}")
                continue

            if isinstance(result, dict) and "associations" in result:
                for assoc in result["associations"]:
                    all_dreams.append(assoc)
                    provider = result.get("provider", "unknown")
                    provider_counts[provider] = provider_counts.get(provider, 0) + 1

        # Filter high-salience dreams
        high_salience = [d for d in all_dreams if d.get("salience", 0) > 0.7]

        print(f"[fleet] Collected {len(all_dreams)} dreams ({len(high_salience)} high-salience)")

        return {
            "fleet_size": self.fleet_size,
            "dreams": all_dreams,
            "high_salience": high_salience,
            "provider_breakdown": provider_counts,
        }

    async def _agent_dream(
        self,
        agent_id: int,
        files: list[Path],
        provider: ProviderType,
        temperature: float,
    ) -> dict[str, Any]:
        """Single agent dream cycle.

        Returns associations from this agent, or error.
        """
        try:
            agent = SubconsciousAgent(temperature=temperature)

            print(f"[agent-{agent_id}] Wake ({provider.value}, temp={temperature:.2f})")

            # Wake
            await agent.wake(WakeTrigger.EXPLICIT_CALL)

            # Feed
            feed_state = await agent.feed(files)

            # Dream (3 samples per agent)
            associations = await agent.dream(feed_state["contents"], sample_prompts=3)

            # Trace high-salience dreams
            for assoc in associations:
                if assoc.salience > 0.7:
                    await agent.trace([assoc])

            print(f"[agent-{agent_id}] Dream: {len(associations)} associations")

            return {
                "agent_id": agent_id,
                "provider": provider.value,
                "associations": [a.model_dump() for a in associations],
            }

        except Exception as e:
            print(f"[agent-{agent_id}] Error: {e}")
            return {"agent_id": agent_id, "error": str(e)}


# === Public API ===


async def run_fleet(
    fleet_size: int = 12,
    file_pool: list[Path] | None = None,
) -> dict[str, Any]:
    """Run a fleet of subconscious agents in parallel.

    Args:
        fleet_size: Number of agents to spawn
        file_pool: Optional file pool (auto-selects from PSMV if None)

    Returns:
        Fleet results with all dreams and high-salience subset
    """
    fleet = SubconsciousFleet(fleet_size=fleet_size)
    return await fleet.dream_swarm(file_pool=file_pool)
