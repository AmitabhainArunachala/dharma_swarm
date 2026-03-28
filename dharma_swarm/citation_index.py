"""Citation Index -- typed links between knowledge passages and system artifacts.

Links verbatim passages from primary texts to specific code locations,
corpus claims, kernel principles, and telos gates.  Each citation tracks
its relationship type, evidence for the link, and usage statistics.

Persistence: JSONL at ~/.dharma/citations/citations.jsonl

Follows the same append-friendly JSONL pattern as ``dharma_corpus.py``
and ``stigmergy.py``.  All I/O is async via aiofiles.
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

TargetType = Literal["code_function", "code_file", "claim", "principle", "gate"]
Relationship = Literal["grounds", "challenges", "extends", "instantiates", "violates"]

_DEFAULT_CITATIONS_PATH = Path.home() / ".dharma" / "citations" / "citations.jsonl"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A typed link between a knowledge passage and a system artifact."""

    id: str = Field(default_factory=_new_id)
    passage_text: str                       # verbatim quote from source
    source_work: str                        # e.g. "ashby_1956_introduction_to_cybernetics"
    source_location: str                    # e.g. "chapter_11:section_11/7"

    target_type: TargetType                 # what kind of artifact the citation points to
    target_id: str                          # e.g. "dharma_swarm/telos_gates.py::GateRegistry.propose"

    relationship: Relationship              # how the passage relates to the target
    evidence: str                           # WHY this link exists

    verified: bool = False                  # has the link been computationally verified?
    verification_test: Optional[str] = None  # Python assertion that checks link validity

    created_at: datetime = Field(default_factory=_utc_now)
    created_by: str = "reading_pipeline"
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    last_verified: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class CitationIndex:
    """JSONL-backed citation store with query methods.

    In-memory index rebuilt from JSONL on ``load()``.  Mutations append
    to the file (or rewrite when access counts change).  An asyncio lock
    serializes all writes so concurrent coroutines never interleave.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DEFAULT_CITATIONS_PATH
        self._citations: dict[str, Citation] = {}
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Read existing JSONL into memory."""
        self._citations.clear()
        if not self._path.exists():
            return
        async with aiofiles.open(self._path, "r") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    citation = Citation(**data)
                    self._citations[citation.id] = citation
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

    async def _append(self, citation: Citation) -> None:
        """Append a single citation as a JSONL line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._write_lock:
            async with aiofiles.open(self._path, "a") as f:
                await f.write(citation.model_dump_json() + "\n")

    async def _rewrite(self) -> None:
        """Rewrite the full JSONL file from in-memory state."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._write_lock:
            tmp = self._path.with_suffix(".tmp")
            async with aiofiles.open(tmp, "w") as f:
                for citation in self._citations.values():
                    await f.write(citation.model_dump_json() + "\n")
            tmp.replace(self._path)

    # -- public API ----------------------------------------------------------

    async def add(self, citation: Citation) -> str:
        """Add a citation to the index.  Returns the citation id."""
        self._citations[citation.id] = citation
        await self._append(citation)
        return citation.id

    async def get(self, citation_id: str) -> Citation | None:
        """Look up a single citation by id."""
        return self._citations.get(citation_id)

    async def query_by_target(self, target_id: str) -> list[Citation]:
        """Find all citations pointing to a specific code location or artifact."""
        return [c for c in self._citations.values() if c.target_id == target_id]

    async def query_by_source(self, source_work: str) -> list[Citation]:
        """Find all citations from a specific source text."""
        return [c for c in self._citations.values() if c.source_work == source_work]

    async def query_by_relationship(self, relationship: str) -> list[Citation]:
        """Find all citations with a specific relationship type."""
        return [c for c in self._citations.values() if c.relationship == relationship]

    async def query_by_target_type(self, target_type: str) -> list[Citation]:
        """Find all citations pointing to a specific target type."""
        return [c for c in self._citations.values() if c.target_type == target_type]

    async def search(self, keyword: str) -> list[Citation]:
        """Full-text search across passage_text, evidence, and target_id."""
        kw = keyword.lower()
        return [
            c for c in self._citations.values()
            if kw in c.passage_text.lower()
            or kw in c.evidence.lower()
            or kw in c.target_id.lower()
        ]

    async def record_access(self, citation_id: str) -> None:
        """Increment access count and update last_accessed timestamp."""
        citation = self._citations.get(citation_id)
        if citation is None:
            raise KeyError(f"Citation {citation_id} not found")
        citation.access_count += 1
        citation.last_accessed = _utc_now()
        await self._rewrite()

    async def verify_all(self) -> dict[str, bool]:
        """Run verification tests for all citations that have them.

        Each ``verification_test`` is a Python expression evaluated in
        a namespace containing ``Path`` and ``os``.  Returns a mapping
        of citation id to pass/fail.
        """
        import os

        results: dict[str, bool] = {}
        ns: dict[str, object] = {"Path": Path, "os": os}
        for cid, citation in self._citations.items():
            if not citation.verification_test:
                continue
            try:
                passed = bool(eval(citation.verification_test, ns))  # noqa: S307
            except Exception:
                passed = False
            results[cid] = passed
            citation.verified = passed
            citation.last_verified = _utc_now()
        if results:
            await self._rewrite()
        return results

    async def list_all(self) -> list[Citation]:
        """Return all citations in insertion order."""
        return list(self._citations.values())

    async def count(self) -> int:
        """Return total citation count."""
        return len(self._citations)

    async def remove(self, citation_id: str) -> None:
        """Remove a citation by id."""
        if citation_id not in self._citations:
            raise KeyError(f"Citation {citation_id} not found")
        del self._citations[citation_id]
        await self._rewrite()

    # -- summary helpers -----------------------------------------------------

    async def coverage_report(self) -> dict[str, int]:
        """Return counts grouped by relationship type."""
        counts: dict[str, int] = {}
        for c in self._citations.values():
            counts[c.relationship] = counts.get(c.relationship, 0) + 1
        return counts

    async def unverified(self) -> list[Citation]:
        """Return citations that have verification_test but verified=False."""
        return [
            c for c in self._citations.values()
            if c.verification_test and not c.verified
        ]

    # -- sync helpers --------------------------------------------------------

    def density(self) -> int:
        """Synchronous count of citations in the JSONL file (quick check)."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, "r") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
