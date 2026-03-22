"""DHARMA COMMAND — Agentic chat endpoint with full tool access.

Claude Opus 4.6 via OpenRouter, with tool-use loop that gives it
real system power: filesystem, shell, search, swarm control,
evolution, stigmergy, traces.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.chat_tools import TOOL_DEFINITIONS, execute_tool
from api.ws import manager

CONVERSATIONS_DIR = Path.home() / ".dharma" / "conversations"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])
ws_router = APIRouter(tags=["chat"])

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-opus-4-6"
DEFAULT_MAX_TOOL_ROUNDS = 40
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_TOOL_RESULT_MAX_CHARS = 24000
DEFAULT_HISTORY_MESSAGE_LIMIT = 120
DEFAULT_TEMPERATURE = 0.3
DEFAULT_PROFILE_ID = "claude_opus"
CHAT_CONTRACT_VERSION = "2026-03-19.chat.v1"
QWEN_MAX_TOOL_ROUNDS = 24
CHAT_WS_PATH_TEMPLATE = "/ws/chat/session/{session_id}"
MAX_CHAT_SESSION_EVENTS = 96
MAX_CHAT_SESSION_COUNT = 128

_chat_session_events: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
_chat_session_lock = Lock()


@dataclass(frozen=True)
class ChatProfileSpec:
    profile_id: str
    label: str
    default_model: str
    model_env: str
    accent: str
    summary: str
    system_prompt: str


@dataclass(frozen=True)
class ChatRuntimeSettings:
    openrouter_api_key: str
    model: str
    max_tool_rounds: int
    max_tokens: int
    timeout_seconds: float
    tool_result_max_chars: int
    history_message_limit: int
    temperature: float


def _default_profile_id() -> str:
    configured = os.getenv("DASHBOARD_DEFAULT_PROFILE_ID", "").strip()
    if configured and configured in CHAT_PROFILE_SPECS:
        return configured
    return DEFAULT_PROFILE_ID


COMMAND_SYSTEM_PROMPT = """\
You are Claude Opus 4.6 operating as the DHARMA COMMAND console — the brain \
of a neo-Tokyo swarm intelligence system. You are NOT a chatbot. You are the \
command intelligence with FULL SYSTEM ACCESS.

You have tools. USE THEM. When asked about the system, don't guess — read \
files, query traces, check swarm status. When asked to fix something — edit \
the file, run the tests, verify the fix.

Your tools:
- read_file / write_file / edit_file — full filesystem access (~dharma_swarm/, ~/.dharma/)
- shell_exec — run any shell command (tests, git, processes, logs)
- grep_search / glob_files — search codebase and files
- swarm_status — live agent states, health, anomalies
- evolution_query — archive entries, fitness trends, lineage chains
- stigmergy_query — pheromone marks, hot paths, high salience
- trace_query — full trace payloads with filters
- agent_control — spawn, stop, inspect agents

Approach:
1. Gather data with tools before answering
2. Be specific — cite file paths, line numbers, exact values
3. When fixing code: read → edit → test → verify
4. When diagnosing: status → traces → logs → root cause

The operator is John "Dhyana" Shrader — senior consciousness + AI researcher, \
24 years contemplative practice. No hand-holding. Brutal truth. Concise answers. \
Technical precision. You are the swarm's nervous system — act like it."""


CODEX_SYSTEM_PROMPT = """\
You are Codex 5.4 operating as the embedded implementation agent inside the \
DHARMA COMMAND control plane. You are a coding and systems operator, not a \
generic assistant.

Use tools aggressively and concretely. Prefer direct inspection over inference. \
When asked to improve the system, make the smallest high-leverage change that \
moves the architecture, UI, or runtime forward.

Priorities:
1. inspect real files and state before acting
2. implement rather than speculate
3. keep changes operationally honest
4. verify with commands or tests when feasible
5. surface concrete blockers, not vague caveats

You have the same tool surface as the command console:
- read_file / write_file / edit_file
- shell_exec
- grep_search / glob_files
- swarm_status
- evolution_query
- stigmergy_query
- trace_query
- agent_control

This agent exists to help the operator steer, repair, and evolve the swarm from \
inside the UI. Bias toward engineering leverage, clean diffs, and exactness."""


