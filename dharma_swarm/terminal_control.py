"""Shared terminal-control state loader for dashboard and terminal bridge.

Reads the persisted overnight supervisor state and exposes a compact,
shell-neutral summary so the dashboard and terminal stop diverging on
verification and resume truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SUPERVISOR_ROOT = Path.home() / ".dharma" / "terminal_supervisor"
CONTROL_SUMMARY_FILENAME = "terminal-control-summary.json"
SUPERVISOR_STATE_ENV_VARS = (
    "DHARMA_TERMINAL_SUPERVISOR_STATE_DIR",
    "DHARMA_TERMINAL_STATE_DIR",
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summary_field(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return value.strip() if isinstance(value, str) else ""


def _string_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _preview_storage_key(label: str) -> str:
    return f"preview_{label.replace(' ', '_')}"


def _preview_field(record: dict[str, Any], label: str, *keys: str) -> str:
    preview_value = _string_field(record, _preview_storage_key(label))
    if preview_value:
        return preview_value
    return _string_field(record, *keys)


def _parse_verification_checks(value: Any) -> list[str]:
    if isinstance(value, list):
        checks: list[str] = []
        for check in value:
            if not isinstance(check, dict):
                continue
            name = str(check.get("name", "") or "").strip()
            if not name:
                continue
            ok = bool(check.get("ok"))
            checks.append(f"{name} {'ok' if ok else 'fail'}")
        return checks
    if isinstance(value, str):
        return [part.strip() for part in value.split(";") if part.strip()]
    return []


def _parse_verification_bundle(checks_text: str, summary_text: str = "") -> list[dict[str, Any]]:
    from_checks: list[dict[str, Any]] = []
    for part in checks_text.split(";"):
        part = part.strip()
        if not part or part.lower() == "none":
            continue
        if part.lower().endswith(" ok"):
            from_checks.append({"name": part[:-3].strip(), "ok": True})
        elif part.lower().endswith(" fail"):
            from_checks.append({"name": part[:-5].strip(), "ok": False})
    if from_checks:
        return from_checks

    from_summary: list[dict[str, Any]] = []
    for part in summary_text.split("|"):
        part = part.strip()
        if not part or part.lower() == "none" or "=" not in part:
            continue
        name, status = [item.strip() for item in part.split("=", 1)]
        if not name:
            continue
        from_summary.append({"name": name, "ok": status.lower() == "ok"})
    return from_summary


def _build_verification_summary(checks: list[dict[str, Any]]) -> dict[str, str]:
    if not checks:
        return {
            "status": "unknown",
            "passing": "unknown",
            "failing": "unknown",
            "bundle": "none",
        }
    passing = [check["name"] for check in checks if check.get("ok")]
    failing = [check["name"] for check in checks if not check.get("ok")]
    return {
        "status": (
            f"{len(failing)} failing, {len(passing)}/{len(checks)} passing"
            if failing
            else f"all {len(checks)} checks passing"
        ),
        "passing": ", ".join(passing) if passing else "none",
        "failing": ", ".join(failing) if failing else "none",
        "bundle": " | ".join(f"{check['name']}={'ok' if check['ok'] else 'fail'}" for check in checks),
    }


def _is_generic_verification_label(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "",
        "ok",
        "pass",
        "passing",
        "fail",
        "failing",
        "failed",
        "error",
        "none",
        "unknown",
        "n/a",
    }


def candidate_supervisor_state_dirs() -> list[Path]:
    explicit = [
        Path(value.strip())
        for name in SUPERVISOR_STATE_ENV_VARS
        for value in [os.getenv(name, "")]
        if value.strip()
    ]
    if explicit:
        return explicit
    if not DEFAULT_SUPERVISOR_ROOT.exists():
        return []
    return [
        child / "state"
        for child in DEFAULT_SUPERVISOR_ROOT.iterdir()
        if child.is_dir()
    ]


def resolve_supervisor_state_dir(repo_root: str | Path) -> Path | None:
    repo_root = Path(repo_root).resolve()
    candidates: list[tuple[Path, str, float]] = []
    for state_dir in candidate_supervisor_state_dirs():
        run_path = state_dir / "run.json"
        if not run_path.exists():
            continue
        run = _read_json(run_path)
        run_repo_root = str(run.get("repo_root", "") or "").strip()
        if run_repo_root and Path(run_repo_root).resolve() != repo_root:
            continue
        updated_at = str(run.get("updated_at", "") or "")
        try:
            mtime = run_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((state_dir, updated_at, mtime))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return candidates[0][0]


def load_terminal_control_state(repo_root: str | Path) -> dict[str, Any] | None:
    state_dir = resolve_supervisor_state_dir(repo_root)
    if state_dir is None:
        return None

    run = _read_json(state_dir / "run.json")
    verification = _read_json(state_dir / "verification.json")
    control_summary = _read_json(state_dir / CONTROL_SUMMARY_FILENAME)
    summary = _as_record(run.get("last_summary_fields"))
    last_verification = _as_record(run.get("last_verification"))
    checks = _parse_verification_checks(
        control_summary.get("verification_checks")
        or control_summary.get(_preview_storage_key("Verification checks"))
        or (verification.get("checks") if "checks" in verification else last_verification.get("checks"))
    )

    verification_summary = _preview_field(
        control_summary,
        "Verification summary",
        "verification_summary",
    )
    if not verification_summary:
        verification_summary = _string_field(
            verification,
            "summary",
        ) or _string_field(last_verification, "summary")

    continue_required = verification.get("continue_required")
    if not isinstance(continue_required, bool):
        continue_required = control_summary.get("continue_required")
    if not isinstance(continue_required, bool):
        continue_required = run.get("last_continue_required")
    if not isinstance(continue_required, bool):
        continue_required = None

    verification_rows = _build_verification_summary(
        _parse_verification_bundle("; ".join(checks), verification_summary or "none")
    )
    if _is_generic_verification_label(verification_summary):
        verification_summary = verification_rows["bundle"]
    verification_status = (
        _preview_field(control_summary, "Verification status", "verification_status")
        or verification_rows["status"]
    )
    if _is_generic_verification_label(verification_status):
        verification_status = verification_rows["status"]
    verification_passing = (
        _preview_field(control_summary, "Verification passing", "verification_passing")
        or verification_rows["passing"]
    )
    if _is_generic_verification_label(verification_passing):
        verification_passing = verification_rows["passing"]
    verification_failing = (
        _preview_field(control_summary, "Verification failing", "verification_failing")
        or verification_rows["failing"]
    )
    if _is_generic_verification_label(verification_failing):
        verification_failing = verification_rows["failing"]
    verification_bundle = (
        _preview_field(control_summary, "Verification bundle", "verification_bundle")
        or verification_rows["bundle"]
    )
    if _is_generic_verification_label(verification_bundle):
        verification_bundle = verification_rows["bundle"]
    active_task_id = (
        _preview_field(control_summary, "Active task", "active_task_id")
        or str(run.get("last_task_id", "") or "")
    )
    last_result_status = (
        _preview_field(control_summary, "Result status", "last_result_status")
        or _summary_field(summary, "status")
    )
    acceptance = _preview_field(control_summary, "Acceptance", "acceptance") or _summary_field(summary, "acceptance")
    next_task = _preview_field(control_summary, "Next task", "next_task") or _summary_field(summary, "next_task")
    updated_at = _preview_field(control_summary, "Updated", "updated_at") or str(run.get("updated_at", "") or "")
    task_progress = _preview_field(control_summary, "Task progress")
    runtime_summary = _preview_field(control_summary, "Runtime summary", "runtime_summary")
    runtime_freshness = _preview_field(control_summary, "Runtime freshness", "runtime_freshness")

    return {
        "state_dir": str(state_dir),
        "cycle": control_summary.get("cycle") if isinstance(control_summary.get("cycle"), int) else run.get("cycle") if isinstance(run.get("cycle"), int) else None,
        "run_status": _string_field(control_summary, "run_status") or str(run.get("status", "unknown") or "unknown"),
        "tasks_total": control_summary.get("tasks_total") if isinstance(control_summary.get("tasks_total"), int) else run.get("tasks_total") if isinstance(run.get("tasks_total"), int) else None,
        "tasks_pending": control_summary.get("tasks_pending") if isinstance(control_summary.get("tasks_pending"), int) else run.get("tasks_pending") if isinstance(run.get("tasks_pending"), int) else None,
        "active_task_id": active_task_id,
        "last_result_status": last_result_status,
        "acceptance": acceptance,
        "verification_summary": verification_summary,
        "verification_checks": checks,
        "verification_status": verification_status,
        "verification_passing": verification_passing,
        "verification_failing": verification_failing,
        "verification_bundle": verification_bundle,
        "continue_required": continue_required,
        "loop_decision": _preview_field(control_summary, "Loop decision", "loop_decision")
        or (
            "continue required"
            if continue_required is True
            else "ready to stop"
            if continue_required is False
            else "unknown"
        ),
        "next_task": next_task,
        "updated_at": updated_at,
        "loop_state": _preview_field(control_summary, "Loop state", "loop_state"),
        "task_progress": task_progress,
        "last_result": _preview_field(control_summary, "Last result", "last_result"),
        "runtime_db": _preview_field(control_summary, "Runtime DB", "runtime_db"),
        "session_state": _preview_field(control_summary, "Session state", "session_state"),
        "run_state": _preview_field(control_summary, "Run state", "run_state"),
        "active_runs_detail": _preview_field(control_summary, "Active runs detail", "active_runs_detail"),
        "context_state": _preview_field(control_summary, "Context state", "context_state"),
        "recent_operator_actions": _preview_field(
            control_summary,
            "Recent operator actions",
            "recent_operator_actions",
        ),
        "runtime_activity": _preview_field(control_summary, "Runtime activity", "runtime_activity"),
        "artifact_state": _preview_field(control_summary, "Artifact state", "artifact_state"),
        "toolchain": _preview_field(control_summary, "Toolchain", "toolchain"),
        "alerts": _preview_field(control_summary, "Alerts", "alerts"),
        "runtime_summary": runtime_summary,
        "runtime_freshness": runtime_freshness,
    }
