"""Tests for Memory Palace integration layer."""

import pytest
from dharma_swarm.memory_palace import (
    MemoryPalace,
    PalaceQuery,
    PalaceResponse,
    PalaceResult,
)


class TestMemoryPalaceNoLattice:
    """Tests that work without a real MemoryLattice."""

    def test_recall_returns_empty_without_lattice(self):
        palace = MemoryPalace()
        import asyncio
        resp = asyncio.run(palace.recall(PalaceQuery(text="test query")))
        assert isinstance(resp, PalaceResponse)
        assert resp.results == []
        assert resp.duration_ms > 0
        assert resp.query_text == "test query"

    def test_ingest_returns_empty_without_lattice(self):
        palace = MemoryPalace()
        import asyncio
        doc_id = asyncio.run(palace.ingest("some content", "test_source"))
        assert doc_id == ""

    def test_stats_empty(self):
        palace = MemoryPalace()
        s = palace.stats()
        assert s["queries_served"] == 0
        assert s["avg_latency_ms"] == 0

    def test_query_history_tracked(self):
        palace = MemoryPalace()
        import asyncio
        asyncio.run(palace.recall(PalaceQuery(text="q1")))
        asyncio.run(palace.recall(PalaceQuery(text="q2")))
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
        # All scores should be between 0 and 1.5 (sum of weights + bonuses)
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
