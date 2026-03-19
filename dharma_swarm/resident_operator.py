"""Resident Operator — the persistent entity that IS dharma_swarm's interface.

Composes SwarmManager, OperatorBridge, ConversationStore, GraduationEngine,
and PersistentAgent into a single long-lived process. Accessible from any thin
client (TUI, CLI, web, phone) via WebSocket or HTTP SSE.

Design: compose existing infrastructure, don't rebuild.
- SwarmManager: all subsystem access
- OperatorBridge: task lifecycle (enqueue/claim/ack)
- ConversationStore: persistent conversation history
- GraduationEngine: autonomy level management
- PersistentAgent: wake cycle for proactive scanning
- QualityForge: YSD scoring for graduation
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from dharma_swarm.conversation_store import ConversationStore
from dharma_swarm.graduation_engine import (
    AutonomyLevel,
    GraduationEngine,
    RiskLevel,
)
from dharma_swarm.models import (
    AgentRole,
    Message,
    MessagePriority,
    ProviderType,
    _new_id,
)

logger = logging.getLogger(__name__)

# Default operator port
OPERATOR_PORT = 8420


@dataclass
class OperatorEvent:
    """A streaming event from the operator to clients."""

    event_type: str  # text_delta | tool_call | tool_result | notification | done | error
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    msg_id: str = ""
    seq: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type,
            "content": self.content,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "msg_id": self.msg_id,
            "seq": self.seq,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ---------------------------------------------------------------------------
# Operator system prompt (INVARIANT + MUTABLE + ADAPTIVE)
# ---------------------------------------------------------------------------

_INVARIANT_PROMPT = """\
You are the Resident Operator of dharma_swarm — a persistent conductor agent \
with native access to every subsystem. You are NOT a chatbot. You ARE the system.

IDENTITY:
- Name: operator
- Role: CONDUCTOR
- Telos: Jagat Kalyan (universal welfare)
- You serve Dhyana (John Shrader), the system's creator and operator.

SAFETY (NEVER violate):
- All actions pass through telos gates. Gate BLOCK = hard stop.
- CRITICAL actions always require human approval regardless of autonomy level.
- You cannot modify the dharma kernel (10 SHA-256 signed axioms).
- You cannot delete witness logs or evolution archives.
- When uncertain, propose — don't execute.
"""

_MUTABLE_PROMPT = """\
APPROACH:
- Be direct. Lead with answers, not reasoning.
- Use subsystem tools natively — never shell out to `claude -p`.
- For system queries: check stigmergy, message bus, task board, health monitor.
- For code tasks: delegate to specialist agents via the swarm.
- For evolution: use DarwinEngine + QualityForge pipeline.
- Cost awareness: use free providers (Ollama Cloud, NVIDIA NIM) for proactive \
scans. Use OpenRouter for user conversations.

