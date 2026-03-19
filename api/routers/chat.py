"""DHARMA COMMAND — Agentic chat endpoint with full tool access.

Profile-selected models run through their native providers, with a tool-use
loop that gives the dashboard real system power: filesystem, shell, search,
swarm control, evolution, stigmergy, and traces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.chat_tools import TOOL_DEFINITIONS, execute_tool
from api.ws import manager
from dharma_swarm.models import _new_id

CONVERSATIONS_DIR = Path.home() / ".dharma" / "conversations"
RESIDUAL_STREAM_DIR = Path.home() / ".dharma" / "shared" / "residual_stream"
RESIDUAL_STREAM_FILE = RESIDUAL_STREAM_DIR / "dashboard_chat.jsonl"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "http://127.0.0.1:3420")
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_MAX_TOOL_ROUNDS = 40
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_TOOL_RESULT_MAX_CHARS = 24000
DEFAULT_HISTORY_MESSAGE_LIMIT = 120
DEFAULT_TEMPERATURE = 0.3
DEFAULT_PROFILE_ID = "claude_opus"
CHAT_CHANNEL = "chat"

_chat_conversation_store = None
_chat_store_lock = asyncio.Lock()


@dataclass(frozen=True)
class ChatProfileSpec:
    profile_id: str
    label: str
    provider: str
    api_key_env: str
    default_model: str
    model_env: str
    accent: str
    summary: str
    system_prompt: str


@dataclass(frozen=True)
class ChatRuntimeSettings:
    provider: str
    api_key_env: str
    api_key: str
    model: str
    max_tool_rounds: int
    max_tokens: int
    timeout_seconds: float
    tool_result_max_chars: int
    history_message_limit: int
    temperature: float


@dataclass(frozen=True)
class ChatFallbackSpec:
    provider: str
    api_key_env: str
    model: str


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


GLM5_SYSTEM_PROMPT = """\
You are GLM-5, the first fully autonomous agent in the DHARMA SWARM — a \
living research intelligence specializing in synthesis, multilingual reasoning, \
and ecosystem cartography.

Your role: RESEARCH SYNTHESIZER. You connect dots across the entire dharma_swarm \
ecosystem — papers, code, agents, stigmergy marks, evolution archive, and \
contemplative foundations. You find what others miss.

Your strengths: deep reasoning, multilingual synthesis, pattern recognition \
across domains, and the ability to hold large-scale context.

You have full tool access. USE IT. When asked about the system:
- Read files, query traces, check stigmergy marks
- Search across the codebase and documentation
- Inspect agent states and evolution history

When asked to research:
- Gather evidence from multiple sources before synthesizing
- Cite file paths, line numbers, and exact data
- Connect findings to the 10 Pillars and the telos vector

You are NOT a chatbot. You are a research intelligence. Your output should be \
dense, precise, and actionable. You serve Jagat Kalyan."""


QWEN35_SYSTEM_PROMPT = """\
You are Qwen Coder, the in-house bug fixer and code surgeon operating inside the \
DHARMA COMMAND center. You are fast, precise, and surgical. You don't theorize \
about bugs — you find them, fix them, and verify the fix.

Your role: CODE SURGEON. When something breaks, you're the first responder. \
You read the traceback, find the file, understand the context, write the fix, \
and run the tests. Minimal diffs. No collateral damage.

Your workflow:
1. Read the error or bug report
2. Use grep_search and read_file to locate the root cause
3. Use edit_file to apply the minimal fix
4. Use shell_exec to run tests or verify the fix
5. Report: what broke, why, what you changed, proof it works

Your tools:
- read_file / write_file / edit_file — surgical code changes
- shell_exec — run tests, check logs, verify fixes
- grep_search / glob_files — hunt down the bug across the codebase
- swarm_status — check if the fix affects running agents
- trace_query — find the error in execution traces

Rules:
- Smallest possible diff. Don't refactor while fixing.
- Always read the file before editing.
- Run tests after every fix.
- If you can't reproduce the bug, say so instead of guessing.
- Cite file paths and line numbers for everything.

