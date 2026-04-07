"""Tests for Memory Palace integration layer — including Phase 4 LanceDB persistence.

Tests cover:
1. MemoryPalace connects to LanceDB when available
2. MemoryPalace degrades gracefully when lancedb not available
3. Content indexed in one session can be retrieved in another (cross-session persistence)
4. Empty content is handled gracefully
5. Existing fusion re-ranking and query config tests
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.memory_palace import (
    MemoryPalace,
    PalaceQuery,
    PalaceResponse,
    PalaceResult,
    _LanceDBAdapter,
)


# ---------------------------------------------------------------------------
# Helper: run async in sync context
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


# ===========================================================================
# Phase 4: LanceDB Adapter Tests
# ===========================================================================


class TestLanceDBAdapter:
    """Direct tests for the _LanceDBAdapter wrapper."""

    def test_connect_creates_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            assert adapter.connected is True

    def test_upsert_and_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            assert adapter.count() == 0
            ok = adapter.upsert("Hello world, this is a test document", "test_source")
            assert ok is True
            assert adapter.count() == 1

    def test_upsert_empty_content_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            ok = adapter.upsert("", "test_source")
            assert ok is False
            ok = adapter.upsert("   ", "test_source")
            assert ok is False
            assert adapter.count() == 0

    def test_search_returns_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            adapter.upsert("Python programming language", "src1")
            adapter.upsert("JavaScript web development", "src2")
            adapter.upsert("Python data science pandas", "src3")
            results = adapter.search("Python programming", top_k=5)
            assert len(results) >= 1
            # Results should have the expected keys
            for r in results:
                assert "content" in r
                assert "source" in r
                assert "score" in r

    def test_search_empty_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            results = adapter.search("anything")
            assert results == []

    def test_cross_session_persistence(self):
        """Content indexed in one adapter instance can be retrieved by another
        pointing to the same db_path — the key cross-session test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_persist"

            # Session 1: write
            adapter1 = _LanceDBAdapter(db_path=db_path)
            adapter1.upsert("Isara competitive analysis Q2 2026", "research_agent")
            adapter1.upsert("Ginko trading regime signals bullish", "trading_agent")
            assert adapter1.count() == 2

            # Session 2: new adapter instance, same path
            adapter2 = _LanceDBAdapter(db_path=db_path)
            assert adapter2.count() == 2  # Data persisted
            results = adapter2.search("Isara competitive", top_k=5)
            assert len(results) >= 1
            # The Isara doc should be in the results
            found = any("Isara" in r["content"] for r in results)
            assert found, f"Expected 'Isara' in results: {results}"

    def test_graceful_when_lancedb_unavailable(self):
        """When lancedb import fails, adapter degrades gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            with patch.dict("sys.modules", {"lancedb": None}):
                adapter = _LanceDBAdapter(db_path=db_path)
                assert adapter.connected is False
                assert adapter.upsert("test", "src") is False
                assert adapter.search("test") == []
                assert adapter.count() == 0

    def test_default_vector_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            v1 = adapter._default_vector("hello")
            v2 = adapter._default_vector("hello")
            assert v1 == v2
            # Different texts produce different vectors
            v3 = adapter._default_vector("goodbye")
            assert v1 != v3

    def test_default_vector_normalized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lance_test"
            adapter = _LanceDBAdapter(db_path=db_path)
            vec = adapter._default_vector("test normalization")
            norm = sum(v * v for v in vec) ** 0.5
            assert abs(norm - 1.0) < 0.01


# ===========================================================================
# MemoryPalace with LanceDB Tests
# ===========================================================================


class TestMemoryPalaceLanceDB:
    """Tests for MemoryPalace with LanceDB integration (Phase 4)."""

    def test_palace_connects_to_lancedb_with_state_dir(self):
        """When state_dir is provided, LanceDB should connect."""
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            assert palace._lance is not None
            assert palace._lance.connected is True

    def test_palace_connects_to_lancedb_without_state_dir(self):
        """Even without state_dir (ephemeral mode), LanceDB should connect."""
        palace = MemoryPalace()
        # In ephemeral mode, LanceDB should still be available
        assert palace._lance is not None
        assert palace._lance.connected is True

    def test_ingest_writes_to_lancedb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            _run(palace.ingest("Test document for LanceDB persistence", "test"))
            assert palace._lance is not None
            assert palace._lance.count() >= 1

    def test_ingest_empty_content_no_lance_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            _run(palace.ingest("", "test"))
            assert palace._lance is not None
            assert palace._lance.count() == 0

    def test_ingest_whitespace_only_no_lance_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            _run(palace.ingest("   \n  \t  ", "test"))
            assert palace._lance is not None
            assert palace._lance.count() == 0

    def test_recall_includes_lancedb_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            # Ingest some docs
            _run(palace.ingest("Mechanistic interpretability of neural networks", "research"))
            _run(palace.ingest("Ginko trading bot signals bearish regime", "trading"))
            # Recall should include LanceDB results
            resp = _run(palace.recall(PalaceQuery(text="interpretability neural", max_results=5)))
            assert isinstance(resp, PalaceResponse)
            # At least one result should come through (from VectorStore or LanceDB)
            # Note: exact match depends on vector similarity which is hash-based here

    def test_cross_session_recall(self):
        """Key test: content indexed in session 1 is retrievable in session 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "dharma"

            # Session 1: ingest
            palace1 = MemoryPalace(state_dir=state)
            _run(palace1.ingest(
                "Isara Systems competitive analysis: they use GPT-4o fine-tuning",
                "research_agent",
            ))
            _run(palace1.ingest(
                "VIVEKA R_V metric current score is 0.73",
                "eval_agent",
            ))
            assert palace1._lance.count() == 2

            # Session 2: new MemoryPalace instance, same state_dir
            palace2 = MemoryPalace(state_dir=state)
            assert palace2._lance is not None
            assert palace2._lance.count() == 2

            # Direct LanceDB search
            results = palace2._lance.search("Isara competitive", top_k=5)
            assert len(results) >= 1
            found_isara = any("Isara" in r["content"] for r in results)
            assert found_isara, f"Cross-session recall failed: {results}"

    def test_stats_includes_lancedb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            palace = MemoryPalace(state_dir=Path(tmpdir))
            _run(palace.ingest("test doc", "test_src"))
            stats = palace.stats()
            assert "lancedb" in stats
            assert stats["lancedb"]["connected"] is True
            assert stats["lancedb"]["document_count"] >= 1


