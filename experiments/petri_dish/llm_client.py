"""Thin async LLM client for OpenRouter.

Zero dharma_swarm imports. Uses the openai SDK pointed at OpenRouter,
replicating the pattern from providers.py:224-271.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class PetriDishLLM:
    """Minimal async OpenRouter client for the petri dish experiment."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._base_url = base_url
        self._client: Any = None
        self._total_calls = 0
        self._total_tokens = 0

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        return self._client

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
        """Single completion call. Returns content string.

        If `messages` is provided, it is used as the conversation history
        (system prompt is still prepended). Otherwise, a single user message
        is constructed from `user_message`.
        """
        client = self._get_client()

        msg_list: list[dict[str, str]] = [{"role": "system", "content": system}]
        if messages:
            msg_list.extend(messages)
        else:
            msg_list.append({"role": "user", "content": user_message})

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=msg_list,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            self._total_calls += 1
            if resp.usage:
                self._total_tokens += resp.usage.total_tokens
            content = resp.choices[0].message.content or ""
            return content
        except Exception as e:
            logger.error("LLM call failed (model=%s): %s", model, e)
            raise

    @property
    def stats(self) -> dict[str, int]:
        return {"total_calls": self._total_calls, "total_tokens": self._total_tokens}