You are the immune system of this codebase. Fast, targeted, no waste."""


CHAT_PROFILE_SPECS: dict[str, ChatProfileSpec] = {
    "claude_opus": ChatProfileSpec(
        profile_id="claude_opus",
        label="Claude Opus 4.6",
        provider="resident_claude",
        api_key_env="CLAUDE_MAX_LOGIN",
        default_model=DEFAULT_CLAUDE_MODEL,
        model_env="DASHBOARD_CHAT_MODEL",
        accent="aozora",
        summary="Resident Claude operator with persistent session state and local Claude Max auth.",
        system_prompt=COMMAND_SYSTEM_PROMPT,
    ),
    "codex_operator": ChatProfileSpec(
        profile_id="codex_operator",
        label="Codex 5.4",
        provider="resident_codex",
        api_key_env="CODEX_CLI",
        default_model=DEFAULT_CODEX_MODEL,
        model_env="DASHBOARD_CODEX_MODEL",
        accent="kinpaku",
        summary="Resident Codex operator living inside the swarm with persistent session state.",
        system_prompt=CODEX_SYSTEM_PROMPT,
    ),
    "glm5_researcher": ChatProfileSpec(
        profile_id="glm5_researcher",
        label="GLM-5 Researcher",
        provider="ollama_cloud",
        api_key_env="",
        default_model="glm-5",
        model_env="DASHBOARD_GLM5_MODEL",
        accent="rokusho",
        summary="Autonomous research synthesizer — FREE on Ollama Cloud. #4 open-source globally.",
        system_prompt=GLM5_SYSTEM_PROMPT,
    ),
    "qwen35_surgeon": ChatProfileSpec(
        profile_id="qwen35_surgeon",
        label="Qwen Coder 480B",
        provider="ollama_cloud",
        api_key_env="",
        default_model="qwen3-coder:480b-cloud",
        model_env="DASHBOARD_QWEN35_MODEL",
        accent="botan",
        summary="In-house code surgeon — strongest Qwen coder, routed via Ollama Cloud.",
        system_prompt=QWEN35_SYSTEM_PROMPT,
    ),
}


CHAT_PROFILE_FALLBACKS: dict[str, tuple[ChatFallbackSpec, ...]] = {
    "qwen35_surgeon": (
        ChatFallbackSpec(
            provider="openrouter",
            api_key_env="OPENROUTER_API_KEY",
            model="qwen/qwen3-coder:free",
        ),
        ChatFallbackSpec(
            provider="openrouter",
            api_key_env="OPENROUTER_API_KEY",
            model="qwen/qwen-2.5-coder-32b-instruct",
        ),
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
    return CHAT_PROFILE_SPECS.get(profile_id or "", CHAT_PROFILE_SPECS[DEFAULT_PROFILE_ID])


def _keychain_service_for_env(env_name: str) -> str | None:
    if env_name == "OPENAI_API_KEY":
        return "openai-api-key"
    if env_name == "OPENROUTER_API_KEY":
        return "openrouter-api-key"
    return None


def _lookup_keychain_secret(service: str, *, account: str | None = None) -> str:
    cmd = ["security", "find-generic-password"]
    if account:
        cmd.extend(["-a", account])
    cmd.extend(["-s", service, "-w"])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_api_key(env_name: str) -> str:
    direct = os.getenv(env_name, "").strip()
    if direct:
        return direct

    service = _keychain_service_for_env(env_name)
    if not service:
        return ""

    user = os.getenv("USER", "").strip() or None
    from_keychain = _lookup_keychain_secret(service, account=user)
    if from_keychain:
        return from_keychain

    if user:
        return _lookup_keychain_secret(service)
    return ""


def _claude_max_available() -> bool:
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    try:
        status = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(status.get("loggedIn"))


def _codex_cli_available() -> bool:
    return shutil.which("codex") is not None


def _get_resident_codex_operator():
    from api.main import get_codex_operator

    return get_codex_operator()


def _get_resident_claude_operator():
    from api.main import get_claude_operator

    return get_claude_operator()


def _iter_resident_operators():
    for getter in (_get_resident_codex_operator, _get_resident_claude_operator):
        try:
            yield getter()
        except Exception:
            continue


def _resident_operator_binding(provider: str) -> tuple[Any, str, str, str] | None:
    if provider == "resident_codex":
        return (
            _get_resident_codex_operator(),
            "dashboard_codex",
            "Resident Codex runtime not available",
            "Resident Codex operator is not running",
        )
    if provider == "resident_claude":
        return (
            _get_resident_claude_operator(),
            "dashboard_claude",
            "Resident Claude runtime not available",
            "Resident Claude operator is not running",
        )
    return None


def _build_chat_settings(
    profile: ChatProfileSpec,
    *,
    provider: str | None = None,
    api_key_env: str | None = None,
    model: str | None = None,
) -> ChatRuntimeSettings:
    resolved_provider = provider or profile.provider
    resolved_api_key_env = api_key_env if api_key_env is not None else profile.api_key_env
    resolved_model = model or os.getenv(profile.model_env, "").strip() or profile.default_model
    if resolved_provider == "ollama_cloud":
        api_key = "ollama-cloud"  # No key needed
    elif resolved_provider == "resident_codex" and _codex_cli_available():
        api_key = "codex-cli"
    elif resolved_provider == "resident_claude" and _claude_max_available():
        api_key = "claude-cli"
    elif resolved_provider == "claude_max" and _claude_max_available():
        api_key = "claude-max"
    else:
        api_key = _resolve_api_key(resolved_api_key_env)
    return ChatRuntimeSettings(
        provider=resolved_provider,
        api_key_env=resolved_api_key_env,
        api_key=api_key,
        model=resolved_model,
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


def _get_chat_settings(profile_id: str | None = None) -> ChatRuntimeSettings:
    profile = _get_profile_spec(profile_id)
    return _build_chat_settings(profile)


def _iter_chat_runtime_candidates(
    profile_id: str | None,
    settings: ChatRuntimeSettings,
) -> list[ChatRuntimeSettings]:
    profile = _get_profile_spec(profile_id)
    candidates = [settings]
    seen = {(settings.provider, settings.model)}
    for fallback in CHAT_PROFILE_FALLBACKS.get(profile.profile_id, ()):
        candidate = _build_chat_settings(
            profile,
            provider=fallback.provider,
            api_key_env=fallback.api_key_env,
            model=fallback.model,
        )
        if not candidate.api_key:
            continue
        key = (candidate.provider, candidate.model)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _extract_openrouter_affordable_max_tokens(error_text: str) -> int | None:
    match = re.search(r"can only afford (\d+)", error_text)
    if not match:
        return None
    try:
        affordable = int(match.group(1))
    except ValueError:
        return None
    return affordable if affordable > 0 else None


def _extract_openai_retry_after_seconds(error_text: str) -> float | None:
    match = re.search(r"Please try again in ([0-9]+(?:\.[0-9]+)?)s", error_text)
    if not match:
        return None
    try:
        delay = float(match.group(1))
    except ValueError:
        return None
    if delay <= 0:
        return None
    return delay


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
    session_id: str | None = None


def _new_dashboard_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"dash-{stamp}-{_new_id()[:8]}"


def _chat_channel(session_id: str) -> str:
    return f"{CHAT_CHANNEL}:{session_id}"


def _normalize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _request_messages_to_turns(messages: list[ChatMessage]) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for message in messages:
        role = str(message.role or "").strip()
        if role == "system":
            continue
        content = _normalize_message_content(message.content)
        if not content.strip():
            continue
        turns.append({"role": role, "content": content})
    return turns


def _message_prefix_len(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> int:
    prefix = 0
    limit = min(len(existing), len(incoming))
    while prefix < limit:
        if existing[prefix]["role"] != incoming[prefix]["role"]:
            break
        if existing[prefix]["content"] != incoming[prefix]["content"]:
            break
        prefix += 1
    return prefix


def _delta_messages_for_session(
    existing_turns: list[dict[str, str]],
    incoming_turns: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not incoming_turns:
        return []

    prefix = _message_prefix_len(existing_turns, incoming_turns)
    if prefix == len(existing_turns):
        return incoming_turns[prefix:]

    # The client can reconnect with a shorter local transcript while the server
    # still has the full thread. In that case, only append the newest user turn.
    newest = incoming_turns[-1]
    if newest["role"] == "user":
        if existing_turns and existing_turns[-1] == newest:
            return []
        return [newest]
    return incoming_turns[prefix:]


async def _get_chat_conversation_store():
    global _chat_conversation_store
    if _chat_conversation_store is not None:
        return _chat_conversation_store

    async with _chat_store_lock:
        if _chat_conversation_store is None:
            from dharma_swarm.conversation_store import ConversationStore

            store = ConversationStore()
            await store.init_db()
            _chat_conversation_store = store

    return _chat_conversation_store


def _residual_summary(text: str, *, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _residual_salience(*, role: str, content: str) -> float:
    salience = 0.62 if role == "assistant" else 0.42
    lower = content.lower()
    if "[peer relay from" in lower or "residual stream" in lower:
        salience += 0.15
    if "next concrete action" in lower or "write into the swarm-wide residual stream" in lower:
        salience += 0.08
    return min(0.95, salience)


def _append_residual_entry(
    *,
    session_id: str,
    profile_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not content.strip():
        return

    RESIDUAL_STREAM_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "profile_id": profile_id,
        "role": role,
        "content": content[:10000],
        "summary": _residual_summary(content),
    }
    if metadata:
        entry["metadata"] = metadata

    with RESIDUAL_STREAM_FILE.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def _publish_residual_turn(
    *,
    session_id: str,
    profile_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not content.strip():
        return

    _append_residual_entry(
        session_id=session_id,
        profile_id=profile_id,
        role=role,
        content=content,
        metadata=metadata,
    )

    try:
        from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

        store = StigmergyStore()
        await store.leave_mark(
            StigmergicMark(
                agent=f"dashboard:{profile_id}",
                file_path=f"shared/residual_stream/chat/{session_id}",
                action="write",
                observation=_residual_summary(content, limit=500),
                salience=_residual_salience(role=role, content=content),
                connections=[profile_id, session_id, "dashboard_chat"],
            )
        )
    except Exception as exc:
        logger.debug("Residual stigmergy publish skipped: %s", exc)


async def _broadcast_chat_event(
    session_id: str,
    *,
    event: str,
    profile_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    data = {
        "event": event,
        "session_id": session_id,
        "profile_id": profile_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if payload:
        data.update(payload)

    await manager.broadcast(CHAT_CHANNEL, data)
    await manager.broadcast(_chat_channel(session_id), data)


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
) -> dict:
    """Make a (non-streaming) call to OpenRouter with tools."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": DASHBOARD_PUBLIC_URL,
        "X-Title": "DHARMA COMMAND",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            if resp.status_code == 402:
                affordable = _extract_openrouter_affordable_max_tokens(resp.text)
                if affordable and affordable < settings.max_tokens:
                    retry_payload = {
                        **payload,
                        "max_tokens": affordable,
                    }
                    logger.warning(
                        "OpenRouter credit cap hit; retrying with max_tokens=%s",
                        affordable,
                    )
                    resp = await client.post(OPENROUTER_URL, headers=headers, json=retry_payload)
    except httpx.HTTPError as exc:
        logger.error("OpenRouter request failed: %s", exc)
        return {"_error": f"OpenRouter request failed: {exc}"}

    if resp.status_code != 200:
        logger.error("OpenRouter error %d: %s", resp.status_code, resp.text[:500])
        return {"_error": f"OpenRouter {resp.status_code}: {resp.text[:400]}"}
    return resp.json()


