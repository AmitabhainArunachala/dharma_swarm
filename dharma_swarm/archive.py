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
    "correctness": 0.20,         # -5% (still most important)
    "dharmic_alignment": 0.15,   # -5%
    "performance": 0.12,         # -3% - wall clock speedup (JIKOKU)
    "utilization": 0.12,         # -3% - concurrent execution (JIKOKU)
    "economic_value": 0.15,      # NEW - real $$ ROI measurement
    "elegance": 0.10,            # -5% (was 15%)
    "efficiency": 0.10,          # unchanged
    "safety": 0.06,              # +1% (slightly more weight)
}


class FitnessScore(BaseModel):
    """Multi-dimensional fitness score for an evolution entry.

    Now includes JIKOKU performance metrics + economic ROI measurement.
    This enables the system to optimize for both technical excellence AND business value.
    """

    correctness: float = 0.0       # Test pass rate (0-1)
    dharmic_alignment: float = 0.0 # Gate outcomes (0-1)
    performance: float = 0.0       # Wall clock speedup (0-1) - JIKOKU
    utilization: float = 0.0       # Concurrent execution (0-1) - JIKOKU
    economic_value: float = 0.5    # ROI-based fitness (0-1) - NEW - Economic fitness
    elegance: float = 0.0          # Code quality (0-1)
    efficiency: float = 0.0        # Diff size penalty (0-1)
    safety: float = 0.0            # Gate pass/fail (0-1)

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
    spec_ref: Optional[str] = None
    requirement_refs: list[str] = Field(default_factory=list)

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

    # MAP-Elites feature coordinates
    feature_coords: dict[str, float] = Field(default_factory=dict)


class MAPElitesGrid:
    """MAP-Elites diversity archive binning entries by feature dimensions.

    Maintains one entry per bin (the fittest). Prevents evolutionary
    convergence by preserving diverse solutions across feature space.

    Feature dimensions for dharma_swarm:
        - dharmic_alignment: [0.0, 1.0] binned into N_BINS intervals
        - elegance: [0.0, 1.0] binned into N_BINS intervals
        - complexity: diff_size mapped to [0.0, 1.0] via min(diff_lines/500, 1.0)
    """

    N_BINS: int = 5  # 5x5x5 = 125 cells max

    def __init__(self) -> None:
        # grid[(d_bin, e_bin, c_bin)] = ArchiveEntry (best per cell)
        self._grid: dict[tuple[int, int, int], ArchiveEntry] = {}

    @staticmethod
    def _bin_value(value: float, n_bins: int = 5) -> int:
        """Map a [0, 1] value to a bin index."""
        return min(int(value * n_bins), n_bins - 1)

    @staticmethod
    def compute_feature_coords(entry: ArchiveEntry) -> dict[str, float]:
        """Compute feature coordinates from an entry's fitness and diff.

        Returns:
            Dict with keys 'dharmic_alignment', 'elegance', 'complexity'.
        """
        diff_lines = len(entry.diff.splitlines()) if entry.diff else 0
        return {
            "dharmic_alignment": entry.fitness.dharmic_alignment,
            "elegance": entry.fitness.elegance,
            "complexity": min(diff_lines / 500.0, 1.0),
        }

    def _coords_to_bin(self, coords: dict[str, float]) -> tuple[int, int, int]:
        """Convert feature coordinates to grid bin indices."""
        return (
            self._bin_value(coords.get("dharmic_alignment", 0.0)),
            self._bin_value(coords.get("elegance", 0.0)),
            self._bin_value(coords.get("complexity", 0.0)),
        )

    def try_insert(self, entry: ArchiveEntry) -> bool:
        """Insert entry if its bin is empty or it beats the current occupant.

        Also populates entry.feature_coords if not already set.

        Returns:
            True if entry was inserted (new bin or higher fitness), False otherwise.
        """
        if not entry.feature_coords:
            entry.feature_coords = self.compute_feature_coords(entry)
        bin_key = self._coords_to_bin(entry.feature_coords)
        existing = self._grid.get(bin_key)
        if existing is None or entry.fitness.weighted() > existing.fitness.weighted():
            self._grid[bin_key] = entry
            return True
        return False

    def get_diverse_parents(self, n: int = 5) -> list[ArchiveEntry]:
        """Return up to n entries from distinct bins, sorted by fitness.

        This provides diverse parents for the next evolution cycle.
        """
        entries = sorted(
            self._grid.values(),
            key=lambda e: e.fitness.weighted(),
            reverse=True,
        )
        return entries[:n]

    @property
    def occupied_bins(self) -> int:
        """Number of occupied bins in the grid."""
        return len(self._grid)

    @property
    def total_bins(self) -> int:
        """Total possible bins (N_BINS^3)."""
        return self.N_BINS ** 3

    def coverage(self) -> float:
        """Fraction of bins occupied."""
        return self.occupied_bins / self.total_bins if self.total_bins > 0 else 0.0


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
        self.grid = MAPElitesGrid()

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
                try:
                    data = json.loads(stripped)
                    if "fitness" in data and isinstance(data["fitness"], dict):
                        data["fitness"] = FitnessScore(**data["fitness"])
                    entry = ArchiveEntry(**data)
                    self._entries[entry.id] = entry
                    self.grid.try_insert(entry)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

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
        self.grid.try_insert(entry)
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

    async def get_diverse(self, n: int = 5) -> list[ArchiveEntry]:
        """Return diverse parents from the MAP-Elites grid.

        Args:
            n: Maximum number of diverse entries to return.

        Returns:
            List of entries from distinct feature bins, sorted by fitness.
        """
        return self.grid.get_diverse_parents(n=n)

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
