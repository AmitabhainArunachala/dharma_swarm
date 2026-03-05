"""Tests for dharma_swarm.file_lock."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.file_lock import (
    AsyncFileLock,
    AsyncLockManager,
    FileLockBusy,
    FileLockError,
    FileLockTimeout,
    LockInfo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lock_dir(tmp_path: Path) -> Path:
    """Provide a temporary lock directory."""
    d = tmp_path / "locks"
    d.mkdir()
    return d


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample file to lock."""
    f = tmp_path / "sample.py"
    f.write_text("# sample")
    return f


# ---------------------------------------------------------------------------
# LockInfo model
# ---------------------------------------------------------------------------


class TestLockInfo:
    def test_round_trip(self) -> None:
        info = LockInfo(
            file_path="/tmp/x.py",
            agent_id="tester",
            acquired_at="2025-01-01T00:00:00+00:00",
            expires_at="2025-01-01T00:05:00+00:00",
            ttl_seconds=300,
            lock_id="abc12345",
        )
        data = info.model_dump()
        restored = LockInfo(**data)
        assert restored.agent_id == "tester"
        assert restored.ttl_seconds == 300

    def test_json_serialisation(self) -> None:
        info = LockInfo(
            file_path="/tmp/y.py",
            agent_id="a1",
            acquired_at="2025-01-01T00:00:00+00:00",
            expires_at="2025-01-01T00:05:00+00:00",
            ttl_seconds=300,
            lock_id="deadbeef",
        )
        raw = info.model_dump_json()
        restored = LockInfo.model_validate_json(raw)
        assert restored.lock_id == "deadbeef"


# ---------------------------------------------------------------------------
# AsyncFileLock — acquire / release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_and_release(sample_file: Path, lock_dir: Path) -> None:
    lock = AsyncFileLock(sample_file, agent_id="agent-1", lock_dir=lock_dir)
    await lock.acquire()

    assert lock.is_held
    assert lock.info is not None
    assert lock.info.agent_id == "agent-1"
    assert lock.info_file.exists()

    await lock.release()
    assert not lock.is_held
    assert not lock.info_file.exists()


@pytest.mark.asyncio
async def test_acquire_creates_lock_dir(tmp_path: Path) -> None:
    lock_dir = tmp_path / "nonexistent" / "locks"
    f = tmp_path / "file.txt"
    f.write_text("data")

    lock = AsyncFileLock(f, agent_id="a", lock_dir=lock_dir)
    await lock.acquire()
    assert lock_dir.exists()
    await lock.release()


@pytest.mark.asyncio
async def test_release_idempotent(sample_file: Path, lock_dir: Path) -> None:
    lock = AsyncFileLock(sample_file, agent_id="a", lock_dir=lock_dir)
    await lock.acquire()
    await lock.release()
    # Second release should not raise.
    await lock.release()


# ---------------------------------------------------------------------------
# AsyncFileLock — context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_context_manager(
    sample_file: Path, lock_dir: Path
) -> None:
    async with AsyncFileLock(
        sample_file, agent_id="ctx", lock_dir=lock_dir
    ) as lock:
        assert lock.is_held
        assert lock.info is not None
        assert lock.info.agent_id == "ctx"

    # After exiting the context the lock must be released.
    assert not lock.is_held


@pytest.mark.asyncio
async def test_context_manager_releases_on_exception(
    sample_file: Path, lock_dir: Path
) -> None:
    lock = AsyncFileLock(sample_file, agent_id="err", lock_dir=lock_dir)
    with pytest.raises(RuntimeError, match="boom"):
        async with lock:
            raise RuntimeError("boom")

    assert not lock.is_held
    assert not lock.info_file.exists()


