"""Tests for dharma_swarm.integrations.data_flywheel."""

from __future__ import annotations

import httpx
import pytest

from dharma_swarm.integrations import (
    DataFlywheelClient,
    DataFlywheelConfig,
    DataFlywheelError,
)


@pytest.mark.asyncio
async def test_create_job_posts_expected_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/jobs"
        body = request.content.decode("utf-8")
        assert '"workload_id":"w1"' in body
        assert '"client_id":"c1"' in body
        return httpx.Response(200, json={"id": "job-1", "status": "queued"})

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.create_job(workload_id="w1", client_id="c1")
    assert out["id"] == "job-1"


@pytest.mark.asyncio
async def test_list_jobs_calls_get():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/jobs"
        return httpx.Response(200, json={"jobs": [{"id": "j1"}]})

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.list_jobs()
    assert out["jobs"][0]["id"] == "j1"


@pytest.mark.asyncio
async def test_cancel_job_calls_post_cancel():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/jobs/job-1/cancel"
        return httpx.Response(200, json={"id": "job-1", "status": "cancelled"})

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.cancel_job("job-1")
    assert out["status"] == "cancelled"


@pytest.mark.asyncio
async def test_wait_for_terminal_returns_completed():
    calls = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"id": "job-1", "status": "running"})
        return httpx.Response(200, json={"id": "job-1", "status": "completed"})

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.wait_for_terminal("job-1", poll_sec=0.0, timeout_sec=1.0)
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_wait_for_terminal_zero_poll_interval_still_times_out(monkeypatch):
    calls = {"n": 0}
    ticks = iter([10.0, 10.0, 10.2])

    def _handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"id": "job-1", "status": "running"})

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    monkeypatch.setattr(
        "dharma_swarm.integrations.data_flywheel._now",
        lambda: next(ticks),
    )

    with pytest.raises(DataFlywheelError, match="Timed out waiting for flywheel job job-1"):
        await client.wait_for_terminal("job-1", poll_sec=0.0, timeout_sec=0.1)

    assert calls["n"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"poll_sec": -0.1, "timeout_sec": 1.0}, "poll_sec must be a finite number >= 0"),
        ({"poll_sec": 0.1, "timeout_sec": -1.0}, "timeout_sec must be a finite number >= 0"),
    ],
)
async def test_wait_for_terminal_rejects_negative_timing_inputs(kwargs, message):
    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"id": "job-1", "status": "running"})
        ),
    )

    with pytest.raises(DataFlywheelError, match=message):
        await client.wait_for_terminal("job-1", **kwargs)


@pytest.mark.asyncio
async def test_http_error_raises_data_flywheel_error():
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(DataFlywheelError, match="failed: 500"):
        await client.list_jobs()


@pytest.mark.asyncio
async def test_invalid_json_raises_data_flywheel_error():
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(DataFlywheelError, match="returned invalid JSON"):
        await client.list_jobs()


@pytest.mark.asyncio
async def test_transport_error_raises_data_flywheel_error():
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    client = DataFlywheelClient(
        config=DataFlywheelConfig(base_url="http://fly.local/api"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(DataFlywheelError, match="failed: unreachable"):
        await client.list_jobs()
