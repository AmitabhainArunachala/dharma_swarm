"""KaizenOps ingest client for canonical operator telemetry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class KaizenOpsError(RuntimeError):
    """Raised when KaizenOps API requests fail."""


@dataclass(slots=True)
class KaizenOpsConfig:
    """Runtime configuration for KaizenOps service."""

    base_url: str = "http://127.0.0.1:8765"
    timeout_sec: float = 10.0
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "KaizenOpsConfig":
        return cls(
            base_url=os.getenv("DGC_KAIZENOPS_URL", "http://127.0.0.1:8765"),
            timeout_sec=float(os.getenv("DGC_KAIZENOPS_TIMEOUT_SEC", "10")),
            api_key=os.getenv("DGC_KAIZENOPS_API_KEY"),
        )


class KaizenOpsClient:
    """Typed HTTP client for KaizenOps ingest endpoints."""

    def __init__(
        self,
        config: KaizenOpsConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or KaizenOpsConfig.from_env()
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config.api_key:
            headers["X-Kaizen-Key"] = self.config.api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
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
                )
        except httpx.RequestError as exc:
            raise KaizenOpsError(f"{method} {url} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise KaizenOpsError(
                f"{method} {url} failed: {resp.status_code} {resp.text[:300]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise KaizenOpsError(
                f"{method} {url} returned invalid JSON: {exc}"
            ) from exc
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def ingest_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/ingest/events",
            json_body={"events": list(events)},
        )


__all__ = [
    "KaizenOpsClient",
    "KaizenOpsConfig",
    "KaizenOpsError",
]
