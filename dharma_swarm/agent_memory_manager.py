"""Self-Managing Agent Memory (Letta-inspired).

Each agent has explicit memory tools: remember(), recall(), forget().
Memory is structured in tiers:
- Working Memory (in-context, fast, limited)
- Short-term Memory (SQLite, session-scoped)
- Long-term Memory (SQLite, cross-session, persistent)
- Shared Memory (visible to all agents in the swarm)

The agent DECIDES what to remember and what to page in/out,
like an OS managing RAM vs disk.

Storage: SQLite at ~/.dharma/agent_memory/memories.db
Compatible with the existing AgentMemoryBank but adds:
- Persistent SQLite storage (no more JSON file corruption)
- Scoped memory (WORKING, SHORT_TERM, LONG_TERM, SHARED)
- TTL-based expiry for ephemeral memories
- Cross-agent shared memory with tags
- Keyword-based retrieval with recency/frequency scoring
- Token-budgeted context building
- Consolidation to prevent unbounded growth
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------


class Scope(str, Enum):
    """Memory scope determines visibility and lifetime."""
    WORKING = "working"          # In-context, fast, limited
    SHORT_TERM = "short_term"    # Session-scoped, auto-expires
    LONG_TERM = "long_term"      # Cross-session, persistent
    SHARED = "shared"            # Visible to all agents


# Alias for recall queries that search all scopes
ALL_SCOPES = (Scope.WORKING, Scope.SHORT_TERM, Scope.LONG_TERM, Scope.SHARED)


@dataclass
class Memory:
    """A single memory entry."""
    id: int = 0
    agent_id: str = ""
    key: str = ""
    content: str = ""
    scope: Scope = Scope.WORKING
    created_at: float = 0.0      # Unix timestamp
    accessed_at: float = 0.0     # Unix timestamp
    access_count: int = 0
    ttl: int | None = None       # Seconds until expiry, None = permanent
    embedding_hash: str = ""     # For future dedup / semantic search
    tags: str = ""               # Comma-separated tags (for shared memories)

    @property
    def is_expired(self) -> bool:
        """Check if this memory has expired based on TTL."""
        if self.ttl is None:
            return False
        return time.time() > (self.created_at + self.ttl)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "key": self.key,
            "content": self.content,
            "scope": self.scope.value,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "ttl": self.ttl,
            "embedding_hash": self.embedding_hash,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'working',
    created_at REAL NOT NULL,
    accessed_at REAL NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    ttl INTEGER,
    embedding_hash TEXT DEFAULT '',
    UNIQUE(agent_id, key, scope)
);

CREATE INDEX IF NOT EXISTS idx_memories_agent_scope
    ON memories(agent_id, scope);
CREATE INDEX IF NOT EXISTS idx_memories_accessed
    ON memories(accessed_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_key
    ON memories(agent_id, key);

CREATE TABLE IF NOT EXISTS shared_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    tags TEXT DEFAULT '',
    UNIQUE(key)
);

CREATE INDEX IF NOT EXISTS idx_shared_key
    ON shared_memories(key);
CREATE INDEX IF NOT EXISTS idx_shared_tags
    ON shared_memories(tags);
"""


# ---------------------------------------------------------------------------
# AgentMemoryManager
# ---------------------------------------------------------------------------