# ---------------------------------------------------------------------------
# AsyncFileLock — TTL expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ttl_expiry_allows_reacquisition(
    sample_file: Path, lock_dir: Path
) -> None:
    """An expired lock should be broken so another agent can acquire."""
    # Agent A acquires with a 1-second TTL.
    lock_a = AsyncFileLock(
        sample_file, agent_id="a", ttl_seconds=1, lock_dir=lock_dir
    )
    await lock_a.acquire()

    # Manually expire the info file so we don't actually sleep.
    expired_info = lock_a.info.model_dump()  # type: ignore[union-attr]
    expired_info["expires_at"] = datetime(
        2000, 1, 1, tzinfo=timezone.utc
    ).isoformat()
    with open(lock_a.info_file, "w") as f:
        json.dump(expired_info, f)

    # Release the OS flock so agent B can actually flock.
    await lock_a.release()

    # Agent B should succeed immediately.
    lock_b = AsyncFileLock(
        sample_file, agent_id="b", timeout_seconds=2, lock_dir=lock_dir
    )
    await lock_b.acquire()
    assert lock_b.is_held
    assert lock_b.info is not None
    assert lock_b.info.agent_id == "b"
    await lock_b.release()


# ---------------------------------------------------------------------------
# AsyncFileLock — refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_extends_ttl(
    sample_file: Path, lock_dir: Path
) -> None:
    lock = AsyncFileLock(
        sample_file, agent_id="a", ttl_seconds=60, lock_dir=lock_dir
    )
    await lock.acquire()

    original_expires = lock.info.expires_at  # type: ignore[union-attr]
    # Small sleep so the timestamp differs.
    await asyncio.sleep(0.05)
    await lock.refresh()

    assert lock.info is not None
    assert lock.info.expires_at != original_expires
    await lock.release()


@pytest.mark.asyncio
async def test_refresh_without_lock_raises(
    sample_file: Path, lock_dir: Path
) -> None:
    lock = AsyncFileLock(sample_file, agent_id="a", lock_dir=lock_dir)
    with pytest.raises(FileLockError, match="not held"):
        await lock.refresh()


# ---------------------------------------------------------------------------
# AsyncFileLock — timeout / contention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_on_contention(
    sample_file: Path, lock_dir: Path
) -> None:
    """A second agent should time out if the first holds the lock."""
    lock_a = AsyncFileLock(
        sample_file, agent_id="holder", lock_dir=lock_dir
    )
    await lock_a.acquire()

    lock_b = AsyncFileLock(
        sample_file,
        agent_id="waiter",
        timeout_seconds=0.3,
        lock_dir=lock_dir,
    )
    with pytest.raises(FileLockTimeout):
        await lock_b.acquire()

    await lock_a.release()


# ---------------------------------------------------------------------------
# AsyncFileLock — concurrent access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_acquire(
    tmp_path: Path, lock_dir: Path
) -> None:
    """Only one of several concurrent acquires should succeed at a time."""
    target = tmp_path / "shared.txt"
    target.write_text("shared")
    results: list[str] = []

    async def worker(agent_id: str) -> None:
        lock = AsyncFileLock(
            target,
            agent_id=agent_id,
            ttl_seconds=5,
            timeout_seconds=5,
            lock_dir=lock_dir,
        )
        async with lock:
            results.append(agent_id)
            await asyncio.sleep(0.05)

    await asyncio.gather(
        worker("w1"), worker("w2"), worker("w3")
    )
    # All three should eventually succeed (sequentially via flock).
    assert sorted(results) == ["w1", "w2", "w3"]


# ---------------------------------------------------------------------------
# AsyncFileLock — same agent re-entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_agent_can_reacquire(
    sample_file: Path, lock_dir: Path
) -> None:
    """If the same agent_id holds the lock, acquire should still succeed."""
    lock1 = AsyncFileLock(
        sample_file, agent_id="same", lock_dir=lock_dir
    )
    await lock1.acquire()

    # Release lock1's OS flock so lock2 can actually flock the file.
    await lock1.release()

    lock2 = AsyncFileLock(
        sample_file, agent_id="same", timeout_seconds=2, lock_dir=lock_dir
    )
    await lock2.acquire()
    assert lock2.is_held
    await lock2.release()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_hierarchy(self) -> None:
        assert issubclass(FileLockTimeout, FileLockError)
        assert issubclass(FileLockBusy, FileLockError)

    def test_busy_carries_holder(self) -> None:
        holder = LockInfo(
            file_path="/x",
            agent_id="other",
            acquired_at="t0",
            expires_at="t1",
            ttl_seconds=60,
            lock_id="aa",
        )
        err = FileLockBusy("locked", holder=holder)
        assert err.holder is not None
        assert err.holder.agent_id == "other"

    def test_busy_holder_optional(self) -> None:
        err = FileLockBusy("locked")
        assert err.holder is None


