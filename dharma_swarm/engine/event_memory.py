"""Replayable event memory for the canonical Memory Palace substrate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.db_utils import connect_async
from dharma_swarm.engine.knowledge_store import _jaccard, _tokenize
from dharma_swarm.runtime_contract import RuntimeEnvelope, validate_envelope

DEFAULT_MEMORY_PLANE_DB = Path.home() / ".dharma" / "db" / "memory_plane.db"

_EVENT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    emitted_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    ingested_at TEXT NOT NULL
)"""

_SOURCE_DOCUMENTS_DDL = """
CREATE TABLE IF NOT EXISTS source_documents (
    doc_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_SOURCE_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS source_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES source_documents(doc_id)
)"""

_INDEX_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS index_runs (
    run_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    stats_json TEXT NOT NULL
)"""

_RETRIEVAL_LOG_DDL = """
CREATE TABLE IF NOT EXISTS retrieval_log (
    feedback_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_path TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    record_text TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL,
    rank INTEGER NOT NULL,
    consumer TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    outcome TEXT,
    outcome_recorded_at TEXT,
    uptake_state TEXT,
    uptake_score REAL,
    uptake_recorded_at TEXT,
    uptake_evidence_json TEXT
)"""

_CONVERSATION_TURNS_DDL = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    flow_state TEXT NOT NULL,
    turn_index INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)"""

_IDEA_SHARDS_DDL = """
CREATE TABLE IF NOT EXISTS idea_shards (
    shard_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    shard_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    text TEXT NOT NULL,
    salience REAL NOT NULL,
    novelty REAL NOT NULL,
    flow_score REAL NOT NULL,
    source_span TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)"""

_IDEA_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS idea_links (
    link_id TEXT PRIMARY KEY,
    from_shard_id TEXT NOT NULL,
    to_shard_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)"""

_IDEA_UPTAKE_DDL = """
CREATE TABLE IF NOT EXISTS idea_uptake (
    uptake_id TEXT PRIMARY KEY,
    shard_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    uptake_kind TEXT NOT NULL,
    evidence_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_event_session_emitted ON event_log(session_id, emitted_at)",
    "CREATE INDEX IF NOT EXISTS idx_event_trace_emitted ON event_log(trace_id, emitted_at)",
    "CREATE INDEX IF NOT EXISTS idx_event_type_emitted ON event_log(event_type, emitted_at)",
    "CREATE INDEX IF NOT EXISTS idx_docs_kind_path ON source_documents(source_kind, source_path)",
    "CREATE INDEX IF NOT EXISTS idx_docs_hash ON source_documents(source_hash)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_doc_idx ON source_chunks(doc_id, chunk_index)",
    "CREATE INDEX IF NOT EXISTS idx_retrieval_consumer_time ON retrieval_log(consumer, retrieved_at)",
    "CREATE INDEX IF NOT EXISTS idx_retrieval_record_time ON retrieval_log(record_id, retrieved_at)",
    "CREATE INDEX IF NOT EXISTS idx_turn_session_time ON conversation_turns(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_turn_task_time ON conversation_turns(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_shard_task_state ON idea_shards(task_id, state, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_shard_session_state ON idea_shards(session_id, state, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_shard_state_created ON idea_shards(state, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_uptake_task_time ON idea_uptake(task_id, recorded_at)",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_memory_plane_schema_sync(db: Any) -> None:
    """Create the full phase-1 memory-plane schema with a sync SQLite connection."""
    for ddl in (
        _EVENT_LOG_DDL,
        _SOURCE_DOCUMENTS_DDL,
        _SOURCE_CHUNKS_DDL,
        _INDEX_RUNS_DDL,
        _RETRIEVAL_LOG_DDL,
        _CONVERSATION_TURNS_DDL,
        _IDEA_SHARDS_DDL,
        _IDEA_LINKS_DDL,
        _IDEA_UPTAKE_DDL,
    ):
        db.execute(ddl)
    for idx in _INDEXES:
        db.execute(idx)
    _ensure_retrieval_log_columns_sync(db)
    _ensure_source_documents_columns_sync(db)
    db.commit()


async def ensure_memory_plane_schema_async(db: aiosqlite.Connection) -> None:
    """Create the full phase-1 memory-plane schema with an async SQLite connection."""
    for ddl in (
        _EVENT_LOG_DDL,
        _SOURCE_DOCUMENTS_DDL,
        _SOURCE_CHUNKS_DDL,
        _INDEX_RUNS_DDL,
        _RETRIEVAL_LOG_DDL,
        _CONVERSATION_TURNS_DDL,
        _IDEA_SHARDS_DDL,
        _IDEA_LINKS_DDL,
        _IDEA_UPTAKE_DDL,
    ):
        await db.execute(ddl)
    for idx in _INDEXES:
        await db.execute(idx)
    await _ensure_retrieval_log_columns_async(db)
    await _ensure_source_documents_columns_async(db)
    await db.commit()


def _ensure_source_documents_columns_sync(db: Any) -> None:
    columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(source_documents)").fetchall()
    }
    if "source_confidence" not in columns:
        db.execute(
            "ALTER TABLE source_documents ADD COLUMN source_confidence REAL NOT NULL DEFAULT 1.0"
        )


async def _ensure_source_documents_columns_async(db: aiosqlite.Connection) -> None:
    rows = await (await db.execute("PRAGMA table_info(source_documents)")).fetchall()
    columns = {row[1] for row in rows}
    if "source_confidence" not in columns:
        await db.execute(
            "ALTER TABLE source_documents ADD COLUMN source_confidence REAL NOT NULL DEFAULT 1.0"
        )


