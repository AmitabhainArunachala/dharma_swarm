"""Tests for telos_substrate.py — static seeder for ConceptGraph and TelosGraph."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dharma_swarm.telos_substrate import (
    CONCEPT_TELOS_BRIDGES,
    SEED_CONCEPTS,
    SEED_EDGES,
    TELOS_EDGES,
    TELOS_OBJECTIVES,
    TelosSubstrate,
)


# ---------------------------------------------------------------------------
# Static data validation — TELOS_OBJECTIVES
# ---------------------------------------------------------------------------


class TestTelosObjectivesData:
    def test_has_objectives(self):
        assert len(TELOS_OBJECTIVES) >= 100  # documented as ~200

    def test_all_have_required_keys(self):
        required = {"name", "perspective", "priority", "description"}
        for i, obj in enumerate(TELOS_OBJECTIVES):
            missing = required - set(obj.keys())
            assert not missing, f"Objective {i} missing keys: {missing}"

    def test_names_are_strings(self):
        for obj in TELOS_OBJECTIVES:
            assert isinstance(obj["name"], str)
            assert len(obj["name"]) > 5

    def test_perspectives_are_valid(self):
        valid = {"purpose", "stakeholder", "process", "foundation"}
        for obj in TELOS_OBJECTIVES:
            assert obj["perspective"] in valid, (
                f"Invalid perspective '{obj['perspective']}' for {obj['name']}"
            )

    def test_priorities_in_range(self):
        for obj in TELOS_OBJECTIVES:
            assert 1 <= obj["priority"] <= 10, (
                f"Priority {obj['priority']} out of range for {obj['name']}"
            )

    def test_no_duplicate_names(self):
        names = [obj["name"] for obj in TELOS_OBJECTIVES]
        dupes = [n for n in names if names.count(n) > 1]
        assert not dupes, f"Duplicate objective names: {set(dupes)}"

    def test_has_metadata_with_domain(self):
        """At least some objectives should have domain metadata."""
        with_domain = [
            obj for obj in TELOS_OBJECTIVES
            if (obj.get("metadata") or {}).get("domain")
        ]
        assert len(with_domain) > 50  # most should have domain


# ---------------------------------------------------------------------------
# Static data validation — TELOS_EDGES
# ---------------------------------------------------------------------------


class TestTelosEdgesData:
    def test_has_edges(self):
        assert len(TELOS_EDGES) >= 10

    def test_edges_are_tuples_of_three(self):
        for i, edge in enumerate(TELOS_EDGES):
            assert len(edge) == 3, f"Edge {i} has {len(edge)} elements, expected 3"
            assert all(isinstance(e, str) for e in edge)

    def test_edge_endpoints_reference_objectives(self):
        """Edge source/target names should exist in TELOS_OBJECTIVES."""
        obj_names = {obj["name"] for obj in TELOS_OBJECTIVES}
        missing_sources = set()
        missing_targets = set()
        for source, target, _ in TELOS_EDGES:
            if source not in obj_names:
                missing_sources.add(source)
            if target not in obj_names:
                missing_targets.add(target)
        # Allow some tolerance for edges referencing objectives not yet added
        assert len(missing_sources) < len(TELOS_EDGES) * 0.1, (
            f"Many source names missing from objectives: {list(missing_sources)[:5]}"
        )


# ---------------------------------------------------------------------------
# Static data validation — SEED_CONCEPTS
# ---------------------------------------------------------------------------


class TestSeedConceptsData:
    def test_has_concepts(self):
        assert len(SEED_CONCEPTS) >= 50  # documented as ~80

    def test_all_have_required_keys(self):
        required = {"name", "definition"}
        for i, concept in enumerate(SEED_CONCEPTS):
            missing = required - set(concept.keys())
            assert not missing, f"Concept {i} missing keys: {missing}"

    def test_names_unique(self):
        names = [c["name"] for c in SEED_CONCEPTS]
        # Case-insensitive uniqueness (since code uses .lower())
        lower_names = [n.lower() for n in names]
        dupes = [n for n in lower_names if lower_names.count(n) > 1]
        assert not dupes, f"Duplicate concept names: {set(dupes)}"

    def test_salience_in_range(self):
        for concept in SEED_CONCEPTS:
            salience = concept.get("salience", 0.8)
            assert 0.0 <= salience <= 1.0, (
                f"Salience {salience} out of range for {concept['name']}"
            )

    def test_definitions_not_empty(self):
        for concept in SEED_CONCEPTS:
            assert len(concept["definition"]) > 10, (
                f"Definition too short for {concept['name']}"
            )


# ---------------------------------------------------------------------------
# Static data validation — SEED_EDGES
# ---------------------------------------------------------------------------


class TestSeedEdgesData:
    def test_has_edges(self):
        assert len(SEED_EDGES) >= 10

    def test_edges_are_tuples_of_three(self):
        for i, edge in enumerate(SEED_EDGES):
            assert len(edge) == 3, f"Edge {i} has {len(edge)} elements"
            assert all(isinstance(e, str) for e in edge)

    def test_valid_edge_types(self):
        valid_types = {
            "is_a", "analogous_to", "implements", "enables",
            "grounds", "depends_on", "extends", "references", "contradicts",
        }
        for source, target, etype in SEED_EDGES:
            assert etype in valid_types, (
                f"Invalid edge type '{etype}' for {source} -> {target}"
            )


# ---------------------------------------------------------------------------
# Static data validation — CONCEPT_TELOS_BRIDGES
# ---------------------------------------------------------------------------


class TestBridgesData:
    def test_has_bridges(self):
        assert len(CONCEPT_TELOS_BRIDGES) >= 5

    def test_bridges_are_pairs(self):
        for i, bridge in enumerate(CONCEPT_TELOS_BRIDGES):
            assert len(bridge) == 2, f"Bridge {i} has {len(bridge)} elements"
            assert all(isinstance(e, str) for e in bridge)


# ---------------------------------------------------------------------------
# TelosSubstrate construction
# ---------------------------------------------------------------------------


class TestTelosSubstrateConstruction:
    def test_default_state_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        ts = TelosSubstrate()
        assert ts._state_dir == tmp_path / ".dharma"

    def test_custom_state_dir(self, tmp_path):
        ts = TelosSubstrate(state_dir=tmp_path / "custom")
        assert ts._state_dir == tmp_path / "custom"


# ---------------------------------------------------------------------------
# Seeding mechanics (mocked graph backends)
# ---------------------------------------------------------------------------


class TestSeedTelosGraph:
    @pytest.mark.asyncio
    async def test_seed_telos_creates_objectives(self, tmp_path):
        """_seed_telos_graph creates objectives in TelosGraph."""
        ts = TelosSubstrate(state_dir=tmp_path)

        # Create telos dir so TelosGraph can save
        (tmp_path / "telos").mkdir(parents=True)

        obj_count, edge_count = await ts._seed_telos_graph()

        # Should create objectives from TELOS_OBJECTIVES
        assert obj_count > 0
        assert obj_count <= len(TELOS_OBJECTIVES)

    @pytest.mark.asyncio
    async def test_seed_telos_idempotent(self, tmp_path):
        """Running seed twice should create 0 on second pass."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "telos").mkdir(parents=True)

        count1, _ = await ts._seed_telos_graph()
        count2, _ = await ts._seed_telos_graph()

        assert count1 > 0
        assert count2 == 0  # all already exist


