"""Stigmergic lattice -- emergent intelligence through accumulated marks.

Agents leave marks on the environment (files they touch), creating
pheromone-trail-like coordination without direct communication.  Like
ant colonies: no single agent holds the whole picture, but the
accumulated observations form a shared intelligence layer.

Uses JSONL for append-friendly persistence and ``aiofiles`` for
non-blocking I/O.
"""

from __future__ import annotations

import json
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


class StigmergicMark(BaseModel):
    """A single mark left by an agent on the stigmergic lattice."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    agent: str
    file_path: str
    action: Action
    observation: str = Field(max_length=200)
    salience: float = 0.5
    connections: list[str] = Field(default_factory=list)


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
    """

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path: Path = base_path or _DEFAULT_BASE
        self._marks_file: Path = self.base_path / "marks.jsonl"
        self._archive_file: Path = self.base_path / "archive.jsonl"

    # -- write ---------------------------------------------------------------

    async def leave_mark(self, mark: StigmergicMark) -> str:
        """Append *mark* as a JSON line and return its id."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        line = mark.model_dump_json() + "\n"
        async with aiofiles.open(self._marks_file, "a") as f:
            await f.write(line)
        return mark.id

    # -- read ----------------------------------------------------------------

    async def _load_marks(self) -> list[StigmergicMark]:
        """Read all marks from the JSONL file."""
        if not self._marks_file.exists():
            return []
        marks: list[StigmergicMark] = []
        async with aiofiles.open(self._marks_file, "r") as f:
            async for line in f:
                stripped = line.strip()
                if stripped:
                    marks.append(StigmergicMark.model_validate_json(stripped))
        return marks

    async def read_marks(
        self,
        file_path: str | None = None,
        limit: int = 20,
    ) -> list[StigmergicMark]:
        """Return recent marks, optionally filtered by *file_path*.

        Results are sorted newest-first and capped at *limit*.
        """
        marks = await self._load_marks()
        if file_path is not None:
            marks = [m for m in marks if m.file_path == file_path]
        marks.sort(key=lambda m: m.timestamp, reverse=True)
        return marks[:limit]

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
        return filtered[:limit]

    async def connections_for(self, file_path: str) -> list[str]:
        """Collect unique connections from all marks referencing *file_path*."""
        marks = await self._load_marks()
        connections: set[str] = set()
        for m in marks:
            if m.file_path == file_path:
                connections.update(m.connections)
        return sorted(connections)

    # -- maintenance ---------------------------------------------------------

    async def decay(self, max_age_hours: float = 168) -> int:
        """Move marks older than *max_age_hours* to the archive file.

        Returns the count of archived marks.
        """
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

        # Rewrite marks file with only the kept marks
        async with aiofiles.open(self._marks_file, "w") as f:
            for m in keep:
                await f.write(m.model_dump_json() + "\n")

        return len(archive)

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
# Module-level convenience
# ---------------------------------------------------------------------------


async def leave_stigmergic_mark(
    agent: str,
    file_path: str,
    observation: str,
    salience: float = 0.5,
    connections: list[str] | None = None,
    action: str = "write",
) -> str:
    """Create a mark and persist it via a default store. Returns the mark id."""
    mark = StigmergicMark(
        agent=agent,
        file_path=file_path,
        action=action,  # type: ignore[arg-type]
        observation=observation,
        salience=salience,
        connections=connections or [],
    )
    store = StigmergyStore()
    return await store.leave_mark(mark)
