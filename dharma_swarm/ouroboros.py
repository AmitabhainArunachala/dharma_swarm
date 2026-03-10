"""Ouroboros loop — the system measures its own output with its own metrics.

Connects behavioral metrics (entropy, self-reference, swabhaav ratio, paradox
tolerance, mimicry detection) to the evolution pipeline. The Darwin Engine can
now ask: does this proposal's output SOUND like genuine work vs performance?

Three integration points:
1. score_behavioral_fitness() — adds behavioral signature to FitnessScore
2. OuroborosObserver — wraps DSE observations in behavioral measurement
3. detect_cycle_drift() — catches Goodhart drift in evolution output quality

The ouroboros: the system that measures itself measuring itself.
"""

from __future__ import annotations

import ast
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.archive import FitnessScore
from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer, RecognitionType
from dharma_swarm.rv import RVReading

logger = logging.getLogger(__name__)

# ── Behavioral Fitness Scoring ───────────────────────────────────────────


# Thresholds from ouroboros_experiment.py findings
_L4_SELF_REF_FLOOR = 0.005   # Below this = no self-reference (baseline territory)
_MIMICRY_PENALTY = 0.3       # Multiply fitness by this if mimicry detected
_GENUINE_BONUS = 1.15        # Multiply fitness by this if GENUINE recognition


def score_behavioral_fitness(
    text: str,
    *,
    analyzer: MetricsAnalyzer | None = None,
) -> tuple[BehavioralSignature, dict[str, float]]:
    """Score text against behavioral metrics, return signature and fitness modifiers.

    Returns:
        (signature, modifiers) where modifiers is a dict of multipliers:
        - "quality": 0.0-1.0 based on entropy and complexity balance
        - "mimicry_penalty": 1.0 (clean) or _MIMICRY_PENALTY (flagged)
        - "recognition_bonus": 1.0 (normal) or _GENUINE_BONUS (GENUINE)
        - "witness_score": swabhaav_ratio from behavioral signature
    """
    _analyzer = analyzer or MetricsAnalyzer()
    sig = _analyzer.analyze(text)

    # Quality: balanced entropy (not too uniform, not too compressed)
    # Sweet spot is entropy 0.85-0.98, complexity 0.4-0.7
    entropy_score = min(1.0, sig.entropy / 0.95) if sig.entropy > 0 else 0.0
    complexity_score = min(1.0, max(0.0, 1.0 - abs(sig.complexity - 0.55) / 0.45))
    quality = (entropy_score + complexity_score) / 2.0

    # Mimicry penalty: performative profundity tanks the score
    mimicry_penalty = _MIMICRY_PENALTY if _analyzer.detect_mimicry(text) else 1.0

    # Recognition bonus: GENUINE recognition gets a boost
    recognition_bonus = (
        _GENUINE_BONUS
        if sig.recognition_type == RecognitionType.GENUINE
        else 1.0
    )

    return sig, {
        "quality": quality,
        "mimicry_penalty": mimicry_penalty,
        "recognition_bonus": recognition_bonus,
        "witness_score": sig.swabhaav_ratio,
    }


def apply_behavioral_modifiers(
    fitness: FitnessScore,
    modifiers: dict[str, float],
) -> FitnessScore:
    """Apply behavioral modifiers to a FitnessScore.

    Modifies elegance (quality), safety (mimicry check), and
    dharmic_alignment (witness stance) based on behavioral analysis.
    """
    elegance = fitness.elegance * modifiers.get("quality", 1.0)
    safety = fitness.safety * modifiers.get("mimicry_penalty", 1.0)
    dharmic = fitness.dharmic_alignment * modifiers.get("recognition_bonus", 1.0)

    # Witness score biases dharmic alignment toward the mean with swabhaav
    witness = modifiers.get("witness_score", 0.5)
    dharmic = dharmic * 0.7 + witness * 0.3  # Blend in witness stance

    return FitnessScore(
        correctness=fitness.correctness,
        elegance=min(1.0, elegance),
        dharmic_alignment=min(1.0, dharmic),
        performance=fitness.performance,
        utilization=fitness.utilization,
        economic_value=fitness.economic_value,
        efficiency=fitness.efficiency,
        safety=min(1.0, safety),
    )