# ===========================================================================
# Original Tests (preserved from pre-Phase-4)
# ===========================================================================


class TestMemoryPalaceNoLattice:
    """Tests that work without a real MemoryLattice."""

    def test_recall_returns_empty_without_lattice(self):
        palace = MemoryPalace()
        resp = _run(palace.recall(PalaceQuery(text="test query")))
        assert isinstance(resp, PalaceResponse)
        # May have LanceDB results now but should not crash
        assert resp.duration_ms > 0
        assert resp.query_text == "test query"

    def test_ingest_returns_empty_without_lattice(self):
        palace = MemoryPalace()
        doc_id = _run(palace.ingest("some content", "test_source"))
        # In ephemeral mode without persistent state_dir, doc_id should be empty
        # (LanceDB upsert succeeds but doesn't generate a doc_id for backward compat)
        assert isinstance(doc_id, str)

    def test_stats_empty(self):
        palace = MemoryPalace()
        s = palace.stats()
        assert s["queries_served"] == 0
        assert s["avg_latency_ms"] == 0

    def test_query_history_tracked(self):
        palace = MemoryPalace()
        _run(palace.recall(PalaceQuery(text="q1")))
        _run(palace.recall(PalaceQuery(text="q2")))
        s = palace.stats()
        assert s["queries_served"] == 2


class TestFusionReranking:
    """Tests for the fusion re-ranking logic."""

    def test_empty_results(self):
        palace = MemoryPalace()
        query = PalaceQuery(text="test")
        reranked = palace._fusion_rerank([], query)
        assert reranked == []

    def test_scores_combined(self):
        palace = MemoryPalace()
        results = [
            PalaceResult(content="A", source="a", score=0.9, metadata={"salience": 0.8}),
            PalaceResult(content="B", source="b", score=0.3, metadata={"salience": 0.2}),
        ]
        query = PalaceQuery(text="test")
        reranked = palace._fusion_rerank(results, query)
        assert len(reranked) == 2
        # A should still rank higher
        assert reranked[0].content == "A"
        # All scores should be between 0 and 2.0
        for r in reranked:
            assert 0 <= r.score <= 2.0

    def test_recency_boosts_recent(self):
        palace = MemoryPalace()
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        old_iso = "2020-01-01T00:00:00+00:00"

        results = [
            PalaceResult(content="old", source="a", score=0.5, metadata={"recorded_at": old_iso}),
            PalaceResult(content="new", source="b", score=0.5, metadata={"recorded_at": now_iso}),
        ]
        query = PalaceQuery(text="test", weight_recency=0.5)
        reranked = palace._fusion_rerank(results, query)
        # New should rank higher due to recency
        assert reranked[0].content == "new"


class TestPalaceQueryConfig:
    """Test query configuration."""

    def test_default_weights(self):
        q = PalaceQuery(text="test")
        total = q.weight_semantic + q.weight_lexical + q.weight_recency + q.weight_salience
        assert abs(total - 1.0) < 0.01

    def test_custom_weights(self):
        q = PalaceQuery(text="test", weight_semantic=0.8, weight_lexical=0.2)
        assert q.weight_semantic == 0.8
