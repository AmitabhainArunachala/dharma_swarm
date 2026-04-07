"""Tests for ginko_bridge.py — Ginko trading bridge + tool integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.ginko_bridge import (
    format_signals,
    ginko_get_brier_scores,
    ginko_get_regime,
    ginko_get_signals,
)
from dharma_swarm.autonomous_agent import (
    TOOL_DEFINITIONS,
    AgentIdentity,
    AutonomousAgent,
    PRESET_AGENTS,
)


# ---------------------------------------------------------------------------
# ginko_get_signals — returns dict with required keys even when Ginko absent
# ---------------------------------------------------------------------------


class TestGinkoGetSignals:
    """ginko_get_signals returns a well-formed dict even without Ginko installed."""

    @pytest.mark.asyncio
    async def test_fallback_returns_dict(self):
        """When Ginko is not installed, returns a dict with required keys."""
        result = await ginko_get_signals(symbol="BTC", lookback_days=7)
        assert isinstance(result, dict)
        assert "regime" in result or "error" in result
        assert "_source" in result

    @pytest.mark.asyncio
    async def test_fallback_contains_symbol(self):
        """Fallback dict contains the requested symbol."""
        result = await ginko_get_signals(symbol="ETH")
        # Either the symbol is returned directly, or it's in an error fallback
        if result.get("_source") == "fallback":
            assert result["symbol"] == "ETH"

    @pytest.mark.asyncio
    async def test_fallback_source_is_set(self):
        """The _source field is always set in the fallback case."""
        result = await ginko_get_signals()
        assert result.get("_source") in ("fallback", "cached", "error", "timeout")

    @pytest.mark.asyncio
    async def test_custom_lookback(self):
        """Different lookback_days values do not crash."""
        result = await ginko_get_signals(symbol="SPY", lookback_days=30)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# ginko_get_regime — returns a string (never crashes)
# ---------------------------------------------------------------------------


class TestGinkoGetRegime:
    """ginko_get_regime returns a string always."""

    @pytest.mark.asyncio
    async def test_returns_string(self):
        regime = await ginko_get_regime(symbol="BTC")
        assert isinstance(regime, str)

    @pytest.mark.asyncio
    async def test_returns_unknown_when_unavailable(self):
        """When Ginko is not installed, regime should be 'unknown'."""
        regime = await ginko_get_regime()
        assert regime == "unknown"

    @pytest.mark.asyncio
    async def test_different_symbols(self):
        """Different symbols don't crash."""
        for sym in ("BTC", "ETH", "SPY"):
            regime = await ginko_get_regime(symbol=sym)
            assert isinstance(regime, str)


# ---------------------------------------------------------------------------
# ginko_get_brier_scores — graceful when missing
# ---------------------------------------------------------------------------


class TestGinkoBrierScores:
    @pytest.mark.asyncio
    async def test_returns_dict(self):
        result = await ginko_get_brier_scores()
        assert isinstance(result, dict)
        assert "scores" in result or "error" in result


# ---------------------------------------------------------------------------
# format_signals — handles missing/malformed data gracefully
# ---------------------------------------------------------------------------


class TestFormatSignals:
    def test_error_signal(self):
        signals = {"error": "Ginko not available", "regime": "unknown"}
        output = format_signals(signals)
        assert "unavailable" in output.lower() or "not available" in output.lower()

    def test_normal_signals(self):
        signals = {
            "symbol": "BTC",
            "regime": "bull",
            "signals": [
                {"name": "RSI", "value": 72, "direction": "up"},
                {"name": "MACD", "value": 0.5, "direction": "up"},
            ],
        }
        output = format_signals(signals)
        assert "BTC" in output
        assert "bull" in output
        assert "RSI" in output
        assert "MACD" in output

    def test_empty_signals_list(self):
        signals = {"symbol": "ETH", "regime": "neutral", "signals": []}
        output = format_signals(signals)
        assert "ETH" in output
        assert "neutral" in output

    def test_missing_fields(self):
        """format_signals doesn't crash on minimal dict."""
        output = format_signals({})
        # Should have defaults for symbol and regime
        assert isinstance(output, str)

    def test_signal_missing_keys(self):
        """Signals with missing sub-keys use '?' fallback."""
        signals = {
            "symbol": "BTC",
            "regime": "bear",
            "signals": [{"name": "RSI"}],  # missing value and direction
        }
        output = format_signals(signals)
        assert "?" in output


# ---------------------------------------------------------------------------
# Tool definitions are present in TOOL_DEFINITIONS
# ---------------------------------------------------------------------------


class TestToolDefinitionsPresence:
    def test_ginko_signals_in_definitions(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert "ginko_signals" in names

    def test_ginko_regime_in_definitions(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert "ginko_regime" in names

    def test_ginko_signals_has_input_schema(self):
        tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "ginko_signals")
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "symbol" in tool["input_schema"]["properties"]

    def test_ginko_regime_has_input_schema(self):
        tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "ginko_regime")
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "symbol" in tool["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# _tool_ginko_signals / _tool_ginko_regime handlers exist in AutonomousAgent
# ---------------------------------------------------------------------------


class TestToolHandlersExist:
    def _make_agent(self) -> AutonomousAgent:
        ident = AgentIdentity(
            name="test", role="test", system_prompt="test",
        )
        return AutonomousAgent(ident)

    def test_ginko_signals_handler_exists(self):
        agent = self._make_agent()
        assert hasattr(agent, "_tool_ginko_signals")
        assert callable(agent._tool_ginko_signals)

    def test_ginko_regime_handler_exists(self):
        agent = self._make_agent()
        assert hasattr(agent, "_tool_ginko_regime")
        assert callable(agent._tool_ginko_regime)

    @pytest.mark.asyncio
    async def test_ginko_signals_handler_runs(self):
        agent = self._make_agent()
        result = await agent._tool_ginko_signals({"symbol": "BTC"})
        assert isinstance(result, str)
        # Should contain either signal data or an unavailability message
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_ginko_regime_handler_runs(self):
        agent = self._make_agent()
        result = await agent._tool_ginko_regime({"symbol": "BTC"})
        assert isinstance(result, str)
        assert "BTC" in result

    def test_ginko_tools_in_default_allowed(self):
        """Both tools are in the default AgentIdentity.allowed_tools."""
        ident = AgentIdentity(name="x", role="x", system_prompt="x")
        assert "ginko_signals" in ident.allowed_tools
        assert "ginko_regime" in ident.allowed_tools

    def test_ginko_tools_in_preset_agents(self):
        """All preset agents have ginko tools in allowed_tools."""
        for name, ident in PRESET_AGENTS.items():
            assert "ginko_signals" in ident.allowed_tools, (
                f"ginko_signals missing from preset agent '{name}'"
            )
            assert "ginko_regime" in ident.allowed_tools, (
                f"ginko_regime missing from preset agent '{name}'"
            )

    @pytest.mark.asyncio
    async def test_execute_tool_dispatches_ginko_signals(self):
        """_execute_tool correctly routes ginko_signals to handler."""
        agent = self._make_agent()
        result = await agent._execute_tool("ginko_signals", {"symbol": "BTC"})
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_execute_tool_dispatches_ginko_regime(self):
        """_execute_tool correctly routes ginko_regime to handler."""
        agent = self._make_agent()
        result = await agent._execute_tool("ginko_regime", {"symbol": "ETH"})
        assert isinstance(result, str)
        assert "ETH" in result
