"""Tests for dharma_swarm.integrations.kaizen_ops."""

from __future__ import annotations

import httpx
import pytest

from dharma_swarm.integrations import KaizenOpsClient, KaizenOpsConfig, KaizenOpsError


@pytest.mark.asyncio
async def test_ingest_events_posts_expected_payload_and_api_key() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/ingest/events"
        assert request.headers["X-Kaizen-Key"] == "secret-key"
        body = request.content.decode("utf-8")
        assert '"agent_id":"agent-1"' in body
        assert '"session_id":"sess-1"' in body
        return httpx.Response(200, json={"accepted": 1})

    client = KaizenOpsClient(
        config=KaizenOpsConfig(
            base_url="http://kaizen.local",
            api_key="secret-key",
        ),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.ingest_events(
        [
            {
                "agent_id": "agent-1",
                "session_id": "sess-1",
                "category": "evaluation",
                "intent": "record_evaluation",
                "timestamp": "2026-03-19T00:00:00+00:00",
            }
        ]
    )
    assert out["accepted"] == 1


@pytest.mark.asyncio
async def test_http_error_raises_kaizen_ops_error() -> None:
    client = KaizenOpsClient(
        config=KaizenOpsConfig(base_url="http://kaizen.local"),
        transport=httpx.MockTransport(lambda _: httpx.Response(500, text="boom")),
    )
    with pytest.raises(KaizenOpsError, match="failed: 500"):
        await client.ingest_events([])


@pytest.mark.asyncio
async def test_transport_error_raises_kaizen_ops_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = KaizenOpsClient(
        config=KaizenOpsConfig(base_url="http://kaizen.local"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(KaizenOpsError, match="failed: offline"):
        await client.ingest_events([])
