"""Tests for dharma_swarm.message_bus."""

import sqlite3

import pytest

import dharma_swarm.message_bus as message_bus_module
from dharma_swarm.models import Message, MessagePriority
from dharma_swarm.message_bus import MessageBus


@pytest.fixture
async def bus(tmp_path):
    b = MessageBus(tmp_path / "messages.db")
    await b.init_db()
    return b


@pytest.mark.asyncio
async def test_send_and_receive(bus):
    msg = Message(from_agent="alice", to_agent="bob", body="hello")
    msg_id = await bus.send(msg)
    assert msg_id == msg.id

    received = await bus.receive("bob")
    assert len(received) == 1
    assert received[0].body == "hello"
    assert received[0].from_agent == "alice"


@pytest.mark.asyncio
async def test_mark_read(bus):
    msg = Message(from_agent="a", to_agent="b", body="test")
    await bus.send(msg)

    await bus.mark_read(msg.id)
    unread = await bus.receive("b", status="unread")
    assert len(unread) == 0

    read = await bus.receive("b", status="read")
    assert len(read) == 1


@pytest.mark.asyncio
async def test_reply(bus):
    msg = Message(from_agent="alice", to_agent="bob", body="question?", subject="Q")
    await bus.send(msg)

    reply_id = await bus.reply(msg.id, from_agent="bob", body="answer!")
    replies = await bus.receive("alice")
    assert len(replies) == 1
    assert replies[0].body == "answer!"
    assert replies[0].subject == "Re: Q"
    assert replies[0].reply_to == msg.id


@pytest.mark.asyncio
async def test_reply_not_found(bus):
    with pytest.raises(ValueError, match="not found"):
        await bus.reply("nonexistent", from_agent="x", body="y")


@pytest.mark.asyncio
async def test_priority_ordering(bus):
    await bus.send(Message(from_agent="a", to_agent="b", body="low", priority=MessagePriority.LOW))
    await bus.send(Message(from_agent="a", to_agent="b", body="urgent", priority=MessagePriority.URGENT))
    await bus.send(Message(from_agent="a", to_agent="b", body="normal", priority=MessagePriority.NORMAL))

    msgs = await bus.receive("b")
    assert msgs[0].body == "urgent"


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus):
    await bus.subscribe("agent1", "updates")
    await bus.subscribe("agent2", "updates")

    msg = Message(from_agent="system", to_agent="", body="new update")
    sent_ids = await bus.publish("updates", msg)
    assert len(sent_ids) == 2

    a1_msgs = await bus.receive("agent1")
    a2_msgs = await bus.receive("agent2")
    assert len(a1_msgs) == 1
    assert len(a2_msgs) == 1
    assert a1_msgs[0].body == "new update"


@pytest.mark.asyncio
async def test_heartbeat_and_status(bus):
    await bus.heartbeat("worker1", metadata={"role": "coder"})
    status = await bus.get_agent_status("worker1")
    assert status is not None
    assert status["status"] == "online"
    assert status["metadata"]["role"] == "coder"


@pytest.mark.asyncio
async def test_unknown_agent_status(bus):
    status = await bus.get_agent_status("nobody")
    assert status is None


@pytest.mark.asyncio
async def test_get_stats(bus):
    await bus.send(Message(from_agent="a", to_agent="b", body="m1"))
    await bus.send(Message(from_agent="a", to_agent="b", body="m2"))
    stats = await bus.get_stats()
    assert stats["total_messages"] == 2
    assert stats["unread_messages"] == 2


@pytest.mark.asyncio
async def test_list_messages_returns_recent_history(bus):
    older = Message(from_agent="a", to_agent="b", body="older")
    newer = Message(from_agent="b", to_agent="a", body="newer")
    await bus.send(older)
    await bus.send(newer)

    messages = await bus.list_messages(limit=2)
    filtered = await bus.list_messages(limit=5, agent_id="a")

    assert [message.body for message in messages] == ["newer", "older"]
    assert {message.id for message in filtered} == {older.id, newer.id}


# -- Regression: reply() TOCTOU fix — Row must be read inside connection --

