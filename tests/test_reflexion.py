"""Tests for dharma_swarm.reflexion -- verbal RL self-correction loop."""

from __future__ import annotations

import json

import pytest

from dharma_swarm.reflexion import (
    ReflexionEntry,
    ReflexionMemory,
    generate_reflection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(response: str = "mock reflection text"):
    """Return an async provider_fn that returns *response*."""
    call_log: list[tuple[str, str]] = []

    async def provider_fn(system_prompt: str, user_prompt: str) -> str:
        call_log.append((system_prompt, user_prompt))
        return response

    provider_fn.call_log = call_log  # type: ignore[attr-defined]
    return provider_fn


# ---------------------------------------------------------------------------
# ReflexionEntry
# ---------------------------------------------------------------------------


def test_entry_creation():
    entry = ReflexionEntry(
        task_id="task-1",
        attempt_number=1,
        outcome="fail",
        error_summary="IndexError",
        reflection_text="Check bounds before access",
    )
    assert entry.task_id == "task-1"
    assert entry.attempt_number == 1
    assert entry.outcome == "fail"
    assert entry.timestamp > 0


def test_entry_roundtrip():
    entry = ReflexionEntry(
        task_id="t2",
        attempt_number=3,
        outcome="success",
        error_summary="",
        reflection_text="It worked",
        timestamp=1000.0,
    )
    d = entry.to_dict()
    restored = ReflexionEntry.from_dict(d)
    assert restored.task_id == entry.task_id
    assert restored.attempt_number == entry.attempt_number
    assert restored.timestamp == entry.timestamp


# ---------------------------------------------------------------------------
# ReflexionMemory — add / get
# ---------------------------------------------------------------------------


def test_add_reflection():
    mem = ReflexionMemory(max_entries=10)
    entry = mem.add_reflection("t1", 1, "fail", "timeout", "increase timeout")
    assert entry.task_id == "t1"
    assert len(mem.entries) == 1


def test_add_reflection_evicts_when_full():
    mem = ReflexionMemory(max_entries=3)
    for i in range(5):
        mem.add_reflection("t1", i, "fail", f"err-{i}", f"fix-{i}")
    assert len(mem.entries) == 3
    # Oldest entries evicted — remaining are attempts 2, 3, 4
    assert mem.entries[0].attempt_number == 2


def test_get_reflections_limit():
    mem = ReflexionMemory()
    for i in range(10):
        mem.add_reflection("task-a", i, "fail", f"err{i}", f"fix{i}")
    # Default limit=3 returns last 3
    result = mem.get_reflections("task-a")
    assert len(result) == 3
    assert result[-1].attempt_number == 9

    # Custom limit
    result = mem.get_reflections("task-a", limit=5)
    assert len(result) == 5


def test_get_reflections_filters_by_task():
    mem = ReflexionMemory()
    mem.add_reflection("task-a", 1, "fail", "err", "fix")
    mem.add_reflection("task-b", 1, "fail", "err", "fix")
    mem.add_reflection("task-a", 2, "success", "", "worked")

    result = mem.get_reflections("task-a")
    assert len(result) == 2
    assert all(e.task_id == "task-a" for e in result)


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_empty():
    mem = ReflexionMemory()
    assert mem.build_context("nonexistent") == ""


def test_build_context():
    mem = ReflexionMemory()
    mem.add_reflection("t1", 1, "fail", "KeyError", "Check key exists first")
    mem.add_reflection("t1", 2, "fail", "TypeError", "Validate input types")

    ctx = mem.build_context("t1")
    assert "Prior Attempt Reflections" in ctx
    assert "Task: t1" in ctx
    assert "Attempt 1 (fail)" in ctx
    assert "KeyError" in ctx
    assert "Attempt 2 (fail)" in ctx
    assert "TypeError" in ctx
    assert "avoid repeating mistakes" in ctx


# ---------------------------------------------------------------------------
# success_rate
# ---------------------------------------------------------------------------


def test_success_rate_no_entries():
    mem = ReflexionMemory()
    assert mem.success_rate("unknown") == 0.0


def test_success_rate():
    mem = ReflexionMemory()
    mem.add_reflection("t1", 1, "fail", "err", "fix")
    mem.add_reflection("t1", 2, "fail", "err", "fix")
    mem.add_reflection("t1", 3, "success", "", "worked")

    assert mem.success_rate("t1") == pytest.approx(1 / 3)


def test_success_rate_all_success():
    mem = ReflexionMemory()
    mem.add_reflection("t1", 1, "success", "", "ok")
    mem.add_reflection("t1", 2, "success", "", "ok")
    assert mem.success_rate("t1") == 1.0


# ---------------------------------------------------------------------------
# persist / load
# ---------------------------------------------------------------------------


def test_persist_and_load(tmp_path):
    persist_file = tmp_path / "entries.jsonl"

    mem = ReflexionMemory(max_entries=10, persist_path=persist_file)
    mem.add_reflection("t1", 1, "fail", "err1", "fix1")
    mem.add_reflection("t1", 2, "success", "", "worked")
    mem.persist()

    # Verify file was written
    lines = persist_file.read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["task_id"] == "t1"
    assert first["attempt_number"] == 1

    # Load into fresh memory
    mem2 = ReflexionMemory(max_entries=10, persist_path=persist_file)
    mem2.load()
    assert len(mem2.entries) == 2
    assert mem2.entries[0].task_id == "t1"
    assert mem2.entries[1].outcome == "success"


def test_load_nonexistent_file(tmp_path):
    """Loading from a missing file should not raise."""
    mem = ReflexionMemory(persist_path=tmp_path / "nope.jsonl")
    mem.load()  # no error
    assert len(mem.entries) == 0


def test_load_respects_max_entries(tmp_path):
    persist_file = tmp_path / "entries.jsonl"

    # Write 10 entries
    mem = ReflexionMemory(max_entries=100, persist_path=persist_file)
    for i in range(10):
        mem.add_reflection("t1", i, "fail", f"e{i}", f"f{i}")
    mem.persist()

    # Load with small cap
    mem2 = ReflexionMemory(max_entries=3, persist_path=persist_file)
    mem2.load()
    assert len(mem2.entries) == 3
    # Should keep the most recent
    assert mem2.entries[-1].attempt_number == 9


def test_load_skips_malformed_lines(tmp_path):
    persist_file = tmp_path / "entries.jsonl"
    good = json.dumps(ReflexionEntry(
        task_id="t1", attempt_number=1, outcome="fail",
        error_summary="err", reflection_text="fix", timestamp=1.0,
    ).to_dict())
    persist_file.write_text(f"{good}\nNOT_JSON\n{good}\n")

    mem = ReflexionMemory(persist_path=persist_file)
    mem.load()
    assert len(mem.entries) == 2  # skipped the bad line


# ---------------------------------------------------------------------------
# generate_reflection
# ---------------------------------------------------------------------------


async def test_generate_reflection():
    provider = _make_provider("WHAT WENT WRONG: timeout\nROOT CAUSE: slow API\nNEXT ATTEMPT: add retry")
    result = await generate_reflection(
        task_description="Deploy service",
        error="Connection timeout after 30s",
        provider_fn=provider,
    )
    assert "WHAT WENT WRONG" in result
    assert "ROOT CAUSE" in result
    assert len(provider.call_log) == 1
    # Verify the prompt included the task and error
    _, user_prompt = provider.call_log[0]
    assert "Deploy service" in user_prompt
    assert "Connection timeout" in user_prompt


async def test_generate_reflection_provider_failure():
    """When the provider raises, generate_reflection returns a fallback."""

    async def bad_provider(system: str, user: str) -> str:
        raise RuntimeError("LLM unreachable")

    result = await generate_reflection(
        task_description="Build widget",
        error="segfault",
        provider_fn=bad_provider,
    )
    assert "WHAT WENT WRONG" in result
    assert "segfault" in result
    assert "provider error" in result.lower()