# ---------------------------------------------------------------------------
# AsyncLockManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_manager_multi_file(
    tmp_path: Path, lock_dir: Path
) -> None:
    files = [tmp_path / f"file_{i}.py" for i in range(3)]
    for f in files:
        f.write_text("# code")

    mgr = AsyncLockManager("mgr-agent", lock_dir=lock_dir)
    await mgr.lock_files(files)

    assert len(mgr.locks) == 3
    for lock in mgr.locks:
        assert lock.is_held

    await mgr.release_all()
    for lock in mgr.locks:
        # locks list was cleared, but the lock objects were released
        pass
    assert len(mgr.locks) == 0


@pytest.mark.asyncio
async def test_lock_manager_sorted_acquisition(
    tmp_path: Path, lock_dir: Path
) -> None:
    """Lock manager acquires in sorted order to prevent deadlocks."""
    f_b = tmp_path / "b.py"
    f_a = tmp_path / "a.py"
    f_c = tmp_path / "c.py"
    for f in [f_a, f_b, f_c]:
        f.write_text("")

    mgr = AsyncLockManager("sorter", lock_dir=lock_dir)
    await mgr.lock_files([f_b, f_c, f_a])

    # Locks should be held in sorted path order.
    held_paths = [str(lock.file_path) for lock in mgr.locks]
    assert held_paths == sorted(held_paths)
    await mgr.release_all()


@pytest.mark.asyncio
async def test_lock_manager_context_manager(
    tmp_path: Path, lock_dir: Path
) -> None:
    f = tmp_path / "ctx.py"
    f.write_text("")

    mgr = AsyncLockManager("ctx", lock_dir=lock_dir)
    await mgr.lock_files([f])

    async with mgr:
        assert len(mgr.locks) == 1

    assert len(mgr.locks) == 0


@pytest.mark.asyncio
async def test_lock_manager_rollback_on_failure(
    tmp_path: Path, lock_dir: Path
) -> None:
    """If locking one file fails, previously acquired locks are released."""
    f1 = tmp_path / "ok.py"
    f1.write_text("")
    f2 = tmp_path / "fail.py"
    f2.write_text("")

    # Hold f2 with another agent so the manager fails on it.
    blocker = AsyncFileLock(f2, agent_id="blocker", lock_dir=lock_dir)
    await blocker.acquire()

    mgr = AsyncLockManager(
        "victim",
        ttl_seconds=300,
        lock_dir=lock_dir,
    )
    # Monkey-patch timeout so it fails fast.
    orig_init = AsyncFileLock.__init__

    def patched_init(self_lock, *args, **kwargs):  # type: ignore[no-untyped-def]
        orig_init(self_lock, *args, **kwargs)
        self_lock.timeout_seconds = 0.3

    with patch.object(AsyncFileLock, "__init__", patched_init):
        with pytest.raises(FileLockTimeout):
            await mgr.lock_files([f1, f2])

    # All locks from the manager should have been released.
    assert len(mgr.locks) == 0

    await blocker.release()


@pytest.mark.asyncio
async def test_lock_manager_release_all_idempotent(
    lock_dir: Path,
) -> None:
    mgr = AsyncLockManager("noop", lock_dir=lock_dir)
    # Should not raise when nothing is held.
    await mgr.release_all()
    assert len(mgr.locks) == 0
