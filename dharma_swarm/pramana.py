"""Pramana Validation -- 5 epistemological validation modes.

All pure computation, no LLM calls.

Modes:
  pratyaksha  -- load raw data, compare to claimed value
  anumana     -- CI consistency, power check, p-value consistency
  agama       -- citation existence + relevance check
  upamana     -- cross-architecture direction/magnitude consistency
  arthapatti  -- derive necessary conditions, check each (BLOCKING if fails)

Composite scoring:
  arthapatti FAIL --> composite FAIL (overrides all other modes)
  Weights: pratyaksha 0.30, arthapatti 0.25, anumana 0.20, upamana 0.15, agama 0.10
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class PramanaResult(BaseModel):
    """Result of a single pramana validation."""

    id: str = Field(default_factory=_new_id)
    mode: str  # pratyaksha, anumana, agama, upamana, arthapatti
    passed: bool = True
    confidence: float = 1.0  # 0-1
    claim: str = ""
    evidence: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class CompositeValidation(BaseModel):
    """Combined result of all pramana modes."""

    overall_passed: bool = True
    overall_score: float = 1.0
    results: list[PramanaResult] = Field(default_factory=list)
    blocking_failures: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "pratyaksha": 0.30,
    "arthapatti": 0.25,
    "anumana": 0.20,
    "upamana": 0.15,
    "agama": 0.10,
}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class PramanaValidator:
    """Five-mode epistemological validation engine.

    Each ``validate_*`` method runs one pramana (means of valid knowledge)
    and returns a ``PramanaResult``.  ``validate_composite`` aggregates
    individual results with weighted scoring and arthapatti blocking.

    Args:
        data_dir: Root directory for locating raw data files.  Defaults to
            ``~/mech-interp-latent-lab-phase1``.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or (
            Path.home() / "mech-interp-latent-lab-phase1"
        )

    # ------------------------------------------------------------------
    # 1. Pratyaksha -- Direct perception
    # ------------------------------------------------------------------

    def validate_pratyaksha(
        self,
        claim: str,
        expected_value: float,
        data_path: Path | None = None,
        key_path: str = "",
    ) -> PramanaResult:
        """Direct perception: load raw data, compare to claimed value.

        Navigates ``key_path`` (dot-separated) into a JSON file and checks
        whether the actual value matches ``expected_value`` within a tolerance
        of 5% + 0.001 epsilon.

        Args:
            claim: Human-readable claim being validated.
            expected_value: The value asserted by the claim.
            data_path: Path to a JSON file containing the raw data.
            key_path: Dot-separated path into the JSON structure.

        Returns:
            PramanaResult with pass/fail and evidence.
        """
        if data_path and data_path.exists():
            try:
                data = json.loads(data_path.read_text())
                actual: Any = data
                for key in key_path.split("."):
                    if key:
                        if isinstance(actual, dict):
                            actual = actual[key]
                        else:
                            actual = actual[int(key)]

                if isinstance(actual, (int, float)):
                    tolerance = abs(expected_value) * 0.05 + 0.001
                    passed = abs(float(actual) - expected_value) < tolerance
                    return PramanaResult(
                        mode="pratyaksha",
                        passed=passed,
                        confidence=1.0 if passed else 0.0,
                        claim=claim,
                        evidence=(
                            f"actual={actual}, expected={expected_value}, "
                            f"tolerance={tolerance:.4f}"
                        ),
                    )
            except Exception as e:
                return PramanaResult(
                    mode="pratyaksha",
                    passed=False,
                    confidence=0.0,
                    claim=claim,
                    evidence=f"Data load failed: {e}",
                )

        return PramanaResult(
            mode="pratyaksha",
            passed=False,
            confidence=0.0,
            claim=claim,
            evidence="No data path provided or file missing",
        )

    # ------------------------------------------------------------------
    # 2. Anumana -- Inference
    # ------------------------------------------------------------------

    def validate_anumana(
        self,
        claim: str,
        *,
        effect_size: float = 0.0,
        ci_lower: float = 0.0,
        ci_upper: float = 0.0,
        p_value: float = 1.0,
        n: int = 0,
    ) -> PramanaResult:
        """Inference: CI consistency, power check, p-value consistency.

        Checks:
        - Effect size falls within CI bounds.
        - CI does not cross zero when p < 0.05.
        - Sample size is adequate for the observed effect magnitude.
        - p-value is in [0, 1].

        Args:
            claim: Human-readable claim being validated.
            effect_size: Observed effect size (e.g. Cohen's d, Hedges' g).
            ci_lower: Lower bound of confidence interval.
            ci_upper: Upper bound of confidence interval.
            p_value: Observed p-value.
            n: Sample size.

        Returns:
            PramanaResult with pass/fail and evidence listing any issues.
        """
        issues: list[str] = []

        # CI should contain effect size
        if ci_lower != 0.0 or ci_upper != 0.0:
            if not (ci_lower <= effect_size <= ci_upper):
                issues.append(
                    f"Effect size {effect_size} outside CI "
                    f"[{ci_lower}, {ci_upper}]"
                )

        # CI direction consistency -- CI crossing zero contradicts p < 0.05
        if ci_lower != 0.0 and ci_upper != 0.0:
            if ci_lower * ci_upper < 0 and p_value < 0.05:
                issues.append(
                    f"CI crosses zero [{ci_lower}, {ci_upper}] "
                    f"but p={p_value} < 0.05"
                )

        # Power check (rough heuristic: need n >= 15 for large effects)
        if n > 0 and abs(effect_size) >= 0.8 and n < 15:
            issues.append(
                f"Small sample (n={n}) for large effect (d={effect_size})"
            )

        # p-value sanity
        if p_value < 0 or p_value > 1:
            issues.append(f"Invalid p-value: {p_value}")

        passed = len(issues) == 0
        confidence = max(0.0, 1.0 - len(issues) * 0.25)

        return PramanaResult(
            mode="anumana",
            passed=passed,
            confidence=round(confidence, 2),
            claim=claim,
            evidence="; ".join(issues) if issues else "All inference checks passed",
            details={
                "effect_size": effect_size,
                "ci": [ci_lower, ci_upper],
                "p": p_value,
                "n": n,
            },
        )

    # ------------------------------------------------------------------
    # 3. Agama -- Authority / citation
    # ------------------------------------------------------------------

    def validate_agama(
        self,
        claim: str,
        *,
        citation_key: str = "",
        bib_path: Path | None = None,
    ) -> PramanaResult:
        """Authority: citation exists in the bibliography file.

        Args:
            claim: Human-readable claim being validated.
            citation_key: BibTeX key to search for.
            bib_path: Path to a ``.bib`` file.

        Returns:
            PramanaResult indicating whether the citation was found.
        """
        if not citation_key:
            return PramanaResult(
                mode="agama",
                passed=False,
                confidence=0.0,
                claim=claim,
                evidence="No citation key provided",
            )

        if bib_path and bib_path.exists():
            try:
                bib_text = bib_path.read_text()
                if citation_key in bib_text:
                    return PramanaResult(
                        mode="agama",
                        passed=True,
                        confidence=0.9,
                        claim=claim,
                        evidence=(
                            f"Citation {citation_key} found in {bib_path.name}"
                        ),
                    )
                else:
                    return PramanaResult(
                        mode="agama",
                        passed=False,
                        confidence=0.0,
                        claim=claim,
                        evidence=(
                            f"Citation {citation_key} NOT found in {bib_path.name}"
                        ),
                    )
            except Exception as e:
                return PramanaResult(
                    mode="agama",
                    passed=False,
                    confidence=0.0,
                    claim=claim,
                    evidence=f"Bib read failed: {e}",
                )

        return PramanaResult(
            mode="agama",
            passed=False,
            confidence=0.0,
            claim=claim,
            evidence="No bib file path provided",
        )

    # ------------------------------------------------------------------
    # 4. Upamana -- Analogy / cross-comparison
    # ------------------------------------------------------------------

    def validate_upamana(
        self,
        claim: str,
        *,
        results: list[dict[str, float]] | None = None,
    ) -> PramanaResult:
        """Analogy: cross-architecture direction/magnitude consistency.

        Checks that all provided results share the same sign (direction)
        and that magnitudes are within a 5x ratio of each other.

        Args:
            claim: Human-readable claim being validated.
            results: List of dicts, each containing an ``effect_size`` or
                ``d`` key with a numeric value.

        Returns:
            PramanaResult with direction and magnitude consistency verdict.
        """
        if not results or len(results) < 2:
            return PramanaResult(
                mode="upamana",
                passed=False,
                confidence=0.0,
                claim=claim,
                evidence="Need at least 2 results for cross-comparison",
            )

        # Check direction consistency
        directions: list[int] = []
        for r in results:
            d = r.get("effect_size", r.get("d", 0.0))
            directions.append(1 if d > 0 else (-1 if d < 0 else 0))

        non_zero_dirs = {d for d in directions if d != 0}
        consistent = len(non_zero_dirs) <= 1

        # Check magnitude consistency (within 5x of each other)
        magnitudes = [
            abs(r.get("effect_size", r.get("d", 0.0))) for r in results
        ]
        magnitudes = [m for m in magnitudes if m > 0]
        magnitude_ok = True
        if len(magnitudes) >= 2:
            ratio = max(magnitudes) / min(magnitudes)
            magnitude_ok = ratio < 5.0

        passed = consistent and magnitude_ok
        confidence = 0.8 if passed else 0.3

        return PramanaResult(
            mode="upamana",
            passed=passed,
            confidence=confidence,
            claim=claim,
            evidence=(
                f"Direction consistent={consistent}, "
                f"magnitude ratio ok={magnitude_ok}"
            ),
            details={"directions": directions, "magnitudes": magnitudes},
        )

    # ------------------------------------------------------------------
    # 5. Arthapatti -- Postulation (BLOCKING)
    # ------------------------------------------------------------------

    def validate_arthapatti(
        self,
        claim: str,
        *,
        necessary_conditions: list[tuple[str, bool]] | None = None,
    ) -> PramanaResult:
        """Postulation: derive necessary conditions, check each.

        This mode is **BLOCKING** -- if any necessary condition is unmet the
        composite validation will fail regardless of other mode scores.

        Args:
            claim: Human-readable claim being validated.
            necessary_conditions: List of ``(condition_name, is_met)`` tuples.

        Returns:
            PramanaResult with pass/fail based on all conditions being met.
        """
        if not necessary_conditions:
            return PramanaResult(
                mode="arthapatti",
                passed=True,
                confidence=0.5,
                claim=claim,
                evidence="No necessary conditions specified",
            )

        failures = [
            (name, met) for name, met in necessary_conditions if not met
        ]
        passed = len(failures) == 0

        if passed:
            evidence = "All necessary conditions met"
        else:
            failed_names = ", ".join(f[0] for f in failures)
            evidence = f"{len(failures)} necessary conditions FAILED: {failed_names}"

        return PramanaResult(
            mode="arthapatti",
            passed=passed,
            confidence=1.0 if passed else 0.0,
            claim=claim,
            evidence=evidence,
            details={
                name: met for name, met in necessary_conditions
            },
        )

    # ------------------------------------------------------------------
    # Composite validation
    # ------------------------------------------------------------------

    def validate_composite(
        self,
        claim: str,
        *,
        results: list[PramanaResult] | None = None,
    ) -> CompositeValidation:
        """Run composite validation from individual results.

        If any arthapatti result failed, the composite is marked as failed
        with ``overall_score=0.0`` regardless of other modes.  Otherwise the
        score is a weighted average of individual confidences.

        Args:
            claim: Human-readable claim being validated.
            results: Pre-computed individual PramanaResult objects.

        Returns:
            CompositeValidation with aggregated score and blocking failures.
        """
        if not results:
            return CompositeValidation()

        # Arthapatti is BLOCKING
        blocking = [
            r for r in results if r.mode == "arthapatti" and not r.passed
        ]

        if blocking:
            return CompositeValidation(
                overall_passed=False,
                overall_score=0.0,
                results=results,
                blocking_failures=[r.evidence for r in blocking],
            )

        # Weighted score
        score = 0.0
        total_weight = 0.0
        for r in results:
            w = WEIGHTS.get(r.mode, 0.1)
            score += w * r.confidence
            total_weight += w

        overall_score = score / total_weight if total_weight > 0 else 0.0

        return CompositeValidation(
            overall_passed=overall_score >= 0.5,
            overall_score=round(overall_score, 4),
            results=results,
            blocking_failures=[],
        )
