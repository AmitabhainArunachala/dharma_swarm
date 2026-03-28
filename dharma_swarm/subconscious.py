"""Subconscious / HUM layer -- lateral association through random sampling.

When stigmergy density crosses a threshold, the subconscious wakes and
*dreams*: randomly sampling marks and computing resonance between them
via simple Jaccard similarity.  Associations are persisted as JSONL and
fed back into the stigmergic lattice with action="dream".

This is the colony's equivalent of sleeping on a problem -- low-cost
lateral connections that no single focused agent would produce.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiofiles
from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class SubconsciousAssociation(BaseModel):
    """A lateral association discovered by the subconscious."""

    id: str = Field(default_factory=_new_id)
    source_a: str
    source_b: str
    resonance_type: str = "unknown"
    description: str
    strength: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------

_DEFAULT_HUM_PATH = Path.home() / ".dharma" / "subconscious"


class SubconsciousStream:
    """Lateral association engine backed by stigmergy.

    Wakes when enough new marks have accumulated, randomly samples
    pairs, and records resonances to a JSONL hum file.
    """

    def __init__(
        self,
        stigmergy: StigmergyStore,
        hum_path: Path | None = None,
    ) -> None:
        self._stigmergy = stigmergy
        self._hum_path: Path = hum_path or _DEFAULT_HUM_PATH
        self._hum_file: Path = self._hum_path / "hum.jsonl"
        self._last_density: int = 0
        self._wake_threshold: int = 50

    # -- dreaming ------------------------------------------------------------

    async def dream(self, sample_size: int = 10) -> list[SubconsciousAssociation]:
        """Sample recent marks and discover lateral associations."""
        marks = await self._stigmergy.read_marks(limit=sample_size * 3)
        if not marks:
            return []

        sampled = random.sample(marks, min(sample_size, len(marks)))
        associations: list[SubconsciousAssociation] = []

        for i in range(len(sampled) - 1):
            mark_a = sampled[i]
            mark_b = sampled[i + 1]

            strength = self._find_resonance(mark_a.observation, mark_b.observation)

            # Classify resonance type
            if mark_a.file_path == mark_b.file_path:
                resonance_type = "structural_echo"
            elif (
                abs((mark_a.timestamp - mark_b.timestamp).total_seconds()) < 3600
            ):
                resonance_type = "temporal_coincidence"
            elif strength > 0.3:
                resonance_type = "pattern_similarity"
            else:
                resonance_type = "unknown"

            description = (
                f"{mark_a.observation[:100]} <-> {mark_b.observation[:100]}"
            )

            # Cap file_path to basename to prevent recursive bloat:
            # dream marks use source file_paths which may themselves be
            # concatenated dream paths from previous cycles.
            def _cap_path(p: str, limit: int = 200) -> str:
                if len(p) <= limit:
                    return p
                # Take last segment (after last <->)
                parts = p.rsplit("<->", 1)
                return parts[-1][:limit]

            assoc = SubconsciousAssociation(
                source_a=_cap_path(mark_a.file_path),
                source_b=_cap_path(mark_b.file_path),
                resonance_type=resonance_type,
                description=description,
                strength=strength,
            )
            associations.append(assoc)

        # Persist and leave stigmergic traces
        self._hum_path.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._hum_file, "a") as f:
            for assoc in associations:
                await f.write(assoc.model_dump_json() + "\n")

        for assoc in associations:
            dream_mark = StigmergicMark(
                agent="subconscious",
                file_path=f"{assoc.source_a[:100]}<->{assoc.source_b[:100]}",
                action="dream",
                observation=assoc.description[:200],
                salience=assoc.strength,
            )
            await self._stigmergy.leave_mark(dream_mark)

        self._last_density = self._stigmergy.density()
        return associations

    # -- wake check ----------------------------------------------------------

    async def should_wake(self) -> bool:
        """Return True if enough new marks have accumulated since last wake."""
        current = self._stigmergy.density()
        return (current - self._last_density) >= self._wake_threshold

    # -- reading dreams ------------------------------------------------------

    async def get_recent_dreams(self, limit: int = 10) -> list[SubconsciousAssociation]:
        """Return the most recent associations from the hum file."""
        if not self._hum_file.exists():
            return []

        entries: list[SubconsciousAssociation] = []
        async with aiofiles.open(self._hum_file, "r") as f:
            async for line in f:
                stripped = line.strip()
                if stripped:
                    entries.append(
                        SubconsciousAssociation.model_validate_json(stripped)
                    )

        # Newest first
        entries.reverse()
        return entries[:limit]

    async def strongest_resonances(
        self, threshold: float = 0.6,
    ) -> list[SubconsciousAssociation]:
        """Return associations with strength >= threshold, sorted descending."""
        if not self._hum_file.exists():
            return []

        entries: list[SubconsciousAssociation] = []
        async with aiofiles.open(self._hum_file, "r") as f:
            async for line in f:
                stripped = line.strip()
                if stripped:
                    assoc = SubconsciousAssociation.model_validate_json(stripped)
                    if assoc.strength >= threshold:
                        entries.append(assoc)

        entries.sort(key=lambda a: a.strength, reverse=True)
        return entries

    # -- resonance heuristic -------------------------------------------------

    @staticmethod
    def _find_resonance(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two observation texts.

        Simple word-overlap heuristic -- no LLM needed.
        """
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        total = len(words_a | words_b)
        if total == 0:
            return 0.0
        overlap = len(words_a & words_b)
        return overlap / total
