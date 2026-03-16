"""Tests for Ginko data layer."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_data import (
    CryptoPrice,
    MacroSnapshot,
    MarketDataPull,
    StockQuote,
    load_latest_pull,
    _pull_to_dict,
    DATA_DIR,
)


class TestDataModels:
    def test_macro_snapshot(self):
        snap = MacroSnapshot(
            timestamp="2026-03-16T00:00:00Z",
            fed_funds_rate=5.25,
            ten_year_yield=4.5,
            yield_spread=0.3,
            vix=16.5,
        )
        assert snap.fed_funds_rate == 5.25
        assert snap.vix == 16.5

    def test_stock_quote(self):
        quote = StockQuote(
            symbol="AAPL",
            current_price=175.50,
            change=2.30,
            percent_change=1.33,
            high=176.00,
            low=173.00,
            open_price=173.50,
            previous_close=173.20,
            timestamp="2026-03-16T00:00:00Z",
        )
        assert quote.symbol == "AAPL"
        assert quote.current_price == 175.50

    def test_crypto_price(self):
        price = CryptoPrice(
            coin_id="bitcoin",
            symbol="btc",
            current_price_usd=65000.0,
            market_cap=1200000000000,
            volume_24h=30000000000,
            price_change_24h_pct=2.5,
            timestamp="2026-03-16T00:00:00Z",
        )
        assert price.coin_id == "bitcoin"
        assert price.current_price_usd == 65000.0

    def test_market_data_pull(self):
        pull = MarketDataPull(
            timestamp="2026-03-16T00:00:00Z",
            macro=MacroSnapshot(timestamp="2026-03-16T00:00:00Z"),
            stocks=[
                StockQuote(
                    symbol="SPY", current_price=500, change=1, percent_change=0.2,
                    high=501, low=499, open_price=499, previous_close=499,
                    timestamp="2026-03-16T00:00:00Z",
                )
            ],
            crypto=[],
            errors=[],
        )
        assert len(pull.stocks) == 1
        assert pull.macro is not None


class TestPullToDict:
    def test_serialization(self):
        pull = MarketDataPull(
            timestamp="2026-03-16T00:00:00Z",
            macro=MacroSnapshot(timestamp="2026-03-16T00:00:00Z", vix=16.5),
            stocks=[],
            crypto=[],
        )
        d = _pull_to_dict(pull)
        assert d["macro"]["vix"] == 16.5
        assert isinstance(d["stocks"], list)

    def test_null_macro(self):
        pull = MarketDataPull(timestamp="2026-03-16T00:00:00Z")
        d = _pull_to_dict(pull)
        assert d["macro"] is None


class TestLoadLatestPull:
    def test_no_files(self):
        """No data files → None."""
        assert load_latest_pull() is None

    def test_load_saved_pull(self):
        """Save then load a pull."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pull = MarketDataPull(
            timestamp="2026-03-16T12:00:00Z",
            macro=MacroSnapshot(
                timestamp="2026-03-16T12:00:00Z",
                fed_funds_rate=5.25,
            ),
            stocks=[
                StockQuote(
                    symbol="SPY", current_price=500, change=1,
                    percent_change=0.2, high=501, low=499,
                    open_price=499, previous_close=499,
                    timestamp="2026-03-16T12:00:00Z",
                )
            ],
            crypto=[],
            errors=[],
        )
        # Write it
        f = DATA_DIR / "pull_20260316_120000.json"
        f.write_text(json.dumps(_pull_to_dict(pull), default=str))

        loaded = load_latest_pull()
        assert loaded is not None
        assert loaded.macro is not None
        assert loaded.macro.fed_funds_rate == 5.25
        assert len(loaded.stocks) == 1
        assert loaded.stocks[0].symbol == "SPY"

        # Cleanup
        f.unlink()


class TestFREDSeries:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Without API key, should return None and not crash."""
        from dharma_swarm.ginko_data import fetch_fred_series

        old_key = os.environ.pop("FRED_API_KEY", None)
        try:
            result = await fetch_fred_series("DFF")
            assert result is None
        finally:
            if old_key:
                os.environ["FRED_API_KEY"] = old_key


class TestFinnhub:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Without API key, should return None and not crash."""
        from dharma_swarm.ginko_data import fetch_stock_quote

        old_key = os.environ.pop("FINNHUB_API_KEY", None)
        try:
            result = await fetch_stock_quote("AAPL")
            assert result is None
        finally:
            if old_key:
                os.environ["FINNHUB_API_KEY"] = old_key
