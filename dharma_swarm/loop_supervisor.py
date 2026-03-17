"""Loop Supervisor — autonomous watchdog for orchestrate_live loops.

Detects stalls, retry storms, and eval degradation without human monitoring.
Pure Python — no LLM calls.  Cheap enough to call at the top of every swarm tick.

Intervention ladder: LOG_WARNING → PAUSE_LOOP → REDUCE_SCOPE → ALERT_DHYANA
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
ALERT_FILE = STATE_DIR / "shared" / "loop_alert.md"
SUPERVISOR_STATE = STATE_DIR / "loop_supervisor"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LoopHealth:
    """Health status of a single loop."""
    name: str
    last_tick: float = 0.0          # monotonic timestamp of last tick
    expected_interval: float = 60.0  # seconds between ticks
    tick_count: int = 0
    error_count: int = 0
    last_errors: list[str] = field(default_factory=list)  # last 5 errors

    @property
    def stale_seconds(self) -> float:
        if self.last_tick == 0:
            return 0.0
        return time.monotonic() - self.last_tick

    @property
    def is_stalled(self) -> bool:
        if self.last_tick == 0:
            return False  # Never ticked = not started yet
        return self.stale_seconds > (2 * self.expected_interval)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stale_seconds"] = round(self.stale_seconds, 1)
        d["is_stalled"] = self.is_stalled
        return d


@dataclass
class SupervisorAlert:
    """An alert raised by the supervisor."""
    alert_type: str       # LOOP_STALL, RETRY_STORM, EVAL_REGRESSION
    loop_name: str
    severity: str         # warning, critical
    message: str
    intervention: str     # LOG_WARNING, PAUSE_LOOP, REDUCE_SCOPE, ALERT_DHYANA
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Intervention levels
# ---------------------------------------------------------------------------

INTERVENTIONS = [
    "LOG_WARNING",     # Just log it
    "PAUSE_LOOP",      # Suggest loop pause
    "REDUCE_SCOPE",    # Reduce work per tick
    "ALERT_DHYANA",    # Write alert file for human attention
]


def _escalation_level(error_count: int, stale_factor: float) -> str:
    """Determine intervention level based on severity indicators."""
    if stale_factor > 5.0 or error_count > 10:
        return "ALERT_DHYANA"
    if stale_factor > 3.0 or error_count > 5:
        return "REDUCE_SCOPE"
    if stale_factor > 2.0 or error_count > 3:
        return "PAUSE_LOOP"
    return "LOG_WARNING"


# ---------------------------------------------------------------------------
# Retry storm detection
# ---------------------------------------------------------------------------

@dataclass
class _ErrorWindow:
    """Sliding window for error tracking."""
    errors: list[tuple[float, str]] = field(default_factory=list)
    window_seconds: float = 300.0  # 5 minutes

    def add(self, error_msg: str) -> None:
        now = time.monotonic()
        self.errors.append((now, error_msg))
        # Prune old entries
        cutoff = now - self.window_seconds
        self.errors = [(t, m) for t, m in self.errors if t > cutoff]

    def is_storm(self, threshold: int = 3) -> bool:
        """True if same error repeated >= threshold times in window."""
        if len(self.errors) < threshold:
            return False
        # Group by error message
        counts: dict[str, int] = {}
        for _, msg in self.errors:
            key = msg[:100]  # Normalize
            counts[key] = counts.get(key, 0) + 1
        return any(c >= threshold for c in counts.values())


# ---------------------------------------------------------------------------
# LoopSupervisor
# ---------------------------------------------------------------------------

class LoopSupervisor:
    """Watchdog that monitors all orchestrate_live loops.

    Lightweight — call tick() at the top of the swarm loop.
    """

    def __init__(self) -> None:
        self._loops: dict[str, LoopHealth] = {}
        self._error_windows: dict[str, _ErrorWindow] = {}
        self._alerts: list[SupervisorAlert] = []
        self._last_eval_pass_rate: float | None = None

    def register_loop(self, name: str, expected_interval: float) -> None:
        """Register a loop to be monitored."""
        self._loops[name] = LoopHealth(
            name=name,
            expected_interval=expected_interval,
        )
        self._error_windows[name] = _ErrorWindow()

    def record_tick(self, loop_name: str) -> None:
        """Record that a loop has ticked (healthy heartbeat)."""
        if loop_name not in self._loops:
            return
        health = self._loops[loop_name]
        health.last_tick = time.monotonic()
        health.tick_count += 1

    def record_error(self, loop_name: str, error: str) -> None:
        """Record an error in a loop."""
        if loop_name not in self._loops:
            return
        health = self._loops[loop_name]
        health.error_count += 1
        health.last_errors = (health.last_errors + [error[:200]])[-5:]
        self._error_windows[loop_name].add(error)

    def tick(self) -> list[SupervisorAlert]:
        """Run all checks, return any new alerts.

        Call this at the top of the swarm loop — cheap pure-Python check.
        """
        alerts: list[SupervisorAlert] = []

        for name, health in self._loops.items():
            # Check stalls
            if health.is_stalled:
                stale_factor = health.stale_seconds / health.expected_interval
                intervention = _escalation_level(health.error_count, stale_factor)
                alert = SupervisorAlert(
                    alert_type="LOOP_STALL",
                    loop_name=name,
                    severity="critical" if intervention in ("REDUCE_SCOPE", "ALERT_DHYANA") else "warning",
                    message=f"Loop '{name}' stalled: {health.stale_seconds:.0f}s since last tick "
                            f"(expected every {health.expected_interval:.0f}s)",
                    intervention=intervention,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                alerts.append(alert)

            # Check retry storms
            ew = self._error_windows.get(name)
            if ew and ew.is_storm():
                alert = SupervisorAlert(
                    alert_type="RETRY_STORM",
                    loop_name=name,
                    severity="critical",
                    message=f"Retry storm in '{name}': {len(ew.errors)} errors in {ew.window_seconds}s",
                    intervention="PAUSE_LOOP",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                alerts.append(alert)

        # Check eval degradation
        eval_alert = self._check_eval_degradation()
        if eval_alert:
            alerts.append(eval_alert)

        # Persist alerts
        if alerts:
            self._alerts.extend(alerts)
            self._write_alert_file(alerts)

        return alerts

    def _check_eval_degradation(self) -> SupervisorAlert | None:
        """Check if eval pass rate dropped significantly."""
        try:
            from dharma_swarm.ecc_eval_harness import load_history
            history = load_history()
            if len(history) < 2:
                return None
            current = history[-1].get("pass_at_1", 0.0)
            previous = history[-2].get("pass_at_1", 0.0)

            if previous > 0 and (previous - current) / previous > 0.2:
                return SupervisorAlert(
                    alert_type="EVAL_REGRESSION",
                    loop_name="eval_harness",
                    severity="critical",
                    message=f"Eval regression: pass@1 dropped from {previous:.1%} to {current:.1%}",
                    intervention="ALERT_DHYANA",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except Exception:
            pass
        return None

    def _write_alert_file(self, alerts: list[SupervisorAlert]) -> None:
        """Write alerts to shared alert file for human/agent consumption."""
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Loop Supervisor Alert — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
        ]
        for a in alerts:
            lines.append(f"## [{a.severity.upper()}] {a.alert_type}")
            lines.append(f"- Loop: {a.loop_name}")
            lines.append(f"- Message: {a.message}")
            lines.append(f"- Intervention: {a.intervention}")
            lines.append("")

        ALERT_FILE.write_text("\n".join(lines))
        logger.warning("Loop supervisor: %d alerts written to %s", len(alerts), ALERT_FILE)

    def status(self) -> dict[str, Any]:
        """Return full supervisor status."""
        return {
            "loops": {name: h.to_dict() for name, h in self._loops.items()},
            "recent_alerts": [a.to_dict() for a in self._alerts[-10:]],
            "total_alerts": len(self._alerts),
        }

    def save_state(self) -> None:
        """Persist supervisor state to disk."""
        SUPERVISOR_STATE.mkdir(parents=True, exist_ok=True)
        state_file = SUPERVISOR_STATE / "state.json"
        state_file.write_text(json.dumps(self.status(), indent=2))

    @staticmethod
    def load_state() -> dict[str, Any] | None:
        """Load persisted supervisor state."""
        state_file = SUPERVISOR_STATE / "state.json"
        if state_file.exists():
            return json.loads(state_file.read_text())
        return None


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def cmd_loop_status() -> int:
    """Print loop health status."""
    state = LoopSupervisor.load_state()
    if not state:
        print("No loop supervisor state yet. Start the orchestrator to generate data.")
        return 0

    print("Loop Supervisor Status")
    print("=" * 55)

    loops = state.get("loops", {})
    for name, health in loops.items():
        stalled = "STALLED" if health.get("is_stalled") else "OK"
        stale = health.get("stale_seconds", 0)
        ticks = health.get("tick_count", 0)
        errors = health.get("error_count", 0)
        print(f"  {name:<20} {stalled:>8}  ticks={ticks}  errors={errors}  stale={stale:.0f}s")

    alerts = state.get("recent_alerts", [])
    if alerts:
        print(f"\nRecent Alerts ({len(alerts)}):")
        for a in alerts[-5:]:
            print(f"  [{a['severity'].upper()}] {a['alert_type']}: {a['message'][:60]}")

    return 0
