"""Tests for strange_loop integration with master_prompt_engineer."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts to path for import
sys.path.insert(0, str(Path.home() / "dharma_swarm" / "scripts"))
sys.path.insert(0, str(Path.home() / "dharma_swarm"))

from scripts.strange_loop import (
    build_todo,
    build_compounding_event,
    execute_ranked_steps,
    extract_test_counts,
    format_signals_for_prompt,
    rank_top_steps,
    run_prompt_evolution,
    step_priority,
)


# ---------------------------------------------------------------------------
# extract_test_counts
# ---------------------------------------------------------------------------


def test_extract_test_counts_basic():
    results = [
        {"label": "tests-provider", "rc": 0, "stdout_tail": "50 passed in 2.5s"},
        {"label": "tests-engine", "rc": 0, "stdout_tail": "30 passed, 2 failed in 3.0s"},
        {"label": "status", "rc": 0, "stdout_tail": "all good"},
    ]
    counts = extract_test_counts(results)
    assert counts["passed"] == 80
    assert counts["failed"] == 2


def test_extract_test_counts_no_tests():
    results = [
        {"label": "status", "rc": 0, "stdout_tail": "OK"},
        {"label": "health-check", "rc": 0, "stdout_tail": "healthy"},
    ]
    counts = extract_test_counts(results)
    assert counts["passed"] == 0
    assert counts["failed"] == 0


def test_extract_test_counts_all_failing():
    results = [
        {"label": "tests-provider", "rc": 1, "stdout_tail": "0 passed, 15 failed in 1.0s"},
    ]
    counts = extract_test_counts(results)
    assert counts["passed"] == 0
    assert counts["failed"] == 15


def test_extract_test_counts_empty():
    assert extract_test_counts([]) == {"passed": 0, "failed": 0}


# ---------------------------------------------------------------------------
# format_signals_for_prompt
# ---------------------------------------------------------------------------


def test_format_signals_basic():
    signals = [
        {"path": "/foo/bar.py", "lines": 200, "todo_markers": 3, "defs": 10, "tests": 5},
        {"path": "/foo/baz.py", "lines": 50, "todo_markers": 0, "defs": 2, "tests": 0},
    ]
    result = format_signals_for_prompt(signals)
    assert "bar.py" in result
    assert "TODO=3" in result
    assert "tests=5" in result
    assert "baz.py" in result


def test_format_signals_with_error():
    signals = [{"path": "/broken.py", "error": "Permission denied"}]
    result = format_signals_for_prompt(signals)
    assert "ERROR" in result
    assert "Permission denied" in result


def test_format_signals_empty():
    assert format_signals_for_prompt([]) == "No files reviewed."


# ---------------------------------------------------------------------------
# ranking / prioritization
# ---------------------------------------------------------------------------


def test_step_priority_classifies_noise():
    p, cat = step_priority("Emit final handoff at 04:00 JST report.")
    assert p == 0
    assert cat == "noise"


def test_rank_top_steps_suppresses_noise_by_default():
    steps = [
        "Emit final handoff at 04:00 JST report.",
        "Emit final handoff at 04:00 JST report.",
        "Run provider core tests (`tests/test_providers.py`).",
    ]
    ranked = rank_top_steps(steps, limit=20)
    examples = [item["example"] for item in ranked]
    assert any("provider core tests" in e.lower() for e in examples)
    assert not any("handoff at 04:00" in e.lower() for e in examples)


def test_rank_top_steps_can_include_noise_with_env():
    steps = [
        "Emit final handoff at 04:00 JST report.",
        "Run provider core tests (`tests/test_providers.py`).",
    ]
    with patch.dict("os.environ", {"ALLOUT_INCLUDE_NOISE": "1"}):
        ranked = rank_top_steps(steps, limit=20)
    examples = [item["example"] for item in ranked]
    assert any("handoff at 04:00" in e.lower() for e in examples)


def test_rank_top_steps_suppresses_infra_when_accelerators_dormant():
    steps = [
        "Bring up NVIDIA RAG services and verify `/v1/health` on ports 8081/8082.",
        "Run provider core tests (`tests/test_providers.py`).",
    ]
    with patch.dict("os.environ", {"DGC_ACCELERATOR_MODE": "dormant"}, clear=False):
        ranked = rank_top_steps(steps, limit=20)
    examples = [item["example"] for item in ranked]
    assert any("provider core tests" in e.lower() for e in examples)
    assert not any("nvidia rag services" in e.lower() for e in examples)


# ---------------------------------------------------------------------------
# run_prompt_evolution
# ---------------------------------------------------------------------------


def test_run_prompt_evolution_not_due(tmp_path: Path):
    """Cycle 1 should not trigger evolution (every_n=3)."""
    log_file = tmp_path / "test.log"
    with patch.dict("os.environ", {"ALLOUT_EVOLVE_EVERY": "3"}):
        result = run_prompt_evolution(
            cycle=1,
            results=[],
            signals=[],
            todo_steps=[],
            log_file=log_file,
        )
        assert result is None


def test_run_prompt_evolution_due_local(tmp_path: Path):
    """Cycle 3 should trigger local evolution (no API key)."""
    log_file = tmp_path / "test.log"
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    with patch.dict("os.environ", {"ALLOUT_EVOLVE_EVERY": "3"}, clear=True):
        with patch("scripts.strange_loop.SHARED_DIR", shared_dir):
            result = run_prompt_evolution(
                cycle=3,
                results=[
                    {"label": "tests-provider", "rc": 0, "stdout_tail": "100 passed in 5s"},
                ],
                signals=[
                    {"path": "/foo.py", "lines": 50, "todo_markers": 1, "defs": 3, "tests": 2},
                ],
                todo_steps=["Fix the thing"],
                log_file=log_file,
            )
            assert result is not None
            assert "Cycle 3" in result
            assert "Passed: 100" in result

            # Check files were written
            evolved = shared_dir / "evolved_prompt_cycle_003.md"
            assert evolved.exists()
            latest = shared_dir / "EVOLVED_PROMPT.md"
            assert latest.exists()

            # Check log entries
            log_text = log_file.read_text()
            assert "EVOLVE" in log_text


def test_run_prompt_evolution_cycle_6(tmp_path: Path):
    """Cycle 6 should also trigger (every 3rd)."""
    log_file = tmp_path / "test.log"
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    with patch.dict("os.environ", {"ALLOUT_EVOLVE_EVERY": "3"}, clear=True):
        with patch("scripts.strange_loop.SHARED_DIR", shared_dir):
            result = run_prompt_evolution(
                cycle=6,
                results=[],
                signals=[],
                todo_steps=[],
                log_file=log_file,
            )
            assert result is not None
            assert "Cycle 6" in result


# ---------------------------------------------------------------------------
# action execution + compounding ledger event
# ---------------------------------------------------------------------------


def test_execute_ranked_steps_uses_fallback_when_ranked_are_noops():
    ranked = [
        {"example": "Unmapped step one", "score": 100},
        {"example": "Unmapped step two", "score": 90},
    ]

    def fake_execute(step: str) -> dict[str, object]:
        low = step.lower()
        if "provider core tests" in low:
            return {"step": step, "action": "pytest_provider_core", "rc": 0, "verify": "ok"}
        if "engine safety tests" in low:
            return {"step": step, "action": "pytest_engine_safety", "rc": 0, "verify": "ok"}
        return {"step": step, "action": "noop_unmapped_step", "rc": 0, "verify": "noop"}

    with patch("scripts.strange_loop.execute_single_step", side_effect=fake_execute):
        actions = execute_ranked_steps(ranked, max_actions=2)

    assert len(actions) == 2
    assert all(a["action"] != "noop_unmapped_step" for a in actions)
    assert actions[0]["action"] == "pytest_provider_core"


def test_execute_ranked_steps_skips_accelerator_items_when_dormant():
    ranked = [
        {"example": "Bring up NVIDIA RAG services and verify `/v1/health` on ports 8081/8082.", "score": 100},
        {"example": "Run provider core tests (`tests/test_providers.py`).", "score": 90},
    ]

    def fake_execute(step: str) -> dict[str, object]:
        low = step.lower()
        if "provider core tests" in low:
            return {"step": step, "action": "pytest_provider_core", "rc": 0, "verify": "ok"}
        if "nvidia rag services" in low:
            return {"step": step, "action": "should_not_run", "rc": 1, "verify": "bad"}
        return {"step": step, "action": "noop_unmapped_step", "rc": 0, "verify": "noop"}

    with patch.dict("os.environ", {"DGC_ACCELERATOR_MODE": "dormant"}, clear=False):
        with patch("scripts.strange_loop.execute_single_step", side_effect=fake_execute):
            actions = execute_ranked_steps(ranked, max_actions=1)

    assert len(actions) == 1
    assert actions[0]["action"] == "pytest_provider_core"


def test_build_todo_omits_accelerator_fixups_when_dormant():
    results = [
        {"label": "rag-health", "rc": 2},
        {"label": "ingest-health", "rc": 2},
        {"label": "flywheel-jobs", "rc": 2},
        {"label": "tests-provider", "rc": 0},
    ]
    signals = [
        {"path": "/tmp/example.py", "todo_markers": 0, "defs": 9, "tests": 0},
    ]

    with patch.dict("os.environ", {"DGC_ACCELERATOR_MODE": "dormant"}, clear=False):
        todo = build_todo(1, results, signals, min_steps=3, max_steps=5)

    combined = "\n".join(todo).lower()
    assert "nvidia rag" not in combined
    assert "flywheel" not in combined
    assert "focused tests" in combined


def test_build_compounding_event_counts():
    event = build_compounding_event(
        run_id="run_1",
        cycle=3,
        jst="2026-03-08 09:00:00 JST",
        results=[
            {"label": "mission-status", "rc": 0},
            {"label": "tests-provider", "rc": 1},
        ],
        todo_steps=["a", "b"],
        ranked_top20=[{"example": "x"}],
        executed_actions=[
            {"action": "pytest_provider_core", "rc": 0},
            {"action": "noop_unmapped_step", "rc": 0},
            {"action": "pytest_engine_safety", "rc": 1},
        ],
        files_reviewed=["f1.py", "f2.py"],
        cycle_elapsed_sec=12.34,
    )
    assert event["checks_total"] == 2
    assert event["checks_ok"] == 1
    assert event["checks_fail"] == 1
    assert event["mission_status_rc"] == 0
    assert event["actions_total"] == 3
    assert event["actions_ok"] == 2
    assert event["actions_fail"] == 1
    assert event["actions_noop"] == 1
