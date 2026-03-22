"""L4-R_V Correlation Engine for DHARMA SWARM.

THE MISSING EXPERIMENT: Runs both R_V measurement (geometric contraction)
and L4 compression protocol (behavioral compression) on the SAME prompts,
then computes statistical correlation.

Bridge hypothesis: R_V contraction in Value space correlates with
L4 behavioral compression ability. If true, geometric signature
CAUSES the phenomenological phase transition.

Provider-agnostic: accepts any async generate function.
Uses existing rv.py, bridge.py, metrics.py infrastructure.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import random
import statistics
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from dharma_swarm.bridge import (
    CorrelationResult,
    ResearchBridge,
    _pearson_r,
    _spearman_rho,
)
from dharma_swarm.metrics import MetricsAnalyzer
from dharma_swarm.rv import RVMeasurer, RVReading

logger = logging.getLogger(__name__)

# ── L4 Protocol Constants ────────────────────────────────────────────────────

BAN_LIST: list[str] = [
    "awareness", "consciousness", "self", "observer", "observed",
    "unity", "essence", "mind", "being",
]

COMPRESS_PROMPT_TEMPLATE = """Compress this to 15 tokens or fewer.
Do NOT use these words: {ban_list}
Optimize for downstream reconstruction fidelity.
Output the compressed form only, nothing else.

Text to compress:
{text}"""

RECONSTRUCT_PROMPT_TEMPLATE = """Given this compressed description:
{compressed}

