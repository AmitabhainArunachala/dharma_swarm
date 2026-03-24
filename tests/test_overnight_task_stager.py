"""Tests for overnight_task_stager -- bounded, verifiable task queue."""

from __future__ import annotations

import json
import time

import pytest

from dharma_swarm.overnight_task_stager import (
    OvernightTask,
    OvernightTaskStager,
)


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture()
def stager(tmp_path):
    """Stager wired to tmp_path so disk ops are isolated."""
    state_dir = tmp_path / "state"
    dharma_root = tmp_path / "repo"
    (dharma_root / "dharma_swarm").mkdir(parents=True)
    (dharma_root / "tests").mkdir(parents=True)
    return OvernightTaskStager(
        date="2026-03-24",
        state_dir=state_dir,
        dharma_root=dharma_root,
    )


@pytest.fixture()
def populated_stager(tmp_path):
    """Stager with mock source files that have no corresponding tests."""
    state_dir = tmp_path / "state"
    dharma_root = tmp_path / "repo"
    src_dir = dharma_root / "dharma_swarm"
    test_dir = dharma_root / "tests"
    src_dir.mkdir(parents=True)
    test_dir.mkdir(parents=True)

    # Source modules (varying sizes)
    (src_dir / "alpha.py").write_text("# alpha\n" * 200)
    (src_dir / "beta.py").write_text("# beta\n" * 50)
    (src_dir / "gamma.py").write_text("# gamma\n" * 400)
    # gamma has a test -- should NOT produce a task
    (test_dir / "test_gamma.py").write_text("def test_placeholder(): pass\n")
    # __init__.py should be skipped
    (src_dir / "__init__.py").write_text("")
    # _private.py should be skipped
    (src_dir / "_private.py").write_text("# private\n" * 100)

    return OvernightTaskStager(
        date="2026-03-24",
        state_dir=state_dir,
        dharma_root=dharma_root,
    )


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


class TestOvernightTask:
    """OvernightTask dataclass basics."""

    def test_overnight_task_creation(self):
        """Verify default values and basic construction."""
        task = OvernightTask(
            task_id="t1",
            goal="Do something",
            task_type="custom",
            acceptance_criterion="It works",
        )
        assert task.task_id == "t1"
        assert task.goal == "Do something"
        assert task.task_type == "custom"
        assert task.acceptance_criterion == "It works"
        assert task.timeout_seconds == 900.0
        assert task.max_tokens == 50_000
        assert task.priority == 0.0
        assert task.status == "pending"
        assert task.result == ""
        assert task.started_at == 0.0
        assert task.completed_at == 0.0
        assert task.metadata == {}

    def test_task_to_dict_serializable(self):
        """to_dict() produces a JSON-serializable dict."""
        task = OvernightTask(
            task_id="ser_1",
            goal="Serialize me",
            task_type="benchmark",
            acceptance_criterion="JSON round-trips cleanly",
            metadata={"nested": {"key": [1, 2, 3]}},
        )
        d = task.to_dict()
        assert isinstance(d, dict)
        # Must not raise
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped["task_id"] == "ser_1"
        assert roundtripped["metadata"]["nested"]["key"] == [1, 2, 3]


class TestCompileQueueEmpty:
    """Compile queue when repo has no source files."""

    def test_compile_queue_empty_repo(self, stager):
        """Empty source directory yields empty queue."""
        tasks = stager.compile_queue()
        assert tasks == []
        assert not stager.has_tasks()

    def test_compile_queue_missing_src_dir(self, tmp_path):
        """Non-existent source directory yields empty queue gracefully."""
        s = OvernightTaskStager(
            date="2026-03-24",
            state_dir=tmp_path / "state",
            dharma_root=tmp_path / "nonexistent",
        )
        tasks = s.compile_queue()
        assert tasks == []