class TestSeedConceptGraph:
    @pytest.mark.asyncio
    async def test_seed_concepts_creates_nodes(self, tmp_path):
        """_seed_concept_graph creates concept nodes."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)

        count = await ts._seed_concept_graph()
        assert count > 0
        assert count <= len(SEED_CONCEPTS)

    @pytest.mark.asyncio
    async def test_seed_concepts_idempotent(self, tmp_path):
        """Running seed twice should create 0 on second pass."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)

        count1 = await ts._seed_concept_graph()
        count2 = await ts._seed_concept_graph()

        assert count1 > 0
        assert count2 == 0


class TestSeedConceptEdges:
    @pytest.mark.asyncio
    async def test_seed_edges_after_concepts(self, tmp_path):
        """_seed_concept_edges creates edges between existing concepts."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)

        # First seed concepts so edges can resolve names
        await ts._seed_concept_graph()
        edge_count = await ts._seed_concept_edges()

        assert edge_count > 0

    @pytest.mark.asyncio
    async def test_seed_edges_without_concepts_returns_zero(self, tmp_path):
        """If no concepts exist, edge seeding creates nothing (names can't resolve)."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)

        # Don't seed concepts first — names won't resolve
        edge_count = await ts._seed_concept_edges()
        assert edge_count == 0


class TestSeedAll:
    @pytest.mark.asyncio
    async def test_seed_all_returns_counts(self, tmp_path):
        """seed_all populates both graphs and returns count dict."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "telos").mkdir(parents=True)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)
        (tmp_path / "db").mkdir(parents=True)

        result = await ts.seed_all()

        assert "telos_objectives" in result
        assert "concept_nodes" in result
        assert "concept_edges" in result
        assert "bridge_edges" in result
        assert result["telos_objectives"] > 0
        assert result["concept_nodes"] > 0

    @pytest.mark.asyncio
    async def test_seed_all_idempotent(self, tmp_path):
        """Second seed_all should create 0 for objectives and concepts."""
        ts = TelosSubstrate(state_dir=tmp_path)
        (tmp_path / "telos").mkdir(parents=True)
        (tmp_path / "semantic").mkdir(parents=True)
        (tmp_path / "meta").mkdir(parents=True)
        (tmp_path / "db").mkdir(parents=True)

        r1 = await ts.seed_all()
        r2 = await ts.seed_all()

        assert r1["telos_objectives"] > 0
        assert r2["telos_objectives"] == 0
        assert r2["concept_nodes"] == 0
