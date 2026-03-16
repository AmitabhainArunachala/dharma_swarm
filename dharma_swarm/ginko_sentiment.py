"""Ginko Social Sentiment — X/Twitter sentiment as a signal source.

Pipeline:
  1. Fetch recent tweets mentioning $TICKER via X API v2
  2. Score sentiment via keyword matching (bullish vs bearish)
  3. Produce SentimentSignal objects consumable by signal synthesis
  4. Optionally adjust existing Signal confidence based on sentiment alignment

Requires X_BEARER_TOKEN env var for live X API calls.
Falls back to keyword_fallback or synthetic mode when unavailable.

Persistence: ~/.dharma/ginko/sentiment/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
SENTIMENT_DIR = GINKO_DIR / "sentiment"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Keyword lexicons
# ---------------------------------------------------------------------------

BULLISH_KEYWORDS: list[str] = [
    "bullish",
    "moon",
    "buy",
    "rally",
    "breakout",
    "undervalued",
    "accumulate",
    "upgrade",
    "beat",
    "strong",
]

BEARISH_KEYWORDS: list[str] = [
    "bearish",
    "crash",
    "sell",
    "dump",
    "overvalued",
    "downgrade",
    "miss",
    "weak",
    "recession",
    "default",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SentimentSignal:
    """Social sentiment measurement for a single ticker."""

    ticker: str
    score: float  # -1.0 (bearish) to +1.0 (bullish)
    tweet_count: int
    sample_texts: list[str] = field(default_factory=list)  # up to 5
    source: str = "x_api"  # "x_api" | "keyword_fallback" | "synthetic"
    timestamp: str = field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Keyword sentiment scoring
# ---------------------------------------------------------------------------

def compute_keyword_sentiment(texts: list[str]) -> float:
    """Score sentiment from a list of texts using keyword matching.

    Counts bullish vs bearish keyword occurrences across all texts.
    Score = (bullish_count - bearish_count) / max(bullish_count + bearish_count, 1)
    Clamped to [-1.0, 1.0].

    Args:
        texts: List of text strings (tweets, posts, etc.).

    Returns:
        Sentiment score from -1.0 (bearish) to +1.0 (bullish).
    """
    bullish_count = 0
    bearish_count = 0

    for text in texts:
        lower = text.lower()
        for kw in BULLISH_KEYWORDS:
            bullish_count += lower.count(kw)
        for kw in BEARISH_KEYWORDS:
            bearish_count += lower.count(kw)

    total = bullish_count + bearish_count
    if total == 0:
        return 0.0

    raw = (bullish_count - bearish_count) / max(total, 1)
    return max(-1.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# X API integration
# ---------------------------------------------------------------------------

async def fetch_x_sentiment(
    ticker: str,
    hours: int = 24,
) -> SentimentSignal | None:
    """Fetch sentiment for a ticker from X/Twitter API v2.

    Uses the recent search endpoint to pull tweets mentioning $TICKER,
    then scores them via keyword sentiment.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        hours: Lookback window in hours (default 24).

    Returns:
        SentimentSignal if successful, None on auth failure or error.
    """
    import httpx

    bearer_token = os.environ.get("X_BEARER_TOKEN")
    if not bearer_token:
        logger.warning(
            "X_BEARER_TOKEN not set — cannot fetch X sentiment for %s", ticker
        )
        return None

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": f"${ticker} lang:en -is:retweet",
        "max_results": "100",
        "tweet.fields": "created_at,text",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code == 429:
                logger.warning("X API rate limited (429) for %s", ticker)
                return None

            if resp.status_code == 401:
                logger.error("X API auth failed (401) — check X_BEARER_TOKEN")
                return None

            if resp.status_code != 200:
                logger.error(
                    "X API error %d for %s: %s",
                    resp.status_code,
                    ticker,
                    resp.text[:200],
                )
                return None

            data = resp.json()

    except httpx.TimeoutException:
        logger.error("X API timeout for %s", ticker)
        return None
    except httpx.HTTPError as exc:
        logger.error("X API HTTP error for %s: %s", ticker, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error fetching X sentiment for %s: %s", ticker, exc)
        return None

    tweets = data.get("data", [])
    if not tweets:
        logger.info("No tweets found for $%s", ticker)
        return SentimentSignal(
            ticker=ticker,
            score=0.0,
            tweet_count=0,
            sample_texts=[],
            source="x_api",
        )

    texts = [t.get("text", "") for t in tweets]
    score = compute_keyword_sentiment(texts)
    sample_texts = texts[:5]

    return SentimentSignal(
        ticker=ticker,
        score=round(score, 4),
        tweet_count=len(tweets),
        sample_texts=sample_texts,
        source="x_api",
    )


# ---------------------------------------------------------------------------
# Batch fetching
# ---------------------------------------------------------------------------

async def fetch_sentiment_batch(
    tickers: list[str],
    hours: int = 24,
) -> list[SentimentSignal]:
    """Fetch sentiment for multiple tickers with rate-limit-safe pacing.

    Inserts a 1-second delay between API calls to respect X rate limits.
    Failures for individual tickers are logged and skipped.

    Args:
        tickers: List of ticker symbols.
        hours: Lookback window in hours.

    Returns:
        List of successfully fetched SentimentSignals.
    """
    results: list[SentimentSignal] = []

    for i, ticker in enumerate(tickers):
        if i > 0:
            await asyncio.sleep(1.0)  # rate limit spacing

        signal = await fetch_x_sentiment(ticker, hours=hours)
        if signal is not None:
            results.append(signal)
            logger.info(
                "Sentiment for %s: score=%.3f tweets=%d source=%s",
                ticker,
                signal.score,
                signal.tweet_count,
                signal.source,
            )
        else:
            logger.warning("Skipped %s — fetch returned None", ticker)

    # Persist batch results
    if results:
        _persist_sentiment(results)

    return results


# ---------------------------------------------------------------------------
# Synthetic / fallback
# ---------------------------------------------------------------------------

def generate_synthetic_sentiment(ticker: str) -> SentimentSignal:
    """Generate neutral synthetic sentiment for testing/demo.

    Used when no X API key is available and real data is not needed.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        SentimentSignal with score=0.0 and source="synthetic".
    """
    return SentimentSignal(
        ticker=ticker,
        score=0.0,
        tweet_count=0,
        sample_texts=[],
        source="synthetic",
    )


# ---------------------------------------------------------------------------
# Signal integration
# ---------------------------------------------------------------------------

def incorporate_sentiment_signals(
    signals: list[Any],
    sentiment: list[SentimentSignal],
    weight: float = 0.10,
) -> list[Any]:
    """Adjust Signal confidence based on social sentiment alignment.

    For each Signal whose symbol matches a SentimentSignal ticker:
      - If sentiment aligns with signal direction: confidence += weight
      - If sentiment conflicts with signal direction: confidence -= weight * 0.5
      - Sentiment score is recorded in signal metadata/reason

    Confidence is capped to [0.0, 1.0].

    Args:
        signals: List of Signal objects (from ginko_signals).
        sentiment: List of SentimentSignal objects.
        weight: Base weight for sentiment adjustment (default 0.10).

    Returns:
        The same list of signals, modified in place.
    """
    sent_by_ticker: dict[str, SentimentSignal] = {s.ticker: s for s in sentiment}

    for signal in signals:
        # Support both .symbol and .ticker attribute names
        symbol = getattr(signal, "symbol", None) or getattr(signal, "ticker", None)
        if symbol is None:
            continue

        sent = sent_by_ticker.get(symbol)
        if sent is None:
            continue

        direction = getattr(signal, "direction", "hold")
        signal_bullish = direction == "buy"
        signal_bearish = direction == "sell"
        sent_bullish = sent.score > 0.1
        sent_bearish = sent.score < -0.1

        old_conf = getattr(signal, "confidence", 0.5)

        if (signal_bullish and sent_bullish) or (signal_bearish and sent_bearish):
            # Aligned — boost confidence
            new_conf = min(1.0, old_conf + weight)
            alignment = "aligned"
        elif (signal_bullish and sent_bearish) or (signal_bearish and sent_bullish):
            # Conflicting — reduce confidence
            new_conf = max(0.0, old_conf - weight * 0.5)
            alignment = "conflicting"
        else:
            # Neutral sentiment or hold signal — no adjustment
            new_conf = old_conf
            alignment = "neutral"

        signal.confidence = round(new_conf, 4)

        # Annotate reason
        sent_label = f"sentiment={sent.score:+.3f}"
        if hasattr(signal, "reason") and isinstance(signal.reason, str):
            signal.reason += f"; social {alignment} ({sent_label})"

        # Annotate metadata
        if hasattr(signal, "metadata") and isinstance(signal.metadata, dict):
            signal.metadata["sentiment_score"] = sent.score
            signal.metadata["sentiment_alignment"] = alignment
            signal.metadata["sentiment_tweet_count"] = sent.tweet_count
            signal.metadata["sentiment_source"] = sent.source

    return signals


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_sentiment_report(signals: list[SentimentSignal]) -> str:
    """Format sentiment signals as a human-readable table.

    Columns: Ticker | Sentiment | Score | Tweets | Source

    Args:
        signals: List of SentimentSignal objects.

    Returns:
        Formatted table string.
    """
    lines = [
        "Ginko Sentiment Report",
        "=" * 60,
        f"{'Ticker':<8} {'Sentiment':<12} {'Score':>8} {'Tweets':>8} {'Source':<18}",
        "-" * 60,
    ]

    for s in signals:
        if s.score > 0.1:
            label = "BULLISH"
        elif s.score < -0.1:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        lines.append(
            f"{s.ticker:<8} {label:<12} {s.score:>+8.3f} {s.tweet_count:>8} {s.source:<18}"
        )

    lines.append("-" * 60)
    lines.append(f"Generated: {_utc_now().isoformat()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist_sentiment(signals: list[SentimentSignal]) -> None:
    """Save sentiment signals to disk as JSON.

    File: ~/.dharma/ginko/sentiment/sentiment_YYYYMMDD_HHMMSS.json
    """
    SENTIMENT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    out_file = SENTIMENT_DIR / f"sentiment_{ts}.json"

    payload = {
        "timestamp": _utc_now().isoformat(),
        "count": len(signals),
        "signals": [asdict(s) for s in signals],
    }

    try:
        out_file.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Persisted sentiment to %s", out_file)
    except Exception as exc:
        logger.error("Failed to persist sentiment: %s", exc)


def load_latest_sentiment() -> dict[str, Any] | None:
    """Load the most recent sentiment report from disk.

    Returns:
        Parsed JSON dict, or None if no reports exist.
    """
    if not SENTIMENT_DIR.exists():
        return None

    files = sorted(SENTIMENT_DIR.glob("sentiment_*.json"), reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to load sentiment report: %s", exc)
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    """Fetch sentiment for a default ticker list and print the report."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    tickers = ["AAPL", "NVDA", "MSFT", "TSLA"]

    bearer = os.environ.get("X_BEARER_TOKEN")
    if not bearer:
        logger.warning(
            "X_BEARER_TOKEN not set — generating synthetic sentiment"
        )
        signals = [generate_synthetic_sentiment(t) for t in tickers]
        _persist_sentiment(signals)
    else:
        signals = await fetch_sentiment_batch(tickers)

    print(format_sentiment_report(signals))


if __name__ == "__main__":
    asyncio.run(_main())
