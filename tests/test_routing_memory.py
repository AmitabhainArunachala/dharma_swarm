from __future__ import annotations

from dharma_swarm.models import ProviderType
from dharma_swarm.routing_memory import (
    RoutingMemoryStore,
    build_task_signature,
    default_routing_memory_db_path,
)


def test_build_task_signature_captures_core_routing_axes() -> None:
    signature = build_task_signature(
        action_name="Apply Patch",
        context={
            "language_code": "ja",
            "complexity_tier": "REASONING",
            "context_tier": "LONG",
            "requires_tooling": True,
        },
    )
    assert signature == "apply-patch|reasoning|ja|long|tooling"


def test_routing_memory_prefers_successful_lane(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    task_signature = "triage|medium|en|short|plain"

    for _ in range(4):
        store.record_outcome(
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            task_signature=task_signature,
            action_name="triage",
            route_path="deliberative",
            success=True,
            latency_ms=900.0,
            total_tokens=3200,
        )
    for _ in range(3):
        store.record_outcome(
            provider=ProviderType.OPENROUTER_FREE,
            model="llama-free",
            task_signature=task_signature,
            action_name="triage",
            route_path="reflex",
            success=False,
            latency_ms=1200.0,
            total_tokens=0,
            error="provider_error",
        )

    ranked, scores = store.rank_candidates(
        task_signature,
        [ProviderType.OPENROUTER_FREE, ProviderType.ANTHROPIC],
        model_hints={
            ProviderType.OPENROUTER_FREE: "llama-free",
            ProviderType.ANTHROPIC: "claude-sonnet-4-6",
        },
    )

    assert ranked[0] == ProviderType.ANTHROPIC
    assert scores[ProviderType.ANTHROPIC].blended_score > scores[
        ProviderType.OPENROUTER_FREE
    ].blended_score


def test_routing_memory_records_global_fallback_profile(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    specific_signature = "coding|reasoning|en|medium-long|tooling"

    store.record_outcome(
        provider=ProviderType.CODEX,
        model="codex",
        task_signature=specific_signature,
        action_name="coding",
        route_path="escalate",
        success=True,
        latency_ms=1500.0,
        total_tokens=8000,
    )

    exact = store.lane_score(
        provider=ProviderType.CODEX,
        model="codex",
        task_signature=specific_signature,
    )
    global_lane = store.lane_score(
        provider=ProviderType.CODEX,
        model="codex",
        task_signature="other-action|medium|en|short|plain",
    )

    assert exact is not None
    assert global_lane is not None
    assert global_lane.global_score is not None
    assert global_lane.sample_count >= 1


def test_routing_memory_uses_similar_patterns_to_break_ties(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    target_signature = "coding-review|reasoning|en|medium-long|tooling"

    store.record_outcome(
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        task_signature="coding|reasoning|en|long|tooling",
        action_name="coding",
        route_path="deliberative",
        success=True,
        latency_ms=900.0,
        total_tokens=4200,
    )
    store.record_outcome(
        provider=ProviderType.OPENROUTER_FREE,
        model="llama-free",
        task_signature="casual-chat|simple|en|short|plain",
        action_name="casual-chat",
        route_path="reflex",
        success=True,
        latency_ms=900.0,
        total_tokens=4200,
    )

    ranked, scores = store.rank_candidates(
        target_signature,
        [ProviderType.OPENROUTER_FREE, ProviderType.ANTHROPIC],
        model_hints={
            ProviderType.OPENROUTER_FREE: "llama-free",
            ProviderType.ANTHROPIC: "claude-sonnet-4-6",
        },
    )

    assert ranked[0] == ProviderType.ANTHROPIC
    assert scores[ProviderType.ANTHROPIC].similar_score is not None
    assert scores[ProviderType.ANTHROPIC].similar_matches >= 1


def test_routing_memory_top_routes_returns_ranked_non_global_entries(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    store.record_outcome(
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        task_signature="coding|reasoning|en|long|tooling",
        action_name="coding",
        route_path="deliberative",
        success=True,
        latency_ms=700.0,
        total_tokens=3000,
    )
    store.record_outcome(
        provider=ProviderType.OPENROUTER_FREE,
        model="llama-free",
        task_signature="triage|medium|en|short|plain",
        action_name="triage",
        route_path="reflex",
        success=False,
        latency_ms=900.0,
        total_tokens=0,
        error="provider_error",
    )

    top = store.top_routes(limit=2)

    assert len(top) == 2
    assert all(lane.task_signature != "*" for lane in top)
    assert top[0].blended_score >= top[1].blended_score


def test_default_routing_memory_db_path_points_under_dharma_home() -> None:
    path = default_routing_memory_db_path()
    assert ".dharma" in str(path)
    assert path.name == "routing_memory.sqlite3"
