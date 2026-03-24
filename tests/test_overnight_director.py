"""Tests for overnight_director.py."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dharma_swarm.overnight_director import (
    CycleOutcome,
    DurableState,
    OvernightConfig,
    OvernightDirector,
    write_morning_brief,
)


# ---------------------------------------------------------------------------
# OvernightConfig
# ---------------------------------------------------------------------------


class TestOvernightConfig:
    def test_defaults(self) -> None:
        cfg = OvernightConfig()
        assert cfg.hours == 8.0
        assert cfg.dry_run is False
        assert cfg.cycle_timeout_seconds == 900.0
        assert cfg.autonomy_level == 1

    def test_to_dict(self) -> None:
        cfg = OvernightConfig(hours=2.0, dry_run=True)
        d = cfg.to_dict()
        assert d["hours"] == 2.0
        assert d["dry_run"] is True


# ---------------------------------------------------------------------------
# DurableState
# ---------------------------------------------------------------------------


class TestDurableState:
    def test_write_spec(self, tmp_path: Path) -> None:
        state = DurableState(run_dir=tmp_path)
        state.write_spec(OvernightConfig())
        assert state.spec_path.exists()
        data = json.loads(state.spec_path.read_text())
        assert "config" in data
        assert data["config"]["hours"] == 8.0

    def test_append_plan(self, tmp_path: Path) -> None:
        state = DurableState(run_dir=tmp_path)
        state.append_plan({"task_id": "t1", "goal": "test"})
        state.append_plan({"task_id": "t2", "goal": "test2"})
        lines = state.plan_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_update_runbook(self, tmp_path: Path) -> None:
        state = DurableState(run_dir=tmp_path)
        state.update_runbook("cycle_0001", "executing", "Doing stuff")
        text = state.runbook_path.read_text()
        assert "cycle_0001" in text
        assert "executing" in text

    def test_append_audit(self, tmp_path: Path) -> None:
        state = DurableState(run_dir=tmp_path)
        state.append_audit({"event": "test_event"})
        lines = state.audit_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event"] == "test_event"
        assert "ts" in data


# ---------------------------------------------------------------------------
# CycleOutcome
# ---------------------------------------------------------------------------


class TestCycleOutcome:
    def test_creation(self) -> None:
        o = CycleOutcome(
            cycle_id="c1",
            task_id="t1",
            task_goal="Do something",
            started_at=1000.0,
            completed_at=1010.0,
            status="completed",
        )
        assert o.duration_seconds == 10.0

    def test_to_dict(self) -> None:
        o = CycleOutcome(
            cycle_id="c1",
            task_id="t1",
            task_goal="Do something",
            started_at=1000.0,
        )
        d = o.to_dict()
        assert "duration_seconds" in d
        assert d["cycle_id"] == "c1"

    def test_zero_duration_when_incomplete(self) -> None:
        o = CycleOutcome(cycle_id="c1", task_id="t1", task_goal="x", started_at=0.0)
        assert o.duration_seconds == 0.0


# ---------------------------------------------------------------------------
# Morning Brief
# ---------------------------------------------------------------------------


class TestMorningBrief:
    def test_generates_file(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()

        # Monkey-patch STATE_DIR for test
        import dharma_swarm.overnight_director as mod
        original_state = mod.STATE_DIR
        mod.STATE_DIR = tmp_path
        try:
            brief = write_morning_brief(
                run_dir=tmp_path,
                config=OvernightConfig(hours=1.0),
                outcomes=[
                    CycleOutcome(
                        cycle_id="c1", task_id="t1", task_goal="Test task",
                        started_at=100, completed_at=110, status="completed",
                        acceptance_passed=True,
                    ),
                    CycleOutcome(
                        cycle_id="c2", task_id="t2", task_goal="Failed task",
                        started_at=120, completed_at=130, status="failed",
                        error="Something broke",
                    ),
                ],
                eval_summary={
                    "morning_capability_delta": 0.5,
                    "test_delta": 3,
                    "verified_completions": 1,
                    "dead_loop_ratio": 0.0,
                    "token_efficiency": 0.001,
                    "total_tokens_spent": 5000,
                },
                stager_stats={"total": 5, "completed": 1, "failed": 1, "pending": 3},
            )
            assert brief.exists()
            text = brief.read_text()
            assert "Morning Brief" in text
            assert "Test task" in text
            assert "Something broke" in text
            assert "0.50" in text  # capability delta
        finally:
            mod.STATE_DIR = original_state


# ---------------------------------------------------------------------------
# OvernightDirector — dry run
# ---------------------------------------------------------------------------


class TestOvernightDirector:
    def test_dry_run_completes(self, tmp_path: Path) -> None:
        """A dry run should stage tasks, simulate execution, and produce output."""
        # Set up a minimal dharma_swarm structure
        src_dir = tmp_path / "dharma_swarm"
        src_dir.mkdir()
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Create a source file without tests → should generate a task
        (src_dir / "example_module.py").write_text("# module\nx = 1\n")

        import dharma_swarm.overnight_director as director_mod
        import dharma_swarm.overnight_task_stager as stager_mod

        # Patch paths
        orig_state = director_mod.STATE_DIR
        orig_root = director_mod.DHARMA_SWARM_ROOT
        orig_stager_state = stager_mod.STATE_DIR
        orig_stager_root = stager_mod.DHARMA_SWARM_ROOT

        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()

        director_mod.STATE_DIR = state_dir
        director_mod.DHARMA_SWARM_ROOT = tmp_path
        stager_mod.STATE_DIR = state_dir
        stager_mod.DHARMA_SWARM_ROOT = tmp_path

        try:
            config = OvernightConfig(
                hours=0.001,  # Very short
                dry_run=True,
                autonomy_level=0,
            )
            director = OvernightDirector(config=config)
            director.run_dir = state_dir / "overnight" / director.date
            director.run_dir.mkdir(parents=True, exist_ok=True)
            director.state = DurableState(run_dir=director.run_dir)

            result = asyncio.run(director.run())

            assert result["date"] == director.date
            assert "eval_summary" in result
            assert "verdict" in result
            assert result["verdict"] in ("advance", "hold", "rollback")
            assert "verdict_reasons" in result
            assert isinstance(result["verdict_reasons"], list)
            # Verdict file should be written
            assert (director.run_dir / "verdict.json").exists()
            assert (state_dir / "shared" / "overnight_morning_brief.md").exists()
        finally:
            director_mod.STATE_DIR = orig_state
            director_mod.DHARMA_SWARM_ROOT = orig_root
            stager_mod.STATE_DIR = orig_stager_state
            stager_mod.DHARMA_SWARM_ROOT = orig_stager_root

    def test_empty_queue_completes(self, tmp_path: Path) -> None:
        """With no tasks, should complete gracefully."""
        import dharma_swarm.overnight_director as director_mod
        import dharma_swarm.overnight_task_stager as stager_mod

        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()

        # Empty dharma_swarm — no source files
        src_dir = tmp_path / "dharma_swarm"
        src_dir.mkdir()
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        orig_state = director_mod.STATE_DIR
        orig_root = director_mod.DHARMA_SWARM_ROOT
        orig_stager_state = stager_mod.STATE_DIR
        orig_stager_root = stager_mod.DHARMA_SWARM_ROOT

        director_mod.STATE_DIR = state_dir
        director_mod.DHARMA_SWARM_ROOT = tmp_path
        stager_mod.STATE_DIR = state_dir
        stager_mod.DHARMA_SWARM_ROOT = tmp_path

        try:
            config = OvernightConfig(hours=0.001, dry_run=True)
            director = OvernightDirector(config=config)
            director.run_dir = state_dir / "overnight" / director.date
            director.run_dir.mkdir(parents=True, exist_ok=True)
            director.state = DurableState(run_dir=director.run_dir)

            result = asyncio.run(director.run())
            assert result["total_cycles"] == 0
        finally:
            director_mod.STATE_DIR = orig_state
            director_mod.DHARMA_SWARM_ROOT = orig_root
            stager_mod.STATE_DIR = orig_stager_state
            stager_mod.DHARMA_SWARM_ROOT = orig_stager_root

    def test_real_test_coverage_task_generates_and_passes_smoke_test(self, tmp_path: Path) -> None:
        """Non-dry-run test_coverage should create a real test file and verify it."""
        src_dir = tmp_path / "dharma_swarm"
        src_dir.mkdir()
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        (src_dir / "example_module.py").write_text(
            "VALUE = 1\n\ndef meaning() -> int:\n    return VALUE\n",
            encoding="utf-8",
        )

        import dharma_swarm.overnight_director as director_mod
        import dharma_swarm.overnight_task_stager as stager_mod

        orig_state = director_mod.STATE_DIR
        orig_root = director_mod.DHARMA_SWARM_ROOT
        orig_stager_state = stager_mod.STATE_DIR
        orig_stager_root = stager_mod.DHARMA_SWARM_ROOT

        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()

        director_mod.STATE_DIR = state_dir
        director_mod.DHARMA_SWARM_ROOT = tmp_path
        stager_mod.STATE_DIR = state_dir
        stager_mod.DHARMA_SWARM_ROOT = tmp_path

        try:
            config = OvernightConfig(
                hours=0.001,
                dry_run=False,
                autonomy_level=0,
            )
            director = OvernightDirector(config=config)
            director.run_dir = state_dir / "overnight" / director.date
            director.run_dir.mkdir(parents=True, exist_ok=True)
            director.state = DurableState(run_dir=director.run_dir)

            result = asyncio.run(director.run())

            generated_test = test_dir / "test_example_module.py"
            assert generated_test.exists()
            assert result["completed"] >= 1
            assert result["failed"] == 0
        finally:
            director_mod.STATE_DIR = orig_state
            director_mod.DHARMA_SWARM_ROOT = orig_root
            stager_mod.STATE_DIR = orig_stager_state
            stager_mod.DHARMA_SWARM_ROOT = orig_stager_root
