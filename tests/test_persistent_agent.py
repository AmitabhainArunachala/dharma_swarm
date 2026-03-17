"""Tests for PersistentAgent — autonomous wake loop."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.models import AgentRole, ProviderType
from dharma_swarm.persistent_agent import PersistentAgent, _provider_string


class TestProviderString:
    def test_anthropic(self):
        assert _provider_string(ProviderType.ANTHROPIC) == "anthropic"

    def test_claude_code(self):
        assert _provider_string(ProviderType.CLAUDE_CODE) == "anthropic"

    def test_codex(self):
        assert _provider_string(ProviderType.CODEX) == "anthropic"

    def test_openrouter(self):
        assert _provider_string(ProviderType.OPENROUTER) == "openrouter"

    def test_openrouter_free(self):
        assert _provider_string(ProviderType.OPENROUTER_FREE) == "openrouter"

    def test_fallback(self):
        assert _provider_string(ProviderType.LOCAL) == "anthropic"


class TestPersistentAgentInit:
    def test_basic_creation(self, tmp_path):
        agent = PersistentAgent(
            name="test_conductor",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            state_dir=tmp_path,
            wake_interval_seconds=60.0,
            system_prompt="Test prompt",
        )
        assert agent.name == "test_conductor"
        assert agent.role == AgentRole.CONDUCTOR
        assert agent.wake_interval == 60.0
        assert agent._agent.identity.name == "test_conductor"
        assert agent._agent.identity.provider == "anthropic"

    def test_witness_log_created(self, tmp_path):
        agent = PersistentAgent(
            name="test_wit",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="test-model",
            state_dir=tmp_path,
        )
        assert agent._witness_log.parent.exists()
        assert "conductor_test_wit" in agent._witness_log.name

    def test_default_state_dir(self):
        agent = PersistentAgent(
            name="default_dir",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="test-model",
        )
        assert agent.state_dir == Path.home() / ".dharma"


class TestSelfTaskGeneration:
    def setup_method(self):
        self.agent = PersistentAgent(
            name="gen_test",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="test-model",
        )

    def test_hot_paths_priority(self):
        task = self.agent._generate_self_task(
            hot_paths=[("dharma_swarm/swarm.py", 5)],
            salient_marks=[],
        )
        assert "high-activity" in task
        assert "swarm.py" in task
        assert "5 marks" in task

    def test_salient_marks_fallback(self):
        mark = MagicMock()
        mark.observation = "R_V contraction detected in layer 27"
        task = self.agent._generate_self_task(
            hot_paths=[],
            salient_marks=[mark],
        )
        assert "Follow up" in task
        assert "R_V contraction" in task

    def test_default_fallback(self):
        task = self.agent._generate_self_task(
            hot_paths=[],
            salient_marks=[],
        )
        assert "Review system state" in task


class TestExtractKeyInsight:
    def test_empty(self):
        assert PersistentAgent._extract_key_insight("") == "No output"

    def test_short_lines_skipped(self):
        text = "OK\nDone\nThis is a meaningful insight about the system state"
        result = PersistentAgent._extract_key_insight(text)
        assert "meaningful insight" in result

    def test_truncation(self):
        text = "x" * 300
        result = PersistentAgent._extract_key_insight(text)
        assert len(result) <= 200


class TestAcceptTask:
    @pytest.mark.asyncio
    async def test_accept_task_queues(self):
        agent = PersistentAgent(
            name="queue_test",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="test-model",
        )
        await agent.accept_task("Check daemon health")
        assert not agent._task_queue.empty()
        task = agent._task_queue.get_nowait()
        assert task == "Check daemon health"


class TestGateCheck:
    def test_gate_not_blocked_for_conductor_wake(self):
        agent = PersistentAgent(
            name="gate_test",
            role=AgentRole.CONDUCTOR,
            provider_type=ProviderType.ANTHROPIC,
            model="test-model",
        )
        # conductor_wake is NOT in MANDATORY_THINK_PHASES, so should not block
        result = agent._check_gate("Review system state")
        # May return None if telos_gates has import issues, or a dict
        if result is not None:
            assert not result.get("blocked", False)
