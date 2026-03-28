from __future__ import annotations

from pathlib import Path

from dharma_swarm.thinkodynamic_canary import (
    CommandResult,
    TaskSnapshot,
    _write_text,
    assess_cycle,
)


def _snapshot(
    *,
    delegated: bool,
    active_before: int,
    max_active_tasks: int,
    workflow_id: str = "wf-current",
    review_id: str = "wf-current",
    workflow_title: str = "Build ecological restoration coordination for AI carbon offset",
    selected_title: str = "Build ecological restoration coordination for AI carbon offset",
    council_error: str = "",
) -> dict:
    return {
        "cycle_id": "cycle-1",
        "delegated": delegated,
        "active_director_tasks_before": active_before,
        "max_active_tasks": max_active_tasks,
        "workflow": {
            "workflow_id": workflow_id,
            "opportunity_title": workflow_title,
        },
        "review": {
            "workflow_id": review_id,
        },
        "selected_opportunity": {
            "title": selected_title,
        },
        "council": {
            "turns": [
                {
                    "success": not council_error,
                    "error": council_error,
                }
            ]
        },
    }


def _command_result(stdout: str = "", stderr: str = "", rc: int = 0) -> CommandResult:
    return CommandResult(
        argv=["python3", "-m", "dharma_swarm.thinkodynamic_director"],
        rc=rc,
        stdout=stdout,
        stderr=stderr,
        elapsed_s=12.5,
    )


def test_assess_cycle_flags_queue_saturation(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text(
        "# Summary\n\n## Top Signals\n\n- /repo/app.py :: score=1\n",
        encoding="utf-8",
    )
    assessment = assess_cycle(
        snapshot=_snapshot(delegated=False, active_before=14, max_active_tasks=12),
        summary_path=summary,
        command_result=_command_result(),
        pre_tasks=TaskSnapshot(active_director_task_ids={"a"}),
        post_tasks=TaskSnapshot(active_director_task_ids={"a"}),
        max_active_tasks=12,
    )

    assert assessment.status == "DEGRADE"
    assert any(f.code == "queue_saturated" for f in assessment.findings)


def test_assess_cycle_flags_stale_review_and_generic_workflow(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text(
        "# Summary\n\n## Top Signals\n\n- /repo/tests/test_thing.py :: score=1\n",
        encoding="utf-8",
    )
    assessment = assess_cycle(
        snapshot=_snapshot(
            delegated=False,
            active_before=1,
            max_active_tasks=12,
            workflow_title="Literature Review**",
            selected_title="Build ecological restoration coordination for AI carbon offset",
            review_id="wf-older",
            council_error="live council disabled; using heuristic consensus",
        ),
        summary_path=summary,
        command_result=_command_result(stdout="Stigmergy: skipped 6 corrupt marks out of 534 total lines"),
        pre_tasks=TaskSnapshot(),
        post_tasks=TaskSnapshot(),
        max_active_tasks=12,
    )

    assert assessment.status == "FAIL"
    codes = {f.code for f in assessment.findings}
    assert "stale_review" in codes
    assert "generic_workflow" in codes
    assert "heuristic_council_only" in codes
    assert "test_file_ranked_as_primary_signal" in codes
    assert "corrupt_stigmergy_marks" in codes


def test_assess_cycle_passes_when_delegation_creates_tasks(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text(
        "# Summary\n\n## Top Signals\n\n- /repo/docs/mission.md :: score=1\n",
        encoding="utf-8",
    )
    assessment = assess_cycle(
        snapshot=_snapshot(delegated=True, active_before=2, max_active_tasks=12),
        summary_path=summary,
        command_result=_command_result(),
        pre_tasks=TaskSnapshot(
            active_director_task_ids={"old"},
            recent_director_task_ids={"old"},
        ),
        post_tasks=TaskSnapshot(
            active_director_task_ids={"old", "new-task"},
            recent_director_task_ids={"old", "new-task"},
        ),
        max_active_tasks=12,
    )

    assert assessment.status == "PASS"
    assert assessment.new_director_task_ids == ["new-task"]


def test_assess_cycle_flags_stale_review_counts(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text(
        "# Summary\n\n## Top Signals\n\n- /repo/docs/mission.md :: score=1\n",
        encoding="utf-8",
    )
    snapshot = _snapshot(delegated=True, active_before=2, max_active_tasks=12)
    snapshot["delegated_task_ids"] = ["task-a", "task-b"]
    snapshot["review"] = {
        "workflow_id": "wf-current",
        "active_count": 2,
        "completed_count": 0,
        "failed_count": 0,
    }
    assessment = assess_cycle(
        snapshot=snapshot,
        summary_path=summary,
        command_result=_command_result(),
        pre_tasks=TaskSnapshot(recent_director_task_ids={"old"}),
        post_tasks=TaskSnapshot(
            recent_director_task_ids={"old", "task-a", "task-b"},
            latest_director_tasks=[
                {
                    "id": "task-a",
                    "title": "Task A",
                    "status": "completed",
                    "created_at": "2026-03-27T00:00:00+00:00",
                    "assigned_to": "worker-loop",
                },
                {
                    "id": "task-b",
                    "title": "Task B",
                    "status": "running",
                    "created_at": "2026-03-27T00:00:01+00:00",
                    "assigned_to": "worker-loop",
                },
            ],
        ),
        max_active_tasks=12,
    )

    assert any(f.code == "stale_review_counts" for f in assessment.findings)


def test_write_text_accepts_bytes(tmp_path: Path) -> None:
    target = tmp_path / "stderr.log"
    _write_text(target, b"binary stderr")

    assert target.read_text(encoding="utf-8") == "binary stderr"
