"""Tests for conductor configurations."""

from __future__ import annotations

from dharma_swarm.conductors import (
    CONDUCTOR_CLAUDE_CONFIG,
    CONDUCTOR_CODEX_CONFIG,
    CONDUCTOR_CONFIGS,
)
from dharma_swarm.models import AgentRole, ProviderType


class TestConductorConfigs:
    def test_two_conductors(self):
        assert len(CONDUCTOR_CONFIGS) == 2

    def test_claude_config(self):
        cfg = CONDUCTOR_CLAUDE_CONFIG
        assert cfg["name"] == "conductor_claude"
        assert cfg["role"] == AgentRole.CONDUCTOR
        assert cfg["provider_type"] == ProviderType.ANTHROPIC
        assert cfg["model"] == "claude-opus-4-6"
        assert cfg["wake_interval_seconds"] == 3600.0
        assert cfg["max_turns"] == 15
        assert "v7" in cfg["system_prompt"].lower() or "non-negotiable" in cfg["system_prompt"].lower()

    def test_codex_config(self):
        cfg = CONDUCTOR_CODEX_CONFIG
        assert cfg["name"] == "conductor_codex"
        assert cfg["role"] == AgentRole.CONDUCTOR
        assert cfg["provider_type"] == ProviderType.ANTHROPIC
        assert cfg["model"] == "claude-sonnet-4-20250514"
        assert cfg["wake_interval_seconds"] == 1800.0
        assert cfg["max_turns"] == 10

    def test_unique_names(self):
        names = [c["name"] for c in CONDUCTOR_CONFIGS]
        assert len(names) == len(set(names))

    def test_all_have_required_keys(self):
        required = {"name", "role", "provider_type", "model", "wake_interval_seconds", "system_prompt", "max_turns"}
        for cfg in CONDUCTOR_CONFIGS:
            assert required.issubset(cfg.keys()), f"Missing keys in {cfg['name']}"

    def test_system_prompts_nonempty(self):
        for cfg in CONDUCTOR_CONFIGS:
            assert len(cfg["system_prompt"]) > 100
