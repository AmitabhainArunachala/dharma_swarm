"""Tests for dharma_swarm.traces -- TraceEntry, TraceStore, atomic_write_json."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.traces import TraceEntry, TraceStore, atomic_write_json


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trace_dir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory for a TraceStore."""
    return tmp_path / "traces"


@pytest.fixture
async def store(trace_dir: Path) -> TraceStore:
    """Return an initialised TraceStore pointed at *trace_dir*."""
    s = TraceStore(base_path=trace_dir)
    await s.init()
    return s


def _make_entry(**kw) -> TraceEntry:
    """Shorthand for building test trace entries."""
    defaults = {"agent": "test-agent", "action": "test_action"}
    defaults.update(kw)
    return TraceEntry(**defaults)


# ---------------------------------------------------------------------------
# atomic_write_json
# ---------------------------------------------------------------------------


def test_atomic_write_creates_file(tmp_path: Path):
    dest = tmp_path / "out.json"
    atomic_write_json(dest, {"hello": "world"})
    assert dest.exists()
    with open(dest) as f:
        data = json.load(f)
    assert data == {"hello": "world"}


def test_atomic_write_overwrites_existing(tmp_path: Path):
    dest = tmp_path / "out.json"
    atomic_write_json(dest, {"v": 1})
    atomic_write_json(dest, {"v": 2})
    with open(dest) as f:
        data = json.load(f)
    assert data["v"] == 2


def test_atomic_write_creates_parent_dirs(tmp_path: Path):
    dest = tmp_path / "a" / "b" / "c" / "out.json"
    atomic_write_json(dest, {"nested": True})
    assert dest.exists()


def test_atomic_write_serialises_datetime(tmp_path: Path):
    dest = tmp_path / "dt.json"
    now = datetime.now(timezone.utc)
    atomic_write_json(dest, {"ts": now})
    with open(dest) as f:
        data = json.load(f)
    assert isinstance(data["ts"], str)


# ---------------------------------------------------------------------------
# TraceEntry model
# ---------------------------------------------------------------------------


def test_entry_defaults():
    e = _make_entry()
    assert len(e.id) == 16
    assert e.state == "active"
    assert e.parent_id is None
    assert e.fitness is None
    assert e.files_changed == []
    assert e.metadata == {}


def test_entry_json_roundtrip():
    e = _make_entry(
        agent="builder",
        action="task_completed",
        state="done",
        fitness=FitnessScore(correctness=0.9, safety=1.0),
        files_changed=["a.py", "b.py"],
        metadata={"tokens": 42},
    )
    data = e.model_dump_json()
    e2 = TraceEntry.model_validate_json(data)
    assert e2.id == e.id
    assert e2.agent == "builder"
    assert e2.fitness is not None
    assert e2.fitness.correctness == 0.9
    assert e2.files_changed == ["a.py", "b.py"]
    assert e2.metadata["tokens"] == 42


# ---------------------------------------------------------------------------
# TraceStore.init
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_creates_directories(trace_dir: Path):
    store = TraceStore(base_path=trace_dir)
    await store.init()
    assert (trace_dir / "history").is_dir()
    assert (trace_dir / "archive").is_dir()
    assert (trace_dir / "patterns").is_dir()


# ---------------------------------------------------------------------------
# log_entry + get_entry roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_entry_creates_file(store: TraceStore, trace_dir: Path):
    entry = _make_entry(agent="alpha", action="agent_spawned")
    eid = await store.log_entry(entry)
    assert (trace_dir / "history" / f"{eid}.json").exists()


@pytest.mark.asyncio
async def test_get_entry_roundtrip(store: TraceStore):
    entry = _make_entry(agent="beta", action="pulse", state="running")
    eid = await store.log_entry(entry)
    got = await store.get_entry(eid)
    assert got is not None
    assert got.agent == "beta"
    assert got.action == "pulse"
    assert got.state == "running"


@pytest.mark.asyncio
async def test_get_entry_missing(store: TraceStore):
    got = await store.get_entry("nonexistent")
    assert got is None


