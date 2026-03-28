"""Ginko Data Layer — async market data fetching from free-tier APIs.

Data sources:
  - FRED (Federal Reserve Economic Data) — macro indicators, unlimited free
  - finnhub — real-time stock quotes, 60 calls/min free
  - CoinGecko — crypto prices, 30 calls/min free

All fetchers return structured dataclasses. Failures are logged,
never raised — downstream consumers handle None gracefully.

Persistence: ~/.dharma/ginko/data/ (JSON snapshots per pull)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from dharma_swarm.api_keys import (
    FINNHUB_API_KEY_ENV,
    FRED_API_KEY_ENV,
    GINKO_API_KEY_ENV_VARS,
)

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
DATA_DIR = GINKO_DIR / "data"

# API key environment variable names mapped to short provider labels
_API_KEY_ENV_VARS: dict[str, str] = dict(GINKO_API_KEY_ENV_VARS)


def validate_api_keys() -> dict[str, bool]:
    """Check which API keys are available in the environment.

    Inspects os.environ for each expected key and logs the result.
    Keys checked: OPENROUTER_API_KEY, FRED_API_KEY, FINNHUB_API_KEY,
    OLLAMA_API_KEY.  CoinGecko is excluded because its free tier
    does not require an API key.

    Returns:
        Dict mapping provider label to presence (True/False).
    """
    status: dict[str, bool] = {}
    for label, env_var in _API_KEY_ENV_VARS.items():
        present = bool(os.environ.get(env_var))
        status[label] = present
        if present:
            logger.info("API key found: %s (%s)", label, env_var)
        else:
            logger.warning("API key missing: %s (%s)", label, env_var)
    return status


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class MacroSnapshot:
    """FRED macro indicators at a point in time."""
    timestamp: str
    fed_funds_rate: float | None = None      # DFF
    ten_year_yield: float | None = None      # DGS10
    two_year_yield: float | None = None      # DGS2
    yield_spread: float | None = None        # T10Y2Y (10Y - 2Y)
    vix: float | None = None                 # VIXCLS
    unemployment: float | None = None        # UNRATE
    cpi_yoy: float | None = None             # CPIAUCSL (year-over-year)
    gdp_growth: float | None = None          # A191RL1Q225SBEA
    m2_money_supply: float | None = None     # M2SL


@dataclass
class StockQuote:
    """Real-time stock quote from finnhub."""
    symbol: str
    current_price: float
    change: float
    percent_change: float
    high: float
    low: float
    open_price: float
    previous_close: float
    timestamp: str


@dataclass
class CryptoPrice:
    """Crypto price data from CoinGecko."""
    coin_id: str
    symbol: str
    current_price_usd: float
    market_cap: float
    volume_24h: float
    price_change_24h_pct: float
    timestamp: str


@dataclass
class MarketDataPull:
    """Complete market data snapshot from a single pull cycle."""
    timestamp: str
    macro: MacroSnapshot | None = None
    stocks: list[StockQuote] = field(default_factory=list)
    crypto: list[CryptoPrice] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FRED API (macro data)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Key FRED series for macro regime detection
FRED_SERIES = {
    "fed_funds_rate": "DFF",
    "ten_year_yield": "DGS10",
    "two_year_yield": "DGS2",
    "yield_spread": "T10Y2Y",
    "vix": "VIXCLS",
    "unemployment": "UNRATE",
}


async def fetch_fred_series(
    series_id: str,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> float | None:
    """Fetch the latest observation for a FRED series.

    Args:
        series_id: FRED series ID (e.g. "DFF", "DGS10").
        api_key: FRED API key. Falls back to FRED_API_KEY env var.
        client: Optional shared httpx client.

    Returns:
        Latest numeric value or None on failure.
    """
    key = api_key or os.getenv(FRED_API_KEY_ENV)
    if not key:
        logger.warning("%s not set — skipping %s", FRED_API_KEY_ENV, series_id)
        return None

    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": "1",
    }

    try:
        if client:
            resp = await client.get(FRED_BASE, params=params, timeout=15)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.get(FRED_BASE, params=params, timeout=15)

        resp.raise_for_status()
        data = resp.json()
        observations = data.get("observations", [])
        if observations:
            val = observations[0].get("value", ".")
            if val != ".":
                return float(val)
    except Exception as e:
        logger.error("FRED fetch %s failed: %s", series_id, e)
    return None


async def fetch_macro_snapshot(
    api_key: str | None = None,
) -> MacroSnapshot | None:
    """Fetch all macro indicators into a MacroSnapshot.

    Returns None early (with a warning) when no FRED API key is available,
    instead of making doomed HTTP calls for every series.
    """
    key = api_key or os.getenv(FRED_API_KEY_ENV)
    if not key:
        logger.warning("Skipping FRED macro snapshot: no %s", FRED_API_KEY_ENV)
        return None

    now = _utc_now().isoformat()
    snapshot = MacroSnapshot(timestamp=now)

    async with httpx.AsyncClient() as client:
        for field_name, series_id in FRED_SERIES.items():
            value = await fetch_fred_series(series_id, api_key, client)
            if value is not None:
                setattr(snapshot, field_name, value)

    return snapshot


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FINNHUB API (stock quotes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"

# Default watchlist — major indices + bellwethers
DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "TLT", "GLD", "AAPL", "NVDA", "MSFT"]


async def fetch_stock_quote(
    symbol: str,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> StockQuote | None:
    """Fetch real-time quote for a stock symbol.

    Args:
        symbol: Ticker symbol (e.g. "AAPL").
        api_key: finnhub API key. Falls back to FINNHUB_API_KEY env var.
        client: Optional shared httpx client.

    Returns:
        StockQuote or None on failure.
    """
    key = api_key or os.getenv(FINNHUB_API_KEY_ENV)
    if not key:
        logger.warning("%s not set — skipping %s", FINNHUB_API_KEY_ENV, symbol)
        return None

    params = {"symbol": symbol, "token": key}

    try:
        if client:
            resp = await client.get(FINNHUB_QUOTE, params=params, timeout=10)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.get(FINNHUB_QUOTE, params=params, timeout=10)

        resp.raise_for_status()
        d = resp.json()

        if d.get("c", 0) == 0:
            return None

        return StockQuote(
            symbol=symbol,
            current_price=d["c"],
            change=d["d"],
            percent_change=d["dp"],
            high=d["h"],
            low=d["l"],
            open_price=d["o"],
            previous_close=d["pc"],
            timestamp=_utc_now().isoformat(),
        )
    except Exception as e:
        logger.error("finnhub fetch %s failed: %s", symbol, e)
        return None


async def fetch_stock_quotes(
    symbols: list[str] | None = None,
    api_key: str | None = None,
) -> list[StockQuote]:
    """Fetch quotes for a list of symbols.

    Returns an empty list early (with a warning) when no finnhub API key
    is available.
    """
    key = api_key or os.getenv(FINNHUB_API_KEY_ENV)
    if not key:
        logger.warning("Skipping stock quotes: no %s", FINNHUB_API_KEY_ENV)
        return []

    symbols = symbols or DEFAULT_SYMBOLS
    quotes: list[StockQuote] = []

    async with httpx.AsyncClient() as client:
        for symbol in symbols:
            quote = await fetch_stock_quote(symbol, api_key, client)
            if quote:
                quotes.append(quote)

    return quotes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COINGECKO API (crypto prices)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

DEFAULT_COINS = ["bitcoin", "ethereum", "solana"]


async def fetch_crypto_prices(
    coin_ids: list[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[CryptoPrice]:
    """Fetch crypto market data from CoinGecko (no API key needed).

    Args:
        coin_ids: List of CoinGecko coin IDs. Defaults to BTC, ETH, SOL.
        client: Optional shared httpx client.

    Returns:
        List of CryptoPrice objects.
    """
    coins = coin_ids or DEFAULT_COINS
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins),
        "order": "market_cap_desc",
        "sparkline": "false",
    }

    try:
        if client:
            resp = await client.get(COINGECKO_MARKETS, params=params, timeout=15)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.get(COINGECKO_MARKETS, params=params, timeout=15)

        resp.raise_for_status()
        data = resp.json()
        now = _utc_now().isoformat()

        return [
            CryptoPrice(
                coin_id=coin["id"],
                symbol=coin["symbol"],
                current_price_usd=coin["current_price"],
                market_cap=coin.get("market_cap", 0),
                volume_24h=coin.get("total_volume", 0),
                price_change_24h_pct=coin.get("price_change_percentage_24h", 0),
                timestamp=now,
            )
            for coin in data
        ]
    except Exception as e:
        logger.error("CoinGecko fetch failed: %s", e)
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMBINED PULL + PERSISTENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def pull_all_data(
    stock_symbols: list[str] | None = None,
    crypto_coins: list[str] | None = None,
) -> MarketDataPull:
    """Pull all market data sources and persist snapshot.

    Calls validate_api_keys() first and skips sources whose required
    key is missing, logging a warning instead of crashing.

    Returns:
        MarketDataPull with all available data.
    """
    now = _utc_now()
    pull = MarketDataPull(timestamp=now.isoformat())
    keys = validate_api_keys()

    # FRED (macro data) — requires FRED_API_KEY
    if keys.get("fred"):
        try:
            pull.macro = await fetch_macro_snapshot()
        except Exception as e:
            pull.errors.append(f"FRED: {e}")
    else:
        logger.warning("Skipping FRED: no FRED_API_KEY")

    # Finnhub (stock quotes) — requires FINNHUB_API_KEY
    if keys.get("finnhub"):
        try:
            pull.stocks = await fetch_stock_quotes(stock_symbols)
        except Exception as e:
            pull.errors.append(f"finnhub: {e}")
    else:
        logger.warning("Skipping finnhub: no FINNHUB_API_KEY")

    # CoinGecko (crypto) — no API key required
    try:
        pull.crypto = await fetch_crypto_prices(crypto_coins)
    except Exception as e:
        pull.errors.append(f"CoinGecko: {e}")

    # Persist snapshot
    _ensure_dirs()
    snapshot_file = DATA_DIR / f"pull_{now.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        snapshot_file.write_text(
            json.dumps(_pull_to_dict(pull), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Failed to persist data pull: %s", e)

    return pull


def _pull_to_dict(pull: MarketDataPull) -> dict[str, Any]:
    """Convert MarketDataPull to serializable dict."""
    return {
        "timestamp": pull.timestamp,
        "macro": asdict(pull.macro) if pull.macro else None,
        "stocks": [asdict(q) for q in pull.stocks],
        "crypto": [asdict(c) for c in pull.crypto],
        "errors": pull.errors,
    }


def load_latest_pull() -> MarketDataPull | None:
    """Load the most recent data pull from disk."""
    _ensure_dirs()
    files = sorted(DATA_DIR.glob("pull_*.json"), reverse=True)
    if not files:
        return None

    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        macro = None
        if data.get("macro"):
            macro = MacroSnapshot(**data["macro"])

        stocks = [StockQuote(**s) for s in data.get("stocks", [])]
        crypto = [CryptoPrice(**c) for c in data.get("crypto", [])]

        return MarketDataPull(
            timestamp=data["timestamp"],
            macro=macro,
            stocks=stocks,
            crypto=crypto,
            errors=data.get("errors", []),
        )
    except Exception as e:
        logger.error("Failed to load data pull: %s", e)
        return None
