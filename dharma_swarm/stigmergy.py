"""Stigmergic lattice -- emergent intelligence through accumulated marks.

Agents leave marks on the environment (files they touch), creating
pheromone-trail-like coordination without direct communication.  Like
ant colonies: no single agent holds the whole picture, but the
accumulated observations form a shared intelligence layer.

Uses JSONL for append-friendly persistence and ``aiofiles`` for
non-blocking I/O.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import aiofiles
from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)

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
    action: str = ""  # Was required Action; defaulted for back-compat with old marks
    observation: str = Field(max_length=500)  # Expanded from 200 for TPP-structured marks
    salience: float = 0.5
    connections: list[str] = Field(default_factory=list)
    access_count: int = 0
    # TPP metadata — optional structured context for richer cross-agent communication
    telos_tag: str = ""  # Tag linking mark to a telos thread
    tpp_version: str = ""  # If set, observation is TPP-formatted
    source: str = ""  # "test" for marks from test context, "" for production


# ---------------------------------------------------------------------------
# Quality gate — reject noise before it hits the lattice
# ---------------------------------------------------------------------------

_NOISE_PATTERNS = [
    re.compile(r"eval_probe_\d+"),
    re.compile(r"^Budget exhausted", re.IGNORECASE),
    re.compile(r"^task done successfully$", re.IGNORECASE),
]

_TEST_ENV_VARS = ("PYTEST_CURRENT_TEST", "_DHARMA_IN_TEST")


def _is_test_context() -> bool:
    """Detect if we're running inside a test harness."""
    return any(os.environ.get(v) for v in _TEST_ENV_VARS)


def _quality_gate(mark: StigmergicMark) -> tuple[bool, str]:
    """Check if a mark passes quality standards.

    Returns (passed, reason). If passed is False, the mark should be
    rejected or redirected to archive.
    """
    obs = mark.observation.strip()

    # Reject too-short observations (noise, not signal)
    if len(obs) < 20:
        return False, f"observation too short ({len(obs)} chars < 20)"

    # Reject known noise patterns
    for pat in _NOISE_PATTERNS:
        if pat.search(obs):
            return False, f"matches noise pattern: {pat.pattern}"

    return True, ""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