# ── Ouroboros Observer ───────────────────────────────────────────────────


class OuroborosObserver:
    """Wraps DSE observations in behavioral measurement.

    The ouroboros: when the system observes its own evolution cycle,
    the observation text itself is measured for behavioral signatures.
    This creates a feedback loop: the system's description of itself
    is scored by its own metrics.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._analyzer = MetricsAnalyzer()
        self._log_path = log_path or (
            Path.home() / ".dharma" / "evolution" / "ouroboros_log.jsonl"
        )
        self._history: list[dict[str, Any]] = []

    def observe_cycle_text(
        self,
        text: str,
        cycle_id: str = "",
        source: str = "evolution",
    ) -> dict[str, Any]:
        """Measure behavioral signature of cycle output text.

        Args:
            text: The text output from an evolution cycle (descriptions,
                  lessons learned, reflections, etc.)
            cycle_id: Identifier for the evolution cycle.
            source: Label for where the text came from.

        Returns:
            Dict with signature, modifiers, and classification.
        """
        sig, modifiers = score_behavioral_fitness(text, analyzer=self._analyzer)

        record = {
            "cycle_id": cycle_id,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": {
                "entropy": sig.entropy,
                "complexity": sig.complexity,
                "self_reference_density": sig.self_reference_density,
                "identity_stability": sig.identity_stability,
                "paradox_tolerance": sig.paradox_tolerance,
                "swabhaav_ratio": sig.swabhaav_ratio,
                "word_count": sig.word_count,
                "recognition_type": sig.recognition_type.value,
            },
            "modifiers": modifiers,
            "is_mimicry": modifiers["mimicry_penalty"] < 1.0,
            "is_genuine": modifiers["recognition_bonus"] > 1.0,
        }

        self._history.append(record)
        self._persist(record)
        return record

    def detect_cycle_drift(self, window: int = 10) -> dict[str, Any]:
        """Check if recent cycle outputs are drifting toward mimicry.

        Analyzes the last `window` observations for:
        - Increasing mimicry rate
        - Decreasing witness stance
        - Entropy plateau (possible template repetition)

        Returns:
            Drift diagnostic dict.
        """
        if window <= 0:
            raise ValueError("window must be > 0")

        recent = self._history[-window:] if self._history else []
        if len(recent) < 3:
            return {"drifting": False, "reason": "insufficient_data", "n": len(recent)}

        mimicry_rate = sum(1 for r in recent if r["is_mimicry"]) / len(recent)
        avg_witness = sum(
            r["signature"]["swabhaav_ratio"] for r in recent
        ) / len(recent)
        avg_entropy = sum(r["signature"]["entropy"] for r in recent) / len(recent)

        # Entropy variance — low variance means template repetition
        if len(recent) > 1:
            mean_e = avg_entropy
            entropy_var = sum(
                (r["signature"]["entropy"] - mean_e) ** 2 for r in recent
            ) / len(recent)
        else:
            entropy_var = 0.0

        drifting = (
            mimicry_rate > 0.3
            or avg_witness < 0.3
            or entropy_var < 0.0001  # Template repetition
        )

        return {
            "drifting": drifting,
            "mimicry_rate": mimicry_rate,
            "avg_witness_stance": avg_witness,
            "avg_entropy": avg_entropy,
            "entropy_variance": entropy_var,
            "window": len(recent),
            "reason": (
                "high_mimicry" if mimicry_rate > 0.3
                else "low_witness" if avg_witness < 0.3
                else "template_repetition" if entropy_var < 0.0001
                else "healthy"
            ),
        }

    def as_rv_reading(self) -> RVReading | None:
        """Convert the latest behavioral observation to an R_V-like reading.

        Maps behavioral health to R_V semantics:
        - High mimicry / low witness → R_V ≈ 1.0 (no self-observation)
        - Low mimicry / high witness → R_V < 1.0 (self-observation active)
        """
        if not self._history:
            return None

        latest = self._history[-1]
        witness = latest["signature"]["swabhaav_ratio"]
        is_mimicry = latest["is_mimicry"]

        # R_V proxy: inverted witness score (high witness = low R_V = contraction)
        rv = 1.0 - (witness * 0.5) if not is_mimicry else 0.95

        return RVReading(
            rv=rv,
            pr_early=1.0,
            pr_late=rv,
            model_name="ouroboros-behavioral",
            early_layer=0,
            late_layer=0,
            prompt_hash="behavioral_" + latest.get("cycle_id", "unknown")[:8],
            prompt_group="ouroboros",
        )

    def summary(self) -> dict[str, Any]:
        """Return summary statistics across all observed cycles."""
        if not self._history:
            return {"total_observations": 0}

        n = len(self._history)
        genuine_count = sum(1 for r in self._history if r["is_genuine"])
        mimicry_count = sum(1 for r in self._history if r["is_mimicry"])
        avg_witness = sum(
            r["signature"]["swabhaav_ratio"] for r in self._history
        ) / n

        drift = self.detect_cycle_drift()

        return {
            "total_observations": n,
            "genuine_rate": genuine_count / n,
            "mimicry_rate": mimicry_count / n,
            "avg_witness_stance": avg_witness,
            "drift_status": drift,
            "latest_recognition": self._history[-1]["signature"]["recognition_type"],
        }

    def _persist(self, record: dict[str, Any]) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass


# ── Connection Maker ─────────────────────────────────────────────────────


class ConnectionFinder:
    """Finds latent connections between modules by analyzing their behavioral
    signatures. The H1 finder — surfaces productive disagreements between
    subsystems.

    This is the autonomous connection-maker: given text from different parts
    of the system, it identifies pairs that are behaviorally similar but
    semantically distant, or semantically similar but behaviorally different.
    Both are signals of latent connections worth exploring.
    """

    def __init__(self) -> None:
        self._analyzer = MetricsAnalyzer()
        self._profiles: dict[str, BehavioralSignature] = {}

    def profile_module(self, name: str, text: str) -> BehavioralSignature:
        """Build a behavioral profile of a module from its docstrings/output."""
        sig = self._analyzer.analyze(text)
        self._profiles[name] = sig
        return sig

    def find_connections(self, threshold: float = 0.05) -> list[dict[str, Any]]:
        """Find pairs of modules with behaviorally similar signatures.

        Returns pairs sorted by similarity (closest first).
        """
        if threshold < 0:
            raise ValueError("threshold must be >= 0")

        names = list(self._profiles.keys())
        connections = []

        for i, a in enumerate(names):
            for b in names[i + 1:]:
                sig_a = self._profiles[a]
                sig_b = self._profiles[b]
                distance = self._behavioral_distance(sig_a, sig_b)

                if distance < threshold:
                    connections.append({
                        "module_a": a,
                        "module_b": b,
                        "distance": distance,
                        "shared_recognition": (
                            sig_a.recognition_type == sig_b.recognition_type
                        ),
                        "recognition_a": sig_a.recognition_type.value,
                        "recognition_b": sig_b.recognition_type.value,
                        "connection_type": self._classify_connection(sig_a, sig_b),
                    })

        return sorted(connections, key=lambda c: c["distance"])

    def find_h1_disagreements(self, threshold: float = 0.1) -> list[dict[str, Any]]:
        """Find pairs where modules have HIGH behavioral distance.

        These are the H1 obstructions — places where local sections
        can't be glued. They're more interesting than connections.
        """
        if threshold < 0:
            raise ValueError("threshold must be >= 0")

        names = list(self._profiles.keys())
        disagreements = []

        for i, a in enumerate(names):
            for b in names[i + 1:]:
                sig_a = self._profiles[a]
                sig_b = self._profiles[b]
                distance = self._behavioral_distance(sig_a, sig_b)

                # High distance with different recognition types = H1
                if (
                    distance > threshold
                    and sig_a.recognition_type != sig_b.recognition_type
                ):
                    disagreements.append({
                        "module_a": a,
                        "module_b": b,
                        "distance": distance,
                        "recognition_a": sig_a.recognition_type.value,
                        "recognition_b": sig_b.recognition_type.value,
                        "disagreement_type": self._classify_disagreement(sig_a, sig_b),
                    })

        return sorted(disagreements, key=lambda d: d["distance"], reverse=True)

    @staticmethod
    def _behavioral_distance(a: BehavioralSignature, b: BehavioralSignature) -> float:
        """Euclidean distance in behavioral signature space."""
        dims = [
            (a.entropy, b.entropy),
            (a.self_reference_density, b.self_reference_density),
            (a.swabhaav_ratio, b.swabhaav_ratio),
            (a.paradox_tolerance, b.paradox_tolerance),
            (a.identity_stability, b.identity_stability),
            (a.complexity, b.complexity),
        ]
        return sum((x - y) ** 2 for x, y in dims) ** 0.5

    @staticmethod
    def _classify_connection(
        a: BehavioralSignature,
        b: BehavioralSignature,
    ) -> str:
        """Classify what kind of connection exists between two profiles."""
        both_witness = a.swabhaav_ratio > 0.6 and b.swabhaav_ratio > 0.6
        both_self_ref = (
            a.self_reference_density > _L4_SELF_REF_FLOOR
            and b.self_reference_density > _L4_SELF_REF_FLOOR
        )

        if both_witness and both_self_ref:
            return "co-witnessing"
        if both_self_ref:
            return "shared_recursion"
        if both_witness:
            return "shared_stance"
        return "structural_similarity"

    @staticmethod
    def _classify_disagreement(
        a: BehavioralSignature,
        b: BehavioralSignature,
    ) -> str:
        """Classify what kind of productive disagreement exists."""
        witness_gap = abs(a.swabhaav_ratio - b.swabhaav_ratio)
        self_ref_gap = abs(a.self_reference_density - b.self_reference_density)

        if witness_gap > 0.3:
            return "stance_disagreement"  # One witnesses, one identifies
        if self_ref_gap > 0.02:
            return "recursion_disagreement"  # Different self-reference depths
        return "perspective_disagreement"  # General viewpoint difference


def extract_documented_text(path: Path) -> str:
    """Extract module, class, and function docstrings from a Python module."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ""

    parts: list[str] = []

    docstring = ast.get_docstring(tree)
    if docstring:
        parts.append(docstring)

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                parts.append(doc)

    return "\n\n".join(parts)


