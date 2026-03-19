"""Algedonic Channel -- Emergency Bypass to S5.

Beer's VSM prescribes a dedicated pain/pleasure channel that bypasses
all normal routing when critical thresholds are crossed. This module
implements that channel for dharma_swarm.

Triggers: error rate spike, resource depletion, security event, coherence collapse.
Response: signal goes DIRECTLY to S5 (and to Dhyana via file notification),
bypassing all normal routing.
Timeout: if not acknowledged in 5 min, auto-enter safe mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


def _coerce_finite_cost(value: object) -> float | None:
    """Return a finite numeric cost or None for malformed ledger values."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class AlgedonicSignal(BaseModel):
    """A single algedonic signal -- pain or pleasure bypassing normal routing.

    Attributes:
        id: Unique signal identifier.
        timestamp: UTC time the signal was emitted.
        severity: Signal severity level.
        trigger: Human-readable description of what caused the signal.
        category: Classification of the signal source.
        message: Detailed description of the condition.
        acknowledged: Whether Dhyana (or an automated handler) has ack'd.
        acknowledged_at: UTC time of acknowledgement, if any.
        auto_safe_mode: Set to True if the signal triggered safe mode
            due to acknowledgement timeout.
    """

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    severity: Literal["critical", "warning", "info"] = "critical"
    trigger: str
    category: Literal[
        "error_spike",
        "resource_depletion",
        "security_event",
        "coherence_collapse",
        "external",
    ]
    message: str
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    auto_safe_mode: bool = False


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------

_DEFAULT_STATE_DIR = Path.home() / ".dharma" / "algedonic"