class TestScanTestCoverageGaps:
    """Scanning for modules without tests."""

    def test_scan_test_coverage_gaps(self, populated_stager):
        """Modules without tests generate tasks; modules with tests do not."""
        tasks = populated_stager.compile_queue()
        task_ids = {t.task_id for t in tasks}

        # alpha and beta have no tests -> tasks created
        assert "test_coverage_alpha" in task_ids
        assert "test_coverage_beta" in task_ids

        # gamma has a test -> no task
        assert "test_coverage_gamma" not in task_ids

        # __init__.py and _private.py -> skipped
        assert not any("__init__" in tid for tid in task_ids)
        assert not any("_private" in tid for tid in task_ids)

    def test_coverage_gap_priority_scales_with_lines(self, populated_stager):
        """Larger modules get higher priority."""
        tasks = populated_stager.compile_queue()
        by_id = {t.task_id: t for t in tasks}
        # alpha: 200 lines -> priority 2.0
        # beta: 50 lines -> priority 0.5
        assert by_id["test_coverage_alpha"].priority > by_id["test_coverage_beta"].priority

    def test_coverage_gap_metadata(self, populated_stager):
        """Tasks carry line count and src path in metadata."""
        tasks = populated_stager.compile_queue()
        by_id = {t.task_id: t for t in tasks}
        alpha = by_id["test_coverage_alpha"]
        assert alpha.metadata["module"] == "alpha"
        assert alpha.metadata["line_count"] == 200
        assert "alpha.py" in alpha.metadata["src_path"]


class TestScanHumanCuratedQueue:
    """Loading tasks from queue.yaml."""

    def test_scan_human_curated_queue(self, stager):
        """Well-formed queue.yaml creates tasks."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: fix_flaky\n"
            '  goal: "Fix flaky test in test_api.py"\n'
            "  type: custom\n"
            '  acceptance: "pytest test_api.py passes 10x in a row"\n'
            "  priority: 9.0\n"
            "  timeout: 600\n"
            "  max_tokens: 30000\n"
            "- id: add_docs\n"
            '  goal: "Add docstrings to models.py"\n'
            "  priority: 3.0\n"
        )
        tasks = stager.compile_queue()
        by_id = {t.task_id: t for t in tasks}

        assert "fix_flaky" in by_id
        assert by_id["fix_flaky"].goal == "Fix flaky test in test_api.py"
        assert by_id["fix_flaky"].timeout_seconds == 600.0
        assert by_id["fix_flaky"].max_tokens == 30000
        assert by_id["fix_flaky"].priority == 9.0

        assert "add_docs" in by_id
        assert by_id["add_docs"].acceptance_criterion == "Manual review required"
        assert by_id["add_docs"].task_type == "custom"

    def test_scan_human_curated_missing_file(self, stager):
        """No queue.yaml -> graceful skip, no errors."""
        # Ensure no queue.yaml exists
        queue_file = stager.state_dir / "overnight" / "queue.yaml"
        assert not queue_file.exists()
        tasks = stager.compile_queue()
        # Should still work (may have other sources, but stager fixture has no src files)
        assert isinstance(tasks, list)

    def test_scan_human_curated_malformed_yaml(self, stager):
        """Non-list YAML doesn't crash -- just skips."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text("just_a_string: true\n")
        tasks = stager.compile_queue()
        assert isinstance(tasks, list)

    def test_scan_human_curated_items_without_goal(self, stager):
        """Items missing 'goal' field are silently skipped."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: no_goal\n"
            "  type: custom\n"
            '- goal: "Valid task"\n'
            "  id: has_goal\n"
        )
        tasks = stager.compile_queue()
        task_ids = {t.task_id for t in tasks}
        assert "no_goal" not in task_ids
        assert "has_goal" in task_ids


class TestRanking:
    """Task ranking by priority."""

    def test_rank_tasks_by_priority(self, stager):
        """Higher priority tasks come first after compile."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: low\n"
            '  goal: "Low priority"\n'
            "  priority: 1.0\n"
            "- id: high\n"
            '  goal: "High priority"\n'
            "  priority: 10.0\n"
            "- id: mid\n"
            '  goal: "Mid priority"\n'
            "  priority: 5.0\n"
        )
        tasks = stager.compile_queue()
        ids_in_order = [t.task_id for t in tasks]
        assert ids_in_order == ["high", "mid", "low"]


