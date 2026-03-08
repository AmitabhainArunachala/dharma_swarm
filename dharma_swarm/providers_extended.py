"""Extended LLM Providers for Subconscious Fleet.

Adds support for:
- Ollama (local models)
- NVIDIA NIM (NVIDIA Inference Microservices)
- Moonshot (Moonshot AI)
- Groq (fast inference)
- Deepseek
- Together AI
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import httpx

from dharma_swarm.models import LLMRequest, LLMResponse
from dharma_swarm.providers import LLMProvider


class OllamaProvider(LLMProvider):
    """Provider for local Ollama models.

    No API key required - runs locally.
    Default models: llama3.2, qwen2.5, mistral, etc.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "llama3.2",
    ):
        self.base_url = base_url or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.default_model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Call Ollama generate API."""
        model = request.model or self.default_model

        # Build prompt from messages
        prompt = ""
        if request.system:
            prompt += f"{request.system}\n\n"
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                prompt += f"User: {content}\n\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n\n"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")

            data = resp.json()

            return LLMResponse(
                content=data.get("response", ""),
                model=model,
                usage={
                    "input_tokens": data.get("prompt_eval_count", 0),
                    "output_tokens": data.get("eval_count", 0),
                },
                tool_calls=[],
                stop_reason="stop",
            )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream not implemented for Ollama yet."""
        # Could implement with stream=True, but not needed for subconscious
        raise NotImplementedError("Ollama streaming not implemented")
        yield  # Make it a generator


class NVIDIANIMProvider(LLMProvider):
    """Provider for NVIDIA Inference Microservices.

    Requires NVIDIA_NIM_API_KEY.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._api_key = api_key or os.environ.get("NVIDIA_NIM_API_KEY")
        self.base_url = base_url or os.environ.get(
            "NVIDIA_NIM_BASE_URL",
            "https://integrate.api.nvidia.com/v1",
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Call NVIDIA NIM API (OpenAI-compatible)."""
        if not self._api_key:
            raise RuntimeError("NVIDIA_NIM_API_KEY not set")

        # NIM uses OpenAI-compatible API
        payload = {
            "model": request.model or "meta/llama-3.3-70b-instruct",
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"NVIDIA NIM error {resp.status_code}: {resp.text}")

            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]

            return LLMResponse(
                content=message.get("content", ""),
                model=data.get("model", request.model),
                usage=data.get("usage", {}),
                tool_calls=[],
                stop_reason=choice.get("finish_reason", "stop"),
            )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream not implemented yet."""
        raise NotImplementedError("NVIDIA NIM streaming not implemented")
        yield  # Make it a generator


class MoonshotProvider(LLMProvider):
    """Provider for Moonshot AI models.

    Requires MOONSHOT_API_KEY.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._api_key = api_key or os.environ.get("MOONSHOT_API_KEY")
        self.base_url = base_url or os.environ.get(
            "MOONSHOT_BASE_URL",
            "https://api.moonshot.cn/v1",
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Call Moonshot API (OpenAI-compatible)."""
        if not self._api_key:
            raise RuntimeError("MOONSHOT_API_KEY not set")

        payload = {
            "model": request.model or "moonshot-v1-8k",
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Moonshot error {resp.status_code}: {resp.text}")

            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]

            return LLMResponse(
                content=message.get("content", ""),
                model=data.get("model", request.model),
                usage=data.get("usage", {}),
                tool_calls=[],
                stop_reason=choice.get("finish_reason", "stop"),
            )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream not implemented yet."""
        raise NotImplementedError("Moonshot streaming not implemented")
        yield  # Make it a generator
