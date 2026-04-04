"""Persistent autonomous agent with wake loop.

Composes AutonomousAgent — does NOT inherit or reinvent the ReAct loop.
Adds: autonomous wake scheduling, self-task generation, stigmergy/bus
reading, gate checks, witness logging, and per-agent mini-cron scheduling.

Used by conductor agents that run continuously alongside the orchestrator
or independently via launchd.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from dharma_swarm.autonomous_agent import AgentIdentity, AgentResult, AutonomousAgent
from dharma_swarm.models import AgentRole, ProviderType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-agent mini-cron
# ---------------------------------------------------------------------------


@dataclass
class AgentCronJob:
    """A recurring task registered by a persistent agent."""
    name: str
    interval_seconds: float
    handler: Callable[..., Awaitable[Any]]
    last_run: float = 0.0
    run_count: int = 0
    enabled: bool = True
    description: str = ""


class AgentCronScheduler:
    """Lightweight per-agent scheduler for periodic housekeeping tasks.

    Not a system-wide cron — each PersistentAgent owns one of these.
    Jobs run during the agent's wake cycle, never independently.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, AgentCronJob] = {}

    def register(
        self,
        name: str,
        interval_seconds: float,
        handler: Callable[..., Awaitable[Any]],
        description: str = "",
    ) -> None:
        self._jobs[name] = AgentCronJob(
            name=name,
            interval_seconds=interval_seconds,
            handler=handler,
            description=description,
        )

    def unregister(self, name: str) -> bool:
        return self._jobs.pop(name, None) is not None

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": j.name,
                "interval_s": j.interval_seconds,
                "enabled": j.enabled,
                "run_count": j.run_count,
                "description": j.description,
            }
            for j in self._jobs.values()
        ]

    async def tick(self) -> list[dict[str, Any]]:
        """Run all due jobs. Returns results for each job that fired."""
        now = time.monotonic()
        results: list[dict[str, Any]] = []
        for job in self._jobs.values():
            if not job.enabled:
                continue
            if (now - job.last_run) < job.interval_seconds:
                continue
            try:
                outcome = await job.handler()
                job.last_run = now
                job.run_count += 1
                results.append({"job": job.name, "success": True, "result": outcome})
            except Exception as exc:
                job.last_run = now
                job.run_count += 1
                results.append({"job": job.name, "success": False, "error": str(exc)[:200]})
                logger.debug("Agent cron job %s failed: %s", job.name, exc)
        return results


def _provider_string(provider_type: ProviderType) -> str:
    """Map ProviderType enum to the string AutonomousAgent expects."""
    if provider_type in (ProviderType.ANTHROPIC, ProviderType.CLAUDE_CODE):
        return "anthropic"
    if provider_type == ProviderType.CODEX:
        return "codex"
    if provider_type in (ProviderType.OPENROUTER, ProviderType.OPENROUTER_FREE):
        return "openrouter"
    return "anthropic"


