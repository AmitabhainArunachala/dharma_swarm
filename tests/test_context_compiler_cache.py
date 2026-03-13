"""Tests for ContextCompiler frozen snapshot (prompt cache) feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.context_compiler import ContextCompiler
from dharma_swarm.runtime_state import ContextBundleRecord


@pytest.fixture
def mock_compiler():
    """Create a ContextCompiler with mocked dependencies."""
    runtime = MagicMock()
    runtime.init_db = AsyncMock()
    runtime.get_session = AsyncMock(return_value=None)
    runtime.list_delegation_runs = AsyncMock(return_value=[])
    runtime.list_memory_facts = AsyncMock(return_value=[])
    runtime.list_artifacts = AsyncMock(return_value=[])
    runtime.list_workspace_leases = AsyncMock(return_value=[])
    runtime.new_bundle_id = MagicMock(return_value="bnd_test")
    runtime.record_context_bundle = AsyncMock(side_effect=lambda b: b)

    lattice = MagicMock()
    lattice.init_db = AsyncMock()
    lattice.replay_session = AsyncMock(return_value=[])
    lattice.recall = AsyncMock(return_value=[])
    lattice.always_on_context = AsyncMock(return_value="")

    return ContextCompiler(runtime_state=runtime, memory_lattice=lattice)


def _make_bundle(session_id: str = "sess_1", text: str = "frozen") -> ContextBundleRecord:
    """Create a minimal ContextBundleRecord for testing."""
    from datetime import datetime, timezone
    return ContextBundleRecord(
        bundle_id="bnd_frozen",
        session_id=session_id,
        task_id="",
        run_id="",
        token_budget=1200,
        rendered_text=text,
        sections=[],
        source_refs=[],
        checksum="abc123",
        created_at=datetime.now(timezone.utc),
        metadata={},
    )


class TestFrozenSnapshot:
    """Tests for freeze/thaw/is_frozen methods."""

    def test_freeze_and_is_frozen(self, mock_compiler):
        bundle = _make_bundle()
        assert mock_compiler.is_frozen("sess_1") is False
        mock_compiler.freeze("sess_1", bundle)
        assert mock_compiler.is_frozen("sess_1") is True

    def test_thaw_returns_bundle(self, mock_compiler):
        bundle = _make_bundle()
        mock_compiler.freeze("sess_1", bundle)
        thawed = mock_compiler.thaw("sess_1")
        assert thawed is bundle
        assert mock_compiler.is_frozen("sess_1") is False

    def test_thaw_nonexistent_returns_none(self, mock_compiler):
        assert mock_compiler.thaw("nonexistent") is None

    def test_multiple_sessions(self, mock_compiler):
        b1 = _make_bundle("s1", "first")
        b2 = _make_bundle("s2", "second")
        mock_compiler.freeze("s1", b1)
        mock_compiler.freeze("s2", b2)
        assert mock_compiler.is_frozen("s1") is True
        assert mock_compiler.is_frozen("s2") is True
        assert mock_compiler.thaw("s1").rendered_text == "first"
        assert mock_compiler.thaw("s2").rendered_text == "second"


class TestCompileBundleWithCache:
    """Tests that compile_bundle respects frozen snapshots."""

    @pytest.mark.asyncio
    async def test_returns_frozen_if_available(self, mock_compiler):
        bundle = _make_bundle("sess_1", "FROZEN CONTENT")
        mock_compiler.freeze("sess_1", bundle)

        result = await mock_compiler.compile_bundle(session_id="sess_1")
        assert result.rendered_text == "FROZEN CONTENT"
        # Runtime should NOT have been queried
        mock_compiler.runtime_state.get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_frozen(self, mock_compiler):
        bundle = _make_bundle("sess_1", "FROZEN")
        mock_compiler.freeze("sess_1", bundle)

        result = await mock_compiler.compile_bundle(
            session_id="sess_1", force_refresh=True
        )
        # Should have queried runtime (fresh compile)
        mock_compiler.runtime_state.get_session.assert_called_once()
        # Result should NOT be the frozen bundle
        assert result.rendered_text != "FROZEN"

    @pytest.mark.asyncio
    async def test_no_frozen_does_fresh_compile(self, mock_compiler):
        result = await mock_compiler.compile_bundle(session_id="sess_fresh")
        # Should have queried runtime
        mock_compiler.runtime_state.get_session.assert_called_once()
