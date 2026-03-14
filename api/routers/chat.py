"""DHARMA COMMAND — Agentic chat endpoint with full tool access.

Claude Opus 4.6 via OpenRouter, with tool-use loop that gives it
real system power: filesystem, shell, search, swarm control,
evolution, stigmergy, traces.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.chat_tools import TOOL_DEFINITIONS, execute_tool

CONVERSATIONS_DIR = Path.home() / ".dharma" / "conversations"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-opus-4-6"
DEFAULT_MAX_TOOL_ROUNDS = 40
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_TOOL_RESULT_MAX_CHARS = 24000
DEFAULT_HISTORY_MESSAGE_LIMIT = 120
DEFAULT_TEMPERATURE = 0.3


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


def _get_chat_settings() -> ChatRuntimeSettings:
    model = os.getenv("DASHBOARD_CHAT_MODEL", "").strip() or DEFAULT_MODEL
    return ChatRuntimeSettings(
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


class ChatMessage(BaseModel):
    role: str
    content: Any = None  # str or list for tool results
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str | None = None


SYSTEM_PROMPT = """\
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
            pass

        monitor = get_monitor()
        try:
            report = await monitor.check_health()
            hs = report.overall_status.value if hasattr(report.overall_status, "value") else str(report.overall_status)
            parts.append(f"Health: {hs}, traces={report.total_traces}")
        except Exception:
            pass
    except Exception:
        pass
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
            logger.error("OpenRouter error %d: %s", resp.status_code, resp.text[:500])
            return None
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


async def _agentic_stream(
    messages_for_api: list[dict],
    settings: ChatRuntimeSettings,
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
        result = await _call_openrouter(messages, settings)
        if not result:
            yield f"data: {json.dumps({'error': 'OpenRouter call failed'})}\n\n"
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
                yield f"data: {json.dumps({'content': msg['content']})}\n\n"

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
                yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args}})}\n\n"

                # Execute
                tool_result = await execute_tool(tool_name, tool_args)

                # Truncate huge results
                if len(tool_result) > settings.tool_result_max_chars:
                    tool_result = (
                        tool_result[: settings.tool_result_max_chars] + "\n... (truncated)"
                    )

                # Emit summary to frontend
                summary = tool_result[:150].replace("\n", " ")
                yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'summary': summary}})}\n\n"

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result,
                })

            # Continue the loop — Claude may want more tools or give final answer
            continue

        # No tool calls — this is the final text response. Stream it.
        final_content = msg.get("content", "")
        if final_content:
            # We already have the full text from the non-streaming call.
            # Send it in chunks to maintain SSE feel.
            chunk_size = 20
            for i in range(0, len(final_content), chunk_size):
                chunk = final_content[i : i + chunk_size]
                yield f"data: {json.dumps({'content': chunk})}\n\n"

        yield "data: [DONE]\n\n"
        return

    # Safety: hit max rounds
    yield f"data: {json.dumps({'content': '\\n\\n[Reached maximum tool rounds. Stopping.]'})}\n\n"
    yield "data: [DONE]\n\n"


def _log_conversation(messages: list[dict], session_id: str = ""):
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
                }
                f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.warning("Failed to log conversation: %s", e)


@router.post("/chat")
async def chat_stream(req: ChatRequest):
    """Agentic SSE streaming chat with Claude Opus 4.6."""
    settings = _get_chat_settings()

    if not settings.openrouter_api_key:
        return StreamingResponse(
            iter(['data: {"error": "OPENROUTER_API_KEY not set"}\n\n']),
            media_type="text/event-stream",
        )

    # Log incoming messages server-side for distillation
    session_id = f"dash-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    _log_conversation(
        [{"role": m.role, "content": m.content} for m in req.messages],
        session_id=session_id,
    )

    # Brief context for system prompt
    brief = await _gather_brief_context()
    system_prompt = SYSTEM_PROMPT + f"\n\n[Live: {brief}]"

    # Build messages for API
    api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in req.messages:
        api_messages.append({"role": m.role, "content": m.content})

    return StreamingResponse(
        _agentic_stream(api_messages, settings),
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
    settings = _get_chat_settings()
    return {
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
    }
