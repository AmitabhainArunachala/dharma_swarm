from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm import terminal_control


def test_load_terminal_control_state_reads_latest_repo_state(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "terminal_supervisor"
    state_dir = root / "run-1" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "run.json").write_text(
        json.dumps(
            {
                "repo_root": str(tmp_path / "repo"),
                "updated_at": "2026-04-02T00:00:00Z",
                "cycle": 4,
                "status": "running",
                "tasks_total": 3,
                "tasks_pending": 1,
                "last_task_id": "task-42",
                "last_continue_required": True,
                "last_summary_fields": {
                    "status": "blocked",
                    "acceptance": "fail",
                    "next_task": "fix verification",
                },
                "last_verification": {
                    "summary": "tsc=ok | tests=fail",
                    "checks": [{"name": "tsc", "ok": True}, {"name": "tests", "ok": False}],
                },
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "verification.json").write_text(
        json.dumps(
            {
                "summary": "tsc=ok | tests=fail",
                "checks": [{"name": "tsc", "ok": True}, {"name": "tests", "ok": False}],
                "continue_required": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(terminal_control, "DEFAULT_SUPERVISOR_ROOT", root)

    state = terminal_control.load_terminal_control_state(tmp_path / "repo")

    assert state is not None
    assert state["active_task_id"] == "task-42"
    assert state["verification_status"] == "1 failing, 1/2 passing"
    assert state["loop_decision"] == "continue required"
    assert state["next_task"] == "fix verification"


def test_load_terminal_control_state_prefers_persisted_control_summary_preview(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "terminal_supervisor"
    state_dir = root / "run-1" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "run.json").write_text(
        json.dumps(
            {
                "repo_root": str(tmp_path / "repo"),
                "updated_at": "2026-04-02T00:00:00Z",
                "cycle": 4,
                "status": "running",
                "tasks_total": 3,
                "tasks_pending": 1,
                "last_task_id": "task-42",
                "last_continue_required": True,
                "last_summary_fields": {
                    "status": "blocked",
                    "acceptance": "fail",
                    "next_task": "fix verification",
                },
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "verification.json").write_text(
        json.dumps(
            {
                "summary": "tsc=ok | tests=fail",
                "checks": [{"name": "tsc", "ok": True}, {"name": "tests", "ok": False}],
                "continue_required": True,
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "terminal-control-summary.json").write_text(
        json.dumps(
            {
                "run_status": "running_cycle",
                "tasks_total": 5,
                "tasks_pending": 2,
                "active_task_id": "task-summary",
                "verification_status": "all 2 checks passing",
                "verification_passing": "tsc, tests",
                "verification_failing": "none",
                "verification_bundle": "tsc=ok | tests=ok",
                "next_task": "stale field should be ignored by preview",
                "preview_Loop_state": "cycle 5 running_cycle",
                "preview_Task_progress": "3 done, 2 pending of 5",
                "preview_Active_task": "task-preview",
                "preview_Result_status": "in_progress",
                "preview_Acceptance": "pass",
                "preview_Verification_summary": "tsc=ok | tests=ok",
                "preview_Verification_checks": "tsc ok; tests ok",
                "preview_Verification_status": "all 2 checks passing",
                "preview_Verification_passing": "tsc, tests",
                "preview_Verification_failing": "none",
                "preview_Verification_bundle": "tsc=ok | tests=ok",
                "preview_Loop_decision": "ready to stop",
                "preview_Next_task": "ship control preview to dashboard",
                "preview_Runtime_DB": "/tmp/runtime.db",
                "preview_Runtime_summary": "/tmp/runtime.db | 12 sessions | 2 runs",
                "preview_Runtime_freshness": "cycle 5 running_cycle | updated 2026-04-02T02:00:00Z | verify tsc=ok | tests=ok",
                "preview_Recent_operator_actions": "reroute by operator (better frontier model)",
                "preview_Updated": "2026-04-02T02:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(terminal_control, "DEFAULT_SUPERVISOR_ROOT", root)

    state = terminal_control.load_terminal_control_state(tmp_path / "repo")

    assert state is not None
    assert state["cycle"] == 4
    assert state["run_status"] == "running_cycle"
    assert state["tasks_total"] == 5
    assert state["tasks_pending"] == 2
    assert state["active_task_id"] == "task-preview"
    assert state["last_result_status"] == "in_progress"
    assert state["acceptance"] == "pass"
    assert state["verification_summary"] == "tsc=ok | tests=ok"
    assert state["verification_checks"] == ["tsc ok", "tests ok"]
    assert state["verification_status"] == "all 2 checks passing"
    assert state["loop_decision"] == "ready to stop"
    assert state["next_task"] == "ship control preview to dashboard"
    assert state["loop_state"] == "cycle 5 running_cycle"
    assert state["task_progress"] == "3 done, 2 pending of 5"
    assert state["runtime_db"] == "/tmp/runtime.db"
    assert state["runtime_summary"] == "/tmp/runtime.db | 12 sessions | 2 runs"
    assert state["runtime_freshness"].startswith("cycle 5 running_cycle")
    assert state["recent_operator_actions"] == "reroute by operator (better frontier model)"
    assert state["updated_at"] == "2026-04-02T02:00:00Z"


def test_load_terminal_control_state_normalizes_generic_verification_preview_fields(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "terminal_supervisor"
    state_dir = root / "run-1" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "run.json").write_text(
        json.dumps(
            {
                "repo_root": str(tmp_path / "repo"),
                "updated_at": "2026-04-02T00:00:00Z",
                "cycle": 4,
                "status": "running",
                "tasks_total": 3,
                "tasks_pending": 1,
                "last_task_id": "task-42",
                "last_continue_required": True,
                "last_summary_fields": {
                    "status": "blocked",
                    "acceptance": "fail",
                    "next_task": "fix verification",
                },
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "verification.json").write_text(
        json.dumps(
            {
                "summary": "tsc=ok | tests=fail",
                "checks": [{"name": "tsc", "ok": True}, {"name": "tests", "ok": False}],
                "continue_required": True,
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "terminal-control-summary.json").write_text(
        json.dumps(
            {
                "preview_Verification_summary": "ok",
                "preview_Verification_checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
                "preview_Verification_status": "passing",
                "preview_Verification_passing": "ok",
                "preview_Verification_failing": "fail",
                "preview_Verification_bundle": "ok",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(terminal_control, "DEFAULT_SUPERVISOR_ROOT", root)

    state = terminal_control.load_terminal_control_state(tmp_path / "repo")

    assert state is not None
    assert state["verification_summary"] == "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail"
    assert state["verification_checks"] == ["tsc ok", "bridge_snapshots ok", "cycle_acceptance fail"]
    assert state["verification_status"] == "1 failing, 2/3 passing"
    assert state["verification_passing"] == "tsc, bridge_snapshots"
    assert state["verification_failing"] == "cycle_acceptance"
    assert state["verification_bundle"] == "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail"