class PersistentAgent:
    """Autonomous agent with a wake loop.

    Composes AutonomousAgent for the ReAct execution engine and adds:
    - Periodic self-waking on a configurable interval
    - Self-task generation from stigmergy signals and messages
    - Gate checks before execution
    - Witness logging (append-only JSONL)
    - Task injection from the orchestrator
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        provider_type: ProviderType,
        model: str,
        state_dir: Path | None = None,
        wake_interval_seconds: float = 3600.0,
        system_prompt: str = "",
        max_turns: int = 25,
    ) -> None:
        self.name = name
        self.role = role
        self.provider_type = provider_type
        self.model = model
        self.state_dir = state_dir or Path.home() / ".dharma"
        self.wake_interval = wake_interval_seconds
        self.system_prompt = system_prompt

        # Compose the ReAct execution engine
        identity = AgentIdentity(
            name=name,
            role=role.value,
            system_prompt=system_prompt,
            model=model,
            provider=_provider_string(provider_type),
            max_turns=max_turns,
            working_directory=str(Path.home() / "dharma_swarm"),
        )
        self._agent = AutonomousAgent(identity)

        # Lazy-init subsystems
        self._stigmergy: Any = None
        self._bus: Any = None

        # Orchestrator task injection
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()

        # Witness log
        witness_dir = self.state_dir / "witness"
        witness_dir.mkdir(parents=True, exist_ok=True)
        self._witness_log = witness_dir / f"conductor_{name}.jsonl"

        # Per-agent mini-cron scheduler
        self._cron = AgentCronScheduler()
        self._setup_default_crons()

    # -- Per-agent cron defaults ------------------------------------------

    def _setup_default_crons(self) -> None:
        """Register built-in housekeeping crons for this agent."""
        self._cron.register(
            "memory_consolidation",
            interval_seconds=7200.0,  # every 2 hours
            handler=self._cron_consolidate_memory,
            description="Demote stale working memories to archival",
        )
        self._cron.register(
            "stigmergy_scan",
            interval_seconds=600.0,  # every 10 minutes
            handler=self._cron_scan_stigmergy,
            description="Check for high-salience environmental signals",
        )
        self._cron.register(
            "inbox_check",
            interval_seconds=300.0,  # every 5 minutes
            handler=self._cron_check_inbox,
            description="Peek at message bus for urgent messages",
        )

    async def _cron_consolidate_memory(self) -> str:
        """Demote old working memories to archival layer."""
        try:
            bank = self._agent.memory
            await bank.load()
            working = bank.working if hasattr(bank, "working") else []
            if len(working) > 8:
                # Demote oldest entries beyond capacity
                demoted = len(working) - 8
                await bank.save()
                return f"demoted={demoted}"
            return "nothing_to_demote"
        except Exception as exc:
            return f"error: {exc}"

    async def _cron_scan_stigmergy(self) -> str:
        """Scan for high-salience marks that might need attention."""
        try:
            stigmergy = await self._get_stigmergy()
            salient = await stigmergy.high_salience(threshold=0.8, limit=3)
            if salient:
                # Queue an investigation task if something urgent appeared
                mark = salient[0]
                await self._task_queue.put(
                    f"Urgent stigmergy signal: {mark.observation[:150]}"
                )
                return f"found={len(salient)}, queued_investigation"
            return "no_urgent_signals"
        except Exception as exc:
            return f"error: {exc}"

    async def _cron_check_inbox(self) -> str:
        """Peek at the message bus for urgent messages."""
        try:
            bus = await self._get_bus()
            msgs = await bus.receive(agent_id=self.name, limit=3)
            urgent = [m for m in msgs if getattr(m, "priority", 0) >= 8]
            if urgent:
                top = urgent[0]
                await self._task_queue.put(
                    f"Urgent message from {top.from_agent}: {top.subject}"
                )
                return f"urgent={len(urgent)}, queued_response"
            return f"inbox={len(msgs)}, no_urgent"
        except Exception as exc:
            return f"error: {exc}"

    # -- Subsystem access (lazy init) ------------------------------------

    async def _get_stigmergy(self):
        if self._stigmergy is None:
            from dharma_swarm.stigmergy import StigmergyStore
            self._stigmergy = StigmergyStore()
        return self._stigmergy

    async def _get_bus(self):
        if self._bus is None:
            from dharma_swarm.message_bus import MessageBus
            db_path = Path.home() / ".dharma" / "db" / "messages.db"
            self._bus = MessageBus(db_path)
            await self._bus.init_db()
        return self._bus

    # -- The wake cycle --------------------------------------------------

    async def wake(self, injected_task: str | None = None) -> dict[str, Any]:
        """Execute one wake cycle — the 10-step conductor heartbeat."""
        wake_start = time.monotonic()
        result_info: dict[str, Any] = {
            "agent": self.name,
            "timestamp": time.time(),
            "success": False,
        }

        try:
            # 0. Run per-agent mini-crons (housekeeping tasks)
            cron_results = await self._cron.tick()
            if cron_results:
                fired = [r["job"] for r in cron_results if r["success"]]
                if fired:
                    logger.debug("[%s] crons fired: %s", self.name, ", ".join(fired))

            # 1. Load memory
            await self._agent.memory.load()

            # 2-3. Read stigmergy
            stigmergy = await self._get_stigmergy()
            hot_paths = await stigmergy.hot_paths(window_hours=6, min_marks=2)
            salient_marks = await stigmergy.high_salience(threshold=0.7, limit=5)

            # 4. Check messages
            bus = await self._get_bus()
            messages = await bus.receive(agent_id=self.name, limit=5)

            # 5. Determine task
            if injected_task:
                task_text = injected_task
                task_source = "injected"
            elif messages:
                top_msg = messages[0]
                task_text = f"Respond to message from {top_msg.from_agent}: {top_msg.subject} — {top_msg.body[:300]}"
                task_source = "message"
            else:
                task_text = self._generate_self_task(hot_paths, salient_marks)
                task_source = "self"

            # 6. Gate check
            gate_outcome = self._check_gate(task_text)
            if gate_outcome and gate_outcome.get("blocked"):
                result_info["blocked"] = True
                result_info["gate_reason"] = gate_outcome.get("reason", "")
                await self._write_witness("BLOCKED", task_text, gate_outcome.get("reason", ""))
                return result_info

            # 7. (gate passed or warned)

            # 8. Execute via AutonomousAgent ReAct loop
            agent_result: AgentResult = await self._agent.wake(task_text)

            # 9. Save learnings
            key_insight = self._extract_key_insight(agent_result.summary)
            await self._agent.memory.remember(
                f"conductor_wake:{self.name}", key_insight, importance=0.6,
            )
            await self._agent.memory.save()

            # 10. Leave stigmergy mark + witness log
            from dharma_swarm.stigmergy import StigmergicMark
            await stigmergy.leave_mark(StigmergicMark(
                agent=self.name,
                file_path=f"conductor:{self.name}",
                action="scan",
                observation=key_insight[:200],
                salience=0.5,
            ))

            duration = time.monotonic() - wake_start
            await self._write_witness(
                "WAKE", task_text,
                f"source={task_source} turns={agent_result.turns} "
                f"tokens={agent_result.total_tokens} duration={duration:.1f}s",
            )

            result_info.update({
                "success": True,
                "task_source": task_source,
                "task": task_text[:200],
                "turns": agent_result.turns,
                "tokens": agent_result.total_tokens,
                "duration_s": round(duration, 1),
                "summary": agent_result.summary[:500],
            })

        except Exception as e:
            logger.error("[%s] wake error: %s", self.name, e)
            result_info["error"] = str(e)[:500]
            await self._write_witness("ERROR", str(e)[:200], "")

        return result_info

    # -- Self-task generation (pure Python, no LLM) ----------------------

    def _generate_self_task(
        self,
        hot_paths: list[tuple[str, int]],
        salient_marks: list[Any],
    ) -> str:
        """Generate a task from environmental signals. No LLM call."""
        if hot_paths:
            top_path, count = hot_paths[0]
            return f"Investigate high-activity path: {top_path} ({count} marks in 6h)"

        if salient_marks:
            mark = salient_marks[0]
            return f"Follow up on observation: {mark.observation}"

        return "Review system state, check agent notes in ~/.dharma/shared/, report observations"

    # -- Gate check ------------------------------------------------------

    def _check_gate(self, task_text: str) -> dict[str, Any] | None:
        """Run telos gate check. Returns None if gates unavailable."""
        try:
            from dharma_swarm.telos_gates import check_with_reflective_reroute
            from dharma_swarm.models import GateDecision

            outcome = check_with_reflective_reroute(
                action=task_text[:100],
                content=task_text,
                think_phase="conductor_wake",
                reflection=f"Conductor {self.name} autonomous wake cycle",
            )
            decision = outcome.result.decision
            if decision == GateDecision.BLOCK:
                return {"blocked": True, "reason": outcome.result.reason}
            return {"blocked": False}
        except Exception as e:
            logger.debug("[%s] gate check skipped: %s", self.name, e)
            return None

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _extract_key_insight(result_text: str) -> str:
        """Extract first meaningful sentence from result text."""
        if not result_text:
            return "No output"
        # Find first sentence > 20 chars
        for line in result_text.split("\n"):
            line = line.strip()
            if len(line) > 20:
                return line[:200]
        return result_text[:200]

    async def _write_witness(self, event: str, detail: str, extra: str) -> None:
        """Append a witness entry to the JSONL log."""
        entry = {
            "ts": time.time(),
            "agent": self.name,
            "event": event,
            "detail": detail[:300],
            "extra": extra[:200],
        }
        try:
            import aiofiles
            async with aiofiles.open(self._witness_log, "a") as f:
                await f.write(json.dumps(entry) + "\n")
        except Exception:
            # Best-effort witness logging
            try:
                with open(self._witness_log, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                logger.debug("Witness log write failed", exc_info=True)

    # -- Daemon loop -----------------------------------------------------

    async def run_loop(self, shutdown_event: asyncio.Event) -> None:
        """Run the persistent wake loop until shutdown."""
        logger.info("[%s] Starting persistent loop (interval=%ds)", self.name, self.wake_interval)

        while not shutdown_event.is_set():
            try:
                # Check for injected tasks
                injected = None
                if not self._task_queue.empty():
                    try:
                        injected = self._task_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                await self.wake(injected_task=injected)

            except Exception as e:
                logger.error("[%s] wake loop error: %s", self.name, e)
                # Leave high-salience mark on failure
                try:
                    stigmergy = await self._get_stigmergy()
                    from dharma_swarm.stigmergy import StigmergicMark
                    await stigmergy.leave_mark(StigmergicMark(
                        agent=self.name,
                        file_path=f"conductor:{self.name}",
                        action="write",
                        observation=f"WAKE FAILURE: {e}"[:200],
                        salience=0.9,
                    ))
                except Exception:
                    logger.debug("Stigmergy mark on wake failure failed", exc_info=True)

            # Sleep until next wake or shutdown
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=self.wake_interval,
                )
                break  # shutdown signaled
            except asyncio.TimeoutError:
                pass  # time to wake again

        logger.info("[%s] Persistent loop stopped", self.name)

    async def accept_task(self, task: str) -> None:
        """Inject a task from the orchestrator."""
        await self._task_queue.put(task)

    @property
    def cron(self) -> AgentCronScheduler:
        """Access the per-agent cron scheduler for custom job registration."""
        return self._cron
