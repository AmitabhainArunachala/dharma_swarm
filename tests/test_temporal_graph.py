"""Tests for dharma_swarm.temporal_graph -- TemporalKnowledgeGraph."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.temporal_graph import (
    ConceptEdge,
    ConceptNode,
    TemporalKnowledgeGraph,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """Return a fresh temporary path for the temporal graph SQLite DB."""
    return tmp_path / "db" / "temporal_graph.db"


@pytest.fixture
def graph(db_file: Path) -> TemporalKnowledgeGraph:
    """Return a TemporalKnowledgeGraph pointed at the temporary DB."""
    return TemporalKnowledgeGraph(db_path=db_file)


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    """Create and return a temporary notes directory."""
    d = tmp_path / "notes"
    d.mkdir()
    return d


def _write_note(notes_dir: Path, name: str, content: str) -> Path:
    """Write a markdown note file and return its path."""
    fpath = notes_dir / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# test_ingest_note_creates_concepts
# ---------------------------------------------------------------------------


def test_ingest_note_creates_concepts(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Ingest a note, verify concepts appear in the DB."""
    note_path = tmp_path / "test_note.md"
    note_path.write_text(
        "The participation_ratio measures geometric contraction in the "
        "transformer value_space. Activation patching validates the causal "
        "mechanism at layer twenty seven.",
        encoding="utf-8",
    )

    count = graph.ingest_note(note_path)
    assert count > 0

    # Verify some expected concepts appear in lineage queries
    lineage = graph.lineage("participation_ratio")
    assert len(lineage) >= 1
    assert str(note_path) in lineage[0]["source"]


