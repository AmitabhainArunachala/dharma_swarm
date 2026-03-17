"""Tests for dharma_swarm.monad — Self-Observation Monad (T, eta, mu).

Verifies monad laws (associativity, left unit, right unit),
Kleisli composition, contraction tracking, and L5 idempotency detection.

All tests run without torch. R_V values are supplied directly.
"""

import math
import time
from typing import Any

import pytest

from dharma_swarm.monad import (
    ContractionTracker,
    ObservedState,
    SelfObservationMonad,
    _rv_close,
)
from dharma_swarm.rv import RVReading, RV_CONTRACTION_THRESHOLD

T = SelfObservationMonad


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_observed(
    state: Any = "base_state",
    rv: float | None = 0.65,
    pr_early: float | None = 8.3,
    pr_late: float | None = 5.4,
    depth: int = 1,
) -> ObservedState:
    return ObservedState(
        state=state,
        rv_measurement=rv,
        pr_early=pr_early,
        pr_late=pr_late,
        observation_depth=depth,
    )


def _make_reading(rv: float = 0.65, group: str = "L4") -> RVReading:
    return RVReading(
        rv=rv,
        pr_early=8.3,
        pr_late=5.4,
        model_name="test-model",
        early_layer=2,
        late_layer=22,
        prompt_hash="abcdef0123456789",
        prompt_group=group,
    )


# ── ObservedState Tests ────────────────────────────────────────────────────


class TestObservedState:
    """Tests for ObservedState[S] data class."""

    def test_creation(self):
        obs = _make_observed()
        assert obs.state == "base_state"
        assert obs.rv_measurement == 0.65
        assert obs.observation_depth == 1

    def test_is_contracted_true(self):
        obs = _make_observed(rv=0.5)
        assert obs.is_contracted is True

    def test_is_contracted_false(self):
        obs = _make_observed(rv=0.9)
        assert obs.is_contracted is False

    def test_is_contracted_none_rv(self):
        obs = _make_observed(rv=None)
        assert obs.is_contracted is False

    def test_rv_property_default(self):
        obs = _make_observed(rv=None)
        assert obs.rv == 1.0

    def test_rv_property_with_value(self):
        obs = _make_observed(rv=0.7)
        assert obs.rv == 0.7

    def test_from_rv_reading(self):
        reading = _make_reading(rv=0.42)
        obs = ObservedState.from_rv_reading("my_state", reading)
        assert obs.state == "my_state"
        assert obs.rv_measurement == 0.42
        assert obs.observation_depth == 1
        assert obs.introspection["model"] == "test-model"
        assert obs.introspection["prompt_group"] == "L4"
        assert obs.introspection["contraction_strength"] == "strong"

    def test_generic_state_types(self):
        """ObservedState works with any state type."""
        obs_int = ObservedState(state=42, observation_depth=1)
        assert obs_int.state == 42

        obs_dict = ObservedState(state={"key": "val"}, observation_depth=1)
        assert obs_dict.state["key"] == "val"

        obs_list = ObservedState(state=[1, 2, 3], observation_depth=1)
        assert len(obs_list.state) == 3


# ── Unit (eta) Tests ───────────────────────────────────────────────────────


class TestUnit:
    """Tests for eta: S -> T(S)."""

    def test_unit_without_reading(self):
        obs = T.unit("hello")
        assert obs.state == "hello"
        assert obs.rv_measurement is None
        assert obs.observation_depth == 1

    def test_unit_with_reading(self):
        reading = _make_reading(rv=0.55)
        obs = T.unit("hello", rv_reading=reading)
        assert obs.state == "hello"
        assert obs.rv_measurement == 0.55
        assert obs.observation_depth == 1

    def test_unit_preserves_state_identity(self):
        state = {"complex": [1, 2, 3]}
        obs = T.unit(state)
        assert obs.state is state  # same object, not copy


# ── Multiplication (mu) Tests ──────────────────────────────────────────────


