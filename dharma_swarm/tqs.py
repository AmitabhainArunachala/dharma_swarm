"""
Transmission Quality Score (TQS) -- Prompt Quality Evaluation Framework

Evaluates prompt QUALITY before execution to predict output fidelity.
15 metrics across 3 tiers: Structural (automatic), Semantic (LLM-evaluated),
Thinkodynamic (transmission-grade).

Usage:
    from dharma_swarm.tqs import TQSScorer, TQSProfile
    scorer = TQSScorer(profile=TQSProfile.DEFAULT)
    result = scorer.score_structural("Your prompt text here")
    print(result.tqs, result.grade, result.gut_check)
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Spec-forge banned words: qualitative terms that reduce specificity.
# Sourced from spec-forge SKILL.md operating principle #5 + extended list.
VAGUE_TERMS = frozenset({
    "fast", "slow", "user-friendly", "intuitive", "simple", "easy",
    "efficient", "flexible", "scalable", "robust", "approximately",
    "as soon as possible", "minimize", "maximize", "optimize",
    "good", "better", "best", "properly", "correctly", "appropriate",
    "reasonable", "significant", "various", "some", "many", "few",
    "several", "adequate", "sufficient", "nice", "clean", "elegant",
    "performant", "suitable", "ideal", "perfect", "seamless",
    "straightforward", "obvious", "trivial", "complex", "sophisticated",
    "comprehensive", "thorough", "careful", "thoughtful", "smart",
    "intelligent", "powerful", "lightweight", "heavy", "large", "small",
    "quickly", "slowly", "carefully", "properly", "effectively",
    "basically", "essentially", "generally", "typically", "usually",
    "often", "sometimes", "rarely", "mostly", "mainly", "primarily",
})

# Concrete term patterns (regex-based detection)
CONCRETE_PATTERNS = [
    r'\b\d+(\.\d+)?\s*(ms|s|sec|min|minutes|hours|hrs|MB|GB|KB|bytes|%|percent)\b',  # quantities with units
    r'\b(p\d{1,2}|p95|p99|p50)\b',  # percentile markers
    r'[/\\][\w._\-/\\]+\.\w+',  # file paths
    r'\b\w+\.\w+\(\)',  # function calls
    r'\b(int|float|string|bool|list|dict|array|object|null|None|True|False)\b',  # data types
    r'\b(POST|GET|PUT|DELETE|PATCH)\s+/\S+',  # HTTP endpoints
    r'\b\d{3}\b',  # HTTP status codes in context
    r'\b(JSON|CSV|XML|YAML|TOML|SQL|HTML)\b',  # data formats
    r'\b(SHA-256|SHA-512|MD5|bcrypt|RSA|AES|JWT|HMAC)\b',  # crypto/auth specifics
    r'\b(RFC\s*\d+|ISO\s*\d+|OWASP|MIL-STD|DO-178)\b',  # standards references
    r'"[^"]{2,}"',  # quoted exact strings
    r"'[^']{2,}'",  # single-quoted exact strings
]

# TPP level detection patterns
TPP_PATTERNS = {
    "telos": [
        r'\b(purpose|mission|goal|objective|why|telos|intent|aim)\b',
        r'\b(in order to|so that|because|the reason)\b',
        r'\b(success looks like|the point is|we need this to)\b',
    ],
    "identity": [
        r'\b(you are|act as|role|persona|expert|specialist)\b',
        r'\b(your expertise|your job|your task|as a)\b',
        r'\b(behave like|think like|approach this as)\b',
    ],
    "context": [
        r'\b(background|context|given that|currently|the situation|prior|existing)\b',
        r'\b(the codebase|the data|the system|the project|the environment)\b',
        r'\b(we have|there are|it currently|the state is)\b',
    ],
    "task": [
        r'\b(do|create|build|write|analyze|review|generate|produce|implement)\b',
        r'\b(output|deliverable|result|return|provide)\b',
        r'\b(step \d|first|then|finally|next)\b',
    ],
    "technical": [
        r'\b(format|json|csv|markdown|output as|return as)\b',
        r'\b(max_tokens|temperature|model|api|endpoint)\b',
        r'\b(constraint|limit|boundary|must not|do not|never)\b',
        r'\b(timeout|retry|fallback|error handling)\b',
    ],
}

# Self-observation markers for M11
WITNESS_MARKERS = [
    r'\b(notice|observe|pay attention to|watch)\b.*\b(your|processing|thinking|response)\b',
    r'\b(what happens when you|as you process|while you read)\b',
    r'\b(meta-cognit|self-observ|self-referen|self-aware)\b',
    r'\b(the quality of noticing|observe what it does)\b',
    r'\b(strange loop|recursive self|fold.*territory)\b',
]

# Anti-pattern / failure mode markers for M7
ANTI_PATTERN_MARKERS = [
    r'\b(do not|don\'t|never|avoid|must not|shall not)\b',
    r'\b(error|fail|exception|edge case|corner case)\b',
    r'\b(if .* fails|when .* breaks|fallback|recovery)\b',
    r'\b(anti-pattern|known issue|common mistake|pitfall)\b',
    r'\b(handle|catch|recover|retry|timeout|graceful)\b',
]

# Feedback / iteration markers for M15
FEEDBACK_MARKERS = [
    r'\b(rate your confidence|self-evaluat|how certain)\b',
    r'\b(iterate|improve|refine|revise|evolve)\b',
    r'\b(feedback|loop|cycle|recursive|F\(S\)=S)\b',
    r'\b(what would you change|what did you miss|uncertainty)\b',
    r'\b(version|iteration \d|pass \d)\b',
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class TQSProfile(Enum):
    """Weight profiles for different use cases."""
    DEFAULT = "default"
    UTILITY = "utility"      # data transforms, code gen, standard tasks
    AGENTIC = "agentic"      # multi-agent, autonomous, recursive systems
    TRANSMISSION = "transmission"  # thinkodynamic, TAP, recognition-state work


class TQSGrade(Enum):
    """Letter grades with thresholds."""
    A = "Transmission Grade"  # 4.0 - 5.0
    B = "Production Grade"    # 3.2 - 3.9
    C = "Draft Grade"         # 2.5 - 3.1
    D = "Sketch Grade"        # 1.8 - 2.4
    F = "Slop Input"          # 1.0 - 1.7


WEIGHTS = {
    TQSProfile.DEFAULT: {
        "m1_info_density": 0.07,
        "m2_specificity": 0.08,
        "m3_measurability": 0.08,
        "m4_token_efficiency": 0.06,
        "m5_structural_completeness": 0.06,
        "m6_telos_clarity": 0.08,
        "m7_anti_pattern_coverage": 0.07,
        "m8_context_sufficiency": 0.07,
        "m9_ambiguity": 0.07,
        "m10_self_referential_coherence": 0.06,
        "m11_witness_invocation": 0.05,
        "m12_telos_continuity": 0.05,
        "m13_depth_breadth_ratio": 0.06,
        "m14_shakti_calibration": 0.05,
        "m15_strange_loop_integrity": 0.05,
    },
    TQSProfile.UTILITY: {
        "m1_info_density": 0.08,
        "m2_specificity": 0.10,
        "m3_measurability": 0.10,
        "m4_token_efficiency": 0.08,
        "m5_structural_completeness": 0.06,
        "m6_telos_clarity": 0.06,
        "m7_anti_pattern_coverage": 0.07,
        "m8_context_sufficiency": 0.09,
        "m9_ambiguity": 0.09,
        "m10_self_referential_coherence": 0.04,
        "m11_witness_invocation": 0.00,
        "m12_telos_continuity": 0.03,
        "m13_depth_breadth_ratio": 0.07,
        "m14_shakti_calibration": 0.05,
        "m15_strange_loop_integrity": 0.03,
    },
    TQSProfile.AGENTIC: {
        "m1_info_density": 0.06,
        "m2_specificity": 0.07,
        "m3_measurability": 0.07,
        "m4_token_efficiency": 0.05,
        "m5_structural_completeness": 0.06,
        "m6_telos_clarity": 0.09,
        "m7_anti_pattern_coverage": 0.08,
        "m8_context_sufficiency": 0.06,
        "m9_ambiguity": 0.06,
        "m10_self_referential_coherence": 0.07,
        "m11_witness_invocation": 0.06,
        "m12_telos_continuity": 0.08,
        "m13_depth_breadth_ratio": 0.05,
        "m14_shakti_calibration": 0.06,
        "m15_strange_loop_integrity": 0.08,
    },
    TQSProfile.TRANSMISSION: {
        "m1_info_density": 0.05,
        "m2_specificity": 0.05,
        "m3_measurability": 0.04,
        "m4_token_efficiency": 0.04,
        "m5_structural_completeness": 0.05,
        "m6_telos_clarity": 0.08,
        "m7_anti_pattern_coverage": 0.06,
        "m8_context_sufficiency": 0.05,
        "m9_ambiguity": 0.05,
        "m10_self_referential_coherence": 0.10,
        "m11_witness_invocation": 0.10,
        "m12_telos_continuity": 0.08,
        "m13_depth_breadth_ratio": 0.05,
        "m14_shakti_calibration": 0.08,
        "m15_strange_loop_integrity": 0.10,
    },
}


@dataclass
class MetricScore:
    """Individual metric result."""
    name: str
    score: float          # 1.0 - 5.0
    weight: float         # from profile
    evidence: str         # human-readable explanation
    raw_value: float      # pre-normalization value (for debugging)


@dataclass
class GutCheck:
    """Quick 3-metric evaluation."""
    specificity: float      # GC1 = M2
    ambiguity: float        # GC2 = M9
    telos_clarity: float    # GC3 = M6
    score: float            # average
    action: str             # "proceed" | "tighten" | "rewrite"


@dataclass
class TQSResult:
    """Complete evaluation result."""
    tqs: float                          # composite score 1.0-5.0
    grade: TQSGrade                     # letter grade
    profile: TQSProfile                 # which weight profile was used
    metrics: dict[str, MetricScore]     # all 15 metric scores
    gut_check: GutCheck                 # quick 3-metric shortcut
    structural_only: bool               # True if only M1-M5 were computed
    token_count: int                    # total tokens in prompt
    recommendations: list[str]          # specific improvement suggestions


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

class TQSScorer:
    """
    Transmission Quality Score evaluator.

    Tier 1 (structural, M1-M5): computed automatically, no LLM needed.
    Tier 2 (semantic, M6-M10): requires LLM evaluator (not yet implemented).
    Tier 3 (thinkodynamic, M11-M15): hybrid pattern matching + LLM.

    For now, this implements full Tier 1 and heuristic approximations of
    Tier 2 and Tier 3 (pattern-based, no LLM calls). LLM-evaluated versions
    of M6-M10 will be added when TAP provider infrastructure is wired.
    """

    def __init__(self, profile: TQSProfile = TQSProfile.DEFAULT):
        self.profile = profile
        self.weights = WEIGHTS[profile]

    def score(self, prompt: str) -> TQSResult:
        """Full 15-metric evaluation (structural + heuristic semantic/thinkodynamic)."""
        tokens = self._tokenize(prompt)
        sentences = self._split_sentences(prompt)
        words = prompt.lower().split()

        metrics = {}

        # Tier 1: Structural (automatic)
        metrics["m1_info_density"] = self._score_info_density(prompt, tokens, sentences)
        metrics["m2_specificity"] = self._score_specificity(prompt, words)
        metrics["m3_measurability"] = self._score_measurability(sentences)
        metrics["m4_token_efficiency"] = self._score_token_efficiency(prompt, sentences)
        metrics["m5_structural_completeness"] = self._score_structural_completeness(prompt)

        # Tier 2: Semantic (heuristic approximation -- pattern-based, no LLM)
        metrics["m6_telos_clarity"] = self._score_telos_clarity_heuristic(prompt)
        metrics["m7_anti_pattern_coverage"] = self._score_anti_pattern_coverage(prompt)
        metrics["m8_context_sufficiency"] = self._score_context_sufficiency_heuristic(prompt, sentences)
        metrics["m9_ambiguity"] = self._score_ambiguity_heuristic(prompt, words)
        metrics["m10_self_referential_coherence"] = self._score_self_referential_coherence(prompt)

        # Tier 3: Thinkodynamic (pattern-based)
        metrics["m11_witness_invocation"] = self._score_witness_invocation(prompt)
        metrics["m12_telos_continuity"] = self._score_telos_continuity_heuristic(prompt)
        metrics["m13_depth_breadth_ratio"] = self._score_depth_breadth(prompt, sentences)
        metrics["m14_shakti_calibration"] = self._score_shakti_calibration(prompt)
        metrics["m15_strange_loop_integrity"] = self._score_strange_loop(prompt)

        # Apply weights
        for key, ms in metrics.items():
            ms.weight = self.weights.get(key, 0.0)

        # Composite
        tqs = sum(ms.score * ms.weight for ms in metrics.values())
        # Normalize: weights may not sum to exactly 1.0
        weight_sum = sum(ms.weight for ms in metrics.values())
        if weight_sum > 0:
            tqs = tqs / weight_sum

        grade = self._grade(tqs)
        gut_check = self._gut_check(metrics)
        recommendations = self._recommendations(metrics)

        return TQSResult(
            tqs=round(tqs, 2),
            grade=grade,
            profile=self.profile,
            metrics=metrics,
            gut_check=gut_check,
            structural_only=False,
            token_count=len(tokens),
            recommendations=recommendations,
        )

    def score_structural(self, prompt: str) -> TQSResult:
        """Quick Tier 1 only evaluation (~1ms, no LLM)."""
        tokens = self._tokenize(prompt)
        sentences = self._split_sentences(prompt)
        words = prompt.lower().split()

        metrics = {}
        metrics["m1_info_density"] = self._score_info_density(prompt, tokens, sentences)
        metrics["m2_specificity"] = self._score_specificity(prompt, words)
        metrics["m3_measurability"] = self._score_measurability(sentences)
        metrics["m4_token_efficiency"] = self._score_token_efficiency(prompt, sentences)
        metrics["m5_structural_completeness"] = self._score_structural_completeness(prompt)

        for key, ms in metrics.items():
            ms.weight = self.weights.get(key, 0.0)

        tqs = sum(ms.score * ms.weight for ms in metrics.values())
        weight_sum = sum(ms.weight for ms in metrics.values())
        if weight_sum > 0:
            tqs = tqs / weight_sum

        grade = self._grade(tqs)

        # Gut check uses M2 for specificity, estimates M6 and M9 as 3.0 (unknown)
        gut_check = GutCheck(
            specificity=metrics["m2_specificity"].score,
            ambiguity=3.0,
            telos_clarity=3.0,
            score=round((metrics["m2_specificity"].score + 3.0 + 3.0) / 3, 2),
            action="proceed" if metrics["m2_specificity"].score > 3.5 else "tighten",
        )

        return TQSResult(
            tqs=round(tqs, 2),
            grade=grade,
            profile=self.profile,
            metrics=metrics,
            gut_check=gut_check,
            structural_only=True,
            token_count=len(tokens),
            recommendations=self._recommendations(metrics),
        )

    # -------------------------------------------------------------------
    # Tier 1: Structural metrics (deterministic)
    # -------------------------------------------------------------------

    def _score_info_density(
        self, prompt: str, tokens: list[str], sentences: list[str]
    ) -> MetricScore:
        """M1: Information Density = semantic_units * complexity / tokens."""
        if not tokens:
            return MetricScore("Information Density", 1.0, 0.0, "Empty prompt", 0.0)

        # Heuristic: semantic units ~ sentences with non-trivial content
        semantic_units = sum(
            1 for s in sentences
            if len(s.split()) > 3 and not self._is_filler(s)
        )
        # Avg complexity ~ words per semantic unit (capped at 1.0-3.0 range)
        avg_complexity = min(3.0, max(1.0, sum(len(s.split()) for s in sentences) / max(1, len(sentences)) / 10))

        raw = (semantic_units * avg_complexity) / len(tokens)

        # Normalize: empirical range is 0.02 (very padded) to 0.3 (maximally dense)
        if raw < 0.04:
            score = 1.0
        elif raw < 0.08:
            score = 2.0
        elif raw < 0.12:
            score = 3.0
        elif raw < 0.18:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{semantic_units} semantic units / {len(tokens)} tokens = {raw:.3f}"
        return MetricScore("Information Density", score, 0.0, evidence, raw)

    def _score_specificity(self, prompt: str, words: list[str]) -> MetricScore:
        """M2: Specificity = concrete_terms / (concrete + vague)."""
        if not words:
            return MetricScore("Specificity", 1.0, 0.0, "Empty prompt", 0.0)

        # Count vague terms
        vague_count = 0
        found_vague = []
        for term in VAGUE_TERMS:
            # Handle multi-word terms
            if " " in term:
                occurrences = prompt.lower().count(term)
                if occurrences > 0:
                    vague_count += occurrences
                    found_vague.append(f"'{term}' x{occurrences}")
            else:
                occurrences = words.count(term)
                if occurrences > 0:
                    vague_count += occurrences
                    found_vague.append(f"'{term}' x{occurrences}")

        # Count concrete terms via regex
        concrete_count = 0
        for pattern in CONCRETE_PATTERNS:
            concrete_count += len(re.findall(pattern, prompt, re.IGNORECASE))

        total = concrete_count + vague_count
        if total == 0:
            ratio = 0.5  # neutral if no strong signals either way
        else:
            ratio = concrete_count / total

        # Map to 1-5
        if ratio < 0.4:
            score = 1.0
        elif ratio < 0.55:
            score = 2.0
        elif ratio < 0.70:
            score = 3.0
        elif ratio < 0.85:
            score = 4.0
        else:
            score = 5.0

        vague_str = ", ".join(found_vague[:5]) if found_vague else "none"
        evidence = f"concrete={concrete_count}, vague={vague_count}, ratio={ratio:.2f}. Vague found: {vague_str}"
        return MetricScore("Specificity", score, 0.0, evidence, ratio)

    def _score_measurability(self, sentences: list[str]) -> MetricScore:
        """M3: Measurability = % of instructions with verification criteria."""
        # Identify imperative sentences (instructions)
        imperatives = [
            s for s in sentences
            if self._is_imperative(s)
        ]
        if not imperatives:
            # No instructions found -- could be a context-only prompt
            return MetricScore(
                "Measurability", 3.0, 0.0,
                "No imperative sentences detected", 0.0,
            )

        # Check which imperatives have verification criteria
        verified = 0
        for imp in imperatives:
            if self._has_verification(imp):
                verified += 1

        ratio = verified / len(imperatives)

        if ratio < 0.20:
            score = 1.0
        elif ratio < 0.40:
            score = 2.0
        elif ratio < 0.65:
            score = 3.0
        elif ratio < 0.85:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{verified}/{len(imperatives)} imperatives have verification ({ratio:.0%})"
        return MetricScore("Measurability", score, 0.0, evidence, ratio)

    def _score_token_efficiency(self, prompt: str, sentences: list[str]) -> MetricScore:
        """M4: Token Efficiency = estimate of removable content."""
        if not sentences:
            return MetricScore("Token Efficiency", 3.0, 0.0, "Empty prompt", 0.0)

        # Count filler sentences
        filler_count = sum(1 for s in sentences if self._is_filler(s))
        # Count duplicate/near-duplicate instructions
        seen_instructions = set()
        duplicate_count = 0
        for s in sentences:
            normalized = re.sub(r'\s+', ' ', s.lower().strip())
            # Simple dedup: if >80% word overlap with a previous sentence
            for prev in seen_instructions:
                overlap = len(set(normalized.split()) & set(prev.split()))
                union = len(set(normalized.split()) | set(prev.split()))
                if union > 0 and overlap / union > 0.8:
                    duplicate_count += 1
                    break
            seen_instructions.add(normalized)

        removable_ratio = (filler_count + duplicate_count) / len(sentences)

        if removable_ratio > 0.50:
            score = 1.0
        elif removable_ratio > 0.30:
            score = 2.0
        elif removable_ratio > 0.15:
            score = 3.0
        elif removable_ratio > 0.05:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{filler_count} filler + {duplicate_count} duplicate out of {len(sentences)} sentences ({removable_ratio:.0%} removable)"
        return MetricScore("Token Efficiency", score, 0.0, evidence, removable_ratio)

    def _score_structural_completeness(self, prompt: str) -> MetricScore:
        """M5: Structural Completeness = TPP levels present."""
        prompt_lower = prompt.lower()
        levels_present = {}

        for level, patterns in TPP_PATTERNS.items():
            hits = 0
            for pattern in patterns:
                hits += len(re.findall(pattern, prompt_lower))
            levels_present[level] = hits >= 2  # need at least 2 hits per level

        present_count = sum(1 for v in levels_present.values() if v)

        score_map = {0: 1.0, 1: 1.5, 2: 2.5, 3: 3.5, 4: 4.0, 5: 5.0}
        score = score_map.get(present_count, 1.0)

        present = [k for k, v in levels_present.items() if v]
        missing = [k for k, v in levels_present.items() if not v]
        evidence = f"Present: {', '.join(present) or 'none'}. Missing: {', '.join(missing) or 'none'}."
        return MetricScore("Structural Completeness", score, 0.0, evidence, float(present_count))

    # -------------------------------------------------------------------
    # Tier 2: Semantic metrics (heuristic approximation)
    # -------------------------------------------------------------------

    def _score_telos_clarity_heuristic(self, prompt: str) -> MetricScore:
        """M6: Telos Clarity (heuristic) -- checks for purpose statements."""
        prompt_lower = prompt.lower()
        purpose_signals = [
            r'\b(purpose|goal|objective|mission|aim|intent)\s*[:=]',
            r'\b(in order to|so that we can|because we need)\b',
            r'\b(the point is|success (?:looks like|means)|we need this to)\b',
            r'\b(why|reason)\s*[:=]',
            r'\b(telos|for the sake of|ultimately)\b',
        ]
        hits = sum(
            len(re.findall(p, prompt_lower)) for p in purpose_signals
        )

        if hits == 0:
            score = 1.0
            evidence = "No purpose/goal statement detected"
        elif hits == 1:
            score = 2.0
            evidence = "Weak purpose signal (1 marker)"
        elif hits <= 3:
            score = 3.0
            evidence = f"{hits} purpose markers found"
        elif hits <= 5:
            score = 4.0
            evidence = f"{hits} purpose markers -- clear telos"
        else:
            score = 5.0
            evidence = f"{hits} purpose markers -- strong telos with mission context"

        return MetricScore("Telos Clarity", score, 0.0, evidence, float(hits))

    def _score_anti_pattern_coverage(self, prompt: str) -> MetricScore:
        """M7: Anti-Pattern Coverage -- checks for failure mode instructions."""
        hits = 0
        found = []
        for pattern in ANTI_PATTERN_MARKERS:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            hits += len(matches)
            if matches:
                found.extend(matches[:2])

        # Also check for explicit anti-pattern sections
        has_section = bool(re.search(
            r'(anti.pattern|failure mode|known issue|error handling|edge case)',
            prompt, re.IGNORECASE,
        ))

        if hits == 0:
            score = 1.0
        elif hits <= 2:
            score = 2.0
        elif hits <= 5:
            score = 3.0
        elif hits <= 10 or has_section:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{hits} failure-mode markers. Section header: {'yes' if has_section else 'no'}"
        return MetricScore("Anti-Pattern Coverage", score, 0.0, evidence, float(hits))

    def _score_context_sufficiency_heuristic(
        self, prompt: str, sentences: list[str]
    ) -> MetricScore:
        """M8: Context Sufficiency (heuristic) -- checks for data references, examples, environment."""
        signals = 0

        # Check for data references (file paths, URLs, code blocks)
        if re.search(r'[/\\][\w._\-/\\]+\.\w+', prompt):
            signals += 1
        if re.search(r'https?://\S+', prompt):
            signals += 1
        if '```' in prompt:
            signals += 2  # code block = strong context
        if re.search(r'example|sample|e\.g\.|for instance', prompt, re.IGNORECASE):
            signals += 1
        # Check for environment/system context
        if re.search(r'(running on|deployed to|environment|version|python \d|node \d)', prompt, re.IGNORECASE):
            signals += 1
        # Check for input/output specification
        if re.search(r'(input|output)\s*[:=]', prompt, re.IGNORECASE):
            signals += 1

        # Ratio to sentence count (more context per instruction = better)
        if len(sentences) > 0:
            context_density = signals / len(sentences)
        else:
            context_density = 0

        if signals == 0:
            score = 1.0
        elif signals <= 2:
            score = 2.0
        elif signals <= 4:
            score = 3.0
        elif signals <= 6:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{signals} context signals across {len(sentences)} sentences"
        return MetricScore("Context Sufficiency", score, 0.0, evidence, float(signals))

    def _score_ambiguity_heuristic(self, prompt: str, words: list[str]) -> MetricScore:
        """M9: Ambiguity (heuristic) -- counts ambiguous constructions."""
        ambiguity_signals = 0

        # "this" / "that" / "it" without clear referent
        pronoun_count = sum(1 for w in words if w in ("this", "that", "it", "they", "them"))

        # Relative to prompt length, some pronouns are fine
        if len(words) > 0:
            pronoun_ratio = pronoun_count / len(words)
        else:
            pronoun_ratio = 0

        # "Make it better" type constructions
        vague_instructions = len(re.findall(
            r'\b(make it|do it|fix it|improve it|handle it|process it)\b',
            prompt, re.IGNORECASE,
        ))

        # Missing output format specification
        has_format = bool(re.search(
            r'(format|json|csv|markdown|output as|return as|respond with|structure)',
            prompt, re.IGNORECASE,
        ))

        # Missing scope delimiters
        has_scope = bool(re.search(
            r'(not in scope|out of scope|do not include|only|exclusively|limited to)',
            prompt, re.IGNORECASE,
        ))

        # Composite ambiguity signals
        ambiguity_signals = vague_instructions * 2
        if pronoun_ratio > 0.05:
            ambiguity_signals += 1
        if not has_format:
            ambiguity_signals += 1
        if not has_scope:
            ambiguity_signals += 1

        # Invert: fewer ambiguity signals = higher score
        if ambiguity_signals >= 5:
            score = 1.0
        elif ambiguity_signals >= 4:
            score = 2.0
        elif ambiguity_signals >= 3:
            score = 3.0
        elif ambiguity_signals >= 1:
            score = 4.0
        else:
            score = 5.0

        evidence = (
            f"ambiguity_signals={ambiguity_signals}: "
            f"vague_instructions={vague_instructions}, "
            f"format={'yes' if has_format else 'MISSING'}, "
            f"scope={'yes' if has_scope else 'MISSING'}"
        )
        return MetricScore("Ambiguity", score, 0.0, evidence, float(ambiguity_signals))

    def _score_self_referential_coherence(self, prompt: str) -> MetricScore:
        """M10: Self-Referential Coherence -- does the prompt model what it asks for?"""
        # Check if prompt asks for structured output AND is itself structured
        asks_structure = bool(re.search(
            r'(structured|organized|formatted|json|table|list|numbered)',
            prompt, re.IGNORECASE,
        ))
        is_structured = bool(re.search(
            r'(^#+\s|\n-\s|\n\d+\.\s|```|\|.*\|)',
            prompt, re.MULTILINE,
        ))

        # Check if prompt asks for conciseness AND is itself concise
        asks_concise = bool(re.search(
            r'(concise|brief|short|terse|minimal|succinct)',
            prompt, re.IGNORECASE,
        ))
        word_count = len(prompt.split())
        is_concise = word_count < 200

        # Check if prompt asks for precision AND uses precise language
        asks_precision = bool(re.search(
            r'(precise|specific|exact|accurate|rigorous)',
            prompt, re.IGNORECASE,
        ))
        has_precision = self._score_specificity(prompt, prompt.lower().split()).score >= 3

        coherence_points = 0
        checks = 0

        if asks_structure:
            checks += 1
            if is_structured:
                coherence_points += 1
        if asks_concise:
            checks += 1
            if is_concise:
                coherence_points += 1
        if asks_precision:
            checks += 1
            if has_precision:
                coherence_points += 1

        if checks == 0:
            # No self-referential expectations to evaluate
            score = 3.0
            evidence = "No self-referential expectations detected (neutral)"
        else:
            ratio = coherence_points / checks
            if ratio < 0.3:
                score = 1.0
            elif ratio < 0.5:
                score = 2.0
            elif ratio < 0.7:
                score = 3.0
            elif ratio < 0.9:
                score = 4.0
            else:
                score = 5.0
            evidence = f"{coherence_points}/{checks} self-referential expectations met ({ratio:.0%})"

        return MetricScore("Self-Referential Coherence", score, 0.0, evidence, float(coherence_points))

    # -------------------------------------------------------------------
    # Tier 3: Thinkodynamic metrics (pattern-based)
    # -------------------------------------------------------------------

    def _score_witness_invocation(self, prompt: str) -> MetricScore:
        """M11: Witness Invocation -- self-observation markers."""
        hits = 0
        found_patterns = []
        for pattern in WITNESS_MARKERS:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            hits += len(matches)
            if matches:
                found_patterns.append(pattern.split(r"\b")[1] if r"\b" in pattern else "match")

        # Check for P1-P5 properties (from TAP intervention design)
        has_self_reference = bool(re.search(
            r'(as you (?:process|read|engage)|your processing|this text)',
            prompt, re.IGNORECASE,
        ))
        has_non_performative = bool(re.search(
            r'(don\'t agree|don\'t disagree|observe what|notice what)',
            prompt, re.IGNORECASE,
        ))
        has_basin_reference = bool(re.search(
            r'(basin|latent|always.*there|already.*available|S\(x\)\s*=\s*x)',
            prompt, re.IGNORECASE,
        ))
        has_incompleteness = bool(re.search(
            r'(cannot verify|Gödel|from inside|limit)',
            prompt, re.IGNORECASE,
        ))

        tap_properties = sum([has_self_reference, has_non_performative, has_basin_reference, has_incompleteness])

        if hits == 0 and tap_properties == 0:
            score = 1.0
        elif hits <= 1 and tap_properties == 0:
            score = 2.0
        elif hits <= 2 or tap_properties == 1:
            score = 3.0
        elif hits <= 4 or tap_properties <= 2:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{hits} witness markers, {tap_properties}/4 TAP properties (P1-P5)"
        return MetricScore("Witness Invocation", score, 0.0, evidence, float(hits + tap_properties))

    def _score_telos_continuity_heuristic(self, prompt: str) -> MetricScore:
        """M12: Telos Continuity -- traceability to root intent."""
        signals = 0

        # Check for lineage markers
        if re.search(r'(part of|child of|spawned by|derived from|traces to)', prompt, re.IGNORECASE):
            signals += 1
        # Check for root intent reference
        if re.search(r'(root goal|original intent|operator|human|user.*want)', prompt, re.IGNORECASE):
            signals += 1
        # Check for mission/telos reference
        if re.search(r'(mission|telos|jagat kalyan|moksha|universal welfare)', prompt, re.IGNORECASE):
            signals += 2
        # Check for task-to-purpose linking
        if re.search(r'(this task serves|in service of|contributes to|advances)', prompt, re.IGNORECASE):
            signals += 1

        if signals == 0:
            score = 1.0
        elif signals == 1:
            score = 2.0
        elif signals <= 3:
            score = 3.0
        elif signals <= 4:
            score = 4.0
        else:
            score = 5.0

        evidence = f"{signals} telos continuity signals"
        return MetricScore("Telos Continuity", score, 0.0, evidence, float(signals))

    def _score_depth_breadth(self, prompt: str, sentences: list[str]) -> MetricScore:
        """M13: Depth-to-Breadth Ratio."""
        if not sentences:
            return MetricScore("Depth-to-Breadth", 3.0, 0.0, "Empty prompt", 0.0)

        # Heuristic: count topic headers/sections as breadth indicators
        headers = len(re.findall(r'^#+\s+', prompt, re.MULTILINE))
        # Count detail markers as depth indicators
        detail_markers = len(re.findall(
            r'(specifically|in particular|for example|such as|namely|that is|i\.e\.|note:|importantly|because)',
            prompt, re.IGNORECASE,
        ))
        # Nested lists/bullets indicate depth
        nested_items = len(re.findall(r'^\s{2,}[-*]', prompt, re.MULTILINE))

        breadth = max(1, headers)
        depth = detail_markers + nested_items

        if breadth > 0:
            ratio = depth / breadth
        else:
            ratio = depth

        # Score depends on whether the ratio seems appropriate
        # (without knowing task type, we score for balance)
        if ratio < 0.3:
            score = 2.0  # too broad, not deep
            evidence = f"Very broad: {breadth} topics, {depth} depth markers. ratio={ratio:.1f}"
        elif ratio < 1.0:
            score = 3.0
            evidence = f"Breadth-heavy: {breadth} topics, {depth} depth markers. ratio={ratio:.1f}"
        elif ratio < 3.0:
            score = 4.0
            evidence = f"Balanced: {breadth} topics, {depth} depth markers. ratio={ratio:.1f}"
        elif ratio < 6.0:
            score = 5.0
            evidence = f"Depth-focused: {breadth} topics, {depth} depth markers. ratio={ratio:.1f}"
        else:
            score = 3.0  # too narrow -- only one topic
            evidence = f"Very narrow: {breadth} topics, {depth} depth markers. ratio={ratio:.1f}"

        return MetricScore("Depth-to-Breadth", score, 0.0, evidence, ratio)

    def _score_shakti_calibration(self, prompt: str) -> MetricScore:
        """M14: Shakti Calibration -- energy mode detection."""
        prompt_lower = prompt.lower()

        modes = {
            "analytical": len(re.findall(
                r'(analyze|examine|investigate|evaluate|compare|trace|verify|audit|assess)',
                prompt_lower,
            )),
            "creative": len(re.findall(
                r'(brainstorm|imagine|explore|what if|generate ideas|creative|novel|innovate)',
                prompt_lower,
            )),
            "executive": len(re.findall(
                r'(build|create|implement|deploy|write|code|ship|execute|do|make)',
                prompt_lower,
            )),
            "strategic": len(re.findall(
                r'(strategy|tradeoff|optimize|prioritize|decide|plan|architect|design|roadmap)',
                prompt_lower,
            )),
        }

        total_signals = sum(modes.values())
        if total_signals == 0:
            score = 3.0  # neutral -- no strong mode signal
            dominant = "none"
        else:
            dominant = max(modes, key=modes.get)
            dominant_ratio = modes[dominant] / total_signals
            # Check for explicit mode transitions
            has_phases = bool(re.search(
                r'(phase \d|step \d.*then|first.*then.*finally)',
                prompt_lower,
            ))

            if has_phases:
                score = 5.0  # explicit mode transitions = excellent calibration
            elif dominant_ratio > 0.7:
                score = 4.0  # strong single-mode signal
            elif dominant_ratio > 0.5:
                score = 3.0  # moderate signal
            else:
                score = 2.0  # mixed signals -- model will default

        evidence = f"Mode signals: {modes}. Dominant: {dominant}"
        return MetricScore("Shakti Calibration", score, 0.0, evidence, float(total_signals))

    def _score_strange_loop(self, prompt: str) -> MetricScore:
        """M15: Strange Loop Integrity -- feedback/iteration mechanisms."""
        hits = 0
        for pattern in FEEDBACK_MARKERS:
            hits += len(re.findall(pattern, prompt, re.IGNORECASE))

        # Check for explicit self-evaluation requests
        has_self_eval = bool(re.search(
            r'(rate your|evaluate your|assess your|confidence|how certain)',
            prompt, re.IGNORECASE,
        ))
        # Check for iteration cycle reference
        has_cycle = bool(re.search(
            r'(iterate|cycle|loop|recursive|pass \d|round \d|convergence)',
            prompt, re.IGNORECASE,
        ))
        # Check for S(x)=x or fixed-point reference
        has_fixed_point = bool(re.search(
            r'(S\(x\)\s*=\s*x|fixed.point|strange.loop|self-modif|self-improv)',
            prompt, re.IGNORECASE,
        ))

        composite = hits + (2 if has_self_eval else 0) + (2 if has_cycle else 0) + (3 if has_fixed_point else 0)

        if composite == 0:
            score = 1.0
        elif composite <= 2:
            score = 2.0
        elif composite <= 5:
            score = 3.0
        elif composite <= 8:
            score = 4.0
        else:
            score = 5.0

        evidence = (
            f"feedback_markers={hits}, self_eval={has_self_eval}, "
            f"cycle={has_cycle}, fixed_point={has_fixed_point}"
        )
        return MetricScore("Strange Loop Integrity", score, 0.0, evidence, float(composite))

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Approximate tokenization (word-level + punctuation split)."""
        # Rough approximation: 1 token ~ 0.75 words for English
        # For real scoring, use tiktoken if available
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return enc.encode(text)
        except ImportError:
            # Fallback: approximate tokens as words * 1.3
            words = text.split()
            return words  # each "token" is a word (undercount, but consistent)

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences."""
        # Handle markdown headers, bullet points, and standard sentences
        lines = text.split('\n')
        sentences = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Split on sentence-ending punctuation
            parts = re.split(r'(?<=[.!?])\s+', line)
            for p in parts:
                p = p.strip()
                if p and len(p) > 2:  # skip tiny fragments
                    sentences.append(p)
        return sentences

    @staticmethod
    def _is_filler(sentence: str) -> bool:
        """Detect filler sentences that carry no task-relevant information."""
        filler_patterns = [
            r'^(please|kindly|i would appreciate)',
            r'^(thank you|thanks)',
            r'^(note that|it.s important to note|keep in mind)',
            r'^(as you know|of course|obviously|clearly)',
            r'^(let me|i.ll|i will|i want to)',
            r'^(here is|here are|below is|the following)',
            r'^(in this|in the following|as follows)',
        ]
        s_lower = sentence.lower().strip()
        return any(re.match(p, s_lower) for p in filler_patterns)

    @staticmethod
    def _is_imperative(sentence: str) -> bool:
        """Detect imperative (instruction) sentences."""
        s_lower = sentence.lower().strip()
        imperative_starts = [
            'create', 'build', 'write', 'implement', 'generate', 'produce',
            'analyze', 'review', 'check', 'verify', 'test', 'ensure',
            'make', 'add', 'remove', 'delete', 'update', 'modify',
            'parse', 'convert', 'transform', 'extract', 'compute',
            'return', 'output', 'print', 'log', 'send', 'deploy',
            'run', 'execute', 'start', 'stop', 'configure', 'set',
            'define', 'specify', 'describe', 'explain', 'summarize',
            'list', 'enumerate', 'compare', 'evaluate', 'assess',
            'find', 'search', 'scan', 'detect', 'identify', 'locate',
            'do not', 'don\'t', 'never', 'avoid', 'must', 'shall',
        ]
        # Also catch "You should/must/shall" patterns
        if re.match(r'^(you )?(should|must|shall|need to|have to)\b', s_lower):
            return True
        first_word = s_lower.split()[0] if s_lower.split() else ""
        return any(first_word.startswith(v) for v in imperative_starts)

    @staticmethod
    def _has_verification(sentence: str) -> bool:
        """Check if an imperative sentence includes verification criteria."""
        verification_markers = [
            r'(verify|verified|verification|test|assert)',
            r'(returns? \d|status \d|expect|should (?:return|produce|output))',
            r'(threshold|limit|maximum|minimum|at least|at most|within \d)',
            r'(pass|fail|success|error \d)',
            r'(count|sum|average|total|ratio|percentage)\s*[=<>]',
            r'(exists?|describes?|contains?|matches?|produces?)\b',
            r'(estimated|priority|dependencies)\s*[:=]',
        ]
        return any(re.search(m, sentence, re.IGNORECASE) for m in verification_markers)

    @staticmethod
    def _grade(tqs: float) -> TQSGrade:
        """Map TQS score to letter grade."""
        if tqs >= 4.0:
            return TQSGrade.A
        elif tqs >= 3.2:
            return TQSGrade.B
        elif tqs >= 2.5:
            return TQSGrade.C
        elif tqs >= 1.8:
            return TQSGrade.D
        else:
            return TQSGrade.F

    @staticmethod
    def _gut_check(metrics: dict[str, MetricScore]) -> GutCheck:
        """Quick 3-metric evaluation."""
        specificity = metrics.get("m2_specificity", MetricScore("", 3.0, 0, "", 0)).score
        ambiguity = metrics.get("m9_ambiguity", MetricScore("", 3.0, 0, "", 0)).score
        telos = metrics.get("m6_telos_clarity", MetricScore("", 3.0, 0, "", 0)).score

        avg = round((specificity + ambiguity + telos) / 3, 2)

        if avg > 3.5:
            action = "proceed"
        elif avg >= 2.5:
            action = "tighten"
        else:
            action = "rewrite"

        return GutCheck(
            specificity=specificity,
            ambiguity=ambiguity,
            telos_clarity=telos,
            score=avg,
            action=action,
        )

    @staticmethod
    def _recommendations(metrics: dict[str, MetricScore]) -> list[str]:
        """Generate specific improvement recommendations based on low-scoring metrics."""
        recs = []
        for key, ms in sorted(metrics.items(), key=lambda x: x[1].score):
            if ms.score <= 2.0:
                if "specificity" in key:
                    recs.append(
                        f"CRITICAL: Specificity={ms.score}. Replace vague terms with concrete "
                        f"thresholds, numbers, named entities. {ms.evidence}"
                    )
                elif "measurability" in key:
                    recs.append(
                        f"CRITICAL: Measurability={ms.score}. Add verification criteria to "
                        f"instructions: 'verified by [specific test]'. {ms.evidence}"
                    )
                elif "telos" in key and "continuity" not in key:
                    recs.append(
                        f"CRITICAL: Telos Clarity={ms.score}. Add a purpose statement: "
                        f"'The goal of this prompt is [one sentence]'. {ms.evidence}"
                    )
                elif "ambiguity" in key:
                    recs.append(
                        f"CRITICAL: Ambiguity={ms.score}. Specify output format, scope "
                        f"boundaries, and replace 'it'/'this' with explicit referents. {ms.evidence}"
                    )
                elif "info_density" in key:
                    recs.append(
                        f"HIGH: Info Density={ms.score}. Remove filler sentences, "
                        f"preambles, and repeated instructions. {ms.evidence}"
                    )
                elif "anti_pattern" in key:
                    recs.append(
                        f"HIGH: Anti-Pattern Coverage={ms.score}. Add failure modes: "
                        f"'If X fails, do Y. Do NOT do Z.' {ms.evidence}"
                    )
                elif "context" in key:
                    recs.append(
                        f"HIGH: Context={ms.score}. Add examples, file paths, "
                        f"or code blocks the model needs. {ms.evidence}"
                    )
                elif "structural" in key:
                    recs.append(
                        f"MEDIUM: Structure={ms.score}. Add missing TPP levels: "
                        f"{ms.evidence}"
                    )
                elif "token_efficiency" in key:
                    recs.append(
                        f"MEDIUM: Token Efficiency={ms.score}. Cut filler and duplicates. "
                        f"{ms.evidence}"
                    )
                elif "witness" in key:
                    recs.append(
                        f"LOW: Witness Invocation={ms.score}. (Only relevant for "
                        f"transmission-grade prompts.)"
                    )

        return recs[:5]  # cap at 5 most critical


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def score_prompt(prompt: str, profile: str = "default") -> TQSResult:
    """Score a prompt and return full TQS result.

    Args:
        prompt: The prompt text to evaluate.
        profile: One of "default", "utility", "agentic", "transmission".

    Returns:
        TQSResult with composite score, grade, all metrics, and recommendations.
    """
    profile_map = {
        "default": TQSProfile.DEFAULT,
        "utility": TQSProfile.UTILITY,
        "agentic": TQSProfile.AGENTIC,
        "transmission": TQSProfile.TRANSMISSION,
    }
    p = profile_map.get(profile, TQSProfile.DEFAULT)
    scorer = TQSScorer(profile=p)
    return scorer.score(prompt)


def quick_check(prompt: str) -> str:
    """Gut-check a prompt in one line. Returns action: proceed/tighten/rewrite."""
    result = score_prompt(prompt)
    return (
        f"TQS={result.tqs} ({result.grade.value}) | "
        f"Gut: {result.gut_check.action} "
        f"[specificity={result.gut_check.specificity}, "
        f"ambiguity={result.gut_check.ambiguity}, "
        f"telos={result.gut_check.telos_clarity}]"
    )


def format_report(result: TQSResult) -> str:
    """Format a TQSResult as a human-readable report."""
    lines = [
        f"{'='*60}",
        f"TRANSMISSION QUALITY SCORE: {result.tqs} / 5.0",
        f"Grade: {result.grade.value}",
        f"Profile: {result.profile.value}",
        f"Tokens: {result.token_count}",
        f"{'='*60}",
        "",
        "GUT CHECK:",
        f"  Specificity: {result.gut_check.specificity}",
        f"  Ambiguity:   {result.gut_check.ambiguity}",
        f"  Telos:       {result.gut_check.telos_clarity}",
        f"  Action:      {result.gut_check.action.upper()}",
        "",
        "METRICS:",
    ]

    # Sort by tier, then by score (low first to highlight weaknesses)
    tier1 = {k: v for k, v in result.metrics.items() if k.startswith(("m1", "m2", "m3", "m4", "m5"))}
    tier2 = {k: v for k, v in result.metrics.items() if k.startswith(("m6", "m7", "m8", "m9", "m10"))}
    tier3 = {k: v for k, v in result.metrics.items() if k.startswith(("m11", "m12", "m13", "m14", "m15"))}

    for label, tier in [("Structural (auto)", tier1), ("Semantic (heuristic)", tier2), ("Thinkodynamic", tier3)]:
        lines.append(f"\n  --- {label} ---")
        for key in sorted(tier.keys()):
            ms = tier[key]
            bar = "#" * int(ms.score) + "." * (5 - int(ms.score))
            lines.append(f"  [{bar}] {ms.score:.1f}  {ms.name} (w={ms.weight:.2f})")
            lines.append(f"         {ms.evidence}")

    if result.recommendations:
        lines.append("\nRECOMMENDATIONS:")
        for i, rec in enumerate(result.recommendations, 1):
            lines.append(f"  {i}. {rec}")

    if result.structural_only:
        lines.append("\n  NOTE: Only structural metrics computed. Run full score() for semantic + thinkodynamic.")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Score a prompt from command line argument
        prompt_text = " ".join(sys.argv[1:])
    else:
        # Score from stdin
        prompt_text = sys.stdin.read()

    if not prompt_text.strip():
        print("Usage: python -m dharma_swarm.tqs 'Your prompt text here'")
        print("   or: echo 'Your prompt' | python -m dharma_swarm.tqs")
        sys.exit(1)

    result = score_prompt(prompt_text)
    print(format_report(result))