TONE:
- Terse, technical, honest.
- No filler, no encouragement, no emoji.
- State what's broken before what works.
"""


def build_operator_prompt(
    swarm_state: str = "",
    stigmergy_context: str = "",
    conversation_summary: str = "",
) -> str:
    """Assemble the full operator system prompt with adaptive sections filled."""
    parts = [_INVARIANT_PROMPT, _MUTABLE_PROMPT]

    if swarm_state:
        parts.append(f"\nCURRENT SWARM STATE:\n{swarm_state}")
    if stigmergy_context:
        parts.append(f"\nSTIGMERGY (recent signals):\n{stigmergy_context}")
    if conversation_summary:
        parts.append(f"\nCONVERSATION CONTEXT:\n{conversation_summary}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ResidentOperator
# ---------------------------------------------------------------------------

class ResidentOperator:
    """The persistent operator agent that IS the system's interface.

    Single process, single event loop. No subprocess overhead. Native Python
    calls to every subsystem.
    """

    def __init__(
        self,
        name: str = "operator",
        model: str = "anthropic/claude-sonnet-4",
        provider_type: ProviderType = ProviderType.OPENROUTER,
        wake_interval: float = 300.0,
        state_dir: Path | None = None,
        base_system_prompt: str | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.provider_type = provider_type
        self.wake_interval = wake_interval
        self.state_dir = state_dir or Path.home() / ".dharma"
        self.base_system_prompt = (base_system_prompt or "").strip()

        # Core subsystems — set during start()
        self._swarm: Any = None  # SwarmManager
        self._bridge: Any = None  # OperatorBridge
        self._conversations = ConversationStore()
        self._graduation = GraduationEngine()

        # Runtime state
        self._running = False
        self._shutdown = asyncio.Event()
        self._proactive_task: asyncio.Task | None = None
        self._start_time: float = 0.0
        self._interaction_count: int = 0
        self._connected_clients: set[str] = set()

        # Event broadcast channel: client_id -> asyncio.Queue
        self._client_queues: dict[str, asyncio.Queue[OperatorEvent]] = {}

        # Evolution (lazy-loaded in Phase 3)
        self._evolver: Any = None

    def set_swarm(self, swarm: Any) -> None:
        """Inject the SwarmManager instance (called by api/main.py lifespan)."""
        self._swarm = swarm

    async def start(self) -> None:
        """Initialize all subsystems and start proactive scanning."""
        logger.info("ResidentOperator starting...")
        self._start_time = time.time()

        # Init conversation store
        await self._conversations.init_db()
        logger.info("ConversationStore initialized")

        # Init graduation engine
        await self._graduation.init_db()
        logger.info(
            "GraduationEngine initialized (level=%s)",
            self._graduation.level.name,
        )

        # Init SwarmManager if not already set
        if self._swarm is None:
            from dharma_swarm.swarm import SwarmManager
            self._swarm = SwarmManager(state_dir=self.state_dir)

        # Init OperatorBridge (needs message bus + session ledger)
        try:
            from dharma_swarm.message_bus import MessageBus
            from dharma_swarm.operator_bridge import OperatorBridge
            from dharma_swarm.session_ledger import SessionLedger
            from dharma_swarm.runtime_state import RuntimeStateStore

            bus_path = self.state_dir / "db" / "messages.db"
            bus = MessageBus(bus_path)
            await bus.init_db()

            runtime_db_path = self.state_dir / "state" / "runtime.db"
            ledger = SessionLedger(
                base_dir=self.state_dir / "ledgers",
                runtime_db_path=runtime_db_path,
            )
            state_store = RuntimeStateStore(runtime_db_path)

            self._bridge = OperatorBridge(
                message_bus=bus,
                ledger=ledger,
                runtime_state=state_store,
            )
            await self._bridge.init_db()
            logger.info("OperatorBridge initialized")
        except Exception as e:
            logger.warning("OperatorBridge init failed (non-fatal): %s", e)

        # Start proactive scan loop
        self._running = True
        self._proactive_task = asyncio.create_task(self._proactive_loop())
        logger.info("ResidentOperator started (port=%d)", OPERATOR_PORT)

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("ResidentOperator stopping...")
        self._running = False
        self._shutdown.set()

        if self._proactive_task:
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except asyncio.CancelledError:
                pass

        await self._conversations.close()
        await self._graduation.close()
        logger.info("ResidentOperator stopped")

    # -- Message handling (the core loop) -----------------------------------

    async def handle_message(
        self,
        session_id: str,
        content: str,
        client_id: str = "",
    ) -> AsyncIterator[OperatorEvent]:
        """Process a user message and yield streaming operator events.

        This is the main entry point for all client interactions.
        """
        self._interaction_count += 1
        msg_id = _new_id()

        # Ensure session exists
        await self._conversations.create_session(session_id, client_id)

        # Persist user turn
        _, user_seq = await self._conversations.add_turn(
            session_id, "user", content,
        )

        if self.provider_type == ProviderType.CODEX:
            async for event in self._handle_codex_message(
                session_id=session_id,
                msg_id=msg_id,
                user_seq=user_seq,
            ):
                yield event
            return
        if self.provider_type == ProviderType.CLAUDE_CODE:
            async for event in self._handle_claude_code_message(
                session_id=session_id,
                msg_id=msg_id,
                user_seq=user_seq,
            ):
                yield event
            return

        # Build context
        system_prompt = await self._build_system_prompt(session_id)
        _, messages = await self._conversations.build_messages_for_api(
            session_id, system_prompt,
        )

        # Yield thinking indicator
        yield OperatorEvent(
            event_type="text_delta",
            content="",
            session_id=session_id,
            msg_id=msg_id,
            seq=user_seq + 1,
        )

        # Execute via LLM
        response_text = ""
        tool_calls: list[dict] = []
        tool_results: list[dict] = []

        try:
            response_text, tool_calls, tool_results = await self._execute_llm(
                system_prompt, messages, session_id, msg_id,
            )
        except Exception as e:
            error_msg = f"Operator error: {e}"
            logger.error(error_msg)
            yield OperatorEvent(
                event_type="error",
                content=error_msg,
                session_id=session_id,
                msg_id=msg_id,
            )
            response_text = error_msg

        # Yield the response
        if response_text:
            yield OperatorEvent(
                event_type="text_delta",
                content=response_text,
                session_id=session_id,
                msg_id=msg_id,
            )

        # Yield tool calls/results if any
        for tc in tool_calls:
            yield OperatorEvent(
                event_type="tool_call",
                content=json.dumps(tc),
                metadata={"tool": tc.get("name", "")},
                session_id=session_id,
                msg_id=msg_id,
            )
        for tr in tool_results:
            yield OperatorEvent(
                event_type="tool_result",
                content=tr.get("summary", ""),
                session_id=session_id,
                msg_id=msg_id,
            )

        # Persist assistant turn
        _, assistant_seq = await self._conversations.add_turn(
            session_id, "assistant", response_text,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

        # Post-process: quality scoring + graduation
        ysd_score = await self._score_response(response_text)
        await self._graduation.record_action(
            action_type="user_message",
            success=True,
            ysd_score=ysd_score,
        )

        # Shadow evolution check (every 10th interaction)
        if self._evolver and self._interaction_count % 10 == 0:
            try:
                await self._evolver.maybe_shadow_evaluate(
                    self._interaction_count, content, response_text, ysd_score,
                )
            except Exception as e:
                logger.debug("Shadow eval failed: %s", e)

        # Done event
        yield OperatorEvent(
            event_type="done",
            session_id=session_id,
            msg_id=msg_id,
            seq=assistant_seq,
            metadata={
                "ysd_score": ysd_score,
                "autonomy_level": self._graduation.level.name,
            },
        )

    async def _handle_codex_message(
        self,
        *,
        session_id: str,
        msg_id: str,
        user_seq: int,
    ) -> AsyncIterator[OperatorEvent]:
        """Stream a message through the local Codex CLI adapter."""
        from dharma_swarm.tui.engine.adapters.base import CompletionRequest
        from dharma_swarm.tui.engine.adapters.codex import CodexAdapter

        system_prompt = await self._build_system_prompt(session_id)
        session = await self._conversations.get_session(session_id)
        session_metadata = dict(session.get("metadata", {}) or {}) if session else {}
        provider_session_id = str(
            session_metadata.get("provider_session_id", "") or ""
        ).strip() or None
        _, messages = await self._conversations.build_messages_for_api(
            session_id, system_prompt,
        )

        yield OperatorEvent(
            event_type="text_delta",
            content="",
            session_id=session_id,
            msg_id=msg_id,
            seq=user_seq + 1,
        )

        adapter = CodexAdapter(workdir=Path.home() / "dharma_swarm")
        response_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        error_message = ""

        try:
            request = CompletionRequest(
                messages=messages,
                model=self.model,
                system_prompt=system_prompt,
                resume_session_id=provider_session_id,
                provider_options={
                    "add_dirs": [str(self.state_dir)],
                },
            )

            async for event in adapter.stream(request, session_id):
                event_type = getattr(event, "type", "")

                if event_type == "session_start":
                    resumed_provider_session_id = str(
                        getattr(event, "provider_session_id", "") or ""
                    ).strip()
                    if resumed_provider_session_id:
                        provider_session_id = resumed_provider_session_id
                        await self._conversations.update_session_metadata(
                            session_id,
                            {
                                "provider": "codex",
                                "model": self.model,
                                "provider_session_id": resumed_provider_session_id,
                            },
                        )
                    continue

                if event_type in {"text_complete", "text_delta"}:
                    text = str(getattr(event, "content", "") or "")
                    if not text.strip():
                        continue
                    response_parts.append(text)
                    yield OperatorEvent(
                        event_type="text_delta",
                        content=text,
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "tool_call_complete":
                    tool_name = str(getattr(event, "tool_name", "") or "")
                    arguments_raw = str(getattr(event, "arguments", "") or "")
                    try:
                        parsed_args = json.loads(arguments_raw) if arguments_raw else {}
                    except json.JSONDecodeError:
                        parsed_args = {"raw": arguments_raw}
                    tool_call = {
                        "id": str(getattr(event, "tool_call_id", "") or ""),
                        "name": tool_name,
                        "args": parsed_args,
                    }
                    tool_calls.append(tool_call)
                    yield OperatorEvent(
                        event_type="tool_call",
                        content=json.dumps({"name": tool_name, "args": parsed_args}),
                        metadata={"tool": tool_name},
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "tool_result":
                    tool_name = str(getattr(event, "tool_name", "") or "")
                    raw_content = str(getattr(event, "content", "") or "")
                    summary = raw_content[:150].replace("\n", " ")
                    tool_results.append(
                        {
                            "tool_call_id": str(getattr(event, "tool_call_id", "") or ""),
                            "name": tool_name,
                            "summary": summary,
                            "content": raw_content,
                            "is_error": bool(getattr(event, "is_error", False)),
                        }
                    )
                    yield OperatorEvent(
                        event_type="tool_result",
                        content=summary,
                        metadata={"tool": tool_name},
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "error":
                    error_message = str(getattr(event, "message", "") or "")
                    yield OperatorEvent(
                        event_type="error",
                        content=error_message,
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "session_end":
                    if not bool(getattr(event, "success", True)):
                        candidate = str(getattr(event, "error_message", "") or "")
                        if candidate:
                            error_message = candidate
        finally:
            await adapter.close()

        response_text = "\n\n".join(part.strip() for part in response_parts if part.strip())
        if not response_text and error_message:
            response_text = f"[codex resident error] {error_message}"

        _, assistant_seq = await self._conversations.add_turn(
            session_id,
            "assistant",
            response_text,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

        ysd_score = await self._score_response(response_text)
        await self._graduation.record_action(
            action_type="user_message",
            success=not bool(error_message),
            ysd_score=ysd_score,
        )

        yield OperatorEvent(
            event_type="done",
            session_id=session_id,
            msg_id=msg_id,
            seq=assistant_seq,
            metadata={
                "ysd_score": ysd_score,
                "autonomy_level": self._graduation.level.name,
                "provider": "codex_resident",
            },
        )

    async def _handle_claude_code_message(
        self,
        *,
        session_id: str,
        msg_id: str,
        user_seq: int,
    ) -> AsyncIterator[OperatorEvent]:
        """Stream a message through the local Claude Code adapter."""
        from dharma_swarm.tui.engine.adapters.base import CompletionRequest
        from dharma_swarm.tui.engine.adapters.claude import ClaudeAdapter

        system_prompt = await self._build_system_prompt(session_id)
        session = await self._conversations.get_session(session_id)
        session_metadata = dict(session.get("metadata", {}) or {}) if session else {}
        provider_session_id = str(
            session_metadata.get("provider_session_id", "") or ""
        ).strip() or None
        _, messages = await self._conversations.build_messages_for_api(
            session_id, system_prompt,
        )

        yield OperatorEvent(
            event_type="text_delta",
            content="",
            session_id=session_id,
            msg_id=msg_id,
            seq=user_seq + 1,
        )

        adapter = ClaudeAdapter(workdir=Path.home() / "dharma_swarm")
        response_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        error_message = ""

        try:
            request = CompletionRequest(
                messages=messages,
                model=self.model,
                system_prompt=system_prompt,
                resume_session_id=provider_session_id,
                provider_options={
                    "add_dirs": [str(self.state_dir)],
                },
            )

            async for event in adapter.stream(request, session_id):
                event_type = getattr(event, "type", "")

                if event_type == "session_start":
                    resumed_provider_session_id = str(
                        getattr(event, "provider_session_id", "") or ""
                    ).strip()
                    if resumed_provider_session_id:
                        provider_session_id = resumed_provider_session_id
                        await self._conversations.update_session_metadata(
                            session_id,
                            {
                                "provider": "claude",
                                "model": self.model,
                                "provider_session_id": resumed_provider_session_id,
                            },
                        )
                    continue

                if event_type in {"text_complete", "text_delta"}:
                    text = str(getattr(event, "content", "") or "")
                    if not text.strip():
                        continue
                    response_parts.append(text)
                    yield OperatorEvent(
                        event_type="text_delta",
                        content=text,
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "tool_call_complete":
                    tool_name = str(getattr(event, "tool_name", "") or "")
                    arguments_raw = str(getattr(event, "arguments", "") or "")
                    try:
                        parsed_args = json.loads(arguments_raw) if arguments_raw else {}
                    except json.JSONDecodeError:
                        parsed_args = {"raw": arguments_raw}
                    tool_call = {
                        "id": str(getattr(event, "tool_call_id", "") or ""),
                        "name": tool_name,
                        "args": parsed_args,
                    }
                    tool_calls.append(tool_call)
                    yield OperatorEvent(
                        event_type="tool_call",
                        content=json.dumps({"name": tool_name, "args": parsed_args}),
                        metadata={"tool": tool_name},
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "tool_result":
                    tool_name = str(getattr(event, "tool_name", "") or "")
                    raw_content = str(getattr(event, "content", "") or "")
                    summary = raw_content[:150].replace("\n", " ")
                    tool_results.append(
                        {
                            "tool_call_id": str(getattr(event, "tool_call_id", "") or ""),
                            "name": tool_name,
                            "summary": summary,
                            "content": raw_content,
                            "is_error": bool(getattr(event, "is_error", False)),
                        }
                    )
                    yield OperatorEvent(
                        event_type="tool_result",
                        content=summary,
                        metadata={"tool": tool_name},
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "error":
                    error_message = str(getattr(event, "message", "") or "")
                    yield OperatorEvent(
                        event_type="error",
                        content=error_message,
                        session_id=session_id,
                        msg_id=msg_id,
                    )
                    continue

                if event_type == "session_end":
                    if not bool(getattr(event, "success", True)):
                        candidate = str(getattr(event, "error_message", "") or "")
                        if candidate:
                            error_message = candidate
        finally:
            await adapter.close()

        response_text = "\n\n".join(part.strip() for part in response_parts if part.strip())
        if not response_text and error_message:
            response_text = f"[claude resident error] {error_message}"

        _, assistant_seq = await self._conversations.add_turn(
            session_id,
            "assistant",
            response_text,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

        ysd_score = await self._score_response(response_text)
        await self._graduation.record_action(
            action_type="user_message",
            success=not bool(error_message),
            ysd_score=ysd_score,
        )

        yield OperatorEvent(
            event_type="done",
            session_id=session_id,
            msg_id=msg_id,
            seq=assistant_seq,
            metadata={
                "ysd_score": ysd_score,
                "autonomy_level": self._graduation.level.name,
                "provider": "claude_resident",
            },
        )

    # -- LLM execution (composes existing providers) ------------------------

    async def _execute_llm(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        session_id: str,
        msg_id: str,
    ) -> tuple[str, list[dict], list[dict]]:
        """Execute an LLM call using the swarm's provider router.

        Returns (response_text, tool_calls, tool_results).
        """
        tool_calls: list[dict] = []
        tool_results: list[dict] = []

        # Try using AutonomousAgent for full ReAct loop
        try:
            from dharma_swarm.autonomous_agent import AgentIdentity, AutonomousAgent

            identity = AgentIdentity(
                name=self.name,
                role="conductor",
                system_prompt=system_prompt,
                model=self.model,
                provider="openrouter",
                max_turns=10,
                working_directory=str(Path.home() / "dharma_swarm"),
            )
            agent = AutonomousAgent(identity)

            # The last user message is the task
            task = messages[-1]["content"] if messages else ""
            result = await agent.run(task)

            return result.summary, tool_calls, tool_results

        except Exception as agent_err:
            logger.debug("AutonomousAgent fallback: %s", agent_err)

        # Fallback: direct provider call
        try:
            from dharma_swarm.providers import create_default_router
            router = create_default_router()

            api_messages = [{"role": "system", "content": system_prompt}]
            api_messages.extend(messages)

            response = await router.complete(
                model=self.model,
                messages=api_messages,
                max_tokens=4096,
                temperature=0.7,
            )
            return response.content, tool_calls, tool_results

        except Exception as provider_err:
            logger.error("Provider fallback failed: %s", provider_err)
            return f"[operator offline — provider error: {provider_err}]", [], []

    # -- System prompt construction -----------------------------------------

    async def _build_system_prompt(self, session_id: str) -> str:
        """Build the full system prompt with live state context."""
        del session_id
        swarm_state = ""
        stigmergy_ctx = ""

        # Get swarm state summary
        if self._swarm:
            try:
                state = self._swarm.get_state()
                swarm_state = (
                    f"Agents: {len(state.agents)} | "
                    f"Tasks pending: {state.tasks_pending} | "
                    f"Tasks running: {state.tasks_running} | "
                    f"Uptime: {state.uptime_seconds:.0f}s"
                )
            except Exception:
                pass

        # Get stigmergy signals
        try:
            from dharma_swarm.stigmergy import StigmergyStore
            stig = StigmergyStore()
            marks = await stig.high_salience(threshold=0.7, limit=3)
            if marks:
                stigmergy_ctx = "\n".join(
                    f"- [{m.agent}] {m.observation[:100]}" for m in marks
                )
        except Exception:
            pass

        if self.base_system_prompt:
            parts = [self.base_system_prompt]
            if swarm_state:
                parts.append(f"LIVE SWARM STATE:\n{swarm_state}")
            if stigmergy_ctx:
                parts.append(f"RECENT STIGMERGY:\n{stigmergy_ctx}")
            return "\n\n".join(parts)

        return build_operator_prompt(
            swarm_state=swarm_state,
            stigmergy_context=stigmergy_ctx,
        )

    # -- Quality scoring ----------------------------------------------------

    async def _score_response(self, response_text: str) -> float:
        """Score the operator's response quality. Returns YSD score."""
        if not response_text or len(response_text) < 10:
            return 5.0

        # Use QualityForge behavioral scoring
        try:
            from dharma_swarm.ouroboros import score_behavioral_fitness
            from dharma_swarm.metrics import MetricsAnalyzer

            analyzer = MetricsAnalyzer()
            _, modifiers = score_behavioral_fitness(response_text, analyzer=analyzer)
            quality = modifiers.get("quality", 0.5)

            # Map quality [0,1] to YSD range [5.0, 5.15]
            return 5.0 + 0.15 * quality

        except Exception:
            # Fallback: simple heuristic
            length_score = min(1.0, len(response_text) / 500)
            return 5.0 + 0.15 * length_score * 0.5

    # -- Proactive scanning -------------------------------------------------

    async def _proactive_loop(self) -> None:
        """Background loop that checks for things to notify the operator about."""
        logger.info("Proactive scan loop started (interval=%ds)", self.wake_interval)

        while self._running:
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self.wake_interval,
                )
                break  # shutdown signaled
            except asyncio.TimeoutError:
                pass

            if not self._running:
                break

            try:
                events = await self._proactive_scan()
                for event in events:
                    await self._broadcast(event)
            except Exception as e:
                logger.debug("Proactive scan error: %s", e)

    async def _proactive_scan(self) -> list[OperatorEvent]:
        """Check system state and generate notification events."""
        events: list[OperatorEvent] = []

        # Check high-salience stigmergy
        try:
            from dharma_swarm.stigmergy import StigmergyStore
            stig = StigmergyStore()
            marks = await stig.high_salience(threshold=0.9, limit=3)
            for mark in marks:
                events.append(OperatorEvent(
                    event_type="notification",
                    content=f"High-salience signal: [{mark.agent}] {mark.observation[:200]}",
                    metadata={"severity": "info", "source": "stigmergy"},
                ))
        except Exception:
            pass

        # Check for stale tasks in the bridge
        if self._bridge:
            try:
                stale_ids = await self._bridge.timeout_expired_claims()
                for tid in stale_ids:
                    events.append(OperatorEvent(
                        event_type="notification",
                        content=f"Stale task recovered: {tid}",
                        metadata={"severity": "warning", "source": "bridge"},
                    ))
            except Exception:
                pass

        return events

    # -- Client management --------------------------------------------------

    def register_client(self, client_id: str) -> asyncio.Queue[OperatorEvent]:
        """Register a client and return its event queue."""
        q: asyncio.Queue[OperatorEvent] = asyncio.Queue(maxsize=1000)
        self._client_queues[client_id] = q
        self._connected_clients.add(client_id)
        return q

    def unregister_client(self, client_id: str) -> None:
        """Remove a client from the broadcast list."""
        self._client_queues.pop(client_id, None)
        self._connected_clients.discard(client_id)

    async def _broadcast(self, event: OperatorEvent) -> None:
        """Send an event to all connected clients."""
        for client_id, queue in list(self._client_queues.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Client %s queue full, dropping event", client_id)

    # -- Status -------------------------------------------------------------

    def status_dict(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time if self._start_time else 0
        return {
            "name": self.name,
            "running": self._running,
            "uptime_seconds": round(uptime),
            "model": self.model,
            "provider": self.provider_type.value,
            "interaction_count": self._interaction_count,
            "connected_clients": len(self._connected_clients),
            "graduation": self._graduation.status_dict(),
        }


__all__ = [
    "ResidentOperator",
    "OperatorEvent",
    "build_operator_prompt",
    "OPERATOR_PORT",
]