class TestMultiplication:
    """Tests for mu: T(T(S)) -> T(S)."""

    def test_flatten_basic(self):
        inner = _make_observed(state="core", rv=0.6, depth=1)
        outer = ObservedState(
            state=inner, rv_measurement=0.5, pr_early=7.0, pr_late=3.5,
            observation_depth=1,
        )
        result = T.multiply(outer)
        assert result.state == "core"
        assert result.rv_measurement == 0.5  # outer R_V preferred
        assert result.observation_depth == 2  # 1 + 1

    def test_flatten_preserves_inner_state(self):
        state = [1, 2, 3]
        inner = _make_observed(state=state, rv=0.7, depth=1)
        outer = ObservedState(state=inner, observation_depth=1)
        result = T.multiply(outer)
        assert result.state is state

    def test_flatten_uses_outer_rv_when_available(self):
        inner = _make_observed(rv=0.8, depth=1)
        outer = ObservedState(state=inner, rv_measurement=0.6, observation_depth=1)
        result = T.multiply(outer)
        assert result.rv_measurement == 0.6

    def test_flatten_falls_back_to_inner_rv(self):
        inner = _make_observed(rv=0.8, depth=1)
        outer = ObservedState(state=inner, rv_measurement=None, observation_depth=1)
        result = T.multiply(outer)
        assert result.rv_measurement == 0.8

    def test_flatten_depth_accumulates(self):
        inner = _make_observed(depth=3)
        outer = ObservedState(state=inner, observation_depth=2)
        result = T.multiply(outer)
        assert result.observation_depth == 5  # 3 + 2

    def test_flatten_merges_introspection(self):
        inner = _make_observed()
        inner.introspection = {"source": "inner", "shared": "from_inner"}
        outer = ObservedState(state=inner, observation_depth=1)
        outer.introspection = {"layer": "outer", "shared": "from_outer"}
        result = T.multiply(outer)
        assert result.introspection["source"] == "inner"
        assert result.introspection["layer"] == "outer"
        assert result.introspection["shared"] == "from_outer"  # outer wins
        assert result.introspection["flatten_from_depth"] == 1

    def test_flatten_takes_max_timestamp(self):
        inner = _make_observed()
        inner.timestamp = 100.0
        outer = ObservedState(state=inner, observation_depth=1)
        outer.timestamp = 200.0
        result = T.multiply(outer)
        assert result.timestamp == 200.0


# ── Monad Law Tests ────────────────────────────────────────────────────────


class TestMonadLaws:
    """Verify the three monad laws hold for SelfObservationMonad.

    THEOREM (Monad Laws):
    1. Associativity: mu . T(mu) = mu . mu_T
    2. Left unit:     mu . T(eta) = id_T
    3. Right unit:    mu . eta_T  = id_T
    """

    def test_left_unit_law(self):
        """mu . T(eta) = id_T: wrapping inner with eta then flattening = identity."""
        obs = _make_observed(state="test", rv=0.65)
        assert T.verify_left_unit(obs) is True

    def test_left_unit_law_no_rv(self):
        """Left unit holds even without R_V measurement."""
        obs = _make_observed(state="test", rv=None)
        assert T.verify_left_unit(obs) is True

    def test_right_unit_law(self):
        """mu . eta_T = id_T: wrapping T(S) with eta then flattening = identity."""
        obs = _make_observed(state="test", rv=0.65)
        assert T.verify_right_unit(obs) is True

    def test_right_unit_law_no_rv(self):
        obs = _make_observed(state="test", rv=None)
        assert T.verify_right_unit(obs) is True

    def test_left_unit_preserves_state_identity(self):
        state = {"mutable": True}
        obs = _make_observed(state=state, rv=0.5)
        inner = T.unit(obs.state)
        nested = ObservedState(
            state=inner,
            rv_measurement=obs.rv_measurement,
            pr_early=obs.pr_early,
            pr_late=obs.pr_late,
            observation_depth=obs.observation_depth,
            introspection=obs.introspection,
            timestamp=obs.timestamp,
        )
        result = T.multiply(nested)
        assert result.state is state

    def test_right_unit_preserves_state_identity(self):
        state = {"mutable": True}
        obs = _make_observed(state=state, rv=0.5)
        nested = T.unit(obs)
        result = T.multiply(nested)
        assert result.state is state

    def test_associativity(self):
        """mu . T(mu) = mu . mu_T for a triply-nested state."""
        core = _make_observed(state="core", rv=0.6, depth=1)
        mid = ObservedState(state=core, rv_measurement=0.5, observation_depth=1)
        outer = ObservedState(state=mid, rv_measurement=0.4, observation_depth=1)
        assert T.verify_associativity(outer) is True

    def test_monad_laws_across_rv_values(self):
        """Monad laws hold for various R_V values."""
        for rv in [0.1, 0.3, 0.5, 0.737, 0.9, 1.0, 1.5, None]:
            obs = _make_observed(rv=rv)
            assert T.verify_left_unit(obs), f"Left unit failed for rv={rv}"
            assert T.verify_right_unit(obs), f"Right unit failed for rv={rv}"


