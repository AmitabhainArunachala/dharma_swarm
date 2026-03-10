"""Darwin Engine -- self-improvement orchestration loop.

Coordinates the full evolution cycle: propose mutations, gate-check them,
evaluate fitness, archive results, and select parents for the next generation.

Pipeline:
    PROPOSE -> GATE CHECK -> WRITE CODE -> TEST -> EVALUATE FITNESS -> ARCHIVE -> SELECT NEXT PARENT
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
import logging
import re
import shutil
from tempfile import TemporaryDirectory
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.archive import (
    ArchiveEntry,
    EvolutionArchive,
    FitnessScore,
    normalize_fitness_weights,
)
from dharma_swarm.convergence import ConvergenceConfig, ConvergenceDetector
from dharma_swarm.diff_applier import DiffApplier
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span
from dharma_swarm.landscape import FitnessLandscapeMapper, LandscapeProbe
from dharma_swarm.models import GateDecision, GateResult, SandboxResult, _new_id, _utc_now
from dharma_swarm.probe_targets import ProbeTargetRegistry, ResolvedProbeTarget
from dharma_swarm.router_retrospective import (
    DriftGuardDecision,
    DriftGuardThresholds,
    RouteOutcomeRecord,
    RouteRetrospectiveArtifact,
    build_route_policy_archive_entry,
    build_route_retrospective,
    evaluate_router_drift,
)
from dharma_swarm.selector import select_parent
from dharma_swarm.telos_gates import check_with_reflective_reroute
from dharma_swarm.traces import TraceEntry, TraceStore
from dharma_swarm.ucb_selector import UCBConfig, UCBParentSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvolutionStatus(str, Enum):
    """Lifecycle status of an evolution proposal."""

    PENDING = "pending"
    REFLECTING = "reflecting"
    GATED = "gated"
    WRITING = "writing"
    TESTING = "testing"
    EVALUATED = "evaluated"
    ARCHIVED = "archived"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Proposal(BaseModel):
    """A proposed code change to be evaluated by the Darwin Engine."""

    id: str = Field(default_factory=_new_id)
    component: str
    change_type: str  # "mutation", "crossover", "ablation"
    description: str
    parent_id: Optional[str] = None
    spec_ref: str | None = None
    requirement_refs: list[str] = Field(default_factory=list)
    think_notes: str = ""
    diff: str = ""
    status: EvolutionStatus = EvolutionStatus.PENDING
    predicted_fitness: float = 0.0
    actual_fitness: Optional[FitnessScore] = None
    gate_decision: Optional[str] = None
    gate_reason: Optional[str] = None
    reflection_attempts: int = 0
    reflection_suggestions: list[str] = Field(default_factory=list)

    @field_validator('component')
    @classmethod
    def validate_component_path(cls, v: str) -> str:
        """Ensure component is a valid filesystem path."""
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            if char in v:
                raise ValueError(f"Component contains invalid filesystem character '{char}'")
        return v


class CycleResult(BaseModel):
    """Summary of a single evolution cycle run."""

    cycle_id: str = Field(default_factory=_new_id)
    plan_id: str = ""
    proposals_submitted: int = 0
    proposals_gated: int = 0
    proposals_tested: int = 0
    proposals_archived: int = 0
    circuit_breakers_tripped: int = 0
    strategy_pivots: int = 0
    best_fitness: float = 0.0
    exploration_ratio: float = 0.0
    convergence_restart_triggered: bool = False
    restart_cycles_remaining: int = 0
    mutation_rate_applied: float = 0.0
    landscape_basin: str | None = None
    adaptive_strategy: str | None = None
    duration_seconds: float = 0.0
    reflection: str = ""
    lessons_learned: list[str] = Field(default_factory=list)


class EvolutionPlan(BaseModel):
    """Planner output consumed by execution loops."""

    id: str = Field(default_factory=_new_id)
    planner_agent: str = "darwin_planner"
    summary: str = ""
    ordered_proposal_ids: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Darwin Engine
# ---------------------------------------------------------------------------


class DarwinEngine:
    """Orchestrates the full evolution cycle.

    Creates proposals, runs them through dharmic safety gates, evaluates
    fitness, archives results, and selects parents for the next generation.

    Args:
        archive_path: Path to the JSONL evolution archive. Defaults to
            ``~/.dharma/evolution/archive.jsonl``.
        traces_path: Base path for the trace store. Defaults to
            ``~/.dharma/traces``.
        predictor_path: Path to the fitness predictor history file.
            Defaults to ``~/.dharma/evolution/predictor_data.jsonl``.
        custom_fitness_weights: Optional custom weighting for fitness scoring.
            Partial overrides are merged onto canonical defaults.
    """

    def __init__(
        self,
        archive_path: Path | None = None,
        traces_path: Path | None = None,
        predictor_path: Path | None = None,
        circuit_breaker_limit: int = 3,
        max_reflection_reroutes: int = 2,
        custom_fitness_weights: dict[str, float] | None = None,
        use_ucb: bool = False,
        ucb_config: UCBConfig | None = None,
        convergence_config: ConvergenceConfig | None = None,
        mutation_rate: float = 0.1,
        landscape_probe_interval: int = 5,
        landscape_probe_workspace: Path | None = None,
        landscape_probe_test_command: str = "python3 -m pytest tests/ -q --tb=short",
        landscape_probe_timeout: float = 60.0,
        probe_targets: ProbeTargetRegistry | list[dict[str, Any]] | None = None,
        meta_evolution_interval: int = 0,
        meta_archive_path: Path | None = None,
        meta_poor_fitness_threshold: float = 0.5,
        meta_auto_apply: bool = True,
        router_drift_thresholds: DriftGuardThresholds | None = None,
    ) -> None:
        self.archive = EvolutionArchive(path=archive_path)
        self.traces = TraceStore(base_path=traces_path)
        self.predictor = FitnessPredictor(history_path=predictor_path)
        self._circuit_breaker_limit = max(1, int(circuit_breaker_limit))
        self._max_reflection_reroutes = max(0, int(max_reflection_reroutes))
        self._fitness_weights = normalize_fitness_weights(custom_fitness_weights)
        self.use_ucb = bool(use_ucb)
        self.ucb_selector = UCBParentSelector(ucb_config)
        self.convergence_detector = ConvergenceDetector(convergence_config)
        self._base_mutation_rate = max(0.01, float(mutation_rate))
        self._map_elites_n_bins = self.archive.grid.n_bins
        self._landscape_probe_interval = max(1, int(landscape_probe_interval))
        self._landscape_probe_workspace = (
            Path(landscape_probe_workspace).resolve()
            if landscape_probe_workspace is not None
            else None
        )
        self._landscape_probe_test_command = landscape_probe_test_command
        self._landscape_probe_timeout = float(landscape_probe_timeout)
        self.probe_target_registry = ProbeTargetRegistry.from_configs(probe_targets)
        self._meta_evolution_interval = max(0, int(meta_evolution_interval))
        self.last_meta_evolution_result: Any | None = None
        self._meta_evolution_engine: Any | None = None
        if self._meta_evolution_interval > 0:
            from dharma_swarm.meta_evolution import MetaEvolutionEngine

            self._meta_evolution_engine = MetaEvolutionEngine(
                self,
                meta_archive_path=meta_archive_path,
                n_object_cycles_per_meta=self._meta_evolution_interval,
                poor_meta_fitness_threshold=meta_poor_fitness_threshold,
                auto_apply=meta_auto_apply,
            )
        self._router_drift_thresholds = router_drift_thresholds or DriftGuardThresholds()
        self._completed_cycles = 0
        self._adaptive_strategy = "explore"
        self.last_landscape_probe: LandscapeProbe | None = None
        self.landscape_mapper = FitnessLandscapeMapper(self)
        self._initialized: bool = False

    def get_fitness_weights(self) -> dict[str, float]:
        """Return the active normalized fitness weights."""
        return dict(self._fitness_weights)

    def set_fitness_weights(
        self,
        weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Set active fitness weights, falling back to canonical defaults."""
        self._fitness_weights = normalize_fitness_weights(weights)
        return self.get_fitness_weights()

    def score_fitness(self, fitness: FitnessScore | None) -> float:
        """Score a fitness vector using the engine's active weights."""
        if fitness is None:
            return 0.0
        return fitness.weighted(weights=self._fitness_weights)

    def get_meta_parameter_state(self) -> dict[str, Any]:
        """Export the engine knobs used by meta-evolution."""
        return {
            "fitness_weights": self.get_fitness_weights(),
            "mutation_rate": self._base_mutation_rate,
            "exploration_coeff": self.ucb_selector.state.exploration_coeff,
            "circuit_breaker_limit": self._circuit_breaker_limit,
            "map_elites_n_bins": self._map_elites_n_bins,
        }

    def apply_meta_parameters(self, meta_params: Any) -> dict[str, Any]:
        """Apply a meta-parameter bundle onto the live engine."""
        self.set_fitness_weights(getattr(meta_params, "fitness_weights", None))
        self._base_mutation_rate = max(
            0.01,
            float(getattr(meta_params, "mutation_rate", self._base_mutation_rate)),
        )
        self._circuit_breaker_limit = max(
            1,
            int(
                getattr(
                    meta_params,
                    "circuit_breaker_limit",
                    self._circuit_breaker_limit,
                )
            ),
        )
        self._map_elites_n_bins = max(
            3,
            int(getattr(meta_params, "map_elites_n_bins", self._map_elites_n_bins)),
        )
        self.archive.reconfigure_grid(self._map_elites_n_bins)
        self.ucb_selector.set_exploration_coeff(
            float(
                getattr(
                    meta_params,
                    "exploration_coeff",
                    self.ucb_selector.state.exploration_coeff,
                )
            )
        )
        self._map_elites_n_bins = self.archive.grid.n_bins
        return self.get_meta_parameter_state()

    def get_active_mutation_rate(self) -> float:
        """Return mutation rate after convergence restart adjustments."""
        return self.convergence_detector.get_restart_mutation_rate(
            self._base_mutation_rate
        )

    def register_probe_target(
        self,
        component_pattern: str,
        *,
        workspace: Path | str | None = None,
        test_command: str | None = None,
        timeout: float | None = None,
        priority: int = 0,
    ) -> ResolvedProbeTarget:
        """Register a component-aware workspace probe target."""
        target = self.probe_target_registry.register(
            component_pattern,
            workspace=workspace,
            test_command=test_command,
            timeout=timeout,
            priority=priority,
        )
        return ResolvedProbeTarget(
            component=component_pattern,
            workspace=target.workspace,
            test_command=target.test_command,
            timeout=target.timeout,
            matched_pattern=target.component_pattern,
            priority=target.priority,
        )

    def resolve_probe_target(self, component: str) -> ResolvedProbeTarget:
        """Resolve probe settings for a component with engine defaults overlaid."""
        resolved = self.probe_target_registry.resolve(component)
        return ResolvedProbeTarget(
            component=component,
            workspace=(
                resolved.workspace
                if resolved and resolved.workspace is not None
                else self._landscape_probe_workspace
            ),
            test_command=(
                resolved.test_command
                if resolved and resolved.test_command is not None
                else self._landscape_probe_test_command
            ),
            timeout=(
                resolved.timeout
                if resolved and resolved.timeout is not None
                else self._landscape_probe_timeout
            ),
            matched_pattern=resolved.matched_pattern if resolved else None,
            priority=resolved.priority if resolved else 0,
        )

    def get_mutation_budget_lines(self) -> int:
        """Translate mutation rate into an LLM diff-size budget."""
        return max(12, min(160, round(12 + (self.get_active_mutation_rate() * 160))))

    def _current_adaptive_strategy(self) -> str:
        """Return the current landscape-guided mutation mode."""
        if self.convergence_detector.is_restart_active():
            return "restart"
        return self._adaptive_strategy

    def _build_propose_system(self) -> str:
        """Build the proposal-generation system prompt from live engine state."""
        strategy = self._current_adaptive_strategy()
        max_lines = self.get_mutation_budget_lines()
        strategy_guidance = {
            "exploit": "Bias toward small, local improvements near the current implementation.",
            "explore": "Allow broader alternatives while staying coherent and file-local.",
            "restart": "Bias toward bolder mutations that may escape a local optimum, while remaining reversible.",
            "backtrack": "Favor simplifying or risk-reducing changes over ambitious rewrites.",
        }
        return (
            "You are an expert Python engineer improving a codebase. "
            "Given a source file, propose ONE focused improvement. "
            "Respond in EXACTLY this format (no markdown fencing around the whole response):\n\n"
            "COMPONENT: <module name>\n"
            "CHANGE_TYPE: mutation\n"
            "DESCRIPTION: <one-line summary>\n"
            "THINK: <why this matters, 1-2 sentences>\n"
            "DIFF:\n"
            "```diff\n"
            "<unified diff>\n"
            "```\n\n"
            "Rules:\n"
            f"- Keep changes under {max_lines} changed lines\n"
            f"- Current mutation mode: {strategy}. {strategy_guidance.get(strategy, strategy_guidance['explore'])}\n"
            "- Only fix real issues: bugs, missing error handling, performance, clarity\n"
            "- Do NOT add docstrings, type hints, or comments to code you didn't change\n"
            "- Do NOT refactor working code for style\n"
            "- The diff must be a valid unified diff (--- a/file, +++ b/file, @@ hunks)\n"
            "- If the code is already good, say DESCRIPTION: no-op and leave DIFF empty"
        )

    async def _update_cycle_dynamics(self, result: CycleResult) -> None:
        """Update convergence/UCB state after a completed cycle."""
        result.exploration_ratio = (
            self.ucb_selector.get_exploration_ratio() if self.use_ucb else 0.0
        )
        triggered = self.convergence_detector.update(result.best_fitness)
        result.convergence_restart_triggered = triggered
        result.restart_cycles_remaining = (
            self.convergence_detector.state.restart_cycles_remaining
        )
        if triggered:
            result.strategy_pivots += 1
            logger.info(
                "Convergence detected: variance=%.4f improvement=%.4f restart=%d",
                self.convergence_detector.state.last_variance,
                self.convergence_detector.state.last_improvement,
                self.convergence_detector.state.restart_cycles_remaining,
            )
        await self._refresh_landscape_guidance(result)
        result.mutation_rate_applied = self.get_active_mutation_rate()

    async def _maybe_run_meta_evolution(self, result: CycleResult) -> None:
        """Observe completed cycles and periodically adapt engine hyperparameters."""
        if self._meta_evolution_engine is None:
            return

        meta_result = self._meta_evolution_engine.observe_cycle_result(result)
        if meta_result is None:
            return

        self.last_meta_evolution_result = meta_result
        if meta_result.applied_parameters:
            result.strategy_pivots += 1

        if self._initialized:
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_meta_engine",
                    action="meta_evolution",
                    state="applied" if meta_result.applied_parameters else "observed",
                    metadata={
                        "meta_result_id": meta_result.id,
                        "trigger": meta_result.trigger,
                        "meta_fitness": meta_result.meta_fitness,
                        "avg_fitness_trend": meta_result.avg_fitness_trend,
                        "improvement_over_baseline": meta_result.improvement_over_baseline,
                        "evolved_parameters": meta_result.evolved_parameters,
                        "applied_parameters": meta_result.applied_parameters,
                        "source_cycle_ids": meta_result.source_cycle_ids,
                        "meta_parameters": meta_result.meta_parameters.model_dump(),
                    },
                )
            )

    async def _refresh_landscape_guidance(self, result: CycleResult) -> None:
        """Probe the archive landscape periodically and adjust mutation strategy."""
        self._completed_cycles += 1
        should_probe = (
            self._completed_cycles % self._landscape_probe_interval == 0
            or result.convergence_restart_triggered
        )
        if not should_probe:
            return

        parents = await self.archive.get_best(n=1, weights=self._fitness_weights)
        if not parents:
            return

        target = self.resolve_probe_target(parents[0].component or "")
        probe = await self.landscape_mapper.probe_landscape(
            parents[0],
            weights=self._fitness_weights,
            workspace=target.workspace,
            test_command=target.test_command or self._landscape_probe_test_command,
            timeout=target.timeout or self._landscape_probe_timeout,
        )
        self.last_landscape_probe = probe
        strategy = self.landscape_mapper.get_adaptive_strategy(probe.basin_type)
        self._adaptive_strategy = strategy
        result.landscape_basin = probe.basin_type.value
        result.adaptive_strategy = strategy

        if self._initialized:
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="landscape_probe",
                    state=probe.basin_type.value,
                    metadata={
                        "parent_id": probe.parent_id,
                        "component": probe.parent_component,
                        "matched_pattern": target.matched_pattern,
                        "workspace": str(target.workspace) if target.workspace else None,
                        "test_command": target.test_command,
                        "timeout": target.timeout,
                        "gradient": probe.gradient,
                        "variance": probe.variance,
                        "neighbor_fitness": probe.neighbor_fitness,
                    },
                )
            )

        if strategy == "exploit":
            self._base_mutation_rate = max(0.01, self._base_mutation_rate * 0.85)
        elif strategy == "explore":
            self._base_mutation_rate = min(1.0, self._base_mutation_rate * 1.2)
        elif strategy == "restart":
            self._base_mutation_rate = min(1.0, self._base_mutation_rate * 1.5)
            if self.convergence_detector.state.restart_cycles_remaining == 0:
                self.convergence_detector.state.restart_cycles_remaining = (
                    self.convergence_detector.config.restart_duration
                )
                result.convergence_restart_triggered = True
                result.strategy_pivots += 1
                result.restart_cycles_remaining = (
                    self.convergence_detector.state.restart_cycles_remaining
                )
        elif strategy == "backtrack":
            self._base_mutation_rate = max(0.01, self._base_mutation_rate * 0.7)

    async def evaluate_probe_proposal(
        self,
        proposal: Proposal,
        *,
        workspace: Path,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> Proposal:
        """Evaluate a speculative probe against an isolated workspace snapshot."""
        candidate = proposal.model_copy(deep=True)
        await self.gate_check(candidate)
        if candidate.status == EvolutionStatus.REJECTED:
            await self.evaluate(candidate, test_results={"pass_rate": 0.0})
            return candidate

        workspace_path = Path(workspace).resolve()
        with TemporaryDirectory(prefix="dharma_landscape_probe_") as tmpdir:
            snapshot_root = Path(tmpdir) / "workspace"
            shutil.copytree(
                workspace_path,
                snapshot_root,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                ),
            )
            candidate, test_results = await self.apply_diff_and_test(
                candidate,
                test_command=test_command,
                timeout=timeout,
                workspace=snapshot_root,
            )

            code: str | None = None
            target_path = (snapshot_root / candidate.component).resolve()
            try:
                target_path.relative_to(snapshot_root)
            except ValueError:
                target_path = snapshot_root / Path(candidate.component).name
            if target_path.exists() and target_path.is_file():
                code = target_path.read_text(encoding="utf-8")

            await self.evaluate(candidate, test_results=test_results, code=code)
            return candidate

    async def init(self) -> None:
        """Load archive, initialize traces, and load predictor history."""
        await self.archive.load()
        await self.traces.init()
        await self.predictor.load()
        self._initialized = True
        logger.info("DarwinEngine initialized")

    # -- proposal creation ---------------------------------------------------

    async def propose(
        self,
        component: str,
        change_type: str,
        description: str,
        diff: str = "",
        parent_id: str | None = None,
        spec_ref: str | None = None,
        requirement_refs: list[str] | None = None,
        think_notes: str = "",
    ) -> Proposal:
        """Create a new evolution proposal and predict its fitness.

        Args:
            component: The module or file being changed.
            change_type: One of ``"mutation"``, ``"crossover"``, ``"ablation"``.
            description: Human-readable description of the change.
            diff: The code diff (patch text).
            parent_id: Optional archive entry id this proposal evolves from.

        Returns:
            A ``Proposal`` with predicted fitness populated.
        """
        async with jikoku_auto_span(
            category="execute.evolution_propose",
            intent=f"Propose {change_type} for {component}",
            component=component,
            change_type=change_type,
            diff_lines=len(diff.splitlines()) if diff else 0,
        ):
            features = ProposalFeatures(
                component=component,
                change_type=change_type,
                diff_size=len(diff.splitlines()),
            )
            predicted = self.predictor.predict(features)

            proposal = Proposal(
                component=component,
                change_type=change_type,
                description=description,
                diff=diff,
                parent_id=parent_id,
                spec_ref=spec_ref,
                requirement_refs=list(requirement_refs or []),
                think_notes=think_notes,
                predicted_fitness=predicted,
            )

            logger.debug(
                "Proposal %s created: predicted_fitness=%.3f",
                proposal.id,
                predicted,
            )
            return proposal

    async def plan_cycle(self, proposals: list[Proposal]) -> EvolutionPlan:
        """Create an explicit planner artifact before execution."""
        ordered = sorted(proposals, key=lambda p: p.predicted_fitness, reverse=True)
        steps: list[str] = []
        for idx, proposal in enumerate(ordered, start=1):
            trace_ref = proposal.spec_ref or "unlinked"
            steps.append(
                f"{idx}. Execute proposal {proposal.id} "
                f"({proposal.component}, {proposal.change_type}, spec={trace_ref})"
            )

        plan = EvolutionPlan(
            summary=(
                "Planner->Executor split: darwin_planner emits ordered proposal "
                "steps; darwin_executor applies gate->evaluate->archive."
            ),
            ordered_proposal_ids=[p.id for p in ordered],
            steps=steps,
        )
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_planner",
                action="plan_cycle",
                state="planned",
                metadata={
                    "plan_id": plan.id,
                    "proposal_count": len(ordered),
                    "ordered_proposal_ids": plan.ordered_proposal_ids,
                },
            )
        )
        return plan

    @staticmethod
    def _failure_signature(proposal: Proposal) -> str:
        reason = (proposal.gate_reason or "unknown").strip().lower()
        decision = (proposal.gate_decision or "unknown").strip().lower()
        return f"{proposal.component}|{decision}|{reason}"

    async def _trip_circuit_breaker_if_needed(
        self,
        *,
        proposal: Proposal,
        failure_streaks: dict[str, int],
        cycle: CycleResult,
    ) -> None:
        """Track repeated identical failures and enforce strategy pivot."""
        sig = self._failure_signature(proposal)
        failure_streaks[sig] = failure_streaks.get(sig, 0) + 1
        count = failure_streaks[sig]
        if count < self._circuit_breaker_limit:
            return

        cycle.circuit_breakers_tripped += 1
        cycle.strategy_pivots += 1
        proposal.gate_reason = (
            f"Circuit breaker tripped after {count} repeated failures "
            f"for signature={sig}. Strategy pivot required."
        )
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_executor",
                action="circuit_breaker",
                state="pivot_required",
                metadata={
                    "proposal_id": proposal.id,
                    "failure_signature": sig,
                    "repeats": count,
                    "limit": self._circuit_breaker_limit,
                },
            )
        )

    # -- gate checking -------------------------------------------------------

    async def gate_check(self, proposal: Proposal) -> Proposal:
        """Run dharmic safety gates against a proposal.

        Updates the proposal status to ``GATED`` if the gates allow or
        advise review, or ``REJECTED`` if any gate blocks.

        Args:
            proposal: The proposal to gate-check.

        Returns:
            The same ``Proposal`` instance with updated status and gate fields.
        """
        async with jikoku_auto_span(
            category="execute.evolution_gate",
            intent=f"Gate check proposal {proposal.id[:8]}",
            proposal_id=proposal.id,
            component=proposal.component,
        ):
            outcome = check_with_reflective_reroute(
                action=proposal.description,
                content=proposal.diff,
                tool_name="darwin_executor",
                think_phase="before_write",
                reflection=proposal.think_notes or proposal.description,
                max_reroutes=self._max_reflection_reroutes,
                spec_ref=proposal.spec_ref,
                requirement_refs=proposal.requirement_refs,
            )
            result = outcome.result

            proposal.gate_decision = result.decision.value
            proposal.gate_reason = result.reason
            proposal.reflection_attempts = outcome.attempts
            proposal.reflection_suggestions = list(outcome.suggestions)
            if outcome.reflection.strip():
                proposal.think_notes = outcome.reflection

            witness_result = result.gate_results.get("WITNESS")
            if witness_result and witness_result[0] == GateResult.WARN:
                logger.warning(
                    "Proposal %s missing think-point reflection: %s",
                    proposal.id,
                    witness_result[1],
                )
            if outcome.attempts:
                proposal.status = EvolutionStatus.REFLECTING
                logger.info(
                    "Proposal %s reflective reroute attempts=%d",
                    proposal.id,
                    outcome.attempts,
                )
                await self.traces.log_entry(
                    TraceEntry(
                        agent="darwin_engine",
                        action="witness_reroute",
                        state="rerouted",
                        metadata={
                            "proposal_id": proposal.id,
                            "attempts": outcome.attempts,
                            "max_attempts": self._max_reflection_reroutes,
                        },
                    )
                )

            if result.decision == GateDecision.BLOCK:
                proposal.status = EvolutionStatus.REJECTED
                logger.warning(
                    "Proposal %s REJECTED by gates: %s",
                    proposal.id,
                    result.reason,
                )
            else:
                proposal.status = EvolutionStatus.GATED
                logger.info(
                    "Proposal %s passed gates (%s): %s",
                    proposal.id,
                    result.decision.value,
                    result.reason,
                )

            # Log trace for gate check
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="gate_check",
                    state=proposal.status.value,
                    metadata={
                        "proposal_id": proposal.id,
                        "decision": result.decision.value,
                        "reason": result.reason,
                        "spec_ref": proposal.spec_ref,
                        "requirement_refs": proposal.requirement_refs,
                    },
                )
            )

            return proposal

    # -- fitness evaluation --------------------------------------------------

    async def evaluate(
        self,
        proposal: Proposal,
        test_results: dict[str, Any] | None = None,
        code: str | None = None,
        baseline_session_id: str | None = None,
        test_session_id: str | None = None,
    ) -> Proposal:
        """Evaluate the fitness of a gated proposal.

        Builds a ``FitnessScore`` from test results, code elegance,
        gate outcomes, diff efficiency, and JIKOKU performance metrics.

        Args:
            proposal: The proposal to evaluate (should be GATED).
            test_results: Dict with test outcome data; key ``"pass_rate"``
                (float 0-1) is used for correctness.
            code: Optional Python source for elegance scoring.
            baseline_session_id: JIKOKU session before changes (for perf comparison)
            test_session_id: JIKOKU session after changes (for perf comparison)

        Returns:
            The proposal with ``actual_fitness`` populated and status
            set to ``EVALUATED``.
        """
        async with jikoku_auto_span(
            category="execute.evolution_evaluate",
            intent=f"Evaluate fitness for {proposal.id[:8]}",
            proposal_id=proposal.id,
            component=proposal.component,
        ):
            test_results = test_results or {}

            correctness = float(test_results.get("pass_rate", 0.0))

            if code:
                elegance_score = evaluate_elegance(code)
                elegance = elegance_score.overall
            else:
                elegance = 0.5

            # Dharmic alignment from gate outcome
            if proposal.gate_decision == GateDecision.ALLOW.value:
                dharmic_alignment = 0.8
            elif proposal.gate_decision == GateDecision.REVIEW.value:
                dharmic_alignment = 0.5
            else:
                dharmic_alignment = 0.0

            # Efficiency: smaller diffs are more efficient
            diff_lines = len(proposal.diff.splitlines()) if proposal.diff else 0
            efficiency = 1.0 - min(diff_lines / 1000.0, 1.0)

            # Safety: full marks if gate passed (not blocked)
            safety = 1.0 if proposal.status != EvolutionStatus.REJECTED else 0.0

            # JIKOKU performance metrics (NEW)
            from dharma_swarm.jikoku_fitness import (
                evaluate_economic_fitness_from_jikoku,
                evaluate_jikoku_metrics,
            )

            performance, utilization = await evaluate_jikoku_metrics(
                proposal,
                baseline_session_id=baseline_session_id,
                test_session_id=test_session_id,
            )
            economic_value, _ = await evaluate_economic_fitness_from_jikoku(
                baseline_session_id,
                test_session_id,
            )

            # Safety floor: if safety == 0, the entire composite fitness is 0
            # regardless of other scores. This enforces the invariant that
            # rejected proposals cannot accumulate fitness.
            if safety == 0.0:
                fitness = FitnessScore(
                    correctness=0.0,
                    elegance=0.0,
                    dharmic_alignment=0.0,
                    performance=0.0,
                    utilization=0.0,
                    economic_value=0.0,
                    efficiency=0.0,
                    safety=0.0,
                )
            else:
                fitness = FitnessScore(
                    correctness=correctness,
                    elegance=elegance,
                    dharmic_alignment=dharmic_alignment,
                    performance=performance,     # NEW - JIKOKU
                    utilization=utilization,     # NEW - JIKOKU
                    economic_value=economic_value,
                    efficiency=efficiency,
                    safety=safety,
                )

            proposal.actual_fitness = fitness
            proposal.status = EvolutionStatus.EVALUATED

            logger.info(
                "Proposal %s evaluated: weighted=%.3f",
                proposal.id,
                self.score_fitness(fitness),
            )
            return proposal

    # -- archiving -----------------------------------------------------------

    async def archive_result(self, proposal: Proposal) -> str:
        """Store an evaluated proposal in the evolution archive.

        Creates an ``ArchiveEntry`` from the proposal, persists it,
        records the outcome in the fitness predictor, and logs a trace.

        Args:
            proposal: The evaluated proposal to archive.

        Returns:
            The archive entry id.
        """
        async with jikoku_auto_span(
            category="execute.evolution_archive",
            intent=f"Archive proposal {proposal.id[:8]}",
            proposal_id=proposal.id,
            component=proposal.component,
            fitness=self.score_fitness(proposal.actual_fitness),
        ):
            fitness = proposal.actual_fitness or FitnessScore()
            weighted_fitness = self.score_fitness(fitness)

            entry = ArchiveEntry(
                component=proposal.component,
                change_type=proposal.change_type,
                description=proposal.description,
                spec_ref=proposal.spec_ref,
                requirement_refs=list(proposal.requirement_refs),
                diff=proposal.diff,
                parent_id=proposal.parent_id,
                fitness=fitness,
                status="applied",
                gates_passed=(
                    ["ALL"]
                    if proposal.gate_decision != GateDecision.BLOCK.value
                    else []
                ),
                gates_failed=(
                    [proposal.gate_reason or "unknown"]
                    if proposal.gate_decision == GateDecision.BLOCK.value
                    else []
                ),
            )

            entry_id = await self.archive.add_entry(entry)
            proposal.status = EvolutionStatus.ARCHIVED

            # Record outcome in predictor for future predictions
            features = ProposalFeatures(
                component=proposal.component,
                change_type=proposal.change_type,
                diff_size=len(proposal.diff.splitlines()) if proposal.diff else 0,
            )
            await self.predictor.record_outcome(features, weighted_fitness)

            # Log trace
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="archive_result",
                    state="archived",
                metadata={
                    "proposal_id": proposal.id,
                    "entry_id": entry_id,
                    "weighted_fitness": weighted_fitness,
                    "spec_ref": proposal.spec_ref,
                    "requirement_refs": proposal.requirement_refs,
                },
            )
        )

        logger.info(
            "Proposal %s archived as %s (fitness=%.3f)",
            proposal.id,
            entry_id,
            weighted_fitness,
        )
        return entry_id

    # -- full cycle ----------------------------------------------------------

    async def run_cycle(self, proposals: list[Proposal]) -> CycleResult:
        """Execute a full evolution cycle on a batch of proposals.

        For each proposal: gate-check, and if it passes, evaluate and
        archive. Tracks aggregate statistics.

        Args:
            proposals: List of proposals to process.

        Returns:
            A ``CycleResult`` summarising the cycle.
        """
        start = time.monotonic()
        plan = await self.plan_cycle(proposals)
        result = CycleResult(
            proposals_submitted=len(proposals),
            plan_id=plan.id,
        )
        best_fitness = 0.0
        proposal_by_id = {p.id: p for p in proposals}
        failure_streaks: dict[str, int] = defaultdict(int)

        for proposal_id in plan.ordered_proposal_ids:
            proposal = proposal_by_id[proposal_id]
            # Gate check
            await self.gate_check(proposal)
            if proposal.status == EvolutionStatus.REJECTED:
                await self._trip_circuit_breaker_if_needed(
                    proposal=proposal,
                    failure_streaks=failure_streaks,
                    cycle=result,
                )
                continue

            result.proposals_gated += 1

            # Evaluate
            await self.evaluate(proposal)
            result.proposals_tested += 1

            # Archive
            await self.archive_result(proposal)
            result.proposals_archived += 1

            # Track best
            if proposal.actual_fitness:
                weighted = self.score_fitness(proposal.actual_fitness)
                if weighted > best_fitness:
                    best_fitness = weighted

        result.best_fitness = best_fitness
        await self._update_cycle_dynamics(result)
        result.duration_seconds = time.monotonic() - start

        logger.info(
            "Cycle %s complete: %d submitted, %d gated, %d archived, "
            "best_fitness=%.3f, pivots=%d, restart=%s, duration=%.2fs",
            result.cycle_id,
            result.proposals_submitted,
            result.proposals_gated,
            result.proposals_archived,
            result.best_fitness,
            result.strategy_pivots,
            result.convergence_restart_triggered,
            result.duration_seconds,
        )

        # Verbal self-reflection (Reflexion pattern)
        await self.reflect_on_cycle(result, proposals)
        await self._maybe_run_meta_evolution(result)

        return result

    # -- sandbox execution ---------------------------------------------------

    @staticmethod
    def _parse_sandbox_result(sr: SandboxResult) -> dict[str, Any]:
        """Parse pytest-style output from a sandbox result.

        Extracts pass/fail counts from stdout and computes a pass rate.
        Falls back to exit code when no recognisable pytest summary is found.

        Args:
            sr: The :class:`SandboxResult` to parse.

        Returns:
            Dict with ``"pass_rate"`` (float 0-1) and ``"exit_code"`` (int).
        """
        passed = 0
        failed = 0

        # Match patterns like "10 passed", "2 failed", "1 error"
        passed_match = re.search(r"(\d+)\s+passed", sr.stdout)
        failed_match = re.search(r"(\d+)\s+failed", sr.stdout)
        error_match = re.search(r"(\d+)\s+error", sr.stdout)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if error_match:
            failed += int(error_match.group(1))

        total = passed + failed
        if total > 0:
            pass_rate = passed / total
        else:
            # No recognisable test output; use exit code as heuristic
            pass_rate = 1.0 if sr.exit_code == 0 else 0.0

        return {"pass_rate": pass_rate, "exit_code": sr.exit_code}

    async def apply_diff_and_test(
        self,
        proposal: Proposal,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 120.0,
        workspace: Path | None = None,
    ) -> tuple[Proposal, dict[str, Any]]:
        """Apply a proposal's diff to the workspace, run tests, rollback on failure.

        Uses :class:`DiffApplier` to atomically apply the unified diff,
        run the test suite, and rollback automatically if tests fail.

        Args:
            proposal: The gated proposal whose ``diff`` to apply.
            test_command: Shell command to validate the change.
            timeout: Maximum seconds for the test command.
            workspace: Root directory for resolving diff paths.

        Returns:
            Tuple of ``(proposal, test_results_dict)`` where test_results_dict
            contains ``"pass_rate"`` (float 0-1).
        """
        if not proposal.diff.strip():
            return (proposal, {"pass_rate": 1.0, "skipped": True})

        proposal.status = EvolutionStatus.WRITING
        applier = DiffApplier(workspace=workspace)

        proposal.status = EvolutionStatus.TESTING
        result = await applier.apply_and_test(
            diff_text=proposal.diff,
            test_command=test_command,
            timeout=timeout,
        )

        # Log trace
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="apply_diff_and_test",
                state="pass" if result.tests_passed else "fail",
                metadata={
                    "proposal_id": proposal.id,
                    "applied": result.applied,
                    "tests_passed": result.tests_passed,
                    "rolled_back": result.rolled_back,
                    "files_changed": result.files_changed,
                    "error": result.error,
                },
            )
        )

        # Parse pass_rate from test output (reuse existing parser heuristic)
        if result.tests_passed:
            pass_rate = 1.0
        elif result.tests_output:
            sr = SandboxResult(
                stdout=result.tests_output, stderr="", exit_code=1
            )
            parsed = self._parse_sandbox_result(sr)
            pass_rate = parsed["pass_rate"]
        else:
            pass_rate = 0.0

        return (proposal, {"pass_rate": pass_rate, "rolled_back": result.rolled_back})

    async def apply_in_sandbox(
        self,
        proposal: Proposal,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> tuple[Proposal, SandboxResult]:
        """Run a test command in a sandbox and record the result.

        Sets the proposal through WRITING -> TESTING status transitions,
        executes the command in a :class:`LocalSandbox`, and logs a trace.

        Args:
            proposal: The gated proposal to test.
            test_command: Shell command to run inside the sandbox.
            timeout: Maximum seconds before the command is killed.

        Returns:
            A tuple of ``(proposal, SandboxResult)``.
        """
        from dharma_swarm.sandbox import LocalSandbox

        proposal.status = EvolutionStatus.WRITING
        sandbox = LocalSandbox()
        try:
            proposal.status = EvolutionStatus.TESTING
            result = await sandbox.execute(test_command, timeout=timeout)

            # Log trace
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_engine",
                    action="sandbox_test",
                    state=proposal.status.value,
                    metadata={
                        "proposal_id": proposal.id,
                        "exit_code": result.exit_code,
                        "stdout_preview": result.stdout[:200],
                    },
                )
            )
        finally:
            await sandbox.cleanup()

        return (proposal, result)

    async def run_cycle_with_sandbox(
        self,
        proposals: list[Proposal],
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> CycleResult:
        """Execute a full evolution cycle with sandbox testing.

        Like :meth:`run_cycle`, but after gate-check each proposal is tested
        in a :class:`LocalSandbox` and the parsed test results are fed into
        the fitness evaluator.

        Args:
            proposals: List of proposals to process.
            test_command: Shell command for sandbox testing.
            timeout: Maximum seconds per sandbox execution.

        Returns:
            A :class:`CycleResult` summarising the cycle.
        """
        start = time.monotonic()
        plan = await self.plan_cycle(proposals)
        result = CycleResult(
            proposals_submitted=len(proposals),
            plan_id=plan.id,
        )
        best_fitness = 0.0
        proposal_by_id = {p.id: p for p in proposals}
        failure_streaks: dict[str, int] = defaultdict(int)

        for proposal_id in plan.ordered_proposal_ids:
            proposal = proposal_by_id[proposal_id]
            # Gate check
            await self.gate_check(proposal)
            if proposal.status == EvolutionStatus.REJECTED:
                await self._trip_circuit_breaker_if_needed(
                    proposal=proposal,
                    failure_streaks=failure_streaks,
                    cycle=result,
                )
                continue

            result.proposals_gated += 1

            # Apply diff (if present) then sandbox test
            if proposal.diff.strip():
                proposal, test_results = await self.apply_diff_and_test(
                    proposal, test_command=test_command, timeout=timeout
                )
                if test_results.get("rolled_back"):
                    logger.warning(
                        "Proposal %s diff rolled back after test failure",
                        proposal.id,
                    )
            else:
                proposal, sr = await self.apply_in_sandbox(
                    proposal, test_command=test_command, timeout=timeout
                )
                test_results = self._parse_sandbox_result(sr)

            # Evaluate with test results
            await self.evaluate(proposal, test_results=test_results)
            result.proposals_tested += 1

            # Archive
            await self.archive_result(proposal)
            result.proposals_archived += 1

            # Track best
            if proposal.actual_fitness:
                weighted = self.score_fitness(proposal.actual_fitness)
                if weighted > best_fitness:
                    best_fitness = weighted

        result.best_fitness = best_fitness
        await self._update_cycle_dynamics(result)
        result.duration_seconds = time.monotonic() - start

        logger.info(
            "Sandbox cycle %s complete: %d submitted, %d gated, %d archived, "
            "best_fitness=%.3f, pivots=%d, restart=%s, duration=%.2fs",
            result.cycle_id,
            result.proposals_submitted,
            result.proposals_gated,
            result.proposals_archived,
            result.best_fitness,
            result.strategy_pivots,
            result.convergence_restart_triggered,
            result.duration_seconds,
        )

        # Verbal self-reflection (Reflexion pattern)
        await self.reflect_on_cycle(result, proposals)
        await self._maybe_run_meta_evolution(result)

        return result

    # -- parent selection ----------------------------------------------------

    async def select_next_parent(
        self, strategy: str = "tournament", **kwargs: Any
    ) -> ArchiveEntry | None:
        """Select a parent entry for the next evolution round.

        Delegates to the selector module's ``select_parent`` dispatch.

        Args:
            strategy: Selection strategy name (``"tournament"``,
                ``"roulette"``, ``"rank"``, ``"elite"``, or ``"ucb"``).
            **kwargs: Forwarded to the strategy function.

        Returns:
            An ``ArchiveEntry``, or ``None`` if the archive is empty.
        """
        if strategy == "ucb" or (self.use_ucb and strategy == "tournament"):
            return await self.ucb_selector.select_parent(
                self.archive,
                weights=self._fitness_weights,
            )
        return await select_parent(
            self.archive,
            strategy=strategy,
            weights=self._fitness_weights,
            **kwargs,
        )

    # -- analytics -----------------------------------------------------------

    async def get_fitness_trend(
        self,
        component: str | None = None,
        limit: int = 20,
    ) -> list[tuple[str, float]]:
        """Return recent fitness trajectory from the archive.

        Args:
            component: Optional filter by component name.
            limit: Maximum number of data points to return.

        Returns:
            List of ``(timestamp, weighted_fitness)`` pairs, oldest first.
        """
        trajectory = self.archive.fitness_over_time(
            component=component,
            weights=self._fitness_weights,
        )
        return trajectory[-limit:]

    async def create_router_retrospective(
        self,
        outcome: RouteOutcomeRecord | dict[str, Any],
    ) -> RouteRetrospectiveArtifact | None:
        """Convert a poor high-confidence route into a Darwin review artifact."""
        record = (
            outcome
            if isinstance(outcome, RouteOutcomeRecord)
            else RouteOutcomeRecord.model_validate(outcome)
        )
        artifact = build_route_retrospective(record)
        if artifact is None:
            return None

        archive_entry = build_route_policy_archive_entry(artifact)
        artifact.darwin_archive_entry_id = await self.archive.add_entry(archive_entry)

        if self._initialized:
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_router_auditor",
                    action="route_retrospective",
                    state=artifact.severity,
                    metadata={
                        "artifact_id": artifact.id,
                        "archive_entry_id": artifact.darwin_archive_entry_id,
                        "action_name": record.action_name,
                        "route_path": record.route_path,
                        "selected_provider": record.selected_provider,
                        "confidence": record.confidence,
                        "quality_score": record.effective_quality,
                    },
                )
            )
        return artifact

    async def audit_router_outcomes(
        self,
        outcomes: list[RouteOutcomeRecord | dict[str, Any]],
    ) -> list[RouteRetrospectiveArtifact]:
        """Scan routing outcomes and persist only the poor high-confidence cases."""
        artifacts: list[RouteRetrospectiveArtifact] = []
        for outcome in outcomes:
            artifact = await self.create_router_retrospective(outcome)
            if artifact is not None:
                artifacts.append(artifact)
        return artifacts

    async def guard_router_promotion(
        self,
        *,
        goal_drift_index: float,
        constraint_preservation: float,
        entry_id: str | None = None,
    ) -> DriftGuardDecision:
        """Apply drift thresholds before promoting a routing policy change."""
        decision = evaluate_router_drift(
            goal_drift_index=goal_drift_index,
            constraint_preservation=constraint_preservation,
            thresholds=self._router_drift_thresholds,
        )
        archive_status: str | None = None
        if entry_id:
            entry = await self.archive.get_entry(entry_id)
            if entry is not None:
                archive_status = (
                    "promoted" if decision.allow_promotion else "promotion_blocked"
                )
                policy_entry = entry.test_results.get("policy_archive_entry")
                if isinstance(policy_entry, dict):
                    policy_entry["promotion_state"] = archive_status
                await self.archive.update_status(
                    entry_id,
                    archive_status,
                    None if decision.allow_promotion else "; ".join(decision.reasons),
                )
        if self._initialized:
            await self.traces.log_entry(
                TraceEntry(
                    agent="darwin_router_guard",
                    action="promotion_guard",
                    state="allow" if decision.allow_promotion else "block",
                    metadata={
                        "entry_id": entry_id,
                        "archive_status": archive_status,
                        "goal_drift_index": decision.goal_drift_index,
                        "constraint_preservation": decision.constraint_preservation,
                        "reasons": decision.reasons,
                    },
                )
            )
        return decision

    async def reflect_on_cycle(
        self,
        cycle: CycleResult,
        proposals: list[Proposal],
        provider: Any | None = None,
    ) -> CycleResult:
        """Generate verbal self-reflection after an evolution cycle.

        If a provider is available, uses LLM to generate reflection.
        Otherwise, generates a rule-based reflection from cycle metrics.

        Args:
            cycle: The completed CycleResult to reflect on.
            proposals: The proposals that were processed.
            provider: Optional LLM provider for verbal reflection.

        Returns:
            The CycleResult with reflection and lessons_learned populated.
        """
        # Rule-based reflection (always available, no LLM needed)
        lessons: list[str] = []

        if cycle.proposals_archived == 0 and cycle.proposals_submitted > 0:
            lessons.append(
                f"All {cycle.proposals_submitted} proposals failed. "
                "Consider: different mutation strategy, different parent, "
                "or relaxing gate criteria."
            )
        if cycle.circuit_breakers_tripped > 0:
            lessons.append(
                f"Circuit breaker tripped {cycle.circuit_breakers_tripped}x. "
                "Repeated failures on same gate signature. Strategy pivot needed."
            )
        if cycle.best_fitness < 0.3 and cycle.proposals_archived > 0:
            lessons.append(
                f"Best fitness only {cycle.best_fitness:.3f}. "
                "Proposals are passing gates but scoring poorly. "
                "Check: correctness (test pass rate), elegance (AST score)."
            )
        if cycle.best_fitness > 0.7:
            lessons.append(
                f"Strong cycle: best fitness {cycle.best_fitness:.3f}. "
                "Archive this lineage for future parent selection."
            )

        # Rejection analysis
        rejected = [p for p in proposals if p.status == EvolutionStatus.REJECTED]
        if rejected:
            gate_reasons = [p.gate_reason or "unknown" for p in rejected]
            unique_reasons = list(set(gate_reasons))
            lessons.append(
                f"{len(rejected)} rejected. Gate reasons: {'; '.join(unique_reasons[:3])}"
            )

        cycle.lessons_learned = lessons
        cycle.reflection = " | ".join(lessons) if lessons else "Clean cycle, no issues."

        # Log reflection as trace
        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="reflect",
                state="reflected",
                metadata={
                    "cycle_id": cycle.cycle_id,
                    "reflection": cycle.reflection,
                    "lessons_count": len(lessons),
                },
            )
        )

        logger.info("Cycle %s reflection: %s", cycle.cycle_id, cycle.reflection[:200])
        return cycle

    # -- LLM-powered proposal generation ------------------------------------

    @staticmethod
    def _parse_llm_proposal(response: str) -> dict[str, str]:
        """Parse structured fields from an LLM proposal response."""
        fields: dict[str, str] = {}
        for key in ("COMPONENT", "CHANGE_TYPE", "DESCRIPTION", "THINK"):
            match = re.search(rf"^{key}:\s*(.+)$", response, re.MULTILINE)
            if match:
                fields[key.lower()] = match.group(1).strip()

        # Extract diff block
        diff_match = re.search(
            r"```diff\s*\n(.*?)```", response, re.DOTALL
        )
        fields["diff"] = diff_match.group(1).strip() if diff_match else ""
        return fields

    async def generate_proposal(
        self,
        provider: Any,
        source_file: Path,
        context: str = "",
        model: str = "meta-llama/llama-3.3-70b-instruct",
    ) -> Proposal | None:
        """Use an LLM to generate an evolution proposal from a source file.

        Reads the file, sends it to the LLM with improvement instructions,
        parses the structured response into a Proposal.

        Args:
            provider: An LLM provider with async ``complete(LLMRequest)`` method.
            source_file: Path to the Python file to improve.
            context: Optional extra context (e.g., recent failures, focus area).
            model: Model identifier for the provider.

        Returns:
            A Proposal ready for gate_check(), or None if the LLM says no-op.
        """
        from dharma_swarm.models import LLMRequest

        if not source_file.exists():
            logger.warning("Source file not found: %s", source_file)
            return None

        source = source_file.read_text(encoding="utf-8")
        if len(source) > 15_000:
            source = source[:15_000] + "\n# ... truncated ..."

        strategy = self._current_adaptive_strategy()
        mutation_rate = self.get_active_mutation_rate()
        mutation_budget = self.get_mutation_budget_lines()
        user_msg = (
            "## Mutation Envelope\n"
            f"- mutation_rate: {mutation_rate:.3f}\n"
            f"- diff_budget_lines: {mutation_budget}\n"
            f"- adaptive_strategy: {strategy}\n\n"
            f"## File: {source_file.name}\n\n```python\n{source}\n```"
        )
        if context:
            user_msg = f"## Context\n{context}\n\n{user_msg}"

        request = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": user_msg}],
            system=self._build_propose_system(),
            max_tokens=2048,
            temperature=min(1.0, max(0.3, 0.4 + mutation_rate)),
        )

        try:
            response = await provider.complete(request)
        except Exception as exc:
            logger.error("LLM proposal generation failed: %s", exc)
            return None

        fields = self._parse_llm_proposal(response.content)

        desc = fields.get("description", "").strip()
        if not desc or desc.lower() == "no-op":
            logger.info("LLM proposed no-op for %s", source_file.name)
            return None

        component = fields.get("component", source_file.stem)
        change_type = fields.get("change_type", "mutation")
        diff = fields.get("diff", "")
        think = fields.get("think", "")

        proposal = await self.propose(
            component=component,
            change_type=change_type,
            description=desc,
            diff=diff,
            think_notes=think,
        )

        await self.traces.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="llm_generate_proposal",
                state="generated",
                metadata={
                    "proposal_id": proposal.id,
                    "source_file": str(source_file),
                    "model": model,
                    "description": desc[:200],
                    "diff_lines": len(diff.splitlines()),
                    "mutation_rate": mutation_rate,
                    "mutation_budget": mutation_budget,
                    "adaptive_strategy": strategy,
                },
            )
        )

        logger.info(
            "LLM generated proposal %s for %s: %s",
            proposal.id[:8], source_file.name, desc[:100],
        )
        return proposal

    async def auto_evolve(
        self,
        provider: Any,
        source_files: list[Path],
        model: str = "meta-llama/llama-3.3-70b-instruct",
        test_command: str = "python3 -m pytest tests/ -q --tb=short -x --timeout=10",
        context: str = "",
    ) -> CycleResult:
        """Autonomous evolution: LLM proposes improvements, engine evaluates them.

        For each source file, generates a proposal via LLM, then runs the
        full gate → test → evaluate → archive pipeline.

        Args:
            provider: An LLM provider with async ``complete()`` method.
            source_files: List of Python files to propose improvements for.
            model: Model identifier for the provider.
            test_command: Shell command for testing proposals.
            context: Extra context to guide the LLM (focus areas, recent errors).

        Returns:
            A CycleResult summarizing the autonomous evolution cycle.
        """
        proposals: list[Proposal] = []
        for sf in source_files:
            proposal = await self.generate_proposal(
                provider=provider,
                source_file=sf,
                context=context,
                model=model,
            )
            if proposal is not None:
                proposals.append(proposal)

        if not proposals:
            logger.info("No proposals generated — nothing to evolve")
            return CycleResult(proposals_submitted=0)

        result = await self.run_cycle_with_sandbox(
            proposals,
            test_command=test_command,
        )

        logger.info(
            "Auto-evolve complete: %d files → %d proposals → %d archived (best=%.3f)",
            len(source_files),
            result.proposals_submitted,
            result.proposals_archived,
            result.best_fitness,
        )
        return result

    # -- auto-commit ---------------------------------------------------------

    @staticmethod
    async def commit_if_worthy(
        proposal: Proposal,
        fitness_threshold: float = 0.6,
        workspace: Path | None = None,
    ) -> str | None:
        """Git commit a proposal's changes if fitness exceeds threshold.

        Args:
            proposal: An evaluated, archived proposal.
            fitness_threshold: Minimum weighted fitness to commit.
            workspace: Git repo root. Defaults to ~/dharma_swarm.

        Returns:
            Commit hash if committed, None otherwise.
        """
        if proposal.actual_fitness is None:
            return None
        weighted_fitness = self.score_fitness(proposal.actual_fitness)
        if weighted_fitness < fitness_threshold:
            return None
        if not proposal.diff.strip():
            return None

        ws = workspace or (Path.home() / "dharma_swarm")
        msg = (
            f"[darwin] {proposal.component}: {proposal.description}\n\n"
            f"Fitness: {weighted_fitness:.3f}\n"
            f"Proposal: {proposal.id}\n"
            f"Change-type: {proposal.change_type}"
        )

        proc = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--cached", "--quiet",
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            # Nothing staged
            return None

        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", msg,
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None

        # Extract commit hash
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--short", "HEAD",
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        commit_hash = stdout.decode().strip()
        logger.info(
            "Committed proposal %s as %s (fitness=%.3f)",
            proposal.id[:8], commit_hash, weighted_fitness,
        )
        return commit_hash

    # -- daemon loop ---------------------------------------------------------

    async def daemon_loop(
        self,
        think_provider: Any,
        source_dir: Path | None = None,
        model: str = "meta-llama/llama-3.3-70b-instruct",
        interval: float = 1800.0,
        fitness_threshold: float = 0.6,
        max_cycles: int | None = None,
    ) -> None:
        """Run autonomous evolution continuously.

        Each cycle:
        1. Pick source files to evolve
        2. Generate proposals via LLM (cheap, OpenRouter)
        3. Gate-check, apply diffs, run tests
        4. Evaluate fitness, archive
        5. Auto-commit if fitness > threshold
        6. Sleep, repeat

        Args:
            think_provider: LLM provider for proposal generation (OpenRouter).
            source_dir: Directory containing Python source files.
            model: Model for proposal generation.
            interval: Seconds between cycles.
            fitness_threshold: Minimum fitness to auto-commit.
            max_cycles: Stop after N cycles (None = run forever).
        """
        src = source_dir or (Path.home() / "dharma_swarm" / "dharma_swarm")
        cycle_count = 0
        context_parts: list[str] = []

        logger.info(
            "Darwin daemon starting: interval=%.0fs, threshold=%.2f, src=%s",
            interval, fitness_threshold, src,
        )

        while True:
            cycle_count += 1
            if max_cycles is not None and cycle_count > max_cycles:
                logger.info("Max cycles (%d) reached, stopping", max_cycles)
                break

            # Pick files — rotate through source files
            all_py = sorted(src.glob("*.py"))
            if not all_py:
                logger.warning("No Python files found in %s", src)
                await asyncio.sleep(interval)
                continue

            # Pick 3 files per cycle, rotating
            offset = (cycle_count - 1) * 3
            files = [all_py[i % len(all_py)] for i in range(offset, offset + 3)]

            # Build context from recent lessons
            recent_trend = await self.get_fitness_trend(limit=5)
            if recent_trend:
                avg = sum(f for _, f in recent_trend) / len(recent_trend)
                context_parts = [f"Recent average fitness: {avg:.3f}"]
            else:
                context_parts = []

            # Add lessons from last cycle
            last_entries = (await self.archive.get_latest(3))
            for entry in last_entries:
                context_parts.append(
                    f"Recent: {entry.component} ({entry.change_type}) "
                    f"fitness={self.score_fitness(entry.fitness):.3f}"
                )

            context = "\n".join(context_parts)

            logger.info(
                "Daemon cycle %d: evolving %s",
                cycle_count,
                ", ".join(f.name for f in files),
            )

            try:
                result = await self.auto_evolve(
                    provider=think_provider,
                    source_files=files,
                    model=model,
                    context=context,
                )

                # Auto-commit winning proposals
                committed = 0
                recent = await self.archive.get_latest(result.proposals_archived)
                for entry in recent:
                    if self.score_fitness(entry.fitness) >= fitness_threshold:
                        # Re-create a minimal proposal for commit
                        p = Proposal(
                            component=entry.component,
                            change_type=entry.change_type,
                            description=entry.description,
                            diff=entry.diff,
                            actual_fitness=entry.fitness,
                        )
                        commit = await self.commit_if_worthy(
                            p, fitness_threshold=fitness_threshold
                        )
                        if commit:
                            committed += 1

                logger.info(
                    "Daemon cycle %d complete: %d proposals, %d archived, "
                    "%d committed, best=%.3f",
                    cycle_count,
                    result.proposals_submitted,
                    result.proposals_archived,
                    committed,
                    result.best_fitness,
                )

            except Exception as exc:
                logger.exception("Daemon cycle %d failed: %s", cycle_count, exc)

            if max_cycles is not None and cycle_count >= max_cycles:
                break
            await asyncio.sleep(interval)
