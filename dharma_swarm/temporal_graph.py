"""Temporal Knowledge Graph -- tracks idea lineage over time.

Nodes: concept mentions (keywords extracted from shared notes)
Edges: co-occurrence in same note
Time: each node has first_seen, last_seen, frequency

Enables: lineage queries, emerging/decaying concept detection,
co-occurrence analysis for cross-pollination insights.
"""

from __future__ import annotations

import itertools
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords -- English core + domain noise terms that carry no concept signal
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    # English function words
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "am", "it", "its",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "but", "and", "or", "if", "while", "about", "up", "me", "my",
    "i", "we", "you", "he", "she", "they", "them", "his", "her", "our",
    "your", "this", "that", "these", "those", "what", "which", "who",
    "whom", "also", "like", "well", "back", "even", "still", "way",
    # Domain noise -- appear everywhere, carry no concept signal
    "file", "path", "note", "notes", "line", "lines", "found", "see",
    "used", "using", "make", "made", "need", "done", "says", "said",
    "true", "false", "none", "null", "data", "text", "list", "item",
    "type", "name", "work", "working", "result", "results", "output",
})


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConceptNode(BaseModel):
    """A concept in the temporal graph."""

    term: str
    first_seen: datetime
    last_seen: datetime
    frequency: int
    sources: list[str] = Field(default_factory=list)