class AgentMemoryManager:
    """Self-managing memory for a single agent.

    Provides remember/recall/forget/share operations with SQLite persistence.
    Thread-safe via a per-instance lock.

    Usage:
        mgr = AgentMemoryManager("agent_alpha")
        await mgr.remember("goal", "finish R_V paper", scope=Scope.WORKING)
        results = await mgr.recall("R_V", limit=5)
        context = await mgr.get_context(budget_tokens=2000)
    """

    # Limits per scope per agent
    MAX_WORKING = 50
    MAX_SHORT_TERM = 500
    MAX_LONG_TERM = 10_000
    MAX_SHARED = 50_000  # Global, not per agent

    def __init__(
        self,
        agent_id: str,
        db_path: str | Path | None = None,
    ) -> None:
        self._agent_id = agent_id
        if db_path is None:
            db_path = Path.home() / ".dharma" / "agent_memory" / "memories.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def db_path(self) -> Path:
        return self._db_path

    # -- Database setup ----------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create the SQLite connection (one per instance)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            conn = self._get_conn()
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- Core API ----------------------------------------------------------

    async def remember(
        self,
        key: str,
        content: str,
        scope: Scope = Scope.WORKING,
        ttl: int | None = None,
        tags: str = "",
    ) -> Memory:
        """Store a memory. Upserts if key+scope already exists.

        Args:
            key: Identifier for this memory (agent-scoped).
            content: The actual memory content.
            scope: WORKING, SHORT_TERM, LONG_TERM, or SHARED.
            ttl: Time-to-live in seconds. None = permanent.
            tags: Comma-separated tags (primarily for shared memories).

        Returns:
            The stored Memory object.
        """
        if scope == Scope.SHARED:
            return await self.share(key, content, tags=tags)

        now = time.time()
        embedding_hash = _content_hash(content)

        with self._lock:
            conn = self._get_conn()

            # Enforce scope limits before insert
            self._enforce_limit(conn, scope)

            conn.execute(
                """INSERT INTO memories
                   (agent_id, key, content, scope, created_at, accessed_at,
                    access_count, ttl, embedding_hash)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(agent_id, key, scope) DO UPDATE SET
                       content = excluded.content,
                       accessed_at = excluded.accessed_at,
                       ttl = excluded.ttl,
                       embedding_hash = excluded.embedding_hash
                """,
                (self._agent_id, key, content, scope.value, now, now,
                 ttl, embedding_hash),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM memories WHERE agent_id=? AND key=? AND scope=?",
                (self._agent_id, key, scope.value),
            ).fetchone()

        return _row_to_memory(row) if row else Memory(
            agent_id=self._agent_id, key=key, content=content,
            scope=scope, created_at=now, accessed_at=now, ttl=ttl,
        )

    async def recall(
        self,
        query: str,
        scope: Scope | None = None,
        limit: int = 5,
    ) -> list[Memory]:
        """Retrieve memories by keyword match, sorted by relevance.

        Searches key and content fields. Scores by:
        - Keyword match count (primary)
        - Recency (secondary)
        - Access frequency (tertiary)

        Args:
            query: Search string (space-separated keywords).
            scope: Restrict to a specific scope, or None for all.
            limit: Maximum results to return.

        Returns:
            List of matching Memory objects, most relevant first.
        """
        keywords = _extract_keywords(query)
        if not keywords:
            return []

        scopes = [scope] if scope else list(ALL_SCOPES)
        results: list[Memory] = []

        with self._lock:
            conn = self._get_conn()
            now = time.time()

            # Search agent-scoped memories
            for s in scopes:
                if s == Scope.SHARED:
                    # Search shared memories separately
                    shared = self._search_shared_locked(conn, keywords, limit)
                    results.extend(shared)
                    continue

                rows = conn.execute(
                    "SELECT * FROM memories WHERE agent_id=? AND scope=?",
                    (self._agent_id, s.value),
                ).fetchall()

                for row in rows:
                    mem = _row_to_memory(row)
                    if mem.is_expired:
                        continue
                    score = _keyword_score(keywords, mem.key, mem.content)
                    if score > 0:
                        # Update accessed_at
                        conn.execute(
                            """UPDATE memories SET accessed_at=?, access_count=access_count+1
                               WHERE id=?""",
                            (now, mem.id),
                        )
                        mem.accessed_at = now
                        mem.access_count += 1
                        mem._score = score  # type: ignore[attr-defined]
                        results.append(mem)

            conn.commit()

        # Sort by score (desc), then recency (desc), then access count (desc)
        results.sort(
            key=lambda m: (
                getattr(m, "_score", 0),
                m.accessed_at,
                m.access_count,
            ),
            reverse=True,
        )
        return results[:limit]

    async def recall_by_key(self, key: str, scope: Scope | None = None) -> Memory | None:
        """Exact key lookup. Returns the memory or None."""
        with self._lock:
            conn = self._get_conn()
            now = time.time()

            if scope:
                row = conn.execute(
                    "SELECT * FROM memories WHERE agent_id=? AND key=? AND scope=?",
                    (self._agent_id, key, scope.value),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM memories WHERE agent_id=? AND key=? ORDER BY accessed_at DESC LIMIT 1",
                    (self._agent_id, key),
                ).fetchone()

            if row is None:
                # Check shared memories
                shared_row = conn.execute(
                    "SELECT * FROM shared_memories WHERE key=?",
                    (key,),
                ).fetchone()
                if shared_row:
                    return _shared_row_to_memory(shared_row)
                return None

            # Update access stats
            conn.execute(
                "UPDATE memories SET accessed_at=?, access_count=access_count+1 WHERE id=?",
                (now, row["id"]),
            )
            conn.commit()

        mem = _row_to_memory(row)
        mem.accessed_at = now
        mem.access_count = row["access_count"] + 1
        return mem

    async def forget(self, key: str, scope: Scope | None = None) -> bool:
        """Explicitly delete a memory.

        Args:
            key: The memory key to delete.
            scope: If provided, only delete from this scope.
                   If None, delete from all scopes.

        Returns:
            True if at least one memory was deleted.
        """
        with self._lock:
            conn = self._get_conn()

            if scope == Scope.SHARED or scope is None:
                shared_deleted = conn.execute(
                    "DELETE FROM shared_memories WHERE key=?",
                    (key,),
                ).rowcount

            if scope and scope != Scope.SHARED:
                deleted = conn.execute(
                    "DELETE FROM memories WHERE agent_id=? AND key=? AND scope=?",
                    (self._agent_id, key, scope.value),
                ).rowcount
            elif scope is None:
                deleted = conn.execute(
                    "DELETE FROM memories WHERE agent_id=? AND key=?",
                    (self._agent_id, key),
                ).rowcount
            else:
                deleted = 0

            conn.commit()

        total = deleted + (shared_deleted if scope in (Scope.SHARED, None) else 0)
        return total > 0

    async def share(
        self,
        key: str,
        content: str,
        tags: str = "",
    ) -> Memory:
        """Write to shared memory (all agents can see).

        Cross-agent pattern sharing: when Agent A solves problem X,
        it calls share("solved:X", strategy). When Agent B faces X,
        recall("solved:X", scope=SHARED) surfaces A's strategy.

        Args:
            key: Unique key for this shared memory.
            content: The content to share.
            tags: Comma-separated tags for discoverability.

        Returns:
            The stored Memory object.
        """
        now = time.time()

        with self._lock:
            conn = self._get_conn()

            # Enforce shared limit
            count = conn.execute(
                "SELECT COUNT(*) FROM shared_memories"
            ).fetchone()[0]
            if count >= self.MAX_SHARED:
                # Remove oldest
                conn.execute(
                    """DELETE FROM shared_memories WHERE id IN (
                       SELECT id FROM shared_memories ORDER BY created_at ASC LIMIT 1
                    )"""
                )

            conn.execute(
                """INSERT INTO shared_memories (agent_id, key, content, created_at, tags)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       content = excluded.content,
                       agent_id = excluded.agent_id,
                       created_at = excluded.created_at,
                       tags = excluded.tags
                """,
                (self._agent_id, key, content, now, tags),
            )
            conn.commit()

        return Memory(
            agent_id=self._agent_id,
            key=key,
            content=content,
            scope=Scope.SHARED,
            created_at=now,
            accessed_at=now,
            tags=tags,
        )

    async def get_context(self, budget_tokens: int = 2000) -> str:
        """Build working context from most relevant memories.

        Prioritizes:
        1. Working memory (always included first)
        2. Recently accessed short-term memories
        3. High-frequency long-term memories
        4. Relevant shared memories

        Stays within the token budget (estimated at ~4 chars/token).

        Args:
            budget_tokens: Maximum tokens for the context string.

        Returns:
            Formatted markdown string ready for prompt injection.
        """
        chars_budget = budget_tokens * 4  # ~4 chars per token estimate
        lines: list[str] = [f"## Memory Context ({self._agent_id})"]
        used = len(lines[0])

        with self._lock:
            conn = self._get_conn()

            # 1. Working memory (sorted by importance-proxy: access_count)
            working = conn.execute(
                """SELECT * FROM memories
                   WHERE agent_id=? AND scope='working'
                   ORDER BY access_count DESC, accessed_at DESC""",
                (self._agent_id,),
            ).fetchall()

            if working:
                lines.append("\n### Working Memory")
                used += 20
                for row in working:
                    mem = _row_to_memory(row)
                    if mem.is_expired:
                        continue
                    line = f"- **{mem.key}**: {mem.content}"
                    if used + len(line) + 1 > chars_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

            # 2. Recent short-term
            short_term = conn.execute(
                """SELECT * FROM memories
                   WHERE agent_id=? AND scope='short_term'
                   ORDER BY accessed_at DESC LIMIT 10""",
                (self._agent_id,),
            ).fetchall()

            if short_term and used < chars_budget - 100:
                lines.append("\n### Recent")
                used += 12
                for row in short_term:
                    mem = _row_to_memory(row)
                    if mem.is_expired:
                        continue
                    line = f"- {mem.key}: {mem.content[:200]}"
                    if used + len(line) + 1 > chars_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

            # 3. High-value long-term
            long_term = conn.execute(
                """SELECT * FROM memories
                   WHERE agent_id=? AND scope='long_term'
                   ORDER BY access_count DESC, accessed_at DESC LIMIT 5""",
                (self._agent_id,),
            ).fetchall()

            if long_term and used < chars_budget - 100:
                lines.append("\n### Long-term Knowledge")
                used += 25
                for row in long_term:
                    mem = _row_to_memory(row)
                    line = f"- {mem.key}: {mem.content[:200]}"
                    if used + len(line) + 1 > chars_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

            # 4. Shared memory (most recent)
            shared = conn.execute(
                """SELECT * FROM shared_memories
                   ORDER BY created_at DESC LIMIT 5"""
            ).fetchall()

            if shared and used < chars_budget - 100:
                lines.append("\n### Shared (Swarm)")
                used += 20
                for row in shared:
                    mem = _shared_row_to_memory(row)
                    tag_str = f" [{mem.tags}]" if mem.tags else ""
                    line = f"- {mem.key}: {mem.content[:150]}{tag_str}"
                    if used + len(line) + 1 > chars_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

        return "\n".join(lines)

    async def consolidate(self) -> int:
        """Memory consolidation to prevent unbounded growth.

        Operations:
        1. Expire TTL-based memories
        2. Merge duplicate keys (keep most recent)
        3. Enforce per-scope limits (evict least accessed)

        Returns:
            Count of memories affected (expired + evicted).
        """
        affected = 0
        now = time.time()

        with self._lock:
            conn = self._get_conn()

            # 1. Expire TTL-based memories
            expired = conn.execute(
                """DELETE FROM memories
                   WHERE ttl IS NOT NULL
                   AND (created_at + ttl) < ?""",
                (now,),
            ).rowcount
            affected += expired

            # 2. Enforce per-scope limits
            for scope, limit in [
                (Scope.WORKING, self.MAX_WORKING),
                (Scope.SHORT_TERM, self.MAX_SHORT_TERM),
                (Scope.LONG_TERM, self.MAX_LONG_TERM),
            ]:
                count = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE agent_id=? AND scope=?",
                    (self._agent_id, scope.value),
                ).fetchone()[0]

                if count > limit:
                    excess = count - limit
                    # Evict least accessed, oldest first
                    evicted = conn.execute(
                        """DELETE FROM memories WHERE id IN (
                           SELECT id FROM memories
                           WHERE agent_id=? AND scope=?
                           ORDER BY access_count ASC, accessed_at ASC
                           LIMIT ?
                        )""",
                        (self._agent_id, scope.value, excess),
                    ).rowcount
                    affected += evicted

            # 3. Promote frequently-accessed short-term to long-term
            # (access_count >= 3 and older than 1 hour)
            one_hour_ago = now - 3600
            promotable = conn.execute(
                """SELECT id, key, content, ttl, embedding_hash
                   FROM memories
                   WHERE agent_id=? AND scope='short_term'
                   AND access_count >= 3 AND created_at < ?""",
                (self._agent_id, one_hour_ago),
            ).fetchall()

            for row in promotable:
                # Check if already exists in long_term
                existing = conn.execute(
                    "SELECT id FROM memories WHERE agent_id=? AND key=? AND scope='long_term'",
                    (self._agent_id, row["key"]),
                ).fetchone()
                if existing:
                    # Update existing long-term memory
                    conn.execute(
                        "UPDATE memories SET content=?, accessed_at=? WHERE id=?",
                        (row["content"], now, existing["id"]),
                    )
                else:
                    conn.execute(
                        """INSERT INTO memories
                           (agent_id, key, content, scope, created_at, accessed_at,
                            access_count, ttl, embedding_hash)
                           VALUES (?, ?, ?, 'long_term', ?, ?, 0, NULL, ?)""",
                        (self._agent_id, row["key"], row["content"],
                         now, now, row["embedding_hash"]),
                    )
                # Remove from short-term
                conn.execute("DELETE FROM memories WHERE id=?", (row["id"],))
                affected += 1

            conn.commit()

        if affected > 0:
            logger.debug(
                "Consolidated %d memories for agent %s",
                affected, self._agent_id,
            )
        return affected

    async def get_stats(self) -> dict[str, Any]:
        """Return memory statistics for observability."""
        with self._lock:
            conn = self._get_conn()

            stats: dict[str, Any] = {"agent_id": self._agent_id}

            for scope in (Scope.WORKING, Scope.SHORT_TERM, Scope.LONG_TERM):
                count = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE agent_id=? AND scope=?",
                    (self._agent_id, scope.value),
                ).fetchone()[0]
                stats[f"{scope.value}_count"] = count

            stats["shared_count"] = conn.execute(
                "SELECT COUNT(*) FROM shared_memories"
            ).fetchone()[0]

            stats["total_count"] = sum(
                stats.get(f"{s.value}_count", 0)
                for s in (Scope.WORKING, Scope.SHORT_TERM, Scope.LONG_TERM)
            ) + stats["shared_count"]

            # Most recent memory
            latest = conn.execute(
                """SELECT accessed_at FROM memories
                   WHERE agent_id=? ORDER BY accessed_at DESC LIMIT 1""",
                (self._agent_id,),
            ).fetchone()
            if latest:
                stats["latest_access"] = datetime.fromtimestamp(
                    latest["accessed_at"], tz=timezone.utc
                ).isoformat()

        return stats

    async def list_keys(self, scope: Scope | None = None) -> list[str]:
        """List all memory keys, optionally filtered by scope."""
        with self._lock:
            conn = self._get_conn()
            if scope == Scope.SHARED:
                rows = conn.execute(
                    "SELECT key FROM shared_memories ORDER BY key"
                ).fetchall()
            elif scope:
                rows = conn.execute(
                    "SELECT key FROM memories WHERE agent_id=? AND scope=? ORDER BY key",
                    (self._agent_id, scope.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key FROM memories WHERE agent_id=? ORDER BY key",
                    (self._agent_id,),
                ).fetchall()
        return [r["key"] for r in rows]

    # -- Internal helpers --------------------------------------------------

    def _enforce_limit(self, conn: sqlite3.Connection, scope: Scope) -> None:
        """Enforce per-scope memory limits. Evicts oldest/least-accessed."""
        limit_map = {
            Scope.WORKING: self.MAX_WORKING,
            Scope.SHORT_TERM: self.MAX_SHORT_TERM,
            Scope.LONG_TERM: self.MAX_LONG_TERM,
        }
        limit = limit_map.get(scope)
        if limit is None:
            return

        count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE agent_id=? AND scope=?",
            (self._agent_id, scope.value),
        ).fetchone()[0]

        if count >= limit:
            # Evict 10% of the limit to avoid evicting on every insert
            evict_count = max(1, limit // 10)
            conn.execute(
                """DELETE FROM memories WHERE id IN (
                   SELECT id FROM memories
                   WHERE agent_id=? AND scope=?
                   ORDER BY access_count ASC, accessed_at ASC
                   LIMIT ?
                )""",
                (self._agent_id, scope.value, evict_count),
            )

    def _search_shared_locked(
        self,
        conn: sqlite3.Connection,
        keywords: list[str],
        limit: int,
    ) -> list[Memory]:
        """Search shared memories. Must be called with self._lock held."""
        rows = conn.execute(
            "SELECT * FROM shared_memories ORDER BY created_at DESC"
        ).fetchall()

        results: list[Memory] = []
        for row in rows:
            mem = _shared_row_to_memory(row)
            score = _keyword_score(keywords, mem.key, mem.content)
            if mem.tags:
                # Boost score if keywords match tags
                tag_score = _keyword_score(keywords, mem.tags, "")
                score += tag_score * 0.5
            if score > 0:
                mem._score = score  # type: ignore[attr-defined]
                results.append(mem)

        results.sort(key=lambda m: getattr(m, "_score", 0), reverse=True)
        return results[:limit]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _content_hash(content: str) -> str:
    """SHA-256 hash of content for dedup and future embedding keying."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a query string."""
    # Split on whitespace and punctuation, lowercase, filter short words
    words = re.findall(r"[a-zA-Z0-9_]+", query.lower())
    # Filter out very short words (< 2 chars) and common stop words
    stop_words = {"a", "an", "the", "is", "it", "in", "on", "at", "to", "of", "and", "or"}
    return [w for w in words if len(w) >= 2 and w not in stop_words]


def _keyword_score(keywords: list[str], key: str, content: str) -> int:
    """Score a memory by keyword match count."""
    text = f"{key} {content}".lower()
    return sum(1 for kw in keywords if kw in text)


def _row_to_memory(row: sqlite3.Row) -> Memory:
    """Convert a SQLite Row from the memories table to a Memory object."""
    return Memory(
        id=row["id"],
        agent_id=row["agent_id"],
        key=row["key"],
        content=row["content"],
        scope=Scope(row["scope"]),
        created_at=row["created_at"],
        accessed_at=row["accessed_at"],
        access_count=row["access_count"],
        ttl=row["ttl"],
        embedding_hash=row["embedding_hash"] or "",
    )


def _shared_row_to_memory(row: sqlite3.Row) -> Memory:
    """Convert a SQLite Row from shared_memories table to a Memory object."""
    return Memory(
        id=row["id"],
        agent_id=row["agent_id"],
        key=row["key"],
        content=row["content"],
        scope=Scope.SHARED,
        created_at=row["created_at"],
        accessed_at=row["created_at"],
        tags=row["tags"] or "",
    )


__all__ = [
    "AgentMemoryManager",
    "Memory",
    "Scope",
    "ALL_SCOPES",
]
