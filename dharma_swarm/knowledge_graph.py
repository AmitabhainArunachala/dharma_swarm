"""Unified Knowledge Graph — ties together all intelligence layers.

Phase 3 of the 1000x Stigmergy plan.  SQLite-backed graph store that
ingests file profiles, stigmergy marks, and dream associations into a
single traversable structure.  Provides BFS traversal, bridge detection,
telos-distance metrics, and bulk sync from all persistent sources.

Design:
  - Synchronous SQLite (batch queries, not real-time)
  - Nodes: file | concept | agent | dream | plan | workflow
  - Edges: 20+ typed relationships (DEPENDS_ON, ENABLES, DREAMED_TOGETHER, ...)
  - BFS for traversal, naive bridge detection (domain-boundary sampling)
  - Default DB: ~/.dharma/knowledge_graph.db

Integration:
  stigmergy.py     — marks become MARKED_BY edges
  subconscious*.py — dreams become DREAMED_TOGETHER edges
  file_profiles.db — file nodes + IMPORTS edges (future: ProfileEngine)
  lineage.py       — complementary (lineage = task provenance, graph = concept topology)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _edge_id() -> str:
    return uuid4().hex[:12]


def _path_hash(path: str) -> str:
    """Deterministic node ID from a file path."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    label TEXT NOT NULL,
    domain TEXT DEFAULT '',
    semantic_density REAL DEFAULT 0.0,
    impact_score REAL DEFAULT 0.0,
    mission_alignment REAL DEFAULT 0.0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES nodes(id),
    target_id TEXT NOT NULL REFERENCES nodes(id),
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_domain ON nodes(domain);
"""

# Valid edge types — kept as a set for validation
EDGE_TYPES = {
    "DEPENDS_ON", "ENABLES", "IMPLEMENTS", "EXTENDS", "CONTRADICTS",
    "ANALOGOUS_TO", "IMPORTS", "REFERENCES", "GROUNDS",
    "VALIDATES", "ATTRACTS", "FUNDS", "IMPROVES",
    "MARKED_BY", "CONNECTS", "DREAMED_TOGETHER", "RESONATES_WITH",
    "PLANS_FOR", "ASSIGNED_TO", "CAPABLE_OF",
}

NODE_TYPES = {"file", "concept", "agent", "dream", "plan", "workflow"}
DOMAINS = {"code", "research", "vault", "config", "state", ""}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KNOWLEDGE GRAPH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class KnowledgeGraph:
    """SQLite-backed knowledge graph for dharma_swarm.

    Provides node/edge CRUD, BFS traversal, bridge detection,
    telos-distance metrics, and bulk ingest from stigmergy/dreams/profiles.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".dharma" / "knowledge_graph.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Node / Edge CRUD ───────────────────────────────────────────────

    def add_node(
        self,
        id: str,
        type: str,
        label: str,
        domain: str = "",
        semantic_density: float = 0.0,
        impact_score: float = 0.0,
        mission_alignment: float = 0.0,
        metadata: dict | None = None,
    ) -> str:
        """Upsert a node.  Returns the node id."""
        now = _utc_now()
        meta_json = json.dumps(metadata or {})
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO nodes
                   (id, type, label, domain, semantic_density, impact_score,
                    mission_alignment, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     type=excluded.type, label=excluded.label,
                     domain=excluded.domain,
                     semantic_density=excluded.semantic_density,
                     impact_score=excluded.impact_score,
                     mission_alignment=excluded.mission_alignment,
                     metadata=excluded.metadata,
                     updated_at=excluded.updated_at""",
                (id, type, label, domain, semantic_density, impact_score,
                 mission_alignment, meta_json, now, now),
            )
        return id

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        weight: float = 1.0,
        metadata: dict | None = None,
    ) -> str:
        """Add an edge.  Auto-generates id.  Returns edge id."""
        eid = _edge_id()
        now = _utc_now()
        meta_json = json.dumps(metadata or {})
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO edges
                   (id, source_id, target_id, edge_type, weight, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (eid, source_id, target_id, edge_type, weight, meta_json, now),
            )
        return eid

    def get_node(self, node_id: str) -> dict | None:
        """Return node as dict or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_edge(self, edge_id: str) -> dict | None:
        """Return edge as dict (with source_label, target_label) or None."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT e.*, s.label AS source_label, t.label AS target_label
                   FROM edges e
                   LEFT JOIN nodes s ON e.source_id = s.id
                   LEFT JOIN nodes t ON e.target_id = t.id
                   WHERE e.id = ?""",
                (edge_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        # Parse JSON metadata if present
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ── Traversal ──────────────────────────────────────────────────────

    def neighbors(
        self,
        node_id: str,
        depth: int = 1,
        edge_types: list[str] | None = None,
    ) -> list[dict]:
        """BFS neighbors up to *depth* hops.  Optionally filter by edge type."""
        visited: set[str] = {node_id}
        result: list[dict] = []
        frontier: set[str] = {node_id}

        for _ in range(depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for nid in frontier:
                with self._conn() as conn:
                    # Outgoing
                    if edge_types:
                        placeholders = ",".join("?" * len(edge_types))
                        rows = conn.execute(
                            f"""SELECT target_id FROM edges
                                WHERE source_id = ? AND edge_type IN ({placeholders})""",
                            [nid] + edge_types,
                        ).fetchall()
                        rows += conn.execute(
                            f"""SELECT source_id FROM edges
                                WHERE target_id = ? AND edge_type IN ({placeholders})""",
                            [nid] + edge_types,
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT target_id FROM edges WHERE source_id = ?",
                            (nid,),
                        ).fetchall()
                        rows += conn.execute(
                            "SELECT source_id FROM edges WHERE target_id = ?",
                            (nid,),
                        ).fetchall()
                neighbor_ids = {r[0] for r in rows} - visited
                next_frontier |= neighbor_ids
                visited |= neighbor_ids
            # Fetch full node data for newly discovered nodes
            for nid in next_frontier:
                node = self.get_node(nid)
                if node:
                    result.append(node)
            frontier = next_frontier

        return result

    def shortest_path(self, source: str, target: str) -> list[dict]:
        """BFS shortest path.  Returns list of edge dicts."""
        if source == target:
            return []

        # Build adjacency from edges (treat graph as undirected for pathfinding)
        with self._conn() as conn:
            all_edges = conn.execute(
                """SELECT e.*, s.label AS source_label, t.label AS target_label
                   FROM edges e
                   LEFT JOIN nodes s ON e.source_id = s.id
                   LEFT JOIN nodes t ON e.target_id = t.id"""
            ).fetchall()

        # Adjacency: node_id -> list of (neighbor_id, edge_dict)
        adj: dict[str, list[tuple[str, dict]]] = {}
        for row in all_edges:
            ed = self._row_to_dict(row)
            src, tgt = ed["source_id"], ed["target_id"]
            adj.setdefault(src, []).append((tgt, ed))
            adj.setdefault(tgt, []).append((src, ed))

        # BFS
        visited: set[str] = {source}
        queue: deque[tuple[str, list[dict]]] = deque([(source, [])])

        while queue:
            current, path = queue.popleft()
            for neighbor, edge_dict in adj.get(current, []):
                if neighbor in visited:
                    continue
                new_path = path + [edge_dict]
                if neighbor == target:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))

        return []  # No path

    def cluster(self, node_id: str) -> list[dict]:
        """Connected component containing node_id."""
        visited: set[str] = set()
        queue: deque[str] = deque([node_id])
        visited.add(node_id)

        with self._conn() as conn:
            # Preload adjacency
            all_edges = conn.execute("SELECT source_id, target_id FROM edges").fetchall()

        adj: dict[str, set[str]] = {}
        for row in all_edges:
            s, t = row[0], row[1]
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)

        while queue:
            current = queue.popleft()
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        result: list[dict] = []
        for nid in visited:
            node = self.get_node(nid)
            if node:
                result.append(node)
        return result

    def _count_components(self, adj: dict[str, set[str]], all_nodes: set[str]) -> int:
        """Count connected components given adjacency map and node set."""
        visited: set[str] = set()
        count = 0
        for node in all_nodes:
            if node not in visited:
                count += 1
                queue: deque[str] = deque([node])
                visited.add(node)
                while queue:
                    cur = queue.popleft()
                    for nb in adj.get(cur, set()):
                        if nb in all_nodes and nb not in visited:
                            visited.add(nb)
                            queue.append(nb)
        return count

    def bridges(self) -> list[dict]:
        """Edges connecting otherwise disconnected clusters.

        Uses sampling: only checks edges between nodes in different domains
        to keep cost manageable on large graphs.  An edge is a bridge if
        removing it increases the component count.
        """
        with self._conn() as conn:
            all_edges = conn.execute(
                """SELECT e.id, e.source_id, e.target_id, e.edge_type, e.weight,
                          e.metadata, e.created_at,
                          s.label AS source_label, s.domain AS source_domain,
                          t.label AS target_label, t.domain AS target_domain
                   FROM edges e
                   LEFT JOIN nodes s ON e.source_id = s.id
                   LEFT JOIN nodes t ON e.target_id = t.id"""
            ).fetchall()

        # Build full adjacency
        adj: dict[str, set[str]] = {}
        all_nodes: set[str] = set()
        edge_list: list[dict] = []

        for row in all_edges:
            ed = self._row_to_dict(row)
            edge_list.append(ed)
            s, t = ed["source_id"], ed["target_id"]
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)
            all_nodes.add(s)
            all_nodes.add(t)

        if not all_nodes:
            return []

        baseline = self._count_components(adj, all_nodes)

        # Only check cross-domain edges (the likely bridges)
        candidates = [
            e for e in edge_list
            if e.get("source_domain", "") != e.get("target_domain", "")
            or e.get("source_domain", "") == ""
        ]
        # If no cross-domain edges, check all (small graph)
        if not candidates:
            candidates = edge_list

        result: list[dict] = []
        for ed in candidates:
            s, t = ed["source_id"], ed["target_id"]
            # Temporarily remove edge
            adj[s].discard(t)
            adj[t].discard(s)
            new_count = self._count_components(adj, all_nodes)
            if new_count > baseline:
                result.append(ed)
            # Restore
            adj[s].add(t)
            adj[t].add(s)

        return result

    # ── Analytics ──────────────────────────────────────────────────────

    def density_map(self, domain: str | None = None) -> dict:
        """Semantic density distribution stats by domain."""
        with self._conn() as conn:
            if domain:
                rows = conn.execute(
                    """SELECT domain, COUNT(*) AS cnt,
                              AVG(semantic_density) AS avg_density,
                              MIN(semantic_density) AS min_density,
                              MAX(semantic_density) AS max_density
                       FROM nodes WHERE domain = ? GROUP BY domain""",
                    (domain,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT domain, COUNT(*) AS cnt,
                              AVG(semantic_density) AS avg_density,
                              MIN(semantic_density) AS min_density,
                              MAX(semantic_density) AS max_density
                       FROM nodes GROUP BY domain"""
                ).fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            d = dict(row)
            key = d.pop("domain") or "(none)"
            result[key] = d
        return result

    def telos_distance(self, node_id: str) -> float:
        """BFS hops to nearest node with mission_alignment > 0.7.

        Returns float('inf') if no such node reachable.
        """
        with self._conn() as conn:
            all_edges = conn.execute(
                "SELECT source_id, target_id FROM edges"
            ).fetchall()
            high_telos = {
                r[0] for r in conn.execute(
                    "SELECT id FROM nodes WHERE mission_alignment > 0.7"
                ).fetchall()
            }

        if node_id in high_telos:
            return 0.0

        if not high_telos:
            return float("inf")

        adj: dict[str, set[str]] = {}
        for row in all_edges:
            s, t = row[0], row[1]
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)

        visited: set[str] = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            current, dist = queue.popleft()
            for nb in adj.get(current, set()):
                if nb in visited:
                    continue
                if nb in high_telos:
                    return float(dist + 1)
                visited.add(nb)
                queue.append((nb, dist + 1))

        return float("inf")

    def ideas_to_plans(self, idea_node_id: str) -> list[dict]:
        """Trace from idea -> plan -> agent -> workflow via typed edges.

        Walks PLANS_FOR to find plans, ASSIGNED_TO for agents,
        CAPABLE_OF / IMPLEMENTS for workflows.
        """
        chain: list[dict] = []

        # idea -> plans (via PLANS_FOR edges where idea is target)
        with self._conn() as conn:
            plans = conn.execute(
                """SELECT e.*, s.label AS source_label, t.label AS target_label
                   FROM edges e
                   LEFT JOIN nodes s ON e.source_id = s.id
                   LEFT JOIN nodes t ON e.target_id = t.id
                   WHERE e.target_id = ? AND e.edge_type = 'PLANS_FOR'""",
                (idea_node_id,),
            ).fetchall()

        plan_ids: list[str] = []
        for row in plans:
            ed = self._row_to_dict(row)
            chain.append(ed)
            plan_ids.append(ed["source_id"])

        # plans -> agents (via ASSIGNED_TO)
        agent_ids: list[str] = []
        for pid in plan_ids:
            with self._conn() as conn:
                agents = conn.execute(
                    """SELECT e.*, s.label AS source_label, t.label AS target_label
                       FROM edges e
                       LEFT JOIN nodes s ON e.source_id = s.id
                       LEFT JOIN nodes t ON e.target_id = t.id
                       WHERE e.source_id = ? AND e.edge_type = 'ASSIGNED_TO'""",
                    (pid,),
                ).fetchall()
            for row in agents:
                ed = self._row_to_dict(row)
                chain.append(ed)
                agent_ids.append(ed["target_id"])

        # agents -> workflows (via CAPABLE_OF or IMPLEMENTS)
        for aid in agent_ids:
            with self._conn() as conn:
                workflows = conn.execute(
                    """SELECT e.*, s.label AS source_label, t.label AS target_label
                       FROM edges e
                       LEFT JOIN nodes s ON e.source_id = s.id
                       LEFT JOIN nodes t ON e.target_id = t.id
                       WHERE e.source_id = ?
                         AND e.edge_type IN ('CAPABLE_OF', 'IMPLEMENTS')""",
                    (aid,),
                ).fetchall()
            for row in workflows:
                chain.append(self._row_to_dict(row))

        return chain

    # ── Bulk Ingest ────────────────────────────────────────────────────

    def ingest_file_profiles(self, profiles: list[dict]) -> int:
        """Bulk load FileProfile dicts as file-type nodes + IMPORTS edges.

        Each profile dict should have at minimum: file_path, label/name.
        Creates IMPORTS edges by scanning Python source for import statements
        and resolving them to other profiled files.
        """
        # Build path lookup for resolving imports
        path_by_module: dict[str, str] = {}  # "dharma_swarm.stigmergy" -> abs path
        path_by_name: dict[str, str] = {}    # "stigmergy.py" -> abs path
        for p in profiles:
            fp = p.get("file_path", "")
            if fp and fp.endswith(".py"):
                fname = Path(fp).name
                path_by_name[fname] = fp
                # Build module path: .../dharma_swarm/foo.py -> dharma_swarm.foo
                # Use the LAST dharma_swarm directory (package, not repo)
                parts = Path(fp).parts
                last_ds = -1
                for i, part in enumerate(parts):
                    if part == "dharma_swarm":
                        last_ds = i
                if last_ds >= 0 and last_ds + 1 < len(parts):
                    mod = ".".join(parts[last_ds:]).removesuffix(".py")
                    # Handle __init__.py -> just the package name
                    if mod.endswith(".__init__"):
                        mod = mod.removesuffix(".__init__")
                    path_by_module[mod] = fp

        count = 0
        for p in profiles:
            fp = p.get("file_path", "")
            if not fp:
                continue
            nid = _path_hash(fp)
            label = p.get("label", p.get("name", Path(fp).name))
            domain = p.get("domain", "code")
            self.add_node(
                id=nid,
                type="file",
                label=label,
                domain=domain,
                semantic_density=p.get("semantic_density", 0.0),
                impact_score=p.get("impact_score", 0.0),
                mission_alignment=p.get("mission_alignment", 0.0),
                metadata={"file_path": fp, **(p.get("metadata") or {})},
            )
            count += 1

            # Resolve IMPORTS edges from source file
            if fp.endswith(".py") and Path(fp).exists():
                try:
                    src = Path(fp).read_text(errors="ignore")
                    for line in src.splitlines():
                        line = line.strip()
                        if line.startswith("from dharma_swarm"):
                            # "from dharma_swarm.foo import bar" -> "dharma_swarm.foo"
                            parts = line.split()
                            if len(parts) >= 2:
                                mod = parts[1]
                                target_fp = path_by_module.get(mod)
                                if target_fp and target_fp != fp:
                                    tid = _path_hash(target_fp)
                                    self.add_edge(nid, tid, "IMPORTS", weight=1.0)
                        elif line.startswith("import dharma_swarm"):
                            parts = line.split()
                            if len(parts) >= 2:
                                mod = parts[1]
                                target_fp = path_by_module.get(mod)
                                if target_fp and target_fp != fp:
                                    tid = _path_hash(target_fp)
                                    self.add_edge(nid, tid, "IMPORTS", weight=1.0)
                except Exception:
                    pass

        return count

    def ingest_stigmergy(self, marks: list[dict]) -> int:
        """Load marks as MARKED_BY edges between agent nodes and file nodes.

        Each mark dict: agent, file_path, observation, salience, connections.
        """
        count = 0
        for mark in marks:
            agent_name = mark.get("agent", "")
            fp = mark.get("file_path", "")
            if not agent_name or not fp:
                continue

            # Ensure agent node
            agent_id = f"agent:{agent_name}"
            self.add_node(
                id=agent_id,
                type="agent",
                label=agent_name,
                domain="state",
            )

            # Ensure file node
            file_id = _path_hash(fp)
            self.add_node(
                id=file_id,
                type="file",
                label=Path(fp).name,
                domain="code",
                metadata={"file_path": fp},
            )

            # MARKED_BY edge
            salience = mark.get("salience", 0.5)
            obs = mark.get("observation", "")
            self.add_edge(
                agent_id, file_id, "MARKED_BY",
                weight=salience,
                metadata={"observation": obs[:500]},
            )
            count += 1

            # CONNECTS edges from connections list
            for conn_path in mark.get("connections", []):
                conn_id = _path_hash(conn_path)
                self.add_node(
                    id=conn_id, type="file",
                    label=Path(conn_path).name, domain="code",
                    metadata={"file_path": conn_path},
                )
                self.add_edge(file_id, conn_id, "CONNECTS", weight=salience * 0.8)

        return count

    def ingest_dreams(self, dreams: list[dict]) -> int:
        """Load dream associations as DREAMED_TOGETHER edges.

        Each dream dict: source_files (list), associations, neologisms, felt_weight.
        """
        count = 0
        for dream in dreams:
            files = dream.get("source_files", [])
            felt_weight = dream.get("felt_weight", 0.5)
            assoc = dream.get("associations", "")
            neologisms = dream.get("neologisms", [])

            # Create a dream concept node
            dream_id = f"dream:{uuid4().hex[:8]}"
            self.add_node(
                id=dream_id,
                type="dream",
                label=assoc[:80] if assoc else "dream",
                domain="state",
                semantic_density=felt_weight,
                metadata={
                    "associations": assoc,
                    "neologisms": neologisms if isinstance(neologisms, list) else [],
                },
            )

            # DREAMED_TOGETHER edges between all file pairs
            file_ids: list[str] = []
            for fp in files:
                fid = _path_hash(fp)
                self.add_node(
                    id=fid, type="file",
                    label=Path(fp).name, domain="code",
                    metadata={"file_path": fp},
                )
                file_ids.append(fid)
                # Link dream node to file
                self.add_edge(dream_id, fid, "RESONATES_WITH", weight=felt_weight)

            # Pairwise DREAMED_TOGETHER between files
            for i in range(len(file_ids)):
                for j in range(i + 1, len(file_ids)):
                    self.add_edge(
                        file_ids[i], file_ids[j], "DREAMED_TOGETHER",
                        weight=felt_weight,
                        metadata={"dream_id": dream_id},
                    )
            count += 1

        return count

    def sync(self) -> dict:
        """Full re-ingest from all persistent sources.  Returns counts."""
        counts: dict[str, int] = {"marks": 0, "dreams": 0, "profiles": 0}

        # 1. Stigmergy marks
        marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
        if marks_file.exists():
            marks: list[dict] = []
            with open(marks_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            marks.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            counts["marks"] = self.ingest_stigmergy(marks)
            logger.info("Synced %d stigmergy marks", counts["marks"])

        # 2. Dream associations
        dreams_file = Path.home() / ".dharma" / "subconscious" / "dream_associations.jsonl"
        if dreams_file.exists():
            dreams: list[dict] = []
            with open(dreams_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            dreams.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            counts["dreams"] = self.ingest_dreams(dreams)
            logger.info("Synced %d dream associations", counts["dreams"])

        # 3. File profiles (from ProfileEngine SQLite DB if available)
        profiles_db = Path.home() / ".dharma" / "file_profiles.db"
        if profiles_db.exists():
            try:
                pconn = sqlite3.connect(str(profiles_db))
                pconn.row_factory = sqlite3.Row
                rows = pconn.execute("SELECT * FROM file_profiles").fetchall()
                profiles = []
                for r in rows:
                    d = dict(r)
                    # Map ProfileEngine's 'path' to ingest's 'file_path'
                    if "path" in d and "file_path" not in d:
                        d["file_path"] = d["path"]
                    if "filename" in d and "label" not in d:
                        d["label"] = d["filename"]
                    profiles.append(d)
                pconn.close()
                counts["profiles"] = self.ingest_file_profiles(profiles)
                logger.info("Synced %d file profiles", counts["profiles"])
            except Exception as exc:
                logger.warning("Failed to sync file profiles: %s", exc)

        # 4. Merge duplicate file nodes (absolute vs relative paths)
        merged = self._merge_duplicate_files()
        counts["merged"] = merged

        logger.info("Knowledge graph sync complete: %s", counts)
        return counts

    def _merge_duplicate_files(self) -> int:
        """Merge file nodes that represent the same file (absolute vs relative path).

        When a profile creates node for '/abs/path/foo.py' and a mark creates
        node for 'dharma_swarm/foo.py', we re-point the mark's edges to the
        profile's node and delete the duplicate.
        """
        merged = 0
        with self._conn() as conn:
            # Find file nodes grouped by label (filename)
            rows = conn.execute(
                "SELECT label, GROUP_CONCAT(id, '|||') as ids "
                "FROM nodes WHERE type='file' GROUP BY label HAVING COUNT(*) > 1"
            ).fetchall()

            for row in rows:
                ids = row[1].split("|||")
                if len(ids) < 2:
                    continue

                # Pick the node with the longest label metadata (absolute path) as canonical
                best_id = ids[0]
                best_meta_len = 0
                for nid in ids:
                    meta_row = conn.execute(
                        "SELECT metadata FROM nodes WHERE id=?", (nid,)
                    ).fetchone()
                    if meta_row and meta_row[0]:
                        fp = json.loads(meta_row[0]).get("file_path", "")
                        if len(fp) > best_meta_len:
                            best_meta_len = len(fp)
                            best_id = nid

                # Re-point all edges from non-canonical nodes to canonical
                for nid in ids:
                    if nid == best_id:
                        continue
                    conn.execute(
                        "UPDATE edges SET source_id=? WHERE source_id=?",
                        (best_id, nid),
                    )
                    conn.execute(
                        "UPDATE edges SET target_id=? WHERE target_id=?",
                        (best_id, nid),
                    )
                    conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
                    merged += 1

        return merged

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Node count, edge count, cluster count, domain breakdown."""
        with self._conn() as conn:
            n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            domain_rows = conn.execute(
                "SELECT domain, COUNT(*) AS cnt FROM nodes GROUP BY domain"
            ).fetchall()
            type_rows = conn.execute(
                "SELECT type, COUNT(*) AS cnt FROM nodes GROUP BY type"
            ).fetchall()
            edge_type_rows = conn.execute(
                "SELECT edge_type, COUNT(*) AS cnt FROM edges GROUP BY edge_type"
            ).fetchall()
            # Count clusters
            all_edges_raw = conn.execute(
                "SELECT source_id, target_id FROM edges"
            ).fetchall()
            all_node_ids = {r[0] for r in conn.execute("SELECT id FROM nodes").fetchall()}

        adj: dict[str, set[str]] = {}
        for row in all_edges_raw:
            s, t = row[0], row[1]
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)

        n_clusters = self._count_components(adj, all_node_ids) if all_node_ids else 0

        return {
            "node_count": n_nodes,
            "edge_count": n_edges,
            "cluster_count": n_clusters,
            "domains": {(r["domain"] or "(none)"): r["cnt"] for r in domain_rows},
            "node_types": {r["type"]: r["cnt"] for r in type_rows},
            "edge_types": {r["edge_type"]: r["cnt"] for r in edge_type_rows},
        }

    def node_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def edge_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Simple text search across node labels and metadata."""
        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM nodes
                   WHERE label LIKE ? OR metadata LIKE ?
                   ORDER BY impact_score DESC, semantic_density DESC
                   LIMIT ?""",
                (pattern, pattern, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def clear(self) -> None:
        """Clear all graph data.  Use with caution."""
        with self._conn() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
