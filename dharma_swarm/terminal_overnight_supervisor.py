"""Durable overnight supervisor for the Bun/Ink Dharma terminal.

This is a launchd-friendly external supervisor. It does not assume a model stays
"awake". Instead it persists state, runs bounded Codex cycles, verifies the
repo after each cycle, and decides whether to continue.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.codex_cli import dgc_codex_exec_prefix
from dharma_swarm.codex_overnight import gather_git_snapshot, run_cmd

STATE_ROOT = Path.home() / ".dharma" / "terminal_supervisor"
REPO_ROOT = Path.home() / "dharma_swarm"
TERMINAL_DIR = REPO_ROOT / "terminal"
PYTHON_BIN = REPO_ROOT / ".venv" / "bin" / "python"

DEFAULT_OBJECTIVE = (
    "Upgrade the Dharma terminal into a repo-aware operator shell. "
    "Each cycle must choose one bounded slice, implement it fully when feasible, "
    "run focused verification, and leave a precise next task if the work is incomplete."
)

DEFAULT_BACKLOG = [
    {
        "id": "terminal-repo-pane",
        "priority": "P0",
        "goal": "Make Repo pane and context mode reflect live git/topology/runtime facts clearly.",
        "acceptance": [
            "repo snapshot includes branch, dirty counts, topology warnings, and hotspot summary",
            "context sidebar surfaces repo and control previews",
            "verification bundle passes",
        ],
        "status": "pending",
    },
    {
        "id": "terminal-command-routing",
        "priority": "P0",
        "goal": "Tighten command routing so slash-command outputs activate the correct pane and do not pollute chat.",
        "acceptance": [
            "command result activates target pane",
            "chat remains conversation-first",
            "verification bundle passes",
        ],
        "status": "pending",
    },
    {
        "id": "terminal-control-surface",
        "priority": "P1",
        "goal": "Improve control/runtime panes so operators can see verification and loop state without reading logs.",
        "acceptance": [
            "control pane shows meaningful state beyond placeholders",
            "verification summary is written to durable state",
            "verification bundle passes",
        ],
        "status": "pending",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def ensure_backlog(path: Path) -> list[dict[str, Any]]:
    if path.exists():
        payload = read_json(path)
        tasks = payload.get("tasks", [])
        if isinstance(tasks, list):
            return [task for task in tasks if isinstance(task, dict)]
    tasks = [dict(task) for task in DEFAULT_BACKLOG]
    write_json(path, {"updated_at": utc_now(), "tasks": tasks})
    return tasks


def parse_summary_fields(summary_text: str) -> dict[str, str]:
    fields = {
        "result": "",
        "files": "",
        "tests": "",
        "blockers": "",
        "next_task": "",
        "status": "",
        "acceptance": "",
    }
    for line in summary_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        if normalized in fields:
            fields[normalized] = value.strip()
    return fields


def parse_csv_field(raw: str) -> list[str]:
    value = raw.strip()
    if not value or value.lower() == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def focused_git_snapshot_text(snapshot: Any) -> str:
    relevant = [
        line for line in list(getattr(snapshot, "changed_files", []))
        if any(
            token in line
            for token in (
                " terminal/",
                " dharma_swarm/terminal_bridge.py",
                " dharma_swarm/dgc_cli.py",
                " docs/TERMINAL",
            )
        )
    ]
    if not relevant:
        relevant = list(getattr(snapshot, "changed_files", []))[:12]
    changed = "\n".join(f"- {line}" for line in relevant) or "- clean"
    return (
        f"branch: {snapshot.branch}\n"
        f"head: {snapshot.head}\n"
        f"dirty: {snapshot.dirty}\n"
        f"staged_count: {snapshot.staged_count}\n"
        f"unstaged_count: {snapshot.unstaged_count}\n"
        f"untracked_count: {snapshot.untracked_count}\n"
        f"focused_changed_files:\n{changed}"
    )


def _looks_like_placeholder(fields: dict[str, str]) -> bool:
    markers = [
        "<one short paragraph>",
        "<comma-separated file paths or \"none\">",
        "<what you ran or \"not run\">",
        "<short note or \"none\">",
        "<one bounded next step or \"none\">",
        "<complete|in_progress|blocked>",
        "<pass|fail>",
    ]
    combined = " ".join(fields.values())
    return any(marker in combined for marker in markers)


def normalize_summary_fields(fields: dict[str, str], stdout: str) -> dict[str, str]:
    normalized = dict(fields)
    lower_stdout = stdout.lower()
    transport_error = (
        "failed to connect to websocket" in lower_stdout
        or "stream disconnected before completion" in lower_stdout
        or "failed to lookup address information" in lower_stdout
    )
    if _looks_like_placeholder(normalized) or transport_error:
        blocker = "codex transport failure" if transport_error else "codex returned placeholder template"
        normalized.update(
            {
                "result": "Supervisor cycle did not receive a valid build summary.",
                "files": "none",
                "tests": "not run",
                "blockers": blocker,
                "next_task": "restore builder connectivity or rerun the same bounded slice in a network-enabled environment",
                "status": "blocked",
                "acceptance": "fail",
            }
        )
    return normalized


def codex_exec_command(*, repo_root: Path, state_dir: Path, output_file: Path, model: str) -> list[str]:
    cmd = dgc_codex_exec_prefix()
    if model.strip():
        cmd.extend(["-m", model.strip()])
    cmd.extend(
        [
            "-C",
            str(repo_root),
            "--add-dir",
            str(state_dir),
            "-o",
            str(output_file),
            "-",
        ]
    )
    return cmd


@dataclass(slots=True)
class SupervisorConfig:
    hours: float = 8.0
    max_cycles: int = 24
    poll_seconds: int = 300
    cycle_timeout: int = 1800
    model: str = ""
    objective: str = DEFAULT_OBJECTIVE
    run_id: str = ""
    once: bool = False


@dataclass(slots=True)
class VerificationBundle:
    ts: str
    checks: list[dict[str, Any]]
    summary: str
    continue_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CycleRecord:
    cycle: int
    started_at: str
    completed_at: str
    rc: int
    timed_out: bool
    summary_fields: dict[str, str]
    verification: dict[str, Any]
    active_task_id: str
    git_before: dict[str, Any]
    git_after: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TerminalOvernightSupervisor:
    def __init__(self, config: SupervisorConfig) -> None:
        self.config = config
        self.run_id = config.run_id.strip() or f"terminal-{utc_slug()}"
        self.run_dir = STATE_ROOT / self.run_id
        self.state_dir = self.run_dir / "state"
        self.logs_dir = self.run_dir / "logs"
        self.prompts_dir = self.run_dir / "prompts"
        self.outputs_dir = self.run_dir / "outputs"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        self.run_path = self.state_dir / "run.json"
        self.backlog_path = self.state_dir / "backlog.json"
        self.verification_path = self.state_dir / "verification.json"
        self.handoff_path = self.state_dir / "handoff.md"
        self.cycles_path = self.state_dir / "cycles.jsonl"
        self.latest_summary_path = self.state_dir / "latest_summary.txt"

    def status(self) -> dict[str, Any]:
        payload = read_json(self.run_path)
        payload["run_dir"] = str(self.run_dir)
        payload["backlog"] = read_json(self.backlog_path)
        payload["verification"] = read_json(self.verification_path)
        return payload

    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        deadline = started + int(self.config.hours * 3600)
        self._write_initial_state()
        cycle = int(read_json(self.run_path).get("cycle", 0))
        last_record: CycleRecord | None = None

        while cycle < self.config.max_cycles and time.monotonic() < deadline:
            cycle += 1
            last_record = self._run_cycle(cycle)
            self._update_run_state(cycle=cycle, last_record=last_record)
            if self.config.once:
                break
            if not self._should_continue(last_record):
                break
            time.sleep(max(1, self.config.poll_seconds))

        return self.status()

    def _write_initial_state(self) -> None:
        tasks = ensure_backlog(self.backlog_path)
        if self.run_path.exists():
            return
        write_json(
            self.run_path,
            {
                "run_id": self.run_id,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "repo_root": str(REPO_ROOT),
                "objective": self.config.objective,
                "cycle": 0,
                "status": "running",
                "tasks_total": len(tasks),
                "last_task_id": "",
                "last_continue_required": True,
            },
        )

    def _select_task(self) -> dict[str, Any]:
        tasks = ensure_backlog(self.backlog_path)
        for task in tasks:
            if str(task.get("status", "pending")) in {"pending", "in_progress"}:
                return task
        return tasks[0] if tasks else {"id": "terminal-generic", "goal": self.config.objective, "acceptance": [], "status": "pending"}

    def _build_prompt(self, *, cycle: int, task: dict[str, Any], git_before: str, previous_summary: str, latest_verification: dict[str, Any]) -> str:
        acceptance_lines = "\n".join(f"- {item}" for item in task.get("acceptance", []))
        verification_summary = latest_verification.get("summary", "No previous verification.")
        return f"""You are running one bounded overnight Codex build cycle for the Dharma terminal.

