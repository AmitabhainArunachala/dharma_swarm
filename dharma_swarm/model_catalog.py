"""Canonical model-pack catalog for human-friendly routing selectors.

Provider defaults live in ``model_hierarchy.py`` and live free-tier OpenRouter
rosters live in ``free_fleet.py``. This module composes those sources into
named packs such as ``top_open_models`` and ``tier1_models`` so agents,
workers, the CLI, and docs can all point at one shared vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Mapping

from dharma_swarm.model_hierarchy import (
    DELEGATED_RESEARCH_PRIORITY,
    PRIMARY_DRIVER_LANES,
    default_model as canonical_default_model,
    get_tier,
    provider_lane_role,
)
from dharma_swarm.models import ProviderType

_SELECTOR_KEYS = (
    "model_catalog_selector",
    "model_pack",
    "provider_pack",
    "model_selector",
)

_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3"}
_FILLER_TOKENS = {
    "canonical",
    "current",
    "load",
    "me",
    "pack",
    "please",
    "show",
    "the",
    "use",
}

_OPEN_MODEL_PROVIDER_PRIORITY: tuple[ProviderType, ...] = tuple(
    provider
    for provider in DELEGATED_RESEARCH_PRIORITY
    if provider not in {ProviderType.GOOGLE_AI, ProviderType.MISTRAL}
)


@dataclass(frozen=True)
class ModelCatalogEntry:
    provider_type: ProviderType
    provider: str
    model: str
    tier: str
    lane_role: str
    source: str


@dataclass(frozen=True)
class ModelPack:
    name: str
    description: str
    provider_types: tuple[ProviderType, ...]
    entries: tuple[ModelCatalogEntry, ...]


def _dedupe_provider_types(items: list[ProviderType]) -> tuple[ProviderType, ...]:
    seen: set[ProviderType] = set()
    out: list[ProviderType] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _normalize_selector(selector: str) -> str:
    lowered = str(selector or "").strip().lower()
    if not lowered:
        return ""
    tokens = [
        _NUMBER_WORDS.get(token, token)
        for token in re.split(r"[^a-z0-9]+", lowered)
        if token
    ]
    normalized = [token for token in tokens if token not in _FILLER_TOKENS]
    if not normalized:
        normalized = tokens
    return " ".join(normalized)


def _provider_entries(
    providers: tuple[ProviderType, ...],
    *,
    source: str,
) -> tuple[ModelCatalogEntry, ...]:
    entries: list[ModelCatalogEntry] = []
    for provider in providers:
        model = canonical_default_model(provider)
        if not model:
            continue
        entries.append(
            ModelCatalogEntry(
                provider_type=provider,
                provider=provider.value,
                model=model,
                tier=get_tier(provider),
                lane_role=provider_lane_role(provider).value,
                source=source,
            )
        )
    return tuple(entries)


def _free_tier_entries(tier: int | None = None) -> tuple[ModelCatalogEntry, ...]:
    from dharma_swarm.free_fleet import FREE_FLEET

    models = FREE_FLEET.get_tier(tier) if tier is not None else list(FREE_FLEET.all_models)
    provider = ProviderType.OPENROUTER_FREE
    return tuple(
        ModelCatalogEntry(
            provider_type=provider,
            provider=provider.value,
            model=model,
            tier=f"free_tier_{tier}" if tier is not None else "free",
            lane_role=provider_lane_role(provider).value,
            source="free_fleet",
        )
        for model in models
    )


def _catalog_packs() -> dict[str, ModelPack]:
    top_open_entries = _provider_entries(
        _dedupe_provider_types(list(_OPEN_MODEL_PROVIDER_PRIORITY)),
        source="model_hierarchy",
    )
    driver_entries = _provider_entries(
        _dedupe_provider_types(list(PRIMARY_DRIVER_LANES) + [ProviderType.OPENAI]),
        source="model_hierarchy",
    )
    free_entries = _free_tier_entries()
    tier1_entries = _free_tier_entries(1)
    tier2_entries = _free_tier_entries(2)
    tier3_entries = _free_tier_entries(3)
    return {
        "top_open_models": ModelPack(
            name="top_open_models",
            description="Top open-model lanes across the shared routing hierarchy.",
            provider_types=_dedupe_provider_types(
                [entry.provider_type for entry in top_open_entries]
            ),
            entries=top_open_entries,
        ),
        "driver_models": ModelPack(
            name="driver_models",
            description="Primary driver lanes for sovereign execution and escalation.",
            provider_types=_dedupe_provider_types(
                [entry.provider_type for entry in driver_entries]
            ),
            entries=driver_entries,
        ),
        "free_models": ModelPack(
            name="free_models",
            description="All live free-tier OpenRouter models discovered by FREE_FLEET.",
            provider_types=(ProviderType.OPENROUTER_FREE,),
            entries=free_entries,
        ),
        "tier1_models": ModelPack(
            name="tier1_models",
            description="FREE_FLEET tier 1: heaviest free reasoning models.",
            provider_types=(ProviderType.OPENROUTER_FREE,),
            entries=tier1_entries,
        ),
        "tier2_models": ModelPack(
            name="tier2_models",
            description="FREE_FLEET tier 2: general-purpose free models.",
            provider_types=(ProviderType.OPENROUTER_FREE,),
            entries=tier2_entries,
        ),
        "tier3_models": ModelPack(
            name="tier3_models",
            description="FREE_FLEET tier 3: fastest/lightest free models.",
            provider_types=(ProviderType.OPENROUTER_FREE,),
            entries=tier3_entries,
        ),
    }


_ALIASES: dict[str, str] = {
    "open": "top_open_models",
    "open model": "top_open_models",
    "open models": "top_open_models",
    "top open": "top_open_models",
    "top open model": "top_open_models",
    "top open models": "top_open_models",
    "driver": "driver_models",
    "driver model": "driver_models",
    "driver models": "driver_models",
    "primary driver": "driver_models",
    "primary drivers": "driver_models",
    "free": "free_models",
    "free model": "free_models",
    "free models": "free_models",
    "tier 1": "tier1_models",
    "tier 1 model": "tier1_models",
    "tier 1 models": "tier1_models",
    "tier1": "tier1_models",
    "tier1 model": "tier1_models",
    "tier1 models": "tier1_models",
    "free tier 1": "tier1_models",
    "tier 2": "tier2_models",
    "tier 2 model": "tier2_models",
    "tier 2 models": "tier2_models",
    "tier2": "tier2_models",
    "tier2 model": "tier2_models",
    "tier2 models": "tier2_models",
    "free tier 2": "tier2_models",
    "tier 3": "tier3_models",
    "tier 3 model": "tier3_models",
    "tier 3 models": "tier3_models",
    "tier3": "tier3_models",
    "tier3 model": "tier3_models",
    "tier3 models": "tier3_models",
    "free tier 3": "tier3_models",
}


def available_model_packs() -> dict[str, ModelPack]:
    """Return the canonical model-pack registry."""
    return _catalog_packs()


def resolve_model_pack(selector: str) -> ModelPack:
    """Resolve a human-friendly selector such as ``top open models``."""
    packs = _catalog_packs()
    normalized = _normalize_selector(selector)
    if normalized in packs:
        return packs[normalized]
    alias = _ALIASES.get(normalized)
    if alias and alias in packs:
        return packs[alias]
    raise KeyError(f"Unknown model catalog selector: {selector!r}")


def model_pack_routing_metadata(selector: str) -> dict[str, Any]:
    """Translate a model-pack selector into routing metadata keys."""
    pack = resolve_model_pack(selector)
    metadata: dict[str, Any] = {
        "model_catalog_selector": pack.name,
        "allow_provider_routing": True,
        "available_provider_types": [provider.value for provider in pack.provider_types],
    }
    if pack.entries:
        metadata["preferred_provider"] = pack.entries[0].provider_type.value
        metadata["preferred_model"] = pack.entries[0].model
    return metadata


def selector_from_metadata(*metadatas: Mapping[str, Any] | None) -> str | None:
    """Return the first catalog selector found in metadata mappings."""
    for metadata in metadatas:
        if not isinstance(metadata, Mapping):
            continue
        for key in _SELECTOR_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def apply_model_pack_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge canonical pack-derived routing keys into a metadata mapping."""
    merged = dict(metadata or {})
    selector = selector_from_metadata(merged)
    if selector is None:
        return merged
    derived = model_pack_routing_metadata(selector)
    merged.setdefault("model_catalog_selector", derived["model_catalog_selector"])
    for key, value in derived.items():
        merged.setdefault(key, value)
    return merged


