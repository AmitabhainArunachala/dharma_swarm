"""FREE_FLEET — zero-cost OpenRouter model preset for dharma_swarm.

Provides a named configuration preset that uses only free-tier OpenRouter
models, organised into three capability tiers.  The existing OPENROUTER_FREE
provider and DEFAULT fleet are unchanged; this module layers on top of them.

Usage
-----
Python API::

    from dharma_swarm.free_fleet import FREE_FLEET, get_tier_model, build_free_fleet_crew

    config = FREE_FLEET
    model = get_tier_model(tier=1)          # best free reasoning model
    crew   = build_free_fleet_crew()        # ready-to-spawn crew specs

CLI::

    dgc free-fleet                          # show current config
    dgc free-fleet --tier 1                 # show tier-1 models
    dgc free-fleet --set-env                # write DGC_FREE_FLEET=1 to shell env

Environment flag
----------------
Set ``DGC_FREE_FLEET=1`` (or ``true``/``yes``) to make the swarm default to
free-fleet model selection instead of the paid OpenRouter fleet.  The
``startup_crew`` module respects this flag when building DEFAULT_CREW.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Literal

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Live discovery from OpenRouter (the ONLY source of truth)
# ---------------------------------------------------------------------------

_MIN_CTX = 32_000  # Minimum context to be useful

# Tier assignment rules: prefix → tier
_TIER_RULES: list[tuple[str, int]] = [
    # Tier 1: heavy reasoning
    ("nvidia/nemotron-3-super", 1),
    ("nousresearch/hermes-3-llama-3.1-405b", 1),
    ("openai/gpt-oss-120b", 1),
    ("meta-llama/llama-3.3-70b", 1),
    # Tier 2: general purpose
    ("qwen/", 2),
    ("nvidia/nemotron-3-nano", 2),
    ("minimax/", 2),
    ("google/gemma-3-27b", 2),
    ("arcee-ai/trinity", 2),
    ("openai/gpt-oss-20b", 2),
    ("z-ai/", 2),
    ("stepfun/", 2),
    # Tier 3: fast/lightweight (everything else with >= _MIN_CTX)
]


def _assign_tier(model_id: str) -> int:
    """Assign a tier to a model based on prefix rules. Default: tier 3."""
    for prefix, tier in _TIER_RULES:
        if model_id.startswith(prefix):
            return tier
    return 3


def discover_free_models_sync() -> dict[int, list[str]]:
    """Query OpenRouter /api/v1/models and return tiered free model dict.

    Returns {1: [...], 2: [...], 3: [...]} with live model IDs.
    Falls back to a minimal known-good set on network failure.
    """
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()

        tiers: dict[int, list[tuple[str, int]]] = {1: [], 2: [], 3: []}
        for m in data.get("data", []):
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_cost = float(pricing.get("prompt", "1") or "1")
            completion_cost = float(pricing.get("completion", "1") or "1")
            if prompt_cost == 0 and completion_cost == 0:
                ctx = int(m.get("context_length", 0))
                if ctx >= _MIN_CTX and mid.endswith(":free"):
                    tier = _assign_tier(mid)
                    tiers[tier].append((mid, ctx))

        # Sort each tier by context length descending
        result: dict[int, list[str]] = {}
        for t in (1, 2, 3):
            tiers[t].sort(key=lambda x: -x[1])
            result[t] = [mid for mid, _ in tiers[t]]

        # Ensure every tier has at least something
        if not result[1] and result[2]:
            result[1] = [result[2][0]]
        if not result[2] and result[3]:
            result[2] = [result[3][0]]

        return result
    except Exception:
        return {
            1: ["meta-llama/llama-3.3-70b-instruct:free"],
            2: ["google/gemma-3-27b-it:free"],
            3: ["mistralai/mistral-small-3.1-24b-instruct:free"],
        }


# ---------------------------------------------------------------------------
# Module-level state — populated lazily or eagerly
# ---------------------------------------------------------------------------

_cached_tiers: dict[int, list[str]] | None = None


def _get_tiers() -> dict[int, list[str]]:
    global _cached_tiers
    if _cached_tiers is None:
        _cached_tiers = discover_free_models_sync()
    return _cached_tiers


def refresh_fleet() -> dict[int, list[str]]:
    """Force re-discovery from OpenRouter. Returns the new tiers."""
    global _cached_tiers
    _cached_tiers = discover_free_models_sync()
    return _cached_tiers


# Backwards-compatible module-level names (now dynamic properties via functions)
TierNumber = Literal[1, 2, 3]


# Module-level constants — eagerly populated for backwards compat
# These are snapshots; use _get_tiers() or refresh_fleet() for live data
TIER1_MODELS: list[str] = []
TIER2_MODELS: list[str] = []
TIER3_MODELS: list[str] = []
TIER_MODELS: dict[TierNumber, list[str]] = {1: [], 2: [], 3: []}  # type: ignore[dict-item]
ALL_FREE_MODELS: list[str] = []


def _populate_module_level() -> None:
    """Populate backwards-compatible module-level lists from live discovery."""
    global TIER1_MODELS, TIER2_MODELS, TIER3_MODELS, TIER_MODELS, ALL_FREE_MODELS
    tiers = _get_tiers()
    TIER1_MODELS[:] = tiers.get(1, [])
    TIER2_MODELS[:] = tiers.get(2, [])
    TIER3_MODELS[:] = tiers.get(3, [])
    TIER_MODELS[1] = TIER1_MODELS
    TIER_MODELS[2] = TIER2_MODELS
    TIER_MODELS[3] = TIER3_MODELS
    ALL_FREE_MODELS[:] = TIER1_MODELS + TIER2_MODELS + TIER3_MODELS


# Populate on import
try:
    _populate_module_level()
except Exception:
    logger.debug("Free fleet populate failed", exc_info=True)

#: Human-readable descriptions for each tier
TIER_DESCRIPTIONS: dict[TierNumber, str] = {
    1: "Heavy reasoning (analysis, complex code, research)",
    2: "General purpose (most swarm tasks, multilingual, code)",
    3: "Fast / lightweight (simple tasks, formatting, status checks)",
}


# ---------------------------------------------------------------------------
# Fleet config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FreeFleetConfig:
    """Immutable snapshot of the FREE_FLEET preset configuration.

    Attributes:
        tier_models: Mapping from tier number to ordered model list.
        default_tier: Tier used when no tier preference is specified.
        all_models: Flat ordered list of all free models (Tier 1 first).
        provider_type: String name of the ProviderType enum value to use.
    """

    tier_models: dict[int, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in TIER_MODELS.items()}
    )
    default_tier: TierNumber = 2
    all_models: list[str] = field(default_factory=lambda: list(ALL_FREE_MODELS))
    provider_type: str = "openrouter_free"

    def get_tier(self, tier: int) -> list[str]:
        """Return models for the given tier, or empty list if tier is invalid.

        Args:
            tier: Capability tier (1, 2, or 3).

        Returns:
            Ordered list of model identifiers for that tier.
        """
        return list(self.tier_models.get(tier, []))

    def preferred_model(self, tier: int | None = None) -> str:
        """Return the first (highest-priority) model for a tier.

        Args:
            tier: Capability tier.  If None, uses ``default_tier``.

        Returns:
            Model identifier string.

        Raises:
            ValueError: If the tier has no models configured.
        """
        resolved_tier = tier if tier is not None else self.default_tier
        models = self.get_tier(resolved_tier)
        if not models:
            raise ValueError(
                f"No models configured for tier {resolved_tier}. "
                f"Valid tiers: {sorted(self.tier_models)}"
            )
        return models[0]

    def fallback_chain(self, tier: int | None = None) -> list[str]:
        """Return full fallback chain starting from tier, descending to tier 3.

        If ``tier`` is 1, returns: all tier-1 models + tier-2 + tier-3.
        Useful for building a graceful-degradation model list.

        Args:
            tier: Starting tier.  If None, uses ``default_tier``.

        Returns:
            Ordered list of model identifiers across tiers.
        """
        start = tier if tier is not None else self.default_tier
        chain: list[str] = []
        for t in sorted(self.tier_models):
            if t >= start:
                chain.extend(self.tier_models[t])
        return chain


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: The canonical FREE_FLEET configuration singleton.
FREE_FLEET = FreeFleetConfig()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_tier_model(tier: int = 2) -> str:
    """Return the preferred model for ``tier`` from the FREE_FLEET preset.

    Args:
        tier: Capability tier (1=heavy reasoning, 2=general, 3=fast).

    Returns:
        Model identifier string suitable for use as ``LLMRequest.model``.
    """
    return FREE_FLEET.preferred_model(tier=tier)


def is_free_fleet_enabled() -> bool:
    """Return True if the DGC_FREE_FLEET environment flag is set.

    Checks ``DGC_FREE_FLEET`` env var for truthy values (1, true, yes, on).
    """
    raw = os.environ.get("DGC_FREE_FLEET", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def build_free_fleet_crew() -> list[dict]:
    """Build a ready-to-spawn crew using only free-tier models.

    Each agent role is mapped to an appropriate tier so that heavy reasoning
    roles get Tier-1 models and fast/support roles get Tier-3.

    Returns:
        List of crew spec dicts compatible with ``startup_crew.spawn_default_crew``.
    """
    from dharma_swarm.models import AgentRole, ProviderType

    # Researcher and cartographer benefit from heavy-reasoning tier
    tier1_model = FREE_FLEET.preferred_model(tier=1)
    tier2_model = FREE_FLEET.preferred_model(tier=2)
    tier3_model = FREE_FLEET.preferred_model(tier=3)

    return [
        {
            "name": "cartographer",
            "role": AgentRole.CARTOGRAPHER,
            "thread": "mechanistic",
            "provider": ProviderType.OPENROUTER_FREE,
            "model": tier1_model,
        },
        {
            "name": "surgeon",
            "role": AgentRole.SURGEON,
            "thread": "alignment",
            "provider": ProviderType.OPENROUTER_FREE,
            "model": tier1_model,
        },
        {
            "name": "architect",
            "role": AgentRole.ARCHITECT,
            "thread": "architectural",
            "provider": ProviderType.OPENROUTER_FREE,
            "model": tier2_model,
        },
        {
            "name": "researcher",
            "role": AgentRole.RESEARCHER,
            "thread": "scaling",
            "provider": ProviderType.OPENROUTER_FREE,
            "model": tier2_model,
        },
        {
            "name": "validator",
            "role": AgentRole.VALIDATOR,
            "thread": "scaling",
            "provider": ProviderType.OPENROUTER_FREE,
            "model": tier3_model,
        },
    ]


def free_fleet_summary(*, as_json: bool = False) -> str:
    """Return a human-readable or JSON summary of the FREE_FLEET preset.

    Args:
        as_json: If True, return compact JSON string instead of plain text.

    Returns:
        Formatted summary string.
    """
    import json

    if as_json:
        data = {
            "enabled": is_free_fleet_enabled(),
            "provider_type": FREE_FLEET.provider_type,
            "default_tier": FREE_FLEET.default_tier,
            "tiers": {
                str(tier): {
                    "description": TIER_DESCRIPTIONS.get(tier, ""),  # type: ignore[arg-type]
                    "models": models,
                }
                for tier, models in sorted(FREE_FLEET.tier_models.items())
            },
            "total_models": len(FREE_FLEET.all_models),
        }
        return json.dumps(data, indent=2)

    lines: list[str] = [
        "=== FREE_FLEET Configuration ===",
        f"Enabled (DGC_FREE_FLEET): {'yes' if is_free_fleet_enabled() else 'no'}",
        f"Provider type:   {FREE_FLEET.provider_type}",
        f"Default tier:    {FREE_FLEET.default_tier}",
        f"Total models:    {len(FREE_FLEET.all_models)}",
        "",
    ]
    for tier_num in sorted(FREE_FLEET.tier_models):
        desc = TIER_DESCRIPTIONS.get(tier_num, "")  # type: ignore[arg-type]
        lines.append(f"Tier {tier_num} — {desc}:")
        for model in FREE_FLEET.tier_models[tier_num]:
            lines.append(f"  {model}")
        lines.append("")

    lines.append(
        "To activate: export DGC_FREE_FLEET=1  (or pass --free-fleet to dgc up)"
    )
    return "\n".join(lines)


__all__ = [
    "ALL_FREE_MODELS",
    "FREE_FLEET",
    "FreeFleetConfig",
    "TIER1_MODELS",
    "TIER2_MODELS",
    "TIER3_MODELS",
    "TIER_DESCRIPTIONS",
    "TIER_MODELS",
    "TierNumber",
    "build_free_fleet_crew",
    "discover_free_models_sync",
    "free_fleet_summary",
    "get_tier_model",
    "is_free_fleet_enabled",
    "refresh_fleet",
]
