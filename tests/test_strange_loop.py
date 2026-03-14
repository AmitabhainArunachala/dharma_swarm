"""Integration tests for Strange Loop Phases 0-5.

Tests the catalytic closure: every module feeds and is fed.
"""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.signal_bus import SignalBus
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore


# --- Phase 0: Control Truth ---

class TestPhase0ControlTruth:
    """Verify unified tick() method exists and returns expected shape."""

    def test_swarm_manager_has_tick(self):
        from dharma_swarm.swarm import SwarmManager
        assert hasattr(SwarmManager, "tick")
        assert asyncio.iscoroutinefunction(SwarmManager.tick)

    def test_orchestrate_live_uses_swarm_tick(self):
        """Verify run_swarm_loop accepts signal_bus parameter."""
        import inspect
        from dharma_swarm.orchestrate_live import run_swarm_loop
        sig = inspect.signature(run_swarm_loop)
        assert "signal_bus" in sig.parameters

    def test_orchestrate_writes_daemon_pid(self):
        """Verify orchestrate() writes daemon.pid for PID tracking."""
        import inspect
        from dharma_swarm.orchestrate_live import orchestrate
        source = inspect.getsource(orchestrate)
        # The actual PID write should use daemon.pid
        assert 'pid_file = STATE_DIR / "daemon.pid"' in source


# --- Phase 1: Amplification Loop ---

class TestPhase1AmplificationLoop:
    """Verify archive.get_best_approaches() and stigmergy.query_relevant()."""

    @pytest.fixture
    def archive_dir(self, tmp_path):
        archive_path = tmp_path / "archive.jsonl"
        return archive_path

    @pytest.mark.asyncio
    async def test_get_best_approaches(self, archive_dir):
        archive = EvolutionArchive(path=archive_dir)
        await archive.load()

        # Add some entries
        for i in range(3):
            entry = ArchiveEntry(
                component=f"module_{i}",
                change_type="mutation",
                description=f"Improvement {i}",
                diff=f"diff {i}",
                fitness=FitnessScore(correctness=0.5 + i * 0.1, elegance=0.6),
                status="applied",
                gates_passed=["AHIMSA", "SATYA"],
            )
            await archive.add_entry(entry)

        approaches = await archive.get_best_approaches(n=2)
        assert len(approaches) == 2
        assert "component" in approaches[0]
        assert "fitness" in approaches[0]
        assert "gates_passed" in approaches[0]
        # Should be ordered by fitness desc
        assert float(approaches[0]["fitness"]) >= float(approaches[1]["fitness"])

    @pytest.mark.asyncio
    async def test_query_relevant(self, tmp_path):
        store = StigmergyStore(base_path=tmp_path / "stig")

        # Leave some marks
        await store.leave_mark(StigmergicMark(
            agent="test",
            file_path="dharma_swarm/evolution.py",
            action="write",
            observation="Fixed mutation rate",
            salience=0.8,
        ))
        await store.leave_mark(StigmergicMark(
            agent="test",
            file_path="dharma_swarm/context.py",
            action="read",
            observation="Checked context injection",
            salience=0.3,
        ))
        await store.leave_mark(StigmergicMark(
            agent="test",
            file_path="dharma_swarm/archive.py",
            action="write",
            observation="Added evolution compaction",
            salience=0.9,
        ))

        # Query with keyword
        results = await store.query_relevant(["evolution", "mutation"])
        assert len(results) >= 1
        assert results[0].salience >= results[-1].salience  # sorted by salience

    @pytest.mark.asyncio
    async def test_query_relevant_no_keywords_returns_high_salience(self, tmp_path):
        store = StigmergyStore(base_path=tmp_path / "stig")
        await store.leave_mark(StigmergicMark(
            agent="test",
            file_path="test.py",
            action="write",
            observation="High salience mark",
            salience=0.9,
        ))
        results = await store.query_relevant([])
        assert len(results) >= 1


# --- Phase 2: Shared Downbeat (tested in test_signal_bus.py) ---


