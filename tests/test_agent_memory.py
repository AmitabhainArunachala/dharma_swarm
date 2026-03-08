"""Tests for dharma_swarm.agent_memory -- self-editing agent memory bank."""

from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.agent_memory import AgentMemoryBank, AgentMemoryEntry


@pytest.fixture
def bank(tmp_path):
    """Create an AgentMemoryBank backed by a temp directory."""
    return AgentMemoryBank(agent_name="test_agent", base_path=tmp_path)


# -- 1. Remember a new entry in working memory ---------------------------

async def test_remember_working(bank):
    entry = await bank.remember("goal", "finish R_V paper", category="working", importance=0.8)
    assert entry.key == "goal"
    assert entry.value == "finish R_V paper"
    assert entry.importance == 0.8
    assert "goal" in bank._working


# -- 2. Remember in archival memory --------------------------------------

async def test_remember_archival(bank):
    entry = await bank.remember("old_finding", "L27 is causal", category="archival")
    assert entry.key == "old_finding"
    assert "old_finding" in bank._archival


# -- 3. Remember in persona ----------------------------------------------

async def test_remember_persona(bank):
    entry = await bank.remember("role", "I am the cartographer", category="persona")
    assert "role" in bank._persona
    assert entry.category == "persona"


# -- 4. Forget removes from correct tier ---------------------------------

async def test_forget_removes(bank):
    await bank.remember("temp", "temporary value", category="working")
    assert await bank.forget("temp") is True
    assert "temp" not in bank._working

    # Forgetting a missing key returns False
    assert await bank.forget("nonexistent") is False


# -- 5. Recall increments access_count -----------------------------------

async def test_recall_increments_access(bank):
    await bank.remember("fact", "water is wet", category="working")
    entry = await bank.recall("fact")
    assert entry is not None
    assert entry.access_count == 1

    entry2 = await bank.recall("fact")
    assert entry2 is not None
    assert entry2.access_count == 2


# -- 6. Search finds entries across tiers --------------------------------

async def test_search_across_tiers(bank):
    await bank.remember("rv_finding", "R_V contraction at Layer 27", category="working")
    await bank.remember("rv_archive", "R_V validated on Mistral", category="archival")
    await bank.remember("identity", "cartographer agent", category="persona")

    results = await bank.search("R_V")
    assert len(results) == 2
    keys = {r.key for r in results}
    assert "rv_finding" in keys
    assert "rv_archive" in keys


# -- 7. Promote moves archival -> working --------------------------------

async def test_promote(bank):
    await bank.remember("archived_item", "was cold", category="archival")
    assert "archived_item" in bank._archival

    result = await bank.promote("archived_item")
    assert result is True
    assert "archived_item" in bank._working
    assert "archived_item" not in bank._archival


# -- 8. Demote moves working -> archival ---------------------------------

async def test_demote(bank):
    await bank.remember("hot_item", "was working", category="working")
    assert "hot_item" in bank._working

    result = await bank.demote("hot_item")
    assert result is True
    assert "hot_item" in bank._archival
    assert "hot_item" not in bank._working


# -- 9. Auto-eviction when working memory is full ------------------------

async def test_auto_eviction(bank):
    # Fill working memory to max
    for i in range(bank.WORKING_MAX):
        await bank.remember(f"item_{i}", f"value_{i}", category="working", importance=0.5 + i * 0.01)

    assert len(bank._working) == bank.WORKING_MAX

    # Adding one more should evict the lowest-importance entry
    await bank.remember("new_item", "new_value", category="working", importance=0.9)
    assert len(bank._working) == bank.WORKING_MAX
    assert "new_item" in bank._working

    # The evicted item should have been demoted to archival
    assert "item_0" in bank._archival


# -- 10. get_working_context format --------------------------------------

async def test_get_working_context_format(bank):
    await bank.remember("name", "cartographer", category="persona")
    await bank.remember("task", "map the codebase", category="working", importance=0.7)

    ctx = await bank.get_working_context()
    assert "## Agent Memory (test_agent)" in ctx
    assert "### Persona" in ctx
    assert "name: cartographer" in ctx
    assert "### Working Memory" in ctx
    assert "task: map the codebase" in ctx
    assert "importance: 0.7" in ctx


# -- 11. Consolidation expires old entries -------------------------------

async def test_consolidate_expires(bank):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    entry = await bank.remember("ephemeral", "gone soon", category="working")
    entry.expires_at = past

    affected = await bank.consolidate()
    assert affected >= 1
    assert "ephemeral" not in bank._working


