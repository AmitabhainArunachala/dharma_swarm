"""Command Fleet — 10-agent high-powered fleet with real models.

Canonical fleet definition. Each agent has a real provider, real model,
and persistent identity in the Ginko registry.

Provider strategy (FREE FIRST — hard constraint):
  1. Ollama Cloud: kimi-k2.5:cloud, glm-5:cloud (FREE)
  2. NVIDIA NIM: llama-3.3-70b, nemotron-ultra (FREE)
  3. OpenRouter: PAID — only for frontier models not on free tiers
  4. When ANTHROPIC_API_KEY is set, opus-primus auto-upgrades to direct.
  5. When OPENAI_API_KEY is set, codex-primus auto-upgrades to direct.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dharma_swarm.models import AgentRole, ProviderType

logger = logging.getLogger(__name__)

# ── The Fleet ─────────────────────────────────────────────────────────────
# FREE providers first. OpenRouter is overflow only.

COMMAND_FLEET: list[dict] = [
    # ── FREE tier: Ollama Cloud ──────────────────────────────────────
    {
        "name": "kimi-cartographer",
        "role": AgentRole.CARTOGRAPHER,
        "provider": ProviderType.OLLAMA,
        "model": "kimi-k2.5:cloud",
        "thread": "phenomenological",
        "display_name": "Kimi Cartographer",
        "tier": "strong",
        "strengths": ("reasoning", "long_context", "synthesis"),
    },
    {
        "name": "glm-researcher",
        "role": AgentRole.RESEARCHER,
        "provider": ProviderType.OLLAMA,
        "model": "glm-5:cloud",
        "thread": "mechanistic",
        "display_name": "GLM Researcher",
        "tier": "strong",
        "strengths": ("reasoning", "synthesis", "multilingual"),
    },
    {
        "name": "cartographer",
        "role": AgentRole.CARTOGRAPHER,
        "provider": ProviderType.OLLAMA,
        "model": "kimi-k2.5:cloud",
        "thread": "mechanistic",
        "display_name": "Cartographer",
        "tier": "strong",
        "strengths": ("code", "reasoning"),
    },
    {
        "name": "architect",
        "role": AgentRole.ARCHITECT,
        "provider": ProviderType.OLLAMA,
        "model": "glm-5:cloud",
        "thread": "architectural",
        "display_name": "Architect",
        "tier": "strong",
        "strengths": ("code", "reasoning"),
    },
    # ── FREE tier: NVIDIA NIM ────────────────────────────────────────
    {
        "name": "nim-validator",
        "role": AgentRole.VALIDATOR,
        "provider": ProviderType.NVIDIA_NIM,
        "model": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        "thread": "scaling",
        "display_name": "NIM Validator",
        "tier": "strong",
        "strengths": ("reasoning", "synthesis", "architecture"),
    },
    {
        "name": "garuda",
        "role": AgentRole.SURGEON,
        "provider": ProviderType.NVIDIA_NIM,
        "model": "meta/llama-3.3-70b-instruct",
        "thread": "alignment",
        "display_name": "Garuda",
        "tier": "strong",
        "strengths": ("reasoning", "code"),
    },
    {
        "name": "deepseek",
        "role": AgentRole.RESEARCHER,
        "provider": ProviderType.NVIDIA_NIM,
        "model": "meta/llama-3.3-70b-instruct",
        "thread": "mechanistic",
        "display_name": "DeepSeek",
        "tier": "strong",
        "strengths": ("code", "reasoning"),
    },
    {
        "name": "qwen-builder",
        "role": AgentRole.ARCHITECT,
        "provider": ProviderType.NVIDIA_NIM,
        "model": "meta/llama-3.3-70b-instruct",
        "thread": "architectural",
        "display_name": "Qwen Builder",
        "tier": "strong",
        "strengths": ("reasoning", "code"),
    },
    # ── PAID tier: OpenRouter (overflow only) ────────────────────────
    # These two use frontier models not available on free tiers.
    # Auto-upgrade to direct API when keys are available.
    {
        "name": "opus-primus",
        "role": AgentRole.ORCHESTRATOR,
        "provider": ProviderType.OPENROUTER,
        "model": "anthropic/claude-opus-4",
        "thread": "phenomenological",
        "display_name": "Opus Prime",
        "tier": "frontier",
        "strengths": ("reasoning", "architecture", "synthesis"),
    },
    {
        "name": "codex-primus",
        "role": AgentRole.ORCHESTRATOR,
        "provider": ProviderType.OPENROUTER,
        "model": "openai/gpt-5-codex",
        "thread": "architectural",
        "display_name": "Codex Prime",
        "tier": "frontier",
        "strengths": ("code", "reasoning", "architecture"),
    },
    {
        "name": "indra-glm",
        "role": AgentRole.RESEARCHER,
        "provider": ProviderType.OLLAMA,
        "model": "glm-5:cloud",
        "thread": "semantic",
        "display_name": "Indra GLM",
        "tier": "strong",
        "strengths": ("semantic_mapping", "multilingual", "synthesis"),
        "tool_name": "semantic_lens",
    },
    {
        "name": "chandra-kimi",
        "role": AgentRole.CARTOGRAPHER,
        "provider": ProviderType.OLLAMA,
        "model": "kimi-k2.5:cloud",
        "thread": "phenomenological",
        "display_name": "Chandra Kimi",
        "tier": "strong",
        "strengths": ("long_context", "file_topology", "narrative_mapping"),
        "tool_name": "path_weaver",
    },
    {
        "name": "vajra-nemotron",
        "role": AgentRole.VALIDATOR,
        "provider": ProviderType.NVIDIA_NIM,
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "thread": "scaling",
        "display_name": "Vajra Nemotron",
        "tier": "strong",
        "strengths": ("validation", "systems_reasoning", "ensemble_review"),
        "tool_name": "truth_hammer",
    },
    {
        "name": "surya-glm",
        "role": AgentRole.ARCHITECT,
        "provider": ProviderType.OLLAMA,
        "model": "glm-5:cloud",
        "thread": "architectural",
        "display_name": "Surya GLM",
        "tier": "strong",
        "strengths": ("ui_architecture", "refactors", "graph_design"),
        "tool_name": "graph_forge",
    },
    {
        "name": "tara-kimi",
        "role": AgentRole.GENERAL,
        "provider": ProviderType.OLLAMA,
        "model": "kimi-k2.5:cloud",
        "thread": "alignment",
        "display_name": "Tara Kimi",
        "tier": "strong",
        "strengths": ("operator_dialogue", "commentary", "task_translation"),
        "tool_name": "whisper_bridge",
    },
]


def _auto_upgrade_providers(fleet: list[dict]) -> list[dict]:
    """Auto-upgrade to direct providers when API keys are available.

    - ANTHROPIC_API_KEY set -> opus-primus uses direct Anthropic
    - OPENAI_API_KEY set -> codex-primus uses direct OpenAI
    """
    upgraded = []
    for spec in fleet:
        spec = dict(spec)  # shallow copy
        if spec["name"] == "opus-primus" and os.environ.get("ANTHROPIC_API_KEY", "").strip():
            spec["provider"] = ProviderType.ANTHROPIC
            spec["model"] = "claude-opus-4-20250514"
            logger.info("opus-primus auto-upgraded to direct Anthropic")
        elif spec["name"] == "codex-primus" and os.environ.get("OPENAI_API_KEY", "").strip():
            spec["provider"] = ProviderType.OPENAI
            spec["model"] = "gpt-4o"
            logger.info("codex-primus auto-upgraded to direct OpenAI")
        upgraded.append(spec)
    return upgraded


# Free-first fallback chain for when a provider is unavailable
_FALLBACK_CHAIN = [
    ProviderType.OLLAMA,
    ProviderType.NVIDIA_NIM,
    ProviderType.OPENROUTER_FREE,
    ProviderType.OPENROUTER,
]
_FALLBACK_MODELS = {
    ProviderType.OLLAMA: "kimi-k2.5:cloud",
    ProviderType.NVIDIA_NIM: "meta/llama-3.3-70b-instruct",
    ProviderType.OPENROUTER_FREE: "meta-llama/llama-3.3-70b-instruct",
    ProviderType.OPENROUTER: "meta-llama/llama-3.3-70b-instruct",
}


async def spawn_command_fleet(swarm) -> list:
    """Spawn the 10-agent command fleet into the swarm.

    Skips agents that already exist. Registers each in Ginko registry.
    Returns list of AgentState for newly spawned agents.
    """
    from dharma_swarm.startup_crew import MEMORY_SURVIVAL_INSTINCT

    fleet = _auto_upgrade_providers(COMMAND_FLEET)

    existing = await swarm.list_agents()
    existing_names = {a.name for a in existing}

    specs_to_spawn = [s for s in fleet if s["name"] not in existing_names]

    if not specs_to_spawn:
        logger.info("All command fleet agents already exist, skipping spawn")
        return []

    # Validate providers — free-first fallback chain
    from dharma_swarm.evolution_roster import _provider_has_key
    validated_specs = []
    for spec in specs_to_spawn:
        provider = spec["provider"]
        if _provider_has_key(provider):
            validated_specs.append(spec)
        else:
            # Walk the free-first fallback chain
            placed = False
            for fallback_provider in _FALLBACK_CHAIN:
                if fallback_provider != provider and _provider_has_key(fallback_provider):
                    logger.warning(
                        "Provider %s unavailable for %s, falling back to %s",
                        provider.value, spec["name"], fallback_provider.value,
                    )
                    fallback = dict(spec)
                    fallback["provider"] = fallback_provider
                    fallback["model"] = _FALLBACK_MODELS[fallback_provider]
                    validated_specs.append(fallback)
                    placed = True
                    break
            if not placed:
                logger.error("No providers available for %s, skipping", spec["name"])

    # Spawn all in parallel
    spawn_tasks = []
    for spec in validated_specs:
        spawn_tasks.append(
            swarm.spawn_agent(
                name=spec["name"],
                role=spec["role"],
                thread=spec["thread"],
                provider_type=spec["provider"],
                model=spec["model"],
                system_prompt=MEMORY_SURVIVAL_INSTINCT,
            )
        )

    agents = await asyncio.gather(*spawn_tasks, return_exceptions=True)

    # Filter out exceptions and log
    spawned = []
    for spec, result in zip(validated_specs, agents):
        if isinstance(result, Exception):
            logger.error("Failed to spawn %s: %s", spec["name"], result)
        else:
            spawned.append(result)
            logger.info(
                "Spawned %s (%s) on %s [%s] — %s",
                spec["name"], spec["role"].value, spec["provider"].value,
                spec["thread"], spec["model"],
            )

    # Register in Ginko
    _register_fleet_in_ginko(validated_specs)

    return spawned


def _register_fleet_in_ginko(specs: list[dict]) -> None:
    """Register fleet agents in Ginko agent registry for persistent identity."""
    try:
        from dharma_swarm.agent_registry import get_registry
        reg = get_registry()
        for spec in specs:
            try:
                reg.register_agent(
                    name=spec["name"],
                    role=spec["role"].value if hasattr(spec["role"], 'value') else str(spec["role"]),
                    model=spec["model"],
                    system_prompt=f"Command Fleet agent: {spec.get('display_name', spec['name'])}",
                )
            except Exception as e:
                logger.warning("Failed to register %s in Ginko: %s", spec["name"], e)
    except Exception as e:
        logger.warning("Ginko registration failed: %s", e)