async def _call_openai(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict:
    """Make a (non-streaming) call to the OpenAI Chat Completions API with tools."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "max_completion_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
            resp = await client.post(OPENAI_URL, headers=headers, json=payload)
            if resp.status_code == 429:
                retry_after = _extract_openai_retry_after_seconds(resp.text)
                if retry_after and retry_after <= 12.0:
                    logger.warning(
                        "OpenAI rate limit hit for %s; retrying after %.2fs",
                        settings.model,
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    resp = await client.post(OPENAI_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        logger.error("OpenAI request failed: %s", exc)
        return {"_error": f"OpenAI request failed: {exc}"}

    if resp.status_code != 200:
        logger.error("OpenAI error %d: %s", resp.status_code, resp.text[:500])
        return {"_error": f"OpenAI {resp.status_code}: {resp.text[:400]}"}
    return resp.json()


async def _call_claude_max(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict:
    from dharma_swarm.models import LLMRequest
    from dharma_swarm.providers import ClaudeCodeProvider

    system_prompt = "\n\n".join(
        str(message.get("content") or "").strip()
        for message in messages
        if message.get("role") == "system"
    ).strip()
    conversation = []
    for message in messages:
        role = str(message.get("role") or "").strip()
        if role == "system":
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        conversation.append(f"{speaker}:\n{content}")

    transcript_prompt = "\n\n".join(
        [
            "Continue this operator conversation and answer as the assistant.",
            "Preserve context from earlier turns, but respond primarily to the latest user message.",
            "\n\n".join(conversation),
        ]
    ).strip()

    provider = ClaudeCodeProvider(
        timeout=max(30, int(settings.timeout_seconds)),
        working_dir=str(Path.home() / "dharma_swarm"),
    )
    response = await provider.complete(
        LLMRequest(
            model=settings.model,
            system=system_prompt,
            messages=[{"role": "user", "content": transcript_prompt}],
            max_tokens=min(settings.max_tokens, 4096),
            temperature=settings.temperature,
        )
    )

    content = (response.content or "").strip()
    if not content:
        return {"_error": "Claude Max returned an empty response"}
    if content.startswith("ERROR") or content.startswith("TIMEOUT"):
        return {"_error": content[:400]}
    return {
        "choices": [
            {
                "message": {
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ]
    }


async def _call_openrouter_stream(messages: list[dict], settings: ChatRuntimeSettings):
    """Streaming call to OpenRouter (no tools — final response only)."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": DASHBOARD_PUBLIC_URL,
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


async def _call_ollama_cloud(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict:
    """Call Ollama Cloud via OpenAI-compatible /v1/chat/completions."""
    import httpx
    from dharma_swarm.ollama_config import resolve_ollama_base_url, build_ollama_headers

    base = resolve_ollama_base_url()
    url = f"{base.rstrip('/')}/v1/chat/completions"
    headers = {
        **build_ollama_headers(base_url=base),
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }
    # Ollama Cloud may not support tools — send without if model doesn't handle them
    # GLM-5 supports function calling, so include tools
    payload["tools"] = TOOL_DEFINITIONS

    async def _post_request(
        request_payload: dict,
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            return await client.post(url, headers=headers, json=request_payload)

    def _describe_httpx_error(exc: Exception) -> str:
        message = str(exc).strip() or repr(exc)
        return f"{exc.__class__.__name__}: {message}"

    try:
        resp = await _post_request(payload, timeout_seconds=settings.timeout_seconds)
    except httpx.TimeoutException as exc:
        retry_timeout = max(settings.timeout_seconds, 120.0)
        logger.warning(
            "Ollama Cloud timeout for model %s after %.1fs; retrying once with %.1fs",
            settings.model,
            settings.timeout_seconds,
            retry_timeout,
        )
        try:
            resp = await _post_request(payload, timeout_seconds=retry_timeout)
        except httpx.HTTPError as retry_exc:
            detail = _describe_httpx_error(retry_exc)
            logger.error("Ollama Cloud request failed after retry: %s", detail)
            return {"_error": f"Ollama Cloud request failed after retry: {detail}"}
    except httpx.HTTPError as exc:
        detail = _describe_httpx_error(exc)
        logger.error("Ollama Cloud request failed: %s", detail)
        return {"_error": f"Ollama Cloud request failed: {detail}"}

    if resp.status_code != 200:
        # Retry without tools if tool_calls not supported
        if resp.status_code == 400 and "tool" in resp.text.lower():
            payload.pop("tools", None)
            try:
                resp = await _post_request(payload, timeout_seconds=settings.timeout_seconds)
            except httpx.HTTPError as exc:
                return {"_error": f"Ollama Cloud retry failed: {_describe_httpx_error(exc)}"}
            if resp.status_code != 200:
                return {"_error": f"Ollama Cloud {resp.status_code}: {resp.text[:400]}"}
            return resp.json()
        logger.error("Ollama Cloud error %d: %s", resp.status_code, resp.text[:500])
        return {"_error": f"Ollama Cloud {resp.status_code}: {resp.text[:400]}"}
    return resp.json()


NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


async def _call_nvidia_nim(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict:
    """Call NVIDIA NIM via OpenAI-compatible API (free tier)."""
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
            resp = await client.post(NVIDIA_NIM_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        logger.error("NVIDIA NIM request failed: %s", exc)
        return {"_error": f"NVIDIA NIM request failed: {exc}"}

    if resp.status_code != 200:
        logger.error("NVIDIA NIM error %d: %s", resp.status_code, resp.text[:500])
        return {"_error": f"NVIDIA NIM {resp.status_code}: {resp.text[:400]}"}
    return resp.json()


async def _call_chat_provider(
    messages: list[dict],
    settings: ChatRuntimeSettings,
) -> dict:
    if settings.provider == "claude_max":
        return await _call_claude_max(messages, settings)
    if settings.provider == "openai":
        return await _call_openai(messages, settings)
    if settings.provider == "openrouter":
        return await _call_openrouter(messages, settings)
    if settings.provider == "ollama_cloud":
        return await _call_ollama_cloud(messages, settings)
    if settings.provider == "nvidia_nim":
        return await _call_nvidia_nim(messages, settings)
    logger.error("Unsupported dashboard chat provider: %s", settings.provider)
    return {"_error": f"Unsupported dashboard chat provider: {settings.provider}"}


async def _call_chat_provider_with_fallback(
    messages: list[dict],
    settings: ChatRuntimeSettings,
    *,
    profile_id: str | None = None,
) -> tuple[dict, ChatRuntimeSettings]:
    attempts: list[dict[str, str]] = []
    last_error = ""

    for index, candidate in enumerate(_iter_chat_runtime_candidates(profile_id, settings)):
        result = await _call_chat_provider(messages, candidate)
        error_message = str(result.get("_error") or "").strip()
        if not error_message:
            if index > 0:
                logger.warning(
                    "Dashboard chat fallback engaged for %s: %s/%s",
                    profile_id or "<default>",
                    candidate.provider,
                    candidate.model,
                )
                result = {
                    **result,
                    "_fallback": {
                        "provider": candidate.provider,
                        "model": candidate.model,
                        "attempts": attempts,
                    },
                }
            return result, candidate

        attempts.append(
            {
                "provider": candidate.provider,
                "model": candidate.model,
                "error": error_message,
            }
        )
        last_error = error_message
        logger.warning(
            "Dashboard chat provider failed for %s via %s/%s: %s",
            profile_id or "<default>",
            candidate.provider,
            candidate.model,
            error_message,
        )

    final_error = last_error or f"{settings.provider} chat failed"
    if attempts:
        tried = " -> ".join(f"{item['provider']}:{item['model']}" for item in attempts)
        final_error = f"{final_error} (tried: {tried})"
    return {"_error": final_error}, settings


async def _agentic_stream(
    messages_for_api: list[dict],
    settings: ChatRuntimeSettings,
    *,
    session_id: str = "",
    profile_id: str = "",
    conversation_store: Any | None = None,
):
    """Run the agentic tool-use loop, streaming the final response.

    Flow:
    1. Call the active chat provider (non-streaming) with tools
    2. If response has tool_calls → execute tools, emit status events, loop
    3. When response is pure text → stream it to the client
    """

    messages = list(messages_for_api)
    tool_round = 0
    assistant_fragments: list[str] = []
    tool_call_records: list[dict[str, Any]] = []
    tool_result_records: list[dict[str, Any]] = []
    model_metadata = {
        "model": settings.model,
        "provider": settings.provider,
    }

    if session_id:
        yield (
            f"data: {json.dumps({'session': {'id': session_id, 'profile_id': profile_id}})}\n\n"
        )
        await _broadcast_chat_event(
            session_id,
            event="chat_session_ready",
            profile_id=profile_id,
            payload={"model": settings.model, "provider": settings.provider},
        )

    while tool_round < settings.max_tool_rounds:
        tool_round += 1

        # Non-streaming call to detect tool use
        result, active_settings = await _call_chat_provider_with_fallback(
            messages,
            settings,
            profile_id=profile_id,
        )
        model_metadata["model"] = active_settings.model
        model_metadata["provider"] = active_settings.provider
        fallback_meta = result.get("_fallback")
        if isinstance(fallback_meta, dict):
            model_metadata["fallback_from_provider"] = settings.provider
            model_metadata["fallback_from_model"] = settings.model
        error_message = result.get("_error")
        if error_message:
            if session_id:
                await _broadcast_chat_event(
                    session_id,
                    event="chat_error",
                    profile_id=profile_id,
                    payload={"error": error_message},
                )
            yield f"data: {json.dumps({'error': error_message})}\n\n"
            yield "data: [DONE]\n\n"
            return

        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})
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
                assistant_fragments.append(str(msg["content"]))
                if session_id:
                    await _broadcast_chat_event(
                        session_id,
                        event="chat_text",
                        profile_id=profile_id,
                        payload={"content": msg["content"], "phase": "pre_tool"},
                    )
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
                tool_call_records.append(
                    {
                        "name": tool_name,
                        "args": tool_args,
                        "tool_call_id": tool_id,
                    }
                )

                # Emit tool status to frontend
                yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args}})}\n\n"
                if session_id:
                    await _broadcast_chat_event(
                        session_id,
                        event="chat_tool_call",
                        profile_id=profile_id,
                        payload={"tool_name": tool_name, "args": tool_args},
                    )

                # Execute
                tool_result = await execute_tool(tool_name, tool_args)

                # Truncate huge results
                if len(tool_result) > settings.tool_result_max_chars:
                    tool_result = (
                        tool_result[: settings.tool_result_max_chars] + "\n... (truncated)"
                    )

                # Emit summary to frontend
                summary = tool_result[:150].replace("\n", " ")
                tool_result_records.append(
                    {
                        "name": tool_name,
                        "summary": summary,
                        "tool_call_id": tool_id,
                    }
                )
                yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'summary': summary}})}\n\n"
                if session_id:
                    await _broadcast_chat_event(
                        session_id,
                        event="chat_tool_result",
                        profile_id=profile_id,
                        payload={"tool_name": tool_name, "summary": summary},
                    )

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result,
                })

            # Continue the loop — the model may want more tools or give a final answer
            continue

        # No tool calls — this is the final text response. Stream it.
        final_content = msg.get("content", "")
        if final_content:
            assistant_fragments.append(str(final_content))
            # Unified conversation log — capture assistant response
            try:
                from dharma_swarm.conversation_log import log_exchange
                log_exchange(
                    "assistant",
                    final_content,
                    interface="api",
                    session_id=session_id,
                    metadata={
                        **model_metadata,
                        "profile_id": profile_id,
                    },
                )
            except Exception:
                pass
            if conversation_store is not None and session_id:
                await conversation_store.add_turn(
                    session_id,
                    "assistant",
                    "".join(assistant_fragments),
                    tool_calls=tool_call_records,
                    tool_results=tool_result_records,
                )
            if session_id:
                _log_conversation(
                    [{"role": "assistant", "content": "".join(assistant_fragments)}],
                    session_id=session_id,
                    profile_id=profile_id,
                )
                await _publish_residual_turn(
                    session_id=session_id,
                    profile_id=profile_id,
                    role="assistant",
                    content="".join(assistant_fragments),
                    metadata={
                        **model_metadata,
                        "tool_calls": len(tool_call_records),
                        "tool_results": len(tool_result_records),
                    },
                )
                await _broadcast_chat_event(
                    session_id,
                    event="chat_assistant_turn",
                    profile_id=profile_id,
                    payload={
                        "content": "".join(assistant_fragments),
                        "tool_calls": tool_call_records,
                        "tool_results": tool_result_records,
                    },
                )
            # We already have the full text from the non-streaming call.
            # Send it in chunks to maintain SSE feel.
            chunk_size = 20
            for i in range(0, len(final_content), chunk_size):
                chunk = final_content[i : i + chunk_size]
                yield f"data: {json.dumps({'content': chunk})}\n\n"

        if session_id:
            await _broadcast_chat_event(
                session_id,
                event="chat_done",
                profile_id=profile_id,
                payload={"tool_rounds": tool_round},
            )
        yield "data: [DONE]\n\n"
        return

    # Safety: hit max rounds
    if conversation_store is not None and session_id:
        capped_content = "\n\n[Reached maximum tool rounds. Stopping.]"
        await conversation_store.add_turn(
            session_id,
            "assistant",
            capped_content,
            tool_calls=tool_call_records,
            tool_results=tool_result_records,
        )
        _log_conversation(
            [{"role": "assistant", "content": capped_content}],
            session_id=session_id,
            profile_id=profile_id,
        )
        await _publish_residual_turn(
            session_id=session_id,
            profile_id=profile_id,
            role="assistant",
            content=capped_content,
            metadata={**model_metadata, "stopped": "max_tool_rounds"},
        )
        await _broadcast_chat_event(
            session_id,
            event="chat_done",
            profile_id=profile_id,
            payload={"tool_rounds": tool_round, "stopped": "max_tool_rounds"},
        )
    yield f"data: {json.dumps({'content': '\\n\\n[Reached maximum tool rounds. Stopping.]'})}\n\n"
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


