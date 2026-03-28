"""Tests for the Citation Index module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.citation_index import Citation, CitationIndex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_citations(tmp_path: Path) -> Path:
    """Return a temp JSONL path for test isolation."""
    return tmp_path / "citations" / "citations.jsonl"


@pytest.fixture
def index(tmp_citations: Path) -> CitationIndex:
    """Return a fresh CitationIndex backed by a temp file."""
    return CitationIndex(path=tmp_citations)


def _make_citation(**overrides: object) -> Citation:
    """Build a Citation with sensible defaults, overriding as needed."""
    defaults = dict(
        passage_text="Only variety can destroy variety.",
        source_work="ashby_1956_introduction_to_cybernetics",
        source_location="chapter_11:section_11/7",
        target_type="code_file",
        target_id="dharma_swarm/telos_gates.py::GateRegistry",
        relationship="grounds",
        evidence="Ashby's Law of Requisite Variety is the formal basis for the GateRegistry.",
    )
    defaults.update(overrides)
    return Citation(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests -- basic CRUD
# ---------------------------------------------------------------------------


class TestAddAndQuery:
    """Add citations and query them back."""

    async def test_add_returns_id(self, index: CitationIndex) -> None:
        c = _make_citation()
        cid = await index.add(c)
        assert cid == c.id

    async def test_count_after_add(self, index: CitationIndex) -> None:
        await index.add(_make_citation())
        await index.add(_make_citation())
        assert await index.count() == 2

    async def test_get_by_id(self, index: CitationIndex) -> None:
        c = _make_citation()
        await index.add(c)
        fetched = await index.get(c.id)
        assert fetched is not None
        assert fetched.passage_text == c.passage_text

    async def test_get_missing_returns_none(self, index: CitationIndex) -> None:
        assert await index.get("nonexistent") is None

    async def test_query_by_target(self, index: CitationIndex) -> None:
        target = "dharma_swarm/evolution.py::DarwinEngine.score_fitness"
        await index.add(_make_citation(target_id=target))
        await index.add(_make_citation(target_id="other/target.py"))
        results = await index.query_by_target(target)
        assert len(results) == 1
        assert results[0].target_id == target

    async def test_query_by_source(self, index: CitationIndex) -> None:
        await index.add(_make_citation(source_work="ashby_1956"))
        await index.add(_make_citation(source_work="conant_ashby_1970"))
        results = await index.query_by_source("conant_ashby_1970")
        assert len(results) == 1
        assert results[0].source_work == "conant_ashby_1970"

    async def test_query_by_relationship(self, index: CitationIndex) -> None:
        await index.add(_make_citation(relationship="grounds"))
        await index.add(_make_citation(relationship="violates"))
        await index.add(_make_citation(relationship="grounds"))
        results = await index.query_by_relationship("grounds")
        assert len(results) == 2

    async def test_query_by_target_type(self, index: CitationIndex) -> None:
        await index.add(_make_citation(target_type="code_function"))
        await index.add(_make_citation(target_type="principle"))
        results = await index.query_by_target_type("principle")
        assert len(results) == 1

    async def test_query_empty_for_nonexistent_target(self, index: CitationIndex) -> None:
        await index.add(_make_citation())
        results = await index.query_by_target("does/not/exist.py")
        assert results == []

    async def test_list_all(self, index: CitationIndex) -> None:
        await index.add(_make_citation())
        await index.add(_make_citation())
        await index.add(_make_citation())
        all_citations = await index.list_all()
        assert len(all_citations) == 3


# ---------------------------------------------------------------------------
# Tests -- search
# ---------------------------------------------------------------------------


class TestSearch:
    """Full-text keyword search."""

    async def test_search_passage(self, index: CitationIndex) -> None:
        await index.add(_make_citation(
            passage_text="Only variety can destroy variety",
            evidence="The law of requisite variety grounds the gate design.",
        ))
        await index.add(_make_citation(
            passage_text="Every good regulator must be a model",
            evidence="Conant-Ashby theorem demands a model of the reguland.",
        ))
        results = await index.search("variety")
        assert len(results) == 1

    async def test_search_evidence(self, index: CitationIndex) -> None:
        await index.add(_make_citation(evidence="The vetoer blocks unfit equilibria"))
        results = await index.search("vetoer")
        assert len(results) == 1

    async def test_search_target_id(self, index: CitationIndex) -> None:
        await index.add(_make_citation(target_id="dharma_swarm/evolution.py"))
        results = await index.search("evolution")
        assert len(results) == 1

    async def test_search_case_insensitive(self, index: CitationIndex) -> None:
        await index.add(_make_citation(passage_text="ONLY VARIETY CAN DESTROY VARIETY"))
        results = await index.search("variety")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Tests -- access tracking
# ---------------------------------------------------------------------------


class TestAccessTracking:
    """Record access increments count and updates timestamp."""

    async def test_record_access_increments(self, index: CitationIndex) -> None:
        c = _make_citation()
        await index.add(c)
        assert c.access_count == 0
        await index.record_access(c.id)
        fetched = await index.get(c.id)
        assert fetched is not None
        assert fetched.access_count == 1
        assert fetched.last_accessed is not None

    async def test_record_access_twice(self, index: CitationIndex) -> None:
        c = _make_citation()
        await index.add(c)
        await index.record_access(c.id)
        await index.record_access(c.id)
        fetched = await index.get(c.id)
        assert fetched is not None
        assert fetched.access_count == 2

    async def test_record_access_missing_raises(self, index: CitationIndex) -> None:
        with pytest.raises(KeyError):
            await index.record_access("nonexistent")


# ---------------------------------------------------------------------------
# Tests -- verification
# ---------------------------------------------------------------------------


class TestVerification:
    """Run verification_test expressions."""

    async def test_verify_passing(self, index: CitationIndex) -> None:
        c = _make_citation(verification_test="1 + 1 == 2")
        await index.add(c)
        results = await index.verify_all()
        assert results[c.id] is True
        fetched = await index.get(c.id)
        assert fetched is not None
        assert fetched.verified is True

    async def test_verify_failing(self, index: CitationIndex) -> None:
        c = _make_citation(verification_test="1 + 1 == 3")
        await index.add(c)
        results = await index.verify_all()
        assert results[c.id] is False

    async def test_verify_exception_counts_as_fail(self, index: CitationIndex) -> None:
        c = _make_citation(verification_test="undefined_name")
        await index.add(c)
        results = await index.verify_all()
        assert results[c.id] is False

    async def test_verify_skips_citations_without_test(self, index: CitationIndex) -> None:
        c = _make_citation(verification_test=None)
        await index.add(c)
        results = await index.verify_all()
        assert c.id not in results

    async def test_verify_path_check(self, index: CitationIndex) -> None:
        c = _make_citation(
            verification_test="Path('/Users/dhyana/dharma_swarm/dharma_swarm/telos_gates.py').exists()"
        )
        await index.add(c)
        results = await index.verify_all()
        # This test only passes if the file actually exists on the machine
        assert c.id in results

    async def test_unverified_returns_failing(self, index: CitationIndex) -> None:
        c1 = _make_citation(verification_test="True")
        c2 = _make_citation(verification_test="False")
        await index.add(c1)
        await index.add(c2)
        await index.verify_all()
        unverified = await index.unverified()
        assert len(unverified) == 1
        assert unverified[0].id == c2.id


# ---------------------------------------------------------------------------
# Tests -- JSONL persistence survives reload
# ---------------------------------------------------------------------------


class TestPersistence:
    """Data survives creating a new CitationIndex from the same file."""

    async def test_reload_preserves_citations(self, tmp_citations: Path) -> None:
        idx1 = CitationIndex(path=tmp_citations)
        c = _make_citation(passage_text="Persistence test")
        await idx1.add(c)

        # Create a brand new index on the same path
        idx2 = CitationIndex(path=tmp_citations)
        await idx2.load()
        assert await idx2.count() == 1
        fetched = await idx2.get(c.id)
        assert fetched is not None
        assert fetched.passage_text == "Persistence test"

    async def test_reload_preserves_access_count(self, tmp_citations: Path) -> None:
        idx1 = CitationIndex(path=tmp_citations)
        c = _make_citation()
        await idx1.add(c)
        await idx1.record_access(c.id)
        await idx1.record_access(c.id)

        idx2 = CitationIndex(path=tmp_citations)
        await idx2.load()
        fetched = await idx2.get(c.id)
        assert fetched is not None
        assert fetched.access_count == 2

    async def test_jsonl_is_valid_ndjson(self, tmp_citations: Path) -> None:
        idx = CitationIndex(path=tmp_citations)
        await idx.add(_make_citation())
        await idx.add(_make_citation())

        # Each line must parse as valid JSON
        lines = [ln for ln in tmp_citations.read_text().strip().splitlines() if ln.strip()]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "passage_text" in data
            assert "target_id" in data


# ---------------------------------------------------------------------------
# Tests -- remove
# ---------------------------------------------------------------------------


class TestRemove:
    """Remove citations."""

    async def test_remove_decrements_count(self, index: CitationIndex) -> None:
        c = _make_citation()
        await index.add(c)
        assert await index.count() == 1
        await index.remove(c.id)
        assert await index.count() == 0

    async def test_remove_missing_raises(self, index: CitationIndex) -> None:
        with pytest.raises(KeyError):
            await index.remove("nonexistent")


# ---------------------------------------------------------------------------
# Tests -- coverage report
# ---------------------------------------------------------------------------


class TestCoverageReport:
    """Coverage report groups by relationship."""

    async def test_coverage_report(self, index: CitationIndex) -> None:
        await index.add(_make_citation(relationship="grounds"))
        await index.add(_make_citation(relationship="grounds"))
        await index.add(_make_citation(relationship="violates"))
        report = await index.coverage_report()
        assert report["grounds"] == 2
        assert report["violates"] == 1


# ---------------------------------------------------------------------------
# Tests -- density (sync)
# ---------------------------------------------------------------------------


class TestDensity:
    """Synchronous density check."""

    def test_density_zero_when_empty(self, index: CitationIndex) -> None:
        assert index.density() == 0

    async def test_density_after_writes(self, index: CitationIndex) -> None:
        await index.add(_make_citation())
        await index.add(_make_citation())
        assert index.density() == 2
