"""Tests for dharma_swarm.agent_memory_manager -- SQLite-backed self-managing memory."""

import asyncio
import importlib
import sys
import time
from pathlib import Path

import pytest

# Avoid triggering dharma_swarm.__init__ (which has a pre-existing circular
# import in the provider chain). Import the module directly via its file path.
_MOD_PATH = Path(__file__).resolve().parent.parent / "dharma_swarm" / "agent_memory_manager.py"
_spec = importlib.util.spec_from_file_location("dharma_swarm.agent_memory_manager", _MOD_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("dharma_swarm.agent_memory_manager", _mod)
_spec.loader.exec_module(_mod)

AgentMemoryManager = _mod.AgentMemoryManager
Memory = _mod.Memory
Scope = _mod.Scope


@pytest.fixture
def db_path(tmp_path):
    """Return a temp SQLite DB path."""
    return tmp_path / "test_memories.db"


@pytest.fixture
def mgr(db_path):
    """Create a fresh AgentMemoryManager."""
    m = AgentMemoryManager("test_agent", db_path=db_path)
    yield m
    m.close()


@pytest.fixture
def mgr_b(db_path):
    """A second agent sharing the same database."""
    m = AgentMemoryManager("agent_b", db_path=db_path)
    yield m
    m.close()


# ---------------------------------------------------------------------------
# 1. Remember / Recall / Forget cycle
# ---------------------------------------------------------------------------


async def test_remember_and_recall_by_key(mgr):
    """remember() stores, recall_by_key() retrieves."""
    mem = await mgr.remember("goal", "finish R_V paper", scope=Scope.WORKING)
    assert mem.key == "goal"
    assert mem.content == "finish R_V paper"
    assert mem.scope == Scope.WORKING

    recalled = await mgr.recall_by_key("goal")
    assert recalled is not None
    assert recalled.content == "finish R_V paper"
    assert recalled.access_count >= 1


async def test_remember_upserts(mgr):
    """Second remember() with same key+scope updates content."""
    await mgr.remember("fact", "water is wet", scope=Scope.WORKING)
    await mgr.remember("fact", "water is very wet", scope=Scope.WORKING)

    recalled = await mgr.recall_by_key("fact", scope=Scope.WORKING)
    assert recalled is not None
    assert recalled.content == "water is very wet"


async def test_forget_removes(mgr):
    """forget() deletes from the correct scope."""
    await mgr.remember("temp", "temporary value", scope=Scope.SHORT_TERM)
    assert await mgr.forget("temp", scope=Scope.SHORT_TERM) is True
    assert await mgr.recall_by_key("temp", scope=Scope.SHORT_TERM) is None


async def test_forget_missing_returns_false(mgr):
    """forget() returns False for nonexistent key."""
    assert await mgr.forget("nonexistent") is False


async def test_forget_all_scopes(mgr):
    """forget() without scope deletes from all scopes."""
    await mgr.remember("multi", "in working", scope=Scope.WORKING)
    await mgr.remember("multi", "in long_term", scope=Scope.LONG_TERM)

    assert await mgr.forget("multi") is True
    assert await mgr.recall_by_key("multi", scope=Scope.WORKING) is None
    assert await mgr.recall_by_key("multi", scope=Scope.LONG_TERM) is None


# ---------------------------------------------------------------------------
# 2. Scope isolation
# ---------------------------------------------------------------------------


async def test_scope_isolation(mgr):
    """Memories in different scopes with same key are independent."""
    await mgr.remember("data", "working version", scope=Scope.WORKING)
    await mgr.remember("data", "long term version", scope=Scope.LONG_TERM)

    w = await mgr.recall_by_key("data", scope=Scope.WORKING)
    lt = await mgr.recall_by_key("data", scope=Scope.LONG_TERM)

    assert w is not None
    assert lt is not None
    assert w.content == "working version"
    assert lt.content == "long term version"


async def test_recall_keyword_scope_filter(mgr):
    """recall() with scope= filters to that scope only."""
    await mgr.remember("rv_working", "R_V in working", scope=Scope.WORKING)
    await mgr.remember("rv_longterm", "R_V in long_term", scope=Scope.LONG_TERM)

    working_only = await mgr.recall("R_V", scope=Scope.WORKING, limit=10)
    assert all(m.scope == Scope.WORKING for m in working_only)
    assert len(working_only) == 1


# ---------------------------------------------------------------------------
# 3. Shared memory visibility
# ---------------------------------------------------------------------------


async def test_shared_memory_cross_agent(mgr, mgr_b):
    """Shared memories are visible to all agents."""
    await mgr.share("solved:auth_bug", "Use refresh tokens", tags="auth,security")

    # Agent B can find it
    results = await mgr_b.recall("auth_bug", scope=Scope.SHARED, limit=5)
    assert len(results) >= 1
    assert results[0].content == "Use refresh tokens"
    assert "auth" in results[0].tags


async def test_share_overwrites_by_key(mgr, mgr_b):
    """Shared memory upserts on key collision."""
    await mgr.share("strategy", "old strategy")
    await mgr_b.share("strategy", "new strategy from B")

    # Both agents see the latest version
    result_a = await mgr.recall_by_key("strategy")
    assert result_a is not None
    assert result_a.content == "new strategy from B"
    assert result_a.agent_id == "agent_b"  # Last writer wins


async def test_shared_via_remember(mgr):
    """remember() with scope=SHARED delegates to share()."""
    mem = await mgr.remember(
        "shared_insight", "patterns converge", scope=Scope.SHARED, tags="meta"
    )
    assert mem.scope == Scope.SHARED
    assert mem.tags == "meta"

    recalled = await mgr.recall_by_key("shared_insight")
    assert recalled is not None
    assert recalled.content == "patterns converge"


# ---------------------------------------------------------------------------
# 4. Consolidation
# ---------------------------------------------------------------------------


async def test_consolidate_expires_ttl(mgr):
    """consolidate() removes expired TTL memories."""
    # Insert with TTL of 1 second
    await mgr.remember("ephemeral", "gone soon", scope=Scope.SHORT_TERM, ttl=1)

    # Wait for expiry
    time.sleep(1.1)

    affected = await mgr.consolidate()
    assert affected >= 1

    recalled = await mgr.recall_by_key("ephemeral", scope=Scope.SHORT_TERM)
    assert recalled is None


async def test_consolidate_enforces_limits(mgr):
    """consolidate() evicts excess memories beyond scope limits."""
    # Insert 10 items at default limit (50)
    for i in range(10):
        await mgr.remember(f"item_{i}", f"value_{i}", scope=Scope.WORKING)

    stats_before = await mgr.get_stats()
    assert stats_before["working_count"] == 10

    # NOW lower the limit and run consolidation
    original = mgr.MAX_WORKING
    mgr.MAX_WORKING = 5

    affected = await mgr.consolidate()
    assert affected >= 5  # At least 5 should be evicted

    stats = await mgr.get_stats()
    assert stats["working_count"] <= 5

    mgr.MAX_WORKING = original


async def test_consolidate_promotes_frequent(mgr):
    """consolidate() promotes frequently-accessed short-term to long-term."""
    # Insert a short-term memory
    await mgr.remember("freq_item", "accessed a lot", scope=Scope.SHORT_TERM)

    # Simulate multiple accesses and age > 1 hour
    with mgr._lock:
        conn = mgr._get_conn()
        conn.execute(
            """UPDATE memories SET access_count=5, created_at=?
               WHERE agent_id=? AND key='freq_item'""",
            (time.time() - 7200, mgr.agent_id),  # 2 hours ago
        )
        conn.commit()

    affected = await mgr.consolidate()
    assert affected >= 1

    # Should now be in long_term
    lt = await mgr.recall_by_key("freq_item", scope=Scope.LONG_TERM)
    assert lt is not None
    assert lt.content == "accessed a lot"


# ---------------------------------------------------------------------------
# 5. Context building with token budget
# ---------------------------------------------------------------------------


async def test_get_context_basic(mgr):
    """get_context() returns formatted markdown with memories."""
    await mgr.remember("goal", "ship R_V paper", scope=Scope.WORKING)
    await mgr.remember("finding", "L27 is causal", scope=Scope.SHORT_TERM)
    await mgr.remember("principle", "telos governs action", scope=Scope.LONG_TERM)

    ctx = await mgr.get_context(budget_tokens=2000)
    assert "## Memory Context (test_agent)" in ctx
    assert "goal" in ctx
    assert "ship R_V paper" in ctx


async def test_get_context_respects_budget(mgr):
    """get_context() stops adding memories when budget is exhausted."""
    # Add many large memories
    for i in range(50):
        await mgr.remember(
            f"big_item_{i}",
            f"A very long content string that takes up space " * 10,
            scope=Scope.WORKING,
        )

    # Tiny budget
    ctx = await mgr.get_context(budget_tokens=100)
    # 100 tokens ~= 400 chars, should be much shorter than all 50 items
    assert len(ctx) < 1000


async def test_get_context_includes_shared(mgr):
    """get_context() includes shared memories."""
    await mgr.share("swarm_strategy", "divide and conquer")

    ctx = await mgr.get_context(budget_tokens=2000)
    assert "Shared" in ctx
    assert "swarm_strategy" in ctx


# ---------------------------------------------------------------------------
# 6. TTL expiry
# ---------------------------------------------------------------------------


async def test_ttl_memory_is_expired(mgr):
    """Memory with TTL is marked expired after TTL passes."""
    await mgr.remember("quick", "fast thought", scope=Scope.SHORT_TERM, ttl=1)

    # Immediately should not be expired
    mem = await mgr.recall_by_key("quick", scope=Scope.SHORT_TERM)
    assert mem is not None
    assert not mem.is_expired

    # After TTL
    time.sleep(1.1)
    mem2 = await mgr.recall_by_key("quick", scope=Scope.SHORT_TERM)
    # The record still exists in DB (consolidate hasn't run)
    # but is_expired should be True
    if mem2 is not None:
        assert mem2.is_expired


async def test_ttl_none_never_expires(mgr):
    """Memory without TTL never expires."""
    await mgr.remember("permanent", "always here", scope=Scope.LONG_TERM)
    mem = await mgr.recall_by_key("permanent")
    assert mem is not None
    assert not mem.is_expired


# ---------------------------------------------------------------------------
# 7. Keyword search
# ---------------------------------------------------------------------------


async def test_recall_keyword_match(mgr):
    """recall() finds memories by keyword in key and content."""
    await mgr.remember("rv_finding", "R_V contraction at Layer 27", scope=Scope.WORKING)
    await mgr.remember("weather", "sunny today", scope=Scope.WORKING)
    await mgr.remember("rv_method", "participation ratio method", scope=Scope.LONG_TERM)

    results = await mgr.recall("R_V contraction", limit=10)
    keys = {m.key for m in results}
    assert "rv_finding" in keys
    # "weather" should not match
    assert "weather" not in keys


async def test_recall_empty_query(mgr):
    """recall() with empty query returns nothing."""
    await mgr.remember("item", "some content", scope=Scope.WORKING)
    results = await mgr.recall("", limit=5)
    assert results == []


async def test_recall_shared_by_tags(mgr):
    """recall() on shared scope matches tags."""
    await mgr.share("pattern:caching", "Use LRU cache for hot paths", tags="performance,optimization")

    results = await mgr.recall("performance", scope=Scope.SHARED, limit=5)
    assert len(results) >= 1
    assert "caching" in results[0].key


# ---------------------------------------------------------------------------
# 8. Stats
# ---------------------------------------------------------------------------


async def test_stats(mgr):
    """get_stats() returns correct counts."""
    await mgr.remember("w1", "working 1", scope=Scope.WORKING)
    await mgr.remember("w2", "working 2", scope=Scope.WORKING)
    await mgr.remember("s1", "short 1", scope=Scope.SHORT_TERM)
    await mgr.remember("l1", "long 1", scope=Scope.LONG_TERM)
    await mgr.share("shared1", "shared content")

    stats = await mgr.get_stats()
    assert stats["agent_id"] == "test_agent"
    assert stats["working_count"] == 2
    assert stats["short_term_count"] == 1
    assert stats["long_term_count"] == 1
    assert stats["shared_count"] == 1
    assert stats["total_count"] == 5


# ---------------------------------------------------------------------------
# 9. List keys
# ---------------------------------------------------------------------------


async def test_list_keys(mgr):
    """list_keys() returns all keys, optionally filtered by scope."""
    await mgr.remember("alpha", "a", scope=Scope.WORKING)
    await mgr.remember("beta", "b", scope=Scope.LONG_TERM)
    await mgr.share("gamma", "c")

    all_keys = await mgr.list_keys()
    assert "alpha" in all_keys
    assert "beta" in all_keys
    # Shared keys are in a separate table, not returned by default
    # unless scope=SHARED
    shared_keys = await mgr.list_keys(scope=Scope.SHARED)
    assert "gamma" in shared_keys

    working_keys = await mgr.list_keys(scope=Scope.WORKING)
    assert "alpha" in working_keys
    assert "beta" not in working_keys


# ---------------------------------------------------------------------------
# 10. Agent isolation in same DB
# ---------------------------------------------------------------------------


async def test_agent_isolation(mgr, mgr_b):
    """Two agents sharing a DB have isolated private memories."""
    await mgr.remember("secret", "agent A secret", scope=Scope.WORKING)
    await mgr_b.remember("secret", "agent B secret", scope=Scope.WORKING)

    a_mem = await mgr.recall_by_key("secret", scope=Scope.WORKING)
    b_mem = await mgr_b.recall_by_key("secret", scope=Scope.WORKING)

    assert a_mem is not None
    assert b_mem is not None
    assert a_mem.content == "agent A secret"
    assert b_mem.content == "agent B secret"
    assert a_mem.agent_id == "test_agent"
    assert b_mem.agent_id == "agent_b"


# ---------------------------------------------------------------------------
# 11. Memory dataclass
# ---------------------------------------------------------------------------


def test_memory_to_dict():
    """Memory.to_dict() produces a serializable dict."""
    mem = Memory(
        id=1,
        agent_id="test",
        key="k",
        content="c",
        scope=Scope.WORKING,
        created_at=1000.0,
        accessed_at=1000.0,
    )
    d = mem.to_dict()
    assert d["scope"] == "working"
    assert d["key"] == "k"
    assert isinstance(d, dict)


def test_memory_is_expired():
    """Memory.is_expired checks TTL correctly."""
    # No TTL = never expires
    mem = Memory(created_at=time.time() - 9999)
    assert not mem.is_expired

    # TTL expired
    mem_expired = Memory(created_at=time.time() - 100, ttl=50)
    assert mem_expired.is_expired

    # TTL not expired
    mem_fresh = Memory(created_at=time.time(), ttl=9999)
    assert not mem_fresh.is_expired
