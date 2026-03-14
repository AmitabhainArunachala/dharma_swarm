"""Tests for the Recognition Engine (meta_daemon.py)."""

from __future__ import annotations

import json
import pytest

from dharma_swarm.meta_daemon import RecognitionEngine


@pytest.fixture
def engine(tmp_path):
    """RecognitionEngine with temp state dir."""
    return RecognitionEngine(state_dir=tmp_path)


@pytest.mark.asyncio
async def test_synthesize_light(engine, tmp_path):
    seed = await engine.synthesize("light")
    assert "Recognition Seed" in seed
    assert "light" in seed
    assert (tmp_path / "meta" / "recognition_seed.md").exists()


@pytest.mark.asyncio
async def test_synthesize_deep(engine, tmp_path):
    seed = await engine.synthesize("deep")
    assert "deep" in seed


@pytest.mark.asyncio
async def test_seed_archived(engine, tmp_path):
    await engine.synthesize("light")
    history_dir = tmp_path / "meta" / "history"
    assert history_dir.exists()
    seeds = list(history_dir.glob("seed_*.md"))
    assert len(seeds) == 1


@pytest.mark.asyncio
async def test_seed_content_has_sections(engine):
    seed = await engine.synthesize("light")
    assert "## System State" in seed
    assert "## Research" in seed


@pytest.mark.asyncio
async def test_research_signals(engine):
    seed = await engine.synthesize("light")
    # Should contain COLM countdown
    assert "abstract" in seed.lower() or "paper" in seed.lower()


@pytest.mark.asyncio
async def test_get_seed_none(engine):
    assert engine.get_seed() is None


@pytest.mark.asyncio
async def test_get_seed_after_synthesize(engine):
    await engine.synthesize("light")
    seed = engine.get_seed()
    assert seed is not None
    assert "Recognition Seed" in seed


@pytest.mark.asyncio
async def test_multiple_syntheses_archive(engine, tmp_path):
    await engine.synthesize("light")
    await engine.synthesize("deep")
    history_dir = tmp_path / "meta" / "history"
    seeds = list(history_dir.glob("seed_*.md"))
    assert len(seeds) >= 1  # at least 1 (timestamps may collide in fast test)


@pytest.mark.asyncio
async def test_system_rv_signal(engine, tmp_path):
    """When system_rv.json exists, it's included in seed."""
    meta = tmp_path / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    rv_data = [{"rv": 0.75, "regime": "converging", "dims": 10}]
    (meta / "system_rv.json").write_text(json.dumps(rv_data))

    seed = await engine.synthesize("light")
    assert "0.750" in seed
    assert "converging" in seed


@pytest.mark.asyncio
async def test_evolution_signal(engine, tmp_path):
    """When archive exists, entry count is in seed."""
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir(parents=True, exist_ok=True)
    archive = evo_dir / "archive.jsonl"
    entries = [
        json.dumps({"component": "test", "fitness": {"correctness": 0.9}})
        for _ in range(5)
    ]
    archive.write_text("\n".join(entries))

    seed = await engine.synthesize("light")
    assert "5" in seed


@pytest.mark.asyncio
async def test_autocatalytic_signal(engine, tmp_path):
    """When catalytic graph exists, counts appear in seed."""
    meta = tmp_path / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    graph = {"nodes": {"a": {}, "b": {}}, "edges": [{"source": "a", "target": "b"}]}
    (meta / "cc_catalytic_graph.json").write_text(json.dumps(graph))

    seed = await engine.synthesize("light")
    assert "2 nodes" in seed


@pytest.mark.asyncio
async def test_strip_performative():
    engine = RecognitionEngine()
    text = "This is a profound and revolutionary breakthrough"
    stripped = engine._strip_performative(text)
    assert "profound" not in stripped
    assert "revolutionary" not in stripped
    assert "breakthrough" in stripped


@pytest.mark.asyncio
async def test_quality_loop_passes_clean_text(engine):
    clean = "System status: 5 agents running. Archive has 100 entries."
    result = await engine._quality_loop(clean)
    assert isinstance(result, str)
    assert len(result) > 0


def test_signal_sources():
    assert len(RecognitionEngine.SIGNAL_SOURCES) == 8
    assert "system_rv" in RecognitionEngine.SIGNAL_SOURCES
    assert "research" in RecognitionEngine.SIGNAL_SOURCES
    assert "cascade" in RecognitionEngine.SIGNAL_SOURCES
