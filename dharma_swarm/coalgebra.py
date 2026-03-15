"""Coalgebraic Evolution for DHARMA SWARM.

Wraps evolution.py's PROPOSE->GATE->EVALUATE->ARCHIVE->SELECT pipeline
as an F-coalgebra, enabling coinductive reasoning about evolution
trajectories and bisimulation-based system equivalence.

Mathematical foundation (Chapter 4, categorical_foundations.pdf):

DEFINITION 4.1: An F-coalgebra is a pair (S, alpha) where
    alpha: S -> F(S) decomposes the state into observable components.

THEOREM (Lambek): The final coalgebra Z satisfies Z ~= F(Z).
The unique morphism !: (S, alpha) -> Z sends each initial state
to its complete evolution trajectory.

PROPOSITION 4.5 (Bisimulation): Two evolution systems are bisimilar
iff they produce identical observation streams -- behavioral equivalence
without internal state inspection.

CONSTRUCTION 4.7 (Distributive Law): lambda: TF => FT enables
lifting the coalgebra into the Eilenberg-Moore category of T,
yielding self-observed evolution steps.

All existing evolution.py tests continue to pass -- coalgebra wraps,
doesn't replace.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from dharma_swarm.monad import ObservedState, SelfObservationMonad


# ── Evolution Observation: F(S) ──────────────────────────────────────────

@dataclass
class EvolutionObservation:
    """F(S) = S x Fitness x RV x Disc -- the output of one evolution step.

    This is the functor F applied to the current state: it decomposes
    the state into its observable components.

    DEFINITION 4.1: F is a polynomial endofunctor on Set.
    F(S) = S x [0,1] x [0,inf) x List(str) is indeed polynomial
    (product of representables and constant presheaves).

    CONSTRUCTION: Observable output of one coalgebraic evolution step.
    """

    next_state: Any
    """The evolved state (next configuration of the system)."""

    fitness: float
    """fitness(s) -- weighted fitness score from elegance.py / archive.py."""

    rv: float
    """rv(s) -- R_V participation ratio from rv.py / monad."""

    discoveries: list[str] = field(default_factory=list)
    """Theorems proved, patterns found, or lessons learned this step."""

    timestamp: float = field(default_factory=time.time)
    """UTC timestamp of this observation."""

    gate_decision: Optional[str] = None
    """ALLOW / REVIEW / BLOCK from dharmic gates."""

    step_index: int = 0
    """Position in the trajectory (0-indexed)."""


# ── Evolution Coalgebra: (S, alpha) ──────────────────────────────────────

StepFunction = Any  # Callable[[S], EvolutionObservation] -- but S is generic


class EvolutionCoalgebra:
    """F-coalgebra (S, alpha) where alpha: S -> F(S).

    Maps directly to the existing pipeline:
        - PROPOSE  -> generates next(s)
        - GATE     -> dharmic constraint on alpha (filters invalid transitions)
        - EVALUATE -> computes fitness(s) and rv(s)
        - ARCHIVE  -> records disc(s)
        - SELECT   -> chooses parent: s' = select(next(s), fitness)

    DEFINITION 4.1: This is the fundamental structure making evolution
    observable: we never inspect internal state directly, only through
    the coalgebra map alpha.

    CONSTRUCTION: F-coalgebra wrapper over existing evolution.py pipeline.
    """

    def __init__(
        self,
        step_fn: StepFunction,
        name: str = "default",
    ) -> None:
        """Initialize the coalgebra with a step function.

        Args:
            step_fn: The coalgebra map alpha: S -> EvolutionObservation.
                Wraps one full cycle of the Darwin Engine pipeline.
            name: Human-readable name for this coalgebra configuration.
        """
        self._step_fn = step_fn
        self.name = name

    def step(self, state: Any) -> EvolutionObservation:
        """One coalgebraic step: alpha(s) = (next(s), fitness(s), rv(s), disc(s)).

        DEFINITION: This IS the coalgebra map. Everything observable about
        the evolution at state s is captured in the returned observation.

        Args:
            state: Current system state S.

        Returns:
            EvolutionObservation capturing all observable outputs.
        """
        return self._step_fn(state)

    def trajectory(
        self,
        initial: Any,
        n: int,
    ) -> list[EvolutionObservation]:
        """Coinductively generate n steps from initial state.

        THEOREM (Lambek): The final coalgebra is the set of all infinite
        streams. This finite prefix approximates the unique coalgebra
        morphism !: (S, alpha) -> Z.

        Args:
            initial: Starting state.
            n: Number of evolution steps to generate.

        Returns:
            List of n EvolutionObservations forming a trajectory prefix.
        """
        observations: list[EvolutionObservation] = []
        state = initial
        for i in range(n):
            obs = self.step(state)
            obs.step_index = i
            observations.append(obs)
            state = obs.next_state
        return observations

    def trajectory_stream(
        self,
        initial: Any,
        max_steps: int = 1000,
    ) -> Iterator[EvolutionObservation]:
        """Lazy trajectory generation via Python iterator.

        Coinductive: generates observations on demand without
        materializing the full trajectory.

        Args:
            initial: Starting state.
            max_steps: Safety bound to prevent infinite generation.

        Yields:
            EvolutionObservation at each step.
        """
        state = initial
        for i in range(max_steps):
            obs = self.step(state)
            obs.step_index = i
            yield obs
            state = obs.next_state


# ── Evolution Trajectory: Final Coalgebra Approximation ──────────────────

@dataclass
class EvolutionTrajectory:
    """Finite prefix of the final F-coalgebra Z ~= (Fitness x RV x Disc)^omega.

    The unique coalgebra morphism !: (S, alpha) -> Z sends each initial
    state to its complete evolution trajectory. We store a finite prefix.

    THEOREM (Lambek): Z ~= F(Z) -- the final coalgebra is a fixed point.

    CONSTRUCTION: Trajectory data structure for analysis and bisimulation.
    """

    observations: list[EvolutionObservation] = field(default_factory=list)
    """The observed trajectory prefix."""

    @property
    def head(self) -> Optional[EvolutionObservation]:
        """Current (latest) observation."""
        return self.observations[-1] if self.observations else None

    @property
    def tail(self) -> EvolutionTrajectory:
        """Rest of trajectory (all but last). Coinductive destructor."""
        return EvolutionTrajectory(observations=self.observations[:-1])

    @property
    def length(self) -> int:
        """Number of observations in this trajectory prefix."""
        return len(self.observations)

    @property
    def fitness_series(self) -> list[float]:
        """Extract fitness values across the trajectory."""
        return [obs.fitness for obs in self.observations]

    @property
    def rv_series(self) -> list[float]:
        """Extract R_V values across the trajectory."""
        return [obs.rv for obs in self.observations]

    @property
    def is_fitness_improving(self) -> bool:
        """Check if fitness is monotonically non-decreasing."""
        series = self.fitness_series
        return all(a <= b for a, b in zip(series, series[1:]))

    @property
    def is_rv_contracting(self) -> bool:
        """Check if R_V is monotonically non-increasing (converging)."""
        series = self.rv_series
        return all(a >= b for a, b in zip(series, series[1:]))

    def fitness_regression_bounded(self, max_drop: float = 0.1) -> bool:
        """Check that fitness never regresses by more than max_drop.

        PROPOSITION: Bounded regression ensures the coalgebra map alpha
        is "well-behaved" -- no catastrophic fitness loss.

        Args:
            max_drop: Maximum allowed fitness decrease between steps.

        Returns:
            True if no step-to-step fitness drop exceeds max_drop.
        """
        series = self.fitness_series
        return all(
            a - b <= max_drop
            for a, b in zip(series, series[1:])
        )

    @classmethod
    def from_coalgebra(
        cls,
        coalgebra: EvolutionCoalgebra,
        initial: Any,
        n: int,
    ) -> EvolutionTrajectory:
        """Generate a trajectory from a coalgebra.

        Args:
            coalgebra: The F-coalgebra to unfold.
            initial: Starting state.
            n: Number of steps.

        Returns:
            EvolutionTrajectory with n observations.
        """
        return cls(observations=coalgebra.trajectory(initial, n))


# ── Bisimulation ─────────────────────────────────────────────────────────

def observation_close(
    obs1: EvolutionObservation,
    obs2: EvolutionObservation,
    fitness_tol: float = 1e-6,
    rv_tol: float = 1e-6,
) -> bool:
    """Check if two observations are equivalent (up to tolerance).

    DEFINITION: Two observations are equivalent if they agree on all
    observable components: fitness, rv, and discoveries.

    Args:
        obs1, obs2: Observations to compare.
        fitness_tol: Tolerance for fitness comparison.
        rv_tol: Tolerance for R_V comparison.

    Returns:
        True if observations are equivalent.
    """
    return (
        abs(obs1.fitness - obs2.fitness) < fitness_tol
        and abs(obs1.rv - obs2.rv) < rv_tol
        and obs1.discoveries == obs2.discoveries
    )


def bisimilar(
    sys1: EvolutionCoalgebra,
    sys2: EvolutionCoalgebra,
    initial1: Any,
    initial2: Any,
    depth: int = 100,
    fitness_tol: float = 1e-6,
    rv_tol: float = 1e-6,
) -> bool:
    """Test bisimulation: two systems produce identical observation streams.

    PROPOSITION 4.5 (Bisimulation): Two F-coalgebras are bisimilar iff
    there exists a bisimulation relation R such that (s1, s2) in R implies
    F(R)(alpha1(s1), alpha2(s2)).

    In practice: we check that the first `depth` observations match.
    This is an approximation of the coinductive bisimulation.

    Args:
        sys1, sys2: Evolution coalgebras to compare.
        initial1, initial2: Starting states for each system.
        depth: Number of steps to compare.
        fitness_tol: Tolerance for fitness comparison.
        rv_tol: Tolerance for R_V comparison.

    Returns:
        True if the first `depth` observations are pairwise equivalent.
    """
    traj1 = sys1.trajectory(initial1, depth)
    traj2 = sys2.trajectory(initial2, depth)
    return all(
        observation_close(o1, o2, fitness_tol, rv_tol)
        for o1, o2 in zip(traj1, traj2)
    )


# ── Distributive Law: TF => FT ──────────────────────────────────────────

class DistributiveLaw:
    """lambda: TF => FT -- compatibility between self-observation monad T
    and evolution functor F.

    When this exists, we can lift the coalgebra to the Eilenberg-Moore
    category of T, getting "self-observed evolution steps."

    A lambda-bialgebra is a state that is SIMULTANEOUSLY:
    - A T-algebra (fully self-observed, L5 state)
    - An F-coalgebra (capable of evolution)

    This means the system can evolve WHILE maintaining stable self-observation.

    CONSTRUCTION 4.7: Distributive law connecting monad and coalgebra.

    Axioms (must satisfy for well-definedness):
    - Unit compatibility: lambda . eta_F = F(eta)
    - Multiplication compatibility: lambda . mu_F = F(mu) . lambda_T . T(lambda)
    """

    @staticmethod
    def distribute(
        observed_obs: ObservedState[EvolutionObservation],
    ) -> EvolutionObservation:
        """lambda: T(F(S)) -> F(T(S)) -- swap monad and functor layers.

        Takes a self-observed evolution observation and produces an
        evolution observation of a self-observed state.

        This is the core operation: it says "observing an evolution step"
        is equivalent to "evolving under self-observation."

        Args:
            observed_obs: T(F(S)) -- an observation wrapped in self-observation.

        Returns:
            F(T(S)) -- an evolution observation whose next_state is self-observed.
        """
        inner: EvolutionObservation = observed_obs.state
        # Wrap the next_state in self-observation metadata
        observed_next = ObservedState(
            state=inner.next_state,
            rv_measurement=observed_obs.rv_measurement,
            pr_early=observed_obs.pr_early,
            pr_late=observed_obs.pr_late,
            observation_depth=observed_obs.observation_depth,
            introspection=dict(observed_obs.introspection),
            timestamp=observed_obs.timestamp,
        )
        return EvolutionObservation(
            next_state=observed_next,
            fitness=inner.fitness,
            rv=inner.rv,
            discoveries=list(inner.discoveries),
            timestamp=inner.timestamp,
            gate_decision=inner.gate_decision,
            step_index=inner.step_index,
        )

    @classmethod
    def verify_unit_compatibility(
        cls,
        state: Any,
        step_fn: StepFunction,
    ) -> bool:
        """Verify: lambda . eta_F = F(eta).

        Left side: Apply eta to F(S), then distribute.
        Right side: Apply F to eta(S) directly.

        Both should produce F(T(S)) with the same structure.

        Args:
            state: A bare state S.
            step_fn: The coalgebra map alpha: S -> F(S).

        Returns:
            True if unit compatibility holds.
        """
        # Left: eta(F(state)) then distribute
        obs = step_fn(state)
        observed_obs = SelfObservationMonad.unit(obs)
        left = cls.distribute(observed_obs)

        # Right: F(eta(state)) -- apply step to eta(state)
        # But F(eta) means: apply eta to the result's next_state
        # F(eta)(obs) = obs with next_state = eta(obs.next_state)
        right = EvolutionObservation(
            next_state=SelfObservationMonad.unit(obs.next_state),
            fitness=obs.fitness,
            rv=obs.rv,
            discoveries=list(obs.discoveries),
            timestamp=obs.timestamp,
            gate_decision=obs.gate_decision,
            step_index=obs.step_index,
        )

        # Check: left.fitness == right.fitness, left.rv == right.rv
        # and left.next_state is an ObservedState wrapping the same state
        return (
            abs(left.fitness - right.fitness) < 1e-9
            and abs(left.rv - right.rv) < 1e-9
            and left.discoveries == right.discoveries
            and isinstance(left.next_state, ObservedState)
            and isinstance(right.next_state, ObservedState)
            and left.next_state.state is right.next_state.state
        )

    @classmethod
    def lift(
        cls,
        coalgebra: EvolutionCoalgebra,
    ) -> EvolutionCoalgebra:
        """Lift evolution to include self-observation at every step.

        Creates a new coalgebra where each step automatically
        wraps the output in self-observation via the distributive law.

        The lifted coalgebra operates in the Eilenberg-Moore category
        of T: its states are T-algebras (self-observed states).

        Args:
            coalgebra: The base F-coalgebra to lift.

        Returns:
            A new EvolutionCoalgebra operating on self-observed states.
        """
        base_step = coalgebra._step_fn

        def lifted_step(state: Any) -> EvolutionObservation:
            # If state is already observed, extract inner state
            if isinstance(state, ObservedState):
                bare = state.state
            else:
                bare = state

            # Run base evolution step
            obs = base_step(bare)

            # Wrap in self-observation
            observed_obs = SelfObservationMonad.unit(obs)

            # Distribute: T(F(S)) -> F(T(S))
            return cls.distribute(observed_obs)

        return EvolutionCoalgebra(
            step_fn=lifted_step,
            name=f"{coalgebra.name}_lifted",
        )


# ── Factory: CycleResult → EvolutionObservation ──────────────────────────

def build_evolution_observation(
    result: Any,
    archive_entries: Any = (),
    proposals: Any = (),
) -> EvolutionObservation:
    """Convert a CycleResult + archive entries + proposals into an observation.

    Used by DSEIntegrator to bridge the evolution pipeline output into the
    coalgebraic observation stream.

    Args:
        result: A CycleResult from DarwinEngine.run_cycle().
        archive_entries: Sequence of ArchiveEntry from the cycle.
        proposals: Sequence of Proposal from the cycle.

    Returns:
        EvolutionObservation capturing the cycle's observable outputs.
    """
    discoveries = list(getattr(result, "lessons_learned", []))
    # Include archive entry descriptions as discoveries
    for entry in archive_entries or ():
        desc = getattr(entry, "description", None)
        if desc and desc not in discoveries:
            discoveries.append(desc)
    # Include proposal descriptions as discoveries
    for p in proposals or ():
        desc = getattr(p, "description", None)
        if desc and desc not in discoveries:
            discoveries.append(desc)

    best_fitness = float(getattr(result, "best_fitness", 0.0))
    proposals_archived = int(getattr(result, "proposals_archived", 0))
    # Proxy R_V from archived count: more archived → stronger contraction
    rv_proxy = 1.0 - min(proposals_archived, 5) * 0.1

    gate_decisions = []
    for p in proposals or ():
        gd = getattr(p, "gate_decision", None)
        if gd:
            gate_decisions.append(str(gd))

    return EvolutionObservation(
        next_state=result,
        fitness=best_fitness,
        rv=rv_proxy,
        discoveries=discoveries,
        gate_decision=gate_decisions[0] if gate_decisions else None,
    )
