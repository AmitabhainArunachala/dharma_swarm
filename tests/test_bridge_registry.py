"""Tests for bridge_registry.py — cross-graph edge persistence and queries."""

from __future__ import annotations

import pytest

from dharma_swarm.bridge_registry import (
    BridgeEdge,
    BridgeEdgeKind,
    BridgeRegistry,
    GraphOrigin,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def registry(tmp_path):
    r = BridgeRegistry(db_path=tmp_path / "bridges.db")
    await r.init()
    yield r
    await r.close()


def _edge(
    source_graph=GraphOrigin.SEMANTIC,
    source_id="s1",
    target_graph=GraphOrigin.TELOS,
    target_id="t1",
    edge_type=BridgeEdgeKind.IMPLEMENTS_CONCEPT,
    confidence=0.8,
    **kw,
) -> BridgeEdge:
    return BridgeEdge(
        source_graph=source_graph,
        source_id=source_id,
        target_graph=target_graph,
        target_id=target_id,
        edge_type=edge_type,
        confidence=confidence,
        **kw,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_graph_origin_values(self):
        assert GraphOrigin.SEMANTIC.value == "semantic"
        assert GraphOrigin.TELOS.value == "telos"
        assert GraphOrigin.TEMPORAL.value == "temporal"

    def test_bridge_edge_kind_values(self):
        # Just verify a few exist
        assert hasattr(BridgeEdgeKind, "IMPLEMENTS_CONCEPT")
        assert isinstance(BridgeEdgeKind.IMPLEMENTS_CONCEPT.value, str)


# ---------------------------------------------------------------------------
# BridgeEdge model
# ---------------------------------------------------------------------------


class TestBridgeEdge:
    def test_creation(self):
        e = _edge()
        assert e.source_graph == GraphOrigin.SEMANTIC
        assert e.target_graph == GraphOrigin.TELOS
        assert e.confidence == 0.8
        assert e.edge_id  # auto-generated

    def test_serialization(self):
        e = _edge()
        d = e.model_dump()
        assert d["source_graph"] == "semantic"
        assert d["target_graph"] == "telos"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, registry):
        e = _edge()
        await registry.upsert(e)
        found = await registry.get(e.edge_id)
        assert found is not None
        assert found.edge_id == e.edge_id
        assert found.confidence == 0.8

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, registry):
        assert await registry.get("ghost") is None

    @pytest.mark.asyncio
    async def test_upsert_many(self, registry):
        edges = [_edge(source_id=f"s{i}") for i in range(5)]
        count = await registry.upsert_many(edges)
        assert count == 5
        total = await registry.count()
        assert total == 5

    @pytest.mark.asyncio
    async def test_upsert_idempotent(self, registry):
        e = _edge()
        await registry.upsert(e)
        await registry.upsert(e)
        total = await registry.count()
        assert total == 1  # same unique key, upserted

    @pytest.mark.asyncio
    async def test_delete(self, registry):
        e = _edge()
        await registry.upsert(e)
        deleted = await registry.delete(e.edge_id)
        assert deleted is True
        assert await registry.get(e.edge_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, registry):
        deleted = await registry.delete("ghost")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_by_node(self, registry):
        await registry.upsert(_edge(source_id="n1", target_id="a"))
        await registry.upsert(_edge(source_id="n1", target_id="b"))
        await registry.upsert(_edge(source_id="other", target_id="n1"))
        count = await registry.delete_by_node(GraphOrigin.SEMANTIC, "n1")
        assert count >= 2  # at least the two with source_id=n1


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestQueries:
    @pytest.mark.asyncio
    async def test_find_bridges(self, registry):
        await registry.upsert(_edge(source_id="c1", target_id="t1"))
        await registry.upsert(_edge(source_id="c1", target_id="t2"))
        await registry.upsert(_edge(source_id="other", target_id="t3"))

        bridges = await registry.find_bridges(GraphOrigin.SEMANTIC, "c1")
        assert len(bridges) == 2

    @pytest.mark.asyncio
    async def test_find_by_type(self, registry):
        await registry.upsert(_edge(edge_type=BridgeEdgeKind.IMPLEMENTS_CONCEPT, confidence=0.9))
        await registry.upsert(_edge(
            source_id="s2",
            edge_type=BridgeEdgeKind.IMPLEMENTS_CONCEPT,
            confidence=0.3,
        ))

        high_conf = await registry.find_by_type(
            BridgeEdgeKind.IMPLEMENTS_CONCEPT, min_confidence=0.5,
        )
        assert len(high_conf) == 1
        assert high_conf[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_query_across(self, registry):
        await registry.upsert(_edge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="s1",
            target_graph=GraphOrigin.TELOS,
        ))
        await registry.upsert(_edge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="s1",
            target_graph=GraphOrigin.TEMPORAL,
            target_id="temp1",
        ))

        # All from semantic:s1
        all_bridges = await registry.query_across(GraphOrigin.SEMANTIC, "s1")
        assert len(all_bridges) == 2

        # Filtered to telos only
        telos_only = await registry.query_across(
            GraphOrigin.SEMANTIC, "s1", target_graph=GraphOrigin.TELOS,
        )
        assert len(telos_only) == 1

    @pytest.mark.asyncio
    async def test_all_edges_with_limit(self, registry):
        for i in range(10):
            await registry.upsert(_edge(source_id=f"s{i}", target_id=f"t{i}"))
        edges = await registry.all_edges(limit=3)
        assert len(edges) == 3


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestAggregation:
    @pytest.mark.asyncio
    async def test_count_empty(self, registry):
        assert await registry.count() == 0

    @pytest.mark.asyncio
    async def test_count_after_inserts(self, registry):
        await registry.upsert(_edge(source_id="a"))
        await registry.upsert(_edge(source_id="b"))
        assert await registry.count() == 2

    @pytest.mark.asyncio
    async def test_health(self, registry):
        await registry.upsert(_edge(confidence=0.9))
        h = await registry.health()
        assert h["total_edges"] == 1
        assert "db_path" in h


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


