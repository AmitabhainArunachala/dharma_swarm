"""Honest GraphQL surface contract.

The API currently exposes REST compatibility routes under ``/graphql/*`` but
does not mount a GraphQL POST endpoint. This module intentionally avoids
placeholder resolvers so imports stay truthful and dependency-tolerant.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from typing import Any, Final

GRAPHQL_FEATURE_FLAG: Final = "DHARMA_ENABLE_GRAPHQL_API"
REST_COMPAT_ROUTES: Final[tuple[str, ...]] = (
    "/graphql/agent/{agent_id}",
    "/graphql/stigmergy_marks",
    "/graphql/connection_graph/{root_id}",
    "/graphql/search",
)


def _feature_enabled(env: Mapping[str, str] | None = None) -> bool:
    raw = (env or os.environ).get(GRAPHQL_FEATURE_FLAG, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _strawberry_available() -> bool:
    return importlib.util.find_spec("strawberry") is not None


def graphql_surface_contract(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return the truthful public GraphQL surface contract."""
    feature_enabled = _feature_enabled(env)
    dependency_ready = _strawberry_available()
    mounted = False
    enabled = False

    if not feature_enabled:
        reason = (
            "GraphQL POST surface is disabled by default; use the REST "
            "compatibility routes under /graphql/*."
        )
    elif not dependency_ready:
        reason = "GraphQL POST surface requested but strawberry is not installed."
    else:
        reason = (
            "GraphQL status schema can be mounted explicitly, but no GraphQL "
            "POST endpoint is mounted by default."
        )

    return {
        "enabled": enabled,
        "mounted": mounted,
        "mode": "rest-compat",
        "reason": reason,
        "feature_flag": GRAPHQL_FEATURE_FLAG,
        "feature_enabled": feature_enabled,
        "dependency_ready": dependency_ready,
        "query_fields": ["graphqlSurface"] if dependency_ready else [],
        "rest_routes": list(REST_COMPAT_ROUTES),
    }


if _strawberry_available():
    import strawberry

    @strawberry.type
    class GraphQLSurfaceStatus:
        enabled: bool
        mounted: bool
        mode: str
        reason: str
        feature_flag: str
        feature_enabled: bool
        dependency_ready: bool
        query_fields: list[str]
        rest_routes: list[str]


    @strawberry.type
    class Query:
        @strawberry.field
        def graphql_surface(self) -> GraphQLSurfaceStatus:
            return GraphQLSurfaceStatus(**graphql_surface_contract())


    schema = strawberry.Schema(query=Query)
else:
    schema = None


__all__ = [
    "GRAPHQL_FEATURE_FLAG",
    "REST_COMPAT_ROUTES",
    "graphql_surface_contract",
    "schema",
]
