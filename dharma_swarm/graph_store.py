"""Four-Graph Knowledge Architecture — Storage Layer (Phase 7.1/7.2).

This module implements the graph storage infrastructure for DHARMA SWARM's
Four-Graph Architecture: Code, Semantic, Runtime, and Telos graphs connected
by a Bridge layer of cross-graph edges.

The architecture draws from Stafford Beer's Viable System Model insight that
an organism requires distinct-but-coupled information substrates — structural,
metabolic, semantic, and teleological — rather than a single conflated
knowledge graph.  The Bridge layer is the connective tissue that transforms
four isolated graphs into a coherent multi-scale knowledge system.

The SQLite implementation uses recursive CTEs for graph traversal, FTS5 for
full-text search, and stores all four graphs in a single database file with
table-name prefixes to avoid ATTACH complexity.

See ``FOUR_GRAPH_ARCHITECTURE.md`` §II, §III, §VI for the full specification.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


# ── Abstract Base Class ───────────────────────────────────────────────────


class GraphStore(ABC):
    """Abstract interface for the Four-Graph storage backend.

    Concrete implementations must support four named graphs (code, semantic,
    runtime, telos) plus a cross-graph bridge layer.  The ABC intentionally
    uses plain ``dict`` for nodes and edges so that each graph can carry
    heterogeneous properties in a flexible JSON ``data`` column.
    """

    @abstractmethod
    def upsert_node(self, graph: str, node: dict) -> None:
        """Insert or update a node.  *node* must contain ``id``, ``kind``, ``name``."""
        ...

    @abstractmethod
    def upsert_edge(self, graph: str, edge: dict) -> None:
        """Insert or update an edge.  *edge* must contain ``source_id``, ``target_id``, ``kind``."""
        ...

    @abstractmethod
    def get_node(self, graph: str, node_id: str) -> dict | None:
        """Return a single node by ID, or ``None``."""
        ...

    @abstractmethod
    def get_edges(
        self,
        graph: str,
        node_id: str,
        direction: str = "both",
        edge_kinds: list[str] | None = None,
    ) -> list[dict]:
        """Return edges touching *node_id*.  *direction*: ``out``, ``in``, or ``both``."""
        ...

    @abstractmethod
    def traverse(
        self,
        graph: str,
        start_id: str,
        edge_kinds: list[str],
        max_depth: int = 3,
    ) -> list[dict]:
        """BFS/recursive traversal returning nodes with ``depth``."""
        ...

    @abstractmethod
    def delete_node(self, graph: str, node_id: str) -> bool:
        """Delete a node and its incident edges.  Returns ``True`` if found."""
        ...

    @abstractmethod
    def delete_edge(self, graph: str, source_id: str, target_id: str, kind: str) -> bool:
        """Delete a specific edge.  Returns ``True`` if found."""
        ...

    @abstractmethod
    def search_nodes(self, graph: str, query: str, limit: int = 10) -> list[dict]:
        """Full-text search over node names and data via FTS5."""
        ...

    @abstractmethod
    def count_nodes(self, graph: str) -> int: ...

    @abstractmethod
    def count_edges(self, graph: str) -> int: ...

    # ── Bridge operations ─────────────────────────────────────────────

    @abstractmethod
    def upsert_bridge(self, edge: dict) -> None:
        """Insert or update a cross-graph bridge edge."""
        ...

    @abstractmethod
    def get_bridges(
        self,
        source_graph: str | None = None,
        source_id: str | None = None,
        target_graph: str | None = None,
        target_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict]:
        """Query bridge edges with optional filters."""
        ...

    @abstractmethod
    def delete_bridge(self, bridge_id: str) -> bool:
        """Delete a bridge edge by ID.  Returns ``True`` if found."""
        ...


# ── SQLite Implementation ─────────────────────────────────────────────────


class SQLiteGraphStore(GraphStore):
    """SQLite-backed Four-Graph store using recursive CTEs for traversal.

    All four graphs live in a **single** database file with table-name
    prefixes (``code_nodes``, ``semantic_edges``, …).  The bridge layer is
    stored in a ``bridge_edges`` table.  FTS5 virtual tables provide
    full-text search on node names and data.

    Thread-safety is achieved via ``check_same_thread=False``; callers are
    expected to serialise writes if concurrent mutation is needed (SQLite's
    WAL mode handles concurrent reads safely).
    """

    GRAPHS: tuple[str, ...] = ("code", "semantic", "runtime", "telos")

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── Context manager ───────────────────────────────────────────────

    def __enter__(self) -> SQLiteGraphStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    # ── Schema initialisation ─────────────────────────────────────────

    def _init_schema(self) -> None:
        """Create all tables, indexes, and FTS5 virtual tables if they don't exist."""
        cur = self._conn.cursor()
        for g in self.GRAPHS:
            cur.executescript(f"""
                CREATE TABLE IF NOT EXISTS {g}_nodes (
                    id      TEXT PRIMARY KEY,
                    kind    TEXT NOT NULL,
                    name    TEXT NOT NULL,
                    data    TEXT DEFAULT '{{}}',
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {g}_edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    kind      TEXT NOT NULL,
                    data      TEXT DEFAULT '{{}}',
                    created   TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, kind)
                );

                CREATE INDEX IF NOT EXISTS idx_{g}_edges_source
                    ON {g}_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_{g}_edges_target
                    ON {g}_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_{g}_edges_kind
                    ON {g}_edges(kind);
                CREATE INDEX IF NOT EXISTS idx_{g}_nodes_kind
                    ON {g}_nodes(kind);
                CREATE INDEX IF NOT EXISTS idx_{g}_nodes_name
                    ON {g}_nodes(name);
            """)
            # Standalone FTS5 table keyed by node id.  We manage inserts
            # and deletes ourselves rather than using content= sync, which
            # is fragile across SQLite versions.
            cur.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {g}_nodes_fts
                USING fts5(id, name, data)
            """)

        # Bridge table
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS bridge_edges (
                id               TEXT PRIMARY KEY,
                source_graph     TEXT NOT NULL,
                source_id        TEXT NOT NULL,
                target_graph     TEXT NOT NULL,
                target_id        TEXT NOT NULL,
                kind             TEXT NOT NULL,
                description      TEXT DEFAULT '',
                confidence       REAL DEFAULT 0.5,
                evidence         TEXT DEFAULT '[]',
                inferred_by      TEXT DEFAULT '',
                created          TEXT NOT NULL,
                last_validated   TEXT NOT NULL,
                validation_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_bridge_source
                ON bridge_edges(source_graph, source_id);
            CREATE INDEX IF NOT EXISTS idx_bridge_target
                ON bridge_edges(target_graph, target_id);
            CREATE INDEX IF NOT EXISTS idx_bridge_kind
                ON bridge_edges(kind);
            CREATE INDEX IF NOT EXISTS idx_bridge_confidence
                ON bridge_edges(confidence);
        """)
        self._conn.commit()

    # ── Validation ────────────────────────────────────────────────────

    def _validate_graph(self, graph: str) -> None:
        if graph not in self.GRAPHS:
            raise ValueError(
                f"Invalid graph {graph!r}. Must be one of {self.GRAPHS}"
            )

    # ── Node operations ───────────────────────────────────────────────

    def upsert_node(self, graph: str, node: dict) -> None:
        self._validate_graph(graph)
        now = _utc_now_iso()
        data = json.dumps(node.get("data", {}))
        self._conn.execute(
            f"""
            INSERT INTO {graph}_nodes (id, kind, name, data, created, updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind    = excluded.kind,
                name    = excluded.name,
                data    = excluded.data,
                updated = excluded.updated
            """,
            (node["id"], node["kind"], node["name"], data, now, now),
        )
        # Sync standalone FTS5 index — delete old entry then re-insert.
        self._conn.execute(
            f"DELETE FROM {graph}_nodes_fts WHERE id = ?", (node["id"],)
        )
        self._conn.execute(
            f"INSERT INTO {graph}_nodes_fts(id, name, data) VALUES (?, ?, ?)",
            (node["id"], node["name"], data),
        )
        self._conn.commit()

    def get_node(self, graph: str, node_id: str) -> dict | None:
        self._validate_graph(graph)
        row = self._conn.execute(
            f"SELECT * FROM {graph}_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def delete_node(self, graph: str, node_id: str) -> bool:
        self._validate_graph(graph)
        row = self._conn.execute(
            f"SELECT id FROM {graph}_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if row is None:
            return False
        # Remove FTS entry
        self._conn.execute(
            f"DELETE FROM {graph}_nodes_fts WHERE id = ?", (node_id,)
        )
        # Delete incident edges
        self._conn.execute(
            f"DELETE FROM {graph}_edges WHERE source_id = ? OR target_id = ?",
            (node_id, node_id),
        )
        self._conn.execute(f"DELETE FROM {graph}_nodes WHERE id = ?", (node_id,))
        self._conn.commit()
        return True

    def search_nodes(self, graph: str, query: str, limit: int = 10) -> list[dict]:
        self._validate_graph(graph)
        # Quote each token so that hyphens and special chars are treated as
        # literal parts of the search rather than FTS5 operators.
        safe_query = " ".join(f'"{token}"' for token in query.split())
        rows = self._conn.execute(
            f"""
            SELECT n.*
            FROM {graph}_nodes_fts fts
            JOIN {graph}_nodes n ON n.id = fts.id
            WHERE {graph}_nodes_fts MATCH ?
            LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def count_nodes(self, graph: str) -> int:
        self._validate_graph(graph)
        row = self._conn.execute(f"SELECT COUNT(*) FROM {graph}_nodes").fetchone()
        return row[0]

    # ── Edge operations ───────────────────────────────────────────────

    def upsert_edge(self, graph: str, edge: dict) -> None:
        self._validate_graph(graph)
        now = _utc_now_iso()
        data = json.dumps(edge.get("data", {}))
        self._conn.execute(
            f"""
            INSERT INTO {graph}_edges (source_id, target_id, kind, data, created)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, kind) DO UPDATE SET
                data    = excluded.data,
                created = excluded.created
            """,
            (edge["source_id"], edge["target_id"], edge["kind"], data, now),
        )
        self._conn.commit()

    def get_edges(
        self,
        graph: str,
        node_id: str,
        direction: str = "both",
        edge_kinds: list[str] | None = None,
    ) -> list[dict]:
        self._validate_graph(graph)
        clauses: list[str] = []
        params: list[Any] = []

        if direction == "out":
            clauses.append("source_id = ?")
            params.append(node_id)
        elif direction == "in":
            clauses.append("target_id = ?")
            params.append(node_id)
        else:  # both
            clauses.append("(source_id = ? OR target_id = ?)")
            params.extend([node_id, node_id])

        if edge_kinds:
            placeholders = ",".join("?" for _ in edge_kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(edge_kinds)

        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM {graph}_edges WHERE {where}", params
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def delete_edge(self, graph: str, source_id: str, target_id: str, kind: str) -> bool:
        self._validate_graph(graph)
        cur = self._conn.execute(
            f"DELETE FROM {graph}_edges WHERE source_id = ? AND target_id = ? AND kind = ?",
            (source_id, target_id, kind),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count_edges(self, graph: str) -> int:
        self._validate_graph(graph)
        row = self._conn.execute(f"SELECT COUNT(*) FROM {graph}_edges").fetchone()
        return row[0]

    # ── Traversal ─────────────────────────────────────────────────────

    def traverse(
        self,
        graph: str,
        start_id: str,
        edge_kinds: list[str],
        max_depth: int = 3,
    ) -> list[dict]:
        """Recursive CTE traversal returning reachable nodes with depth.

        Follows outgoing edges from *start_id* up to *max_depth* hops,
        filtering by *edge_kinds*.  Prevents cycles via ``NOT IN`` guard.
        """
        self._validate_graph(graph)
        if not edge_kinds:
            return []

        placeholders = ",".join("?" for _ in edge_kinds)
        # UNION (not UNION ALL) prevents revisiting nodes already in the
        # result set, which handles cycles without a second recursive ref.
        query = f"""
        WITH RECURSIVE reach(id, depth) AS (
            SELECT target_id, 1
            FROM {graph}_edges
            WHERE source_id = ?
              AND kind IN ({placeholders})
            UNION
            SELECT e.target_id, r.depth + 1
            FROM {graph}_edges e
            JOIN reach r ON e.source_id = r.id
            WHERE r.depth < ?
              AND e.kind IN ({placeholders})
        )
        SELECT n.*, MIN(r.depth) AS depth
        FROM {graph}_nodes n
        JOIN reach r ON n.id = r.id
        GROUP BY n.id
        ORDER BY depth
        """
        params: list[Any] = [start_id, *edge_kinds, max_depth, *edge_kinds]
        rows = self._conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            node = self._row_to_node(r)
            node["depth"] = r["depth"]
            result.append(node)
        return result

    # ── Bridge operations ─────────────────────────────────────────────

    def upsert_bridge(self, edge: dict) -> None:
        now = _utc_now_iso()
        evidence = json.dumps(edge.get("evidence", []))
        self._conn.execute(
            """
            INSERT INTO bridge_edges
                (id, source_graph, source_id, target_graph, target_id, kind,
                 description, confidence, evidence, inferred_by,
                 created, last_validated, validation_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_graph     = excluded.source_graph,
                source_id        = excluded.source_id,
                target_graph     = excluded.target_graph,
                target_id        = excluded.target_id,
                kind             = excluded.kind,
                description      = excluded.description,
                confidence       = excluded.confidence,
                evidence         = excluded.evidence,
                inferred_by      = excluded.inferred_by,
                last_validated   = excluded.last_validated,
                validation_count = excluded.validation_count
            """,
            (
                edge["id"],
                edge["source_graph"],
                edge["source_id"],
                edge["target_graph"],
                edge["target_id"],
                edge["kind"],
                edge.get("description", ""),
                edge.get("confidence", 0.5),
                evidence,
                edge.get("inferred_by", ""),
                now,
                now,
                edge.get("validation_count", 0),
            ),
        )
        self._conn.commit()

    def get_bridges(
        self,
        source_graph: str | None = None,
        source_id: str | None = None,
        target_graph: str | None = None,
        target_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []

        if source_graph is not None:
            clauses.append("source_graph = ?")
            params.append(source_graph)
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if target_graph is not None:
            clauses.append("target_graph = ?")
            params.append(target_graph)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)

        where = " AND ".join(clauses) if clauses else "1=1"
        rows = self._conn.execute(
            f"SELECT * FROM bridge_edges WHERE {where}", params
        ).fetchall()
        return [self._row_to_bridge(r) for r in rows]

    def delete_bridge(self, bridge_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM bridge_edges WHERE id = ?", (bridge_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ── Row converters ────────────────────────────────────────────────

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> dict:
        d = dict(row)
        if "data" in d and isinstance(d["data"], str):
            d["data"] = json.loads(d["data"])
        return d

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> dict:
        d = dict(row)
        if "data" in d and isinstance(d["data"], str):
            d["data"] = json.loads(d["data"])
        return d

    @staticmethod
    def _row_to_bridge(row: sqlite3.Row) -> dict:
        d = dict(row)
        if "evidence" in d and isinstance(d["evidence"], str):
            d["evidence"] = json.loads(d["evidence"])
        return d
