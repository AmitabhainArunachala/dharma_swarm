"""Tests for SleepTimeAgent — Phase 6 background memory refinement.

Tests cover:
    - Tick interval gating (only runs every N heartbeats)
    - Phase 1: Entity extraction from pulse history
    - Phase 2: Duplicate consolidation (Jaccard ≥ 0.6)
    - Phase 3: Confidence decay delegation
    - Phase 4: Implicit relationship inference
    - Phase 5: Learned context generation
    - Phase 6: Garbage collection
    - Stats and output API
    - Never-fatal guarantees
"""

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from dharma_swarm.sleep_time_agent import SleepTimeAgent, _jaccard


# ---------------------------------------------------------------------------
# Mock organism + pulse for testing
# ---------------------------------------------------------------------------

class MockPulse:
    """Minimal pulse object for SleepTimeAgent tests."""

    def __init__(
        self,
        cycle: int = 1,
        algedonic_active: int = 0,
        fleet_health: float = 0.95,
        identity_coherence: float = 0.8,
    ):
        self._data = {
            "cycle": cycle,
            "algedonic_active": algedonic_active,
            "fleet_health": fleet_health,
            "identity_coherence": identity_coherence,
        }

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class MockOrganism:
    """Lightweight organism stand-in for SleepTimeAgent tests."""

    def __init__(self, tmp_path: Path):
        from dharma_swarm.organism_memory import OrganismMemory
        from dharma_swarm.memory_palace import MemoryPalace

        self.memory = OrganismMemory(state_dir=tmp_path)
        self.palace = MemoryPalace(state_dir=tmp_path / "palace")
        self._pulses: list[MockPulse] = []

    def add_pulses(self, pulses: list[MockPulse]):
        self._pulses.extend(pulses)


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class TestJaccard:

    def test_identical_strings(self):
        assert _jaccard("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert _jaccard("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap(self):
        sim = _jaccard("the quick brown fox", "the slow brown dog")
        # Shared: {the, brown} = 2, Union: {the, quick, brown, fox, slow, dog} = 6
        assert abs(sim - 2.0 / 6.0) < 0.01

    def test_empty_strings(self):
        assert _jaccard("", "") == 0.0
        assert _jaccard("hello", "") == 0.0


# ---------------------------------------------------------------------------
# Tick interval gating
# ---------------------------------------------------------------------------

class TestTickInterval:

    def test_skips_non_interval_cycles(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=5)
        org = MockOrganism(tmp_path)
        # Cycles 1, 2, 3, 4 should all be skipped
        for cycle in [1, 2, 3, 4]:
            stats = agent.tick(cycle, org)
            assert stats.get("skipped") is True

    def test_runs_on_interval_cycle(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=5)
        org = MockOrganism(tmp_path)
        stats = agent.tick(5, org)
        assert stats.get("skipped") is not True
        assert "phases" in stats
        assert stats["cycle"] == 5

    def test_runs_on_cycle_zero(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=5)
        org = MockOrganism(tmp_path)
        stats = agent.tick(0, org)
        assert stats.get("skipped") is not True

    def test_tick_count_increments(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=5)
        org = MockOrganism(tmp_path)
        agent.tick(5, org)
        agent.tick(10, org)
        assert agent._tick_count == 2


# ---------------------------------------------------------------------------
# Phase 1: Entity extraction
# ---------------------------------------------------------------------------

class TestPhaseExtract:

    def test_extracts_algedonic_events(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        org.add_pulses([
            MockPulse(cycle=1, algedonic_active=2, fleet_health=0.6),
        ])
        stats = agent.tick(1, org)
        extracted = stats["phases"]["extract"]["entities_extracted"]
        assert extracted >= 1
        # Check entity was recorded in memory
        algedonic_entities = org.memory.entities_by_type("algedonic_event", last_n=10)
        assert len(algedonic_entities) >= 1
        assert "Algedonic" in algedonic_entities[0].description

    def test_extracts_degraded_health_insights(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        org.add_pulses([
            MockPulse(cycle=1, fleet_health=0.2, identity_coherence=0.1),
        ])
        stats = agent.tick(1, org)
        extracted = stats["phases"]["extract"]["entities_extracted"]
        assert extracted >= 1
        insights = org.memory.entities_by_type("insight", last_n=10)
        assert any("degraded" in i.description.lower() for i in insights)

    def test_no_extraction_without_pulses(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        stats = agent.tick(1, org)
        assert stats["phases"]["extract"]["entities_extracted"] == 0

    def test_no_duplicate_extraction(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        org.add_pulses([
            MockPulse(cycle=1, algedonic_active=1),
        ])
        # Run twice with the same pulses
        agent.tick(1, org)
        stats = agent.tick(2, org)
        # Second run should not re-extract the same pulse
        assert stats["phases"]["extract"]["entities_extracted"] == 0


# ---------------------------------------------------------------------------
# Phase 2: Consolidation
# ---------------------------------------------------------------------------

class TestPhaseConsolidate:

    def test_consolidates_near_duplicates(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, consolidation_threshold=0.6)
        org = MockOrganism(tmp_path)
        # Use non-insight entity type to avoid auto-invalidation by record_event
        # (record_event calls invalidate_contradicted only for insights)
        org.memory.record_event("decision", "The agent fleet health is very good")
        org.memory.record_event("decision", "The agent fleet health is very good today")
        stats = agent.tick(1, org)
        merged = stats["phases"]["consolidate"]["merged"]
        assert merged >= 1
        # The older one should be invalidated
        valid_decisions = [
            e for e in org.memory._entities
            if e.entity_type == "decision" and e.temporal_valid_to is None
        ]
        # At least one should remain valid
        assert len(valid_decisions) >= 1

    def test_does_not_consolidate_dissimilar(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, consolidation_threshold=0.6)
        org = MockOrganism(tmp_path)
        org.memory.record_event("insight", "Agent routing performance is excellent")
        org.memory.record_event("insight", "Memory palace latency needs improvement")
        stats = agent.tick(1, org)
        merged = stats["phases"]["consolidate"]["merged"]
        assert merged == 0


# ---------------------------------------------------------------------------
# Phase 3: Confidence decay
# ---------------------------------------------------------------------------

class TestPhaseDecay:

    def test_decay_delegates_to_memory(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, decay_rate=0.95, max_age_days=30)
        org = MockOrganism(tmp_path)
        eid = org.memory.record_event("insight", "Old insight for decay")
        entity = org.memory._get_entity(eid)
        entity.ingestion_time = datetime.now(timezone.utc) - timedelta(days=5)
        stats = agent.tick(1, org)
        assert stats["phases"]["decay"]["entities_decayed"] >= 1


# ---------------------------------------------------------------------------
# Phase 4: Implicit relationship inference
# ---------------------------------------------------------------------------

class TestPhaseInfer:

    def test_infers_relationships_from_shared_metadata(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        # Two entities sharing the same agent_id
        org.memory.record_event(
            "insight", "Agent X performed well",
            metadata={"agent_id": "agent_x"},
        )
        org.memory.record_event(
            "decision", "Agent X should scale up",
            metadata={"agent_id": "agent_x"},
        )
        stats = agent.tick(1, org)
        inferred = stats["phases"]["infer"]["relationships_inferred"]
        assert inferred >= 1
        # Check the relationship was recorded
        assert len(org.memory._relationships) >= 1
        rel = org.memory._relationships[0]
        assert rel.rel_type == "preceded"
        assert rel.metadata.get("shared_key") == "agent_id"

    def test_no_inference_without_shared_keys(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        org.memory.record_event("insight", "Standalone entity 1")
        org.memory.record_event("decision", "Standalone entity 2")
        stats = agent.tick(1, org)
        assert stats["phases"]["infer"]["relationships_inferred"] == 0

    def test_inference_capped_at_20(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        # Create 30 entities with the same pulse_cycle
        for i in range(30):
            org.memory.record_event(
                "insight", f"Entity number {i}",
                metadata={"pulse_cycle": 42},
            )
        stats = agent.tick(1, org)
        inferred = stats["phases"]["infer"]["relationships_inferred"]
        assert inferred <= 20


# ---------------------------------------------------------------------------
# Phase 5: Learned context generation
# ---------------------------------------------------------------------------

class TestPhaseContext:

    def test_generates_context_block(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, max_context_entities=5)
        org = MockOrganism(tmp_path)
        for i in range(8):
            org.memory.record_event("insight", f"Important insight number {i}", confidence=0.9)
        stats = agent.tick(1, org)
        context_len = stats["phases"]["context"]["context_length"]
        assert context_len > 0
        context = agent.learned_context()
        assert "[LEARNED CONTEXT" in context
        assert "insight" in context.lower()

    def test_empty_context_without_entities(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        stats = agent.tick(1, org)
        assert stats["phases"]["context"]["context_length"] == 0
        assert agent.learned_context() == ""

    def test_context_excludes_low_confidence(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, max_context_entities=5)
        org = MockOrganism(tmp_path)
        org.memory.record_event("insight", "Low confidence noise", confidence=0.1)
        org.memory.record_event("insight", "High confidence signal", confidence=0.9)
        stats = agent.tick(1, org)
        context = agent.learned_context()
        assert "High confidence" in context
        # Low confidence (0.1 < 0.3 threshold) should be excluded
        assert "Low confidence" not in context


# ---------------------------------------------------------------------------
# Phase 6: Garbage collection
# ---------------------------------------------------------------------------

class TestPhaseGC:

    def test_gc_runs(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1, gc_min_confidence=0.01)
        org = MockOrganism(tmp_path)
        org.memory.record_event("insight", "Garbage insight", confidence=0.005)
        stats = agent.tick(1, org)
        removed = stats["phases"]["gc"]["removed"]
        assert removed >= 1


# ---------------------------------------------------------------------------
# Output API
# ---------------------------------------------------------------------------

class TestOutputAPI:

    def test_learned_context_initially_empty(self):
        agent = SleepTimeAgent()
        assert agent.learned_context() == ""

    def test_stats_structure(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        agent.tick(1, org)
        s = agent.stats()
        assert s["tick_count"] == 1
        assert s["last_tick_cycle"] == 1
        assert s["tick_interval"] == 1
        assert "recent_ticks" in s

    def test_stats_history_capped(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)
        for i in range(150):
            agent.tick(i, org)
        assert len(agent._stats_history) <= 100


# ---------------------------------------------------------------------------
# Never-fatal guarantees
# ---------------------------------------------------------------------------

class TestNeverFatal:

    def test_tick_survives_none_memory(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MagicMock()
        org.memory = None
        org.palace = None
        org._pulses = []
        stats = agent.tick(1, org)
        assert "phases" in stats
        # All phases should complete without crashing

    def test_tick_survives_broken_pulse(self, tmp_path):
        agent = SleepTimeAgent(tick_interval=1)
        org = MockOrganism(tmp_path)

        class BrokenPulse:
            def to_dict(self):
                raise RuntimeError("Pulse exploded")

        org._pulses = [BrokenPulse()]
        stats = agent.tick(1, org)
        # Should not crash — extraction phase should handle the error
        assert "phases" in stats

    def test_tick_survives_missing_attributes(self, tmp_path):
        """Organism without memory/palace attributes should not crash."""
        agent = SleepTimeAgent(tick_interval=1)

        class BarebonesOrganism:
            pass

        stats = agent.tick(1, BarebonesOrganism())
        assert "phases" in stats


# ---------------------------------------------------------------------------
# Memory Palace Phase 6 integration
# ---------------------------------------------------------------------------

class TestMemoryPalacePhase6:
    """Tests for Phase 6 upgrades to MemoryPalace."""

    def test_palace_has_vector_store(self, tmp_path):
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        assert palace._vector_store is not None

    def test_palace_ingest_stores_in_vector_store(self, tmp_path):
        import asyncio
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        doc_id = asyncio.run(palace.ingest(
            "Important knowledge about agent routing",
            "test_source",
            layer="working",
        ))
        assert doc_id != ""
        # Verify it's in the vector store
        vs_stats = palace._vector_store.stats()
        assert vs_stats["total_documents"] >= 1

    def test_palace_recall_uses_vector_store(self, tmp_path):
        import asyncio
        from dharma_swarm.memory_palace import MemoryPalace, PalaceQuery
        palace = MemoryPalace(state_dir=tmp_path)
        # Ingest several documents
        asyncio.run(palace.ingest("Agent heartbeat monitoring system", "heartbeat"))
        asyncio.run(palace.ingest("Memory palace vector retrieval", "palace"))
        asyncio.run(palace.ingest("Evolution mutation strategy results", "evolution"))
        # Recall should use hybrid search
        response = asyncio.run(palace.recall(PalaceQuery(text="heartbeat monitoring")))
        assert len(response.results) > 0

    def test_palace_decay_delegates_to_vector_store(self, tmp_path):
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        # decay with empty store should return 0
        decayed = palace.decay()
        assert decayed == 0

    def test_palace_gc_delegates_to_vector_store(self, tmp_path):
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        removed = palace.gc()
        assert removed == 0

    def test_palace_stats_includes_vector_store(self, tmp_path):
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        s = palace.stats()
        assert "vector_store" in s
        assert "total_documents" in s["vector_store"]

    def test_palace_search_sync(self, tmp_path):
        import asyncio
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(state_dir=tmp_path)
        asyncio.run(palace.ingest("Organism health metrics are stable", "health"))
        asyncio.run(palace.ingest("Agent viability scores need attention", "vsm"))
        results = palace.search("organism health", top_k=5)
        assert len(results) >= 1
        assert "text" in results[0]
        assert "score" in results[0]
