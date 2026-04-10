"""Local landscape probing for Darwin Engine."""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from statistics import mean, pvariance
from typing import TYPE_CHECKING

from pydantic import BaseModel

from dharma_swarm.archive import ArchiveEntry

if TYPE_CHECKING:
    from dharma_swarm.evolution import DarwinEngine


class BasinType(str, Enum):
    """Local basin categories in the fitness landscape."""

    ASCENDING = "ascending"
    PLATEAU = "plateau"
    DESCENDING = "descending"
    LOCAL_OPTIMUM = "local_optimum"
    UNKNOWN = "unknown"


class LandscapeProbe(BaseModel):
    """Observed neighborhood structure around a parent entry."""

    parent_id: str
    parent_component: str = ""
    parent_fitness: float
    neighbor_fitness: list[float]
    gradient: float
    variance: float
    basin_type: BasinType


class FitnessLandscapeMapper:
    """Map a local neighborhood around a parent entry."""

    def __init__(
        self,
        darwin: DarwinEngine,
        n_samples: int = 10,
        gradient_threshold: float = 0.05,
        variance_threshold: float = 0.01,
        seed: int | None = None,
    ) -> None:
        self.darwin = darwin
        self.n_samples = max(1, int(n_samples))
        self.gradient_threshold = float(gradient_threshold)
        self.variance_threshold = float(variance_threshold)
        self._rng = random.Random(seed)

    async def probe_landscape(
        self,
        parent: ArchiveEntry,
        weights: dict[str, float] | None = None,
        workspace: Path | None = None,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> LandscapeProbe:
        """Sample neighboring fitness values and classify the basin."""
        parent_fitness = parent.fitness.weighted(weights=weights)
        neighbors = [
            await self._sample_neighbor_fitness(
                parent,
                weights=weights,
                workspace=workspace,
                test_command=test_command,
                timeout=timeout,
            )
            for _ in range(self.n_samples)
        ]
        deltas = [fitness - parent_fitness for fitness in neighbors]
        gradient = mean(deltas) if deltas else 0.0
        variance = pvariance(neighbors) if len(neighbors) > 1 else 0.0
        basin_type = self._classify_basin(gradient, variance)
        return LandscapeProbe(
            parent_id=parent.id,
            parent_component=parent.component,
            parent_fitness=parent_fitness,
            neighbor_fitness=neighbors,
            gradient=gradient,
            variance=variance,
            basin_type=basin_type,
        )

    async def _sample_neighbor_fitness(
        self,
        parent: ArchiveEntry,
        weights: dict[str, float] | None = None,
        workspace: Path | None = None,
        test_command: str = "python3 -m pytest tests/ -q --tb=short",
        timeout: float = 60.0,
    ) -> float:
        """Generate a real neighbor proposal and score it through Darwin."""
        proposal = await self._build_neighbor_proposal(parent, workspace=workspace)
        if workspace is None:
            await self.darwin.gate_check(proposal)
            await self.darwin.evaluate(
                proposal,
                test_results={"pass_rate": parent.fitness.correctness},
            )
        else:
            proposal = await self.darwin.evaluate_probe_proposal(
                proposal,
                workspace=workspace,
                test_command=test_command,
                timeout=timeout,
            )
        return self._score_neighbor(proposal, weights=weights)

    async def _build_neighbor_proposal(
        self,
        parent: ArchiveEntry,
        workspace: Path | None = None,
    ):
        """Construct a nearby proposal around an archived parent."""
        component = parent.component or "probe.py"
        description = f"Landscape probe for {component}"
        think_notes = (
            "Risk: low. Purpose: probe local fitness neighborhood. "
            "Rollback: discard probe proposal."
        )
        diff = self._build_neighbor_diff(
            parent,
            component=component,
            workspace=workspace,
        )
        return await self.darwin.propose(
            component=component,
            change_type=parent.change_type or "mutation",
            description=description,
            diff=diff,
            parent_id=parent.id,
            spec_ref=parent.spec_ref,
            requirement_refs=list(parent.requirement_refs),
            think_notes=think_notes,
        )

    def _build_neighbor_diff(
        self,
        parent: ArchiveEntry,
        component: str,
        workspace: Path | None = None,
    ) -> str:
        """Create a bounded diff-like perturbation guided by mutation rate."""
        if workspace is not None:
            workspace_diff = self._build_workspace_neighbor_diff(
                component=component,
                workspace=workspace,
            )
            if workspace_diff:
                return workspace_diff

        mutation_rate = self.darwin.get_active_mutation_rate()
        base_body = [
            line
            for line in parent.diff.splitlines()
            if line.strip() and not line.startswith(("---", "+++", "@@"))
        ]
        if not base_body:
            base_body = ["+ probe change"]

        base_size = max(1, len(base_body))
        span = max(1, round(base_size * mutation_rate))
        target_size = max(1, base_size + self._rng.randint(-span, span))

        body: list[str] = base_body[:target_size]
        while len(body) < target_size:
            body.append(f"+ probe mutation {len(body)}")

        header = [f"--- a/{component}", f"+++ b/{component}", "@@"]
        return "\n".join(header + body)

    def _build_workspace_neighbor_diff(self, component: str, workspace: Path) -> str:
        """Generate a real unified diff from a workspace file snapshot."""
        workspace_root = Path(workspace).resolve()
        candidate = (workspace_root / component).resolve()
        try:
            candidate.relative_to(workspace_root)
        except ValueError:
            return ""

        if not candidate.exists() or not candidate.is_file():
            return ""

        original = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        mutated = list(original)
        mutation_rate = self.darwin.get_active_mutation_rate()
        n_mutations = max(1, round(1 + (mutation_rate * 4)))
        for idx in range(n_mutations):
            mutated.append(self._probe_line_for_component(component, idx))

        diff_lines = list(
            difflib.unified_diff(
                original,
                mutated,
                fromfile=f"a/{component}",
                tofile=f"b/{component}",
                lineterm="",
            )
        )
        return "\n".join(diff_lines)

    @staticmethod
    def _probe_line_for_component(component: str, idx: int) -> str:
        suffix = Path(component).suffix.lower()
        if suffix in {".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cc", ".cpp", ".rs", ".go"}:
            return f"// probe mutation {idx}"
        if suffix == ".sql":
            return f"-- probe mutation {idx}"
        if suffix in {".md", ".txt", ".rst"}:
            return f"probe mutation {idx}"
        return f"# probe mutation {idx}"

    def _score_neighbor(
        self,
        proposal,
        weights: dict[str, float] | None = None,
    ) -> float:
        if proposal.actual_fitness is None:
            return 0.0
        if weights is None:
            return self.darwin.score_fitness(proposal.actual_fitness)
        return proposal.actual_fitness.weighted(weights=weights)

    def _classify_basin(self, gradient: float, variance: float) -> BasinType:
        """Classify the local neighborhood by gradient and variance."""
        if gradient > self.gradient_threshold:
            return BasinType.ASCENDING
        if gradient < -self.gradient_threshold:
            return BasinType.DESCENDING
        if variance < self.variance_threshold:
            return BasinType.PLATEAU
        return BasinType.LOCAL_OPTIMUM

    @staticmethod
    def get_adaptive_strategy(basin_type: BasinType) -> str:
        """Map a basin type to an engine strategy hint."""
        strategies = {
            BasinType.ASCENDING: "exploit",
            BasinType.PLATEAU: "explore",
            BasinType.LOCAL_OPTIMUM: "restart",
            BasinType.DESCENDING: "backtrack",
            BasinType.UNKNOWN: "explore",
        }
        return strategies.get(basin_type, "explore")


# ---------------------------------------------------------------------------
# FitnessLandscapeMap — time-series tracking per component type
# ---------------------------------------------------------------------------


class LandscapeEvent(str, Enum):
    """Detected event in a component's fitness trajectory."""

    NONE = "none"
    PLATEAU = "plateau"        # fitness stuck for >= plateau_window cycles
    REGRESSION = "regression"  # fitness dropped >= regression_pct from recent peak
    BREAKTHROUGH = "breakthrough"  # fitness jumped >= breakthrough_pct


@dataclass
class ComponentLandscapeState:
    """Per-component fitness history and current event."""

    component_type: str
    scores: list[float] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    event: LandscapeEvent = field(default=LandscapeEvent.NONE)
    event_detail: str = ""
    peak_score: float = 0.0
    trough_score: float = 1.0

    def record(self, score: float, ts: str = "") -> None:
        """Append a new fitness score and update peak/trough."""
        self.scores.append(score)
        self.timestamps.append(ts)
        if score > self.peak_score:
            self.peak_score = score
        if score < self.trough_score:
            self.trough_score = score

    def recent_mean(self, window: int) -> float:
        """Mean fitness over the last *window* scores."""
        tail = self.scores[-window:]
        return mean(tail) if tail else 0.0


class FitnessLandscapeMap:
    """Track fitness scores over time per component type.

    Detects three landscape events:
    - **plateau**: fitness variance is below threshold for >= plateau_window cycles.
    - **regression**: current score dropped >= regression_pct from recent peak.
    - **breakthrough**: current score jumped >= breakthrough_pct from recent mean.

    Usage::

        lmap = FitnessLandscapeMap()
        lmap.record(component_type="swarm", score=0.72)
        summary = lmap.landscape_summary()
    """

    def __init__(
        self,
        plateau_window: int = 5,
        plateau_variance_threshold: float = 0.005,
        regression_pct: float = 0.20,
        breakthrough_pct: float = 0.30,
    ) -> None:
        self.plateau_window = max(2, int(plateau_window))
        self.plateau_variance_threshold = float(plateau_variance_threshold)
        self.regression_pct = float(regression_pct)
        self.breakthrough_pct = float(breakthrough_pct)
        self._states: dict[str, ComponentLandscapeState] = {}

    def record(
        self,
        component_type: str,
        score: float,
        ts: str = "",
    ) -> LandscapeEvent:
        """Record a fitness score for a component and return the detected event.

        Args:
            component_type: Logical category of the component (e.g. "swarm", "agent").
            score: Weighted fitness score in [0, 1].
            ts: ISO timestamp string; defaults to empty string.

        Returns:
            The :class:`LandscapeEvent` detected after recording this score.
        """
        score = max(0.0, min(1.0, float(score)))
        if component_type not in self._states:
            self._states[component_type] = ComponentLandscapeState(
                component_type=component_type
            )
        state = self._states[component_type]
        prev_scores = list(state.scores)
        state.record(score, ts)

        event = self._detect_event(state, score, prev_scores)
        state.event = event
        state.event_detail = self._event_detail(event, state, score)
        return event

    def _detect_event(
        self,
        state: ComponentLandscapeState,
        new_score: float,
        prev_scores: list[float],
    ) -> LandscapeEvent:
        """Determine which event, if any, occurred at this score."""
        if len(state.scores) < 2:
            return LandscapeEvent.NONE

        # Breakthrough: jumped >= breakthrough_pct above recent mean (before this score)
        if prev_scores:
            prev_mean = mean(prev_scores[-self.plateau_window:])
            if prev_mean > 0.0 and (new_score - prev_mean) / prev_mean >= self.breakthrough_pct:
                return LandscapeEvent.BREAKTHROUGH

        # Regression: dropped >= regression_pct below recent peak
        if state.peak_score > 0.0:
            drop_frac = (state.peak_score - new_score) / state.peak_score
            if drop_frac >= self.regression_pct:
                return LandscapeEvent.REGRESSION

        # Plateau: last plateau_window scores have near-zero variance
        window = state.scores[-self.plateau_window:]
        if len(window) >= self.plateau_window:
            var = pvariance(window)
            if var < self.plateau_variance_threshold:
                return LandscapeEvent.PLATEAU

        return LandscapeEvent.NONE

    @staticmethod
    def _event_detail(
        event: LandscapeEvent,
        state: ComponentLandscapeState,
        score: float,
    ) -> str:
        """Human-readable detail string for an event."""
        if event == LandscapeEvent.PLATEAU:
            return (
                f"Plateau detected over last {len(state.scores)} scores "
                f"(mean={state.recent_mean(len(state.scores)):.3f})"
            )
        if event == LandscapeEvent.REGRESSION:
            drop_pct = (state.peak_score - score) / max(state.peak_score, 1e-9) * 100
            return f"Regression {drop_pct:.1f}% from peak {state.peak_score:.3f}"
        if event == LandscapeEvent.BREAKTHROUGH:
            return f"Breakthrough to {score:.3f} (new high {state.peak_score:.3f})"
        return ""

    def get_state(self, component_type: str) -> ComponentLandscapeState | None:
        """Return current landscape state for a component type, or None."""
        return self._states.get(component_type)

    def landscape_summary(self) -> dict[str, dict[str, object]]:
        """Return a summary dict of current landscape state per component type.

        Keys are component type strings.  Each value is a dict with:
        - ``event``: current :class:`LandscapeEvent` value string
        - ``event_detail``: human-readable explanation
        - ``peak_score``: highest recorded fitness
        - ``trough_score``: lowest recorded fitness
        - ``n_records``: total number of scores recorded
        - ``recent_mean``: mean of last ``plateau_window`` scores
        """
        summary: dict[str, dict[str, object]] = {}
        for comp_type, state in self._states.items():
            summary[comp_type] = {
                "event": state.event.value,
                "event_detail": state.event_detail,
                "peak_score": round(state.peak_score, 4),
                "trough_score": round(state.trough_score, 4),
                "n_records": len(state.scores),
                "recent_mean": round(state.recent_mean(self.plateau_window), 4),
            }
        return summary