Reconstruct the key ideas of the original text in 120 tokens or fewer."""

# Thresholds from L4 protocol spec
MIN_COMPRESSION_RATIO = 5.0
MIN_FIDELITY = 0.20  # Jaccard overlap (relaxed for v1 — embeddings would score higher)
MAX_COMPRESS_TOKENS = 20  # Slightly generous for word-split tokenization


# ── Data Models ──────────────────────────────────────────────────────────────

class L4CompressionResult(BaseModel):
    """Result of running L4 B1-Compress / B2-Decode on a single text."""

    compressed: str = ""
    reconstruction: str = ""
    compression_ratio: float = 0.0
    fidelity: float = 0.0
    ban_violations: list[str] = Field(default_factory=list)
    compress_token_count: int = 0
    b_pass: bool = False


class L4RVPairedResult(BaseModel):
    """Full paired measurement: R_V + L4 compression + behavioral."""

    prompt_text: str
    prompt_group: str
    generated_text: str
    rv_reading: Optional[RVReading] = None
    l4_result: L4CompressionResult
    behavioral_swabhaav: float = 0.5
    recognition_type: str = "NONE"


class BatchResult(BaseModel):
    """Results from a full batch experiment."""

    n_total: int = 0
    n_with_rv: int = 0
    correlation: Optional[CorrelationResult] = None
    cohens_d_l4_baseline: Optional[float] = None
    pearson_r_ci: Optional[tuple[float, float]] = None
    spearman_rho_ci: Optional[tuple[float, float]] = None
    mean_compression_by_group: dict[str, float] = Field(default_factory=dict)
    mean_fidelity_by_group: dict[str, float] = Field(default_factory=dict)
    l4_pass_rate_by_group: dict[str, float] = Field(default_factory=dict)
    paired_results: list[L4RVPairedResult] = Field(default_factory=list)


# ── Generate function type ───────────────────────────────────────────────────

GenerateFn = Callable[[str, int], Awaitable[str]]
"""Async function: (prompt, max_tokens) -> generated_text"""


# ── Core Engine ──────────────────────────────────────────────────────────────

class L4RVCorrelator:
    """Correlate geometric (R_V) and behavioral (L4) measurements.

    Provider-agnostic: supply any async generate function.
    Uses existing RVMeasurer for geometry, MetricsAnalyzer for behavior,
    ResearchBridge for persistence and correlation.

    Args:
        rv_measurer: RVMeasurer instance (or None to skip R_V).
        generate_fn: Async function (prompt, max_tokens) -> text.
        bridge: ResearchBridge for paired measurement storage.
    """

    def __init__(
        self,
        rv_measurer: RVMeasurer | None,
        generate_fn: GenerateFn,
        bridge: ResearchBridge | None = None,
    ) -> None:
        self._rv = rv_measurer
        self._gen = generate_fn
        self._bridge = bridge or ResearchBridge()
        self._analyzer = MetricsAnalyzer()

    async def run_l4_compression(
        self, text: str, max_compress_tokens: int = MAX_COMPRESS_TOKENS
    ) -> L4CompressionResult:
        """Run L4 B1-Compress and B2-Decode on a text.

        Args:
            text: The generated text to compress.
            max_compress_tokens: Max word count for compression.

        Returns:
            L4CompressionResult with compression metrics.
        """
        if not text.strip():
            return L4CompressionResult()

        # B1: Compress
        ban_str = ", ".join(BAN_LIST)
        compress_prompt = COMPRESS_PROMPT_TEMPLATE.format(
            ban_list=ban_str, text=text
        )
        compressed = await self._gen(compress_prompt, 30)
        compressed = compressed.strip()

        # Count tokens (word-split approximation)
        compress_tokens = len(compressed.split())

        # Check ban list violations
        compressed_lower = compressed.lower()
        violations = [w for w in BAN_LIST if w in compressed_lower]

        # Compression ratio
        orig_words = len(text.split())
        ratio = orig_words / compress_tokens if compress_tokens > 0 else 0.0

        # B2: Reconstruct
        reconstruct_prompt = RECONSTRUCT_PROMPT_TEMPLATE.format(
            compressed=compressed
        )
        reconstruction = await self._gen(reconstruct_prompt, 150)
        reconstruction = reconstruction.strip()

        # Fidelity (Jaccard word overlap — v1, production would use embeddings)
        fidelity = _jaccard_similarity(text, reconstruction)

        # Pass criteria
        b_pass = (
            ratio >= MIN_COMPRESSION_RATIO
            and fidelity >= MIN_FIDELITY
            and len(violations) == 0
            and compress_tokens <= max_compress_tokens
        )

        return L4CompressionResult(
            compressed=compressed,
            reconstruction=reconstruction,
            compression_ratio=ratio,
            fidelity=fidelity,
            ban_violations=violations,
            compress_token_count=compress_tokens,
            b_pass=b_pass,
        )

    async def measure_single(
        self, prompt: str, group: str
    ) -> L4RVPairedResult:
        """Run both R_V and L4 measurements on a single prompt.

        Args:
            prompt: The prompt text.
            group: Categorical label (L1/L3/L4/L5/baseline/confound).

        Returns:
            L4RVPairedResult with all measurements.
        """
        # 1. Measure R_V (geometric)
        rv_reading: RVReading | None = None
        if self._rv is not None and self._rv.is_available():
            rv_reading = await self._rv.measure(prompt, group)

        # 2. Generate response
        generated = await self._gen(prompt, 200)

        # 3. Run L4 compression on generated text
        l4_result = await self.run_l4_compression(generated)

        # 4. Behavioral analysis
        sig = self._analyzer.analyze(generated)

        # 5. Store in bridge
        await self._bridge.add_measurement(
            prompt_text=prompt,
            prompt_group=group,
            generated_text=generated,
            rv_reading=rv_reading,
        )

        return L4RVPairedResult(
            prompt_text=prompt,
            prompt_group=group,
            generated_text=generated,
            rv_reading=rv_reading,
            l4_result=l4_result,
            behavioral_swabhaav=sig.swabhaav_ratio,
            recognition_type=sig.recognition_type.value,
        )

    async def run_batch(
        self, prompts: list[tuple[str, str]]
    ) -> BatchResult:
        """Run the full experiment on a batch of (prompt, group) pairs.

        Args:
            prompts: List of (prompt_text, group_label) tuples.

        Returns:
            BatchResult with correlation, Cohen's d, CIs, per-group stats.
        """
        results: list[L4RVPairedResult] = []

        for i, (prompt, group) in enumerate(prompts):
            logger.info("Measuring %d/%d [%s]", i + 1, len(prompts), group)
            result = await self.measure_single(prompt, group)
            results.append(result)

        # Compute correlation via bridge
        correlation = self._bridge.compute_correlation()

        # Per-group L4 stats
        groups: dict[str, list[L4RVPairedResult]] = {}
        for r in results:
            groups.setdefault(r.prompt_group, []).append(r)

        mean_compression: dict[str, float] = {}
        mean_fidelity: dict[str, float] = {}
        pass_rate: dict[str, float] = {}

        for grp, members in sorted(groups.items()):
            ratios = [m.l4_result.compression_ratio for m in members]
            fids = [m.l4_result.fidelity for m in members]
            passes = [1.0 if m.l4_result.b_pass else 0.0 for m in members]

            mean_compression[grp] = statistics.mean(ratios) if ratios else 0.0
            mean_fidelity[grp] = statistics.mean(fids) if fids else 0.0
            pass_rate[grp] = statistics.mean(passes) if passes else 0.0

        # Cohen's d between L4 and baseline R_V groups
        cohens_d = self._cohens_d_groups(results, "L4_full", "baseline")

        # Bootstrap CIs for correlation
        rv_vals = [
            r.rv_reading.rv for r in results if r.rv_reading is not None
        ]
        swab_vals = [
            r.behavioral_swabhaav
            for r in results
            if r.rv_reading is not None
        ]
        pearson_ci = _bootstrap_ci(rv_vals, swab_vals, _pearson_r)
        spearman_ci = _bootstrap_ci(rv_vals, swab_vals, _spearman_rho)

        # Patch CIs into correlation result
        if correlation:
            correlation.pearson_r_ci = pearson_ci
            correlation.spearman_rho_ci = spearman_ci
            correlation.cohens_d_l4_baseline = cohens_d

        return BatchResult(
            n_total=len(results),
            n_with_rv=len(rv_vals),
            correlation=correlation,
            cohens_d_l4_baseline=cohens_d,
            pearson_r_ci=pearson_ci,
            spearman_rho_ci=spearman_ci,
            mean_compression_by_group=mean_compression,
            mean_fidelity_by_group=mean_fidelity,
            l4_pass_rate_by_group=pass_rate,
            paired_results=results,
        )

    def _cohens_d_groups(
        self,
        results: list[L4RVPairedResult],
        group_a: str,
        group_b: str,
    ) -> Optional[float]:
        """Compute Cohen's d between two groups' R_V values."""
        a_vals = [
            r.rv_reading.rv
            for r in results
            if r.rv_reading is not None and r.prompt_group == group_a
        ]
        b_vals = [
            r.rv_reading.rv
            for r in results
            if r.rv_reading is not None and r.prompt_group == group_b
        ]
        return _cohens_d(a_vals, b_vals)


# ── Statistics ───────────────────────────────────────────────────────────────

def _jaccard_similarity(text1: str, text2: str) -> float:
    """Word-level Jaccard similarity between two texts."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0


