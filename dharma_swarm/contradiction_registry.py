"""Contradiction Registry -- tracks genuine disagreements between traditions.

Contradictions aren't bugs -- they're the most intellectually fertile parts
of the corpus.  This registry tracks them explicitly so they can be tested,
resolved, or held as productive tensions.

Persistence: JSONL at ~/.dharma/contradictions/registry.jsonl

Follows the same append-friendly JSONL pattern as ``citation_index.py``
and ``dharma_corpus.py``.  All I/O is async via aiofiles.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import aiofiles
from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ResolutionStatus = Literal[
    "open", "acknowledged", "testing", "resolved", "irreconcilable"
]
ContradictionDomain = Literal["theoretical", "operational", "architectural"]

_DEFAULT_REGISTRY_PATH = (
    Path.home() / ".dharma" / "contradictions" / "registry.jsonl"
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class Contradiction(BaseModel):
    """A genuine disagreement between two traditions or frameworks."""

    id: str = Field(default_factory=_new_id)
    name: str                              # short key, e.g. "fixed_point_reachability"
    tradition_a: str                       # e.g. "cybernetics_ashby"
    claim_a: str                           # what tradition A asserts
    tradition_b: str                       # e.g. "akram_vignan"
    claim_b: str                           # what tradition B asserts (incompatible)
    tension: str                           # why relabeling cannot dissolve this
    resolution_status: ResolutionStatus = "open"
    resolution_path: str                   # how it might be tested or resolved
    testable_prediction: Optional[str] = None
    severity: float = 0.5                  # 0.0-1.0, operational importance
    domain: ContradictionDomain = "theoretical"
    created_at: datetime = Field(default_factory=_utc_now)
    created_by: str = "reading_pipeline"
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ContradictionRegistry:
    """JSONL-backed contradiction store with query methods.

    In-memory index rebuilt from JSONL on ``load()``.  Mutations append
    to the file (or rewrite when status changes).  An asyncio lock
    serializes all writes so concurrent coroutines never interleave.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DEFAULT_REGISTRY_PATH
        self._contradictions: dict[str, Contradiction] = {}
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Read existing JSONL into memory."""
        self._contradictions.clear()
        if not self._path.exists():
            return
        async with aiofiles.open(self._path, "r") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    contradiction = Contradiction(**data)
                    self._contradictions[contradiction.id] = contradiction
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

    async def _append(self, contradiction: Contradiction) -> None:
        """Append a single contradiction as a JSONL line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._write_lock:
            async with aiofiles.open(self._path, "a") as f:
                await f.write(contradiction.model_dump_json() + "\n")

    async def _rewrite(self) -> None:
        """Rewrite the full JSONL file from in-memory state."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._write_lock:
            tmp = self._path.with_suffix(".tmp")
            async with aiofiles.open(tmp, "w") as f:
                for contradiction in self._contradictions.values():
                    await f.write(contradiction.model_dump_json() + "\n")
            tmp.replace(self._path)

    # -- public API ----------------------------------------------------------

    async def record(self, contradiction: Contradiction) -> str:
        """Add a contradiction to the registry.  Returns the contradiction id."""
        self._contradictions[contradiction.id] = contradiction
        await self._append(contradiction)
        return contradiction.id

    async def get(self, contradiction_id: str) -> Contradiction | None:
        """Look up a single contradiction by id."""
        return self._contradictions.get(contradiction_id)

    async def query_open(self, domain: str | None = None) -> list[Contradiction]:
        """Find all contradictions with status 'open', optionally filtered by domain."""
        return [
            c for c in self._contradictions.values()
            if c.resolution_status == "open"
            and (domain is None or c.domain == domain)
        ]

    async def query_by_traditions(
        self, trad_a: str, trad_b: str
    ) -> list[Contradiction]:
        """Find contradictions involving both specified traditions (order-independent)."""
        results: list[Contradiction] = []
        for c in self._contradictions.values():
            pair = {c.tradition_a, c.tradition_b}
            if trad_a in pair and trad_b in pair:
                results.append(c)
        return results

    async def mark_resolved(self, contradiction_id: str, notes: str) -> None:
        """Transition a contradiction to 'resolved' status with resolution notes."""
        c = self._contradictions.get(contradiction_id)
        if c is None:
            raise KeyError(f"Contradiction {contradiction_id} not found")
        c.resolution_status = "resolved"
        c.resolution_notes = notes
        c.resolved_at = _utc_now()
        await self._rewrite()

    async def mark_testing(
        self, contradiction_id: str, prediction: str
    ) -> None:
        """Transition a contradiction to 'testing' status with a testable prediction."""
        c = self._contradictions.get(contradiction_id)
        if c is None:
            raise KeyError(f"Contradiction {contradiction_id} not found")
        c.resolution_status = "testing"
        c.testable_prediction = prediction
        await self._rewrite()

    async def list_all(self) -> list[Contradiction]:
        """Return all contradictions in insertion order."""
        return list(self._contradictions.values())

    async def count(self) -> int:
        """Return total contradiction count."""
        return len(self._contradictions)

    async def count_by_status(self) -> dict[str, int]:
        """Return counts grouped by resolution_status."""
        counts: dict[str, int] = {}
        for c in self._contradictions.values():
            counts[c.resolution_status] = counts.get(c.resolution_status, 0) + 1
        return counts

    async def search(self, keyword: str) -> list[Contradiction]:
        """Full-text search across name, claims, tension, and resolution_path."""
        kw = keyword.lower()
        return [
            c for c in self._contradictions.values()
            if kw in c.name.lower()
            or kw in c.claim_a.lower()
            or kw in c.claim_b.lower()
            or kw in c.tension.lower()
            or kw in c.resolution_path.lower()
        ]

    async def remove(self, contradiction_id: str) -> None:
        """Remove a contradiction by id."""
        if contradiction_id not in self._contradictions:
            raise KeyError(f"Contradiction {contradiction_id} not found")
        del self._contradictions[contradiction_id]
        await self._rewrite()

    # -- sync helpers --------------------------------------------------------

    def density(self) -> int:
        """Synchronous count of contradictions in the JSONL file (quick check)."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, "r") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