# -- 12. Consolidation demotes low-access working entries ----------------

async def test_consolidate_demotes_low_access(bank):
    entry = await bank.remember("weak", "low importance", category="working", importance=0.1)
    # access_count stays at 0, importance < 0.3 -> should be demoted
    assert entry.access_count == 0

    affected = await bank.consolidate()
    assert affected >= 1
    assert "weak" not in bank._working
    assert "weak" in bank._archival


# -- 13. learn_lesson creates high-importance archival entry --------------

async def test_learn_lesson(bank):
    entry = await bank.learn_lesson("Never trust bfloat16 on CPU", source="surgeon")
    assert entry.importance == 0.9
    assert entry.source == "surgeon"
    assert entry.key.startswith("lesson_")
    assert "Never trust" in entry.value
    # Lessons go to archival tier
    assert any(e.value == "Never trust bfloat16 on CPU" for e in bank._archival.values())


# -- 14. Save and load roundtrip -----------------------------------------

async def test_save_load_roundtrip(bank):
    await bank.remember("persistent", "survives restart", category="working", importance=0.8)
    await bank.remember("cold_store", "archived fact", category="archival")
    await bank.remember("identity", "I am the tester", category="persona")

    await bank.save()

    # Create a fresh bank pointing at the same path
    bank2 = AgentMemoryBank(agent_name="test_agent", base_path=bank._base_path)
    await bank2.load()

    assert "persistent" in bank2._working
    assert bank2._working["persistent"].value == "survives restart"
    assert bank2._working["persistent"].importance == 0.8
    assert "cold_store" in bank2._archival
    assert "identity" in bank2._persona


# -- 15. get_stats returns correct counts --------------------------------

async def test_get_stats(bank):
    await bank.remember("w1", "working 1", category="working")
    await bank.remember("w2", "working 2", category="working")
    await bank.remember("a1", "archival 1", category="archival")
    await bank.remember("p1", "persona 1", category="persona")

    stats = await bank.get_stats()
    assert stats["agent_name"] == "test_agent"
    assert stats["working_count"] == 2
    assert stats["archival_count"] == 1
    assert stats["persona_count"] == 1
    assert stats["total_count"] == 4
    assert "oldest" in stats
    assert "newest" in stats
    assert stats["total_importance"] > 0


# -- 16. Recall returns None for missing key -----------------------------

async def test_recall_missing_returns_none(bank):
    result = await bank.recall("does_not_exist")
    assert result is None


# -- 17. Cross-tier remember() moves entry from archival to working ------

async def test_remember_moves_archival_to_working(bank):
    """Regression: remember() with key in archival and category='working'
    must pop the entry from archival and insert it into working."""
    await bank.remember("migrating_key", "original value", category="archival")
    assert "migrating_key" in bank._archival
    assert "migrating_key" not in bank._working

    entry = await bank.remember("migrating_key", "updated value", category="working")

    assert entry.key == "migrating_key"
    assert entry.value == "updated value"
    assert entry.category == "working"
    assert "migrating_key" in bank._working
    assert "migrating_key" not in bank._archival


# -- 18. Cross-tier remember() moves entry from working to archival ------

async def test_remember_moves_working_to_archival(bank):
    """Regression: remember() with key in working and category='lesson'
    must pop the entry from working and insert it into archival."""
    await bank.remember("lesson_key", "hot insight", category="working", importance=0.7)
    assert "lesson_key" in bank._working
    assert "lesson_key" not in bank._archival

    entry = await bank.remember("lesson_key", "crystallized lesson", category="lesson", importance=0.9)

    assert entry.key == "lesson_key"
    assert entry.value == "crystallized lesson"
    assert entry.category == "lesson"
    assert entry.importance == 0.9
    assert "lesson_key" in bank._archival
    assert "lesson_key" not in bank._working


# -- 19. Cross-tier move leaves no orphan in old tier --------------------

async def test_cross_tier_move_no_orphan(bank):
    """After a cross-tier remember(), the old tier must not retain the key
    even after subsequent operations on the new tier."""
    await bank.remember("orphan_check", "start in archival", category="archival")
    await bank.remember("orphan_check", "now in working", category="working")

    # Verify old tier is clean
    assert "orphan_check" not in bank._archival

    # Access via recall — should find it in working, not archival
    recalled = await bank.recall("orphan_check")
    assert recalled is not None
    assert recalled.category == "working"

    # Total count should be 1, not 2
    stats = await bank.get_stats()
    assert stats["total_count"] == 1
    assert stats["working_count"] == 1
    assert stats["archival_count"] == 0