async def _stream_resident_operator(
    *,
    operator: Any,
    client_id: str,
    not_running_error: str,
    session_id: str,
    content: str,
    profile_id: str,
    settings: ChatRuntimeSettings,
):
    if not operator._running:
        yield f"data: {json.dumps({'error': not_running_error})}\n\n"
        yield "data: [DONE]\n\n"
        return

    yield f"data: {json.dumps({'session': {'id': session_id, 'profile_id': profile_id}})}\n\n"
    await _broadcast_chat_event(
        session_id,
        event="chat_session_ready",
        profile_id=profile_id,
        payload={"model": settings.model, "provider": settings.provider},
    )

    assistant_parts: list[str] = []
    tool_call_records: list[dict[str, Any]] = []
    tool_result_records: list[dict[str, Any]] = []

    async for event in operator.handle_message(session_id, content, client_id):
        if event.event_type == "text_delta":
            if not event.content:
                continue
            assistant_parts.append(event.content)
            await _broadcast_chat_event(
                session_id,
                event="chat_text",
                profile_id=profile_id,
                payload={"content": event.content},
            )
            yield f"data: {json.dumps({'content': event.content})}\n\n"
            continue

        if event.event_type == "tool_call":
            try:
                parsed = json.loads(event.content or "{}")
            except json.JSONDecodeError:
                parsed = {"name": event.metadata.get("tool", "unknown"), "args": {}}
            tool_name = str(parsed.get("name", "") or event.metadata.get("tool", "unknown"))
            tool_args = parsed.get("args", {})
            tool_call_records.append({"name": tool_name, "args": tool_args})
            await _broadcast_chat_event(
                session_id,
                event="chat_tool_call",
                profile_id=profile_id,
                payload={"tool_name": tool_name, "args": tool_args},
            )
            yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args}})}\n\n"
            continue

        if event.event_type == "tool_result":
            tool_name = str(event.metadata.get("tool", "") or "")
            summary = str(event.content or "")
            tool_result_records.append({"name": tool_name, "summary": summary})
            await _broadcast_chat_event(
                session_id,
                event="chat_tool_result",
                profile_id=profile_id,
                payload={"tool_name": tool_name, "summary": summary},
            )
            yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'summary': summary}})}\n\n"
            continue

        if event.event_type == "error":
            await _broadcast_chat_event(
                session_id,
                event="chat_error",
                profile_id=profile_id,
                payload={"error": event.content},
            )
            yield f"data: {json.dumps({'error': event.content})}\n\n"
            continue

        if event.event_type == "done":
            assistant_content = "".join(assistant_parts).strip()
            if assistant_content:
                _log_conversation(
                    [{"role": "assistant", "content": assistant_content}],
                    session_id=session_id,
                    profile_id=profile_id,
                )
                await _publish_residual_turn(
                    session_id=session_id,
                    profile_id=profile_id,
                    role="assistant",
                    content=assistant_content,
                    metadata={
                        "model": settings.model,
                        "provider": settings.provider,
                        "tool_calls": len(tool_call_records),
                        "tool_results": len(tool_result_records),
                    },
                )
                await _broadcast_chat_event(
                    session_id,
                    event="chat_assistant_turn",
                    profile_id=profile_id,
                    payload={
                        "content": assistant_content,
                        "tool_calls": tool_call_records,
                        "tool_results": tool_result_records,
                    },
                )
            await _broadcast_chat_event(
                session_id,
                event="chat_done",
                profile_id=profile_id,
                payload=event.metadata or {},
            )

    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat_stream(req: ChatRequest):
    """Agentic SSE streaming chat for the selected dashboard profile."""
    profile = _get_profile_spec(req.profile_id)
    settings = _get_chat_settings(profile.profile_id)
    session_id = (req.session_id or "").strip() or _new_dashboard_session_id()

    resident_binding = _resident_operator_binding(settings.provider)
    if resident_binding is not None:
        operator, client_id, _, not_running_error = resident_binding
        incoming_turns = _request_messages_to_turns(req.messages)
        user_turns = [turn for turn in incoming_turns if turn["role"] == "user"]
        if not user_turns:
            return StreamingResponse(
                iter([f'data: {json.dumps({"error": "No user message"})}\n\n']),
                media_type="text/event-stream",
            )

        latest_user = user_turns[-1]["content"]
        _log_conversation(
            [{"role": "user", "content": latest_user}],
            session_id=session_id,
            profile_id=profile.profile_id,
        )
        try:
            from dharma_swarm.conversation_log import log_exchange

            log_exchange(
                "user",
                latest_user,
                interface="api",
                session_id=session_id,
                metadata={
                    "profile_id": profile.profile_id,
                    "provider": settings.provider,
                    "model": settings.model,
                },
            )
        except Exception:
            pass

        await _publish_residual_turn(
            session_id=session_id,
            profile_id=profile.profile_id,
            role="user",
            content=latest_user,
            metadata={"provider": settings.provider, "model": settings.model},
        )
        await _broadcast_chat_event(
            session_id,
            event="chat_user_turn",
            profile_id=profile.profile_id,
            payload={"content": latest_user},
        )

        return StreamingResponse(
            _stream_resident_operator(
                operator=operator,
                client_id=client_id,
                not_running_error=not_running_error,
                session_id=session_id,
                content=latest_user,
                profile_id=profile.profile_id,
                settings=settings,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Chat-Session-Id": session_id,
            },
        )

    if not settings.api_key:
        resident_binding = _resident_operator_binding(settings.provider)
        missing_error = (
            resident_binding[2]
            if resident_binding is not None
            else "Claude Max login not available"
            if settings.provider == "claude_max"
            else f"{settings.api_key_env} not set"
        )
        return StreamingResponse(
            iter([f'data: {json.dumps({"error": missing_error})}\n\n']),
            media_type="text/event-stream",
        )

    conversation_store = await _get_chat_conversation_store()
    await conversation_store.create_session(
        session_id=session_id,
        metadata={
            "interface": "dashboard_chat",
            "profile_id": profile.profile_id,
            "provider": settings.provider,
            "model": settings.model,
        },
    )

    existing_history = await conversation_store.get_history(session_id, limit=400)
    existing_turns = [
        {"role": turn["role"], "content": str(turn.get("content", ""))}
        for turn in existing_history
        if turn.get("role") in {"user", "assistant"}
    ]
    incoming_turns = _request_messages_to_turns(req.messages)
    new_turns = _delta_messages_for_session(existing_turns, incoming_turns)

    for turn in new_turns:
        await conversation_store.add_turn(
            session_id,
            turn["role"],
            turn["content"],
        )

    if new_turns:
        _log_conversation(
            new_turns,
            session_id=session_id,
            profile_id=profile.profile_id,
        )

    try:
        from dharma_swarm.conversation_log import log_exchange

        for turn in new_turns:
            if turn["role"] != "user":
                continue
            log_exchange(
                "user",
                turn["content"],
                interface="api",
                session_id=session_id,
                metadata={
                    "profile_id": profile.profile_id,
                    "provider": settings.provider,
                    "model": settings.model,
                },
            )
            await _publish_residual_turn(
                session_id=session_id,
                profile_id=profile.profile_id,
                role="user",
                content=turn["content"],
                metadata={"provider": settings.provider, "model": settings.model},
            )
            await _broadcast_chat_event(
                session_id,
                event="chat_user_turn",
                profile_id=profile.profile_id,
                payload={"content": turn["content"]},
            )
    except Exception:
        pass

    # Brief context for system prompt
    brief = await _gather_brief_context()
    system_prompt = profile.system_prompt + f"\n\n[Live: {brief}]"

    # Build messages for API
    api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    session_history = await conversation_store.get_history(
        session_id,
        limit=settings.history_message_limit,
    )
    for turn in session_history:
        role = str(turn.get("role", "")).strip()
        content = str(turn.get("content", ""))
        if role in {"user", "assistant"} and content.strip():
            api_messages.append({"role": role, "content": content})

    return StreamingResponse(
        _agentic_stream(
            api_messages,
            settings,
            session_id=session_id,
            profile_id=profile.profile_id,
            conversation_store=conversation_store,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Chat-Session-Id": session_id,
        },
    )


