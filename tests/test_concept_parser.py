"""Tests for concept_parser.py — Semantic GitNexus extraction pipeline.

Tests the three-stage pipeline:
1. ConceptRegistry — loading and lookup
2. ConceptParser — extraction from Python source
3. ConceptIndexer — population of GraphStore
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from dharma_swarm.concept_parser import (
    ConceptExtraction,
    ConceptIndexer,
    ConceptParser,
    ConceptRegistry,
)
from dharma_swarm.graph_store import SQLiteGraphStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINI_CONCEPTS = {
    "version": "1.0-test",
    "generated": "2026-03-21",
    "concepts": [
        {
            "id": "autopoiesis",
            "canonical_name": "Autopoiesis",
            "aliases": ["autopoietic", "self-production"],
            "definition": "Self-producing system.",
            "domain": "autopoiesis",
            "source_attribution": "Maturana & Varela, 1980",
            "dharma_interpretation": "The organism maintains itself.",
            "related_concepts": ["structural_coupling"],
            "codebase_frequency": 14,
            "codebase_files": 7,
        },
        {
            "id": "structural_coupling",
            "canonical_name": "Structural Coupling",
            "aliases": ["structurally coupled"],
            "definition": "Mutual perturbation between system and environment.",
            "domain": "autopoiesis",
            "source_attribution": "Maturana & Varela, 1980",
            "dharma_interpretation": "Agent-environment interaction.",
            "related_concepts": ["autopoiesis"],
            "codebase_frequency": 3,
            "codebase_files": 1,
        },
        {
            "id": "algedonic_signal",
            "canonical_name": "Algedonic Signal",
            "aliases": ["algedonic", "algedonic channel"],
            "definition": "Pain/pleasure signal in the VSM.",
            "domain": "cybernetics_vsm",
            "source_attribution": "Beer, 1972",
            "dharma_interpretation": "AlgedonicChannel class.",
            "related_concepts": ["viable_system_model"],
            "codebase_frequency": 105,
            "codebase_files": 15,
        },
        {
            "id": "viable_system_model",
            "canonical_name": "Viable System Model",
            "aliases": ["VSM", "vsm"],
            "definition": "Beer's model for viable organizations.",
            "domain": "cybernetics_vsm",
            "source_attribution": "Beer, 1972",
            "dharma_interpretation": "vsm_channels.py implements the five systems.",
            "related_concepts": ["algedonic_signal"],
            "codebase_frequency": 10,
            "codebase_files": 6,
        },
        {
            "id": "stigmergy",
            "canonical_name": "Stigmergy",
            "aliases": ["stigmergic"],
            "definition": "Indirect coordination through environment modification.",
            "domain": "stigmergy_swarm",
            "source_attribution": "Grassé, 1959",
            "dharma_interpretation": "Agents coordinate via shared workspace traces.",
            "related_concepts": [],
            "codebase_frequency": 442,
            "codebase_files": 83,
        },
    ],
    "domains": [
        {"id": "autopoiesis", "name": "Autopoiesis", "description": "Self-producing systems",
         "primary_sources": ["Maturana & Varela, 1980"]},
        {"id": "cybernetics_vsm", "name": "Cybernetics / VSM", "description": "Beer's cybernetics",
         "primary_sources": ["Beer, 1972"]},
        {"id": "stigmergy_swarm", "name": "Stigmergy / Swarm", "description": "Indirect coordination",
         "primary_sources": ["Grassé, 1959"]},
    ],
    "relationships": [
        {"source": "autopoiesis", "target": "structural_coupling", "kind": "enables",
         "description": "Autopoietic systems interact through structural coupling"},
        {"source": "algedonic_signal", "target": "viable_system_model", "kind": "part_of",
         "description": "Algedonic signals are part of the VSM System 5"},
    ],
}

SAMPLE_PYTHON = '''\
"""organism.py — The Organism's autopoietic heartbeat.

Implements the Viable System Model (VSM) operational loop.
The heartbeat is the core autopoiesis mechanism — the system
maintaining itself through continuous self-production.

Ground: Maturana & Varela (autopoiesis), Beer (VSM).
"""

import logging

# Algedonic signal handling — pain/pleasure from Beer's VSM
ALGEDONIC_THRESHOLD = 0.5

class OrganismHeartbeat:
    """The VSM System 1 operational loop.

    This is structurally coupled with the agent environment.
    Stigmergy enables indirect coordination between agents.
    """

    def __init__(self):
        self.algedonic_level = 0.0
        self._autopoietic_cycle = 0

    def tick(self):
        """One heartbeat cycle — the autopoietic pulse."""
        self._autopoietic_cycle += 1
        if self.algedonic_level > ALGEDONIC_THRESHOLD:
            self._handle_algedonic_signal()

    def _handle_algedonic_signal(self):
        """Process algedonic activation — Beer's pain signal."""
        pass
