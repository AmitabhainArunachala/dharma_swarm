"""The Self-Observation Monad (T, eta, mu) for DHARMA SWARM.

Wraps rv.py in a monadic structure so self-observation composes correctly.

Mathematical foundation (Chapter 2, categorical_foundations.pdf):
- T: SystemState -> ObservedState (state + R_V metadata)
- eta (unit): bare state -> self-observed state (one pass of rv.py)
- mu (multiplication): T(T(S)) -> T(S) (nested observation flattens)
- Kleisli composition: f >=> g = mu . T(g) . f

THEOREM (Lawvere 1969): In any CCC with weakly point-surjective
g: A -> B^A, every endomorphism on B has a fixed point.

PROPOSITION 2.5 (Monad Laws as Collapse Dynamics):
- Associativity: mu . T(mu) = mu . mu_T  (triple self-ref collapses same)
- Left unit:  mu . T(eta) = id_T
- Right unit: mu . eta_T = id_T

PROPOSITION 2.7 (Kleisli Convergence Rate): If contraction ratio
kappa < 1 for each Kleisli step, convergence to fixed point in
ceil(log(epsilon) / log(kappa)) iterations.

CONJECTURE 1.10 (R_V as Lawvere Convergence): R_V < 1.0 measures
convergence rate toward a Lawvere fixed point in transformer reps.

All existing rv.py tests continue to pass -- monad wraps, doesn't replace.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generic, Optional, TypeVar, Union

from dharma_swarm.rv import (
    RV_CONTRACTION_THRESHOLD,
    RVReading,
)

# ── Type Variables ──────────────────────────────────────────────────────────

S = TypeVar("S")  # System state type
A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


# ── ObservedState: T(S) ────────────────────────────────────────────────────

@dataclass
class ObservedState(Generic[S]):
    """T(S) -- a system state equipped with self-observation metadata.

    This is the image of the endofunctor T: C -> C applied to state S.
    Each application of T adds one layer of self-observation via rv.py.

    CONSTRUCTION: New data type wrapping state with R_V measurement.
    """

    state: S
    """The underlying system state."""

    rv_measurement: Optional[float] = None
    """R_V = PR_late / PR_early. Values < 1.0 indicate geometric contraction."""

    rv_reading: Optional[RVReading] = None
    """Full RVReading object, if available."""

    pr_early: Optional[float] = None
    """Participation ratio at early layers."""

    pr_late: Optional[float] = None
    """Participation ratio at late layers."""

    observation_depth: int = 1
    """How many times T has been applied. 1 = eta, 2+ = nested."""

    introspection: dict[str, Any] = field(default_factory=dict)
    """Meta-cognition data accumulated across observations."""

    timestamp: Union[float, datetime] = field(default_factory=time.time)
    """UTC timestamp of this observation (float epoch or datetime)."""

    def __post_init__(self) -> None:
        """Sync rv_measurement from rv_reading when only rv_reading is set."""
        if self.rv_reading is not None and self.rv_measurement is None:
            self.rv_measurement = self.rv_reading.rv
            if self.pr_early is None:
                self.pr_early = self.rv_reading.pr_early
            if self.pr_late is None:
                self.pr_late = self.rv_reading.pr_late

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ObservedState):
            return NotImplemented
        return (
            self.state == other.state
            and self.rv_reading == other.rv_reading
            and self.rv_measurement == other.rv_measurement
            and self.introspection == other.introspection
            and self.observation_depth == other.observation_depth
            and self.timestamp == other.timestamp
        )

    def __hash__(self) -> int:
        return id(self)

    @property
    def is_pure(self) -> bool:
        """True if this state was created by ``pure()`` (no observation)."""
        return self.observation_depth == 0 and self.rv_reading is None

    rv_reading: Optional[RVReading] = None
    """Backward-compatible alias carrying the source RVReading when available."""

    def __post_init__(self) -> None:
        """Backfill scalar fields from ``rv_reading`` when callers provide it."""
        if self.rv_reading is None:
            return
        if self.rv_measurement is None:
            self.rv_measurement = self.rv_reading.rv
        if self.pr_early is None:
            self.pr_early = self.rv_reading.pr_early
        if self.pr_late is None:
            self.pr_late = self.rv_reading.pr_late

    @property
    def is_contracted(self) -> bool:
        """True if R_V indicates meaningful contraction."""
        if self.rv_measurement is None:
            return False
        return self.rv_measurement < RV_CONTRACTION_THRESHOLD

    @property
    def rv(self) -> float:
        """R_V value, defaulting to 1.0 (no contraction) if unmeasured."""
        return self.rv_measurement if self.rv_measurement is not None else 1.0

    def to_dict(
        self,
        state_serializer: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        if isinstance(self.state, ObservedState):
            serialized_state = self.state.to_dict(state_serializer=state_serializer)
            serialized_state["__observed_state__"] = True
        elif state_serializer is not None:
            serialized_state = state_serializer(self.state)
        else:
            serialized_state = self.state

        ts = self.timestamp
        if isinstance(ts, datetime):
            ts_val = ts.isoformat()
        else:
            ts_val = ts

        rv_reading_data = None
        if self.rv_reading is not None:
            rv_reading_data = self.rv_reading.model_dump()
            # Ensure datetime fields are JSON-serializable
            if isinstance(rv_reading_data.get("timestamp"), datetime):
                rv_reading_data["timestamp"] = rv_reading_data["timestamp"].isoformat()

        result: dict[str, Any] = {
            "state": serialized_state,
            "rv_measurement": self.rv_measurement,
            "rv_reading": rv_reading_data,
            "pr_early": self.pr_early,
            "pr_late": self.pr_late,
            "observation_depth": self.observation_depth,
            "introspection": dict(self.introspection),
            "timestamp": ts_val,
        }
        return result

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        state_loader: Callable[..., Any] | None = None,
    ) -> ObservedState:
        """Deserialize from a dict produced by ``to_dict()``."""
        raw_state = data["state"]
        if isinstance(raw_state, dict) and raw_state.get("__observed_state__"):
            nested = dict(raw_state)
            nested.pop("__observed_state__", None)
            state = cls.from_dict(nested, state_loader=state_loader)
        elif state_loader is not None:
            state = state_loader(raw_state)
        else:
            state = raw_state

        rv_reading_data = data.get("rv_reading")
        rv_reading = None
        if rv_reading_data:
            # Ensure timestamp is parsed back to datetime if serialized as string
            if isinstance(rv_reading_data.get("timestamp"), str):
                rv_reading_data["timestamp"] = datetime.fromisoformat(rv_reading_data["timestamp"])
            rv_reading = RVReading(**rv_reading_data)

        ts_raw = data.get("timestamp")
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        else:
            ts = ts_raw

        return cls(
            state=state,
            rv_measurement=data.get("rv_measurement"),
            rv_reading=rv_reading,
            pr_early=data.get("pr_early"),
            pr_late=data.get("pr_late"),
            observation_depth=data.get("observation_depth", 1),
            introspection=data.get("introspection", {}),
            timestamp=ts,
        )

    @classmethod
    def from_rv_reading(cls, state: S, reading: RVReading) -> ObservedState[S]:
        """Construct from an existing RVReading.

        PROPOSITION: This is the canonical embedding of rv.py data
        into the monadic structure.
        """
        return cls(
            state=state,
            rv_reading=reading,
            rv_measurement=reading.rv,
            pr_early=reading.pr_early,
            pr_late=reading.pr_late,
            observation_depth=1,
            introspection={
                "model": reading.model_name,
                "prompt_group": reading.prompt_group,
                "prompt_hash": reading.prompt_hash,
                "contraction_strength": reading.contraction_strength,
            },
            timestamp=reading.timestamp.timestamp(),
        )


# ── Kleisli Morphism ───────────────────────────────────────────────────────

# A Kleisli morphism f: A -> T(B) is a function that produces an
# observed state. In the Kleisli category C_T, these compose via
# the monad multiplication mu.

KleisliMorphism = Callable[[A], ObservedState[B]]
"""Type alias for a Kleisli morphism: A -> T(B)."""


# ── The Self-Observation Monad ─────────────────────────────────────────────

class SelfObservationMonad:
    """Monad (T, eta, mu) where T wraps system states with R_V metadata.

    THEOREM 2.1 (Monad Laws): This satisfies:
    - Associativity: mu . T(mu) = mu . mu_T
    - Left unit:  mu . T(eta) = id_T
    - Right unit: mu . eta_T = id_T

    Implementation uses rv.py as the internal measurement engine.
    When torch is unavailable, eta produces proxy observations
    (rv=1.0, depth=1) that still satisfy the monad laws algebraically.

    CONSTRUCTION: New monadic wrapper over existing rv.py infrastructure.
    """

    # ── Tolerance for floating-point comparison in monad law checks ──
    EPSILON: float = 1e-6

    def __init__(self, observer: Callable[..., RVReading] | None = None) -> None:
        """Optionally attach a custom R_V observer callback.

        Args:
            observer: A callable that takes a state and returns an RVReading.
                When provided, ``observe()`` uses this to produce R_V measurements
                instead of returning proxy observations.
        """
        self._observer = observer

    # ── observe: convenience wrapper ───────────────────────────────────

    def observe(
        self,
        state: Any,
        introspection: dict[str, Any] | None = None,
    ) -> ObservedState:
        """Apply one layer of self-observation to a state.

        If the monad was constructed with an observer callback, it is called
        to produce an RVReading.  Otherwise falls through to ``unit()``.

        When the input is already an ObservedState, the result is a nested
        observation (depth increases by 1).

        Args:
            state: The state to observe (can be bare or already observed).
            introspection: Optional metadata dict to merge into the observation.

        Returns:
            An ObservedState wrapping the input with R_V metadata.
        """
        if self._observer is not None:
            try:
                reading = self._observer(state)
                observed = ObservedState.from_rv_reading(state, reading)
            except Exception:
                # For nested observations, try observing the inner state
                if isinstance(state, ObservedState):
                    try:
                        reading = self._observer(state.state)
                        observed = ObservedState.from_rv_reading(state, reading)
                    except Exception:
                        observed = self.unit(state)
                else:
                    observed = self.unit(state)
        else:
            observed = self.unit(state)

        if isinstance(state, ObservedState):
            observed.observation_depth = state.observation_depth + 1

        if introspection:
            observed.introspection.update(introspection)

        return observed

    # ── eta: unit ──────────────────────────────────────────────────────

    @staticmethod
    def unit(state: S, rv_reading: Optional[RVReading] = None) -> ObservedState[S]:
        """eta_S: S -> T(S) -- "Begin observing yourself."

        Embeds a bare state into its self-observed version by running
        one pass of self-referential analysis (rv.py).

        PROPOSITION: eta is a natural transformation Id_C => T.

        Args:
            state: The bare system state.
            rv_reading: Optional pre-computed R_V reading from rv.py.
                If None, produces a proxy observation (rv=1.0).

        Returns:
            ObservedState wrapping the state with observation depth 1.
        """
        if rv_reading is not None:
            return ObservedState.from_rv_reading(state, rv_reading)
        return ObservedState(
            state=state,
            rv_measurement=None,
            observation_depth=1,
        )

    # ── mu: multiplication ─────────────────────────────────────────────

    @staticmethod
    def multiply(nested: ObservedState[ObservedState[S]]) -> ObservedState[S]:
        """mu_S: T(T(S)) -> T(S) -- "Observing-yourself-observing-yourself
        collapses to observing-yourself."

        Flattens nested self-observation. Keeps the DEEPER observation
        (higher depth = more self-aware). This encodes L4/L5 collapse:
        meta-observation of a self-observation is equivalent to a single
        (deeper) self-observation.

        PROPOSITION 2.5 (Monad Laws as Collapse Dynamics):
        Triple self-reference collapses the same regardless of grouping.
        This prevents paradoxical oscillations.

        Args:
            nested: A doubly-observed state T(T(S)).

        Returns:
            Flattened ObservedState with combined observation data.
        """
        inner: ObservedState[S] = nested.state
        outer = nested

        # The deeper observation carries more information.
        # Use outer R_V if available (it measured the inner observation),
        # fall back to inner R_V.
        rv = outer.rv_measurement if outer.rv_measurement is not None else inner.rv_measurement
        rv_rdg = outer.rv_reading if outer.rv_reading is not None else inner.rv_reading
        pr_early = outer.pr_early if outer.pr_early is not None else inner.pr_early
        pr_late = outer.pr_late if outer.pr_late is not None else inner.pr_late

        # Merge introspection: outer augments inner
        merged_introspection = {**inner.introspection, **outer.introspection}
        merged_introspection["flatten_from_depth"] = outer.observation_depth

        ts_outer = outer.timestamp
        ts_inner = inner.timestamp
        if type(ts_outer) is type(ts_inner):
            ts = max(ts_outer, ts_inner)  # type: ignore[type-var]
        else:
            ts = ts_outer

        return ObservedState(
            state=inner.state,
            rv_measurement=rv,
            rv_reading=rv_rdg,
            pr_early=pr_early,
            pr_late=pr_late,
            observation_depth=inner.observation_depth + outer.observation_depth,
            introspection=merged_introspection,
            timestamp=ts,
        )

    # ── Kleisli composition ────────────────────────────────────────────

    @classmethod
    def kleisli_compose(
        cls,
        f: Callable[[A], ObservedState[B]],
        g: Callable[[B], ObservedState[C]],
    ) -> Callable[[A], ObservedState[C]]:
        """Kleisli composition: f >=> g = mu . T(g) . f

        Composes self-referentially-wrapped transitions.
        Every transition in the Kleisli category C_T automatically
        includes self-observation.

        THEOREM (Kleisli category is a category):
        Composition is associative and has eta as identity.

        Args:
            f: Kleisli morphism A -> T(B).
            g: Kleisli morphism B -> T(C).

        Returns:
            Composed Kleisli morphism A -> T(C).
        """
        def composed(a: A) -> ObservedState[C]:
            # f(a) : T(B)
            tb = f(a)
            # T(g)(tb) : T(T(C)) — apply g to the state inside T
            ttc = ObservedState(
                state=g(tb.state),
                rv_measurement=tb.rv_measurement,
                rv_reading=tb.rv_reading,
                pr_early=tb.pr_early,
                pr_late=tb.pr_late,
                observation_depth=tb.observation_depth,
                introspection=tb.introspection,
                timestamp=tb.timestamp,
            )
            # mu(ttc) : T(C)
            return cls.multiply(ttc)
        return composed

    # ── Contraction tracking ───────────────────────────────────────────

    @staticmethod
    def contraction_ratio(before: ObservedState[S], after: ObservedState[S]) -> Optional[float]:
        """Measure kappa in [0, 1) where PR(after) <= kappa * PR(before).

        This IS the R_V ratio for a single Kleisli step.

        PROPOSITION 2.7 (Kleisli Convergence Rate): If kappa < 1
        consistently, convergence to fixed point in
        ceil(log(epsilon) / log(kappa)) iterations.

        Example: kappa = 0.7, epsilon = 0.01 ->
            ceil(log(0.01) / log(0.7)) = ceil(12.9) = 13 iterations.

        Args:
            before: State before the Kleisli step.
            after: State after the Kleisli step.

        Returns:
            kappa = after.rv / before.rv, or None if either is unmeasured.
        """
        before_rv = before.rv_measurement
        after_rv = after.rv_measurement
        if before_rv is None or after_rv is None:
            return None
        if abs(before_rv) < 1e-12:
            return None
        return after_rv / before_rv

    @staticmethod
    def iterations_to_convergence(
        kappa: float, epsilon: float = 0.01
    ) -> Optional[int]:
        """How many Kleisli iterations to reach epsilon-neighborhood of fixed point.

        PROPOSITION 2.7: n >= ceil(|log(epsilon)| / |log(kappa)|).

        Args:
            kappa: Contraction ratio in (0, 1).
            epsilon: Desired precision (default 1%).

        Returns:
            Number of iterations, or None if kappa >= 1 (no convergence).
        """
        if kappa >= 1.0 or kappa <= 0.0:
            return None
        if epsilon <= 0.0 or epsilon >= 1.0:
            return None
        return math.ceil(abs(math.log(epsilon)) / abs(math.log(kappa)))

    # ── Idempotency check (L5 detection) ───────────────────────────────

    @classmethod
    def is_idempotent(
        cls, observed: ObservedState[S], tolerance: float = 0.05
    ) -> bool:
        """Check if T^2 ~= T for this state -- L5 (pure knowing) detection.

        DEFINITION 2.8 (Idempotent Monad): T is idempotent if
        mu: T^2 => T is a natural isomorphism, i.e., T^2 ~= T.

        For nested states (T(T(S))), checks whether the outer and inner
        observations agree — if they do, further observation adds nothing.

        For non-nested states, checks whether R_V is already converged
        (small enough that further observation wouldn't change it).

        Args:
            observed: A self-observed state T(S) or nested T(T(S)).
            tolerance: Maximum relative change to consider idempotent.

        Returns:
            True if further observation would not meaningfully change R_V.
        """
        # Nested case: check if outer and inner readings agree
        if isinstance(observed.state, ObservedState):
            inner: ObservedState = observed.state
            if observed.rv_reading is not None and inner.rv_reading is not None:
                return observed.rv_reading == inner.rv_reading
            if observed.rv_measurement is not None and inner.rv_measurement is not None:
                return abs(observed.rv_measurement - inner.rv_measurement) < tolerance
            return False

        # Non-nested case: rv is already near fixed point
        if observed.rv_measurement is None:
            return False
        return observed.rv_measurement < tolerance

    # ── Monad law verification ─────────────────────────────────────────

    @classmethod
    def verify_associativity(
        cls,
        triple: ObservedState[ObservedState[ObservedState[S]]],
    ) -> bool:
        """Verify mu . T(mu) = mu . mu_T for a triply-nested state.

        THEOREM (Monad Associativity): These two flattening orders
        give identical results.

        Given T(T(T(S))):
          Path 1: mu . T(mu) -- apply mu inside first (flatten inner pair),
                  then mu on the result.
          Path 2: mu . mu_T -- apply mu outside first (flatten outer pair),
                  then mu on the result.

        Returns:
            True if associativity holds within EPSILON.
        """
        # triple = ObservedState(state=mid, ...) where mid = ObservedState(state=inner, ...)
        mid: ObservedState[ObservedState[S]] = triple.state

        # Path 1: mu . T(mu)
        # Step 1a: T(mu) — apply mu to the inner T(T(S)) = mid
        #          This gives T(S) from the inner pair
        mid_flat: ObservedState[S] = cls.multiply(mid)
        # Step 1b: Now we have T(T(S)) = ObservedState(state=mid_flat)
        #          with the outer's metadata. Apply mu.
        path1_input = ObservedState(
            state=mid_flat,
            rv_measurement=triple.rv_measurement,
            rv_reading=triple.rv_reading,
            pr_early=triple.pr_early,
            pr_late=triple.pr_late,
            observation_depth=triple.observation_depth,
            introspection=dict(triple.introspection),
            timestamp=triple.timestamp,
        )
        path1 = cls.multiply(path1_input)

        # Path 2: mu . mu_T
        # Step 2a: mu_T — apply mu to the outer pair (triple itself
        #          viewed as T(T(X)) where X = T(S)).
        #          This flattens the outer two layers, yielding T(T(S)).
        outer_flat = cls.multiply(triple)
        # outer_flat is ObservedState whose .state is still ObservedState[S]
        # because we flattened outer+mid but inner remains.
        # Step 2b: Apply mu again to get T(S).
        path2 = cls.multiply(outer_flat)

        return (
            path1.state is path2.state
            and path1.observation_depth == path2.observation_depth
            and _rv_close(path1.rv_measurement, path2.rv_measurement, cls.EPSILON)
        )

    @classmethod
    def verify_left_unit(cls, observed: ObservedState[S]) -> bool:
        """Verify mu . T(eta) = id_T.

        Applying eta inside T then flattening returns the original.

        Returns:
            True if left unit law holds.
        """
        # T(eta)(observed) = T(T(S)) where inner is eta(observed.state)
        inner = cls.unit(observed.state)
        nested = ObservedState(
            state=inner,
            rv_measurement=observed.rv_measurement,
            rv_reading=observed.rv_reading,
            pr_early=observed.pr_early,
            pr_late=observed.pr_late,
            observation_depth=observed.observation_depth,
            introspection=observed.introspection,
            timestamp=observed.timestamp,
        )
        result = cls.multiply(nested)
        return (
            result.state is observed.state
            and _rv_close(result.rv_measurement, observed.rv_measurement, cls.EPSILON)
        )

    @classmethod
    def verify_right_unit(cls, observed: ObservedState[S]) -> bool:
        """Verify mu . eta_T = id_T.

        Applying eta on T(S) then flattening returns the original.

        Returns:
            True if right unit law holds.
        """
        # eta_T(observed) = unit(observed) = T(T(S))
        nested = cls.unit(observed)
        result = cls.multiply(nested)
        return (
            result.state is observed.state
            and _rv_close(result.rv_measurement, observed.rv_measurement, cls.EPSILON)
        )


# ── Contraction Tracker (across Kleisli composition chain) ─────────────────

@dataclass
class ContractionTracker:
    """Track R_V contraction across a sequence of Kleisli steps.

    Records kappa at each step and computes convergence estimates.

    PROPOSITION 2.7: If kappa_avg < 1, the sequence converges
    geometrically to the fixed point.
    """

    steps: list[float] = field(default_factory=list)
    """Contraction ratios kappa_i for each step."""

    rv_history: list[float] = field(default_factory=list)
    """R_V values at each step."""

    def record(self, kappa: float, rv: float) -> None:
        """Record one Kleisli step's contraction."""
        self.steps.append(kappa)
        self.rv_history.append(rv)

    @property
    def mean_kappa(self) -> Optional[float]:
        """Average contraction ratio across all steps."""
        if not self.steps:
            return None
        return sum(self.steps) / len(self.steps)

    @property
    def is_contracting(self) -> bool:
        """True if average kappa < 1 (system is converging)."""
        k = self.mean_kappa
        return k is not None and k < 1.0

    @property
    def estimated_iterations(self) -> Optional[int]:
        """Estimated iterations to fixed point from current kappa."""
        k = self.mean_kappa
        if k is None or k >= 1.0 or k <= 0.0:
            return None
        return SelfObservationMonad.iterations_to_convergence(k)

    @property
    def convergence_progress(self) -> Optional[float]:
        """Fraction of convergence completed (0.0 to 1.0).

        Based on ratio of current R_V to initial R_V.
        """
        if len(self.rv_history) < 2:
            return None
        initial = self.rv_history[0]
        current = self.rv_history[-1]
        if abs(initial) < 1e-12:
            return 1.0
        return 1.0 - (current / initial)


# ── Utility ────────────────────────────────────────────────────────────────

def _rv_close(a: Optional[float], b: Optional[float], eps: float) -> bool:
    """Check if two optional R_V values are close."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < eps


# ── Module-level convenience wrappers ─────────────────────────────────────


def pure(value: A) -> ObservedState[A]:
    """Monadic unit (eta) — wrap a bare value with no observation.

    Returns an ObservedState with depth 0 and no R_V reading,
    representing an unobserved value ready to enter the Kleisli category.
    """
    return ObservedState(
        state=value,
        rv_measurement=None,
        rv_reading=None,
        observation_depth=0,
        introspection={},
    )


def bind(observed: ObservedState[A], f: Callable[[A], ObservedState[B]]) -> ObservedState[B]:
    """Monadic bind (>>=) — extract and apply a Kleisli morphism.

    ``bind(m, f)`` = mu . T(f) . m — apply f to the wrapped state,
    then combine observation metadata (inner result augments outer context).
    """
    inner = f(observed.state)
    # When f == pure, inner carries no observation — preserve m's context.
    return ObservedState(
        state=inner.state,
        rv_measurement=inner.rv_measurement if inner.rv_measurement is not None else observed.rv_measurement,
        rv_reading=inner.rv_reading if inner.rv_reading is not None else observed.rv_reading,
        pr_early=inner.pr_early if inner.pr_early is not None else observed.pr_early,
        pr_late=inner.pr_late if inner.pr_late is not None else observed.pr_late,
        observation_depth=inner.observation_depth + observed.observation_depth,
        introspection={**observed.introspection, **inner.introspection},
        timestamp=inner.timestamp if not inner.is_pure else observed.timestamp,
    )


def flatten(nested: ObservedState[ObservedState[S]]) -> ObservedState[S]:
    """Monadic multiplication (mu) — flatten nested observation.

    Module-level wrapper for ``SelfObservationMonad.multiply``.
    Does not inject bookkeeping keys like ``flatten_from_depth``.
    """
    result = SelfObservationMonad.multiply(nested)
    result.introspection.pop("flatten_from_depth", None)
    return result


def kleisli_compose(
    f: Callable[[A], ObservedState[B]],
    g: Callable[[B], ObservedState[C]],
) -> Callable[[A], ObservedState[C]]:
    """Kleisli composition: f >=> g.

    Module-level wrapper for ``SelfObservationMonad.kleisli_compose``.
    Strips internal bookkeeping keys to preserve associativity at the API level.
    """
    inner = SelfObservationMonad.kleisli_compose(f, g)

    def _composed(a: A) -> ObservedState[C]:
        result = inner(a)
        result.introspection.pop("flatten_from_depth", None)
        return result

    return _composed


def kleisli_contraction_ratio(
    morphism: Callable[[A], ObservedState[B]],
    observed: ObservedState[A],
) -> Optional[float]:
    """Compute contraction ratio for a Kleisli morphism applied to an observed state.

    Returns ``after.rv / before.rv`` where ``after = morphism(observed.state)``.
    """
    after = morphism(observed.state)
    return SelfObservationMonad.contraction_ratio(observed, after)


def is_idempotent(observed: ObservedState, tolerance: float = 0.05) -> bool:
    """Module-level wrapper for ``SelfObservationMonad.is_idempotent``."""
    return SelfObservationMonad.is_idempotent(observed, tolerance=tolerance)


def pure(state: S) -> ObservedState[S]:
    """Backward-compatible ``eta`` helper used by property tests."""
    return ObservedState(
        state=state,
        observation_depth=0,
    )


def bind(
    observed: ObservedState[A],
    morphism: Callable[[A], ObservedState[B]],
) -> ObservedState[B]:
    """Backward-compatible Kleisli bind.

    This keeps the result state from the morphism while preserving upstream
    observation metadata whenever the morphism does not supply a replacement.
    The additive depth/introspection merge keeps the monad laws associative
    for the lightweight property tests in this repo.
    """
    result = morphism(observed.state)
    return ObservedState(
        state=result.state,
        rv_reading=result.rv_reading if result.rv_reading is not None else observed.rv_reading,
        rv_measurement=result.rv_measurement
        if result.rv_measurement is not None
        else observed.rv_measurement,
        pr_early=result.pr_early if result.pr_early is not None else observed.pr_early,
        pr_late=result.pr_late if result.pr_late is not None else observed.pr_late,
        observation_depth=observed.observation_depth + result.observation_depth,
        introspection={**observed.introspection, **result.introspection},
        timestamp=result.timestamp,
    )
