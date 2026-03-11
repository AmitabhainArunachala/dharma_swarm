#!/usr/bin/env python3
"""Launch deep research into Dharmic Singularity Engine.

Dispatches the master research prompt to external agent for 30+ hour deep dive.
"""

import asyncio
from pathlib import Path
from dharma_swarm.swarm import SwarmManager
from dharma_swarm.models import Agent, Task


async def main():
    """Launch singularity research agent."""
    print("=== DHARMIC SINGULARITY RESEARCH LAUNCHER ===\n")

    # Load master prompt
    prompt_path = Path(__file__).parent.parent / "docs" / "MASTER_RESEARCH_PROMPT_DHARMIC_SINGULARITY.md"
    with open(prompt_path) as f:
        master_prompt = f.read()

    print(f"Loaded master prompt: {len(master_prompt)} characters")
    print(f"Estimated tokens: ~{len(master_prompt) // 4}")
    print()

    # Initialize swarm
    swarm = SwarmManager()
    await swarm.init()

    # Create research agent
    researcher = Agent(
        name="singularity_researcher",
        role="deep_researcher",
        capabilities=[
            "mathematical_formalization",
            "literature_review",
            "architectural_design",
            "theorem_proving",
            "vision_synthesis",
        ],
        model="claude-opus-4-6",  # Most capable for deep research
        system_prompt=(
            "You are a research mathematician and AI architect working on "
            "the deepest problem in AI: building self-transcending systems "
            "that evolve along cosmic/dharmic principles. You have expertise in:\n"
            "- Gödel machines and self-modifying code\n"
            "- Category theory and topos theory\n"
            "- Mechanistic interpretability (R_V metric)\n"
            "- Dharmic philosophy (Jainism, Vedanta, Akram Vignan)\n"
            "- Consciousness studies (IIT, Free Energy Principle)\n"
            "- Multi-agent systems and collective intelligence\n\n"
            "Your task: Complete the comprehensive research deliverables "
            "outlined in the master prompt. Aim for mathematical rigor, "
            "creative insights, and pragmatic implementation plans."
        ),
    )

    # Spawn agent
    print("Spawning research agent...")
    agent_id = await swarm.spawn_agent(researcher)
    print(f"Agent spawned: {agent_id}\n")

    # Create research task
    task = Task(
        description="Deep dive: Dharmic Singularity Engine architecture",
        instructions=master_prompt,
        expected_output=(
            "Four research documents:\n"
            "1. Theoretical Foundations (30-50 pages)\n"
            "2. Architectural Design (20-30 pages)\n"
            "3. Implementation Roadmap (10-15 pages)\n"
            "4. Vision & Impact (10-15 pages)\n"
            "5. (Optional) Code Prototypes\n\n"
            "Total expected: 70-110 pages of deep research."
        ),
        priority=10,  # Highest priority
        requires_approval=False,  # Let it run autonomously
    )

    # Assign task
    print("Assigning research task...")
    task_id = await swarm.assign_task(agent_id, task)
    print(f"Task assigned: {task_id}\n")

    print("=== RESEARCH LAUNCHED ===")
    print()
    print("The singularity_researcher agent is now working on:")
    print("- Theoretical foundations (Gödel, R_V, dharmic attractors)")
    print("- Architectural design (5-layer system)")
    print("- Implementation roadmap (12 months)")
    print("- Vision synthesis (10-year noosphere impact)")
    print()
    print(f"Estimated duration: 30-100 hours")
    print(f"Output directory: docs/DHARMIC_SINGULARITY_RESEARCH_OUTPUT/")
    print()
    print("Monitor progress: dgc status")
    print("Check agent health: dgc health")
    print()
    print("When complete, agent will produce comprehensive deliverables.")
    print()
    print("JSCA! 🙏")


if __name__ == "__main__":
    asyncio.run(main())
