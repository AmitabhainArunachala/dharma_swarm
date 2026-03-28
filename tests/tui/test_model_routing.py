"""Tests for TUI model routing helpers."""

from __future__ import annotations

from dharma_swarm.tui.model_routing import (
    default_target,
    detect_inline_switch_intent,
    fallback_chain,
    resolve_strategy,
    resolve_model_target,
    target_by_index,
)


def test_default_target_is_claude_sonnet() -> None:
    target = default_target()
    # Default is now GLM-5 (free frontier) per model_hierarchy.py
    assert target.provider_id == "ollama"
    assert target.model_id == "glm-5:cloud"


def test_resolve_alias_and_model_id() -> None:
    assert resolve_model_target("opus 4.6") is not None
    assert resolve_model_target("claude-opus-4-6") is not None
    assert resolve_model_target("openai/gpt-5-codex") is not None
    minimax = resolve_model_target("minimax")
    assert minimax is not None
    assert minimax.model_id == "minimax-m2.7:cloud"
    assert resolve_model_target("not-a-real-model") is None


def test_inline_switch_detection() -> None:
    target = detect_inline_switch_intent("hey, switch to codex 5.4")
    assert target is not None
    assert target.provider_id == "codex"
    assert target.model_id == "gpt-5.4"

    assert detect_inline_switch_intent("can you summarize this text?") is None


def test_fallback_chain_excludes_current() -> None:
    chain = fallback_chain("claude", "claude-sonnet-4-5")
    assert chain
    assert all(
        not (t.provider_id == "claude" and t.model_id == "claude-sonnet-4-5")
        for t in chain
    )


def test_strategy_aliases_resolve() -> None:
    assert resolve_strategy("fast") == "responsive"
    assert resolve_strategy("budget") == "cost"
    assert resolve_strategy("best") == "genius"
    assert resolve_strategy("unknown") is None


def test_target_by_index_maps_in_model_list_order() -> None:
    first = target_by_index(1)
    assert first is not None
    # First target is now GLM-5 (free frontier) per model_hierarchy.py
    assert first.alias == "glm-5"
    assert target_by_index(999) is None
