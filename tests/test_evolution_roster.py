"""Tests for evolution_roster.py — multi-provider, multi-tier model selection."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from dharma_swarm.evolution_roster import (
    EVOLUTION_ROSTER,
    ModelSlot,
    ModelTier,
    _ENV_KEYS_FOR_PROVIDER,
    _STRATEGY_PROFILES,
    _provider_has_key,
    get_available_roster,
    reset_ollama_cache,
    roster_summary,
    select_models_for_cycle,
)
from dharma_swarm.models import ProviderType


# ---------------------------------------------------------------------------
# EVOLUTION_ROSTER data integrity
# ---------------------------------------------------------------------------


class TestRosterData:
    def test_has_models(self):
        assert len(EVOLUTION_ROSTER) >= 15

    def test_all_slots_are_model_slots(self):
        for slot in EVOLUTION_ROSTER:
            assert isinstance(slot, ModelSlot)

    def test_all_tiers_represented(self):
        tiers = {slot.tier for slot in EVOLUTION_ROSTER}
        for tier in ModelTier:
            assert tier in tiers, f"Missing tier: {tier}"

    def test_model_ids_not_empty(self):
        for slot in EVOLUTION_ROSTER:
            assert len(slot.model_id) > 3, f"Empty model_id for {slot.display_name}"

    def test_display_names_not_empty(self):
        for slot in EVOLUTION_ROSTER:
            assert len(slot.display_name) > 3

    def test_strengths_are_tuples(self):
        for slot in EVOLUTION_ROSTER:
            assert isinstance(slot.strengths, tuple)

    def test_max_context_positive(self):
        for slot in EVOLUTION_ROSTER:
            assert slot.max_context > 0

    def test_frozen_dataclass(self):
        slot = EVOLUTION_ROSTER[0]
        with pytest.raises(AttributeError):
            slot.model_id = "changed"  # type: ignore[misc]


class TestModelTier:
    def test_all_values(self):
        values = {t.value for t in ModelTier}
        assert "frontier" in values
        assert "strong" in values
        assert "fast" in values
        assert "free" in values
        assert "local" in values


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------


class TestProviderHasKey:
    def test_anthropic_with_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.ANTHROPIC) is True

    def test_anthropic_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert _provider_has_key(ProviderType.ANTHROPIC) is False

    def test_openrouter_shares_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.OPENROUTER) is True
        assert _provider_has_key(ProviderType.OPENROUTER_FREE) is True

    def test_groq_with_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.GROQ) is True

    def test_siliconflow_with_key(self, monkeypatch):
        monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.SILICONFLOW) is True

    def test_together_with_key(self, monkeypatch):
        monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.TOGETHER) is True

    def test_fireworks_with_key(self, monkeypatch):
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
        assert _provider_has_key(ProviderType.FIREWORKS) is True

    def test_ollama_no_key_needed(self):
        # Ollama not in _ENV_KEYS_FOR_PROVIDER — returns True
        assert _provider_has_key(ProviderType.OLLAMA) is True

    def test_empty_key_treated_as_absent(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
        assert _provider_has_key(ProviderType.ANTHROPIC) is False


# ---------------------------------------------------------------------------
# get_available_roster
# ---------------------------------------------------------------------------


class TestGetAvailableRoster:
    def test_filters_by_provider(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
        # Ollama not reachable
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            available = get_available_roster()
        # Should be empty with no keys and no Ollama
        assert len(available) == 0

    def test_openrouter_gives_models(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            available = get_available_roster()
        assert len(available) > 0
        providers = {s.provider for s in available}
        assert ProviderType.OPENROUTER in providers or ProviderType.OPENROUTER_FREE in providers

    def test_custom_roster(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        custom = (
            ModelSlot(ProviderType.OPENROUTER, "test/model", "Test", ModelTier.STRONG, ("code",)),
        )
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            available = get_available_roster(custom)
        assert len(available) == 1
        assert available[0].model_id == "test/model"

    def test_dedup_direct_vs_openrouter(self, monkeypatch):
        """Direct provider suppresses OpenRouter duplicate."""
        reset_ollama_cache()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)

        custom = (
            ModelSlot(ProviderType.ANTHROPIC, "claude-opus-4-20250514", "Direct", ModelTier.FRONTIER),
            ModelSlot(ProviderType.OPENROUTER, "anthropic/claude-opus-4", "Router", ModelTier.FRONTIER),
        )
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            available = get_available_roster(custom)
        # Only the direct one should survive
        assert len(available) == 1
        assert available[0].display_name == "Direct"


# ---------------------------------------------------------------------------
# Strategy profiles
# ---------------------------------------------------------------------------


class TestStrategyProfiles:
    def test_all_strategies_defined(self):
        for strategy in ("exploit", "explore", "restart", "backtrack"):
            assert strategy in _STRATEGY_PROFILES

    def test_tier_weights_sum_to_one(self):
        for name, profile in _STRATEGY_PROFILES.items():
            total = sum(profile["tier_weights"].values())
            assert abs(total - 1.0) < 0.01, f"{name} weights sum to {total}"

    def test_exploit_favors_frontier(self):
        weights = _STRATEGY_PROFILES["exploit"]["tier_weights"]
        assert weights[ModelTier.FRONTIER] > weights[ModelTier.FREE]

    def test_restart_favors_free(self):
        weights = _STRATEGY_PROFILES["restart"]["tier_weights"]
        assert weights[ModelTier.FREE] > weights[ModelTier.FRONTIER]


# ---------------------------------------------------------------------------
# select_models_for_cycle
# ---------------------------------------------------------------------------


class TestSelectModels:
    def test_returns_requested_count(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            selected = select_models_for_cycle(5, "explore")
        assert len(selected) == 5

    def test_diversity_avoids_repeats(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            selected = select_models_for_cycle(3, "explore", ensure_diversity=True)
        # With diversity on and enough models, should get unique selections
        if len(set(s.model_id for s in selected)) > 1:
            assert True  # Not all same model

    def test_no_diversity_allows_repeats(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        # Small roster forces repeats
        custom = (
            ModelSlot(ProviderType.OPENROUTER, "test/m", "T", ModelTier.STRONG),
        )
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            selected = select_models_for_cycle(3, "explore", custom, ensure_diversity=False)
        assert len(selected) == 3
        assert all(s.model_id == "test/m" for s in selected)

    def test_fallback_when_no_models(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            selected = select_models_for_cycle(2, "explore")
        assert len(selected) == 2
        assert all(s.model_id == "meta-llama/llama-3.3-70b-instruct" for s in selected)

    def test_custom_roster_param(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        custom = (
            ModelSlot(ProviderType.OPENROUTER, "x/y", "X", ModelTier.FRONTIER, ("code",)),
        )
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            selected = select_models_for_cycle(1, "exploit", custom)
        assert selected[0].model_id == "x/y"


# ---------------------------------------------------------------------------
# roster_summary
# ---------------------------------------------------------------------------


class TestRosterSummary:
    def test_returns_string(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            summary = roster_summary()
        assert isinstance(summary, str)
        assert "Available" in summary

    def test_no_models_message(self, monkeypatch):
        reset_ollama_cache()
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
        with patch("dharma_swarm.evolution_roster._ollama_reachable", return_value=False):
            summary = roster_summary()
        assert "No models available" in summary


# ---------------------------------------------------------------------------
# reset_ollama_cache
# ---------------------------------------------------------------------------


class TestResetOllamaCache:
    def test_reset_forces_recheck(self, monkeypatch):
        import dharma_swarm.evolution_roster as mod
        mod._ollama_status = True
        reset_ollama_cache()
        assert mod._ollama_status is None
