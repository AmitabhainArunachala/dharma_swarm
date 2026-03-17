"""Async SQLite-backed pub/sub message bus for agent-to-agent communication.

Ported from the CHAIWALA sync MessageBus to async using aiosqlite.
All operations non-blocking. No global singletons.

Supports typed artifact attachments linked to messages (ArtifactType from
handoff.py). Artifacts are stored in a dedicated ``artifacts`` table with
a foreign key back to ``messages(id)``.
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

_ARTIFACTS_DDL = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT DEFAULT '',
    files_touched TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id)
)"""

_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    source_pid INTEGER,
    occurred_at TEXT NOT NULL,
    consumed_at TEXT,
    payload TEXT DEFAULT '{}'
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_agent)",
    "CREATE INDEX IF NOT EXISTS idx_msg_status ON messages(status)",
    "CREATE INDEX IF NOT EXISTS idx_msg_priority ON messages(priority)",
    "CREATE INDEX IF NOT EXISTS idx_sub_topic ON subscriptions(topic)",
    "CREATE INDEX IF NOT EXISTS idx_art_msg ON artifacts(message_id)",
    "CREATE INDEX IF NOT EXISTS idx_evt_type ON events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_evt_consumed ON events(consumed_at)",
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
        """Create messages, heartbeats, subscriptions, events, and artifacts tables.

        Enables WAL mode for safe cross-process concurrent access.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA synchronous=NORMAL")
            for ddl in (
                _MESSAGES_DDL, _HEARTBEATS_DDL, _SUBSCRIPTIONS_DDL,
                _ARTIFACTS_DDL, _EVENTS_DDL,
            ):
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

    async def list_messages(
        self,
        *,
        limit: int = 200,
        agent_id: str | None = None,
    ) -> list[Message]:
        """List recent messages, optionally filtered to one agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = (
                "SELECT id, from_agent, to_agent, subject, body, priority,"
                " status, created_at, read_at, reply_to, metadata"
                " FROM messages"
            )
            params: list[Any] = []
            if agent_id:
                query += " WHERE from_agent = ? OR to_agent = ?"
                params.extend([agent_id, agent_id])
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, int(limit)))
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_message(row) for row in rows]

    # ------------------------------------------------------------------
    # Artifact attachment support
    # ------------------------------------------------------------------

    async def attach_artifact(
        self,
        message_id: str,
        artifact_type: str,
        content: str,
        summary: str = "",
        files_touched: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Attach a typed artifact to an existing message.

        Args:
            message_id: The message to attach the artifact to.
            artifact_type: A string from ArtifactType (e.g. ``"code_diff"``).
            content: The artifact payload (code, analysis text, etc.).
            summary: One-line summary for quick scanning.
            files_touched: List of file paths affected by this artifact.
            metadata: Arbitrary key-value metadata.

        Returns:
            The generated artifact ID.

        Raises:
            ValueError: If *message_id* does not reference an existing message.
        """
        artifact_id = _new_id()
        async with aiosqlite.connect(self.db_path) as db:
            # Verify the parent message exists.
            cursor = await db.execute(
                "SELECT id FROM messages WHERE id=?", (message_id,),
            )
            if await cursor.fetchone() is None:
                raise ValueError(f"Message {message_id} not found")
            await db.execute(
                "INSERT INTO artifacts"
                " (id, message_id, artifact_type, content, summary,"
                "  files_touched, metadata, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    message_id,
                    artifact_type,
                    content,
                    summary,
                    json.dumps(files_touched or []),
                    json.dumps(metadata or {}),
                    _now_iso(),
                ),
            )
            await db.commit()
        return artifact_id

    async def get_artifacts(
        self,
        message_id: str,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve artifacts attached to a message.

        Args:
            message_id: The message whose artifacts to fetch.
            artifact_type: If provided, only return artifacts of this type.

        Returns:
            List of artifact dicts with keys: ``id``, ``message_id``,
            ``artifact_type``, ``content``, ``summary``, ``files_touched``,
            ``metadata``, ``created_at``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = (
                "SELECT id, message_id, artifact_type, content, summary,"
                " files_touched, metadata, created_at"
                " FROM artifacts WHERE message_id = ?"
            )
            params: list[Any] = [message_id]
            if artifact_type is not None:
                query += " AND artifact_type = ?"
                params.append(artifact_type)
            query += " ORDER BY created_at"
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "message_id": row["message_id"],
                "artifact_type": row["artifact_type"],
                "content": row["content"],
                "summary": row["summary"],
                "files_touched": json.loads(row["files_touched"]),
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def send_with_artifacts(
        self,
        message: Message,
        artifacts: list[dict[str, Any]],
    ) -> str:
        """Send a message with attached artifacts in a single transaction.

        Each artifact dict must contain at least ``artifact_type`` and
        ``content``.  Optional keys: ``summary``, ``files_touched``,
        ``metadata``.

        Args:
            message: The message to send.
            artifacts: List of artifact dicts to attach.

        Returns:
            The message ID.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Insert the message.
            await db.execute(
                "INSERT INTO messages (id, from_agent, to_agent, subject, body,"
                " priority, status, created_at, reply_to, metadata)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    message.id,
                    message.from_agent,
                    message.to_agent,
                    message.subject,
                    message.body,
                    message.priority.value,
                    message.status.value,
                    message.created_at.isoformat(),
                    message.reply_to,
                    json.dumps(message.metadata),
                ),
            )
            # Insert each artifact in the same transaction.
            for art in artifacts:
                artifact_id = _new_id()
                await db.execute(
                    "INSERT INTO artifacts"
                    " (id, message_id, artifact_type, content, summary,"
                    "  files_touched, metadata, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        artifact_id,
                        message.id,
                        art["artifact_type"],
                        art["content"],
                        art.get("summary", ""),
                        json.dumps(art.get("files_touched", [])),
                        json.dumps(art.get("metadata", {})),
                        _now_iso(),
                    ),
                )
            await db.commit()
        return message.id

    async def build_context_from_artifacts(
        self,
        agent_id: str,
        budget: int = 5000,
    ) -> str:
        """Build injectable context from unread messages and their artifacts.

        Reads all unread messages for *agent_id*, fetches their artifacts,
        and formats them into a priority-sorted context string truncated to
        *budget* characters.

        Args:
            agent_id: The agent to build context for.
            budget: Maximum character count for the returned string.

        Returns:
            Formatted context string, or ``""`` if no unread messages with
            artifacts exist.
        """
        messages = await self.receive(agent_id, status="unread")
        if not messages:
            return ""

        # Collect (message, artifacts) pairs; skip messages with no artifacts.
        msg_art_pairs: list[tuple[Message, list[dict[str, Any]]]] = []
        for msg in messages:
            arts = await self.get_artifacts(msg.id)
            if arts:
                msg_art_pairs.append((msg, arts))

        if not msg_art_pairs:
            return ""

        sections: list[str] = ["# Artifact Context"]
        used = len(sections[0])

        for msg, arts in msg_art_pairs:
            header = (
                f"\n## [{msg.priority.value.upper()}] "
                f"From {msg.from_agent}: {msg.subject or '(no subject)'}"
            )
            body_parts: list[str] = [header]
            for art in arts:
                label = art["artifact_type"]
                summary = art.get("summary") or art["content"][:80]
                body_parts.append(f"- **{label}**: {summary}")
            section = "\n".join(body_parts)

            if used + len(section) > budget:
                remaining = budget - used
                if remaining > 40:
                    sections.append(section[:remaining] + "\n... [truncated]")
                break
            sections.append(section)
            used += len(section)

        return "\n".join(sections)

    # ── Cross-process event rail ──────────────────────────────────────

    async def emit_event(
        self,
        event_type: str,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Persist a cross-process event.  Returns the event_id."""
        import os
        event_id = _new_id()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                "INSERT INTO events (event_id, event_type, task_id, agent_id,"
                " source_pid, occurred_at, payload)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    event_id, event_type, task_id, agent_id,
                    os.getpid(), _now_iso(),
                    json.dumps(payload or {}, default=str),
                ),
            )
            await db.commit()
        return event_id

    async def consume_events(
        self,
        event_type: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read and claim unconsumed events of a given type.

        Marks consumed events with a timestamp so they aren't re-read.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cursor = await db.execute(
                "SELECT * FROM events WHERE event_type = ? AND consumed_at IS NULL"
                " ORDER BY occurred_at ASC LIMIT ?",
                (event_type, limit),
            )
            rows = await cursor.fetchall()
            events: list[dict[str, Any]] = []
            now = _now_iso()
            for row in rows:
                event = dict(row)
                if event.get("payload"):
                    try:
                        event["payload"] = json.loads(event["payload"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                events.append(event)
                await db.execute(
                    "UPDATE events SET consumed_at = ? WHERE event_id = ?",
                    (now, event["event_id"]),
                )
            await db.commit()
        return events

    async def event_stats(self) -> dict[str, Any]:
        """Return bus metrics: queued, consumed, stale heartbeats."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            queued_cur = await db.execute(
                "SELECT COUNT(*) FROM events WHERE consumed_at IS NULL"
            )
            queued = (await queued_cur.fetchone())[0]  # type: ignore[index]
            consumed_cur = await db.execute(
                "SELECT COUNT(*) FROM events WHERE consumed_at IS NOT NULL"
            )
            consumed = (await consumed_cur.fetchone())[0]  # type: ignore[index]
            total_cur = await db.execute("SELECT COUNT(*) FROM events")
            total = (await total_cur.fetchone())[0]  # type: ignore[index]

            # Stale heartbeats (no update in 5 minutes)
            stale_cur = await db.execute(
                "SELECT COUNT(*) FROM heartbeats WHERE last_seen < datetime('now', '-5 minutes')"
            )
            stale_heartbeats = (await stale_cur.fetchone())[0]  # type: ignore[index]
        return {
            "total_events": total,
            "queued": queued,
            "consumed": consumed,
            "stale_heartbeats": stale_heartbeats,
        }