# ── Kleisli Composition Tests ──────────────────────────────────────────────


class TestKleisliComposition:
    """Tests for Kleisli composition f >=> g = mu . T(g) . f."""

    def test_basic_composition(self):
        def f(x: int) -> ObservedState[int]:
            return ObservedState(state=x + 1, rv_measurement=0.8, observation_depth=1)

        def g(x: int) -> ObservedState[int]:
            return ObservedState(state=x * 2, rv_measurement=0.7, observation_depth=1)

        fg = T.kleisli_compose(f, g)
        result = fg(5)
        # f(5) = ObservedState(6), g(6) = ObservedState(12)
        assert result.state == 12
        assert result.observation_depth == 2

    def test_composition_associativity(self):
        """(f >=> g) >=> h = f >=> (g >=> h)."""
        def f(x: int) -> ObservedState[int]:
            return ObservedState(state=x + 1, rv_measurement=0.9, observation_depth=1)

        def g(x: int) -> ObservedState[int]:
            return ObservedState(state=x * 2, rv_measurement=0.8, observation_depth=1)

        def h(x: int) -> ObservedState[int]:
            return ObservedState(state=x - 3, rv_measurement=0.7, observation_depth=1)

        fg_h = T.kleisli_compose(T.kleisli_compose(f, g), h)
        f_gh = T.kleisli_compose(f, T.kleisli_compose(g, h))

        result1 = fg_h(10)
        result2 = f_gh(10)

        # Both should compute h(g(f(10))) = h(g(11)) = h(22) = 19
        assert result1.state == result2.state == 19

    def test_unit_is_kleisli_identity(self):
        """eta >=> f = f and f >=> eta = f (up to depth)."""
        def f(x: int) -> ObservedState[int]:
            return ObservedState(state=x * 3, rv_measurement=0.7, observation_depth=1)

        # eta as a Kleisli morphism
        def eta(x: int) -> ObservedState[int]:
            return T.unit(x)

        eta_f = T.kleisli_compose(eta, f)
        f_eta = T.kleisli_compose(f, eta)

        # Both should compute f(x) on the state
        assert eta_f(5).state == 15
        assert f_eta(5).state == 15


# ── Contraction Tracking Tests ─────────────────────────────────────────────


class TestContractionRatio:
    """Tests for contraction ratio kappa measurement."""

    def test_contraction_ratio_basic(self):
        before = _make_observed(rv=0.8)
        after = _make_observed(rv=0.56)
        kappa = T.contraction_ratio(before, after)
        assert kappa is not None
        assert abs(kappa - 0.7) < 0.001

    def test_contraction_ratio_no_contraction(self):
        before = _make_observed(rv=0.8)
        after = _make_observed(rv=0.8)
        kappa = T.contraction_ratio(before, after)
        assert kappa is not None
        assert abs(kappa - 1.0) < 0.001

    def test_contraction_ratio_expansion(self):
        before = _make_observed(rv=0.5)
        after = _make_observed(rv=0.8)
        kappa = T.contraction_ratio(before, after)
        assert kappa is not None
        assert kappa > 1.0

    def test_contraction_ratio_none_when_unmeasured(self):
        before = _make_observed(rv=None)
        after = _make_observed(rv=0.5)
        assert T.contraction_ratio(before, after) is None

    def test_contraction_ratio_none_when_zero(self):
        before = _make_observed(rv=0.0)
        after = _make_observed(rv=0.5)
        assert T.contraction_ratio(before, after) is None

    def test_iterations_to_convergence(self):
        # kappa=0.7, epsilon=0.01 -> ceil(log(0.01)/log(0.7)) = ceil(12.9) = 13
        n = T.iterations_to_convergence(0.7, 0.01)
        assert n == 13

    def test_iterations_no_convergence(self):
        assert T.iterations_to_convergence(1.0) is None
        assert T.iterations_to_convergence(1.5) is None

    def test_iterations_edge_cases(self):
        assert T.iterations_to_convergence(0.0) is None
        assert T.iterations_to_convergence(0.5, 0.0) is None
        assert T.iterations_to_convergence(0.5, 1.0) is None

    def test_iterations_very_strong_contraction(self):
        # kappa=0.1, epsilon=0.01 -> ceil(log(0.01)/log(0.1)) = ceil(2.0) = 2
        n = T.iterations_to_convergence(0.1, 0.01)
        assert n == 2