_DEFAULT_BASE = Path.home() / ".dharma" / "stigmergy"
_PRODUCTION_BASE = Path.home() / ".dharma" / "stigmergy"  # Immutable reference


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
        """Append *mark* as a JSON line and return its id.

        Marks are quality-gated: noise patterns and too-short observations
        are rejected.  Test-context marks are tagged ``source="test"``
        and excluded from read queries by default.
        """
        # Tag test-context marks when writing to the real production store.
        # Marks written to custom base_paths (e.g. tmp_path in tests) are not tagged,
        # so tests can read them back normally.
        _is_prod = self.base_path == _PRODUCTION_BASE
        if not mark.source and _is_prod and _is_test_context():
            mark.source = "test"

        # Quality gate — reject noise (skip for test-context and non-production stores)
        if mark.source != "test" and _is_prod:
            passed, reason = _quality_gate(mark)
            if not passed:
                logger.debug("Stigmergy quality gate rejected mark %s: %s", mark.id, reason)
                return mark.id  # Return id but don't persist

        self.base_path.mkdir(parents=True, exist_ok=True)
        line = mark.model_dump_json() + "\n"
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
        include_test: bool = False,
    ) -> list[StigmergicMark]:
        """Return recent marks, optionally filtered by *file_path*.

        Results are sorted newest-first and capped at *limit*.
        Salience reinforcement: marks that are read gain salience
        proportional to their access_count.

        Args:
            include_test: If False (default), exclude marks with source="test".
        """
        all_marks = await self._load_marks()
        if not include_test:
            all_marks = [m for m in all_marks if m.source != "test"]
        if file_path is not None:
            filtered = [m for m in all_marks if m.file_path == file_path]
        else:
            filtered = list(all_marks)
        filtered.sort(key=lambda m: m.timestamp, reverse=True)
        result = filtered[:limit]

        # Salience reinforcement: boost accessed marks
        result_ids = {m.id for m in result}
        changed = False
        for m in all_marks:
            if m.id in result_ids:
                m.access_count += 1
                m.salience = min(1.0, m.salience + 0.02 * m.access_count)
                changed = True

        if changed:
            self.base_path.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._marks_file, "w") as f:
                for m in all_marks:
                    await f.write(m.model_dump_json() + "\n")

        return result

    async def hot_paths(
        self,
        window_hours: float = 24,
        min_marks: int = 3,
        include_test: bool = False,
    ) -> list[tuple[str, int]]:
        """Return file paths with heavy recent activity.

        Only marks within the last *window_hours* are counted.  Paths
        with fewer than *min_marks* marks are excluded.  Sorted by count
        descending.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        marks = await self._load_marks()
        if not include_test:
            marks = [m for m in marks if m.source != "test"]
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
        include_test: bool = False,
    ) -> list[StigmergicMark]:
        """Return marks with salience >= *threshold*, sorted descending."""
        marks = await self._load_marks()
        if not include_test:
            marks = [m for m in marks if m.source != "test"]
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

    async def query_relevant(self, task_keywords: list[str], limit: int = 10) -> list[StigmergicMark]:
        """Filter marks by keyword overlap, sorted by salience (PULL protocol)."""
        if not task_keywords:
            return await self.high_salience(limit=limit)
        marks = await self._load_marks()
        keywords_lower = [kw.lower() for kw in task_keywords if kw.strip()]
        if not keywords_lower:
            return await self.high_salience(limit=limit)
        relevant = [m for m in marks if any(kw in (m.observation + " " + m.file_path).lower() for kw in keywords_lower)]
        relevant.sort(key=lambda m: m.salience, reverse=True)
        return relevant[:limit]

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

    async def access_decay(self, decay_factor: float = 0.95) -> int:
        """Decay marks based on access count -- unused marks fade faster."""
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
        async with aiofiles.open(self._marks_file, "w") as f:
            for m in marks:
                await f.write(m.model_dump_json() + "\n")
        return dead_count

    # -- adaptive maintenance ------------------------------------------------

    async def adaptive_decay(self) -> int:
        """Adaptive evaporation: decay faster when saturated, slower when sparse.

        Mark count thresholds:
            >100  ->  72h max age   (fast evaporation, reduce noise)
            <20   ->  336h max age  (2 weeks, preserve sparse signals)
            else  ->  168h default  (1 week)

        Also runs access_decay to fade unused marks.

        Returns:
            Total number of archived marks.
        """
        count = self.density()
        if count > 100:
            max_age_hours = 72.0
        elif count < 20:
            max_age_hours = 336.0
        else:
            max_age_hours = 168.0

        archived = await self.decay(max_age_hours=max_age_hours)
        await self.access_decay()
        return archived

    async def saturation_check(self) -> float:
        """Check if new marks are redundant. Returns redundancy ratio 0.0-1.0.

        Loads the last 20 marks and checks pairwise observation overlap.
        Two marks are considered redundant if they share >50% of words
        (measured against the shorter observation).

        If ratio > 0.8, callers should slow down mark generation.
        """
        marks = await self._load_marks()
        marks.sort(key=lambda m: m.timestamp, reverse=True)
        recent = marks[:20]

        if len(recent) < 2:
            return 0.0

        def _word_set(text: str) -> set[str]:
            return set(text.lower().split())

        total_pairs = 0
        redundant_pairs = 0
        for i in range(len(recent)):
            words_i = _word_set(recent[i].observation)
            for j in range(i + 1, len(recent)):
                total_pairs += 1
                words_j = _word_set(recent[j].observation)
                shorter_len = min(len(words_i), len(words_j))
                if shorter_len == 0:
                    continue
                overlap = len(words_i & words_j)
                if overlap / shorter_len > 0.5:
                    redundant_pairs += 1

        if total_pairs == 0:
            return 0.0
        return round(redundant_pairs / total_pairs, 3)

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
    action: Action = "write",
) -> str:
    """Create a mark and persist it via a default store. Returns the mark id."""
    mark = StigmergicMark(
        agent=agent,
        file_path=file_path,
        action=action,
        observation=observation,
        salience=salience,
        connections=connections or [],
    )
    store = StigmergyStore()
    return await store.leave_mark(mark)
