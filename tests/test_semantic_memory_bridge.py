"""Tests for dharma_swarm.semantic_memory_bridge — all 5 integration bridges."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from dharma_swarm.semantic_gravity import (
    ClusterFileSpec,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    FileClusterSpec,
    ResearchAnnotation,
    ResearchConnectionType,
)
from dharma_swarm.semantic_memory_bridge import (
    _find_best_matching_concept,
    apply_retrieval_uptake_to_salience,
    harvest_idea_shards_as_research,
    index_concepts_into_memory,
    map_experiment_cautions_to_hardening,
    run_semantic_sleep_phase,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(n: int = 5) -> ConceptGraph:
    """Build a small graph with *n* concepts for testing."""
    graph = ConceptGraph()
    for i in range(n):
        node = ConceptNode(
            name=f"concept_{i}",
            definition=f"Definition of concept {i} about category_{i % 3}",
            source_file=f"dharma_swarm/mod_{i}.py",
            category=f"category_{i % 3}",
            salience=0.4 + (i * 0.1),
            formal_structures=[f"struct_{i}"],
            recognition_type="class",
        )
        graph.add_node(node)
    # Wire up some edges
    nodes = list(graph.all_nodes())
    for i in range(len(nodes) - 1):
        graph.add_edge(ConceptEdge(
            source_id=nodes[i].id,
            target_id=nodes[i + 1].id,
            edge_type=EdgeType.REFERENCES,
        ))
    return graph


def _setup_memory_db(db_path: Path) -> None:
    """Ensure the memory plane schema exists for testing."""
    from dharma_swarm.engine.event_memory import ensure_memory_plane_schema_sync

    with sqlite3.connect(str(db_path)) as db:
        ensure_memory_plane_schema_sync(db)


def _insert_retrieval_log(
    db_path: Path, record_id: str, source_kind: str, uptake: str,
) -> None:
    """Insert a fake retrieval_log row for Bridge 2 tests."""
    from uuid import uuid4

    with sqlite3.connect(str(db_path)) as db:
        db.execute(
            "INSERT INTO retrieval_log "
            "(feedback_id, query_text, record_id, source_kind, source_path, "
            " score, rank, consumer, retrieved_at, evidence_json, "
            " outcome, uptake_state) "
            "VALUES (?, ?, ?, ?, '', 0.5, 1, 'test', datetime('now'), '{}', ?, ?)",
            (uuid4().hex[:16], "test query", record_id, source_kind, uptake, uptake),
        )
        db.commit()


def _insert_idea_shard(
    db_path: Path, shard_id: str, text: str, kind: str, salience: float,
) -> None:
    """Insert a fake idea_shard for Bridge 3 tests."""
    with sqlite3.connect(str(db_path)) as db:
        db.execute(
            "INSERT OR IGNORE INTO idea_shards "
            "(shard_id, turn_id, session_id, shard_kind, state, text, "
            " salience, novelty, flow_score, metadata_json, created_at) "
            "VALUES (?, 'turn_0', 'sess_0', ?, 'active', ?, ?, 0.5, 0.5, '{}', datetime('now'))",
            (shard_id, kind, text, salience),
        )
        db.commit()


# ---------------------------------------------------------------------------
# Bridge 1: Concepts → UnifiedIndex
# ---------------------------------------------------------------------------


class TestBridge1IndexConcepts:
    """Index concepts into the UnifiedIndex and verify retrieval."""

    def test_indexes_all_concepts(self, tmp_path: Path) -> None:
        graph = _make_graph(5)
        db = tmp_path / "mem.db"
        count = index_concepts_into_memory(graph, db_path=db)
        assert count == 5

    def test_records_have_semantic_concept_kind(self, tmp_path: Path) -> None:
        from dharma_swarm.engine.unified_index import UnifiedIndex

        graph = _make_graph(3)
        db = tmp_path / "mem.db"
        index_concepts_into_memory(graph, db_path=db)

        idx = UnifiedIndex(db)
        records = idx.records(filters={"source_kind": "semantic_concept"})
        assert len(records) >= 3
        for r in records:
            assert r.metadata["source_kind"] == "semantic_concept"

    def test_search_returns_hits(self, tmp_path: Path) -> None:
        from dharma_swarm.engine.hybrid_retriever import HybridRetriever
        from dharma_swarm.engine.unified_index import UnifiedIndex

        graph = _make_graph(5)
        db = tmp_path / "mem.db"
        index_concepts_into_memory(graph, db_path=db)

        idx = UnifiedIndex(db)
        retriever = HybridRetriever(idx)
        hits = retriever.search("concept_0 struct_0", limit=5)
        assert len(hits) > 0

    def test_empty_graph_indexes_zero(self, tmp_path: Path) -> None:
        graph = ConceptGraph()
        db = tmp_path / "mem.db"
        count = index_concepts_into_memory(graph, db_path=db)
        assert count == 0


# ---------------------------------------------------------------------------
# Bridge 2: Retrieval Uptake → Salience
# ---------------------------------------------------------------------------


class TestBridge2RetrievalUptake:
    """Retrieval feedback adjusts concept salience."""

    def test_boost_on_used(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        db = tmp_path / "mem.db"
        _setup_memory_db(db)

        node = list(graph.all_nodes())[0]
        original_salience = node.salience
        _insert_retrieval_log(db, f"concept://{node.id}", "semantic_concept", "used")

        changes = apply_retrieval_uptake_to_salience(graph, db_path=db)
        assert node.id in changes
        assert node.salience > original_salience

    def test_decay_on_not_used(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        db = tmp_path / "mem.db"
        _setup_memory_db(db)

        node = list(graph.all_nodes())[1]
        original_salience = node.salience
        _insert_retrieval_log(db, f"concept://{node.id}", "semantic_concept", "not_used")

        changes = apply_retrieval_uptake_to_salience(graph, db_path=db)
        assert node.id in changes
        assert node.salience < original_salience

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        result = apply_retrieval_uptake_to_salience(
            graph, db_path=tmp_path / "nonexistent.db",
        )
        assert result == {}

    def test_no_semantic_rows_returns_empty(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        db = tmp_path / "mem.db"
        _setup_memory_db(db)
        result = apply_retrieval_uptake_to_salience(graph, db_path=db)
        assert result == {}


# ---------------------------------------------------------------------------
# Bridge 3: Idea Shards → Research Candidates
# ---------------------------------------------------------------------------


class TestBridge3IdeaShards:
    """Idea shards become research annotations on matching concepts."""

    def test_harvest_creates_annotations(self, tmp_path: Path) -> None:
        graph = _make_graph(5)
        db = tmp_path / "mem.db"
        _setup_memory_db(db)

        node = list(graph.all_nodes())[0]
        # Insert shard whose text contains the concept name
        _insert_idea_shard(
            db, "shard_1", f"Hypothesis about {node.name} extension", "hypothesis", 0.8,
        )
        annotations = harvest_idea_shards_as_research(graph, db_path=db)
        assert len(annotations) >= 1
        assert annotations[0].concept_id == node.id
        assert annotations[0].field == "conversation_insight"

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        result = harvest_idea_shards_as_research(
            graph, db_path=tmp_path / "nonexistent.db",
        )
        assert result == []

    def test_low_salience_shards_skipped(self, tmp_path: Path) -> None:
        graph = _make_graph(3)
        db = tmp_path / "mem.db"
        _setup_memory_db(db)
        _insert_idea_shard(db, "shard_low", "low shard", "hypothesis", 0.1)
        annotations = harvest_idea_shards_as_research(graph, db_path=db)
        assert len(annotations) == 0


# ---------------------------------------------------------------------------
# _find_best_matching_concept helper
# ---------------------------------------------------------------------------


class TestFindBestMatchingConcept:
    """Concept matching from free text."""

    def test_matches_by_name(self) -> None:
        graph = _make_graph(5)
        node = list(graph.all_nodes())[2]
        match = _find_best_matching_concept(graph, f"something about {node.name}")
        assert match is not None
        assert match.id == node.id

    def test_matches_by_structure(self) -> None:
        graph = _make_graph(5)
        node = list(graph.all_nodes())[3]
        match = _find_best_matching_concept(graph, f"using {node.formal_structures[0]} transform")
        assert match is not None
        assert match.id == node.id

    def test_no_match_returns_none(self) -> None:
        graph = _make_graph(3)
        match = _find_best_matching_concept(graph, "completely unrelated quantum flux capacitor")
        assert match is None


# ---------------------------------------------------------------------------
# Bridge 4: Sleep Semantic Phase (async)
# ---------------------------------------------------------------------------


class TestBridge4SleepPhase:
    """Semantic sleep phase runs the full pipeline."""

    @pytest.mark.asyncio
    async def test_sleep_phase_runs(self, tmp_path: Path) -> None:
        graph_path = tmp_path / "graph.json"
        db = tmp_path / "mem.db"

        result = await run_semantic_sleep_phase(
            project_root=Path(__file__).resolve().parent.parent,
            graph_path=graph_path,
            db_path=db,
        )
        assert result["phase"] == "semantic"
        assert result["concepts_digested"] > 0
        assert result["gravity_snapshot"] is not None
        assert graph_path.exists()


# ---------------------------------------------------------------------------
# Bridge 5: Experiment Memory → Hardening Gaps
# ---------------------------------------------------------------------------


class TestBridge5ExperimentCautions:
    """Experiment caution components map to cluster hardening gaps."""

    def test_maps_cautions_to_clusters(self) -> None:
        graph = _make_graph(5)
        nodes = list(graph.all_nodes())

        cluster = FileClusterSpec(
            name="test_cluster",
            description="Test cluster",
            files=[ClusterFileSpec(path="dharma_swarm/mod_0.py")],
            core_concepts=[nodes[0].id, nodes[1].id],
            intersection_type="structural",
        )

        class FakeExp:
            caution_components = ["mod_0"]

        gaps = map_experiment_cautions_to_hardening(FakeExp(), graph, [cluster])
        assert cluster.id in gaps
        assert len(gaps[cluster.id]) >= 1
        assert "mod_0" in gaps[cluster.id][0]

    def test_no_cautions_returns_empty(self) -> None:
        graph = _make_graph(3)
        cluster = FileClusterSpec(
            name="c", description="d",
            files=[ClusterFileSpec(path="a.py")], core_concepts=[],
            intersection_type="x",
        )

        class NoExp:
            caution_components = []

        gaps = map_experiment_cautions_to_hardening(NoExp(), graph, [cluster])
        assert gaps == {}

    def test_unrelated_cautions_no_match(self) -> None:
        graph = _make_graph(3)
        nodes = list(graph.all_nodes())
        cluster = FileClusterSpec(
            name="c", description="d",
            files=[ClusterFileSpec(path="dharma_swarm/mod_0.py")],
            core_concepts=[nodes[0].id],
            intersection_type="x",
        )

        class UnrelatedExp:
            caution_components = ["zzz_nonexistent_module"]

        gaps = map_experiment_cautions_to_hardening(UnrelatedExp(), graph, [cluster])
        assert gaps == {}
