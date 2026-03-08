#!/usr/bin/env python3
"""Import legacy DHARMIC_GODEL_CLAW archive entries into current predictor history.

This is idempotent and stateful: imported entry keys are tracked so re-runs only
append newly discovered legacy entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NEW_WEIGHTS: dict[str, float] = {
    "correctness": 0.25,
    "dharmic_alignment": 0.20,
    "performance": 0.15,
    "utilization": 0.15,
    "elegance": 0.10,
    "efficiency": 0.10,
    "safety": 0.05,
}

OLD_WEIGHTS: dict[str, float] = {
    "correctness": 0.30,
    "dharmic_alignment": 0.25,
    "elegance": 0.15,
    "efficiency": 0.15,
    "safety": 0.15,
}

DEFAULT_ALLOWED_STATUSES = {"applied", "rejected", "approved", "rolled_back"}


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_weighted_fitness(fitness: dict[str, Any]) -> float:
    if not isinstance(fitness, dict):
        return 0.0

    if any(k in fitness for k in ("performance", "utilization")):
        weights = NEW_WEIGHTS
    else:
        weights = OLD_WEIGHTS

    total = 0.0
    for key, weight in weights.items():
        try:
            value = float(fitness.get(key, 0.0))
        except Exception:
            value = 0.0
        total += value * weight

    if total < 0.0:
        return 0.0
    if total > 1.0:
        return 1.0
    return round(total, 6)


def infer_test_coverage(test_results: Any) -> bool:
    if not isinstance(test_results, dict):
        return False
    passed = test_results.get("passed", test_results.get("pass", 0))
    failed = test_results.get("failed", test_results.get("fail", 0))
    try:
        return (int(passed) + int(failed)) > 0
    except Exception:
        return False


def parse_diff_size(diff_text: Any) -> int:
    if not isinstance(diff_text, str) or not diff_text:
        return 0
    return len(diff_text.splitlines())


def make_entry_key(entry: dict[str, Any], line: str) -> str:
    eid = str(entry.get("id", "")).strip()
    if eid:
        return f"legacy:{eid}"
    digest = hashlib.sha256(line.encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"legacy:sha:{digest}"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"imported_keys": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"imported_keys": []}


def save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    status = str(entry.get("status", "")).strip().lower()
    component = str(entry.get("component", "unknown") or "unknown")
    change_type = str(entry.get("change_type", "mutation") or "mutation")

    gates_passed = entry.get("gates_passed", [])
    gates_count = len(gates_passed) if isinstance(gates_passed, list) else 0

    features = {
        "component": component,
        "change_type": change_type,
        "diff_size": parse_diff_size(entry.get("diff", "")),
        "complexity_delta": 0.0,
        "test_coverage_exists": infer_test_coverage(entry.get("test_results", {})),
        "gates_likely_to_pass": gates_count,
    }

    return {
        "status": status,
        "features": features,
        "actual_fitness": compute_weighted_fitness(entry.get("fitness", {})),
    }


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def render_markdown_report(report: dict[str, Any]) -> str:
    top_components = report.get("top_components", [])
    lines = [
        "# Legacy Archive Import Report",
        "",
        f"- Generated (UTC): {report['generated_utc']}",
        f"- Source archive: `{report['source_archive']}`",
        f"- Predictor path: `{report['predictor_path']}`",
        f"- State path: `{report['state_path']}`",
        "",
        "## Counts",
        f"- Source lines parsed: {report['source_total']}",
        f"- Status-eligible: {report['eligible_total']}",
        f"- Newly imported: {report['imported_now']}",
        f"- Skipped (already imported): {report['skipped_known']}",
        f"- Skipped (status filtered): {report['skipped_status']}",
        "",
        "## Status Distribution (eligible)",
    ]

    for key, value in report.get("status_distribution", {}).items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Top Components (newly imported)"])
    if top_components:
        for comp, count in top_components:
            lines.append(f"- `{comp}`: {count}")
    else:
        lines.append("- None (no new imports this run)")

    lines.append("")
    lines.append("This report is generated by `scripts/import_legacy_archive.py`.")
    return "\n".join(lines) + "\n"


def import_legacy(
    source_archive: Path,
    predictor_path: Path,
    state_path: Path,
    report_dir: Path,
    allowed_statuses: set[str],
) -> dict[str, Any]:
    if not source_archive.exists():
        raise FileNotFoundError(f"Missing source archive: {source_archive}")

    state = load_state(state_path)
    imported_keys = set(state.get("imported_keys", []))

    source_total = 0
    eligible_total = 0
    skipped_known = 0
    skipped_status = 0

    status_counter: Counter[str] = Counter()
    imported_component_counter: Counter[str] = Counter()

    rows_to_append: list[dict[str, Any]] = []
    new_keys: list[str] = []

    with source_archive.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            source_total += 1
            try:
                entry = json.loads(line)
            except Exception:
                continue

            key = make_entry_key(entry, line)
            normalized = normalize_entry(entry)
            status = normalized["status"]

            if status not in allowed_statuses:
                skipped_status += 1
                continue

            eligible_total += 1
            status_counter[status] += 1

            if key in imported_keys:
                skipped_known += 1
                continue

            rows_to_append.append(
                {
                    "features": normalized["features"],
                    "actual_fitness": normalized["actual_fitness"],
                }
            )
            new_keys.append(key)
            comp = normalized["features"]["component"]
            imported_component_counter[comp] += 1

    append_jsonl(predictor_path, rows_to_append)

    updated_keys = list(imported_keys.union(new_keys))
    updated_keys.sort()
    state_payload = {
        "updated_utc": utc_ts(),
        "source_archive": str(source_archive),
        "imported_total": len(updated_keys),
        "imported_keys": updated_keys,
    }
    save_state(state_path, state_payload)

    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_utc": utc_ts(),
        "source_archive": str(source_archive),
        "predictor_path": str(predictor_path),
        "state_path": str(state_path),
        "source_total": source_total,
        "eligible_total": eligible_total,
        "imported_now": len(rows_to_append),
        "skipped_known": skipped_known,
        "skipped_status": skipped_status,
        "status_distribution": dict(sorted(status_counter.items())),
        "top_components": imported_component_counter.most_common(20),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_report = report_dir / f"legacy_import_{stamp}.json"
    md_report = report_dir / f"legacy_import_{stamp}.md"
    latest_md = report_dir / "LATEST_LEGACY_IMPORT.md"
    latest_json = report_dir / "LATEST_LEGACY_IMPORT.json"

    json_report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    md_text = render_markdown_report(report)
    md_report.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    report["report_json"] = str(json_report)
    report["report_md"] = str(md_report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy DGC archive into current predictor history.")
    parser.add_argument(
        "--source-archive",
        default=str(Path.home() / "DHARMIC_GODEL_CLAW" / "src" / "dgm" / "archive.jsonl"),
    )
    parser.add_argument(
        "--predictor-path",
        default=str(Path.home() / ".dharma" / "evolution" / "predictor_data.jsonl"),
    )
    parser.add_argument(
        "--state-path",
        default=str(Path.home() / ".dharma" / "evolution" / "legacy_import_state.json"),
    )
    parser.add_argument(
        "--report-dir",
        default=str(Path.home() / "dharma_swarm" / "docs" / "merge" / "imports"),
    )
    parser.add_argument(
        "--allowed-statuses",
        default=",".join(sorted(DEFAULT_ALLOWED_STATUSES)),
        help="Comma-separated status names to import",
    )

    args = parser.parse_args()
    allowed_statuses = {
        s.strip().lower() for s in args.allowed_statuses.split(",") if s.strip()
    }

    report = import_legacy(
        source_archive=Path(args.source_archive).expanduser(),
        predictor_path=Path(args.predictor_path).expanduser(),
        state_path=Path(args.state_path).expanduser(),
        report_dir=Path(args.report_dir).expanduser(),
        allowed_statuses=allowed_statuses,
    )

    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
