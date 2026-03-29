"""Darwin Engine -- self-improvement orchestration loop.

Coordinates the full evolution cycle: propose mutations, gate-check them,
evaluate fitness, archive results, and select parents for the next generation.

Pipeline:
    PROPOSE -> GATE CHECK -> WRITE CODE -> TEST -> EVALUATE FITNESS -> ARCHIVE -> SELECT NEXT PARENT
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import inspect
import logging
import re
import shlex
import shutil
from tempfile import TemporaryDirectory
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.archive import (
    ArchiveEntry,
    EvolutionArchive,
    FitnessScore,
    normalize_fitness_weights,
    research_reward_to_fitness,
)
from dharma_swarm.convergence import ConvergenceConfig, ConvergenceDetector
from dharma_swarm.diff_applier import DiffApplier
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.execution_profile import (
    EvidenceTier,
    ExecutionProfileRegistry,
    PromotionState,
    ResolvedExecutionProfile,
    derive_promotion_state,
)
from dharma_swarm.experiment_memory import ExperimentMemory, ExperimentMemorySnapshot
from dharma_swarm.experiment_log import ExperimentLog, ExperimentRecord
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span
from dharma_swarm.landscape import FitnessLandscapeMapper, LandscapeProbe
from dharma_swarm.models import GateDecision, GateResult, SandboxResult, _new_id, _utc_now
from dharma_swarm.pending_proposals import PENDING_PROPOSALS_FILE
from dharma_swarm.quality_gates import QualityGateResult, run_quality_gate
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
    test_results: dict[str, Any] = Field(default_factory=dict)
    cycle_id: str | None = None
    execution_profile: str = "default"
    execution_matched_pattern: str | None = None
    execution_workspace: str | None = None
    execution_test_command: str | None = None
    execution_timeout: float | None = None
    execution_risk_level: str = "medium"
    execution_rollback_policy: str = "revert_patch"
    execution_expected_metrics: list[str] = Field(default_factory=list)
    evidence_tier: str = EvidenceTier.UNVALIDATED.value
    promotion_state: str = PromotionState.CANDIDATE.value
    experiment_id: str | None = None
    metadata: dict[str, Any] | None = None

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


@dataclass
class RuntimeFieldEvolutionResult:
    """Outcome of a runtime-field Darwin trial."""

    proposal: Proposal
    archive_entry_id: str
    trial_result: Any
    reward_signal: Any | None = None


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
        max_cycle_tokens: int = 0,
        landscape_probe_workspace: Path | None = None,
        landscape_probe_test_command: str = "python3 -m pytest tests/ -q --tb=short",
        landscape_probe_timeout: float = 60.0,
        probe_targets: ExecutionProfileRegistry | list[dict[str, Any]] | None = None,
        meta_evolution_interval: int = 0,
        meta_archive_path: Path | None = None,
        meta_poor_fitness_threshold: float = 0.5,
        meta_auto_apply: bool = True,
        experiment_log_path: Path | None = None,
        router_drift_thresholds: DriftGuardThresholds | None = None,
        quality_gate_threshold: float = 60.0,
        quality_gate_enabled: bool = False,
        quality_gate_use_llm: bool = False,
        quality_gate_provider: Any = None,
    ) -> None:
        self.archive = EvolutionArchive(path=archive_path)
        self.traces = TraceStore(base_path=traces_path)
        self.predictor = FitnessPredictor(history_path=predictor_path)
        self.experiment_log = ExperimentLog(
            path=experiment_log_path or (self.archive.path.parent / "experiments.jsonl")
        )
        self.experiment_memory = ExperimentMemory()
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
        self.execution_profile_registry = ExecutionProfileRegistry.from_configs(
            probe_targets
        )
        # Quality gates: post-fitness evaluation filter (must be before MetaEvolutionEngine
        # which calls get_meta_parameter_state() which references these)
        self._quality_gate_threshold = max(0.0, min(100.0, float(quality_gate_threshold)))
        self._quality_gate_enabled = bool(quality_gate_enabled)
        self._quality_gate_use_llm = bool(quality_gate_use_llm)
        self._quality_gate_provider = quality_gate_provider
        self.last_quality_gate_result: QualityGateResult | None = None

        self._meta_evolution_interval = max(0, int(meta_evolution_interval))
        self.last_meta_evolution_result: Any | None = None
        self.last_coordination_summary: dict[str, Any] = {}
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
        self._max_cycle_tokens = max(0, int(max_cycle_tokens))
        self._session_tokens_used = 0
        # Mutation budget: max mutations per day (prevents runaway self-modification)
        self._daily_mutation_budget = 5
        self._mutations_today = 0
        self._budget_reset_date = ""
        self.last_landscape_probe: LandscapeProbe | None = None
        self.last_experiment_memory: ExperimentMemorySnapshot | None = None
        self.landscape_mapper = FitnessLandscapeMapper(self)
        self._forge: Any | None = None
        self._system_rv: Any | None = None
        self._dse_integrator: Any | None = None
        self._initialized: bool = False
        # Phase 4 velocity: content-hash skip for unchanged files
        self._file_hashes: dict[str, str] = {}
        # Phase 4 velocity: pending background trace tasks
        self._trace_tasks: set[asyncio.Task[None]] = set()
        # W4: Agent fitness from real task execution (via SignalBus)
        self._agent_fitness_signals: list[dict[str, Any]] = []
        # C11: Diversity health from SignalBus — drives mutation pressure
        self._diversity_status: str = "unknown"
        self._diversity_boost_active: bool = False

    # -- Phase 4: fire-and-forget trace helper --------------------------------

    def _trace_bg(self, entry: TraceEntry) -> None:
        """Log a trace entry in the background without blocking the caller."""
        task = asyncio.create_task(self.traces.log_entry(entry))
        self._trace_tasks.add(task)
        task.add_done_callback(self._trace_tasks.discard)

    # -- W4: Real-task fitness from SignalBus ---------------------------------

    def consume_agent_fitness_signals(self) -> int:
        """Drain AGENT_FITNESS signals from the bus and store them.

        Returns the number of signals consumed. Call this before
        select_next_parent() so real-world quality scores influence
        parent selection and mutation pressure.
        """
        try:
            from dharma_swarm.signal_bus import SignalBus, SIGNAL_AGENT_FITNESS

            bus = SignalBus.get()
            signals = bus.drain([SIGNAL_AGENT_FITNESS])
            self._agent_fitness_signals.extend(signals)
            if signals:
                logger.debug("W4: Consumed %d agent fitness signals", len(signals))
            return len(signals)
        except Exception:
            return 0

    def drain_diversity_signals(self) -> str:
        """Drain SIGNAL_DIVERSITY_HEALTH from the bus and adjust mutation pressure.

        When diversity_status is 'critical' (behavioral_div < 0.2):
          - Increase mutation_rate by 1.5x to encourage exploration
          - Set flag for cross-family parent selection
        When 'healthy':
          - Allow normal convergence (clear boost flag)

        Returns the last observed diversity status ('critical', 'healthy',
        'warning', or 'unknown' if no signal was present).
        """
        try:
            from dharma_swarm.signal_bus import SignalBus, SIGNAL_DIVERSITY_HEALTH

            bus = SignalBus.get()
            signals = bus.drain([SIGNAL_DIVERSITY_HEALTH])
            if not signals:
                return self._diversity_status

            # Use the most recent signal
            latest = signals[-1]
            status = latest.get("diversity_status", "unknown")
            behavioral_div = latest.get("behavioral_div", 1.0)

            self._diversity_status = status

            if status == "critical" or (
                isinstance(behavioral_div, (int, float)) and behavioral_div < 0.2
            ):
                if not self._diversity_boost_active:
                    self._base_mutation_rate = min(
                        1.0, self._base_mutation_rate * 1.5
                    )
                    self._diversity_boost_active = True
                    logger.info(
                        "C11: Diversity CRITICAL (%.2f) — mutation_rate boosted to %.3f, "
                        "cross-family selection enabled",
                        behavioral_div,
                        self._base_mutation_rate,
                    )
            else:
                if self._diversity_boost_active:
                    logger.info(
                        "C11: Diversity recovered to '%s' — clearing boost", status
                    )
                self._diversity_boost_active = False

            return self._diversity_status
        except Exception:
            return self._diversity_status

    def agent_fitness_summary(self) -> dict[str, dict[str, float]]:
        """Summarize consumed agent fitness signals by agent name.

        Returns dict mapping agent_name → {mean_quality, count, mean_swabhaav}.
        Useful for biasing parent selection toward agents whose real-world
        task quality is high.
        """
        from collections import defaultdict
        accum: dict[str, list[float]] = defaultdict(list)
        swab: dict[str, list[float]] = defaultdict(list)
        for sig in self._agent_fitness_signals:
            agent = sig.get("agent", "unknown")
            q = sig.get("quality_score")
            if isinstance(q, (int, float)):
                accum[agent].append(float(q))
            s = sig.get("swabhaav_ratio")
            if isinstance(s, (int, float)):
                swab[agent].append(float(s))
        result: dict[str, dict[str, float]] = {}
        for agent, scores in accum.items():
            result[agent] = {
                "mean_quality": sum(scores) / len(scores),
                "count": float(len(scores)),
                "mean_swabhaav": (
                    sum(swab.get(agent, [0.5])) / len(swab.get(agent, [0.5]))
                ),
            }
        return result

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

    # -- Sprint 1-3 wiring: subsystem setters + extended fitness ----------

    def set_knowledge_store(self, store: Any) -> None:
        """Attach a KnowledgeStore for memory quality fitness signals."""
        self._knowledge_store = store

    def set_economic_spine(self, spine: Any) -> None:
        """Attach an EconomicSpine for economic efficiency fitness signals."""
        self._economic_spine = spine

    def set_correction_engine(self, engine: Any) -> None:
        """Attach a DynamicCorrectionEngine for correction health signals."""
        self._correction_engine = engine

    def compute_extended_fitness(self, agent_id: str, base_fitness: float) -> float:
        """Extend base fitness with Sprint 1-3 signals + verification.

        Four dimensions (each 0.0-1.0, weighted):
        1. Memory quality: proportion of tasks that produced useful knowledge
        2. Economic efficiency: quality per token (normalized)
        3. Correction health: inverse of correction frequency
        4. Verification survival: how often output survives cross-model verification

        Final = base * 0.50 + memory * 0.12 + econ * 0.12 + health * 0.08 + verify * 0.18
        """
        memory_signal = self._memory_quality_signal(agent_id)
        econ_signal = self._economic_efficiency_signal(agent_id)
        health_signal = self._correction_health_signal(agent_id)
        verify_signal = self._verification_survival_signal(agent_id)

        return (
            base_fitness * 0.50
            + memory_signal * 0.12
            + econ_signal * 0.12
            + health_signal * 0.08
            + verify_signal * 0.18
        )

    def _memory_quality_signal(self, agent_id: str) -> float:
        """How well does this agent's work produce reusable knowledge?

        Metric: count of knowledge units with this agent's provenance.
        Returns 0.5 (neutral) if KnowledgeStore is not wired.
        """
        store = getattr(self, "_knowledge_store", None)
        if store is None:
            return 0.5
        try:
            props = store.get_by_agent_provenance(agent_id, unit_type="proposition")
            prescs = store.get_by_agent_provenance(agent_id, unit_type="prescription")
            total_units = len(props) + len(prescs)
            # Normalize: 10+ units = 1.0, 0 = 0.0
            return min(total_units / 10.0, 1.0)
        except Exception:
            return 0.5

    def _economic_efficiency_signal(self, agent_id: str) -> float:
        """Quality per token spent.

        Returns 0.5 (neutral) if EconomicSpine is not wired.
        """
        spine = getattr(self, "_economic_spine", None)
        if spine is None:
            return 0.5
        try:
            stats = spine.get_agent_stats(agent_id)
            if stats.get("mission_count", 0) == 0:
                return 0.5
            avg_quality = stats.get("efficiency_score", 0.5)
            avg_cost = stats.get("tokens_spent", 1)
            # Higher quality per token = better
            efficiency = avg_quality / max(avg_cost / 10000.0, 0.01)
            return min(efficiency, 1.0)
        except Exception:
            return 0.5

    def _correction_health_signal(self, agent_id: str) -> float:
        """Agents that trigger fewer corrections are fitter.

        Returns 0.5 (neutral) if CorrectionEngine is not wired.
        """
        correction_engine = getattr(self, "_correction_engine", None)
        if correction_engine is None:
            return 0.5
        try:
            history = correction_engine.get_correction_history(agent_id=agent_id, limit=20)
            correction_count = len(history)
            # 10+ corrections in window = 0.0, 0 = 1.0
            return max(1.0 - (correction_count / 10.0), 0.0)
        except Exception:
            return 0.5

    def _verification_survival_signal(self, agent_id: str) -> float:
        """How often does this agent's output survive cross-model verification?

        Reads from ~/.dharma/transcendence/verification.jsonl.
        Returns 0.5 (neutral) if no verification data exists.
        """
        import json as _json
        from pathlib import Path as _Path

        log_path = _Path.home() / ".dharma" / "transcendence" / "verification.jsonl"
        if not log_path.exists():
            return 0.5

        try:
            total = 0
            passed = 0
            for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = _json.loads(line)
                if entry.get("agent") == agent_id:
                    total += 1
                    if entry.get("issues_found", 0) == 0:
                        passed += 1
            if total == 0:
                return 0.5
            return passed / total
        except Exception:
            return 0.5

    def get_meta_parameter_state(self) -> dict[str, Any]:
        """Export the engine knobs used by meta-evolution."""
        return {
            "fitness_weights": self.get_fitness_weights(),
            "mutation_rate": self._base_mutation_rate,
            "exploration_coeff": self.ucb_selector.state.exploration_coeff,
            "circuit_breaker_limit": self._circuit_breaker_limit,
            "map_elites_n_bins": self._map_elites_n_bins,
            "quality_gate_threshold": self._quality_gate_threshold,
            "quality_gate_enabled": self._quality_gate_enabled,
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

    def observe_coordination_summary(self, summary: dict[str, Any] | None) -> None:
        """Forward live coordination uncertainty into meta-evolution."""
        self.last_coordination_summary = dict(summary or {})
        if self._meta_evolution_engine is None:
            return
        observer = getattr(self._meta_evolution_engine, "observe_coordination_summary", None)
        if callable(observer):
            observer(summary or {})

    def get_active_mutation_rate(self) -> float:
        """Return mutation rate after convergence restart adjustments."""
        return self.convergence_detector.get_restart_mutation_rate(
            self._base_mutation_rate
        )

    @staticmethod
    def _component_key_for_source_file(source_file: Path) -> str:
        """Derive a stable component key from a concrete source path."""
        try:
            return str(source_file.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return source_file.name

    @staticmethod
    def _workspace_roots(workspace: Path | None = None) -> list[Path]:
        """Return candidate roots for resolving component and test paths."""
        roots: list[Path] = []
        if workspace is not None:
            roots.append(Path(workspace).resolve())
        cwd = Path.cwd().resolve()
        if cwd not in roots:
            roots.append(cwd)
        return roots

    @classmethod
    def _candidate_component_paths(
        cls,
        component: str,
        *,
        workspace: Path | None = None,
    ) -> list[Path]:
        """Enumerate plausible on-disk locations for a component path."""
        component_path = Path(component)
        if component_path.is_absolute():
            return [component_path]

        candidates: list[Path] = []
        seen: set[Path] = set()
        for root in cls._workspace_roots(workspace):
            options = [root / component_path]
            if len(component_path.parts) == 1:
                options.append(root / "dharma_swarm" / component_path.name)
            for option in options:
                resolved = option.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(resolved)
        return candidates

    @classmethod
    def _resolve_component_source_path(
        cls,
        component: str,
        *,
        workspace: Path | None = None,
    ) -> Path | None:
        """Resolve a component to an existing source file when possible."""
        for candidate in cls._candidate_component_paths(component, workspace=workspace):
            if candidate.is_file():
                return candidate
        return None

    @classmethod
    def _infer_component_test_command(
        cls,
        component: str,
        *,
        workspace: Path | None = None,
    ) -> str | None:
        """Infer a targeted pytest command for a component when convention matches."""
        component_path = Path(component)
        stem = component_path.stem.strip()
        if not stem:
            return None

        for root in cls._workspace_roots(workspace):
            candidates: list[Path] = [root / "tests" / f"test_{stem}.py"]
            if component_path.parent != Path("."):
                candidates.append(root / component_path.parent / f"test_{stem}.py")
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                try:
                    command_target = candidate.resolve().relative_to(root)
                except ValueError:
                    command_target = candidate.resolve()
                return (
                    "python3 -m pytest "
                    f"{shlex.quote(command_target.as_posix())} -q --tb=short"
                )
        return None

    @staticmethod
    def _read_component_code(source_file: Path | None) -> str | None:
        """Read Python source for elegance scoring when a file is available."""
        if source_file is None or not source_file.is_file():
            return None
        try:
            return source_file.read_text(encoding="utf-8")
        except OSError:
            return None

    def _resolve_cycle_execution_target(
        self,
        component: str,
    ) -> tuple[ResolvedExecutionProfile, Path | None]:
        """Resolve the best runtime-validation target for ``run_cycle``."""
        resolved = self.execution_profile_registry.resolve(component)
        target = ResolvedExecutionProfile(
            component=component,
            profile_name=(
                resolved.profile_name if resolved is not None else "unvalidated"
            ),
            workspace=resolved.workspace if resolved is not None else None,
            test_command=resolved.test_command if resolved is not None else None,
            timeout=resolved.timeout if resolved is not None else None,
            matched_pattern=resolved.matched_pattern if resolved is not None else None,
            priority=resolved.priority if resolved is not None else 0,
            risk_level=resolved.risk_level if resolved is not None else "medium",
            expected_metrics=(
                list(resolved.expected_metrics) if resolved is not None else []
            ),
            rollback_policy=(
                resolved.rollback_policy if resolved is not None else "discard"
            ),
            evidence_tier=(
                resolved.evidence_tier
                if resolved is not None
                else EvidenceTier.UNVALIDATED
            ),
        )

        if target.test_command is None:
            inferred = self._infer_component_test_command(
                component,
                workspace=target.workspace,
            )
            if inferred is not None:
                target.test_command = inferred
                target.timeout = target.timeout or 60.0
                target.expected_metrics = list(target.expected_metrics or ["pass_rate"])
                if target.evidence_tier == EvidenceTier.UNVALIDATED:
                    target.evidence_tier = EvidenceTier.COMPONENT
                if target.profile_name == "unvalidated":
                    target.profile_name = "component_inferred"
                # Ensure workspace is set so sandbox runs in the right dir
                if target.workspace is None:
                    for root in self._workspace_roots():
                        if (root / "tests").is_dir():
                            target.workspace = root
                            break
        elif target.timeout is None:
            target.timeout = 60.0

        source_file = self._resolve_component_source_path(
            component,
            workspace=target.workspace,
        )
        return target, source_file

    def get_contextual_mutation_rate(
        self,
        *,
        component: str | None = None,
        profile_name: str | None = None,
    ) -> float:
        """Return the active mutation rate after experiment-memory biasing."""
        rate = self.get_active_mutation_rate()
        snapshot = self.last_experiment_memory
        if snapshot is None or snapshot.records_considered == 0:
            return rate

        if component:
            rate *= snapshot.component_mutation_bias.get(component, 1.0)
        if profile_name:
            rate *= snapshot.profile_mutation_bias.get(profile_name, 1.0)
        return max(0.01, min(1.0, rate))

    def register_probe_target(
        self,
        component_pattern: str,
        *,
        name: str = "",
        workspace: Path | str | None = None,
        test_command: str | None = None,
        timeout: float | None = None,
        priority: int = 0,
        risk_level: str = "medium",
        expected_metrics: list[str] | None = None,
        rollback_policy: str = "revert_patch",
        evidence_tier: EvidenceTier | str = EvidenceTier.COMPONENT,
    ) -> ResolvedExecutionProfile:
        """Register a component-aware workspace probe target."""
        target = self.execution_profile_registry.register(
            component_pattern,
            name=name,
            workspace=workspace,
            test_command=test_command,
            timeout=timeout,
            priority=priority,
            risk_level=risk_level,
            expected_metrics=expected_metrics,
            rollback_policy=rollback_policy,
            evidence_tier=evidence_tier,
        )
        return ResolvedExecutionProfile(
            component=component_pattern,
            profile_name=target.name or target.component_pattern,
            workspace=target.workspace,
            test_command=target.test_command,
            timeout=target.timeout,
            matched_pattern=target.component_pattern,
            priority=target.priority,
            risk_level=target.risk_level,
            expected_metrics=list(target.expected_metrics),
            rollback_policy=target.rollback_policy,
            evidence_tier=target.evidence_tier,
        )

    def resolve_probe_target(self, component: str) -> ResolvedExecutionProfile:
        """Resolve probe settings for a component with engine defaults overlaid."""
        return self.resolve_execution_target(
            component,
            fallback_test_command=self._landscape_probe_test_command,
            fallback_timeout=self._landscape_probe_timeout,
            fallback_workspace=self._landscape_probe_workspace,
            fallback_evidence_tier=EvidenceTier.PROBE,
            fallback_profile_name="probe_default",
        )

    def resolve_execution_target(
        self,
        component: str,
        *,
        fallback_test_command: str | None = None,
        fallback_timeout: float | None = None,
        fallback_workspace: Path | None = None,
        fallback_evidence_tier: EvidenceTier | str = EvidenceTier.LOCAL,
        fallback_profile_name: str = "default",
        fallback_risk_level: str = "medium",
        fallback_expected_metrics: list[str] | None = None,
        fallback_rollback_policy: str = "revert_patch",
    ) -> ResolvedExecutionProfile:
        """Resolve execution settings for a component using registry and fallbacks."""
        resolved = self.execution_profile_registry.resolve(component)
        default_workspace = (
            Path(fallback_workspace).resolve()
            if fallback_workspace is not None
            else None
        )
        try:
            evidence_tier = (
                resolved.evidence_tier
                if resolved is not None
                else (
                    fallback_evidence_tier
                    if isinstance(fallback_evidence_tier, EvidenceTier)
                    else EvidenceTier(str(fallback_evidence_tier))
                )
            )
        except ValueError:
            evidence_tier = EvidenceTier.UNVALIDATED

        return ResolvedExecutionProfile(
            component=component,
            profile_name=(
                resolved.profile_name if resolved else fallback_profile_name
            ),
            workspace=(
                resolved.workspace
                if resolved and resolved.workspace is not None
                else default_workspace
            ),
            test_command=(
                resolved.test_command
                if resolved and resolved.test_command is not None
                else (
                    fallback_test_command
                    if fallback_test_command is not None
                    else self._landscape_probe_test_command
                )
            ),
            timeout=(
                resolved.timeout
                if resolved and resolved.timeout is not None
                else (
                    float(fallback_timeout)
                    if fallback_timeout is not None
                    else None
                )
            ),
            matched_pattern=resolved.matched_pattern if resolved else None,
            priority=resolved.priority if resolved else 0,
            risk_level=resolved.risk_level if resolved else fallback_risk_level,
            expected_metrics=(
                list(resolved.expected_metrics)
                if resolved
                else list(fallback_expected_metrics or ["pass_rate"])
            ),
            rollback_policy=(
                resolved.rollback_policy if resolved else fallback_rollback_policy
            ),
            evidence_tier=evidence_tier,
        )

    @staticmethod
    def _stage_execution_context(
        proposal: Proposal,
        target: ResolvedExecutionProfile,
        *,
        cycle_id: str | None = None,
    ) -> None:
        """Attach resolved execution context to a proposal."""
        proposal.cycle_id = cycle_id
        proposal.execution_profile = target.profile_name
        proposal.execution_matched_pattern = target.matched_pattern
        proposal.execution_workspace = (
            str(target.workspace) if target.workspace is not None else None
        )
        proposal.execution_test_command = target.test_command
        proposal.execution_timeout = target.timeout
        proposal.execution_risk_level = target.risk_level
        proposal.execution_rollback_policy = target.rollback_policy
        proposal.execution_expected_metrics = list(target.expected_metrics)
        proposal.evidence_tier = target.evidence_tier.value

    def get_mutation_budget_lines(
        self,
        *,
        component: str | None = None,
        profile_name: str | None = None,
    ) -> int:
        """Translate mutation rate into an LLM diff-size budget."""
        mutation_rate = self.get_contextual_mutation_rate(
            component=component,
            profile_name=profile_name,
        )
        return max(12, min(160, round(12 + (mutation_rate * 160))))

    def _current_adaptive_strategy(self) -> str:
        """Return the current landscape-guided mutation mode."""
        if self.convergence_detector.is_restart_active():
            return "restart"
        if (
            self.last_experiment_memory is not None
            and self.last_experiment_memory.confidence >= 0.4
            and self.last_experiment_memory.recommended_strategy
        ):
            recommended = self.last_experiment_memory.recommended_strategy
            if recommended == "backtrack":
                return "backtrack"
            if self._adaptive_strategy == "explore":
                return recommended
        return self._adaptive_strategy

    async def refresh_experiment_memory(
        self,
        limit: int = 32,
    ) -> ExperimentMemorySnapshot:
        """Refresh experiment-memory snapshot from the recent experiment log."""
        records = await self.experiment_log.get_recent(limit=limit)
        self.last_experiment_memory = self.experiment_memory.analyze(records)
        return self.last_experiment_memory

    def _parent_memory_score(self, entry: ArchiveEntry) -> float:
        """Bias parent fitness using recent experiment-memory outcomes."""
        base = entry.fitness.weighted(weights=self._fitness_weights)
        snapshot = self.last_experiment_memory
        if snapshot is None or snapshot.records_considered == 0:
            return base

        parent_bias = snapshot.parent_scores.get(entry.id, 0.5)
        component_bias = snapshot.component_scores.get(entry.component, 0.5)
        multiplier = 1.0 + ((parent_bias - 0.5) * 0.6) + ((component_bias - 0.5) * 0.3)
        if entry.component in snapshot.caution_components:
            multiplier -= 0.15
        multiplier = max(0.5, min(1.5, multiplier))
        return base * multiplier

    def _build_propose_system(
        self,
        *,
        component: str | None = None,
        profile_name: str | None = None,
    ) -> str:
        """Build the proposal-generation system prompt from live engine state."""
        strategy = self._current_adaptive_strategy()
        max_lines = self.get_mutation_budget_lines(
            component=component,
            profile_name=profile_name,
        )
        memory_guidance = ""
        if (
            self.last_experiment_memory is not None
            and self.last_experiment_memory.lessons
        ):
            memory_guidance = "Recent experiment memory:\n" + "\n".join(
                f"- {lesson}"
                for lesson in self.last_experiment_memory.lessons[:3]
            ) + "\n"
        if (
            component
            and self.last_experiment_memory is not None
            and self.last_experiment_memory.records_considered > 0
        ):
            component_guidance = self._component_memory_guidance(
                component=component,
                profile_name=profile_name,
            )
            if component_guidance:
                memory_guidance += "Target-specific guidance:\n" + "\n".join(
                    f"- {line}"
                    for line in component_guidance
                ) + "\n"
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
            f"{memory_guidance}"
            "Rules:\n"
            f"- Keep changes under {max_lines} changed lines\n"
            f"- Current mutation mode: {strategy}. {strategy_guidance.get(strategy, strategy_guidance['explore'])}\n"
            "- Only fix real issues: bugs, missing error handling, performance, clarity\n"
            "- Do NOT add docstrings, type hints, or comments to code you didn't change\n"
            "- Do NOT refactor working code for style\n"
            "- The diff must be a valid unified diff (--- a/path/to/file, +++ b/path/to/file, @@ hunks)\n"
            "- IMPORTANT: Use the EXACT relative path shown in the '## File:' header for diff paths\n"
            "- If the code is already good, say DESCRIPTION: no-op and leave DIFF empty"
        )

    def _component_memory_guidance(
        self,
        *,
        component: str,
        profile_name: str | None = None,
    ) -> list[str]:
        """Return bounded, human-readable mutation guidance for a target component."""
        snapshot = self.last_experiment_memory
        if snapshot is None or snapshot.records_considered == 0:
            return []

        guidance: list[str] = []
        component_bias = snapshot.component_mutation_bias.get(component)
        if component in snapshot.caution_components:
            guidance.append(
                f"{component} has been fragile recently; prefer smaller, reversible edits."
            )
        if component_bias is not None and component_bias < 0.95:
            guidance.append(
                f"Lower mutation pressure on {component} (bias {component_bias:.2f}) until failures stop repeating."
            )
        if profile_name:
            profile_bias = snapshot.profile_mutation_bias.get(profile_name)
            if profile_bias is not None and profile_bias > 1.05:
                guidance.append(
                    f"Profile {profile_name} has been validating well; moderate exploration is acceptable."
                )
        guidance.extend(snapshot.avoidance_hints[:2])
        return guidance[:3]

    @staticmethod
    def _compact_reason(reason: str | None) -> str:
        """Compress a failure reason into a stable, human-readable signature token."""
        normalized = re.sub(r"\s+", " ", (reason or "").strip().lower())
        normalized = re.sub(r"[^a-z0-9._ -]", "", normalized)
        if not normalized:
            return "unknown"
        words = normalized.split()[:6]
        compact = " ".join(words).strip()
        return compact[:60] or "unknown"

    def _derive_experiment_failure(
        self,
        proposal: Proposal,
        test_results: dict[str, Any],
        weighted_fitness: float,
    ) -> tuple[str | None, str | None]:
        """Classify a Darwin experiment failure into bounded categories."""
        if proposal.gate_decision == GateDecision.BLOCK.value:
            reason = self._compact_reason(proposal.gate_reason)
            return ("gate_block", f"gate_block:{reason}")
        if test_results.get("rolled_back"):
            return ("rollback", "rollback:apply_or_test")
        exit_code = test_results.get("exit_code")
        if exit_code not in (None, 0):
            return ("test_failure", f"test_failure:exit_{int(exit_code)}")
        pass_rate = float(test_results.get("pass_rate", 0.0))
        if pass_rate < 1.0:
            return ("test_failure", "test_failure:pass_rate_drop")
        if weighted_fitness < 0.35:
            return ("low_fitness", "low_fitness:weak_total_score")
        return (None, None)

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

    async def _emit_coalgebra_observation(
        self,
        result: CycleResult,
        proposals: list[Proposal],
        new_entries: list[ArchiveEntry],
    ) -> None:
        """Emit a self-observed evolution observation after each cycle.

        Delegates to the DSE integrator which:
        1. Wraps the cycle in the self-observation monad
        2. Publishes discoveries to the sheaf coordination layer
        3. Every N cycles, runs Čech cohomology (H⁰ = global truths,
           H¹ = productive disagreements backed by Anekanta)
        4. Feeds coordination results back as engine context

        Fire-and-forget — failures never break the core pipeline.
        """
        try:
            if self._dse_integrator is None:
                from dharma_swarm.dse_integration import DSEIntegrator
                self._dse_integrator = DSEIntegrator(
                    archive_path=self.archive.path.parent,
                    coordination_interval=5,
                )

            snapshot = await self._dse_integrator.after_cycle(
                result,
                proposals,
                new_entries,
            )
            self.last_coordination_summary = (
                self._dse_integrator.get_coordination_context()
            )
            observer = getattr(self._meta_evolution_engine, "observe_coordination_summary", None)
            if callable(observer):
                observer(self._dse_integrator.get_coordination_summary())

            if snapshot is not None:
                logger.info(
                    "DSE coordination: H⁰=%d truths, H¹=%d disagreements, "
                    "coherent=%s, rv_trend=%s, fixed_point=%s",
                    snapshot.global_truths,
                    snapshot.productive_disagreements,
                    snapshot.is_globally_coherent,
                    f"{snapshot.rv_trend:.4f}" if snapshot.rv_trend is not None else "n/a",
                    snapshot.approaching_fixed_point,
                )
        except Exception as exc:
            logger.debug("DSE observation emission failed: %s", exc)

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
            self._trace_bg(
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

    async def flush_trace_tasks(self) -> None:
        """Wait for pending background trace writes to finish."""
        if not self._trace_tasks:
            return

        pending = tuple(self._trace_tasks)
        results = await asyncio.gather(*pending, return_exceptions=True)
        self._trace_tasks.difference_update(pending)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Background trace logging failed during flush", exc_info=result)

    async def close(self) -> None:
        """Flush background tasks owned by the Darwin engine."""
        await self.flush_trace_tasks()
        self._initialized = False

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
        self._trace_bg(
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
                self._trace_bg(
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

            # Log trace for gate check (fire-and-forget)
            self._trace_bg(
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
            proposal.test_results = dict(test_results)

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

            # Ouroboros: behavioral-score the proposal text (non-fatal).
            # Only applied when the description alone has substantial text
            # (>100 words), excluding auto-generated reflection notes.
            try:
                proposal_text = proposal.description
                if len(proposal_text.split()) > 100:
                    from dharma_swarm.ouroboros import (
                        apply_behavioral_modifiers,
                        score_behavioral_fitness,
                    )
                    _, modifiers = score_behavioral_fitness(proposal_text)
                    fitness = apply_behavioral_modifiers(fitness, modifiers)
            except Exception:
                logger.debug("Ouroboros behavioral modifiers failed", exc_info=True)

            # L4 compression: measure behavioral compression ability (non-fatal).
            # Only applied when the description alone has substantial text
            # (>50 words), providing L4-relevant behavioral metrics for the
            # research bridge without requiring LLM calls.
            try:
                proposal_text = proposal.description
                if hasattr(proposal, 'think_notes') and proposal.think_notes:
                    proposal_text = proposal.think_notes
                if len(proposal_text.split()) > 50:
                    from dharma_swarm.metrics import MetricsAnalyzer

                    _analyzer = MetricsAnalyzer()
                    sig = _analyzer.analyze(proposal_text)

                    # Store L4-relevant behavioral metrics alongside fitness
                    proposal.metadata = proposal.metadata or {}
                    proposal.metadata["l4_behavioral"] = {
                        "swabhaav_ratio": sig.swabhaav_ratio,
                        "entropy": sig.entropy,
                        "self_reference_density": sig.self_reference_density,
                        "recognition_type": sig.recognition_type.value,
                        "paradox_tolerance": sig.paradox_tolerance,
                    }
            except Exception:
                logger.debug("L4 behavioral correlation failed", exc_info=True)

            proposal.actual_fitness = fitness
            proposal.status = EvolutionStatus.EVALUATED
            proposal.promotion_state = derive_promotion_state(
                evidence_tier=proposal.evidence_tier,
                pass_rate=correctness,
                rolled_back=bool(test_results.get("rolled_back")),
            ).value

            logger.info(
                "Proposal %s evaluated: weighted=%.3f",
                proposal.id,
                self.score_fitness(fitness),
            )
            return proposal

    # -- quality gate --------------------------------------------------------

    async def _run_quality_gate(self, proposal: Proposal) -> QualityGateResult:
        """Run quality gate on an evaluated proposal.

        Uses the proposal description, diff, and any code artifact to
        determine whether the proposal meets minimum quality standards.
        Falls back to structural analysis if no LLM provider is available.

        Args:
            proposal: The evaluated proposal to gate.

        Returns:
            QualityGateResult with pass/fail, score, and feedback.
        """
        code = None
        if proposal.diff and proposal.diff.strip():
            # Extract added lines from diff as "code" for code quality gate
            added_lines = []
            for line in proposal.diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:])
            if added_lines:
                code = "\n".join(added_lines)

        return await run_quality_gate(
            proposal_description=proposal.description,
            proposal_diff=proposal.diff,
            proposal_component=proposal.component,
            proposal_change_type=proposal.change_type,
            code=code,
            threshold=self._quality_gate_threshold,
            provider=self._quality_gate_provider,
            use_llm=self._quality_gate_use_llm,
            cache_enabled=True,
        )

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
            experiment_id = proposal.experiment_id or _new_id()
            proposal.experiment_id = experiment_id
            test_results = dict(proposal.test_results)
            test_results.setdefault(
                "execution_target",
                {
                    "profile_name": proposal.execution_profile,
                    "matched_pattern": proposal.execution_matched_pattern,
                    "workspace": proposal.execution_workspace,
                    "test_command": proposal.execution_test_command,
                    "timeout": proposal.execution_timeout,
                    "risk_level": proposal.execution_risk_level,
                    "rollback_policy": proposal.execution_rollback_policy,
                    "expected_metrics": list(proposal.execution_expected_metrics),
                },
            )
            failure_class, failure_signature = self._derive_experiment_failure(
                proposal,
                test_results,
                weighted_fitness,
            )

            entry = ArchiveEntry(
                component=proposal.component,
                change_type=proposal.change_type,
                description=proposal.description,
                spec_ref=proposal.spec_ref,
                requirement_refs=list(proposal.requirement_refs),
                diff=proposal.diff,
                parent_id=proposal.parent_id,
                fitness=fitness,
                test_results=test_results,
                experiment_id=experiment_id,
                execution_profile=proposal.execution_profile,
                evidence_tier=proposal.evidence_tier,
                promotion_state=proposal.promotion_state,
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

            # GAIA ecological fitness (non-fatal): blend ecological awareness
            try:
                from dharma_swarm.gaia_ledger import GaiaLedger
                from dharma_swarm.gaia_fitness import (
                    EcologicalFitness,
                    detect_goodhart_drift,
                )

                ledger_dir = Path(self.archive.path).parent / "gaia_ledger"
                if ledger_dir.exists():
                    ledger = GaiaLedger(data_dir=ledger_dir)
                    ledger.load()
                    eco_fitness = EcologicalFitness()
                    eco_score = eco_fitness.weighted_score(ledger)
                    drift = detect_goodhart_drift(ledger)

                    entry.test_results["gaia_fitness"] = eco_score
                    entry.test_results["gaia_drifting"] = drift["is_drifting"]

                    # If Goodhart drifting, annotate the entry
                    if drift["is_drifting"]:
                        entry.test_results["gaia_warning"] = drift["diagnosis"]
            except Exception:
                logger.debug("GAIA fitness evaluation failed", exc_info=True)

            entry_id = await self.archive.add_entry(entry)
            proposal.status = EvolutionStatus.ARCHIVED
            experiment = ExperimentRecord(
                id=experiment_id,
                proposal_id=proposal.id,
                archive_entry_id=entry_id,
                cycle_id=proposal.cycle_id,
                component=proposal.component,
                change_type=proposal.change_type,
                description=proposal.description,
                parent_id=proposal.parent_id,
                execution_profile=proposal.execution_profile,
                matched_pattern=proposal.execution_matched_pattern,
                workspace=proposal.execution_workspace,
                test_command=proposal.execution_test_command,
                timeout=proposal.execution_timeout,
                evidence_tier=proposal.evidence_tier,
                promotion_state=proposal.promotion_state,
                risk_level=proposal.execution_risk_level,
                rollback_policy=proposal.execution_rollback_policy,
                expected_metrics=list(proposal.execution_expected_metrics),
                pass_rate=float(test_results.get("pass_rate", 0.0)),
                weighted_fitness=weighted_fitness,
                outcome=proposal.status.value,
                failure_class=failure_class,
                failure_signature=failure_signature,
                test_results=test_results,
                fitness=fitness,
                agent_id=entry.agent_id,
                model=entry.model,
                tokens_used=entry.tokens_used,
            )
            await self.experiment_log.append(experiment)
            await self.refresh_experiment_memory()

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
                    "experiment_id": experiment_id,
                    "weighted_fitness": weighted_fitness,
                    "promotion_state": proposal.promotion_state,
                    "evidence_tier": proposal.evidence_tier,
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

    async def run_runtime_field_trial(
        self,
        *,
        component: str,
        registry: Any,
        mutations: list[Any],
        evaluate: Callable[[], Any],
        description: str,
        parent_id: str | None = None,
        spec_ref: str | None = None,
        requirement_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeFieldEvolutionResult:
        """Run one reward-scored runtime-field trial through the archive path."""

        from dharma_swarm.optimizer_bridge import (
            apply_runtime_field_mutations,
            render_runtime_field_trial_diff,
            rollback_runtime_field_trial,
        )

        proposal = Proposal(
            component=component,
            change_type="runtime_field_trial",
            description=description,
            parent_id=parent_id,
            spec_ref=spec_ref,
            requirement_refs=list(requirement_refs or []),
            diff=render_runtime_field_trial_diff(mutations),
            metadata=dict(metadata or {}),
        )
        trial_result = apply_runtime_field_mutations(registry, mutations)
        reward_signal: Any | None = None

        try:
            outcome = evaluate()
            if inspect.isawaitable(outcome):
                outcome = await outcome
            reward_signal = outcome
            proposal.actual_fitness = research_reward_to_fitness(reward_signal)
            proposal.gate_decision = GateDecision.ALLOW.value

            reward_payload = (
                reward_signal.model_dump()
                if hasattr(reward_signal, "model_dump")
                else dict(reward_signal)
            )
            grade_card = dict(reward_payload.get("grade_card") or {})
            proposal.promotion_state = derive_promotion_state(
                evidence_tier=proposal.evidence_tier,
                pass_rate=1.0,
                rolled_back=True,
            ).value
            proposal.test_results["runtime_field_trial"] = {
                "mutated_fields": list(trial_result.applied_fields),
                "before": dict(trial_result.before),
                "after": dict(trial_result.after),
                "reward_signal": reward_payload,
                "reward_promotion_state": str(grade_card.get("promotion_state") or ""),
            }
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            trial_result.error = error
            proposal.actual_fitness = FitnessScore(safety=0.0)
            proposal.gate_decision = GateDecision.BLOCK.value
            proposal.gate_reason = error
            proposal.promotion_state = PromotionState.CANDIDATE.value
            proposal.test_results["runtime_field_trial"] = {
                "mutated_fields": list(trial_result.applied_fields),
                "before": dict(trial_result.before),
                "after": dict(trial_result.after),
                "error": error,
            }
        finally:
            rollback_runtime_field_trial(registry, trial_result)
            proposal.test_results.setdefault("runtime_field_trial", {})
            proposal.test_results["runtime_field_trial"]["rolled_back"] = (
                trial_result.rolled_back
            )

        archive_entry_id = await self.archive_result(proposal)
        return RuntimeFieldEvolutionResult(
            proposal=proposal,
            archive_entry_id=archive_entry_id,
            trial_result=trial_result,
            reward_signal=reward_signal,
        )

    def propose_curriculum_tasks(
        self,
        *,
        report: Any,
        reward_signal: Any,
        curriculum_engine: Any | None = None,
    ) -> list[Any]:
        """Explicitly derive frontier tasks from a poor or uncertain research result."""

        if curriculum_engine is None:
            from dharma_swarm.curriculum_engine import CurriculumEngine

            curriculum_engine = CurriculumEngine()
        return list(
            curriculum_engine.derive_frontier_tasks(
                report=report,
                reward_signal=reward_signal,
            )
        )

    # -- full cycle ----------------------------------------------------------

    async def run_cycle(self, proposals: list[Proposal]) -> CycleResult:
        """Execute a full evolution cycle on a batch of proposals.

        For each proposal: gate-check, and if it passes, evaluate and
        archive. Tracks aggregate statistics.

        Respects the daily mutation budget (default 5/day). When exhausted,
        the cycle evaluates existing population only — no new mutations.

        Args:
            proposals: List of proposals to process.

        Returns:
            A ``CycleResult`` summarising the cycle.
        """
        # Check and reset daily mutation budget
        from datetime import date
        today = date.today().isoformat()
        if self._budget_reset_date != today:
            self._mutations_today = 0
            self._budget_reset_date = today

        if self._mutations_today >= self._daily_mutation_budget:
            logger.warning(
                "Daily mutation budget exhausted (%d/%d). "
                "Skipping mutations, eval-only mode.",
                self._mutations_today,
                self._daily_mutation_budget,
            )
            proposals = []  # Empty proposals = eval-only

        start = time.monotonic()
        plan = await self.plan_cycle(proposals)
        result = CycleResult(
            proposals_submitted=len(proposals),
            plan_id=plan.id,
        )
        best_fitness = 0.0
        new_entries: list[ArchiveEntry] = []
        proposal_by_id = {p.id: p for p in proposals}
        failure_streaks: dict[str, int] = defaultdict(int)

        # Stage execution context for all proposals
        ordered_proposals: list[Proposal] = []
        proposal_targets: dict[str, tuple[ResolvedExecutionProfile, Path | None]] = {}
        for proposal_id in plan.ordered_proposal_ids:
            proposal = proposal_by_id[proposal_id]
            target, source_file = self._resolve_cycle_execution_target(proposal.component)
            self._stage_execution_context(
                proposal,
                target,
                cycle_id=result.cycle_id,
            )
            ordered_proposals.append(proposal)
            proposal_targets[proposal.id] = (target, source_file)

        # Phase 4: parallel gate-check all proposals
        await asyncio.gather(
            *(self.gate_check(p) for p in ordered_proposals)
        )

        for proposal in ordered_proposals:
            if proposal.status == EvolutionStatus.REJECTED:
                await self._trip_circuit_breaker_if_needed(
                    proposal=proposal,
                    failure_streaks=failure_streaks,
                    cycle=result,
                )
                continue

            result.proposals_gated += 1
            target, source_file = proposal_targets[proposal.id]
            code = self._read_component_code(source_file)
            test_results: dict[str, Any] | None = None

            if target.test_command is not None:
                if proposal.diff.strip():
                    proposal, test_results = await self.apply_diff_and_test(
                        proposal,
                        test_command=target.test_command,
                        timeout=target.timeout or 60.0,
                        workspace=target.workspace,
                    )
                    code = self._read_component_code(
                        self._resolve_component_source_path(
                            proposal.component,
                            workspace=target.workspace,
                        )
                    )
                    if test_results.get("rolled_back"):
                        logger.warning(
                            "Proposal %s diff rolled back after test failure",
                            proposal.id,
                        )
                else:
                    proposal, sr = await self.apply_in_sandbox(
                        proposal,
                        test_command=target.test_command,
                        timeout=target.timeout or 60.0,
                        workspace=target.workspace,
                    )
                    test_results = self._parse_sandbox_result(sr)

            # Evaluate
            await self.evaluate(proposal, test_results=test_results, code=code)
            result.proposals_tested += 1

            # Quality gate: reject low-quality proposals before archiving
            if self._quality_gate_enabled:
                qg_result = await self._run_quality_gate(proposal)
                self.last_quality_gate_result = qg_result
                if not qg_result.passed:
                    proposal.status = EvolutionStatus.REJECTED
                    proposal.gate_reason = (
                        f"quality_gate: {qg_result.reason} "
                        f"(score={qg_result.score.overall:.1f}, "
                        f"threshold={qg_result.threshold:.1f})"
                    )
                    logger.info(
                        "Proposal %s rejected by quality gate: %s",
                        proposal.id,
                        qg_result.reason,
                    )
                    await self._trip_circuit_breaker_if_needed(
                        proposal=proposal,
                        failure_streaks=failure_streaks,
                        cycle=result,
                    )
                    continue

            # Archive
            entry_id = await self.archive_result(proposal)
            result.proposals_archived += 1
            self._mutations_today += 1
            archived_entry = await self.archive.get_entry(entry_id)
            if archived_entry is not None:
                new_entries.append(archived_entry)

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
        await self._emit_coalgebra_observation(result, proposals, new_entries)

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

        # Log trace (fire-and-forget)
        self._trace_bg(
            TraceEntry(
                agent="darwin_engine",
                action="apply_diff_and_test",
                state="pass" if result.tests_passed else "fail",
                metadata={
                    "proposal_id": proposal.id,
                    "workspace": str(applier.workspace),
                    "test_command": test_command,
                    "timeout": timeout,
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
        workspace: Path | None = None,
    ) -> tuple[Proposal, SandboxResult]:
        """Run a test command in a sandbox and record the result.

        Sets the proposal through WRITING -> TESTING status transitions,
        executes the command in a :class:`LocalSandbox`, and logs a trace.

        Args:
            proposal: The gated proposal to test.
            test_command: Shell command to run inside the sandbox.
            timeout: Maximum seconds before the command is killed.
            workspace: Optional working directory for sandbox execution.

        Returns:
            A tuple of ``(proposal, SandboxResult)``.
        """
        from dharma_swarm.sandbox import LocalSandbox

        proposal.status = EvolutionStatus.WRITING
        sandbox = LocalSandbox(
            workdir=Path(workspace).resolve() if workspace is not None else None
        )
        try:
            proposal.status = EvolutionStatus.TESTING
            result = await sandbox.execute(test_command, timeout=timeout)

            # Log trace (fire-and-forget)
            self._trace_bg(
                TraceEntry(
                    agent="darwin_engine",
                    action="sandbox_test",
                    state=proposal.status.value,
                    metadata={
                        "proposal_id": proposal.id,
                        "workspace": str(sandbox.workdir),
                        "test_command": test_command,
                        "timeout": timeout,
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
        new_entries: list[ArchiveEntry] = []
        proposal_by_id = {p.id: p for p in proposals}
        failure_streaks: dict[str, int] = defaultdict(int)

        # Stage execution context and resolve targets for all proposals
        ordered_proposals: list[Proposal] = []
        proposal_targets: dict[str, Any] = {}
        for proposal_id in plan.ordered_proposal_ids:
            proposal = proposal_by_id[proposal_id]
            target = self.resolve_execution_target(
                proposal.component,
                fallback_test_command=test_command,
                fallback_timeout=timeout,
                fallback_evidence_tier=EvidenceTier.LOCAL,
                fallback_profile_name="local_default",
                fallback_expected_metrics=["pass_rate"],
                fallback_rollback_policy="revert_patch",
            )
            self._stage_execution_context(proposal, target, cycle_id=result.cycle_id)
            ordered_proposals.append(proposal)
            proposal_targets[proposal.id] = target

        # Phase 4: parallel gate-check all proposals
        await asyncio.gather(
            *(self.gate_check(p) for p in ordered_proposals)
        )

        for proposal in ordered_proposals:
            if proposal.status == EvolutionStatus.REJECTED:
                await self._trip_circuit_breaker_if_needed(
                    proposal=proposal,
                    failure_streaks=failure_streaks,
                    cycle=result,
                )
                continue

            result.proposals_gated += 1
            target = proposal_targets[proposal.id]

            # Apply diff (if present) then sandbox test
            if proposal.diff.strip():
                proposal, test_results = await self.apply_diff_and_test(
                    proposal,
                    test_command=target.test_command or test_command,
                    timeout=target.timeout or timeout,
                    workspace=target.workspace,
                )
                if test_results.get("rolled_back"):
                    logger.warning(
                        "Proposal %s diff rolled back after test failure",
                        proposal.id,
                    )
            else:
                proposal, sr = await self.apply_in_sandbox(
                    proposal,
                    test_command=target.test_command or test_command,
                    timeout=target.timeout or timeout,
                    workspace=target.workspace,
                )
                test_results = self._parse_sandbox_result(sr)

            # Evaluate with test results
            await self.evaluate(proposal, test_results=test_results)
            result.proposals_tested += 1

            # Archive
            entry_id = await self.archive_result(proposal)
            result.proposals_archived += 1
            self._mutations_today += 1
            archived_entry = await self.archive.get_entry(entry_id)
            if archived_entry is not None:
                new_entries.append(archived_entry)

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
        await self._emit_coalgebra_observation(result, proposals, new_entries)

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
            selected = await self.ucb_selector.select_parent(
                self.archive,
                weights=self._fitness_weights,
            )
        else:
            selected = await select_parent(
                self.archive,
                strategy=strategy,
                weights=self._fitness_weights,
                **kwargs,
            )

        await self.refresh_experiment_memory()
        if selected is None or self.last_experiment_memory is None:
            return selected

        candidates = await self.archive.get_best(n=5, weights=self._fitness_weights)
        if not candidates:
            return selected
        if all(candidate.id != selected.id for candidate in candidates):
            candidates.append(selected)

        # C11: When diversity is critical, prefer cross-family candidates
        if self._diversity_boost_active and selected.model:
            selected_family = selected.model.split("/")[0]
            cross = [
                c for c in candidates
                if c.model and c.model.split("/")[0] != selected_family
            ]
            if cross:
                best_cross = max(cross, key=self._parent_memory_score)
                logger.debug(
                    "C11: Cross-family parent override: %s → %s",
                    selected.model,
                    best_cross.model,
                )
                return best_cross

        best = max(candidates, key=self._parent_memory_score)
        if self._parent_memory_score(best) > (self._parent_memory_score(selected) * 1.05):
            return best
        return selected

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
        model: str = "",
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
        if not model:
            from dharma_swarm.model_hierarchy import default_model as _dm
            from dharma_swarm.models import ProviderType as _PT
            model = _dm(_PT.OPENROUTER)

        if not source_file.exists():
            logger.warning("Source file not found: %s", source_file)
            return None

        source = source_file.read_text(encoding="utf-8")

        # Phase 4: content-hash skip — don't re-propose for unchanged files
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_key = str(source_file.resolve())
        if self._file_hashes.get(file_key) == source_hash:
            logger.debug("Skipping unchanged file: %s", source_file.name)
            return None
        self._file_hashes[file_key] = source_hash

        if len(source) > 15_000:
            source = source[:15_000] + "\n# ... truncated ..."

        component_key = self._component_key_for_source_file(source_file)
        target = self.resolve_execution_target(
            component_key,
            fallback_test_command=None,
            fallback_timeout=None,
            fallback_workspace=None,
            fallback_evidence_tier=EvidenceTier.UNVALIDATED,
            fallback_profile_name="llm_default",
            fallback_expected_metrics=[],
            fallback_rollback_policy="discard",
        )
        strategy = self._current_adaptive_strategy()
        mutation_rate = self.get_contextual_mutation_rate(
            component=component_key,
            profile_name=target.profile_name,
        )
        mutation_budget = self.get_mutation_budget_lines(
            component=component_key,
            profile_name=target.profile_name,
        )
        # Compute relative path from workspace root so the LLM produces
        # correct diff headers (e.g. --- a/dharma_swarm/selector.py)
        try:
            file_rel_path = str(source_file.relative_to(Path.cwd()))
        except ValueError:
            try:
                file_rel_path = str(source_file.relative_to(Path.home() / "dharma_swarm"))
            except ValueError:
                file_rel_path = source_file.name

        user_msg = (
            "## Mutation Envelope\n"
            f"- mutation_rate: {mutation_rate:.3f}\n"
            f"- diff_budget_lines: {mutation_budget}\n"
            f"- adaptive_strategy: {strategy}\n"
            f"- execution_profile: {target.profile_name}\n\n"
            f"## File: {file_rel_path}\n\n```python\n{source}\n```"
        )
        if context:
            user_msg = f"## Context\n{context}\n\n{user_msg}"

        request = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": user_msg}],
            system=self._build_propose_system(
                component=component_key,
                profile_name=target.profile_name,
            ),
            max_tokens=2048,
            temperature=min(1.0, max(0.3, 0.4 + mutation_rate)),
        )

        # Token budget check
        if (
            self._max_cycle_tokens > 0
            and self._session_tokens_used >= self._max_cycle_tokens
        ):
            logger.warning(
                "Token budget exhausted (%d/%d) — skipping proposal for %s",
                self._session_tokens_used,
                self._max_cycle_tokens,
                source_file.name,
            )
            return None

        try:
            response = await provider.complete(request)
        except Exception as exc:
            logger.error("LLM proposal generation failed: %s", exc)
            return None

        # Track token usage
        tokens_used = int(
            response.usage.get("total_tokens")
            or (
                response.usage.get("prompt_tokens", 0)
                + response.usage.get("completion_tokens", 0)
                + response.usage.get("input_tokens", 0)
                + response.usage.get("output_tokens", 0)
            )
            or 0
        )
        self._session_tokens_used += tokens_used

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

        self._trace_bg(
            TraceEntry(
                agent="darwin_engine",
                action="llm_generate_proposal",
                state="generated",
                metadata={
                    "proposal_id": proposal.id,
                    "source_file": str(source_file),
                    "execution_profile": target.profile_name,
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

    # -- pending proposals (from consolidation / skill bridge) ----------------

    _PENDING_PROPOSALS_PATH = PENDING_PROPOSALS_FILE

    def load_pending_proposals(self) -> list[Proposal]:
        """Load and clear pending proposals written by consolidation or skill bridge.

        Returns a list of Proposal objects.  The file is truncated after reading
        so proposals are consumed exactly once.
        """
        path = self._PENDING_PROPOSALS_PATH
        if not path.exists():
            return []
        proposals: list[Proposal] = []
        try:
            import json as _pp_json
            lines = path.read_text().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = _pp_json.loads(line)
                    proposals.append(Proposal(**data))
                except Exception as exc:
                    logger.warning("Skipping malformed pending proposal: %s", exc)
            # Truncate after successful read
            path.write_text("")
        except Exception as exc:
            logger.warning("Failed to load pending proposals: %s", exc)
        return proposals

    async def auto_evolve(
        self,
        provider: Any,
        source_files: list[Path],
        model: str = "",
        test_command: str = "python3 -m pytest tests/ -q --tb=short -x --timeout=10",
        timeout: float = 60.0,
        context: str = "",
        router: Any | None = None,
        shadow: bool = False,
        on_progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> CycleResult:
        """Autonomous evolution: LLM proposes improvements, engine evaluates them.

        For each source file, generates a proposal via LLM, then runs the
        full gate → test → evaluate → archive pipeline.

        When *router* is provided, the engine uses the evolution roster to
        assign a different model (and provider) to each source file based
        on the current adaptive strategy.  This produces more diverse
        proposals across frontier, strong, fast, free, and local tiers.

        When *shadow* is True, proposals are generated, gated, and evaluated,
        but diffs are NOT applied to the real codebase.  Useful for safe
        experimentation and cost estimation.

        Args:
            provider: Fallback LLM provider with async ``complete()`` method.
            source_files: List of Python files to propose improvements for.
            model: Fallback model identifier (used when roster is unavailable).
            test_command: Shell command for testing proposals.
            timeout: Fallback timeout for component test execution.
            context: Extra context to guide the LLM (focus areas, recent errors).
            router: Optional ModelRouter for multi-model roster selection.
            shadow: If True, do not apply diffs — evaluate proposals in dry-run mode.
            on_progress: Optional callback ``(event_name, data)`` for real-time UX.

        Returns:
            A CycleResult summarizing the autonomous evolution cycle.
        """
        _emit = on_progress or (lambda _e, _d: None)

        if not model:
            from dharma_swarm.model_hierarchy import default_model as _dm
            from dharma_swarm.models import ProviderType as _PT
            model = _dm(_PT.OPENROUTER)

        await self.refresh_experiment_memory()
        # C11: Drain diversity signals before each cycle — adjusts mutation
        # pressure and parent selection when diversity is critical.
        self.drain_diversity_signals()
        _emit("cycle_start", {
            "files": [str(sf) for sf in source_files],
            "shadow": shadow,
            "strategy": self._current_adaptive_strategy(),
        })

        # ── Multi-model roster selection ──────────────────────────────
        if router is not None:
            from dharma_swarm.evolution_roster import select_models_for_cycle
            strategy = self._current_adaptive_strategy()
            slots = select_models_for_cycle(
                n=len(source_files), strategy=strategy,
            )
            file_assignments = list(zip(source_files, slots))
            logger.info(
                "Multi-model cycle (strategy=%s): %s",
                strategy,
                ", ".join(
                    f"{sf.name}→{slot.display_name}"
                    for sf, slot in file_assignments
                ),
            )
        else:
            file_assignments = None

        # Phase 4: parallel LLM dispatch — all files hit providers simultaneously
        async def _generate_one(idx: int, sf: Path) -> Proposal | None:
            if file_assignments is not None:
                _, slot = file_assignments[idx]
                try:
                    file_provider = router.get_provider(slot.provider)
                    file_model = slot.model_id
                except KeyError:
                    logger.warning(
                        "Provider %s unavailable for %s — falling back",
                        slot.provider.value, slot.display_name,
                    )
                    file_provider = provider
                    file_model = model
            else:
                file_provider = provider
                file_model = model

            return await self.generate_proposal(
                provider=file_provider,
                source_file=sf,
                context=context,
                model=file_model,
            )

        _emit("proposals_generating", {"count": len(source_files)})
        results = await asyncio.gather(
            *(_generate_one(idx, sf) for idx, sf in enumerate(source_files)),
            return_exceptions=True,
        )
        proposals: list[Proposal] = []
        for r in results:
            if isinstance(r, BaseException):
                logger.error("Parallel proposal generation failed: %s", r)
            elif r is not None:
                proposals.append(r)

        _emit("proposals_generated", {
            "count": len(proposals),
            "skipped": len(source_files) - len(proposals),
        })

        if not proposals:
            logger.info("No proposals generated — nothing to evolve")
            return CycleResult(proposals_submitted=0)

        if shadow:
            # Shadow mode: gate and evaluate without applying diffs
            logger.info("Shadow mode: evaluating %d proposals (no diffs applied)", len(proposals))
            for p in proposals:
                p.diff = ""  # Strip diffs so sandbox doesn't apply them
            result = await self.run_cycle(proposals)
        else:
            result = await self.run_cycle_with_sandbox(
                proposals,
                test_command=test_command,
                timeout=timeout,
            )

        _emit("cycle_complete", {
            "proposals": result.proposals_submitted,
            "archived": result.proposals_archived,
            "best_fitness": result.best_fitness,
            "duration": result.duration_seconds,
            "tokens": self._session_tokens_used,
            "shadow": shadow,
        })
        logger.info(
            "Auto-evolve complete%s: %d files → %d proposals → %d archived (best=%.3f)",
            " [SHADOW]" if shadow else "",
            len(source_files),
            result.proposals_submitted,
            result.proposals_archived,
            result.best_fitness,
        )
        return result

    # -- auto-commit ---------------------------------------------------------

    async def commit_if_worthy(
        self,
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
        model: str = "",
        interval: float = 1800.0,
        fitness_threshold: float = 0.6,
        max_cycles: int | None = None,
        router: Any | None = None,
        shadow: bool = False,
        on_progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Run autonomous evolution continuously.

        Each cycle:
        1. Pick source files to evolve
        2. Generate proposals via LLM — multi-model when router is provided
        3. Gate-check, apply diffs, run tests
        4. Evaluate fitness, archive
        5. Auto-commit if fitness > threshold (skipped in shadow mode)
        6. Sleep, repeat

        Args:
            think_provider: Fallback LLM provider for proposal generation.
            source_dir: Directory containing Python source files.
            model: Fallback model for proposal generation.
            interval: Seconds between cycles.
            fitness_threshold: Minimum fitness to auto-commit.
            max_cycles: Stop after N cycles (None = run forever).
            router: Optional ModelRouter for multi-model roster selection.
            shadow: If True, do not apply diffs or commit.
            on_progress: Optional callback ``(event_name, data)`` for real-time UX.
        """
        if not model:
            from dharma_swarm.model_hierarchy import default_model as _dm
            from dharma_swarm.models import ProviderType as _PT
            model = _dm(_PT.OPENROUTER)

        src = source_dir or (Path.home() / "dharma_swarm" / "dharma_swarm")
        cycle_count = 0
        context_parts: list[str] = []

        if router is not None:
            from dharma_swarm.evolution_roster import roster_summary
            logger.info(
                "Darwin daemon starting (MULTI-MODEL): interval=%.0fs, "
                "threshold=%.2f, src=%s\n%s",
                interval, fitness_threshold, src, roster_summary(),
            )
        else:
            logger.info(
                "Darwin daemon starting: interval=%.0fs, threshold=%.2f, "
                "model=%s, src=%s",
                interval, fitness_threshold, model, src,
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
                    router=router,
                    shadow=shadow,
                    on_progress=on_progress,
                )

                # Auto-commit winning proposals (skip in shadow mode)
                committed = 0
                if not shadow and result.proposals_archived > 0:
                    recent = await self.archive.get_latest(result.proposals_archived)
                    for entry in recent:
                        if self.score_fitness(entry.fitness) >= fitness_threshold:
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

                # Check token budget exhaustion
                if (
                    self._max_cycle_tokens > 0
                    and self._session_tokens_used >= self._max_cycle_tokens
                ):
                    logger.info(
                        "Token budget exhausted (%d/%d) — stopping daemon",
                        self._session_tokens_used,
                        self._max_cycle_tokens,
                    )
                    break

                logger.info(
                    "Daemon cycle %d complete: %d proposals, %d archived, "
                    "%d committed, best=%.3f, tokens=%d",
                    cycle_count,
                    result.proposals_submitted,
                    result.proposals_archived,
                    committed,
                    result.best_fitness,
                    self._session_tokens_used,
                )

            except Exception as exc:
                logger.exception("Daemon cycle %d failed: %s", cycle_count, exc)

            if max_cycles is not None and cycle_count >= max_cycles:
                break
            await asyncio.sleep(interval)
