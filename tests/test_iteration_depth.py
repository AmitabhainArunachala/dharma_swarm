"""Tests for the Iteration Depth Tracker (quality ratchet)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm import iteration_depth
from dharma_swarm.iteration_depth import (
    CompoundingQueue,
    Initiative,
    InitiativeStatus,
    IterationLedger,
    IterationRecord,
    QueueItem,
    MIN_ITERATIONS_FOR_SOLID,
    MIN_QUALITY_FOR_SOLID,
    MIN_QUALITY_FOR_SHIPPED,
)


@pytest.fixture(autouse=True)
def isolate_iteration_dir(tmp_path, monkeypatch):
    """Redirect iteration storage to a temp directory."""
    iter_dir = tmp_path / "iteration"
    monkeypatch.setattr(iteration_depth, "ITERATION_DIR", iter_dir)
    monkeypatch.setattr(iteration_depth, "INITIATIVES_FILE", iter_dir / "initiatives.jsonl")
    monkeypatch.setattr(iteration_depth, "QUEUE_FILE", iter_dir / "queue.jsonl")


# ── Initiative Model ─────────────────────────────────────────────────


class TestInitiativeModel:
    def test_default_status_is_seed(self):
        init = Initiative(title="Test")
        assert init.status == InitiativeStatus.SEED
        assert init.iteration_count == 0
        assert init.quality_score == 0.0

    def test_compute_quality(self):
        init = Initiative(
            title="Test",
            has_tests=1.0,
            tests_pass=1.0,
            integrated=0.5,
            documented=0.5,
            real_usage=0.0,
        )
        q = init.compute_quality()
        assert q == pytest.approx(0.6, abs=0.001)

    def test_can_promote_to_solid_false_low_iterations(self):
        init = Initiative(title="Test", iteration_count=1, quality_score=0.9)
        assert init.can_promote_to_solid() is False

    def test_can_promote_to_solid_false_low_quality(self):
        init = Initiative(title="Test", iteration_count=5, quality_score=0.3)
        assert init.can_promote_to_solid() is False

    def test_can_promote_to_solid_true(self):
        init = Initiative(
            title="Test",
            iteration_count=MIN_ITERATIONS_FOR_SOLID,
            quality_score=MIN_QUALITY_FOR_SOLID,
        )
        assert init.can_promote_to_solid() is True

    def test_can_promote_to_shipped(self):
        init = Initiative(
            title="Test",
            status=InitiativeStatus.SOLID,
            quality_score=MIN_QUALITY_FOR_SHIPPED,
        )
        assert init.can_promote_to_shipped() is True

    def test_can_promote_to_shipped_not_solid(self):
        init = Initiative(
            title="Test",
            status=InitiativeStatus.GROWING,
            quality_score=0.9,
        )
        assert init.can_promote_to_shipped() is False

    def test_serialization_roundtrip(self):
        init = Initiative(title="Roundtrip Test", tags=["a", "b"])
        data = json.loads(init.model_dump_json())
        restored = Initiative(**data)
        assert restored.title == init.title
        assert restored.tags == ["a", "b"]


# ── Iteration Ledger ─────────────────────────────────────────────────


class TestIterationLedger:
    def test_create_and_load(self):
        ledger = IterationLedger()
        init = ledger.create("My Feature", description="cool stuff")
        assert init.status == InitiativeStatus.SEED

        # Reload from disk
        ledger2 = IterationLedger()
        loaded = ledger2.load()
        assert len(loaded) == 1
        assert loaded[0].title == "My Feature"

    def test_get_active_excludes_abandoned(self):
        ledger = IterationLedger()
        a = ledger.create("Active One")
        b = ledger.create("To Abandon")
        ledger.abandon(b.id, "no longer needed")

        active = ledger.get_active()
        assert len(active) == 1
        assert active[0].id == a.id

    def test_record_iteration_increments_count(self):
        ledger = IterationLedger()
        init = ledger.create("Iterating Feature")
        updated = ledger.record_iteration(init.id, "added tests", evidence="5 tests")
        assert updated.iteration_count == 1
        assert updated.status == InitiativeStatus.GROWING  # auto-promoted from seed

    def test_quality_ratchet_only_increases(self):
        ledger = IterationLedger()
        init = ledger.create("Ratchet Test")

        # Set quality high
        ledger.record_iteration(
            init.id, "first pass",
            quality_updates={"has_tests": 0.8, "tests_pass": 0.9},
        )
        after_first = ledger.get(init.id)
        assert after_first.has_tests == 0.8
        assert after_first.tests_pass == 0.9

        # Try to reduce quality — should not decrease (ratchet)
        ledger.record_iteration(
            init.id, "bad pass",
            quality_updates={"has_tests": 0.3, "tests_pass": 0.1},
        )
        after_second = ledger.get(init.id)
        assert after_second.has_tests == 0.8  # ratchet: kept higher
        assert after_second.tests_pass == 0.9  # ratchet: kept higher

    def test_record_iteration_nonexistent(self):
        ledger = IterationLedger()
        assert ledger.record_iteration("nope", "action") is None

    def test_promote_growing_to_solid_blocked(self):
        ledger = IterationLedger()
        init = ledger.create("Shallow Feature")
        ledger.record_iteration(init.id, "one pass")

        ok, reason = ledger.promote(init.id)
        assert ok is False
        assert "Not ready for solid" in reason

    def test_promote_growing_to_solid_success(self):
        ledger = IterationLedger()
        init = ledger.create("Deep Feature")

        # Build up iterations and quality (avg must be >= 0.7)
        for i in range(MIN_ITERATIONS_FOR_SOLID):
            ledger.record_iteration(
                init.id, f"iteration {i+1}",
                quality_updates={
                    "has_tests": 1.0,
                    "tests_pass": 1.0,
                    "integrated": 0.8,
                    "documented": 0.5,
                    "real_usage": 0.5,
                },
            )

        ok, reason = ledger.promote(init.id)
        assert ok is True
        assert ledger.get(init.id).status == InitiativeStatus.SOLID

    def test_promote_solid_to_shipped(self):
        ledger = IterationLedger()
        init = ledger.create("Ship-ready")

        # Get to solid first
        for i in range(MIN_ITERATIONS_FOR_SOLID):
            ledger.record_iteration(
                init.id, f"iter {i}",
                quality_updates={
                    "has_tests": 1.0,
                    "tests_pass": 1.0,
                    "integrated": 0.8,
                    "documented": 0.7,
                    "real_usage": 0.8,
                },
            )
        ledger.promote(init.id)
        assert ledger.get(init.id).status == InitiativeStatus.SOLID

        ok, reason = ledger.promote(init.id)
        assert ok is True
        assert ledger.get(init.id).status == InitiativeStatus.SHIPPED

    def test_abandon_logs_reason(self):
        ledger = IterationLedger()
        init = ledger.create("Doomed")
        assert ledger.abandon(init.id, "scope changed") is True

        abandoned = ledger.get(init.id)
        assert abandoned.status == InitiativeStatus.ABANDONED
        assert abandoned.abandon_reason == "scope changed"
        assert any("ABANDONED" in h.action for h in abandoned.history)

    def test_abandon_nonexistent(self):
        ledger = IterationLedger()
        assert ledger.abandon("nope", "reason") is False

    def test_promote_nonexistent(self):
        ledger = IterationLedger()
        ledger.load()
        ok, reason = ledger.promote("nope")
        assert ok is False

    def test_get_by_status(self):
        ledger = IterationLedger()
        ledger.create("Seed A")
        b = ledger.create("Seed B")
        ledger.record_iteration(b.id, "grow it")

        seeds = ledger.get_by_status(InitiativeStatus.SEED)
        growing = ledger.get_by_status(InitiativeStatus.GROWING)
        assert len(seeds) == 1
        assert len(growing) == 1

    def test_summary(self):
        ledger = IterationLedger()
        ledger.create("Feature A")
        b = ledger.create("Feature B")
        ledger.record_iteration(b.id, "first pass")

        summary = ledger.summary()
        assert summary["total"] == 2
        assert summary["active_count"] == 2
        assert summary["shallow_count"] == 2  # both below MIN_ITERATIONS_FOR_SOLID

    def test_persistence_across_instances(self):
        """Anti-amnesia: data survives reload."""
        ledger1 = IterationLedger()
        init = ledger1.create("Persistent")
        ledger1.record_iteration(init.id, "first", quality_updates={"has_tests": 0.5})

        ledger2 = IterationLedger()
        loaded = ledger2.load()
        assert len(loaded) == 1
        assert loaded[0].iteration_count == 1
        assert loaded[0].has_tests == 0.5


# ── Compounding Queue ────────────────────────────────────────────────


class TestCompoundingQueue:
    def test_add_and_load(self):
        queue = CompoundingQueue()
        item = queue.add("init_1", "add more tests", priority=0.8)
        assert item.initiative_id == "init_1"

        queue2 = CompoundingQueue()
        loaded = queue2.load()
        assert len(loaded) == 1
        assert loaded[0].task == "add more tests"

    def test_get_pending_sorted(self):
        queue = CompoundingQueue()
        queue.add("a", "low priority", priority=0.2)
        queue.add("b", "high priority", priority=0.9)
        queue.add("c", "medium priority", priority=0.5)

        pending = queue.get_pending()
        assert len(pending) == 3
        assert pending[0].task == "high priority"
        assert pending[-1].task == "low priority"

    def test_complete(self):
        queue = CompoundingQueue()
        item = queue.add("a", "do thing")
        assert queue.complete(item.id) is True

        pending = queue.get_pending()
        assert len(pending) == 0

    def test_complete_nonexistent(self):
        queue = CompoundingQueue()
        assert queue.complete("nope") is False

    def test_remove(self):
        queue = CompoundingQueue()
        item = queue.add("a", "remove me")
        assert queue.remove(item.id) is True
        assert len(queue.get_pending()) == 0

    def test_remove_nonexistent(self):
        queue = CompoundingQueue()
        assert queue.remove("nope") is False

    def test_get_for_initiative(self):
        queue = CompoundingQueue()
        queue.add("init_1", "task a")
        queue.add("init_2", "task b")
        queue.add("init_1", "task c")

        items = queue.get_for_initiative("init_1")
        assert len(items) == 2

    def test_summary(self):
        queue = CompoundingQueue()
        queue.add("a", "task 1")
        item = queue.add("b", "task 2")
        queue.complete(item.id)

        summary = queue.summary()
        assert summary["total"] == 2
        assert summary["pending"] == 1
        assert summary["completed"] == 1

    def test_persistence(self):
        """Anti-amnesia: queue persists across reloads."""
        q1 = CompoundingQueue()
        q1.add("x", "remember this")

        q2 = CompoundingQueue()
        q2.load()
        assert len(q2.get_pending()) == 1
        assert q2.get_pending()[0].task == "remember this"
