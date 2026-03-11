"""OpenRouter adapter for TUI model switching and fallback."""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any, AsyncIterator

import httpx

from .base import Capability, CompletionRequest, ModelProfile, ProviderAdapter, ProviderConfig
from ..events import ErrorEvent, SessionEnd, SessionStart, TextComplete, UsageReport

OPENROUTER_CAPABILITIES = (
    Capability.SYSTEM_PROMPT
    | Capability.COST_TRACKING
    | Capability.CANCEL
)


class OpenRouterAdapter(ProviderAdapter):
    """Provider adapter for OpenRouter chat completions."""

    provider_id = "openrouter"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            provider_id=self.provider_id,
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-5-codex",
        )
        self._cancelled = False
        self._profiles: dict[str, ModelProfile] = {
            "openai/gpt-5-codex": ModelProfile(
                provider_id=self.provider_id,
                model_id="openai/gpt-5-codex",
                display_name="Codex 5.4 (OpenRouter)",
                capabilities=OPENROUTER_CAPABILITIES,
            ),
            "google/gemini-2.5-pro": ModelProfile(
                provider_id=self.provider_id,
                model_id="google/gemini-2.5-pro",
                display_name="Gemini 3 class (OpenRouter)",
                capabilities=OPENROUTER_CAPABILITIES,
            ),
        }

    async def list_models(self) -> list[ModelProfile]:
        return list(self._profiles.values())

    def get_profile(self, model_id: str | None = None) -> ModelProfile:
        model = model_id or self._config.default_model or "openai/gpt-5-codex"
        return self._profiles.get(model, next(iter(self._profiles.values())))

    async def stream(
        self,
        request: CompletionRequest,
        session_id: str,
    ) -> AsyncIterator[SessionStart | TextComplete | UsageReport | ErrorEvent | SessionEnd]:
        profile = self.get_profile(request.model)
        model = request.model or profile.model_id
        self._cancelled = False

        yield SessionStart(
            provider_id=self.provider_id,
            session_id=session_id,
            model=model,
            capabilities=[c.name.lower() for c in Capability if profile.capabilities & c],
            tools_available=[],
            system_info={"base_url": self._config.base_url or "https://openrouter.ai/api/v1"},
        )

        api_key = (
            self._config.api_key
            or request.provider_options.get("openrouter_api_key")
            or os.environ.get("OPENROUTER_API_KEY")
        )
        if not api_key:
            yield ErrorEvent(
                provider_id=self.provider_id,
                session_id=session_id,
                code="missing_api_key",
                message="OPENROUTER_API_KEY not set",
                retryable=False,
            )
            yield SessionEnd(
                provider_id=self.provider_id,
                session_id=session_id,
                success=False,
                error_code="missing_api_key",
                error_message="OPENROUTER_API_KEY not set",
            )
            return

        base_url = (self._config.base_url or "https://openrouter.ai/api/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        messages = request.messages or []
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if request.system_prompt:
            payload["messages"] = [
                {"role": "system", "content": request.system_prompt},
                *messages,
            ]
        if request.max_tokens is not None:
            payload["max_tokens"] = int(request.max_tokens)
        if request.temperature is not None:
            payload["temperature"] = float(request.temperature)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = float(request.provider_options.get("timeout_sec", 120))
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if self._cancelled:
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=False,
                    error_code="cancelled",
                    error_message="request cancelled",
                )
                return

            if resp.status_code >= 400:
                msg = resp.text.strip()[:1000]
                code = "rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}"
                yield ErrorEvent(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    code=code,
                    message=msg or f"HTTP {resp.status_code}",
                    retryable=resp.status_code in {408, 409, 429, 500, 502, 503, 504},
                )
                yield SessionEnd(
                    provider_id=self.provider_id,
                    session_id=session_id,
                    success=False,
                    error_code=code,
                    error_message=msg or f"HTTP {resp.status_code}",
                )
                return

            data = resp.json()
            content = _extract_content(data)
            yield TextComplete(
                provider_id=self.provider_id,
                session_id=session_id,
                content=content,
                role="assistant",
            )
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            yield UsageReport(
                provider_id=self.provider_id,
                session_id=session_id,
                input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage.get("completion_tokens", 0) or 0),
                total_cost_usd=_extract_cost(data),
                model_breakdown=usage if isinstance(usage, dict) else {},
            )
            yield SessionEnd(
                provider_id=self.provider_id,
                session_id=session_id,
                success=True,
            )
        except httpx.TimeoutException:
            yield ErrorEvent(
                provider_id=self.provider_id,
                session_id=session_id,
                code="timeout",
                message="OpenRouter request timed out",
                retryable=True,
            )
            yield SessionEnd(
                provider_id=self.provider_id,
                session_id=session_id,
                success=False,
                error_code="timeout",
                error_message="OpenRouter request timed out",
            )
        except Exception as exc:
            yield ErrorEvent(
                provider_id=self.provider_id,
                session_id=session_id,
                code="openrouter_error",
                message=str(exc),
                retryable=False,
            )
            yield SessionEnd(
                provider_id=self.provider_id,
                session_id=session_id,
                success=False,
                error_code="openrouter_error",
                error_message=str(exc),
            )

    async def cancel(self) -> None:
        self._cancelled = True
        # keep API parity with other adapters
        await asyncio.sleep(0)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.cancel()


def _extract_content(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    msg = first.get("message", {})
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str):
                        chunks.append(txt)
            return "\n".join(chunks)
    return ""


def _extract_cost(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    usage = data.get("usage", {})
    if isinstance(usage, dict):
        # OpenRouter can include either total_cost or cost
        for key in ("total_cost", "cost"):
            if key in usage:
                try:
                    return float(usage[key])
                except Exception:
                    pass
    return None
