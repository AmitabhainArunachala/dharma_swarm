"""Tests for dharma_swarm.message_bus."""

import pytest

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
