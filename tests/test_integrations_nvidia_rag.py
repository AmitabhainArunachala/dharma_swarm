"""Tests for dharma_swarm.integrations.nvidia_rag."""

from __future__ import annotations

import httpx
import pytest

from dharma_swarm.integrations import NvidiaRagClient, NvidiaRagConfig, NvidiaRagError


@pytest.mark.asyncio
async def test_rag_health_calls_expected_endpoint():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/health"
        assert request.url.params["check_dependencies"] == "true"
        return httpx.Response(200, json={"message": "Service is up."})

    client = NvidiaRagClient(
        config=NvidiaRagConfig(
            rag_base_url="http://rag.local/v1",
            ingest_base_url="http://ingest.local/v1",
        ),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.health(service="rag", check_dependencies=True)
    assert out["message"] == "Service is up."


@pytest.mark.asyncio
async def test_rag_search_posts_payload():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/search"
        body = request.content.decode("utf-8")
        assert '"query":"kernel optimization"' in body
        assert '"top_k":3' in body
        assert '"collection_name":"dharma"' in body
        return httpx.Response(200, json={"results": [{"text": "x"}]})

    client = NvidiaRagClient(
        config=NvidiaRagConfig(
            rag_base_url="http://rag.local/v1",
            ingest_base_url="http://ingest.local/v1",
        ),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.search("kernel optimization", top_k=3, collection_name="dharma")
    assert out["results"][0]["text"] == "x"


@pytest.mark.asyncio
async def test_rag_chat_posts_chat_completions():
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/chat/completions"
        body = request.content.decode("utf-8")
        assert '"messages"' in body
        assert '"stream":false' in body
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "grounded answer"}}]},
        )

    client = NvidiaRagClient(
        config=NvidiaRagConfig(
            rag_base_url="http://rag.local/v1",
            ingest_base_url="http://ingest.local/v1",
        ),
        transport=httpx.MockTransport(_handler),
    )
    out = await client.chat("what changed?")
    assert out["choices"][0]["message"]["content"] == "grounded answer"


@pytest.mark.asyncio
async def test_rag_error_raises():
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = NvidiaRagClient(
        config=NvidiaRagConfig(
            rag_base_url="http://rag.local/v1",
            ingest_base_url="http://ingest.local/v1",
        ),
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(NvidiaRagError, match="failed: 500"):
        await client.health()
