"""Tests for the research scout module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.research_scout import (
    Finding,
    ResearchScout,
    cross_reference_corpus,
    detect_pillars,
    detect_telos_impact,
)


def test_detect_pillars_single():
    pillars = detect_pillars("Active inference and free energy principle in agent design")
    assert "PILLAR_10_FRISTON" in pillars


def test_detect_pillars_multiple():
    pillars = detect_pillars("Strange loops in autopoiesis systems with active inference")
    assert "PILLAR_04_HOFSTADTER" in pillars
    assert "PILLAR_07_VARELA" in pillars
    assert "PILLAR_10_FRISTON" in pillars


def test_detect_pillars_none():
    pillars = detect_pillars("How to make a sandwich with peanut butter")
    assert pillars == []


def test_detect_telos_impact():
    impact = detect_telos_impact("This improves truth verification and accuracy")
    assert "T1" in impact

    impact = detect_telos_impact("Reduces karma binding and supports dissolution")
    assert "T7" in impact


def test_detect_telos_impact_none():
    impact = detect_telos_impact("Generic text about nothing specific")
    assert impact == ""


def test_cross_reference_novel():
    is_novel, explanation = cross_reference_corpus(
        "Brand new finding about quantum cognition",
        existing_claims=["The system uses SQLite for persistence"],
        existing_foundations=["Viable System Model organizes governance"],
    )
    assert is_novel is True
    assert "Novel" in explanation


def test_cross_reference_redundant():
    is_novel, explanation = cross_reference_corpus(
        "The system uses SQLite database for data persistence and storage",
        existing_claims=["The system uses SQLite for persistence and data storage"],
        existing_foundations=[],
    )
    assert is_novel is False
    assert "Redundant" in explanation


@pytest.fixture
def scout_dir(tmp_path: Path) -> Path:
    return tmp_path / "scout"


@pytest.fixture
def scout(scout_dir: Path) -> ResearchScout:
    return ResearchScout(base_dir=scout_dir)


@pytest.mark.asyncio
async def test_init_creates_files(scout: ResearchScout, scout_dir: Path):
    await scout.init()
    assert (scout_dir / "research_scout_findings.md").exists()
    assert (scout_dir / "research_scout_findings.jsonl").exists()


@pytest.mark.asyncio
async def test_evaluate_finding_accepted(scout: ResearchScout):
    await scout.init()
    finding = await scout.evaluate_finding(
        title="New autopoiesis framework for agent coordination",
        summary="A novel approach using enactive cognition principles for multi-agent systems",
        source_url="https://example.com/paper",
        source_type="paper",
    )
    assert finding.is_novel is True
    assert "PILLAR_07_VARELA" in finding.pillars


@pytest.mark.asyncio
async def test_evaluate_finding_rejected_no_pillar(scout: ResearchScout):
    await scout.init()
    finding = await scout.evaluate_finding(
        title="Best pizza recipes in New York",
        summary="A comprehensive guide to pizza making",
    )
    assert finding.is_novel is False
    assert "No pillar grounding" in finding.cross_ref_result


@pytest.mark.asyncio
async def test_get_findings(scout: ResearchScout):
    await scout.init()
    await scout.evaluate_finding(
        title="Strange loop self-reference in LLM agents",
        summary="How self-referential patterns emerge in large language model agents",
    )
    findings = await scout.get_findings()
    assert len(findings) == 1
    assert "Strange loop" in findings[0].title


@pytest.mark.asyncio
async def test_get_stats(scout: ResearchScout):
    await scout.init()
    await scout.evaluate_finding(
        title="Active inference for agent sandboxing",
        summary="Using free energy principle to design self-evidencing security boundaries",
    )
    stats = await scout.get_stats()
    assert stats["total"] == 1
    assert "PILLAR_10_FRISTON" in stats["by_pillar"]
