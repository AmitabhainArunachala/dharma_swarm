from __future__ import annotations

import importlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import graphql_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(graphql_router.router)
    return TestClient(app)


def _reload_graphql_schema_module():
    sys.modules.pop("api.graphql.schema", None)
    module = importlib.import_module("api.graphql.schema")
    return importlib.reload(module)


def test_graphql_surface_contract_is_honest_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DHARMA_ENABLE_GRAPHQL_API", raising=False)

    graphql_schema = _reload_graphql_schema_module()
    contract = graphql_schema.graphql_surface_contract()

    assert contract["enabled"] is False
    assert contract["mounted"] is False
    assert contract["mode"] == "rest-compat"
    assert contract["feature_flag"] == "DHARMA_ENABLE_GRAPHQL_API"
    assert contract["feature_enabled"] is False
    assert "/graphql/agent/{agent_id}" in contract["rest_routes"]
    assert "/graphql/connection_graph/{root_id}" in contract["rest_routes"]

    if graphql_schema.schema is None:
        assert contract["dependency_ready"] is False
    else:
        sdl = graphql_schema.schema.as_str()
        assert "graphqlSurface" in sdl
        assert "agentIdentity" not in sdl
        assert "stigmergyMarks" not in sdl
        assert "connectionGraph" not in sdl


def test_graphql_router_root_reports_surface_contract(monkeypatch) -> None:
    monkeypatch.delenv("DHARMA_ENABLE_GRAPHQL_API", raising=False)
    client = _client()

    response = client.get("/graphql")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["mounted"] is False
    assert payload["mode"] == "rest-compat"
    assert "disabled by default" in payload["reason"]
    assert "/graphql/search" in payload["rest_routes"]
