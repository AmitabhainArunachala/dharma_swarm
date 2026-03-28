"""KaizenOps Local — SQLite-backed operational telemetry store.

The monitoring brain that sits OUTSIDE the swarm and watches everything.
Replaces the HTTP KaizenOpsClient with direct local writes — no server needed.

Ingests:
  1. Cron job results (from CronJobRuntimeStore)
  2. Scout reports (from scout_report.py)
  3. Synthesis outputs (from synthesis_agent.py)
  4. Arbitrary operational events

Queries:
  - Missed/failed/stale cron jobs
  - Scout finding trends over time
  - System health score
  - Anomaly detection (via kaizen_stats.py when available)

Usage:
    from dharma_swarm.kaizen_ops_local import KaizenOpsLocal

    ops = KaizenOpsLocal()
    ops.ingest_cron_result("pulse", "completed", duration=12.3)
    ops.ingest_scout_report(report)
    health = ops.system_health()
    stale = ops.stale_cron_jobs(max_age_hours=2)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KAIZEN_DIR = Path.home() / ".dharma" / "kaizen"
KAIZEN_DB = KAIZEN_DIR / "ops.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    duration_sec REAL DEFAULT 0.0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cron_health (
    job_id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL DEFAULT '',
    last_run TEXT,
    last_status TEXT DEFAULT 'unknown',
    last_duration_sec REAL DEFAULT 0.0,
    consecutive_failures INTEGER DEFAULT 0,
    total_runs INTEGER DEFAULT 0,
    total_failures INTEGER DEFAULT 0,
    last_error TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scout_health (
    domain TEXT PRIMARY KEY,
    last_run TEXT,
    last_finding_count INTEGER DEFAULT 0,
    last_critical_count INTEGER DEFAULT 0,
    last_actionable_count INTEGER DEFAULT 0,
    total_runs INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_dt() -> datetime:
    return datetime.now(timezone.utc)


class KaizenOpsLocal:
    """Local SQLite-backed operational telemetry store."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or KAIZEN_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # -------------------------------------------------------------------
    # Event ingestion
    # -------------------------------------------------------------------

    def ingest_event(
        self,
        category: str,
        source: str,
        status: str = "ok",
        duration_sec: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Ingest a generic operational event."""
        now = _utc_now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO events (timestamp, category, source, status, duration_sec, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, category, source, status, duration_sec, json.dumps(metadata or {}), now),
        )
        conn.commit()

    # -------------------------------------------------------------------
    # Cron monitoring
    # -------------------------------------------------------------------

    def ingest_cron_result(
        self,
        job_id: str,
        status: str,
        *,
        job_name: str = "",
        duration_sec: float = 0.0,
        error: str = "",
    ) -> None:
        """Record a cron job execution result."""
        now = _utc_now()
        conn = self._get_conn()

        # Upsert cron_health
        existing = conn.execute(
            "SELECT consecutive_failures, total_runs, total_failures FROM cron_health WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        is_failure = status in ("failed", "error")

        if existing:
            consec = (existing["consecutive_failures"] + 1) if is_failure else 0
            total_runs = existing["total_runs"] + 1
            total_failures = existing["total_failures"] + (1 if is_failure else 0)
            conn.execute(
                "UPDATE cron_health SET last_run=?, last_status=?, last_duration_sec=?, "
                "consecutive_failures=?, total_runs=?, total_failures=?, last_error=?, "
                "job_name=?, updated_at=? WHERE job_id=?",
                (now, status, duration_sec, consec, total_runs, total_failures,
                 error if is_failure else "", job_name or existing["job_name"] if hasattr(existing, "__getitem__") else job_name, now, job_id),
            )
        else:
            conn.execute(
                "INSERT INTO cron_health (job_id, job_name, last_run, last_status, last_duration_sec, "
                "consecutive_failures, total_runs, total_failures, last_error, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (job_id, job_name, now, status, duration_sec,
                 1 if is_failure else 0, 1 if is_failure else 0, error if is_failure else "", now),
            )

        # Also log as event
        self.ingest_event(
            category="cron",
            source=job_id,
            status=status,
            duration_sec=duration_sec,
            metadata={"job_name": job_name, "error": error} if error else {"job_name": job_name},
        )
        conn.commit()

    def stale_cron_jobs(self, max_age_hours: float = 2.0) -> list[dict[str, Any]]:
        """Find cron jobs that haven't run within their expected window."""
        cutoff = (_utc_dt() - timedelta(hours=max_age_hours)).isoformat()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM cron_health WHERE last_run < ? OR last_run IS NULL "
            "ORDER BY last_run ASC",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    def failing_cron_jobs(self, min_consecutive: int = 2) -> list[dict[str, Any]]:
        """Find cron jobs with consecutive failures."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM cron_health WHERE consecutive_failures >= ? "
            "ORDER BY consecutive_failures DESC",
            (min_consecutive,),
        ).fetchall()
        return [dict(r) for r in rows]

    def cron_health_summary(self) -> dict[str, Any]:
        """Overall cron health dashboard."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM cron_health").fetchone()["c"]
        healthy = conn.execute(
            "SELECT COUNT(*) as c FROM cron_health WHERE last_status = 'completed' AND consecutive_failures = 0"
        ).fetchone()["c"]
        failing = conn.execute(
            "SELECT COUNT(*) as c FROM cron_health WHERE consecutive_failures >= 2"
        ).fetchone()["c"]
        stale = len(self.stale_cron_jobs(max_age_hours=2.0))

        return {
            "total_jobs": total,
            "healthy": healthy,
            "failing": failing,
            "stale": stale,
            "health_pct": round(healthy / total * 100, 1) if total > 0 else 0.0,
        }

    # -------------------------------------------------------------------
    # Scout monitoring
    # -------------------------------------------------------------------

    def ingest_scout_report(self, domain: str, finding_count: int, critical_count: int, actionable_count: int) -> None:
        """Record a scout run."""
        now = _utc_now()
        conn = self._get_conn()

        existing = conn.execute("SELECT total_runs FROM scout_health WHERE domain = ?", (domain,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE scout_health SET last_run=?, last_finding_count=?, last_critical_count=?, "
                "last_actionable_count=?, total_runs=total_runs+1, updated_at=? WHERE domain=?",
                (now, finding_count, critical_count, actionable_count, now, domain),
            )
        else:
            conn.execute(
                "INSERT INTO scout_health (domain, last_run, last_finding_count, last_critical_count, "
                "last_actionable_count, total_runs, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (domain, now, finding_count, critical_count, actionable_count, now),
            )

        self.ingest_event(
            category="scout",
            source=domain,
            status="critical" if critical_count > 0 else "ok",
            metadata={"findings": finding_count, "critical": critical_count, "actionable": actionable_count},
        )
        conn.commit()

    # -------------------------------------------------------------------
    # System health
    # -------------------------------------------------------------------

    def system_health(self) -> dict[str, Any]:
        """Composite system health score."""
        cron = self.cron_health_summary()
        conn = self._get_conn()

        # Scout health
        scout_total = conn.execute("SELECT COUNT(*) as c FROM scout_health").fetchone()["c"]
        scout_critical = conn.execute(
            "SELECT COUNT(*) as c FROM scout_health WHERE last_critical_count > 0"
        ).fetchone()["c"]

        # Recent event counts (last 24h)
        cutoff_24h = (_utc_dt() - timedelta(hours=24)).isoformat()
        events_24h = conn.execute(
            "SELECT COUNT(*) as c FROM events WHERE timestamp > ?", (cutoff_24h,)
        ).fetchone()["c"]
        failures_24h = conn.execute(
            "SELECT COUNT(*) as c FROM events WHERE timestamp > ? AND status IN ('failed', 'error')",
            (cutoff_24h,),
        ).fetchone()["c"]

        # Composite score: 0-100
        score = 100.0
        if cron["total_jobs"] > 0:
            score -= (cron["failing"] / cron["total_jobs"]) * 30  # -30 max for cron failures
            score -= (cron["stale"] / cron["total_jobs"]) * 20    # -20 max for stale jobs
        if scout_critical > 0:
            score -= min(scout_critical * 10, 30)                  # -10 per critical, max -30
        if events_24h > 0:
            failure_rate = failures_24h / events_24h
            score -= failure_rate * 20                              # -20 max for high failure rate

        return {
            "score": round(max(0, score), 1),
            "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F",
            "cron": cron,
            "scouts": {"total": scout_total, "with_criticals": scout_critical},
            "events_24h": events_24h,
            "failures_24h": failures_24h,
        }

    # -------------------------------------------------------------------
    # Bulk ingest from existing cron state files
    # -------------------------------------------------------------------

    def sync_from_cron_runtime_store(self) -> int:
        """Import existing cron state into KaizenOps.

        Reads ~/.dharma/cron/state/latest/*.json and backfills cron_health.
        Returns count of jobs synced.
        """
        state_dir = Path.home() / ".dharma" / "cron" / "state" / "latest"
        if not state_dir.exists():
            return 0

        count = 0
        for path in state_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.ingest_cron_result(
                    job_id=data.get("job_id", path.stem),
                    status=data.get("status", "unknown"),
                    job_name=data.get("job_name", ""),
                    duration_sec=0.0,
                    error=data.get("error", ""),
                )
                count += 1
            except Exception as e:
                logger.debug("Failed to sync cron state %s: %s", path, e)

        return count

    def sync_from_scout_reports(self) -> int:
        """Import existing scout reports into KaizenOps.

        Reads ~/.dharma/scouts/*/latest.json and backfills scout_health.
        """
        scouts_dir = Path.home() / ".dharma" / "scouts"
        if not scouts_dir.exists():
            return 0

        count = 0
        for domain_dir in scouts_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name == "synthesis":
                continue
            latest = domain_dir / "latest.json"
            if not latest.exists():
                continue
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                findings = data.get("findings", [])
                critical = sum(1 for f in findings if f.get("severity") == "critical")
                actionable = sum(1 for f in findings if f.get("actionable"))
                self.ingest_scout_report(
                    domain=domain_dir.name,
                    finding_count=len(findings),
                    critical_count=critical,
                    actionable_count=actionable,
                )
                count += 1
            except Exception as e:
                logger.debug("Failed to sync scout report %s: %s", domain_dir.name, e)

        return count


# ---------------------------------------------------------------------------
# CLI / quick health check
# ---------------------------------------------------------------------------

def print_health() -> None:
    """Print system health to stdout."""
    ops = KaizenOpsLocal()

    # Sync existing data first
    cron_count = ops.sync_from_cron_runtime_store()
    scout_count = ops.sync_from_scout_reports()

    health = ops.system_health()
    print(f"=== KaizenOps System Health: {health['grade']} ({health['score']}/100) ===")
    print(f"  Cron: {health['cron']['healthy']}/{health['cron']['total_jobs']} healthy, "
          f"{health['cron']['failing']} failing, {health['cron']['stale']} stale")
    print(f"  Scouts: {health['scouts']['total']} domains, "
          f"{health['scouts']['with_criticals']} with criticals")
    print(f"  Events 24h: {health['events_24h']} total, {health['failures_24h']} failures")
    print(f"  Synced: {cron_count} cron jobs, {scout_count} scout reports")

    # Show failing jobs
    failing = ops.failing_cron_jobs()
    if failing:
        print(f"\n  FAILING JOBS:")
        for j in failing:
            print(f"    {j['job_id']}: {j['consecutive_failures']} consecutive failures — {j['last_error'][:80]}")

    # Show stale jobs
    stale = ops.stale_cron_jobs(max_age_hours=2.0)
    if stale:
        print(f"\n  STALE JOBS (>2h since last run):")
        for j in stale:
            print(f"    {j['job_id']}: last ran {j['last_run']}")

    ops.close()


if __name__ == "__main__":
    print_health()
