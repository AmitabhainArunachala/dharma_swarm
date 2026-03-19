"""Tests for action_dispatch — the PAL→execution connector."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.action_dispatch import (
    ActionDispatcher,
    DispatchOutcome,
    ExperienceBase,
    SwarmContext,
    _RestartCooldown,
)
from dharma_swarm.complexity_router import ComplexityRoute
from dharma_swarm.perception_action_loop import (
    CandidateAction,
    Percept,
    PerceptionModality,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    return tmp_path / ".dharma"


@pytest.fixture
def ctx(tmp_state_dir: Path) -> SwarmContext:
    return SwarmContext(state_dir=tmp_state_dir)


@pytest.fixture
def dispatcher(ctx: SwarmContext) -> ActionDispatcher:
    return ActionDispatcher(context=ctx)


def _make_candidate(
    action_type: str = "health_check",
    target: str = "dharma_swarm",
    description: str = "test action",
    percept_data: dict[str, Any] | None = None,
    complexity_route: ComplexityRoute = ComplexityRoute.FAST,
) -> CandidateAction:
    percept = Percept(
        modality=PerceptionModality.HEALTH,
        observation=description,
        salience=0.8,
        data=percept_data or {},
    )
    return CandidateAction(
        action_type=action_type,
        target=target,
        description=description,
        source_percept=percept,
        complexity_route=complexity_route,
    )


# ---------------------------------------------------------------------------
# ExperienceBase tests
# ---------------------------------------------------------------------------


class TestExperienceBase:
    def test_record_and_total(self) -> None:
        eb = ExperienceBase(max_records=5)
        for i in range(3):
            eb.record(DispatchOutcome(action_type="test", target="t", executed=True))
        assert eb.total == 3

    def test_fifo_eviction(self) -> None:
        eb = ExperienceBase(max_records=3)
        for i in range(5):
            eb.record(DispatchOutcome(
                action_type="test", target=f"t{i}", executed=True,
            ))
        assert eb.total == 3

    def test_success_rate(self) -> None:
        eb = ExperienceBase()
        eb.record(DispatchOutcome(action_type="health", target="t", executed=True))
        eb.record(DispatchOutcome(action_type="health", target="t", executed=True))
        eb.record(DispatchOutcome(action_type="health", target="t", executed=False))
        assert abs(eb.success_rate("health") - 2 / 3) < 0.01

    def test_success_rate_unknown_type(self) -> None:
        eb = ExperienceBase()
        assert eb.success_rate("nonexistent") == 0.0


# ---------------------------------------------------------------------------
# RestartCooldown tests
# ---------------------------------------------------------------------------


class TestRestartCooldown:
    def test_initial_allows_restart(self) -> None:
        cd = _RestartCooldown(cooldown_seconds=600)
        assert cd.can_restart("daemon_a") is True

    def test_cooldown_blocks_restart(self) -> None:
        cd = _RestartCooldown(cooldown_seconds=600)
        cd.record_restart("daemon_a")
        assert cd.can_restart("daemon_a") is False

    def test_different_daemons_independent(self) -> None:
        cd = _RestartCooldown(cooldown_seconds=600)
        cd.record_restart("daemon_a")
        assert cd.can_restart("daemon_b") is True

    def test_cooldown_expires(self) -> None:
        cd = _RestartCooldown(cooldown_seconds=0.01)
        cd.record_restart("daemon_a")
        import time
        time.sleep(0.02)
        assert cd.can_restart("daemon_a") is True


# ---------------------------------------------------------------------------
# ActionDispatcher core tests
# ---------------------------------------------------------------------------


class TestActionDispatcher:
    @pytest.mark.asyncio
    async def test_unknown_action_type(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(action_type="nonexistent")
        result = await dispatcher.handle(candidate)
        assert result["executed"] is False
        assert "unknown_action_type" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_viveka_blocks_action(self, ctx: SwarmContext) -> None:
        viveka = MagicMock()
        viveka_result = MagicMock()
        viveka_result.should_act = False
        viveka_result.reason = "EFE too high"
        viveka_result.decision.value = "wait"
        viveka.evaluate.return_value = viveka_result

        d = ActionDispatcher(context=ctx, viveka=viveka)
        candidate = _make_candidate()
        result = await d.handle(candidate)
        assert result["executed"] is False
        assert "viveka_wait" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_viveka_allows_action(self, ctx: SwarmContext) -> None:
        viveka = MagicMock()
        viveka_result = MagicMock()
        viveka_result.should_act = True
        viveka.evaluate.return_value = viveka_result

        d = ActionDispatcher(context=ctx, viveka=viveka)
        # health_check with no pid_file data → handled but returns no_pid_file
        candidate = _make_candidate(percept_data={})
        result = await d.handle(candidate)
        assert result["executed"] is False
        assert result.get("reason") == "no_pid_file"

    @pytest.mark.asyncio
    async def test_experience_records_outcome(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(action_type="nonexistent")
        await dispatcher.handle(candidate)
        assert dispatcher._experience.total == 1

    @pytest.mark.asyncio
    async def test_dispatch_log_written(self, dispatcher: ActionDispatcher) -> None:
        # Use health_check with a real PID file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", delete=False) as f:
            f.write(str(os.getpid()))
            pid_file = f.name
        try:
            candidate = _make_candidate(
                percept_data={"target": "test_daemon", "pid_file": pid_file},
            )
            await dispatcher.handle(candidate)
            log_file = dispatcher._log_dir / "dispatch.jsonl"
            assert log_file.exists()
            lines = log_file.read_text().strip().splitlines()
            assert len(lines) >= 1
        finally:
            os.unlink(pid_file)


# ---------------------------------------------------------------------------
# Health check handler tests
# ---------------------------------------------------------------------------


class TestHealthCheckHandler:
    @pytest.mark.asyncio
    async def test_alive_daemon(self, dispatcher: ActionDispatcher) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", delete=False) as f:
            f.write(str(os.getpid()))
            pid_file = f.name
        try:
            candidate = _make_candidate(
                percept_data={"target": "dharma_swarm", "pid_file": pid_file},
            )
            result = await dispatcher.handle(candidate)
            assert result["executed"] is True
            assert "alive" in result.get("summary", "")
        finally:
            os.unlink(pid_file)

    @pytest.mark.asyncio
    async def test_dead_daemon_cleanup(self, dispatcher: ActionDispatcher, tmp_path: Path) -> None:
        pid_file = tmp_path / "dead.pid"
        pid_file.write_text("999999")  # Almost certainly dead PID
        candidate = _make_candidate(
            percept_data={"target": "test_daemon", "pid_file": str(pid_file)},
        )
        result = await dispatcher.handle(candidate)
        assert result["executed"] is True
        assert "cleaned" in result.get("summary", "") or "dead" in result.get("summary", "").lower()

    @pytest.mark.asyncio
    async def test_restart_cooldown(self, dispatcher: ActionDispatcher, tmp_path: Path) -> None:
        pid_file = tmp_path / "dead2.pid"

        # First restart should work
        pid_file.write_text("999998")
        candidate = _make_candidate(
            target="cooldown_daemon",
            percept_data={"target": "cooldown_daemon", "pid_file": str(pid_file)},
        )
        result1 = await dispatcher.handle(candidate)
        assert result1["executed"] is True

        # Second restart should be on cooldown
        pid_file.write_text("999997")
        result2 = await dispatcher.handle(candidate)
        assert result2["executed"] is False
        assert "cooldown" in result2.get("reason", "")

    @pytest.mark.asyncio
    async def test_no_pid_file(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(percept_data={})
        result = await dispatcher.handle(candidate)
        assert result["executed"] is False
        assert result.get("reason") == "no_pid_file"


# ---------------------------------------------------------------------------
# Investigate mark handler tests
# ---------------------------------------------------------------------------


class TestInvestigateMarkHandler:
    @pytest.mark.asyncio
    async def test_self_referential_mark_skipped(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(
            action_type="investigate_mark",
            percept_data={"source": "pal_dispatch"},
        )
        result = await dispatcher.handle(candidate)
        assert result["executed"] is False
        assert "self_referential" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_no_task_board(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(
            action_type="investigate_mark",
            percept_data={"file_path": "foo.py", "agent": "test"},
        )
        result = await dispatcher.handle(candidate)
        assert result["executed"] is False
        assert "task_board_unavailable" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_creates_task(self, ctx: SwarmContext) -> None:
        ctx.task_board = AsyncMock()
        ctx.task_board.add = AsyncMock(return_value="task_123")
        d = ActionDispatcher(context=ctx)

        candidate = _make_candidate(
            action_type="investigate_mark",
            percept_data={"file_path": "foo.py", "agent": "test_agent"},
        )
        result = await d.handle(candidate)
        assert result["executed"] is True
        assert result.get("task_id") == "task_123"
        ctx.task_board.add.assert_called_once()


# ---------------------------------------------------------------------------
# Process signal handler tests
# ---------------------------------------------------------------------------


class TestProcessSignalHandler:
    @pytest.mark.asyncio
    async def test_signal_no_proposed_action(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(
            action_type="process_signal",
            percept_data={"source": "agni"},
        )
        result = await dispatcher.handle(candidate)
        assert result["executed"] is True
        assert "noted" in result.get("summary", "")

    @pytest.mark.asyncio
    async def test_signal_with_proposed_action_creates_task(self, ctx: SwarmContext) -> None:
        ctx.task_board = AsyncMock()
        ctx.task_board.add = AsyncMock(return_value="sig_task_1")
        d = ActionDispatcher(context=ctx)

        candidate = _make_candidate(
            action_type="process_signal",
            percept_data={"source": "agni", "proposed_action": "run backup"},
        )
        result = await d.handle(candidate)
        assert result["executed"] is True
        assert result.get("task_id") == "sig_task_1"


# ---------------------------------------------------------------------------
# Deadline handler tests
# ---------------------------------------------------------------------------


class TestDeadlineHandler:
    @pytest.mark.asyncio
    async def test_no_task_board(self, dispatcher: ActionDispatcher) -> None:
        candidate = _make_candidate(
            action_type="deadline_action",
            target="COLM_abstract",
        )
        result = await dispatcher.handle(candidate)
        assert result["executed"] is False

    @pytest.mark.asyncio
    async def test_creates_urgent_task(self, ctx: SwarmContext) -> None:
        ctx.task_board = AsyncMock()
        ctx.task_board.add = AsyncMock(return_value="deadline_1")
        d = ActionDispatcher(context=ctx)

        candidate = _make_candidate(
            action_type="deadline_action",
            target="COLM_abstract",
            description="COLM abstract deadline in 8 days",
        )
        result = await d.handle(candidate)
        assert result["executed"] is True
        assert result.get("task_id") == "deadline_1"


# ---------------------------------------------------------------------------
# Filesystem check handler tests
# ---------------------------------------------------------------------------


class TestFilesystemCheckHandler:
    @pytest.mark.asyncio
    async def test_filesystem_check_passes(self, dispatcher: ActionDispatcher) -> None:
        mock_verification = MagicMock()
        mock_verification.passed = True
        mock_verification.prediction_error = 0.1

        with patch(
            "dharma_swarm.action_dispatch.ActionDispatcher._handle_filesystem_check",
            new_callable=lambda: lambda: AsyncMock(return_value={
                "executed": True, "summary": "fs check passed", "passed": True,
            }),
        ):
            # Direct handler call
            candidate = _make_candidate(
                action_type="filesystem_check",
                target="/tmp/test",
            )
            # Use the actual handler with mocked verify_action
            with patch("dharma_swarm.environmental_verifier.verify_action", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = mock_verification
                result = await dispatcher.handle(candidate)
                assert result["executed"] is True


# ---------------------------------------------------------------------------
# Deliberation wiring tests
# ---------------------------------------------------------------------------


class TestDeliberationWiring:
    @pytest.mark.asyncio
    async def test_slow_path_triggers_deliberation(self, ctx: SwarmContext) -> None:
        delib = MagicMock()
        delib_result = MagicMock()
        delib_result.decision = "allow"
        delib_result.used_arbitration = False
        delib.deliberate.return_value = delib_result

        d = ActionDispatcher(context=ctx, deliberation=delib)

        candidate = _make_candidate(
            action_type="health_check",
            complexity_route=ComplexityRoute.SLOW,
            percept_data={},
        )
        await d.handle(candidate)
        delib.deliberate.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliberation_block(self, ctx: SwarmContext) -> None:
        delib = MagicMock()
        delib_result = MagicMock()
        delib_result.decision = "block"
        delib_result.reason = "S5 says no"
        delib.deliberate.return_value = delib_result

        d = ActionDispatcher(context=ctx, deliberation=delib)

        candidate = _make_candidate(
            action_type="health_check",
            complexity_route=ComplexityRoute.SLOW,
            percept_data={},
        )
        result = await d.handle(candidate)
        assert result["executed"] is False
        assert "deliberation_blocked" in result.get("reason", "")


# ---------------------------------------------------------------------------
# Status method test
# ---------------------------------------------------------------------------


class TestDispatcherStatus:
    def test_status_reports(self, dispatcher: ActionDispatcher) -> None:
        status = dispatcher.status()
        assert "experience_total" in status
        assert "handlers" in status
        assert "health_check" in status["handlers"]
        assert status["viveka_attached"] is False
        assert status["deliberation_attached"] is False
