from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


ROOT = Path.home() / "dharma_swarm"
STATE = Path.home() / ".dharma"
LOG_ROOT = STATE / "logs" / "codex_overnight"
HEARTBEAT_FILE = STATE / "codex_overnight_heartbeat.json"
RUN_FILE = STATE / "codex_overnight_run_dir.txt"

DEFAULT_MISSION = (
    "Continue the highest-leverage work in dharma_swarm autonomously. "
    "Inspect the current repo state each cycle, choose one bounded slice, "
    "implement it end-to-end when feasible, run focused verification, and "
    "leave the tree in a clean explainable state without committing or pushing."
)


@dataclass(slots=True)
class GitSnapshot:
    branch: str
    head: str
    dirty: bool
    changed_files: list[str]
    staged_count: int
    unstaged_count: int
    untracked_count: int


@dataclass(slots=True)
class RunSettings:
    label: str
    hours: float
    poll_seconds: int
    cycle_timeout: int
    max_cycles: int
    model: str


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def heartbeat_file_for(state_dir: Path) -> Path:
    return state_dir / "codex_overnight_heartbeat.json"


def run_file_for(state_dir: Path) -> Path:
    return state_dir / "codex_overnight_run_dir.txt"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        input=input_text,
        capture_output=True,
        timeout=timeout,
    )


def _safe_text(text: str, *, limit: int = 1200) -> str:
    squashed = " ".join(text.split())
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3] + "..."


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _resolve_cycle_summary(*, output_file: Path, stdout: str) -> str:
    if output_file.exists():
        summary_text = output_file.read_text(encoding="utf-8", errors="ignore").strip()
        if summary_text:
            return summary_text
    return stdout.strip()


def parse_summary_fields(summary_text: str) -> dict[str, str]:
    fields = {
        "result": "",
        "files": "",
        "tests": "",
        "blockers": "",
    }
    for line in summary_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower()
        if normalized in fields:
            fields[normalized] = value.strip()
    return fields


