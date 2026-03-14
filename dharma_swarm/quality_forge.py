"""Quality Forge -- unified artifact scorer with self-referential measurement.

Composes elegance (AST), behavioral (entropy/complexity/swabhaav), and telos
gate checks into a single ForgeScore. The strange loop: ``self_score()``
calls ``score_artifact(Path(__file__))`` -- the system scores itself.

Integration points:
    - elegance.evaluate_elegance (AST analysis)
    - ouroboros.score_behavioral_fitness (entropy, complexity, mimicry)
    - telos_gates.TelosGatekeeper (dharmic alignment)
    - archive.FitnessScore (evolution pipeline projection)
    - models.ForgeScore (output schema)
"""

from __future__ import annotations

import logging
from pathlib import Path

from dharma_swarm.archive import FitnessScore
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.metrics import MetricsAnalyzer
from dharma_swarm.models import ForgeScore, GateDecision
from dharma_swarm.ouroboros import score_behavioral_fitness
from dharma_swarm.telos_gates import TelosGatekeeper

logger = logging.getLogger(__name__)


class QualityForge:
    """Multi-dimensional quality scorer that composes existing analysis tools.

    Produces a ForgeScore by running an artifact through three pipelines:
        1. Elegance -- AST-based structural quality (cyclomatic complexity,
           nesting, docstring coverage, naming conventions).
        2. Behavioral -- text-level analysis (entropy, compression complexity,
           swabhaav ratio, mimicry detection).
        3. Telos gate -- dharmic alignment check (AHIMSA, SATYA, etc.).

    The composite ForgeScore contains:
        - stars: weighted overall score [0, 10]
        - yosemite: difficulty-adjusted quality grade [5.0, 5.15]
        - dharmic: telos alignment score [0, 10]
        - efficiency: quality-per-token estimate
        - elegance_sub: raw elegance sub-score [0, 1]
        - behavioral_sub: raw behavioral quality sub-score [0, 1]

    The strange loop: ``self_score()`` scores this very file, making the
    system a fixed-point evaluator of its own quality.

    Args:
        threshold: Minimum ``stars`` value below which evolution is needed.
    """

    def __init__(self, *, threshold: float = 6.0) -> None:
        self.threshold = threshold
        self._analyzer = MetricsAnalyzer()
        self._gatekeeper = TelosGatekeeper()

    def score_artifact(self, path: Path) -> ForgeScore:
        """Score a Python source file through the full forge pipeline.

        Args:
            path: Path to a Python source file.

        Returns:
            ForgeScore with all sub-scores populated.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        source = path.read_text(encoding="utf-8")

        # 1. Elegance (AST analysis)
        elegance = evaluate_elegance(source)
        elegance_sub = elegance.overall  # 0-1

        # 2. Behavioral analysis
        sig, modifiers = score_behavioral_fitness(source, analyzer=self._analyzer)
        behavioral_sub = modifiers["quality"]  # 0-1

        # 3. Gate check
        action_desc = f"Score artifact: {path.name} ({elegance.line_count} lines)"
        gate_result = self._gatekeeper.check(
            action=action_desc,
            content=source[:500],
        )
        # ALLOW and REVIEW both count as passing; only BLOCK fails.
        gate_pass = 0.0 if gate_result.decision == GateDecision.BLOCK else 1.0

        # 4. Compute composite scores
        stars = (0.4 * elegance_sub + 0.3 * behavioral_sub + 0.3 * gate_pass) * 10.0

        # Yosemite: difficulty-adjusted grade
        difficulty = min(1.0, elegance.line_count / 500.0)
        quality = elegance_sub
        yosemite = 5.0 + 0.15 * (difficulty * 0.4 + quality * 0.6) * quality

        # Dharmic score
        witness = modifiers.get("witness_score", 0.0)
        anti_mimicry = 1.0 if modifiers.get("mimicry_penalty", 1.0) >= 1.0 else 0.0
        dharmic = gate_pass * 5.0 + witness * 3.0 + anti_mimicry * 2.0

        # Efficiency (placeholder compute_tokens)
        compute_tokens = elegance.line_count * 10  # rough estimate
        quality_delta = stars / 10.0
        carnot_factor = 0.8
        efficiency = (
            quality_delta / max(compute_tokens * 0.000003, 0.001) * carnot_factor
        )

        return ForgeScore(
            stars=round(stars, 3),
            yosemite=round(yosemite, 4),
            dharmic=round(dharmic, 3),
            efficiency=round(efficiency, 4),
            elegance_sub=round(elegance_sub, 4),
            behavioral_sub=round(behavioral_sub, 4),
        )

    def self_score(self) -> ForgeScore:
        """Score THIS file -- the strange loop.

        Returns:
            ForgeScore for ``quality_forge.py`` itself.
        """
        return self.score_artifact(Path(__file__))

    def needs_evolution(self, score: ForgeScore | None = None) -> bool:
        """Check if score is below threshold, indicating evolution needed.

        Args:
            score: A pre-computed ForgeScore.  If *None*, ``self_score()``
                   is called to obtain one.

        Returns:
            True if ``score.stars < self.threshold``.
        """
        if score is None:
            score = self.self_score()
        return score.stars < self.threshold

    def to_fitness_score(self, forge: ForgeScore) -> FitnessScore:
        """Project ForgeScore onto FitnessScore for archive compatibility.

        Maps forge dimensions into the evolution archive's 8-dimensional
        fitness space so that forge-scored artifacts can participate in the
        Darwin Engine selection pipeline.

        Args:
            forge: A ForgeScore to project.

        Returns:
            FitnessScore with correctness, dharmic_alignment, elegance,
            efficiency, and safety populated from forge values.
        """
        return FitnessScore(
            correctness=forge.stars / 10.0,
            dharmic_alignment=forge.dharmic / 10.0,
            elegance=forge.elegance_sub,
            efficiency=min(1.0, forge.efficiency / 100.0),
            safety=1.0 if forge.dharmic >= 5.0 else forge.dharmic / 5.0,
        )


__all__ = [
    "QualityForge",
]
