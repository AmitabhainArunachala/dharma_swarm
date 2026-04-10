"""Stigmergic lattice -- emergent intelligence through accumulated marks.

Agents leave marks on the environment (files they touch), creating
pheromone-trail-like coordination without direct communication.  Like
ant colonies: no single agent holds the whole picture, but the
accumulated observations form a shared intelligence layer.

Uses JSONL for append-friendly persistence and ``aiofiles`` for
non-blocking I/O.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import aiofiles
from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

Action = Literal["read", "write", "scan", "connect", "dream"]

# Stigmergy channels — scoped visibility per domain.
# Marks are visible only within their channel unless salience exceeds
# the cross-channel threshold (default 0.8).
STIGMERGY_CHANNELS: list[str] = [
    "general",      # Default catch-all
    "research",     # R_V, MI, experiments
    "systems",      # Code, infra, debugging
    "strategy",     # Business, grants, partnerships
    "governance",   # Telos alignment, audit findings
    "memory",       # Consolidation, retrieval, knowledge graph
]

# Marks above this salience are visible across all channels
CROSS_CHANNEL_SALIENCE_THRESHOLD: float = 0.8


class StigmergicMark(BaseModel):
    """A single mark left by an agent on the stigmergic lattice."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    agent: str
    file_path: str
    action: str = ""  # Was required Action; defaulted for back-compat with old marks
    observation: str = Field(max_length=200)
    salience: float = 0.5
    connections: list[str] = Field(default_factory=list)
    access_count: int = 0
    channel: str = "general"  # Stigmergy channel for scoped visibility


# ---------------------------------------------------------------------------
# Channel derivation
# ---------------------------------------------------------------------------

_AGENT_CHANNEL_PREFIXES: dict[str, str] = {
    "dashboard:": "dashboard",
    "cascade": "cascade",
    "test-": "test",
    "mem-": "test",
    "bad-": "test",
    "ok-": "test",
    "ginko": "strategy",
}


def _derive_channel(agent: str) -> str:
    """Derive a stigmergy channel from the agent name.

    Returns ``"general"`` when no prefix matches.
    """
    lower = agent.lower()
    for prefix, channel in _AGENT_CHANNEL_PREFIXES.items():
        if lower.startswith(prefix):
            return channel
    return "general"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

_DEFAULT_BASE = Path.home() / ".dharma" / "stigmergy"


