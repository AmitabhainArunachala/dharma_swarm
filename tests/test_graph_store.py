"""Tests for the Four-Graph Knowledge Architecture storage layer."""

from __future__ import annotations

import pytest

from dharma_swarm.graph_store import GraphStore, SQLiteGraphStore


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    """Yield a fresh SQLiteGraphStore backed by a temp database."""
    db = tmp_path / "test_graphs.db"
    with SQLiteGraphStore(db) as s:
        yield s


def _make_node(node_id: str, kind: str = "function", name: str = "foo", **extra) -> dict:
    d = {"id": node_id, "kind": kind, "name": name}
    if extra:
        d["data"] = extra
    return d


def _make_edge(source: str, target: str, kind: str = "calls", **extra) -> dict:
    d = {"source_id": source, "target_id": target, "kind": kind}
    if extra:
        d["data"] = extra
    return d


def _make_bridge(
    bridge_id: str,
    src_graph: str = "code",
    src_id: str = "n1",
    tgt_graph: str = "semantic",
    tgt_id: str = "c1",
    kind: str = "implements_concept",
    **extra,
) -> dict:
    return {
        "id": bridge_id,
        "source_graph": src_graph,
        "source_id": src_id,
        "target_graph": tgt_graph,
        "target_id": tgt_id,
        "kind": kind,
        **extra,
    }


# ── Graph validation ─────────────────────────────────────────────────────


class TestGraphValidation:
    def test_invalid_graph_name_raises(self, store):
        with pytest.raises(ValueError, match="Invalid graph"):
            store.upsert_node("invalid", _make_node("n1"))

    def test_invalid_graph_on_get_node(self, store):
        with pytest.raises(ValueError):
            store.get_node("nope", "n1")

    def test_invalid_graph_on_get_edges(self, store):
        with pytest.raises(ValueError):
            store.get_edges("nope", "n1")

    def test_invalid_graph_on_traverse(self, store):
        with pytest.raises(ValueError):
            store.traverse("nope", "n1", ["calls"])

    def test_invalid_graph_on_delete_node(self, store):
        with pytest.raises(ValueError):
            store.delete_node("nope", "n1")

    def test_invalid_graph_on_delete_edge(self, store):
        with pytest.raises(ValueError):
            store.delete_edge("nope", "a", "b", "k")

    def test_invalid_graph_on_search(self, store):
        with pytest.raises(ValueError):
            store.search_nodes("nope", "query")

    def test_invalid_graph_on_count(self, store):
        with pytest.raises(ValueError):
            store.count_nodes("nope")

    def test_all_valid_graphs_accepted(self, store):
        for g in SQLiteGraphStore.GRAPHS:
            store.upsert_node(g, _make_node(f"{g}_n1", name=f"{g}_node"))
            assert store.count_nodes(g) == 1


# ── Node CRUD ─────────────────────────────────────────────────────────────


class TestNodeCRUD:
    @pytest.mark.parametrize("graph", SQLiteGraphStore.GRAPHS)
    def test_insert_and_get(self, store, graph):
        node = _make_node("n1", kind="class", name="MyClass", description="a class")
        store.upsert_node(graph, node)
        fetched = store.get_node(graph, "n1")
        assert fetched is not None
        assert fetched["id"] == "n1"
        assert fetched["kind"] == "class"
        assert fetched["name"] == "MyClass"
        assert fetched["data"]["description"] == "a class"
        assert "created" in fetched
        assert "updated" in fetched

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_node("code", "nonexistent") is None

    def test_upsert_updates_existing(self, store):
        store.upsert_node("code", _make_node("n1", name="old_name"))
        store.upsert_node("code", _make_node("n1", name="new_name"))
        fetched = store.get_node("code", "n1")
        assert fetched["name"] == "new_name"
        assert store.count_nodes("code") == 1

    def test_delete_node(self, store):
        store.upsert_node("code", _make_node("n1"))
        assert store.delete_node("code", "n1") is True
        assert store.get_node("code", "n1") is None
        assert store.count_nodes("code") == 0

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete_node("code", "nonexistent") is False

    def test_delete_node_removes_incident_edges(self, store):
        store.upsert_node("code", _make_node("a"))
        store.upsert_node("code", _make_node("b"))
        store.upsert_edge("code", _make_edge("a", "b"))
        store.delete_node("code", "a")
        assert store.count_edges("code") == 0

    def test_count_nodes(self, store):
        assert store.count_nodes("code") == 0
        store.upsert_node("code", _make_node("n1"))
        store.upsert_node("code", _make_node("n2"))
        assert store.count_nodes("code") == 2

    def test_node_data_as_json(self, store):
        node = _make_node("n1", nested={"a": [1, 2, 3]})
        store.upsert_node("code", node)
        fetched = store.get_node("code", "n1")
        assert fetched["data"]["nested"] == {"a": [1, 2, 3]}

    def test_nodes_isolated_between_graphs(self, store):
        store.upsert_node("code", _make_node("n1", name="code_node"))
        store.upsert_node("semantic", _make_node("n1", name="semantic_node"))
        assert store.get_node("code", "n1")["name"] == "code_node"
        assert store.get_node("semantic", "n1")["name"] == "semantic_node"
        assert store.count_nodes("code") == 1
        assert store.count_nodes("semantic") == 1


