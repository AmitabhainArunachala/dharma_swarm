"""Tests for dharma_swarm.pramana -- PramanaValidator."""

import json

import pytest

from dharma_swarm.pramana import (
    CompositeValidation,
    PramanaResult,
    PramanaValidator,
    WEIGHTS,
)


# ---------------------------------------------------------------------------
# Pratyaksha -- Direct perception
# ---------------------------------------------------------------------------


def test_pratyaksha_match(tmp_path):
    """Value matches data within tolerance -> pass."""
    data_file = tmp_path / "result.json"
    data_file.write_text(json.dumps({"results": {"hedges_g": -1.47}}))

    v = PramanaValidator()
    r = v.validate_pratyaksha(
        "Hedges' g = -1.47",
        expected_value=-1.47,
        data_path=data_file,
        key_path="results.hedges_g",
    )

    assert r.passed is True
    assert r.confidence == 1.0
    assert r.mode == "pratyaksha"


def test_pratyaksha_mismatch(tmp_path):
    """Value differs significantly -> fail."""
    data_file = tmp_path / "result.json"
    data_file.write_text(json.dumps({"value": 0.5}))

    v = PramanaValidator()
    r = v.validate_pratyaksha(
        "value = 1.0",
        expected_value=1.0,
        data_path=data_file,
        key_path="value",
    )

    assert r.passed is False
    assert r.confidence == 0.0


def test_pratyaksha_missing_file(tmp_path):
    """Missing data file -> fail."""
    v = PramanaValidator()
    r = v.validate_pratyaksha(
        "some claim",
        expected_value=1.0,
        data_path=tmp_path / "nonexistent.json",
        key_path="x",
    )

    assert r.passed is False
    assert "missing" in r.evidence.lower() or "No data" in r.evidence


# ---------------------------------------------------------------------------
# Anumana -- Inference
# ---------------------------------------------------------------------------


def test_anumana_consistent():
    """Effect size within CI, valid p -> pass."""
    v = PramanaValidator()
    r = v.validate_anumana(
        "d = -1.47",
        effect_size=-1.47,
        ci_lower=-1.82,
        ci_upper=-1.17,
        p_value=0.001,
        n=100,
    )

    assert r.passed is True
    assert "All inference checks passed" in r.evidence


def test_anumana_ci_violation():
    """Effect size outside CI -> fail."""
    v = PramanaValidator()
    r = v.validate_anumana(
        "d = 2.0 but CI is [0.5, 1.5]",
        effect_size=2.0,
        ci_lower=0.5,
        ci_upper=1.5,
        p_value=0.01,
        n=50,
    )

    assert r.passed is False
    assert "outside CI" in r.evidence


def test_anumana_ci_crosses_zero():
    """CI crosses zero with p < 0.05 -> fail."""
    v = PramanaValidator()
    r = v.validate_anumana(
        "inconsistent CI and p",
        effect_size=0.5,
        ci_lower=-0.3,
        ci_upper=1.2,
        p_value=0.01,
        n=50,
    )

    assert r.passed is False
    assert "crosses zero" in r.evidence


def test_anumana_small_sample():
    """Small n with large effect -> flagged."""
    v = PramanaValidator()
    r = v.validate_anumana(
        "large effect, tiny n",
        effect_size=1.5,
        ci_lower=0.5,
        ci_upper=2.5,
        p_value=0.04,
        n=10,
    )

    assert r.passed is False
    assert "Small sample" in r.evidence


# ---------------------------------------------------------------------------
# Agama -- Authority / citation
# ---------------------------------------------------------------------------


def test_agama_found(tmp_path):
    """Citation found in bib -> pass."""
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{vaswani2017attention,\n  title={Attention Is All You Need},\n}")

    v = PramanaValidator()
    r = v.validate_agama(
        "Transformer architecture",
        citation_key="vaswani2017attention",
        bib_path=bib,
    )

    assert r.passed is True
    assert r.confidence == 0.9


