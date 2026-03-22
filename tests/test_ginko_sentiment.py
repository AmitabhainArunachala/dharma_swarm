"""Tests for ginko_sentiment.py — X/Twitter sentiment signal pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pytest

from dharma_swarm.ginko_sentiment import (
    BEARISH_KEYWORDS,
    BULLISH_KEYWORDS,
    SentimentSignal,
    _persist_sentiment,
    compute_keyword_sentiment,
    format_sentiment_report,
    generate_synthetic_sentiment,
    incorporate_sentiment_signals,
    load_latest_sentiment,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_bullish_keywords(self):
        assert len(BULLISH_KEYWORDS) >= 8
        assert "bullish" in BULLISH_KEYWORDS
        assert "moon" in BULLISH_KEYWORDS

    def test_bearish_keywords(self):
        assert len(BEARISH_KEYWORDS) >= 8
        assert "bearish" in BEARISH_KEYWORDS
        assert "crash" in BEARISH_KEYWORDS


# ---------------------------------------------------------------------------
# SentimentSignal
# ---------------------------------------------------------------------------


class TestSentimentSignal:
    def test_construction(self):
        s = SentimentSignal(ticker="AAPL", score=0.5, tweet_count=10)
        assert s.ticker == "AAPL"
        assert s.source == "x_api"
        assert s.timestamp != ""

    def test_asdict(self):
        s = SentimentSignal(ticker="NVDA", score=-0.3, tweet_count=5)
        d = asdict(s)
        assert d["ticker"] == "NVDA"
        assert d["score"] == -0.3


# ---------------------------------------------------------------------------
# Keyword sentiment
# ---------------------------------------------------------------------------


class TestComputeKeywordSentiment:
    def test_bullish(self):
        texts = ["AAPL is bullish, great rally!", "buy the breakout!"]
        score = compute_keyword_sentiment(texts)
        assert score > 0

    def test_bearish(self):
        texts = ["crash incoming, sell everything", "bearish dump ahead"]
        score = compute_keyword_sentiment(texts)
        assert score < 0

    def test_neutral(self):
        texts = ["The market opened today", "Nothing special happening"]
        assert compute_keyword_sentiment(texts) == 0.0

    def test_empty(self):
        assert compute_keyword_sentiment([]) == 0.0

    def test_clamped(self):
        # All bullish keywords
        texts = [" ".join(BULLISH_KEYWORDS) * 10]
        score = compute_keyword_sentiment(texts)
        assert -1.0 <= score <= 1.0

    def test_mixed(self):
        texts = ["bullish rally but could crash soon, bearish sell"]
        score = compute_keyword_sentiment(texts)
        # Has both — should be near neutral
        assert -0.5 <= score <= 0.5

    def test_case_insensitive(self):
        texts = ["BULLISH MOON RALLY"]
        assert compute_keyword_sentiment(texts) > 0


# ---------------------------------------------------------------------------
# Synthetic sentiment
# ---------------------------------------------------------------------------


class TestGenerateSyntheticSentiment:
    def test_returns_neutral(self):
        s = generate_synthetic_sentiment("TSLA")
        assert s.ticker == "TSLA"
        assert s.score == 0.0
        assert s.source == "synthetic"
        assert s.tweet_count == 0

    def test_different_tickers(self):
        a = generate_synthetic_sentiment("AAPL")
        b = generate_synthetic_sentiment("MSFT")
        assert a.ticker != b.ticker


# ---------------------------------------------------------------------------
# Signal integration
# ---------------------------------------------------------------------------


@dataclass
class _FakeSignal:
    symbol: str
    direction: str
    confidence: float
    reason: str = ""
    metadata: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TestIncorporateSentimentSignals:
    def test_aligned_boost(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.6)]
        sentiment = [SentimentSignal(ticker="AAPL", score=0.5, tweet_count=10)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.10)
        assert result[0].confidence > 0.6

    def test_conflicting_reduce(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.6)]
        sentiment = [SentimentSignal(ticker="AAPL", score=-0.5, tweet_count=10)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.10)
        assert result[0].confidence < 0.6

    def test_neutral_no_change(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.6)]
        sentiment = [SentimentSignal(ticker="AAPL", score=0.0, tweet_count=0)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.10)
        assert result[0].confidence == 0.6

    def test_no_matching_ticker(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.6)]
        sentiment = [SentimentSignal(ticker="MSFT", score=0.8, tweet_count=10)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.10)
        assert result[0].confidence == 0.6

    def test_confidence_capped_at_one(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.95)]
        sentiment = [SentimentSignal(ticker="AAPL", score=0.8, tweet_count=50)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.20)
        assert result[0].confidence <= 1.0

    def test_confidence_floored_at_zero(self):
        signals = [_FakeSignal(symbol="AAPL", direction="buy", confidence=0.02)]
        sentiment = [SentimentSignal(ticker="AAPL", score=-0.9, tweet_count=50)]
        result = incorporate_sentiment_signals(signals, sentiment, weight=0.20)
        assert result[0].confidence >= 0.0

    def test_metadata_annotated(self):
        signals = [_FakeSignal(symbol="AAPL", direction="sell", confidence=0.7)]
        sentiment = [SentimentSignal(ticker="AAPL", score=-0.6, tweet_count=20)]
        incorporate_sentiment_signals(signals, sentiment)
        assert "sentiment_score" in signals[0].metadata
        assert signals[0].metadata["sentiment_alignment"] == "aligned"

    def test_hold_signal_neutral(self):
        signals = [_FakeSignal(symbol="AAPL", direction="hold", confidence=0.5)]
        sentiment = [SentimentSignal(ticker="AAPL", score=0.8, tweet_count=10)]
        incorporate_sentiment_signals(signals, sentiment)
        assert signals[0].confidence == 0.5  # hold + bullish = neutral treatment

    def test_empty_signals(self):
        result = incorporate_sentiment_signals([], [], weight=0.10)
        assert result == []


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestFormatSentimentReport:
    def test_basic(self):
        signals = [
            SentimentSignal(ticker="AAPL", score=0.5, tweet_count=20),
            SentimentSignal(ticker="TSLA", score=-0.3, tweet_count=15),
        ]
        report = format_sentiment_report(signals)
        assert "AAPL" in report
        assert "BULLISH" in report
        assert "TSLA" in report
        assert "BEARISH" in report

    def test_neutral_label(self):
        signals = [SentimentSignal(ticker="XYZ", score=0.0, tweet_count=0)]
        report = format_sentiment_report(signals)
        assert "NEUTRAL" in report

    def test_header(self):
        report = format_sentiment_report([])
        assert "Ginko Sentiment Report" in report

    def test_returns_string(self):
        assert isinstance(format_sentiment_report([]), str)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistSentiment:
    def test_saves_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_sentiment.SENTIMENT_DIR", tmp_path)
        signals = [
            SentimentSignal(ticker="AAPL", score=0.3, tweet_count=10),
        ]
        _persist_sentiment(signals)
        files = list(tmp_path.glob("sentiment_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["count"] == 1
        assert data["signals"][0]["ticker"] == "AAPL"


class TestLoadLatestSentiment:
    def test_loads_latest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_sentiment.SENTIMENT_DIR", tmp_path)
        # Create two files — "latest" alphabetically last
        (tmp_path / "sentiment_20240101_000000.json").write_text(
            json.dumps({"count": 1}), encoding="utf-8"
        )
        (tmp_path / "sentiment_20240102_000000.json").write_text(
            json.dumps({"count": 2}), encoding="utf-8"
        )
        data = load_latest_sentiment()
        assert data is not None
        assert data["count"] == 2

    def test_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_sentiment.SENTIMENT_DIR", tmp_path)
        assert load_latest_sentiment() is None

    def test_no_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.ginko_sentiment.SENTIMENT_DIR", tmp_path / "nope"
        )
        assert load_latest_sentiment() is None
