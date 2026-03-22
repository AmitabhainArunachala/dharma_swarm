"""Persistent autonomous agent with wake loop.

Composes AutonomousAgent — does NOT inherit or reinvent the ReAct loop.
Adds: autonomous wake scheduling, self-task generation, stigmergy/bus
reading, gate checks, and witness logging.

Used by conductor agents that run continuously alongside the orchestrator
or independently via launchd.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from dharma_swarm.autonomous_agent import AgentIdentity, AgentResult, AutonomousAgent
from dharma_swarm.models import AgentRole, ProviderType

logger = logging.getLogger(__name__)


def _provider_string(provider_type: ProviderType) -> str:
    """Map ProviderType enum to the string AutonomousAgent expects."""
    if provider_type in (ProviderType.ANTHROPIC, ProviderType.CLAUDE_CODE):
        return "anthropic"
    if provider_type == ProviderType.CODEX:
        logger.warning(
            "ProviderType.CODEX passed to PersistentAgent — remapping to 'anthropic'. "
            "If this agent uses an Anthropic model, set provider_type=ANTHROPIC instead."
        )
        return "anthropic"
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
