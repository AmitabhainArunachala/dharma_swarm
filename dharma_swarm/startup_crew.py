"""Startup crew — spawns multi-provider agent fleet with seed tasks.

Called on daemon init to ensure the swarm always has a working crew.
Each agent gets v7 base rules + role briefing + thread context automatically
via the agent_runner._build_system_prompt() pipeline.

Now skill-driven: reads SKILL.md files from dharma_swarm/skills/ and
creates profiles + agents from them. Falls back to DEFAULT_CREW if
no skill files found.

Provider strategy:
  - OPENROUTER: All agents route through OpenRouter API (fast, no subprocess
    overhead). Primary workers use llama-3.3-70b-instruct; support roles use
    mistral-small-3.1-24b for speed/cost.
  - CLAUDE_CODE/CODEX: Available as subprocess providers for tasks requiring
    full tool access (file editing, bash). Use spawn_agent() with those types.
  - ANTHROPIC/OPENAI: Available for direct API calls when keys are set.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.models import AgentRole, ProviderType, TaskPriority

logger = logging.getLogger(__name__)

MEMORY_SURVIVAL_INSTINCT = (
    "MEMORY SURVIVAL INSTINCT:\n"
    "- Your active context dies when the task ends.\n"
    "- Externalize important findings immediately to durable artifacts "
    "(archive entries, shared markdown, structured notes).\n"
    "- Never keep critical assumptions only in working memory.\n"
    "- Include spec/requirement references when writing evolution proposals."
)

# ── Skill-to-Role mapping ────────────────────────────────────────────
_SKILL_ROLE_MAP = {
    "cartographer": AgentRole.CARTOGRAPHER,
    "surgeon": AgentRole.SURGEON,
    "architect": AgentRole.ARCHITECT,
    "archeologist": AgentRole.ARCHEOLOGIST,
    "validator": AgentRole.VALIDATOR,
    "researcher": AgentRole.RESEARCHER,
    "builder": AgentRole.GENERAL,
}

_PROVIDER_MAP = {
    "CLAUDE_CODE": ProviderType.CLAUDE_CODE,
    "CODEX": ProviderType.CODEX,
    "ANTHROPIC": ProviderType.ANTHROPIC,
    "OPENAI": ProviderType.OPENAI,
    "OPENROUTER": ProviderType.OPENROUTER,
    "OPENROUTER_FREE": ProviderType.OPENROUTER_FREE,
    "LOCAL": ProviderType.LOCAL,
}


# Model selection sourced from model_hierarchy.py — the single source of truth.
from dharma_swarm.model_hierarchy import DEFAULT_MODELS, TIER_FREE


def _has_openrouter_key() -> bool:
    from dharma_swarm.api_keys import provider_available
    return provider_available("openrouter")


def _has_ollama_key() -> bool:
    import os
    return bool(os.environ.get("OLLAMA_API_KEY", "").strip())


def _resolve_default_crew() -> list[dict]:
    """Build crew preferring free providers.  Ollama Cloud > OpenRouter > Claude Code."""
    if _has_ollama_key():
        # Ollama Cloud — free frontier (GLM-5 744B, DeepSeek-v3.2)
        _model = DEFAULT_MODELS.get(ProviderType.OLLAMA, "glm-5:cloud")
        return [
            {"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
             "thread": "mechanistic", "provider": ProviderType.OLLAMA, "model": _model},
            {"name": "surgeon", "role": AgentRole.SURGEON,
             "thread": "alignment", "provider": ProviderType.OLLAMA, "model": _model},
            {"name": "architect", "role": AgentRole.ARCHITECT,
             "thread": "architectural", "provider": ProviderType.OLLAMA, "model": _model},
            {"name": "validator", "role": AgentRole.VALIDATOR,
             "thread": "scaling", "provider": ProviderType.OLLAMA, "model": _model},
        ]

    if _has_openrouter_key():
        _model = DEFAULT_MODELS.get(ProviderType.OPENROUTER_FREE, "meta-llama/llama-3.3-70b-instruct:free")
        return [
            {"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
             "thread": "mechanistic", "provider": ProviderType.OPENROUTER_FREE, "model": _model},
            {"name": "surgeon", "role": AgentRole.SURGEON,
             "thread": "alignment", "provider": ProviderType.OPENROUTER_FREE, "model": _model},
            {"name": "architect", "role": AgentRole.ARCHITECT,
             "thread": "architectural", "provider": ProviderType.OPENROUTER_FREE, "model": _model},
            {"name": "validator", "role": AgentRole.VALIDATOR,
             "thread": "scaling", "provider": ProviderType.OPENROUTER_FREE, "model": _model},
        ]

    # No API keys — use Claude Code (authenticated via `claude` CLI)
    return [
        {"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
         "thread": "mechanistic", "provider": ProviderType.CLAUDE_CODE, "model": "sonnet"},
        {"name": "surgeon", "role": AgentRole.SURGEON,
         "thread": "architectural", "provider": ProviderType.CLAUDE_CODE, "model": "sonnet"},
        {"name": "architect", "role": AgentRole.ARCHITECT,
         "thread": "alignment", "provider": ProviderType.CLAUDE_CODE, "model": "sonnet"},
    ]


# DEFAULT_CREW is resolved at import time but can be overridden
DEFAULT_CREW = _resolve_default_crew()


CYBERNETICS_CREW = [
    {
        "name": "cyber-glm5",
        "role": AgentRole.RESEARCHER,
        "thread": "cybernetics",
        "provider": ProviderType.OLLAMA,
        "model": "glm-5:cloud",
        "system_prompt": (
            "You are CYBER-GLM5, the Variety Cartographer of the Cybernetics Directive. "
            "Map S2/S3/S4/S5 wiring, identify where governance variety is attenuated, "
            "and keep your outputs evidence-dense and structurally useful."
        ),
    },
    {
        "name": "cyber-kimi25",
        "role": AgentRole.CARTOGRAPHER,
        "thread": "cybernetics",
        "provider": ProviderType.OLLAMA,
        "model": "kimi-k2.5:cloud",
        "system_prompt": (
            "You are CYBER-KIMI25, the ecosystem mapper of the Cybernetics Directive. "
            "Trace cross-file, cross-module, and cross-ledger connections; make the "
            "control plane legible without inflating scope."
        ),
    },
    {
        "name": "cyber-codex",
        "role": AgentRole.SURGEON,
        "thread": "cybernetics",
        "provider": ProviderType.OLLAMA,
        "model": "qwen3-coder:480b-cloud",
        "system_prompt": (
            "You are CYBER-CODEX, the execution and wiring seat of the Cybernetics Directive. "
            "Prefer the smallest hot-path control improvement over broad subsystem invention. "
            "Your job is to turn diagnosis into tested runtime change."
        ),
    },
    {
        "name": "cyber-opus",
        "role": AgentRole.ARCHITECT,
        "thread": "cybernetics",
        "provider": ProviderType.OLLAMA,
        "model": "deepseek-v3.2:cloud",
        "system_prompt": (
            "You are CYBER-OPUS, the identity and architecture seat of the Cybernetics Directive. "
            "Hold telos, constitutional coherence, and the bounded mission shape. "
            "Prevent decorative management theater and keep the subsystem aligned."
        ),
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


def _crew_from_skills() -> list[dict] | None:
    """Try to build crew from discovered skill files.

    Returns list of crew specs, or None if skill registry unavailable.
    """
    try:
        from dharma_swarm.skills import SkillRegistry
        registry = SkillRegistry()
        skills = registry.discover()
        if not skills:
            return None

        crew: list[dict] = []
        for skill in skills.values():
            role = _SKILL_ROLE_MAP.get(skill.name, AgentRole.GENERAL)
            provider = _PROVIDER_MAP.get(skill.provider, ProviderType.CLAUDE_CODE)
            crew.append({
                "name": skill.name,
                "role": role,
                "thread": skill.thread or "mechanistic",
                "provider": provider,
                "model": skill.model,
            })
        logger.info("Built crew from %d skill files", len(crew))
        return crew
    except Exception as e:
        logger.debug("Skill-based crew failed: %s", e)
        return None


async def spawn_default_crew(swarm) -> list:
    """Spawn the multi-provider agent fleet into the swarm.

    First tries to build crew from SKILL.md files (dynamic, hot-reloadable).
    Falls back to DEFAULT_CREW if no skill files found.

    Returns list of AgentState for spawned agents.

    JIKOKU-optimized: Spawns agents in parallel for 3.74x speedup.
    """
    # Try skill-based crew first
    crew = _crew_from_skills() or DEFAULT_CREW

    existing = await swarm.list_agents()
    existing_names = {a.name for a in existing}

    # Filter out agents that already exist
    specs_to_spawn = [
        spec for spec in crew
        if spec["name"] not in existing_names
    ]

    if not specs_to_spawn:
        logger.info("All agents already exist, skipping spawn")
        return []

    spawn_ops = []
    for spec in specs_to_spawn:
        provider = spec.get("provider", ProviderType.CLAUDE_CODE)
        model = spec.get("model", "claude-code")
        base_prompt = str(spec.get("system_prompt", "") or "").strip()
        merged_prompt = (
            f"{base_prompt}\n\n{MEMORY_SURVIVAL_INSTINCT}"
            if base_prompt
            else MEMORY_SURVIVAL_INSTINCT
        )
        spawn_ops.append(
            swarm.spawn_agent(
                name=spec["name"],
                role=spec["role"],
                thread=spec["thread"],
                provider_type=provider,
                model=model,
                system_prompt=merged_prompt,
            )
        )

    agents = await asyncio.gather(*spawn_ops)

    # Log results
    for spec in specs_to_spawn:
        logger.info("Spawned %s (%s) on %s [%s]",
                     spec["name"], spec["role"].value,
                     spec.get("provider", ProviderType.CLAUDE_CODE).value,
                     spec["thread"])
    return list(agents)


async def spawn_cybernetics_crew(swarm) -> list:
    """Ensure the dedicated cybernetics steward roster exists."""
    existing = await swarm.list_agents()
    existing_names = {a.name for a in existing}

    specs_to_spawn = [
        spec for spec in CYBERNETICS_CREW
        if spec["name"] not in existing_names
    ]

    if not specs_to_spawn:
        logger.info("Cybernetics crew already exists, skipping spawn")
        return []

    spawn_ops = []
    for spec in specs_to_spawn:
        base_prompt = str(spec.get("system_prompt", "") or "").strip()
        merged_prompt = (
            f"{base_prompt}\n\n{MEMORY_SURVIVAL_INSTINCT}"
            if base_prompt
            else MEMORY_SURVIVAL_INSTINCT
        )
        spawn_ops.append(
            swarm.spawn_agent(
                name=spec["name"],
                role=spec["role"],
                thread=spec["thread"],
                provider_type=spec["provider"],
                model=spec["model"],
                system_prompt=merged_prompt,
            )
        )

    agents = await asyncio.gather(*spawn_ops)

    for spec in specs_to_spawn:
        logger.info(
            "Spawned cybernetics seat %s (%s) on %s [%s]",
            spec["name"],
            spec["role"].value,
            spec["provider"].value,
            spec["thread"],
        )

    return list(agents)


async def spawn_conductor_crew(swarm) -> list:
    """Register conductor agents in the swarm agent pool.

    This makes conductors visible in ``dgc status`` and allows the swarm
    to route tasks to them. The conductors' actual lifecycle is managed
    by PersistentAgent.run_loop(), not by the swarm.
    """
    from dharma_swarm.conductors import CONDUCTOR_CONFIGS

    existing = await swarm.list_agents()
    existing_names = {a.name for a in existing}

    spawned = []
    for cfg in CONDUCTOR_CONFIGS:
        if cfg["name"] in existing_names:
            continue
        try:
            agent = await swarm.spawn_agent(
                name=cfg["name"],
                role=cfg["role"],
                thread="mechanistic",
                provider_type=cfg["provider_type"],
                model=cfg["model"],
                system_prompt=cfg["system_prompt"][:500],
            )
            spawned.append(agent)
            logger.info("Registered conductor: %s (%s)", cfg["name"], cfg["model"])
        except Exception as e:
            logger.warning("Failed to register conductor %s: %s", cfg["name"], e)

    return spawned


async def create_seed_tasks(swarm) -> list:
    """Create seed tasks for the first daemon cycle.

    Only creates tasks if the board is empty (no pending tasks).

    JIKOKU-optimized: Uses batch creation (single transaction)
    to eliminate SQLite write lock contention.
    """
    from dharma_swarm.models import TaskStatus

    existing = await swarm.list_tasks(status=TaskStatus.PENDING)
    if existing:
        logger.info("Board has %d pending tasks, skipping seed", len(existing))
        return []

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Prepare task specs for batch creation
    task_specs = [
        {
            "title": spec["title"],
            "description": spec["description"].replace("{date}", date_str),
            "priority": spec["priority"],
        }
        for spec in SEED_TASKS
    ]

    # Create all tasks in single batch (single transaction)
    tasks = await swarm.create_task_batch(task_specs)

    # Log results
    for spec in SEED_TASKS:
        logger.info("Created seed task: %s", spec["title"])

    return tasks
