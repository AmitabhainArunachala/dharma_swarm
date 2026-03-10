"""Local landscape probing for Darwin Engine."""

from __future__ import annotations

import difflib
import random
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
        gradient_threshold: float = 0.1,
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