# ── Edge CRUD ─────────────────────────────────────────────────────────────


class TestEdgeCRUD:
    @pytest.mark.parametrize("graph", SQLiteGraphStore.GRAPHS)
    def test_insert_and_get_out(self, store, graph):
        store.upsert_edge(graph, _make_edge("a", "b", "calls"))
        edges = store.get_edges(graph, "a", direction="out")
        assert len(edges) == 1
        assert edges[0]["source_id"] == "a"
        assert edges[0]["target_id"] == "b"
        assert edges[0]["kind"] == "calls"

    def test_get_edges_in(self, store):
        store.upsert_edge("code", _make_edge("a", "b"))
        edges = store.get_edges("code", "b", direction="in")
        assert len(edges) == 1

    def test_get_edges_both(self, store):
        store.upsert_edge("code", _make_edge("a", "b"))
        store.upsert_edge("code", _make_edge("c", "a"))
        edges = store.get_edges("code", "a", direction="both")
        assert len(edges) == 2

    def test_get_edges_filtered_by_kind(self, store):
        store.upsert_edge("code", _make_edge("a", "b", "calls"))
        store.upsert_edge("code", _make_edge("a", "c", "imports"))
        edges = store.get_edges("code", "a", direction="out", edge_kinds=["calls"])
        assert len(edges) == 1
        assert edges[0]["kind"] == "calls"

    def test_upsert_edge_updates(self, store):
        store.upsert_edge("code", _make_edge("a", "b", "calls", weight=1.0))
        store.upsert_edge("code", _make_edge("a", "b", "calls", weight=2.0))
        edges = store.get_edges("code", "a", direction="out")
        assert len(edges) == 1
        assert edges[0]["data"]["weight"] == 2.0

    def test_delete_edge(self, store):
        store.upsert_edge("code", _make_edge("a", "b", "calls"))
        assert store.delete_edge("code", "a", "b", "calls") is True
        assert store.count_edges("code") == 0

    def test_delete_nonexistent_edge_returns_false(self, store):
        assert store.delete_edge("code", "x", "y", "z") is False

    def test_count_edges(self, store):
        assert store.count_edges("code") == 0
        store.upsert_edge("code", _make_edge("a", "b"))
        store.upsert_edge("code", _make_edge("b", "c"))
        assert store.count_edges("code") == 2

    def test_edge_data_as_json(self, store):
        store.upsert_edge("code", _make_edge("a", "b", "calls", meta={"line": 42}))
        edges = store.get_edges("code", "a", direction="out")
        assert edges[0]["data"]["meta"] == {"line": 42}


# ── Traversal ─────────────────────────────────────────────────────────────


