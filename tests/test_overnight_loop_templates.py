"""Tests for overnight loop template progress tracking."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tools.loop_templates.conductor_efficiency import (
    LoopConfig as ConductorConfig,
    SimulationResult,
    _service_level_met,
    run as run_conductor_loop,
)
from tools.loop_templates.progress_protocol import LoopProgressTracker, ProgressSnapshot
from tools.loop_templates.rv_pipeline_optimization import (
    LoopConfig as RVConfig,
    run as run_rv_loop,
)
from tools.loop_templates.telos_gate_coverage import (
    verify_existing_gate_tests,
)


def test_progress_protocol_writes_snapshot_and_history(tmp_path: Path) -> None:
    tracker = LoopProgressTracker("demo_loop", tmp_path)
    tracker.start("Demo objective", {"max_iterations": 1})
    tracker.record(ProgressSnapshot(
        loop_name="demo_loop",
        objective="Demo objective",
        status="running",
        iteration=1,
        target_metric={"score": 1.0},
        current_metric={"score": 0.5},
        best_metric={"score": 0.5},
        verifier={"passed": False},
        artifact_delta={"metrics_updated": 1},
        next_best_task="Run one more iteration.",
    ))
    tracker.finish({"converged": False})

    snapshot = json.loads((tmp_path / "demo_loop_progress.json").read_text())
    history = (tmp_path / "demo_loop_progress.jsonl").read_text().strip().splitlines()

    assert snapshot["next_best_task"] == "Run one more iteration."
    assert len(history) == 3


def test_rv_loop_writes_progress_snapshot(tmp_path: Path) -> None:
    cfg = RVConfig(max_iterations=2, seed_count=2, log_dir=tmp_path)
    results = asyncio.run(run_rv_loop(config=cfg))

    assert results
    snapshot = json.loads((tmp_path / "rv_pipeline_optimization_progress.json").read_text())
    assert snapshot["loop_name"] == "rv_pipeline_optimization"
    assert "next_best_task" in snapshot
    assert "verifier" in snapshot


def test_verify_existing_gate_tests_requires_passing_dedicated_file(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_gate_ahimsa.py").write_text(
        "def test_ahimsa_passes():\n    assert True\n",
        encoding="utf-8",
    )
    (tests_dir / "test_gate_satya.py").write_text(
        "def test_satya_fails():\n    assert False\n",
        encoding="utf-8",
    )

    verified = verify_existing_gate_tests(
        tests_dir=tests_dir,
        gate_names=["AHIMSA", "SATYA"],
        timeout=5.0,
    )

    assert "AHIMSA" in verified
    assert "SATYA" not in verified


def test_conductor_service_level_requires_latency_and_missed_work() -> None:
    cfg = ConductorConfig(max_avg_latency=120.0, max_missed_work=0)
    good = SimulationResult(
        wake_interval=30.0,
        total_wakes=10,
        productive_wakes=9,
        idle_wakes=1,
        waste_ratio=0.1,
        work_items_completed=9,
        work_items_missed=0,
        avg_response_latency=30.0,
    )
    bad = SimulationResult(
        wake_interval=300.0,
        total_wakes=2,
        productive_wakes=2,
        idle_wakes=0,
        waste_ratio=0.0,
        work_items_completed=2,
        work_items_missed=3,
        avg_response_latency=240.0,
    )

    assert _service_level_met(good, cfg) is True
    assert _service_level_met(bad, cfg) is False


def test_conductor_loop_writes_progress_snapshot(tmp_path: Path) -> None:
    cfg = ConductorConfig(max_iterations=2, log_dir=tmp_path, max_wake_interval=120.0)
    results = asyncio.run(run_conductor_loop(config=cfg))

    assert results
    snapshot = json.loads((tmp_path / "conductor_efficiency_progress.json").read_text())
    assert snapshot["loop_name"] == "conductor_efficiency"
    assert "next_best_task" in snapshot
