"""Tests for dharma_swarm.catalytic_graph -- CatalyticGraph + Tarjan SCC."""

import json

import pytest

from dharma_swarm.catalytic_graph import EDGE_TYPES, CatalyticGraph
from dharma_swarm.models import CatalyticEdge


# ---------------------------------------------------------------------------
# Node / edge basics
# ---------------------------------------------------------------------------


def test_add_node():
    g = CatalyticGraph()
    g.add_node("a", type="research")
    assert g.node_count == 1
    assert g._nodes["a"] == {"type": "research"}


def test_add_edge():
    g = CatalyticGraph()
    g.add_node("a")
    g.add_node("b")
    edge = g.add_edge("a", "b", "enables", 0.7, "test evidence")
    assert g.edge_count == 1
    assert isinstance(edge, CatalyticEdge)
    assert "b" in g._adj["a"]
    assert "a" in g._rev["b"]


def test_auto_add_nodes():
    g = CatalyticGraph()
    g.add_edge("x", "y")
    assert g.node_count == 2
    assert "x" in g._nodes
    assert "y" in g._nodes


def test_edge_types():
    g = CatalyticGraph()
    for et in EDGE_TYPES:
        edge = g.add_edge("src", "tgt", edge_type=et)
        assert edge.edge_type == et

    with pytest.raises(ValueError, match="Invalid edge_type"):
        g.add_edge("a", "b", edge_type="destroys")


# ---------------------------------------------------------------------------
# Tarjan SCC
# ---------------------------------------------------------------------------


def test_tarjan_simple_cycle():
    g = CatalyticGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", "A")
    sccs = g.tarjan_scc()
    # All three nodes form one SCC
    big = [s for s in sccs if len(s) >= 2]
    assert len(big) == 1
    assert set(big[0]) == {"A", "B", "C"}


def test_tarjan_no_cycle():
    g = CatalyticGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    sccs = g.tarjan_scc()
    # Three singleton SCCs
    assert len(sccs) == 3
    assert all(len(s) == 1 for s in sccs)


def test_tarjan_two_sccs():
    g = CatalyticGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "A")
    g.add_edge("C", "D")
    g.add_edge("D", "C")
    sccs = g.tarjan_scc()
    big = [s for s in sccs if len(s) >= 2]
    assert len(big) == 2
    scc_sets = [set(s) for s in big]
    assert {"A", "B"} in scc_sets
    assert {"C", "D"} in scc_sets


# ---------------------------------------------------------------------------
# Autocatalytic sets
# ---------------------------------------------------------------------------


def test_autocatalytic_simple():
    g = CatalyticGraph()
    # A->B->C->A : every node has an internal incoming edge
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", "A")
    ac = g.detect_autocatalytic_sets()
    assert len(ac) == 1
    assert set(ac[0]) == {"A", "B", "C"}


def test_autocatalytic_empty():
    g = CatalyticGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    ac = g.detect_autocatalytic_sets()
    assert ac == []


def test_autocatalytic_partial():
    """SCC where one node lacks an internal incoming edge.

    Build A<->B as an SCC with a dangling node C that has an outgoing
    edge into the SCC but no incoming edge from it.  The SCC {A,B} is
    valid (both have internal incoming), so this actually passes.

    To test a real partial failure we need an SCC where one member has
    NO internal incoming.  That requires a node reachable within the SCC
    only via an external bridge -- which contradicts SCC definition.
    In practice, every SCC of size >= 2 is autocatalytic by construction
    since every node must be reachable from every other (implying an
    incoming path exists). So we verify the filter correctly excludes
    singletons.
    """
    g = CatalyticGraph()
    # Singleton nodes (no cycle) should be excluded
    g.add_node("lone")
    g.add_edge("A", "B")
    g.add_edge("B", "A")
    ac = g.detect_autocatalytic_sets()
    # {A, B} is autocatalytic; "lone" is not (singleton)
    assert len(ac) == 1
    assert set(ac[0]) == {"A", "B"}


# ---------------------------------------------------------------------------
# Growth potential
# ---------------------------------------------------------------------------


