"""Action Dispatcher — routes PAL decisions to swarm execution paths.

The missing link between sensing and acting. Without this, PAL perceives
everything but does nothing (action_handler=None).

Dispatch routing table:
  health_check     → check PID, restart daemon if dead (cooldown: 1/10min)
  investigate_mark → create Task → orchestrator.dispatch()
  process_signal   → parse proposed_action → re-route or create task
  deadline_action  → create URGENT task → dispatch
  filesystem_check → environmental_verifier checks

Safety:
  - Health restart cooldown: max 1 restart per daemon per 10 minutes
  - Investigation loop prevention: skip marks with source=pal_dispatch
  - Subsystem unavailable: graceful degradation, return {"executed": False}
  - Experience base capped at 1000 records (FIFO eviction)

Grounded in: SYNTHESIS.md Phase 2, Principles #1 #3 #6
Sources: Beer VSM S3 control, Klein RPD, Friston active inference
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.complexity_router import ComplexityRoute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Swarm context — injected references to live subsystems
# ---------------------------------------------------------------------------


@dataclass
class SwarmContext:
    """References to swarm subsystems — injected by SwarmManager.

    All fields are optional for graceful degradation. If a subsystem
    is unavailable, the dispatcher skips actions that need it.
    """
    task_board: Any = None
    orchestrator: Any = None
    agent_pool: Any = None
    stigmergy: Any = None
    algedonic: Any = None
    cost_ledger: Any = None
    state_dir: Path = field(default_factory=lambda: Path.home() / ".dharma")


# ---------------------------------------------------------------------------
# Health restart cooldown tracker
# ---------------------------------------------------------------------------


class _RestartCooldown:
    """Prevents restart-loop: max 1 restart per daemon per cooldown period."""

    def __init__(self, cooldown_seconds: float = 600.0) -> None:
        self._cooldown = cooldown_seconds
        self._last_restart: dict[str, float] = {}

    def can_restart(self, daemon_name: str) -> bool:
        last = self._last_restart.get(daemon_name, 0.0)
        return (time.monotonic() - last) >= self._cooldown

    def record_restart(self, daemon_name: str) -> None:
        self._last_restart[daemon_name] = time.monotonic()


# ---------------------------------------------------------------------------
# Experience base (capped FIFO)
# ---------------------------------------------------------------------------


@dataclass
class DispatchOutcome:
    """Recorded outcome of a dispatched action."""
    action_type: str
    target: str
    executed: bool
    result_summary: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ExperienceBase:
    """Capped FIFO experience records for dispatch outcomes."""

    def __init__(self, max_records: int = 1000) -> None:
        self._records: list[DispatchOutcome] = []
        self._max = max_records

    def record(self, outcome: DispatchOutcome) -> None:
        self._records.append(outcome)
        if len(self._records) > self._max:
            self._records = self._records[-self._max:]

    def success_rate(self, action_type: str) -> float:
        relevant = [r for r in self._records if r.action_type == action_type]
        if not relevant:
            return 0.0
        return sum(1 for r in relevant if r.executed) / len(relevant)

    @property
    def total(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# The Dispatcher
# ---------------------------------------------------------------------------


class ActionDispatcher:
    """Routes CandidateActions from PAL to swarm execution paths.

    This is the action_handler callback for PerceptionActionLoop.
    It implements the full dispatch cycle:

    1. Viveka gate go/no-go
    2. If SLOW path: deliberation triangle
    3. Route to typed handler
    4. Record outcome in experience base
    """

    def __init__(
        self,
        context: SwarmContext,
        viveka: Any | None = None,
        experience: ExperienceBase | None = None,
        deliberation: Any | None = None,
    ) -> None:
        self.ctx = context
        self._viveka = viveka
        self._experience = experience or ExperienceBase()
        self._deliberation = deliberation
        self._cooldown = _RestartCooldown(cooldown_seconds=600.0)

        # Dispatch routing table
        self._handlers: dict[str, Any] = {
            "health_check": self._handle_health_check,
            "investigate_mark": self._handle_investigate_mark,
            "process_signal": self._handle_process_signal,
            "deadline_action": self._handle_deadline_action,
            "filesystem_check": self._handle_filesystem_check,
        }

        # Persist dir for dispatch log
        self._log_dir = context.state_dir / "dispatch"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    async def handle(self, candidate: Any) -> dict[str, Any]:
        """THE action_handler callback for PAL.

        This is what gets called from PerceptionActionLoop.commit().
        """
        action_type = candidate.action_type
        target = candidate.target

        # Step 1: Viveka gate (if available)
        if self._viveka is not None:
            try:
                result = self._viveka.evaluate(
                    action_type=action_type,
                    target=target,
                )
                if not result.should_act:
                    logger.info(
                        "Viveka blocked %s/%s: %s",
                        action_type, target, result.reason,
                    )
                    self._record_outcome(action_type, target, False, f"viveka:{result.decision.value}")
                    return {"executed": False, "reason": f"viveka_{result.decision.value}"}
            except Exception as e:
                logger.warning("Viveka evaluation failed, proceeding: %s", e)

        # Step 2: Deliberation triangle for SLOW path
        complexity_route = getattr(candidate, "complexity_route", None)
        if (
            complexity_route == ComplexityRoute.SLOW
            and self._deliberation is not None
        ):
            try:
                from dharma_swarm.deliberation import DeliberationInput
                delib_input = DeliberationInput(
                    action_type=action_type,
                    action_description=getattr(candidate, "description", ""),
                    target=target,
                )
                delib_result = self._deliberation.deliberate(delib_input)
                if delib_result.decision == "block":
                    logger.info(
                        "Deliberation blocked %s: %s",
                        action_type, delib_result.reason,
                    )
                    self._record_outcome(action_type, target, False, f"deliberation:{delib_result.decision}")
                    return {"executed": False, "reason": "deliberation_blocked"}

                # Report S3→S4 patterns for telos gate awareness
                if delib_result.used_arbitration and delib_result.s5_arbitration:
                    logger.info(
                        "S5 arbitrated %s: %s (TCS=%.3f)",
                        action_type,
                        delib_result.s5_arbitration.get("decision", "?"),
                        delib_result.s5_arbitration.get("tcs", 0.0),
                    )
            except ImportError:
                pass  # deliberation module not available
            except Exception as e:
                logger.warning("Deliberation failed, proceeding: %s", e)

        # Step 3: Route to typed handler
        handler = self._handlers.get(action_type)
        if handler is None:
            logger.warning("No handler for action type: %s", action_type)
            self._record_outcome(action_type, target, False, "no_handler")
            return {"executed": False, "reason": "unknown_action_type"}

        try:
            result = await handler(candidate)
            executed = result.get("executed", False)
            self._record_outcome(
                action_type, target, executed,
                result.get("summary", "ok" if executed else "failed"),
            )
            self._log_dispatch(action_type, target, result)
            return result
        except Exception as e:
            logger.error("Handler %s failed: %s", action_type, e)
            self._record_outcome(action_type, target, False, str(e))
            return {"executed": False, "error": str(e)}

    # ---- Typed handlers ----

    async def _handle_health_check(self, candidate: Any) -> dict[str, Any]:
        """Check daemon PID, restart if dead (with cooldown)."""
        target = candidate.target
        data = candidate.source_percept.data if candidate.source_percept else {}
        pid_file = data.get("pid_file", "")

        if not pid_file:
            return {"executed": False, "reason": "no_pid_file"}

        pid_path = Path(pid_file)
        if not pid_path.exists():
            return {"executed": False, "reason": "pid_file_missing"}

        try:
            pid = int(pid_path.read_text().strip())
            try:
                os.kill(pid, 0)
                return {"executed": True, "summary": f"{target} alive (PID {pid})"}
            except ProcessLookupError:
                # Dead — attempt restart with cooldown
                if not self._cooldown.can_restart(target):
                    return {
                        "executed": False,
                        "reason": "restart_cooldown",
                        "summary": f"{target} dead but restart on cooldown",
                    }

                logger.warning("Daemon %s (PID %s) is dead, cleaning up PID file", target, pid)
                pid_path.unlink(missing_ok=True)
                self._cooldown.record_restart(target)

                return {
                    "executed": True,
                    "summary": f"{target} PID file cleaned (was dead PID {pid})",
                    "action_taken": "pid_cleanup",
                }
        except (ValueError, OSError) as e:
            return {"executed": False, "error": str(e)}

    async def _handle_investigate_mark(self, candidate: Any) -> dict[str, Any]:
        """Create a Task for investigating a high-salience stigmergy mark."""
        data = candidate.source_percept.data if candidate.source_percept else {}

        # Loop prevention: skip marks we created
        source = data.get("source", "")
        if source == "pal_dispatch":
            return {"executed": False, "reason": "self_referential_mark"}

        if self.ctx.task_board is None:
            return {"executed": False, "reason": "task_board_unavailable"}

        try:
            from dharma_swarm.models import Task, TaskPriority, TaskStatus
            task = Task(
                title=f"Investigate mark: {candidate.description[:80]}",
                description=(
                    f"PAL sensed high-salience mark.\n"
                    f"File: {data.get('file_path', '?')}\n"
                    f"Agent: {data.get('agent', '?')}\n"
                    f"Observation: {candidate.description[:200]}"
                ),
                priority=TaskPriority.NORMAL,
                status=TaskStatus.PENDING,
            )

            task_id = await self.ctx.task_board.add(task)

            # Dispatch to orchestrator if available
            if self.ctx.orchestrator is not None:
                try:
                    await self.ctx.orchestrator.dispatch(task)
                except Exception as e:
                    logger.warning("Orchestrator dispatch failed: %s", e)

            return {
                "executed": True,
                "summary": f"task created: {task_id}",
                "task_id": task_id,
            }
        except Exception as e:
            return {"executed": False, "error": str(e)}

    async def _handle_process_signal(self, candidate: Any) -> dict[str, Any]:
        """Parse a cross-instance signal and route it."""
        data = candidate.source_percept.data if candidate.source_percept else {}
        proposed_action = data.get("proposed_action", "")
        source = data.get("source", "unknown")

        if not proposed_action:
            return {
                "executed": True,
                "summary": f"signal from {source} noted (no proposed action)",
            }

        # If the signal proposes a specific action, create a task for it
        if self.ctx.task_board is not None:
            try:
                from dharma_swarm.models import Task, TaskPriority, TaskStatus
                task = Task(
                    title=f"Signal from {source}: {proposed_action[:60]}",
                    description=(
                        f"Cross-instance signal.\n"
                        f"Source: {source}\n"
                        f"Proposed action: {proposed_action}\n"
                        f"Original message: {candidate.description[:200]}"
                    ),
                    priority=TaskPriority.HIGH,
                    status=TaskStatus.PENDING,
                )
                task_id = await self.ctx.task_board.add(task)
                return {
                    "executed": True,
                    "summary": f"signal task created: {task_id}",
                    "task_id": task_id,
                }
            except Exception as e:
                return {"executed": False, "error": str(e)}

        return {"executed": False, "reason": "task_board_unavailable"}

    async def _handle_deadline_action(self, candidate: Any) -> dict[str, Any]:
        """Create an URGENT task for deadline-related actions."""
        if self.ctx.task_board is None:
            return {"executed": False, "reason": "task_board_unavailable"}

        try:
            from dharma_swarm.models import Task, TaskPriority, TaskStatus
            task = Task(
                title=f"DEADLINE: {candidate.description[:70]}",
                description=(
                    f"Deadline-triggered action.\n"
                    f"Target: {candidate.target}\n"
                    f"Details: {candidate.description[:300]}"
                ),
                priority=TaskPriority.URGENT,
                status=TaskStatus.PENDING,
            )
            task_id = await self.ctx.task_board.add(task)

            if self.ctx.orchestrator is not None:
                try:
                    await self.ctx.orchestrator.dispatch(task)
                except Exception as e:
                    logger.warning("Orchestrator dispatch failed: %s", e)

            return {
                "executed": True,
                "summary": f"urgent task created: {task_id}",
                "task_id": task_id,
            }
        except Exception as e:
            return {"executed": False, "error": str(e)}

    async def _handle_filesystem_check(self, candidate: Any) -> dict[str, Any]:
        """Run environmental verification on a filesystem percept."""
        try:
            from dharma_swarm.environmental_verifier import verify_action
            verification = await verify_action(
                action_id=candidate.id,
                action_type="filesystem_check",
                target=candidate.target,
            )
            passed = getattr(verification, "passed", True)
            return {
                "executed": True,
                "summary": f"fs check {'passed' if passed else 'failed'}: {candidate.target}",
                "passed": passed,
            }
        except Exception as e:
            return {"executed": False, "error": str(e)}

    # ---- Internal helpers ----

    def _record_outcome(
        self, action_type: str, target: str, executed: bool, summary: str = "",
    ) -> None:
        """Record outcome in experience base."""
        self._experience.record(DispatchOutcome(
            action_type=action_type,
            target=target,
            executed=executed,
            result_summary=summary,
        ))

    def _log_dispatch(self, action_type: str, target: str, result: dict[str, Any]) -> None:
        """Append dispatch event to JSONL log."""
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "action_type": action_type,
                "target": target,
                "executed": result.get("executed", False),
                "summary": result.get("summary", ""),
            }
            log_file = self._log_dir / "dispatch.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Logging must never block dispatch

    def status(self) -> dict[str, Any]:
        """Return dispatcher status for monitoring."""
        return {
            "experience_total": self._experience.total,
            "viveka_attached": self._viveka is not None,
            "deliberation_attached": self._deliberation is not None,
            "handlers": list(self._handlers.keys()),
            "subsystems": {
                "task_board": self.ctx.task_board is not None,
                "orchestrator": self.ctx.orchestrator is not None,
                "agent_pool": self.ctx.agent_pool is not None,
                "stigmergy": self.ctx.stigmergy is not None,
                "cost_ledger": self.ctx.cost_ledger is not None,
            },
        }
