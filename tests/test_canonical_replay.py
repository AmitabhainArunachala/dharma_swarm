"""Tests for canonical replay harness."""

import asyncio
import pytest
from pathlib import Path
from dharma_swarm.canonical_replay import (
    CanonicalReplayEngine,
    ReplayResult,
)


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary log directory."""
    log_dir = tmp_path / "events"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def replay_engine(temp_log_dir):
    """Create a replay engine with temp directory."""
    return CanonicalReplayEngine(temp_log_dir)


def test_replay_engine_init(temp_log_dir):
    """CanonicalReplayEngine can be initialized."""
    engine = CanonicalReplayEngine(temp_log_dir)
    assert engine.event_log_dir == temp_log_dir


def test_replay_engine_default_dir():
    """CanonicalReplayEngine uses default directory if none provided."""
    engine = CanonicalReplayEngine()
    assert engine.event_log_dir == Path.home() / ".dharma" / "events"


@pytest.mark.asyncio
async def test_execute_replay_returns_state(replay_engine):
    """_execute_replay returns a state dict."""
    events = [
        {"event_type": "test", "data": "foo"},
        {"event_type": "test", "data": "bar"},
    ]
    
    state = await replay_engine._execute_replay(events)
    
    assert isinstance(state, dict)
    assert "event_count" in state
    assert state["event_count"] == 2


@pytest.mark.asyncio
async def test_execute_replay_is_deterministic(replay_engine):
    """_execute_replay produces same result on repeated calls."""
    events = [
        {"event_type": "test", "data": "foo"},
        {"event_type": "test", "data": "bar"},
    ]
    
    state1 = await replay_engine._execute_replay(events)
    state2 = await replay_engine._execute_replay(events)
    
    # Should produce identical results
    assert state1 == state2


def test_hash_state_is_deterministic(replay_engine):
    """_hash_state produces same hash for same state."""
    state = {"key": "value", "number": 42}
    
    hash1 = replay_engine._hash_state(state)
    hash2 = replay_engine._hash_state(state)
    
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest


def test_hash_state_different_for_different_state(replay_engine):
    """_hash_state produces different hashes for different states."""
    state1 = {"key": "value1"}
    state2 = {"key": "value2"}
    
    hash1 = replay_engine._hash_state(state1)
    hash2 = replay_engine._hash_state(state2)
    
    assert hash1 != hash2


def test_hash_state_order_independent(replay_engine):
    """_hash_state is independent of key order (uses sorted keys)."""
    state1 = {"a": 1, "b": 2, "c": 3}
    state2 = {"c": 3, "b": 2, "a": 1}
    
    hash1 = replay_engine._hash_state(state1)
    hash2 = replay_engine._hash_state(state2)
    
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_replay_session_no_events(replay_engine):
    """replay_session handles missing session gracefully."""
    result = await replay_engine.replay_session(
        "nonexistent_session",
        verify_determinism=False,
    )
    
    assert isinstance(result, ReplayResult)
    assert result.session_id == "nonexistent_session"
    assert result.original_event_count == 0
    assert result.replayed_event_count == 0
    assert not result.passed()
    assert len(result.errors) > 0


@pytest.mark.asyncio
async def test_replay_result_passed_requires_all_conditions():
    """ReplayResult.passed() requires count match + deterministic + no errors."""
    # All good
    result = ReplayResult(
        session_id="test",
        original_event_count=5,
        replayed_event_count=5,
        final_state_hash="abc123",
        deterministic=True,
        errors=[],
    )
    assert result.passed()
    
    # Count mismatch
    result = ReplayResult(
        session_id="test",
        original_event_count=5,
        replayed_event_count=4,
        final_state_hash="abc123",
        deterministic=True,
        errors=[],
    )
    assert not result.passed()
    
    # Not deterministic
    result = ReplayResult(
        session_id="test",
        original_event_count=5,
        replayed_event_count=5,
        final_state_hash="abc123",
        deterministic=False,
        errors=[],
    )
    assert not result.passed()
    
    # Has errors
    result = ReplayResult(
        session_id="test",
        original_event_count=5,
        replayed_event_count=5,
        final_state_hash="abc123",
        deterministic=True,
        errors=["some error"],
    )
    assert not result.passed()


@pytest.mark.asyncio
async def test_canonical_replay_cli():
    """CLI test runs successfully."""
    import subprocess
    
    result = subprocess.run(
        ["python3", "-m", "dharma_swarm.canonical_replay"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
    assert "✅" in result.stdout or "PASSED" in result.stdout
