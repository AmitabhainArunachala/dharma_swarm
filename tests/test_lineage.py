"""Tests for Data Lineage.

Covers recording, querying, ancestor/descendant traversal,
provenance chains, impact analysis, and persistence.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dharma_swarm.lineage import (
    ImpactReport,
    LineageEdge,
    LineageGraph,
    ProvenanceChain,
)


@pytest.fixture()
def graph(tmp_path):
    """Fresh lineage graph in a temp directory."""
    return LineageGraph(db_path=tmp_path / "lineage.db")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Recording
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRecording:
    def test_record_edge(self, graph):
        edge = LineageEdge(
            task_id="task_01",
            input_artifacts=["prompts", "config"],
            output_artifacts=["rv_results"],
            agent="researcher",
            operation="compute_rv",
        )
        edge_id = graph.record(edge)
        assert edge_id == edge.edge_id

        retrieved = graph.get_edge(edge_id)
        assert retrieved is not None
        assert retrieved.task_id == "task_01"
        assert retrieved.input_artifacts == ["prompts", "config"]
        assert retrieved.output_artifacts == ["rv_results"]
        assert retrieved.agent == "researcher"

    def test_record_transformation_convenience(self, graph):
        edge_id = graph.record_transformation(
            task_id="t1",
            inputs=["a", "b"],
            outputs=["c"],
            agent="builder",
            operation="merge",
        )
        edge = graph.get_edge(edge_id)
        assert edge is not None
        assert edge.operation == "merge"

    def test_record_no_inputs(self, graph):
        """Source artifacts have no inputs."""
        edge_id = graph.record_transformation(
            task_id="import",
            inputs=[],
            outputs=["raw_data"],
            operation="ingest",
        )
        edge = graph.get_edge(edge_id)
        assert edge.input_artifacts == []
        assert edge.output_artifacts == ["raw_data"]

    def test_record_with_metadata(self, graph):
        edge = LineageEdge(
            task_id="t1",
            input_artifacts=["x"],
            output_artifacts=["y"],
            metadata={"model": "mistral-7b", "seed": 42},
        )
        graph.record(edge)
        retrieved = graph.get_edge(edge.edge_id)
        assert retrieved.metadata["model"] == "mistral-7b"
        assert retrieved.metadata["seed"] == 42

    def test_record_with_pipeline(self, graph):
        edge = LineageEdge(
            task_id="t1",
            input_artifacts=["x"],
            output_artifacts=["y"],
            pipeline_id="pipe_01",
            pipeline_label="rv_experiment",
            block_id="block_03",
        )
        graph.record(edge)
        retrieved = graph.get_edge(edge.edge_id)
        assert retrieved.pipeline_id == "pipe_01"
        assert retrieved.pipeline_label == "rv_experiment"
        assert retrieved.block_id == "block_03"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Querying
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestQuerying:
    def _build_chain(self, graph):
        """Build: raw -> cleaned -> features -> model -> predictions"""
        graph.record_transformation("t1", [], ["raw"], operation="ingest")
        graph.record_transformation("t2", ["raw"], ["cleaned"], operation="clean")
        graph.record_transformation("t3", ["cleaned"], ["features"], operation="featurize")
        graph.record_transformation("t4", ["features"], ["model"], operation="train")
        graph.record_transformation("t5", ["model", "features"], ["predictions"], operation="predict")

    def test_producers_of(self, graph):
        self._build_chain(graph)
        producers = graph.producers_of("features")
        assert len(producers) == 1
        assert producers[0].operation == "featurize"

    def test_consumers_of(self, graph):
        self._build_chain(graph)
        consumers = graph.consumers_of("features")
        assert len(consumers) == 2  # train and predict

    def test_edges_for_task(self, graph):
        graph.record_transformation("t1", ["a"], ["b"])
        graph.record_transformation("t1", ["b"], ["c"])
        graph.record_transformation("t2", ["c"], ["d"])
        edges = graph.edges_for_task("t1")
        assert len(edges) == 2

    def test_edges_for_pipeline(self, graph):
        graph.record_transformation("t1", ["a"], ["b"], pipeline_id="p1")
        graph.record_transformation("t2", ["b"], ["c"], pipeline_id="p1")
        graph.record_transformation("t3", ["x"], ["y"], pipeline_id="p2")
        edges = graph.edges_for_pipeline("p1")
        assert len(edges) == 2

    def test_get_nonexistent_edge(self, graph):
        assert graph.get_edge("nonexistent") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Traversal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTraversal:
    def _build_diamond(self, graph):
        """Diamond DAG:
             raw
            /   \\
        cleaned  enriched
            \\   /
           merged
             |
          analyzed
        """
        graph.record_transformation("t1", [], ["raw"], operation="ingest")
        graph.record_transformation("t2", ["raw"], ["cleaned"], operation="clean")
        graph.record_transformation("t3", ["raw"], ["enriched"], operation="enrich")
        graph.record_transformation("t4", ["cleaned", "enriched"], ["merged"], operation="merge")
        graph.record_transformation("t5", ["merged"], ["analyzed"], operation="analyze")

    def test_ancestors(self, graph):
        self._build_diamond(graph)
        anc = graph.ancestors("analyzed")
        operations = {e.operation for e in anc}
        assert "merge" in operations
        assert "clean" in operations
        assert "enrich" in operations
        assert "ingest" in operations

    def test_descendants(self, graph):
        self._build_diamond(graph)
        desc = graph.descendants("raw")
        operations = {e.operation for e in desc}
        assert "clean" in operations
        assert "enrich" in operations
        assert "merge" in operations
        assert "analyze" in operations

    def test_ancestors_of_source(self, graph):
        self._build_diamond(graph)
        anc = graph.ancestors("raw")
        # "raw" was produced by ingest — so 1 ancestor edge (but that edge has no inputs)
        assert len(anc) == 1
        assert anc[0].operation == "ingest"
        assert anc[0].input_artifacts == []

    def test_descendants_of_leaf(self, graph):
        self._build_diamond(graph)
        assert graph.descendants("analyzed") == []

    def test_max_depth_limit(self, graph):
        # Long chain: a0 -> a1 -> a2 -> ... -> a20
        for i in range(20):
            graph.record_transformation(f"t{i}", [f"a{i}"], [f"a{i+1}"])
        anc = graph.ancestors("a20", max_depth=5)
        # Should get at most 5 levels back
        assert len(anc) <= 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Provenance & Impact
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestProvenanceAndImpact:
    def _build_pipeline(self, graph):
        """Simulate an R_V experiment pipeline."""
        graph.record_transformation("load", [], ["prompts_v1"], operation="load_prompts")
        graph.record_transformation("load", [], ["model_config"], operation="load_config")
        graph.record_transformation(
            "compute", ["prompts_v1", "model_config"], ["rv_results_001"],
            agent="researcher", operation="compute_rv",
        )
        graph.record_transformation(
            "analyze", ["rv_results_001"], ["analysis_001"],
            agent="researcher", operation="llm_analyze",
        )
        graph.record_transformation(
            "archive", ["rv_results_001", "analysis_001"], ["archive_entry_001"],
            agent="researcher", operation="archive",
        )

    def test_provenance_chain(self, graph):
        self._build_pipeline(graph)
        chain = graph.provenance("archive_entry_001")
        assert isinstance(chain, ProvenanceChain)
        assert chain.artifact_id == "archive_entry_001"
        assert len(chain.chain) >= 3  # archive, compute/analyze, load
        # All inputs are also outputs of load edges, so no "unproduced" roots
        # The chain itself contains all the provenance info
        operations = {e.operation for e in chain.chain}
        assert "compute_rv" in operations
        assert "load_prompts" in operations or "load_config" in operations

    def test_root_causes(self, graph):
        self._build_pipeline(graph)
        roots = graph.root_causes("archive_entry_001")
        # Should trace back to original sources (things with no producer edges)
        # prompts_v1 and model_config are produced by "load" tasks with no inputs
        # so they're effectively produced but from empty inputs
        assert len(roots) == 0  # they were produced from [] inputs, so no inputs to trace

    def test_root_causes_with_actual_roots(self, graph):
        """When ancestors have inputs, those inputs that weren't produced are roots."""
        graph.record_transformation("t1", ["source_a", "source_b"], ["intermediate"])
        graph.record_transformation("t2", ["intermediate"], ["final"])
        roots = graph.root_causes("final")
        assert "source_a" in roots
        assert "source_b" in roots

    def test_impact_analysis(self, graph):
        self._build_pipeline(graph)
        impact = graph.impact("prompts_v1")
        assert isinstance(impact, ImpactReport)
        assert "rv_results_001" in impact.affected_artifacts
        assert "analysis_001" in impact.affected_artifacts or "archive_entry_001" in impact.affected_artifacts
        assert impact.total_descendants >= 2

    def test_impact_of_leaf(self, graph):
        self._build_pipeline(graph)
        impact = graph.impact("archive_entry_001")
        assert impact.total_descendants == 0

    def test_isolated_artifact(self, graph):
        chain = graph.provenance("nonexistent")
        assert chain.chain == []
        assert chain.root_sources == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stats & Introspection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestStats:
    def test_empty_stats(self, graph):
        s = graph.stats()
        assert s["total_edges"] == 0
        assert s["unique_artifacts"] == 0

    def test_stats_after_recording(self, graph):
        graph.record_transformation("t1", ["a", "b"], ["c", "d"])
        graph.record_transformation("t2", ["c"], ["e"])
        s = graph.stats()
        assert s["total_edges"] == 2
        assert s["total_input_refs"] == 3  # a, b, c
        assert s["total_output_refs"] == 3  # c, d, e
        assert s["unique_artifacts"] == 5  # a, b, c, d, e

    def test_summary(self, graph):
        graph.record_transformation("t1", ["a"], ["b"], pipeline_id="p1")
        summary = graph.summary()
        assert "1 edges" in summary
        assert "1 pipelines" in summary

    def test_clear(self, graph):
        graph.record_transformation("t1", ["a"], ["b"])
        graph.clear()
        s = graph.stats()
        assert s["total_edges"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPersistence:
    def test_survives_reinstantiation(self, tmp_path):
        db = tmp_path / "lineage.db"
        g1 = LineageGraph(db_path=db)
        g1.record_transformation("t1", ["x"], ["y"])

        g2 = LineageGraph(db_path=db)
        assert g2.stats()["total_edges"] == 1
        edge = g2.producers_of("y")
        assert len(edge) == 1
        assert edge[0].task_id == "t1"
