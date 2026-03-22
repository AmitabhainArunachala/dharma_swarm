"""Tests for dharma_swarm.ontology_query -- graph query API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.ontology import (
    Link,
    LinkCardinality,
    LinkDef,
    OntologyObj,
    OntologyRegistry,
)
from dharma_swarm.ontology_query import OntologyGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _utc(minutes_ago: int = 0) -> datetime:
    """Return a UTC datetime offset by minutes_ago from now."""
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


@pytest.fixture()
def graph_fixture() -> tuple[OntologyRegistry, OntologyGraph]:
    """Create a known graph with 5 objects and 6 links.

    Graph topology::

        A --r1--> B --r2--> C
        |                   |
        r3                  r5
        |                   |
        v                   v
        D --r4--> E
        (no connection from E to anything else)

    A = ResearchThread
    B = Experiment
    C = KnowledgeArtifact
    D = AgentIdentity
    E = TypedTask
    """
    reg = OntologyRegistry.create_dharma_registry()

    # Create objects
    obj_a = OntologyObj(
        id="obj_a",
        type_name="ResearchThread",
        properties={
            "name": "R_V Metric",
            "domain": "mechanistic",
            "status": "active",
            "hypothesis": "Value matrices contract under self-reference",
            "priority": 0.9,
        },
        created_at=_utc(100),
    )
    obj_b = OntologyObj(
        id="obj_b",
        type_name="Experiment",
        properties={
            "name": "Mistral-7B contraction test",
            "status": "completed",
            "model": "mistral-7b",
            "r_v_value": 0.737,
        },
        created_at=_utc(80),
    )
    obj_c = OntologyObj(
        id="obj_c",
        type_name="KnowledgeArtifact",
        properties={
            "title": "R_V results table",
            "artifact_type": "result",
            "domain": "mech_interp",
            "content": "Hedges g=-1.47, AUROC=0.909",
            "confidence": 0.95,
        },
        created_at=_utc(60),
    )
    obj_d = OntologyObj(
        id="obj_d",
        type_name="AgentIdentity",
        properties={
            "name": "coder-1",
            "role": "coder",
            "tasks_completed": 42,
        },
        created_at=_utc(200),
    )
    obj_e = OntologyObj(
        id="obj_e",
        type_name="TypedTask",
        properties={
            "title": "Run baseline experiment",
            "status": "completed",
            "priority": "high",
            "task_type": "experiment",
        },
        created_at=_utc(5),
    )

    for obj in [obj_a, obj_b, obj_c, obj_d, obj_e]:
        reg._objects[obj.id] = obj

    # Create links
    # A -> B (has_experiment)
    link_r1 = Link(
        id="link_r1",
        link_name="has_experiment",
        source_id="obj_a",
        source_type="ResearchThread",
        target_id="obj_b",
        target_type="Experiment",
    )
    # B -> C (produces)
    link_r2 = Link(
        id="link_r2",
        link_name="produces",
        source_id="obj_b",
        source_type="Experiment",
        target_id="obj_c",
        target_type="KnowledgeArtifact",
    )
    # A -> D (via "authored" inverse -- we use a generic link for test)
    # Using assigned_to in reverse: D is an agent, A is a thread
    # For test purposes, add a custom link
    reg.register_link(LinkDef(
        name="led_by",
        source_type="ResearchThread",
        target_type="AgentIdentity",
        cardinality=LinkCardinality.MANY_TO_ONE,
        inverse_name="leads_thread",
    ))
    link_r3 = Link(
        id="link_r3",
        link_name="led_by",
        source_id="obj_a",
        source_type="ResearchThread",
        target_id="obj_d",
        target_type="AgentIdentity",
    )
    # D -> E (assigned_tasks inverse: task assigned to agent)
    link_r4 = Link(
        id="link_r4",
        link_name="assigned_to",
        source_id="obj_e",
        source_type="TypedTask",
        target_id="obj_d",
        target_type="AgentIdentity",
    )
    # C -> E (consumed_by_task inverse: task consumes artifact)
    link_r5 = Link(
        id="link_r5",
        link_name="consumes",
        source_id="obj_e",
        source_type="TypedTask",
        target_id="obj_c",
        target_type="KnowledgeArtifact",
    )
    # Extra link: B -> D for richer connectivity
    reg.register_link(LinkDef(
        name="run_by",
        source_type="Experiment",
        target_type="AgentIdentity",
        cardinality=LinkCardinality.MANY_TO_ONE,
    ))
    link_r6 = Link(
        id="link_r6",
        link_name="run_by",
        source_id="obj_b",
        source_type="Experiment",
        target_id="obj_d",
        target_type="AgentIdentity",
    )

    for link in [link_r1, link_r2, link_r3, link_r4, link_r5, link_r6]:
        reg._link_instances[link.id] = link

    graph = OntologyGraph(reg)
    return reg, graph


# ---------------------------------------------------------------------------
# Traverse tests
# ---------------------------------------------------------------------------


class TestTraverse:
    def test_traverse_from_root_depth_1(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.traverse("obj_a", depth=1)
        assert result["root"] is not None
        assert result["root"].id == "obj_a"
        # At depth 1, should reach B and D (direct neighbors of A)
        node_ids = {n.id for n in result["nodes"]}
        assert "obj_a" in node_ids  # root
        assert "obj_b" in node_ids
        assert "obj_d" in node_ids
        assert result["depth_reached"] == 1

    def test_traverse_full_depth(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.traverse("obj_a", depth=5)
        # Should reach all 5 nodes
        node_ids = {n.id for n in result["nodes"]}
        assert node_ids == {"obj_a", "obj_b", "obj_c", "obj_d", "obj_e"}

    def test_traverse_filtered_by_link_name(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # Only follow "has_experiment" links from A
        result = graph.traverse(
            "obj_a", link_names=["has_experiment"], depth=3
        )
        node_ids = {n.id for n in result["nodes"]}
        assert "obj_b" in node_ids
        # Should NOT reach D through led_by
        assert "obj_d" not in node_ids

    def test_traverse_nonexistent_start(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.traverse("nonexistent")
        assert result["root"] is None
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["depth_reached"] == 0

    def test_traverse_collects_edges(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.traverse("obj_a", depth=5)
        # Should have collected all 6 links as edges
        assert len(result["edges"]) == 6


# ---------------------------------------------------------------------------
# Find tests
# ---------------------------------------------------------------------------


class TestFind:
    def test_find_by_type(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find("Experiment")
        assert len(results) == 1
        assert results[0].id == "obj_b"

    def test_find_by_type_and_property_filter(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find(
            "ResearchThread", filters={"status": "active"}
        )
        assert len(results) == 1
        assert results[0].properties["name"] == "R_V Metric"

    def test_find_with_text_query(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find("KnowledgeArtifact", text_query="AUROC")
        assert len(results) == 1
        assert results[0].id == "obj_c"

    def test_find_text_query_case_insensitive(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find("KnowledgeArtifact", text_query="auroc")
        assert len(results) == 1

    def test_find_no_matches(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find("Experiment", text_query="nonexistent stuff")
        assert results == []

    def test_find_with_filter_and_text(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        results = graph.find(
            "TypedTask",
            filters={"status": "completed"},
            text_query="baseline",
        )
        assert len(results) == 1
        assert results[0].id == "obj_e"

    def test_find_respects_limit(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        reg, graph = graph_fixture
        # Add more objects of the same type
        for i in range(10):
            reg._objects[f"extra_{i}"] = OntologyObj(
                id=f"extra_{i}",
                type_name="KnowledgeArtifact",
                properties={"title": f"Extra artifact {i}"},
            )
        results = graph.find("KnowledgeArtifact", limit=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# Neighbors tests
# ---------------------------------------------------------------------------


class TestNeighbors:
    def test_neighbors_returns_both_directions(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # D has incoming: A->D (led_by), E->D (assigned_to), B->D (run_by)
        neighbors = graph.neighbors("obj_d")
        neighbor_ids = {obj.id for _, obj in neighbors}
        assert "obj_a" in neighbor_ids
        assert "obj_e" in neighbor_ids
        assert "obj_b" in neighbor_ids

    def test_neighbors_includes_link_names(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        neighbors = graph.neighbors("obj_a")
        link_names = {name for name, _ in neighbors}
        assert "has_experiment" in link_names
        assert "led_by" in link_names

    def test_neighbors_of_leaf_node(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # E has: E->D (assigned_to), E->C (consumes)
        neighbors = graph.neighbors("obj_e")
        assert len(neighbors) >= 2

    def test_neighbors_nonexistent_obj(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        neighbors = graph.neighbors("nonexistent")
        assert neighbors == []


# ---------------------------------------------------------------------------
# Shortest path tests
# ---------------------------------------------------------------------------


class TestShortestPath:
    def test_direct_path(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        path = graph.shortest_path("obj_a", "obj_b")
        assert len(path) == 1
        assert path[0] == ("has_experiment", "obj_b")

    def test_multi_hop_path(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        path = graph.shortest_path("obj_a", "obj_c")
        # A -> B -> C (2 hops)
        assert len(path) == 2
        obj_ids = [oid for _, oid in path]
        assert "obj_c" in obj_ids

    def test_no_path_returns_empty(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        reg, graph = graph_fixture
        # Add a disconnected node
        reg._objects["island"] = OntologyObj(
            id="island",
            type_name="ResearchThread",
            properties={"name": "Isolated thread"},
        )
        path = graph.shortest_path("obj_a", "island")
        assert path == []

    def test_same_node_returns_empty(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        path = graph.shortest_path("obj_a", "obj_a")
        assert path == []

    def test_nonexistent_source_returns_empty(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        path = graph.shortest_path("nonexistent", "obj_a")
        assert path == []

    def test_nonexistent_target_returns_empty(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        path = graph.shortest_path("obj_a", "nonexistent")
        assert path == []

    def test_path_respects_max_depth(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # E is reachable from A but may need >1 hop
        # With max_depth=1, only direct neighbors are checked
        path = graph.shortest_path("obj_a", "obj_e", max_depth=1)
        # A's direct neighbors are B and D. E is at depth 2 (A->D->E).
        # So max_depth=1 should fail to find E.
        assert path == []

    def test_path_through_reverse_links(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # E -> D via assigned_to, then D -> A via led_by (reverse)
        path = graph.shortest_path("obj_e", "obj_a")
        assert len(path) >= 1
        final_id = path[-1][1]
        assert final_id == "obj_a"


# ---------------------------------------------------------------------------
# Subgraph tests
# ---------------------------------------------------------------------------


class TestSubgraph:
    def test_subgraph_all(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.subgraph()
        assert result["stats"]["object_count"] == 5
        assert result["stats"]["link_count"] == 6

    def test_subgraph_filtered_by_type(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.subgraph(type_names=["Experiment", "KnowledgeArtifact"])
        assert result["stats"]["object_count"] == 2
        # Only links between B and C should appear
        obj_ids = {o.id for o in result["objects"]}
        assert obj_ids == {"obj_b", "obj_c"}

    def test_subgraph_since_filter(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        # Only objects created in the last 10 minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        result = graph.subgraph(since=cutoff)
        # obj_e was created 5 minutes ago, all others are older
        obj_ids = {o.id for o in result["objects"]}
        assert "obj_e" in obj_ids
        # obj_a (100 min ago), obj_b (80), obj_c (60), obj_d (200) should be excluded
        assert "obj_a" not in obj_ids
        assert "obj_d" not in obj_ids

    def test_subgraph_stats_type_distribution(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        result = graph.subgraph()
        dist = result["stats"]["type_distribution"]
        assert dist["ResearchThread"] == 1
        assert dist["Experiment"] == 1
        assert dist["KnowledgeArtifact"] == 1
        assert dist["AgentIdentity"] == 1
        assert dist["TypedTask"] == 1


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_counts(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        s = graph.stats()
        assert s["total_objects"] == 5
        assert s["total_links"] == 6

    def test_stats_object_counts_by_type(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        s = graph.stats()
        assert s["object_counts"]["ResearchThread"] == 1
        assert s["object_counts"]["Experiment"] == 1

    def test_stats_link_counts_by_name(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        s = graph.stats()
        assert s["link_counts"]["has_experiment"] == 1
        assert s["link_counts"]["produces"] == 1

    def test_stats_freshness(
        self, graph_fixture: tuple[OntologyRegistry, OntologyGraph]
    ) -> None:
        _, graph = graph_fixture
        s = graph.stats()
        assert s["newest_object"] is not None
        assert s["oldest_object"] is not None
        assert s["newest_object"] >= s["oldest_object"]

    def test_stats_empty_registry(self) -> None:
        reg = OntologyRegistry()
        graph = OntologyGraph(reg)
        s = graph.stats()
        assert s["total_objects"] == 0
        assert s["total_links"] == 0
        assert s["newest_object"] is None
        assert s["oldest_object"] is None