def model_catalog_summary(
    *,
    selector: str | None = None,
    as_json: bool = False,
) -> str:
    """Return a human-readable or JSON summary of the catalog."""
    if selector:
        pack = resolve_model_pack(selector)
        payload = {
            "canonical_selector": pack.name,
            "description": pack.description,
            "provider_types": [provider.value for provider in pack.provider_types],
            "entries": [asdict(entry) for entry in pack.entries],
        }
        if as_json:
            return json.dumps(payload, indent=2)
        lines = [
            f"{pack.name}: {pack.description}",
            f"Providers: {', '.join(payload['provider_types']) or '(none)'}",
        ]
        for entry in pack.entries:
            lines.append(
                f"- {entry.provider} -> {entry.model} [{entry.tier}/{entry.lane_role}]"
            )
        return "\n".join(lines)

    packs = _catalog_packs()
    payload = {
        "packs": {
            name: {
                "description": pack.description,
                "provider_types": [provider.value for provider in pack.provider_types],
                "entry_count": len(pack.entries),
            }
            for name, pack in packs.items()
        }
    }
    if as_json:
        return json.dumps(payload, indent=2)
    lines = ["Canonical model catalog:"]
    for name, pack in packs.items():
        providers = ", ".join(provider.value for provider in pack.provider_types) or "(none)"
        lines.append(f"- {name}: {pack.description} [{providers}]")
    return "\n".join(lines)


__all__ = [
    "ModelCatalogEntry",
    "ModelPack",
    "apply_model_pack_metadata",
    "available_model_packs",
    "model_catalog_summary",
    "model_pack_routing_metadata",
    "resolve_model_pack",
    "selector_from_metadata",
]
