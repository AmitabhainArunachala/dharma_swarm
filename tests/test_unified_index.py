"""Tests for dharma_swarm.engine.unified_index and chunker."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.engine.chunker import chunk_markdown
from dharma_swarm.engine.unified_index import UnifiedIndex


def test_chunk_markdown_preserves_header_metadata() -> None:
    text = """# Root

Intro paragraph.

## Child

Second paragraph with specific detail.
"""
    chunks = chunk_markdown(text, max_words=20)
    assert len(chunks) == 2
    assert chunks[0].metadata["header_path"] == ["Root"]
    assert chunks[1].metadata["header_path"] == ["Root", "Child"]


def test_index_document_is_incremental_for_unchanged_source(tmp_path: Path) -> None:
    index = UnifiedIndex(tmp_path / "memory_plane.db")
    doc_id_1 = index.index_document(
        "note",
        "notes/example.md",
        "# Header\n\nHello world.\n",
        {"topic": "example"},
    )
    first_stats = index.stats()
    doc_id_2 = index.index_document(
        "note",
        "notes/example.md",
        "# Header\n\nHello world.\n",
        {"topic": "example"},
    )
    second_stats = index.stats()

    assert doc_id_1 == doc_id_2
    assert first_stats == second_stats


def test_index_note_file_and_search_returns_chunk_metadata(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text(
        "---\n"
        "topic: memory\n"
        "---\n"
        "# Retrieval\n\n"
        "BGE-M3 and BM25 make memory retrieval stronger.\n"
    )
    index = UnifiedIndex(tmp_path / "memory_plane.db")
    index.index_note_file(note)

    results = index.search("BM25 retrieval", limit=5)
    assert len(results) == 1
    record, score = results[0]
    assert score > 0
    assert record.metadata["source_kind"] == "note"
    assert record.metadata["source_path"] == str(note)
    assert record.metadata["header_path"] == ["Retrieval"]
    assert record.metadata["topic"] == "memory"


def test_reindex_changed_writes_run_stats(tmp_path: Path) -> None:
    note_a = tmp_path / "a.md"
    note_b = tmp_path / "b.md"
    note_a.write_text("# A\n\nalpha memory\n")
    note_b.write_text("# B\n\nbeta memory\n")

    index = UnifiedIndex(tmp_path / "memory_plane.db")
    stats = index.reindex_changed([note_a, note_b])

    assert stats["indexed"] == 2
    assert stats["errors"] == 0
    db_stats = index.stats()
    assert db_stats["index_runs"] == 1
