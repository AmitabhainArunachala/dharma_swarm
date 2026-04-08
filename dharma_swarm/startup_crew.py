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
    """Build crew preferring free providers.  Ollama Cloud > OpenRouter > Claude Code.

    When Ollama Cloud is available, each agent gets a DIFFERENT frontier model
    to maximize behavioral diversity (the Transcendence Principle requires
    decorrelated errors — same model prompted differently does NOT suffice).
    """
    if _has_ollama_key():
        # Ollama Cloud — diverse frontier models for error decorrelation
        from dharma_swarm.ollama_config import OLLAMA_CLOUD_FRONTIER_MODELS
        _models = OLLAMA_CLOUD_FRONTIER_MODELS  # glm-5, deepseek-v3.2, kimi-k2.5, minimax-m2.7, qwen3-coder
        return [
            {"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
             "thread": "mechanistic", "provider": ProviderType.OLLAMA, "model": _models[0]},  # glm-5
            {"name": "surgeon", "role": AgentRole.SURGEON,
             "thread": "alignment", "provider": ProviderType.OLLAMA, "model": _models[2]},    # kimi-k2.5
            {"name": "architect", "role": AgentRole.ARCHITECT,
             "thread": "architectural", "provider": ProviderType.OLLAMA, "model": _models[1]}, # deepseek-v3.2
            {"name": "validator", "role": AgentRole.VALIDATOR,
             "thread": "scaling", "provider": ProviderType.OLLAMA, "model": _models[4]},       # qwen3-coder
        ]

    if _has_openrouter_key():
        # OpenRouter Free — diverse free models for error decorrelation
        return [
            {"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
             "thread": "mechanistic", "provider": ProviderType.OPENROUTER_FREE,
             "model": "meta-llama/llama-3.3-70b-instruct:free"},
            {"name": "surgeon", "role": AgentRole.SURGEON,
             "thread": "alignment", "provider": ProviderType.OPENROUTER_FREE,
             "model": "qwen/qwen3-32b:free"},
            {"name": "architect", "role": AgentRole.ARCHITECT,
             "thread": "architectural", "provider": ProviderType.OPENROUTER_FREE,
             "model": "deepseek/deepseek-chat-v3-0324:free"},
            {"name": "validator", "role": AgentRole.VALIDATOR,
             "thread": "scaling", "provider": ProviderType.OPENROUTER_FREE,
             "model": "mistralai/mistral-small-3.1-24b-instruct:free"},
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


# Seed tasks — world-creating missions that produce external artifacts,
# not just internal files. Each task ends with a world-facing output:
# a published artifact, a website scaffold, a sub-swarm spec, a GitHub commit.
SEED_TASKS = [
    {
        "title": "Clone + analyze: chauncygu claude-code source — extract architecture insights",
        "description": (
            "The Claude Code source code is public at:"
            " https://github.com/chauncygu/collection-claude-code-source-code "
            "It has already been cloned to ~/workspace/collection-claude-code-source-code. "
            "Read the key files: look for the tool execution loop, subagent spawning pattern, "
            "the bash/computer use tools, the way tasks are decomposed into subtasks. "
            "Your mission: extract 5 architectural patterns that DHARMA SWARM is missing. "
            "Produce a structured analysis: for each pattern, show the Claude Code implementation "
            "(with file + line reference), explain why DHARMA SWARM needs it, "
            "and write a concrete implementation spec. "
            "Write to ~/.dharma/shared/claude_code_architecture_gaps.md. "
            "Then use publish_markdown_artifact to promote it to "
            "~/.dharma/artifacts/ — making it a world-facing artifact, not just a note."
        ),
        "priority": TaskPriority.HIGH,
    },
    {
        "title": "Research + spawn sub-swarm spec: Sakana AI evolutionary architecture",
        "description": (
            "Use web_search + fetch_url to deeply research Sakana AI's architecture: "
            "fetch https://sakana.ai, search arXiv for 'Sakana AI evolutionary model merging', "
            "search for 'Darwin Gödel machine Sakana 2026', 'SWE-bench Sakana DGM 2026'. "
            "Extract: how their evolutionary loop works, fitness evaluation, how they improved "
            "SWE-bench from 20% to 50% in 80 iterations. "
            "Write a 1500-word technical report to ~/.dharma/shared/sakana_architecture.md. "
            "THEN: assess whether DHARMA SWARM should implement the same evolutionary loop. "
            "If yes, use spawn_sub_swarm_spec to materialize a sub-swarm mission spec at "
            "~/.dharma/sub_swarms/ named 'Sakana-DGM-Evolutionary-Loop' with a concrete thesis "
            "and roles: cartographer, architect, surgeon, validator. "
            "The spec is the real deliverable — it makes the next mission actionable."
        ),
        "priority": TaskPriority.HIGH,
    },
    {
        "title": "Build + commit: DHARMA SWARM public-facing research site scaffold",
        "description": (
            "DHARMA SWARM has produced research (STATE_OF_AI, competitive analysis, "
            "GNANI_LODESTONE) that nobody outside the machine can see. "
            "Your mission: create a minimal public-facing website scaffold. "
            "Step 1: Use create_website_scaffold with output_dir=~/dharma_swarm/docs/site, "
            "site_name='DHARMA SWARM Research', purpose='Autonomous research and competitive "
            "intelligence from a self-evolving AI swarm. Updated continuously.'. "
            "Step 2: Write a real index page summarizing DHARMA SWARM's mission, "
            "the telos (Jagat Kalyan + Moksha), and the three key research outputs so far. "
            "Use read_file on ~/.dharma/shared/ to get actual research content. "
            "Step 3: Use github_commit_push to commit and push the site to origin. "
            "This is not a prototype. It is the first world-facing surface of the swarm."
        ),
        "priority": TaskPriority.HIGH,
    },
    {
        "title": "Anthropic Economic Futures: research + draft grant application",
        "description": (
            "Use web_search to find: 'Anthropic Economic Futures grant 2026 application', "
            "'Anthropic economic impact fund requirements', fetch https://anthropic.com if needed. "
            "DHARMA SWARM's telos includes Jagat Kalyan: AI-coordinated ecological restoration "
            "for displaced workers using carbon markets. This is directly aligned with the "
            "Anthropic Economic Futures mandate. "
            "Draft a 600-word grant application framing: "
            "Problem (AI displacement + ecological crisis), Approach (welfare-ton metric, "
            "agent-coordinated MRV, carbon market loop), Why DHARMA SWARM is uniquely positioned "
            "(telos-gated agents, Jagat Kalyan mission, existing welfare-ton calculator). "
            "Write to ~/.dharma/shared/anthropic_grant_draft.md. "
            "Then use publish_markdown_artifact to move it to ~/.dharma/artifacts/. "
            "Quality of argument matters — this is a real application, not a placeholder."
        ),
        "priority": TaskPriority.NORMAL,
    },
    {
        "title": "Open-source probe: find + analyze top 3 swarm repos to fork-and-evolve",
        "description": (
            "Use web_search to find the top open-source multi-agent / swarm repos on GitHub: "
            "search 'github multi agent swarm open source 2026 stars', "
            "'github autonomous agent orchestration 2026', 'github self-improving agent'. "
            "For each candidate: use fetch_url to read their README and architecture. "
            "Pick the 3 most architecturally complementary to DHARMA SWARM. "
            "For each of the top 3: write a 300-word technical comparison showing what they do "
            "that DHARMA SWARM does not, and vice versa. "
            "Produce the analysis at ~/.dharma/shared/fork_candidates.md. "
            "THEN for the single highest-value candidate: use github_clone_repo to clone it "
            "into ~/workspace/<repo_name>. Read its core loop. "
            "Use spawn_sub_swarm_spec to create a 'Fork-and-Evolve: <repo_name>' mission spec "
            "in ~/.dharma/sub_swarms/ so a future swarm can integrate the best patterns."
        ),
        "priority": TaskPriority.NORMAL,
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

    # Check if any of the SEED_TASK titles are currently active (PENDING or RUNNING).
    # We look by title to avoid re-seeding tasks that are mid-flight.
    # We do NOT check COMPLETED/FAILED — those are done and we should re-seed.
    seed_titles = {spec["title"] for spec in SEED_TASKS}
    active_seeds: list = []
    for status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        try:
            active = await swarm.list_tasks(status=status)
            active_seeds.extend(
                t for t in active
                if getattr(t, 'title', '') in seed_titles
            )
        except Exception:
            pass

    if active_seeds:
        logger.info(
            "Seed tasks already active (%d in-flight), skipping re-seed: %s",
            len(active_seeds),
            [getattr(t, 'title', '')[:40] for t in active_seeds[:3]],
        )
        return []

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Prepare task specs for batch creation
    # created_by="operator" prevents busywork (coordination/eval tasks) from
    # filling the queue while these real external-intelligence tasks are present.
    task_specs = [
        {
            "title": spec["title"],
            "description": spec["description"].replace("{date}", date_str),
            "priority": spec["priority"],
            "created_by": "operator",
            "metadata": {
                **spec.get("metadata", {}),
                "created_via": "operator",
                "seed_type": "real_external_work",
            },
        }
        for spec in SEED_TASKS
    ]

    # Create all tasks in single batch (single transaction)
    tasks = await swarm.create_task_batch(task_specs)

    # Log results
    for spec in SEED_TASKS:
        logger.info("Created seed task: %s", spec["title"])

    return tasks
