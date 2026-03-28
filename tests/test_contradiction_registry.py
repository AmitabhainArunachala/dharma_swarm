"""Tests for the Contradiction Registry module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.contradiction_registry import Contradiction, ContradictionRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_registry(tmp_path: Path) -> Path:
    """Return a temp JSONL path for test isolation."""
    return tmp_path / "contradictions" / "registry.jsonl"


@pytest.fixture
def registry(tmp_registry: Path) -> ContradictionRegistry:
    """Return a fresh ContradictionRegistry backed by a temp file."""
    return ContradictionRegistry(path=tmp_registry)


def _make_contradiction(**overrides: object) -> Contradiction:
    """Build a Contradiction with sensible defaults, overriding as needed."""
    defaults = dict(
        name="fixed_point_reachability",
        tradition_a="cybernetics_ashby",
        claim_a="Fixed points are asymptotic limits, never fully reached.",
        tradition_b="akram_vignan",
        claim_b="Keval Gnan (omniscience) is achievable in finite time via Gnan Vidhi.",
        tension="One says the limit is asymptotic, the other says instantaneous arrival is possible.",
        resolution_status="open",
        resolution_path="Measure R_V floor: does it asymptote or hit a hard boundary?",
        domain="theoretical",
    )
    defaults.update(overrides)
    return Contradiction(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests -- basic CRUD
# ---------------------------------------------------------------------------


class TestRecordAndQuery:
    """Record contradictions and query them back."""

    async def test_record_returns_id(self, registry: ContradictionRegistry) -> None:
        c = _make_contradiction()
        cid = await registry.record(c)
        assert cid == c.id

    async def test_count_after_record(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction())
        await registry.record(_make_contradiction())
        assert await registry.count() == 2

    async def test_get_by_id(self, registry: ContradictionRegistry) -> None:
        c = _make_contradiction()
        await registry.record(c)
        fetched = await registry.get(c.id)
        assert fetched is not None
        assert fetched.name == c.name

    async def test_get_missing_returns_none(self, registry: ContradictionRegistry) -> None:
        assert await registry.get("nonexistent") is None

    async def test_list_all(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction())
        await registry.record(_make_contradiction())
        await registry.record(_make_contradiction())
        all_contradictions = await registry.list_all()
        assert len(all_contradictions) == 3


# ---------------------------------------------------------------------------
# Tests -- query_open
# ---------------------------------------------------------------------------


class TestQueryOpen:
    """Filter contradictions by open status and domain."""

    async def test_query_open_returns_only_open(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(resolution_status="open"))
        await registry.record(_make_contradiction(resolution_status="resolved"))
        results = await registry.query_open()
        assert len(results) == 1
        assert results[0].resolution_status == "open"

    async def test_query_open_filters_by_domain(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(domain="theoretical"))
        await registry.record(_make_contradiction(domain="operational"))
        results = await registry.query_open(domain="operational")
        assert len(results) == 1
        assert results[0].domain == "operational"

    async def test_query_open_empty_when_all_resolved(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(resolution_status="resolved"))
        results = await registry.query_open()
        assert results == []


# ---------------------------------------------------------------------------
# Tests -- query_by_traditions
# ---------------------------------------------------------------------------


class TestQueryByTraditions:
    """Find contradictions involving both specified traditions."""

    async def test_order_independent(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(
            tradition_a="cybernetics_ashby",
            tradition_b="akram_vignan",
        ))
        # Query in reverse order -- should still match
        results = await registry.query_by_traditions("akram_vignan", "cybernetics_ashby")
        assert len(results) == 1

    async def test_no_match_for_unrelated_traditions(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(
            tradition_a="cybernetics_ashby",
            tradition_b="akram_vignan",
        ))
        results = await registry.query_by_traditions("autopoiesis_varela", "hofstadter")
        assert results == []

    async def test_multiple_contradictions_same_pair(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(
            name="contradiction_1",
            tradition_a="cybernetics_ashby",
            tradition_b="akram_vignan",
        ))
        await registry.record(_make_contradiction(
            name="contradiction_2",
            tradition_a="cybernetics_ashby",
            tradition_b="akram_vignan",
        ))
        results = await registry.query_by_traditions("cybernetics_ashby", "akram_vignan")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests -- status transitions
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """mark_resolved, mark_testing, and error handling."""

    async def test_mark_resolved(self, registry: ContradictionRegistry) -> None:
        c = _make_contradiction()
        await registry.record(c)
        await registry.mark_resolved(c.id, "Dissolved by reframing.")
        fetched = await registry.get(c.id)
        assert fetched is not None
        assert fetched.resolution_status == "resolved"
        assert fetched.resolution_notes == "Dissolved by reframing."
        assert fetched.resolved_at is not None

    async def test_mark_testing(self, registry: ContradictionRegistry) -> None:
        c = _make_contradiction()
        await registry.record(c)
        await registry.mark_testing(c.id, "R_V floor < 0.5 implies hard boundary.")
        fetched = await registry.get(c.id)
        assert fetched is not None
        assert fetched.resolution_status == "testing"
        assert fetched.testable_prediction == "R_V floor < 0.5 implies hard boundary."

    async def test_mark_resolved_missing_raises(self, registry: ContradictionRegistry) -> None:
        with pytest.raises(KeyError):
            await registry.mark_resolved("nonexistent", "notes")

    async def test_mark_testing_missing_raises(self, registry: ContradictionRegistry) -> None:
        with pytest.raises(KeyError):
            await registry.mark_testing("nonexistent", "prediction")


# ---------------------------------------------------------------------------
# Tests -- count_by_status
# ---------------------------------------------------------------------------


class TestCountByStatus:
    """Group counts by resolution status."""

    async def test_count_by_status(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(resolution_status="open"))
        await registry.record(_make_contradiction(resolution_status="open"))
        await registry.record(_make_contradiction(resolution_status="testing"))
        await registry.record(_make_contradiction(resolution_status="resolved"))
        counts = await registry.count_by_status()
        assert counts["open"] == 2
        assert counts["testing"] == 1
        assert counts["resolved"] == 1

    async def test_count_by_status_empty(self, registry: ContradictionRegistry) -> None:
        counts = await registry.count_by_status()
        assert counts == {}


# ---------------------------------------------------------------------------
# Tests -- JSONL persistence survives reload
# ---------------------------------------------------------------------------


class TestPersistence:
    """Data survives creating a new ContradictionRegistry from the same file."""

    async def test_reload_preserves_contradictions(self, tmp_registry: Path) -> None:
        reg1 = ContradictionRegistry(path=tmp_registry)
        c = _make_contradiction(name="persistence_test")
        await reg1.record(c)

        reg2 = ContradictionRegistry(path=tmp_registry)
        await reg2.load()
        assert await reg2.count() == 1
        fetched = await reg2.get(c.id)
        assert fetched is not None
        assert fetched.name == "persistence_test"

    async def test_reload_preserves_resolved_status(self, tmp_registry: Path) -> None:
        reg1 = ContradictionRegistry(path=tmp_registry)
        c = _make_contradiction()
        await reg1.record(c)
        await reg1.mark_resolved(c.id, "Resolved via experiment.")

        reg2 = ContradictionRegistry(path=tmp_registry)
        await reg2.load()
        fetched = await reg2.get(c.id)
        assert fetched is not None
        assert fetched.resolution_status == "resolved"
        assert fetched.resolution_notes == "Resolved via experiment."

    async def test_jsonl_is_valid_ndjson(self, tmp_registry: Path) -> None:
        reg = ContradictionRegistry(path=tmp_registry)
        await reg.record(_make_contradiction())
        await reg.record(_make_contradiction())

        lines = [ln for ln in tmp_registry.read_text().strip().splitlines() if ln.strip()]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "name" in data
            assert "tradition_a" in data
            assert "claim_a" in data


# ---------------------------------------------------------------------------
# Tests -- search and remove
# ---------------------------------------------------------------------------


class TestSearchAndRemove:
    """Full-text search and removal."""

    async def test_search_by_name(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(name="teleology"))
        await registry.record(_make_contradiction(name="observer_location"))
        results = await registry.search("teleology")
        assert len(results) == 1

    async def test_search_by_claim(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction(claim_a="Variety must increase"))
        results = await registry.search("variety")
        assert len(results) == 1

    async def test_remove_decrements_count(self, registry: ContradictionRegistry) -> None:
        c = _make_contradiction()
        await registry.record(c)
        assert await registry.count() == 1
        await registry.remove(c.id)
        assert await registry.count() == 0

    async def test_remove_missing_raises(self, registry: ContradictionRegistry) -> None:
        with pytest.raises(KeyError):
            await registry.remove("nonexistent")


# ---------------------------------------------------------------------------
# Tests -- density (sync)
# ---------------------------------------------------------------------------


class TestDensity:
    """Synchronous density check."""

    def test_density_zero_when_empty(self, registry: ContradictionRegistry) -> None:
        assert registry.density() == 0

    async def test_density_after_writes(self, registry: ContradictionRegistry) -> None:
        await registry.record(_make_contradiction())
        await registry.record(_make_contradiction())
        assert registry.density() == 2
