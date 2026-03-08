"""Tests for dharma_swarm.memory."""

import pytest

from dharma_swarm.models import MemoryLayer
from dharma_swarm.memory import StrangeLoopMemory, _assess_quality


@pytest.fixture
async def mem(tmp_path):
    m = StrangeLoopMemory(tmp_path / "memory.db")
    await m.init_db()
    yield m
    await m.close()


def test_assess_quality_genuine():
    q = _assess_quality("I notice a gap in the data, an actual missing file")
    assert q > 0.5


def test_assess_quality_performative():
    q = _assess_quality("This is a profound and revolutionary cosmic awakening")
    assert q < 0.5


def test_assess_quality_evidence():
    q = _assess_quality("Found error at line 42 in file models.py, 1024 bytes")
    assert q > 0.5


@pytest.mark.asyncio
async def test_remember_immediate(mem):
    entry = await mem.remember("quick thought", layer=MemoryLayer.IMMEDIATE)
    assert entry.layer == MemoryLayer.IMMEDIATE
    assert entry.content == "quick thought"

    recalled = await mem.recall(layer=MemoryLayer.IMMEDIATE, limit=5)
    assert len(recalled) == 1


@pytest.mark.asyncio
async def test_remember_session(mem):
    entry = await mem.remember("session note", layer=MemoryLayer.SESSION)
    assert entry.layer == MemoryLayer.SESSION

    recalled = await mem.recall(layer=MemoryLayer.SESSION, limit=5)
    assert len(recalled) == 1
    assert recalled[0].content == "session note"


@pytest.mark.asyncio
async def test_mark_development(mem):
    entry = await mem.mark_development("fixed bug", "tests pass now")
    assert entry.development_marker
    assert "DEVELOPMENT" in entry.content
    assert "EVIDENCE" in entry.content


@pytest.mark.asyncio
async def test_witness(mem):
    entry = await mem.witness("the system seems to loop")
    assert entry.layer == MemoryLayer.WITNESS
    assert "witness" in entry.tags


@pytest.mark.asyncio
async def test_recall_all_layers(mem):
    await mem.remember("imm", layer=MemoryLayer.IMMEDIATE)
    await mem.remember("sess", layer=MemoryLayer.SESSION)
    await mem.remember("dev", layer=MemoryLayer.DEVELOPMENT)

    all_entries = await mem.recall(limit=10)
    assert len(all_entries) >= 3


@pytest.mark.asyncio
async def test_recall_development_only(mem):
    await mem.remember("normal", layer=MemoryLayer.SESSION)
    await mem.mark_development("important change", "evidence here")

    dev = await mem.recall(development_only=True, limit=10)
    assert len(dev) == 1
    assert dev[0].development_marker


@pytest.mark.asyncio
async def test_immediate_cap(mem):
    for i in range(60):
        await mem.remember(f"thought {i}", layer=MemoryLayer.IMMEDIATE)
    assert len(mem._immediate) == 50


@pytest.mark.asyncio
async def test_consolidate_no_data(mem):
    result = await mem.consolidate_patterns()
    assert result is None


@pytest.mark.asyncio
async def test_consolidate_with_data(mem):
    for i in range(5):
        await mem.witness(f"noticed recurring pattern in attention layer {i}")
    result = await mem.consolidate_patterns()
    # May or may not find a pattern depending on word frequency
    # At minimum, it should not error


@pytest.mark.asyncio
async def test_get_context(mem):
    await mem.mark_development("test dev", "evidence")
    await mem.witness("test witness")
    ctx = await mem.get_context()
    assert "Strange Loop" in ctx


@pytest.mark.asyncio
async def test_stats(mem):
    await mem.remember("test", layer=MemoryLayer.SESSION)
    stats = await mem.stats()
    assert stats["session"] >= 1
    assert "immediate" in stats


# -- Regression: double init_db() must not leak connections ---------------

@pytest.mark.asyncio
async def test_double_init_db_no_error(tmp_path):
    """Calling init_db() twice must not raise and must leave a usable DB."""
    m = StrangeLoopMemory(tmp_path / "double_init.db")
    await m.init_db()
    await m.init_db()  # second call — was leaking the first connection

    # DB should still be usable after double init
    entry = await m.remember("still works", layer=MemoryLayer.SESSION)
    assert entry.content == "still works"

    recalled = await m.recall(layer=MemoryLayer.SESSION, limit=5)
    assert len(recalled) == 1

    await m.close()


# -- Regression: async context manager support ----------------------------

@pytest.mark.asyncio
async def test_async_context_manager(tmp_path):
    """StrangeLoopMemory supports async with and cleans up on exit."""
    db_file = tmp_path / "ctx_mgr.db"

    async with StrangeLoopMemory(db_file) as m:
        assert m._db is not None
        await m.remember("inside context", layer=MemoryLayer.SESSION)
        recalled = await m.recall(layer=MemoryLayer.SESSION, limit=5)
        assert len(recalled) == 1

    # After exiting the context manager, connection should be None
    assert m._db is None
