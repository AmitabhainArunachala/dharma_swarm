"""Tests for DarwinEngine._generate_real_diff — Phase 2 real diff generation.

Verifies the second LLM call that produces actual code diffs when the first
proposal-generation LLM call does not include one.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.evolution import DarwinEngine, Proposal
from dharma_swarm.models import LLMResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine_paths(tmp_path):
    """Return archive, traces, and predictor paths under tmp_path."""
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


@pytest.fixture
async def engine(engine_paths):
    """Create and initialize a DarwinEngine with tmp paths."""
    eng = DarwinEngine(**engine_paths)
    await eng.init()
    try:
        yield eng
    finally:
        await eng.close()


VALID_DIFF = """\
--- a/dharma_swarm/selector.py
+++ b/dharma_swarm/selector.py
@@ -10,6 +10,7 @@
 import logging
 
 logger = logging.getLogger(__name__)
+# Improvement: added structured logging for parent selection tracing
 
 
 def select_parent(entries):
"""


def _mock_provider(response_content: str) -> AsyncMock:
    """Create a mock provider that returns the given content."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=response_content,
            model="test-model",
            provider="test",
            usage={"total_tokens": 100},
        )
    )
    return provider


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestGenerateRealDiff:
    """Tests for DarwinEngine._generate_real_diff."""

    @pytest.mark.asyncio
    async def test_valid_diff_returned(self, engine):
        """When the provider returns a valid unified diff, it is returned."""
        provider = _mock_provider(VALID_DIFF)

        result = await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add structured logging for parent selection",
        )

        assert result == VALID_DIFF.strip()
        provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_response_returns_empty(self, engine):
        """When the provider returns 'SKIP', an empty string is returned."""
        provider = _mock_provider("SKIP")

        result = await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add structured logging",
        )

        assert result == ""
        provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_format_returns_empty(self, engine):
        """When the response doesn't start with '---', return empty."""
        provider = _mock_provider("Here is my suggestion:\nJust add a docstring.")

        result = await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add docstring",
        )

        assert result == ""
        provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_provider_exception_returns_empty(self, engine):
        """When the provider raises an exception, return empty (no crash)."""
        provider = AsyncMock()
        provider.complete = AsyncMock(
            side_effect=RuntimeError("LLM provider unavailable")
        )

        result = await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add error handling",
        )

        assert result == ""
        provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_component_skips_llm_call(self, engine):
        """When component is empty, no LLM call is made."""
        provider = _mock_provider(VALID_DIFF)

        result = await engine._generate_real_diff(
            provider=provider,
            component="",
            description="Some description",
        )

        assert result == ""
        provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_description_skips_llm_call(self, engine):
        """When description is empty, no LLM call is made."""
        provider = _mock_provider(VALID_DIFF)

        result = await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="",
        )

        assert result == ""
        provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_tracking(self, engine):
        """Token usage from diff generation is tracked."""
        provider = _mock_provider(VALID_DIFF)
        initial_tokens = engine._session_tokens_used

        await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add logging",
        )

        assert engine._session_tokens_used == initial_tokens + 100

    @pytest.mark.asyncio
    async def test_improvement_direction_passed_to_prompt(self, engine):
        """The improvement_direction is included in the LLM prompt."""
        provider = _mock_provider("SKIP")

        await engine._generate_real_diff(
            provider=provider,
            component="selector.py",
            description="Add logging",
            improvement_direction="Focus on performance optimization",
        )

        # Check the prompt content passed to the provider
        call_args = provider.complete.call_args
        request = call_args[0][0]  # First positional arg is the LLMRequest
        prompt_content = request.messages[0]["content"]
        assert "Focus on performance optimization" in prompt_content


class TestGenerateProposalWiresDiff:
    """Test that generate_proposal calls _generate_real_diff when diff is empty."""

    @pytest.mark.asyncio
    async def test_second_llm_call_when_first_has_no_diff(self, engine, tmp_path):
        """When the first LLM call returns no diff, _generate_real_diff is called."""
        # Create a source file for generate_proposal
        source_file = tmp_path / "test_module.py"
        source_file.write_text("def hello():\n    return 'world'\n")

        # First LLM call returns proposal without diff
        first_response = LLMResponse(
            content=(
                "COMPONENT: test_module.py\n"
                "CHANGE_TYPE: mutation\n"
                "DESCRIPTION: Add type hints to hello function\n"
                "THINK: Risk: minimal. Rollback: revert. Alternatives: none.\n"
            ),
            model="test-model",
            provider="test",
            usage={"total_tokens": 200},
        )

        # Second LLM call returns a real diff
        second_response = LLMResponse(
            content=VALID_DIFF,
            model="test-model",
            provider="test",
            usage={"total_tokens": 100},
        )

        provider = AsyncMock()
        provider.complete = AsyncMock(side_effect=[first_response, second_response])

        proposal = await engine.generate_proposal(
            provider=provider,
            source_file=source_file,
            model="test-model",
        )

        assert proposal is not None
        assert proposal.diff == VALID_DIFF.strip()
        # Two LLM calls: one for proposal, one for diff
        assert provider.complete.call_count == 2

    @pytest.mark.asyncio
    async def test_no_second_call_when_first_has_diff(self, engine, tmp_path):
        """When the first LLM call includes a diff, _generate_real_diff is NOT called."""
        source_file = tmp_path / "test_module.py"
        source_file.write_text("def hello():\n    return 'world'\n")

        # First LLM call returns proposal WITH diff
        first_response = LLMResponse(
            content=(
                "COMPONENT: test_module.py\n"
                "CHANGE_TYPE: mutation\n"
                "DESCRIPTION: Add type hints\n"
                "THINK: Risk: minimal.\n"
                "```diff\n"
                "--- a/test_module.py\n"
                "+++ b/test_module.py\n"
                "@@ -1,2 +1,2 @@\n"
                "-def hello():\n"
                "+def hello() -> str:\n"
                "     return 'world'\n"
                "```\n"
            ),
            model="test-model",
            provider="test",
            usage={"total_tokens": 200},
        )

        provider = AsyncMock()
        provider.complete = AsyncMock(return_value=first_response)

        proposal = await engine.generate_proposal(
            provider=provider,
            source_file=source_file,
            model="test-model",
        )

        assert proposal is not None
        assert proposal.diff  # Should have the diff from first pass
        # Only one LLM call — no second diff generation needed
        assert provider.complete.call_count == 1