def _ensure_retrieval_log_columns_sync(db: Any) -> None:
    columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(retrieval_log)").fetchall()
    }
    expected = {
        "task_id": "TEXT NOT NULL DEFAULT ''",
        "record_text": "TEXT NOT NULL DEFAULT ''",
        "outcome": "TEXT",
        "outcome_recorded_at": "TEXT",
        "uptake_state": "TEXT",
        "uptake_score": "REAL",
        "uptake_recorded_at": "TEXT",
        "uptake_evidence_json": "TEXT",
    }
    for name, ddl in expected.items():
        if name not in columns:
            db.execute(f"ALTER TABLE retrieval_log ADD COLUMN {name} {ddl}")


async def _ensure_retrieval_log_columns_async(db: aiosqlite.Connection) -> None:
    rows = await (await db.execute("PRAGMA table_info(retrieval_log)")).fetchall()
    columns = {row[1] for row in rows}
    expected = {
        "task_id": "TEXT NOT NULL DEFAULT ''",
        "record_text": "TEXT NOT NULL DEFAULT ''",
        "outcome": "TEXT",
        "outcome_recorded_at": "TEXT",
        "uptake_state": "TEXT",
        "uptake_score": "REAL",
        "uptake_recorded_at": "TEXT",
        "uptake_evidence_json": "TEXT",
    }
    for name, ddl in expected.items():
        if name not in columns:
            await db.execute(f"ALTER TABLE retrieval_log ADD COLUMN {name} {ddl}")


def _event_text(row: dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    payload_text = json.dumps(payload, sort_keys=True, ensure_ascii=True).replace("_", " ")
    return " ".join(
        [
            str(row.get("event_type", "")),
            str(row.get("source", "")),
            str(row.get("agent_id", "")),
            payload_text,
        ]
    ).strip()


def _score(query: str, text: str) -> float:
    normalized_query = query.replace("_", " ")
    normalized_text = text.replace("_", " ")
    tokens = _tokenize(normalized_query)
    score = _jaccard(tokens, _tokenize(normalized_text))
    if normalized_query and normalized_query.lower() in normalized_text.lower():
        score += 0.5
    return round(score, 4)


class EventMemoryStore:
    """Async replayable storage for runtime envelopes."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with connect_async(self.db_path) as db:
            await ensure_memory_plane_schema_async(db)

    async def ingest_envelope(self, envelope: RuntimeEnvelope | dict[str, Any]) -> bool:
        """Persist a validated envelope. Duplicate event IDs are ignored."""
        data = envelope.as_dict() if isinstance(envelope, RuntimeEnvelope) else dict(envelope)
        ok, _errors = validate_envelope(data)
        if not ok:
            return False

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with connect_async(self.db_path) as db:
            await ensure_memory_plane_schema_async(db)
            try:
                await db.execute(
                    "INSERT INTO event_log (event_id, session_id, trace_id, event_type,"
                    " source, agent_id, emitted_at, payload_json, checksum, ingested_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(data["event_id"]),
                        str(data["session_id"]),
                        str(data["trace_id"]),
                        str(data["event_type"]),
                        str(data["source"]),
                        str(data["agent_id"]),
                        str(data["emitted_at"]),
                        json.dumps(data["payload"], sort_keys=True, ensure_ascii=True),
                        str(data["checksum"]),
                        _utc_now_iso(),
                    ),
                )
            except aiosqlite.IntegrityError:
                return False
            await db.commit()
        return True

    async def replay_session(self, session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        return await self._replay("session_id", session_id, limit)

    async def replay_trace(self, trace_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        return await self._replay("trace_id", trace_id, limit)

    async def search_events(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search events by simple lexical scoring across type, source, agent, and payload."""
        async with connect_async(self.db_path) as db:
            await ensure_memory_plane_schema_async(db)
            rows = await (
                await db.execute(
                    "SELECT event_id, session_id, trace_id, event_type, source, agent_id,"
                    " emitted_at, payload_json, checksum FROM event_log ORDER BY emitted_at DESC"
                )
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            item = {
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "trace_id": row["trace_id"],
                "event_type": row["event_type"],
                "source": row["source"],
                "agent_id": row["agent_id"],
                "emitted_at": row["emitted_at"],
                "payload": payload,
                "checksum": row["checksum"],
            }
            score = _score(query, _event_text(item))
            if score > 0:
                results.append({**item, "score": score})
        results.sort(key=lambda item: (item["score"], item["emitted_at"]), reverse=True)
        return results[: max(1, limit)]

    async def _replay(self, column: str, value: str, limit: int) -> list[dict[str, Any]]:
        async with connect_async(self.db_path) as db:
            await ensure_memory_plane_schema_async(db)
            rows = await (
                await db.execute(
                    "SELECT event_id, session_id, trace_id, event_type, source, agent_id,"
                    " emitted_at, payload_json, checksum"
                    f" FROM event_log WHERE {column} = ?"
                    " ORDER BY emitted_at ASC, event_id ASC LIMIT ?",
                    (value, max(1, limit)),
                )
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "trace_id": row["trace_id"],
                "event_type": row["event_type"],
                "source": row["source"],
                "agent_id": row["agent_id"],
                "emitted_at": row["emitted_at"],
                "payload": json.loads(row["payload_json"]) if row["payload_json"] else {},
                "checksum": row["checksum"],
            }
            for row in rows
        ]
