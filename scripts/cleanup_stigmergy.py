#!/usr/bin/env python3
"""One-time cleanup: archive noise marks from marks.jsonl.

Applies the same quality gate used in the live system to existing marks.
Noise marks are moved to marks_archived_noise.jsonl, keeping only
marks that pass the quality gate.

Usage:
    python3 scripts/cleanup_stigmergy.py [--dry-run]
"""

import json
import re
import sys
from pathlib import Path

MARKS_FILE = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
ARCHIVE_FILE = Path.home() / ".dharma" / "stigmergy" / "marks_archived_noise.jsonl"

NOISE_PATTERNS = [
    re.compile(r"eval_probe_\d+"),
    re.compile(r"^Budget exhausted", re.IGNORECASE),
    re.compile(r"^task done successfully$", re.IGNORECASE),
]


def is_noise(mark: dict) -> bool:
    obs = mark.get("observation", "").strip()
    if len(obs) < 20:
        return True
    for pat in NOISE_PATTERNS:
        if pat.search(obs):
            return True
    return False


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if not MARKS_FILE.exists():
        print(f"No marks file at {MARKS_FILE}")
        return

    marks = []
    with open(MARKS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    marks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    keep = []
    noise = []
    for m in marks:
        if is_noise(m):
            noise.append(m)
        else:
            keep.append(m)

    print(f"Total marks:    {len(marks)}")
    print(f"Noise (remove): {len(noise)}")
    print(f"Keep:           {len(keep)}")

    if dry_run:
        print("\n[DRY RUN] No files modified.")
        if noise:
            print("\nSample noise marks:")
            for m in noise[:5]:
                print(f"  [{m.get('agent', '?')}] {m.get('observation', '')[:60]}")
        return

    # Archive noise
    with open(ARCHIVE_FILE, "a") as f:
        for m in noise:
            f.write(json.dumps(m) + "\n")

    # Rewrite clean marks
    with open(MARKS_FILE, "w") as f:
        for m in keep:
            f.write(json.dumps(m) + "\n")

    print(f"\nDone. Archived {len(noise)} noise marks to {ARCHIVE_FILE.name}")
    print(f"Clean marks file: {len(keep)} marks")


if __name__ == "__main__":
    main()
