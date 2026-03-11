"""NVIDIA RAG Blueprint client.

Supports both services exposed by the blueprint:
- rag-server (default :8081)
- ingestor-server (default :8082)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class NvidiaRagError(RuntimeError):
    """Raised when NVIDIA RAG API requests fail."""


@dataclass(slots=True)
class NvidiaRagConfig:
    """Runtime configuration for NVIDIA RAG endpoints."""

    rag_base_url: str = "http://127.0.0.1:8081/v1"
    ingest_base_url: str = "http://127.0.0.1:8082/v1"
    timeout_sec: float = 30.0
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "NvidiaRagConfig":
        return cls(
            rag_base_url=os.getenv("DGC_NVIDIA_RAG_URL", "http://127.0.0.1:8081/v1"),
            ingest_base_url=os.getenv(
                "DGC_NVIDIA_INGEST_URL", "http://127.0.0.1:8082/v1"
            ),
            timeout_sec=float(os.getenv("DGC_NVIDIA_TIMEOUT_SEC", "30")),
            api_key=os.getenv("NVIDIA_NIM_API_KEY"),
        )


class NvidiaRagClient:
    """Typed HTTP client for NVIDIA RAG blueprint services."""

    def __init__(
        self,
        config: NvidiaRagConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or NvidiaRagConfig.from_env()
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_sec,
                transport=self._transport,
            ) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise NvidiaRagError(f"{method} {url} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise NvidiaRagError(f"{method} {url} failed: {resp.status_code} {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise NvidiaRagError(f"{method} {url} returned invalid JSON: {exc}") from exc
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def health(
        self,
        *,
        service: str = "rag",
        check_dependencies: bool = True,
    ) -> dict[str, Any]:
        """Check health for rag-server or ingestor-server."""
        base = (
            self.config.rag_base_url
            if service == "rag"
            else self.config.ingest_base_url
        )
        return await self._request(
            "GET",
            base,
            "/health",
            params={"check_dependencies": str(check_dependencies).lower()},
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        collection_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run retrieval query through rag-server."""
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if collection_name:
            payload["collection_name"] = collection_name
        if filters:
            payload["filters"] = filters
        return await self._request("POST", self.config.rag_base_url, "/search", json_body=payload)

    async def chat(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Request grounded answer from rag-server chat endpoint."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if model:
            payload["model"] = model
        return await self._request(
            "POST", self.config.rag_base_url, "/chat/completions", json_body=payload
        )

    async def list_documents(self, *, limit: int = 50) -> dict[str, Any]:
        """List ingested documents from ingestor-server."""
        return await self._request(
            "GET",
            self.config.ingest_base_url,
            "/documents",
            params={"limit": limit},
        )

    async def submit_ingestion(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit ingestion task using ingestor-server /documents endpoint."""
        return await self._request(
            "POST",
            self.config.ingest_base_url,
            "/documents",
            json_body=payload,
        )

    async def get_ingestion_task(self, task_id: str) -> dict[str, Any]:
        """Get ingestion task status."""
        return await self._request(
            "GET",
            self.config.ingest_base_url,
            f"/documents/{task_id}",
        )