def test_ingest_note_with_content(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Ingest a note with pre-read content string."""
    note_path = tmp_path / "preread.md"
    note_path.write_text("placeholder", encoding="utf-8")

    content = "activation_patching causal_validation geometric_signature"
    count = graph.ingest_note(note_path, content=content)
    assert count > 0


# ---------------------------------------------------------------------------
# test_co_occurrences_created
# ---------------------------------------------------------------------------


def test_co_occurrences_created(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Ingest a note with multiple concepts, verify co-occurrence edges exist."""
    note_path = tmp_path / "cooccur.md"
    note_path.write_text(
        "The participation_ratio and geometric_contraction are both "
        "measured during activation_patching experiments.",
        encoding="utf-8",
    )

    count = graph.ingest_note(note_path)
    assert count >= 3

    # Check co-occurrences for one of the concepts
    cooc = graph.co_occurring("participation_ratio")
    # Should have at least one co-occurring partner
    assert len(cooc) >= 1
    partner_terms = [c["term"] for c in cooc]
    # geometric_contraction should co-occur with participation_ratio
    assert "geometric_contraction" in partner_terms or "activation_patching" in partner_terms


# ---------------------------------------------------------------------------
# test_lineage_returns_history
# ---------------------------------------------------------------------------


def test_lineage_returns_history(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Ingest same concept in multiple notes, verify lineage tracks all."""
    for i in range(3):
        note_path = tmp_path / f"note_{i}.md"
        note_path.write_text(
            f"The participation_ratio shows contraction in experiment {i}. "
            f"Measurement run number {i} completed successfully.",
            encoding="utf-8",
        )
        graph.ingest_note(note_path)

    lineage = graph.lineage("participation_ratio")
    assert len(lineage) == 3
    sources = [entry["source"] for entry in lineage]
    # All 3 notes should be in sources
    for i in range(3):
        assert any(f"note_{i}.md" in s for s in sources)


# ---------------------------------------------------------------------------
# test_emerging_detects_new_concepts
# ---------------------------------------------------------------------------


def test_emerging_detects_new_concepts(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Ingest a recent note, verify its concepts show as emerging."""
    note_path = tmp_path / "recent.md"
    note_path.write_text(
        "The quantum_coherence phenomenon shows entanglement_signature "
        "across multiple measurement runs. quantum_coherence is validated.",
        encoding="utf-8",
    )
    graph.ingest_note(note_path)

    # Ingest again with different source to reach min_freq=2
    note_path2 = tmp_path / "recent2.md"
    note_path2.write_text(
        "quantum_coherence shows strong entanglement_signature again.",
        encoding="utf-8",
    )
    graph.ingest_note(note_path2)

    emerging = graph.emerging(window_days=7, min_freq=2)
    emerging_terms = [c.term for c in emerging]
    assert "quantum_coherence" in emerging_terms


# ---------------------------------------------------------------------------
# test_decaying_detects_old_concepts
# ---------------------------------------------------------------------------


def test_decaying_detects_old_concepts(graph: TemporalKnowledgeGraph, db_file: Path):
    """Create concept with old timestamp, verify it shows as decaying."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    # Directly insert an old concept into the DB
    import sqlite3
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO concepts (term, first_seen, last_seen, frequency) "
        "VALUES (?, ?, ?, ?)",
        ("deprecated_metric", old_time, old_time, 5),
    )
    conn.commit()
    conn.close()

    decaying = graph.decaying(window_days=14, min_historical_freq=3)
    decaying_terms = [c.term for c in decaying]
    assert "deprecated_metric" in decaying_terms


# ---------------------------------------------------------------------------
# test_build_from_notes_processes_all
# ---------------------------------------------------------------------------


def test_build_from_notes_processes_all(
    graph: TemporalKnowledgeGraph, notes_dir: Path
):
    """Create directory with multiple note files, build, verify counts."""
    _write_note(
        notes_dir,
        "alpha.md",
        "Participation_ratio contraction measurement geometric signature.",
    )
    _write_note(
        notes_dir,
        "beta.md",
        "Activation_patching layer_analysis causal_validation mechanism.",
    )
    _write_note(
        notes_dir,
        "gamma.md",
        "Behavioral_transfer dimensional_collapse value_space analysis.",
    )

    result = graph.build_from_notes(notes_dir)
    assert result["notes_processed"] == 3
    assert result["concepts_found"] > 0
    assert result["edges_created"] > 0


def test_build_from_notes_nonexistent_dir(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Build from a non-existent directory should return zero counts."""
    result = graph.build_from_notes(tmp_path / "nonexistent")
    assert result["notes_processed"] == 0
    assert result["concepts_found"] == 0
    assert result["edges_created"] == 0


# ---------------------------------------------------------------------------
# test_hot_pairs_returns_recent
# ---------------------------------------------------------------------------


def test_hot_pairs_returns_recent(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Verify hot_pairs respects time window and returns recent pairs."""
    note_path = tmp_path / "hot_note.md"
    note_path.write_text(
        "The participation_ratio and geometric_contraction are strongly "
        "correlated in the activation_patching experiments.",
        encoding="utf-8",
    )
    graph.ingest_note(note_path)

    pairs = graph.hot_pairs(window_days=7, limit=10)
    assert isinstance(pairs, list)
    assert len(pairs) > 0
    for pair in pairs:
        assert isinstance(pair, ConceptEdge)
        assert pair.weight >= 1
        assert pair.term_a < pair.term_b  # canonical ordering


def test_hot_pairs_old_data_excluded(graph: TemporalKnowledgeGraph, db_file: Path):
    """Pairs whose last_co is older than the window should be excluded."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    import sqlite3
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO co_occurrences (term_a, term_b, weight, first_co, last_co) "
        "VALUES (?, ?, ?, ?, ?)",
        ("ancient_a", "ancient_b", 10, old_time, old_time),
    )
    conn.commit()
    conn.close()

    pairs = graph.hot_pairs(window_days=7, limit=10)
    pair_terms = [(p.term_a, p.term_b) for p in pairs]
    assert ("ancient_a", "ancient_b") not in pair_terms


# ---------------------------------------------------------------------------
# test_summary_format
# ---------------------------------------------------------------------------


def test_summary_format(graph: TemporalKnowledgeGraph, tmp_path: Path):
    """Verify summary() returns a meaningful string."""
    note_path = tmp_path / "summary_note.md"
    note_path.write_text(
        "Geometric_contraction participation_ratio value_space "
        "activation_patching layer_analysis mechanism experiment.",
        encoding="utf-8",
    )
    graph.ingest_note(note_path)

    summary = graph.summary()
    assert isinstance(summary, str)
    assert "Temporal Knowledge Graph" in summary
    assert "concepts" in summary
    assert "edges" in summary
    assert "sources" in summary


def test_summary_empty_graph(graph: TemporalKnowledgeGraph):
    """Summary on empty graph should still produce valid string."""
    summary = graph.summary()
    assert isinstance(summary, str)
    assert "0 concepts" in summary
    assert "0 edges" in summary


# ---------------------------------------------------------------------------
# Concept extraction
# ---------------------------------------------------------------------------


def test_extract_concepts_finds_compounds(graph: TemporalKnowledgeGraph):
    """Compound terms connected by underscores/hyphens are extracted."""
    concepts = graph._extract_concepts("activation_patching value-space layer_analysis")
    assert "activation_patching" in concepts
    assert "value_space" in concepts
    assert "layer_analysis" in concepts


def test_extract_concepts_filters_short(graph: TemporalKnowledgeGraph):
    """Terms shorter than min_length are filtered out."""
    concepts = graph._extract_concepts("a an the to in for and of")
    assert len(concepts) == 0


def test_extract_concepts_filters_stopwords(graph: TemporalKnowledgeGraph):
    """Stopwords are filtered even if long enough."""
    concepts = graph._extract_concepts("through during before after between")
    assert len(concepts) == 0
