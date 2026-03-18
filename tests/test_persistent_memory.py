"""Tests for the persistent memory layer."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.persistent_memory import (
    ConsolidationResult,
    MemoryEntry,
    PersistentMemory,
    _entry_to_md,
    _parse_entries_from_md,
)


@pytest.fixture
def mem_dir(tmp_path: Path) -> Path:
    return tmp_path / "memory"


@pytest.fixture
def memory(mem_dir: Path) -> PersistentMemory:
    return PersistentMemory(base_dir=mem_dir)


def test_entry_to_md_roundtrip():
    entry = MemoryEntry(
        id="abc123",
        content="Decided to use SQLite for persistence",
        category="decision",
        pillars=["PILLAR_08_BEER"],
        principles=["P1", "P6"],
        vsm_system="S3",
        tags=["persistence", "architecture"],
    )
    md = _entry_to_md(entry)
    assert "abc123" in md
    assert "DECISION" in md
    assert "PILLAR_08_BEER" in md
    assert "P1" in md

    # Parse back
    parsed = _parse_entries_from_md(md)
    assert len(parsed) == 1
    assert parsed[0].id == "abc123"
    assert parsed[0].category == "decision"
    assert "PILLAR_08_BEER" in parsed[0].pillars


@pytest.mark.asyncio
async def test_init_creates_files(memory: PersistentMemory, mem_dir: Path):
    await memory.init()
    assert (mem_dir / "recent-context.md").exists()
    assert (mem_dir / "long-term-patterns.md").exists()
    assert (mem_dir / "project-state.md").exists()


@pytest.mark.asyncio
async def test_add_and_get_recent(memory: PersistentMemory):
    await memory.init()
    entry = MemoryEntry(
        content="Test entry",
        category="general",
        tags=["test"],
    )
    entry_id = await memory.add_recent(entry)
    assert entry_id == entry.id

    entries = await memory.get_recent()
    assert len(entries) == 1
    assert entries[0].content == "Test entry"


@pytest.mark.asyncio
async def test_add_and_get_longterm(memory: PersistentMemory):
    await memory.init()
    entry = MemoryEntry(
        content="Pattern: gates always catch injection attempts",
        category="pattern",
        pillars=["PILLAR_06_DADA_BHAGWAN"],
    )
    await memory.add_longterm(entry)

    entries = await memory.get_longterm()
    assert len(entries) == 1
    assert "gates" in entries[0].content


@pytest.mark.asyncio
async def test_longterm_filter_by_category(memory: PersistentMemory):
    await memory.init()
    await memory.add_longterm(MemoryEntry(content="A", category="pattern"))
    await memory.add_longterm(MemoryEntry(content="B", category="decision"))

    patterns = await memory.get_longterm(category="pattern")
    assert len(patterns) == 1
    assert patterns[0].content == "A"


@pytest.mark.asyncio
async def test_consolidation_promotes_grounded_entries(memory: PersistentMemory):
    await memory.init()
    # Add an old entry with pillar grounding (should be promoted)
    old = MemoryEntry(
        content="Old grounded entry",
        category="decision",
        pillars=["PILLAR_04_HOFSTADTER"],
        timestamp=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    await memory.add_recent(old)

    # Add a recent entry (should stay)
    recent = MemoryEntry(content="Fresh entry", category="general")
    await memory.add_recent(recent)

    result = await memory.consolidate()
    assert result.promoted == 1

    # Recent should only have the fresh entry
    entries = await memory.get_recent()
    assert len(entries) == 1
    assert entries[0].content == "Fresh entry"

    # Long-term should have the promoted entry
    lt = await memory.get_longterm()
    assert len(lt) == 1
    assert lt[0].content == "Old grounded entry"


@pytest.mark.asyncio
async def test_consolidation_prunes_ungrounded_old_entries(memory: PersistentMemory):
    await memory.init()
    old = MemoryEntry(
        content="Random old note",
        category="general",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    await memory.add_recent(old)

    result = await memory.consolidate()
    assert result.pruned == 1
    assert result.archived_as_claims == 1

    entries = await memory.get_recent()
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_search(memory: PersistentMemory):
    await memory.init()
    await memory.add_recent(MemoryEntry(content="SQLite performance tuning", tags=["sqlite"]))
    await memory.add_longterm(MemoryEntry(content="Gate evaluation patterns", tags=["gates"]))

    results = await memory.search("sqlite")
    assert len(results) == 1
    assert "SQLite" in results[0].content

    results = await memory.search("gate", tier="longterm")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_project_state(memory: PersistentMemory):
    await memory.init()
    state = await memory.get_project_state()
    assert "Project State" in state
    assert "VSM Gap" in state
