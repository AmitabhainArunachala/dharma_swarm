"""Tests for Ginko Report Generator."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_report_gen import (
    DailyReport,
    format_report_markdown,
    format_report_html,
    format_report_substack,
    format_report_email_subject,
    save_report,
    load_report,
    list_reports,
    REPORTS_DIR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report() -> DailyReport:
    """Create a fully populated test report."""
    return DailyReport(
        date="2026-03-17",
        regime="bull",
        regime_confidence=0.68,
        macro_summary="Fed Funds: 5.25% | VIX: 16.5 | Yield Spread: 0.30%",
        risk_level="moderate",
        signals=[
            {
                "symbol": "SPY",
                "direction": "buy",
                "strength": "moderate",
                "confidence": 0.65,
                "reason": "bull regime, uptrend",
            },
            {
                "symbol": "AAPL",
                "direction": "hold",
                "strength": "weak",
                "confidence": 0.35,
                "reason": "neutral RSI",
            },
        ],
        new_predictions=[],
        resolved_predictions=[],
        brier_scorecard={
            "total_predictions": 5,
            "resolved_predictions": 3,
            "overall_brier": 0.2333,
            "win_rate": 0.667,
            "edge_validated": False,
        },
        paper_portfolio_summary={
            "total_value": 100500,
            "total_pnl_pct": 0.5,
            "sharpe_ratio": 1.2,
            "open_positions": 2,
        },
        sec_highlights=[],
        generated_at="2026-03-17T00:00:00Z",
    )


def _make_minimal_report() -> DailyReport:
    """Create a report with minimal data -- no signals, no portfolio, no SEC."""
    return DailyReport(
        date="2026-03-17",
        regime="unknown",
        regime_confidence=0.0,
        macro_summary="No data available.",
        risk_level="unknown",
        signals=[],
        brier_scorecard={},
        generated_at="2026-03-17T00:00:00Z",
    )


@pytest.fixture(autouse=True)
def _clean_reports():
    """Remove any leftover report files before each test."""
    for f in REPORTS_DIR.glob("report_*"):
        f.unlink(missing_ok=True)
    yield
    for f in REPORTS_DIR.glob("report_*"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DailyReport construction
# ---------------------------------------------------------------------------


class TestDailyReportCreation:
    """Test DailyReport dataclass construction."""

    def test_daily_report_creation(self):
        """Construct DailyReport with all fields and verify values."""
        r = _make_report()
        assert r.date == "2026-03-17"
        assert r.regime == "bull"
        assert r.regime_confidence == 0.68
        assert r.risk_level == "moderate"
        assert len(r.signals) == 2
        assert r.signals[0]["symbol"] == "SPY"
        assert r.brier_scorecard["total_predictions"] == 5
        assert r.paper_portfolio_summary is not None
        assert r.paper_portfolio_summary["total_value"] == 100500
        assert r.generated_at == "2026-03-17T00:00:00Z"

    def test_daily_report_defaults(self):
        """Verify DailyReport default values for optional fields."""
        r = DailyReport(
            date="2026-01-01",
            regime="bear",
            regime_confidence=0.5,
            macro_summary="test",
            risk_level="high",
        )
        assert r.signals == []
        assert r.new_predictions == []
        assert r.resolved_predictions == []
        assert r.brier_scorecard == {}
        assert r.paper_portfolio_summary is None
        assert r.sec_highlights == []
        assert r.generated_at == ""


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


class TestMarkdownFormat:
    """Test format_report_markdown output."""

    def test_format_markdown_has_all_sections(self):
        """Verify header, signals table, brier scorecard, and SATYA are present."""
        r = _make_report()
        md = format_report_markdown(r)
        assert "# Dharmic Quant" in md
        assert "## Macro Summary" in md
        assert "## Signals" in md
        assert "| Symbol |" in md
        assert "SPY" in md
        assert "## Prediction Scorecard" in md
        assert "Brier score" in md
        assert "SATYA Disclosure" in md
        assert "## Methodology" in md

    def test_format_markdown_empty_signals(self):
        """Works correctly with no signals -- shows 'No signals' message."""
        r = _make_minimal_report()
        md = format_report_markdown(r)
        assert "No signals generated" in md
        assert "| Symbol |" not in md


# ---------------------------------------------------------------------------
# HTML formatting
# ---------------------------------------------------------------------------


class TestHtmlFormat:
    """Test format_report_html output."""

    def test_format_html_has_style(self):
        """Verify CSS classes and style tag are present."""
        r = _make_report()
        html = format_report_html(r)
        assert "<style>" in html
        assert "badge-bull" in html
        assert "risk-moderate" in html
        assert "dir-buy" in html

    def test_format_html_has_all_sections(self):
        """Verify all major sections appear in HTML output."""
        r = _make_report()
        html = format_report_html(r)
        assert "<!DOCTYPE html>" in html
        assert "<h1>" in html
        assert "Macro Summary" in html
        assert "<table>" in html
        assert "SPY" in html
        assert "Prediction Scorecard" in html
        assert "SATYA Disclosure" in html
        assert "Risk Assessment" in html
        assert "</html>" in html


# ---------------------------------------------------------------------------
# Substack formatting
# ---------------------------------------------------------------------------


class TestSubstackFormat:
    """Test format_report_substack output."""

    def test_format_substack_hook(self):
        """Verify the opening hook with strongest signal is present."""
        r = _make_report()
        sub = format_report_substack(r)
        # SPY has confidence 0.65, AAPL 0.35 -- SPY should be the hook
        assert "Today's strongest signal: SPY" in sub
        assert "BUY" in sub
        assert "65%" in sub

    def test_format_substack_regime_box(self):
        """Verify regime box with regime and risk level."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "MARKET REGIME: BULL" in sub
        assert "confidence: 68%" in sub
        assert "Risk Level: MODERATE" in sub

    def test_format_substack_signal_table(self):
        """Verify markdown table format with all signals."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "## Today's Signals" in sub
        assert "| Symbol | Direction | Strength | Confidence | Reason |" in sub
        assert "| **SPY** |" in sub
        assert "| **AAPL** |" in sub

    def test_format_substack_satya(self):
        """Verify SATYA disclosure block is present."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "SATYA Disclosure" in sub
        assert "radical transparency" in sub

    def test_format_substack_disclaimer(self):
        """Verify disclaimer footer is present."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "not financial advice" in sub
        assert "Paper trading only" in sub
        assert "dharma_swarm" in sub

    def test_format_substack_no_signals(self):
        """Substack format handles empty signals gracefully."""
        r = _make_minimal_report()
        sub = format_report_substack(r)
        # No hook line when no signals
        assert "Today's strongest signal" not in sub
        # Table headers still present
        assert "## Today's Signals" in sub

    def test_format_substack_prediction_scorecard(self):
        """Verify prediction scorecard values in Substack output."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "## Prediction Scorecard" in sub
        assert "Total predictions**: 5" in sub
        assert "Resolved**: 3" in sub
        assert "Brier score**: 0.2333" in sub
        assert "Win rate**: 66.7%" in sub
        assert "Edge validated**: NO" in sub

    def test_format_substack_paper_portfolio(self):
        """Verify paper portfolio section in Substack output."""
        r = _make_report()
        sub = format_report_substack(r)
        assert "## Paper Portfolio" in sub
        assert "$100,500" in sub
        assert "+0.50%" in sub
        assert "Sharpe**: 1.20" in sub
        assert "Open positions**: 2" in sub

    def test_format_substack_no_portfolio(self):
        """Substack format omits portfolio section when not present."""
        r = _make_report()
        r.paper_portfolio_summary = None
        sub = format_report_substack(r)
        assert "## Paper Portfolio" not in sub