def _parse_files_field(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if not value or value.lower() == "none":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_run_manifest(
    *,
    run_dir: Path,
    repo_root: Path,
    state_dir: Path,
    mission: str,
    settings: RunSettings,
    initial_snapshot: GitSnapshot,
) -> Path:
    mission_file = run_dir / "mission_brief.md"
    mission_file.write_text(mission.rstrip() + "\n", encoding="utf-8")
    manifest_file = run_dir / "run_manifest.json"
    payload = {
        "run_id": run_dir.name,
        "label": settings.label,
        "created_at": utc_ts(),
        "repo_root": str(repo_root),
        "state_dir": str(state_dir),
        "mission_file": str(mission_file),
        "mission_excerpt": _safe_text(mission, limit=300),
        "settings": asdict(settings),
        "initial_git_snapshot": asdict(initial_snapshot),
    }
    write_json(manifest_file, payload)
    return manifest_file


def _update_run_manifest(
    manifest_file: Path,
    *,
    latest_cycle: dict[str, Any],
    cycle_count: int,
) -> None:
    payload = _read_json(manifest_file)
    payload["updated_at"] = utc_ts()
    payload["cycles_completed"] = cycle_count
    payload["latest_cycle"] = latest_cycle
    payload["latest_summary_fields"] = latest_cycle.get("summary_fields", {})
    payload["final_git_snapshot"] = latest_cycle.get("after", {})
    write_json(manifest_file, payload)


def write_morning_handoff(
    *,
    run_dir: Path,
    state_dir: Path,
    mission: str,
    settings: RunSettings,
    snapshots: Sequence[dict[str, Any]],
) -> Path:
    latest = snapshots[-1] if snapshots else {}
    summary_fields = latest.get("summary_fields", {})
    files = _parse_files_field(str(summary_fields.get("files", "")))
    lines = [
        "# Codex Overnight Handoff",
        "",
        f"- updated_at: {utc_ts()}",
        f"- label: {settings.label}",
        f"- run_dir: {run_dir}",
        f"- cycles_completed: {len(snapshots)}",
        f"- mission: {_safe_text(mission, limit=220)}",
    ]
    if latest:
        lines.extend(
            [
                f"- latest_cycle: {latest.get('cycle', 0)}",
                f"- latest_rc: {latest.get('rc', 1)}",
                f"- latest_timed_out: {latest.get('timed_out', False)}",
                "",
                "## Latest Result",
                "",
                f"- result: {summary_fields.get('result', '') or '(missing)'}",
                f"- files: {', '.join(files) if files else 'none'}",
                f"- tests: {summary_fields.get('tests', '') or 'not reported'}",
                f"- blockers: {summary_fields.get('blockers', '') or 'none'}",
                "",
                "## Recent Cycles",
                "",
            ]
        )
        recent = list(snapshots)[-5:]
        for snapshot in recent:
            recent_fields = snapshot.get("summary_fields", {})
            lines.append(
                f"- cycle {snapshot.get('cycle', 0):03d}: "
                f"rc={snapshot.get('rc', 1)} "
                f"timed_out={snapshot.get('timed_out', False)} "
                f"result={recent_fields.get('result', '') or '(missing)'}"
            )
    else:
        lines.extend(["", "No cycles completed yet."])

    handoff_text = "\n".join(lines) + "\n"
    handoff_file = run_dir / "morning_handoff.md"
    handoff_file.write_text(handoff_text, encoding="utf-8")
    shared_handoff = state_dir / "shared" / "codex_overnight_handoff.md"
    shared_handoff.parent.mkdir(parents=True, exist_ok=True)
    shared_handoff.write_text(handoff_text, encoding="utf-8")
    return handoff_file


def _read_mission(args: argparse.Namespace) -> str:
    if args.mission_file:
        return Path(args.mission_file).expanduser().read_text(encoding="utf-8").strip()
    if args.mission_brief:
        return args.mission_brief.strip()
    return DEFAULT_MISSION


def gather_git_snapshot(repo_root: Path) -> GitSnapshot:
    branch = "unknown"
    head = "unknown"
    changed_files: list[str] = []
    staged_count = 0
    unstaged_count = 0
    untracked_count = 0

    status_proc = run_cmd(
        ["git", "status", "--porcelain=v1", "--branch"],
        cwd=repo_root,
        timeout=30,
    )
    if status_proc.returncode == 0:
        lines = status_proc.stdout.splitlines()
        if lines and lines[0].startswith("## "):
            branch = lines[0][3:].strip()
        for line in lines[1:]:
            if not line.strip():
                continue
            changed_files.append(line.rstrip())
            x = line[0]
            y = line[1]
            if line.startswith("??"):
                untracked_count += 1
                continue
            if x != " ":
                staged_count += 1
            if y != " ":
                unstaged_count += 1

    head_proc = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=30)
    if head_proc.returncode == 0:
        head = head_proc.stdout.strip()

    return GitSnapshot(
        branch=branch,
        head=head,
        dirty=bool(changed_files),
        changed_files=changed_files[:40],
        staged_count=staged_count,
        unstaged_count=unstaged_count,
        untracked_count=untracked_count,
    )


def render_git_snapshot(snapshot: GitSnapshot) -> str:
    changed = "\n".join(f"- {line}" for line in snapshot.changed_files) or "- clean"
    return (
        f"branch: {snapshot.branch}\n"
        f"head: {snapshot.head}\n"
        f"dirty: {snapshot.dirty}\n"
        f"staged_count: {snapshot.staged_count}\n"
        f"unstaged_count: {snapshot.unstaged_count}\n"
        f"untracked_count: {snapshot.untracked_count}\n"
        f"changed_files:\n{changed}"
    )


def read_previous_summary(run_dir: Path, *, limit_chars: int = 3000) -> str:
    latest_output = run_dir / "latest_last_message.txt"
    if not latest_output.exists():
        return "(No previous cycle output.)"
    return latest_output.read_text(encoding="utf-8", errors="ignore")[:limit_chars]


def build_cycle_prompt(
    *,
    mission: str,
    repo_root: Path,
    state_dir: Path,
    cycle: int,
    before: GitSnapshot,
    previous_summary: str,
) -> str:
    dse_readme = repo_root / "docs" / "dse" / "README.md"
    dse_hint = ""
    if dse_readme.exists():
        dse_hint = (
            f"- There is an active DSE document stack at {dse_readme}. "
            "Use it when it is relevant to the current highest-leverage slice.\n"
        )

    return f"""You are running an overnight Codex autonomy cycle for dharma_swarm.

Cycle: {cycle}
Repo root: {repo_root}
Writable state dir: {state_dir}

Mission brief:
{mission}

Current git snapshot:
{render_git_snapshot(before)}

Previous cycle summary:
{previous_summary}

Operational rules:
- Inspect the current worktree yourself before deciding what to do.
- Choose one bounded, high-leverage slice that can be completed in this cycle.
- Respect existing uncommitted user changes. Do not revert, overwrite, or clean work you did not make.
- Do not commit, push, reset, or open PRs.
- Prefer concrete code, tests, and verification over broad planning.
- If the best next move is preparatory, make it specific and useful: tests, docs, build packet, or a small refactor seam.
- Run focused verification after edits whenever feasible.
- If unrelated failures block full verification, note them clearly and still finish the bounded slice.
{dse_hint}- You may read and write under the repo root and {state_dir}.

At the end, respond in this exact shape:
RESULT: <one short paragraph>
FILES: <comma-separated file paths or "none">
TESTS: <what you ran or "not run">
BLOCKERS: <short note or "none">
"""


