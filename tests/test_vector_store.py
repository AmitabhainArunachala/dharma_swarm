"""Tests for VectorStore — Phase 6 hard memory infrastructure.

Tests cover:
    - TFIDFEmbedder: fit, embed, persistence, fallback
    - VectorStore: upsert, search_vector, search_fts, search_hybrid
    - Bi-temporal fields: event_time, ingestion_time
    - Confidence decay: age-based exponential decay
    - Access tracking: access_count, last_accessed
    - Edge invalidation: soft-delete via valid_until
    - Garbage collection: removal below confidence threshold
    - Stats reporting
"""

import asyncio
import struct
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# TFIDFEmbedder tests
# ---------------------------------------------------------------------------

class TestTFIDFEmbedder:

    def test_embed_produces_vectors(self, tmp_path):
        from dharma_swarm.vector_store import TFIDFEmbedder
        emb = TFIDFEmbedder(dim=32, state_path=tmp_path / "emb.pkl")
        texts = [
            "The organism heartbeat is running well",
            "Agent viability scores are dropping",
            "Memory palace recall latency increased",
        ]
        vecs = emb.embed(texts)
        assert len(vecs) == 3
        for v in vecs:
            assert len(v) == 32
            # Vectors should be L2-normalized (magnitude ≈ 1.0)
            magnitude = sum(x * x for x in v) ** 0.5
            assert abs(magnitude - 1.0) < 0.1 or magnitude == 0.0

    def test_embed_empty_list(self, tmp_path):
        from dharma_swarm.vector_store import TFIDFEmbedder
        emb = TFIDFEmbedder(dim=16)
        assert emb.embed([]) == []

    def test_dim_property(self, tmp_path):
        from dharma_swarm.vector_store import TFIDFEmbedder
        emb = TFIDFEmbedder(dim=64)
        assert emb.dim == 64

    def test_fit_add_expands_vocabulary(self, tmp_path):
        pytest.importorskip("sklearn", reason="scikit-learn not installed")
        from dharma_swarm.vector_store import TFIDFEmbedder
        emb = TFIDFEmbedder(dim=16, state_path=tmp_path / "emb.pkl")
        # Initial fit
        emb.fit_add(["hello world", "foo bar baz"])
        assert emb._fitted
        # Expand
        emb.fit_add(["quantum computing research", "neural network training"])
        # Should still produce valid vectors
        vecs = emb.embed(["quantum computing"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 16

    def test_persistence_round_trip(self, tmp_path):
        pytest.importorskip("sklearn", reason="scikit-learn not installed")
        from dharma_swarm.vector_store import TFIDFEmbedder
        path = tmp_path / "emb.pkl"
        emb1 = TFIDFEmbedder(dim=32, state_path=path)
        emb1.fit_add(["alpha beta gamma", "delta epsilon zeta"])
        vecs1 = emb1.embed(["alpha beta"])

        # Create a new embedder from the same path
        emb2 = TFIDFEmbedder(dim=32, state_path=path)
        assert emb2._fitted
        vecs2 = emb2.embed(["alpha beta"])
        # Vectors should be identical since state was loaded
        for a, b in zip(vecs1[0], vecs2[0]):
            assert abs(a - b) < 1e-6

    def test_single_word_corpus(self, tmp_path):
        """Edge case: single-word corpus should not crash."""
        from dharma_swarm.vector_store import TFIDFEmbedder
        emb = TFIDFEmbedder(dim=16)
        vecs = emb.embed(["hello"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 16


# ---------------------------------------------------------------------------
# VectorStore core tests
# ---------------------------------------------------------------------------

class TestVectorStoreUpsert:

    def test_upsert_returns_positive_id(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("The organism is healthy", source="heartbeat")
        assert doc_id > 0

    def test_upsert_empty_content_returns_negative(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        assert store.upsert("") == -1
        assert store.upsert("   ") == -1

    def test_upsert_stores_metadata(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert(
            "Agent performance is good",
            source="vsm",
            layer="consolidated",
            metadata={"agent_id": "researcher_01", "score": 0.95},
        )
        doc = store.get_document(doc_id)
        assert doc is not None
        assert doc["source"] == "vsm"
        assert doc["layer"] == "consolidated"
        assert doc["metadata"]["agent_id"] == "researcher_01"

    def test_upsert_bi_temporal_fields(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        event_dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        doc_id = store.upsert(
            "Historical event data",
            source="import",
            event_time=event_dt,
        )
        doc = store.get_document(doc_id)
        assert doc is not None
        # event_time should be the provided date
        assert "2025-06-15" in doc["event_time"]
        # ingestion_time should be recent (today)
        assert doc["ingestion_time"] is not None
        # They should be different (event in past, ingestion now)
        assert doc["event_time"] != doc["ingestion_time"]

    def test_upsert_default_confidence_is_one(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Fresh knowledge", source="test")
        doc = store.get_document(doc_id)
        assert doc["confidence"] == 1.0

    def test_upsert_initial_access_count_zero(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Fresh knowledge", source="test")
        doc = store.get_document(doc_id)
        assert doc["access_count"] == 0
        assert doc["last_accessed"] is None


# ---------------------------------------------------------------------------
# VectorStore search tests
# ---------------------------------------------------------------------------

class TestVectorStoreSearch:

    def _seed_store(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        store.upsert("The organism heartbeat is running normally", source="heartbeat")
        store.upsert("Agent viability scores have dropped below threshold", source="vsm")
        store.upsert("Memory palace recall latency has increased significantly", source="palace")
        store.upsert("Evolution cycle found a better mutation strategy", source="evolution")
        store.upsert("Algedonic pain signal detected in production fleet", source="algedonic")
        return store

    def test_search_vector_returns_results(self, tmp_path):
        store = self._seed_store(tmp_path)
        results = store.search_vector("heartbeat organism health", top_k=3)
        assert len(results) > 0
        assert len(results) <= 3
        for r in results:
            assert "content" in r
            assert "id" in r
            assert "distance" in r

    def test_search_fts_returns_results(self, tmp_path):
        store = self._seed_store(tmp_path)
        results = store.search_fts("organism heartbeat", top_k=3)
        assert len(results) > 0
        # FTS should find the heartbeat document
        contents = [r["content"] for r in results]
        assert any("heartbeat" in c for c in contents)

    def test_search_hybrid_returns_scored_results(self, tmp_path):
        store = self._seed_store(tmp_path)
        results = store.search_hybrid("organism heartbeat running", top_k=3)
        assert len(results) > 0
        # Hybrid results should have a 'score' field
        for r in results:
            assert "score" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_search_hybrid_fuses_both_channels(self, tmp_path):
        store = self._seed_store(tmp_path)
        results = store.search_hybrid(
            "algedonic pain signal",
            top_k=5,
            vector_weight=0.5,
            fts_weight=0.5,
        )
        assert len(results) > 0
        # The algedonic document should rank well
        contents = [r["content"] for r in results]
        assert any("algedonic" in c.lower() for c in contents)

    def test_search_empty_query_returns_empty(self, tmp_path):
        store = self._seed_store(tmp_path)
        assert store.search_vector("") == []
        assert store.search_fts("") == []
        assert store.search_hybrid("") == []
        assert store.search_vector("   ") == []

    def test_search_updates_access_tracking(self, tmp_path):
        store = self._seed_store(tmp_path)
        results = store.search_vector("heartbeat", top_k=2)
        if results:
            doc = store.get_document(results[0]["id"])
            assert doc["access_count"] >= 1
            assert doc["last_accessed"] is not None


# ---------------------------------------------------------------------------
# Invalidation tests
# ---------------------------------------------------------------------------

class TestVectorStoreInvalidation:

    def test_invalidate_sets_valid_until(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Soon to be invalidated", source="test")
        assert store.invalidate(doc_id, reason="superseded")
        doc = store.get_document(doc_id)
        assert doc["valid_until"] is not None
        assert "superseded" in str(doc["metadata"].get("invalidated_reason", ""))

    def test_invalidated_docs_excluded_from_search(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Unique canary string xyzzy", source="test")
        store.upsert("Another document for context padding", source="test")
        store.upsert("Yet another document for the corpus", source="test")
        store.invalidate(doc_id, reason="test")
        results = store.search_fts("xyzzy", top_k=10)
        found_ids = [r["id"] for r in results]
        assert doc_id not in found_ids

    def test_invalidated_docs_visible_with_include_invalid(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Invalidated but still visible", source="test")
        store.upsert("Padding doc one for the corpus context", source="test")
        store.upsert("Padding doc two for the corpus context", source="test")
        store.invalidate(doc_id, reason="test")
        results = store.search_fts("invalidated visible", top_k=10, include_invalid=True)
        found_ids = [r["id"] for r in results]
        assert doc_id in found_ids


# ---------------------------------------------------------------------------
# Confidence decay tests
# ---------------------------------------------------------------------------

class TestVectorStoreDecay:

    def test_decay_reduces_confidence(self, tmp_path):
        pytest.importorskip("sqlite_vec", reason="sqlite_vec not installed")
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Decaying knowledge item", source="test")
        # Force the ingestion_time to be 10 days ago
        import sqlite3, sqlite_vec
        conn = sqlite3.connect(str(tmp_path / "vectors.db"))
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        conn.execute("UPDATE vec_documents SET ingestion_time = ? WHERE id = ?", (old_time, doc_id))
        conn.commit()
        conn.close()

        updated = store.decay_confidence(max_age_days=30, decay_rate=0.95)
        assert updated >= 1
        doc = store.get_document(doc_id)
        # After 10 days with 0.95 rate: 1.0 * 0.95^10 ≈ 0.5987
        assert doc["confidence"] < 1.0
        assert doc["confidence"] > 0.0

    def test_decay_skips_invalidated(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Will be invalidated", source="test")
        store.invalidate(doc_id)
        updated = store.decay_confidence()
        # Invalidated docs should not be decayed
        assert updated == 0


# ---------------------------------------------------------------------------
# Garbage collection tests
# ---------------------------------------------------------------------------

class TestVectorStoreGC:

    def test_gc_removes_low_confidence(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("Very low confidence item", source="test")
        # Manually set confidence very low using store's own connection
        conn = store._connect()
        conn.execute("UPDATE vec_documents SET confidence = 0.001 WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

        removed = store.gc(min_confidence=0.01)
        assert removed >= 1
        # Document should be gone
        doc = store.get_document(doc_id)
        assert doc is None

    def test_gc_preserves_high_confidence(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        doc_id = store.upsert("High confidence item", source="test")
        removed = store.gc(min_confidence=0.01)
        assert removed == 0
        doc = store.get_document(doc_id)
        assert doc is not None


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestVectorStoreStats:

    def test_stats_empty_store(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        s = store.stats()
        assert s["total_documents"] == 0
        assert s["valid_documents"] == 0
        assert s["embedder_dim"] == 32

    def test_stats_after_inserts(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        store.upsert("doc one", source="a")
        store.upsert("doc two", source="b")
        store.upsert("doc three", source="c", layer="consolidated")
        s = store.stats()
        assert s["total_documents"] == 3
        assert s["valid_documents"] == 3
        assert s["avg_confidence"] == 1.0
        assert "working" in s["by_layer"]

    def test_stats_reflects_invalidation(self, tmp_path):
        from dharma_swarm.vector_store import VectorStore
        store = VectorStore(state_dir=tmp_path, dim=32)
        id1 = store.upsert("valid doc", source="a")
        id2 = store.upsert("invalid doc", source="b")
        store.invalidate(id2)
        s = store.stats()
        assert s["total_documents"] == 2
        assert s["valid_documents"] == 1
        assert s["invalidated_documents"] == 1
