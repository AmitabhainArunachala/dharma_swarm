"""Model management and switching for dharma_swarm.

Handles model discovery, configuration, and autonomous switching
across Claude, OpenAI, and other providers.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dharma_swarm.model_hierarchy import DEFAULT_MODELS
from dharma_swarm.models import ProviderType

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about an available model."""

    id: str
    name: str
    provider: ProviderType
    description: str
    context_window: int
    cost_per_1m_input: float
    cost_per_1m_output: float
    speed: Literal["fast", "medium", "slow"]
    capability: Literal["high", "medium", "low"]


# Model catalog
MODELS: dict[str, ModelInfo] = {
    # Claude models
    "opus": ModelInfo(
        id="claude-opus-4-6",
        name="Claude Opus 4.6",
        provider=ProviderType.ANTHROPIC,
        description="Most capable, best for complex reasoning",
        context_window=200_000,
        cost_per_1m_input=15.0,
        cost_per_1m_output=75.0,
        speed="slow",
        capability="high",
    ),
    "sonnet": ModelInfo(
        id="claude-sonnet-4-6",
        name="Claude Sonnet 4.6",
        provider=ProviderType.ANTHROPIC,
        description="Balanced speed and capability",
        context_window=200_000,
        cost_per_1m_input=3.0,
        cost_per_1m_output=15.0,
        speed="medium",
        capability="high",
    ),
    "sonnet-4.5": ModelInfo(
        id="claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        provider=ProviderType.ANTHROPIC,
        description="Fast output, current default",
        context_window=200_000,
        cost_per_1m_input=3.0,
        cost_per_1m_output=15.0,
        speed="fast",
        capability="high",
    ),
    "haiku": ModelInfo(
        id="claude-haiku-4-5-20251001",
        name="Claude Haiku 4.5",
        provider=ProviderType.ANTHROPIC,
        description="Fastest, cost-effective",
        context_window=200_000,
        cost_per_1m_input=0.8,
        cost_per_1m_output=4.0,
        speed="fast",
        capability="medium",
    ),
    # OpenAI models
    "gpt-4o": ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider=ProviderType.OPENAI,
        description="OpenAI's flagship model",
        context_window=128_000,
        cost_per_1m_input=2.5,
        cost_per_1m_output=10.0,
        speed="medium",
        capability="high",
    ),
    "o1": ModelInfo(
        id="o1",
        name="O1",
        provider=ProviderType.OPENAI,
        description="Reasoning-focused model",
        context_window=128_000,
        cost_per_1m_input=15.0,
        cost_per_1m_output=60.0,
        speed="slow",
        capability="high",
    ),
    "o1-mini": ModelInfo(
        id="o1-mini",
        name="O1 Mini",
        provider=ProviderType.OPENAI,
        description="Faster reasoning model",
        context_window=128_000,
        cost_per_1m_input=3.0,
        cost_per_1m_output=12.0,
        speed="medium",
        capability="medium",
    ),
    # Free tier frontier models (from model_hierarchy.py)
    "glm-5": ModelInfo(
        id="glm-5:cloud",
        name="GLM-5 (744B MoE)",
        provider=ProviderType.OLLAMA,
        description="Zhipu AI frontier model via Ollama Cloud, free",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="medium",
        capability="high",
    ),
    "deepseek-v3.2": ModelInfo(
        id="deepseek-v3.2:cloud",
        name="DeepSeek V3.2",
        provider=ProviderType.OLLAMA,
        description="DeepSeek frontier model via Ollama Cloud, free",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="medium",
        capability="high",
    ),
    "kimi-k2.5": ModelInfo(
        id="kimi-k2.5:cloud",
        name="Kimi K2.5",
        provider=ProviderType.OLLAMA,
        description="Moonshot AI frontier model via Ollama Cloud, free",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="medium",
        capability="high",
    ),
    "minimax-m2.7": ModelInfo(
        id="minimax-m2.7:cloud",
        name="MiniMax M2.7",
        provider=ProviderType.OLLAMA,
        description="MiniMax frontier model via Ollama Cloud, free",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="medium",
        capability="high",
    ),
    "llama-3.3-70b": ModelInfo(
        id="meta/llama-3.3-70b-instruct",
        name="Llama 3.3 70B",
        provider=ProviderType.NVIDIA_NIM,
        description="Meta Llama via NVIDIA NIM, free (50 req/day)",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="fast",
        capability="high",
    ),
    "nemotron-120b": ModelInfo(
        id="nvidia/nemotron-3-super-120b-a12b:free",
        name="Nemotron 3 Super 120B",
        provider=ProviderType.OPENROUTER_FREE,
        description="NVIDIA Nemotron via OpenRouter free tier",
        context_window=128_000,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        speed="medium",
        capability="high",
    ),
}

# Extra alias variants (normalized from user input)
_ALIAS_VARIANTS: dict[str, str] = {
    "opus-4.6": "opus",
    "opus 4.6": "opus",
    "claude-opus-4-6": "opus",
    "sonnet-4.6": "sonnet",
    "sonnet 4.6": "sonnet",
    "claude-sonnet-4-6": "sonnet",
    "claude": "opus",  # generic "claude" → canonical primary Claude runner
    "minimax": "minimax-m2.7",
    "minimax m2.7": "minimax-m2.7",
    "minimax-m2.7:cloud": "minimax-m2.7",
}