def build_codex_exec_command(
    *,
    repo_root: Path,
    state_dir: Path,
    output_file: Path,
    model: str = "",
) -> list[str]:
    cmd = [
        "codex",
        "exec",
        "--full-auto",
        "-C",
        str(repo_root),
        "--add-dir",
        str(state_dir),
        "-o",
        str(output_file),
        "-",
    ]
    if model.strip():
        cmd[2:2] = ["-m", model.strip()]
    return cmd


def append_cycle_report(
    *,
    report_file: Path,
    cycle: int,
    started_at: str,
    duration_sec: float,
    prompt_file: Path,
    output_file: Path,
    summary_text: str,
    rc: int,
    before: GitSnapshot,
    after: GitSnapshot,
) -> None:
    lines = [
        f"## Cycle {cycle:03d}",
        f"- started_at: {started_at}",
        f"- duration_sec: {duration_sec:.1f}",
        f"- rc: {rc}",
        f"- prompt_file: {prompt_file}",
        f"- output_file: {output_file}",
        f"- before_dirty: {before.dirty}",
        f"- after_dirty: {after.dirty}",
        f"- before_changed: {len(before.changed_files)}",
        f"- after_changed: {len(after.changed_files)}",
        "",
        "Summary:",
        "",
        _safe_text(summary_text, limit=1800),
        "",
    ]
    append_text(report_file, "\n".join(lines))


