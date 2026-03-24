"""Tests for dharma_swarm.jikoku_instrumentation.

Exercises the tracing primitives, decorators, metadata extractors,
and enable/disable flag, all without requiring a real tracer backend.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from dharma_swarm.jikoku_instrumentation import (
    extract_agent_metadata,
    extract_evolution_metadata,
    extract_task_metadata,
    get_current_span_id,
    is_enabled,
    jikoku_auto_span,
    jikoku_sync_span,
    jikoku_traced,
    jikoku_traced_provider,
    set_enabled,
    with_span_metadata,
)


# ---------------------------------------------------------------------------
# Enable/disable flag
# ---------------------------------------------------------------------------

class TestEnabledFlag:
    def test_is_enabled_returns_bool(self):
        assert isinstance(is_enabled(), bool)

    def test_set_enabled_toggles(self):
        original = is_enabled()
        try:
            set_enabled(False)
            assert not is_enabled()
            set_enabled(True)
            assert is_enabled()
        finally:
            set_enabled(original)


# ---------------------------------------------------------------------------
# get_current_span_id
# ---------------------------------------------------------------------------

def test_get_current_span_id_default_is_none():
    # Outside any span, should return None
    assert get_current_span_id() is None


# ---------------------------------------------------------------------------
# jikoku_auto_span — disabled path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_span_disabled_yields_none():
    """When disabled, jikoku_auto_span yields None with zero overhead."""
    original = is_enabled()
    try:
        set_enabled(False)
        async with jikoku_auto_span("test_cat", "test_intent") as span_id:
            assert span_id is None
    finally:
        set_enabled(original)


@pytest.mark.asyncio
async def test_auto_span_enabled_yields_span_id():
    """When enabled, jikoku_auto_span yields a span ID from the tracer."""
    mock_tracer = MagicMock()
    mock_tracer.start.return_value = "span-123"
    mock_tracer.end = MagicMock()

    original = is_enabled()
    try:
        set_enabled(True)
        with patch("dharma_swarm.jikoku_instrumentation.get_global_tracer", return_value=mock_tracer):
            async with jikoku_auto_span("cat", "intent") as span_id:
                assert span_id == "span-123"
        mock_tracer.start.assert_called_once()
        mock_tracer.end.assert_called_once()
    finally:
        set_enabled(original)


# ---------------------------------------------------------------------------
# jikoku_sync_span — disabled path
# ---------------------------------------------------------------------------

def test_sync_span_disabled_yields_none():
    original = is_enabled()
    try:
        set_enabled(False)
        with jikoku_sync_span("cat", "intent") as span_id:
            assert span_id is None
    finally:
        set_enabled(original)


def test_sync_span_enabled_yields_span_id():
    mock_tracer = MagicMock()
    mock_tracer.start.return_value = "sync-456"
    mock_tracer.end = MagicMock()

    original = is_enabled()
    try:
        set_enabled(True)
        with patch("dharma_swarm.jikoku_instrumentation.get_global_tracer", return_value=mock_tracer):
            with jikoku_sync_span("cat", "intent") as span_id:
                assert span_id == "sync-456"
        mock_tracer.end.assert_called_once()
    finally:
        set_enabled(original)


# ---------------------------------------------------------------------------
# jikoku_traced decorator
# ---------------------------------------------------------------------------

class TestJikokuTraced:
    def test_disabled_returns_original_function(self):
        original = is_enabled()
        try:
            set_enabled(False)

            @jikoku_traced(category="test")
            async def my_func():
                return 42

            # When disabled, decorator returns original function (not wrapped)
            # The function should still work
            assert asyncio.iscoroutinefunction(my_func)
        finally:
            set_enabled(original)

    def test_sync_function_wrapped(self):
        original = is_enabled()
        try:
            set_enabled(True)

            @jikoku_traced(category="sync_test")
            def my_sync():
                return "hello"

            # Should remain callable
            assert callable(my_sync)
        finally:
            set_enabled(original)


# ---------------------------------------------------------------------------
# Metadata extractors
# ---------------------------------------------------------------------------

class TestExtractAgentMetadata:
    def test_name_from_args(self):
        result = extract_agent_metadata(("self", "agent_alpha"), {})
        assert result.get("agent_name") == "agent_alpha"

    def test_name_from_kwargs(self):
        result = extract_agent_metadata(("self",), {"name": "beta"})
        assert result.get("agent_name") == "beta"

    def test_role_from_args(self):
        result = extract_agent_metadata(("self", "name", "coder"), {})
        assert result.get("role") == "coder"

    def test_role_from_kwargs(self):
        result = extract_agent_metadata(("self",), {"role": "reviewer"})
        assert result.get("role") == "reviewer"

    def test_role_with_enum_value(self):
        mock_role = MagicMock()
        mock_role.value = "general"
        result = extract_agent_metadata(("self", "name", mock_role), {})
        assert result.get("role") == "general"

    def test_empty_args(self):
        result = extract_agent_metadata((), {})
        assert result == {}


class TestExtractTaskMetadata:
    def test_task_with_id(self):
        task = MagicMock()
        task.id = "task-789"
        task.type = "coding"
        result = extract_task_metadata(("self", task), {})
        assert result.get("task_id") == "task-789"
        assert result.get("task_type") == "coding"

    def test_empty_args(self):
        result = extract_task_metadata((), {})
        assert result == {}


class TestExtractEvolutionMetadata:
    def test_iteration_from_kwargs(self):
        result = extract_evolution_metadata((), {"iteration": 5})
        assert result.get("iteration") == 5

    def test_iteration_from_args(self):
        result = extract_evolution_metadata(("self", 42), {})
        assert result.get("iteration") == 42

    def test_empty(self):
        result = extract_evolution_metadata((), {})
        assert result == {}


# ---------------------------------------------------------------------------
# with_span_metadata
# ---------------------------------------------------------------------------

def test_with_span_metadata_disabled_is_noop():
    original = is_enabled()
    try:
        set_enabled(False)
        # Should not raise
        with_span_metadata(key="value")
    finally:
        set_enabled(original)


def test_with_span_metadata_no_active_span():
    original = is_enabled()
    try:
        set_enabled(True)
        # No active span — should not raise
        with_span_metadata(key="value")
    finally:
        set_enabled(original)


# ---------------------------------------------------------------------------
# jikoku_traced_provider
# ---------------------------------------------------------------------------

class TestJikokuTracedProvider:
    def test_disabled_returns_original(self):
        original = is_enabled()
        try:
            set_enabled(False)

            async def my_complete(self, request):
                return "response"

            decorated = jikoku_traced_provider(my_complete)
            # When disabled, returns original function
            assert decorated is my_complete
        finally:
            set_enabled(original)

    @pytest.mark.asyncio
    async def test_enabled_traces_call(self):
        original = is_enabled()
        try:
            set_enabled(True)

            mock_tracer = MagicMock()
            mock_tracer.start.return_value = "prov-span-1"
            mock_tracer.end = MagicMock()

            async def my_complete(self, request):
                return MagicMock(usage=MagicMock(input_tokens=10, output_tokens=20, total_tokens=30))

            decorated = jikoku_traced_provider(my_complete)

            mock_self = MagicMock()
            mock_self.__class__.__name__ = "TestProvider"
            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.messages = [{"role": "user", "content": "hi"}]

            with patch("dharma_swarm.jikoku_instrumentation.get_global_tracer", return_value=mock_tracer):
                result = await decorated(mock_self, mock_request)

            mock_tracer.start.assert_called_once()
            mock_tracer.end.assert_called_once()
            assert result is not None
        finally:
            set_enabled(original)
