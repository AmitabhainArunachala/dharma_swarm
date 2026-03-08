"""NVIDIA Data Flywheel Blueprint client."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx


class DataFlywheelError(RuntimeError):
    """Raised when Data Flywheel API requests fail."""


@dataclass(slots=True)
class DataFlywheelConfig:
    """Runtime configuration for Data Flywheel service."""

    base_url: str = "http://127.0.0.1:8000/api"
    timeout_sec: float = 30.0
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "DataFlywheelConfig":
        return cls(
            base_url=os.getenv("DGC_DATA_FLYWHEEL_URL", "http://127.0.0.1:8000/api"),
            timeout_sec=float(os.getenv("DGC_DATA_FLYWHEEL_TIMEOUT_SEC", "30")),
            api_key=os.getenv("DGC_DATA_FLYWHEEL_API_KEY"),
        )


class DataFlywheelClient:
    """Typed HTTP client for Data Flywheel job lifecycle."""

    TERMINAL_STATES = {"completed", "failed", "cancelled"}

    def __init__(
        self,
        config: DataFlywheelConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or DataFlywheelConfig.from_env()
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
        if resp.status_code >= 400:
            raise DataFlywheelError(
                f"{method} {url} failed: {resp.status_code} {resp.text[:300]}"
            )
        data = resp.json()
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def create_job(
        self,
        *,
        workload_id: str,
        client_id: str,
        data_split_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "workload_id": workload_id,
            "client_id": client_id,
        }
        if data_split_config:
            payload["data_split_config"] = data_split_config
        return await self._request("POST", "/jobs", json_body=payload)

    async def list_jobs(self) -> dict[str, Any]:
        return await self._request("GET", "/jobs")

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/jobs/{job_id}")

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/jobs/{job_id}/cancel")

    async def delete_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/jobs/{job_id}")

    async def wait_for_terminal(
        self,
        job_id: str,
        *,
        poll_sec: float = 5.0,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Wait until a job reaches terminal status."""
        elapsed = 0.0
        while elapsed <= timeout_sec:
            job = await self.get_job(job_id)
            status = str(job.get("status", "")).lower()
            if status in self.TERMINAL_STATES:
                return job
            await asyncio.sleep(poll_sec)
            elapsed += poll_sec
        raise DataFlywheelError(
            f"Timed out waiting for flywheel job {job_id} after {timeout_sec:.1f}s"
        )

