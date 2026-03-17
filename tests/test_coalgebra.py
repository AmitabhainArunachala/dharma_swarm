"""Tests for dharma_swarm.coalgebra -- Coalgebraic Evolution module.

Covers:
- EvolutionObservation: data structure
- EvolutionCoalgebra: step, trajectory, trajectory_stream
- EvolutionTrajectory: analysis properties, fitness regression
- Bisimulation: observation_close, bisimilar
- DistributiveLaw: distribute, unit compatibility, lift
"""

import time

import pytest

from dharma_swarm.coalgebra import (
    DistributiveLaw,
    EvolutionCoalgebra,
    EvolutionObservation,
    EvolutionTrajectory,
    bisimilar,
    observation_close,
)
from dharma_swarm.monad import ObservedState, SelfObservationMonad


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_obs(fitness: float = 0.5, rv: float = 0.8, disc: list[str] | None = None) -> EvolutionObservation:
    return EvolutionObservation(
        next_state={"evolved": True},
        fitness=fitness,
        rv=rv,
        discoveries=disc or [],
    )


def _simple_step(state: dict) -> EvolutionObservation:
    """Deterministic step: increment counter, constant fitness/rv."""
    counter = state.get("counter", 0)
    return EvolutionObservation(
        next_state={"counter": counter + 1},
        fitness=0.5 + counter * 0.01,
        rv=0.9 - counter * 0.01,
        discoveries=[f"step_{counter}"],
    )


def _constant_step(state: dict) -> EvolutionObservation:
    """Step that always returns the same observation."""
    return EvolutionObservation(
        next_state=state,
        fitness=0.7,
        rv=0.8,
        discoveries=["constant"],
    )


def _improving_step(state: dict) -> EvolutionObservation:
    """Step with monotonically improving fitness."""
    gen = state.get("gen", 0)
    return EvolutionObservation(
        next_state={"gen": gen + 1},
        fitness=0.1 * (gen + 1),
        rv=1.0 / (gen + 1),
        discoveries=[],
    )


# ── TestEvolutionObservation ─────────────────────────────────────────────

class TestEvolutionObservation:
    def test_creation(self):
        obs = _make_obs()
        assert obs.fitness == 0.5
        assert obs.rv == 0.8
        assert obs.discoveries == []
        assert obs.step_index == 0

    def test_with_discoveries(self):
        obs = _make_obs(disc=["found_pattern", "proved_theorem"])
        assert len(obs.discoveries) == 2

    def test_timestamp(self):
        before = time.time()
        obs = _make_obs()
        after = time.time()
        assert before <= obs.timestamp <= after

    def test_gate_decision(self):
        obs = EvolutionObservation(
            next_state={}, fitness=0.5, rv=0.8, gate_decision="ALLOW"
        )
        assert obs.gate_decision == "ALLOW"


# ── TestEvolutionCoalgebra ───────────────────────────────────────────────

