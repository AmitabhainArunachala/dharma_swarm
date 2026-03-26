"""Evolution Archive -- lineage tracking for swarm mutations.

Ported from ~/DHARMIC_GODEL_CLAW/src/dgm/archive.py into dharma_swarm
conventions: Pydantic BaseModel, async I/O, no singletons.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.execution_profile import EvidenceTier, PromotionState
from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.merkle_log import MerkleLog


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

FITNESS_DIMENSIONS: tuple[str, ...] = tuple(_DEFAULT_WEIGHTS)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalize_fitness_weights(
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Return a normalized full fitness-weight mapping.

    Partial overrides are merged onto the canonical defaults, then normalized so
    the total weight mass remains 1.0.
    """
    if weights is None:
        return dict(_DEFAULT_WEIGHTS)

    unknown = sorted(set(weights) - set(_DEFAULT_WEIGHTS))
    if unknown:
        raise ValueError(f"Unknown fitness dimensions: {', '.join(unknown)}")

    merged: dict[str, float] = dict(_DEFAULT_WEIGHTS)
    for key, value in weights.items():
        scalar = float(value)
        if scalar < 0.0:
            raise ValueError(f"Fitness weight for {key!r} must be non-negative")
        merged[key] = scalar

    total = sum(merged.values())
    if total <= 0.0:
        raise ValueError("At least one fitness weight must be positive")

    return {key: value / total for key, value in merged.items()}


def research_reward_to_fitness(reward_signal: Any) -> "FitnessScore":
    """Project a research reward signal into archive-compatible fitness."""
    if hasattr(reward_signal, "model_dump"):
        payload = reward_signal.model_dump()
    elif isinstance(reward_signal, dict):
        payload = dict(reward_signal)
    else:
        raise TypeError("reward_signal must be a RewardSignal or dict-like payload")

    grade_card = dict(payload.get("grade_card") or {})
    metadata = dict(grade_card.get("metadata") or {})
    gate_failures = list(grade_card.get("gate_failures") or [])
    final_score = _clamp01(float(grade_card.get("final_score", 0.0) or 0.0))
    groundedness = _clamp01(float(grade_card.get("groundedness", 0.0) or 0.0))
    contradiction_handling = _clamp01(
        float(grade_card.get("contradiction_handling", 0.0) or 0.0)
    )
    structure = _clamp01(float(grade_card.get("structure", 0.0) or 0.0))
    cost_norm = _clamp01(float(metadata.get("cost_norm", 0.0) or 0.0))
    latency_norm = _clamp01(float(metadata.get("latency_norm", 0.0) or 0.0))
    token_norm = _clamp01(float(metadata.get("token_norm", 0.0) or 0.0))

    return FitnessScore(
        correctness=final_score,
        dharmic_alignment=_clamp01((groundedness * 0.6) + (contradiction_handling * 0.4)),
        performance=_clamp01(1.0 - latency_norm),
        utilization=_clamp01(1.0 - token_norm),
        economic_value=_clamp01(1.0 - cost_norm),
        elegance=structure,
        efficiency=_clamp01(1.0 - ((cost_norm + latency_norm + token_norm) / 3.0)),
        safety=1.0 if not gate_failures else 0.0,
    )


