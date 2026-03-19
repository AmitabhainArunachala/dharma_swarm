"""Persistent conversation store for the Resident Operator.

SQLite-backed storage for multi-session conversations that survives restarts.
Each session holds an ordered sequence of turns (user/assistant/tool).
Clients reconnect and catch up via seq-based replay.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.models import _new_id

_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS operator_sessions (
    session_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_TURNS_DDL = """
CREATE TABLE IF NOT EXISTS operator_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT NOT NULL DEFAULT '[]',
    tool_results_json TEXT NOT NULL DEFAULT '[]',
    timestamp REAL NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    quality_score REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY (session_id) REFERENCES operator_sessions(session_id)
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_turns_session ON operator_turns(session_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_updated ON operator_sessions(updated_at)",
]


class ConversationStore:
    """SQLite-backed conversation persistence for the operator."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path.home() / ".dharma" / "db" / "conversations.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute(_SESSIONS_DDL)
        await self._db.execute(_TURNS_DDL)
        for idx in _INDEXES:
            await self._db.execute(idx)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("ConversationStore not initialized — call init_db() first")
        return self._db

    async def create_session(
        self,
        session_id: str | None = None,
        client_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        db = self._require_db()
        sid = session_id or _new_id()
        now = time.time()
        await db.execute(
            "INSERT OR IGNORE INTO operator_sessions "
            "(session_id, client_id, created_at, updated_at, metadata_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, client_id, now, now, json.dumps(metadata or {})),
        )
        await db.commit()
        return sid

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        token_count: int = 0,
        cost_usd: float = 0.0,
        quality_score: float = 0.0,
    ) -> tuple[str, int]:
        """Add a turn. Returns (turn_id, seq)."""
        db = self._require_db()
        now = time.time()

        # Get next seq for this session
        async with db.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM operator_turns WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            seq = (row[0] if row else 0) + 1

        turn_id = _new_id()
        await db.execute(
            "INSERT INTO operator_turns "
            "(turn_id, session_id, seq, role, content, tool_calls_json, "
            "tool_results_json, timestamp, token_count, cost_usd, quality_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                turn_id, session_id, seq, role, content,
                json.dumps(tool_calls or []),
                json.dumps(tool_results or []),
                now, token_count, cost_usd, quality_score,
            ),
        )
        await db.execute(
            "UPDATE operator_sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        await db.commit()
        return turn_id, seq

    async def get_history(
        self, session_id: str, limit: int = 100, after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM operator_turns WHERE session_id = ? AND seq > ? "
            "ORDER BY seq ASC LIMIT ?",
            (session_id, after_seq, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def get_recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM operator_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._session_row_to_dict(r) for r in rows]

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM operator_sessions WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return self._session_row_to_dict(row)

    async def update_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
        *,
        merge: bool = True,
    ) -> None:
        db = self._require_db()
        now = time.time()
        existing: dict[str, Any] = {}
        if merge:
            session = await self.get_session(session_id)
            if session:
                existing = dict(session.get("metadata", {}) or {})
        updated = {**existing, **metadata} if merge else dict(metadata)
        await db.execute(
            "UPDATE operator_sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(updated), now, session_id),
        )
        await db.commit()

    async def build_messages_for_api(
        self,
        session_id: str,
        system_prompt: str = "",
        max_tokens: int = 100_000,
    ) -> tuple[str, list[dict[str, str]]]:
        """Build messages list suitable for LLM API calls.

        Returns (system_prompt, messages) where messages is a list of
        {"role": ..., "content": ...} dicts, trimmed to fit within max_tokens.
        """
        history = await self.get_history(session_id, limit=200)

        messages: list[dict[str, str]] = []
        token_budget = max_tokens
        for turn in reversed(history):
            content = turn.get("content", "")
            # Rough token estimate: 4 chars per token
            est_tokens = len(content) // 4
            if token_budget - est_tokens < 0 and messages:
                break
            token_budget -= est_tokens
            messages.append({"role": turn["role"], "content": content})

        messages.reverse()
        return system_prompt, messages

    async def get_latest_seq(self, session_id: str) -> int:
        db = self._require_db()
        async with db.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM operator_turns WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("tool_calls_json", "tool_results_json"):
            if key in d:
                try:
                    d[key.replace("_json", "")] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key.replace("_json", "")] = []
                del d[key]
        return d

    @staticmethod
    def _session_row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        d = dict(row)
        raw = d.pop("metadata_json", "{}")
        try:
            d["metadata"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
        return d


__all__ = ["ConversationStore"]
