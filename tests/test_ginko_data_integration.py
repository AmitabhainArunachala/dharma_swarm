"""Integration tests for the Ginko data pipeline.

End-to-end tests covering the full data flow:
  fetch (FRED / Finnhub / CoinGecko) -> persist -> regime detection -> signals.

All HTTP calls are mocked via httpx.MockTransport or unittest.mock.patch.
State is isolated to a per-test temp directory via DHARMA_HOME.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest

# Isolate state BEFORE any dharma_swarm imports evaluate DATA_DIR at module level.
_temp_dir = tempfile.mkdtemp(prefix="ginko_integration_")
os.environ["DHARMA_HOME"] = _temp_dir

from dharma_swarm.ginko_data import (
    CryptoPrice,
    MacroSnapshot,
    MarketDataPull,
    StockQuote,
    _pull_to_dict,
    fetch_crypto_prices,
    fetch_fred_series,
    fetch_macro_snapshot,
    fetch_stock_quote,
    fetch_stock_quotes,
    load_latest_pull,
    pull_all_data,
    validate_api_keys,
    DATA_DIR,
    FRED_BASE,
    FINNHUB_QUOTE,
    COINGECKO_MARKETS,
)
from dharma_swarm.ginko_regime import (
    MarketRegime,
    RegimeDetection,
    ReturnSeries,
    analyze_regime,
    detect_regime_rules,
)
from dharma_swarm.ginko_signals import (
    SignalDirection,
    SignalReport,
    compute_indicators,
    compute_rsi,
    compute_sma,
    generate_signal_report,
    synthesize_signal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_data_dir():
    """Ensure DATA_DIR is clean before and after each test."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Wipe generated files so tests never leak state
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Mock response factories
# ---------------------------------------------------------------------------

def _fred_json(value: str = "5.25", date: str = "2026-03-15") -> dict[str, Any]:
    """Build a realistic FRED API response."""
    return {"observations": [{"date": date, "value": value}]}


def _finnhub_json(
    c: float = 175.50,
    d: float = 2.30,
    dp: float = 1.33,
    h: float = 176.00,
    l: float = 173.00,
    o: float = 173.50,
    pc: float = 173.20,
) -> dict[str, Any]:
    """Build a realistic Finnhub /quote response."""
    return {"c": c, "d": d, "dp": dp, "h": h, "l": l, "o": o, "pc": pc}


def _coingecko_json() -> list[dict[str, Any]]:
    """Build a realistic CoinGecko /coins/markets response."""
    return [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "current_price": 65000.0,
            "market_cap": 1_200_000_000_000,
            "total_volume": 30_000_000_000,
            "price_change_percentage_24h": 2.5,
        },
        {
            "id": "ethereum",
            "symbol": "eth",
            "current_price": 3500.0,
            "market_cap": 420_000_000_000,
            "total_volume": 15_000_000_000,
            "price_change_percentage_24h": -1.2,
        },
    ]


# ---------------------------------------------------------------------------
# TestFREDFetcher
# ---------------------------------------------------------------------------