# ---------------------------------------------------------------------------
# get_recent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_ordering(store: TraceStore):
    now = datetime.now(timezone.utc)
    old = _make_entry(agent="a", action="old")
    old.timestamp = now - timedelta(hours=2)
    mid = _make_entry(agent="b", action="mid")
    mid.timestamp = now - timedelta(hours=1)
    new = _make_entry(agent="c", action="new")
    new.timestamp = now

    for e in (old, mid, new):
        await store.log_entry(e)

    recent = await store.get_recent(limit=10)
    assert len(recent) == 3
    assert recent[0].agent == "c"
    assert recent[1].agent == "b"
    assert recent[2].agent == "a"


@pytest.mark.asyncio
async def test_get_recent_limit(store: TraceStore):
    for i in range(10):
        await store.log_entry(_make_entry(agent=f"agent-{i}", action="tick"))
    recent = await store.get_recent(limit=3)
    assert len(recent) == 3


@pytest.mark.asyncio
async def test_get_recent_empty(store: TraceStore):
    recent = await store.get_recent()
    assert recent == []


# ---------------------------------------------------------------------------
# get_lineage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lineage_chain(store: TraceStore):
    grandparent = _make_entry(agent="gp", action="start")
    parent = _make_entry(agent="p", action="fork", parent_id=grandparent.id)
    child = _make_entry(agent="c", action="task", parent_id=parent.id)

    for e in (grandparent, parent, child):
        await store.log_entry(e)

    lineage = await store.get_lineage(child.id)
    assert len(lineage) == 3
    assert lineage[0].id == child.id
    assert lineage[1].id == parent.id
    assert lineage[2].id == grandparent.id


@pytest.mark.asyncio
async def test_get_lineage_single(store: TraceStore):
    entry = _make_entry(agent="lone", action="solo")
    await store.log_entry(entry)
    lineage = await store.get_lineage(entry.id)
    assert len(lineage) == 1
    assert lineage[0].id == entry.id


@pytest.mark.asyncio
async def test_get_lineage_missing_id(store: TraceStore):
    lineage = await store.get_lineage("nope")
    assert lineage == []


@pytest.mark.asyncio
async def test_get_lineage_broken_chain(store: TraceStore):
    """Parent referenced but not present -- lineage stops at the break."""
    child = _make_entry(agent="orphan", action="task", parent_id="ghost")
    await store.log_entry(child)
    lineage = await store.get_lineage(child.id)
    assert len(lineage) == 1
    assert lineage[0].id == child.id


# ---------------------------------------------------------------------------
# archive_old
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_old_moves_entries(store: TraceStore, trace_dir: Path):
    now = datetime.now(timezone.utc)

    old_entry = _make_entry(agent="old", action="ancient")
    old_entry.timestamp = now - timedelta(hours=48)
    await store.log_entry(old_entry)

    new_entry = _make_entry(agent="new", action="fresh")
    new_entry.timestamp = now
    await store.log_entry(new_entry)

    count = await store.archive_old(max_age_hours=24)
    assert count == 1

    # Old entry moved to archive
    assert not (trace_dir / "history" / f"{old_entry.id}.json").exists()
    assert (trace_dir / "archive" / f"{old_entry.id}.json").exists()

    # New entry still in history
    assert (trace_dir / "history" / f"{new_entry.id}.json").exists()


@pytest.mark.asyncio
async def test_archive_old_returns_zero_when_nothing_old(store: TraceStore):
    now = datetime.now(timezone.utc)
    entry = _make_entry(agent="fresh", action="new")
    entry.timestamp = now
    await store.log_entry(entry)
    count = await store.archive_old(max_age_hours=24)
    assert count == 0


@pytest.mark.asyncio
async def test_archive_old_empty_store(store: TraceStore):
    count = await store.archive_old(max_age_hours=1)
    assert count == 0


# ---------------------------------------------------------------------------
# Empty store edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_store_operations(store: TraceStore):
    assert await store.get_entry("anything") is None
    assert await store.get_recent(5) == []
    assert await store.get_lineage("anything") == []
    assert await store.archive_old(1) == 0