# ---------------------------------------------------------------------------
# Email subject
# ---------------------------------------------------------------------------


class TestEmailSubject:
    """Test format_report_email_subject output."""

    def test_email_subject(self):
        """Verify email subject format and content."""
        r = _make_report()
        subj = format_report_email_subject(r)
        assert subj.startswith("[BULL]")
        assert "2 signals" in subj
        assert "Brier: 0.233" in subj
        assert "Dharmic Quant" in subj
        assert "2026-03-17" in subj

    def test_email_subject_no_brier(self):
        """Email subject omits Brier when not available."""
        r = _make_minimal_report()
        subj = format_report_email_subject(r)
        assert "[UNKNOWN]" in subj
        assert "0 signals" in subj
        assert "Brier" not in subj
        assert "Dharmic Quant" in subj


# ---------------------------------------------------------------------------
# Persistence: save / load / list
# ---------------------------------------------------------------------------


class TestPersistence:
    """Test report save, load, and list operations."""

    def test_save_report_creates_files(self):
        """Verify .md, .html, and .json files are created on save."""
        r = _make_report()
        md_path = save_report(r)
        assert md_path.exists()
        assert md_path.suffix == ".md"
        # Check sibling files
        html_path = md_path.with_suffix(".html")
        json_path = md_path.with_suffix(".json")
        assert html_path.exists()
        assert json_path.exists()
        # Verify JSON is valid
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["date"] == "2026-03-17"
        assert data["regime"] == "bull"

    def test_load_report_round_trip(self):
        """Save then load a report and verify all fields match."""
        original = _make_report()
        save_report(original)
        loaded = load_report("2026-03-17")
        assert loaded is not None
        assert loaded.date == original.date
        assert loaded.regime == original.regime
        assert loaded.regime_confidence == original.regime_confidence
        assert loaded.macro_summary == original.macro_summary
        assert loaded.risk_level == original.risk_level
        assert len(loaded.signals) == len(original.signals)
        assert loaded.signals[0]["symbol"] == "SPY"
        assert loaded.brier_scorecard["total_predictions"] == 5
        assert loaded.paper_portfolio_summary["total_value"] == 100500
        assert loaded.generated_at == original.generated_at

    def test_load_report_not_found(self):
        """Loading a nonexistent report returns None."""
        result = load_report("1999-01-01")
        assert result is None

    def test_list_reports(self):
        """Create multiple reports and list them."""
        r1 = _make_report()
        r1.date = "2026-03-15"
        save_report(r1)

        r2 = _make_report()
        r2.date = "2026-03-16"
        save_report(r2)

        r3 = _make_report()
        r3.date = "2026-03-17"
        save_report(r3)

        reports = list_reports(limit=10)
        assert len(reports) >= 3
        dates = [r["date"] for r in reports]
        assert "2026-03-17" in dates
        assert "2026-03-16" in dates
        assert "2026-03-15" in dates
        # Each entry has all path keys
        for entry in reports:
            assert "date" in entry
            assert "json_path" in entry
            assert "md_path" in entry
            assert "html_path" in entry


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test report generation with missing or unusual data."""

    def test_report_with_missing_data(self):
        """No SEC highlights, no portfolio -- all formats still generate."""
        r = _make_minimal_report()
        md = format_report_markdown(r)
        assert isinstance(md, str)
        assert len(md) > 100

        html = format_report_html(r)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

        sub = format_report_substack(r)
        assert isinstance(sub, str)
        assert "MARKET REGIME" in sub

        subj = format_report_email_subject(r)
        assert isinstance(subj, str)
        assert "Dharmic Quant" in subj

    def test_sell_signal_direction(self):
        """Verify sell signals render correctly in Substack format."""
        r = _make_report()
        r.signals = [
            {
                "symbol": "TSLA",
                "direction": "sell",
                "strength": "strong",
                "confidence": 0.82,
                "reason": "bearish divergence confirmed",
            },
        ]
        sub = format_report_substack(r)
        assert "TSLA" in sub
        assert "SELL" in sub
        assert "82%" in sub

    def test_extreme_risk_level(self):
        """Markdown renders extreme risk advisory text."""
        r = _make_report()
        r.risk_level = "extreme"
        md = format_report_markdown(r)
        assert "extreme risk conditions" in md

    def test_brier_none_in_scorecard(self):
        """Substack handles missing brier score gracefully."""
        r = _make_report()
        r.brier_scorecard = {
            "total_predictions": 2,
            "resolved_predictions": 0,
            "overall_brier": None,
            "win_rate": None,
            "edge_validated": False,
        }
        sub = format_report_substack(r)
        assert "Brier score" not in sub
        assert "Win rate" not in sub
        assert "Edge validated**: NO" in sub