'''


@pytest.fixture
def concepts_file(tmp_path):
    """Write mini concepts JSON to a temp file."""
    path = tmp_path / "dharma_concepts.json"
    path.write_text(json.dumps(MINI_CONCEPTS))
    return path


@pytest.fixture
def registry(concepts_file):
    """Create a ConceptRegistry from the mini concepts."""
    return ConceptRegistry(concepts_file)


@pytest.fixture
def parser(registry):
    """Create a ConceptParser."""
    return ConceptParser(registry)


@pytest.fixture
def sample_file(tmp_path):
    """Write sample Python to a temp file."""
    path = tmp_path / "organism.py"
    path.write_text(SAMPLE_PYTHON)
    return path


@pytest.fixture
def graph_store(tmp_path):
    """Create a temporary GraphStore."""
    db_path = tmp_path / "test_graphs.db"
    store = SQLiteGraphStore(str(db_path))
    yield store
    store.close()


# ---------------------------------------------------------------------------
# ConceptRegistry tests
# ---------------------------------------------------------------------------

class TestConceptRegistry:
    def test_load_concepts(self, registry):
        assert len(registry) == 5

    def test_get_concept(self, registry):
        concept = registry.get("autopoiesis")
        assert concept is not None
        assert concept.canonical_name == "Autopoiesis"
        assert concept.domain == "autopoiesis"

    def test_resolve_canonical(self, registry):
        assert registry.resolve("Autopoiesis") == "autopoiesis"

    def test_resolve_alias(self, registry):
        assert registry.resolve("autopoietic") == "autopoiesis"
        assert registry.resolve("self-production") == "autopoiesis"

    def test_resolve_case_insensitive(self, registry):
        assert registry.resolve("AUTOPOIESIS") == "autopoiesis"
        assert registry.resolve("vsm") == "viable_system_model"
        assert registry.resolve("VSM") == "viable_system_model"

    def test_resolve_unknown(self, registry):
        assert registry.resolve("quantum_gravity") is None

    def test_contains(self, registry):
        assert "autopoiesis" in registry
        assert "nonexistent" not in registry

    def test_pattern_built(self, registry):
        assert registry._pattern is not None

    def test_missing_file(self, tmp_path):
        reg = ConceptRegistry(tmp_path / "nonexistent.json")
        assert len(reg) == 0


# ---------------------------------------------------------------------------
# ConceptParser tests
# ---------------------------------------------------------------------------

class TestConceptParser:
    def test_parse_file_returns_extractions(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        assert len(results) > 0
        assert all(isinstance(r, ConceptExtraction) for r in results)

    def test_finds_docstring_concepts(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        docstring_hits = [r for r in results if r.source_type == "docstring"]
        concept_ids = {r.concept_id for r in docstring_hits}
        # The module docstring mentions autopoiesis, VSM
        assert "autopoiesis" in concept_ids

    def test_finds_comment_concepts(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        comment_hits = [r for r in results if r.source_type == "comment"]
        concept_ids = {r.concept_id for r in comment_hits}
        assert "algedonic_signal" in concept_ids

    def test_finds_identifier_concepts(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        id_hits = [r for r in results if r.source_type == "identifier"]
        # _autopoietic_cycle should match autopoiesis via name analysis
        concept_ids = {r.concept_id for r in id_hits}
        # algedonic_level or similar should match
        assert "algedonic_signal" in concept_ids or "autopoiesis" in concept_ids

    def test_confidence_hierarchy(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        for r in results:
            if r.source_type == "docstring":
                assert r.confidence == 0.9
            elif r.source_type == "comment":
                assert r.confidence == 0.85
            elif r.source_type == "identifier":
                assert r.confidence == 0.8
            elif r.source_type == "code":
                assert r.confidence == 0.7

    def test_deduplication(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        # No duplicate (concept_id, line, source_type) tuples
        keys = [(r.concept_id, r.line_number, r.source_type) for r in results]
        assert len(keys) == len(set(keys))

    def test_relative_paths(self, parser, sample_file, tmp_path):
        results = parser.parse_file(sample_file, repo_root=tmp_path)
        for r in results:
            assert r.source_file == "organism.py"

    def test_parse_empty_file(self, parser, tmp_path):
        empty = tmp_path / "empty.py"
        empty.write_text("")
        results = parser.parse_file(empty)
        assert results == []

    def test_parse_syntax_error(self, parser, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def foo(:\n    pass")
        # Should not raise, just return what it can
        results = parser.parse_file(bad)
        # May still find matches in code lines
        assert isinstance(results, list)

    def test_parse_nonexistent(self, parser):
        results = parser.parse_file("/nonexistent/path.py")
        assert results == []

    def test_parse_directory(self, parser, tmp_path):
        # Write two files
        (tmp_path / "a.py").write_text('"""Autopoiesis module."""\n')
        (tmp_path / "b.py").write_text("# Uses stigmergy\n")
        results = parser.parse_directory(tmp_path)
        concept_ids = {r.concept_id for r in results}
        assert "autopoiesis" in concept_ids
        assert "stigmergy" in concept_ids

    def test_extraction_method_field(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        methods = {r.extraction_method for r in results}
        assert "pattern_match" in methods

    def test_context_not_empty(self, parser, sample_file):
        results = parser.parse_file(sample_file)
        for r in results:
            assert r.context, f"Empty context for {r.concept_id} at line {r.line_number}"


# ---------------------------------------------------------------------------
# ConceptIndexer tests
# ---------------------------------------------------------------------------

class TestConceptIndexer:
    def test_index_concepts(self, registry, graph_store):
        indexer = ConceptIndexer(graph_store, registry)
        stats = indexer.index_concepts()
        assert stats["concept_nodes"] == 5
        assert stats["relationship_edges"] > 0

        # Verify nodes exist in semantic graph
        node = graph_store.get_node("semantic", "autopoiesis")
        assert node is not None
        assert node["kind"] == "concept"
        assert node["name"] == "Autopoiesis"
        data = json.loads(node["data"])
        assert data["domain"] == "autopoiesis"

    def test_index_concepts_relationships(self, registry, graph_store):
        indexer = ConceptIndexer(graph_store, registry)
        indexer.index_concepts()

        # Check edges exist
        edges = graph_store.get_edges("semantic", "autopoiesis", direction="out")
        assert len(edges) > 0
        kinds = {e["kind"] for e in edges}
        # Should have both explicit relationship and related_to
        assert "enables" in kinds or "related_to" in kinds

    def test_index_extractions(self, registry, graph_store, parser, sample_file, tmp_path):
        indexer = ConceptIndexer(graph_store, registry)
        indexer.index_concepts()

        extractions = parser.parse_file(sample_file, repo_root=tmp_path)
        stats = indexer.index_extractions(extractions)

        assert stats["bridge_edges"] > 0
        assert stats["files_indexed"] == 1

        # Check bridge edges exist
        bridges = graph_store.get_bridges(
            source_graph="code",
            source_id=None,
            target_graph="semantic",
            target_id="autopoiesis",
        )
        assert len(bridges) > 0
        assert bridges[0]["kind"] == "references_concept"

    def test_full_index(self, registry, graph_store, parser, sample_file, tmp_path):
        indexer = ConceptIndexer(graph_store, registry)
        extractions = parser.parse_file(sample_file, repo_root=tmp_path)
        stats = indexer.full_index(extractions)

        assert "concept_nodes" in stats
        assert "relationship_edges" in stats
        assert "bridge_edges" in stats
        assert "files_indexed" in stats
        assert stats["concept_nodes"] == 5
        assert stats["bridge_edges"] > 0

    def test_file_nodes_created(self, registry, graph_store, parser, sample_file, tmp_path):
        indexer = ConceptIndexer(graph_store, registry)
        extractions = parser.parse_file(sample_file, repo_root=tmp_path)
        indexer.index_extractions(extractions)

        # Verify code graph has a file node
        node = graph_store.get_node("code", "file::organism.py")
        assert node is not None
        assert node["kind"] == "file"

    def test_bridge_evidence(self, registry, graph_store, parser, sample_file, tmp_path):
        indexer = ConceptIndexer(graph_store, registry)
        extractions = parser.parse_file(sample_file, repo_root=tmp_path)
        indexer.index_extractions(extractions)

        bridges = graph_store.get_bridges(
            source_graph="code",
            source_id=None,
            target_graph="semantic",
            target_id=None,
        )
        for bridge in bridges:
            evidence = json.loads(bridge["evidence"])
            assert len(evidence) > 0
            assert "type" in evidence[0]
            assert "line" in evidence[0]


# ---------------------------------------------------------------------------
# Integration test — full pipeline on real concepts file (if available)
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_real_concepts_file_loads(self):
        """Test that the actual dharma_concepts.json loads without error."""
        real_path = Path(__file__).parent.parent / "dharma_swarm" / "dharma_concepts.json"
        if real_path.exists():
            reg = ConceptRegistry(real_path)
            assert len(reg) > 50, f"Expected 50+ concepts, got {len(reg)}"
        else:
            pytest.skip("dharma_concepts.json not found (expected in CI)")

    def test_real_concepts_all_resolvable(self):
        """All concept aliases should resolve to valid concept IDs."""
        real_path = Path(__file__).parent.parent / "dharma_swarm" / "dharma_concepts.json"
        if not real_path.exists():
            pytest.skip("dharma_concepts.json not found")

        reg = ConceptRegistry(real_path)
        for concept in reg.concepts.values():
            # Canonical name should resolve
            resolved = reg.resolve(concept.canonical_name)
            assert resolved == concept.id, (
                f"Canonical name '{concept.canonical_name}' resolved to "
                f"'{resolved}' instead of '{concept.id}'"
            )
            # Each alias should resolve
            for alias in concept.aliases:
                resolved = reg.resolve(alias)
                assert resolved is not None, (
                    f"Alias '{alias}' of concept '{concept.id}' did not resolve"
                )
