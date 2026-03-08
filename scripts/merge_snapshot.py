#!/usr/bin/env python3
"""Generate canonical merge-control snapshot facts for dharma_swarm."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path.home() / "dharma_swarm"
DOCS_MERGE = ROOT / "docs" / "merge"
STATE_DIR = Path.home() / ".dharma"
STATE_MERGE = STATE_DIR / "merge"
HEARTBEAT_FILE = STATE_DIR / "merge_heartbeat.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def utc_day() -> str:
    return utc_now().strftime("%Y-%m-%d")


def run_cmd(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def safe_json_load(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def parse_git_counts(porcelain: str) -> dict[str, int]:
    staged = 0
    unstaged = 0
    untracked = 0
    deleted = 0

    for raw in porcelain.splitlines():
        if not raw:
            continue
        if raw.startswith("?? "):
            untracked += 1
            continue

        if len(raw) < 3:
            continue

        x = raw[0]
        y = raw[1]

        if x != " ":
            staged += 1
            if x == "D":
                deleted += 1

        if y != " ":
            unstaged += 1
            if y == "D":
                deleted += 1

    total_dirty = staged + unstaged + untracked
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "deleted": deleted,
        "total_dirty": total_dirty,
    }


def get_git_facts() -> dict[str, Any]:
    rc, branch_out, _ = run_cmd(["git", "status", "--short", "--branch"], timeout=30)
    if rc != 0:
        return {"ok": False, "error": "git status failed"}

    lines = branch_out.splitlines()
    branch_line = lines[0] if lines else ""

    rc, head_out, _ = run_cmd(["git", "rev-parse", "HEAD"], timeout=30)
    head = head_out.strip() if rc == 0 else "unknown"

    rc, porcelain_out, _ = run_cmd(["git", "status", "--porcelain"], timeout=30)
    counts = parse_git_counts(porcelain_out if rc == 0 else "")

    rc, staged_files_out, _ = run_cmd(["git", "diff", "--cached", "--name-only"], timeout=30)
    staged_files = [ln for ln in staged_files_out.splitlines() if ln.strip()] if rc == 0 else []

    rc, branch_name_out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=30)
    branch_name = branch_name_out.strip() if rc == 0 else "unknown"

    rc, remote_out, _ = run_cmd(["git", "remote", "-v"], timeout=30)
    remotes = [ln.strip() for ln in remote_out.splitlines() if ln.strip()] if rc == 0 else []

    return {
        "ok": True,
        "branch_line": branch_line,
        "branch": branch_name,
        "head": head,
        "counts": counts,
        "staged_files": staged_files,
        "remote_lines": remotes,
    }


def run_mission_status(profile: str, strict_core: bool, require_tracked: bool) -> dict[str, Any]:
    cmd = [
        "python3",
        "-m",
        "dharma_swarm.dgc_cli",
        "mission-status",
        "--profile",
        profile,
        "--json",
    ]
    if strict_core:
        cmd.append("--strict-core")
    if require_tracked:
        cmd.append("--require-tracked")

    rc, out, err = run_cmd(cmd, timeout=180)
    payload = safe_json_load(out)
    return {
        "exit_code": rc,
        "ok": rc == 0,
        "json": payload,
        "stdout_tail": out[-4000:],
        "stderr_tail": err[-1000:],
    }


def run_health_check() -> dict[str, Any]:
    rc, out, err = run_cmd(
        ["python3", "-m", "dharma_swarm.dgc_cli", "health-check"],
        timeout=180,
    )
    return {
        "exit_code": rc,
        "ok": rc == 0,
        "stdout_tail": out[-3000:],
        "stderr_tail": err[-1000:],
    }


def run_tests(tests_command: str) -> dict[str, Any]:
    rc, out, err = run_cmd(["/bin/zsh", "-lc", tests_command], timeout=1800)
    return {
        "exit_code": rc,
        "ok": rc == 0,
        "command": tests_command,
        "stdout_tail": out[-4000:],
        "stderr_tail": err[-1000:],
    }


def legacy_source_facts() -> dict[str, Any]:
    old_repo = Path.home() / "DHARMIC_GODEL_CLAW"
    core_repo = Path.home() / "dgc-core"
    old_archive = old_repo / "src" / "dgm" / "archive.jsonl"

    archive_entries = 0
    if old_archive.exists():
        try:
            archive_entries = sum(1 for _ in old_archive.open("r", encoding="utf-8", errors="ignore"))
        except Exception:
            archive_entries = -1

    return {
        "dharmic_godel_claw": {
            "path": str(old_repo),
            "exists": old_repo.exists(),
            "archive_jsonl": str(old_archive),
            "archive_entries": archive_entries,
        },
        "dgc_core": {
            "path": str(core_repo),
            "exists": core_repo.exists(),
        },
    }


def legacy_import_facts() -> dict[str, Any]:
    predictor_path = Path.home() / ".dharma" / "evolution" / "predictor_data.jsonl"
    state_path = Path.home() / ".dharma" / "evolution" / "legacy_import_state.json"
    report_dir = ROOT / "docs" / "merge" / "imports"
    latest_report_json = report_dir / "LATEST_LEGACY_IMPORT.json"

    predictor_lines = 0
    if predictor_path.exists():
        try:
            predictor_lines = sum(
                1 for _ in predictor_path.open("r", encoding="utf-8", errors="ignore")
            )
        except Exception:
            predictor_lines = -1

    state_payload: dict[str, Any] | None = None
    if state_path.exists():
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state_payload = None

    latest_payload: dict[str, Any] | None = None
    if latest_report_json.exists():
        try:
            latest_payload = json.loads(latest_report_json.read_text(encoding="utf-8"))
        except Exception:
            latest_payload = None

    return {
        "predictor_path": str(predictor_path),
        "predictor_lines": predictor_lines,
        "state_path": str(state_path),
        "state_exists": state_path.exists(),
        "imported_total": (
            state_payload.get("imported_total")
            if isinstance(state_payload, dict)
            else 0
        ),
        "latest_report_json": str(latest_report_json),
        "latest_imported_now": (
            latest_payload.get("imported_now")
            if isinstance(latest_payload, dict)
            else None
        ),
    }


def ensure_ledger_exists(ledger_path: Path) -> None:
    if ledger_path.exists():
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "# DGC Merge Ledger\n\n"
        "Purpose: canonical merge decisions.\n\n"
        "## Decision Table\n\n"
        "| Date (UTC) | Source | Target | Decision | Reason | Tests | Commit |\n"
        "|---|---|---|---|---|---|---|\n\n"
        "## Session Log\n\n",
        encoding="utf-8",
    )


def append_ledger_log_line(summary: dict[str, Any], ledger_path: Path) -> None:
    ensure_ledger_exists(ledger_path)
    ts = summary["generated_utc"]
    branch = summary.get("git", {}).get("branch", "unknown")
    head = summary.get("git", {}).get("head", "unknown")[:12]
    mission_exit = summary.get("mission_status", {}).get("exit_code", 99)
    tracked = "unknown"
    mission_json = summary.get("mission_status", {}).get("json") or {}
    tracked_info = mission_json.get("tracked_wiring", {}) if isinstance(mission_json, dict) else {}
    if isinstance(tracked_info, dict):
        tracked = f"{tracked_info.get('tracked_count', '?')}/{tracked_info.get('total', '?')}"
    imported_total = summary.get("legacy_import", {}).get("imported_total", "?")
    predictor_rows = summary.get("legacy_import", {}).get("predictor_lines", "?")

    line = (
        f"- {ts} snapshot={summary.get('snapshot_dir_name')} "
        f"branch={branch} head={head} mission_exit={mission_exit} tracked={tracked} "
        f"legacy_imported={imported_total} predictor_rows={predictor_rows}\n"
    )
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(line)


def render_canonical_state(summary: dict[str, Any]) -> str:
    git = summary.get("git", {})
    counts = git.get("counts", {})
    mission = summary.get("mission_status", {})
    mission_json = mission.get("json") or {}
    tracked = mission_json.get("tracked_wiring", {}) if isinstance(mission_json, dict) else {}
    core = mission_json.get("core", {}) if isinstance(mission_json, dict) else {}

    lines = [
        "# Canonical State",
        "",
        f"- Generated (UTC): {summary.get('generated_utc')}",
        f"- Snapshot: `{summary.get('snapshot_path')}`",
        f"- Branch: `{git.get('branch', 'unknown')}`",
        f"- HEAD: `{git.get('head', 'unknown')}`",
        f"- Dirty entries: `{counts.get('total_dirty', '?')}`",
        f"- Staged / Unstaged / Untracked: `{counts.get('staged', '?')}` / `{counts.get('unstaged', '?')}` / `{counts.get('untracked', '?')}`",
        "",
        "## Mission Status",
        f"- Exit code: `{mission.get('exit_code')}`",
        f"- Core checks: `{core.get('pass_count', '?')}/{core.get('total', '?')}`",
        f"- Tracked wiring: `{tracked.get('tracked_count', '?')}/{tracked.get('total', '?')}`",
        "",
        "## Legacy Import Sources",
    ]

    legacy = summary.get("legacy_sources", {})
    old = legacy.get("dharmic_godel_claw", {})
    core_src = legacy.get("dgc_core", {})
    lines.append(
        f"- DHARMIC_GODEL_CLAW exists: `{old.get('exists')}` archive_entries=`{old.get('archive_entries')}`"
    )
    lines.append(f"- dgc-core exists: `{core_src.get('exists')}`")
    lines.append("")
    lines.append("## Legacy Import Progress")
    imp = summary.get("legacy_import", {})
    lines.append(f"- Predictor rows: `{imp.get('predictor_lines', '?')}`")
    lines.append(f"- Imported legacy keys: `{imp.get('imported_total', '?')}`")
    lines.append(f"- Latest import delta: `{imp.get('latest_imported_now', '?')}`")
    lines.append(f"- Import state present: `{imp.get('state_exists')}`")
    lines.append("")
    lines.append("Generated by `scripts/merge_snapshot.py`.")
    return "\n".join(lines) + "\n"


def write_snapshot_files(snapshot_dir: Path, summary: dict[str, Any]) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    (snapshot_dir / "FACTS.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    git = summary.get("git", {})
    (snapshot_dir / "git_status.txt").write_text(
        git.get("branch_line", "") + "\n" + "\n".join(git.get("staged_files", [])) + "\n",
        encoding="utf-8",
    )

    mission = summary.get("mission_status", {})
    mission_out = mission.get("stdout_tail", "")
    if mission.get("json") is not None:
        mission_out = json.dumps(mission.get("json"), indent=2, ensure_ascii=True)
    (snapshot_dir / "mission_status.json").write_text(mission_out + "\n", encoding="utf-8")

    health = summary.get("health_check", {})
    (snapshot_dir / "health_check.txt").write_text(
        (health.get("stdout_tail", "") + "\n" + health.get("stderr_tail", "")).strip() + "\n",
        encoding="utf-8",
    )

    tests = summary.get("tests")
    if tests is not None:
        (snapshot_dir / "tests_tail.txt").write_text(
            (tests.get("stdout_tail", "") + "\n" + tests.get("stderr_tail", "")).strip() + "\n",
            encoding="utf-8",
        )


def write_canonical_outputs(summary: dict[str, Any], facts_path: Path, state_path: Path) -> None:
    facts_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    facts_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    state_path.write_text(render_canonical_state(summary), encoding="utf-8")


def write_heartbeat(summary: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    heartbeat = {
        "ts_utc": summary.get("generated_utc"),
        "snapshot": summary.get("snapshot_path"),
        "branch": summary.get("git", {}).get("branch"),
        "head": summary.get("git", {}).get("head"),
        "mission_exit": summary.get("mission_status", {}).get("exit_code"),
    }
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def resolve_output_paths(*, state_only: bool) -> dict[str, Path]:
    if state_only:
        root = STATE_MERGE
    else:
        root = DOCS_MERGE
    return {
        "output_root": root,
        "snapshot_root": root / "snapshots",
        "canonical_facts": root / "FACTS.json",
        "canonical_state": root / "CANONICAL_STATE.md",
        "merge_ledger": root / "MERGE_LEDGER.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate merge-control snapshot.")
    parser.add_argument("--profile", default=os.getenv("MISSION_PROFILE", "workspace_auto"))
    parser.add_argument("--strict-core", action="store_true")
    parser.add_argument("--require-tracked", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument(
        "--tests-command",
        default="python3 -m pytest -q tests/test_dgc_cli.py tests/test_engine_provider_runner.py --tb=short",
    )
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument(
        "--state-only",
        action="store_true",
        help="Write canonical outputs under ~/.dharma/merge instead of tracked docs/merge.",
    )
    args = parser.parse_args()

    paths = resolve_output_paths(state_only=args.state_only)
    stamp = utc_stamp()
    day = utc_day()
    snapshot_dir = paths["snapshot_root"] / day / stamp

    git = get_git_facts()
    mission = run_mission_status(args.profile, args.strict_core, args.require_tracked)
    health = run_health_check()
    tests = run_tests(args.tests_command) if args.run_tests else None

    summary: dict[str, Any] = {
        "generated_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_dir_name": stamp,
        "snapshot_path": str(snapshot_dir),
        "output_root": str(paths["output_root"]),
        "profile": args.profile,
        "strict_core": bool(args.strict_core),
        "require_tracked": bool(args.require_tracked),
        "state_only": bool(args.state_only),
        "git": git,
        "mission_status": mission,
        "health_check": health,
        "tests": tests,
        "legacy_sources": legacy_source_facts(),
        "legacy_import": legacy_import_facts(),
    }

    write_snapshot_files(snapshot_dir, summary)
    write_canonical_outputs(summary, paths["canonical_facts"], paths["canonical_state"])
    write_heartbeat(summary)
    if args.append_ledger:
        append_ledger_log_line(summary, paths["merge_ledger"])

    print(json.dumps(
        {
            "snapshot_path": str(snapshot_dir),
            "mission_exit": mission.get("exit_code"),
            "git_dirty": git.get("counts", {}).get("total_dirty"),
            "tracked_wiring": ((mission.get("json") or {}).get("tracked_wiring") if isinstance(mission.get("json"), dict) else None),
        },
        ensure_ascii=True,
    ))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
