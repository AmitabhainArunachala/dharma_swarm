"""Tests for compounding ledger report generation."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.home() / "dharma_swarm" / "scripts"))

from scripts import compounding_ledger as ledger


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_build_report_with_snapshot_and_events(tmp_path: Path):
    state = tmp_path / ".dharma"
    log_dir = state / "logs" / "allout" / "run1"
    shared_dir = state / "shared"
    log_dir.mkdir(parents=True)
    shared_dir.mkdir(parents=True)

    snapshots = log_dir / "snapshots.jsonl"
    snapshots.write_text(
        json.dumps(
            {
                "ts_utc": _now_ts(),
                "run_id": "run1",
                "cycle": 1,
                "results": [
                    {"label": "mission-status", "rc": 0},
                    {"label": "tests-provider", "rc": 1},
                ],
                "actions_executed": [
                    {"action": "pytest_provider_core", "rc": 0},
                    {"action": "noop_unmapped_step", "rc": 0},
                ],
                "todo_steps": ["a", "b", "c"],
                "files_reviewed": ["x.py", "y.py"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    comp_path = shared_dir / "compounding_ledger.jsonl"
    comp_path.write_text(
        json.dumps(
            {
                "ts_utc": _now_ts(),
                "run_id": "run1",
                "cycle": 1,
                "checks_total": 3,
                "checks_ok": 2,
                "actions_total": 2,
                "actions_ok": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    hb_allout = state / "allout_heartbeat.json"
    hb_allout.write_text(json.dumps({"ts_utc": _now_ts(), "cycle": 1}) + "\n", encoding="utf-8")
    hb_caffeine = state / "caffeine_heartbeat.json"
    hb_caffeine.write_text(json.dumps({"ts_utc": _now_ts(), "cycle": 2}) + "\n", encoding="utf-8")

    with patch.object(ledger, "LOG_DIR", state / "logs" / "allout"), patch.object(
        ledger, "SHARED_DIR", shared_dir
    ), patch.object(ledger, "COMPOUNDING_LEDGER", comp_path), patch.object(
        ledger, "ALL_OUT_HEARTBEAT", hb_allout
    ), patch.object(ledger, "CAFFEINE_HEARTBEAT", hb_caffeine):
        report = ledger.build_report(24)

    snap = report["allout_snapshots"]
    assert snap["cycles"] == 1
    assert snap["checks_total"] == 2
    assert snap["checks_ok"] == 1
    assert snap["mission_fail_cycles"] == 0
    assert snap["actions_total"] == 2
    assert snap["actions_noop"] == 1

    comp = report["compounding_ledger"]
    assert comp["events"] == 1
    assert comp["checks_total"] == 3
    assert comp["checks_ok"] == 2


def test_render_markdown_no_cycles_mentions_start_instruction():
    report = {
        "generated_utc": _now_ts(),
        "window_hours": 24,
        "since_utc": _now_ts(),
        "allout_snapshots": {
            "cycles": 0,
            "run_ids": [],
            "checks_total": 0,
            "checks_ok": 0,
            "checks_fail": 0,
            "mission_fail_cycles": 0,
            "actions_total": 0,
            "actions_ok": 0,
            "actions_fail": 0,
            "actions_noop": 0,
            "todo_steps_total": 0,
            "files_reviewed_total": 0,
            "latest_cycle_ts": None,
        },
        "compounding_ledger": {
            "path": "/tmp/compounding_ledger.jsonl",
            "events": 0,
            "checks_total": 0,
            "checks_ok": 0,
            "actions_total": 0,
            "actions_ok": 0,
            "latest_event_ts": None,
        },
        "heartbeats": {
            "allout": {"status": "missing", "fresh_minutes": None},
            "caffeine": {"status": "missing", "fresh_minutes": None},
        },
    }

    markdown = ledger.render_markdown(report)
    assert "No cycles in the window" in markdown
    assert "start_allout_tmux.sh" in markdown
