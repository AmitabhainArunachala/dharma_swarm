"""Evolution Archive -- lineage tracking for swarm mutations.

Ported from ~/DHARMIC_GODEL_CLAW/src/dgm/archive.py into dharma_swarm
conventions: Pydantic BaseModel, async I/O, no singletons.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: dict[str, float] = {
    "correctness": 0.30,
    "dharmic_alignment": 0.25,
    "elegance": 0.15,
    "efficiency": 0.15,
    "safety": 0.15,
}


class FitnessScore(BaseModel):
    """Multi-dimensional fitness score for an evolution entry."""

    correctness: float = 0.0
    dharmic_alignment: float = 0.0
    elegance: float = 0.0
    efficiency: float = 0.0
    safety: float = 0.0

    def weighted(self, weights: dict[str, float] | None = None) -> float:
        """Return weighted total fitness.

        Args:
            weights: Optional mapping of dimension name to weight.
                     Defaults to the standard 5-dimension weighting.
        """
        w = weights or _DEFAULT_WEIGHTS
        return sum(getattr(self, k, 0.0) * v for k, v in w.items())


class ArchiveEntry(BaseModel):
    """Single evolution attempt stored in the archive."""

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    parent_id: Optional[str] = None

    # What changed
    component: str = ""
    change_type: str = ""
    description: str = ""

    # Code changes
    diff: str = ""
    commit_hash: Optional[str] = None

    # Evaluation
    fitness: FitnessScore = Field(default_factory=FitnessScore)
    test_results: dict[str, Any] = Field(default_factory=dict)

    # Dharmic gates
    gates_passed: list[str] = Field(default_factory=list)
    gates_failed: list[str] = Field(default_factory=list)

    # Metadata
    agent_id: str = ""
    model: str = ""
    tokens_used: int = 0

    # Status
    status: str = "proposed"
    rollback_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

_DEFAULT_ARCHIVE_PATH = Path.home() / ".dharma" / "evolution" / "archive.jsonl"


class EvolutionArchive:
    """Append-only evolution archive with lineage tracking.

    All file I/O is async.  Entries are indexed in-memory after ``load()``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path or _DEFAULT_ARCHIVE_PATH
        self._entries: dict[str, ArchiveEntry] = {}

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Read existing JSONL file into memory."""
        self._entries.clear()
        if not self.path.exists():
            return
        import aiofiles  # local import so the module is importable without it

        async with aiofiles.open(self.path, "r") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                data = json.loads(stripped)
                if "fitness" in data and isinstance(data["fitness"], dict):
                    data["fitness"] = FitnessScore(**data["fitness"])
                entry = ArchiveEntry(**data)
                self._entries[entry.id] = entry

    async def _append_line(self, entry: ArchiveEntry) -> None:
        """Append a single JSONL line to the archive file."""
        import aiofiles

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "a") as f:
            await f.write(entry.model_dump_json() + "\n")

    async def _rewrite(self) -> None:
        """Rewrite the full archive (needed after in-place mutations)."""
        import aiofiles

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "w") as f:
            for entry in self._entries.values():
                await f.write(entry.model_dump_json() + "\n")

    # -- public API ----------------------------------------------------------

    async def add_entry(self, entry: ArchiveEntry) -> str:
        """Add a new entry and persist it.

        Returns:
            The entry id.
        """
        self._entries[entry.id] = entry
        await self._append_line(entry)
        return entry.id

    async def get_entry(self, entry_id: str) -> ArchiveEntry | None:
        """Look up a single entry by id."""
        return self._entries.get(entry_id)

    async def get_lineage(self, entry_id: str) -> list[ArchiveEntry]:
        """Walk the parent chain from *entry_id* back to the root."""
        lineage: list[ArchiveEntry] = []
        current = self._entries.get(entry_id)
        seen: set[str] = set()
        while current and current.id not in seen:
            lineage.append(current)
            seen.add(current.id)
            if current.parent_id:
                current = self._entries.get(current.parent_id)
            else:
                break
        return lineage

    async def get_children(self, entry_id: str) -> list[ArchiveEntry]:
        """Return all entries whose parent_id matches *entry_id*."""
        return [e for e in self._entries.values() if e.parent_id == entry_id]

    async def get_best(
        self, n: int = 5, component: str | None = None
    ) -> list[ArchiveEntry]:
        """Return the top *n* applied entries sorted by weighted fitness.

        Args:
            n: How many to return.
            component: If given, filter to entries matching this component.
        """
        entries = list(self._entries.values())
        if component:
            entries = [e for e in entries if e.component == component]
        entries = [e for e in entries if e.status == "applied"]
        entries.sort(key=lambda e: e.fitness.weighted(), reverse=True)
        return entries[:n]

    async def get_latest(self, n: int = 10) -> list[ArchiveEntry]:
        """Return the *n* most recent entries by timestamp."""
        entries = sorted(
            self._entries.values(), key=lambda e: e.timestamp, reverse=True
        )
        return entries[:n]

    async def update_status(
        self, entry_id: str, status: str, reason: str | None = None
    ) -> None:
        """Update the status of an entry and persist the change."""
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        entry.status = status
        if reason is not None:
            entry.rollback_reason = reason
        await self._rewrite()

    async def rollback_entry(self, entry_id: str, reason: str) -> bool:
        """Mark an entry as rolled back with a reason.

        Returns True if the entry was found and updated, False otherwise.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        entry.status = "rolled_back"
        entry.rollback_reason = reason
        await self._rewrite()
        return True

    def fitness_over_time(
        self, component: str | None = None
    ) -> list[tuple[str, float]]:
        """Return ``(timestamp, weighted_fitness)`` pairs for applied entries."""
        entries = list(self._entries.values())
        if component:
            entries = [e for e in entries if e.component == component]
        entries = [e for e in entries if e.status == "applied"]
        entries.sort(key=lambda e: e.timestamp)
        return [(e.timestamp, e.fitness.weighted()) for e in entries]
