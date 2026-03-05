"""Claude Code provider adapter (subprocess + NDJSON -> canonical events)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from .base import Capability, CompletionRequest, ModelProfile, ProviderAdapter, ProviderConfig
from ..events import (
    CanonicalEventType,
    ErrorEvent,
    RateLimitEvent,
    SessionEnd,
    SessionStart,
    TaskProgress,
    TaskStarted,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    ToolArgumentsDelta,
    ToolCallComplete,
    ToolProgress,
    ToolResult,
    UsageReport,
)
from ..event_types import (
    AssistantMessage as LegacyAssistantMessage,
    RateLimitEvent as LegacyRateLimitEvent,
    ResultMessage as LegacyResultMessage,
    StreamDelta as LegacyStreamDelta,
    SystemInit as LegacySystemInit,
    TaskProgress as LegacyTaskProgress,
    TaskStarted as LegacyTaskStarted,
    ToolProgress as LegacyToolProgress,
    ToolResult as LegacyToolResult,
)
from ..stream_parser import parse_ndjson_line

DHARMA_SWARM = Path(__file__).resolve().parents[4]

CLAUDE_CAPABILITIES = (
    Capability.STREAMING
    | Capability.TOOL_USE
    | Capability.THINKING
    | Capability.VISION
    | Capability.PARALLEL_TOOLS
    | Capability.RESUME
    | Capability.COST_TRACKING
    | Capability.CONTEXT_USAGE
    | Capability.SYSTEM_PROMPT
    | Capability.CANCEL
)


def _capability_names(caps: Capability) -> list[str]:
    names: list[str] = []
    for cap in Capability:
        if caps & cap:
            names.append(cap.name.lower())
    return names


class ClaudeAdapter(ProviderAdapter):
    """ProviderAdapter implementation for Claude Code CLI."""

    provider_id = "claude"

    def __init__(
        self,
        config: ProviderConfig | None = None,
        cli_path: str = "claude",
        workdir: Path | None = None,
    ) -> None:
        self._config = config or ProviderConfig(
            provider_id=self.provider_id,
            default_model="claude-sonnet-4-5",
        )
        self._cli_path = cli_path
        self._workdir = workdir or DHARMA_SWARM
        self._proc: asyncio.subprocess.Process | None = None

        self._profiles: dict[str, ModelProfile] = {
            "claude-sonnet-4-5": ModelProfile(
                provider_id=self.provider_id,
                model_id="claude-sonnet-4-5",
                display_name="Claude Sonnet 4.5",
                capabilities=CLAUDE_CAPABILITIES,
            ),
            "claude-opus-4": ModelProfile(
                provider_id=self.provider_id,
                model_id="claude-opus-4",
                display_name="Claude Opus 4",
                capabilities=CLAUDE_CAPABILITIES,
            ),
            "claude-haiku-4-5": ModelProfile(
                provider_id=self.provider_id,
                model_id="claude-haiku-4-5",
                display_name="Claude Haiku 4.5",
                capabilities=CLAUDE_CAPABILITIES,
            ),
        }

    async def list_models(self) -> list[ModelProfile]:
        return list(self._profiles.values())

    def get_profile(self, model_id: str | None = None) -> ModelProfile:
        model = model_id or self._config.default_model or "claude-sonnet-4-5"
        return self._profiles.get(model, next(iter(self._profiles.values())))

    async def stream(
        self,
        request: CompletionRequest,
        session_id: str,
    ) -> AsyncIterator[CanonicalEventType]:
        profile = self.get_profile(request.model)
        cmd = self._build_command(request)
        env = self._build_env(request)
        emitted_session_end = False

        proc = await self._spawn_process(cmd, env)
        self._proc = proc

        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                raw_line = line.decode("utf-8", errors="replace").strip()
                if not raw_line:
                    continue
                events = self._normalize_line(raw_line, session_id=session_id, profile=profile)
                for event in events:
                    if isinstance(event, SessionEnd):
                        emitted_session_end = True
                    yield event

            exit_code = await proc.wait()
            if exit_code != 0 and not emitted_session_end:
                err_text = ""
                if proc.stderr is not None:
                    with contextlib.suppress(Exception):
                        err_text = (
                            (await proc.stderr.read())
                            .decode("utf-8", errors="replace")
                            .strip()
                        )
                yield ErrorEvent(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    code="process_exit",
                    message=err_text or f"claude exited with code {exit_code}",
                    retryable=False,
                )
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=False,
                    error_code="process_exit",
                    error_message=f"claude exited with code {exit_code}",
                )
            elif exit_code == 0 and not emitted_session_end:
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=True,
                )
        finally:
            self._proc = None

    async def cancel(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        self._proc.terminate()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._proc.kill()
            with contextlib.suppress(Exception):
                await self._proc.wait()
        finally:
            self._proc = None

    async def close(self) -> None:
        await self.cancel()

    async def _spawn_process(
        self,
        cmd: list[str],
        env: dict[str, str],
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workdir),
            env=env,
        )

    def _build_env(self, request: CompletionRequest) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        internet_enabled = bool(request.provider_options.get("internet_enabled", True))
        if internet_enabled:
            env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
        else:
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return env

    def _build_command(self, request: CompletionRequest) -> list[str]:
        prompt = self._build_prompt(request)
        cmd = [
            self._cli_path,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]

        if request.resume_session_id:
            cmd.extend(["--resume", request.resume_session_id])
        elif request.provider_options.get("continue_last"):
            cmd.append("--continue")

        model = request.model or self._config.default_model
        if model:
            cmd.extend(["--model", model])

        permission_mode = str(
            request.provider_options.get("permission_mode", "bypassPermissions")
        )
        if permission_mode:
            cmd.extend(["--permission-mode", permission_mode])
            if permission_mode == "bypassPermissions":
                cmd.extend(["--allowedTools", "*", "--dangerously-skip-permissions"])

        max_turns = request.provider_options.get("max_turns")
        if isinstance(max_turns, int) and max_turns > 0:
            cmd.extend(["--max-turns", str(max_turns)])

        if request.system_prompt:
            cmd.extend(["--append-system-prompt", request.system_prompt])

        if request.enable_thinking:
            cmd.append("--include-partial-messages")

        return cmd

    def _build_prompt(self, request: CompletionRequest) -> str:
        # Keep this intentionally simple and deterministic for adapter tests.
        if request.messages:
            rendered: list[str] = []
            for msg in request.messages:
                role = str(msg.get("role", "user")).title()
                content = msg.get("content", "")
                if isinstance(content, list):
                    chunks: list[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            if isinstance(part.get("text"), str):
                                chunks.append(part["text"])
                        elif isinstance(part, str):
                            chunks.append(part)
                    content_text = "\n".join(chunks)
                else:
                    content_text = str(content)
                rendered.append(f"{role}: {content_text}")
            return "\n\n".join(rendered)
        return "Hello."

    def _normalize_line(
        self,
        raw_line: str,
        session_id: str,
        profile: ModelProfile,
    ) -> list[CanonicalEventType]:
        try:
            raw: dict[str, Any] = json.loads(raw_line)
        except Exception:
            raw = {}

        parsed = parse_ndjson_line(raw_line)
        if parsed is None:
            return []

        base = {
            "provider_id": self.provider_id,
            "session_id": session_id,
            "raw": raw,
        }

        events: list[CanonicalEventType] = []

        if isinstance(parsed, LegacySystemInit):
            events.append(
                SessionStart(
                    **base,
                    model=parsed.model,
                    provider_session_id=parsed.session_id or None,
                    capabilities=_capability_names(profile.capabilities),
                    tools_available=parsed.tools,
                    system_info={
                        "cwd": parsed.cwd,
                        "permission_mode": parsed.permission_mode,
                        "claude_code_version": parsed.claude_code_version,
                        "mcp_servers": parsed.mcp_servers,
                    },
                )
            )
            return events

        if isinstance(parsed, LegacyAssistantMessage):
            for idx, block in enumerate(parsed.content_blocks):
                btype = block.get("type")
                if btype == "text":
                    events.append(
                        TextComplete(
                            **base,
                            content=str(block.get("text", "")),
                            content_index=idx,
                            role="assistant",
                        )
                    )
                elif btype == "thinking":
                    events.append(
                        ThinkingComplete(
                            **base,
                            content=str(block.get("thinking", "")),
                            is_redacted=False,
                        )
                    )
                elif btype == "redacted_thinking":
                    events.append(
                        ThinkingComplete(
                            **base,
                            content="",
                            is_redacted=True,
                        )
                    )
                elif btype == "tool_use":
                    arguments = block.get("input", {})
                    if isinstance(arguments, str):
                        arg_text = arguments
                    else:
                        arg_text = json.dumps(arguments)
                    events.append(
                        ToolCallComplete(
                            **base,
                            tool_call_id=str(block.get("id", "")),
                            tool_name=str(block.get("name", "")),
                            arguments=arg_text,
                        )
                    )
            return events

        if isinstance(parsed, LegacyToolResult):
            events.append(
                ToolResult(
                    **base,
                    tool_call_id=parsed.tool_use_id,
                    tool_name=parsed.tool_name,
                    content=parsed.content,
                    is_error=parsed.is_error,
                    structured_result=parsed.structured_result,
                    duration_ms=parsed.duration_ms,
                )
            )
            return events

        if isinstance(parsed, LegacyStreamDelta):
            if parsed.delta_type == "text_delta":
                events.append(
                    TextDelta(
                        **base,
                        content=parsed.content,
                        content_index=parsed.block_index,
                    )
                )
            elif parsed.delta_type == "thinking_delta":
                events.append(ThinkingDelta(**base, content=parsed.content))
            elif parsed.delta_type == "input_json_delta":
                events.append(
                    ToolArgumentsDelta(
                        **base,
                        tool_call_id=parsed.parent_tool_use_id or "",
                        delta=parsed.content,
                    )
                )
            return events

        if isinstance(parsed, LegacyToolProgress):
            events.append(
                ToolProgress(
                    **base,
                    tool_call_id=parsed.tool_use_id,
                    tool_name=parsed.tool_name,
                    elapsed_seconds=parsed.elapsed_seconds,
                )
            )
            return events

        if isinstance(parsed, LegacyTaskStarted):
            events.append(
                TaskStarted(
                    **base,
                    task_id=parsed.task_id,
                    description=parsed.description,
                    parent_tool_call_id=parsed.tool_use_id or None,
                )
            )
            return events

        if isinstance(parsed, LegacyTaskProgress):
            summary = parsed.last_tool_name or ""
            if parsed.usage:
                summary = (summary + " " if summary else "") + f"usage={parsed.usage}"
            events.append(TaskProgress(**base, task_id=parsed.task_id, summary=summary))
            return events

        if isinstance(parsed, LegacyRateLimitEvent):
            events.append(
                RateLimitEvent(
                    **base,
                    status=parsed.status,
                    utilization=parsed.utilization,
                    resets_at=float(parsed.resets_at) if parsed.resets_at else None,
                )
            )
            return events

        if isinstance(parsed, LegacyResultMessage):
            usage = parsed.model_usage or {}
            events.append(
                UsageReport(
                    **base,
                    input_tokens=int(usage.get("input_tokens", 0) or 0),
                    output_tokens=int(usage.get("output_tokens", 0) or 0),
                    cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                    cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                    thinking_tokens=int(usage.get("thinking_tokens", 0) or 0),
                    total_cost_usd=parsed.total_cost_usd,
                    model_breakdown=usage,
                )
            )
            if parsed.is_error:
                message = parsed.errors[0] if parsed.errors else (parsed.result_text or "")
                events.append(
                    ErrorEvent(
                        **base,
                        code=parsed.subtype,
                        message=message or "provider execution failed",
                    )
                )
            events.append(
                SessionEnd(
                    **base,
                    success=not parsed.is_error,
                    error_code=parsed.subtype if parsed.is_error else None,
                    error_message=(
                        parsed.errors[0]
                        if parsed.is_error and parsed.errors
                        else (parsed.result_text if parsed.is_error else None)
                    ),
                )
            )
            return events

        return events
