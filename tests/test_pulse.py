"""Tests for dharma_swarm.pulse living-layer heartbeat wiring."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import dharma_swarm.pulse as pulse


class _FakeStore:
    def __init__(self, density: int) -> None:
        self._density = density
        self.left_marks = []

    def density(self) -> int:
        return self._density

    async def leave_mark(self, mark):
        self.left_marks.append(mark)
        return "mark-id"


@pytest.fixture
def living_paths(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir(parents=True, exist_ok=True)
    living = state_dir / "living_state.json"
    monkeypatch.setattr(pulse, "STATE_DIR", state_dir)
    monkeypatch.setattr(pulse, "_LIVING_STATE_PATH", living)
    return living


def test_load_living_state_defaults_when_missing(living_paths: Path):
    state = pulse._load_living_state()
    assert state["last_dream_density"] == 0
    assert state["last_shakti_at"] == 0


def test_load_living_state_defaults_when_invalid_json(living_paths: Path):
    living_paths.write_text("not-json")
    state = pulse._load_living_state()
    assert state["last_dream_density"] == 0
    assert state["last_shakti_at"] == 0


def test_save_and_load_living_state_roundtrip(living_paths: Path):
    pulse._save_living_state({"last_dream_density": 72, "last_shakti_at": 123})
    state = pulse._load_living_state()
    assert state["last_dream_density"] == 72
    assert state["last_shakti_at"] == 123


@pytest.mark.asyncio
async def test_run_living_layers_triggers_dream_and_shakti(monkeypatch, living_paths: Path):
    store = _FakeStore(density=60)
    monkeypatch.setattr(pulse, "StigmergyStore", lambda: store)

    calls = {"dream": 0, "perceive": 0}

    class _FakeSubconscious:
        def __init__(self, stigmergy):
            assert stigmergy is store

        async def dream(self):
            calls["dream"] += 1
            return [SimpleNamespace(), SimpleNamespace()]

    class _FakeShakti:
        def __init__(self, stigmergy):
            assert stigmergy is store

        async def perceive(self, current_context: str = "", agent_role: str = "general"):
            calls["perceive"] += 1
            return [
                SimpleNamespace(
                    connection="dharma_swarm/pulse.py",
                    proposal=None,
                    observation="high salience signal",
                    salience=0.9,
                    impact_level="module",
                    energy=SimpleNamespace(value="maheshwari"),
                )
            ]

    monkeypatch.setattr(pulse, "SubconsciousStream", _FakeSubconscious)
    monkeypatch.setattr(pulse, "ShaktiLoop", _FakeShakti)

    summary = await pulse._run_living_layers("mechanistic", "pulse result")

    assert summary["dream_triggered"] is True
    assert summary["dream_associations"] == 2
    assert summary["shakti_perceptions"] == 1
    assert summary["shakti_escalations"] == 1
    assert calls["dream"] == 1
    assert calls["perceive"] == 1
    assert len(store.left_marks) == 1

    persisted = json.loads(living_paths.read_text())
    assert persisted["last_dream_density"] == 60
    assert persisted["last_shakti_at"] > 0


@pytest.mark.asyncio
async def test_run_living_layers_hysteresis_blocks_repeat_dream(monkeypatch, living_paths: Path):
    living_paths.write_text(json.dumps({"last_dream_density": 60, "last_shakti_at": 0}))

    store = _FakeStore(density=65)
    monkeypatch.setattr(pulse, "StigmergyStore", lambda: store)

    calls = {"dream": 0}

    class _FakeSubconscious:
        def __init__(self, stigmergy):
            pass

        async def dream(self):
            calls["dream"] += 1
            return [SimpleNamespace()]

    class _FakeShakti:
        def __init__(self, stigmergy):
            pass

        async def perceive(self, current_context: str = "", agent_role: str = "general"):
            return []

    monkeypatch.setattr(pulse, "SubconsciousStream", _FakeSubconscious)
    monkeypatch.setattr(pulse, "ShaktiLoop", _FakeShakti)

    monkeypatch.setenv("DGC_DREAM_HYSTERESIS", "10")
    summary = await pulse._run_living_layers("mechanistic", "pulse result")

    assert summary["dream_triggered"] is False
    assert summary["dream_associations"] == 0
    assert calls["dream"] == 0


@pytest.mark.asyncio
async def test_run_living_layers_respects_shakti_interval(monkeypatch, living_paths: Path):
    now = int(time.time())
    living_paths.write_text(json.dumps({"last_dream_density": 0, "last_shakti_at": now}))

    store = _FakeStore(density=10)
    monkeypatch.setattr(pulse, "StigmergyStore", lambda: store)

    class _FakeSubconscious:
        def __init__(self, stigmergy):
            pass

        async def dream(self):
            return [SimpleNamespace()]

    calls = {"perceive": 0}

    class _FakeShakti:
        def __init__(self, stigmergy):
            pass

        async def perceive(self, current_context: str = "", agent_role: str = "general"):
            calls["perceive"] += 1
            return []

    monkeypatch.setattr(pulse, "SubconsciousStream", _FakeSubconscious)
    monkeypatch.setattr(pulse, "ShaktiLoop", _FakeShakti)
    monkeypatch.setenv("DGC_SHAKTI_INTERVAL_SEC", "3600")

    summary = await pulse._run_living_layers("alignment", "pulse result")

    assert summary["dream_triggered"] is False
    assert summary["shakti_perceptions"] == 0
    assert calls["perceive"] == 0


@pytest.mark.asyncio
async def test_run_living_layers_handles_exceptions(monkeypatch, living_paths: Path):
    class _BrokenStore:
        def density(self) -> int:
            raise RuntimeError("boom")

    monkeypatch.setattr(pulse, "StigmergyStore", lambda: _BrokenStore())

    summary = await pulse._run_living_layers("alignment", "pulse result")
    assert summary["dream_triggered"] is False
    assert summary["shakti_perceptions"] == 0