# --- Phase 3: Honest Gates ---

class TestPhase3HonestGates:
    """Verify DOGMA_DRIFT and STEELMAN produce real results."""

    def test_dogma_drift_detects_confidence_without_evidence(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        from dharma_swarm.models import GateResult
        gk = TelosGatekeeper()
        result = gk.check(
            action="update model",
            content="This is certainly proven and obviously correct without question",
        )
        # DOGMA_DRIFT should warn or fail
        dogma = result.gate_results.get("DOGMA_DRIFT")
        assert dogma is not None
        assert dogma[0] in (GateResult.WARN, GateResult.FAIL)

    def test_steelman_fails_on_proposal_without_counterarguments(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        from dharma_swarm.models import GateResult
        gk = TelosGatekeeper()
        result = gk.check(
            action="propose mutation to core module",
            content="Just change it, no downsides at all.",
        )
        steelman = result.gate_results.get("STEELMAN")
        assert steelman is not None
        assert steelman[0] in (GateResult.FAIL, GateResult.WARN)

    def test_steelman_passes_with_counterarguments(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        from dharma_swarm.models import GateResult
        gk = TelosGatekeeper()
        result = gk.check(
            action="propose refactoring of the context engine",
            content=(
                "This refactoring improves readability. "
                "However, it could break backward compatibility with existing agents. "
                "Alternatively, we could use an adapter pattern instead."
            ),
        )
        steelman = result.gate_results.get("STEELMAN")
        assert steelman is not None
        assert steelman[0] == GateResult.PASS

    def test_reflection_insufficient_with_generic_text(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        # Generic text without substance markers should fail
        result = TelosGatekeeper._is_reflection_sufficient(
            "This looks good and seems fine to proceed with the changes"
        )
        assert result is False

    def test_reflection_sufficient_with_rollback_path(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        result = TelosGatekeeper._is_reflection_sufficient(
            "If this fails we can revert the change and restore the previous version from backup"
        )
        assert result is True

    def test_monitor_detects_rejected_as_failure(self):
        from dharma_swarm.monitor import _is_failure
        from dharma_swarm.traces import TraceEntry
        entry = TraceEntry(agent="test", action="gate_check", state="rejected")
        assert _is_failure(entry) is True

    def test_monitor_detects_blocked_as_failure(self):
        from dharma_swarm.monitor import _is_failure
        from dharma_swarm.traces import TraceEntry
        entry = TraceEntry(agent="test", action="submit", state="blocked")
        assert _is_failure(entry) is True

    def test_monitor_detects_rolled_back_as_failure(self):
        from dharma_swarm.monitor import _is_failure
        from dharma_swarm.traces import TraceEntry
        entry = TraceEntry(agent="test", action="apply", state="rolled_back")
        assert _is_failure(entry) is True


# --- Phase 4: Substrate Curdling ---

class TestPhase4SubstrateCurdling:
    """Verify rejection learning in fitness predictor."""

    @pytest.mark.asyncio
    async def test_rejection_creates_penalty(self, tmp_path):
        predictor = FitnessPredictor(history_path=tmp_path / "pred.jsonl")
        features = ProposalFeatures(
            component="evolution.py",
            change_type="mutation",
            diff_size=30,
        )
        # Record several rejections
        for _ in range(5):
            await predictor.record_rejection(features, reason="test rejection")

        # Record one success
        await predictor.record_outcome(features, actual_fitness=0.7)

        # Predict should be lower than neutral prior due to high rejection rate
        prediction = predictor.predict(features)
        assert prediction < 0.5  # neutral prior is 0.5

    @pytest.mark.asyncio
    async def test_no_rejection_no_penalty(self, tmp_path):
        predictor = FitnessPredictor(history_path=tmp_path / "pred.jsonl")
        features = ProposalFeatures(
            component="clean_module.py",
            change_type="mutation",
            diff_size=30,
        )
        # Record only successes
        for _ in range(3):
            await predictor.record_outcome(features, actual_fitness=0.8)

        prediction = predictor.predict(features)
        assert prediction >= 0.5  # should not be penalized


# --- Phase 5: Forgetting Law ---

class TestPhase5ForgettingLaw:
    """Verify access-based decay and archive compaction."""

    @pytest.mark.asyncio
    async def test_access_decay_unused_marks_fade_faster(self, tmp_path):
        store = StigmergyStore(base_path=tmp_path / "stig")

        # Mark with access_count=0 (never read)
        unused = StigmergicMark(
            agent="test", file_path="unused.py", action="write",
            observation="Never accessed", salience=0.8, access_count=0,
        )
        # Mark with access_count=3 (frequently read)
        used = StigmergicMark(
            agent="test", file_path="used.py", action="write",
            observation="Frequently accessed", salience=0.8, access_count=3,
        )
        await store.leave_mark(unused)
        await store.leave_mark(used)

        await store.access_decay(decay_factor=0.95)

        marks = await store.read_marks(limit=10)
        mark_by_path = {m.file_path: m for m in marks}

        unused_after = mark_by_path["unused.py"]
        used_after = mark_by_path["used.py"]

        # Unused should have decayed more
        assert unused_after.salience < used_after.salience

    @pytest.mark.asyncio
    async def test_archive_compaction(self, tmp_path):
        archive = EvolutionArchive(path=tmp_path / "archive.jsonl")
        await archive.load()

        # Add 20 entries: 10 low fitness (old), 10 high fitness (new)
        # With min_age_entries=5, entries 0-14 are "old", 15-19 protected
        for i in range(20):
            entry = ArchiveEntry(
                component=f"module_{i}",
                change_type="mutation",
                description=f"Change {i}",
                # First 10 are very low fitness, last 10 are high
                fitness=FitnessScore(correctness=0.05 if i < 10 else 0.9),
                status="applied",
            )
            await archive.add_entry(entry)

        composted = await archive.compact(min_age_entries=5)
        assert composted > 0

        # Composted entries should be excluded from get_best
        best = await archive.get_best(n=100)
        for e in best:
            assert e.status != "composted"

    @pytest.mark.asyncio
    async def test_stigmergy_access_count_field(self):
        mark = StigmergicMark(
            agent="test", file_path="x.py", action="read",
            observation="test", access_count=5,
        )
        assert mark.access_count == 5

    @pytest.mark.asyncio
    async def test_stigmergy_access_count_default(self):
        mark = StigmergicMark(
            agent="test", file_path="x.py", action="read",
            observation="test",
        )
        assert mark.access_count == 0


# --- Catalytic Closure ---

class TestCatalyticClosure:
    """Verify the torus: every module feeds and is fed."""

    def test_signal_bus_exists(self):
        from dharma_swarm.signal_bus import SignalBus
        bus = SignalBus()
        assert hasattr(bus, "emit")
        assert hasattr(bus, "drain")

    def test_archive_has_get_best_approaches(self):
        assert hasattr(EvolutionArchive, "get_best_approaches")

    def test_archive_has_compact(self):
        assert hasattr(EvolutionArchive, "compact")

    def test_stigmergy_has_query_relevant(self):
        assert hasattr(StigmergyStore, "query_relevant")

    def test_stigmergy_has_access_decay(self):
        assert hasattr(StigmergyStore, "access_decay")

    def test_fitness_predictor_has_record_rejection(self):
        assert hasattr(FitnessPredictor, "record_rejection")

    def test_event_types_include_strange_loop_signals(self):
        from dharma_swarm.engine.events import EventType
        assert hasattr(EventType, "FITNESS_IMPROVED")
        assert hasattr(EventType, "ANOMALY_DETECTED")
        assert hasattr(EventType, "CASCADE_EIGENFORM_DISTANCE")
        assert hasattr(EventType, "GATE_REJECTION_SPIKE")
        assert hasattr(EventType, "RECOGNITION_UPDATED")
