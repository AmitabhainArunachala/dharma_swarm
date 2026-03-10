"""Tests for dharma_swarm.integrations.reciprocity_commons."""

from __future__ import annotations

import httpx
import pytest

from dharma_swarm.integrations import (
    ReciprocityCommonsClient,
    ReciprocityCommonsConfig,
    ReciprocityCommonsError,
)


@pytest.mark.asyncio
async def test_health_calls_expected_endpoint():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/health"
        return httpx.Response(200, json={"status": "ok"})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.health()
    assert out["status"] == "ok"


@pytest.mark.asyncio
async def test_publish_activity_posts_expected_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/activities"
        body = request.content.decode("utf-8")
        assert '"activity_id":"a1"' in body
        assert '"energy_mwh":12.5' in body
        return httpx.Response(200, json={"accepted": True})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.publish_activity(
        {"activity_id": "a1", "energy_mwh": 12.5, "emissions_tco2e": 4.2}
    )
    assert out["accepted"] is True


@pytest.mark.asyncio
async def test_publish_outcome_posts_expected_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/outcomes"
        body = request.content.decode("utf-8")
        assert '"outcome_type":"carbon"' in body
        assert '"quantity":18.0' in body
        return httpx.Response(200, json={"id": "out-1"})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.publish_outcome(
        {"outcome_type": "carbon", "quantity": 18.0, "unit": "tco2e"}
    )
    assert out["id"] == "out-1"


@pytest.mark.asyncio
async def test_publish_obligation_posts_expected_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/obligations"
        body = request.content.decode("utf-8")
        assert '"obligation_id":"obl-1"' in body
        assert '"amount_usd":2400.0' in body
        return httpx.Response(200, json={"accepted": True, "id": "obl-1"})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.publish_obligation(
        {"obligation_id": "obl-1", "amount_usd": 2400.0, "status": "active"}
    )
    assert out["id"] == "obl-1"


@pytest.mark.asyncio
async def test_publish_project_posts_expected_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/projects"
        body = request.content.decode("utf-8")
        assert '"project_id":"proj-1"' in body
        assert '"title":"Louisiana Wetlands"' in body
        return httpx.Response(200, json={"accepted": True, "id": "proj-1"})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.publish_project(
        {"project_id": "proj-1", "title": "Louisiana Wetlands", "status": "active"}
    )
    assert out["id"] == "proj-1"


@pytest.mark.asyncio
async def test_ledger_summary_calls_expected_endpoint():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/ledger/summary"
        return httpx.Response(200, json={"actors": 2, "obligations": 4})

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.ledger_summary()
    assert out["obligations"] == 4


@pytest.mark.asyncio
async def test_http_error_raises_reciprocity_commons_error():
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(ReciprocityCommonsError, match="failed: 502"):
        await client.ledger_summary()


@pytest.mark.asyncio
async def test_invalid_json_raises_reciprocity_commons_error():
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(ReciprocityCommonsError, match="returned invalid JSON"):
        await client.ledger_summary()


@pytest.mark.asyncio
async def test_transport_error_raises_reciprocity_commons_error():
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = ReciprocityCommonsClient(
        config=ReciprocityCommonsConfig(base_url="http://commons.local/v1"),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(ReciprocityCommonsError, match="failed: offline"):
        await client.ledger_summary()
