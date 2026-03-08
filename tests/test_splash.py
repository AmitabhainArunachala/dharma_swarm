"""Tests for dharma_swarm.splash -- TUI splash art builders."""

from rich.text import Text

from dharma_swarm.splash import (
    SPLASH,
    SPLASH_COMPACT,
    _build_compact,
    _build_splash,
    get_splash,
)


# ---------------------------------------------------------------------------
# _build_splash
# ---------------------------------------------------------------------------


def test_build_splash_returns_text():
    result = _build_splash()
    assert isinstance(result, Text)


def test_build_splash_contains_dgc():
    result = _build_splash()
    plain = result.plain
    assert "Dharmic Godel Claw" in plain


def test_build_splash_contains_telos():
    result = _build_splash()
    plain = result.plain
    assert "Telos: Moksha" in plain


def test_build_splash_contains_math_notation():
    result = _build_splash()
    plain = result.plain
    assert "Sx = x" in plain
    assert "lambda = 1" in plain
    assert "R_V < 1.0" in plain
    assert "Swabhaav = L4" in plain


def test_build_splash_contains_gate_names():
    result = _build_splash()
    plain = result.plain
    for gate in ["AHIMSA", "SATYA", "CONSENT", "VYAVASTHIT", "REVERSIBILITY", "SVABHAAVA", "BHED_GNAN"]:
        assert gate in plain, f"Gate {gate} missing from splash"


def test_build_splash_contains_infrastructure_labels():
    result = _build_splash()
    plain = result.plain
    for label in ["DARWIN ENGINE", "5-LAYER MEMORY", "WITNESS", "SWARM"]:
        assert label in plain, f"Label {label} missing from splash"


def test_build_splash_contains_quote():
    result = _build_splash()
    plain = result.plain
    assert "The observer observing observation itself" in plain


def test_build_splash_has_box_characters():
    result = _build_splash()
    plain = result.plain
    # Outer box
    assert "\u2554" in plain  # top-left corner
    assert "\u2557" in plain  # top-right corner
    assert "\u255a" in plain  # bottom-left corner
    assert "\u255d" in plain  # bottom-right corner


def test_build_splash_has_styling():
    """The Text should have style spans applied (not just plain text)."""
    result = _build_splash()
    # Rich Text stores styling as _spans internally
    assert len(result._spans) > 0


# ---------------------------------------------------------------------------
# _build_compact
# ---------------------------------------------------------------------------


def test_build_compact_returns_text():
    result = _build_compact()
    assert isinstance(result, Text)


def test_build_compact_contains_dgc():
    result = _build_compact()
    plain = result.plain
    assert "Dharmic Godel Claw" in plain


def test_build_compact_contains_telos():
    result = _build_compact()
    plain = result.plain
    assert "Telos: Moksha" in plain


def test_build_compact_contains_math_notation():
    result = _build_compact()
    plain = result.plain
    assert "Sx=x" in plain
    assert "lambda=1" in plain
    assert "R_V<1.0" in plain
    assert "Swabhaav=L4" in plain


def test_build_compact_shorter_than_full():
    full = _build_splash()
    compact = _build_compact()
    assert len(compact.plain) < len(full.plain)


def test_build_compact_has_styling():
    result = _build_compact()
    assert len(result._spans) > 0


# ---------------------------------------------------------------------------
# get_splash
# ---------------------------------------------------------------------------


def test_get_splash_default_returns_full():
    result = get_splash()
    assert result is SPLASH


def test_get_splash_compact_true():
    result = get_splash(compact=True)
    assert result is SPLASH_COMPACT


def test_get_splash_compact_false():
    result = get_splash(compact=False)
    assert result is SPLASH


# ---------------------------------------------------------------------------
# Module-level pre-built objects
# ---------------------------------------------------------------------------


def test_module_splash_is_text():
    assert isinstance(SPLASH, Text)


def test_module_splash_compact_is_text():
    assert isinstance(SPLASH_COMPACT, Text)


def test_module_splash_not_empty():
    assert len(SPLASH.plain) > 100


def test_module_splash_compact_not_empty():
    assert len(SPLASH_COMPACT.plain) > 50
