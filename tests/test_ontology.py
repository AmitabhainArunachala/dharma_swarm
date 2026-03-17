"""Tests for dharma_swarm.ontology — unified entity model."""

from datetime import date
from pathlib import Path

import pytest

from dharma_swarm.ontology import (
    ONTOLOGY,
    Entity,
    blocked_entities,
    deadline_pressure,
    deadline_summary,
    entities_by_type,
    entity_context,
    entity_graph,
)


class TestOntologyRegistry:
    def test_ontology_not_empty(self):
        assert len(ONTOLOGY) >= 15

    def test_all_entities_have_required_fields(self):
        for eid, entity in ONTOLOGY.items():
            assert entity.id == eid
            assert entity.type in {
                "research_paper", "application", "module",
                "infrastructure", "knowledge_base", "venture_cell",
            }
            assert isinstance(entity.canonical_path, Path)
            assert entity.status in {"active", "submitted", "blocked", "dormant", "complete"}
            assert entity.description

    def test_known_entities_exist(self):
        expected = {
            "rv_paper", "ura_paper", "grant_app", "welfare_calc",
            "dharma_swarm", "mech_interp_lab", "prompt_bank",
            "psmv", "kailash_vault", "agni_vps", "jagat_kalyan",
        }
        assert expected.issubset(set(ONTOLOGY.keys()))

    def test_rv_paper_has_deadline(self):
        rv = ONTOLOGY["rv_paper"]
        assert rv.deadline == date(2026, 3, 31)
        assert rv.type == "research_paper"

    def test_relationships_are_well_formed(self):
        for entity in ONTOLOGY.values():
            for rel in entity.relationships:
                assert ":" in rel, f"{entity.id} has malformed relationship: {rel}"
                kind, target = rel.split(":", 1)
                assert kind in {"depends_on", "blocks", "feeds"}


class TestEntitiesByType:
    def test_research_papers(self):
        papers = entities_by_type("research_paper")
        assert len(papers) >= 2
        ids = {p.id for p in papers}
        assert "rv_paper" in ids
        assert "ura_paper" in ids

    def test_infrastructure(self):
        infra = entities_by_type("infrastructure")
        assert len(infra) >= 2

    def test_nonexistent_type_returns_empty(self):
        assert entities_by_type("nonexistent") == []


class TestEntityGraph:
    def test_returns_adjacency_list(self):
        graph = entity_graph()
        assert isinstance(graph, dict)
        assert len(graph) == len(ONTOLOGY)

    def test_rv_paper_dependencies(self):
        graph = entity_graph()
        assert "mech_interp_lab" in graph["rv_paper"]
        assert "prompt_bank" in graph["rv_paper"]

    def test_no_orphan_targets(self):
        """All relationship targets should reference existing entities."""
        graph = entity_graph()
        all_ids = set(ONTOLOGY.keys())
        for source, targets in graph.items():
            for target in targets:
                assert target in all_ids, (
                    f"{source} references unknown entity '{target}'"
                )


class TestDeadlinePressure:
    def test_returns_sorted_by_date(self):
        entities = deadline_pressure()
        assert len(entities) >= 1
        dates = [e.deadline for e in entities]
        assert dates == sorted(dates)

    def test_rv_paper_in_deadlines(self):
        entities = deadline_pressure()
        ids = {e.id for e in entities}
        assert "rv_paper" in ids

    def test_entities_without_deadlines_excluded(self):
        entities = deadline_pressure()
        assert all(e.deadline is not None for e in entities)


class TestDeadlineSummary:
    def test_returns_string(self):
        summary = deadline_summary()
        assert isinstance(summary, str)
        assert "rv_paper" in summary

    def test_contains_day_counts(self):
        summary = deadline_summary()
        assert "d" in summary  # e.g. "17d"


class TestEntityContext:
    def test_known_entity(self):
        ctx = entity_context("rv_paper")
        assert "rv_paper" in ctx
        assert "COLM" in ctx
        assert "Deadline" in ctx

    def test_unknown_entity(self):
        ctx = entity_context("nonexistent_thing")
        assert "Unknown" in ctx

    def test_entity_without_deadline(self):
        ctx = entity_context("psmv")
        assert "Deadline" not in ctx
        assert "psmv" in ctx


class TestBlockedEntities:
    def test_returns_list(self):
        blocked = blocked_entities()
        assert isinstance(blocked, list)
        # Currently nothing should be blocked
        for e in blocked:
            assert e.status == "blocked"