@pytest.mark.asyncio
async def test_reply_toctou_regression(bus):
    """Regression: reply() was constructing the Message from a Row object
    after the connection context had closed (TOCTOU). The fix moves Message
    construction inside the connection block. Verify reply returns a valid
    ID and the reply message carries correct data from the original."""
    original = Message(
        from_agent="sender", to_agent="responder",
        body="original question", subject="Important Topic",
    )
    await bus.send(original)

    reply_id = await bus.reply(original.id, from_agent="responder", body="the answer")

    # reply_id must be a non-empty string (proves Message was built correctly)
    assert isinstance(reply_id, str)
    assert len(reply_id) > 0

    # The reply should be deliverable to the original sender
    replies = await bus.receive("sender")
    assert len(replies) == 1
    reply_msg = replies[0]
    assert reply_msg.id == reply_id
    assert reply_msg.from_agent == "responder"
    assert reply_msg.to_agent == "sender"
    assert reply_msg.body == "the answer"
    assert reply_msg.subject == "Re: Important Topic"
    assert reply_msg.reply_to == original.id


@pytest.mark.asyncio
async def test_reply_nonexistent_raises(bus):
    """Regression: reply() to a non-existent message must raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await bus.reply("totally_fake_id", from_agent="x", body="orphan reply")


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return list(self._rows)


class _FlakyEventConnection:
    def __init__(self, state):
        self._state = state
        self.row_factory = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("PRAGMA"):
            return _FakeCursor([])

        if normalized.startswith("INSERT INTO events"):
            if not self._state["lock_raised"]:
                self._state["lock_raised"] = True
                raise sqlite3.OperationalError("database is locked")
            self._state["events"].append({
                "event_id": params[0],
                "event_type": params[1],
                "task_id": params[2],
                "agent_id": params[3],
                "source_pid": params[4],
                "occurred_at": params[5],
                "consumed_at": None,
                "payload": params[6],
            })
            return _FakeCursor([])

        if normalized.startswith("SELECT * FROM events"):
            event_type, limit = params
            rows = [
                event.copy()
                for event in self._state["events"]
                if event["event_type"] == event_type and event["consumed_at"] is None
            ][:limit]
            return _FakeCursor(rows)

        if normalized.startswith("UPDATE events SET consumed_at = ? WHERE event_id = ?"):
            consumed_at, event_id = params
            for event in self._state["events"]:
                if event["event_id"] == event_id:
                    event["consumed_at"] = consumed_at
            return _FakeCursor([])

        raise AssertionError(f"Unexpected SQL in test double: {sql}")

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_emit_event_retries_transient_database_lock(tmp_path, monkeypatch):
    """Regression: transient SQLite writer contention should not drop events."""
    state = {"lock_raised": False, "events": []}

    def fake_connect(*args, **kwargs):
        return _FlakyEventConnection(state)

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr("dharma_swarm.message_bus.aiosqlite.connect", fake_connect)
    if hasattr(message_bus_module, "asyncio"):
        monkeypatch.setattr(message_bus_module.asyncio, "sleep", fast_sleep)

    bus = MessageBus(tmp_path / "messages.db")
    event_id = await bus.emit_event(
        "EVAL_PROBE",
        agent_id="eval_harness",
        payload={"probe": True},
    )

    events = await bus.consume_events("EVAL_PROBE", limit=10)

    assert state["lock_raised"] is True
    assert event_id
    assert len(events) == 1
    assert events[0]["event_id"] == event_id
    assert events[0]["payload"]["probe"] is True


@pytest.mark.asyncio
async def test_send_uses_managed_connection(monkeypatch, tmp_path):
    """send() should go through the bus connection wrapper, not raw connect()."""
    state = {"opened": 0, "configured": 0, "inserts": 0, "commits": 0}

    class _ManagedConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, sql, params=()):
            if sql.startswith("INSERT INTO messages"):
                state["inserts"] += 1
                return _FakeCursor([])
            raise AssertionError(f"Unexpected SQL in managed connection test: {sql}")

        async def commit(self):
            state["commits"] += 1

    def fake_open(self):
        state["opened"] += 1
        return _ManagedConnection()

    async def fake_configure(_db):
        state["configured"] += 1

    def fail_raw_connect(*args, **kwargs):
        raise AssertionError("raw aiosqlite.connect should not be used here")

    monkeypatch.setattr(MessageBus, "_open", fake_open)
    monkeypatch.setattr(MessageBus, "_configure_connection", staticmethod(fake_configure))
    monkeypatch.setattr(message_bus_module.aiosqlite, "connect", fail_raw_connect)

    bus = MessageBus(tmp_path / "messages.db")
    msg = Message(from_agent="alice", to_agent="bob", body="hello")

    message_id = await bus.send(msg)

    assert message_id == msg.id
    assert state == {"opened": 1, "configured": 1, "inserts": 1, "commits": 1}
