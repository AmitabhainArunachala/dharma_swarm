"""Async file locking for multi-agent safety.

Prevents race conditions when multiple agents modify files concurrently.
Uses file-based locks with TTL to prevent deadlocks from crashed agents.
All I/O is async via asyncio.to_thread to avoid blocking the event loop.

Usage:
    from dharma_swarm.file_lock import AsyncFileLock

    async with AsyncFileLock("/path/to/file.py", agent_id="CODER") as lock:
        # File is locked; modify safely
        ...
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCK_DIR = Path.home() / ".dharma" / "locks"
DEFAULT_TTL_SECONDS: int = 300  # 5 minutes
LOCK_POLL_INTERVAL: float = 0.1  # 100 ms


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FileLockError(Exception):
    """Raised when a file lock operation fails."""


class FileLockTimeout(FileLockError):
    """Raised when lock acquisition times out."""


class FileLockBusy(FileLockError):
    """Raised when a file is locked by another agent.

    Attributes:
        holder: LockInfo for the current holder, if available.
    """

    def __init__(self, message: str, holder: Optional[LockInfo] = None) -> None:
        super().__init__(message)
        self.holder = holder


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class LockInfo(BaseModel):
    """Metadata about an active file lock."""

    file_path: str
    agent_id: str
    acquired_at: str
    expires_at: str
    ttl_seconds: int
    lock_id: str


# ---------------------------------------------------------------------------
# AsyncFileLock
# ---------------------------------------------------------------------------


class AsyncFileLock:
    """Async file-based lock with TTL for multi-agent safety.

    Features:
        - Atomic lock acquisition using ``fcntl.flock``.
        - Blocking I/O wrapped in ``asyncio.to_thread`` so the event loop
          is never blocked.
        - TTL prevents deadlocks from crashed agents.
        - Lock metadata stored as JSON for debugging.
        - Async context manager support.

    Args:
        file_path: Path to the file to lock.
        agent_id: Identifier for the locking agent.
        ttl_seconds: Time-to-live for the lock in seconds.
        timeout_seconds: Maximum wait time for lock acquisition.
        force: If True, automatically break expired locks.
        lock_dir: Override the default lock directory (useful for testing).
    """

    def __init__(
        self,
        file_path: str | Path,
        agent_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        timeout_seconds: int = 30,
        force: bool = False,
        lock_dir: Optional[Path] = None,
    ) -> None:
        self.file_path = Path(file_path).resolve()
        self.agent_id = agent_id
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.force = force
        self._lock_dir = lock_dir or LOCK_DIR

        # Derive lock file paths from a hash of the target path.
        file_hash = hashlib.md5(str(self.file_path).encode()).hexdigest()[:12]
        self.lock_file = self._lock_dir / f"{file_hash}.lock"
        self.info_file = self._lock_dir / f"{file_hash}.info.json"

        self._lock_fd: Optional[int] = None
        self._lock_info: Optional[LockInfo] = None

    # -- public async API ---------------------------------------------------

    async def acquire(self) -> AsyncFileLock:
        """Acquire the file lock.

        Returns:
            self, for chaining.

        Raises:
            FileLockTimeout: If the lock cannot be acquired within
                ``timeout_seconds``.
        """
        return await asyncio.to_thread(self._acquire_sync)

    async def release(self) -> None:
        """Release the file lock and remove lock files."""
        await asyncio.to_thread(self._release_sync)

    async def refresh(self) -> None:
        """Refresh the lock TTL without releasing it.

        Raises:
            FileLockError: If the lock is not currently held.
        """
        await asyncio.to_thread(self._refresh_sync)

    # -- async context manager ----------------------------------------------

    async def __aenter__(self) -> AsyncFileLock:
        return await self.acquire()

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: object,
    ) -> None:
        await self.release()

    # -- properties ---------------------------------------------------------

    @property
    def is_held(self) -> bool:
        """Return True if this instance currently holds the lock."""
        return self._lock_fd is not None

    @property
    def info(self) -> Optional[LockInfo]:
        """Return lock metadata if the lock is held."""
        return self._lock_info

    # -- synchronous internals (run via to_thread) --------------------------

    def _acquire_sync(self) -> AsyncFileLock:
        """Blocking lock acquisition — called inside ``to_thread``."""
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        start_time = time.monotonic()

        while True:
            existing = self._read_lock_info()

            if existing is not None:
                expires_at = datetime.fromisoformat(existing.expires_at)
                now_utc = datetime.now(timezone.utc)

                if now_utc > expires_at:
                    # Lock expired — break it regardless of ``force``.
                    logger.warning(
                        "Breaking expired lock held by %s (lock_id=%s)",
                        existing.agent_id,
                        existing.lock_id,
                    )
                    self._break_lock()
                elif existing.agent_id == self.agent_id:
                    # Same agent — treat as refresh.
                    pass
                else:
                    # Another agent holds it.
                    elapsed = time.monotonic() - start_time
                    if elapsed > self.timeout_seconds:
                        raise FileLockTimeout(
                            f"Timeout after {self.timeout_seconds}s waiting "
                            f"for lock on {self.file_path}"
                        )
                    time.sleep(LOCK_POLL_INTERVAL)
                    continue

            # Attempt to acquire the OS-level lock.
            try:
                self._lock_fd = os.open(
                    str(self.lock_file), os.O_CREAT | os.O_RDWR
                )
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._write_lock_info()
                return self
            except (IOError, OSError):
                if self._lock_fd is not None:
                    os.close(self._lock_fd)
                    self._lock_fd = None

                elapsed = time.monotonic() - start_time
                if elapsed > self.timeout_seconds:
                    raise FileLockTimeout(
                        f"Timeout after {self.timeout_seconds}s waiting "
                        f"for lock on {self.file_path}"
                    )
                time.sleep(LOCK_POLL_INTERVAL)

    def _release_sync(self) -> None:
        """Blocking lock release — called inside ``to_thread``."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except (IOError, OSError):
                pass
            finally:
                self._lock_fd = None

        self._cleanup_files()
        self._lock_info = None

    def _refresh_sync(self) -> None:
        """Blocking TTL refresh — called inside ``to_thread``."""
        if self._lock_fd is None:
            raise FileLockError("Cannot refresh — lock not held")
        self._write_lock_info()

    # -- file helpers -------------------------------------------------------

    def _read_lock_info(self) -> Optional[LockInfo]:
        """Read existing lock metadata from disk."""
        if not self.info_file.exists():
            return None
        try:
            with open(self.info_file) as f:
                data = json.load(f)
            return LockInfo(**data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def _write_lock_info(self) -> None:
        """Write lock metadata to disk."""
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(
            now.timestamp() + self.ttl_seconds, timezone.utc
        )
        self._lock_info = LockInfo(
            file_path=str(self.file_path),
            agent_id=self.agent_id,
            acquired_at=now.isoformat(),
            expires_at=expires.isoformat(),
            ttl_seconds=self.ttl_seconds,
            lock_id=hashlib.md5(
                f"{self.file_path}{now.isoformat()}".encode()
            ).hexdigest()[:8],
        )
        with open(self.info_file, "w") as f:
            json.dump(self._lock_info.model_dump(), f, indent=2)

    def _break_lock(self) -> None:
        """Remove stale lock files so a new lock can be acquired."""
        self._cleanup_files()

    def _cleanup_files(self) -> None:
        """Remove lock and info files from disk."""
        try:
            self.lock_file.unlink(missing_ok=True)
        except (IOError, OSError):
            pass
        try:
            self.info_file.unlink(missing_ok=True)
        except (IOError, OSError):
            pass


# ---------------------------------------------------------------------------
# AsyncLockManager
# ---------------------------------------------------------------------------


class AsyncLockManager:
    """Manage multiple async file locks for batch operations.

    Files are locked in sorted path order to prevent deadlocks.

    Args:
        agent_id: Identifier for the locking agent.
        ttl_seconds: Time-to-live for each individual lock.
        lock_dir: Override the default lock directory (useful for testing).
    """

    def __init__(
        self,
        agent_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        lock_dir: Optional[Path] = None,
    ) -> None:
        self.agent_id = agent_id
        self.ttl_seconds = ttl_seconds
        self._lock_dir = lock_dir
        self._locks: list[AsyncFileLock] = []

    async def lock_files(
        self, file_paths: list[str | Path]
    ) -> AsyncLockManager:
        """Acquire locks on multiple files in sorted order.

        Args:
            file_paths: Paths to the files to lock.

        Returns:
            self, for chaining / context manager usage.

        Raises:
            FileLockError: If any lock cannot be acquired. Already-acquired
                locks are released before re-raising.
        """
        sorted_paths = sorted(str(p) for p in file_paths)

        try:
            for path in sorted_paths:
                lock = AsyncFileLock(
                    path,
                    self.agent_id,
                    ttl_seconds=self.ttl_seconds,
                    lock_dir=self._lock_dir,
                )
                await lock.acquire()
                self._locks.append(lock)
            return self
        except FileLockError:
            await self.release_all()
            raise

    async def release_all(self) -> None:
        """Release all held locks."""
        for lock in self._locks:
            try:
                await lock.release()
            except Exception:
                logger.debug("Lock release failed", exc_info=True)
        self._locks.clear()

    @property
    def locks(self) -> list[AsyncFileLock]:
        """Return the list of currently held locks."""
        return list(self._locks)

    async def __aenter__(self) -> AsyncLockManager:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: object,
    ) -> None:
        await self.release_all()
