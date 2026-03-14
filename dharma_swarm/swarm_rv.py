"""Swarm R_V -- behavioral contraction measurement for the colony.

Applies R_V-like measurements to the swarm's behavioral outputs.
Measures topic diversity, solution convergence, and exploration/exploitation.

When agents converge on a solution -> PR drops -> contraction
When agents explore diverse paths -> PR rises -> expansion

L3 crisis = agents stuck in loops (high similarity, low fitness)
L4 collapse = agents converge on breakthrough (high similarity, high fitness)
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now

logger = logging.getLogger(__name__)

# ── Stopwords ────────────────────────────────────────────────────────────────

_ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "the", "is", "a", "an", "to", "in", "for", "of", "and", "or", "but",
    "it", "its", "this", "that", "with", "from", "be", "are", "was", "were",
    "has", "have", "had", "not", "all", "can", "will", "would", "should",
    "could", "may", "might", "do", "does", "did", "been", "being", "more",
    "most", "some", "any", "each", "than", "then", "also", "into", "only",
    "very", "just", "about", "over", "such", "through", "after", "before",
    "between", "under", "during", "without", "within", "along", "these",
    "those", "which", "what", "when", "where", "who", "how", "there",
    "here", "they", "them", "their", "your", "our", "out", "up", "down",
    "new", "one", "two", "use", "used", "using", "like", "need", "make",
    "get", "set", "see", "now", "way", "well", "back", "still", "even",
})

_DOMAIN_STOPWORDS: frozenset[str] = frozenset({
    "file", "path", "note", "notes", "agent", "agents", "swarm", "dharma",
    "system", "data", "task", "tasks", "status", "completed", "running",
    "output", "input", "result", "results", "report", "test", "tests",
    "code", "line", "lines", "module", "function", "class", "utc", "date",
})

_ALL_STOPWORDS: frozenset[str] = _ENGLISH_STOPWORDS | _DOMAIN_STOPWORDS

_WORD_RE = re.compile(r"[a-z][a-z0-9_-]+")
_MIN_WORD_LEN = 4

# ── Productivity markers ─────────────────────────────────────────────────────

_PRODUCTIVE_WORDS: frozenset[str] = frozenset({
    "conclusion", "resolved", "decided", "solution", "breakthrough",
    "confirmed", "verified", "fixed", "implemented", "shipped", "merged",
    "pass", "passing", "success", "complete", "done", "answer", "found",
})

_STUCK_WORDS: frozenset[str] = frozenset({
    "confused", "stuck", "unclear", "blocked", "loop", "looping",
    "repeated", "retry", "retrying", "failed", "failing", "broken",
    "error", "bug", "regression", "again", "still", "unknown",
})


# ── Models ───────────────────────────────────────────────────────────────────

class ContractionLevel(str, Enum):
    """Swarm cognitive contraction state."""

    EXPANDING = "expanding"
    STABLE = "stable"
    CONTRACTING = "contracting"
    COLLAPSED = "collapsed"


class SwarmRVReading(BaseModel):
    """A single R_V measurement for the swarm."""

    timestamp: datetime = Field(default_factory=_utc_now)
    topic_pr: float = Field(
        description="Participation ratio of topic distribution, normalized 0-1."
    )
    similarity: float = Field(
        description="Average pairwise Jaccard similarity of consecutive notes."
    )
    exploration_ratio: float = Field(
        description="Fraction of topics that are new in this window."
    )
    contraction_level: ContractionLevel
    is_productive: bool = Field(
        description="True if contracting with high fitness (L4), False if stuck (L3)."
    )
    window_size: int = Field(description="Number of notes in the measurement window.")
    top_topics: list[str] = Field(
        default_factory=list, description="Top 5 topics by frequency."
    )


# ── Core measurement ─────────────────────────────────────────────────────────

class SwarmRV:
    """Behavioral R_V measurement for the swarm colony.

    Reads agent-produced shared notes and computes topic diversity,
    inter-note similarity, and exploration ratio to assess whether
    the colony is expanding, stable, contracting, or collapsed.
    """

    def __init__(self, shared_dir: Optional[Path] = None) -> None:
        self.shared_dir = shared_dir or (Path.home() / ".dharma" / "shared")

    # ── Private helpers ──────────────────────────────────────────────────

    def _extract_topics(self, text: str) -> list[str]:
        """Extract topic keywords from text using simple TF approach.

        Splits on whitespace/punctuation, lowercases, filters stopwords and
        short words, returns top 15 keywords by frequency.

        Args:
            text: Raw note content.

        Returns:
            Up to 15 topic keywords sorted by descending frequency.
        """
        words = _WORD_RE.findall(text.lower())
        counts: Counter[str] = Counter(
            w for w in words
            if len(w) >= _MIN_WORD_LEN and w not in _ALL_STOPWORDS
        )
        return [word for word, _ in counts.most_common(15)]

    def _compute_participation_ratio(self, counts: Counter[str]) -> float:
        """Compute normalized participation ratio from a frequency counter.

        PR = (sum p_i)^2 / sum(p_i^2), normalized to [0, 1] by dividing by N.
        Where p_i = count_i / total.

        Args:
            counts: Token frequency counter.

        Returns:
            Normalized PR in [0, 1]. Returns 0.0 for empty counters.
        """
        total = sum(counts.values())
        if total == 0:
            return 0.0

        n = len(counts)
        if n == 0:
            return 0.0

        probs = [c / total for c in counts.values()]
        sum_sq = sum(p * p for p in probs)

        if sum_sq == 0.0:
            return 0.0

        raw_pr = 1.0 / sum_sq  # (sum(p))^2 = 1.0 since probs are normalized
        return raw_pr / n

    def _compute_similarity(self, topic_lists: list[list[str]]) -> float:
        """Compute average Jaccard similarity between consecutive note topic lists.

        Args:
            topic_lists: List of topic keyword lists, one per note.

        Returns:
            Mean Jaccard index in [0, 1]. Returns 0.0 if fewer than 2 lists.
        """
        if len(topic_lists) < 2:
            return 0.0

        similarities: list[float] = []
        for i in range(len(topic_lists) - 1):
            set_a = set(topic_lists[i])
            set_b = set(topic_lists[i + 1])
            union = set_a | set_b
            if not union:
                similarities.append(0.0)
            else:
                similarities.append(len(set_a & set_b) / len(union))

        return sum(similarities) / len(similarities)

    def _assess_contraction(
        self,
        topic_pr: float,
        similarity: float,
        exploration_ratio: float,
    ) -> ContractionLevel:
        """Map measurements to contraction level.

        Args:
            topic_pr: Normalized participation ratio [0, 1].
            similarity: Average Jaccard similarity [0, 1].
            exploration_ratio: Fraction of new topics [0, 1].

        Returns:
            The assessed ContractionLevel.
        """
        if topic_pr < 0.15 and similarity > 0.7:
            return ContractionLevel.COLLAPSED
        if topic_pr < 0.3 or similarity > 0.5:
            return ContractionLevel.CONTRACTING
        if topic_pr > 0.6 and exploration_ratio > 0.4:
            return ContractionLevel.EXPANDING
        return ContractionLevel.STABLE

    def _assess_productivity(
        self,
        contraction: ContractionLevel,
        recent_notes: list[str],
    ) -> bool:
        """Check if contraction is productive (L4) vs stuck (L3).

        Productive contraction: notes contain conclusion/result/decision words.
        Unproductive: notes contain confusion/loop/repeated-question words.

        Args:
            contraction: Current contraction level.
            recent_notes: Raw text of recent notes.

        Returns:
            True if productive (L4-like), False if stuck (L3-like).
        """
        if contraction in (ContractionLevel.EXPANDING, ContractionLevel.STABLE):
            return True

        productive_count = 0
        stuck_count = 0
        for text in recent_notes:
            words = set(_WORD_RE.findall(text.lower()))
            productive_count += len(words & _PRODUCTIVE_WORDS)
            stuck_count += len(words & _STUCK_WORDS)

        return productive_count >= stuck_count

    def _read_notes(self, limit: int) -> list[tuple[Path, str]]:
        """Read the most recent note files sorted by mtime descending.

        Args:
            limit: Maximum number of files to read.

        Returns:
            List of (path, content) tuples, most recent first.
        """
        if not self.shared_dir.is_dir():
            logger.debug("Shared dir %s does not exist", self.shared_dir)
            return []

        md_files = sorted(
            self.shared_dir.glob("*_notes.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        results: list[tuple[Path, str]] = []
        for path in md_files[:limit]:
            try:
                results.append((path, path.read_text(encoding="utf-8")))
            except OSError:
                logger.warning("Could not read %s", path)
        return results

    # ── Public API ───────────────────────────────────────────────────────

    def measure(self, window: int = 20) -> SwarmRVReading:
        """Take a single R_V measurement from recent shared notes.

        Reads the most recent ``window`` note files (by mtime), extracts
        topics, computes PR, similarity, and exploration ratio.

        Args:
            window: Number of recent note files to include.

        Returns:
            A SwarmRVReading with the current measurement.
        """
        notes = self._read_notes(window)

        if not notes:
            return SwarmRVReading(
                topic_pr=1.0,
                similarity=0.0,
                exploration_ratio=1.0,
                contraction_level=ContractionLevel.STABLE,
                is_productive=True,
                window_size=0,
                top_topics=[],
            )

        # Extract per-note topic lists and build global counter.
        topic_lists: list[list[str]] = []
        global_counts: Counter[str] = Counter()
        all_topics_seen: set[str] = set()

        for _, content in notes:
            topics = self._extract_topics(content)
            topic_lists.append(topics)
            global_counts.update(topics)

        # Exploration ratio: topics in most recent half that were NOT in
        # the older half.
        midpoint = max(1, len(topic_lists) // 2)
        recent_topics: set[str] = set()
        older_topics: set[str] = set()
        for tl in topic_lists[:midpoint]:
            recent_topics.update(tl)
        for tl in topic_lists[midpoint:]:
            older_topics.update(tl)

        if recent_topics:
            new_topics = recent_topics - older_topics
            exploration_ratio = len(new_topics) / len(recent_topics)
        else:
            exploration_ratio = 0.0

        topic_pr = self._compute_participation_ratio(global_counts)
        similarity = self._compute_similarity(topic_lists)
        contraction = self._assess_contraction(topic_pr, similarity, exploration_ratio)
        is_productive = self._assess_productivity(
            contraction, [content for _, content in notes]
        )
        top_topics = [word for word, _ in global_counts.most_common(5)]

        return SwarmRVReading(
            topic_pr=round(topic_pr, 4),
            similarity=round(similarity, 4),
            exploration_ratio=round(exploration_ratio, 4),
            contraction_level=contraction,
            is_productive=is_productive,
            window_size=len(notes),
            top_topics=top_topics,
        )

    def trend(
        self, measurements: int = 5, window: int = 20
    ) -> list[SwarmRVReading]:
        """Take multiple measurements over sliding windows to show trend.

        Each measurement uses ``window`` notes, sliding by
        ``window // measurements`` between each reading.

        Args:
            measurements: Number of readings to take.
            window: Notes per reading.

        Returns:
            List of SwarmRVReading from oldest to newest window.
        """
        all_notes = self._read_notes(window + window)  # fetch enough to slide
        if not all_notes:
            return [self.measure(window)]

        step = max(1, window // measurements)
        readings: list[SwarmRVReading] = []

        for i in range(measurements):
            offset = i * step
            chunk = all_notes[offset : offset + window]
            if not chunk:
                break

            # Build a temporary SwarmRV-like measurement from the chunk.
            topic_lists: list[list[str]] = []
            global_counts: Counter[str] = Counter()
            for _, content in chunk:
                topics = self._extract_topics(content)
                topic_lists.append(topics)
                global_counts.update(topics)

            midpoint = max(1, len(topic_lists) // 2)
            recent_topics: set[str] = set()
            older_topics: set[str] = set()
            for tl in topic_lists[:midpoint]:
                recent_topics.update(tl)
            for tl in topic_lists[midpoint:]:
                older_topics.update(tl)

            if recent_topics:
                new_in_window = recent_topics - older_topics
                exploration_ratio = len(new_in_window) / len(recent_topics)
            else:
                exploration_ratio = 0.0

            topic_pr = self._compute_participation_ratio(global_counts)
            similarity = self._compute_similarity(topic_lists)
            contraction = self._assess_contraction(
                topic_pr, similarity, exploration_ratio
            )
            is_productive = self._assess_productivity(
                contraction, [c for _, c in chunk]
            )
            top_topics = [w for w, _ in global_counts.most_common(5)]

            readings.append(
                SwarmRVReading(
                    topic_pr=round(topic_pr, 4),
                    similarity=round(similarity, 4),
                    exploration_ratio=round(exploration_ratio, 4),
                    contraction_level=contraction,
                    is_productive=is_productive,
                    window_size=len(chunk),
                    top_topics=top_topics,
                )
            )

        # Return oldest-to-newest (we read most-recent-first).
        readings.reverse()
        return readings

    def summary(self) -> str:
        """Human-readable one-paragraph summary of current swarm cognitive state.

        Returns:
            A concise string describing colony contraction state.
        """
        reading = self.measure()

        productive_label = "productive" if reading.is_productive else "stuck"
        topics_str = ", ".join(reading.top_topics) if reading.top_topics else "none"

        return (
            f"Colony state: {reading.contraction_level.value.upper()} "
            f"({productive_label}). "
            f"PR={reading.topic_pr:.2f}, similarity={reading.similarity:.2f}. "
            f"Top topics: {topics_str}. "
            f"{reading.window_size} notes in window."
        )