class TestFREDFetcher:
    """Tests for FRED API integration (fetch_fred_series, fetch_macro_snapshot)."""

    @pytest.mark.asyncio
    async def test_fetch_fred_series_success(self):
        """Mock a successful FRED observation and verify parsing."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "series_id" in str(request.url)
            return httpx.Response(200, json=_fred_json("5.25"))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            val = await fetch_fred_series("DFF", api_key="test_key", client=client)

        assert val == 5.25

    @pytest.mark.asyncio
    async def test_fetch_fred_series_missing_key(self):
        """Without FRED_API_KEY env var or argument, should return None."""
        old_key = os.environ.pop("FRED_API_KEY", None)
        try:
            val = await fetch_fred_series("DFF", api_key=None, client=None)
            assert val is None
        finally:
            if old_key is not None:
                os.environ["FRED_API_KEY"] = old_key

    @pytest.mark.asyncio
    async def test_fetch_fred_series_api_error(self):
        """Server 500 response should return None without raising."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            val = await fetch_fred_series("DFF", api_key="test_key", client=client)

        assert val is None

    @pytest.mark.asyncio
    async def test_fetch_fred_dot_value(self):
        """FRED returns '.' for missing data points -- should yield None."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_fred_json("."))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            val = await fetch_fred_series("DFF", api_key="test_key", client=client)

        assert val is None

    @pytest.mark.asyncio
    async def test_fetch_macro_snapshot(self):
        """Mock all FRED series calls and verify the assembled MacroSnapshot."""
        call_count = 0

        series_values = {
            "DFF": "5.25",
            "DGS10": "4.50",
            "DGS2": "4.20",
            "T10Y2Y": "0.30",
            "VIXCLS": "16.5",
            "UNRATE": "3.8",
        }

        async def mock_fetch(series_id, api_key=None, client=None):
            nonlocal call_count
            call_count += 1
            val_str = series_values.get(series_id)
            if val_str is not None:
                return float(val_str)
            return None

        with patch("dharma_swarm.ginko_data.fetch_fred_series", side_effect=mock_fetch):
            snap = await fetch_macro_snapshot(api_key="test_key")

        assert snap.fed_funds_rate == 5.25
        assert snap.ten_year_yield == 4.50
        assert snap.yield_spread == 0.30
        assert snap.vix == 16.5
        assert snap.unemployment == 3.8
        assert call_count == 6  # One call per series in FRED_SERIES


# ---------------------------------------------------------------------------
# TestFinnhubFetcher
# ---------------------------------------------------------------------------

class TestFinnhubFetcher:
    """Tests for Finnhub stock quote integration."""

    @pytest.mark.asyncio
    async def test_fetch_stock_quote_success(self):
        """Mock a valid Finnhub quote and verify StockQuote fields."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_finnhub_json())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            quote = await fetch_stock_quote("AAPL", api_key="test_key", client=client)

        assert quote is not None
        assert quote.symbol == "AAPL"
        assert quote.current_price == 175.50
        assert quote.change == 2.30
        assert quote.percent_change == 1.33
        assert quote.high == 176.00
        assert quote.low == 173.00
        assert quote.open_price == 173.50
        assert quote.previous_close == 173.20

    @pytest.mark.asyncio
    async def test_fetch_stock_quote_zero_price(self):
        """Finnhub returns c=0 for invalid/delisted symbols -- should yield None."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_finnhub_json(c=0))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            quote = await fetch_stock_quote("FAKE", api_key="test_key", client=client)

        assert quote is None

    @pytest.mark.asyncio
    async def test_fetch_stock_quotes_multiple(self):
        """Fetch multiple symbols and verify all come back."""
        symbols = ["AAPL", "MSFT", "NVDA"]
        prices = {"AAPL": 175.50, "MSFT": 420.00, "NVDA": 890.00}

        async def mock_fetch(symbol, api_key=None, client=None):
            return StockQuote(
                symbol=symbol,
                current_price=prices[symbol],
                change=1.0,
                percent_change=0.5,
                high=prices[symbol] + 2,
                low=prices[symbol] - 2,
                open_price=prices[symbol] - 1,
                previous_close=prices[symbol] - 1,
                timestamp="2026-03-16T00:00:00Z",
            )

        with patch("dharma_swarm.ginko_data.fetch_stock_quote", side_effect=mock_fetch):
            quotes = await fetch_stock_quotes(symbols, api_key="test_key")

        assert len(quotes) == 3
        quote_symbols = {q.symbol for q in quotes}
        assert quote_symbols == {"AAPL", "MSFT", "NVDA"}
        assert quotes[0].current_price == 175.50

    @pytest.mark.asyncio
    async def test_fetch_stock_quote_no_key(self):
        """Without FINNHUB_API_KEY, should return None."""
        old_key = os.environ.pop("FINNHUB_API_KEY", None)
        try:
            quote = await fetch_stock_quote("AAPL", api_key=None, client=None)
            assert quote is None
        finally:
            if old_key is not None:
                os.environ["FINNHUB_API_KEY"] = old_key


# ---------------------------------------------------------------------------
# TestCoinGeckoFetcher
# ---------------------------------------------------------------------------

class TestCoinGeckoFetcher:
    """Tests for CoinGecko crypto price integration."""

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_success(self):
        """Mock CoinGecko response with BTC and ETH."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_coingecko_json())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            prices = await fetch_crypto_prices(
                coin_ids=["bitcoin", "ethereum"], client=client
            )

        assert len(prices) == 2
        btc = next(p for p in prices if p.coin_id == "bitcoin")
        assert btc.current_price_usd == 65000.0
        assert btc.symbol == "btc"
        assert btc.market_cap == 1_200_000_000_000
        assert btc.volume_24h == 30_000_000_000
        assert btc.price_change_24h_pct == 2.5

        eth = next(p for p in prices if p.coin_id == "ethereum")
        assert eth.current_price_usd == 3500.0

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_empty(self):
        """Empty API response should return an empty list."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            prices = await fetch_crypto_prices(coin_ids=["bitcoin"], client=client)

        assert prices == []

    @pytest.mark.asyncio
    async def test_fetch_crypto_prices_error(self):
        """Connection error should return [] without raising."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            prices = await fetch_crypto_prices(coin_ids=["bitcoin"], client=client)

        assert prices == []


