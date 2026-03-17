"""CLI runner for assurance scanners."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.assurance.runner import run_assurance, scan_reports
from dharma_swarm.assurance.scanner_test_gaps import _git_changed_files

ASSURANCE_DIR = Path.home() / ".dharma" / "assurance"
SCANS_DIR = ASSURANCE_DIR / "scans"
METRICS_FILE = ASSURANCE_DIR / "metrics.jsonl"


def _write_scan_artifacts(assurance_report: dict, reports: list) -> dict[str, str]:
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    written: dict[str, str] = {}
    metric_entry: dict[str, int | str] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    for report in reports:
        payload = report.model_dump(mode="json")
        latest_path = SCANS_DIR / f"{report.scanner}_latest.json"
        history_path = SCANS_DIR / f"{report.scanner}_{stamp}.json"
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        history_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written[report.scanner] = str(latest_path)
        metric_entry[f"{report.scanner}_total"] = report.summary.total
        metric_entry[f"{report.scanner}_critical"] = report.summary.critical

    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metric_entry) + "\n")

    summary_path = SCANS_DIR / "assurance_latest.json"
    summary_path.write_text(json.dumps(assurance_report, indent=2), encoding="utf-8")
    written["summary"] = str(summary_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dharma_swarm assurance scanners")
    parser.add_argument("--diff-only", action="store_true", help="Only scan current changed files")
    parser.add_argument("--nightly", action="store_true", help="Run the full nightly scan")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    changed_files = _git_changed_files(repo_root) if args.diff_only else None
    reports = scan_reports(repo_root=repo_root, changed_files=changed_files)
    assurance_report = run_assurance(repo_root=repo_root, changed_files=changed_files)
    written = _write_scan_artifacts(assurance_report, reports)
    assurance_report["artifacts"] = written

    if args.json:
        print(json.dumps(assurance_report, indent=2))
        return

    print("ASSURANCE SCAN")
    print(
        f"  status={assurance_report['status']} "
        f"critical={assurance_report['summary']['critical']} "
        f"high={assurance_report['summary']['high']} "
        f"medium={assurance_report['summary']['medium']} "
        f"low={assurance_report['summary']['low']}"
    )
    for report in reports:
        print(
            f"  - {report.scanner}: total={report.summary.total} "
            f"critical={report.summary.critical} high={report.summary.high}"
        )
    print(f"  summary_artifact={written['summary']}")
