"""Canonical SQLite runtime state spine for DGC vNext.

This module provides the structured source-of-truth layer for single-host
orchestration. It complements the append-only JSONL ledgers and the derived
memory/retrieval indexes by keeping live control-plane state explicit,
transactional, and inspectable.
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

from dharma_swarm.engine.event_memory import (
    ensure_memory_plane_schema_async,
    ensure_memory_plane_schema_sync,
)

DEFAULT_RUNTIME_DB = Path.home() / ".dharma" / "state" / "runtime.db"

_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    current_task_id TEXT NOT NULL DEFAULT '',
    active_bundle_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_TASK_CLAIMS_DDL = """
CREATE TABLE IF NOT EXISTS task_claims (
    claim_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    acked_at TEXT,
    heartbeat_at TEXT,
    stale_after TEXT,
    recovered_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_DELEGATION_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS delegation_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL,
    claim_id TEXT NOT NULL DEFAULT '',
    parent_run_id TEXT NOT NULL DEFAULT '',
    assigned_by TEXT NOT NULL DEFAULT '',
    assigned_to TEXT NOT NULL,
    requested_output_json TEXT NOT NULL DEFAULT '[]',
    current_artifact_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    failure_code TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_WORKSPACE_LEASES_DDL = """
CREATE TABLE IF NOT EXISTS workspace_leases (
    lease_id TEXT PRIMARY KEY,
    zone_path TEXT NOT NULL,
    holder_run_id TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,
    base_hash TEXT NOT NULL DEFAULT '',
    acquired_at TEXT NOT NULL,
    expires_at TEXT,
    released_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_ARTIFACT_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS artifact_records (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    artifact_kind TEXT NOT NULL,
    manifest_path TEXT NOT NULL DEFAULT '',
    payload_path TEXT NOT NULL DEFAULT '',
    checksum TEXT NOT NULL DEFAULT '',
    parent_artifact_id TEXT NOT NULL DEFAULT '',
    promotion_state TEXT NOT NULL DEFAULT 'ephemeral',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_ARTIFACT_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS artifact_links (
    link_id TEXT PRIMARY KEY,
    from_artifact_id TEXT NOT NULL,
    to_artifact_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_MEMORY_FACTS_DDL = """
CREATE TABLE IF NOT EXISTS memory_facts (
    fact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    fact_kind TEXT NOT NULL,
    truth_state TEXT NOT NULL,
    text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    valid_from TEXT,
    valid_to TEXT,
    source_event_id TEXT NOT NULL DEFAULT '',
    source_artifact_id TEXT NOT NULL DEFAULT '',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_MEMORY_EDGES_DDL = """
CREATE TABLE IF NOT EXISTS memory_edges (
    edge_id TEXT PRIMARY KEY,
    from_fact_id TEXT NOT NULL,
    to_fact_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.0,
    source_event_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_CONTEXT_BUNDLES_DDL = """
CREATE TABLE IF NOT EXISTS context_bundles (
    bundle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    token_budget INTEGER NOT NULL,
    rendered_text TEXT NOT NULL,
    sections_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)"""

_OPERATOR_ACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS operator_actions (
    action_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    action_name TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_status_updated ON sessions(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_claims_task_status ON task_claims(task_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_claims_agent_status ON task_claims(agent_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_runs_task_status ON delegation_runs(task_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_runs_session_started ON delegation_runs(session_id, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_leases_zone_released ON workspace_leases(zone_path, released_at)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_task_created ON artifact_records(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run_created ON artifact_records(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_truth_updated ON memory_facts(truth_state, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_task_truth ON memory_facts(task_id, truth_state)",
    "CREATE INDEX IF NOT EXISTS idx_context_session_created ON context_bundles(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_context_task_created ON context_bundles(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_operator_actions_session_created ON operator_actions(session_id, created_at)",
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


def ensure_runtime_state_schema_sync(
    db: sqlite3.Connection,
    *,
    include_memory_plane: bool = True,
) -> None:
    """Create runtime-state tables on a sync SQLite connection."""
    _apply_connection_pragmas_sync(db)
    for ddl in (
        _SESSIONS_DDL,
        _TASK_CLAIMS_DDL,
        _DELEGATION_RUNS_DDL,
        _WORKSPACE_LEASES_DDL,
        _ARTIFACT_RECORDS_DDL,
        _ARTIFACT_LINKS_DDL,
        _MEMORY_FACTS_DDL,
        _MEMORY_EDGES_DDL,
        _CONTEXT_BUNDLES_DDL,
        _OPERATOR_ACTIONS_DDL,
    ):
        db.execute(ddl)
    for idx in _INDEXES:
        db.execute(idx)
    if include_memory_plane:
        ensure_memory_plane_schema_sync(db)
    db.commit()


async def ensure_runtime_state_schema_async(
    db: aiosqlite.Connection,
    *,
    include_memory_plane: bool = True,
) -> None:
    """Create runtime-state tables on an async SQLite connection."""
    await _apply_connection_pragmas_async(db)
    for ddl in (
        _SESSIONS_DDL,
        _TASK_CLAIMS_DDL,
        _DELEGATION_RUNS_DDL,
        _WORKSPACE_LEASES_DDL,
        _ARTIFACT_RECORDS_DDL,
        _ARTIFACT_LINKS_DDL,
        _MEMORY_FACTS_DDL,
        _MEMORY_EDGES_DDL,
        _CONTEXT_BUNDLES_DDL,
        _OPERATOR_ACTIONS_DDL,
    ):
        await db.execute(ddl)
    for idx in _INDEXES:
        await db.execute(idx)
    if include_memory_plane:
        await ensure_memory_plane_schema_async(db)
    await db.commit()


@dataclass(frozen=True)
class SessionState:
    session_id: str
    operator_id: str = ""
    status: str = "active"
    current_task_id: str = ""
    active_bundle_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class TaskClaim:
    claim_id: str
    task_id: str
    agent_id: str
    status: str = "claimed"
    session_id: str = ""
    claimed_at: datetime = field(default_factory=_utc_now)
    acked_at: datetime | None = None
    heartbeat_at: datetime | None = None
    stale_after: datetime | None = None
    recovered_at: datetime | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationRun:
    run_id: str
    task_id: str
    assigned_to: str
    status: str = "queued"
    session_id: str = ""
    claim_id: str = ""
    parent_run_id: str = ""
    assigned_by: str = ""
    requested_output: list[str] = field(default_factory=list)
    current_artifact_id: str = ""
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime | None = None
    failure_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceLease:
    lease_id: str
    zone_path: str
    mode: str
    holder_run_id: str = ""
    base_hash: str = ""
    acquired_at: datetime = field(default_factory=_utc_now)
    expires_at: datetime | None = None
    released_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    artifact_kind: str
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    manifest_path: str = ""
    payload_path: str = ""
    checksum: str = ""
    parent_artifact_id: str = ""
    promotion_state: str = "ephemeral"
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryFact:
    fact_id: str
    fact_kind: str
    truth_state: str
    text: str
    confidence: float = 0.0
    session_id: str = ""
    task_id: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_event_id: str = ""
    source_artifact_id: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class MemoryEdge:
    edge_id: str
    from_fact_id: str
    to_fact_id: str
    relation: str
    weight: float = 0.0
    source_event_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class ContextBundleRecord:
    bundle_id: str
    session_id: str
    task_id: str = ""
    run_id: str = ""
    token_budget: int = 0
    rendered_text: str = ""
    sections: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    checksum: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorAction:
    action_id: str
    action_name: str
    actor: str
    session_id: str = ""
    task_id: str = ""
    run_id: str = ""
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


def _row_to_session(row: sqlite3.Row | aiosqlite.Row) -> SessionState:
    return SessionState(
        session_id=str(row["session_id"]),
        operator_id=str(row["operator_id"] or ""),
        status=str(row["status"]),
        current_task_id=str(row["current_task_id"] or ""),
        active_bundle_id=str(row["active_bundle_id"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


def _row_to_claim(row: sqlite3.Row | aiosqlite.Row) -> TaskClaim:
    return TaskClaim(
        claim_id=str(row["claim_id"]),
        task_id=str(row["task_id"]),
        agent_id=str(row["agent_id"]),
        status=str(row["status"]),
        session_id=str(row["session_id"] or ""),
        claimed_at=_parse_dt(row["claimed_at"]) or _utc_now(),
        acked_at=_parse_dt(row["acked_at"]),
        heartbeat_at=_parse_dt(row["heartbeat_at"]),
        stale_after=_parse_dt(row["stale_after"]),
        recovered_at=_parse_dt(row["recovered_at"]),
        retry_count=int(row["retry_count"] or 0),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _row_to_run(row: sqlite3.Row | aiosqlite.Row) -> DelegationRun:
    return DelegationRun(
        run_id=str(row["run_id"]),
        task_id=str(row["task_id"]),
        assigned_to=str(row["assigned_to"]),
        status=str(row["status"]),
        session_id=str(row["session_id"] or ""),
        claim_id=str(row["claim_id"] or ""),
        parent_run_id=str(row["parent_run_id"] or ""),
        assigned_by=str(row["assigned_by"] or ""),
        requested_output=list(_json_load(row["requested_output_json"], [])),
        current_artifact_id=str(row["current_artifact_id"] or ""),
        started_at=_parse_dt(row["started_at"]) or _utc_now(),
        completed_at=_parse_dt(row["completed_at"]),
        failure_code=str(row["failure_code"] or ""),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _row_to_lease(row: sqlite3.Row | aiosqlite.Row) -> WorkspaceLease:
    return WorkspaceLease(
        lease_id=str(row["lease_id"]),
        zone_path=str(row["zone_path"]),
        mode=str(row["mode"]),
        holder_run_id=str(row["holder_run_id"] or ""),
        base_hash=str(row["base_hash"] or ""),
        acquired_at=_parse_dt(row["acquired_at"]) or _utc_now(),
        expires_at=_parse_dt(row["expires_at"]),
        released_at=_parse_dt(row["released_at"]),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _row_to_artifact(row: sqlite3.Row | aiosqlite.Row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=str(row["artifact_id"]),
        artifact_kind=str(row["artifact_kind"]),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        manifest_path=str(row["manifest_path"] or ""),
        payload_path=str(row["payload_path"] or ""),
        checksum=str(row["checksum"] or ""),
        parent_artifact_id=str(row["parent_artifact_id"] or ""),
        promotion_state=str(row["promotion_state"] or "ephemeral"),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _row_to_memory_fact(row: sqlite3.Row | aiosqlite.Row) -> MemoryFact:
    return MemoryFact(
        fact_id=str(row["fact_id"]),
        fact_kind=str(row["fact_kind"]),
        truth_state=str(row["truth_state"]),
        text=str(row["text"]),
        confidence=float(row["confidence"] or 0.0),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        valid_from=_parse_dt(row["valid_from"]),
        valid_to=_parse_dt(row["valid_to"]),
        source_event_id=str(row["source_event_id"] or ""),
        source_artifact_id=str(row["source_artifact_id"] or ""),
        provenance=_json_load(row["provenance_json"], {}),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


def _row_to_context_bundle(row: sqlite3.Row | aiosqlite.Row) -> ContextBundleRecord:
    return ContextBundleRecord(
        bundle_id=str(row["bundle_id"]),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        token_budget=int(row["token_budget"] or 0),
        rendered_text=str(row["rendered_text"] or ""),
        sections=list(_json_load(row["sections_json"], [])),
        source_refs=list(_json_load(row["source_refs_json"], [])),
        checksum=str(row["checksum"] or ""),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _row_to_operator_action(row: sqlite3.Row | aiosqlite.Row) -> OperatorAction:
    return OperatorAction(
        action_id=str(row["action_id"]),
        action_name=str(row["action_name"]),
        actor=str(row["actor"]),
        session_id=str(row["session_id"] or ""),
        task_id=str(row["task_id"] or ""),
        run_id=str(row["run_id"] or ""),
        reason=str(row["reason"] or ""),
        payload=_json_load(row["payload_json"], {}),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
    )


class RuntimeStateStore:
    """WAL-backed SQLite store for live runtime truth."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        include_memory_plane: bool = True,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_RUNTIME_DB)
        self.include_memory_plane = include_memory_plane

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await ensure_runtime_state_schema_async(
                db,
                include_memory_plane=self.include_memory_plane,
            )

    async def upsert_session(self, session: SessionState) -> SessionState:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (session_id, operator_id, status, current_task_id,"
                " active_bundle_id, metadata_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                " operator_id = excluded.operator_id,"
                " status = excluded.status,"
                " current_task_id = excluded.current_task_id,"
                " active_bundle_id = excluded.active_bundle_id,"
                " metadata_json = excluded.metadata_json,"
                " updated_at = excluded.updated_at",
                (
                    session.session_id,
                    session.operator_id,
                    session.status,
                    session.current_task_id,
                    session.active_bundle_id,
                    _json_dump(session.metadata),
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
            await db.commit()
        loaded = await self.get_session(session.session_id)
        assert loaded is not None
        return loaded

    async def get_session(self, session_id: str) -> SessionState | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT session_id, operator_id, status, current_task_id,"
                    " active_bundle_id, metadata_json, created_at, updated_at"
                    " FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    async def record_task_claim(self, claim: TaskClaim) -> TaskClaim:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO task_claims (claim_id, task_id, session_id, agent_id, status,"
                " claimed_at, acked_at, heartbeat_at, stale_after, recovered_at,"
                " retry_count, metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(claim_id) DO UPDATE SET"
                " task_id = excluded.task_id,"
                " session_id = excluded.session_id,"
                " agent_id = excluded.agent_id,"
                " status = excluded.status,"
                " claimed_at = excluded.claimed_at,"
                " acked_at = excluded.acked_at,"
                " heartbeat_at = excluded.heartbeat_at,"
                " stale_after = excluded.stale_after,"
                " recovered_at = excluded.recovered_at,"
                " retry_count = excluded.retry_count,"
                " metadata_json = excluded.metadata_json",
                (
                    claim.claim_id,
                    claim.task_id,
                    claim.session_id,
                    claim.agent_id,
                    claim.status,
                    claim.claimed_at.isoformat(),
                    claim.acked_at.isoformat() if claim.acked_at else None,
                    claim.heartbeat_at.isoformat() if claim.heartbeat_at else None,
                    claim.stale_after.isoformat() if claim.stale_after else None,
                    claim.recovered_at.isoformat() if claim.recovered_at else None,
                    int(claim.retry_count),
                    _json_dump(claim.metadata),
                ),
            )
            await db.commit()
        loaded = await self.get_task_claim(claim.claim_id)
        assert loaded is not None
        return loaded

    async def get_task_claim(self, claim_id: str) -> TaskClaim | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT claim_id, task_id, session_id, agent_id, status, claimed_at,"
                    " acked_at, heartbeat_at, stale_after, recovered_at, retry_count,"
                    " metadata_json FROM task_claims WHERE claim_id = ?",
                    (claim_id,),
                )
            ).fetchone()
        return _row_to_claim(row) if row is not None else None

    async def acknowledge_task_claim(
        self,
        claim_id: str,
        *,
        status: str = "acknowledged",
        acknowledged_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskClaim:
        existing = await self.get_task_claim(claim_id)
        if existing is None:
            raise KeyError(f"claim {claim_id} not found")
        merged_metadata = {**existing.metadata, **(metadata or {})}
        acked_at = acknowledged_at or _utc_now()
        updated = TaskClaim(
            claim_id=existing.claim_id,
            task_id=existing.task_id,
            agent_id=existing.agent_id,
            status=status,
            session_id=existing.session_id,
            claimed_at=existing.claimed_at,
            acked_at=acked_at,
            heartbeat_at=existing.heartbeat_at or acked_at,
            stale_after=existing.stale_after,
            recovered_at=existing.recovered_at,
            retry_count=existing.retry_count,
            metadata=merged_metadata,
        )
        return await self.record_task_claim(updated)

    async def heartbeat_task_claim(
        self,
        claim_id: str,
        *,
        heartbeat_at: datetime | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskClaim:
        existing = await self.get_task_claim(claim_id)
        if existing is None:
            raise KeyError(f"claim {claim_id} not found")
        beat_at = heartbeat_at or _utc_now()
        merged_metadata = {**existing.metadata, **(metadata or {})}
        updated = TaskClaim(
            claim_id=existing.claim_id,
            task_id=existing.task_id,
            agent_id=existing.agent_id,
            status=status or existing.status,
            session_id=existing.session_id,
            claimed_at=existing.claimed_at,
            acked_at=existing.acked_at,
            heartbeat_at=beat_at,
            stale_after=existing.stale_after,
            recovered_at=existing.recovered_at,
            retry_count=existing.retry_count,
            metadata=merged_metadata,
        )
        return await self.record_task_claim(updated)

    async def record_delegation_run(self, run: DelegationRun) -> DelegationRun:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO delegation_runs (run_id, session_id, task_id, claim_id,"
                " parent_run_id, assigned_by, assigned_to, requested_output_json,"
                " current_artifact_id, status, started_at, completed_at, failure_code,"
                " metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(run_id) DO UPDATE SET"
                " session_id = excluded.session_id,"
                " task_id = excluded.task_id,"
                " claim_id = excluded.claim_id,"
                " parent_run_id = excluded.parent_run_id,"
                " assigned_by = excluded.assigned_by,"
                " assigned_to = excluded.assigned_to,"
                " requested_output_json = excluded.requested_output_json,"
                " current_artifact_id = excluded.current_artifact_id,"
                " status = excluded.status,"
                " started_at = excluded.started_at,"
                " completed_at = excluded.completed_at,"
                " failure_code = excluded.failure_code,"
                " metadata_json = excluded.metadata_json",
                (
                    run.run_id,
                    run.session_id,
                    run.task_id,
                    run.claim_id,
                    run.parent_run_id,
                    run.assigned_by,
                    run.assigned_to,
                    _json_dump(run.requested_output),
                    run.current_artifact_id,
                    run.status,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.failure_code,
                    _json_dump(run.metadata),
                ),
            )
            await db.commit()
        loaded = await self.get_delegation_run(run.run_id)
        assert loaded is not None
        return loaded

    async def get_delegation_run(self, run_id: str) -> DelegationRun | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT run_id, session_id, task_id, claim_id, parent_run_id,"
                    " assigned_by, assigned_to, requested_output_json,"
                    " current_artifact_id, status, started_at, completed_at,"
                    " failure_code, metadata_json FROM delegation_runs WHERE run_id = ?",
                    (run_id,),
                )
            ).fetchone()
        return _row_to_run(row) if row is not None else None

    async def list_delegation_runs(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[DelegationRun]:
        await self.init_db()
        query = (
            "SELECT run_id, session_id, task_id, claim_id, parent_run_id, assigned_by,"
            " assigned_to, requested_output_json, current_artifact_id, status,"
            " started_at, completed_at, failure_code, metadata_json"
            " FROM delegation_runs WHERE 1=1"
        )
        params: list[Any] = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_run(row) for row in rows]

    async def record_workspace_lease(self, lease: WorkspaceLease) -> WorkspaceLease:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO workspace_leases (lease_id, zone_path, holder_run_id, mode,"
                " base_hash, acquired_at, expires_at, released_at, metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(lease_id) DO UPDATE SET"
                " zone_path = excluded.zone_path,"
                " holder_run_id = excluded.holder_run_id,"
                " mode = excluded.mode,"
                " base_hash = excluded.base_hash,"
                " acquired_at = excluded.acquired_at,"
                " expires_at = excluded.expires_at,"
                " released_at = excluded.released_at,"
                " metadata_json = excluded.metadata_json",
                (
                    lease.lease_id,
                    lease.zone_path,
                    lease.holder_run_id,
                    lease.mode,
                    lease.base_hash,
                    lease.acquired_at.isoformat(),
                    lease.expires_at.isoformat() if lease.expires_at else None,
                    lease.released_at.isoformat() if lease.released_at else None,
                    _json_dump(lease.metadata),
                ),
            )
            await db.commit()
        loaded = await self.get_workspace_lease(lease.lease_id)
        assert loaded is not None
        return loaded

    async def get_workspace_lease(self, lease_id: str) -> WorkspaceLease | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT lease_id, zone_path, holder_run_id, mode, base_hash,"
                    " acquired_at, expires_at, released_at, metadata_json"
                    " FROM workspace_leases WHERE lease_id = ?",
                    (lease_id,),
                )
            ).fetchone()
        return _row_to_lease(row) if row is not None else None

    async def list_workspace_leases(
        self,
        *,
        holder_run_id: str | None = None,
        active_only: bool = True,
        limit: int = 20,
    ) -> list[WorkspaceLease]:
        await self.init_db()
        query = (
            "SELECT lease_id, zone_path, holder_run_id, mode, base_hash, acquired_at,"
            " expires_at, released_at, metadata_json FROM workspace_leases WHERE 1=1"
        )
        params: list[Any] = []
        if holder_run_id is not None:
            query += " AND holder_run_id = ?"
            params.append(holder_run_id)
        if active_only:
            query += " AND released_at IS NULL"
        query += " ORDER BY acquired_at DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_lease(row) for row in rows]

    async def release_workspace_lease(
        self,
        lease_id: str,
        *,
        released_at: datetime | None = None,
    ) -> WorkspaceLease:
        existing = await self.get_workspace_lease(lease_id)
        if existing is None:
            raise KeyError(f"lease {lease_id} not found")
        released = WorkspaceLease(
            lease_id=existing.lease_id,
            zone_path=existing.zone_path,
            mode=existing.mode,
            holder_run_id=existing.holder_run_id,
            base_hash=existing.base_hash,
            acquired_at=existing.acquired_at,
            expires_at=existing.expires_at,
            released_at=released_at or _utc_now(),
            metadata=existing.metadata,
        )
        return await self.record_workspace_lease(released)

    async def record_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO artifact_records (artifact_id, session_id, task_id, run_id,"
                " artifact_kind, manifest_path, payload_path, checksum,"
                " parent_artifact_id, promotion_state, created_at, metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(artifact_id) DO UPDATE SET"
                " session_id = excluded.session_id,"
                " task_id = excluded.task_id,"
                " run_id = excluded.run_id,"
                " artifact_kind = excluded.artifact_kind,"
                " manifest_path = excluded.manifest_path,"
                " payload_path = excluded.payload_path,"
                " checksum = excluded.checksum,"
                " parent_artifact_id = excluded.parent_artifact_id,"
                " promotion_state = excluded.promotion_state,"
                " created_at = excluded.created_at,"
                " metadata_json = excluded.metadata_json",
                (
                    artifact.artifact_id,
                    artifact.session_id,
                    artifact.task_id,
                    artifact.run_id,
                    artifact.artifact_kind,
                    artifact.manifest_path,
                    artifact.payload_path,
                    artifact.checksum,
                    artifact.parent_artifact_id,
                    artifact.promotion_state,
                    artifact.created_at.isoformat(),
                    _json_dump(artifact.metadata),
                ),
            )
            await db.commit()
        loaded = await self.get_artifact(artifact.artifact_id)
        assert loaded is not None
        return loaded

    async def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT artifact_id, session_id, task_id, run_id, artifact_kind,"
                    " manifest_path, payload_path, checksum, parent_artifact_id,"
                    " promotion_state, created_at, metadata_json"
                    " FROM artifact_records WHERE artifact_id = ?",
                    (artifact_id,),
                )
            ).fetchone()
        return _row_to_artifact(row) if row is not None else None

    async def list_artifacts(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        promotion_state: str | None = None,
        limit: int = 20,
    ) -> list[ArtifactRecord]:
        await self.init_db()
        query = (
            "SELECT artifact_id, session_id, task_id, run_id, artifact_kind,"
            " manifest_path, payload_path, checksum, parent_artifact_id,"
            " promotion_state, created_at, metadata_json"
            " FROM artifact_records WHERE 1=1"
        )
        params: list[Any] = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        if promotion_state is not None:
            query += " AND promotion_state = ?"
            params.append(promotion_state)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_artifact(row) for row in rows]

    async def record_memory_fact(self, fact: MemoryFact) -> MemoryFact:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memory_facts (fact_id, session_id, task_id, fact_kind,"
                " truth_state, text, confidence, valid_from, valid_to, source_event_id,"
                " source_artifact_id, provenance_json, metadata_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(fact_id) DO UPDATE SET"
                " session_id = excluded.session_id,"
                " task_id = excluded.task_id,"
                " fact_kind = excluded.fact_kind,"
                " truth_state = excluded.truth_state,"
                " text = excluded.text,"
                " confidence = excluded.confidence,"
                " valid_from = excluded.valid_from,"
                " valid_to = excluded.valid_to,"
                " source_event_id = excluded.source_event_id,"
                " source_artifact_id = excluded.source_artifact_id,"
                " provenance_json = excluded.provenance_json,"
                " metadata_json = excluded.metadata_json,"
                " created_at = excluded.created_at,"
                " updated_at = excluded.updated_at",
                (
                    fact.fact_id,
                    fact.session_id,
                    fact.task_id,
                    fact.fact_kind,
                    fact.truth_state,
                    fact.text,
                    float(fact.confidence),
                    fact.valid_from.isoformat() if fact.valid_from else None,
                    fact.valid_to.isoformat() if fact.valid_to else None,
                    fact.source_event_id,
                    fact.source_artifact_id,
                    _json_dump(fact.provenance),
                    _json_dump(fact.metadata),
                    fact.created_at.isoformat(),
                    fact.updated_at.isoformat(),
                ),
            )
            await db.commit()
        loaded = await self.get_memory_fact(fact.fact_id)
        assert loaded is not None
        return loaded

    async def get_memory_fact(self, fact_id: str) -> MemoryFact | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT fact_id, session_id, task_id, fact_kind, truth_state, text,"
                    " confidence, valid_from, valid_to, source_event_id,"
                    " source_artifact_id, provenance_json, metadata_json,"
                    " created_at, updated_at FROM memory_facts WHERE fact_id = ?",
                    (fact_id,),
                )
            ).fetchone()
        return _row_to_memory_fact(row) if row is not None else None

    async def list_memory_facts(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        truth_state: str | None = None,
        limit: int = 20,
    ) -> list[MemoryFact]:
        await self.init_db()
        query = (
            "SELECT fact_id, session_id, task_id, fact_kind, truth_state, text,"
            " confidence, valid_from, valid_to, source_event_id, source_artifact_id,"
            " provenance_json, metadata_json, created_at, updated_at"
            " FROM memory_facts WHERE 1=1"
        )
        params: list[Any] = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if truth_state is not None:
            query += " AND truth_state = ?"
            params.append(truth_state)
        query += " ORDER BY updated_at DESC, confidence DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_memory_fact(row) for row in rows]

    async def update_memory_fact_truth(
        self,
        fact_id: str,
        *,
        truth_state: str,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryFact:
        existing = await self.get_memory_fact(fact_id)
        if existing is None:
            raise KeyError(f"fact {fact_id} not found")
        updated = MemoryFact(
            fact_id=existing.fact_id,
            session_id=existing.session_id,
            task_id=existing.task_id,
            fact_kind=existing.fact_kind,
            truth_state=truth_state,
            text=existing.text,
            confidence=existing.confidence if confidence is None else float(confidence),
            valid_from=existing.valid_from,
            valid_to=existing.valid_to,
            source_event_id=existing.source_event_id,
            source_artifact_id=existing.source_artifact_id,
            provenance=existing.provenance,
            metadata={**existing.metadata, **(metadata or {})},
            created_at=existing.created_at,
            updated_at=_utc_now(),
        )
        return await self.record_memory_fact(updated)

    async def record_memory_edge(self, edge: MemoryEdge) -> MemoryEdge:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO memory_edges (edge_id, from_fact_id, to_fact_id,"
                " relation, weight, source_event_id, metadata_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    edge.edge_id,
                    edge.from_fact_id,
                    edge.to_fact_id,
                    edge.relation,
                    float(edge.weight),
                    edge.source_event_id,
                    _json_dump(edge.metadata),
                    edge.created_at.isoformat(),
                ),
            )
            await db.commit()
        return edge

    async def record_context_bundle(self, bundle: ContextBundleRecord) -> ContextBundleRecord:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO context_bundles (bundle_id, session_id, task_id,"
                " run_id, token_budget, rendered_text, sections_json, source_refs_json,"
                " checksum, created_at, metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bundle.bundle_id,
                    bundle.session_id,
                    bundle.task_id,
                    bundle.run_id,
                    int(bundle.token_budget),
                    bundle.rendered_text,
                    _json_dump(bundle.sections),
                    _json_dump(bundle.source_refs),
                    bundle.checksum,
                    bundle.created_at.isoformat(),
                    _json_dump(bundle.metadata),
                ),
            )
            await db.commit()
        loaded = await self.get_context_bundle(bundle.bundle_id)
        assert loaded is not None
        return loaded

    async def get_context_bundle(self, bundle_id: str) -> ContextBundleRecord | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT bundle_id, session_id, task_id, run_id, token_budget,"
                    " rendered_text, sections_json, source_refs_json, checksum,"
                    " created_at, metadata_json FROM context_bundles WHERE bundle_id = ?",
                    (bundle_id,),
                )
            ).fetchone()
        return _row_to_context_bundle(row) if row is not None else None

    async def list_context_bundles(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        limit: int = 20,
    ) -> list[ContextBundleRecord]:
        await self.init_db()
        query = (
            "SELECT bundle_id, session_id, task_id, run_id, token_budget,"
            " rendered_text, sections_json, source_refs_json, checksum,"
            " created_at, metadata_json FROM context_bundles WHERE 1=1"
        )
        params: list[Any] = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_context_bundle(row) for row in rows]

    async def record_operator_action(self, action: OperatorAction) -> OperatorAction:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO operator_actions (action_id, session_id, task_id,"
                " run_id, action_name, actor, reason, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    action.action_id,
                    action.session_id,
                    action.task_id,
                    action.run_id,
                    action.action_name,
                    action.actor,
                    action.reason,
                    _json_dump(action.payload),
                    action.created_at.isoformat(),
                ),
            )
            await db.commit()
        loaded = await self.get_operator_action(action.action_id)
        assert loaded is not None
        return loaded

    async def get_operator_action(self, action_id: str) -> OperatorAction | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT action_id, session_id, task_id, run_id, action_name, actor,"
                    " reason, payload_json, created_at FROM operator_actions"
                    " WHERE action_id = ?",
                    (action_id,),
                )
            ).fetchone()
        return _row_to_operator_action(row) if row is not None else None

    async def list_operator_actions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        limit: int = 20,
    ) -> list[OperatorAction]:
        await self.init_db()
        query = (
            "SELECT action_id, session_id, task_id, run_id, action_name, actor,"
            " reason, payload_json, created_at FROM operator_actions WHERE 1=1"
        )
        params: list[Any] = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [_row_to_operator_action(row) for row in rows]

    @staticmethod
    def new_session_id() -> str:
        return _new_id("session")

    @staticmethod
    def new_claim_id() -> str:
        return _new_id("claim")

    @staticmethod
    def new_run_id() -> str:
        return _new_id("run")

    @staticmethod
    def new_lease_id() -> str:
        return _new_id("lease")

    @staticmethod
    def new_artifact_id() -> str:
        return _new_id("art")

    @staticmethod
    def new_fact_id() -> str:
        return _new_id("fact")

    @staticmethod
    def new_edge_id() -> str:
        return _new_id("edge")

    @staticmethod
    def new_bundle_id() -> str:
        return _new_id("ctx")

    @staticmethod
    def new_action_id() -> str:
        return _new_id("act")