def test_growth_potential():
    g = CatalyticGraph()
    g.add_node("hub")
    g.add_node("spoke1")
    g.add_node("spoke2")
    g.add_node("island")
    g.add_edge("hub", "spoke1")
    # hub is connected to spoke1 (outgoing). Not connected to spoke2 or island.
    assert g.growth_potential("hub") == 2  # spoke2, island
    assert g.growth_potential("unknown") == 0


# ---------------------------------------------------------------------------
# Loop closure priority
# ---------------------------------------------------------------------------


def test_loop_closure_priority():
    g = CatalyticGraph()
    # A->B->C but missing C->A to close the loop
    g.add_edge("A", "B", strength=0.8)
    g.add_edge("B", "C", strength=0.6)
    priorities = g.loop_closure_priority()
    # C->A should appear as a candidate
    closing_edges = [(s, t) for s, t, _ in priorities]
    assert ("C", "A") in closing_edges


# ---------------------------------------------------------------------------
# Revenue-ready sets
# ---------------------------------------------------------------------------


def test_revenue_ready_sets():
    g = CatalyticGraph()
    g.add_edge("paper", "credibility", "attracts", 0.7)
    g.add_edge("credibility", "consulting", "enables", 0.6)
    g.add_edge("consulting", "paper", "funds", 0.5)
    rr = g.revenue_ready_sets()
    assert len(rr) == 1
    assert set(rr[0]) == {"paper", "credibility", "consulting"}


def test_revenue_ready_sets_none():
    g = CatalyticGraph()
    # Cycle with only 'enables' edges -- no funds/attracts
    g.add_edge("A", "B", "enables")
    g.add_edge("B", "A", "enables")
    rr = g.revenue_ready_sets()
    assert rr == []


# ---------------------------------------------------------------------------
# Seed ecosystem
# ---------------------------------------------------------------------------


def test_seed_ecosystem():
    g = CatalyticGraph()
    g.seed_ecosystem()
    assert g.node_count == 6
    assert g.edge_count == 7
    # rv_paper, credibility, mi_consulting, rvm_toolkit form a cycle
    ac = g.detect_autocatalytic_sets()
    assert len(ac) >= 1
    # The 4-node cycle should be autocatalytic
    ac_nodes = set()
    for s in ac:
        ac_nodes.update(s)
    assert {"rv_paper", "credibility", "mi_consulting", "rvm_toolkit"}.issubset(
        ac_nodes
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_load(tmp_path):
    path = tmp_path / "graph.json"
    g = CatalyticGraph(persist_path=path)
    g.add_node("a", role="test")
    g.add_edge("a", "b", "validates", 0.9, "proof")
    g.save()

    assert path.exists()

    g2 = CatalyticGraph(persist_path=path)
    loaded = g2.load()
    assert loaded is True
    assert g2.node_count == 2
    assert g2.edge_count == 1
    assert g2._edges[0].edge_type == "validates"
    assert g2._edges[0].strength == 0.9
    assert "b" in g2._adj["a"]


def test_load_missing(tmp_path):
    path = tmp_path / "nonexistent.json"
    g = CatalyticGraph(persist_path=path)
    assert g.load() is False


def test_load_corrupt(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("not json {{{")
    g = CatalyticGraph(persist_path=path)
    assert g.load() is False


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary():
    g = CatalyticGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "A")
    s = g.summary()
    assert set(s.keys()) == {
        "nodes", "edges", "sccs", "autocatalytic_sets",
        "largest_scc", "revenue_ready",
    }
    assert s["nodes"] == 2
    assert s["edges"] == 2
    assert s["autocatalytic_sets"] >= 1
    assert s["largest_scc"] == 2
    assert isinstance(s["revenue_ready"], int)


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------


def test_empty_graph():
    g = CatalyticGraph()
    assert g.node_count == 0
    assert g.edge_count == 0
    assert g.tarjan_scc() == []
    assert g.detect_autocatalytic_sets() == []
    assert g.growth_potential("anything") == 0
    assert g.loop_closure_priority() == []
    assert g.revenue_ready_sets() == []
    s = g.summary()
    assert s["nodes"] == 0
    assert s["largest_scc"] == 0