Cycle: {cycle}
Repo root: {REPO_ROOT}
Durable state dir: {self.state_dir}
Terminal dir: {TERMINAL_DIR}

Global objective:
{self.config.objective}

Active task:
- id: {task.get("id", "unknown")}
- goal: {task.get("goal", "unknown")}
- acceptance:
{acceptance_lines or "- none listed"}

Current git snapshot:
{git_before}

Previous cycle summary:
{previous_summary}

Latest verification summary:
{verification_summary}

Rules:
- Inspect the repo before acting.
- Choose exactly one bounded slice inside the active task.
- Respect existing user changes. Do not revert unrelated work.
- Do not commit, push, reset, or clean the tree.
- Prefer code plus focused verification over broad planning.
- Update terminal/operator surfaces, not generic docs, unless docs are required for the slice.
- Leave a precise next task if the active task is not complete.

At the end, respond in this exact shape:
RESULT: <one short paragraph>
FILES: <comma-separated file paths or "none">
TESTS: <what you ran or "not run">
BLOCKERS: <short note or "none">
NEXT_TASK: <one bounded next step or "none">
STATUS: <complete|in_progress|blocked>
ACCEPTANCE: <pass|fail>
"""

    def _run_cycle(self, cycle: int) -> CycleRecord:
        task = self._select_task()
        started_at = utc_now()
        git_before = gather_git_snapshot(REPO_ROOT)
        previous_summary = self.latest_summary_path.read_text(encoding="utf-8", errors="ignore") if self.latest_summary_path.exists() else "(no previous summary)"
        latest_verification = read_json(self.verification_path)
        self._mark_cycle_started(cycle=cycle, task_id=str(task.get("id", "")))
        prompt = self._build_prompt(
            cycle=cycle,
            task=task,
            git_before=focused_git_snapshot_text(git_before),
            previous_summary=previous_summary[:3000],
            latest_verification=latest_verification,
        )

        prompt_file = self.prompts_dir / f"cycle_{cycle:03d}.md"
        output_file = self.outputs_dir / f"cycle_{cycle:03d}_last_message.txt"
        stdout_file = self.logs_dir / f"cycle_{cycle:03d}_stdout.log"
        prompt_file.write_text(prompt, encoding="utf-8")
        output_file.touch()
        stdout_file.touch()

        cmd = codex_exec_command(
            repo_root=REPO_ROOT,
            state_dir=self.state_dir,
            output_file=output_file,
            model=self.config.model,
        )

        timed_out = False
        start = time.monotonic()
        try:
            proc = run_cmd(cmd, cwd=REPO_ROOT, timeout=self.config.cycle_timeout, input_text=prompt)
            stdout = (proc.stdout or "") + (proc.stderr or "")
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
            rc = 124
        stdout_file.write_text(stdout, encoding="utf-8", errors="ignore")

        summary_text = output_file.read_text(encoding="utf-8", errors="ignore").strip() if output_file.exists() else stdout.strip()
        self.latest_summary_path.write_text(summary_text + "\n", encoding="utf-8")
        summary_fields = normalize_summary_fields(parse_summary_fields(summary_text), stdout)
        verification = self._run_verification(summary_fields)
        git_after = gather_git_snapshot(REPO_ROOT)

        record = CycleRecord(
            cycle=cycle,
            started_at=started_at,
            completed_at=utc_now(),
            rc=rc,
            timed_out=timed_out,
            summary_fields=summary_fields,
            verification=verification.to_dict(),
            active_task_id=str(task.get("id", "")),
            git_before=asdict(git_before),
            git_after=asdict(git_after),
        )
        append_jsonl(self.cycles_path, record.to_dict())
        self._update_backlog(task_id=str(task.get("id", "")), summary_fields=summary_fields, verification=verification)
        self._write_handoff(record)
        return record

    def _mark_cycle_started(self, *, cycle: int, task_id: str) -> None:
        current = read_json(self.run_path)
        current.update(
            {
                "updated_at": utc_now(),
                "cycle": cycle,
                "status": "running_cycle",
                "last_task_id": task_id,
                "last_continue_required": True,
            }
        )
        write_json(self.run_path, current)

    def _run_verification(self, summary_fields: dict[str, str]) -> VerificationBundle:
        checks: list[dict[str, Any]] = []

        checks.append(self._check("tsc", ["bunx", "tsc", "--noEmit"], cwd=TERMINAL_DIR, timeout=300))
        checks.append(self._check("py_compile_bridge", [str(PYTHON_BIN), "-m", "py_compile", str(REPO_ROOT / "dharma_swarm" / "terminal_bridge.py")], cwd=REPO_ROOT, timeout=120))
        checks.append(
            self._check(
                "bridge_snapshots",
                [
                    str(PYTHON_BIN),
                    "-m",
                    "dharma_swarm.terminal_bridge",
                    "stdio",
                ],
                cwd=REPO_ROOT,
                timeout=120,
                input_text='\n'.join(
                    [
                        '{"id":"1","type":"workspace.snapshot"}',
                        '{"id":"2","type":"ontology.snapshot"}',
                        '{"id":"3","type":"runtime.snapshot"}',
                        "",
                    ]
                ),
            )
        )

        acceptance_pass = summary_fields.get("acceptance", "").strip().lower() == "pass"
        checks.append(
            {
                "name": "cycle_acceptance",
                "ok": acceptance_pass,
                "rc": 0 if acceptance_pass else 1,
                "preview": summary_fields.get("result", "")[:200],
            }
        )

        continue_required = any(not bool(check.get("ok")) for check in checks)
        summary = " | ".join(f"{check['name']}={'ok' if check['ok'] else 'fail'}" for check in checks)
        bundle = VerificationBundle(
            ts=utc_now(),
            checks=checks,
            summary=summary,
            continue_required=continue_required,
        )
        write_json(self.verification_path, bundle.to_dict())
        return bundle

    def _check(self, name: str, cmd: list[str], *, cwd: Path, timeout: int, input_text: str | None = None) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                text=True,
                input=input_text,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            preview = " ".join((proc.stdout or proc.stderr or "").split())[:240]
            return {"name": name, "ok": proc.returncode == 0, "rc": proc.returncode, "preview": preview}
        except Exception as exc:
            return {"name": name, "ok": False, "rc": 1, "preview": f"{type(exc).__name__}: {exc}"}

    def _update_backlog(self, *, task_id: str, summary_fields: dict[str, str], verification: VerificationBundle) -> None:
        tasks = ensure_backlog(self.backlog_path)
        status = summary_fields.get("status", "").strip().lower() or "in_progress"
        acceptance = summary_fields.get("acceptance", "").strip().lower()
        for task in tasks:
            if str(task.get("id", "")) != task_id:
                continue
            if acceptance == "pass" and not verification.continue_required:
                task["status"] = "completed"
            elif status == "blocked":
                task["status"] = "blocked"
            else:
                task["status"] = "in_progress"
            task["updated_at"] = utc_now()
            task["next_task"] = summary_fields.get("next_task", "")
            task["last_result"] = summary_fields.get("result", "")
            break
        write_json(self.backlog_path, {"updated_at": utc_now(), "tasks": tasks})

    def _write_handoff(self, record: CycleRecord) -> None:
        lines = [
            "# Terminal Overnight Handoff",
            "",
            f"- run_id: {self.run_id}",
            f"- updated_at: {utc_now()}",
            f"- cycle: {record.cycle}",
            f"- active_task: {record.active_task_id}",
            f"- status: {record.summary_fields.get('status', '') or 'unknown'}",
            f"- acceptance: {record.summary_fields.get('acceptance', '') or 'unknown'}",
            f"- blockers: {record.summary_fields.get('blockers', '') or 'none'}",
            f"- tests: {record.summary_fields.get('tests', '') or 'not reported'}",
            "",
            "## Result",
            "",
            record.summary_fields.get("result", "") or "(missing)",
            "",
            "## Next Task",
            "",
            record.summary_fields.get("next_task", "") or "none",
            "",
            "## Verification",
            "",
            record.verification.get("summary", ""),
        ]
        self.handoff_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _update_run_state(self, *, cycle: int, last_record: CycleRecord) -> None:
        backlog = read_json(self.backlog_path).get("tasks", [])
        pending = len([task for task in backlog if str(task.get("status", "")) != "completed"])
        write_json(
            self.run_path,
            {
                "run_id": self.run_id,
                "updated_at": utc_now(),
                "repo_root": str(REPO_ROOT),
                "objective": self.config.objective,
                "cycle": cycle,
                "status": "running" if self._should_continue(last_record) else "completed",
                "tasks_total": len(backlog),
                "tasks_pending": pending,
                "last_task_id": last_record.active_task_id,
                "last_continue_required": self._should_continue(last_record),
                "last_summary_fields": last_record.summary_fields,
                "last_verification": last_record.verification,
            },
        )

    def _should_continue(self, record: CycleRecord) -> bool:
        if record.timed_out or record.rc != 0:
            return True
        if bool(record.verification.get("continue_required")):
            return True
        backlog = read_json(self.backlog_path).get("tasks", [])
        return any(str(task.get("status", "")) != "completed" for task in backlog)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Terminal overnight supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the supervisor loop")
    run_parser.add_argument("--hours", type=float, default=8.0)
    run_parser.add_argument("--max-cycles", type=int, default=24)
    run_parser.add_argument("--poll-seconds", type=int, default=300)
    run_parser.add_argument("--cycle-timeout", type=int, default=1800)
    run_parser.add_argument("--model", default="")
    run_parser.add_argument("--objective", default=DEFAULT_OBJECTIVE)
    run_parser.add_argument("--run-id", default="")
    run_parser.add_argument("--once", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show supervisor status")
    status_parser.add_argument("--run-id", default="")
    return parser


def _resolve_run_id(explicit: str) -> str:
    if explicit.strip():
        return explicit.strip()
    if not STATE_ROOT.exists():
        return ""
    runs = [path for path in STATE_ROOT.iterdir() if path.is_dir()]
    if not runs:
        return ""
    latest = max(runs, key=lambda path: path.stat().st_mtime)
    return latest.name


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        supervisor = TerminalOvernightSupervisor(
            SupervisorConfig(
                hours=args.hours,
                max_cycles=args.max_cycles,
                poll_seconds=args.poll_seconds,
                cycle_timeout=args.cycle_timeout,
                model=args.model,
                objective=args.objective,
                run_id=args.run_id,
                once=args.once,
            )
        )
        print(json.dumps(supervisor.run(), indent=2))
        return 0
    if args.command == "status":
        run_id = _resolve_run_id(args.run_id)
        if not run_id:
            print(json.dumps({"status": "missing", "message": "no terminal supervisor runs found"}, indent=2))
            return 1
        supervisor = TerminalOvernightSupervisor(SupervisorConfig(run_id=run_id))
        print(json.dumps(supervisor.status(), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
