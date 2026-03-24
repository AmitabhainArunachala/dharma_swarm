"""Tests for OrganismMemory Phase 6 upgrades.

Tests cover:
    - Bi-temporal fields: ingestion_time, event_time
    - Access tracking: access_count, last_accessed
    - Entity invalidation: invalidate_entity(), invalidate_contradicted()
    - Graph traversal: graph_traverse() (BFS), find_related()
    - Confidence decay: age-based exponential decay
    - Garbage collection: soft-delete below threshold
    - Backward compatibility: old JSONL records without Phase 6 fields
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from dharma_swarm.organism_memory import (
    MemoryEntity,
    MemoryRelationship,
    OrganismMemory,
)


# ---------------------------------------------------------------------------
# Bi-temporal fields
# ---------------------------------------------------------------------------

class TestBiTemporalFields:

    def test_entity_has_ingestion_time(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Test insight", confidence=0.9)
        entity = mem._get_entity(eid)
        assert entity is not None
        assert entity.ingestion_time is not None
        assert isinstance(entity.ingestion_time, datetime)

    def test_event_time_equals_timestamp(self, tmp_path):
        """timestamp IS the event_time in our model."""
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("decision", "Scaling decision")
        entity = mem._get_entity(eid)
        # Both should be set to approximately the same time
        delta = abs((entity.timestamp - entity.ingestion_time).total_seconds())
        assert delta < 1.0  # Within 1 second

    def test_backward_compat_missing_ingestion_time(self, tmp_path):
        """Old JSONL records without ingestion_time should load with defaults."""
        state_dir = tmp_path / "organism_memory"
        state_dir.mkdir(parents=True)
        # Write an old-format record without Phase 6 fields
        old_record = {
            "type": "entity",
            "id": "e_old_test_12345",
            "entity_type": "insight",
            "description": "Legacy insight from Phase 4",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "metadata": {},
            "confidence": 0.8,
            "temporal_valid_from": None,
            "temporal_valid_to": None,
            # No ingestion_time, access_count, last_accessed
        }
        (state_dir / "entities.jsonl").write_text(json.dumps(old_record) + "\n")

        mem = OrganismMemory(state_dir=tmp_path)
        assert len(mem._entities) == 1
        entity = mem._entities[0]
        assert entity.ingestion_time is not None  # Pydantic default
        assert entity.access_count == 0
        assert entity.last_accessed is None


# ---------------------------------------------------------------------------
# Access tracking
# ---------------------------------------------------------------------------

class TestAccessTracking:

    def test_initial_access_count_is_zero(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Fresh insight")
        entity = mem._get_entity(eid)
        assert entity.access_count == 0
        assert entity.last_accessed is None

    def test_touch_increments_access(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Touched insight")
        entity = mem._get_entity(eid)
        mem._touch_entity(entity)
        assert entity.access_count == 1
        assert entity.last_accessed is not None
        mem._touch_entity(entity)
        assert entity.access_count == 2


# ---------------------------------------------------------------------------
# Entity invalidation
# ---------------------------------------------------------------------------

class TestEntityInvalidation:

    def test_invalidate_entity_sets_valid_to(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Will be invalidated")
        assert mem.invalidate_entity(eid, reason="test_reason")
        entity = mem._get_entity(eid)
        assert entity.temporal_valid_to is not None
        assert entity.metadata.get("invalidation_reason") == "test_reason"

    def test_invalidate_nonexistent_returns_false(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        assert not mem.invalidate_entity("nonexistent_id")

    def test_invalidate_contradicted_supersedes_similar(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        # Add an older insight
        eid1 = mem.record_event("insight", "The organism health is very good and stable")
        # Add a newer insight with similar words
        eid2 = mem.record_event("insight", "The organism health is very good and improving")
        # The old insight should be superseded
        old = mem._get_entity(eid1)
        assert old.temporal_valid_to is not None
        assert old.metadata.get("superseded_by") == eid2

    def test_invalidate_contradicted_ignores_dissimilar(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid1 = mem.record_event("insight", "Agent routing performs well")
        eid2 = mem.record_event("insight", "Memory latency is a concern")
        # Different enough — old should NOT be superseded
        old = mem._get_entity(eid1)
        assert old.temporal_valid_to is None

    def test_invalidate_contradicted_only_affects_insights(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid1 = mem.record_event("decision", "The organism health is very good and stable")
        eid2 = mem.record_event("insight", "The organism health is very good and stable")
        # The decision entity should NOT be invalidated (only insights)
        decision = mem._get_entity(eid1)
        assert decision.temporal_valid_to is None

    def test_invalidated_entity_persists_to_disk(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Persistent invalidation test")
        mem.invalidate_entity(eid, reason="disk_test")
        # Reload from disk
        mem2 = OrganismMemory(state_dir=tmp_path)
        entity = mem2._get_entity(eid)
        assert entity is not None
        assert entity.temporal_valid_to is not None


# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------

class TestGraphTraversal:

    def _build_graph(self, tmp_path):
        """Build a small test graph: A → B → C, A → D."""
        mem = OrganismMemory(state_dir=tmp_path)
        a = mem.record_event("insight", "Node A")
        b = mem.record_event("decision", "Node B")
        c = mem.record_event("mutation", "Node C")
        d = mem.record_event("capability", "Node D")
        mem.record_relationship(a, b, "caused")
        mem.record_relationship(b, c, "preceded")
        mem.record_relationship(a, d, "enabled")
        return mem, a, b, c, d

    def test_traverse_depth_1(self, tmp_path):
        mem, a, b, c, d = self._build_graph(tmp_path)
        result = mem.graph_traverse(a, max_depth=1, direction="out")
        ids = [e.id for e in result]
        assert b in ids
        assert d in ids
        # C should NOT be reachable at depth 1
        assert c not in ids

    def test_traverse_depth_2(self, tmp_path):
        mem, a, b, c, d = self._build_graph(tmp_path)
        result = mem.graph_traverse(a, max_depth=2, direction="out")
        ids = [e.id for e in result]
        assert b in ids
        assert c in ids
        assert d in ids

    def test_traverse_in_direction(self, tmp_path):
        mem, a, b, c, d = self._build_graph(tmp_path)
        # From C going IN → should reach B (depth 1)
        result = mem.graph_traverse(c, max_depth=1, direction="in")
        ids = [e.id for e in result]
        assert b in ids
        assert a not in ids  # A is 2 hops away in reverse

    def test_traverse_both_directions(self, tmp_path):
        mem, a, b, c, d = self._build_graph(tmp_path)
        result = mem.graph_traverse(b, max_depth=1, direction="both")
        ids = [e.id for e in result]
        assert a in ids  # incoming
        assert c in ids  # outgoing

    def test_traverse_nonexistent_start(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        result = mem.graph_traverse("nonexistent_id", max_depth=2)
        assert result == []

    def test_traverse_skips_invalidated_edges(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        a = mem.record_event("insight", "Node A")
        b = mem.record_event("insight", "Node B")
        mem.record_relationship(a, b, "caused")
        # Manually invalidate the relationship
        mem._relationships[0].valid_until = datetime.now(timezone.utc)
        result = mem.graph_traverse(a, max_depth=1, direction="out")
        assert len(result) == 0  # Edge is invalidated


class TestFindRelated:

    def test_find_related_returns_neighbors(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        a = mem.record_event("insight", "Center node")
        b = mem.record_event("decision", "Related node 1")
        c = mem.record_event("mutation", "Related node 2")
        mem.record_relationship(a, b, "caused")
        mem.record_relationship(a, c, "enabled")
        related = mem.find_related(a)
        assert len(related) == 2
        # Each tuple is (entity, relationship)
        ids = [e.id for e, r in related]
        assert b in ids
        assert c in ids

    def test_find_related_with_type_filter(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        a = mem.record_event("insight", "Center")
        b = mem.record_event("decision", "Caused node")
        c = mem.record_event("mutation", "Enabled node")
        mem.record_relationship(a, b, "caused")
        mem.record_relationship(a, c, "enabled")
        # Filter to only "caused" relationships
        related = mem.find_related(a, rel_types=["caused"])
        assert len(related) == 1
        assert related[0][0].id == b


# ---------------------------------------------------------------------------
# Confidence decay
# ---------------------------------------------------------------------------

class TestConfidenceDecay:

    def test_decay_reduces_confidence(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Aging insight", confidence=1.0)
        entity = mem._get_entity(eid)
        # Backdate ingestion_time by 10 days
        entity.ingestion_time = datetime.now(timezone.utc) - timedelta(days=10)
        updated = mem.decay_confidence(max_age_days=30, decay_rate=0.95)
        assert updated >= 1
        assert entity.confidence < 1.0
        # 0.95^10 ≈ 0.5987
        assert entity.confidence < 0.65
        assert entity.confidence > 0.50

    def test_decay_skips_invalidated(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Invalidated insight")
        mem.invalidate_entity(eid)
        updated = mem.decay_confidence()
        assert updated == 0

    def test_decay_no_change_for_fresh_entities(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("insight", "Just created")
        updated = mem.decay_confidence()
        # Fresh entity (< 1 second old) — insignificant decay
        assert updated == 0


# ---------------------------------------------------------------------------
# Garbage collection
# ---------------------------------------------------------------------------

class TestGarbageCollection:

    def test_gc_soft_deletes_low_confidence(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Low confidence insight", confidence=0.005)
        removed = mem.gc(min_confidence=0.01)
        assert removed >= 1
        entity = mem._get_entity(eid)
        assert entity.temporal_valid_to is not None
        assert "gc_reason" in entity.metadata

    def test_gc_preserves_high_confidence(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Solid insight", confidence=0.9)
        removed = mem.gc(min_confidence=0.01)
        assert removed == 0
        entity = mem._get_entity(eid)
        assert entity.temporal_valid_to is None

    def test_gc_skips_already_invalid(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Already dead", confidence=0.005)
        mem.invalidate_entity(eid)
        removed = mem.gc(min_confidence=0.01)
        assert removed == 0  # Already invalid, should not re-gc


# ---------------------------------------------------------------------------
# Relationship valid_until (Phase 6 edge invalidation)
# ---------------------------------------------------------------------------

class TestRelationshipInvalidation:

    def test_relationship_has_valid_until_field(self, tmp_path):
        rel = MemoryRelationship(
            from_id="a", to_id="b", rel_type="caused"
        )
        assert rel.valid_until is None

    def test_relationship_backward_compat(self, tmp_path):
        """Old relationship records without valid_until should load fine."""
        state_dir = tmp_path / "organism_memory"
        state_dir.mkdir(parents=True)
        old_rel = {
            "type": "relationship",
            "from_id": "a",
            "to_id": "b",
            "rel_type": "caused",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "metadata": {},
            # No valid_until field
        }
        (state_dir / "relationships.jsonl").write_text(json.dumps(old_rel) + "\n")
        mem = OrganismMemory(state_dir=tmp_path)
        assert len(mem._relationships) == 1
        assert mem._relationships[0].valid_until is None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestOrganismMemoryStats:

    def test_stats_counts(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("insight", "Insight 1")
        mem.record_event("decision", "Decision 1")
        mem.record_event("mutation", "Mutation 1")
        s = mem.stats()
        assert s["total_entities"] == 3
        assert s["valid_entities"] == 3
        assert s["total_relationships"] == 0
        assert "insight" in s["by_type"]
        assert "decision" in s["by_type"]

    def test_stats_reflects_invalidation(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Will invalidate")
        mem.record_event("decision", "Will keep")
        mem.invalidate_entity(eid)
        s = mem.stats()
        assert s["total_entities"] == 2
        assert s["valid_entities"] == 1


# ---------------------------------------------------------------------------
# Developmental narrative
# ---------------------------------------------------------------------------

class TestDevelopmentalNarrative:

    def test_narrative_includes_invalidated_marker(self, tmp_path):
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("insight", "Old insight")
        mem.invalidate_entity(eid)
        mem.record_event("insight", "New insight")
        narrative = mem.developmental_narrative()
        assert "[INVALIDATED]" in narrative
        assert "New insight" in narrative
