"""Async SQLite-backed pub/sub message bus for agent-to-agent communication.

Ported from the CHAIWALA sync MessageBus to async using aiosqlite.
All operations non-blocking. No global singletons.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.models import (
    Message,
    MessagePriority,
    MessageStatus,
    _new_id,
)

_MESSAGES_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
    subject TEXT, body TEXT NOT NULL, priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'unread', created_at TEXT NOT NULL,
    read_at TEXT, reply_to TEXT, metadata TEXT DEFAULT '{}'
)"""

_HEARTBEATS_DDL = """
CREATE TABLE IF NOT EXISTS heartbeats (
    agent_id TEXT PRIMARY KEY, last_seen TEXT NOT NULL,
    status TEXT DEFAULT 'online', metadata TEXT DEFAULT '{}'
)"""

_SUBSCRIPTIONS_DDL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    agent_id TEXT NOT NULL, topic TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY (agent_id, topic)
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_agent)",
    "CREATE INDEX IF NOT EXISTS idx_msg_status ON messages(status)",
    "CREATE INDEX IF NOT EXISTS idx_msg_priority ON messages(priority)",
    "CREATE INDEX IF NOT EXISTS idx_sub_topic ON subscriptions(topic)",
]

_RECEIVE_ORDER = """
ORDER BY
    CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
         WHEN 'normal' THEN 3 ELSE 4 END,
    created_at DESC
LIMIT ?"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_message(row: aiosqlite.Row) -> Message:
    """Convert a database row into a Message model."""
    return Message(
        id=row["id"], from_agent=row["from_agent"], to_agent=row["to_agent"],
        subject=row["subject"], body=row["body"],
        priority=MessagePriority(row["priority"]),
        status=MessageStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
        reply_to=row["reply_to"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )


class MessageBus:
    """Async SQLite message bus for inter-agent communication."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init_db(self) -> None:
        """Create messages, heartbeats, and subscriptions tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            for ddl in (_MESSAGES_DDL, _HEARTBEATS_DDL, _SUBSCRIPTIONS_DDL):
                await db.execute(ddl)
            for idx in _INDEXES:
                await db.execute(idx)
            await db.commit()

    async def send(self, message: Message) -> str:
        """Insert a message into the bus. Returns the message ID."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, from_agent, to_agent, subject, body,"
                " priority, status, created_at, reply_to, metadata)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (message.id, message.from_agent, message.to_agent,
                 message.subject, message.body, message.priority.value,
                 message.status.value, message.created_at.isoformat(),
                 message.reply_to, json.dumps(message.metadata)),
            )
            await db.commit()
        return message.id

    async def receive(
        self, agent_id: str, status: str = "unread", limit: int = 50,
    ) -> list[Message]:
        """Fetch messages for an agent, ordered by priority then time."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = ("SELECT id, from_agent, to_agent, subject, body, priority,"
                     " status, created_at, read_at, reply_to, metadata"
                     " FROM messages WHERE to_agent = ?")
            params: list[Any] = [agent_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += _RECEIVE_ORDER
            params.append(limit)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_message(r) for r in rows]

    async def mark_read(self, msg_id: str) -> None:
        """Update message status to read."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE messages SET status='read', read_at=? WHERE id=?",
                (_now_iso(), msg_id),
            )
            await db.commit()

    async def reply(self, original_id: str, from_agent: str, body: str) -> str:
        """Reply to an existing message. Returns the reply message ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT from_agent, subject FROM messages WHERE id=?",
                (original_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Message {original_id} not found")
        reply_msg = Message(
            from_agent=from_agent,
            to_agent=row["from_agent"],
            subject=f"Re: {row['subject']}" if row["subject"] else None,
            body=body,
            reply_to=original_id,
        )
        return await self.send(reply_msg)

    async def subscribe(self, agent_id: str, topic: str) -> None:
        """Add a topic subscription for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO subscriptions (agent_id, topic, created_at)"
                " VALUES (?,?,?)",
                (agent_id, topic, _now_iso()),
            )
            await db.commit()

    async def publish(self, topic: str, message: Message) -> list[str]:
        """Fan-out a message to every subscriber of a topic. Returns sent IDs."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT agent_id FROM subscriptions WHERE topic=?", (topic,),
            )
            rows = await cursor.fetchall()
        sent_ids: list[str] = []
        for (agent_id,) in rows:
            fan_msg = message.model_copy(update={
                "id": _new_id(),
                "to_agent": agent_id,
                "metadata": {**message.metadata, "topic": topic},
            })
            sent_ids.append(await self.send(fan_msg))
        return sent_ids

    async def heartbeat(
        self, agent_id: str, metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a heartbeat for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO heartbeats"
                " (agent_id, last_seen, status, metadata) VALUES (?,?,'online',?)",
                (agent_id, _now_iso(), json.dumps(metadata or {})),
            )
            await db.commit()

    async def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """Check agent liveness. Returns None if agent unknown."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT last_seen, status, metadata FROM heartbeats WHERE agent_id=?",
                (agent_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        last_seen = datetime.fromisoformat(row["last_seen"])
        age = (datetime.now(timezone.utc) - last_seen).total_seconds() / 60.0
        return {
            "agent_id": agent_id,
            "last_seen": row["last_seen"],
            "status": "online" if age < 10 else "offline",
            "age_minutes": round(age, 1),
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        }

    async def get_stats(self) -> dict[str, Any]:
        """Message counts, unread counts per agent, and known agent count."""
        async with aiosqlite.connect(self.db_path) as db:
            total = (await (await db.execute(
                "SELECT COUNT(*) FROM messages")).fetchone())[0]  # type: ignore[index]
            unread = (await (await db.execute(
                "SELECT COUNT(*) FROM messages WHERE status='unread'"
            )).fetchone())[0]  # type: ignore[index]
            unread_by_agent: dict[str, int] = dict(await (await db.execute(
                "SELECT to_agent, COUNT(*) FROM messages"
                " WHERE status='unread' GROUP BY to_agent"
            )).fetchall())
            agents = (await (await db.execute(
                "SELECT COUNT(*) FROM heartbeats")).fetchone())[0]  # type: ignore[index]
        return {
            "total_messages": total, "unread_messages": unread,
            "unread_by_agent": unread_by_agent, "known_agents": agents,
            "db_path": str(self.db_path),
        }
