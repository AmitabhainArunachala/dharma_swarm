"""Tests for dharma_swarm.durable_execution -- DurableWorkflow and crash recovery."""

import json

import pytest

from dharma_swarm.durable_execution import (
    DurableWorkflow,
    StepStatus,
    WorkflowStep,
)


# ---------------------------------------------------------------------------
# WorkflowStep basics
# ---------------------------------------------------------------------------


def test_workflow_step_defaults():
    step = WorkflowStep(step_id="s1", name="first")
    assert step.status == StepStatus.PENDING
    assert step.result is None
    assert step.error is None
    assert step.depends_on == []


def test_workflow_step_roundtrip():
    step = WorkflowStep(
        step_id="s1",
        name="first",
        status=StepStatus.COMPLETED,
        result={"key": "value"},
        depends_on=["s0"],
    )
    d = step.to_dict()
    restored = WorkflowStep.from_dict(d)
    assert restored.step_id == "s1"
    assert restored.status == StepStatus.COMPLETED
    assert restored.result == {"key": "value"}
    assert restored.depends_on == ["s0"]


# ---------------------------------------------------------------------------
# add_step
# ---------------------------------------------------------------------------


def test_add_steps():
    wf = DurableWorkflow("test_wf", persist_dir=None)
    wf._persist_dir = None  # disable checkpointing for this unit test
    # We need to override checkpoint to be a no-op for pure logic tests
    wf.checkpoint = lambda: None  # type: ignore[assignment]

    s1 = wf.add_step("a", "step_a")
    s2 = wf.add_step("b", "step_b", depends_on=["a"])

    assert s1.step_id == "a"
    assert s2.depends_on == ["a"]
    assert len(wf.steps) == 2