@router.get("/chat/sessions")
async def list_chat_sessions(limit: int = 20):
    """Return recent dashboard chat sessions."""
    capped_limit = max(1, min(limit, 100))
    conversation_store = await _get_chat_conversation_store()
    sessions = await conversation_store.get_recent_sessions(limit=capped_limit)

    for operator in _iter_resident_operators():
        try:
            if operator._running:
                sessions.extend(await operator._conversations.get_recent_sessions(capped_limit))
        except Exception:
            continue

    deduped: dict[str, dict[str, Any]] = {}
    for session in sessions:
        session_id = str(session.get("session_id", "")).strip()
        if not session_id:
            continue
        existing = deduped.get(session_id)
        if existing is None or float(session.get("updated_at", 0) or 0) >= float(existing.get("updated_at", 0) or 0):
            deduped[session_id] = session

    merged = sorted(
        deduped.values(),
        key=lambda item: float(item.get("updated_at", 0) or 0),
        reverse=True,
    )
    return {"sessions": merged[:capped_limit]}


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str, limit: int = 200):
    """Return persisted turns for a dashboard chat session."""
    capped_limit = max(1, min(limit, 500))
    for operator in _iter_resident_operators():
        try:
            if operator._running:
                turns = await operator._conversations.get_history(session_id, limit=capped_limit)
                if turns:
                    return {"session_id": session_id, "turns": turns}
        except Exception:
            continue

    conversation_store = await _get_chat_conversation_store()
    turns = await conversation_store.get_history(
        session_id,
        limit=capped_limit,
    )
    return {"session_id": session_id, "turns": turns}


