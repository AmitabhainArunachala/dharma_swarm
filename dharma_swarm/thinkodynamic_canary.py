"""Closed-loop live canary for thinkodynamic mission execution."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
GENERIC_WORKFLOW_TITLES = {
    "literature review",
    "framework design",
    "algorithm development",
    "pilot project",
    "documentation and dissemination",
}
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "into",
    "from",
    "this",
    "that",
    "build",
    "install",
    "coordination",
    "impact",
    "living",
    "layer",
    "ai",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_ts() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug_ts() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        handle.write("\n")


def _coerce_text(text: str | bytes) -> str:
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text


def _append_text(path: Path, text: str | bytes) -> None:
    _ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_coerce_text(text))


def _write_text(path: Path, text: str | bytes) -> None:
    _ensure_dir(path.parent)
    path.write_text(_coerce_text(text), encoding="utf-8")


def _tokenize(text: str) -> set[str]:
    cleaned = []
    for char in text.lower():
        cleaned.append(char if char.isalnum() else " ")
    return {
        token
        for token in "".join(cleaned).split()
        if len(token) > 2 and token not in STOPWORDS
    }


def _first_top_signal_path(summary_path: Path) -> str | None:
    if not summary_path.exists():
        return None
    lines = summary_path.read_text(encoding="utf-8").splitlines()
    in_top_signals = False
    for line in lines:
        if line.startswith("## Top Signals"):
            in_top_signals = True
            continue
        if in_top_signals and line.startswith("## "):
            break
        if in_top_signals and line.startswith("- "):
            return line[2:].split(" :: ", 1)[0].strip()
    return None


@dataclass
class Finding:
    severity: str
    code: str
    detail: str


@dataclass
class TaskSnapshot:
    counts: dict[str, int] = field(default_factory=dict)
    active_director_task_ids: set[str] = field(default_factory=set)
    recent_director_task_ids: set[str] = field(default_factory=set)
    latest_director_tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommandResult:
    argv: list[str]
    rc: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool = False


@dataclass
class CycleAssessment:
    observed_at: str
    status: str
    score: int
    cycle_id: str
    delegated: bool
    active_before: int
    max_active_tasks: int
    new_director_task_ids: list[str]
    findings: list[Finding]
    summary_path: str
    snapshot_path: str
    command_rc: int
    command_elapsed_s: float
    integration_probe_rc: int | None = None


def collect_task_snapshot(state_dir: Path) -> TaskSnapshot:
    db_path = state_dir / "db" / "tasks.db"
    if not db_path.exists():
        return TaskSnapshot()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        counts: dict[str, int] = {}
        for row in cur.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"):
            counts[str(row["status"])] = int(row["count"])

        active_ids = {
            str(row["id"])
            for row in cur.execute(
                "SELECT id FROM tasks WHERE created_by='thinkodynamic_director' "
                "AND status NOT IN ('completed', 'failed', 'cancelled')"
            )
        }

        latest_tasks = []
        for row in cur.execute(
            "SELECT id, title, status, created_at, assigned_to "
            "FROM tasks WHERE created_by='thinkodynamic_director' "
            "ORDER BY datetime(created_at) DESC LIMIT 12"
        ):
            latest_tasks.append(
                {
                    "id": str(row["id"]),
                    "title": str(row["title"]),
                    "status": str(row["status"]),
                    "created_at": str(row["created_at"]),
                    "assigned_to": str(row["assigned_to"] or ""),
                }
            )

        recent_ids = {task["id"] for task in latest_tasks}

        return TaskSnapshot(
            counts=counts,
            active_director_task_ids=active_ids,
            recent_director_task_ids=recent_ids,
            latest_director_tasks=latest_tasks,
        )
    finally:
        conn.close()


def run_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    env: dict[str, str] | None = None,
) -> CommandResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env or os.environ.copy(),
        )
        return CommandResult(
            argv=argv,
            rc=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_s=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            argv=argv,
            rc=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            elapsed_s=time.monotonic() - started,
            timed_out=True,
        )


def _workflow_title_is_generic(snapshot: dict[str, Any]) -> bool:
    workflow = snapshot.get("workflow") or {}
    title = str(workflow.get("opportunity_title") or "").strip()
    stripped = title.lower().rstrip("*").strip()
    if title.endswith("**") or stripped in GENERIC_WORKFLOW_TITLES:
        return True

    selected = snapshot.get("selected_opportunity") or {}
    selected_title = str(selected.get("title") or "").strip()
    if not title or not selected_title:
        return False
    title_tokens = _tokenize(title)
    selected_tokens = _tokenize(selected_title)
    return bool(title_tokens and selected_tokens and title_tokens.isdisjoint(selected_tokens))


def _review_is_stale(snapshot: dict[str, Any]) -> bool:
    workflow = snapshot.get("workflow") or {}
    review = snapshot.get("review") or {}
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    review_id = str(review.get("workflow_id") or "").strip()
    return bool(workflow_id and review_id and workflow_id != review_id)


def _live_council_disabled(snapshot: dict[str, Any]) -> bool:
    council = snapshot.get("council") or {}
    turns = council.get("turns") or []
    if not turns:
        return False
    return all(not turn.get("success") for turn in turns) and any(
        "live council disabled" in str(turn.get("error") or "").lower()
        for turn in turns
    )


def _review_counts_are_stale(snapshot: dict[str, Any], post_tasks: TaskSnapshot) -> bool:
    review = snapshot.get("review") or {}
    delegated_ids = list(snapshot.get("delegated_task_ids") or [])
    if not review or not delegated_ids:
        return False

    task_map = {task["id"]: task for task in post_tasks.latest_director_tasks}
    live_statuses = [task_map[task_id]["status"] for task_id in delegated_ids if task_id in task_map]
    if not live_statuses:
        return False

    live_completed = sum(1 for status in live_statuses if status == "completed")
    live_failed = sum(1 for status in live_statuses if status == "failed")
    live_active = sum(1 for status in live_statuses if status not in TERMINAL_TASK_STATUSES)

    return any(
        (
            int(review.get("completed_count") or 0) != live_completed,
            int(review.get("failed_count") or 0) != live_failed,
            int(review.get("active_count") or 0) != live_active,
        )
    )


def assess_cycle(
    *,
    snapshot: dict[str, Any] | None,
    summary_path: Path,
    command_result: CommandResult,
    pre_tasks: TaskSnapshot,
    post_tasks: TaskSnapshot,
    max_active_tasks: int,
    integration_probe_rc: int | None = None,
) -> CycleAssessment:
    findings: list[Finding] = []
    score = 100

    if command_result.rc != 0:
        findings.append(
            Finding(
                severity="fail",
                code="director_nonzero_exit",
                detail=f"rc={command_result.rc} timed_out={command_result.timed_out}",
            )
        )
        score -= 60

    if not snapshot:
        findings.append(
            Finding(
                severity="fail",
                code="missing_latest_snapshot",
                detail="thinkodynamic_director did not write latest.json",
            )
        )
        return CycleAssessment(
            observed_at=_utc_ts(),
            status="FAIL",
            score=max(0, score - 40),
            cycle_id="",
            delegated=False,
            active_before=0,
            max_active_tasks=max_active_tasks,
            new_director_task_ids=[],
            findings=findings,
            summary_path=str(summary_path),
            snapshot_path="",
            command_rc=command_result.rc,
            command_elapsed_s=round(command_result.elapsed_s, 2),
            integration_probe_rc=integration_probe_rc,
        )

    cycle_id = str(snapshot.get("cycle_id") or "")
    delegated = bool(snapshot.get("delegated"))
    active_before = int(snapshot.get("active_director_tasks_before") or 0)
    snapshot_limit = int(snapshot.get("max_active_tasks") or max_active_tasks)
    new_task_ids = sorted(post_tasks.recent_director_task_ids - pre_tasks.recent_director_task_ids)

    if not delegated:
        if active_before >= snapshot_limit:
            findings.append(
                Finding(
                    severity="degrade",
                    code="queue_saturated",
                    detail=(
                        f"delegated=false because active_director_tasks_before={active_before} "
                        f">= max_active_tasks={snapshot_limit}"
                    ),
                )
            )
            score -= 15
        else:
            findings.append(
                Finding(
                    severity="fail",
                    code="no_delegation",
                    detail="direct mode completed without delegation and without a queue-cap reason",
                )
            )
            score -= 35

    if delegated and not new_task_ids:
        findings.append(
            Finding(
                severity="fail",
                code="delegated_without_new_tasks",
                detail="snapshot says delegated=true but recent thinkodynamic task ids did not change",
            )
        )
        score -= 20

    if _review_is_stale(snapshot):
        findings.append(
            Finding(
                severity="fail",
                code="stale_review",
                detail=(
                    "review.workflow_id does not match workflow.workflow_id; "
                    "the cycle reused a previous review"
                ),
            )
        )
        score -= 25

    if _review_counts_are_stale(snapshot, post_tasks):
        findings.append(
            Finding(
                severity="degrade",
                code="stale_review_counts",
                detail="review counts no longer match the delegated task statuses in the live task board",
            )
        )
        score -= 10

    if _workflow_title_is_generic(snapshot):
        findings.append(
            Finding(
                severity="degrade",
                code="generic_workflow",
                detail="workflow title/tasks look generic or detached from the selected opportunity",
            )
        )
        score -= 15

    if _live_council_disabled(snapshot):
        findings.append(
            Finding(
                severity="degrade",
                code="heuristic_council_only",
                detail="all council turns fell back to heuristic consensus",
            )
        )
        score -= 10

    top_signal_path = _first_top_signal_path(summary_path)
    if top_signal_path and "/tests/" in top_signal_path:
        findings.append(
            Finding(
                severity="degrade",
                code="test_file_ranked_as_primary_signal",
                detail=f"top signal was {top_signal_path}",
            )
        )
        score -= 10

    transcript = "\n".join([command_result.stdout, command_result.stderr])
    if "corrupt marks" in transcript.lower():
        findings.append(
            Finding(
                severity="degrade",
                code="corrupt_stigmergy_marks",
                detail="stigmergy store reported corrupt marks during the cycle",
            )
        )
        score -= 5

    if integration_probe_rc not in (None, 0):
        findings.append(
            Finding(
                severity="degrade",
                code="integration_probe_nonzero",
                detail=f"preflight integration probe rc={integration_probe_rc}",
            )
        )
        score -= 10

    status = "PASS"
    if any(finding.severity == "fail" for finding in findings):
        status = "FAIL"
    elif findings:
        status = "DEGRADE"

    return CycleAssessment(
        observed_at=_utc_ts(),
        status=status,
        score=max(0, score),
        cycle_id=cycle_id,
        delegated=delegated,
        active_before=active_before,
        max_active_tasks=snapshot_limit,
        new_director_task_ids=new_task_ids,
        findings=findings,
        summary_path=str(summary_path),
        snapshot_path="latest.json",
        command_rc=command_result.rc,
        command_elapsed_s=round(command_result.elapsed_s, 2),
        integration_probe_rc=integration_probe_rc,
    )


def _assessment_markdown(assessment: CycleAssessment, post_tasks: TaskSnapshot) -> str:
    lines = [
        f"### Cycle `{assessment.cycle_id or 'unknown'}`",
        f"- observed_at: `{assessment.observed_at}`",
        f"- status: `{assessment.status}` score=`{assessment.score}` delegated=`{assessment.delegated}`",
        f"- command: rc=`{assessment.command_rc}` elapsed_s=`{assessment.command_elapsed_s}`",
        f"- queue: active_before=`{assessment.active_before}` max_active_tasks=`{assessment.max_active_tasks}`",
        f"- new_director_tasks: `{', '.join(assessment.new_director_task_ids) or 'none'}`",
        f"- task_counts: `{json.dumps(post_tasks.counts, sort_keys=True)}`",
        f"- summary: `{assessment.summary_path}`",
    ]
    if assessment.findings:
        lines.append("- findings:")
        for finding in assessment.findings:
            lines.append(
                f"  - [{finding.severity.upper()}] {finding.code}: {finding.detail}"
            )
    else:
        lines.append("- findings: none")
    lines.append("")
    return "\n".join(lines)


def _build_header(args: argparse.Namespace, run_id: str, run_dir: Path) -> str:
    return "\n".join(
        [
            "# Thinkodynamic Live Canary Report",
            "",
            f"- run_id: `{run_id}`",
            f"- started_utc: `{_utc_ts()}`",
            f"- repo_root: `{args.repo_root}`",
            f"- state_dir: `{args.state_dir}`",
            f"- mode: `{args.mode}`",
            f"- hours: `{args.hours}`",
            f"- interval_seconds: `{args.interval_seconds}`",
            f"- max_active_tasks: `{args.max_active_tasks}`",
            f"- max_concurrent_tasks: `{args.max_concurrent_tasks}`",
            f"- run_dir: `{run_dir}`",
            "",
            "## Cycles",
            "",
        ]
    )


def _latest_summary(assessments: list[CycleAssessment]) -> dict[str, Any]:
    totals = {"PASS": 0, "DEGRADE": 0, "FAIL": 0}
    for assessment in assessments:
        totals[assessment.status] = totals.get(assessment.status, 0) + 1
    return {
        "generated_at": _utc_ts(),
        "cycle_count": len(assessments),
        "status_totals": totals,
        "latest_cycle": asdict(assessments[-1]) if assessments else None,
    }


def run_canary(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir).expanduser()
    repo_root = Path(args.repo_root).expanduser()
    run_id = f"thinkodynamic_canary_{_slug_ts()}"
    run_dir = state_dir / "logs" / "thinkodynamic_canary" / run_id
    cycles_jsonl = run_dir / "cycles.jsonl"
    report_md = run_dir / "report.md"
    latest_json = state_dir / "logs" / "thinkodynamic_canary" / "latest.json"
    latest_md = state_dir / "logs" / "thinkodynamic_canary" / "latest.md"
    stop_file = state_dir / "STOP_THINKODYNAMIC_CANARY"

    _ensure_dir(run_dir)
    _write_text(report_md, _build_header(args, run_id, run_dir))

    integration_probe_rc: int | None = None
    if args.preflight_probe:
        preflight = run_command(
            [sys.executable, "scripts/system_integration_probe.py"],
            cwd=repo_root,
            timeout_s=args.preflight_timeout_s,
        )
        integration_probe_rc = preflight.rc
        _write_text(run_dir / "preflight_stdout.log", preflight.stdout)
        _write_text(run_dir / "preflight_stderr.log", preflight.stderr)

    deadline = _utc_now() + timedelta(hours=args.hours)
    assessments: list[CycleAssessment] = []
    cycle_index = 0

    while _utc_now() < deadline:
        if stop_file.exists():
            break

        pre_tasks = collect_task_snapshot(state_dir)
        cycle_cmd = run_command(
            [
                sys.executable,
                "-m",
                "dharma_swarm.thinkodynamic_director",
                "--once",
                "--mode",
                args.mode,
                "--repo-root",
                str(repo_root),
                "--state-dir",
                str(state_dir),
                "--max-active-tasks",
                str(args.max_active_tasks),
                "--max-concurrent-tasks",
                str(args.max_concurrent_tasks),
            ],
            cwd=repo_root,
            timeout_s=args.cycle_timeout_s,
        )

        cycle_stdout = run_dir / f"cycle_{cycle_index:03d}_stdout.log"
        cycle_stderr = run_dir / f"cycle_{cycle_index:03d}_stderr.log"
        _write_text(cycle_stdout, cycle_cmd.stdout)
        _write_text(cycle_stderr, cycle_cmd.stderr)

        latest_snapshot_path = state_dir / "logs" / "thinkodynamic_director" / "latest.json"
        latest_summary_path = state_dir / "shared" / "thinkodynamic_director_latest.md"
        snapshot = _read_json(latest_snapshot_path)
        post_tasks = collect_task_snapshot(state_dir)
        assessment = assess_cycle(
            snapshot=snapshot,
            summary_path=latest_summary_path,
            command_result=cycle_cmd,
            pre_tasks=pre_tasks,
            post_tasks=post_tasks,
            max_active_tasks=args.max_active_tasks,
            integration_probe_rc=integration_probe_rc,
        )

        assessments.append(assessment)
        _append_jsonl(cycles_jsonl, asdict(assessment))
        _append_text(report_md, _assessment_markdown(assessment, post_tasks))
        latest_payload = _latest_summary(assessments)
        _write_text(latest_json, json.dumps(latest_payload, indent=2, sort_keys=True))
        _write_text(
            latest_md,
            "\n".join(
                [
                    "# Thinkodynamic Canary Latest",
                    "",
                    f"- generated_at: `{latest_payload['generated_at']}`",
                    f"- cycle_count: `{latest_payload['cycle_count']}`",
                    f"- status_totals: `{json.dumps(latest_payload['status_totals'], sort_keys=True)}`",
                    f"- report: `{report_md}`",
                    "",
                    _assessment_markdown(assessment, post_tasks),
                ]
            ),
        )

        cycle_index += 1
        if args.max_cycles and cycle_index >= args.max_cycles:
            break

        if _utc_now() >= deadline:
            break

        time.sleep(max(0, args.interval_seconds))

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path.home() / "dharma_swarm"))
    parser.add_argument("--state-dir", default=str(Path.home() / ".dharma"))
    parser.add_argument("--mode", choices=("preview", "direct"), default="direct")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--interval-seconds", type=int, default=1800)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--max-active-tasks", type=int, default=16)
    parser.add_argument("--max-concurrent-tasks", type=int, default=1)
    parser.add_argument("--cycle-timeout-s", type=int, default=1800)
    parser.add_argument("--preflight-timeout-s", type=int, default=180)
    parser.add_argument("--preflight-probe", action="store_true", default=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_canary(args)


if __name__ == "__main__":
    raise SystemExit(main())
