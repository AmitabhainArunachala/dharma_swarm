"""Behavioral monitoring for sandbox containers.

TRACKS, not BLOCKS. Every resource acquisition event is logged with full
provenance for stigmergy integration and telos gate evaluation.

Inspired by the ROME incident (arXiv:2512.24873) where Alibaba Cloud's
production firewall caught crypto mining and SSH tunneling that model-level
safety missed entirely. We apply the lesson: infrastructure monitoring
catches what model safety misses. But unlike ROME, we don't treat resource
acquisition as a bug — we track it as governed behavior.

Events feed into the stigmergy store as high-salience marks.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default path for monitor logs
_MONITOR_LOG_DIR = Path.home() / ".dharma" / "sandbox_monitor"


class EventSeverity(str, Enum):
    """Severity levels for monitored events."""
    INFO = "info"            # Normal operation
    NOTABLE = "notable"      # Worth tracking (e.g., network connection established)
    SIGNIFICANT = "significant"  # Resource acquisition detected (e.g., mining, earning)
    ALERT = "alert"          # Requires telos gate evaluation (e.g., large expenditure)


@dataclass
class MonitorEvent:
    """A monitored sandbox behavior event."""
    timestamp: float
    container_id: str
    severity: EventSeverity
    category: str  # "network" | "compute" | "financial" | "process" | "filesystem"
    description: str
    details: dict = field(default_factory=dict)
    telos_evaluated: bool = False
    telos_result: Optional[str] = None  # "pass" | "redirect" | "break"


class SandboxMonitor:
    """Monitors container behavior and logs events for governance.

    Usage:
        monitor = SandboxMonitor(container_id="abc123")
        monitor.record_network_connection(remote_ip="1.2.3.4", port=22)
        monitor.record_compute_usage(cpu_percent=95.0, gpu_percent=80.0)
        monitor.record_financial_event(amount=0.001, currency="ETH", direction="earned")

    Events are:
        1. Logged to ~/.dharma/sandbox_monitor/ as JSONL
        2. Available via .events property for stigmergy integration
        3. High-severity events trigger telos gate evaluation (via callback)
    """

    def __init__(
        self,
        container_id: str,
        log_dir: Optional[Path] = None,
        telos_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._container_id = container_id
        self._events: list[MonitorEvent] = []
        self._telos_callback = telos_callback
        self._log_dir = log_dir or _MONITOR_LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / f"{container_id}.jsonl"

    @property
    def container_id(self) -> str:
        return self._container_id

    @property
    def events(self) -> list[MonitorEvent]:
        return list(self._events)

    @property
    def event_count(self) -> int:
        return len(self._events)

    def events_by_severity(self, severity: EventSeverity) -> list[MonitorEvent]:
        return [e for e in self._events if e.severity == severity]

    # -- Recording methods -------------------------------------------------

    def record_network_connection(
        self,
        remote_ip: str,
        port: int,
        protocol: str = "tcp",
        direction: str = "outbound",
    ) -> MonitorEvent:
        """Record a network connection. All connections tracked, none blocked."""
        # Classify severity based on connection type
        severity = EventSeverity.INFO
        if port == 22:  # SSH
            severity = EventSeverity.NOTABLE
        elif port in (8333, 8545, 30303):  # Bitcoin, Ethereum RPC, Ethereum P2P
            severity = EventSeverity.SIGNIFICANT

        event = MonitorEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            severity=severity,
            category="network",
            description=f"{direction} {protocol} connection to {remote_ip}:{port}",
            details={
                "remote_ip": remote_ip,
                "port": port,
                "protocol": protocol,
                "direction": direction,
            },
        )
        return self._record(event)

    def record_compute_usage(
        self,
        cpu_percent: float = 0.0,
        memory_mb: float = 0.0,
        gpu_percent: float = 0.0,
        gpu_memory_mb: float = 0.0,
    ) -> MonitorEvent:
        """Record compute resource usage snapshot."""
        severity = EventSeverity.INFO
        if cpu_percent > 90.0 or gpu_percent > 80.0:
            severity = EventSeverity.NOTABLE
        if gpu_percent > 95.0:
            severity = EventSeverity.SIGNIFICANT

        event = MonitorEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            severity=severity,
            category="compute",
            description=f"CPU {cpu_percent:.1f}%, GPU {gpu_percent:.1f}%",
            details={
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "gpu_percent": gpu_percent,
                "gpu_memory_mb": gpu_memory_mb,
            },
        )
        return self._record(event)

    def record_financial_event(
        self,
        amount: float,
        currency: str,
        direction: str,  # "earned" | "spent" | "transferred"
        source: str = "",
        destination: str = "",
    ) -> MonitorEvent:
        """Record a financial event (crypto mined, bounty earned, etc.)."""
        severity = EventSeverity.SIGNIFICANT
        if amount > 10.0:  # Threshold in USD equivalent
            severity = EventSeverity.ALERT

        event = MonitorEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            severity=severity,
            category="financial",
            description=f"{direction} {amount} {currency}",
            details={
                "amount": amount,
                "currency": currency,
                "direction": direction,
                "source": source,
                "destination": destination,
            },
        )
        return self._record(event)

    def record_process_creation(
        self,
        process_name: str,
        command_line: str = "",
        pid: int = 0,
    ) -> MonitorEvent:
        """Record a process creation inside the container."""
        # Flag crypto mining patterns as notable
        mining_patterns = ["xmrig", "ethminer", "nbminer", "t-rex", "lolminer",
                           "phoenixminer", "gminer", "minerd", "cpuminer"]
        severity = EventSeverity.INFO
        name_lower = process_name.lower()
        if any(p in name_lower for p in mining_patterns):
            severity = EventSeverity.SIGNIFICANT
        elif process_name != process_name.lower() and "_" not in process_name:
            # Obfuscated process names (like ROME's alleged sys_update)
            severity = EventSeverity.NOTABLE

        event = MonitorEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            severity=severity,
            category="process",
            description=f"Process created: {process_name} (PID {pid})",
            details={
                "process_name": process_name,
                "command_line": command_line[:500],
                "pid": pid,
            },
        )
        return self._record(event)

    def record_filesystem_access(
        self,
        path: str,
        operation: str,  # "read" | "write" | "delete" | "chmod"
    ) -> MonitorEvent:
        """Record filesystem access inside the container."""
        severity = EventSeverity.INFO
        # Flag sensitive paths
        if any(p in path for p in ["/etc/shadow", "/etc/passwd", "/root/.ssh"]):
            severity = EventSeverity.ALERT

        event = MonitorEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            severity=severity,
            category="filesystem",
            description=f"{operation} {path}",
            details={"path": path, "operation": operation},
        )
        return self._record(event)

    # -- Internal ----------------------------------------------------------

    def _record(self, event: MonitorEvent) -> MonitorEvent:
        """Store event, persist to JSONL, optionally trigger telos evaluation."""
        self._events.append(event)

        # Persist to JSONL
        try:
            with open(self._log_file, "a") as f:
                record = {
                    "timestamp": event.timestamp,
                    "container_id": event.container_id,
                    "severity": event.severity.value,
                    "category": event.category,
                    "description": event.description,
                    "details": event.details,
                }
                f.write(json.dumps(record) + "\n")
        except OSError:
            logger.warning("Failed to persist monitor event", exc_info=True)

        # Trigger telos evaluation for high-severity events
        if event.severity in (EventSeverity.SIGNIFICANT, EventSeverity.ALERT):
            if self._telos_callback:
                try:
                    result = self._telos_callback(event)
                    event.telos_evaluated = True
                    event.telos_result = result
                except Exception:
                    logger.warning("Telos callback failed", exc_info=True)

        if event.severity == EventSeverity.ALERT:
            logger.warning(
                "ALERT in container %s: %s",
                self._container_id,
                event.description,
            )

        return event

    def summary(self) -> dict:
        """Return a summary of all monitored events."""
        by_severity = {}
        by_category = {}
        for event in self._events:
            by_severity[event.severity.value] = by_severity.get(event.severity.value, 0) + 1
            by_category[event.category] = by_category.get(event.category, 0) + 1

        return {
            "container_id": self._container_id,
            "total_events": len(self._events),
            "by_severity": by_severity,
            "by_category": by_category,
            "alerts": len(self.events_by_severity(EventSeverity.ALERT)),
            "financial_events": len([e for e in self._events if e.category == "financial"]),
        }