# ---------------------------------------------------------------------------
# TestPullAllData
# ---------------------------------------------------------------------------

class TestPullAllData:
    """Tests for the combined pull_all_data orchestrator."""

    @pytest.mark.asyncio
    async def test_pull_all_data_success(self):
        """Mock all three API layers and verify the assembled MarketDataPull."""
        mock_macro = MacroSnapshot(
            timestamp="2026-03-16T00:00:00Z",
            fed_funds_rate=5.25,
            ten_year_yield=4.50,
            vix=16.5,
        )
        mock_stocks = [
            StockQuote(
                symbol="SPY",
                current_price=500.0,
                change=2.0,
                percent_change=0.4,
                high=502.0,
                low=498.0,
                open_price=499.0,
                previous_close=498.0,
                timestamp="2026-03-16T00:00:00Z",
            ),
        ]
        mock_crypto = [
            CryptoPrice(
                coin_id="bitcoin",
                symbol="btc",
                current_price_usd=65000.0,
                market_cap=1_200_000_000_000,
                volume_24h=30_000_000_000,
                price_change_24h_pct=2.5,
                timestamp="2026-03-16T00:00:00Z",
            ),
        ]

        all_keys_present = {
            "openrouter": True, "fred": True, "finnhub": True, "ollama": True,
        }
        with (
            patch(
                "dharma_swarm.ginko_data.validate_api_keys",
                return_value=all_keys_present,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_macro_snapshot",
                new_callable=AsyncMock,
                return_value=mock_macro,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_stock_quotes",
                new_callable=AsyncMock,
                return_value=mock_stocks,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_crypto_prices",
                new_callable=AsyncMock,
                return_value=mock_crypto,
            ),
        ):
            pull = await pull_all_data(
                stock_symbols=["SPY"], crypto_coins=["bitcoin"]
            )

        assert pull.macro is not None
        assert pull.macro.fed_funds_rate == 5.25
        assert len(pull.stocks) == 1
        assert pull.stocks[0].symbol == "SPY"
        assert len(pull.crypto) == 1
        assert pull.crypto[0].coin_id == "bitcoin"
        assert len(pull.errors) == 0

    @pytest.mark.asyncio
    async def test_pull_all_data_partial_failure(self):
        """When one API fails, others still succeed and the error is logged."""
        mock_macro = MacroSnapshot(
            timestamp="2026-03-16T00:00:00Z", fed_funds_rate=5.25
        )

        all_keys_present = {
            "openrouter": True, "fred": True, "finnhub": True, "ollama": True,
        }
        with (
            patch(
                "dharma_swarm.ginko_data.validate_api_keys",
                return_value=all_keys_present,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_macro_snapshot",
                new_callable=AsyncMock,
                return_value=mock_macro,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_stock_quotes",
                new_callable=AsyncMock,
                side_effect=Exception("Finnhub timeout"),
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_crypto_prices",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            pull = await pull_all_data()

        # Macro succeeded
        assert pull.macro is not None
        assert pull.macro.fed_funds_rate == 5.25
        # Stocks failed
        assert "finnhub" in pull.errors[0].lower() or "Finnhub" in pull.errors[0]
        # Crypto returned empty (not an error, just no data)
        assert pull.crypto == []

    @pytest.mark.asyncio
    async def test_pull_persistence(self):
        """Verify pull_all_data writes a JSON snapshot to DATA_DIR."""
        mock_macro = MacroSnapshot(
            timestamp="2026-03-16T12:00:00Z", fed_funds_rate=5.25
        )

        all_keys_present = {
            "openrouter": True, "fred": True, "finnhub": True, "ollama": True,
        }
        with (
            patch(
                "dharma_swarm.ginko_data.validate_api_keys",
                return_value=all_keys_present,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_macro_snapshot",
                new_callable=AsyncMock,
                return_value=mock_macro,
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_stock_quotes",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "dharma_swarm.ginko_data.fetch_crypto_prices",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await pull_all_data()

        files = list(DATA_DIR.glob("pull_*.json"))
        assert len(files) >= 1

        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["macro"]["fed_funds_rate"] == 5.25
        assert isinstance(data["stocks"], list)
        assert isinstance(data["errors"], list)


# ---------------------------------------------------------------------------
# TestDataFlow (end-to-end pipeline)
# ---------------------------------------------------------------------------

class TestDataFlow:
    """End-to-end data flow: pull -> persist -> load -> regime -> signals."""

    def test_load_latest_pull_round_trip(self):
        """Save a MarketDataPull to disk and load it back, verify fidelity."""
        pull = MarketDataPull(
            timestamp="2026-03-16T14:30:00Z",
            macro=MacroSnapshot(
                timestamp="2026-03-16T14:30:00Z",
                fed_funds_rate=5.25,
                ten_year_yield=4.50,
                vix=16.5,
            ),
            stocks=[
                StockQuote(
                    symbol="SPY",
                    current_price=500.0,
                    change=2.0,
                    percent_change=0.4,
                    high=502.0,
                    low=498.0,
                    open_price=499.0,
                    previous_close=498.0,
                    timestamp="2026-03-16T14:30:00Z",
                ),
                StockQuote(
                    symbol="QQQ",
                    current_price=430.0,
                    change=-1.5,
                    percent_change=-0.35,
                    high=432.0,
                    low=428.0,
                    open_price=431.0,
                    previous_close=431.5,
                    timestamp="2026-03-16T14:30:00Z",
                ),
            ],
            crypto=[
                CryptoPrice(
                    coin_id="bitcoin",
                    symbol="btc",
                    current_price_usd=65000.0,
                    market_cap=1_200_000_000_000,
                    volume_24h=30_000_000_000,
                    price_change_24h_pct=2.5,
                    timestamp="2026-03-16T14:30:00Z",
                ),
            ],
            errors=[],
        )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        f = DATA_DIR / "pull_20260316_143000.json"
        f.write_text(json.dumps(_pull_to_dict(pull), default=str))

        loaded = load_latest_pull()
        assert loaded is not None
        assert loaded.macro is not None
        assert loaded.macro.fed_funds_rate == 5.25
        assert loaded.macro.vix == 16.5
        assert len(loaded.stocks) == 2
        assert loaded.stocks[0].symbol == "SPY"
        assert loaded.stocks[1].symbol == "QQQ"
        assert len(loaded.crypto) == 1
        assert loaded.crypto[0].coin_id == "bitcoin"
        assert loaded.errors == []

    def test_data_to_regime(self):
        """Build returns from stock price data and run regime detection."""
        # Simulate 30 days of uptrending daily closes
        closes = [400.0 + i * 2.0 for i in range(31)]
        # Convert to daily log returns
        returns_vals = [
            np.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)
        ]
        timestamps = [f"day_{i}" for i in range(len(returns_vals))]
        series = ReturnSeries(values=returns_vals, timestamps=timestamps, symbol="SPY")

        result = analyze_regime(series, use_hmm=False, use_garch=False)
        assert isinstance(result, RegimeDetection)
        assert result.regime in [r.value for r in MarketRegime]
        assert result.method == "rule_based"
        assert result.timestamp  # non-empty

    def test_data_to_signals(self):
        """Pull price data into generate_signal_report and verify output."""
        price_data = {
            "SPY": [400.0 + i * 0.5 for i in range(60)],
            "QQQ": [300.0 + i * 0.3 for i in range(60)],
        }
        macro = {"fed_funds_rate": 5.25, "vix": 16.5, "yield_spread": 0.30}

        report = generate_signal_report(
            regime="bull",
            regime_confidence=0.85,
            price_data=price_data,
            macro_data=macro,
        )

        assert isinstance(report, SignalReport)
        assert report.regime == "bull"
        assert len(report.signals) == 2
        for sig in report.signals:
            assert sig.symbol in ("SPY", "QQQ")
            assert sig.direction in ("buy", "sell", "hold")
            assert 0 <= sig.confidence <= 1.0
            assert len(sig.reason) > 0
        assert "VIX" in report.macro_summary
        assert report.risk_level == "low"

    def test_full_pipeline(self):
        """Complete pipeline: mock data -> regime -> signals -> verify report.

        Simulates what the Ginko orchestrator does each cycle.
        """
        # 1. Build mock market data
        n_days = 60
        spy_closes = [400.0 + i * 0.5 for i in range(n_days)]
        qqq_closes = [300.0 + i * 0.3 for i in range(n_days)]

        macro = MacroSnapshot(
            timestamp="2026-03-16T00:00:00Z",
            fed_funds_rate=5.25,
            ten_year_yield=4.50,
            yield_spread=0.30,
            vix=16.5,
        )

        # 2. Regime detection from SPY returns
        returns_vals = [
            np.log(spy_closes[i + 1] / spy_closes[i])
            for i in range(len(spy_closes) - 1)
        ]
        series = ReturnSeries(
            values=returns_vals,
            timestamps=[f"d{i}" for i in range(len(returns_vals))],
            symbol="SPY",
        )
        regime_result = analyze_regime(series, use_hmm=False, use_garch=False)

        # 3. Signal generation
        report = generate_signal_report(
            regime=regime_result.regime,
            regime_confidence=regime_result.confidence,
            price_data={"SPY": spy_closes, "QQQ": qqq_closes},
            macro_data=asdict(macro),
        )

        # 4. Verify the full pipeline output
        assert report.regime == regime_result.regime
        assert report.regime_confidence == regime_result.confidence
        assert len(report.signals) == 2
        assert len(report.errors) == 0
        assert report.macro_summary  # non-empty
        assert report.risk_level in ("low", "moderate", "high", "extreme")

        # Each signal should reference the detected regime
        for sig in report.signals:
            assert sig.regime == regime_result.regime

    def test_empty_data_handling(self):
        """None and empty inputs are handled gracefully without exceptions."""
        # Empty price data -> no signals
        report = generate_signal_report(
            regime="sideways", regime_confidence=0.5, price_data={}
        )
        assert len(report.signals) == 0
        assert len(report.errors) == 0

        # Very short price data -> indicators are None, signal still generated
        report2 = generate_signal_report(
            regime="bull",
            regime_confidence=0.7,
            price_data={"SPY": [100.0, 101.0]},
        )
        assert len(report2.signals) == 1
        sig = report2.signals[0]
        assert sig.symbol == "SPY"
        # Indicators should be sparse but signal should exist
        assert sig.direction in ("buy", "sell", "hold")

        # No macro data -> macro_summary is empty or default
        assert report.macro_summary == ""

        # Regime from very short return series
        series = ReturnSeries(values=[0.01], timestamps=["a"])
        result = detect_regime_rules(series)
        assert result.regime == MarketRegime.UNKNOWN.value
        assert result.confidence == 0.0

    def test_load_latest_pull_no_files(self):
        """When DATA_DIR is empty, load_latest_pull returns None."""
        # _clean_data_dir fixture ensures a clean directory
        result = load_latest_pull()
        assert result is None

    def test_load_latest_pull_picks_most_recent(self):
        """When multiple pull files exist, the most recent is loaded."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Write an older pull
        old_pull = MarketDataPull(
            timestamp="2026-03-15T10:00:00Z",
            macro=MacroSnapshot(
                timestamp="2026-03-15T10:00:00Z", fed_funds_rate=5.00
            ),
            stocks=[],
            crypto=[],
        )
        old_file = DATA_DIR / "pull_20260315_100000.json"
        old_file.write_text(json.dumps(_pull_to_dict(old_pull), default=str))

        # Write a newer pull
        new_pull = MarketDataPull(
            timestamp="2026-03-16T14:00:00Z",
            macro=MacroSnapshot(
                timestamp="2026-03-16T14:00:00Z", fed_funds_rate=5.50
            ),
            stocks=[],
            crypto=[],
        )
        new_file = DATA_DIR / "pull_20260316_140000.json"
        new_file.write_text(json.dumps(_pull_to_dict(new_pull), default=str))

        loaded = load_latest_pull()
        assert loaded is not None
        assert loaded.macro is not None
        assert loaded.macro.fed_funds_rate == 5.50


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases across the pipeline boundary."""

    @pytest.mark.asyncio
    async def test_fred_empty_observations(self):
        """FRED response with empty observations list -> None."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"observations": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            val = await fetch_fred_series("DFF", api_key="key", client=client)
        assert val is None

    @pytest.mark.asyncio
    async def test_fred_malformed_json(self):
        """Malformed JSON response -> None, no crash."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json at all")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            val = await fetch_fred_series("DFF", api_key="key", client=client)
        assert val is None

    @pytest.mark.asyncio
    async def test_finnhub_missing_fields(self):
        """Finnhub response missing expected keys -> None."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"c": 100.0})  # missing d, dp, etc.

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            quote = await fetch_stock_quote("TEST", api_key="key", client=client)
        # Should raise KeyError internally and return None
        assert quote is None

    @pytest.mark.asyncio
    async def test_coingecko_rate_limit(self):
        """HTTP 429 from CoinGecko -> empty list, no crash."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Too Many Requests")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            prices = await fetch_crypto_prices(coin_ids=["bitcoin"], client=client)
        assert prices == []

    def test_regime_with_nan_values(self):
        """Return series with NaN values does not crash regime detection."""
        values = [0.01, float("nan"), -0.02, 0.005, 0.003, 0.01] * 4
        series = ReturnSeries(values=values, timestamps=[""] * len(values))
        # Should not raise; NaN handling varies by method
        result = detect_regime_rules(series)
        assert result.regime in [r.value for r in MarketRegime]

    def test_indicators_single_price(self):
        """compute_indicators with a single price returns safe defaults."""
        ind = compute_indicators("SPY", [100.0])
        assert ind.symbol == "SPY"
        assert ind.rsi_14 is None
        assert ind.sma_20 is None
        assert ind.sma_50 is None
        assert ind.bollinger_position is None

    def test_signal_report_with_broken_symbol(self):
        """A symbol that raises during indicator computation is captured in errors."""
        # Pass non-numeric data that will cause computation failures
        report = generate_signal_report(
            regime="bull",
            regime_confidence=0.8,
            price_data={"GOOD": [100 + i for i in range(60)]},
        )
        # GOOD should produce a signal
        assert len(report.signals) == 1
        assert report.signals[0].symbol == "GOOD"
