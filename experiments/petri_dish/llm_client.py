"""Thin async LLM client for the petri dish.

Uses the canonical dharma_swarm runtime-provider preference:
Ollama -> NVIDIA NIM -> OpenRouter Free -> OpenRouter.
"""

from __future__ import annotations

import logging
from typing import Any

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.runtime_provider import (
    create_runtime_provider,
    preferred_runtime_provider_configs,
)

logger = logging.getLogger(__name__)


class PetriDishLLM:
    """Minimal async client that respects the canonical low-cost provider order."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        # Kept for backward compatibility with existing tests/call sites.
        self._api_key = api_key
        self._base_url = base_url
        self._total_calls = 0
        self._total_tokens = 0

    async def complete(
        self,
        system: str,
        user_message: str,
        *,
        model: str = "meta-llama/llama-3.3-70b-instruct:free",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Single completion call via preferred runtime providers."""
        msg_list: list[dict[str, str]]
        if messages:
            msg_list = list(messages)
        else:
            msg_list = [{"role": "user", "content": user_message}]

        configs = preferred_runtime_provider_configs(
            model_overrides={
                ProviderType.OPENROUTER_FREE: model,
                ProviderType.OPENROUTER: model,
            }
        )
        if not configs:
            raise RuntimeError(
                "No preferred providers available; configure Ollama, NVIDIA NIM, or OpenRouter"
            )

        last_exc: Exception | None = None
        for config in configs:
            provider = create_runtime_provider(config)
            try:
                response = await provider.complete(
                    LLMRequest(
                        model=config.default_model or model,
                        system=system,
                        messages=msg_list,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                )
                self._total_calls += 1
                usage = response.usage or {}
                if "total_tokens" in usage:
                    try:
                        self._total_tokens += int(usage["total_tokens"])
                    except (TypeError, ValueError):
                        pass
                elif "prompt_tokens" in usage or "completion_tokens" in usage:
                    try:
                        self._total_tokens += int(usage.get("prompt_tokens", 0)) + int(
                            usage.get("completion_tokens", 0)
                        )
                    except (TypeError, ValueError):
                        pass
                return response.content
            except Exception as exc:
                last_exc = exc
                logger.error(
                    "LLM call failed (provider=%s, model=%s): %s",
                    config.provider.value,
                    config.default_model or model,
                    exc,
                )
            finally:
                close = getattr(provider, "close", None)
                if callable(close):
                    await close()

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Provider chain exhausted without an explicit error")

    @property
    def stats(self) -> dict[str, int]:
        return {"total_calls": self._total_calls, "total_tokens": self._total_tokens}
