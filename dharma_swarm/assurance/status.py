"""Quick status check for the assurance mesh.

Usage:
    python3 -m dharma_swarm.assurance.status
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ASSURANCE_DIR = Path.home() / ".dharma" / "assurance"
SCANS_DIR = ASSURANCE_DIR / "scans"
METRICS_FILE = ASSURANCE_DIR / "metrics.jsonl"

SCANNERS = [
    "route_contract", "provider_contract", "storage_path",
    "lifecycle_audit", "ownership_audit", "test_gap",
]


def main() -> None:
    print("=" * 50)
    print("       ASSURANCE MESH STATUS")
    print("=" * 50)

    if not SCANS_DIR.exists():
        print("  No scans found. Run: /assurance-mesh scan")
        return

    # Show latest scan for each scanner
    for scanner in SCANNERS:
        latest = SCANS_DIR / f"{scanner}_latest.json"
        if latest.exists():
            try:
                data = json.loads(latest.read_text())
                ts = data.get("timestamp", "unknown")
                summary = data.get("summary", {})
                total = summary.get("total", 0)
                critical = summary.get("critical", 0)
                high = summary.get("high", 0)

                # Parse timestamp for age
                if ts != "unknown":
                    try:
                        scan_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        age = datetime.now(timezone.utc) - scan_time
                        age_str = f"{age.total_seconds() / 3600:.1f}h ago"
                    except (ValueError, TypeError):
                        age_str = "unknown age"
                else:
                    age_str = "unknown age"

                status = "OK" if total == 0 else (
                    "CRIT" if critical > 0 else
                    "HIGH" if high > 0 else "WARN"
                )
                print(f"  [{status:4s}] {scanner}: {total} findings ({age_str})")
            except (json.JSONDecodeError, KeyError):
                print(f"  [????] {scanner}: corrupt scan file")
        else:
            print(f"  [----] {scanner}: never scanned")

    # Show metrics trend
    print()
    if METRICS_FILE.exists():
        lines = METRICS_FILE.read_text().strip().splitlines()
        if lines:
            recent = lines[-min(5, len(lines)):]
            print(f"  Metrics: {len(lines)} entries, last {len(recent)} shown:")
            for line in recent:
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")[:16]
                    totals = sum(
                        v for k, v in entry.items()
                        if k.endswith("_total") and isinstance(v, int)
                    )
                    crits = sum(
                        v for k, v in entry.items()
                        if k.endswith("_critical") and isinstance(v, int)
                    )
                    print(f"    {ts}: {totals} findings, {crits} critical")
                except json.JSONDecodeError:
                    pass
    else:
        print("  No metrics history yet.")

    print("=" * 50)


if __name__ == "__main__":
    main()
