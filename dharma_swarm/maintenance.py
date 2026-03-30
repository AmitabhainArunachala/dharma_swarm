"""Maintenance utilities — WAL checkpoint and JSONL rotation.

Designed to run daily to keep ~/.dharma/ from accumulating unbounded disk usage.

Usage (CLI):
    dgc maintenance             # run both checkpoint + rotate
    dgc maintenance --dry-run   # preview what would be rotated
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"


def checkpoint_wal_files(
    state_dir: Path | None = None,
) -> dict[str, int]:
    """Run PRAGMA wal_checkpoint(TRUNCATE) on every .db file under state_dir.

    Returns a mapping of {db_path: wal_pages_checkpointed}.
    """
    root = Path(state_dir) if state_dir else STATE_DIR
    results: dict[str, int] = {}

    for db_path in sorted(root.rglob("*.db")):
        try:
            con = sqlite3.connect(str(db_path), timeout=5)
            try:
                # Returns (busy, log, checkpointed)
                row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                pages = int(row[2]) if row else 0
                results[str(db_path)] = pages
                logger.info("WAL checkpoint %s: %d pages", db_path.name, pages)
            finally:
                con.close()
        except Exception as e:
            logger.warning("WAL checkpoint failed for %s: %s", db_path, e)
            results[str(db_path)] = -1

    logger.info("WAL checkpoint complete: %d databases", len(results))
    return results


def rotate_jsonl_files(
    max_mb: float = 50.0,
    state_dir: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Rotate .jsonl files larger than max_mb under state_dir.

    Renames foo.jsonl → foo.jsonl.YYYYMMDD and creates a fresh empty foo.jsonl.
    Returns list of rotated file paths.
    """
    root = Path(state_dir) if state_dir else STATE_DIR
    threshold = int(max_mb * 1024 * 1024)
    rotated: list[str] = []
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d")

    for jsonl_path in sorted(root.rglob("*.jsonl")):
        try:
            size = jsonl_path.stat().st_size
        except OSError:
            continue

        if size < threshold:
            continue

        archive = jsonl_path.with_suffix(f".jsonl.{stamp}")
        # Avoid clobbering an existing archive from the same day
        counter = 0
        while archive.exists():
            counter += 1
            archive = jsonl_path.with_suffix(f".jsonl.{stamp}_{counter}")

        if dry_run:
            logger.info(
                "DRY-RUN: would rotate %s (%.1f MB) → %s",
                jsonl_path.name,
                size / 1024 / 1024,
                archive.name,
            )
        else:
            try:
                jsonl_path.rename(archive)
                jsonl_path.touch()  # fresh empty file
                logger.info(
                    "Rotated %s (%.1f MB) → %s",
                    jsonl_path.name,
                    size / 1024 / 1024,
                    archive.name,
                )
            except OSError as e:
                logger.warning("Failed to rotate %s: %s", jsonl_path, e)
                continue

        rotated.append(str(jsonl_path))

    return rotated


async def run_maintenance(
    max_mb: float = 50.0,
    state_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Async entrypoint: run WAL checkpoint + JSONL rotation in an executor."""
    import asyncio

    loop = asyncio.get_event_loop()
    wal_result = await loop.run_in_executor(
        None, lambda: checkpoint_wal_files(state_dir=state_dir)
    )
    rotated = await loop.run_in_executor(
        None,
        lambda: rotate_jsonl_files(max_mb=max_mb, state_dir=state_dir, dry_run=dry_run),
    )
    return {"wal_checkpointed": wal_result, "jsonl_rotated": rotated}