class ConceptEdge(BaseModel):
    """Co-occurrence edge between two concepts."""

    term_a: str
    term_b: str
    weight: int
    first_co_occurrence: datetime
    last_co_occurrence: datetime


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS concepts (
    term TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS concept_sources (
    term TEXT NOT NULL,
    source TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    UNIQUE(term, source)
);
CREATE INDEX IF NOT EXISTS idx_cs_term ON concept_sources(term);
CREATE INDEX IF NOT EXISTS idx_cs_seen ON concept_sources(seen_at);
CREATE TABLE IF NOT EXISTS co_occurrences (
    term_a TEXT NOT NULL,
    term_b TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 0,
    first_co TEXT NOT NULL,
    last_co TEXT NOT NULL,
    PRIMARY KEY (term_a, term_b)
);
CREATE INDEX IF NOT EXISTS idx_co_weight ON co_occurrences(weight DESC);
CREATE INDEX IF NOT EXISTS idx_co_last ON co_occurrences(last_co);
"""


# ---------------------------------------------------------------------------
# Core graph
# ---------------------------------------------------------------------------

class TemporalKnowledgeGraph:
    """Tracks concept appearance, development, and connection over time.

    Uses SQLite for persistence at ``~/.dharma/db/temporal_graph.db``.

    Tables:
        concepts       -- term (PK), first_seen, last_seen, frequency
        concept_sources -- term, source (file path), seen_at
        co_occurrences -- (term_a, term_b) PK, weight, first_co, last_co
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path.home() / ".dharma" / "db" / "temporal_graph.db")
        self._init_db()

    # -- Setup ---------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """Return a connection with row_factory set."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # -- Concept extraction --------------------------------------------------

    def _extract_concepts(self, text: str, min_length: int = 4) -> list[str]:
        """Extract meaningful concept terms from text.

        Captures both single words and compound terms connected by underscores
        or hyphens (e.g. ``activation_patching``, ``value-space``).

        Args:
            text: Raw note content.
            min_length: Minimum character length for a term to qualify.

        Returns:
            Deduplicated list of lowercase concept terms.
        """
        # First pass: find compound terms (underscore/hyphen connected)
        compound_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9]*(?:[_-][a-zA-Z][a-zA-Z0-9]*)+")
        compounds = {m.group().lower().replace("-", "_") for m in compound_pattern.finditer(text)}

        # Second pass: single words (alphanumeric, no surrounding underscores)
        word_pattern = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*\b")
        singles = {m.group().lower() for m in word_pattern.finditer(text)}

        # Merge, filter by length and stopwords
        all_terms = compounds | singles
        return sorted(
            t for t in all_terms
            if len(t) >= min_length and t not in _STOPWORDS
        )

    # -- Ingestion -----------------------------------------------------------

    def ingest_note(self, path: Path, content: str | None = None) -> int:
        """Ingest a single note file into the graph.

        Extracts concepts, updates frequencies, records co-occurrences.

        Args:
            path: Path to the note file.
            content: Optional pre-read content (avoids re-reading).

        Returns:
            Number of concepts found in the note.
        """
        path = Path(path)
        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", path, exc)
                return 0

        concepts = self._extract_concepts(content)
        if not concepts:
            return 0

        # Timestamp from file mtime, falling back to now
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            mtime = _utc_now()

        ts_iso = mtime.isoformat()
        source_str = str(path)

        with self._connect() as conn:
            for term in concepts:
                # Upsert concept
                conn.execute(
                    """INSERT INTO concepts (term, first_seen, last_seen, frequency)
                       VALUES (?, ?, ?, 1)
                       ON CONFLICT(term) DO UPDATE SET
                           last_seen = MAX(last_seen, excluded.last_seen),
                           first_seen = MIN(first_seen, excluded.first_seen),
                           frequency = frequency + 1""",
                    (term, ts_iso, ts_iso),
                )
                # Record source
                conn.execute(
                    """INSERT INTO concept_sources (term, source, seen_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(term, source) DO UPDATE SET
                           seen_at = MAX(seen_at, excluded.seen_at)""",
                    (term, source_str, ts_iso),
                )

            # Co-occurrence edges: all pairs, canonical ordering (a < b)
            for a, b in itertools.combinations(concepts, 2):
                ta, tb = (a, b) if a < b else (b, a)
                conn.execute(
                    """INSERT INTO co_occurrences (term_a, term_b, weight, first_co, last_co)
                       VALUES (?, ?, 1, ?, ?)
                       ON CONFLICT(term_a, term_b) DO UPDATE SET
                           weight = weight + 1,
                           first_co = MIN(first_co, excluded.first_co),
                           last_co = MAX(last_co, excluded.last_co)""",
                    (ta, tb, ts_iso, ts_iso),
                )

        return len(concepts)

    def build_from_notes(self, notes_dir: Path | None = None) -> dict[str, int]:
        """Build/update graph from all shared notes.

        Default directory: ``~/.dharma/shared/``

        Returns:
            Dict with ``notes_processed``, ``concepts_found``, ``edges_created``.
        """
        notes_dir = notes_dir or (Path.home() / ".dharma" / "shared")
        if not notes_dir.is_dir():
            logger.info("Notes directory %s does not exist, nothing to build.", notes_dir)
            return {"notes_processed": 0, "concepts_found": 0, "edges_created": 0}

        note_files = sorted(notes_dir.glob("*.md"))
        total_concepts = 0
        for nf in note_files:
            total_concepts += self.ingest_note(nf)

        # Count totals from DB
        with self._connect() as conn:
            concept_count = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM co_occurrences").fetchone()[0]

        logger.info(
            "Built graph: %d notes, %d concepts, %d edges",
            len(note_files), concept_count, edge_count,
        )
        return {
            "notes_processed": len(note_files),
            "concepts_found": concept_count,
            "edges_created": edge_count,
        }

    # -- Queries -------------------------------------------------------------

    def lineage(self, concept: str, limit: int = 20) -> list[dict]:
        """Trace the lineage of a concept through time.

        Args:
            concept: The term to trace.
            limit: Maximum number of source entries to return.

        Returns:
            List of ``{source, seen_at}`` dicts ordered chronologically.
        """
        concept = concept.lower().replace("-", "_")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT source, seen_at FROM concept_sources
                   WHERE term = ?
                   ORDER BY seen_at ASC
                   LIMIT ?""",
                (concept, limit),
            ).fetchall()
        return [{"source": r["source"], "seen_at": r["seen_at"]} for r in rows]

    def co_occurring(self, concept: str, limit: int = 10) -> list[dict]:
        """Find concepts that frequently co-occur with the given concept.

        Args:
            concept: The term to find co-occurrences for.
            limit: Maximum number of results.

        Returns:
            List of ``{term, weight, first_co, last_co}`` ordered by weight desc.
        """
        concept = concept.lower().replace("-", "_")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT
                       CASE WHEN term_a = ? THEN term_b ELSE term_a END AS partner,
                       weight, first_co, last_co
                   FROM co_occurrences
                   WHERE term_a = ? OR term_b = ?
                   ORDER BY weight DESC
                   LIMIT ?""",
                (concept, concept, concept, limit),
            ).fetchall()
        return [
            {
                "term": r["partner"],
                "weight": r["weight"],
                "first_co": r["first_co"],
                "last_co": r["last_co"],
            }
            for r in rows
        ]

    def emerging(self, window_days: int = 7, min_freq: int = 2) -> list[ConceptNode]:
        """Find concepts that appeared or accelerated recently.

        A concept is *emerging* if its ``first_seen`` is within
        ``window_days`` of now and it has at least ``min_freq`` mentions.

        Args:
            window_days: Lookback window in days.
            min_freq: Minimum frequency to qualify.

        Returns:
            List of :class:`ConceptNode` sorted by frequency descending.
        """
        cutoff = (_utc_now() - timedelta(days=window_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.term, c.first_seen, c.last_seen, c.frequency
                   FROM concepts c
                   WHERE c.first_seen >= ? AND c.frequency >= ?
                   ORDER BY c.frequency DESC""",
                (cutoff, min_freq),
            ).fetchall()

        results: list[ConceptNode] = []
        for r in rows:
            sources = self._sources_for(r["term"])
            results.append(ConceptNode(
                term=r["term"],
                first_seen=datetime.fromisoformat(r["first_seen"]),
                last_seen=datetime.fromisoformat(r["last_seen"]),
                frequency=r["frequency"],
                sources=sources,
            ))
        return results

    def decaying(self, window_days: int = 14, min_historical_freq: int = 3) -> list[ConceptNode]:
        """Find concepts that were active but have not appeared recently.

        A concept is *decaying* if its ``last_seen`` is older than
        ``window_days`` ago and its historical ``frequency`` meets the
        minimum threshold.

        Args:
            window_days: How many days of silence qualifies as decay.
            min_historical_freq: Minimum past frequency (filters noise).

        Returns:
            List of :class:`ConceptNode` sorted by frequency descending.
        """
        cutoff = (_utc_now() - timedelta(days=window_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.term, c.first_seen, c.last_seen, c.frequency
                   FROM concepts c
                   WHERE c.last_seen < ? AND c.frequency >= ?
                   ORDER BY c.frequency DESC""",
                (cutoff, min_historical_freq),
            ).fetchall()

        results: list[ConceptNode] = []
        for r in rows:
            sources = self._sources_for(r["term"])
            results.append(ConceptNode(
                term=r["term"],
                first_seen=datetime.fromisoformat(r["first_seen"]),
                last_seen=datetime.fromisoformat(r["last_seen"]),
                frequency=r["frequency"],
                sources=sources,
            ))
        return results

    def hot_pairs(self, window_days: int = 7, limit: int = 10) -> list[ConceptEdge]:
        """Find the most active concept pairs in the recent window.

        Args:
            window_days: Lookback window in days.
            limit: Maximum number of pairs to return.

        Returns:
            List of :class:`ConceptEdge` sorted by weight descending.
        """
        cutoff = (_utc_now() - timedelta(days=window_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT term_a, term_b, weight, first_co, last_co
                   FROM co_occurrences
                   WHERE last_co >= ?
                   ORDER BY weight DESC
                   LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [
            ConceptEdge(
                term_a=r["term_a"],
                term_b=r["term_b"],
                weight=r["weight"],
                first_co_occurrence=datetime.fromisoformat(r["first_co"]),
                last_co_occurrence=datetime.fromisoformat(r["last_co"]),
            )
            for r in rows
        ]

    def summary(self) -> str:
        """Human-readable summary of the knowledge graph state."""
        with self._connect() as conn:
            n_concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
            n_edges = conn.execute("SELECT COUNT(*) FROM co_occurrences").fetchone()[0]
            n_sources = conn.execute(
                "SELECT COUNT(DISTINCT source) FROM concept_sources"
            ).fetchone()[0]

            top_concepts = conn.execute(
                "SELECT term, frequency FROM concepts ORDER BY frequency DESC LIMIT 5"
            ).fetchall()

            top_edges = conn.execute(
                "SELECT term_a, term_b, weight FROM co_occurrences ORDER BY weight DESC LIMIT 5"
            ).fetchall()

        lines = [
            f"Temporal Knowledge Graph: {n_concepts} concepts, {n_edges} edges, {n_sources} sources",
            "",
            "Top concepts by frequency:",
        ]
        for r in top_concepts:
            lines.append(f"  {r['term']}: {r['frequency']}")

        lines.append("")
        lines.append("Strongest co-occurrences:")
        for r in top_edges:
            lines.append(f"  {r['term_a']} + {r['term_b']}: {r['weight']}")

        return "\n".join(lines)

    # -- Internal helpers ----------------------------------------------------

    def _sources_for(self, term: str) -> list[str]:
        """Return distinct source paths for a concept term."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source FROM concept_sources WHERE term = ?",
                (term,),
            ).fetchall()
        return [r["source"] for r in rows]
