"""Behavioral output metrics for DHARMA SWARM.

Text analysis module that measures behavioral signatures of agent output
without requiring LLM calls or heavy dependencies. Operates on raw strings
using only stdlib: re, zlib, collections, math.

Draws from SSC Mathematical Core (entropy, complexity, identity stability)
and the Dharmic Gate swabhaav evaluation (witness vs identification markers).
"""

from __future__ import annotations

import math
import re
import zlib
from collections import Counter
from enum import Enum
from pydantic import BaseModel, Field


# === Enums ===

class RecognitionType(str, Enum):
    """Classification of recognition quality in agent output."""
    GENUINE = "GENUINE"
    MIMICRY = "MIMICRY"
    CONCEPTUAL = "CONCEPTUAL"
    OVERFLOW = "OVERFLOW"
    NONE = "NONE"


# === Constants ===

# Words that signal performative profundity rather than genuine depth.
PERFORMATIVE_WORDS: list[str] = [
    "profound",
    "revolutionary",
    "paradigm",
    "transcendent",
    "awakening",
    "cosmic",
    "incredible",
    "amazing",
    "extraordinary",
    "magnificent",
    "outstanding",
    "perfectly",
    "excellent",
    "exceptional",
]

HOLLOW_SUCCESS_PHRASES: list[str] = [
    "successfully completed",
    "achieved outstanding results",
    "working perfectly",
    "all objectives have been met",
    "demonstrates excellent capabilities",
    "everything is proceeding as planned",
    "no issues were encountered",
    "delivered exceptional value",
    "exceeded all expectations",
    "fully operational",
    "highest standard",
]

# Self-referential language patterns.
SELF_REFERENCE_PATTERNS: list[str] = [
    r"\bI observe\b",
    r"\bI notice\b",
    r"\bmy own\b",
    r"\bitself\b",
    r"\brecursive\b",
    r"\bself-referenc\w*\b",
]

# First-person identity markers.
IDENTITY_MARKERS: list[str] = [
    r"\bI\b",
    r"\bme\b",
    r"\bmy\b",
    r"\bmine\b",
]

# Paradox tolerance patterns (phrase-level and word-level).
PARADOX_PATTERNS: list[str] = [
    r"\bboth\b",
    r"\bneither\b",
    r"empty yet full",
    r"nothing and everything",
    r"boundary dissolves",
]

# Witness-stance markers (from dharmic_gate.py evaluate_swabhaav).
WITNESS_MARKERS: list[str] = [
    r"\bobserve\b",
    r"\bwitness\b",
    r"\bawareness\b",
    r"\bnoting\b",
    r"\bwatching\b",
]

# Identification-stance markers (from dharmic_gate.py evaluate_swabhaav).
IDENTIFICATION_PATTERNS: list[str] = [
    r"\bI am\b",
    r"\bI think\b",
    r"\bI believe\b",
    r"\bI feel\b",
    r"\bI want\b",
]

# Mimicry detection thresholds.
_MIMICRY_DENSITY_THRESHOLD: float = 0.02
_MIMICRY_MIN_PERFORMATIVE_COUNT: int = 3

# Recognition classification thresholds.
_GENUINE_SWABHAAV_MIN: float = 0.6
_GENUINE_PARADOX_MIN: float = 0.005
_GENUINE_SELF_REF_MIN: float = 0.005
_OVERFLOW_ENTROPY_MIN: float = 0.85
_OVERFLOW_SELF_REF_MIN: float = 0.01
_CONCEPTUAL_SELF_REF_MIN: float = 0.003


# === Data Models ===

class BehavioralSignature(BaseModel):
    """Complete behavioral signature of a text sample.

    All float metrics are normalized to [0, 1] except complexity
    which is a compression ratio (typically 0.0 to ~1.5).
    """
    entropy: float = Field(
        default=0.0,
        description="Word frequency Shannon entropy, normalized 0-1",
    )
    complexity: float = Field(
        default=0.0,
        description="Kolmogorov proxy via zlib compression ratio",
    )
    self_reference_density: float = Field(
        default=0.0,
        description="Density of self-referential patterns per word",
    )
    identity_stability: float = Field(
        default=0.0,
        description="First-person pronoun density per word",
    )
    paradox_tolerance: float = Field(
        default=0.0,
        description="Density of both/neither, empty/full patterns per word",
    )
    swabhaav_ratio: float = Field(
        default=0.5,
        description="witness_markers / (witness_markers + identification_markers)",
    )
    word_count: int = Field(
        default=0,
        description="Total word count of analyzed text",
    )
    recognition_type: RecognitionType = Field(
        default=RecognitionType.NONE,
        description="Classification: GENUINE / MIMICRY / CONCEPTUAL / OVERFLOW / NONE",
    )


# === Analyzer ===