def get_current_model() -> str:
    """Get the currently active model from environment/config."""
    # Check environment variable first
    if model := os.environ.get("ANTHROPIC_MODEL"):
        return model
    if model := os.environ.get("CLAUDE_MODEL"):
        return model

    # Check Claude Code config
    config_path = Path.home() / ".claude" / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            if model := config.get("model"):
                return model
        except Exception:
            logger.debug("Model config read failed", exc_info=True)

    # Default from environment info
    return DEFAULT_MODELS.get(ProviderType.ANTHROPIC, "claude-opus-4-6")


def list_models(provider: ProviderType | None = None) -> list[ModelInfo]:
    """List all available models, optionally filtered by provider."""
    models = list(MODELS.values())
    if provider:
        models = [m for m in models if m.provider == provider]
    return sorted(models, key=lambda m: (m.provider.value, -m.context_window))


def get_model_info(alias_or_id: str) -> ModelInfo | None:
    """Get model info by alias (e.g., 'opus') or full ID."""
    # Try direct alias first
    if alias_or_id in MODELS:
        return MODELS[alias_or_id]

    # Try variant aliases (e.g. 'opus-4.6', 'sonnet 4.6')
    canonical = _ALIAS_VARIANTS.get(alias_or_id.lower())
    if canonical and canonical in MODELS:
        return MODELS[canonical]

    # Try full ID match
    for model in MODELS.values():
        if model.id == alias_or_id:
            return model

    return None


def resolve_model_request(request: str) -> tuple[ModelInfo | None, str | None]:
    """Resolve a model request, preferring existing user config when request is generic.

    If *request* is ``"claude"`` (or another generic alias), first checks
    ``~/.claude/config.json`` for an existing model preference and returns
    that if it's a Claude model.  Otherwise returns the default Claude model.

    Returns:
        (ModelInfo, note) where *note* describes how the model was resolved.
    """
    key = request.strip().lower()
    if key == "claude":
        # Check existing config
        config_path = Path.home() / ".claude" / "config.json"
        existing_id: str | None = None
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                existing_id = cfg.get("model")
            except Exception:
                logger.debug("Model config parse failed", exc_info=True)
        if existing_id:
            m = get_model_info(existing_id)
            if m and m.provider == ProviderType.ANTHROPIC:
                return m, f"Using existing config model {m.id}"
        # Fall through to default
        default = MODELS.get("opus")
        return default, f"Defaulting to {default.id}" if default else None

    m = get_model_info(request)
    return m, f"Resolved {request} → {m.id}" if m else None


def format_model_table(_models: list[ModelInfo] | None = None) -> str:
    """Format models as a table for CLI display."""
    lines = [
        "Available Models:",
        "",
        f"{'Alias':<15} {'Model ID':<30} {'Provider':<12} {'Speed':<8} {'Capability':<10} {'Cost ($/1M tokens)'}",
        "-" * 120,
    ]

    for alias, model in MODELS.items():
        cost_str = f"${model.cost_per_1m_input:.1f} in / ${model.cost_per_1m_output:.1f} out"
        lines.append(
            f"{alias:<15} {model.id:<30} {model.provider.value:<12} "
            f"{model.speed:<8} {model.capability:<10} {cost_str}"
        )

    lines.extend([
        "",
        "Context Windows: All models support 128K-200K tokens",
        "",
        "Usage: dgc model [alias]  # e.g., 'dgc model opus'",
    ])

    return "\n".join(lines)


def update_claude_config(model_id: str) -> bool:
    """Update ~/.claude/config.json with new model.

    Returns True if successful, False otherwise.
    """
    config_path = Path.home() / ".claude" / "config.json"

    try:
        # Create config dir if needed
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing config or create new
        if config_path.exists():
            config = json.loads(config_path.read_text())
        else:
            config = {}

        # Update model
        config["model"] = model_id

        # Write back
        config_path.write_text(json.dumps(config, indent=2))
        return True
    except Exception as e:
        print(f"Failed to update config: {e}")
        return False


def switch_model(alias_or_id: str) -> tuple[bool, str]:
    """Switch to a different model.

    Returns (success, message).
    """
    model = get_model_info(alias_or_id)
    if not model:
        available = ", ".join(MODELS.keys())
        return False, f"Unknown model '{alias_or_id}'. Available: {available}"

    # Update config
    if not update_claude_config(model.id):
        return False, "Failed to update configuration"

    return True, f"""
Model switched to {model.name} ({model.id})

Provider: {model.provider.value}
Speed: {model.speed}
Capability: {model.capability}
Context: {model.context_window:,} tokens
Cost: ${model.cost_per_1m_input}/1M input, ${model.cost_per_1m_output}/1M output

Note: Restart Claude Code session for this to take effect.
      Or use 'dgc spawn --model {alias_or_id}' to spawn agents with this model immediately.
"""


def show_current_model() -> str:
    """Show information about the currently active model."""
    current_id = get_current_model()

    # Find model info
    model = None
    for m in MODELS.values():
        if m.id == current_id:
            model = m
            break

    if not model:
        return f"Current model: {current_id} (not in catalog)"

    return f"""
Current Model: {model.name}

ID: {model.id}
Provider: {model.provider.value}
Description: {model.description}
Speed: {model.speed}
Capability: {model.capability}
Context Window: {model.context_window:,} tokens
Cost: ${model.cost_per_1m_input}/1M input, ${model.cost_per_1m_output}/1M output

Switch with: dgc model [alias]
List all: dgc model list
"""
