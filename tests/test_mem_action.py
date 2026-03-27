"""Tests for MemPO-style <mem> action format (dharma_swarm.mem_action)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.mem_action import (
    MemAction,
    MEM_INSTRUCTION,
    build_truncated_context,
    inject_mem_instruction,
    parse_mem_actions,
    store_mem_action,
    strip_mem_blocks,
)


# ── MemAction dataclass tests ─────────────────────────────────────────


class TestMemAction:
    def test_defaults(self):
        ma = MemAction()
        assert ma.content == ""
        assert ma.step_number == 0
        assert ma.confidence == 0.5
        assert ma.key_facts == []
        assert ma.key_skills == []

    def test_to_dict_roundtrip(self):
        ma = MemAction(
            content="Some summary",
            step_number=3,
            confidence=0.9,
            key_facts=["fact1", "fact2"],
            key_skills=["skill1"],
            agent_id="agent-x",
            task_id="task-y",
        )
        d = ma.to_dict()
        restored = MemAction.from_dict(d)
        assert restored.content == "Some summary"
        assert restored.step_number == 3
        assert restored.confidence == 0.9
        assert restored.key_facts == ["fact1", "fact2"]
        assert restored.key_skills == ["skill1"]
        assert restored.agent_id == "agent-x"
        assert restored.task_id == "task-y"

    def test_from_dict_minimal(self):
        ma = MemAction.from_dict({})
        assert ma.content == ""
        assert ma.confidence == 0.5

    def test_token_estimate(self):
        ma = MemAction(
            content="a" * 100,
            key_facts=["b" * 20, "c" * 20],
            key_skills=["d" * 40],
        )
        # (100 + 20 + 20 + 40) / 4 = 45
        assert ma.token_estimate == 45


# ── Parsing tests ──────────────────────────────────────────────────────


class TestParsing:
    def test_parse_simple_mem_block(self):
        text = "Some preamble\n<mem>\nThis is my memory summary.\n</mem>\nSome postamble"
        actions = parse_mem_actions(text)
        assert len(actions) == 1
        assert "memory summary" in actions[0].content

    def test_parse_multiple_mem_blocks(self):
        text = "<mem>Block 1</mem> middle text <mem>Block 2</mem>"
        actions = parse_mem_actions(text)
        assert len(actions) == 2
        assert actions[0].content == "Block 1"
        assert actions[1].content == "Block 2"

    def test_parse_empty_mem_block(self):
        text = "<mem></mem>"
        actions = parse_mem_actions(text)
        assert len(actions) == 0  # empty blocks are skipped

    def test_parse_with_whitespace(self):
        text = "<mem>  \n  content here  \n  </mem>"
        actions = parse_mem_actions(text)
        assert len(actions) == 1
        assert actions[0].content == "content here"

    def test_parse_structured_mem(self):
        text = """\