class StigmergyStore:
    """File-backed stigmergic mark store.

    Marks are appended to a JSONL file for fast writes.  Decay moves
    old marks to an archive file, keeping the hot file lean.

    All public methods (except ``density``) are async, backed by
    ``aiofiles`` so the event loop never blocks.

    Thread-safety: an ``asyncio.Lock`` serializes all mutations
    (``leave_mark``, ``decay``, ``access_decay``) so concurrent
    coroutines cannot interleave reads and writes — preventing
    silent mark loss during decay rewrites.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path: Path = base_path or _DEFAULT_BASE
        self._marks_file: Path = self.base_path / "marks.jsonl"
        self._archive_file: Path = self.base_path / "archive.jsonl"
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # -- write ---------------------------------------------------------------

    async def leave_mark(self, mark: StigmergicMark) -> str:
        """Append *mark* as a JSON line and return its id.

        Derives a channel from the agent name when the mark uses the
        default channel (``general``), giving dashboard, cascade, and
        test agents proper channel separation.

        Applies salience boosting so the living layers (Shakti, subconscious)
        have meaningful signal to perceive:
        - Governance/witness channel marks: +0.1
        - Marks with connections: +0.05 per connection (cap +0.2)
        """
        updates: dict[str, object] = {}

        # Channel derivation
        if mark.channel == "general" and mark.agent:
            derived = _derive_channel(mark.agent)
            if derived != "general":
                updates["channel"] = derived

        # Salience boosting — feed the living layers
        boosted = mark.salience
        effective_channel = updates.get("channel", mark.channel)
        if effective_channel in ("governance", "witness"):
            boosted += 0.1
        if mark.connections:
            boosted += min(len(mark.connections) * 0.05, 0.2)
        if boosted != mark.salience:
            updates["salience"] = min(boosted, 1.0)

        if updates:
            mark = mark.model_copy(update=updates)

        self.base_path.mkdir(parents=True, exist_ok=True)
        line = mark.model_dump_json() + "\n"
        async with self._write_lock:
            async with aiofiles.open(self._marks_file, "a") as f:
                await f.write(line)
        return mark.id

    # -- read ----------------------------------------------------------------

    async def _load_marks(self) -> list[StigmergicMark]:
        """Read all marks from the JSONL file.

        Tolerant: bad marks are counted and skipped, never crash the caller.
        """
        if not self._marks_file.exists():
            return []
        marks: list[StigmergicMark] = []
        self._corrupt_count = 0
        async with aiofiles.open(self._marks_file, "r") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    marks.append(StigmergicMark.model_validate_json(stripped))
                except Exception:
                    self._corrupt_count += 1
        if self._corrupt_count:
            import logging
            logging.getLogger(__name__).warning(
                "Stigmergy: skipped %d corrupt marks out of %d total lines",
                self._corrupt_count,
                len(marks) + self._corrupt_count,
            )
        return marks

    async def read_marks(
        self,
        file_path: str | None = None,
        limit: int = 20,
        channel: str | None = None,
    ) -> list[StigmergicMark]:
        """Return recent marks, optionally filtered by *file_path* and/or *channel*.

        When *channel* is specified, only marks in that channel are returned,
        plus any marks whose salience exceeds CROSS_CHANNEL_SALIENCE_THRESHOLD
        (cross-channel bleed for high-salience signals).

        Results are sorted newest-first and capped at *limit*.
        """
        marks = await self._load_marks()
        if file_path is not None:
            marks = [m for m in marks if m.file_path == file_path]
        if channel is not None:
            marks = [
                m for m in marks
                if m.channel == channel
                or m.salience >= CROSS_CHANNEL_SALIENCE_THRESHOLD
            ]
        marks.sort(key=lambda m: m.timestamp, reverse=True)
        result = marks[:limit]
        await self._record_access(result)
        return result

    async def hot_paths(
        self,
        window_hours: float = 24,
        min_marks: int = 3,
    ) -> list[tuple[str, int]]:
        """Return file paths with heavy recent activity.

        Only marks within the last *window_hours* are counted.  Paths
        with fewer than *min_marks* marks are excluded.  Sorted by count
        descending.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        marks = await self._load_marks()
        counts: dict[str, int] = {}
        for m in marks:
            if m.timestamp >= cutoff:
                counts[m.file_path] = counts.get(m.file_path, 0) + 1
        result = [(path, count) for path, count in counts.items() if count >= min_marks]
        result.sort(key=lambda t: t[1], reverse=True)
        return result

    async def high_salience(
        self,
        threshold: float = 0.7,
        limit: int = 10,
    ) -> list[StigmergicMark]:
        """Return marks with salience >= *threshold*, sorted descending."""
        marks = await self._load_marks()
        filtered = [m for m in marks if m.salience >= threshold]
        filtered.sort(key=lambda m: m.salience, reverse=True)
        result = filtered[:limit]
        await self._record_access(result)
        return result

    async def connections_for(self, file_path: str) -> list[str]:
        """Collect unique connections from all marks referencing *file_path*."""
        marks = await self._load_marks()
        connections: set[str] = set()
        for m in marks:
            if m.file_path == file_path:
                connections.update(m.connections)
        return sorted(connections)

    async def query_relevant(
        self,
        task_keywords: list[str] | str,
        limit: int = 10,
        channel: str | None = None,
    ) -> list[StigmergicMark]:
        """Filter marks by keyword overlap, sorted by salience (PULL protocol).

        When *channel* is specified, results are scoped to that channel
        (plus cross-channel high-salience marks).
        """
        if isinstance(task_keywords, str):
            task_keywords = [task_keywords]
        if not task_keywords:
            return await self.high_salience(limit=limit)
        marks = await self._load_marks()
        if channel is not None:
            marks = [
                m for m in marks
                if m.channel == channel
                or m.salience >= CROSS_CHANNEL_SALIENCE_THRESHOLD
            ]
        keywords_lower = [kw.lower() for kw in task_keywords if kw.strip()]
        if not keywords_lower:
            return await self.high_salience(limit=limit)
        relevant = [m for m in marks if any(kw in (m.observation + " " + m.file_path).lower() for kw in keywords_lower)]
        relevant.sort(key=lambda m: (m.salience, m.timestamp), reverse=True)
        result = relevant[:limit]
        await self._record_access(result)
        return result

    async def _record_access(self, marks: list[StigmergicMark]) -> None:
        """Persist access-count increments for read marks."""
        if not marks:
            return

        mark_ids = {mark.id for mark in marks if getattr(mark, "id", "")}
        if not mark_ids:
            return

        async with self._write_lock:
            persisted = await self._load_marks()
            touched = False
            for mark in persisted:
                if mark.id in mark_ids:
                    mark.access_count += 1
                    touched = True
            if not touched:
                return

            self.base_path.mkdir(parents=True, exist_ok=True)
            tmp = self._marks_file.with_suffix(".tmp")
            async with aiofiles.open(tmp, "w") as f:
                for mark in persisted:
                    await f.write(mark.model_dump_json() + "\n")
            tmp.replace(self._marks_file)

        for mark in marks:
            mark.access_count += 1

    # -- maintenance ---------------------------------------------------------

    async def decay(self, max_age_hours: float = 168) -> int:
        """Move marks older than *max_age_hours* to the archive file.

        Returns the count of archived marks.

        The write lock prevents concurrent ``leave_mark`` calls from
        appending between the read and the rewrite — which would
        silently lose the new mark.
        """
        async with self._write_lock:
            marks = await self._load_marks()
            if not marks:
                return 0

            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            keep: list[StigmergicMark] = []
            archive: list[StigmergicMark] = []

            for m in marks:
                if m.timestamp < cutoff:
                    archive.append(m)
                else:
                    keep.append(m)

            if not archive:
                return 0

            # Append old marks to archive file
            self.base_path.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._archive_file, "a") as f:
                for m in archive:
                    await f.write(m.model_dump_json() + "\n")

            # Atomic rewrite: temp file → rename
            tmp = self._marks_file.with_suffix(".tmp")
            async with aiofiles.open(tmp, "w") as f:
                for m in keep:
                    await f.write(m.model_dump_json() + "\n")
            tmp.replace(self._marks_file)

            return len(archive)

    async def access_decay(self, decay_factor: float = 0.95) -> int:
        """Decay marks based on access count -- unused marks fade faster."""
        async with self._write_lock:
            marks = await self._load_marks()
            if not marks:
                return 0
            dead_count = 0
            for m in marks:
                exponent = max(1, 3 - m.access_count)
                m.salience *= decay_factor ** exponent
                if m.salience < 0.1:
                    dead_count += 1
            self.base_path.mkdir(parents=True, exist_ok=True)
            # Atomic rewrite: temp file → rename
            tmp = self._marks_file.with_suffix(".tmp")
            async with aiofiles.open(tmp, "w") as f:
                for m in marks:
                    await f.write(m.model_dump_json() + "\n")
            tmp.replace(self._marks_file)
            return dead_count

    # -- sync helpers --------------------------------------------------------

    def density(self) -> int:
        """Synchronous count of marks in the hot file (for quick checks)."""
        if not self._marks_file.exists():
            return 0
        count = 0
        with open(self._marks_file, "r") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


# ---------------------------------------------------------------------------
# Module-level convenience (singleton store for lock sharing)
# ---------------------------------------------------------------------------

_default_store: StigmergyStore | None = None


def _get_default_store() -> StigmergyStore:
    """Return the module-level singleton store so all callers share one lock."""
    global _default_store
    if _default_store is None:
        _default_store = StigmergyStore()
    return _default_store


async def leave_stigmergic_mark(
    agent: str,
    file_path: str,
    observation: str,
    salience: float = 0.5,
    connections: list[str] | None = None,
    action: Action = "write",
    channel: str = "general",
) -> str:
    """Create a mark and persist it via the default store. Returns the mark id."""
    mark = StigmergicMark(
        agent=agent,
        file_path=file_path,
        action=action,
        observation=observation,
        salience=salience,
        connections=connections or [],
        channel=channel,
    )
    return await _get_default_store().leave_mark(mark)
