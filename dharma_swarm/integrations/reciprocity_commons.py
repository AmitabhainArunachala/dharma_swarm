"""Planetary Reciprocity Commons integration client for DGC.

This is the thin native layer that should remain in DGC even after the
reciprocity stack grows into its own repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class ReciprocityCommonsError(RuntimeError):
    """Raised when Reciprocity Commons API requests fail."""


@dataclass(slots=True)
class ReciprocityCommonsConfig:
    """Runtime configuration for Planetary Reciprocity Commons service."""

    base_url: str = "http://127.0.0.1:8095/v1"
    timeout_sec: float = 30.0
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "ReciprocityCommonsConfig":
        return cls(
            base_url=os.getenv(
                "DGC_RECIPROCITY_COMMONS_URL",
                "http://127.0.0.1:8095/v1",
            ),
            timeout_sec=float(
                os.getenv("DGC_RECIPROCITY_COMMONS_TIMEOUT_SEC", "30")
            ),
            api_key=os.getenv("DGC_RECIPROCITY_COMMONS_API_KEY"),
        )


class ReciprocityCommonsClient:
    """Typed HTTP client for future reciprocity-ledger and pilot services."""

    def __init__(
        self,
        config: ReciprocityCommonsConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or ReciprocityCommonsConfig.from_env()
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_sec,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise ReciprocityCommonsError(f"{method} {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise ReciprocityCommonsError(
                f"{method} {url} failed: {response.status_code} "
                f"{response.text[:300]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ReciprocityCommonsError(
                f"{method} {url} returned invalid JSON: {exc}"
            ) from exc
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def publish_activity(self, record: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/activities", json_body=record)

    async def publish_obligation(self, record: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/obligations", json_body=record)

    async def publish_project(self, record: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/projects", json_body=record)

    async def publish_outcome(self, record: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/outcomes", json_body=record)

    async def ledger_summary(self) -> dict[str, Any]:
        return await self._request("GET", "/ledger/summary")
