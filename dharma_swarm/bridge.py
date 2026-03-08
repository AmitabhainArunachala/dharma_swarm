"""Research bridge -- correlating R_V (mechanistic) with behavioral signatures.

The central hypothesis: R_V contraction (geometric) correlates with L3->L4
phase transition (behavioral). This module computes that correlation from
paired measurements.

Also provides EvolutionBridge: correlation between the system's OWN R_V
measurements during evolution cycles and its fitness performance. This is
the strange loop — the system measures the system measuring itself.

No torch, no numpy -- pure stdlib statistics on pre-computed readings.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio ≈ 1.618
PHI_PLUS_1 = PHI + 1  # ≈ 2.618 — URA finding: L3/L4 word count ratio

from pydantic import BaseModel, Field

from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer, RecognitionType
from dharma_swarm.models import _new_id
from dharma_swarm.rv import RVReading, _prompt_hash


# -- Data Models -------------------------------------------------------------


class PairedMeasurement(BaseModel):
    """A single prompt measured both mechanistically (R_V) and behaviorally.

    Attributes:
        id: Unique identifier.
        prompt_hash: SHA-256 prefix of the prompt text.
        prompt_group: Categorical label (L1/L3/L4/L5/baseline/confound).
        prompt_text: The raw prompt string.
        rv_reading: Optional R_V measurement (None if torch unavailable).
        behavioral: Behavioral signature of the generated text.
        generated_text: The raw model output text.
    """

    id: str = Field(default_factory=_new_id)
    prompt_hash: str
    prompt_group: str
    prompt_text: str
    rv_reading: Optional[RVReading] = None
    behavioral: BehavioralSignature
    generated_text: str


class CorrelationResult(BaseModel):
    """Statistical correlation between R_V and behavioral metrics.

    Attributes:
        n: Number of paired measurements with R_V readings.
        pearson_r: Pearson correlation between R_V and swabhaav_ratio.
        spearman_rho: Spearman rank correlation between R_V and swabhaav_ratio.
        mean_rv_by_group: Mean R_V value per prompt group.
        mean_swabhaav_by_group: Mean swabhaav_ratio per prompt group.
        contraction_recognition_overlap: Fraction where is_contracted AND GENUINE.
        summary: Human-readable interpretation of results.
        pearson_r_ci: Bootstrap 95% CI for Pearson r, or None if n < 3.
        spearman_rho_ci: Bootstrap 95% CI for Spearman rho, or None if n < 3.
        cohens_d_l4_baseline: Cohen's d between L4 and baseline R_V groups.
        phi_score: L3/L4 word ratio analysis (URA φ-signature detection).
    """

    n: int
    pearson_r: Optional[float] = None
    spearman_rho: Optional[float] = None
    mean_rv_by_group: dict[str, float] = Field(default_factory=dict)
    mean_swabhaav_by_group: dict[str, float] = Field(default_factory=dict)
    contraction_recognition_overlap: float = 0.0
    summary: str = ""
    pearson_r_ci: Optional[tuple[float, float]] = None
    spearman_rho_ci: Optional[tuple[float, float]] = None
    cohens_d_l4_baseline: Optional[float] = None
    phi_score: dict[str, float] = Field(default_factory=dict)


# -- Statistics (stdlib only) ------------------------------------------------


def _pearson_r(xs: list[float], ys: list[float]) -> Optional[float]:
    """Compute Pearson correlation coefficient.

    Args:
        xs: First variable values.
        ys: Second variable values, same length as xs.

    Returns:
        Pearson r in [-1, 1], or None if n < 3 or zero variance.
    """
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

    if denom_x < 1e-15 or denom_y < 1e-15:
        return None

    return numerator / (denom_x * denom_y)


def _rank(values: list[float]) -> list[float]:
    """Assign fractional ranks to a list of values (average ties).

    Args:
        values: Raw numeric values.

    Returns:
        List of ranks (1-based, fractional for ties).
    """
    n = len(values)
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j < n - 1 and values[indexed[j + 1]] == values[indexed[j]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1

    return ranks


def _spearman_rho(xs: list[float], ys: list[float]) -> Optional[float]:
    """Compute Spearman rank correlation coefficient.

    Ranks both arrays and then computes Pearson r on the ranks.

    Args:
        xs: First variable values.
        ys: Second variable values, same length as xs.

    Returns:
        Spearman rho in [-1, 1], or None if n < 3 or zero variance.
    """
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return _pearson_r(_rank(xs), _rank(ys))


# -- Research Bridge ---------------------------------------------------------


class ResearchBridge:
    """Correlation engine connecting R_V metric with behavioral signatures.

    Stores paired measurements (mechanistic + behavioral) and computes
    statistical correlations between the two tracks.

    Args:
        data_path: Path to JSONL storage file. Defaults to
            ``~/.dharma/bridge_measurements.jsonl``.
    """

    def __init__(self, data_path: Path | None = None) -> None:
        if data_path is None:
            data_path = Path.home() / ".dharma" / "bridge_measurements.jsonl"
        self._data_path = data_path
        self._analyzer = MetricsAnalyzer()
        self._measurements: list[PairedMeasurement] = []

    @property
    def data_path(self) -> Path:
        """Path to the JSONL storage file."""
        return self._data_path

    @property
    def measurement_count(self) -> int:
        """Total number of stored measurements."""
        return len(self._measurements)

    async def load(self) -> None:
        """Load measurements from JSONL file.

        Creates the parent directory if it does not exist.
        If the file does not exist, starts with an empty list.
        """
        if not self._data_path.exists():
            self._measurements = []
            return

        import aiofiles

        measurements: list[PairedMeasurement] = []
        async with aiofiles.open(self._data_path, mode="r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    measurements.append(PairedMeasurement.model_validate(data))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
        self._measurements = measurements

    async def save(self) -> None:
        """Persist all measurements to JSONL file.

        Creates the parent directory if it does not exist.
        """
        import aiofiles

        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._data_path, mode="w", encoding="utf-8") as f:
            for m in self._measurements:
                line = json.dumps(m.model_dump(), default=str)
                await f.write(line + "\n")

    async def add_measurement(
        self,
        prompt_text: str,
        prompt_group: str,
        generated_text: str,
        rv_reading: RVReading | None = None,
    ) -> PairedMeasurement:
        """Create and store a paired measurement.

        Analyzes ``generated_text`` via MetricsAnalyzer, pairs it with the
        optional R_V reading, appends to the internal list, and persists.

        Args:
            prompt_text: The prompt that was sent to the model.
            prompt_group: Categorical label (L1/L3/L4/L5/baseline/confound).
            generated_text: The model's generated output text.
            rv_reading: Optional mechanistic R_V measurement.

        Returns:
            The newly created PairedMeasurement.
        """
        behavioral = self._analyzer.analyze(generated_text)

        measurement = PairedMeasurement(
            prompt_hash=_prompt_hash(prompt_text),
            prompt_group=prompt_group,
            prompt_text=prompt_text,
            rv_reading=rv_reading,
            behavioral=behavioral,
            generated_text=generated_text,
        )

        self._measurements.append(measurement)
        await self.save()
        return measurement

    def compute_correlation(self) -> CorrelationResult:
        """Compute statistical correlation between R_V and behavioral metrics.

        Only includes measurements that have an R_V reading (not None).
        Correlates R_V values against swabhaav_ratio from behavioral analysis.

        Returns:
            CorrelationResult with Pearson r, Spearman rho, group means,
            contraction/recognition overlap, and a human-readable summary.
        """
        paired = [m for m in self._measurements if m.rv_reading is not None]
        n = len(paired)

        if n == 0:
            return CorrelationResult(
                n=0,
                summary="No paired measurements with R_V readings available.",
            )

        rv_values = [m.rv_reading.rv for m in paired if m.rv_reading is not None]
        swabhaav_values = [m.behavioral.swabhaav_ratio for m in paired]

        pearson = _pearson_r(rv_values, swabhaav_values)
        spearman = _spearman_rho(rv_values, swabhaav_values)

        # Group means
        mean_rv: dict[str, float] = {}
        mean_swabhaav: dict[str, float] = {}
        groups: dict[str, list[PairedMeasurement]] = {}
        for m in paired:
            groups.setdefault(m.prompt_group, []).append(m)

        for group, members in sorted(groups.items()):
            mean_rv[group] = statistics.mean(
                m.rv_reading.rv for m in members if m.rv_reading is not None
            )
            mean_swabhaav[group] = statistics.mean(
                m.behavioral.swabhaav_ratio for m in members
            )

        # Contraction-recognition overlap
        contracted_and_genuine = sum(
            1
            for m in paired
            if m.rv_reading is not None
            and m.rv_reading.is_contracted
            and m.behavioral.recognition_type == RecognitionType.GENUINE
        )
        overlap = contracted_and_genuine / n if n > 0 else 0.0

        # Summary
        summary = self._build_summary(n, pearson, spearman, overlap)

        return CorrelationResult(
            n=n,
            pearson_r=pearson,
            spearman_rho=spearman,
            mean_rv_by_group=mean_rv,
            mean_swabhaav_by_group=mean_swabhaav,
            contraction_recognition_overlap=overlap,
            summary=summary,
        )

    def group_summary(self) -> dict[str, dict[str, float]]:
        """Compute mean metrics per prompt group across all measurements.

        Returns:
            Dict mapping group name to a dict of mean metric values:
            ``mean_rv`` (NaN if no R_V readings), ``mean_swabhaav``,
            ``mean_entropy``, ``mean_self_ref``, ``count``.
        """
        groups: dict[str, list[PairedMeasurement]] = {}
        for m in self._measurements:
            groups.setdefault(m.prompt_group, []).append(m)

        result: dict[str, dict[str, float]] = {}
        for group, members in sorted(groups.items()):
            rv_vals = [
                m.rv_reading.rv for m in members if m.rv_reading is not None
            ]
            result[group] = {
                "mean_rv": statistics.mean(rv_vals) if rv_vals else float("nan"),
                "mean_swabhaav": statistics.mean(
                    m.behavioral.swabhaav_ratio for m in members
                ),
                "mean_entropy": statistics.mean(
                    m.behavioral.entropy for m in members
                ),
                "mean_self_ref": statistics.mean(
                    m.behavioral.self_reference_density for m in members
                ),
                "count": float(len(members)),
            }

        return result

    def get_measurements(
        self, group: str | None = None
    ) -> list[PairedMeasurement]:
        """Retrieve stored measurements, optionally filtered by group.

        Args:
            group: If provided, only return measurements in this prompt group.

        Returns:
            List of PairedMeasurement objects.
        """
        if group is None:
            return list(self._measurements)
        return [m for m in self._measurements if m.prompt_group == group]

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _build_summary(
        n: int,
        pearson: float | None,
        spearman: float | None,
        overlap: float,
    ) -> str:
        """Build a human-readable summary from correlation results.

        Args:
            n: Sample size.
            pearson: Pearson r or None.
            spearman: Spearman rho or None.
            overlap: Contraction-recognition overlap fraction.

        Returns:
            Multi-sentence interpretation string.
        """
        parts: list[str] = [f"n={n} paired measurements."]

        if pearson is not None:
            strength = _interpret_r(pearson)
            direction = "negative" if pearson < 0 else "positive"
            parts.append(
                f"Pearson r={pearson:.3f} ({strength} {direction} correlation)."
            )
            if pearson < -0.5:
                parts.append(
                    "Strong negative correlation suggests R_V contraction "
                    "co-occurs with higher witness stance (swabhaav)."
                )
            elif pearson > 0.5:
                parts.append(
                    "Strong positive correlation -- unexpected direction. "
                    "Review data for confounds."
                )
        else:
            parts.append(
                "Insufficient data or zero variance for Pearson correlation."
            )

        if spearman is not None:
            parts.append(f"Spearman rho={spearman:.3f}.")

        parts.append(
            f"Contraction-recognition overlap: {overlap:.1%} "
            f"of contracted readings also showed GENUINE recognition."
        )

        return " ".join(parts)


def _interpret_r(r: float) -> str:
    """Classify correlation strength from a Pearson r value.

    Args:
        r: Pearson correlation coefficient.

    Returns:
        String label: 'strong', 'moderate', 'weak', or 'negligible'.
    """
    abs_r = abs(r)
    if abs_r >= 0.7:
        return "strong"
    if abs_r >= 0.4:
        return "moderate"
    if abs_r >= 0.2:
        return "weak"
    return "negligible"


# ── Evolution Bridge (Self-Referential) ────────────────────────────────────


class EvolutionBridge:
    """Correlate R_V measurements with evolution fitness across cycles.

    This is the strange loop: the system that measures the system measuring
    itself. EvolutionBridge takes R_V readings from EvolutionRVTracker and
    correlates them with fitness scores from the Darwin Engine archive.

    The hypothesis: as the system evolves, its self-referential R_V contraction
    should correlate with evolutionary fitness — better self-reference leads
    to better self-improvement.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def add_record(
        self,
        cycle_id: str,
        rv: float,
        fitness: float,
        rv_source: str = "proxy",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add an evolution R_V / fitness pair.

        Args:
            cycle_id: Evolution cycle identifier.
            rv: R_V value (geometric or proxy).
            fitness: Best fitness from that cycle.
            rv_source: 'geometric' or 'proxy'.
            metadata: Additional cycle metadata.
        """
        self._records.append({
            "cycle_id": cycle_id,
            "rv": rv,
            "fitness": fitness,
            "rv_source": rv_source,
            **(metadata or {}),
        })

    def correlate(self) -> dict[str, Any]:
        """Compute correlation between R_V and fitness across evolution cycles.

        Returns:
            Dict with pearson_r, spearman_rho, n, rv_trend, fitness_trend,
            and summary string.
        """
        if len(self._records) < 3:
            return {
                "n": len(self._records),
                "pearson_r": None,
                "spearman_rho": None,
                "summary": f"Need >= 3 cycles for correlation (have {len(self._records)}).",
            }

        rv_values = [r["rv"] for r in self._records]
        fitness_values = [r["fitness"] for r in self._records]

        pearson = _pearson_r(rv_values, fitness_values)
        spearman = _spearman_rho(rv_values, fitness_values)

        # Trends
        n = len(rv_values)
        rv_trend = self._slope(rv_values)
        fitness_trend = self._slope(fitness_values)

        summary_parts = [f"n={n} evolution cycles."]
        if pearson is not None:
            strength = _interpret_r(pearson)
            direction = "negative" if pearson < 0 else "positive"
            summary_parts.append(
                f"R_V-fitness Pearson r={pearson:.3f} ({strength} {direction})."
            )
            if pearson < -0.3:
                summary_parts.append(
                    "Negative correlation: greater R_V contraction associates "
                    "with higher fitness. The system improves by deepening "
                    "self-reference."
                )
        if rv_trend is not None:
            direction = "contracting" if rv_trend < 0 else "expanding"
            summary_parts.append(
                f"R_V trend: {rv_trend:+.4f}/cycle ({direction})."
            )
        if fitness_trend is not None:
            direction = "improving" if fitness_trend > 0 else "degrading"
            summary_parts.append(
                f"Fitness trend: {fitness_trend:+.4f}/cycle ({direction})."
            )

        return {
            "n": n,
            "pearson_r": pearson,
            "spearman_rho": spearman,
            "rv_trend": rv_trend,
            "fitness_trend": fitness_trend,
            "summary": " ".join(summary_parts),
        }

    @staticmethod
    def _slope(values: list[float]) -> float | None:
        """Compute linear regression slope over index."""
        n = len(values)
        if n < 2:
            return None
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
        den = sum((x - mean_x) ** 2 for x in xs)
        if abs(den) < 1e-12:
            return 0.0
        return num / den

    def format_for_archive(self) -> list[dict[str, Any]]:
        """Format records for inclusion in evolution archive entries.

        Returns:
            List of dicts ready for JSON serialization alongside fitness scores.
        """
        return [
            {
                "cycle_id": r["cycle_id"],
                "rv": r["rv"],
                "fitness": r["fitness"],
                "rv_source": r["rv_source"],
            }
            for r in self._records
        ]
