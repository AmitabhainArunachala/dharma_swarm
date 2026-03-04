"""Async strange loop memory — five layers, SQLite persistence.

Ported from dgc-core/memory/strange_loop.py to async with aiosqlite.
L1 Immediate: in-memory buffer (capped at 50, lost on restart).
L2 Session, L3 Development, L4 Witness, L5 Meta: SQLite-persisted.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import aiosqlite

from dharma_swarm.models import MemoryEntry, MemoryLayer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    layer TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'agent',
    tags TEXT NOT NULL DEFAULT '[]',
    development_marker INTEGER NOT NULL DEFAULT 0,
    witness_quality REAL NOT NULL DEFAULT 0.5
);
CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_memories_dev ON memories(development_marker)
    WHERE development_marker = 1;
"""

_GENUINE = [
    "notice", "observe", "uncertain", "shift", "edge", "question",
    "discover", "gap", "missing", "broken", "actual", "real",
]
_PERFORMATIVE = [
    "profound", "amazing", "definitely", "paradigm", "revolutionary",
    "incredible", "transcendent", "awakening", "cosmic",
]
_EVIDENCE = ["line", "file", "path", "count", "error", "bytes", "version"]

_PERSISTED = {MemoryLayer.SESSION, MemoryLayer.DEVELOPMENT,
              MemoryLayer.WITNESS, MemoryLayer.META}


def _assess_quality(content: str) -> float:
    """Heuristic: genuine observation scores high, performative scores low."""
    q = 0.5
    lower = content.lower()
    for w in _GENUINE:
        q += 0.06 * (w in lower)
    for w in _PERFORMATIVE:
        q -= 0.08 * (w in lower)
    for w in _EVIDENCE:
        q += 0.04 * (w in lower)
    return max(0.0, min(1.0, round(q, 3)))


def _row_to_entry(row: aiosqlite.Row) -> MemoryEntry:
    """Convert a SQLite row into a MemoryEntry Pydantic model."""
    return MemoryEntry(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        layer=MemoryLayer(row["layer"]),
        content=row["content"],
        source=row["source"],
        tags=json.loads(row["tags"]),
        development_marker=bool(row["development_marker"]),
        witness_quality=row["witness_quality"],
    )