class TestTopology:
    @pytest.mark.asyncio
    async def test_connected_graphs(self, registry):
        await registry.upsert(_edge(
            source_graph=GraphOrigin.SEMANTIC,
            target_graph=GraphOrigin.TELOS,
        ))
        await registry.upsert(_edge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="s2",
            target_graph=GraphOrigin.TEMPORAL,
            target_id="temp1",
        ))

        connected = await registry.connected_graphs(GraphOrigin.SEMANTIC)
        assert "telos" in connected or GraphOrigin.TELOS.value in [str(c) for c in connected]

    @pytest.mark.asyncio
    async def test_cross_graph_density(self, registry):
        await registry.upsert(_edge(
            source_graph=GraphOrigin.SEMANTIC,
            target_graph=GraphOrigin.TELOS,
        ))
        density = await registry.cross_graph_density()
        assert isinstance(density, dict)


# ---------------------------------------------------------------------------
# Confidence dynamics
# ---------------------------------------------------------------------------


class TestConfidenceDynamics:
    @pytest.mark.asyncio
    async def test_boost_confidence(self, registry):
        e = _edge(confidence=0.5)
        await registry.upsert(e)
        new_conf = await registry.boost_confidence(e.edge_id, delta=0.2)
        assert new_conf is not None
        assert abs(new_conf - 0.7) < 0.01

    @pytest.mark.asyncio
    async def test_boost_confidence_clamps_at_one(self, registry):
        e = _edge(confidence=0.95)
        await registry.upsert(e)
        new_conf = await registry.boost_confidence(e.edge_id, delta=0.5)
        assert new_conf is not None
        assert new_conf <= 1.0

    @pytest.mark.asyncio
    async def test_decay_confidence(self, registry):
        e = _edge(confidence=0.8)
        await registry.upsert(e)
        new_conf = await registry.decay_confidence(e.edge_id, delta=0.3)
        assert new_conf is not None
        assert abs(new_conf - 0.5) < 0.01

    @pytest.mark.asyncio
    async def test_decay_confidence_clamps_at_zero(self, registry):
        e = _edge(confidence=0.05)
        await registry.upsert(e)
        new_conf = await registry.decay_confidence(e.edge_id, delta=0.5)
        assert new_conf is not None
        assert new_conf >= 0.0

    @pytest.mark.asyncio
    async def test_boost_nonexistent(self, registry):
        result = await registry.boost_confidence("ghost", delta=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_decay_nonexistent(self, registry):
        result = await registry.decay_confidence("ghost", delta=0.1)
        assert result is None


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


class TestMaintenance:
    @pytest.mark.asyncio
    async def test_prune_stale(self, registry):
        # Insert with low confidence — should be prunable if old enough
        e = _edge(confidence=0.05)
        await registry.upsert(e)

        # Prune with very lenient settings (0 days, 0.1 confidence)
        pruned = await registry.prune_stale(max_age_days=0, min_confidence=0.1)
        assert pruned >= 1

    @pytest.mark.asyncio
    async def test_prune_keeps_high_confidence(self, registry):
        e = _edge(confidence=0.95)
        await registry.upsert(e)
        pruned = await registry.prune_stale(max_age_days=0, min_confidence=0.1)
        assert pruned == 0
        assert await registry.count() == 1


# ---------------------------------------------------------------------------
# Init idempotency
# ---------------------------------------------------------------------------


class TestInit:
    @pytest.mark.asyncio
    async def test_double_init(self, tmp_path):
        r = BridgeRegistry(db_path=tmp_path / "test.db")
        await r.init()
        await r.init()  # should not raise
        await r.close()

    @pytest.mark.asyncio
    async def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "new_bridges.db"
        r = BridgeRegistry(db_path=db_path)
        await r.init()
        assert db_path.exists()
        await r.close()