class TestTraversal:
    def _build_chain(self, store, graph="code"):
        """Build a→b→c→d chain with 'calls' edges and nodes."""
        for nid in ("a", "b", "c", "d"):
            store.upsert_node(graph, _make_node(nid, name=nid))
        for src, tgt in [("a", "b"), ("b", "c"), ("c", "d")]:
            store.upsert_edge(graph, _make_edge(src, tgt, "calls"))

    def test_traverse_basic(self, store):
        self._build_chain(store)
        result = store.traverse("code", "a", ["calls"], max_depth=3)
        ids = [n["id"] for n in result]
        assert "b" in ids
        assert "c" in ids
        assert "d" in ids

    def test_traverse_respects_depth(self, store):
        self._build_chain(store)
        result = store.traverse("code", "a", ["calls"], max_depth=1)
        ids = [n["id"] for n in result]
        assert ids == ["b"]

    def test_traverse_depth_field(self, store):
        self._build_chain(store)
        result = store.traverse("code", "a", ["calls"], max_depth=3)
        depths = {n["id"]: n["depth"] for n in result}
        assert depths["b"] == 1
        assert depths["c"] == 2
        assert depths["d"] == 3

    def test_traverse_filters_by_edge_kind(self, store):
        for nid in ("a", "b", "c"):
            store.upsert_node("code", _make_node(nid, name=nid))
        store.upsert_edge("code", _make_edge("a", "b", "calls"))
        store.upsert_edge("code", _make_edge("a", "c", "imports"))
        result = store.traverse("code", "a", ["calls"], max_depth=3)
        ids = [n["id"] for n in result]
        assert "b" in ids
        assert "c" not in ids

    def test_traverse_empty_graph(self, store):
        result = store.traverse("code", "nonexistent", ["calls"], max_depth=3)
        assert result == []

    def test_traverse_handles_cycles(self, store):
        for nid in ("a", "b", "c"):
            store.upsert_node("code", _make_node(nid, name=nid))
        store.upsert_edge("code", _make_edge("a", "b", "calls"))
        store.upsert_edge("code", _make_edge("b", "c", "calls"))
        store.upsert_edge("code", _make_edge("c", "a", "calls"))
        result = store.traverse("code", "a", ["calls"], max_depth=10)
        # Should not infinite-loop; should find b and c
        ids = [n["id"] for n in result]
        assert "b" in ids
        assert "c" in ids

    def test_traverse_empty_edge_kinds(self, store):
        store.upsert_node("code", _make_node("a"))
        result = store.traverse("code", "a", [], max_depth=3)
        assert result == []

    def test_traverse_multiple_edge_kinds(self, store):
        for nid in ("a", "b", "c"):
            store.upsert_node("code", _make_node(nid, name=nid))
        store.upsert_edge("code", _make_edge("a", "b", "calls"))
        store.upsert_edge("code", _make_edge("a", "c", "imports"))
        result = store.traverse("code", "a", ["calls", "imports"], max_depth=1)
        ids = sorted([n["id"] for n in result])
        assert ids == ["b", "c"]


# ── FTS5 Search ───────────────────────────────────────────────────────────


class TestFTS5Search:
    def test_search_by_name(self, store):
        store.upsert_node("code", _make_node("n1", name="heartbeat_loop"))
        store.upsert_node("code", _make_node("n2", name="sleep_cycle"))
        results = store.search_nodes("code", "heartbeat")
        assert len(results) == 1
        assert results[0]["id"] == "n1"

    def test_search_by_data(self, store):
        store.upsert_node(
            "semantic",
            _make_node("c1", name="autopoiesis", description="self-producing system"),
        )
        results = store.search_nodes("semantic", "self-producing")
        assert len(results) == 1
        assert results[0]["id"] == "c1"

    def test_search_respects_limit(self, store):
        for i in range(20):
            store.upsert_node("code", _make_node(f"n{i}", name=f"function_{i}"))
        results = store.search_nodes("code", "function", limit=5)
        assert len(results) == 5

    def test_search_no_results(self, store):
        store.upsert_node("code", _make_node("n1", name="heartbeat"))
        results = store.search_nodes("code", "nonexistent_term_xyz")
        assert results == []

    def test_search_after_upsert_update(self, store):
        store.upsert_node("code", _make_node("n1", name="old_name"))
        store.upsert_node("code", _make_node("n1", name="new_name"))
        assert store.search_nodes("code", "old_name") == []
        results = store.search_nodes("code", "new_name")
        assert len(results) == 1

    def test_search_after_delete(self, store):
        store.upsert_node("code", _make_node("n1", name="heartbeat"))
        store.delete_node("code", "n1")
        results = store.search_nodes("code", "heartbeat")
        assert results == []


