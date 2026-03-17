from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

try:
    from dharma_swarm.monad import (
        ObservedState,
        SelfObservationMonad,
        bind,
        flatten,
        is_idempotent,
        kleisli_compose,
        kleisli_contraction_ratio,
        pure,
    )
    from dharma_swarm.rv import RVReading
except ImportError:
    pytest.skip(
        "monad module-level API (pure/bind/flatten) not yet implemented",
        allow_module_level=True,
    )


def _ts(second: int) -> datetime:
    return datetime(2026, 3, 10, 0, 0, second, tzinfo=timezone.utc)


def _reading(rv: float) -> RVReading:
    return RVReading(
        rv=rv,
        pr_early=1.0,
        pr_late=rv,
        model_name="test-model",
        early_layer=1,
        late_layer=2,
        prompt_hash=f"{int(rv * 1000):016d}"[:16],
        prompt_group="test",
        timestamp=_ts(0),
    )


def test_pure_is_neutral() -> None:
    value = pure({"x": 1})

    assert value.state == {"x": 1}
    assert value.rv_reading is None
    assert value.introspection == {}
    assert value.observation_depth == 0
    assert value.is_pure is True


def test_observe_wraps_payload_and_increments_depth() -> None:
    monad: SelfObservationMonad[dict[str, float]] = SelfObservationMonad(
        observer=lambda state: _reading(state["rv"])
    )

    first = monad.observe({"rv": 0.8}, introspection={"stage": "first"})
    second = monad.observe(first, introspection={"stage": "second"})

    assert first.state == {"rv": 0.8}
    assert first.observation_depth == 1
    assert first.rv_reading == _reading(0.8)
    assert second.state == first
    assert second.observation_depth == 2
    assert second.rv_reading == _reading(0.8)


def test_bind_left_unit() -> None:
    def f(value: int) -> ObservedState[int]:
        return ObservedState(
            state=value + 1,
            rv_reading=_reading(0.6),
            introspection={"step": "f"},
            observation_depth=1,
            timestamp=_ts(1),
        )

    assert bind(pure(2), f) == f(2)


def test_bind_right_unit() -> None:
    observed = ObservedState(
        state=5,
        rv_reading=_reading(0.7),
        introspection={"origin": "seed"},
        observation_depth=1,
        timestamp=_ts(2),
    )

    assert bind(observed, pure) == observed


def test_flatten_merges_nested_observation() -> None:
    inner = ObservedState(
        state={"id": 1},
        rv_reading=_reading(0.7),
        introspection={"inner": True},
        observation_depth=1,
        timestamp=_ts(3),
    )
    outer = ObservedState(
        state=inner,
        rv_reading=_reading(0.5),
        introspection={"outer": True},
        observation_depth=1,
        timestamp=_ts(4),
    )

    flat = flatten(outer)

    assert flat.state == {"id": 1}
    assert flat.rv_reading == _reading(0.5)
    assert flat.introspection == {"inner": True, "outer": True}
    assert flat.observation_depth == 2
    assert flat.timestamp == _ts(4)


def test_kleisli_compose_is_associative_for_deterministic_morphisms() -> None:
    def f(value: int) -> ObservedState[int]:
        return ObservedState(
            state=value + 1,
            rv_reading=_reading(0.9),
            introspection={"f": value},
            observation_depth=1,
            timestamp=_ts(5),
        )

    def g(value: int) -> ObservedState[int]:
        return ObservedState(
            state=value * 2,
            rv_reading=_reading(0.6),
            introspection={"g": value},
            observation_depth=1,
            timestamp=_ts(6),
        )

    def h(value: int) -> ObservedState[int]:
        return ObservedState(
            state=value - 3,
            rv_reading=_reading(0.4),
            introspection={"h": value},
            observation_depth=1,
            timestamp=_ts(7),
        )

    left = kleisli_compose(kleisli_compose(f, g), h)
    right = kleisli_compose(f, kleisli_compose(g, h))

    assert left(4) == right(4)


def test_kleisli_contraction_ratio_uses_input_observation() -> None:
    start = ObservedState(
        state=10,
        rv_reading=_reading(0.8),
        introspection={},
        observation_depth=1,
        timestamp=_ts(8),
    )

    def shrink(value: int) -> ObservedState[int]:
        return ObservedState(
            state=value,
            rv_reading=_reading(0.4),
            introspection={"mode": "shrink"},
            observation_depth=1,
            timestamp=_ts(9),
        )

    assert kleisli_contraction_ratio(shrink, start) == 0.5


def test_is_idempotent_for_matching_nested_readings() -> None:
    inner = ObservedState(
        state="payload",
        rv_reading=_reading(0.5),
        introspection={"depth": 1},
        observation_depth=1,
        timestamp=_ts(10),
    )
    outer = ObservedState(
        state=inner,
        rv_reading=_reading(0.5),
        introspection={"depth": 2},
        observation_depth=1,
        timestamp=_ts(11),
    )

    assert is_idempotent(outer) is True


def test_is_idempotent_false_when_nested_readings_diverge() -> None:
    inner = ObservedState(
        state="payload",
        rv_reading=_reading(0.5),
        introspection={},
        observation_depth=1,
        timestamp=_ts(12),
    )
    outer = ObservedState(
        state=inner,
        rv_reading=_reading(0.7),
        introspection={},
        observation_depth=1,
        timestamp=_ts(13),
    )

    assert is_idempotent(outer) is False


def test_observed_state_dict_roundtrip_is_json_safe() -> None:
    observed = ObservedState(
        state={"payload": ["alpha", "beta"]},
        rv_reading=_reading(0.55),
        introspection={"origin": "unit-test"},
        observation_depth=1,
        timestamp=_ts(14),
    )

    payload = observed.to_dict()
    restored = ObservedState.from_dict(json.loads(json.dumps(payload)))

    assert payload["rv_reading"]["rv"] == 0.55
    assert restored == observed


def test_nested_observed_state_roundtrip_preserves_wrapper_structure() -> None:
    inner = ObservedState(
        state={"id": 7},
        rv_reading=_reading(0.45),
        introspection={"inner": True},
        observation_depth=1,
        timestamp=_ts(15),
    )
    outer = ObservedState(
        state=inner,
        rv_reading=_reading(0.4),
        introspection={"outer": True},
        observation_depth=2,
        timestamp=_ts(16),
    )

    payload = outer.to_dict()
    restored = ObservedState.from_dict(payload)

    assert payload["state"]["__observed_state__"] is True
    assert restored == outer
    assert flatten(restored) == flatten(outer)


def test_observed_state_roundtrip_supports_custom_payload_codec() -> None:
    observed = ObservedState(
        state={3, 1, 2},
        rv_reading=_reading(0.72),
        introspection={"codec": "set"},
        observation_depth=1,
        timestamp=_ts(17),
    )

    payload = observed.to_dict(state_serializer=lambda value: sorted(value))
    restored = ObservedState.from_dict(payload, state_loader=set)

    assert payload["state"] == [1, 2, 3]
    assert restored == observed
