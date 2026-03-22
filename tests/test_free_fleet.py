"""Tests for the FREE_FLEET zero-cost OpenRouter model preset.

Covers:
  - Module constants and tier definitions (now auto-discovered)
  - FreeFleetConfig model selection per tier
  - Fallback chain construction
  - is_free_fleet_enabled env-flag detection
  - build_free_fleet_crew crew spec structure
  - free_fleet_summary output (text + JSON)
  - OpenRouterFreeProvider auto-discovery
  - dgc free-fleet CLI command (parser round-trip)
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Test: module-level constants (now live-discovered)
# ---------------------------------------------------------------------------


def test_all_free_models_populated() -> None:
    """ALL_FREE_MODELS must be non-empty after import (live discovery ran)."""
    from dharma_swarm.free_fleet import ALL_FREE_MODELS

    assert len(ALL_FREE_MODELS) >= 1, "No free models discovered"


def test_tier_models_are_non_empty() -> None:
    """All three tiers must contain at least one model."""
    from dharma_swarm.free_fleet import TIER_MODELS

    for tier_num in (1, 2, 3):
        assert TIER_MODELS[tier_num], f"Tier {tier_num} has no models"


def test_all_free_models_is_flat_union_of_tiers() -> None:
    """ALL_FREE_MODELS must be the union of all tier lists, no duplicates."""
    from dharma_swarm.free_fleet import ALL_FREE_MODELS, TIER_MODELS

    flat = [m for models in TIER_MODELS.values() for m in models]
    assert sorted(flat) == sorted(ALL_FREE_MODELS), (
        "ALL_FREE_MODELS does not match flat union of TIER_MODELS"
    )
    assert len(ALL_FREE_MODELS) == len(set(ALL_FREE_MODELS)), "Duplicate models in ALL_FREE_MODELS"


def test_every_model_has_free_suffix() -> None:
    """All model IDs must end with ':free' for zero-cost routing."""
    from dharma_swarm.free_fleet import ALL_FREE_MODELS

    bad = [m for m in ALL_FREE_MODELS if not m.endswith(":free")]
    assert not bad, f"Non-free models found: {bad}"


def test_refresh_fleet_repopulates() -> None:
    """refresh_fleet() should repopulate module-level lists."""
    from dharma_swarm.free_fleet import refresh_fleet, ALL_FREE_MODELS

    result = refresh_fleet()
    assert isinstance(result, dict)
    assert all(k in result for k in (1, 2, 3))
    assert len(ALL_FREE_MODELS) >= 1


# ---------------------------------------------------------------------------
# Test: FreeFleetConfig
# ---------------------------------------------------------------------------


def test_free_fleet_config_preferred_model_per_tier() -> None:
    """preferred_model() returns the first model in each tier."""
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS

    for tier_num in (1, 2, 3):
        expected = TIER_MODELS[tier_num][0]
        assert FREE_FLEET.preferred_model(tier=tier_num) == expected, (
            f"Tier {tier_num} preferred model mismatch"
        )


def test_free_fleet_config_default_tier_preferred_model() -> None:
    """preferred_model() without arg uses default_tier."""
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS

    default = FREE_FLEET.default_tier
    expected = TIER_MODELS[default][0]
    assert FREE_FLEET.preferred_model() == expected


def test_free_fleet_config_invalid_tier_raises() -> None:
    """preferred_model(tier=99) raises ValueError."""
    from dharma_swarm.free_fleet import FREE_FLEET

    try:
        FREE_FLEET.preferred_model(tier=99)
        raise AssertionError("Should have raised ValueError")
    except ValueError:
        pass


def test_free_fleet_config_get_tier_returns_copy() -> None:
    """get_tier() returns a copy; mutations do not affect the config."""
    from dharma_swarm.free_fleet import FREE_FLEET

    tier1 = FREE_FLEET.get_tier(1)
    tier1.append("injected-model:free")
    assert "injected-model:free" not in FREE_FLEET.get_tier(1)


def test_free_fleet_config_unknown_tier_returns_empty() -> None:
    """get_tier() returns empty list for unknown tier numbers."""
    from dharma_swarm.free_fleet import FREE_FLEET

    assert FREE_FLEET.get_tier(99) == []
    assert FREE_FLEET.get_tier(0) == []


# ---------------------------------------------------------------------------
# Test: tier fallback chain
# ---------------------------------------------------------------------------


def test_fallback_chain_tier1_includes_all_tiers() -> None:
    """Fallback chain from tier 1 must include models from tiers 1, 2, and 3."""
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS

    chain = FREE_FLEET.fallback_chain(tier=1)
    for tier_num in (1, 2, 3):
        for model in TIER_MODELS[tier_num]:
            assert model in chain, f"{model} missing from tier-1 fallback chain"


def test_fallback_chain_tier3_excludes_tier1_and_tier2() -> None:
    """Fallback chain from tier 3 must NOT include tier-1 or tier-2 models."""
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS

    chain = set(FREE_FLEET.fallback_chain(tier=3))
    for model in TIER_MODELS[1] + TIER_MODELS[2]:
        assert model not in chain, f"Tier-1/2 model {model} leaked into tier-3 chain"


def test_fallback_chain_tier2_includes_tier2_and_tier3() -> None:
    """Fallback chain from tier 2 includes tiers 2 and 3 but not tier 1."""
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS

    chain = FREE_FLEET.fallback_chain(tier=2)
    for model in TIER_MODELS[2] + TIER_MODELS[3]:
        assert model in chain
    for model in TIER_MODELS[1]:
        assert model not in chain, f"Tier-1 model {model} in tier-2 chain"


# ---------------------------------------------------------------------------
# Test: environment flag
# ---------------------------------------------------------------------------


def test_is_free_fleet_enabled_default_false() -> None:
    """is_free_fleet_enabled() returns False when env var is not set."""
    from dharma_swarm.free_fleet import is_free_fleet_enabled

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DGC_FREE_FLEET", None)
        assert not is_free_fleet_enabled()


def test_is_free_fleet_enabled_truthy_values() -> None:
    """is_free_fleet_enabled() returns True for '1', 'true', 'yes', 'on'."""
    from dharma_swarm.free_fleet import is_free_fleet_enabled

    for val in ("1", "true", "yes", "on", "True", "YES"):
        with patch.dict(os.environ, {"DGC_FREE_FLEET": val}):
            assert is_free_fleet_enabled(), f"Expected True for DGC_FREE_FLEET={val!r}"


def test_is_free_fleet_enabled_falsy_values() -> None:
    """is_free_fleet_enabled() returns False for '0', 'false', 'no', 'off'."""
    from dharma_swarm.free_fleet import is_free_fleet_enabled

    for val in ("0", "false", "no", "off", ""):
        with patch.dict(os.environ, {"DGC_FREE_FLEET": val}):
            assert not is_free_fleet_enabled(), f"Expected False for DGC_FREE_FLEET={val!r}"


# ---------------------------------------------------------------------------
# Test: build_free_fleet_crew
# ---------------------------------------------------------------------------


def test_build_free_fleet_crew_returns_non_empty_list() -> None:
    """build_free_fleet_crew() returns a non-empty list of crew specs."""
    from dharma_swarm.free_fleet import build_free_fleet_crew

    crew = build_free_fleet_crew()
    assert isinstance(crew, list)
    assert len(crew) >= 3, "Crew must have at least 3 agents"


def test_build_free_fleet_crew_all_use_openrouter_free_provider() -> None:
    """Every crew spec must use ProviderType.OPENROUTER_FREE."""
    from dharma_swarm.free_fleet import build_free_fleet_crew
    from dharma_swarm.models import ProviderType

    crew = build_free_fleet_crew()
    for spec in crew:
        assert spec["provider"] == ProviderType.OPENROUTER_FREE, (
            f"Agent {spec.get('name')} uses wrong provider: {spec.get('provider')}"
        )


def test_build_free_fleet_crew_models_are_free_tier() -> None:
    """Every crew spec must use a model that ends with ':free'."""
    from dharma_swarm.free_fleet import build_free_fleet_crew

    crew = build_free_fleet_crew()
    for spec in crew:
        model = spec.get("model", "")
        assert model.endswith(":free"), (
            f"Agent {spec.get('name')} has non-free model: {model}"
        )


def test_build_free_fleet_crew_has_required_keys() -> None:
    """Each crew spec must contain name, role, thread, provider, model keys."""
    from dharma_swarm.free_fleet import build_free_fleet_crew

    required_keys = {"name", "role", "thread", "provider", "model"}
    crew = build_free_fleet_crew()
    for spec in crew:
        missing = required_keys - set(spec.keys())
        assert not missing, f"Crew spec missing keys: {missing} in {spec}"


def test_build_free_fleet_crew_tier1_model_for_heavy_roles() -> None:
    """Cartographer and surgeon should get a Tier-1 model."""
    from dharma_swarm.free_fleet import FREE_FLEET, build_free_fleet_crew

    tier1_models = set(FREE_FLEET.get_tier(1))
    crew = {spec["name"]: spec for spec in build_free_fleet_crew()}

    for heavy_role in ("cartographer", "surgeon"):
        if heavy_role in crew:
            model = crew[heavy_role]["model"]
            assert model in tier1_models, (
                f"{heavy_role} should use a Tier-1 model, got {model}"
            )


# ---------------------------------------------------------------------------
# Test: free_fleet_summary
# ---------------------------------------------------------------------------


def test_free_fleet_summary_text_contains_all_tiers() -> None:
    """Plain-text summary must mention Tier 1, 2, and 3."""
    from dharma_swarm.free_fleet import free_fleet_summary

    summary = free_fleet_summary()
    for tier_num in (1, 2, 3):
        assert f"Tier {tier_num}" in summary, f"Tier {tier_num} missing from summary"


def test_free_fleet_summary_json_is_valid() -> None:
    """JSON summary must parse without error and contain tier data."""
    from dharma_swarm.free_fleet import free_fleet_summary

    raw = free_fleet_summary(as_json=True)
    data = json.loads(raw)
    assert "tiers" in data
    assert "total_models" in data
    assert data["total_models"] > 0
    assert "1" in data["tiers"]
    assert "2" in data["tiers"]
    assert "3" in data["tiers"]


def test_free_fleet_summary_json_enabled_flag_reflects_env() -> None:
    """JSON summary 'enabled' field reflects DGC_FREE_FLEET env var."""
    from dharma_swarm.free_fleet import free_fleet_summary

    with patch.dict(os.environ, {"DGC_FREE_FLEET": "1"}):
        data = json.loads(free_fleet_summary(as_json=True))
        assert data["enabled"] is True

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DGC_FREE_FLEET", None)
        data = json.loads(free_fleet_summary(as_json=True))
        assert data["enabled"] is False


# ---------------------------------------------------------------------------
# Test: OpenRouterFreeProvider auto-discovery
# ---------------------------------------------------------------------------


def test_openrouter_free_provider_has_get_free_models() -> None:
    """OpenRouterFreeProvider must expose get_free_models() classmethod."""
    from dharma_swarm.providers import OpenRouterFreeProvider

    assert hasattr(OpenRouterFreeProvider, "get_free_models")
    assert callable(OpenRouterFreeProvider.get_free_models)


def test_openrouter_free_provider_discovers_models() -> None:
    """Auto-discovery should find at least 3 free models on OpenRouter."""
    import asyncio
    from dharma_swarm.providers import OpenRouterFreeProvider

    # Reset cache to force fresh discovery
    OpenRouterFreeProvider._discovered_models = []
    OpenRouterFreeProvider._discovery_done = False

    async def _discover():
        return await OpenRouterFreeProvider.get_free_models()

    models = asyncio.run(_discover())
    assert len(models) >= 3, f"Expected >=3 free models, got {len(models)}: {models}"
    for m in models:
        assert m.endswith(":free"), f"Non-free model in roster: {m}"


# ---------------------------------------------------------------------------
# Test: CLI parser (dgc free-fleet)
# ---------------------------------------------------------------------------


def test_dgc_free_fleet_parser_registered() -> None:
    """The 'free-fleet' subcommand must be registered in the DGC argument parser."""
    from dharma_swarm.dgc_cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["free-fleet"])
    assert args.command == "free-fleet"
    assert args.tier is None
    assert args.json is False
    assert args.set_env is False


def test_dgc_free_fleet_parser_tier_arg() -> None:
    """The --tier argument must accept values 1, 2, 3."""
    from dharma_swarm.dgc_cli import _build_parser

    parser = _build_parser()
    for tier_val in (1, 2, 3):
        args = parser.parse_args(["free-fleet", "--tier", str(tier_val)])
        assert args.tier == tier_val


def test_dgc_free_fleet_parser_json_flag() -> None:
    """The --json flag must be parsed correctly."""
    from dharma_swarm.dgc_cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["free-fleet", "--json"])
    assert args.json is True


def test_dgc_free_fleet_parser_set_env_flag() -> None:
    """The --set-env flag must be parsed correctly."""
    from dharma_swarm.dgc_cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["free-fleet", "--set-env"])
    assert args.set_env is True


# ---------------------------------------------------------------------------
# Test: cmd_free_fleet output
# ---------------------------------------------------------------------------


def test_cmd_free_fleet_outputs_summary(capsys: Any) -> None:
    """cmd_free_fleet() with no args prints the fleet summary."""
    from dharma_swarm.dgc_cli import cmd_free_fleet

    cmd_free_fleet()
    captured = capsys.readouterr()
    assert "FREE_FLEET" in captured.out
    assert "Tier 1" in captured.out
    assert "Tier 2" in captured.out
    assert "Tier 3" in captured.out


def test_cmd_free_fleet_tier_filter(capsys: Any) -> None:
    """cmd_free_fleet(tier=1) only shows tier-1 models."""
    from dharma_swarm.dgc_cli import cmd_free_fleet
    from dharma_swarm.free_fleet import TIER_MODELS

    cmd_free_fleet(tier=1)
    captured = capsys.readouterr()
    for model in TIER_MODELS[1]:
        assert model in captured.out, f"Tier-1 model {model} missing from output"


def test_cmd_free_fleet_json_output(capsys: Any) -> None:
    """cmd_free_fleet(as_json=True) emits valid JSON."""
    from dharma_swarm.dgc_cli import cmd_free_fleet

    cmd_free_fleet(as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "tiers" in data


def test_cmd_free_fleet_set_env(capsys: Any) -> None:
    """cmd_free_fleet(set_env=True) prints the export command."""
    from dharma_swarm.dgc_cli import cmd_free_fleet

    cmd_free_fleet(set_env=True)
    captured = capsys.readouterr()
    assert "DGC_FREE_FLEET=1" in captured.out


def test_cmd_free_fleet_invalid_tier_exits(capsys: Any) -> None:
    """cmd_free_fleet(tier=99) raises SystemExit(1)."""
    import pytest
    from dharma_swarm.dgc_cli import cmd_free_fleet

    with pytest.raises(SystemExit) as exc_info:
        cmd_free_fleet(tier=99)
    assert exc_info.value.code == 1


def test_cmd_free_fleet_tier_json_output(capsys: Any) -> None:
    """cmd_free_fleet(tier=2, as_json=True) emits valid JSON with tier data."""
    from dharma_swarm.dgc_cli import cmd_free_fleet

    cmd_free_fleet(tier=2, as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["tier"] == 2
    assert "models" in data
    assert len(data["models"]) > 0
    for model in data["models"]:
        assert model.endswith(":free")