class FitnessScore(BaseModel):
    """Multi-dimensional fitness score for an evolution entry.

    Now includes JIKOKU performance metrics + economic ROI measurement.
    This enables the system to optimize for both technical excellence AND business value.
    """

    correctness: float = 0.0       # Test pass rate (0-1)
    dharmic_alignment: float = 0.0 # Gate outcomes (0-1)
    performance: float = 0.0       # Wall clock speedup (0-1) - JIKOKU
    utilization: float = 0.0       # Concurrent execution (0-1) - JIKOKU
    economic_value: float = 0.0    # ROI-based fitness (0-1) - NEW - Economic fitness
    elegance: float = 0.0          # Code quality (0-1)
    efficiency: float = 0.0        # Diff size penalty (0-1)
    safety: float = 0.0            # Gate pass/fail (0-1)

    def weighted(self, weights: dict[str, float] | None = None) -> float:
        """Return weighted total fitness.

        Args:
            weights: Optional mapping of dimension name to weight.
                     Defaults to the canonical fitness weighting.
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
    experiment_id: str | None = None
    execution_profile: str = "default"
    evidence_tier: str = EvidenceTier.UNVALIDATED.value
    promotion_state: str = PromotionState.CANDIDATE.value

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

    # Cryptographic audit trail (Merkle log)
    merkle_root: Optional[str] = None          # SHA-256 hash after this entry
    parent_merkle_root: Optional[str] = None   # Parent's merkle_root (for verification)


class MAPElitesGrid:
    """MAP-Elites diversity archive binning entries by feature dimensions.

    Maintains one entry per bin (the fittest). Prevents evolutionary
    convergence by preserving diverse solutions across feature space.

    Feature dimensions for dharma_swarm:
        - dharmic_alignment: [0.0, 1.0] binned into N_BINS intervals
        - elegance: [0.0, 1.0] binned into N_BINS intervals
        - complexity: diff_size mapped to [0.0, 1.0] via min(diff_lines/500, 1.0)
    """

    N_BINS: int = 5  # Default 5x5x5 = 125 cells max

    def __init__(self, n_bins: int | None = None) -> None:
        # grid[(d_bin, e_bin, c_bin)] = ArchiveEntry (best per cell)
        self.n_bins = max(3, int(n_bins or self.N_BINS))
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
            self._bin_value(coords.get("dharmic_alignment", 0.0), self.n_bins),
            self._bin_value(coords.get("elegance", 0.0), self.n_bins),
            self._bin_value(coords.get("complexity", 0.0), self.n_bins),
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

    def get_diverse_parents(
        self,
        n: int = 5,
        weights: dict[str, float] | None = None,
    ) -> list[ArchiveEntry]:
        """Return up to n entries from distinct bins, sorted by fitness.

        This provides diverse parents for the next evolution cycle.
        """
        entries = sorted(
            self._grid.values(),
            key=lambda e: e.fitness.weighted(weights=weights),
            reverse=True,
        )
        return entries[:n]

    @property
    def occupied_bins(self) -> int:
        """Number of occupied bins in the grid."""
        return len(self._grid)

    @property
    def total_bins(self) -> int:
        """Total possible bins (n_bins^3)."""
        return self.n_bins ** 3

    def coverage(self) -> float:
        """Fraction of bins occupied."""
        return self.occupied_bins / self.total_bins if self.total_bins > 0 else 0.0

    def rebuild(self, entries: list[ArchiveEntry]) -> None:
        """Rebuild the grid from a list of applied entries."""
        self._grid.clear()
        for entry in entries:
            self.try_insert(entry)


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

_DEFAULT_ARCHIVE_PATH = Path.home() / ".dharma" / "evolution" / "archive.jsonl"


class EvolutionArchive:
    """Append-only evolution archive with lineage tracking.

    All file I/O is async.  Entries are indexed in-memory after ``load()``.
    """

    def __init__(self, path: Path | None = None, grid_bins: int | None = None) -> None:
        self.path: Path = path or _DEFAULT_ARCHIVE_PATH
        self._entries: dict[str, ArchiveEntry] = {}
        self.grid = MAPElitesGrid(n_bins=grid_bins)
        # Merkle log for tamper-evident audit trail
        merkle_path = self.path.parent / "merkle_log.json"
        self.merkle_log = MerkleLog(merkle_path)

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Read existing JSONL file into memory."""
        self._entries.clear()
        self.grid.rebuild([])
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

        Also appends to Merkle log for cryptographic tamper-evidence.

        Returns:
            The entry id.
        """
        # Get parent's merkle root if this has a parent
        if entry.parent_id:
            parent = self._entries.get(entry.parent_id)
            if parent and parent.merkle_root:
                entry.parent_merkle_root = parent.merkle_root

        # Append to Merkle log (tamper-evident audit trail)
        merkle_data = {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "parent_id": entry.parent_id,
            "component": entry.component,
            "change_type": entry.change_type,
            "description": entry.description,
            "diff_hash": hashlib.sha256(entry.diff.encode()).hexdigest() if entry.diff else None,
            "fitness_weighted": entry.fitness.weighted(),
            "status": entry.status,
            "execution_profile": entry.execution_profile,
            "promotion_state": entry.promotion_state,
        }
        entry.merkle_root = self.merkle_log.append(merkle_data)

        # Add to in-memory structures
        self._entries[entry.id] = entry
        self.grid.try_insert(entry)

        # Persist to JSONL
        await self._append_line(entry)

        return entry.id

    def reconfigure_grid(self, n_bins: int) -> None:
        """Change MAP-Elites granularity and rebuild from current applied entries."""
        self.grid = MAPElitesGrid(n_bins=n_bins)
        applied_entries = [
            entry for entry in self._entries.values() if entry.status == "applied"
        ]
        self.grid.rebuild(applied_entries)

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

    async def list_entries(
        self,
        status: str | None = None,
        component: str | None = None,
    ) -> list[ArchiveEntry]:
        """List archive entries with optional status/component filters."""
        entries = list(self._entries.values())
        if status is not None:
            entries = [entry for entry in entries if entry.status == status]
        if component is not None:
            entries = [entry for entry in entries if entry.component == component]
        entries.sort(key=lambda entry: entry.timestamp)
        return entries

    async def get_best(
        self,
        n: int = 5,
        component: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[ArchiveEntry]:
        """Return the top *n* applied entries sorted by weighted fitness.

        Args:
            n: How many to return.
            component: If given, filter to entries matching this component.
            weights: Optional weight override for ranking entries.
        """
        entries = list(self._entries.values())
        if component:
            entries = [e for e in entries if e.component == component]
        entries = [e for e in entries if e.status == "applied"]
        entries.sort(
            key=lambda e: e.fitness.weighted(weights=weights),
            reverse=True,
        )
        return entries[:n]

    async def get_best_approaches(self, n: int = 5, component: str | None = None) -> list[dict[str, str]]:
        """Return condensed summaries of top applied entries (PULL interface)."""
        best = await self.get_best(n=n, component=component)
        return [{
            "component": e.component,
            "change_type": e.change_type,
            "description": e.description[:200],
            "fitness": f"{e.fitness.weighted():.3f}",
            "gates_passed": ", ".join(e.gates_passed[:5]) if e.gates_passed else "none",
        } for e in best]

    async def get_latest(self, n: int = 10) -> list[ArchiveEntry]:
        """Return the *n* most recent entries by timestamp."""
        entries = sorted(
            self._entries.values(), key=lambda e: e.timestamp, reverse=True
        )
        return entries[:n]

    async def get_diverse(
        self,
        n: int = 5,
        weights: dict[str, float] | None = None,
    ) -> list[ArchiveEntry]:
        """Return diverse parents from the MAP-Elites grid.

        Args:
            n: Maximum number of diverse entries to return.

        Returns:
            List of entries from distinct feature bins, sorted by fitness.
        """
        return self.grid.get_diverse_parents(n=n, weights=weights)

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

    async def compact(self, min_age_entries: int = 50, fitness_percentile: float = 0.5) -> int:
        """Mark low-value childless entries as composted (forgetting law)."""
        entries = list(self._entries.values())
        if len(entries) < min_age_entries:
            return 0
        applied = [e for e in entries if e.status == "applied"]
        if not applied:
            return 0
        fitness_values = sorted(e.fitness.weighted() for e in applied)
        median_idx = int(len(fitness_values) * fitness_percentile)
        threshold = fitness_values[min(median_idx, len(fitness_values) - 1)]
        has_children: set[str] = set()
        for e in entries:
            if e.parent_id:
                has_children.add(e.parent_id)
        entries_by_time = sorted(entries, key=lambda e: e.timestamp)
        old_entries = entries_by_time[:-min_age_entries] if len(entries_by_time) > min_age_entries else []
        composted = 0
        for e in old_entries:
            if (e.status in ("applied", "proposed") and e.fitness.weighted() < threshold and e.id not in has_children):
                e.status = "composted"
                composted += 1
        if composted > 0:
            await self._rewrite()
        return composted

    def fitness_over_time(
        self,
        component: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``(timestamp, weighted_fitness)`` pairs for applied entries."""
        entries = list(self._entries.values())
        if component:
            entries = [e for e in entries if e.component == component]
        entries = [e for e in entries if e.status == "applied"]
        entries.sort(key=lambda e: e.timestamp)
        return [
            (e.timestamp, e.fitness.weighted(weights=weights))
            for e in entries
        ]

    def verify_merkle_chain(self) -> tuple[bool, str]:
        """Verify cryptographic integrity of evolution history.

        Uses the Merkle log to detect any tampering with the archive.

        Returns:
            Tuple of (is_valid, message)
                is_valid: True if chain is intact, False if tampering detected
                message: Human-readable verification result

        Example:
            >>> archive = EvolutionArchive()
            >>> await archive.load()
            >>> valid, msg = archive.verify_merkle_chain()
            >>> print(f"Archive integrity: {msg}")
        """
        # Verify the underlying Merkle log structure
        chain_valid, last_index = self.merkle_log.verify_chain()

        if not chain_valid:
            return False, f"Merkle chain broken at index {last_index}"

        # Verify parent-child relationships match merkle roots
        for entry in self._entries.values():
            if entry.parent_id and entry.parent_merkle_root:
                parent = self._entries.get(entry.parent_id)
                if parent and parent.merkle_root:
                    if parent.merkle_root != entry.parent_merkle_root:
                        return False, (
                            f"Parent merkle root mismatch for entry {entry.id[:8]}: "
                            f"expected {parent.merkle_root[:16]}..., "
                            f"got {entry.parent_merkle_root[:16]}..."
                        )

        chain_length = self.merkle_log.get_chain_length()
        root = self.merkle_log.get_root()
        root_display = root[:16] + "..." if root else "empty"
        return True, (
            f"✓ Archive verified: {chain_length} entries, "
            f"Merkle root: {root_display}"
        )

    # -- Methods required by API routers ------------------------------------

    def stats(self) -> dict:
        """Summary statistics for the evolution archive."""
        entries = list(self._entries.values())
        by_status: dict[str, int] = {}
        by_component: dict[str, int] = {}
        for e in entries:
            by_status[e.status] = by_status.get(e.status, 0) + 1
            if e.component:
                by_component[e.component] = by_component.get(e.component, 0) + 1
        applied = [e for e in entries if e.status == "applied"]
        avg_fitness = (
            sum(e.fitness.weighted() for e in applied) / len(applied)
            if applied
            else 0.0
        )
        return {
            "total": len(entries),
            "by_status": by_status,
            "by_component": by_component,
            "avg_applied_fitness": round(avg_fitness, 4),
        }

    def entries_by_component(self, component: str) -> list:
        """Return entries filtered by component (sync, for API compatibility)."""
        return [e for e in self._entries.values() if e.component == component]

    def lineage(self, entry_id: str) -> list:
        """Sync wrapper for get_lineage (API router calls this synchronously)."""
        chain: list = []
        current = self._entries.get(entry_id)
        seen: set[str] = set()
        while current and current.id not in seen:
            chain.append(current)
            seen.add(current.id)
            if current.parent_id:
                current = self._entries.get(current.parent_id)
            else:
                break
        return chain