def test_add_step_duplicate_raises():
    wf = DurableWorkflow("dup", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    with pytest.raises(ValueError, match="already exists"):
        wf.add_step("a", "step_a_again")


def test_add_step_unknown_dep_raises():
    wf = DurableWorkflow("dep", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="not found"):
        wf.add_step("b", "step_b", depends_on=["nonexistent"])


# ---------------------------------------------------------------------------
# ready_steps with dependencies
# ---------------------------------------------------------------------------


def test_ready_steps_no_deps():
    wf = DurableWorkflow("ready", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b")

    ready = wf.ready_steps()
    assert len(ready) == 2
    assert {s.step_id for s in ready} == {"a", "b"}


def test_ready_steps_with_deps():
    wf = DurableWorkflow("ready_dep", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b", depends_on=["a"])
    wf.add_step("c", "step_c", depends_on=["a"])

    # Initially only 'a' is ready
    ready = wf.ready_steps()
    assert [s.step_id for s in ready] == ["a"]

    # Complete 'a' -> 'b' and 'c' become ready
    wf.get_step("a").status = StepStatus.COMPLETED
    ready = wf.ready_steps()
    assert {s.step_id for s in ready} == {"b", "c"}


def test_ready_steps_chain():
    wf = DurableWorkflow("chain", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b", depends_on=["a"])
    wf.add_step("c", "step_c", depends_on=["b"])

    assert [s.step_id for s in wf.ready_steps()] == ["a"]

    wf.get_step("a").status = StepStatus.COMPLETED
    assert [s.step_id for s in wf.ready_steps()] == ["b"]

    wf.get_step("b").status = StepStatus.COMPLETED
    assert [s.step_id for s in wf.ready_steps()] == ["c"]


# ---------------------------------------------------------------------------
# mark_* transitions
# ---------------------------------------------------------------------------


def test_mark_running(tmp_path):
    wf = DurableWorkflow("mark_run", persist_dir=tmp_path / "wf")
    wf.add_step("a", "step_a")
    wf.mark_running("a")

    step = wf.get_step("a")
    assert step.status == StepStatus.RUNNING
    assert step.started_at != ""


def test_mark_completed(tmp_path):
    wf = DurableWorkflow("mark_done", persist_dir=tmp_path / "wf")
    wf.add_step("a", "step_a")
    wf.mark_running("a")
    wf.mark_completed("a", result={"output": 42})

    step = wf.get_step("a")
    assert step.status == StepStatus.COMPLETED
    assert step.result == {"output": 42}
    assert step.completed_at != ""


def test_mark_failed(tmp_path):
    wf = DurableWorkflow("mark_fail", persist_dir=tmp_path / "wf")
    wf.add_step("a", "step_a")
    wf.mark_running("a")
    wf.mark_failed("a", error="something broke")

    step = wf.get_step("a")
    assert step.status == StepStatus.FAILED
    assert step.error == "something broke"


# ---------------------------------------------------------------------------
# Checkpoint and restore
# ---------------------------------------------------------------------------


def test_checkpoint_creates_file(tmp_path):
    persist = tmp_path / "wf_ckpt"
    wf = DurableWorkflow("ckpt_test", persist_dir=persist)
    wf.add_step("a", "step_a")
    path = wf.checkpoint()

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["workflow_id"] == "ckpt_test"
    assert len(data["steps"]) == 1


def test_checkpoint_and_restore(tmp_path):
    persist = tmp_path / "wf_restore"
    wf = DurableWorkflow("restore_test", persist_dir=persist)
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b", depends_on=["a"])
    wf.mark_running("a")
    wf.mark_completed("a", result="done_a")

    # Restore from disk
    restored = DurableWorkflow.restore("restore_test", persist_dir=persist)

    assert restored.workflow_id == "restore_test"
    assert len(restored.steps) == 2

    step_a = restored.get_step("a")
    assert step_a.status == StepStatus.COMPLETED
    assert step_a.result == "done_a"

    step_b = restored.get_step("b")
    assert step_b.status == StepStatus.PENDING
    assert step_b.depends_on == ["a"]

    # Restored workflow should have 'b' as ready
    ready = restored.ready_steps()
    assert [s.step_id for s in ready] == ["b"]


def test_auto_checkpoint_on_mark(tmp_path):
    persist = tmp_path / "wf_auto"
    wf = DurableWorkflow("auto_ckpt", persist_dir=persist)
    wf.add_step("a", "step_a")

    # Before any mark_*, no file exists
    state_path = persist / "state.json"
    # The add_step doesn't checkpoint, but mark_running does
    assert not state_path.exists()

    wf.mark_running("a")
    assert state_path.exists()

    # Verify the file is updated on mark_completed
    wf.mark_completed("a", result="final")
    data = json.loads(state_path.read_text())
    assert data["steps"][0]["status"] == "completed"
    assert data["steps"][0]["result"] == "final"


def test_restore_nonexistent_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        DurableWorkflow.restore("nonexistent", persist_dir=tmp_path / "nope")


# ---------------------------------------------------------------------------
# is_complete
# ---------------------------------------------------------------------------


def test_is_complete_all_completed(tmp_path):
    wf = DurableWorkflow("complete", persist_dir=tmp_path / "wf")
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b")
    wf.mark_running("a")
    wf.mark_completed("a")
    wf.mark_running("b")
    wf.mark_completed("b")

    assert wf.is_complete() is True


def test_is_complete_with_pending():
    wf = DurableWorkflow("incomplete", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b")
    wf.get_step("a").status = StepStatus.COMPLETED

    assert wf.is_complete() is False


def test_is_complete_with_failed_and_skipped():
    wf = DurableWorkflow("mixed", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b")
    wf.get_step("a").status = StepStatus.FAILED
    wf.get_step("b").status = StepStatus.SKIPPED

    assert wf.is_complete() is True


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary():
    wf = DurableWorkflow("summary", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]
    wf.add_step("a", "step_a")
    wf.add_step("b", "step_b")
    wf.add_step("c", "step_c")
    wf.get_step("a").status = StepStatus.COMPLETED
    wf.get_step("b").status = StepStatus.FAILED

    s = wf.summary()
    assert s["completed"] == 1
    assert s["failed"] == 1
    assert s["pending"] == 1
    assert s["running"] == 0
    assert s["skipped"] == 0


def test_summary_empty():
    wf = DurableWorkflow("empty", persist_dir=None)
    wf.checkpoint = lambda: None  # type: ignore[assignment]

    s = wf.summary()
    assert all(v == 0 for v in s.values())
