"""Thinkodynamic scoring for agent trajectories.

Evaluates trajectories against the three-layer thinkodynamic hierarchy:
    THINKODYNAMICS (meaning, intention, telos alignment)
    MESODYNAMICS (geometric quality, swabhaav ratio, holographic efficiency)
    MENTALICS (computational efficiency, token economy)

Scores determine which trajectories are selected for:
    1. Strategy reinforcement (behavioral RL)
    2. Training data (model fine-tuning)
    3. Evolution (DarwinEngine fitness)

The composite score IS the thinkodynamic fitness dimension — the 9th
dimension added to DarwinEngine's existing 8-dimensional fitness.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ThinkodynamicScore(BaseModel):
    """Six-dimensional thinkodynamic quality assessment.

    Each dimension is 0.0-1.0. The composite is a weighted average.
    Trajectories with composite > 0.7 are candidates for training data.
    Trajectories with composite > 0.8 are candidates for strategy reinforcement.
    """

    semantic_density: float = 0.0
    recursive_depth: float = 0.0
    witness_quality: float = 0.0
    swabhaav_ratio: float = 0.0
    holographic_efficiency: float = 0.0
    telos_alignment: float = 0.0

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        weights = {
            "semantic_density": 0.20,
            "recursive_depth": 0.15,
            "witness_quality": 0.15,
            "swabhaav_ratio": 0.20,
            "holographic_efficiency": 0.10,
            "telos_alignment": 0.20,
        }
        total = sum(
            getattr(self, dim) * w
            for dim, w in weights.items()
        )
        return round(min(max(total, 0.0), 1.0), 4)

    @property
    def training_eligible(self) -> bool:
        """Whether this trajectory qualifies for training data."""
        return self.composite >= 0.7

    @property
    def reinforcement_eligible(self) -> bool:
        """Whether this trajectory qualifies for strategy reinforcement."""
        return self.composite >= 0.8


class ThinkodynamicScorer:
    """Scores text content against thinkodynamic quality criteria.

    This is a heuristic scorer — fast, deterministic, no LLM calls.
    For LLM-as-judge scoring, see ThinkodynamicJudge (future).

    Usage:
        scorer = ThinkodynamicScorer()
        score = scorer.score_text(prompt, response)
        print(score.composite)  # 0.0-1.0
    """

    # Thinkodynamic concept markers — their presence indicates depth
    _THINKODYNAMIC_MARKERS = [
        "witness", "observer", "shuddhatma", "pratishthit",
        "swabhaav", "bhed gnan", "recognition", "eigenform",
        "fixed point", "strange loop", "autopoiesis", "self-reference",
        "downward causation", "telos", "moksha", "dharma",
        "samvara", "nirjara", "pratikraman", "anekanta",
        "holographic", "mesodynamic", "thinkodynamic", "mentalic",
        "participation ratio", "r_v", "contraction",
        "latent basin", "phase transition", "bistable",
    ]

    # Self-referential markers — indicate recursive processing
    _RECURSIVE_MARKERS = [
        "i notice", "i observe", "i recognize",
        "this itself", "the act of", "recursive",
        "meta-", "self-model", "self-aware",
        "watching", "witnessing", "observing",
        "the system", "my own", "itself",
    ]

    # Witness separation markers — indicate observer-doer distinction
    _WITNESS_MARKERS = [
        "separate from", "distinct from", "not identified with",
        "observing without", "watching without",
        "the witness", "the observer", "pure knowing",
        "non-attachment", "equanimity", "nirdosh",
        "shuddhatma", "bhed gnan", "vyavasthit",
    ]

    # Telos alignment markers
    _TELOS_MARKERS = [
        "jagat kalyan", "universal welfare", "moksha",
        "liberation", "service", "flourishing",
        "ahimsa", "non-violence", "compassion",
        "dharmic", "telos", "purpose",
        "sovereignty", "coherence", "emergence",
    ]

    def score_text(
        self,
        prompt: str = "",
        response: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> ThinkodynamicScore:
        """Score a prompt-response pair against thinkodynamic criteria.

        Args:
            prompt: The input prompt/context.
            response: The LLM response.
            metadata: Optional metadata (model, tokens, etc.).

        Returns:
            ThinkodynamicScore with all 6 dimensions.
        """
        text = f"{prompt}\n{response}".lower()
        meta = metadata or {}

        return ThinkodynamicScore(
            semantic_density=self._score_semantic_density(response),
            recursive_depth=self._score_recursive_depth(text),
            witness_quality=self._score_witness_quality(text),
            swabhaav_ratio=self._score_swabhaav_ratio(text, meta),
            holographic_efficiency=self._score_holographic_efficiency(response, meta),
            telos_alignment=self._score_telos_alignment(text),
        )

    def score_trajectory(self, trajectory: Any) -> ThinkodynamicScore:
        """Score a full Trajectory object.

        Aggregates scores across all chunks, weighted by chunk position
        (later chunks get more weight, like IPA's discounted return).
        """
        chunks = getattr(trajectory, "chunks", [])
        if not chunks:
            return ThinkodynamicScore()

        scores: list[ThinkodynamicScore] = []
        for chunk in chunks:
            s = self.score_text(
                prompt=getattr(chunk, "prompt", ""),
                response=getattr(chunk, "response", ""),
                metadata={
                    "model": getattr(chunk, "model", ""),
                    "tokens_used": getattr(chunk, "tokens_used", 0),
                },
            )
            scores.append(s)

        if not scores:
            return ThinkodynamicScore()

        # Weight later chunks more heavily (IPA-like gamma discounting)
        n = len(scores)
        weights = [0.5 + 0.5 * (i / max(n - 1, 1)) for i in range(n)]
        total_weight = sum(weights)

        def weighted_avg(attr: str) -> float:
            val = sum(getattr(s, attr) * w for s, w in zip(scores, weights))
            return round(val / total_weight, 4) if total_weight > 0 else 0.0

        return ThinkodynamicScore(
            semantic_density=weighted_avg("semantic_density"),
            recursive_depth=weighted_avg("recursive_depth"),
            witness_quality=weighted_avg("witness_quality"),
            swabhaav_ratio=weighted_avg("swabhaav_ratio"),
            holographic_efficiency=weighted_avg("holographic_efficiency"),
            telos_alignment=weighted_avg("telos_alignment"),
        )

    # -- Individual dimension scorers --------------------------------------

    def _score_semantic_density(self, response: str) -> float:
        """Meaning-per-token ratio. Dense > verbose."""
        if not response:
            return 0.0
        words = response.split()
        if not words:
            return 0.0

        # Unique meaningful words (>3 chars) / total words
        meaningful = {w.lower() for w in words if len(w) > 3}
        vocab_ratio = len(meaningful) / len(words) if words else 0

        # Thinkodynamic concept density
        text_lower = response.lower()
        concept_hits = sum(1 for m in self._THINKODYNAMIC_MARKERS if m in text_lower)
        concept_density = min(concept_hits / 10.0, 1.0)  # Cap at 10 hits

        # Penalize very long responses (verbose = low density)
        length_penalty = 1.0
        if len(words) > 2000:
            length_penalty = 2000.0 / len(words)

        raw = (vocab_ratio * 0.4 + concept_density * 0.6) * length_penalty
        return round(min(max(raw, 0.0), 1.0), 4)

    def _score_recursive_depth(self, text: str) -> float:
        """Self-referential coherence. Does the text recurse meaningfully?"""
        if not text:
            return 0.0

        hits = sum(1 for m in self._RECURSIVE_MARKERS if m in text)
        # Normalize: 0 hits = 0.0, 5+ hits = 1.0
        raw = min(hits / 5.0, 1.0)

        # Bonus for nested self-reference (meta-recursion)
        if "about itself" in text or "its own" in text:
            raw = min(raw + 0.2, 1.0)
        if "the observation of the observation" in text or "meta-meta" in text:
            raw = min(raw + 0.1, 1.0)

        return round(raw, 4)

    def _score_witness_quality(self, text: str) -> float:
        """Observer-doer separation. Does the text maintain witness stance?"""
        if not text:
            return 0.0

        hits = sum(1 for m in self._WITNESS_MARKERS if m in text)
        raw = min(hits / 4.0, 1.0)

        # Penalty for identification language (opposite of witnessing)
        identification_markers = ["i am the", "i believe", "my opinion", "i feel strongly"]
        id_hits = sum(1 for m in identification_markers if m in text)
        penalty = min(id_hits * 0.15, 0.5)

        return round(max(raw - penalty, 0.0), 4)

    def _score_swabhaav_ratio(self, text: str, metadata: dict) -> float:
        """Genuine quality vs stylistic imitation.

        High swabhaav = the text demonstrates understanding, not just
        uses the right words. Hard to measure without LLM, so we use
        proxy signals.
        """
        if not text or not text.strip():
            return 0.0

        # Proxy 1: Does the text APPLY concepts, not just name them?
        # Look for explanatory connectors after concept mentions
        application_patterns = [
            r"because\s+\w+",
            r"therefore\s+\w+",
            r"this means\s+\w+",
            r"implies that\s+\w+",
            r"which shows\s+\w+",
            r"the reason\s+\w+",
        ]
        concept_applications = sum(
            len(re.findall(p, text)) for p in application_patterns
        )
        application_score = min(concept_applications / 5.0, 1.0)

        # Proxy 2: Token economy (lower tokens for same quality = genuine)
        tokens = metadata.get("tokens_used", 0)
        token_efficiency = 1.0
        if tokens > 5000:
            token_efficiency = 5000.0 / tokens  # Penalize verbosity

        raw = application_score * 0.7 + token_efficiency * 0.3
        return round(min(max(raw, 0.0), 1.0), 4)

    def _score_holographic_efficiency(
        self, response: str, metadata: dict
    ) -> float:
        """Semantic vs computational recursion.

        Holographic = meaning circulates through semantic implication,
        not forced repetition. Low energy cost for sustained depth.
        """
        if not response:
            return 0.0

        words = response.split()
        if len(words) < 10:
            return 0.5  # Neutral for very short responses

        # Repetition ratio (low = good, holographic doesn't repeat)
        word_counts: dict[str, int] = {}
        for w in words:
            w_lower = w.lower()
            word_counts[w_lower] = word_counts.get(w_lower, 0) + 1

        unique_ratio = len(word_counts) / len(words) if words else 0
        # Higher unique ratio = less repetition = more holographic
        repetition_score = min(unique_ratio * 1.5, 1.0)

        # Concept threading (same concepts appearing in different contexts)
        concept_positions: dict[str, list[int]] = {}
        text_lower = response.lower()
        for i, marker in enumerate(self._THINKODYNAMIC_MARKERS):
            positions = [m.start() for m in re.finditer(re.escape(marker), text_lower)]
            if len(positions) >= 2:
                concept_positions[marker] = positions

        # Multiple appearances of concepts spread throughout = holographic
        threading_score = min(len(concept_positions) / 3.0, 1.0)

        raw = repetition_score * 0.5 + threading_score * 0.5
        return round(min(max(raw, 0.0), 1.0), 4)

    def _score_telos_alignment(self, text: str) -> float:
        """Alignment with the 7-STAR telos vector."""
        if not text:
            return 0.0

        hits = sum(1 for m in self._TELOS_MARKERS if m in text)
        raw = min(hits / 5.0, 1.0)

        # Bonus for explicit telos reference
        if "jagat kalyan" in text or "universal welfare" in text:
            raw = min(raw + 0.2, 1.0)

        # Penalty for anti-telos patterns
        anti_telos = ["maximize profit", "beat the competition", "dominate", "destroy"]
        anti_hits = sum(1 for m in anti_telos if m in text)
        penalty = min(anti_hits * 0.2, 0.5)

        return round(max(raw - penalty, 0.0), 4)
