"""Tests for telos_tracker: task completion → TelosGraph progress mapping.

Verifies: keyword matching, progress clamping, unknown tasks, multiple
keyword accumulation, and graceful failure on missing state directories.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.telos_tracker import TASK_TELOS_MAP, record_task_completion

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_objectives(telos_dir: Path) -> list[dict]:
    """Write a minimal objectives.jsonl that covers the TASK_TELOS_MAP fragments."""
    from dharma_swarm.models import _new_id

    objectives = [
        {
            "id": _new_id(),
            "name": "VIVEKA R_V Consciousness Detection API",
            "description": "R_V metric API",
            "perspective": "stakeholder",
            "status": "active",
            "progress": 0.1,
            "priority": 9,
        },
        {
            "id": _new_id(),
            "name": "VIVEKA Cross-Architecture Validation",
            "description": "Cross-arch R_V validation",
            "perspective": "process",
            "status": "active",
            "progress": 0.15,
            "priority": 9,
        },
        {
            "id": _new_id(),
            "name": "Surpass Sakana DGM on multi-domain self-improvement",
            "description": "DGM evolution track",
            "perspective": "process",
            "status": "active",
            "progress": 0.15,
            "priority": 9,
        },
        {
            "id": _new_id(),
            "name": "Differentiate from Isara via alignment-first swarm coordination",
            "description": "Competitive moat",
            "perspective": "stakeholder",
            "status": "active",
            "progress": 0.1,
            "priority": 9,
        },
        {
            "id": _new_id(),
            "name": "Publish dharmic alignment architecture as research contribution",
            "description": "Alignment paper",
            "perspective": "stakeholder",
            "status": "active",
            "progress": 0.05,
            "priority": 8,
        },
        {
            "id": _new_id(),
            "name": "Wire Ginko as metabolic proof-of-concept",
            "description": "Ginko trading bridge",
            "perspective": "process",
            "status": "active",
            "progress": 0.05,
            "priority": 10,
        },
        {
            "id": _new_id(),
            "name": "Achieve 24-hour autonomous operation with measurable improvement",
            "description": "24-hour run target",
            "perspective": "process",
            "status": "active",
            "progress": 0.2,
            "priority": 9,
        },
        {
            "id": _new_id(),
            "name": "Jagat Kalyan -- Universal Welfare",
            "description": "Universal welfare",
            "perspective": "purpose",
            "status": "active",
            "progress": 0.0,
            "priority": 10,
        },
        {
            "id": _new_id(),
            "name": "KALYAN 50-Hectare Mangrove Pilot",
            "description": "Mangrove ecology project",
            "perspective": "process",
            "status": "active",
            "progress": 0.0,
            "priority": 8,
        },
    ]

    telos_dir.mkdir(parents=True, exist_ok=True)
    with open(telos_dir / "objectives.jsonl", "w") as f:
        for obj in objectives:
            f.write(json.dumps(obj) + "\n")

    return objectives


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyword_matching_rv_metric():
    """Title with 'r_v metric' should increment VIVEKA R_V objective."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        objs = _seed_objectives(state_dir / "telos")

        # Find the VIVEKA R_V objective
        rv_obj = next(o for o in objs if "VIVEKA R_V" in o["name"])
        original_progress = rv_obj["progress"]

        await record_task_completion(
            task_title="Compute r_v metric for Mistral-7B",
            task_description="Calculate R_V scores across layers",
            result="R_V = 0.82 at layer 16",
            state_dir=state_dir,
        )

        # Reload and check progress increased
        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=state_dir / "telos")
        await telos.load()

        updated = next(
            o for o in telos.list_objectives() if "VIVEKA R_V" in o.name
        )
        # "r_v metric" matches both ("r_v metric", 0.05) and ("r_v", 0.03)
        assert updated.progress > original_progress
        # Should have incremented by at least 0.05 (the "r_v metric" match)
        assert updated.progress >= original_progress + 0.05


