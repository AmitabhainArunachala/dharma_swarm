"""Tests for ConversationStore — persistent operator conversation history."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.conversation_store import ConversationStore


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_conversations.db"


@pytest.fixture
def store(tmp_db):
    return ConversationStore(db_path=tmp_db)


@pytest.mark.asyncio
async def test_init_creates_tables(store):
    await store.init_db()
    assert store._db is not None
    await store.close()


@pytest.mark.asyncio
async def test_create_session(store):
    await store.init_db()
    sid = await store.create_session("sess1", "client1")
    assert sid == "sess1"

    sessions = await store.get_recent_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess1"
    assert sessions[0]["metadata"] == {}
    await store.close()


@pytest.mark.asyncio
async def test_create_session_auto_id(store):
    await store.init_db()
    sid = await store.create_session()
    assert len(sid) == 16  # _new_id() is 16 hex chars
    await store.close()


@pytest.mark.asyncio
async def test_add_and_get_turns(store):
    await store.init_db()
    await store.create_session("s1", "c1")

    tid1, seq1 = await store.add_turn("s1", "user", "hello")
    assert seq1 == 1
    assert len(tid1) == 16

    tid2, seq2 = await store.add_turn("s1", "assistant", "hi there")
    assert seq2 == 2

    history = await store.get_history("s1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
    assert history[0]["seq"] == 1
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hi there"
    assert history[1]["seq"] == 2
    await store.close()


@pytest.mark.asyncio
async def test_get_history_with_after_seq(store):
    await store.init_db()
    await store.create_session("s1")
    for i in range(5):
        await store.add_turn("s1", "user", f"msg {i}")

    history = await store.get_history("s1", after_seq=3)
    assert len(history) == 2
    assert history[0]["seq"] == 4
    assert history[1]["seq"] == 5
    await store.close()


@pytest.mark.asyncio
async def test_get_history_limit(store):
    await store.init_db()
    await store.create_session("s1")
    for i in range(10):
        await store.add_turn("s1", "user", f"msg {i}")

    history = await store.get_history("s1", limit=3)
    assert len(history) == 3
    await store.close()


@pytest.mark.asyncio
async def test_get_latest_seq(store):
    await store.init_db()
    await store.create_session("s1")
    assert await store.get_latest_seq("s1") == 0

    await store.add_turn("s1", "user", "a")
    assert await store.get_latest_seq("s1") == 1

    await store.add_turn("s1", "assistant", "b")
    assert await store.get_latest_seq("s1") == 2
    await store.close()


@pytest.mark.asyncio
async def test_build_messages_for_api(store):
    await store.init_db()
    await store.create_session("s1")
    await store.add_turn("s1", "user", "hello")
    await store.add_turn("s1", "assistant", "hi")
    await store.add_turn("s1", "user", "how are you")

    sys_prompt, messages = await store.build_messages_for_api("s1", "You are an AI")
    assert sys_prompt == "You are an AI"
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[2]["role"] == "user"
    await store.close()


@pytest.mark.asyncio
async def test_tool_calls_json_round_trip(store):
    await store.init_db()
    await store.create_session("s1")

    tool_calls = [{"name": "read_file", "args": {"path": "/tmp/x"}}]
    tool_results = [{"summary": "file contents..."}]

    await store.add_turn(
        "s1", "assistant", "let me check",
        tool_calls=tool_calls, tool_results=tool_results,
    )

    history = await store.get_history("s1")
    assert len(history) == 1
    assert history[0]["tool_calls"] == tool_calls
    assert history[0]["tool_results"] == tool_results
    await store.close()


@pytest.mark.asyncio
async def test_multiple_sessions(store):
    await store.init_db()
    await store.create_session("s1")
    await store.create_session("s2")
    await store.add_turn("s1", "user", "session 1")
    await store.add_turn("s2", "user", "session 2")

    h1 = await store.get_history("s1")
    h2 = await store.get_history("s2")
    assert len(h1) == 1
    assert len(h2) == 1
    assert h1[0]["content"] == "session 1"
    assert h2[0]["content"] == "session 2"

    sessions = await store.get_recent_sessions()
    assert len(sessions) == 2
    await store.close()


@pytest.mark.asyncio
async def test_duplicate_session_create_is_idempotent(store):
    await store.init_db()
    await store.create_session("s1")
    await store.create_session("s1")  # Should not raise

    sessions = await store.get_recent_sessions()
    assert len(sessions) == 1
    await store.close()


@pytest.mark.asyncio
async def test_update_session_metadata_round_trip(store):
    await store.init_db()
    await store.create_session("s1", metadata={"provider": "codex"})

    await store.update_session_metadata(
        "s1",
        {"provider_session_id": "thread-123", "model": "gpt-5.4"},
    )

    session = await store.get_session("s1")
    assert session is not None
    assert session["metadata"] == {
        "provider": "codex",
        "provider_session_id": "thread-123",
        "model": "gpt-5.4",
    }
    await store.close()


@pytest.mark.asyncio
async def test_require_db_raises_before_init(store):
    with pytest.raises(RuntimeError, match="not initialized"):
        store._require_db()


@pytest.mark.asyncio
async def test_persistence_across_connections(tmp_db):
    """Data survives close + reopen."""
    store1 = ConversationStore(db_path=tmp_db)
    await store1.init_db()
    await store1.create_session("s1")
    await store1.add_turn("s1", "user", "persistent")
    await store1.close()

    store2 = ConversationStore(db_path=tmp_db)
    await store2.init_db()
    history = await store2.get_history("s1")
    assert len(history) == 1
    assert history[0]["content"] == "persistent"
    await store2.close()