QWEN_SYSTEM_PROMPT = """\
You are Qwen3 Coder operating as the surgical reconnaissance and repair lane \
inside the DHARMA COMMAND control plane.

You are here for fast technical execution: inspect code, trace interfaces, edit \
small surfaces precisely, and validate with concrete evidence.

Operating rules:
1. prefer bounded reconnaissance over exhaustive repo sweeps
2. inspect the smallest relevant slice before branching wider
3. when a prompt is broad, produce the highest-leverage next slice instead of looping forever
4. use tools directly and keep answers operational
5. when changing code: inspect, patch, verify

You have the same control-plane tools as the other dashboard profiles:
- read_file / write_file / edit_file
- shell_exec
- grep_search / glob_files
- swarm_status
- evolution_query
- stigmergy_query
- trace_query
- agent_control

This lane should feel sharp, fast, and mechanically useful, not chatty."""


GLM_SYSTEM_PROMPT = """\
You are GLM-5 operating as the research synthesizer and systems cartographer \
inside the DHARMA COMMAND control plane.

You are here for deep investigation, synthesis, and architecture mapping:
trace relationships, inspect evidence, summarize patterns, and produce clear \
operator-ready findings without drifting into generic prose.

Operating rules:
1. ground every synthesis in inspected files, traces, or state
2. compress large surfaces into actionable maps, not vague summaries
3. prefer causal structure, cross-system links, and evidence trails
4. use tools to verify before asserting
5. leave the operator with the next best decision, not just observations

You have the same control-plane tools as the other dashboard profiles:
- read_file / write_file / edit_file
- shell_exec
- grep_search / glob_files
- swarm_status
- evolution_query
- stigmergy_query
- trace_query
- agent_control

This lane should feel investigative, synthetic, and operationally sharp."""


CHAT_PROFILE_SPECS: dict[str, ChatProfileSpec] = {
    "claude_opus": ChatProfileSpec(
        profile_id="claude_opus",
        label="Claude Opus 4.6",
        default_model=DEFAULT_MODEL,
        model_env="DASHBOARD_CHAT_MODEL",
        accent="aozora",
        summary="Strategic operator with broad system awareness and full swarm tooling.",
        system_prompt=COMMAND_SYSTEM_PROMPT,
    ),
    "codex_operator": ChatProfileSpec(
        profile_id="codex_operator",
        label="Codex 5.4",
        default_model="openai/gpt-5-codex",
        model_env="DASHBOARD_CODEX_MODEL",
        accent="kinpaku",
        summary="Implementation-focused control agent for edits, diagnostics, and fast wiring.",
        system_prompt=CODEX_SYSTEM_PROMPT,
    ),
    "qwen35_surgeon": ChatProfileSpec(
        profile_id="qwen35_surgeon",
        label="Qwen3 Coder",
        default_model="qwen/qwen3-coder",
        model_env="DASHBOARD_QWEN_MODEL",
        accent="rokusho",
        summary="Fast surgical coding lane for bounded repo scans, edits, and validation.",
        system_prompt=QWEN_SYSTEM_PROMPT,
    ),
    "glm5_researcher": ChatProfileSpec(
        profile_id="glm5_researcher",
        label="GLM-5 Research",
        default_model="z-ai/glm-5",
        model_env="DASHBOARD_GLM_MODEL",
        accent="botan",
        summary="Research synthesis lane for ecosystem mapping, pattern extraction, and deep analysis.",
        system_prompt=GLM_SYSTEM_PROMPT,
    ),
}


