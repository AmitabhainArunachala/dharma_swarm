"""Additional quality-track tests for dharma_swarm.message_bus."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import Message, MessagePriority


@pytest.fixture
async def bus(tmp_path):
    b = MessageBus(tmp_path / "quality_messages.db")
    await b.init_db()
    return b


@pytest.mark.asyncio
async def test_init_db_creates_core_tables(bus):
    with sqlite3.connect(str(bus.db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"messages", "heartbeats", "subscriptions"}.issubset(tables)


@pytest.mark.asyncio
async def test_receive_without_status_filter_returns_read_and_unread(bus):
    msg = Message(from_agent="a", to_agent="b", body="x")
    await bus.send(msg)
    await bus.mark_read(msg.id)

    all_msgs = await bus.receive("b", status="", limit=10)
    assert len(all_msgs) == 1
    assert all_msgs[0].status.value == "read"


@pytest.mark.asyncio
async def test_receive_respects_limit(bus):
    for i in range(5):
        await bus.send(Message(from_agent="a", to_agent="b", body=f"m{i}"))

    msgs = await bus.receive("b", limit=2)
    assert len(msgs) == 2


@pytest.mark.asyncio
async def test_receive_orders_same_priority_by_created_at_desc(bus):
    old = Message(
        from_agent="a",
        to_agent="b",
        body="old",
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    new = Message(
        from_agent="a",
        to_agent="b",
        body="new",
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(timezone.utc),
    )
    await bus.send(old)
    await bus.send(new)

    msgs = await bus.receive("b", limit=10)
    assert msgs[0].body == "new"


@pytest.mark.asyncio
async def test_mark_read_unknown_message_is_noop(bus):
    await bus.mark_read("does-not-exist")
    stats = await bus.get_stats()
    assert stats["total_messages"] == 0


@pytest.mark.asyncio
async def test_subscribe_is_idempotent(bus):
    await bus.subscribe("agent-x", "topic-a")
    await bus.subscribe("agent-x", "topic-a")

    with sqlite3.connect(str(bus.db_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE agent_id='agent-x' AND topic='topic-a'"
        ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_publish_injects_topic_metadata_and_unique_ids(bus):
    await bus.subscribe("a1", "topic")
    await bus.subscribe("a2", "topic")
    source = Message(from_agent="sys", to_agent="", body="hello", metadata={"k": "v"})

    sent_ids = await bus.publish("topic", source)
    assert len(sent_ids) == 2
    assert len(set(sent_ids)) == 2

    msgs1 = await bus.receive("a1")
    msgs2 = await bus.receive("a2")
    assert msgs1[0].metadata["topic"] == "topic"
    assert msgs2[0].metadata["topic"] == "topic"
    assert msgs1[0].metadata["k"] == "v"


@pytest.mark.asyncio
async def test_reply_without_subject_sets_none_subject(bus):
    msg = Message(from_agent="alice", to_agent="bob", body="q", subject=None)
    await bus.send(msg)

    await bus.reply(msg.id, from_agent="bob", body="a")
    inbox = await bus.receive("alice")
    assert inbox[0].subject is None


@pytest.mark.asyncio
async def test_heartbeat_overwrite_updates_metadata(bus):
    await bus.heartbeat("agent-1", metadata={"role": "coder"})
    await bus.heartbeat("agent-1", metadata={"role": "reviewer"})

    status = await bus.get_agent_status("agent-1")
    assert status is not None
    assert status["metadata"]["role"] == "reviewer"


@pytest.mark.asyncio
async def test_get_agent_status_reports_offline_for_stale_heartbeat(bus):
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    with sqlite3.connect(str(bus.db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO heartbeats (agent_id, last_seen, status, metadata) VALUES (?, ?, 'online', '{}')",
            ("stale-agent", old_ts),
        )
        conn.commit()

    status = await bus.get_agent_status("stale-agent")
    assert status is not None
    assert status["status"] == "offline"
    assert status["age_minutes"] >= 11


@pytest.mark.asyncio
async def test_concurrent_send_and_stats(bus):
    async def send_one(i: int) -> None:
        await bus.send(Message(from_agent="bulk", to_agent=f"a{i%3}", body=f"b{i}"))

    await asyncio.gather(*(send_one(i) for i in range(30)))
    stats = await bus.get_stats()
    assert stats["total_messages"] == 30
    assert stats["unread_messages"] == 30
    assert set(stats["unread_by_agent"].keys()) <= {"a0", "a1", "a2"}