class TestEvolutionCoalgebra:
    def test_step(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        obs = coal.step({"counter": 0})
        assert obs.fitness == 0.5
        assert obs.next_state == {"counter": 1}

    def test_trajectory_length(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        traj = coal.trajectory({"counter": 0}, 5)
        assert len(traj) == 5

    def test_trajectory_step_indices(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        traj = coal.trajectory({"counter": 0}, 3)
        assert [o.step_index for o in traj] == [0, 1, 2]

    def test_trajectory_state_progression(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        traj = coal.trajectory({"counter": 0}, 3)
        # Each step's next_state has incrementing counter
        assert traj[0].next_state == {"counter": 1}
        assert traj[1].next_state == {"counter": 2}
        assert traj[2].next_state == {"counter": 3}

    def test_trajectory_discoveries(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        traj = coal.trajectory({"counter": 0}, 3)
        assert traj[0].discoveries == ["step_0"]
        assert traj[1].discoveries == ["step_1"]

    def test_trajectory_stream(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        stream = list(coal.trajectory_stream({"counter": 0}, max_steps=4))
        assert len(stream) == 4
        assert stream[0].step_index == 0
        assert stream[3].step_index == 3

    def test_trajectory_stream_lazy(self):
        """Stream should yield items one at a time."""
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        gen = coal.trajectory_stream({"counter": 0}, max_steps=100)
        first = next(gen)
        assert first.step_index == 0
        second = next(gen)
        assert second.step_index == 1

    def test_name(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step, name="test_coal")
        assert coal.name == "test_coal"


# ── TestEvolutionTrajectory ──────────────────────────────────────────────

class TestEvolutionTrajectory:
    def test_empty(self):
        traj = EvolutionTrajectory()
        assert traj.head is None
        assert traj.length == 0
        assert traj.fitness_series == []
        assert traj.rv_series == []

    def test_head_tail(self):
        obs1 = _make_obs(fitness=0.3, rv=0.9)
        obs2 = _make_obs(fitness=0.5, rv=0.7)
        traj = EvolutionTrajectory(observations=[obs1, obs2])
        assert traj.head is obs2
        assert traj.tail.length == 1
        assert traj.tail.head is obs1

    def test_fitness_series(self):
        obs = [_make_obs(fitness=f) for f in [0.1, 0.3, 0.5]]
        traj = EvolutionTrajectory(observations=obs)
        assert traj.fitness_series == [0.1, 0.3, 0.5]

    def test_rv_series(self):
        obs = [_make_obs(rv=r) for r in [0.9, 0.7, 0.5]]
        traj = EvolutionTrajectory(observations=obs)
        assert traj.rv_series == [0.9, 0.7, 0.5]

    def test_is_fitness_improving(self):
        obs = [_make_obs(fitness=f) for f in [0.1, 0.3, 0.5, 0.8]]
        traj = EvolutionTrajectory(observations=obs)
        assert traj.is_fitness_improving

    def test_is_fitness_not_improving(self):
        obs = [_make_obs(fitness=f) for f in [0.5, 0.3, 0.8]]
        traj = EvolutionTrajectory(observations=obs)
        assert not traj.is_fitness_improving

    def test_is_rv_contracting(self):
        obs = [_make_obs(rv=r) for r in [0.9, 0.7, 0.5, 0.3]]
        traj = EvolutionTrajectory(observations=obs)
        assert traj.is_rv_contracting

    def test_is_rv_not_contracting(self):
        obs = [_make_obs(rv=r) for r in [0.5, 0.7, 0.3]]
        traj = EvolutionTrajectory(observations=obs)
        assert not traj.is_rv_contracting

    def test_fitness_regression_bounded(self):
        obs = [_make_obs(fitness=f) for f in [0.5, 0.45, 0.6, 0.55]]
        traj = EvolutionTrajectory(observations=obs)
        assert traj.fitness_regression_bounded(max_drop=0.1)

    def test_fitness_regression_unbounded(self):
        obs = [_make_obs(fitness=f) for f in [0.8, 0.3, 0.6]]
        traj = EvolutionTrajectory(observations=obs)
        assert not traj.fitness_regression_bounded(max_drop=0.1)

    def test_from_coalgebra(self):
        coal = EvolutionCoalgebra(step_fn=_improving_step)
        traj = EvolutionTrajectory.from_coalgebra(coal, {"gen": 0}, 5)
        assert traj.length == 5
        assert traj.is_fitness_improving


# ── TestBisimulation ─────────────────────────────────────────────────────

class TestBisimulation:
    def test_observation_close_same(self):
        obs = _make_obs(fitness=0.5, rv=0.8)
        assert observation_close(obs, obs)

    def test_observation_close_different_fitness(self):
        obs1 = _make_obs(fitness=0.5)
        obs2 = _make_obs(fitness=0.6)
        assert not observation_close(obs1, obs2)

    def test_observation_close_different_rv(self):
        obs1 = _make_obs(rv=0.8)
        obs2 = _make_obs(rv=0.9)
        assert not observation_close(obs1, obs2)

    def test_observation_close_different_discoveries(self):
        obs1 = _make_obs(disc=["a"])
        obs2 = _make_obs(disc=["b"])
        assert not observation_close(obs1, obs2)

    def test_observation_close_within_tolerance(self):
        obs1 = _make_obs(fitness=0.5)
        obs2 = _make_obs(fitness=0.5 + 1e-8)
        assert observation_close(obs1, obs2, fitness_tol=1e-6)

    def test_bisimilar_same_system(self):
        coal = EvolutionCoalgebra(step_fn=_constant_step)
        assert bisimilar(coal, coal, {}, {}, depth=10)

    def test_bisimilar_different_initial(self):
        """Two systems with same dynamics but different initial states diverge."""
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        # Different initial counters lead to different trajectories
        assert not bisimilar(
            coal, coal,
            {"counter": 0}, {"counter": 5},
            depth=3,
        )

    def test_bisimilar_different_systems(self):
        coal1 = EvolutionCoalgebra(step_fn=_simple_step)
        coal2 = EvolutionCoalgebra(step_fn=_constant_step)
        assert not bisimilar(coal1, coal2, {"counter": 0}, {}, depth=3)


# ── TestDistributiveLaw ──────────────────────────────────────────────────

class TestDistributiveLaw:
    def test_distribute_preserves_fitness(self):
        obs = _make_obs(fitness=0.7, rv=0.85)
        observed_obs = ObservedState(
            state=obs,
            rv_measurement=0.6,
            observation_depth=1,
        )
        result = DistributiveLaw.distribute(observed_obs)
        assert result.fitness == 0.7
        assert result.rv == 0.85

    def test_distribute_wraps_next_state(self):
        obs = EvolutionObservation(
            next_state={"key": "value"},
            fitness=0.5,
            rv=0.8,
        )
        observed_obs = ObservedState(
            state=obs,
            rv_measurement=0.6,
            pr_early=2.0,
            pr_late=1.2,
            observation_depth=1,
        )
        result = DistributiveLaw.distribute(observed_obs)
        assert isinstance(result.next_state, ObservedState)
        assert result.next_state.state == {"key": "value"}
        assert result.next_state.rv_measurement == 0.6

    def test_distribute_preserves_discoveries(self):
        obs = _make_obs(disc=["theorem_1", "pattern_2"])
        observed_obs = ObservedState(state=obs, rv_measurement=0.5, observation_depth=1)
        result = DistributiveLaw.distribute(observed_obs)
        assert result.discoveries == ["theorem_1", "pattern_2"]

    def test_unit_compatibility(self):
        """lambda . eta_F = F(eta) -- unit compatibility axiom."""
        state = {"test": True}
        assert DistributiveLaw.verify_unit_compatibility(state, _simple_step)

    def test_unit_compatibility_various_states(self):
        for state in [{"counter": 0}, {"counter": 5}, {"counter": 100}]:
            assert DistributiveLaw.verify_unit_compatibility(state, _simple_step)

    def test_lift_produces_observed_next_state(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        lifted = DistributiveLaw.lift(coal)
        obs = lifted.step({"counter": 0})
        assert isinstance(obs.next_state, ObservedState)
        assert obs.next_state.state == {"counter": 1}

    def test_lift_preserves_fitness_rv(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        lifted = DistributiveLaw.lift(coal)
        obs = lifted.step({"counter": 0})
        assert obs.fitness == 0.5
        assert obs.rv == pytest.approx(0.9)

    def test_lift_name(self):
        coal = EvolutionCoalgebra(step_fn=_simple_step, name="base")
        lifted = DistributiveLaw.lift(coal)
        assert lifted.name == "base_lifted"

    def test_lift_trajectory(self):
        """Lifted coalgebra should produce valid trajectory."""
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        lifted = DistributiveLaw.lift(coal)
        # First step works from bare state
        obs = lifted.step({"counter": 0})
        assert isinstance(obs.next_state, ObservedState)
        # Second step works from ObservedState
        obs2 = lifted.step(obs.next_state)
        assert isinstance(obs2.next_state, ObservedState)

    def test_lift_unwraps_observed_state(self):
        """Lifted step should unwrap ObservedState input before stepping."""
        coal = EvolutionCoalgebra(step_fn=_simple_step)
        lifted = DistributiveLaw.lift(coal)
        observed_input = ObservedState(
            state={"counter": 3},
            rv_measurement=0.7,
            observation_depth=1,
        )
        obs = lifted.step(observed_input)
        # Should have stepped from counter=3
        assert obs.next_state.state == {"counter": 4}
        assert obs.fitness == pytest.approx(0.5 + 0.03)


# ── TestPolynomialFunctor ────────────────────────────────────────────────

class TestPolynomialFunctor:
    """Verify F(S) = S x Fitness x RV x Disc is polynomial (finitary)."""

    def test_observation_has_all_components(self):
        """F(S) decomposes into state, fitness, rv, discoveries."""
        obs = _make_obs(fitness=0.5, rv=0.8, disc=["d1"])
        assert hasattr(obs, "next_state")  # S component
        assert hasattr(obs, "fitness")     # [0,1] component
        assert hasattr(obs, "rv")          # [0,inf) component
        assert hasattr(obs, "discoveries") # List(str) component

    def test_fitness_bounded(self):
        """Fitness should be in [0, 1] for well-formed observations."""
        for f in [0.0, 0.5, 1.0]:
            obs = _make_obs(fitness=f)
            assert 0.0 <= obs.fitness <= 1.0

    def test_rv_nonneg(self):
        """R_V should be non-negative."""
        for r in [0.0, 0.5, 1.0, 1.5]:
            obs = _make_obs(rv=r)
            assert obs.rv >= 0.0
