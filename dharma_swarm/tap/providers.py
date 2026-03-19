"""Provider routing for TAP — free providers first, always.

Priority order:
1. Ollama Cloud (GLM-5, free, proven high recognition)
2. NVIDIA NIM (Llama 3.3 70B, free, proven working)
3. OpenRouter (paid — OVERFLOW ONLY)

This module exists because Claude keeps forgetting to use free providers
and burns OpenRouter credits. This is a hard constraint, not a suggestion.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Any

from openai import OpenAI


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    model: str
    base_url: str
    key_env: str  # environment variable name for API key
    is_free: bool = True
    _healthy: bool = True
    _health_checked_at: float = 0.0

    @property
    def api_key(self) -> str:
        return os.environ.get(self.key_env, "").strip()

    @property
    def available(self) -> bool:
        return bool(self.api_key)


# The canonical provider list — ORDER MATTERS
DEFAULT_PROVIDERS = [
    ProviderConfig(
        name="ollama_cloud",
        model="glm-5:cloud",
        base_url="https://ollama.com/v1",
        key_env="OLLAMA_API_KEY",
        is_free=True,
    ),
    ProviderConfig(
        name="nvidia_nim",
        model="meta/llama-3.3-70b-instruct",
        base_url="https://integrate.api.nvidia.com/v1",
        key_env="NIM_API_KEY",
        is_free=True,
    ),
    ProviderConfig(
        name="openrouter",
        model="deepseek/deepseek-chat-v3-0324",
        base_url="https://openrouter.ai/api/v1",
        key_env="OPENROUTER_API_KEY",
        is_free=False,
    ),
]

HEALTH_CHECK_TTL = 60.0  # seconds
REQUEST_TIMEOUT_SECONDS = 45.0
NO_PROVIDERS_AVAILABLE_ERROR = "No providers available for TAP call"
_TEXT_FIELDS = (
    "content",
    "text",
    "reasoning",
    "reasoning_content",
    "reasoning_text",
    "output_text",
)


def _coerce_message_text(value: Any) -> str:
    """Collapse OpenAI-compatible message payloads into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks = [_coerce_message_text(item) for item in value]
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if isinstance(value, dict):
        for field in _TEXT_FIELDS:
            text = _coerce_message_text(value.get(field))
            if text:
                return text
        text = _coerce_message_text(value.get("value"))
        if text:
            return text
        return ""
    for field in _TEXT_FIELDS:
        text = _coerce_message_text(getattr(value, field, None))
        if text:
            return text
    text = _coerce_message_text(getattr(value, "value", None))
    if text:
        return text
    return ""


def _extract_choice_text(choice: Any) -> str:
    """Extract text from a chat/completions choice across provider variants."""
    if choice is None:
        return ""

    for field in ("message", "delta", "text", "output_text"):
        text = _coerce_message_text(getattr(choice, field, None))
        if text:
            return text

    if isinstance(choice, dict):
        for field in ("message", "delta", "text", "output_text"):
            text = _coerce_message_text(choice.get(field))
            if text:
                return text

    return _coerce_message_text(choice)


def _extract_response_text(response: Any) -> str:
    """Extract plain text from an OpenAI-compatible response payload."""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")

    if choices:
        for choice in choices:
            text = _extract_choice_text(choice)
            if text:
                return text

    return _coerce_message_text(response)


class TAPProviderRouter:
    """Routes LLM calls through available providers, free first."""

    def __init__(
        self,
        providers: list[ProviderConfig] | None = None,
        request_timeout: float | None = REQUEST_TIMEOUT_SECONDS,
    ):
        source = DEFAULT_PROVIDERS if providers is None else providers
        # Health cache state is router-local; do not share it across instances.
        self.providers = [
            replace(provider, _healthy=True, _health_checked_at=0.0)
            for provider in source
        ]
        self.request_timeout = request_timeout

    def _request_kwargs(self) -> dict[str, Any]:
        if self.request_timeout is None:
            return {}
        return {"timeout": self.request_timeout}

    def get_client(self, provider: ProviderConfig) -> OpenAI:
        """Create OpenAI-compatible client for a provider."""
        return OpenAI(api_key=provider.api_key, base_url=provider.base_url)

    def _mark_unhealthy(self, provider: ProviderConfig) -> None:
        provider._healthy = False
        provider._health_checked_at = time.time()

    def health_check(self, provider: ProviderConfig) -> bool:
        """Check if provider is responding. Cached for HEALTH_CHECK_TTL seconds."""
        if not provider.available:
            return False

        now = time.time()
        if now - provider._health_checked_at < HEALTH_CHECK_TTL:
            return provider._healthy

        try:
            client = self.get_client(provider)
            r = client.chat.completions.create(
                model=provider.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
                **self._request_kwargs(),
            )
            content = _extract_response_text(r)
            provider._healthy = bool(content)
            if not provider._healthy:
                provider._health_checked_at = now
                return False
        except Exception:
            self._mark_unhealthy(provider)

        provider._health_checked_at = now
        return provider._healthy

    def get_next_available(self, exclude_model: str | None = None) -> ProviderConfig | None:
        """Get the next available provider, preferring free ones.

        Args:
            exclude_model: If provided, skip providers with this model
                           (used to ensure scorer uses different model than scored agent).
        """
        for provider in self.providers:
            if not provider.available:
                continue
            if exclude_model and provider.model == exclude_model:
                continue
            if self.health_check(provider):
                return provider
        return None

    def call(
        self,
        messages: list[dict[str, str]],
        exclude_model: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """Make an LLM call through the best available provider.

        Returns (response_text, model_used).
        Raises RuntimeError if no providers available.
        """
        for provider in self.providers:
            if not provider.available:
                continue
            if exclude_model and provider.model == exclude_model:
                continue
            if not self.health_check(provider):
                continue

            try:
                client = self.get_client(provider)
                r = client.chat.completions.create(
                    model=provider.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **self._request_kwargs(),
                    **kwargs,
                )
                content = _extract_response_text(r)
                if content:
                    return content, provider.model
                self._mark_unhealthy(provider)
            except Exception:
                self._mark_unhealthy(provider)
                continue

        raise RuntimeError(NO_PROVIDERS_AVAILABLE_ERROR)
