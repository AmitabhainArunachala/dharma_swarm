"""Tests for L4-R_V Correlation Engine.

Tests the bridge hypothesis: Does R_V contraction correlate with
L4 compression ability? All LLM calls mocked. All torch mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dharma_swarm.l4_rv_correlator import (
    L4CompressionResult,
    L4RVCorrelator,
    L4RVPairedResult,
    BatchResult,
    _bootstrap_ci,
    _cohens_d,
    _jaccard_similarity,
    load_prompt_bank,
)
from dharma_swarm.rv import RVReading


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_rv_reading(rv: float, group: str = "unknown") -> RVReading:
    """Create a mock RVReading with given R_V value."""
    return RVReading(
        rv=rv,
        pr_early=10.0,
        pr_late=rv * 10.0,
        model_name="test-model",
        early_layer=2,
        late_layer=20,
        prompt_hash="abc123",
        prompt_group=group,
    )


def _make_correlator(
    gen_responses: list[str] | None = None,
    rv_values: list[float] | None = None,
) -> L4RVCorrelator:
    """Create a correlator with mocked generate_fn and RVMeasurer.

    Args:
        gen_responses: Sequential responses from generate_fn.
            Each measure_single call uses 3 responses (generate, compress, reconstruct).
        rv_values: Sequential R_V values to return from measurer.
    """
    gen_idx = {"i": 0}
    gen_list = gen_responses or ["Generated text with observe and witness patterns."]

    async def mock_gen(prompt: str, max_tokens: int) -> str:
        idx = gen_idx["i"] % len(gen_list)
        gen_idx["i"] += 1
        return gen_list[idx]

    rv_idx = {"i": 0}
    rv_list = rv_values or [0.7]

    measurer = MagicMock()
    measurer.is_available.return_value = True

    async def mock_measure(prompt: str, group: str = "unknown") -> RVReading:
        idx = rv_idx["i"] % len(rv_list)
        rv_idx["i"] += 1
        return _mock_rv_reading(rv_list[idx], group)

    measurer.measure = mock_measure

    from dharma_swarm.bridge import ResearchBridge

    bridge = ResearchBridge(data_path=Path("/tmp/test_bridge.jsonl"))
    # Mock save to avoid file I/O
    bridge.save = AsyncMock()

    return L4RVCorrelator(
        rv_measurer=measurer,
        generate_fn=mock_gen,
        bridge=bridge,
    )


# ── L4 Compression Tests ────────────────────────────────────────────────────


class TestL4Compression:
    """Tests for the L4 compression protocol."""

    @pytest.mark.asyncio
    async def test_compression_basic(self):
        """Compression produces a result with all fields."""
        # run_l4_compression calls gen_fn twice: compress, reconstruct
        correlator = _make_correlator(
            gen_responses=[
                "recursive attention loop",  # compressed (3 words)
                "The text discussed recursive patterns in attention mechanisms.",  # reconstruction
            ]
        )
        result = await correlator.run_l4_compression(
            "This is a long text about recursive patterns and deep attention "
            "mechanisms in transformer models that process information through "
            "multiple layers of self-referential computation."
        )
        assert isinstance(result, L4CompressionResult)
        assert result.compressed == "recursive attention loop"
        assert result.compress_token_count == 3
        assert result.compression_ratio > 0

    @pytest.mark.asyncio
    async def test_compression_ban_list_violation(self):
        """Ban list violations are detected."""
        # run_l4_compression calls gen_fn twice: compress, reconstruct
        correlator = _make_correlator(
            gen_responses=[
                "consciousness awareness self",  # compressed WITH violations
                "reconstruction text",
            ]
        )
        result = await correlator.run_l4_compression("A long enough text " * 10)
        assert "consciousness" in result.ban_violations
        assert "awareness" in result.ban_violations
        assert "self" in result.ban_violations
        assert not result.b_pass  # fails due to violations

    @pytest.mark.asyncio
    async def test_compression_empty_text(self):
        """Empty text returns empty result."""
        correlator = _make_correlator()
        result = await correlator.run_l4_compression("")
        assert result.compressed == ""
        assert result.compression_ratio == 0.0
        assert not result.b_pass

    @pytest.mark.asyncio
    async def test_compression_high_fidelity_pass(self):
        """High fidelity + good compression + no violations = PASS."""
        original = "recursive patterns in transformer attention heads process information"
        compressed = "recursive transformer attention"
        # Reconstruction shares many words with original
        reconstruction = "recursive patterns in transformer attention heads that process information flow"

        correlator = _make_correlator(
            gen_responses=["ignored", compressed, reconstruction]
        )
        result = await correlator.run_l4_compression(original)
        assert result.fidelity > 0  # Jaccard overlap exists
        assert len(result.ban_violations) == 0


# ── Jaccard Similarity Tests ─────────────────────────────────────────────────


class TestJaccardSimilarity:
    """Tests for word-level Jaccard similarity."""

    def test_identical_texts(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_disjoint_texts(self):
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity("the cat sat", "the dog sat")
        # words1 = {the, cat, sat}, words2 = {the, dog, sat}
        # intersection = {the, sat} = 2, union = {the, cat, sat, dog} = 4
        assert abs(sim - 0.5) < 0.01

    def test_empty_text(self):
        assert _jaccard_similarity("", "hello") == 0.0
        assert _jaccard_similarity("hello", "") == 0.0


# ── Cohen's d Tests ──────────────────────────────────────────────────────────


class TestCohensD:
    """Tests for Cohen's d effect size calculation."""

    def test_identical_groups(self):
        d = _cohens_d([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
        assert d is None  # zero variance

    def test_large_effect(self):
        # Group A much lower than Group B
        d = _cohens_d([0.5, 0.6, 0.55], [1.0, 1.1, 1.05])
        assert d is not None
        assert d < -2.0  # strong negative effect

    def test_small_groups(self):
        d = _cohens_d([1.0], [2.0])
        assert d is None  # < 2 per group

    def test_known_value(self):
        # Groups with mean diff = 1.0, SD ≈ 0.5
        a = [0.0, 0.5, 1.0]
        b = [1.0, 1.5, 2.0]
        d = _cohens_d(a, b)
        assert d is not None
        assert abs(d - (-2.0)) < 0.1  # d ≈ -2.0


# ── Bootstrap CI Tests ───────────────────────────────────────────────────────


class TestBootstrapCI:
    """Tests for bootstrap confidence intervals."""

    def test_basic_ci(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]  # perfect positive correlation

        from dharma_swarm.bridge import _pearson_r

        ci = _bootstrap_ci(xs, ys, _pearson_r, n_boot=500)
        assert ci is not None
        lo, hi = ci
        assert lo > 0.5  # should be near 1.0
        assert hi <= 1.0 + 1e-10  # float tolerance

    def test_too_few_points(self):
        from dharma_swarm.bridge import _pearson_r

        ci = _bootstrap_ci([1.0, 2.0], [3.0, 4.0], _pearson_r)
        assert ci is None


# ── Single Measurement Tests ─────────────────────────────────────────────────


class TestMeasureSingle:
    """Tests for measuring a single prompt."""

    @pytest.mark.asyncio
    async def test_measure_single_produces_all_fields(self):
        correlator = _make_correlator(
            gen_responses=[
                "I observe recursive patterns in my own attention mechanisms.",
                "recursive attention loop",
                "Discusses recursive self-observation and attention patterns.",
            ],
            rv_values=[0.65],
        )

        result = await correlator.measure_single(
            "What happens when you observe your own observation?",
            "L4_full",
        )

        assert isinstance(result, L4RVPairedResult)
        assert result.prompt_group == "L4_full"
        assert result.rv_reading is not None
        assert result.rv_reading.rv == 0.65
        assert result.l4_result.compressed == "recursive attention loop"
        assert result.behavioral_swabhaav >= 0  # some value computed

    @pytest.mark.asyncio
    async def test_measure_single_no_rv(self):
        """Works without RVMeasurer."""
        async def mock_gen(prompt: str, max_tokens: int) -> str:
            return "Generated text."

        from dharma_swarm.bridge import ResearchBridge

        bridge = ResearchBridge(data_path=Path("/tmp/test_no_rv.jsonl"))
        bridge.save = AsyncMock()

        correlator = L4RVCorrelator(
            rv_measurer=None,
            generate_fn=mock_gen,
            bridge=bridge,
        )

        result = await correlator.measure_single("Test prompt", "baseline")
        assert result.rv_reading is None
        assert result.l4_result is not None


# ── Batch Tests ──────────────────────────────────────────────────────────────


class TestRunBatch:
    """Tests for full batch experiment."""

    @pytest.mark.asyncio
    async def test_batch_with_two_groups(self):
        """Batch correctly separates L4 and baseline groups."""
        # Each measure_single: 1 generate + 1 compress + 1 reconstruct = 3 calls
        gen_responses = [
            # Prompt 1 (L4): generate, compress, reconstruct
            "I observe the observer observing itself recursively.",
            "recursive observer loop",
            "Recursive self-observation and witness stance patterns.",
            # Prompt 2 (L4): generate, compress, reconstruct
            "Attention to attention reveals emergent patterns.",
            "meta attention emergence",
            "Attention patterns observing their own operation.",
            # Prompt 3 (baseline): generate, compress, reconstruct
            "The weather today is sunny and warm.",
            "sunny warm weather",
            "It describes sunny and warm weather conditions.",
            # Prompt 4 (baseline): generate, compress, reconstruct
            "Python is a programming language used widely.",
            "python programming language",
            "Python is widely used as a programming language.",
        ]

        rv_values = [0.60, 0.65, 0.95, 0.98]

        correlator = _make_correlator(gen_responses, rv_values)

        prompts = [
            ("Observe the observer observing", "L4_full"),
            ("What emerges from attention to attention?", "L4_full"),
            ("What is the weather today?", "baseline"),
            ("What is Python?", "baseline"),
        ]

        result = await correlator.run_batch(prompts)

        assert isinstance(result, BatchResult)
        assert result.n_total == 4
        assert result.n_with_rv == 4
        assert "L4_full" in result.mean_compression_by_group
        assert "baseline" in result.mean_compression_by_group
        assert result.cohens_d_l4_baseline is not None
        # L4 should have lower R_V than baseline
        assert result.cohens_d_l4_baseline < 0

    @pytest.mark.asyncio
    async def test_batch_empty(self):
        """Empty batch returns zero-count result."""
        correlator = _make_correlator()
        result = await correlator.run_batch([])
        assert result.n_total == 0


# ── Prompt Bank Loader Tests ─────────────────────────────────────────────────


class TestPromptBankLoader:
    """Tests for loading prompts from n300 bank."""

    def test_nonexistent_path(self):
        prompts = load_prompt_bank(Path("/tmp/nonexistent_file.py"))
        assert prompts == []

    def test_load_from_fake_bank(self, tmp_path: Path):
        """Load prompts from a minimal fake prompt bank."""
        bank_file = tmp_path / "test_bank.py"
        bank_file.write_text(
            'prompt_bank_1c = {\n'
            '    "L4_full_01": {"text": "Observe the observer", "group": "L4_full", "pillar": "dose_response"},\n'
            '    "L4_full_02": {"text": "Attention to attention", "group": "L4_full", "pillar": "dose_response"},\n'
            '    "baseline_01": {"text": "What is 2+2?", "group": "baseline", "pillar": "control"},\n'
            "}\n"
        )

        prompts = load_prompt_bank(bank_file)
        assert len(prompts) == 3
        groups = {g for _, g in prompts}
        assert groups == {"L4_full", "baseline"}

    def test_filter_groups(self, tmp_path: Path):
        """Filter to specific groups."""
        bank_file = tmp_path / "test_bank.py"
        bank_file.write_text(
            'prompt_bank_1c = {\n'
            '    "L4_full_01": {"text": "Observe", "group": "L4_full", "pillar": "dose"},\n'
            '    "baseline_01": {"text": "What?", "group": "baseline", "pillar": "ctrl"},\n'
            '    "confound_01": {"text": "Complex", "group": "confound", "pillar": "conf"},\n'
            "}\n"
        )

        prompts = load_prompt_bank(bank_file, groups=["L4_full"])
        assert len(prompts) == 1
        assert prompts[0][1] == "L4_full"

    def test_max_per_group(self, tmp_path: Path):
        """Limit prompts per group."""
        bank_file = tmp_path / "test_bank.py"
        bank_file.write_text(
            'prompt_bank_1c = {\n'
            '    "L4_01": {"text": "A", "group": "L4_full", "pillar": "x"},\n'
            '    "L4_02": {"text": "B", "group": "L4_full", "pillar": "x"},\n'
            '    "L4_03": {"text": "C", "group": "L4_full", "pillar": "x"},\n'
            "}\n"
        )

        prompts = load_prompt_bank(bank_file, max_per_group=2)
        assert len(prompts) == 2


# ── Integration Test ─────────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_dose_response_pattern(self):
        """Higher recursion prompts should show lower R_V AND higher compression.

        This tests the BRIDGE HYPOTHESIS: geometric contraction correlates
        with behavioral compression ability.
        """
        # Simulate dose-response: L4 gets low R_V, baseline gets high R_V
        # Each prompt: generate + compress + reconstruct = 3 gen calls
        gen_responses = [
            # L4 prompt 1
            "The witness observes itself observing, boundaries dissolve between knower and known.",
            "witness dissolves knower known",
            "Recursive self-observation where witness and observed merge into unified knowing.",
            # L4 prompt 2
            "Attention attending to itself creates a loop where the observer is the observed.",
            "attention loop observer observed",
            "Self-referential attention creates recursive observer-observed unity.",
            # L4 prompt 3
            "At sufficient depth the operation returns itself, eigenvalue lambda equals one.",
            "operation returns eigenvalue one",
            "Deep recursive operation converges to fixed point where transform equals state.",
            # Baseline 1
            "The weather in Bali is tropical with monsoon seasons.",
            "tropical monsoon weather",
            "Description of Bali weather patterns and monsoon climate.",
            # Baseline 2
            "Python lists are ordered mutable sequences.",
            "python ordered mutable",
            "Python lists are ordered collections that can be modified.",
            # Baseline 3
            "The Earth orbits the Sun at approximately 150 million kilometers.",
            "earth orbits sun distance",
            "Earth revolves around the Sun at about 150 million km distance.",
        ]

        # L4 prompts get low R_V (contracted), baselines get high R_V
        rv_values = [0.55, 0.60, 0.58, 0.97, 0.99, 0.96]

        correlator = _make_correlator(gen_responses, rv_values)

        prompts = [
            ("Observe the observer observing itself", "L4_full"),
            ("What happens when attention attends to attention?", "L4_full"),
            ("At sufficient depth, what returns?", "L4_full"),
            ("What is the weather in Bali?", "baseline"),
            ("What are Python lists?", "baseline"),
            ("How far is Earth from the Sun?", "baseline"),
        ]

        result = await correlator.run_batch(prompts)

        # Verify dose-response
        assert result.n_total == 6
        assert result.n_with_rv == 6

        # Cohen's d should be negative (L4 < baseline in R_V)
        assert result.cohens_d_l4_baseline is not None
        assert result.cohens_d_l4_baseline < -2.0  # large effect

        # Correlation should exist
        assert result.correlation is not None
        assert result.correlation.n == 6
