from __future__ import annotations

import json

from dharma_swarm.models import ProviderType


def test_resolve_model_pack_alias_for_top_open_models() -> None:
    from dharma_swarm.model_catalog import resolve_model_pack

    pack = resolve_model_pack("top open models")

    assert pack.name == "top_open_models"
    assert pack.entries
    assert ProviderType.OPENROUTER in pack.provider_types
    assert ProviderType.OLLAMA in pack.provider_types
    assert ProviderType.ANTHROPIC not in pack.provider_types
    assert ProviderType.OPENAI not in pack.provider_types


def test_model_pack_routing_metadata_for_tier_one_models() -> None:
    from dharma_swarm.model_catalog import model_pack_routing_metadata

    metadata = model_pack_routing_metadata("tier one models")

    assert metadata["model_catalog_selector"] == "tier1_models"
    assert metadata["allow_provider_routing"] is True
    assert metadata["available_provider_types"] == [ProviderType.OPENROUTER_FREE.value]
    assert metadata["preferred_provider"] == ProviderType.OPENROUTER_FREE.value
    assert str(metadata["preferred_model"]).endswith(":free")


def test_dgc_model_catalog_parser_registered() -> None:
    from dharma_swarm.dgc_cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["model-catalog", "tier one models", "--json"])

    assert args.command == "model-catalog"
    assert args.selector == "tier one models"
    assert args.json is True


def test_cmd_model_catalog_json_output(capsys) -> None:
    from dharma_swarm.dgc_cli import cmd_model_catalog

    cmd_model_catalog(selector="top open models", as_json=True)
    data = json.loads(capsys.readouterr().out)

    assert data["canonical_selector"] == "top_open_models"
    assert data["provider_types"]
    assert data["entries"]