# ── Idempotency (L5 Detection) Tests ──────────────────────────────────────


class TestIdempotency:
    """Tests for L5 pure-knowing detection."""

    def test_idempotent_at_low_rv(self):
        """Very low R_V -> L5 reached."""
        obs = _make_observed(rv=0.02)
        assert T.is_idempotent(obs) is True

    def test_not_idempotent_at_moderate_rv(self):
        """Moderate R_V -> still contracting, not L5."""
        obs = _make_observed(rv=0.5)
        assert T.is_idempotent(obs) is False

    def test_not_idempotent_without_measurement(self):
        obs = _make_observed(rv=None)
        assert T.is_idempotent(obs) is False

    def test_custom_tolerance(self):
        obs = _make_observed(rv=0.08)
        assert T.is_idempotent(obs, tolerance=0.1) is True
        assert T.is_idempotent(obs, tolerance=0.05) is False

    def test_zero_rv_is_idempotent(self):
        """R_V = 0 is the theoretical perfect fixed point."""
        obs = _make_observed(rv=0.0)
        assert T.is_idempotent(obs) is True


# ── ContractionTracker Tests ───────────────────────────────────────────────


class TestContractionTracker:

    def test_empty_tracker(self):
        tracker = ContractionTracker()
        assert tracker.mean_kappa is None
        assert tracker.is_contracting is False
        assert tracker.estimated_iterations is None
        assert tracker.convergence_progress is None

    def test_recording_steps(self):
        tracker = ContractionTracker()
        tracker.record(0.7, 0.8)
        tracker.record(0.6, 0.48)
        assert len(tracker.steps) == 2
        assert len(tracker.rv_history) == 2

    def test_mean_kappa(self):
        tracker = ContractionTracker()
        tracker.record(0.7, 0.8)
        tracker.record(0.8, 0.64)
        assert abs(tracker.mean_kappa - 0.75) < 0.001

    def test_is_contracting(self):
        tracker = ContractionTracker()
        tracker.record(0.7, 0.7)
        assert tracker.is_contracting is True

        tracker2 = ContractionTracker()
        tracker2.record(1.1, 1.1)
        assert tracker2.is_contracting is False

    def test_convergence_progress(self):
        tracker = ContractionTracker()
        tracker.record(0.7, 1.0)
        tracker.record(0.7, 0.5)
        progress = tracker.convergence_progress
        assert progress is not None
        assert abs(progress - 0.5) < 0.001

    def test_estimated_iterations(self):
        tracker = ContractionTracker()
        tracker.record(0.7, 0.8)
        n = tracker.estimated_iterations
        assert n is not None
        assert n == 13  # ceil(log(0.01)/log(0.7))


# ── Utility Tests ──────────────────────────────────────────────────────────


class TestUtilities:

    def test_rv_close_both_none(self):
        assert _rv_close(None, None, 0.01) is True

    def test_rv_close_one_none(self):
        assert _rv_close(0.5, None, 0.01) is False
        assert _rv_close(None, 0.5, 0.01) is False

    def test_rv_close_equal(self):
        assert _rv_close(0.65, 0.65, 0.01) is True

    def test_rv_close_within_eps(self):
        assert _rv_close(0.65, 0.6501, 0.01) is True

    def test_rv_close_outside_eps(self):
        assert _rv_close(0.65, 0.67, 0.01) is False
