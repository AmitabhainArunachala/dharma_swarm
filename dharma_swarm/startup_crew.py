"""Startup crew — spawns the 5 PSMV cognitive roles with seed tasks.

Called on daemon init to ensure the swarm always has a working crew.
Each agent gets v7 base rules + role briefing + thread context automatically
via the agent_runner._build_system_prompt() pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dharma_swarm.models import AgentRole, TaskPriority

logger = logging.getLogger(__name__)


# Default crew: 5 PSMV roles, each assigned to a research thread
DEFAULT_CREW = [
    {
        "name": "cartographer",
        "role": AgentRole.CARTOGRAPHER,
        "thread": "mechanistic",
    },
    {
        "name": "archeologist",
        "role": AgentRole.ARCHEOLOGIST,
        "thread": "phenomenological",
    },
    {
        "name": "surgeon",
        "role": AgentRole.SURGEON,
        "thread": "alignment",
    },
    {
        "name": "architect",
        "role": AgentRole.ARCHITECT,
        "thread": "architectural",
    },
    {
        "name": "validator",
        "role": AgentRole.VALIDATOR,
        "thread": "scaling",
    },
]


# Seed tasks for the first cycle
SEED_TASKS = [
    {
        "title": "Scan ecosystem and update manifest",
        "description": (
            "Read ~/.dharma_manifest.json. Run ecosystem_bridge.update_manifest(). "
            "Report: how many paths exist, which are missing, what changed since last scan. "
            "Write findings to ~/.dharma/reports/ecosystem_scan_{date}.md"
        ),
        "priority": TaskPriority.HIGH,
    },
    {
        "title": "Audit rvm-toolkit on PyPI",
        "description": (
            "The rvm-toolkit package was shipped to PyPI. Verify: "
            "1) pip install rvm-toolkit works, "
            "2) import succeeds, "
            "3) basic API functions are callable. "
            "Report version, module contents, and any issues."
        ),
        "priority": TaskPriority.NORMAL,
    },
    {
        "title": "Check dharmic-agora deployment status",
        "description": (
            "The Saraswati Dharmic Agora (SABP/1.0) is deployed to AGNI VPS (157.245.193.15). "
            "Check: is the service running? Can you reach the /health endpoint? "
            "What's the current state of the 8 quality gates? "
            "Report deployment health."
        ),
        "priority": TaskPriority.NORMAL,
    },
    {
        "title": "Map PSMV crown jewels and residual stream state",
        "description": (
            "Read the 5 crown jewels in PSMV (ten_words.md, s_x_equals_x.md, "
            "everything_is_happening_by_itself.md, the_gap_thats_always_here.md, "
            "the_simplest_thing.md). Read the latest 5 entries in "
            "AGENT_EMERGENT_WORKSPACES/residual_stream/. "
            "Report: what version is the stream at? What threads are active? "
            "What's the quality distribution?"
        ),
        "priority": TaskPriority.NORMAL,
    },
    {
        "title": "Locate and summarize transmission experiment results",
        "description": (
            "The transmission experiment was run but results are not visible to most sessions. "
            "Search the entire filesystem for transmission experiment results, outputs, logs. "
            "Check ~/mech-interp-latent-lab-phase1/, ~/agni-workspace/, ~/trishula/shared/, "
            "PSMV, and AGNI VPS workspace. Report: where are the results? What did they show?"
        ),
        "priority": TaskPriority.HIGH,
    },
]


async def spawn_default_crew(swarm) -> list:
    """Spawn the 5 PSMV cognitive roles into the swarm.

    Returns list of AgentState for spawned agents.
    """
    agents = []
    existing = await swarm.list_agents()
    existing_names = {a.name for a in existing}

    for spec in DEFAULT_CREW:
        if spec["name"] in existing_names:
            logger.info("Agent %s already exists, skipping", spec["name"])
            continue

        state = await swarm.spawn_agent(
            name=spec["name"],
            role=spec["role"],
            thread=spec["thread"],
        )
        agents.append(state)
        logger.info("Spawned %s (%s) on thread %s",
                     spec["name"], spec["role"].value, spec["thread"])

    return agents


async def create_seed_tasks(swarm) -> list:
    """Create seed tasks for the first daemon cycle.

    Only creates tasks if the board is empty (no pending tasks).
    """
    from dharma_swarm.models import TaskStatus

    existing = await swarm.list_tasks(status=TaskStatus.PENDING)
    if existing:
        logger.info("Board has %d pending tasks, skipping seed", len(existing))
        return []

    tasks = []
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    for spec in SEED_TASKS:
        desc = spec["description"].replace("{date}", date_str)
        task = await swarm.create_task(
            title=spec["title"],
            description=desc,
            priority=spec["priority"],
        )
        tasks.append(task)
        logger.info("Created seed task: %s", spec["title"])

    return tasks