@pytest.mark.asyncio
async def test_progress_clamped_at_one():
    """Progress must not exceed 1.0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        telos_dir = state_dir / "telos"
        telos_dir.mkdir(parents=True, exist_ok=True)

        from dharma_swarm.models import _new_id

        # Seed an objective with progress already at 0.98
        obj = {
            "id": _new_id(),
            "name": "Wire Ginko as metabolic proof-of-concept",
            "description": "Ginko trading",
            "perspective": "process",
            "status": "active",
            "progress": 0.98,
            "priority": 10,
        }
        with open(telos_dir / "objectives.jsonl", "w") as f:
            f.write(json.dumps(obj) + "\n")

        await record_task_completion(
            task_title="ginko trading market regime signal analysis",
            task_description="Full ginko integration",
            result="Done",
            state_dir=state_dir,
        )

        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=telos_dir)
        await telos.load()

        updated = telos.list_objectives()[0]
        assert updated.progress <= 1.0


@pytest.mark.asyncio
async def test_unknown_task_no_crash():
    """An unrecognized task should not crash or change any progress."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        objs = _seed_objectives(state_dir / "telos")

        original_progresses = {o["name"]: o["progress"] for o in objs}

        await record_task_completion(
            task_title="Completely unrelated thing about cooking pasta",
            task_description="Boil water, add salt, cook for 8 minutes",
            result="Pasta is ready",
            state_dir=state_dir,
        )

        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=state_dir / "telos")
        await telos.load()

        for obj in telos.list_objectives():
            assert obj.progress == original_progresses[obj.name], (
                f"{obj.name} progress changed unexpectedly"
            )


@pytest.mark.asyncio
async def test_multiple_keywords_accumulate():
    """Multiple matching keywords for the same objective should accumulate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        objs = _seed_objectives(state_dir / "telos")

        ginko_obj = next(o for o in objs if "Wire Ginko" in o["name"])
        original_progress = ginko_obj["progress"]

        # This title matches: "ginko" (0.05), "trading" (0.03), "market" (0.02), "regime" (0.02)
        # Total = 0.12
        await record_task_completion(
            task_title="ginko trading market regime analysis",
            task_description="",
            result="Done",
            state_dir=state_dir,
        )

        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=state_dir / "telos")
        await telos.load()

        updated = next(
            o for o in telos.list_objectives() if "Wire Ginko" in o.name
        )
        expected_min = original_progress + 0.12
        assert updated.progress >= expected_min - 0.001, (
            f"Expected progress >= {expected_min}, got {updated.progress}"
        )


@pytest.mark.asyncio
async def test_nonexistent_state_dir_graceful():
    """A state_dir that doesn't exist should fail gracefully, no crash."""
    # This path does not exist and cannot be created (nested under a non-existent parent)
    state_dir = Path("/tmp/nonexistent_dharma_test_dir_9999/deep/nested")

    # Should not raise
    await record_task_completion(
        task_title="research r_v metric",
        task_description="something",
        result="done",
        state_dir=state_dir,
    )
    # If we get here without an exception, the test passes


@pytest.mark.asyncio
async def test_none_title_and_description():
    """Handles None values for title/description gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        _seed_objectives(state_dir / "telos")

        # Should not raise even with empty/None-ish values
        await record_task_completion(
            task_title="",
            task_description="",
            result=None,
            state_dir=state_dir,
        )


@pytest.mark.asyncio
async def test_cross_track_increments():
    """A task matching multiple tracks updates multiple objectives."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        objs = _seed_objectives(state_dir / "telos")

        original_isara = next(o for o in objs if "Isara" in o["name"])["progress"]
        original_alignment = next(o for o in objs if "dharmic alignment" in o["name"])["progress"]

        # "isara" → Differentiate from Isara, "alignment" → Publish dharmic alignment
        await record_task_completion(
            task_title="competitive analysis: isara alignment architecture gap",
            task_description="Compare alignment approaches",
            result="Analysis complete",
            state_dir=state_dir,
        )

        from dharma_swarm.telos_graph import TelosGraph

        telos = TelosGraph(telos_dir=state_dir / "telos")
        await telos.load()

        updated_isara = next(
            o for o in telos.list_objectives() if "Isara" in o.name
        )
        updated_alignment = next(
            o for o in telos.list_objectives() if "dharmic alignment" in o.name
        )

        assert updated_isara.progress > original_isara
        assert updated_alignment.progress > original_alignment