def test_agama_missing(tmp_path):
    """Citation not found -> fail."""
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{smith2020,\n  title={Unrelated},\n}")

    v = PramanaValidator()
    r = v.validate_agama(
        "citing nonexistent paper",
        citation_key="ghost2099hallucinated",
        bib_path=bib,
    )

    assert r.passed is False
    assert "NOT found" in r.evidence


# ---------------------------------------------------------------------------
# Upamana -- Analogy / cross-comparison
# ---------------------------------------------------------------------------


def test_upamana_consistent():
    """Same direction effects -> pass."""
    v = PramanaValidator()
    r = v.validate_upamana(
        "contraction consistent across models",
        results=[
            {"effect_size": -1.47},
            {"effect_size": -1.20},
            {"effect_size": -0.95},
        ],
    )

    assert r.passed is True
    assert r.confidence == 0.8


def test_upamana_inconsistent():
    """Opposite direction effects -> fail."""
    v = PramanaValidator()
    r = v.validate_upamana(
        "mixed direction",
        results=[
            {"effect_size": -1.47},
            {"effect_size": 0.85},
        ],
    )

    assert r.passed is False
    assert r.confidence == 0.3


# ---------------------------------------------------------------------------
# Arthapatti -- Postulation (BLOCKING)
# ---------------------------------------------------------------------------


def test_arthapatti_all_met():
    """All conditions met -> pass."""
    v = PramanaValidator()
    r = v.validate_arthapatti(
        "R_V contraction requires GQA",
        necessary_conditions=[
            ("model_has_gqa", True),
            ("layer_count_sufficient", True),
            ("self_ref_prompts_present", True),
        ],
    )

    assert r.passed is True
    assert r.confidence == 1.0
    assert "All" in r.evidence


def test_arthapatti_failure_blocks():
    """Failed condition -> fail with evidence."""
    v = PramanaValidator()
    r = v.validate_arthapatti(
        "causal validation",
        necessary_conditions=[
            ("ablation_run", True),
            ("control_run", False),
            ("sufficient_n", True),
        ],
    )

    assert r.passed is False
    assert r.confidence == 0.0
    assert "control_run" in r.evidence


# ---------------------------------------------------------------------------
# Composite validation
# ---------------------------------------------------------------------------


def test_composite_arthapatti_blocks():
    """Arthapatti FAIL -> composite FAIL regardless of other modes."""
    v = PramanaValidator()

    pratyaksha = PramanaResult(mode="pratyaksha", passed=True, confidence=1.0)
    anumana = PramanaResult(mode="anumana", passed=True, confidence=1.0)
    arthapatti = PramanaResult(mode="arthapatti", passed=False, confidence=0.0,
                               evidence="missing control")

    comp = v.validate_composite(
        "blocked by arthapatti",
        results=[pratyaksha, anumana, arthapatti],
    )

    assert comp.overall_passed is False
    assert comp.overall_score == 0.0
    assert len(comp.blocking_failures) == 1
    assert "missing control" in comp.blocking_failures[0]


def test_composite_weighted():
    """Composite score uses correct weights when all pass."""
    v = PramanaValidator()

    results = [
        PramanaResult(mode="pratyaksha", passed=True, confidence=1.0),
        PramanaResult(mode="anumana", passed=True, confidence=0.8),
        PramanaResult(mode="agama", passed=True, confidence=0.9),
        PramanaResult(mode="upamana", passed=True, confidence=0.7),
        PramanaResult(mode="arthapatti", passed=True, confidence=1.0),
    ]

    comp = v.validate_composite("full validation", results=results)

    assert comp.overall_passed is True
    assert len(comp.blocking_failures) == 0

    # Manually compute expected weighted score
    expected = (
        WEIGHTS["pratyaksha"] * 1.0
        + WEIGHTS["anumana"] * 0.8
        + WEIGHTS["agama"] * 0.9
        + WEIGHTS["upamana"] * 0.7
        + WEIGHTS["arthapatti"] * 1.0
    ) / sum(WEIGHTS.values())

    assert comp.overall_score == pytest.approx(expected, abs=1e-3)
