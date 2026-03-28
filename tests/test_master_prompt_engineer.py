"""Tests for dharma_swarm.master_prompt_engineer -- 3-layer prompt evolution."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.master_prompt_engineer import (
    _detect_loops,
    _format_cycle_history,
    _load_cycle_history,
    _save_cycle_entry,
    assess_quality,
    gather_system_state,
    generate_local_prompt,
    record_cycle,
    should_evolve_prompt,
)


# ---------------------------------------------------------------------------
# should_evolve_prompt
# ---------------------------------------------------------------------------


def test_should_evolve_every_3():
    assert should_evolve_prompt(3, every_n=3) is True
    assert should_evolve_prompt(6, every_n=3) is True
    assert should_evolve_prompt(9, every_n=3) is True


def test_should_not_evolve_between():
    assert should_evolve_prompt(1, every_n=3) is False
    assert should_evolve_prompt(2, every_n=3) is False
    assert should_evolve_prompt(4, every_n=3) is False
    assert should_evolve_prompt(5, every_n=3) is False


def test_should_not_evolve_zero():
    assert should_evolve_prompt(0, every_n=3) is False


def test_should_evolve_every_1():
    assert should_evolve_prompt(1, every_n=1) is True
    assert should_evolve_prompt(2, every_n=1) is True


def test_should_evolve_every_5():
    assert should_evolve_prompt(5, every_n=5) is True
    assert should_evolve_prompt(3, every_n=5) is False


# ---------------------------------------------------------------------------
# _detect_loops
# ---------------------------------------------------------------------------


def test_detect_loops_insufficient_history():
    result = _detect_loops([])
    assert "Insufficient" in result

    result = _detect_loops([{"todo_steps": ["a"]}])
    assert "Insufficient" in result


def test_detect_loops_no_repeats():
    history = [
        {"todo_steps": ["fix module A"]},
        {"todo_steps": ["fix module B"]},
        {"todo_steps": ["fix module C"]},
    ]
    result = _detect_loops(history)
    assert "non-degenerate" in result


def test_detect_loops_with_repeats():
    history = [
        {"todo_steps": ["fix the flaky test in test_providers.py"]},
        {"todo_steps": ["fix the flaky test in test_providers.py"]},
        {"todo_steps": ["add coverage for module X"]},
    ]
    result = _detect_loops(history)
    assert "REPEATED TODO" in result
    assert "fix the flaky test" in result


def test_detect_loops_case_insensitive():
    history = [
        {"todo_steps": ["Fix Module A"]},
        {"todo_steps": ["fix module a"]},
    ]
    result = _detect_loops(history)
    assert "REPEATED TODO" in result


# ---------------------------------------------------------------------------
# _format_cycle_history
# ---------------------------------------------------------------------------


def test_format_cycle_history_empty():
    result = _format_cycle_history([])
    assert "No previous" in result


def test_format_cycle_history_with_data():
    history = [
        {
            "timestamp": "2026-03-07T10:00:00",
            "cycle": 1,
            "tests_passed": 100,
            "tests_failed": 2,
            "todo_steps": ["step A", "step B"],
            "quality_verdict": "HEALTHY",
        },
    ]
    result = _format_cycle_history(history)
    assert "Cycle 1" in result
    assert "100p" in result
    assert "2f" in result
    assert "HEALTHY" in result
    assert "step A" in result


def test_format_cycle_history_truncates_steps():
    history = [
        {
            "timestamp": "2026-03-07",
            "cycle": 5,
            "tests_passed": 50,
            "tests_failed": 0,
            "todo_steps": ["a", "b", "c", "d", "e"],
            "quality_verdict": "HEALTHY",
        },
    ]
    result = _format_cycle_history(history)
    assert "and 2 more" in result


# ---------------------------------------------------------------------------
# Cycle history persistence
# ---------------------------------------------------------------------------


def test_save_and_load_cycle_history(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        _save_cycle_entry({"cycle": 1, "todo_steps": ["a"]})
        _save_cycle_entry({"cycle": 2, "todo_steps": ["b"]})
        _save_cycle_entry({"cycle": 3, "todo_steps": ["c"]})

        loaded = _load_cycle_history(max_entries=10)
        assert len(loaded) == 3
        assert loaded[0]["cycle"] == 1
        assert loaded[2]["cycle"] == 3


def test_load_cycle_history_max_entries(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        for i in range(10):
            _save_cycle_entry({"cycle": i, "todo_steps": [f"step {i}"]})

        loaded = _load_cycle_history(max_entries=3)
        assert len(loaded) == 3
        assert loaded[0]["cycle"] == 7
        assert loaded[2]["cycle"] == 9


def test_load_cycle_history_missing_file(tmp_path: Path):
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", tmp_path / "nope.jsonl"):
        loaded = _load_cycle_history()
        assert loaded == []


def test_load_cycle_history_corrupt_lines(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    history_file.write_text('{"cycle": 1}\nnot json\n{"cycle": 2}\n')
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        loaded = _load_cycle_history()
        assert len(loaded) == 2


# ---------------------------------------------------------------------------
# record_cycle
# ---------------------------------------------------------------------------


def test_record_cycle(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        record_cycle(
            cycle_number=1,
            todo_steps=["fix A", "fix B"],
            test_results={"passed": 100, "failed": 2},
            files_reviewed=["foo.py", "bar.py"],
            quality_verdict="HEALTHY",
        )

        loaded = _load_cycle_history()
        assert len(loaded) == 1
        entry = loaded[0]
        assert entry["cycle"] == 1
        assert entry["tests_passed"] == 100
        assert entry["tests_failed"] == 2
        assert entry["quality_verdict"] == "HEALTHY"
        assert "fix A" in entry["todo_steps"]


def test_record_cycle_defaults(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        record_cycle(cycle_number=5, todo_steps=["x"])
        loaded = _load_cycle_history()
        assert loaded[0]["tests_passed"] == 0
        assert loaded[0]["files_reviewed"] == []


# ---------------------------------------------------------------------------
# assess_quality
# ---------------------------------------------------------------------------


def test_assess_quality_healthy():
    history = [
        {"todo_steps": ["a"], "tests_passed": 100, "tests_failed": 0, "files_reviewed": ["x.py"]},
        {"todo_steps": ["b"], "tests_passed": 101, "tests_failed": 0, "files_reviewed": ["y.py"]},
    ]
    assert assess_quality(history) == "HEALTHY"


def test_assess_quality_insufficient_data():
    assert assess_quality([]) == "HEALTHY"
    assert assess_quality([{"todo_steps": ["a"]}]) == "HEALTHY"


def test_assess_quality_looping():
    history = [
        {"todo_steps": ["fix the same thing"]},
        {"todo_steps": ["fix the same thing"]},
        {"todo_steps": ["fix the same thing"]},
    ]
    assert assess_quality(history) == "LOOPING"


def test_assess_quality_stuck():
    history = [
        {"todo_steps": ["a"], "tests_passed": 100, "tests_failed": 0, "files_reviewed": ["x"]},
        {"todo_steps": ["b"], "tests_passed": 100, "tests_failed": 0, "files_reviewed": ["y"]},
        {"todo_steps": ["c"], "tests_passed": 100, "tests_failed": 0, "files_reviewed": ["z"]},
    ]
    assert assess_quality(history) == "STUCK"


def test_assess_quality_drifting():
    history = [
        {"todo_steps": ["a"], "tests_passed": 100, "tests_failed": 0, "files_reviewed": []},
        {"todo_steps": ["b"], "tests_passed": 101, "tests_failed": 0, "files_reviewed": []},
        {"todo_steps": ["c"], "tests_passed": 102, "tests_failed": 0, "files_reviewed": []},
    ]
    assert assess_quality(history) == "DRIFTING"


# ---------------------------------------------------------------------------
# gather_system_state
# ---------------------------------------------------------------------------


def test_gather_system_state():
    state = gather_system_state()
    assert "test_files" in state
    assert "modules" in state
    assert "api_keys" in state
    assert "infrastructure" in state
    assert "timestamp" in state
    # Should have actual counts (we are in the dharma_swarm repo)
    assert isinstance(state["test_files"], int)
    assert isinstance(state["modules"], int)


# ---------------------------------------------------------------------------
# generate_local_prompt
# ---------------------------------------------------------------------------


def test_generate_local_prompt_basic():
    prompt = generate_local_prompt(
        test_summary="Passed: 100, Failed: 2",
        file_signals="  foo.py: 200 lines (TODO=3)",
        prev_todo="  1. Fix flaky test",
        cycle_number=5,
        colm_days=15,
    )
    assert "Cycle 5" in prompt
    assert "COLM deadline: 15 days" in prompt
    assert "Passed: 100" in prompt
    assert "foo.py" in prompt
    assert "Fix flaky test" in prompt


def test_generate_local_prompt_no_data():
    prompt = generate_local_prompt()
    assert "Cycle 0" in prompt
    assert "No test data" in prompt


def test_generate_local_prompt_with_looping_history(tmp_path: Path):
    history_file = tmp_path / "history.jsonl"
    with patch("dharma_swarm.master_prompt_engineer._HISTORY_FILE", history_file):
        for _ in range(3):
            _save_cycle_entry({"cycle": 1, "todo_steps": ["same thing again"]})
        prompt = generate_local_prompt(cycle_number=4)
        assert "LOOPING" in prompt


# ---------------------------------------------------------------------------
# generate_evolved_prompt (LLM-powered, mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_evolved_prompt_no_available_providers():
    with patch.dict("os.environ", {}, clear=True):
        with patch(
            "dharma_swarm.master_prompt_engineer.complete_via_preferred_runtime_providers",
            new=AsyncMock(side_effect=RuntimeError("No preferred providers available")),
        ):
            from dharma_swarm.master_prompt_engineer import generate_evolved_prompt

            with pytest.raises(RuntimeError, match="No preferred providers available"):
                await generate_evolved_prompt()


@pytest.mark.asyncio
async def test_generate_evolved_prompt_mocked():
    with patch(
        "dharma_swarm.master_prompt_engineer.complete_via_preferred_runtime_providers",
        new=AsyncMock(
            return_value=(
                LLMResponse(
                    content="EVOLVED PROMPT: do the thing",
                    model="nim-local",
                ),
                SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
            )
        ),
    ):
        from dharma_swarm.master_prompt_engineer import generate_evolved_prompt

        result = await generate_evolved_prompt(
            test_summary="Passed: 50",
            cycle_number=3,
        )
        assert "do the thing" in result


@pytest.mark.asyncio
async def test_generate_evolved_prompt_empty_choices():
    with patch(
        "dharma_swarm.master_prompt_engineer.complete_via_preferred_runtime_providers",
        new=AsyncMock(
            return_value=(
                LLMResponse(content="", model="nim-local"),
                SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
            )
        ),
    ):
        from dharma_swarm.master_prompt_engineer import generate_evolved_prompt

        with pytest.raises(RuntimeError, match="empty prompt content"):
            await generate_evolved_prompt()