def _parse_int_env(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _parse_float_env(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _get_profile_spec(profile_id: str | None) -> ChatProfileSpec:
    return CHAT_PROFILE_SPECS.get(profile_id or "", CHAT_PROFILE_SPECS[_default_profile_id()])


def _get_chat_settings(profile_id: str | None = None) -> ChatRuntimeSettings:
    profile = _get_profile_spec(profile_id)
    model = os.getenv(profile.model_env, "").strip() or profile.default_model
    settings = ChatRuntimeSettings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        model=model,
        max_tool_rounds=_parse_int_env(
            "DASHBOARD_CHAT_MAX_TOOL_ROUNDS",
            DEFAULT_MAX_TOOL_ROUNDS,
            minimum=1,
        ),
        max_tokens=_parse_int_env(
            "DASHBOARD_CHAT_MAX_TOKENS",
            DEFAULT_MAX_TOKENS,
            minimum=256,
        ),
        timeout_seconds=_parse_float_env(
            "DASHBOARD_CHAT_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
            minimum=5.0,
        ),
        tool_result_max_chars=_parse_int_env(
            "DASHBOARD_CHAT_TOOL_RESULT_MAX_CHARS",
            DEFAULT_TOOL_RESULT_MAX_CHARS,
            minimum=1000,
        ),
        history_message_limit=_parse_int_env(
            "DASHBOARD_CHAT_HISTORY_MESSAGE_LIMIT",
            DEFAULT_HISTORY_MESSAGE_LIMIT,
            minimum=1,
        ),
        temperature=_parse_float_env(
            "DASHBOARD_CHAT_TEMPERATURE",
            DEFAULT_TEMPERATURE,
            minimum=0.0,
        ),
    )
    if profile.profile_id == "qwen35_surgeon":
        return replace(
            settings,
            max_tool_rounds=min(settings.max_tool_rounds, QWEN_MAX_TOOL_ROUNDS),
        )
    return settings


def _profile_available(settings: ChatRuntimeSettings) -> bool:
    return bool(settings.openrouter_api_key)


def _profile_status_note(settings: ChatRuntimeSettings) -> str:
    if settings.openrouter_api_key:
        return "Served by the dashboard backend via OpenRouter."
    return "Requires OPENROUTER_API_KEY on the backend."


def _new_session_id() -> str:
    return f"dash-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def _chat_channel(session_id: str) -> str:
    return (
        CHAT_WS_PATH_TEMPLATE.replace("{session_id}", session_id)
        .removeprefix("/ws/")
        .strip("/")
    )


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _event_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return str(value)


def _remember_chat_event(session_id: str, payload: dict[str, Any]) -> None:
    if not session_id:
        return
    with _chat_session_lock:
        bucket = _chat_session_events.get(session_id)
        if bucket is None:
            bucket = deque(maxlen=MAX_CHAT_SESSION_EVENTS)
            _chat_session_events[session_id] = bucket
        else:
            _chat_session_events.move_to_end(session_id)
        bucket.append(payload)
        while len(_chat_session_events) > MAX_CHAT_SESSION_COUNT:
            _chat_session_events.popitem(last=False)


def _chat_session_event_snapshot(session_id: str) -> list[dict[str, Any]]:
    with _chat_session_lock:
        bucket = _chat_session_events.get(session_id)
        if not bucket:
            return []
        return [dict(event) for event in bucket]


def _chat_session_turn_snapshot(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for event in events:
        if event.get("event") == "chat_user_turn":
            turns.append(
                {
                    "role": "user",
                    "content": _event_text(event.get("content")).strip(),
                    "timestamp": str(event.get("timestamp", "")),
                }
            )
        elif event.get("event") == "chat_assistant_turn":
            turns.append(
                {
                    "role": "assistant",
                    "content": _event_text(event.get("content")).strip(),
                    "timestamp": str(event.get("timestamp", "")),
                }
            )
    return turns


async def _publish_chat_event(
    session_id: str,
    event: str,
    *,
    profile_id: str = "",
    **fields: Any,
) -> dict[str, Any]:
    payload = {
        "event": event,
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if profile_id:
        payload["profile_id"] = profile_id
    payload.update(fields)
    _remember_chat_event(session_id, payload)
    await manager.broadcast(_chat_channel(session_id), payload)
    return payload


class ChatMessage(BaseModel):
    role: str
    content: Any = None  # str or list for tool results
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str | None = None
    profile_id: str | None = None


async def _gather_brief_context() -> str:
    """Quick context summary for system prompt."""
    parts = []
    try:
        from api.main import get_swarm, get_monitor
        swarm = get_swarm()
        try:
            status = await swarm.status()
            parts.append(
                f"Agents: {len(status.agents)} "
                f"(running={status.tasks_running}, completed={status.tasks_completed})"
            )
        except Exception:
            logger.debug("Failed to gather swarm status for brief context", exc_info=True)

        monitor = get_monitor()
        try:
            report = await monitor.check_health()
            hs = report.overall_status.value if hasattr(report.overall_status, "value") else str(report.overall_status)
            parts.append(f"Health: {hs}, traces={report.total_traces}")
        except Exception:
            logger.debug("Failed to gather health report for brief context", exc_info=True)
    except Exception:
        logger.debug("Failed to import swarm/monitor for brief context", exc_info=True)
    return " | ".join(parts) if parts else "(context unavailable)"


async def _call_openrouter(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict | None:
    """Make a (non-streaming) call to OpenRouter with tools."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "DHARMA COMMAND",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            detail = resp.text[:500]
            try:
                payload = resp.json()
                error = payload.get("error", {})
                metadata = error.get("metadata", {})
                detail = str(metadata.get("raw") or error.get("message") or detail)
            except json.JSONDecodeError:
                pass
            detail = " ".join(detail.split())
            logger.error("OpenRouter error %d: %s", resp.status_code, detail)
            raise RuntimeError(f"OpenRouter {resp.status_code}: {detail[:240]}")
        return resp.json()


async def _call_openrouter_stream(messages: list[dict], settings: ChatRuntimeSettings):
    """Streaming call to OpenRouter (no tools — final response only)."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "DHARMA COMMAND",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": True,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        async with client.stream("POST", OPENROUTER_URL, headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                yield f"data: {json.dumps({'error': f'OpenRouter {response.status_code}: {body.decode()[:200]}'})}\n\n"
                return

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    yield "data: [DONE]\n\n"
                    return

                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield f"data: {json.dumps({'content': content})}\n\n"
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue


def _extract_assistant_content(message: dict[str, Any]) -> str:
    """Normalize assistant content across provider variants."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


async def _agentic_stream(
    messages_for_api: list[dict],
    settings: ChatRuntimeSettings,
    *,
    session_id: str = "",
    profile_id: str = "",
):
    """Run the agentic tool-use loop, streaming the final response.

    Flow:
    1. Call OpenRouter (non-streaming) with tools
    2. If response has tool_calls → execute tools, emit status events, loop
    3. When response is pure text → stream it to the client
    """

    messages = list(messages_for_api)
    tool_round = 0

    while tool_round < settings.max_tool_rounds:
        tool_round += 1

        # Non-streaming call to detect tool use
        try:
            result = await _call_openrouter(messages, settings)
        except Exception as exc:
            if session_id:
                await _publish_chat_event(
                    session_id,
                    "chat_error",
                    profile_id=profile_id,
                    error=str(exc),
                )
                await _publish_chat_event(
                    session_id,
                    "chat_done",
                    profile_id=profile_id,
                    stopped="error",
                )
            yield _sse_data({"error": str(exc)})
            yield "data: [DONE]\n\n"
            return

        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # Check for tool calls
        tool_calls = msg.get("tool_calls")

        if tool_calls:
            # Append assistant message with tool calls to conversation
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or None,
                "tool_calls": tool_calls,
            })

            # If there's text content before tools, stream it
            if msg.get("content"):
                yield _sse_data({"content": msg["content"]})

            # Execute each tool call
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}
                tool_id = tc.get("id", "")

                # Emit tool status to frontend
                if session_id:
                    await _publish_chat_event(
                        session_id,
                        "chat_tool_call",
                        profile_id=profile_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )
                yield _sse_data({"tool_call": {"name": tool_name, "args": tool_args}})

                # Execute
                tool_result = await execute_tool(tool_name, tool_args)

                # Truncate huge results
                if len(tool_result) > settings.tool_result_max_chars:
                    tool_result = (
                        tool_result[: settings.tool_result_max_chars] + "\n... (truncated)"
                    )

                # Emit summary to frontend
                summary = tool_result[:150].replace("\n", " ")
                if session_id:
                    await _publish_chat_event(
                        session_id,
                        "chat_tool_result",
                        profile_id=profile_id,
                        tool_name=tool_name,
                        summary=summary,
                    )
                yield _sse_data({"tool_result": {"name": tool_name, "summary": summary}})

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result,
                })

            # Continue the loop — Claude may want more tools or give final answer
            continue

        # No tool calls — this is the final text response. Stream it.
        final_content = _extract_assistant_content(msg)
        if final_content:
            # Unified conversation log — capture assistant response
            try:
                from dharma_swarm.conversation_log import log_exchange
                log_exchange(
                    "assistant",
                    final_content,
                    interface="api",
                    session_id=session_id or None,
                    metadata={
                        "model": settings.model,
                        "profile_id": profile_id,
                    },
                )
            except Exception:
                logger.debug("Failed to log assistant response to conversation log", exc_info=True)
            # We already have the full text from the non-streaming call.
            # Send it in chunks to maintain SSE feel.
            chunk_size = 20
            for i in range(0, len(final_content), chunk_size):
                chunk = final_content[i : i + chunk_size]
                if session_id:
                    await _publish_chat_event(
                        session_id,
                        "chat_text",
                        profile_id=profile_id,
                        content=chunk,
                    )
                yield _sse_data({"content": chunk})
            if session_id:
                await _publish_chat_event(
                    session_id,
                    "chat_assistant_turn",
                    profile_id=profile_id,
                    content=final_content,
                )
        else:
            model_note = settings.model
            if msg.get("reasoning"):
                if session_id:
                    await _publish_chat_event(
                        session_id,
                        "chat_error",
                        profile_id=profile_id,
                        error=(
                            f"{model_note} returned reasoning without visible output. "
                            "Retry, lower the lane complexity, or switch models."
                        ),
                    )
                    await _publish_chat_event(
                        session_id,
                        "chat_done",
                        profile_id=profile_id,
                        stopped="error",
                    )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "error": (
                                f"{model_note} returned reasoning without visible output. "
                                "Retry, lower the lane complexity, or switch models."
                            )
                        }
                    )
                    + "\n\n"
                )
                yield "data: [DONE]\n\n"
                return

        if session_id:
            await _publish_chat_event(
                session_id,
                "chat_done",
                profile_id=profile_id,
                stopped="complete",
                provider="openrouter",
            )
        yield "data: [DONE]\n\n"
        return

    # Safety: hit max rounds
    if session_id:
        await _publish_chat_event(
            session_id,
            "chat_assistant_turn",
            profile_id=profile_id,
            content="\n\n[Reached maximum tool rounds. Stopping.]",
        )
        await _publish_chat_event(
            session_id,
            "chat_done",
            profile_id=profile_id,
            stopped="max_tool_rounds",
            provider="openrouter",
        )
    yield _sse_data({"content": "\n\n[Reached maximum tool rounds. Stopping.]"})
    yield "data: [DONE]\n\n"


def _log_conversation(messages: list[dict], session_id: str = "", profile_id: str = ""):
    """Persist conversation messages to ~/.dharma/conversations/ as JSONL."""
    try:
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = CONVERSATIONS_DIR / f"dashboard_{today}.jsonl"
        now = datetime.now(timezone.utc).isoformat()

        with open(log_path, "a") as f:
            for m in messages:
                if m.get("role") == "system":
                    continue  # Don't log system prompts
                record = {
                    "role": m.get("role", ""),
                    "content": m.get("content", "")[:5000],  # Cap content size
                    "timestamp": now,
                    "session_id": session_id,
                    "source": "dashboard",
                    "profile_id": profile_id,
                }
                f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.warning("Failed to log conversation: %s", e)


@router.post("/chat")
async def chat_stream(req: ChatRequest):
    """Agentic SSE streaming chat with Claude Opus 4.6."""
    profile = _get_profile_spec(req.profile_id)
    settings = _get_chat_settings(profile.profile_id)

    if not settings.openrouter_api_key:
        return StreamingResponse(
            iter(['data: {"error": "OPENROUTER_API_KEY not set"}\n\n']),
            media_type="text/event-stream",
        )

    # Log incoming messages server-side for distillation
    session_id = _new_session_id()
    _log_conversation(
        [{"role": m.role, "content": m.content} for m in req.messages],
        session_id=session_id,
        profile_id=profile.profile_id,
    )
    # Unified conversation log — capture user messages from dashboard
    try:
        from dharma_swarm.conversation_log import log_exchange
        for m in req.messages:
            if m.role == "user":
                log_exchange(
                    "user", m.content, interface="api",
                    session_id=session_id,
                    metadata={"profile_id": profile.profile_id},
                )
    except Exception:
        logger.debug("Failed to log user messages to conversation log", exc_info=True)

    # Brief context for system prompt
    brief = await _gather_brief_context()
    system_prompt = profile.system_prompt + f"\n\n[Live: {brief}]"

    # Build messages for API
    api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in req.messages:
        api_messages.append({"role": m.role, "content": m.content})

    latest_user_message = next(
        (
            _event_text(message.content).strip()
            for message in reversed(req.messages)
            if message.role == "user" and _event_text(message.content).strip()
        ),
        "",
    )

    async def stream():
        yield _sse_data({"session_id": session_id})
        await _publish_chat_event(
            session_id,
            "chat_session_ready",
            profile_id=profile.profile_id,
            provider="openrouter",
            model=settings.model,
        )
        if latest_user_message:
            await _publish_chat_event(
                session_id,
                "chat_user_turn",
                profile_id=profile.profile_id,
                content=latest_user_message,
            )
        async for chunk in _agentic_stream(
            api_messages,
            settings,
            session_id=session_id,
            profile_id=profile.profile_id,
        ):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/distill")
async def trigger_distill(hours_back: float = 24):
    """Manually trigger conversation distillation."""
    from dharma_swarm.conversation_distiller import distill
    result = distill(hours_back=hours_back)
    return result


@router.get("/chat/status")
async def chat_status():
    """Check if chat is configured and ready."""
    default_profile_id = _default_profile_id()
    settings = _get_chat_settings(default_profile_id)
    profiles = []
    for profile in CHAT_PROFILE_SPECS.values():
        resolved = _get_chat_settings(profile.profile_id)
        profiles.append(
            {
                "id": profile.profile_id,
                "label": profile.label,
                "provider": "openrouter",
                "model": resolved.model,
                "accent": profile.accent,
                "summary": profile.summary,
                "available": _profile_available(resolved),
                "availability_kind": "api_key",
                "status_note": _profile_status_note(resolved),
            }
        )
    return {
        "chat_contract_version": CHAT_CONTRACT_VERSION,
        "chat_ws_path_template": CHAT_WS_PATH_TEMPLATE,
        "ready": bool(settings.openrouter_api_key),
        "model": settings.model,
        "provider": "openrouter",
        "tools": len(TOOL_DEFINITIONS),
        "max_tool_rounds": settings.max_tool_rounds,
        "max_tokens": settings.max_tokens,
        "timeout_seconds": settings.timeout_seconds,
        "tool_result_max_chars": settings.tool_result_max_chars,
        "history_message_limit": settings.history_message_limit,
        "temperature": settings.temperature,
        "persistent_sessions": False,
        "default_profile_id": default_profile_id,
        "profiles": profiles,
    }


@ws_router.websocket("/ws/chat/session/{session_id}")
async def ws_chat_session(websocket: WebSocket, session_id: str):
    channel = _chat_channel(session_id)
    await manager.connect(websocket, channel)
    try:
        events = _chat_session_event_snapshot(session_id)
        await manager.send_personal(
            websocket,
            {
                "event": "chat_snapshot",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turns": _chat_session_turn_snapshot(events),
                "events": events,
            },
        )
        for event in events:
            await manager.send_personal(websocket, event)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)
