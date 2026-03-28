"""Centralized SQLite connection utilities with WAL mode enforcement.

EVERY SQLite connection in dharma_swarm should go through these helpers.
WAL mode prevents the lock contention that cripples the 3.4GB memory_plane.db.

Usage:
    # Sync
    with connect_sync(db_path) as conn:
        conn.execute("SELECT ...")

    # Async
    async with connect_async(db_path) as db:
        await db.execute("SELECT ...")
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import aiosqlite

# Default busy timeout: 5 seconds
_BUSY_TIMEOUT_S = 5.0


@contextmanager
def connect_sync(
    db_path: str | Path,
    timeout: float = _BUSY_TIMEOUT_S,
    row_factory: Any = sqlite3.Row,
) -> Iterator[sqlite3.Connection]:
    """Open a sync SQLite connection with WAL mode enforced.

    Args:
        db_path: Path to the database file.
        timeout: Busy timeout in seconds.
        row_factory: Row factory (default: sqlite3.Row for dict-like access).
    """
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    try:
        conn.row_factory = row_factory
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def connect_async(
    db_path: str | Path,
    timeout: float = _BUSY_TIMEOUT_S,
) -> AsyncIterator[aiosqlite.Connection]:
    """Open an async SQLite connection with WAL mode enforced.

    Args:
        db_path: Path to the database file.
        timeout: Busy timeout in seconds.
    """
    async with aiosqlite.connect(str(db_path), timeout=timeout) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        yield db


def ensure_wal(db_path: str | Path) -> str:
    """Ensure a database is in WAL mode. Returns the current journal mode.

    Safe to call on databases that are already in WAL mode.
    Can be called as a standalone fix for existing databases.
    """
    with sqlite3.connect(str(db_path)) as conn:
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.execute("PRAGMA busy_timeout=5000")
        return result[0] if result else "unknown"
