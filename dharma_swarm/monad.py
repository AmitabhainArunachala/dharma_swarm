"""Self-observation monad over existing RV measurement semantics.

The repo does not currently expose a single canonical system-state type, so
this module keeps the observation boundary generic and typed. ``rv.py``
remains the source of truth for mechanistic measurement via ``RVReading``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generic, Mapping, TypeVar

from dharma_swarm.models import _utc_now
from dharma_swarm.rv import RVReading

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")

Observer = Callable[[T], RVReading | None]
KleisliMorphism = Callable[[T], "ObservedState[U]"]


@dataclass(slots=True)
class ObservedState(Generic[T]):
    """A payload wrapped with self-observation metadata."""

    state: T
    rv_reading: RVReading | None = None
    introspection: dict[str, Any] = field(default_factory=dict)
    observation_depth: int = 0
    timestamp: datetime = field(default_factory=_utc_now)

    @property
    def is_pure(self) -> bool:
        """True when the wrapper carries no observational effects."""
        return (
            self.rv_reading is None
            and not self.introspection
            and self.observation_depth == 0
        )


def pure(state: T) -> ObservedState[T]:
    """Embed a bare value in the monad without adding observation metadata."""
    return ObservedState(state=state)


def _merge_introspection(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(left)
    merged.update(right)
    return merged


def bind(
    observed: ObservedState[T],
    func: KleisliMorphism[T, U],
) -> ObservedState[U]:
    """Monadic bind over an observed payload."""
    next_observed = func(observed.state)

    if observed.is_pure:
        return next_observed
    if next_observed.is_pure:
        return ObservedState(
            state=next_observed.state,
            rv_reading=observed.rv_reading,
            introspection=dict(observed.introspection),
            observation_depth=observed.observation_depth,
            timestamp=observed.timestamp,
        )

    rv_reading = next_observed.rv_reading or observed.rv_reading
    return ObservedState(
        state=next_observed.state,
        rv_reading=rv_reading,
        introspection=_merge_introspection(
            observed.introspection,
            next_observed.introspection,
        ),
        observation_depth=observed.observation_depth + next_observed.observation_depth,
        timestamp=next_observed.timestamp,
    )


def flatten(observed: ObservedState[ObservedState[T]]) -> ObservedState[T]:
    """Collapse one level of nested observation."""
    inner = observed.state
    rv_reading = observed.rv_reading or inner.rv_reading
    timestamp = observed.timestamp if observed.rv_reading is not None else inner.timestamp
    return ObservedState(
        state=inner.state,
        rv_reading=rv_reading,
        introspection=_merge_introspection(inner.introspection, observed.introspection),
        observation_depth=observed.observation_depth + inner.observation_depth,
        timestamp=timestamp,
    )


def kleisli_compose(
    first: KleisliMorphism[T, U],
    second: KleisliMorphism[U, V],
) -> KleisliMorphism[T, V]:
    """Compose Kleisli morphisms with metadata-preserving bind."""

    def _composed(value: T) -> ObservedState[V]:
        return bind(first(value), second)

    return _composed


def kleisli_contraction_ratio(
    morphism: KleisliMorphism[T, U],
    value: T | ObservedState[T],
) -> float | None:
    """Return output RV divided by input RV when both are available."""
    if isinstance(value, ObservedState):
        before = value
        raw_value = value.state
    else:
        before = None
        raw_value = value

    after = morphism(raw_value)
    before_rv = before.rv_reading.rv if before and before.rv_reading else None
    after_rv = after.rv_reading.rv if after.rv_reading else None
    if before_rv is None or after_rv is None or abs(before_rv) < 1e-12:
        return None
    return after_rv / before_rv


def is_idempotent(observed: ObservedState[Any], tolerance: float = 1e-9) -> bool:
    """Check whether a nested observation is effectively stable under flattening."""
    if not isinstance(observed.state, ObservedState):
        return observed.observation_depth <= 1

    inner = observed.state
    outer_rv = observed.rv_reading.rv if observed.rv_reading else None
    inner_rv = inner.rv_reading.rv if inner.rv_reading else None
    if outer_rv is None or inner_rv is None:
        return False

    flattened = flatten(observed)
    return (
        flattened.state == inner.state
        and abs(outer_rv - inner_rv) <= tolerance
    )


class SelfObservationMonad(Generic[T]):
    """Monadic wrapper around an injected observer function."""

    def __init__(self, observer: Observer[T]) -> None:
        self._observer = observer

    def pure(self, state: T) -> ObservedState[T]:
        return pure(state)

    def observe(
        self,
        state: T | ObservedState[T],
        introspection: Mapping[str, Any] | None = None,
    ) -> ObservedState[T] | ObservedState[ObservedState[T]]:
        """Apply one layer of self-observation.

        If the input is already observed, the observer is run against the
        underlying payload while the wrapper itself becomes one level deeper.
        """
        subject = state.state if isinstance(state, ObservedState) else state
        reading = self._observer(subject)
        depth = state.observation_depth + 1 if isinstance(state, ObservedState) else 1
        return ObservedState(
            state=state,
            rv_reading=reading,
            introspection=dict(introspection or {}),
            observation_depth=depth,
        )

    def bind(
        self,
        observed: ObservedState[T],
        func: KleisliMorphism[T, U],
    ) -> ObservedState[U]:
        return bind(observed, func)

    def flatten(self, observed: ObservedState[ObservedState[T]]) -> ObservedState[T]:
        return flatten(observed)


__all__ = [
    "KleisliMorphism",
    "ObservedState",
    "Observer",
    "SelfObservationMonad",
    "bind",
    "flatten",
    "is_idempotent",
    "kleisli_compose",
    "kleisli_contraction_ratio",
    "pure",
]
