"""Property-based tests for self-observation monad laws."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import given, strategies as st

from dharma_swarm.monad import ObservedState, bind, pure
from dharma_swarm.rv import RVReading


def _ts(second: int) -> datetime:
    return datetime(2026, 3, 10, 0, 0, second, tzinfo=timezone.utc)


def _reading(rv: float) -> RVReading:
    return RVReading(
        rv=rv,
        pr_early=1.0,
        pr_late=rv,
        model_name="property-test",
        early_layer=1,
        late_layer=2,
        prompt_hash=f"{int(rv * 1000):016d}"[:16],
        prompt_group="monad",
        timestamp=_ts(0),
    )


def observed_state_strategy():
    return st.builds(
        ObservedState,
        state=st.integers(min_value=-100, max_value=100),
        rv_reading=st.one_of(
            st.none(),
            st.floats(
                min_value=0.1,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ).map(_reading),
        ),
        introspection=st.dictionaries(
            st.sampled_from(["a", "b", "c", "d"]),
            st.integers(min_value=-10, max_value=10),
            max_size=4,
        ),
        observation_depth=st.integers(min_value=0, max_value=3),
        timestamp=st.integers(min_value=0, max_value=59).map(_ts),
    )


def morphism_params_strategy():
    return st.fixed_dictionaries(
        {
            "offset": st.integers(min_value=-10, max_value=10),
            "depth": st.integers(min_value=0, max_value=3),
            "rv": st.one_of(
                st.none(),
                st.floats(
                    min_value=0.1,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            ),
            "label": st.sampled_from(["f", "g", "h", ""]),
            "timestamp_second": st.integers(min_value=0, max_value=59),
        }
    )


def _morphism(params):
    offset = params["offset"]
    depth = params["depth"]
    rv = params["rv"]
    label = params["label"]
    timestamp = _ts(params["timestamp_second"])

    def _apply(value: int) -> ObservedState[int]:
        if depth == 0 and rv is None and not label:
            return pure(value + offset)
        return ObservedState(
            state=value + offset,
            rv_reading=None if rv is None else _reading(float(rv)),
            introspection={} if not label else {label: value},
            observation_depth=depth,
            timestamp=timestamp,
        )

    return _apply


def _same_observed(left: ObservedState[int], right: ObservedState[int]) -> bool:
    return (
        left.state == right.state
        and left.rv_reading == right.rv_reading
        and left.introspection == right.introspection
        and left.observation_depth == right.observation_depth
    )


@given(st.integers(min_value=-100, max_value=100), morphism_params_strategy())
def test_left_unit_law(value, params):
    morphism = _morphism(params)

    assert _same_observed(bind(pure(value), morphism), morphism(value))


@given(observed_state_strategy())
def test_right_unit_law(observed):
    assert _same_observed(bind(observed, pure), observed)


@given(
    observed_state_strategy(),
    morphism_params_strategy(),
    morphism_params_strategy(),
)
def test_bind_associativity(observed, first_params, second_params):
    first = _morphism(first_params)
    second = _morphism(second_params)

    left = bind(bind(observed, first), second)
    right = bind(observed, lambda value: bind(first(value), second))

    assert _same_observed(left, right)
