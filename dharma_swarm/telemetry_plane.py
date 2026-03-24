"""Canonical telemetry plane for company-state records.

This module fills the next missing layer above the runtime spine: first-class
records for identity, rewards, routing, policy, intervention, economics, and
external outcomes. It is intentionally separate from ``runtime_state.py`` so
the sovereign contract and adapter work can land against a stable telemetry
surface without creating merge pressure in the core runtime file.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

DEFAULT_TELEMETRY_DB = Path.home() / ".dharma" / "state" / "runtime.db"

_AGENT_IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS agent_identity (
    agent_id TEXT PRIMARY KEY,
    codename TEXT NOT NULL DEFAULT '',
    serial TEXT NOT NULL DEFAULT '',
    avatar_id TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    squad_id TEXT NOT NULL DEFAULT '',
    specialization TEXT NOT NULL DEFAULT '',
    level INTEGER NOT NULL DEFAULT 1,
    xp REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_active TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_AGENT_REWARD_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS agent_reward_ledger (
    entry_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    reward_type TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0.0,
    unit TEXT NOT NULL DEFAULT 'points',
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_AGENT_REPUTATION_DDL = """
CREATE TABLE IF NOT EXISTS agent_reputation (
    agent_id TEXT PRIMARY KEY,
    reputation REAL NOT NULL DEFAULT 0.0,
    trust_band TEXT NOT NULL DEFAULT 'unknown',
    last_reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
)"""

_TEAM_ROSTER_DDL = """
CREATE TABLE IF NOT EXISTS team_roster (
    roster_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_WORKFLOW_SCORES_DDL = """
CREATE TABLE IF NOT EXISTS workflow_scores (
    score_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    score_name TEXT NOT NULL,
    score_value REAL NOT NULL DEFAULT 0.0,
    weighting REAL NOT NULL DEFAULT 1.0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
)"""

_ROUTING_DECISIONS_DDL = """
CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    action_name TEXT NOT NULL,
    route_path TEXT NOT NULL,
    selected_provider TEXT NOT NULL DEFAULT '',
    selected_model_hint TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    requires_human INTEGER NOT NULL DEFAULT 0,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_POLICY_DECISIONS_DDL = """
CREATE TABLE IF NOT EXISTS policy_decisions (
    decision_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    policy_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    status_before TEXT NOT NULL DEFAULT '',
    status_after TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_INTERVENTION_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS intervention_outcomes (
    intervention_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    operator_id TEXT NOT NULL DEFAULT '',
    intervention_type TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    impact_score REAL NOT NULL DEFAULT 0.0,
    summary TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_ECONOMIC_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS economic_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    event_kind TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0.0,
    currency TEXT NOT NULL DEFAULT 'USD',
    counterparty TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_EXTERNAL_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS external_outcomes (
    outcome_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    outcome_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL DEFAULT '',
    value REAL NOT NULL DEFAULT 0.0,
    unit TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'observed',
    summary TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_agent_identity_status_updated ON agent_identity(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_reward_agent_created ON agent_reward_ledger(agent_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_reward_session_created ON agent_reward_ledger(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_team_team_active ON team_roster(team_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_team_agent_active ON team_roster(agent_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_workflow_score ON workflow_scores(workflow_id, score_name, recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_routing_task_created ON routing_decisions(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_routing_run_created ON routing_decisions(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_policy_task_created ON policy_decisions(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_intervention_task_created ON intervention_outcomes(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_economic_kind_created ON economic_events(event_kind, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_external_kind_created ON external_outcomes(outcome_kind, created_at)",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _apply_connection_pragmas_sync(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=NORMAL")


async def _apply_connection_pragmas_async(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA synchronous=NORMAL")


def ensure_telemetry_schema_sync(db: sqlite3.Connection) -> None:
    _apply_connection_pragmas_sync(db)
    for ddl in (
        _AGENT_IDENTITY_DDL,
        _AGENT_REWARD_LEDGER_DDL,
        _AGENT_REPUTATION_DDL,
        _TEAM_ROSTER_DDL,
        _WORKFLOW_SCORES_DDL,
        _ROUTING_DECISIONS_DDL,
        _POLICY_DECISIONS_DDL,
        _INTERVENTION_OUTCOMES_DDL,
        _ECONOMIC_EVENTS_DDL,
        _EXTERNAL_OUTCOMES_DDL,
    ):
        db.execute(ddl)
    for idx in _INDEXES:
        db.execute(idx)
    db.commit()


async def ensure_telemetry_schema_async(db: aiosqlite.Connection) -> None:
    await _apply_connection_pragmas_async(db)
    for ddl in (
        _AGENT_IDENTITY_DDL,
        _AGENT_REWARD_LEDGER_DDL,
        _AGENT_REPUTATION_DDL,
        _TEAM_ROSTER_DDL,
        _WORKFLOW_SCORES_DDL,
        _ROUTING_DECISIONS_DDL,
        _POLICY_DECISIONS_DDL,
        _INTERVENTION_OUTCOMES_DDL,
        _ECONOMIC_EVENTS_DDL,
        _EXTERNAL_OUTCOMES_DDL,
    ):
        await db.execute(ddl)
    for idx in _INDEXES:
        await db.execute(idx)
    await db.commit()


@dataclass(frozen=True)
class AgentIdentityRecord:
    agent_id: str
    codename: str = ""
    serial: str = ""
    avatar_id: str = ""
    department: str = ""
    squad_id: str = ""
    specialization: str = ""
    level: int = 1
    xp: float = 0.0
    status: str = "unknown"
    last_active: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class AgentRewardLedgerEntry:
    entry_id: str
    agent_id: str
    reward_type: str
    amount: float
    unit: str = "points"
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class AgentReputationRecord:
    agent_id: str
    reputation: float = 0.0
    trust_band: str = "unknown"
    last_reason: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class TeamRosterRecord:
    roster_id: str
    team_id: str
    agent_id: str
    role: str = ""
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class WorkflowScoreRecord:
    score_id: str
    workflow_id: str
    score_name: str
    score_value: float
    weighting: float = 1.0
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    recorded_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class RoutingDecisionRecord:
    decision_id: str
    action_name: str
    route_path: str
    selected_provider: str = ""
    selected_model_hint: str = ""
    confidence: float = 0.0
    requires_human: bool = False
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class PolicyDecisionRecord:
    decision_id: str
    policy_name: str
    decision: str
    status_before: str = ""
    status_after: str = ""
    confidence: float = 0.0
    reason: str = ""
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class InterventionOutcomeRecord:
    intervention_id: str
    intervention_type: str
    outcome_status: str
    impact_score: float = 0.0
    summary: str = ""
    operator_id: str = ""
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class EconomicEventRecord:
    event_id: str
    event_kind: str
    amount: float
    currency: str = "USD"
    counterparty: str = ""
    summary: str = ""
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class ExternalOutcomeRecord:
    outcome_id: str
    outcome_kind: str
    value: float
    unit: str = ""
    confidence: float = 0.0
    status: str = "observed"
    subject_id: str = ""
    summary: str = ""
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


def _row_to_agent_identity(row: sqlite3.Row | aiosqlite.Row) -> AgentIdentityRecord:
    return AgentIdentityRecord(
        agent_id=str(row["agent_id"]),
        codename=str(row["codename"] or ""),
        serial=str(row["serial"] or ""),
        avatar_id=str(row["avatar_id"] or ""),
        department=str(row["department"] or ""),
        squad_id=str(row["squad_id"] or ""),
        specialization=str(row["specialization"] or ""),
        level=int(row["level"] or 1),
        xp=float(row["xp"] or 0.0),
        status=str(row["status"] or "unknown"),
        last_active=_parse_dt(row["last_active"]),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


def _row_to_reward(row: sqlite3.Row | aiosqlite.Row) -> AgentRewardLedgerEntry:
    return AgentRewardLedgerEntry(
        entry_id=str(row["entry_id"]),
        agent_id=str(row["agent_id"]),
        reward_type=str(row["reward_type"]),
        amount=float(row["amount"] or 0.0),
        unit=str(row["unit"] or "points"),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        reason=str(row["reason"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


def _row_to_reputation(row: sqlite3.Row | aiosqlite.Row) -> AgentReputationRecord:
    evidence = _json_load(row["evidence_json"], [])
    return AgentReputationRecord(
        agent_id=str(row["agent_id"]),
        reputation=float(row["reputation"] or 0.0),
        trust_band=str(row["trust_band"] or "unknown"),
        last_reason=str(row["last_reason"] or ""),
        evidence=evidence if isinstance(evidence, list) else [],
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


def _row_to_team_roster(row: sqlite3.Row | aiosqlite.Row) -> TeamRosterRecord:
    return TeamRosterRecord(
        roster_id=str(row["roster_id"]),
        team_id=str(row["team_id"]),
        agent_id=str(row["agent_id"]),
        role=str(row["role"] or ""),
        active=bool(row["active"]),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


def _row_to_workflow_score(row: sqlite3.Row | aiosqlite.Row) -> WorkflowScoreRecord:
    evidence = _json_load(row["evidence_json"], [])
    return WorkflowScoreRecord(
        score_id=str(row["score_id"]),
        workflow_id=str(row["workflow_id"]),
        score_name=str(row["score_name"]),
        score_value=float(row["score_value"] or 0.0),
        weighting=float(row["weighting"] or 1.0),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        evidence=evidence if isinstance(evidence, list) else [],
        metadata=_json_load(row["metadata_json"], {}),
        recorded_at=_parse_dt(row["recorded_at"]) or _utc_now(),
    )


def _row_to_routing_decision(row: sqlite3.Row | aiosqlite.Row) -> RoutingDecisionRecord:
    reasons = _json_load(row["reasons_json"], [])
    return RoutingDecisionRecord(
        decision_id=str(row["decision_id"]),
        action_name=str(row["action_name"]),
        route_path=str(row["route_path"]),
        selected_provider=str(row["selected_provider"] or ""),
        selected_model_hint=str(row["selected_model_hint"] or ""),
        confidence=float(row["confidence"] or 0.0),
        requires_human=bool(row["requires_human"]),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        reasons=[str(item) for item in reasons] if isinstance(reasons, list) else [],
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


def _row_to_policy_decision(row: sqlite3.Row | aiosqlite.Row) -> PolicyDecisionRecord:
    evidence = _json_load(row["evidence_json"], [])
    return PolicyDecisionRecord(
        decision_id=str(row["decision_id"]),
        policy_name=str(row["policy_name"]),
        decision=str(row["decision"]),
        status_before=str(row["status_before"] or ""),
        status_after=str(row["status_after"] or ""),
        confidence=float(row["confidence"] or 0.0),
        reason=str(row["reason"] or ""),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        evidence=evidence if isinstance(evidence, list) else [],
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


def _row_to_intervention(row: sqlite3.Row | aiosqlite.Row) -> InterventionOutcomeRecord:
    return InterventionOutcomeRecord(
        intervention_id=str(row["intervention_id"]),
        intervention_type=str(row["intervention_type"]),
        outcome_status=str(row["outcome_status"]),
        impact_score=float(row["impact_score"] or 0.0),
        summary=str(row["summary"] or ""),
        operator_id=str(row["operator_id"] or ""),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


def _row_to_economic_event(row: sqlite3.Row | aiosqlite.Row) -> EconomicEventRecord:
    return EconomicEventRecord(
        event_id=str(row["event_id"]),
        event_kind=str(row["event_kind"]),
        amount=float(row["amount"] or 0.0),
        currency=str(row["currency"] or "USD"),
        counterparty=str(row["counterparty"] or ""),
        summary=str(row["summary"] or ""),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


def _row_to_external_outcome(row: sqlite3.Row | aiosqlite.Row) -> ExternalOutcomeRecord:
    return ExternalOutcomeRecord(
        outcome_id=str(row["outcome_id"]),
        outcome_kind=str(row["outcome_kind"]),
        value=float(row["value"] or 0.0),
        unit=str(row["unit"] or ""),
        confidence=float(row["confidence"] or 0.0),
        status=str(row["status"] or "observed"),
        subject_id=str(row["subject_id"] or ""),
        summary=str(row["summary"] or ""),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


class TelemetryPlaneStore:
    """SQLite-backed telemetry store for company-state records."""

    _BUSY_TIMEOUT_MS = 30000

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_TELEMETRY_DB
        self._initialized = False

    def _open(self) -> aiosqlite.Connection:
        """Open connection with busy_timeout to prevent 'database is locked'."""
        return aiosqlite.connect(self.db_path, timeout=self._BUSY_TIMEOUT_MS / 1000)

    async def init_db(self) -> None:
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._open() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=30000")
            await ensure_telemetry_schema_async(db)
        self._initialized = True

    async def upsert_agent_identity(
        self,
        record: AgentIdentityRecord,
    ) -> AgentIdentityRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO agent_identity (agent_id, codename, serial, avatar_id,"
                " department, squad_id, specialization, level, xp, status,"
                " last_active, metadata_json, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(agent_id) DO UPDATE SET"
                " codename = excluded.codename,"
                " serial = excluded.serial,"
                " avatar_id = excluded.avatar_id,"
                " department = excluded.department,"
                " squad_id = excluded.squad_id,"
                " specialization = excluded.specialization,"
                " level = excluded.level,"
                " xp = excluded.xp,"
                " status = excluded.status,"
                " last_active = excluded.last_active,"
                " metadata_json = excluded.metadata_json,"
                " updated_at = excluded.updated_at",
                (
                    record.agent_id,
                    record.codename,
                    record.serial,
                    record.avatar_id,
                    record.department,
                    record.squad_id,
                    record.specialization,
                    int(record.level),
                    float(record.xp),
                    record.status,
                    record.last_active.isoformat() if record.last_active else None,
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()
        loaded = await self.get_agent_identity(record.agent_id)
        if loaded is None:
            raise RuntimeError(f"Failed to reload agent identity after upsert: {record.agent_id}")
        return loaded

    async def get_agent_identity(self, agent_id: str) -> AgentIdentityRecord | None:
        await self.init_db()
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT agent_id, codename, serial, avatar_id, department, squad_id,"
                " specialization, level, xp, status, last_active, metadata_json,"
                " created_at, updated_at FROM agent_identity WHERE agent_id = ?",
                (agent_id,),
            )
            row = await cursor.fetchone()
        return _row_to_agent_identity(row) if row is not None else None

    async def list_agent_identities(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AgentIdentityRecord]:
        await self.init_db()
        query = (
            "SELECT agent_id, codename, serial, avatar_id, department, squad_id,"
            " specialization, level, xp, status, last_active, metadata_json,"
            " created_at, updated_at FROM agent_identity WHERE 1=1"
        )
        params: list[Any] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_agent_identity(row) for row in rows]

    async def record_reward_entry(
        self,
        entry: AgentRewardLedgerEntry,
    ) -> AgentRewardLedgerEntry:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO agent_reward_ledger (entry_id, agent_id, session_id,"
                " task_id, run_id, reward_type, amount, unit, reason, metadata_json,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry.entry_id,
                    entry.agent_id,
                    entry.session_id,
                    entry.task_id,
                    entry.run_id,
                    entry.reward_type,
                    float(entry.amount),
                    entry.unit,
                    entry.reason,
                    _json_dump(entry.metadata),
                    entry.created_at.isoformat(),
                ),
            )
            await db.commit()
        return entry

    async def list_reward_entries(
        self,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentRewardLedgerEntry]:
        await self.init_db()
        query = (
            "SELECT entry_id, agent_id, session_id, task_id, run_id, reward_type,"
            " amount, unit, reason, metadata_json, created_at"
            " FROM agent_reward_ledger WHERE 1=1"
        )
        params: list[Any] = []
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_reward(row) for row in rows]

    async def upsert_agent_reputation(
        self,
        record: AgentReputationRecord,
    ) -> AgentReputationRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO agent_reputation (agent_id, reputation, trust_band,"
                " last_reason, evidence_json, updated_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(agent_id) DO UPDATE SET"
                " reputation = excluded.reputation,"
                " trust_band = excluded.trust_band,"
                " last_reason = excluded.last_reason,"
                " evidence_json = excluded.evidence_json,"
                " updated_at = excluded.updated_at",
                (
                    record.agent_id,
                    float(record.reputation),
                    record.trust_band,
                    record.last_reason,
                    _json_dump(record.evidence),
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()
        loaded = await self.get_agent_reputation(record.agent_id)
        if loaded is None:
            raise RuntimeError(f"Failed to reload agent reputation after upsert: {record.agent_id}")
        return loaded

    async def get_agent_reputation(self, agent_id: str) -> AgentReputationRecord | None:
        await self.init_db()
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT agent_id, reputation, trust_band, last_reason,"
                    " evidence_json, updated_at FROM agent_reputation"
                    " WHERE agent_id = ?",
                    (agent_id,),
                )
            ).fetchone()
        return _row_to_reputation(row) if row is not None else None

    async def record_team_roster(
        self,
        record: TeamRosterRecord,
    ) -> TeamRosterRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO team_roster (roster_id, team_id, agent_id, role, active,"
                " metadata_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(roster_id) DO UPDATE SET"
                " team_id = excluded.team_id,"
                " agent_id = excluded.agent_id,"
                " role = excluded.role,"
                " active = excluded.active,"
                " metadata_json = excluded.metadata_json,"
                " updated_at = excluded.updated_at",
                (
                    record.roster_id,
                    record.team_id,
                    record.agent_id,
                    record.role,
                    1 if record.active else 0,
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_team_roster(
        self,
        *,
        team_id: str | None = None,
        agent_id: str | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[TeamRosterRecord]:
        await self.init_db()
        query = (
            "SELECT roster_id, team_id, agent_id, role, active, metadata_json,"
            " created_at, updated_at FROM team_roster WHERE 1=1"
        )
        params: list[Any] = []
        if team_id is not None:
            query += " AND team_id = ?"
            params.append(team_id)
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_team_roster(row) for row in rows]

    async def record_workflow_score(
        self,
        record: WorkflowScoreRecord,
    ) -> WorkflowScoreRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO workflow_scores (score_id, workflow_id, session_id,"
                " task_id, run_id, score_name, score_value, weighting,"
                " evidence_json, metadata_json, recorded_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.score_id,
                    record.workflow_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.score_name,
                    float(record.score_value),
                    float(record.weighting),
                    _json_dump(record.evidence),
                    _json_dump(record.metadata),
                    record.recorded_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_workflow_scores(
        self,
        *,
        workflow_id: str | None = None,
        score_name: str | None = None,
        limit: int = 100,
    ) -> list[WorkflowScoreRecord]:
        await self.init_db()
        query = (
            "SELECT score_id, workflow_id, session_id, task_id, run_id, score_name,"
            " score_value, weighting, evidence_json, metadata_json, recorded_at"
            " FROM workflow_scores WHERE 1=1"
        )
        params: list[Any] = []
        if workflow_id is not None:
            query += " AND workflow_id = ?"
            params.append(workflow_id)
        if score_name is not None:
            query += " AND score_name = ?"
            params.append(score_name)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_workflow_score(row) for row in rows]

    async def record_routing_decision(
        self,
        record: RoutingDecisionRecord,
    ) -> RoutingDecisionRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO routing_decisions (decision_id, session_id, task_id,"
                " run_id, action_name, route_path, selected_provider,"
                " selected_model_hint, confidence, requires_human, reasons_json,"
                " metadata_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.decision_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.action_name,
                    record.route_path,
                    record.selected_provider,
                    record.selected_model_hint,
                    float(record.confidence),
                    1 if record.requires_human else 0,
                    _json_dump(record.reasons),
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_routing_decisions(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[RoutingDecisionRecord]:
        await self.init_db()
        query = (
            "SELECT decision_id, session_id, task_id, run_id, action_name,"
            " route_path, selected_provider, selected_model_hint, confidence,"
            " requires_human, reasons_json, metadata_json, created_at"
            " FROM routing_decisions WHERE 1=1"
        )
        params: list[Any] = []
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_routing_decision(row) for row in rows]

    async def record_policy_decision(
        self,
        record: PolicyDecisionRecord,
    ) -> PolicyDecisionRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO policy_decisions (decision_id, session_id, task_id,"
                " run_id, policy_name, decision, status_before, status_after,"
                " confidence, reason, evidence_json, metadata_json, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.decision_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.policy_name,
                    record.decision,
                    record.status_before,
                    record.status_after,
                    float(record.confidence),
                    record.reason,
                    _json_dump(record.evidence),
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_policy_decisions(
        self,
        *,
        task_id: str | None = None,
        policy_name: str | None = None,
        limit: int = 100,
    ) -> list[PolicyDecisionRecord]:
        await self.init_db()
        query = (
            "SELECT decision_id, session_id, task_id, run_id, policy_name,"
            " decision, status_before, status_after, confidence, reason,"
            " evidence_json, metadata_json, created_at"
            " FROM policy_decisions WHERE 1=1"
        )
        params: list[Any] = []
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if policy_name is not None:
            query += " AND policy_name = ?"
            params.append(policy_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_policy_decision(row) for row in rows]

    async def record_intervention_outcome(
        self,
        record: InterventionOutcomeRecord,
    ) -> InterventionOutcomeRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO intervention_outcomes (intervention_id, session_id,"
                " task_id, run_id, operator_id, intervention_type, outcome_status,"
                " impact_score, summary, metadata_json, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.intervention_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.operator_id,
                    record.intervention_type,
                    record.outcome_status,
                    float(record.impact_score),
                    record.summary,
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_intervention_outcomes(
        self,
        *,
        task_id: str | None = None,
        operator_id: str | None = None,
        limit: int = 100,
    ) -> list[InterventionOutcomeRecord]:
        await self.init_db()
        query = (
            "SELECT intervention_id, session_id, task_id, run_id, operator_id,"
            " intervention_type, outcome_status, impact_score, summary,"
            " metadata_json, created_at FROM intervention_outcomes WHERE 1=1"
        )
        params: list[Any] = []
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if operator_id is not None:
            query += " AND operator_id = ?"
            params.append(operator_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_intervention(row) for row in rows]

    async def record_economic_event(
        self,
        record: EconomicEventRecord,
    ) -> EconomicEventRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO economic_events (event_id, session_id, task_id, run_id,"
                " event_kind, amount, currency, counterparty, summary, metadata_json,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.event_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.event_kind,
                    float(record.amount),
                    record.currency,
                    record.counterparty,
                    record.summary,
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_economic_events(
        self,
        *,
        event_kind: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[EconomicEventRecord]:
        await self.init_db()
        query = (
            "SELECT event_id, session_id, task_id, run_id, event_kind, amount,"
            " currency, counterparty, summary, metadata_json, created_at"
            " FROM economic_events WHERE 1=1"
        )
        params: list[Any] = []
        if event_kind is not None:
            query += " AND event_kind = ?"
            params.append(event_kind)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_economic_event(row) for row in rows]

    async def record_external_outcome(
        self,
        record: ExternalOutcomeRecord,
    ) -> ExternalOutcomeRecord:
        await self.init_db()
        async with self._open() as db:
            await db.execute(
                "INSERT INTO external_outcomes (outcome_id, session_id, task_id,"
                " run_id, outcome_kind, subject_id, value, unit, confidence, status,"
                " summary, metadata_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.outcome_id,
                    record.session_id,
                    record.task_id,
                    record.run_id,
                    record.outcome_kind,
                    record.subject_id,
                    float(record.value),
                    record.unit,
                    float(record.confidence),
                    record.status,
                    record.summary,
                    _json_dump(record.metadata),
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
        return record

    async def list_external_outcomes(
        self,
        *,
        outcome_kind: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[ExternalOutcomeRecord]:
        await self.init_db()
        query = (
            "SELECT outcome_id, session_id, task_id, run_id, outcome_kind,"
            " subject_id, value, unit, confidence, status, summary, metadata_json,"
            " created_at FROM external_outcomes WHERE 1=1"
        )
        params: list[Any] = []
        if outcome_kind is not None:
            query += " AND outcome_kind = ?"
            params.append(outcome_kind)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._open() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_external_outcome(row) for row in rows]

    @staticmethod
    def new_agent_id() -> str:
        return _new_id("agent")

    @staticmethod
    def new_reward_entry_id() -> str:
        return _new_id("reward")

    @staticmethod
    def new_roster_id() -> str:
        return _new_id("roster")

    @staticmethod
    def new_score_id() -> str:
        return _new_id("score")

    @staticmethod
    def new_routing_decision_id() -> str:
        return _new_id("route")

    @staticmethod
    def new_policy_decision_id() -> str:
        return _new_id("policy")

    @staticmethod
    def new_intervention_id() -> str:
        return _new_id("intervention")

    @staticmethod
    def new_economic_event_id() -> str:
        return _new_id("economic")

    @staticmethod
    def new_external_outcome_id() -> str:
        return _new_id("outcome")