<mem>
confidence: 0.85
key_facts:
- The API uses REST endpoints
- Authentication is via JWT tokens
key_skills:
- Use pagination for large result sets
- Always validate input before processing
Overall, we've mapped the API surface and identified auth patterns.
</mem>"""
        actions = parse_mem_actions(text, agent_id="test-agent", task_id="task-1")
        assert len(actions) == 1
        ma = actions[0]
        assert ma.confidence == 0.85
        assert len(ma.key_facts) == 2
        assert "REST endpoints" in ma.key_facts[0]
        assert "JWT tokens" in ma.key_facts[1]
        assert len(ma.key_skills) == 2
        assert "pagination" in ma.key_skills[0]
        assert ma.agent_id == "test-agent"
        assert ma.task_id == "task-1"

    def test_parse_confidence_clamped(self):
        text = "<mem>\nconfidence: 1.5\nsome text\n</mem>"
        actions = parse_mem_actions(text)
        assert actions[0].confidence == 1.0

    def test_parse_confidence_invalid_falls_to_default(self):
        # Negative values don't match the regex ([\d.]+), so default 0.5 is used
        text = "<mem>\nconfidence: -0.3\nsome text\n</mem>"
        actions = parse_mem_actions(text)
        assert actions[0].confidence == 0.5

    def test_parse_no_mem_blocks(self):
        text = "This is just regular text with no mem blocks."
        actions = parse_mem_actions(text)
        assert len(actions) == 0

    def test_parse_mem_with_step_number(self):
        text = "<mem>summary</mem>"
        actions = parse_mem_actions(text, step_number=5)
        assert actions[0].step_number == 5

    def test_parse_key_facts_alternate_header(self):
        text = "<mem>\nfacts:\n- fact A\n- fact B\n</mem>"
        actions = parse_mem_actions(text)
        assert len(actions[0].key_facts) == 2

    def test_parse_key_skills_alternate_header(self):
        text = "<mem>\npatterns:\n- pattern X\n</mem>"
        actions = parse_mem_actions(text)
        assert len(actions[0].key_skills) == 1

    def test_strip_mem_blocks(self):
        text = "Before <mem>content</mem> After"
        stripped = strip_mem_blocks(text)
        assert stripped == "Before  After"

    def test_strip_multiple_mem_blocks(self):
        text = "A <mem>1</mem> B <mem>2</mem> C"
        stripped = strip_mem_blocks(text)
        assert "A" in stripped
        assert "B" in stripped
        assert "C" in stripped
        assert "<mem>" not in stripped


# ── Prompt injection tests ─────────────────────────────────────────────


class TestPromptInjection:
    def test_inject_adds_instruction(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_ACTION", "true")
        prompt = "You are a helpful agent."
        result = inject_mem_instruction(prompt)
        assert "<mem>" in result
        assert "key_facts" in result

    def test_inject_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_ACTION", "false")
        prompt = "You are a helpful agent."
        result = inject_mem_instruction(prompt)
        assert result == prompt

    def test_inject_off(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_ACTION", "off")
        prompt = "You are a helpful agent."
        result = inject_mem_instruction(prompt)
        assert result == prompt

    def test_inject_default_enabled(self, monkeypatch):
        monkeypatch.delenv("ENABLE_MEM_ACTION", raising=False)
        prompt = "You are a helpful agent."
        result = inject_mem_instruction(prompt)
        assert "<mem>" in result

    def test_inject_no_duplication(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_ACTION", "true")
        prompt = "Already has <mem> in it."
        result = inject_mem_instruction(prompt)
        # Should not add another <mem> block
        assert result == prompt


# ── Context truncation tests ───────────────────────────────────────────


class TestContextTruncation:
    def test_truncation_enabled_with_mem(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_TRUNCATION", "true")
        mem = MemAction(
            content="Previous summary of work done.",
            key_facts=["fact A", "fact B"],
            key_skills=["skill X"],
        )
        result = build_truncated_context(
            system_prompt="You are an agent.",
            previous_mem=mem,
            current_query="Now do the next step.",
        )
        assert "You are an agent." in result
        assert "Previous summary of work done." in result
        assert "fact A" in result
        assert "skill X" in result
        assert "Now do the next step." in result

    def test_truncation_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_TRUNCATION", "false")
        mem = MemAction(content="summary")
        result = build_truncated_context(
            system_prompt="sys",
            previous_mem=mem,
            current_query="query",
        )
        assert result == ""  # Signal to use full context

    def test_truncation_no_previous_mem(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_TRUNCATION", "true")
        result = build_truncated_context(
            system_prompt="sys",
            previous_mem=None,
            current_query="query",
        )
        assert result == ""

    def test_truncation_empty_mem_content(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_TRUNCATION", "true")
        mem = MemAction(content="")
        result = build_truncated_context(
            system_prompt="sys",
            previous_mem=mem,
            current_query="query",
        )
        # Empty content means no truncation
        assert result == ""

    def test_truncation_with_only_facts(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEM_TRUNCATION", "true")
        mem = MemAction(
            content="summary",
            key_facts=["fact1"],
            key_skills=[],
        )
        result = build_truncated_context(
            system_prompt="sys",
            previous_mem=mem,
            current_query="query",
        )
        assert "Key Facts" in result
        assert "Learned Patterns" not in result


# ── Memory Palace storage tests ────────────────────────────────────────


class TestStoreMemAction:
    @pytest.mark.asyncio
    async def test_store_full_mem_action(self):
        palace = MagicMock()
        palace.ingest = AsyncMock()

        mem = MemAction(
            content="Summary of work",
            key_facts=["fact1", "fact2"],
            key_skills=["skill1"],
            agent_id="agent-a",
            task_id="task-b",
            step_number=3,
            confidence=0.8,
        )

        await store_mem_action(palace, mem)

        # Should have called ingest for: summary + 2 facts + 1 skill = 4 calls
        assert palace.ingest.call_count == 4

    @pytest.mark.asyncio
    async def test_store_empty_content_noop(self):
        palace = MagicMock()
        palace.ingest = AsyncMock()

        mem = MemAction(content="")
        await store_mem_action(palace, mem)
        palace.ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_no_palace_noop(self):
        mem = MemAction(content="something")
        await store_mem_action(None, mem)  # Should not raise

    @pytest.mark.asyncio
    async def test_store_palace_without_ingest(self):
        palace = object()  # No ingest method
        mem = MemAction(content="something")
        await store_mem_action(palace, mem)  # Should not raise

    @pytest.mark.asyncio
    async def test_store_ingest_failure_nonfatal(self):
        palace = MagicMock()
        palace.ingest = AsyncMock(side_effect=RuntimeError("boom"))

        mem = MemAction(
            content="Summary",
            key_facts=["fact"],
            agent_id="a",
            task_id="t",
        )
        # Should not raise
        await store_mem_action(palace, mem)


# ── Integration test: parse → store cycle ──────────────────────────────


class TestParseAndStore:
    @pytest.mark.asyncio
    async def test_end_to_end_parse_and_store(self):
        """Parse <mem> from agent output, then store in palace."""
        agent_output = """\
I've completed the analysis.

<mem>
confidence: 0.9
key_facts:
- The database has 15 tables
- Users table has 10M rows
- No indexes on created_at columns
key_skills:
- Always check index coverage before query optimization
Summary: Database analysis complete. Main bottleneck is missing indexes.
</mem>

The next step is to add the missing indexes.
"""
        palace = MagicMock()
        palace.ingest = AsyncMock()

        actions = parse_mem_actions(
            agent_output,
            agent_id="analyst",
            task_id="db-audit",
            step_number=2,
        )
        assert len(actions) == 1
        ma = actions[0]
        assert ma.confidence == 0.9
        assert len(ma.key_facts) == 3
        assert len(ma.key_skills) == 1

        await store_mem_action(palace, ma)
        # 1 summary + 3 facts + 1 skill = 5
        assert palace.ingest.call_count == 5

        # Verify fact tags
        fact_calls = [
            c for c in palace.ingest.call_args_list
            if "propositional" in (c.kwargs.get("tags") or c[1].get("tags", []))
        ]
        assert len(fact_calls) == 3
