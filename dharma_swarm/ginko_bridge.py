"""Ginko Trading Bridge — connects DHARMA SWARM to Ginko trading signals.

This closes the metabolic loop: the organism's intelligence feeds its
trading system, and trading results flow back as economic signals.

Usage in agents via tools:
    ginko_signals  — get current market signals from Ginko
    ginko_regime   — get current market regime classification
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GINKO_ROOT = Path.home() / "ginko-trading"
_GINKO_SIGNAL_FILE = Path.home() / ".dharma" / "shared" / "ginko_signals.json"


async def ginko_get_signals(symbol: str = "BTC", lookback_days: int = 7) -> dict[str, Any]:
    """Get current Ginko market signals for a symbol.
    
    Falls back gracefully if Ginko is not installed.
    """
    try:
        # Try running Ginko signal generation
        if (_GINKO_ROOT / "ginko" / "signals.py").exists():
            proc = await asyncio.create_subprocess_exec(
                "python3", "-m", "ginko.signals",
                "--symbol", symbol,
                "--lookback", str(lookback_days),
                "--format", "json",
                cwd=str(_GINKO_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            return json.loads(stdout.decode())
        
        # Fallback: read cached signal file if it exists
        if _GINKO_SIGNAL_FILE.exists():
            data = json.loads(_GINKO_SIGNAL_FILE.read_text())
            data['_source'] = 'cached'
            return data
        
        return {
            "symbol": symbol,
            "regime": "unknown",
            "signals": [],
            "error": "Ginko not available — run from ginko-trading repo",
            "_source": "fallback",
        }
    except asyncio.TimeoutError:
        return {"error": "Ginko timed out", "regime": "unknown", "_source": "timeout"}
    except Exception as exc:
        logger.debug("Ginko bridge failed: %s", exc)
        return {"error": str(exc), "regime": "unknown", "_source": "error"}


async def ginko_get_regime(symbol: str = "BTC") -> str:
    """Get current market regime from Ginko (bull/bear/neutral/unknown)."""
    signals = await ginko_get_signals(symbol=symbol, lookback_days=30)
    return signals.get("regime", "unknown")


async def ginko_get_brier_scores() -> dict[str, Any]:
    """Get Ginko's Brier score track record (signal quality measure)."""
    try:
        brier_file = _GINKO_ROOT / "data" / "brier_scores.json"
        if brier_file.exists():
            return json.loads(brier_file.read_text())
        return {"error": "No Brier scores available yet", "scores": []}
    except Exception as exc:
        return {"error": str(exc), "scores": []}


def format_signals(signals: dict[str, Any]) -> str:
    """Format Ginko signals for agent consumption."""
    if signals.get("error"):
        return f"Ginko unavailable: {signals['error']}"
    
    regime = signals.get("regime", "unknown")
    symbol = signals.get("symbol", "?")
    lines = [f"## Ginko Market Signals: {symbol}", f"**Regime:** {regime}"]
    
    for sig in signals.get("signals", []):
        lines.append(f"- {sig.get('name', '?')}: {sig.get('value', '?')} ({sig.get('direction', '?')})")
    
    return "\n".join(lines)
