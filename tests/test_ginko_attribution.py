"""Tests for ginko_attribution.py — P&L decomposition by agent, signal, regime, symbol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.ginko_attribution import (
    AttributionReport,
    _KNOWN_AGENTS,
    _SIGNAL_TYPE_PATTERNS,
    _classify_signal_type,
    _extract_agent,
    _extract_regime,
    _format_pnl,
    _pnl_bar,
    compute_attribution,
    format_attribution_report,
    get_attribution_api_data,
    load_trades,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_known_agents(self):
        assert "kimi" in _KNOWN_AGENTS
        assert "sentinel" in _KNOWN_AGENTS
        assert len(_KNOWN_AGENTS) >= 6

    def test_signal_patterns(self):
        assert len(_SIGNAL_TYPE_PATTERNS) >= 4
        types = [t for t, _ in _SIGNAL_TYPE_PATTERNS]
        assert "technical" in types
        assert "sec" in types
        assert "sentiment" in types


# ---------------------------------------------------------------------------
# AttributionReport
# ---------------------------------------------------------------------------


class TestAttributionReport:
    def test_defaults(self):
        r = AttributionReport()
        assert r.total_pnl == 0.0
        assert r.trade_count == 0
        assert r.pnl_by_agent == {}


# ---------------------------------------------------------------------------
# Trade loading
# ---------------------------------------------------------------------------


class TestLoadTrades:
    def test_loads_from_jsonl(self, tmp_path):
        p = tmp_path / "trades.jsonl"
        p.write_text(
            '{"symbol": "AAPL", "realized_pnl": 100}\n'
            '{"symbol": "MSFT", "realized_pnl": -50}\n',
            encoding="utf-8",
        )
        trades = load_trades(p)
        assert len(trades) == 2
        assert trades[0]["symbol"] == "AAPL"

    def test_skips_malformed(self, tmp_path):
        p = tmp_path / "trades.jsonl"
        p.write_text(
            '{"symbol": "AAPL"}\nnot json\n{"symbol": "MSFT"}\n',
            encoding="utf-8",
        )
        trades = load_trades(p)
        assert len(trades) == 2

    def test_missing_file(self, tmp_path):
        trades = load_trades(tmp_path / "nope.jsonl")
        assert trades == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "trades.jsonl"
        p.write_text("", encoding="utf-8")
        assert load_trades(p) == []


# ---------------------------------------------------------------------------
# Agent extraction
# ---------------------------------------------------------------------------


class TestExtractAgent:
    def test_direct_signal_source(self):
        assert _extract_agent({"signal_source": "kimi"}) == "kimi"

    def test_substring_match(self):
        assert _extract_agent({"signal_source": "kimi_technical_v2"}) == "kimi"

    def test_agent_field(self):
        assert _extract_agent({"agent": "scout"}) == "scout"

    def test_agent_name_field(self):
        assert _extract_agent({"agent_name": "sentinel"}) == "sentinel"

    def test_unknown(self):
        assert _extract_agent({"signal_source": "mystery"}) == "unknown"

    def test_empty(self):
        assert _extract_agent({}) == "unknown"


# ---------------------------------------------------------------------------
# Signal type classification
# ---------------------------------------------------------------------------


class TestClassifySignalType:
    def test_explicit_field(self):
        assert _classify_signal_type({"signal_type": "technical"}) == "technical"

    def test_from_source_rsi(self):
        assert _classify_signal_type({"signal_source": "rsi_crossover"}) == "technical"

    def test_from_source_sec(self):
        assert _classify_signal_type({"signal_source": "sec_filing_alert"}) == "sec"

    def test_from_source_sentiment(self):
        assert _classify_signal_type({"signal_source": "news_sentiment"}) == "sentiment"

    def test_from_source_multi(self):
        assert _classify_signal_type({"signal_source": "consensus_signal"}) == "multi"

    def test_infer_from_agent(self):
        # kimi is mapped to "technical"
        assert _classify_signal_type({"signal_source": "kimi"}) == "technical"

    def test_scout_sentiment(self):
        assert _classify_signal_type({"signal_source": "scout"}) == "sentiment"

    def test_unknown(self):
        assert _classify_signal_type({}) == "unknown"


# ---------------------------------------------------------------------------
# Regime extraction
# ---------------------------------------------------------------------------


class TestExtractRegime:
    def test_direct_field(self):
        assert _extract_regime({"regime": "bull"}) == "bull"

    def test_metadata(self):
        assert _extract_regime({"metadata": {"regime": "bear"}}) == "bear"

    def test_from_signal_source(self):
        assert _extract_regime({"signal_source": "bull_breakout"}) == "bull"

    def test_sideways(self):
        assert _extract_regime({"regime": "sideways"}) == "sideways"

    def test_unknown(self):
        assert _extract_regime({}) == "unknown"

    def test_invalid_regime(self):
        assert _extract_regime({"regime": "chaos"}) == "unknown"


# ---------------------------------------------------------------------------
# compute_attribution
# ---------------------------------------------------------------------------


class TestComputeAttribution:
    def _make_trades(self):
        return [
            {"symbol": "AAPL", "realized_pnl": 500, "signal_source": "kimi", "regime": "bull"},
            {"symbol": "AAPL", "realized_pnl": -200, "signal_source": "kimi", "regime": "bear"},
            {"symbol": "MSFT", "realized_pnl": 300, "signal_source": "scout", "regime": "bull"},
            {"symbol": "TSLA", "realized_pnl": -100, "signal_source": "sentinel", "regime": "sideways"},
        ]

    def test_basic(self):
        report = compute_attribution(self._make_trades())
        assert report.trade_count == 4
        assert report.total_pnl == 500.0
        assert report.win_count == 2
        assert report.loss_count == 2

    def test_pnl_by_agent(self):
        report = compute_attribution(self._make_trades())
        assert report.pnl_by_agent["kimi"] == 300.0
        assert report.pnl_by_agent["scout"] == 300.0
        assert report.pnl_by_agent["sentinel"] == -100.0

    def test_pnl_by_symbol(self):
        report = compute_attribution(self._make_trades())
        assert report.pnl_by_symbol["AAPL"] == 300.0
        assert report.pnl_by_symbol["TSLA"] == -100.0

    def test_pnl_by_regime(self):
        report = compute_attribution(self._make_trades())
        assert report.pnl_by_regime["bull"] == 800.0
        assert report.pnl_by_regime["bear"] == -200.0

    def test_best_worst_agent(self):
        report = compute_attribution(self._make_trades())
        assert report.best_agent in ("kimi", "scout")  # both have 300
        assert report.worst_agent == "sentinel"

    def test_win_rate(self):
        report = compute_attribution(self._make_trades())
        assert abs(report.win_rate - 0.5) < 0.01

    def test_empty_trades(self):
        report = compute_attribution([])
        assert report.trade_count == 0
        assert report.total_pnl == 0.0
        assert report.best_agent == ""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormatPnl:
    def test_positive(self):
        assert _format_pnl(1234.56) == "+$1,234.56"

    def test_negative(self):
        assert _format_pnl(-500.0) == "-$500.00"

    def test_zero(self):
        assert _format_pnl(0.0) == "$0.00"


class TestPnlBar:
    def test_positive(self):
        bar = _pnl_bar(100.0, 100.0, width=10)
        assert "+" in bar

    def test_negative(self):
        bar = _pnl_bar(-50.0, 100.0, width=10)
        assert "-" in bar

    def test_zero_max(self):
        assert _pnl_bar(50.0, 0.0) == ""

    def test_zero_value(self):
        assert _pnl_bar(0.0, 100.0) == ""


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestFormatAttributionReport:
    def test_contains_header(self):
        report = compute_attribution([])
        text = format_attribution_report(report)
        assert "PERFORMANCE ATTRIBUTION" in text

    def test_contains_sections(self):
        trades = [
            {"symbol": "AAPL", "realized_pnl": 100, "signal_source": "kimi", "regime": "bull"},
        ]
        report = compute_attribution(trades)
        text = format_attribution_report(report)
        assert "P&L BY AGENT" in text
        assert "P&L BY SIGNAL TYPE" in text
        assert "P&L BY REGIME" in text
        assert "P&L BY SYMBOL" in text

    def test_returns_string(self):
        assert isinstance(format_attribution_report(AttributionReport()), str)


# ---------------------------------------------------------------------------
# API data export
# ---------------------------------------------------------------------------


class TestGetAttributionApiData:
    def test_structure(self):
        trades = [
            {"symbol": "AAPL", "realized_pnl": 100, "signal_source": "kimi", "regime": "bull"},
        ]
        report = compute_attribution(trades)
        data = get_attribution_api_data(report)
        assert "summary" in data
        assert "pnl_by_agent" in data
        assert "pnl_by_signal_type" in data
        assert "pnl_by_regime" in data
        assert "pnl_by_symbol" in data

    def test_summary_fields(self):
        report = compute_attribution([
            {"symbol": "X", "realized_pnl": 50, "signal_source": "kimi"},
        ])
        data = get_attribution_api_data(report)
        s = data["summary"]
        assert s["total_pnl"] == 50.0
        assert s["trade_count"] == 1
        assert s["win_count"] == 1

    def test_json_serializable(self):
        report = compute_attribution([
            {"symbol": "AAPL", "realized_pnl": 100},
        ])
        data = get_attribution_api_data(report)
        # Should not raise
        json.dumps(data)

    def test_empty(self):
        data = get_attribution_api_data(AttributionReport())
        assert data["summary"]["trade_count"] == 0
        assert data["pnl_by_agent"] == []
