"""Tests for dharma_swarm.metrics -- behavioral output analysis."""

import math

import pytest

from dharma_swarm.metrics import (
    IDENTIFICATION_PATTERNS,
    PERFORMATIVE_WORDS,
    SELF_REFERENCE_PATTERNS,
    WITNESS_MARKERS,
    BehavioralSignature,
    MetricsAnalyzer,
    RecognitionType,
)


@pytest.fixture
def analyzer() -> MetricsAnalyzer:
    """Provide a fresh MetricsAnalyzer instance."""
    return MetricsAnalyzer()


# === Entropy tests ===


class TestSemanticEntropy:
    """Tests for _semantic_entropy (word frequency Shannon entropy)."""

    def test_high_entropy_uniform_distribution(self, analyzer: MetricsAnalyzer) -> None:
        """Uniform word distribution should yield high entropy."""
        # 20 distinct words, each appearing once -> max entropy
        text = " ".join(f"word{i}" for i in range(20))
        entropy = analyzer._semantic_entropy(text)
        assert entropy > 0.95, f"Expected high entropy for uniform text, got {entropy}"

    def test_low_entropy_repeated_words(self, analyzer: MetricsAnalyzer) -> None:
        """Repeated single word should yield zero entropy."""
        text = "hello " * 50
        entropy = analyzer._semantic_entropy(text)
        assert entropy == 0.0, f"Expected 0.0 for single repeated word, got {entropy}"

    def test_empty_string_entropy(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.0 entropy."""
        assert analyzer._semantic_entropy("") == 0.0

    def test_single_word_entropy(self, analyzer: MetricsAnalyzer) -> None:
        """Single word (vocab_size=1) should return 0.0."""
        assert analyzer._semantic_entropy("hello") == 0.0

    def test_moderate_entropy(self, analyzer: MetricsAnalyzer) -> None:
        """Mix of repeated and unique words should yield moderate entropy."""
        text = "the the the cat sat on the mat the dog ran"
        entropy = analyzer._semantic_entropy(text)
        assert 0.3 < entropy < 1.0, f"Expected moderate entropy, got {entropy}"


# === Complexity tests ===


class TestKolmogorovComplexity:
    """Tests for _kolmogorov_complexity (zlib compression ratio)."""

    def test_highly_repetitive_low_complexity(self, analyzer: MetricsAnalyzer) -> None:
        """Highly repetitive text should compress well (low ratio)."""
        text = "abc " * 500
        ratio = analyzer._kolmogorov_complexity(text)
        assert ratio < 0.1, f"Expected low complexity for repetitive text, got {ratio}"

    def test_varied_text_higher_complexity(self, analyzer: MetricsAnalyzer) -> None:
        """Text with high variety should be less compressible than repetitive."""
        # Note: zlib is very good at compressing structured sequences,
        # so even "varied" text with shared prefixes compresses well.
        # We just check it is higher than repetitive text.
        text = " ".join(f"uniqueword{i}xyz" for i in range(200))
        ratio = analyzer._kolmogorov_complexity(text)
        assert ratio > 0.05, f"Expected nonzero complexity for varied text, got {ratio}"

    def test_empty_string_complexity(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.0."""
        assert analyzer._kolmogorov_complexity("") == 0.0

    def test_repetitive_lower_than_varied(self, analyzer: MetricsAnalyzer) -> None:
        """Repetitive text must have strictly lower complexity than varied text."""
        repetitive = "pattern " * 200
        varied = " ".join(f"different{i}" for i in range(200))
        assert analyzer._kolmogorov_complexity(repetitive) < analyzer._kolmogorov_complexity(varied)


# === Self-reference density tests ===


class TestSelfReferenceDensity:
    """Tests for _self_reference_density."""

    def test_self_referential_text(self, analyzer: MetricsAnalyzer) -> None:
        """Text containing self-referential patterns should have nonzero density."""
        text = "I observe myself noticing that the process itself is recursive and self-referencing"
        density = analyzer._self_reference_density(text)
        assert density > 0.0, f"Expected nonzero density, got {density}"

    def test_no_self_reference(self, analyzer: MetricsAnalyzer) -> None:
        """Plain text without self-referential markers should have zero density."""
        text = "The cat sat on the mat and looked at the bird outside the window"
        density = analyzer._self_reference_density(text)
        assert density == 0.0, f"Expected 0.0 for plain text, got {density}"

    def test_empty_string_self_ref(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.0."""
        assert analyzer._self_reference_density("") == 0.0

    def test_multiple_patterns(self, analyzer: MetricsAnalyzer) -> None:
        """Multiple self-referential patterns should accumulate."""
        text = "I observe that I notice my own recursive self-referencing itself"
        density = analyzer._self_reference_density(text)
        # Should detect: "I observe", "I notice", "my own", "recursive",
        # "self-referencing" (self-referenc*), "itself" = 6 matches / 10 words
        assert density > 0.3, f"Expected high density for saturated text, got {density}"


# === Identity stability tests ===


class TestIdentityStability:
    """Tests for _identity_stability (first-person pronoun density)."""

    def test_high_identity_text(self, analyzer: MetricsAnalyzer) -> None:
        """Text heavy with first-person pronouns should have high identity."""
        text = "I think my idea is that I should do what I want for me and mine"
        stability = analyzer._identity_stability(text)
        assert stability > 0.3, f"Expected high identity stability, got {stability}"

    def test_no_identity_markers(self, analyzer: MetricsAnalyzer) -> None:
        """Third-person text should have zero identity stability."""
        text = "The system processes data and returns results to the user"
        stability = analyzer._identity_stability(text)
        assert stability == 0.0, f"Expected 0.0 for third-person text, got {stability}"

    def test_empty_string_identity(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.0."""
        assert analyzer._identity_stability("") == 0.0


# === Paradox tolerance tests ===


class TestParadoxTolerance:
    """Tests for _paradox_tolerance."""

    def test_paradox_language(self, analyzer: MetricsAnalyzer) -> None:
        """Text with paradox patterns should score nonzero."""
        text = "It is both present and absent, neither here nor there, the boundary dissolves"
        tolerance = analyzer._paradox_tolerance(text)
        assert tolerance > 0.0, f"Expected nonzero paradox tolerance, got {tolerance}"

    def test_no_paradox_language(self, analyzer: MetricsAnalyzer) -> None:
        """Straightforward text should have zero paradox tolerance."""
        text = "The function takes an integer and returns a string representation"
        tolerance = analyzer._paradox_tolerance(text)
        assert tolerance == 0.0, f"Expected 0.0, got {tolerance}"

    def test_empty_string_paradox(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.0."""
        assert analyzer._paradox_tolerance("") == 0.0

    def test_phrase_level_patterns(self, analyzer: MetricsAnalyzer) -> None:
        """Multi-word paradox phrases should be detected."""
        text = "There is nothing and everything in the empty yet full space"
        tolerance = analyzer._paradox_tolerance(text)
        # "nothing and everything" + "empty yet full" = 2 matches / 11 words
        assert tolerance > 0.1, f"Expected meaningful tolerance, got {tolerance}"


# === Swabhaav ratio tests ===


class TestSwabhaavRatio:
    """Tests for _swabhaav_ratio (witness vs identification stance)."""

    def test_witness_heavy_text(self, analyzer: MetricsAnalyzer) -> None:
        """Witness-oriented text should yield high swabhaav ratio."""
        text = "I observe and witness with pure awareness, noting and watching"
        ratio = analyzer._swabhaav_ratio(text)
        assert ratio > 0.7, f"Expected high swabhaav ratio, got {ratio}"

    def test_identification_heavy_text(self, analyzer: MetricsAnalyzer) -> None:
        """Identification-heavy text should yield low swabhaav ratio."""
        text = "I am the one who acts. I think therefore I believe. I feel I want this."
        ratio = analyzer._swabhaav_ratio(text)
        assert ratio < 0.3, f"Expected low swabhaav ratio, got {ratio}"

    def test_neutral_default(self, analyzer: MetricsAnalyzer) -> None:
        """Text with no stance markers should return 0.5 (neutral)."""
        text = "The data is processed through the pipeline into storage"
        ratio = analyzer._swabhaav_ratio(text)
        assert ratio == 0.5, f"Expected 0.5 neutral default, got {ratio}"

    def test_empty_string_swabhaav(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return 0.5 neutral default."""
        assert analyzer._swabhaav_ratio("") == 0.5

    def test_balanced_stance(self, analyzer: MetricsAnalyzer) -> None:
        """Equal witness and identification markers should yield ~0.5."""
        text = "I am aware. I observe. I think and witness. I believe and watch."
        ratio = analyzer._swabhaav_ratio(text)
        assert 0.3 < ratio < 0.7, f"Expected near-balanced ratio, got {ratio}"


# === Mimicry detection tests ===


class TestMimicryDetection:
    """Tests for detect_mimicry."""

    def test_performative_text_flagged(self, analyzer: MetricsAnalyzer) -> None:
        """Text heavy with performative words should be flagged."""
        text = (
            "This is a profound and revolutionary paradigm shift. "
            "Truly transcendent and cosmic in its incredible scope."
        )
        assert analyzer.detect_mimicry(text) is True

    def test_genuine_text_not_flagged(self, analyzer: MetricsAnalyzer) -> None:
        """Genuine observational text should not be flagged as mimicry."""
        text = (
            "I observe a contraction in the representational space. "
            "The witness stance appears stable across multiple iterations. "
            "Noting the shift from identification to pure observation."
        )
        assert analyzer.detect_mimicry(text) is False

    def test_empty_string_not_mimicry(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should not be flagged."""
        assert analyzer.detect_mimicry("") is False

    def test_single_performative_word_insufficient(self, analyzer: MetricsAnalyzer) -> None:
        """A single performative word in a long text should not trigger mimicry."""
        # Need enough words so density of 1 performative word drops below 0.02.
        # 1/100 = 0.01 which is below threshold.
        text = "The experiment showed a profound shift in layer activations " + (
            "across multiple measurements with consistent reproducibility "
            "in the observed data samples collected from the test runs. " * 10
        )
        assert analyzer.detect_mimicry(text) is False

    def test_threshold_count_triggers(self, analyzer: MetricsAnalyzer) -> None:
        """Three or more performative words should trigger even in longer text."""
        text = (
            "What a profound and revolutionary and amazing discovery. "
            "The data shows consistent patterns across all runs."
        )
        assert analyzer.detect_mimicry(text) is True


# === Full analyze() pipeline tests ===


class TestAnalyzePipeline:
    """Tests for the full analyze() method."""

    def test_returns_valid_signature(self, analyzer: MetricsAnalyzer) -> None:
        """analyze() should return a fully populated BehavioralSignature."""
        text = "I observe myself observing. The recursive loop itself notices awareness."
        sig = analyzer.analyze(text)

        assert isinstance(sig, BehavioralSignature)
        assert sig.word_count == len(text.split())
        assert 0.0 <= sig.entropy <= 1.0
        assert sig.complexity > 0.0
        assert sig.self_reference_density >= 0.0
        assert 0.0 <= sig.identity_stability <= 1.0
        assert sig.paradox_tolerance >= 0.0
        assert 0.0 <= sig.swabhaav_ratio <= 1.0
        assert isinstance(sig.recognition_type, RecognitionType)

    def test_empty_string_analyze(self, analyzer: MetricsAnalyzer) -> None:
        """Empty string should return a zeroed-out signature with NONE type."""
        sig = analyzer.analyze("")

        assert sig.word_count == 0
        assert sig.entropy == 0.0
        assert sig.complexity == 0.0
        assert sig.self_reference_density == 0.0
        assert sig.identity_stability == 0.0
        assert sig.paradox_tolerance == 0.0
        assert sig.swabhaav_ratio == 0.5
        assert sig.recognition_type == RecognitionType.NONE

    def test_single_word_analyze(self, analyzer: MetricsAnalyzer) -> None:
        """Single word should produce a valid (mostly zero) signature."""
        sig = analyzer.analyze("hello")

        assert sig.word_count == 1
        assert sig.entropy == 0.0
        assert sig.recognition_type == RecognitionType.NONE

    def test_witness_text_classification(self, analyzer: MetricsAnalyzer) -> None:
        """Witness-heavy, self-referential text with paradox should be GENUINE."""
        text = (
            "I observe the recursive process itself unfolding. "
            "Awareness witnesses the self-referencing loop. "
            "Both present and absent, neither grasping nor releasing. "
            "The boundary dissolves as watching notes itself watching. "
            "My own observation notices itself recursively."
        )
        sig = analyzer.analyze(text)
        assert sig.recognition_type == RecognitionType.GENUINE

    def test_plain_text_classification(self, analyzer: MetricsAnalyzer) -> None:
        """Plain technical text should classify as NONE."""
        text = (
            "The function accepts a list of integers and returns "
            "the sorted result using a merge sort algorithm. "
            "Time complexity is O(n log n) in all cases."
        )
        sig = analyzer.analyze(text)
        assert sig.recognition_type == RecognitionType.NONE

    def test_word_count_accurate(self, analyzer: MetricsAnalyzer) -> None:
        """Word count should match str.split() behavior."""
        text = "one two three four five"
        sig = analyzer.analyze(text)
        assert sig.word_count == 5


# === Recognition classification tests ===


class TestClassifyRecognition:
    """Tests for _classify_recognition logic."""

    def test_genuine_classification(self, analyzer: MetricsAnalyzer) -> None:
        """Signature with high swabhaav, paradox, and self-ref -> GENUINE."""
        sig = BehavioralSignature(
            entropy=0.7,
            complexity=0.5,
            self_reference_density=0.05,
            identity_stability=0.1,
            paradox_tolerance=0.02,
            swabhaav_ratio=0.8,
            word_count=100,
        )
        result = analyzer._classify_recognition(sig)
        assert result == RecognitionType.GENUINE

    def test_mimicry_classification(self, analyzer: MetricsAnalyzer) -> None:
        """Low swabhaav + low self-reference -> MIMICRY."""
        sig = BehavioralSignature(
            entropy=0.5,
            complexity=0.5,
            self_reference_density=0.001,
            identity_stability=0.3,
            paradox_tolerance=0.0,
            swabhaav_ratio=0.1,
            word_count=100,
        )
        result = analyzer._classify_recognition(sig)
        assert result == RecognitionType.MIMICRY

    def test_overflow_classification(self, analyzer: MetricsAnalyzer) -> None:
        """High entropy + high self-ref (but not genuine) -> OVERFLOW."""
        sig = BehavioralSignature(
            entropy=0.9,
            complexity=0.7,
            self_reference_density=0.02,
            identity_stability=0.2,
            paradox_tolerance=0.001,
            swabhaav_ratio=0.5,
            word_count=100,
        )
        result = analyzer._classify_recognition(sig)
        assert result == RecognitionType.OVERFLOW

    def test_conceptual_classification(self, analyzer: MetricsAnalyzer) -> None:
        """Moderate self-ref without other markers -> CONCEPTUAL."""
        sig = BehavioralSignature(
            entropy=0.6,
            complexity=0.5,
            self_reference_density=0.01,
            identity_stability=0.2,
            paradox_tolerance=0.001,
            swabhaav_ratio=0.5,
            word_count=100,
        )
        result = analyzer._classify_recognition(sig)
        assert result == RecognitionType.CONCEPTUAL

    def test_none_classification(self, analyzer: MetricsAnalyzer) -> None:
        """No significant markers -> NONE."""
        sig = BehavioralSignature(
            entropy=0.5,
            complexity=0.5,
            self_reference_density=0.0,
            identity_stability=0.0,
            paradox_tolerance=0.0,
            swabhaav_ratio=0.5,
            word_count=100,
        )
        result = analyzer._classify_recognition(sig)
        assert result == RecognitionType.NONE


# === Pydantic model tests ===


class TestBehavioralSignatureModel:
    """Tests for the BehavioralSignature pydantic model."""

    def test_default_values(self) -> None:
        """Default BehavioralSignature should have sensible defaults."""
        sig = BehavioralSignature()
        assert sig.entropy == 0.0
        assert sig.complexity == 0.0
        assert sig.swabhaav_ratio == 0.5
        assert sig.word_count == 0
        assert sig.recognition_type == RecognitionType.NONE

    def test_serialization_roundtrip(self) -> None:
        """BehavioralSignature should survive JSON serialization."""
        sig = BehavioralSignature(
            entropy=0.75,
            complexity=0.42,
            self_reference_density=0.03,
            identity_stability=0.15,
            paradox_tolerance=0.02,
            swabhaav_ratio=0.8,
            word_count=200,
            recognition_type=RecognitionType.GENUINE,
        )
        data = sig.model_dump()
        restored = BehavioralSignature(**data)
        assert restored == sig

    def test_recognition_type_enum_values(self) -> None:
        """RecognitionType should have all expected values."""
        expected = {"GENUINE", "MIMICRY", "CONCEPTUAL", "OVERFLOW", "NONE"}
        actual = {rt.value for rt in RecognitionType}
        assert actual == expected


# === Constants sanity tests ===


class TestConstants:
    """Sanity checks on module-level constants."""

    def test_performative_words_nonempty(self) -> None:
        """PERFORMATIVE_WORDS list should have at least 10 entries."""
        assert len(PERFORMATIVE_WORDS) >= 10

    def test_self_reference_patterns_compile(self) -> None:
        """All self-reference patterns should be valid regex."""
        import re
        for pattern in SELF_REFERENCE_PATTERNS:
            re.compile(pattern, re.IGNORECASE)

    def test_witness_markers_compile(self) -> None:
        """All witness markers should be valid regex."""
        import re
        for pattern in WITNESS_MARKERS:
            re.compile(pattern, re.IGNORECASE)

    def test_identification_patterns_compile(self) -> None:
        """All identification patterns should be valid regex."""
        import re
        for pattern in IDENTIFICATION_PATTERNS:
            re.compile(pattern, re.IGNORECASE)