# ── Bridge CRUD ───────────────────────────────────────────────────────────


class TestBridgeCRUD:
    def test_upsert_and_get(self, store):
        bridge = _make_bridge("b1", confidence=0.8, description="test bridge")
        store.upsert_bridge(bridge)
        results = store.get_bridges(source_graph="code", source_id="n1")
        assert len(results) == 1
        assert results[0]["id"] == "b1"
        assert results[0]["confidence"] == 0.8
        assert results[0]["description"] == "test bridge"

    def test_upsert_updates_existing(self, store):
        store.upsert_bridge(_make_bridge("b1", confidence=0.3))
        store.upsert_bridge(_make_bridge("b1", confidence=0.9))
        results = store.get_bridges()
        assert len(results) == 1
        assert results[0]["confidence"] == 0.9

    def test_get_bridges_no_filter(self, store):
        store.upsert_bridge(_make_bridge("b1"))
        store.upsert_bridge(_make_bridge("b2", src_id="n2", tgt_id="c2"))
        results = store.get_bridges()
        assert len(results) == 2

    def test_get_bridges_by_target(self, store):
        store.upsert_bridge(_make_bridge("b1", tgt_graph="semantic", tgt_id="c1"))
        store.upsert_bridge(_make_bridge("b2", tgt_graph="runtime", tgt_id="e1"))
        results = store.get_bridges(target_graph="semantic")
        assert len(results) == 1
        assert results[0]["target_id"] == "c1"

    def test_get_bridges_by_kind(self, store):
        store.upsert_bridge(_make_bridge("b1", kind="implements_concept"))
        store.upsert_bridge(_make_bridge("b2", src_id="n2", kind="advances_goal"))
        results = store.get_bridges(kind="advances_goal")
        assert len(results) == 1
        assert results[0]["id"] == "b2"

    def test_delete_bridge(self, store):
        store.upsert_bridge(_make_bridge("b1"))
        assert store.delete_bridge("b1") is True
        assert store.get_bridges() == []

    def test_delete_nonexistent_bridge(self, store):
        assert store.delete_bridge("nonexistent") is False

    def test_bridge_evidence_json(self, store):
        bridge = _make_bridge("b1", evidence=["docstring match", "llm inference"])
        store.upsert_bridge(bridge)
        results = store.get_bridges()
        assert results[0]["evidence"] == ["docstring match", "llm inference"]

    def test_bridge_combined_filters(self, store):
        store.upsert_bridge(
            _make_bridge("b1", src_graph="code", src_id="f1", tgt_graph="semantic", tgt_id="c1", kind="implements_concept")
        )
        store.upsert_bridge(
            _make_bridge("b2", src_graph="code", src_id="f1", tgt_graph="telos", tgt_id="o1", kind="change_advances")
        )
        store.upsert_bridge(
            _make_bridge("b3", src_graph="runtime", src_id="e1", tgt_graph="telos", tgt_id="o1", kind="advances_goal")
        )
        results = store.get_bridges(source_graph="code", source_id="f1", kind="implements_concept")
        assert len(results) == 1
        assert results[0]["id"] == "b1"


# ── Context manager ──────────────────────────────────────────────────────


class TestContextManager:
    def test_context_manager(self, tmp_path):
        db = tmp_path / "ctx.db"
        with SQLiteGraphStore(db) as store:
            store.upsert_node("code", _make_node("n1"))
            assert store.count_nodes("code") == 1
        # Connection should be closed; re-opening should see persisted data.
        with SQLiteGraphStore(db) as store2:
            assert store2.count_nodes("code") == 1

    def test_close_idempotent(self, tmp_path):
        db = tmp_path / "close.db"
        store = SQLiteGraphStore(db)
        store.close()
        store.close()  # Should not raise

    def test_is_subclass_of_abc(self):
        assert issubclass(SQLiteGraphStore, GraphStore)


# ── GRAPHS constant ──────────────────────────────────────────────────────


class TestGraphsConstant:
    def test_graphs_tuple(self):
        assert SQLiteGraphStore.GRAPHS == ("code", "semantic", "runtime", "telos")

    def test_graphs_is_tuple(self):
        assert isinstance(SQLiteGraphStore.GRAPHS, tuple)