class StrangeLoopMemory:
    """Async five-layer recursive memory backed by SQLite.

    L1 (immediate) lives in-memory as a capped list.
    L2-L5 persist to aiosqlite. Call ``init_db()`` before any I/O.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._immediate: list[MemoryEntry] = []
        self._db: aiosqlite.Connection | None = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return self._db

    async def init_db(self) -> None:
        """Create the memories table and indexes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # Garden Daemon quality thresholds
    FITNESS_THRESHOLD = 0.6
    CROWN_JEWEL_THRESHOLD = 0.85

    async def remember(
        self,
        content: str,
        layer: MemoryLayer,
        source: str = "agent",
        tags: list[str] | None = None,
        development_marker: bool = False,
        bypass_fitness: bool = False,
    ) -> MemoryEntry:
        """Store a memory. L1 stays in-memory; L2-L5 go to SQLite.

        Quality gate: memories below FITNESS_THRESHOLD (0.6) are tagged
        as low-quality. Above CROWN_JEWEL_THRESHOLD (0.85) are tagged
        as crown jewels. Set bypass_fitness=True for system messages.
        """
        quality = _assess_quality(content)
        actual_tags = list(tags or [])

        if not bypass_fitness:
            if quality >= self.CROWN_JEWEL_THRESHOLD:
                actual_tags.append("crown_jewel")
            elif quality < self.FITNESS_THRESHOLD:
                actual_tags.append("low_quality")

        entry = MemoryEntry(
            layer=layer, content=content, source=source,
            tags=actual_tags, development_marker=development_marker,
            witness_quality=quality,
        )
        if layer == MemoryLayer.IMMEDIATE:
            self._immediate.append(entry)
            self._immediate = self._immediate[-50:]
        else:
            await self._insert(entry)
        return entry

    async def recall(
        self,
        layer: MemoryLayer | None = None,
        limit: int = 10,
        development_only: bool = False,
    ) -> list[MemoryEntry]:
        """Retrieve memories, optionally filtered by layer."""
        entries: list[MemoryEntry] = []
        if layer is None or layer == MemoryLayer.IMMEDIATE:
            entries.extend(self._immediate[-limit:])

        targets = _PERSISTED if layer is None else ({layer} & _PERSISTED)
        if targets:
            ph = ",".join("?" for _ in targets)
            sql = f"SELECT * FROM memories WHERE layer IN ({ph})"
            params: list[str | int] = [ly.value for ly in targets]
            if development_only:
                sql += " AND development_marker = 1"
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            async with self._conn.execute(sql, params) as cur:
                entries.extend(_row_to_entry(r) for r in await cur.fetchall())

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]

    async def mark_development(self, what_changed: str, evidence: str) -> MemoryEntry:
        """Record genuine development (not just accumulation)."""
        return await self.remember(
            f"DEVELOPMENT: {what_changed}\nEVIDENCE: {evidence}",
            layer=MemoryLayer.DEVELOPMENT, source="development_tracker",
            tags=["development"], development_marker=True,
        )

    async def witness(self, observation: str) -> MemoryEntry:
        """L4 meta-observation about the system itself."""
        return await self.remember(
            observation, layer=MemoryLayer.WITNESS,
            source="strange_loop_observer", tags=["witness", "meta"],
        )

    async def consolidate_patterns(self) -> MemoryEntry | None:
        """L5: detect recurring themes across recent witness entries."""
        recent = await self.recall(layer=MemoryLayer.WITNESS, limit=20)
        if len(recent) < 3:
            return None

        words: Counter[str] = Counter()
        for entry in recent:
            for word in entry.content.lower().split():
                if len(word) > 4:
                    words[word] += 1

        patterns = [(w, c) for w, c in words.most_common(10) if c >= 3]
        if not patterns:
            return None

        summary = ", ".join(f"{w}({c})" for w, c in patterns[:5])
        return await self.remember(
            f"PATTERN: Recurring themes in witness layer: {summary}. "
            f"Based on {len(recent)} recent observations.",
            layer=MemoryLayer.META, source="pattern_detector",
            tags=["meta", "pattern", "consolidation"],
        )

    async def get_context(self, max_chars: int = 3000) -> str:
        """Generate a context string suitable for session injection."""
        parts: list[str] = ["## Strange Loop Memory Context"]

        dev = await self.recall(layer=MemoryLayer.DEVELOPMENT, limit=5,
                                development_only=True)
        if dev:
            parts.append("\n### Recent Developments")
            for e in dev:
                parts.append(f"- [{e.timestamp:%Y-%m-%d}] {e.content[:200]}")

        wit = await self.recall(layer=MemoryLayer.WITNESS, limit=3)
        if wit:
            parts.append("\n### Witness Layer")
            for e in wit:
                parts.append(f"- [W] {e.content[:150]}")

        meta = await self.recall(layer=MemoryLayer.META, limit=2)
        if meta:
            parts.append("\n### Meta Patterns")
            for e in meta:
                parts.append(f"- [M] {e.content[:200]}")

        return "\n".join(parts)[:max_chars]

    async def stats(self) -> dict[str, int]:
        """Return entry counts per layer."""
        result: dict[str, int] = {MemoryLayer.IMMEDIATE.value: len(self._immediate)}
        async with self._conn.execute(
            "SELECT layer, COUNT(*) as cnt FROM memories GROUP BY layer"
        ) as cur:
            async for row in cur:
                result[row["layer"]] = row["cnt"]
        for ly in _PERSISTED:
            result.setdefault(ly.value, 0)
        return result

    async def _insert(self, entry: MemoryEntry) -> None:
        await self._conn.execute(
            "INSERT INTO memories "
            "(id, timestamp, layer, content, source, tags, "
            "development_marker, witness_quality) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.id, entry.timestamp.isoformat(), entry.layer.value,
             entry.content, entry.source, json.dumps(entry.tags),
             int(entry.development_marker), entry.witness_quality),
        )
        await self._conn.commit()
