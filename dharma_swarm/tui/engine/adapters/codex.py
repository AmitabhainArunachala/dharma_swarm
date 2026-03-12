"""Codex CLI adapter for the DGC TUI engine."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, AsyncIterator

from .base import Capability, CompletionRequest, ModelProfile, ProviderAdapter, ProviderConfig
from ..events import ErrorEvent, SessionEnd, SessionStart, TextComplete, UsageReport

DHARMA_SWARM = Path(__file__).resolve().parents[4]

CODEX_CAPABILITIES = (
    Capability.SYSTEM_PROMPT
    | Capability.CANCEL
)


def _capability_names(caps: Capability) -> list[str]:
    names: list[str] = []
    for cap in Capability:
        if caps & cap:
            names.append(cap.name.lower())
    return names


class CodexAdapter(ProviderAdapter):
    """Provider adapter for the locally authenticated Codex CLI."""

    provider_id = "codex"

    def __init__(
        self,
        config: ProviderConfig | None = None,
        cli_path: str = "codex",
        workdir: Path | None = None,
    ) -> None:
        self._config = config or ProviderConfig(
            provider_id=self.provider_id,
            default_model="gpt-5.4",
        )
        self._cli_path = cli_path
        self._workdir = workdir or DHARMA_SWARM
        self._proc: asyncio.subprocess.Process | None = None
        self._profiles: dict[str, ModelProfile] = {
            "gpt-5.4": ModelProfile(
                provider_id=self.provider_id,
                model_id="gpt-5.4",
                display_name="Codex 5.4",
                capabilities=CODEX_CAPABILITIES,
            ),
        }

    async def list_models(self) -> list[ModelProfile]:
        return list(self._profiles.values())

    def get_profile(self, model_id: str | None = None) -> ModelProfile:
        model = model_id or self._config.default_model or "gpt-5.4"
        return self._profiles.get(model, next(iter(self._profiles.values())))

    async def stream(
        self,
        request: CompletionRequest,
        session_id: str,
    ) -> AsyncIterator[SessionStart | TextComplete | UsageReport | ErrorEvent | SessionEnd]:
        profile = self.get_profile(request.model)
        prompt = self._build_prompt(request)
        output_path = Path(
            tempfile.mkstemp(prefix="dgc-codex-last-message-", suffix=".txt")[1]
        )
        cmd = self._build_command(request, output_path=output_path)
        env = self._build_env()
        emitted_session_start = False
        emitted_text = False
        last_error: ErrorEvent | None = None

        proc = await self._spawn_process(cmd, env)
        self._proc = proc

        try:
            try:
                await self._write_prompt(proc, prompt)
            except Exception as exc:
                last_error = ErrorEvent(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    code="stdin_write_error",
                    message=str(exc),
                    retryable=True,
                )
                yield last_error
                with contextlib.suppress(Exception):
                    await self.cancel()
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=False,
                    error_code=last_error.code,
                    error_message=last_error.message,
                )
                return

            assert proc.stdout is not None
            while True:
                try:
                    line = await proc.stdout.readline()
                except Exception as exc:
                    last_error = ErrorEvent(
                        provider_id=self.provider_id,
                        session_id=session_id,
                        code="stream_read_error",
                        message=str(exc),
                        retryable=True,
                    )
                    yield last_error
                    break
                if not line:
                    break
                raw_line = line.decode("utf-8", errors="replace").strip()
                if not raw_line:
                    continue
                for event in self._normalize_line(
                    raw_line,
                    session_id=session_id,
                    profile=profile,
                ):
                    if isinstance(event, SessionStart):
                        emitted_session_start = True
                    elif isinstance(event, TextComplete):
                        emitted_text = True
                    elif isinstance(event, ErrorEvent):
                        last_error = event
                    yield event

            exit_code = await proc.wait()
            if not emitted_session_start:
                yield SessionStart(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    model=profile.model_id,
                    capabilities=_capability_names(profile.capabilities),
                    tools_available=[],
                    system_info={"cli_path": self._cli_path, "cwd": str(self._workdir)},
                )

            last_message = ""
            with contextlib.suppress(Exception):
                last_message = output_path.read_text(encoding="utf-8", errors="ignore").strip()
            if last_message and not emitted_text:
                emitted_text = True
                yield TextComplete(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    content=last_message,
                    role="assistant",
                )

            if exit_code != 0:
                err_text = await self._read_stderr(proc)
                error = last_error or ErrorEvent(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    code="process_exit",
                    message=err_text or f"codex exited with code {exit_code}",
                    retryable=False,
                )
                if last_error is None:
                    yield error
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=False,
                    error_code=error.code or "process_exit",
                    error_message=error.message or f"codex exited with code {exit_code}",
                )
                return

            yield SessionEnd(
                provider_id=self.provider_id,
                session_id=session_id,
                success=True,
            )
        finally:
            self._proc = None
            with contextlib.suppress(Exception):
                output_path.unlink()

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
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workdir),
            env=env,
        )

    def _build_env(self) -> dict[str, str]:
        return dict(os.environ)

    def _build_command(
        self,
        request: CompletionRequest,
        *,
        output_path: Path,
    ) -> list[str]:
        model = request.model or self._config.default_model or "gpt-5.4"
        cmd = [
            self._cli_path,
            "exec",
            "-m",
            model,
            "--json",
            "--full-auto",
            "--color",
            "never",
            "-C",
            str(self._workdir),
            "-o",
            str(output_path),
            "-",
        ]
        return cmd

    async def _write_prompt(
        self,
        proc: asyncio.subprocess.Process,
        prompt: str,
    ) -> None:
        if proc.stdin is None:
            raise RuntimeError("codex subprocess stdin is unavailable")
        payload = prompt if prompt.endswith("\n") else f"{prompt}\n"
        proc.stdin.write(payload.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
        wait_closed = getattr(proc.stdin, "wait_closed", None)
        if callable(wait_closed):
            with contextlib.suppress(Exception):
                await wait_closed()

    def _build_prompt(self, request: CompletionRequest) -> str:
        rendered: list[str] = []
        if request.system_prompt:
            rendered.append(f"System:\n{request.system_prompt.strip()}")
        for msg in request.messages:
            role = str(msg.get("role", "user")).title()
            content = msg.get("content", "")
            if isinstance(content, list):
                chunks: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str):
                            chunks.append(text)
                    elif isinstance(part, str):
                        chunks.append(part)
                content_text = "\n".join(chunks)
            else:
                content_text = str(content)
            rendered.append(f"{role}: {content_text}")
        return "\n\n".join(rendered) if rendered else "Hello."

    async def _read_stderr(self, proc: asyncio.subprocess.Process) -> str:
        if proc.stderr is None:
            return ""
        with contextlib.suppress(Exception):
            return (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        return ""

    def _normalize_line(
        self,
        raw_line: str,
        *,
        session_id: str,
        profile: ModelProfile,
    ) -> list[SessionStart | TextComplete | UsageReport | ErrorEvent]:
        try:
            raw: dict[str, Any] = json.loads(raw_line)
        except Exception:
            return []

        base = {
            "provider_id": self.provider_id,
            "session_id": session_id,
            "raw": raw,
        }
        event_type = str(raw.get("type", "") or "")
        if event_type == "thread.started":
            provider_session_id = str(raw.get("thread_id", "") or "") or None
            return [
                SessionStart(
                    **base,
                    model=profile.model_id,
                    provider_session_id=provider_session_id,
                    capabilities=_capability_names(profile.capabilities),
                    tools_available=[],
                    system_info={"cli_path": self._cli_path, "cwd": str(self._workdir)},
                )
            ]
        if event_type == "item.completed":
            item = raw.get("item")
            if isinstance(item, dict):
                item_type = str(item.get("type", "") or "")
                if item_type == "message":
                    content = _extract_message_text(item)
                    if content:
                        return [TextComplete(**base, content=content, role="assistant")]
                if item_type == "error":
                    message = str(item.get("message", "") or "").strip()
                    if message:
                        code, retryable = _classify_error(message)
                        return [
                            ErrorEvent(
                                **base,
                                code=code,
                                message=message,
                                retryable=retryable,
                            )
                        ]
        if event_type == "turn.completed":
            usage = raw.get("usage")
            if isinstance(usage, dict):
                return [
                    UsageReport(
                        **base,
                        input_tokens=int(usage.get("input_tokens", 0) or 0),
                        output_tokens=int(usage.get("output_tokens", 0) or 0),
                        total_cost_usd=_coerce_float(usage.get("total_cost_usd")),
                        model_breakdown=usage,
                    )
                ]
        if event_type == "error":
            message = str(raw.get("message", "") or "").strip()
            if message:
                code, retryable = _classify_error(message)
                return [
                    ErrorEvent(
                        **base,
                        code=code,
                        message=message,
                        retryable=retryable,
                    )
                ]
        return []


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _classify_error(message: str) -> tuple[str, bool]:
    lower = message.lower()
    if "out of extra usage" in lower:
        return ("usage_exhausted", False)
    if "rate limit" in lower or "rejected" in lower:
        return ("rate_limit", True)
    if "logged in" in lower or "sign in" in lower or "unauthorized" in lower:
        return ("missing_auth", False)
    if "lookup address" in lower or "timed out" in lower or "disconnected" in lower:
        return ("transport_error", True)
    return ("codex_error", False)


def _extract_message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            chunks.append(part["text"])
            continue
        if isinstance(part.get("content"), str):
            chunks.append(part["content"])
            continue
        if isinstance(part.get("content"), list):
            for nested in part["content"]:
                if isinstance(nested, dict) and isinstance(nested.get("text"), str):
                    chunks.append(nested["text"])
    return "\n".join(chunk for chunk in chunks if chunk).strip()