class AlgedonicChannel:
    """Emergency bypass channel from any subsystem to S5 (identity) and Dhyana.

    Signals are persisted as append-only JSONL.  Critical signals also write
    a human-visible marker file at ``~/.dharma/.ALGEDONIC_ALERT``.  If a
    critical signal is not acknowledged within ``timeout_minutes``, the
    channel writes ``~/.dharma/.SAFE_MODE`` to instruct the system to
    reduce autonomy.

    Args:
        state_dir: Directory for signal storage.  Defaults to
            ``~/.dharma/algedonic/``.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or _DEFAULT_STATE_DIR
        self._dharma_dir = self._state_dir.parent  # ~/.dharma
        self._signals_path = self._state_dir / "signals.jsonl"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    # -- emit ----------------------------------------------------------------

    async def emit(
        self,
        trigger: str,
        category: str,
        message: str,
        severity: str = "critical",
    ) -> AlgedonicSignal:
        """Create and persist an algedonic signal.

        For critical signals, also writes ``~/.dharma/.ALGEDONIC_ALERT``
        as a human-visible marker that something needs immediate attention.

        Args:
            trigger: Short label for what fired (e.g. ``"error_rate > 0.5"``).
            category: One of the ``AlgedonicSignal.category`` literals.
            message: Detailed description of the condition.
            severity: ``"critical"``, ``"warning"``, or ``"info"``.

        Returns:
            The persisted ``AlgedonicSignal``.
        """
        signal = AlgedonicSignal(
            trigger=trigger,
            category=category,  # type: ignore[arg-type]
            message=message,
            severity=severity,  # type: ignore[arg-type]
        )
        await asyncio.to_thread(self._append_signal, signal)

        if severity == "critical":
            await asyncio.to_thread(self._write_alert_marker, signal)

        logger.warning(
            "ALGEDONIC [%s] %s: %s -- %s",
            signal.severity.upper(),
            signal.category,
            signal.trigger,
            signal.message,
        )
        return signal

    # -- check ---------------------------------------------------------------

    async def check_unacknowledged(
        self, timeout_minutes: int = 5
    ) -> list[AlgedonicSignal]:
        """Return signals that have not been acknowledged within timeout.

        If any **critical** signal exceeds the timeout, writes
        ``~/.dharma/.SAFE_MODE`` and sets ``auto_safe_mode=True`` on
        those signals.

        Args:
            timeout_minutes: Minutes before an unacknowledged signal is
                considered timed-out.

        Returns:
            List of timed-out signals (may be empty).
        """
        all_signals = await asyncio.to_thread(self._load_all_signals)
        now = _utc_now()
        timed_out: list[AlgedonicSignal] = []

        for sig in all_signals:
            if sig.acknowledged:
                continue
            age_minutes = (now - sig.timestamp).total_seconds() / 60.0
            if age_minutes > timeout_minutes:
                timed_out.append(sig)

        # Auto safe-mode for critical timeouts
        critical_timeout = [s for s in timed_out if s.severity == "critical"]
        if critical_timeout:
            safe_mode_path = self._dharma_dir / ".SAFE_MODE"
            reasons = [f"[{s.id}] {s.trigger}" for s in critical_timeout]
            content = (
                f"# SAFE MODE -- unacknowledged critical algedonic signals\n"
                f"Entered: {now.isoformat()}\n\n"
                + "\n".join(reasons)
                + "\n"
            )
            await asyncio.to_thread(safe_mode_path.write_text, content)
            logger.critical(
                "SAFE MODE entered: %d critical signal(s) unacknowledged past %d min",
                len(critical_timeout),
                timeout_minutes,
            )

            # Update the signals in storage
            for sig in critical_timeout:
                sig.auto_safe_mode = True
            await asyncio.to_thread(
                self._rewrite_signals,
                {s.id: s for s in critical_timeout},
            )

        return timed_out

    # -- acknowledge ---------------------------------------------------------

    async def acknowledge(self, signal_id: str) -> bool:
        """Mark a signal as acknowledged.

        If no more unacknowledged critical signals remain after this,
        removes the ``~/.dharma/.ALGEDONIC_ALERT`` marker.

        Args:
            signal_id: The ``id`` of the signal to acknowledge.

        Returns:
            ``True`` if the signal was found and acknowledged; ``False``
            if not found.
        """
        all_signals = await asyncio.to_thread(self._load_all_signals)
        target: AlgedonicSignal | None = None
        for sig in all_signals:
            if sig.id == signal_id:
                sig.acknowledged = True
                sig.acknowledged_at = _utc_now()
                target = sig
                break

        if target is None:
            return False

        await asyncio.to_thread(
            self._rewrite_signals, {signal_id: target}
        )

        # Remove alert marker if no more unacknowledged critical signals
        unacked_critical = [
            s
            for s in all_signals
            if not s.acknowledged and s.severity == "critical"
        ]
        if not unacked_critical:
            alert_path = self._dharma_dir / ".ALGEDONIC_ALERT"
            if alert_path.exists():
                await asyncio.to_thread(alert_path.unlink)
                logger.info("Removed .ALGEDONIC_ALERT -- no unacked critical signals")

        return True

    # -- recent --------------------------------------------------------------

    async def recent(self, limit: int = 10) -> list[AlgedonicSignal]:
        """Return the most recent signals, newest first.

        Args:
            limit: Maximum number of signals to return.

        Returns:
            List of ``AlgedonicSignal`` instances sorted by timestamp
            descending.
        """
        all_signals = await asyncio.to_thread(self._load_all_signals)
        all_signals.sort(key=lambda s: s.timestamp, reverse=True)
        return all_signals[:limit]

    # -- active_alerts -------------------------------------------------------

    @property
    def active_alerts(self) -> list[AlgedonicSignal]:
        """Return unacknowledged signals (synchronous).

        Reads from disk synchronously -- suitable for quick status checks
        but prefer :meth:`recent` in async contexts.
        """
        all_signals = self._load_all_signals()
        return [s for s in all_signals if not s.acknowledged]

    # -- private persistence -------------------------------------------------

    def _append_signal(self, signal: AlgedonicSignal) -> None:
        """Append a single signal to the JSONL file."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with self._signals_path.open("a", encoding="utf-8") as fh:
            fh.write(signal.model_dump_json() + "\n")

    def _load_all_signals(self) -> list[AlgedonicSignal]:
        """Load all signals from JSONL (synchronous)."""
        if not self._signals_path.exists():
            return []
        signals: list[AlgedonicSignal] = []
        try:
            for line in self._signals_path.read_text(encoding="utf-8").strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    signals.append(AlgedonicSignal.model_validate_json(line))
                except Exception:
                    logger.debug("Skipping malformed algedonic line: %s", line[:80])
        except Exception as exc:
            logger.warning("Failed to load algedonic signals: %s", exc)
        return signals

    def _rewrite_signals(self, updates: dict[str, AlgedonicSignal]) -> None:
        """Rewrite the JSONL file, applying updates to matching signal ids.

        This is the only operation that mutates existing entries.  It reads
        the full file, patches matching entries, and writes back atomically.
        """
        all_signals = self._load_all_signals()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._signals_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                for sig in all_signals:
                    if sig.id in updates:
                        fh.write(updates[sig.id].model_dump_json() + "\n")
                    else:
                        fh.write(sig.model_dump_json() + "\n")
            tmp_path.replace(self._signals_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def _write_alert_marker(self, signal: AlgedonicSignal) -> None:
        """Write the human-visible .ALGEDONIC_ALERT file."""
        self._dharma_dir.mkdir(parents=True, exist_ok=True)
        alert_path = self._dharma_dir / ".ALGEDONIC_ALERT"
        content = (
            f"# ALGEDONIC ALERT -- CRITICAL\n"
            f"Signal: {signal.id}\n"
            f"Time: {signal.timestamp.isoformat()}\n"
            f"Trigger: {signal.trigger}\n"
            f"Category: {signal.category}\n"
            f"Message: {signal.message}\n\n"
            f"Acknowledge via: dgc algedonic ack {signal.id}\n"
        )
        alert_path.write_text(content)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


async def detect_error_spike(
    threshold: float = 0.5,
    state_dir: Path | None = None,
) -> AlgedonicSignal | None:
    """Check recent session actions for error rate exceeding *threshold*.

    Reads the last 10 entries from
    ``~/.dharma/loops/session_actions.jsonl`` and counts those with
    ``"status": "error"`` or ``"status": "failed"``.

    Args:
        threshold: Error fraction (0.0-1.0) that triggers the signal.
        state_dir: Override ``.dharma`` root.

    Returns:
        An ``AlgedonicSignal`` if the error rate exceeds *threshold*,
        otherwise ``None``.
    """
    dharma_dir = state_dir or (Path.home() / ".dharma")
    actions_path = dharma_dir / "loops" / "session_actions.jsonl"
    if not actions_path.exists():
        return None

    def _check() -> tuple[int, int]:
        lines: list[str] = []
        try:
            raw = actions_path.read_text(encoding="utf-8").strip()
            if raw:
                lines = raw.split("\n")
        except Exception:
            return 0, 0

        # Take last 10 actions
        recent = lines[-10:]
        total = 0
        errors = 0
        for line in recent:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                total += 1
                status = str(entry.get("status", "")).lower()
                if status in ("error", "failed"):
                    errors += 1
            except json.JSONDecodeError:
                continue
        return total, errors

    total, errors = await asyncio.to_thread(_check)
    if total == 0:
        return None

    rate = errors / total
    if rate <= threshold:
        return None

    channel = AlgedonicChannel(
        state_dir=dharma_dir / "algedonic"
    )
    return await channel.emit(
        trigger=f"error_rate={rate:.2f} > {threshold:.2f} (last {total} actions)",
        category="error_spike",
        message=(
            f"{errors}/{total} recent session actions failed. "
            f"Error rate {rate:.0%} exceeds threshold {threshold:.0%}."
        ),
        severity="critical" if rate > 0.8 else "warning",
    )


async def detect_coherence_collapse(
    threshold: float = 0.25,
    state_dir: Path | None = None,
) -> AlgedonicSignal | None:
    """Check identity history for TCS below *threshold*.

    Reads the most recent entry from
    ``~/.dharma/meta/identity_history.jsonl`` and checks its ``tcs``
    field.

    Args:
        threshold: TCS value below which coherence is considered collapsed.
        state_dir: Override ``.dharma`` root.

    Returns:
        An ``AlgedonicSignal`` if the most recent TCS < *threshold*,
        otherwise ``None``.
    """
    dharma_dir = state_dir or (Path.home() / ".dharma")
    history_path = dharma_dir / "meta" / "identity_history.jsonl"
    if not history_path.exists():
        return None

    def _check() -> float | None:
        try:
            raw = history_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            lines = raw.split("\n")
            # Most recent entry is the last line
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    return float(entry.get("tcs", 1.0))
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        except Exception:
            return None
        return None

    tcs = await asyncio.to_thread(_check)
    if tcs is None:
        return None

    if tcs >= threshold:
        return None

    channel = AlgedonicChannel(
        state_dir=dharma_dir / "algedonic"
    )
    return await channel.emit(
        trigger=f"TCS={tcs:.3f} < {threshold:.3f}",
        category="coherence_collapse",
        message=(
            f"Telos Coherence Score has dropped to {tcs:.3f}, "
            f"below the critical threshold of {threshold:.3f}. "
            f"S5 identity is destabilizing."
        ),
        severity="critical",
    )


async def detect_resource_depletion(
    daily_limit: float = 12.0,
    state_dir: Path | None = None,
) -> AlgedonicSignal | None:
    """Check daily cost ledger for spend exceeding *daily_limit*.

    Reads ``~/.dharma/costs/daily_ledger.jsonl`` and sums supported cost
    fields (``cost``, ``cost_usd``, ``estimated_cost_usd``) for entries
    whose ``date`` matches today (UTC).

    Args:
        daily_limit: Maximum daily spend in USD before triggering.
        state_dir: Override ``.dharma`` root.

    Returns:
        An ``AlgedonicSignal`` if today's spend exceeds *daily_limit*,
        otherwise ``None``.
    """
    dharma_dir = state_dir or (Path.home() / ".dharma")
    ledger_path = dharma_dir / "costs" / "daily_ledger.jsonl"
    if not ledger_path.exists():
        return None

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check() -> float:
        total = 0.0
        try:
            raw = ledger_path.read_text(encoding="utf-8").strip()
            if not raw:
                return 0.0
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_date = str(entry.get("date", ""))
                    # Handle both "date" field and "timestamp" field
                    if not entry_date:
                        ts = str(entry.get("timestamp", ""))
                        entry_date = ts[:10] if len(ts) >= 10 else ""
                    if entry_date == today_str:
                        amount = None
                        for key in ("cost", "cost_usd", "estimated_cost_usd"):
                            amount = _coerce_finite_cost(entry.get(key))
                            if amount is not None:
                                break
                        if amount is not None:
                            total += amount
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        except Exception:
            return 0.0
        return total

    today_spend = await asyncio.to_thread(_check)
    if today_spend <= daily_limit:
        return None

    channel = AlgedonicChannel(
        state_dir=dharma_dir / "algedonic"
    )
    return await channel.emit(
        trigger=f"daily_spend=${today_spend:.2f} > ${daily_limit:.2f}",
        category="resource_depletion",
        message=(
            f"Today's API spend has reached ${today_spend:.2f}, "
            f"exceeding the ${daily_limit:.2f} daily limit. "
            f"Consider throttling agent dispatch."
        ),
        severity="critical" if today_spend > daily_limit * 1.5 else "warning",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_detectors(
    state_dir: Path | None = None,
) -> list[AlgedonicSignal]:
    """Run all detectors and return any signals emitted.

    This is the main entry point for periodic algedonic scanning.
    Call from the living layers loop or a dedicated cron.

    Args:
        state_dir: Override ``.dharma`` root (passed through to each detector).

    Returns:
        List of ``AlgedonicSignal`` instances for any triggered conditions.
        Empty list means all clear.
    """
    results = await asyncio.gather(
        detect_error_spike(state_dir=state_dir),
        detect_coherence_collapse(state_dir=state_dir),
        detect_resource_depletion(state_dir=state_dir),
        return_exceptions=True,
    )

    signals: list[AlgedonicSignal] = []
    for result in results:
        if isinstance(result, AlgedonicSignal):
            signals.append(result)
        elif isinstance(result, Exception):
            logger.error("Algedonic detector failed: %s", result)

    if signals:
        logger.warning(
            "Algedonic scan: %d signal(s) emitted (%s)",
            len(signals),
            ", ".join(s.category for s in signals),
        )
    else:
        logger.debug("Algedonic scan: all clear")

    return signals
