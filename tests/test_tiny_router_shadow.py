from __future__ import annotations

from types import SimpleNamespace

import dharma_swarm.tiny_router_shadow as tiny_router_shadow
from dharma_swarm.tiny_router_shadow import (
    TinyRouterHeadPrediction,
    TinyRouterShadowInput,
    TinyRouterShadowSignal,
    infer_tiny_router_shadow,
    infer_tiny_router_shadow_from_messages,
)


_TINY_ROUTER_SOURCES = {"heuristic-shadow", "hf-tgupj-tiny-router-shadow"}


def test_tiny_router_shadow_detects_correction_and_action_needed() -> None:
    signal = infer_tiny_router_shadow(
        TinyRouterShadowInput(
            current_text="Actually next Monday",
            previous_text="Set a reminder for Friday",
            previous_action="created_reminder",
            previous_outcome="success",
            recency_seconds=45,
        )
    )

    assert signal.relation_to_previous.label == "correction"
    assert signal.actionability.label == "act"
    assert signal.retention.label == "useful"
    assert signal.urgency.label in {"medium", "high"}
    assert signal.source in _TINY_ROUTER_SOURCES


def test_tiny_router_shadow_uses_previous_user_message_when_available() -> None:
    signal = infer_tiny_router_shadow_from_messages(
        [
            {"role": "user", "content": "Set a reminder for Friday"},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "Actually next Monday"},
        ]
    )

    assert signal is not None
    assert signal.relation_to_previous.label == "correction"
    assert signal.actionability.label == "act"


def test_tiny_router_shadow_prefers_checkpoint_backend_when_available(monkeypatch) -> None:
    expected = TinyRouterShadowSignal(
        relation_to_previous=TinyRouterHeadPrediction("follow_up", 0.91),
        actionability=TinyRouterHeadPrediction("review", 0.82),
        retention=TinyRouterHeadPrediction("useful", 0.77),
        urgency=TinyRouterHeadPrediction("medium", 0.69),
        overall_confidence=0.7975,
        source="hf-tgupj-tiny-router-shadow",
    )
    monkeypatch.setattr(
        tiny_router_shadow,
        "_infer_tiny_router_checkpoint",
        lambda payload: expected,
    )

    signal = infer_tiny_router_shadow(
        TinyRouterShadowInput(
            current_text="What about Tuesday instead?",
            previous_text="Set a reminder for Monday",
        )
    )

    assert signal is expected


def test_tiny_router_shadow_falls_back_when_checkpoint_backend_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        tiny_router_shadow,
        "_infer_tiny_router_checkpoint",
        lambda payload: None,
    )

    signal = infer_tiny_router_shadow(
        TinyRouterShadowInput(
            current_text="Actually next Monday",
            previous_text="Set a reminder for Friday",
            previous_action="created_reminder",
        )
    )

    assert signal.relation_to_previous.label == "correction"
    assert signal.source == "heuristic-shadow"


def test_tiny_router_shadow_skips_checkpoint_backend_on_python_314(monkeypatch) -> None:
    monkeypatch.setattr(
        tiny_router_shadow,
        "_requested_backend",
        lambda: "checkpoint",
    )
    monkeypatch.setattr(
        tiny_router_shadow,
        "sys",
        SimpleNamespace(version_info=(3, 14, 0, "final", 0)),
        raising=False,
    )

    def _unexpected_artifact_load(*_args, **_kwargs):
        raise AssertionError("checkpoint artifacts should not load on Python 3.14+")

    monkeypatch.setattr(
        tiny_router_shadow,
        "_load_tiny_router_artifacts",
        _unexpected_artifact_load,
    )

    signal = infer_tiny_router_shadow(
        TinyRouterShadowInput(
            current_text="Actually next Monday",
            previous_text="Set a reminder for Friday",
            previous_action="created_reminder",
        )
    )

    assert signal.source == "heuristic-shadow"
