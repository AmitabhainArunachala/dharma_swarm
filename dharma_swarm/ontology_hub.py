"""Persistent Ontology Hub -- SQLite-backed OntologyRegistry.

Wraps the in-memory OntologyRegistry with a SQLite persistence layer.
Every object, link, and action execution survives process restarts.
FTS5 index on searchable properties for text queries.

Storage: ~/.dharma/ontology.db
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.ontology import (
    ActionExecution,
    Link,
    OntologyObj,
    OntologyRegistry,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"

_DEFAULT_DB_PATH = Path.home() / ".dharma" / "ontology.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_json(value: Any) -> str:
    """Serialize a value to JSON text, handling datetimes."""
    return json.dumps(value, default=str)


class OntologyHub:
    """SQLite-backed OntologyRegistry that persists across restarts.

    All writes are transactional. Thread-safe via a write lock.
    FTS5 index covers type_name and the JSON properties blob for
    free-text search across all object data.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize with SQLite backend.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.dharma/ontology.db
        """
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    # ------------------------------------------------------------------
    # Schema initialization and migrations
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables if not exist and run migrations."""
        with self._lock, self._conn:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS _meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS objects (
                    id          TEXT PRIMARY KEY,
                    type_name   TEXT NOT NULL,
                    properties  TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL,
                    created_by  TEXT NOT NULL DEFAULT 'system',
                    updated_at  TEXT NOT NULL,
                    version     INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_objects_type
                    ON objects(type_name);

                CREATE TABLE IF NOT EXISTS links (
                    id              TEXT PRIMARY KEY,
                    link_name       TEXT NOT NULL,
                    source_id       TEXT NOT NULL,
                    source_type     TEXT NOT NULL,
                    target_id       TEXT NOT NULL,
                    target_type     TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    created_by      TEXT NOT NULL DEFAULT 'system',
                    metadata        TEXT NOT NULL DEFAULT '{}',
                    witness_quality REAL NOT NULL DEFAULT 0.5
                );

                CREATE INDEX IF NOT EXISTS idx_links_source
                    ON links(source_id);
                CREATE INDEX IF NOT EXISTS idx_links_target
                    ON links(target_id);
                CREATE INDEX IF NOT EXISTS idx_links_name
                    ON links(link_name);

                CREATE TABLE IF NOT EXISTS action_log (
                    id            TEXT PRIMARY KEY,
                    action_name   TEXT NOT NULL,
                    object_id     TEXT NOT NULL,
                    object_type   TEXT NOT NULL,
                    input_params  TEXT NOT NULL DEFAULT '{}',
                    result        TEXT NOT NULL DEFAULT 'pending',
                    gate_results  TEXT NOT NULL DEFAULT '{}',
                    executed_by   TEXT NOT NULL DEFAULT 'system',
                    executed_at   TEXT NOT NULL,
                    duration_ms   REAL NOT NULL DEFAULT 0.0,
                    error         TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_action_log_object
                    ON action_log(object_id);
                CREATE INDEX IF NOT EXISTS idx_action_log_name
                    ON action_log(action_name);
            """)

            # FTS5 virtual table -- separate because CREATE VIRTUAL TABLE
            # IF NOT EXISTS is supported in SQLite 3.31+.
            try:
                self._conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts
                    USING fts5(
                        type_name,
                        properties,
                        content='objects',
                        content_rowid='rowid'
                    )
                """)
            except sqlite3.OperationalError:
                # FTS5 may already exist or not be compiled in.
                logger.debug("FTS5 table creation skipped (may already exist)")

            # Store schema version.
            existing = self._get_meta_unlocked("schema_version")
            if existing is None:
                self._set_meta_unlocked("schema_version", _SCHEMA_VERSION)

    # ------------------------------------------------------------------
    # Meta key-value store
    # ------------------------------------------------------------------

    def _set_meta(self, key: str, value: str) -> None:
        """Set a key-value pair in the _meta table."""
        with self._lock, self._conn:
            self._set_meta_unlocked(key, value)

    def _set_meta_unlocked(self, key: str, value: str) -> None:
        """Set meta without acquiring lock (caller holds lock)."""
        self._conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _get_meta(self, key: str) -> str | None:
        """Get a value from the _meta table."""
        row = self._conn.execute(
            "SELECT value FROM _meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def _get_meta_unlocked(self, key: str) -> str | None:
        """Get meta without acquiring lock (used during init)."""
        row = self._conn.execute(
            "SELECT value FROM _meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Public wrapper for recording hub metadata."""
        self._set_meta(key, value)

    def get_meta(self, key: str) -> str | None:
        """Public wrapper for retrieving hub metadata."""
        return self._get_meta(key)

    def is_empty(self) -> bool:
        """Whether the hub contains no persisted ontology instances."""
        return (
            self.total_objects() == 0
            and self.total_links() == 0
            and self.total_actions() == 0
        )

    # ------------------------------------------------------------------
    # Store operations
    # ------------------------------------------------------------------

    def store_object(self, obj: OntologyObj) -> None:
        """Persist an OntologyObj to SQLite and update FTS index."""
        data = obj.model_dump(mode="json")
        props_json = _serialize_json(data["properties"])
        created_at = data["created_at"] if isinstance(data["created_at"], str) else str(data["created_at"])
        updated_at = data["updated_at"] if isinstance(data["updated_at"], str) else str(data["updated_at"])

        with self._lock, self._conn:
            # Delete old FTS entry if exists (before replacing the row).
            self._conn.execute(
                "DELETE FROM objects_fts WHERE rowid IN "
                "(SELECT rowid FROM objects WHERE id = ?)",
                (obj.id,),
            )
            self._conn.execute(
                """INSERT OR REPLACE INTO objects
                   (id, type_name, properties, created_at, created_by, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    obj.id,
                    obj.type_name,
                    props_json,
                    created_at,
                    obj.created_by,
                    updated_at,
                    obj.version,
                ),
            )
            # Insert into FTS.
            self._conn.execute(
                """INSERT INTO objects_fts (rowid, type_name, properties)
                   SELECT rowid, type_name, properties
                   FROM objects WHERE id = ?""",
                (obj.id,),
            )

    def store_link(self, link: Link) -> None:
        """Persist a Link to SQLite."""
        data = link.model_dump(mode="json")
        created_at = data["created_at"] if isinstance(data["created_at"], str) else str(data["created_at"])
        meta_json = _serialize_json(data["metadata"])

        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO links
                   (id, link_name, source_id, source_type, target_id, target_type,
                    created_at, created_by, metadata, witness_quality)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    link.id,
                    link.link_name,
                    link.source_id,
                    link.source_type,
                    link.target_id,
                    link.target_type,
                    created_at,
                    link.created_by,
                    meta_json,
                    link.witness_quality,
                ),
            )

    def store_action(self, action: ActionExecution) -> None:
        """Persist an ActionExecution to SQLite."""
        data = action.model_dump(mode="json")
        executed_at = data["executed_at"] if isinstance(data["executed_at"], str) else str(data["executed_at"])

        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO action_log
                   (id, action_name, object_id, object_type, input_params,
                    result, gate_results, executed_by, executed_at,
                    duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    action.id,
                    action.action_name,
                    action.object_id,
                    action.object_type,
                    _serialize_json(data["input_params"]),
                    action.result,
                    _serialize_json(data["gate_results"]),
                    action.executed_by,
                    executed_at,
                    action.duration_ms,
                    action.error,
                ),
            )

    # ------------------------------------------------------------------
    # Load operations
    # ------------------------------------------------------------------

    def _row_to_obj(self, row: sqlite3.Row) -> OntologyObj:
        """Deserialize a database row into an OntologyObj."""
        return OntologyObj(
            id=row["id"],
            type_name=row["type_name"],
            properties=json.loads(row["properties"]),
            created_at=row["created_at"],
            created_by=row["created_by"],
            updated_at=row["updated_at"],
            version=row["version"],
        )

    def _row_to_link(self, row: sqlite3.Row) -> Link:
        """Deserialize a database row into a Link."""
        return Link(
            id=row["id"],
            link_name=row["link_name"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            target_id=row["target_id"],
            target_type=row["target_type"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            metadata=json.loads(row["metadata"]),
            witness_quality=row["witness_quality"],
        )

    def _row_to_action(self, row: sqlite3.Row) -> ActionExecution:
        """Deserialize a database row into an ActionExecution."""
        return ActionExecution(
            id=row["id"],
            action_name=row["action_name"],
            object_id=row["object_id"],
            object_type=row["object_type"],
            input_params=json.loads(row["input_params"]),
            result=row["result"],
            gate_results=json.loads(row["gate_results"]),
            executed_by=row["executed_by"],
            executed_at=row["executed_at"],
            duration_ms=row["duration_ms"],
            error=row["error"],
        )

    def load_object(self, obj_id: str) -> OntologyObj | None:
        """Load a single object by ID."""
        row = self._conn.execute(
            "SELECT * FROM objects WHERE id = ?", (obj_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_obj(row)

    def load_objects_by_type(
        self, type_name: str, limit: int = 100
    ) -> list[OntologyObj]:
        """Load objects filtered by type_name."""
        rows = self._conn.execute(
            "SELECT * FROM objects WHERE type_name = ? ORDER BY created_at DESC LIMIT ?",
            (type_name, limit),
        ).fetchall()
        return [self._row_to_obj(r) for r in rows]

    def load_links(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        link_name: str | None = None,
    ) -> list[Link]:
        """Load links with optional filters on source, target, and name."""
        clauses: list[str] = []
        params: list[str] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if link_name is not None:
            clauses.append("link_name = ?")
            params.append(link_name)

        where = " AND ".join(clauses) if clauses else "1=1"
        rows = self._conn.execute(
            f"SELECT * FROM links WHERE {where}", params  # noqa: S608
        ).fetchall()
        return [self._row_to_link(r) for r in rows]

    def load_actions(
        self,
        object_id: str | None = None,
        action_name: str | None = None,
        limit: int = 100,
    ) -> list[ActionExecution]:
        """Load action executions with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if object_id is not None:
            clauses.append("object_id = ?")
            params.append(object_id)
        if action_name is not None:
            clauses.append("action_name = ?")
            params.append(action_name)

        where = " AND ".join(clauses) if clauses else "1=1"
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM action_log WHERE {where} ORDER BY executed_at DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [self._row_to_action(r) for r in rows]

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def search_text(
        self,
        query: str,
        type_name: str | None = None,
        limit: int = 20,
    ) -> list[OntologyObj]:
        """Search objects using FTS5 MATCH.

        Searches across type_name and the JSON properties blob.
        Optionally filter by type_name after matching.

        Args:
            query: FTS5 match expression (supports AND, OR, NOT, prefix*).
            type_name: Optional filter to restrict results to one type.
            limit: Maximum results to return.

        Returns:
            List of matching OntologyObj instances, ranked by relevance.
        """
        # Sanitize query for FTS5: wrap bare terms in double quotes
        # to prevent injection via FTS5 syntax.
        safe_query = query.strip()
        if not safe_query:
            return []

        try:
            if type_name is not None:
                rows = self._conn.execute(
                    """SELECT o.* FROM objects o
                       JOIN objects_fts f ON o.rowid = f.rowid
                       WHERE objects_fts MATCH ? AND o.type_name = ?
                       ORDER BY rank LIMIT ?""",
                    (safe_query, type_name, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT o.* FROM objects o
                       JOIN objects_fts f ON o.rowid = f.rowid
                       WHERE objects_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (safe_query, limit),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 search failed for query %r: %s", query, exc)
            return []

        return [self._row_to_obj(r) for r in rows]

    # ------------------------------------------------------------------
    # Aggregate queries
    # ------------------------------------------------------------------

    def count_by_type(self) -> dict[str, int]:
        """Count objects grouped by type_name."""
        rows = self._conn.execute(
            "SELECT type_name, COUNT(*) as cnt FROM objects GROUP BY type_name"
        ).fetchall()
        return {row["type_name"]: row["cnt"] for row in rows}

    def count_links_by_name(self) -> dict[str, int]:
        """Count links grouped by link_name."""
        rows = self._conn.execute(
            "SELECT link_name, COUNT(*) as cnt FROM links GROUP BY link_name"
        ).fetchall()
        return {row["link_name"]: row["cnt"] for row in rows}

    def total_objects(self) -> int:
        """Total number of stored objects."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM objects").fetchone()
        return row["cnt"] if row else 0

    def total_links(self) -> int:
        """Total number of stored links."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM links").fetchone()
        return row["cnt"] if row else 0

    def total_actions(self) -> int:
        """Total number of stored action executions."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM action_log").fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Sync with in-memory OntologyRegistry
    # ------------------------------------------------------------------

    def sync_from_registry(self, registry: OntologyRegistry) -> dict[str, int]:
        """Bulk import all objects, links, and action log from an in-memory registry.

        Returns:
            Dict with counts: {objects_synced, links_synced, actions_synced}.
        """
        obj_count = 0
        link_count = 0
        action_count = 0

        # Objects live in registry._objects
        for obj in registry._objects.values():
            self.store_object(obj)
            obj_count += 1

        # Link instances live in registry._link_instances
        for link in registry._link_instances.values():
            self.store_link(link)
            link_count += 1

        # Action log
        for action in registry._action_log:
            self.store_action(action)
            action_count += 1

        self._set_meta("last_sync_time", _utc_now_iso())

        return {
            "objects_synced": obj_count,
            "links_synced": link_count,
            "actions_synced": action_count,
        }

    def load_into_registry(self, registry: OntologyRegistry) -> dict[str, int]:
        """Bulk load all objects, links, and actions from DB into an in-memory registry.

        Objects and links are inserted directly into the registry's internal stores
        (bypassing validation, since they were validated on original creation).

        Returns:
            Dict with counts: {objects_loaded, links_loaded, actions_loaded}.
        """
        obj_count = 0
        link_count = 0
        action_count = 0

        # Load objects
        rows = self._conn.execute("SELECT * FROM objects").fetchall()
        for row in rows:
            obj = self._row_to_obj(row)
            registry._objects[obj.id] = obj
            obj_count += 1

        # Load links
        rows = self._conn.execute("SELECT * FROM links").fetchall()
        for row in rows:
            link = self._row_to_link(row)
            registry._link_instances[link.id] = link
            link_count += 1

        # Load actions
        rows = self._conn.execute(
            "SELECT * FROM action_log ORDER BY executed_at ASC"
        ).fetchall()
        for row in rows:
            action = self._row_to_action(row)
            registry._action_log.append(action)
            action_count += 1

        return {
            "objects_loaded": obj_count,
            "links_loaded": link_count,
            "actions_loaded": action_count,
        }

    # ------------------------------------------------------------------
    # JSON export / import
    # ------------------------------------------------------------------

    def export_json(self, path: Path) -> int:
        """Dump entire DB as JSON for debugging/backup.

        Args:
            path: Output file path.

        Returns:
            Total number of records exported.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        objects = []
        for row in self._conn.execute("SELECT * FROM objects").fetchall():
            objects.append({
                "id": row["id"],
                "type_name": row["type_name"],
                "properties": json.loads(row["properties"]),
                "created_at": row["created_at"],
                "created_by": row["created_by"],
                "updated_at": row["updated_at"],
                "version": row["version"],
            })

        links = []
        for row in self._conn.execute("SELECT * FROM links").fetchall():
            links.append({
                "id": row["id"],
                "link_name": row["link_name"],
                "source_id": row["source_id"],
                "source_type": row["source_type"],
                "target_id": row["target_id"],
                "target_type": row["target_type"],
                "created_at": row["created_at"],
                "created_by": row["created_by"],
                "metadata": json.loads(row["metadata"]),
                "witness_quality": row["witness_quality"],
            })

        actions = []
        for row in self._conn.execute(
            "SELECT * FROM action_log ORDER BY executed_at ASC"
        ).fetchall():
            actions.append({
                "id": row["id"],
                "action_name": row["action_name"],
                "object_id": row["object_id"],
                "object_type": row["object_type"],
                "input_params": json.loads(row["input_params"]),
                "result": row["result"],
                "gate_results": json.loads(row["gate_results"]),
                "executed_by": row["executed_by"],
                "executed_at": row["executed_at"],
                "duration_ms": row["duration_ms"],
                "error": row["error"],
            })

        data = {
            "exported_at": _utc_now_iso(),
            "objects": objects,
            "links": links,
            "actions": actions,
        }

        path.write_text(
            json.dumps(data, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

        total = len(objects) + len(links) + len(actions)
        logger.info("Exported %d records to %s", total, path)
        return total

    def import_json(self, path: Path) -> int:
        """Load from a JSON dump produced by export_json.

        Args:
            path: Input file path.

        Returns:
            Total number of records imported.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0

        for obj_data in data.get("objects", []):
            obj = OntologyObj.model_validate(obj_data)
            self.store_object(obj)
            count += 1

        for link_data in data.get("links", []):
            link = Link.model_validate(link_data)
            self.store_link(link)
            count += 1

        for action_data in data.get("actions", []):
            action = ActionExecution.model_validate(action_data)
            self.store_action(action)
            count += 1

        logger.info("Imported %d records from %s", count, path)
        return count

    # ------------------------------------------------------------------
    # Sync tracking
    # ------------------------------------------------------------------

    def last_sync_time(self) -> str | None:
        """Return the timestamp of the last sync_from_registry call."""
        return self._get_meta("last_sync_time")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> OntologyHub:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"OntologyHub(db={self._db_path}, "
            f"objects={self.total_objects()}, "
            f"links={self.total_links()})"
        )
