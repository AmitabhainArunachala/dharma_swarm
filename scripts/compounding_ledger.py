#!/usr/bin/env python3
"""Generate a compounding evidence report from allout/caffeine telemetry."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATE = Path.home() / ".dharma"
LOG_DIR = STATE / "logs" / "allout"
SHARED_DIR = STATE / "shared"
ALL_OUT_HEARTBEAT = STATE / "allout_heartbeat.json"
CAFFEINE_HEARTBEAT = STATE / "caffeine_heartbeat.json"
COMPOUNDING_LEDGER = SHARED_DIR / "compounding_ledger.jsonl"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_ts() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1] + "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_jsonl(path: Path, *, since: datetime) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        dt = parse_ts(obj.get("ts_utc"))
        if dt is None or dt < since:
            continue
        records.append(obj)
    return records


def read_snapshot_records(*, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not LOG_DIR.exists():
        return rows

    for snap in sorted(LOG_DIR.glob("*/snapshots.jsonl")):
        rows.extend(read_jsonl(snap, since=since))

    rows.sort(key=lambda x: str(x.get("ts_utc", "")))
    return rows


def summarize_snapshots(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks_total = 0
    checks_ok = 0
    mission_fail = 0
    actions_total = 0
    actions_ok = 0
    actions_noop = 0
    todo_total = 0
    files_total = 0
    run_ids: set[str] = set()

    for row in rows:
        run_id = str(row.get("run_id", "")).strip()
        if run_id:
            run_ids.add(run_id)

        todo_total += len(row.get("todo_steps") or [])
        files_total += len(row.get("files_reviewed") or [])

        for result in row.get("results") or []:
            checks_total += 1
            rc = int(result.get("rc", 1))
            if rc == 0:
                checks_ok += 1
            if result.get("label") == "mission-status" and rc != 0:
                mission_fail += 1

        for action in row.get("actions_executed") or []:
            actions_total += 1
            rc = int(action.get("rc", 1))
            if rc == 0:
                actions_ok += 1
            if action.get("action") == "noop_unmapped_step":
                actions_noop += 1

    checks_fail = checks_total - checks_ok
    actions_fail = actions_total - actions_ok
    latest = rows[-1].get("ts_utc") if rows else None

    return {
        "cycles": len(rows),
        "run_ids": sorted(run_ids),
        "checks_total": checks_total,
        "checks_ok": checks_ok,
        "checks_fail": checks_fail,
        "mission_fail_cycles": mission_fail,
        "actions_total": actions_total,
        "actions_ok": actions_ok,
        "actions_fail": actions_fail,
        "actions_noop": actions_noop,
        "todo_steps_total": todo_total,
        "files_reviewed_total": files_total,
        "latest_cycle_ts": latest,
    }


def summarize_compounding_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "events": 0,
            "checks_total": 0,
            "checks_ok": 0,
            "actions_total": 0,
            "actions_ok": 0,
            "latest_event_ts": None,
        }

    checks_total = sum(int(r.get("checks_total", 0)) for r in rows)
    checks_ok = sum(int(r.get("checks_ok", 0)) for r in rows)
    actions_total = sum(int(r.get("actions_total", 0)) for r in rows)
    actions_ok = sum(int(r.get("actions_ok", 0)) for r in rows)

    return {
        "events": len(rows),
        "checks_total": checks_total,
        "checks_ok": checks_ok,
        "actions_total": actions_total,
        "actions_ok": actions_ok,
        "latest_event_ts": rows[-1].get("ts_utc"),
    }


def heartbeat_status(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not payload:
        return {"present": False, "fresh_minutes": None, "status": "missing"}
    ts = parse_ts(payload.get("ts_utc"))
    if ts is None:
        return {"present": True, "fresh_minutes": None, "status": "invalid_ts"}
    minutes = round((utc_now() - ts).total_seconds() / 60.0, 2)
    status = "fresh" if minutes <= 10 else "stale"
    return {
        "present": True,
        "status": status,
        "fresh_minutes": minutes,
        "ts_utc": payload.get("ts_utc"),
        "cycle": payload.get("cycle"),
        "log": payload.get("log"),
    }


def build_report(hours: int) -> dict[str, Any]:
    since = utc_now() - timedelta(hours=max(1, int(hours)))
    snapshots = read_snapshot_records(since=since)
    compounding_rows = read_jsonl(COMPOUNDING_LEDGER, since=since)

    snapshot_summary = summarize_snapshots(snapshots)
    comp_summary = summarize_compounding_events(compounding_rows)

    return {
        "generated_utc": utc_ts(),
        "window_hours": max(1, int(hours)),
        "since_utc": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "allout_snapshots": snapshot_summary,
        "compounding_ledger": {
            "path": str(COMPOUNDING_LEDGER),
            **comp_summary,
        },
        "heartbeats": {
            "allout": heartbeat_status(ALL_OUT_HEARTBEAT),
            "caffeine": heartbeat_status(CAFFEINE_HEARTBEAT),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    snap = report["allout_snapshots"]
    comp = report["compounding_ledger"]
    hb = report["heartbeats"]

    lines = [
        "# DGC Compounding Ledger Report",
        f"- Generated (UTC): {report['generated_utc']}",
        f"- Window: last {report['window_hours']} hours",
        f"- Since (UTC): {report['since_utc']}",
        "",
        "## AllOut Snapshot Summary",
        f"- Cycles observed: {snap['cycles']}",
        f"- Runs observed: {len(snap['run_ids'])}",
        f"- Command checks: {snap['checks_ok']}/{snap['checks_total']} passed",
        f"- Mission-status failures: {snap['mission_fail_cycles']}",
        f"- Executed actions: {snap['actions_ok']}/{snap['actions_total']} successful",
        f"- No-op actions: {snap['actions_noop']}",
        f"- Todo steps generated: {snap['todo_steps_total']}",
        f"- Files reviewed: {snap['files_reviewed_total']}",
        f"- Latest cycle timestamp: {snap['latest_cycle_ts']}",
        "",
        "## Compounding Event Ledger",
        f"- Path: `{comp['path']}`",
        f"- Events observed: {comp['events']}",
        f"- Event-level checks: {comp['checks_ok']}/{comp['checks_total']} passed",
        f"- Event-level actions: {comp['actions_ok']}/{comp['actions_total']} successful",
        f"- Latest event timestamp: {comp['latest_event_ts']}",
        "",
        "## Heartbeats",
        f"- AllOut: {hb['allout']['status']} (fresh_minutes={hb['allout']['fresh_minutes']})",
        f"- Caffeine: {hb['caffeine']['status']} (fresh_minutes={hb['caffeine']['fresh_minutes']})",
        "",
        "## Interpretation",
    ]

    if snap["cycles"] == 0:
        lines.append("- No cycles in the window. Start `scripts/start_allout_tmux.sh` and re-run this report.")
    else:
        lines.append("- Compounding is evidenced by repeated cycles with persisted checks/actions over time.")

    if snap["mission_fail_cycles"] > 0:
        lines.append("- Strict mission lane is not fully stable inside observed cycles.")
    else:
        lines.append("- Strict mission lane remained green in observed cycles.")

    if hb["allout"]["status"] != "fresh":
        lines.append("- AllOut heartbeat is stale or missing; autonomous loop may be down.")

    return "\n".join(lines) + "\n"


def write_report_files(report: dict[str, Any], markdown: str) -> tuple[Path, Path]:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = SHARED_DIR / f"compounding_{report['window_hours']}h_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DGC compounding ledger report.")
    parser.add_argument("--hours", type=int, default=24, help="Window size in hours (default: 24)")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write markdown+json reports to ~/.dharma/shared and print paths.",
    )
    args = parser.parse_args()

    report = build_report(args.hours)
    markdown = render_markdown(report)

    if args.write:
        md_path, json_path = write_report_files(report, markdown)
        print(json.dumps({"markdown": str(md_path), "json": str(json_path)}, ensure_ascii=True))
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