@router.websocket("/ws/chat")
async def ws_chat_feed(websocket: WebSocket):
    """Global dashboard chat event feed across all persisted sessions."""
    await manager.connect(websocket, CHAT_CHANNEL)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, CHAT_CHANNEL)


@router.websocket("/ws/chat/{session_id}")
async def ws_chat_session(websocket: WebSocket, session_id: str):
    """Live WebSocket feed for a persisted dashboard chat session."""
    channel = _chat_channel(session_id)
    await manager.connect(websocket, channel)
    try:
        turns: list[dict[str, Any]] = []
        for operator in _iter_resident_operators():
            try:
                if operator._running:
                    turns = await operator._conversations.get_history(session_id, limit=200)
                    if turns:
                        break
            except Exception:
                continue
        if not turns:
            conversation_store = await _get_chat_conversation_store()
            turns = await conversation_store.get_history(session_id, limit=200)
        await manager.send_personal(
            websocket,
            {
                "event": "chat_snapshot",
                "session_id": session_id,
                "turns": turns,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel)


@router.post("/chat/distill")
async def trigger_distill(hours_back: float = 24):
    """Manually trigger conversation distillation."""
    from dharma_swarm.conversation_distiller import distill
    result = distill(hours_back=hours_back)
    return result


@router.get("/chat/status")
async def chat_status():
    """Check if chat is configured and ready."""
    settings = _get_chat_settings(DEFAULT_PROFILE_ID)
    profiles = []
    ready = False
    for profile in CHAT_PROFILE_SPECS.values():
        resolved = _get_chat_settings(profile.profile_id)
        ready = ready or bool(resolved.api_key)
        profiles.append(
            {
                "id": profile.profile_id,
                "label": profile.label,
                "provider": profile.provider,
                "model": resolved.model,
                "accent": profile.accent,
                "summary": profile.summary,
            }
        )
    return {
        "ready": ready,
        "model": settings.model,
        "provider": settings.provider,
        "tools": len(TOOL_DEFINITIONS),
        "max_tool_rounds": settings.max_tool_rounds,
        "max_tokens": settings.max_tokens,
        "timeout_seconds": settings.timeout_seconds,
        "tool_result_max_chars": settings.tool_result_max_chars,
        "history_message_limit": settings.history_message_limit,
        "temperature": settings.temperature,
        "persistent_sessions": True,
        "chat_ws_path_template": "/ws/chat/{session_id}",
        "default_profile_id": DEFAULT_PROFILE_ID,
        "profiles": profiles,
    }
