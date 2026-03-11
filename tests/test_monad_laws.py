"""Test monad laws and Lawvere fixed-point convergence.

Three sections:
1. Monad laws (left unit, right unit, associativity)
2. Kleisli composition and contraction tracking
3. Fixed-point convergence: iterated self-observation converges to idempotent state
   (the numerical Lawvere fixed point — L5 condition)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ts() -> datetime:
    return datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc)


def _reading(rv: float, group: str = "test") -> RVReading:
    return RVReading(
        rv=rv,
        pr_early=10.0,
        pr_late=rv * 10.0,
        model_name="test-model",
        early_layer=2,
        late_layer=30,
        prompt_hash="0" * 16,
        prompt_group=group,
        timestamp=_ts(),
    )


def _observe_with_rv(rv: float):
    """Return a Kleisli morphism that wraps a value with a given R_V reading."""
    def morphism(x):
        return ObservedState(
            state=x,
            rv_reading=_reading(rv),
            introspection={"rv": rv},
            observation_depth=1,
        )
    return morphism


# ── 1. Monad Laws ───────────────────────────────────────────────────────────

class TestMonadLaws:
    """The three monad laws must hold for ObservedState to be a valid monad."""

    def test_left_unit(self):
        """bind(pure(x), f) == f(x)

        Embedding a value then binding is the same as applying f directly.
        """
        x = "hello"
        f = _observe_with_rv(0.7)

        result = bind(pure(x), f)
        direct = f(x)

        assert result.state == direct.state
        assert result.rv_reading == direct.rv_reading
        assert result.observation_depth == direct.observation_depth

    def test_right_unit(self):
        """bind(m, pure) == m

        Binding with pure is identity.
        """
        m = ObservedState(
            state=42,
            rv_reading=_reading(0.6),
            introspection={"cycle": 1},
            observation_depth=1,
        )

        result = bind(m, pure)

        assert result.state == m.state
        assert result.rv_reading == m.rv_reading
        assert result.introspection == m.introspection
        assert result.observation_depth == m.observation_depth

    def test_associativity(self):
        """bind(bind(m, f), g) == bind(m, lambda x: bind(f(x), g))

        Chaining binds is associative — order of composition doesn't matter.
        """
        m = ObservedState(
            state=1,
            rv_reading=_reading(0.9),
            introspection={"step": 0},
            observation_depth=1,
        )
        f = _observe_with_rv(0.7)
        g = _observe_with_rv(0.5)

        # Left: bind(bind(m, f), g)
        left = bind(bind(m, f), g)

        # Right: bind(m, lambda x: bind(f(x), g))
        right = bind(m, lambda x: bind(f(x), g))

        assert left.state == right.state
        assert left.observation_depth == right.observation_depth
        # Both should carry the latest rv_reading (from g)
        assert left.rv_reading.rv == right.rv_reading.rv


class TestFlatten:
    """μ (join) collapses nested ObservedState."""

    def test_flatten_extracts_inner_state(self):
        inner = ObservedState(
            state="payload",
            rv_reading=_reading(0.6),
            introspection={"inner": True},
            observation_depth=1,
        )
        outer = ObservedState(
            state=inner,
            rv_reading=_reading(0.4),
            introspection={"outer": True},
            observation_depth=1,
        )

        flat = flatten(outer)

        assert flat.state == "payload"
        # Outer has rv_reading so it takes precedence
        assert flat.rv_reading.rv == pytest.approx(0.4)
        # Introspection merges (inner first, outer overlays)
        assert flat.introspection["inner"] is True
        assert flat.introspection["outer"] is True
        # Depths add
        assert flat.observation_depth == 2

    def test_flatten_prefers_outer_rv_when_present(self):
        inner = ObservedState(state="x", rv_reading=_reading(0.8), observation_depth=1)
        outer = ObservedState(state=inner, rv_reading=_reading(0.3), observation_depth=1)

        flat = flatten(outer)
        assert flat.rv_reading.rv == pytest.approx(0.3)

    def test_flatten_falls_through_to_inner_rv(self):
        inner = ObservedState(state="x", rv_reading=_reading(0.5), observation_depth=1)
        outer = ObservedState(state=inner, rv_reading=None, observation_depth=1)

        flat = flatten(outer)
        assert flat.rv_reading.rv == pytest.approx(0.5)


# ── 2. Kleisli Composition ──────────────────────────────────────────────────

class TestKleisliComposition:

    def test_kleisli_compose_chains_morphisms(self):
        f = _observe_with_rv(0.8)
        g = _observe_with_rv(0.6)

        composed = kleisli_compose(f, g)
        result = composed("input")

        assert result.state == "input"
        # g's reading should be the final one
        assert result.rv_reading.rv == pytest.approx(0.6)

    def test_contraction_ratio_measures_rv_change(self):
        before = ObservedState(
            state="x",
            rv_reading=_reading(0.8),
            observation_depth=1,
        )
        morphism = _observe_with_rv(0.4)

        ratio = kleisli_contraction_ratio(morphism, before)

        assert ratio is not None
        assert ratio == pytest.approx(0.5)  # 0.4 / 0.8

    def test_contraction_ratio_none_without_input_rv(self):
        morphism = _observe_with_rv(0.4)
        ratio = kleisli_contraction_ratio(morphism, "bare_value")
        # No input rv_reading → cannot compute ratio
        assert ratio is None


# ── 3. Fixed-Point Convergence (The Lawvere Test) ───────────────────────────

class TestFixedPointConvergence:
    """The central claim: iterated self-observation converges.

    If self-reference is a contraction mapping, then repeated application of
    the self-observation monad should converge to a fixed point where
    additional observation adds nothing — the L5 condition.

    We simulate this with a contracting observer: each observation contracts
    the R_V reading by a fixed ratio (< 1), mimicking the empirical finding
    that recursive self-reference contracts Value matrix column space.
    """

    @staticmethod
    def _contracting_observer(contraction_rate: float = 0.8):
        """Observer that contracts R_V by a fixed ratio each application.

        monad.observe() strips the wrapper and passes the bare payload to
        the observer. To simulate cumulative geometric contraction (each
        observation compounds on the last), we track the current R_V in a
        closure. This models the empirical finding: each layer of recursive
        self-reference further contracts Value matrix column space.
        """
        state = {"current_rv": 1.0}

        def observer(_payload):
            state["current_rv"] *= contraction_rate
            return _reading(state["current_rv"], group="L5_convergence")
        return observer

    def test_iterated_observation_converges(self):
        """Apply self-observation repeatedly. R_V should converge toward 0.

        Each observation contracts R_V by 0.8:
        1.0 → 0.8 → 0.64 → 0.512 → 0.4096 → ...
        Geometric series converging to 0. The Banach fixed point.
        """
        monad = SelfObservationMonad(self._contracting_observer(0.8))

        state = "initial_state"
        rv_trajectory = []

        # Apply 10 iterations of self-observation
        observed = monad.pure(state)
        for i in range(10):
            observed = monad.observe(observed)
            if observed.rv_reading is not None:
                rv_trajectory.append(observed.rv_reading.rv)

        # R_V should be monotonically decreasing
        for j in range(1, len(rv_trajectory)):
            assert rv_trajectory[j] < rv_trajectory[j - 1], (
                f"R_V not decreasing at step {j}: {rv_trajectory[j]:.4f} >= {rv_trajectory[j-1]:.4f}"
            )

        # After 10 iterations with rate 0.8: 0.8^10 ≈ 0.107
        assert rv_trajectory[-1] < 0.15, (
            f"R_V did not converge sufficiently: {rv_trajectory[-1]:.4f}"
        )

    def test_convergence_rate_matches_contraction(self):
        """The convergence rate should match the Lipschitz constant.

        With contraction rate k=0.8, after n steps: R_V ≈ k^n.
        This is the Banach fixed-point theorem's quantitative prediction.
        """
        k = 0.7
        monad = SelfObservationMonad(self._contracting_observer(k))

        observed = monad.pure("state")
        for _ in range(5):
            observed = monad.observe(observed)

        actual_rv = observed.rv_reading.rv
        predicted_rv = k ** 5  # 0.7^5 = 0.16807

        assert actual_rv == pytest.approx(predicted_rv, rel=1e-6), (
            f"Actual R_V {actual_rv:.6f} != predicted {predicted_rv:.6f}"
        )

    def test_idempotent_at_convergence(self):
        """At convergence, nested observation should be idempotent.

        When outer_rv ≈ inner_rv (within tolerance), the system has reached
        the fixed point: Sx = x. This IS the L5 condition — observation of
        observation yields no new information.
        """
        # Use a very strong contraction so values are near-zero quickly
        monad = SelfObservationMonad(self._contracting_observer(0.01))

        observed = monad.pure("state")
        # After enough iterations, R_V ≈ 0
        for _ in range(5):
            observed = monad.observe(observed)

        # Now apply one more layer and check idempotency
        double_observed = monad.observe(observed)

        # Both inner and outer R_V should be approximately equal (both ≈ 0)
        assert is_idempotent(double_observed, tolerance=1e-6), (
            "System did not reach idempotent fixed point after strong contraction"
        )

    def test_not_idempotent_early(self):
        """Before convergence, observation should NOT be idempotent.

        The L3 state: self-reference is active but hasn't stabilized.
        """
        monad = SelfObservationMonad(self._contracting_observer(0.8))

        # Just one observation — far from convergence
        observed = monad.observe(monad.pure("state"))
        double_observed = monad.observe(observed)

        # 0.8 vs 0.64 — not close enough for idempotency
        assert not is_idempotent(double_observed, tolerance=1e-6), (
            "System falsely reported idempotent before convergence"
        )

    def test_l3_to_l5_trajectory(self):
        """Simulate the full L1 → L3 → L4 → L5 trajectory.

        L1-L2: No self-reference (R_V ≈ 1.0)
        L3:    Self-reference begins, R_V contracting but unstable
        L4:    Strong contraction, R_V < 0.737
        L5:    Fixed point reached, observation is idempotent
        """
        monad = SelfObservationMonad(self._contracting_observer(0.7))

        trajectory = []
        observed = monad.pure("awareness")

        for i in range(15):
            observed = monad.observe(observed)
            rv = observed.rv_reading.rv if observed.rv_reading else 1.0
            double = monad.observe(observed)
            idempotent = is_idempotent(double, tolerance=0.01)

            level = (
                "L5" if idempotent else
                "L4" if rv < 0.5 else
                "L3" if rv < 0.737 else
                "L1-L2"
            )
            trajectory.append({
                "step": i + 1,
                "rv": rv,
                "level": level,
                "idempotent": idempotent,
            })

        # Verify phase transitions occurred
        levels_seen = {t["level"] for t in trajectory}

        # Must pass through L3 (contraction begins)
        assert "L3" in levels_seen, "Never entered L3 (crisis/paradox)"

        # Must reach L4 (strong contraction)
        assert "L4" in levels_seen, "Never reached L4 (collapse)"

        # Must reach L5 (fixed point) eventually
        assert "L5" in levels_seen, "Never reached L5 (fixed point)"

        # L5 must come after L3 — the phase transition has direction
        first_l3 = next(t["step"] for t in trajectory if t["level"] == "L3")
        first_l5 = next(t["step"] for t in trajectory if t["level"] == "L5")
        assert first_l5 > first_l3, "L5 appeared before L3 — impossible"

    def test_different_contraction_rates_different_convergence_speed(self):
        """Stronger contraction (lower k) → faster convergence.

        This mirrors the empirical finding: L5 prompts (Sx=x, eigenstate)
        produce stronger R_V contraction than L3 prompts.
        """
        slow_monad = SelfObservationMonad(self._contracting_observer(0.9))
        fast_monad = SelfObservationMonad(self._contracting_observer(0.5))

        slow_obs = slow_monad.pure("state")
        fast_obs = fast_monad.pure("state")

        for _ in range(5):
            slow_obs = slow_monad.observe(slow_obs)
            fast_obs = fast_monad.observe(fast_obs)

        slow_rv = slow_obs.rv_reading.rv
        fast_rv = fast_obs.rv_reading.rv

        # 0.9^5 = 0.590, 0.5^5 = 0.031
        assert fast_rv < slow_rv, (
            f"Stronger contraction didn't converge faster: "
            f"fast={fast_rv:.4f} >= slow={slow_rv:.4f}"
        )

    def test_kleisli_chain_contraction(self):
        """Composing Kleisli morphisms should accumulate contraction.

        f >=> g >=> h should show progressive R_V decrease,
        modeling the pipeline: self-reference → deeper recursion → collapse.
        """
        f = _observe_with_rv(0.8)  # L3: mild contraction
        g = _observe_with_rv(0.5)  # L4: strong contraction
        h = _observe_with_rv(0.3)  # L5: near fixed point

        pipeline = kleisli_compose(kleisli_compose(f, g), h)
        result = pipeline("awareness")

        # Final R_V should be from h (the deepest observation)
        assert result.rv_reading.rv == pytest.approx(0.3)
        # Depth accumulates through composition
        assert result.observation_depth >= 1


class TestSelfObservationMonadClass:
    """Test the SelfObservationMonad class interface."""

    def test_pure_creates_effect_free_wrapper(self):
        monad = SelfObservationMonad(lambda x: _reading(0.5))
        observed = monad.pure("state")

        assert observed.state == "state"
        assert observed.is_pure

    def test_observe_adds_rv_reading(self):
        monad = SelfObservationMonad(lambda x: _reading(0.6))
        observed = monad.observe("raw_state")

        assert observed.rv_reading.rv == pytest.approx(0.6)
        assert observed.observation_depth == 1
        assert not observed.is_pure

    def test_observe_on_observed_increases_depth(self):
        monad = SelfObservationMonad(lambda x: _reading(0.5))
        first = monad.observe("state")
        second = monad.observe(first)

        assert second.observation_depth == 2
        # The inner state is the first ObservedState
        assert isinstance(second.state, ObservedState)
        assert second.state.state == "state"

    def test_bind_preserves_observation_chain(self):
        monad = SelfObservationMonad(lambda x: _reading(0.5))
        observed = monad.observe("start")

        result = monad.bind(observed, _observe_with_rv(0.3))

        assert result.rv_reading.rv == pytest.approx(0.3)
        assert result.state == "start"