class TestTaskConsumption:
    """Pulling tasks from the queue."""

    @pytest.fixture()
    def ready_stager(self, stager):
        """Stager with three pre-ranked tasks."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: first\n"
            '  goal: "First"\n'
            "  priority: 10.0\n"
            "- id: second\n"
            '  goal: "Second"\n'
            "  priority: 5.0\n"
            "- id: third\n"
            '  goal: "Third"\n'
            "  priority: 1.0\n"
        )
        stager.compile_queue()
        return stager

    def test_next_task_returns_highest_priority(self, ready_stager):
        """next_task() returns the highest-priority pending task."""
        task = ready_stager.next_task()
        assert task is not None
        assert task.task_id == "first"

    def test_next_task_marks_in_progress(self, ready_stager):
        """Pulled task has status in_progress and started_at set."""
        task = ready_stager.next_task()
        assert task is not None
        assert task.status == "in_progress"
        assert task.started_at > 0

    def test_next_task_sequential_pulls(self, ready_stager):
        """Successive pulls return tasks in priority order."""
        t1 = ready_stager.next_task()
        t2 = ready_stager.next_task()
        t3 = ready_stager.next_task()
        t4 = ready_stager.next_task()
        assert t1 is not None and t1.task_id == "first"
        assert t2 is not None and t2.task_id == "second"
        assert t3 is not None and t3.task_id == "third"
        assert t4 is None  # exhausted

    def test_record_result_updates_status(self, ready_stager):
        """record_result updates status, result text, and completed_at."""
        task = ready_stager.next_task()
        assert task is not None
        ready_stager.record_result(task.task_id, "completed", "All tests pass")
        assert task.status == "completed"
        assert task.result == "All tests pass"
        assert task.completed_at > 0

    def test_record_result_failed(self, ready_stager):
        """Failed status works correctly."""
        task = ready_stager.next_task()
        assert task is not None
        ready_stager.record_result(task.task_id, "failed", "Timeout exceeded")
        assert task.status == "failed"

    def test_record_result_dead_cycle(self, ready_stager):
        """dead_cycle status marks the task as non-retryable."""
        task = ready_stager.next_task()
        assert task is not None
        ready_stager.record_result(task.task_id, "dead_cycle", "Circular dependency")
        assert task.status == "dead_cycle"

    def test_record_result_unknown_task(self, ready_stager):
        """Recording result for nonexistent task_id is a no-op."""
        ready_stager.record_result("nonexistent", "completed", "Nope")
        # No exception, no side effects

    def test_has_tasks_false_when_all_done(self, ready_stager):
        """has_tasks() returns False when no pending tasks remain."""
        assert ready_stager.has_tasks() is True
        # Pull and complete all
        while True:
            task = ready_stager.next_task()
            if task is None:
                break
            ready_stager.record_result(task.task_id, "completed")
        assert ready_stager.has_tasks() is False


class TestPersistence:
    """Disk persistence of the task queue."""

    def test_persist_queue_to_disk(self, populated_stager):
        """compile_queue writes a JSONL file with one line per task."""
        tasks = populated_stager.compile_queue()
        assert populated_stager.queue_path.exists()

        lines = populated_stager.queue_path.read_text().strip().splitlines()
        assert len(lines) == len(tasks)

        # Each line is valid JSON with expected fields
        for line in lines:
            data = json.loads(line)
            assert "task_id" in data
            assert "goal" in data
            assert "status" in data
            assert data["status"] == "pending"

    def test_persist_updates_on_status_change(self, stager):
        """Status changes are reflected in the persisted file."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: tracked\n"
            '  goal: "Track persistence"\n'
            "  priority: 5.0\n"
        )
        stager.compile_queue()
        task = stager.next_task()
        assert task is not None

        # After pulling, file should show in_progress
        lines = stager.queue_path.read_text().strip().splitlines()
        data = json.loads(lines[0])
        assert data["status"] == "in_progress"

        # After recording result, file should show completed
        stager.record_result("tracked", "completed", "Done")
        lines = stager.queue_path.read_text().strip().splitlines()
        data = json.loads(lines[0])
        assert data["status"] == "completed"
        assert data["result"] == "Done"


class TestStats:
    """Queue statistics."""

    def test_stats_counts(self, stager):
        """stats() returns correct counts per status."""
        queue_dir = stager.state_dir / "overnight"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "queue.yaml").write_text(
            "- id: a\n"
            '  goal: "A"\n'
            "  priority: 3.0\n"
            "- id: b\n"
            '  goal: "B"\n'
            "  priority: 2.0\n"
            "- id: c\n"
            '  goal: "C"\n'
            "  priority: 1.0\n"
        )
        stager.compile_queue()

        stats = stager.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 3
        assert stats["in_progress"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["dead_cycle"] == 0

        # Pull one, complete one, fail one
        t1 = stager.next_task()
        assert t1 is not None
        stager.record_result(t1.task_id, "completed")
        t2 = stager.next_task()
        assert t2 is not None
        stager.record_result(t2.task_id, "failed")

        stats = stager.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 1
        assert stats["in_progress"] == 0
        assert stats["completed"] == 1
        assert stats["failed"] == 1

    def test_stats_empty_queue(self, stager):
        """Stats on empty queue returns all zeros."""
        stager.compile_queue()
        stats = stager.stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0