def run_cycle(
    *,
    repo_root: Path,
    state_dir: Path,
    run_dir: Path,
    cycle: int,
    mission: str,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    before = gather_git_snapshot(repo_root)
    previous_summary = read_previous_summary(run_dir)
    prompt = build_cycle_prompt(
        mission=mission,
        repo_root=repo_root,
        state_dir=state_dir,
        cycle=cycle,
        before=before,
        previous_summary=previous_summary,
    )

    prompts_dir = run_dir / "prompts"
    outputs_dir = run_dir / "outputs"
    logs_dir = run_dir / "logs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = prompts_dir / f"cycle_{cycle:03d}.md"
    output_file = outputs_dir / f"cycle_{cycle:03d}_last_message.txt"
    stdout_file = logs_dir / f"cycle_{cycle:03d}_stdout.log"
    prompt_file.write_text(prompt, encoding="utf-8")

    cmd = build_codex_exec_command(
        repo_root=repo_root,
        state_dir=state_dir,
        output_file=output_file,
        model=model,
    )

    started_at = utc_ts()
    start = time.time()
    timed_out = False
    try:
        proc = run_cmd(cmd, cwd=repo_root, timeout=timeout, input_text=prompt)
        stdout = _coerce_text(proc.stdout) + _coerce_text(proc.stderr)
        rc = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (
            _coerce_text(getattr(exc, "stdout", None) or getattr(exc, "output", None))
            + _coerce_text(exc.stderr)
        )
        rc = 124
    duration_sec = time.time() - start

    stdout_file.write_text(stdout, encoding="utf-8", errors="ignore")
    if not output_file.exists():
        output_file.write_text("", encoding="utf-8")

    summary_text = _resolve_cycle_summary(output_file=output_file, stdout=stdout)
    summary_fields = parse_summary_fields(summary_text)
    (run_dir / "latest_last_message.txt").write_text(summary_text + "\n", encoding="utf-8")

    after = gather_git_snapshot(repo_root)
    report_file = run_dir / "report.md"
    append_cycle_report(
        report_file=report_file,
        cycle=cycle,
        started_at=started_at,
        duration_sec=duration_sec,
        prompt_file=prompt_file,
        output_file=output_file,
        summary_text=summary_text or stdout,
        rc=rc,
        before=before,
        after=after,
    )

    snapshot = {
        "cycle": cycle,
        "ts": utc_ts(),
        "started_at": started_at,
        "duration_sec": round(duration_sec, 2),
        "rc": rc,
        "timed_out": timed_out,
        "prompt_file": str(prompt_file),
        "output_file": str(output_file),
        "stdout_file": str(stdout_file),
        "summary_text": summary_text,
        "summary_fields": summary_fields,
        "before": asdict(before),
        "after": asdict(after),
    }
    append_jsonl(run_dir / "cycles.jsonl", snapshot)
    write_json(run_dir / "latest.json", snapshot)
    write_json(
        heartbeat_file_for(state_dir),
        {
            "ts": utc_ts(),
            "cycle": cycle,
            "run_dir": str(run_dir),
            "duration_sec": round(duration_sec, 2),
            "rc": rc,
            "timed_out": timed_out,
            "report_file": str(report_file),
            "result": summary_fields.get("result", ""),
            "blockers": summary_fields.get("blockers", ""),
        },
    )
    return snapshot


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Codex overnight in repeated autonomous cycles.")
    parser.add_argument("--hours", type=float, default=8.0, help="Wall-clock hours to run. Use 0 for continuous.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Sleep between cycles.")
    parser.add_argument("--cycle-timeout", type=int, default=5400, help="Per-cycle Codex timeout in seconds.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional hard cap on cycle count.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repo root to run in.")
    parser.add_argument("--state-dir", default=str(STATE), help="State directory for logs and heartbeat.")
    parser.add_argument("--mission-brief", default="", help="Inline mission brief override.")
    parser.add_argument("--mission-file", default="", help="Read mission brief from a file.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument("--label", default="codex-overnight", help="Short operator label for this run.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repo_root = Path(args.repo_root).expanduser()
    state_dir = Path(args.state_dir).expanduser()
    run_dir = state_dir / "logs" / "codex_overnight" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    run_file = run_file_for(state_dir)
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_file.write_text(str(run_dir), encoding="utf-8")

    mission = _read_mission(args)
    settings = RunSettings(
        label=args.label.strip() or "codex-overnight",
        hours=args.hours,
        poll_seconds=args.poll_seconds,
        cycle_timeout=args.cycle_timeout,
        max_cycles=args.max_cycles,
        model=args.model.strip(),
    )
    initial_snapshot = gather_git_snapshot(repo_root)
    manifest_file = _write_run_manifest(
        run_dir=run_dir,
        repo_root=repo_root,
        state_dir=state_dir,
        mission=mission,
        settings=settings,
        initial_snapshot=initial_snapshot,
    )
    append_text(
        run_dir / "report.md",
        "\n".join(
            [
                f"# Codex Overnight Run — {utc_ts()}",
                "",
                f"- repo_root: {repo_root}",
                f"- state_dir: {state_dir}",
                f"- label: {settings.label}",
                f"- mission: {_safe_text(mission, limit=300)}",
                f"- manifest: {manifest_file}",
                "",
            ]
        ),
    )

    end_at = time.time() + (args.hours * 3600.0) if args.hours > 0 else None
    cycle = 0
    latest: dict[str, Any] = {}
    cycle_snapshots: list[dict[str, Any]] = []
    while True:
        cycle += 1
        latest = run_cycle(
            repo_root=repo_root,
            state_dir=state_dir,
            run_dir=run_dir,
            cycle=cycle,
            mission=mission,
            model=args.model,
            timeout=args.cycle_timeout,
        )
        cycle_snapshots.append(latest)
        _update_run_manifest(
            manifest_file,
            latest_cycle=latest,
            cycle_count=len(cycle_snapshots),
        )
        write_morning_handoff(
            run_dir=run_dir,
            state_dir=state_dir,
            mission=mission,
            settings=settings,
            snapshots=cycle_snapshots,
        )
        if args.once:
            break
        if args.max_cycles > 0 and cycle >= args.max_cycles:
            break
        if end_at is not None and time.time() >= end_at:
            break
        time.sleep(max(1, args.poll_seconds))

    print(
        f"codex_overnight cycle={latest.get('cycle', 0)} "
        f"rc={latest.get('rc', 1)} run_dir={run_dir} "
        f"report={run_dir / 'report.md'}"
    )
    return 0


__all__ = [
    "DEFAULT_MISSION",
    "GitSnapshot",
    "RunSettings",
    "build_arg_parser",
    "build_codex_exec_command",
    "build_cycle_prompt",
    "gather_git_snapshot",
    "main",
    "parse_summary_fields",
    "render_git_snapshot",
    "write_morning_handoff",
]