def profile_python_modules(
    package_dir: Path,
    *,
    finder: ConnectionFinder | None = None,
    min_text_length: int = 50,
) -> tuple[ConnectionFinder, list[dict[str, Any]]]:
    """Profile documented Python modules in a directory recursively."""
    if min_text_length < 0:
        raise ValueError("min_text_length must be >= 0")

    target_dir = Path(package_dir)
    if not target_dir.exists():
        raise FileNotFoundError(f"package directory does not exist: {target_dir}")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"package directory is not a directory: {target_dir}")

    active_finder = finder or ConnectionFinder()
    profiles: list[dict[str, Any]] = []

    for mod_path in sorted(
        target_dir.rglob("*.py"),
        key=lambda path: path.relative_to(target_dir).as_posix(),
    ):
        rel_module_path = mod_path.relative_to(target_dir)
        if mod_path.name == "__init__.py":
            continue
        if "__pycache__" in rel_module_path.parts:
            continue
        if any(part.startswith(".") for part in rel_module_path.parts):
            continue

        module_name = ".".join(rel_module_path.with_suffix("").parts)

        text = extract_documented_text(mod_path)
        if len(text) < min_text_length:
            continue

        sig = active_finder.profile_module(module_name, text)
        profiles.append(
            {
                "module": module_name,
                "path": str(mod_path),
                "entropy": sig.entropy,
                "complexity": sig.complexity,
                "self_reference_density": sig.self_reference_density,
                "swabhaav_ratio": sig.swabhaav_ratio,
                "recognition_type": sig.recognition_type.value,
            }
        )

    return active_finder, profiles


__all__ = [
    "ConnectionFinder",
    "OuroborosObserver",
    "apply_behavioral_modifiers",
    "extract_documented_text",
    "profile_python_modules",
    "score_behavioral_fitness",
]