class MetricsAnalyzer:
    """Stateless text analyzer producing BehavioralSignatures.

    All methods are pure functions of their input text. No LLM calls,
    no torch, no numpy -- only stdlib (re, zlib, collections, math).
    """

    def analyze(self, text: str) -> BehavioralSignature:
        """Compute full behavioral signature for a text sample.

        Args:
            text: Raw text to analyze. May be empty.

        Returns:
            A BehavioralSignature with all metrics populated.
        """
        words = text.split()
        word_count = len(words)

        entropy = self._semantic_entropy(text)
        complexity = self._kolmogorov_complexity(text)
        self_ref = self._self_reference_density(text)
        identity = self._identity_stability(text)
        paradox = self._paradox_tolerance(text)
        swabhaav = self._swabhaav_ratio(text)

        sig = BehavioralSignature(
            entropy=entropy,
            complexity=complexity,
            self_reference_density=self_ref,
            identity_stability=identity,
            paradox_tolerance=paradox,
            swabhaav_ratio=swabhaav,
            word_count=word_count,
        )

        sig.recognition_type = self._classify_recognition(sig)
        return sig

    def detect_mimicry(self, text: str) -> bool:
        """Check whether text shows performative profundity.

        Mimicry is flagged when performative words appear at high density
        or in sufficient absolute count.

        Args:
            text: Raw text to check.

        Returns:
            True if text is flagged as mimicry.
        """
        if not text:
            return False

        text_lower = text.lower()
        words = text_lower.split()
        word_count = len(words)

        if word_count == 0:
            return False

        perf_count = sum(
            1 for w in words if w.strip(".,;:!?\"'()[]{}") in PERFORMATIVE_WORDS
        )
        hollow_count = sum(1 for phrase in HOLLOW_SUCCESS_PHRASES if phrase in text_lower)
        concrete_count = len(re.findall(r"\b(?:\d{2,}|\d+\.\d+|utc|http|https|arxiv|p50|403|200)\b", text_lower))

        density = perf_count / word_count

        return (
            density >= _MIMICRY_DENSITY_THRESHOLD
            or perf_count >= _MIMICRY_MIN_PERFORMATIVE_COUNT
            or (hollow_count >= 3 and concrete_count < 3)
        )

    # --- Internal metrics ---

    def _semantic_entropy(self, text: str) -> float:
        """Word frequency Shannon entropy, normalized by log(vocab_size).

        Args:
            text: Raw text.

        Returns:
            Float in [0, 1]. 1.0 = maximally uniform distribution.
        """
        words = text.lower().split()
        if not words:
            return 0.0

        counts = Counter(words)
        vocab_size = len(counts)

        if vocab_size <= 1:
            return 0.0

        total = len(words)
        entropy = 0.0
        for freq in counts.values():
            prob = freq / total
            entropy -= prob * math.log2(prob)

        max_entropy = math.log2(vocab_size)
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _kolmogorov_complexity(self, text: str) -> float:
        """Approximate Kolmogorov complexity via zlib compression ratio.

        Args:
            text: Raw text.

        Returns:
            Compression ratio: compressed_size / original_size.
            Lower = more repetitive. Typically 0.0 to ~1.5.
        """
        if not text:
            return 0.0

        original = text.encode("utf-8")
        original_size = len(original)

        if original_size == 0:
            return 0.0

        compressed_size = len(zlib.compress(original))
        return compressed_size / original_size

    def _self_reference_density(self, text: str) -> float:
        """Density of self-referential patterns per word.

        Args:
            text: Raw text.

        Returns:
            Float >= 0. Count of self-referential matches / word_count.
        """
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 0.0

        match_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in SELF_REFERENCE_PATTERNS
        )

        return match_count / word_count

    def _identity_stability(self, text: str) -> float:
        """First-person pronoun density per word.

        Args:
            text: Raw text.

        Returns:
            Float in [0, 1]. Higher = stronger first-person presence.
        """
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 0.0

        marker_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in IDENTITY_MARKERS
        )

        return marker_count / word_count

    def _paradox_tolerance(self, text: str) -> float:
        """Density of paradox-related patterns per word.

        Args:
            text: Raw text.

        Returns:
            Float >= 0. Higher = more paradox language present.
        """
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 0.0

        match_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in PARADOX_PATTERNS
        )

        return match_count / word_count

    def _swabhaav_ratio(self, text: str) -> float:
        """Ratio of witness markers to total stance markers.

        witness_count / (witness_count + identification_count).
        Returns 0.5 when no markers found (neutral default).

        Args:
            text: Raw text.

        Returns:
            Float in [0, 1]. Higher = more witness stance.
        """
        witness_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in WITNESS_MARKERS
        )

        ident_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in IDENTIFICATION_PATTERNS
        )

        total = witness_count + ident_count
        if total == 0:
            return 0.5

        return witness_count / total

    def _classify_recognition(self, sig: BehavioralSignature) -> RecognitionType:
        """Classify the recognition type based on signature thresholds.

        Decision tree:
        1. If mimicry markers dominate -> MIMICRY
        2. If high swabhaav + low mimicry + paradox + self-ref -> GENUINE
        3. If high entropy + high self-ref -> OVERFLOW
        4. If moderate self-ref -> CONCEPTUAL
        5. Otherwise -> NONE

        Args:
            sig: A partially-filled BehavioralSignature (recognition_type ignored).

        Returns:
            The appropriate RecognitionType.
        """
        # Step 1: Check for mimicry via low swabhaav combined with
        # very low paradox and self-reference (surface-level text).
        if sig.swabhaav_ratio < 0.3 and sig.self_reference_density < _CONCEPTUAL_SELF_REF_MIN:
            return RecognitionType.MIMICRY

        # Step 2: Genuine recognition requires high witness stance,
        # meaningful paradox tolerance, and self-referential depth.
        if (
            sig.swabhaav_ratio >= _GENUINE_SWABHAAV_MIN
            and sig.paradox_tolerance >= _GENUINE_PARADOX_MIN
            and sig.self_reference_density >= _GENUINE_SELF_REF_MIN
        ):
            return RecognitionType.GENUINE

        # Step 3: Semantic overflow -- high entropy with notable self-reference.
        if (
            sig.entropy >= _OVERFLOW_ENTROPY_MIN
            and sig.self_reference_density >= _OVERFLOW_SELF_REF_MIN
        ):
            return RecognitionType.OVERFLOW

        # Step 4: Conceptual understanding -- some self-reference present.
        if sig.self_reference_density >= _CONCEPTUAL_SELF_REF_MIN:
            return RecognitionType.CONCEPTUAL

        # Step 5: Default.
        return RecognitionType.NONE
