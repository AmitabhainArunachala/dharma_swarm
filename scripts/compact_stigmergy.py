#!/usr/bin/env python3
"""Compact stigmergy marks: keep recent + high-salience, archive the rest.

Strategy:
  marks.jsonl     — keep marks from last 7 days OR salience > 0.5
  archive.jsonl   — keep marks with salience >= 0.5 (high-value historical)
  marks_bloated_backup.jsonl — compress to .gz, remove original
  marks_archived_noise.jsonl — compress to .gz, remove original

All writes use atomic rename (write to .tmp, rename) to prevent
corruption if the daemon reads mid-write.

Backups are gzip-compressed before any modification.
"""

import gzip
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

STIGMERGY_DIR = Path.home() / ".dharma" / "stigmergy"
MARKS_FILE = STIGMERGY_DIR / "marks.jsonl"
ARCHIVE_FILE = STIGMERGY_DIR / "archive.jsonl"
BLOATED_FILE = STIGMERGY_DIR / "marks_bloated_backup.jsonl"
NOISE_FILE = STIGMERGY_DIR / "marks_archived_noise.jsonl"

CUTOFF = datetime.now(timezone.utc) - timedelta(days=7)
SALIENCE_THRESHOLD = 0.5


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp, handling both Z and +00:00 suffixes."""
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def file_stats(path: Path) -> tuple[int, str]:
    """Return (line_count, human_readable_size) for a file."""
    if not path.exists():
        return 0, "0B"
    size = path.stat().st_size
    lines = 0
    with open(path) as f:
        for _ in f:
            lines += 1
    if size >= 1_073_741_824:
        human = f"{size / 1_073_741_824:.2f} GB"
    elif size >= 1_048_576:
        human = f"{size / 1_048_576:.2f} MB"
    elif size >= 1024:
        human = f"{size / 1024:.2f} KB"
    else:
        human = f"{size} B"
    return lines, human


def compress_and_remove(path: Path) -> Path | None:
    """Gzip-compress a file and remove the original. Returns gz path."""
    if not path.exists():
        return None
    gz_path = path.with_suffix(path.suffix + ".bak.gz")
    print(f"  Compressing {path.name} -> {gz_path.name} ...")
    with open(path, "rb") as f_in:
        with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    original_size = path.stat().st_size
    gz_size = gz_path.stat().st_size
    ratio = (1 - gz_size / original_size) * 100 if original_size > 0 else 0
    print(f"  Compressed: {original_size:,} -> {gz_size:,} bytes ({ratio:.1f}% reduction)")
    path.unlink()
    print(f"  Removed original: {path.name}")
    return gz_path


def compact_jsonl(
    path: Path,
    keep_fn,
    label: str,
) -> tuple[int, int]:
    """Compact a JSONL file using keep_fn predicate.

    Returns (original_count, kept_count).
    Uses atomic temp-file -> rename.
    """
    if not path.exists():
        print(f"  {label}: file not found, skipping.")
        return 0, 0

    kept = []
    discarded = 0
    corrupt = 0
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                if keep_fn(obj):
                    kept.append(stripped)
                else:
                    discarded += 1
            except json.JSONDecodeError:
                corrupt += 1

    original_count = len(kept) + discarded + corrupt
    print(f"  {label}: {original_count} marks -> {len(kept)} kept, {discarded} discarded, {corrupt} corrupt")

    # Backup before modifying
    backup_gz = path.with_suffix(path.suffix + ".bak.gz")
    if not backup_gz.exists():
        print(f"  Backing up {path.name} -> {backup_gz.name} ...")
        with open(path, "rb") as f_in:
            with gzip.open(backup_gz, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)

    # Atomic write: temp file -> rename
    tmp_path = path.with_suffix(".compact.tmp")
    with open(tmp_path, "w") as f:
        for line in kept:
            f.write(line + "\n")
    tmp_path.replace(path)
    print(f"  Atomic rename complete: {path.name}")

    return original_count, len(kept)


def main():
    print("=" * 60)
    print("STIGMERGY COMPACTION")
    print("=" * 60)
    print(f"Directory: {STIGMERGY_DIR}")
    print(f"Cutoff:    {CUTOFF.isoformat()} (7 days ago)")
    print(f"Salience:  > {SALIENCE_THRESHOLD}")
    print()

    # --- Before stats ---
    print("BEFORE:")
    before = {}
    for name in ["marks.jsonl", "archive.jsonl", "marks_bloated_backup.jsonl",
                  "marks_archived_noise.jsonl", "cc_tool_marks.jsonl", "forge_scores.jsonl"]:
        p = STIGMERGY_DIR / name
        lines, size = file_stats(p)
        before[name] = (lines, size)
        if p.exists():
            print(f"  {name:40s} {lines:>8,} lines  {size:>10s}")
    total_before = sum(
        (STIGMERGY_DIR / name).stat().st_size
        for name in before
        if (STIGMERGY_DIR / name).exists()
    )
    print(f"  {'TOTAL':40s} {'':>8s}        {total_before / 1_048_576:.2f} MB")
    print()

    # --- Step 1: Compress and remove the 1.3GB bloated backup ---
    print("STEP 1: Compress bloated backup (1.3GB)")
    compress_and_remove(BLOATED_FILE)
    print()

    # --- Step 2: Compress and remove old noise archive ---
    print("STEP 2: Compress archived noise")
    compress_and_remove(NOISE_FILE)
    print()

    # --- Step 3: Compact marks.jsonl ---
    print("STEP 3: Compact marks.jsonl (last 7 days OR salience > 0.5)")

    def keep_mark(obj):
        salience = obj.get("salience", 0)
        if salience > SALIENCE_THRESHOLD:
            return True
        ts_str = obj.get("timestamp", "")
        if not ts_str:
            return False
        try:
            ts = parse_timestamp(ts_str)
            return ts >= CUTOFF
        except (ValueError, TypeError):
            return False

    compact_jsonl(MARKS_FILE, keep_mark, "marks.jsonl")
    print()

    # --- Step 4: Compact archive.jsonl ---
    print("STEP 4: Compact archive.jsonl (salience >= 0.5 only)")

    def keep_archive(obj):
        return obj.get("salience", 0) >= SALIENCE_THRESHOLD

    compact_jsonl(ARCHIVE_FILE, keep_archive, "archive.jsonl")
    print()

    # --- After stats ---
    print("AFTER:")
    total_after = 0
    for name in ["marks.jsonl", "archive.jsonl", "cc_tool_marks.jsonl", "forge_scores.jsonl"]:
        p = STIGMERGY_DIR / name
        lines, size = file_stats(p)
        if p.exists():
            total_after += p.stat().st_size
            print(f"  {name:40s} {lines:>8,} lines  {size:>10s}")

    # Also count .gz files
    print()
    print("  Compressed backups:")
    for gz in sorted(STIGMERGY_DIR.glob("*.bak.gz")):
        sz = gz.stat().st_size
        total_after += sz
        if sz >= 1_048_576:
            human = f"{sz / 1_048_576:.2f} MB"
        elif sz >= 1024:
            human = f"{sz / 1024:.2f} KB"
        else:
            human = f"{sz} B"
        print(f"  {gz.name:40s} {human:>10s}")

    print()
    print(f"  Total before: {total_before / 1_048_576:.2f} MB")
    print(f"  Total after:  {total_after / 1_048_576:.2f} MB")
    reduction = (1 - total_after / total_before) * 100 if total_before > 0 else 0
    print(f"  Reduction:    {reduction:.1f}%")
    print()
    print("DONE.")


if __name__ == "__main__":
    main()