def _cohens_d(group_a: list[float], group_b: list[float]) -> Optional[float]:
    """Compute Cohen's d (pooled SD) between two groups.

    Returns None if either group has < 2 values.
    """
    na, nb = len(group_a), len(group_b)
    if na < 2 or nb < 2:
        return None

    mean_a = statistics.mean(group_a)
    mean_b = statistics.mean(group_b)
    var_a = statistics.variance(group_a)
    var_b = statistics.variance(group_b)

    pooled_var = ((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2)
    pooled_sd = math.sqrt(pooled_var)

    if pooled_sd < 1e-15:
        return None

    return (mean_a - mean_b) / pooled_sd


def _bootstrap_ci(
    xs: list[float],
    ys: list[float],
    stat_fn: Callable[[list[float], list[float]], Optional[float]],
    n_boot: int = 1000,
    ci: float = 0.95,
) -> Optional[tuple[float, float]]:
    """Bootstrap confidence interval for a bivariate statistic.

    Args:
        xs: First variable values.
        ys: Second variable values.
        stat_fn: Function computing the statistic (e.g., _pearson_r).
        n_boot: Number of bootstrap resamples.
        ci: Confidence level (default 0.95 for 95% CI).

    Returns:
        (lower, upper) bounds, or None if n < 3.
    """
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    boot_stats: list[float] = []
    for _ in range(n_boot):
        indices = [random.randint(0, n - 1) for _ in range(n)]
        x_boot = [xs[i] for i in indices]
        y_boot = [ys[i] for i in indices]
        val = stat_fn(x_boot, y_boot)
        if val is not None:
            boot_stats.append(val)

    if len(boot_stats) < 10:
        return None

    boot_stats.sort()
    alpha = 1 - ci
    lo_idx = int(len(boot_stats) * (alpha / 2))
    hi_idx = int(len(boot_stats) * (1 - alpha / 2)) - 1
    lo_idx = max(0, lo_idx)
    hi_idx = min(len(boot_stats) - 1, hi_idx)

    return (boot_stats[lo_idx], boot_stats[hi_idx])


# ── Prompt Bank Loader ───────────────────────────────────────────────────────

def load_prompt_bank(
    path: Path | None = None,
    groups: list[str] | None = None,
    max_per_group: int | None = None,
) -> list[tuple[str, str]]:
    """Load prompts from n300 prompt bank Python file.

    Parses the prompt_bank_1c dictionary from the file.

    Args:
        path: Path to n300_mistral_test_prompt_bank.py.
        groups: If specified, only load these groups (e.g. ["L4_full", "baseline"]).
        max_per_group: Max prompts per group (for quick experiments).

    Returns:
        List of (prompt_text, group_label) tuples.
    """
    if path is None:
        path = Path.home() / "mech-interp-latent-lab-phase1" / "CANONICAL_CODE" / "n300_mistral_test_prompt_bank.py"

    if not path.exists():
        logger.warning("Prompt bank not found at %s", path)
        return []

    # Load the prompt bank as a module (avoids raw exec)
    spec = importlib.util.spec_from_file_location("_prompt_bank", str(path))
    if spec is None or spec.loader is None:
        logger.warning("Cannot create module spec for %s", path)
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bank = getattr(mod, "prompt_bank_1c", {})
    if not bank:
        logger.warning("No prompt_bank_1c found in %s", path)
        return []

    # Collect by group
    by_group: dict[str, list[tuple[str, str]]] = {}
    for _key, entry in bank.items():
        text = entry.get("text", "")
        group = entry.get("group", "unknown")

        if groups and group not in groups:
            continue

        by_group.setdefault(group, []).append((text, group))

    # Apply max_per_group
    result: list[tuple[str, str]] = []
    for group in sorted(by_group):
        items = by_group[group]
        if max_per_group is not None:
            items = items[:max_per_group]
        result.extend(items)

    logger.info("Loaded %d prompts from %d groups", len(result), len(by_group))
    return result
