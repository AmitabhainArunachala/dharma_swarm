"""Semantic ingestion spine for dharma_swarm.

Builds the organism's semantic metabolism substrate:

    radar -> ingestion -> distillation -> archive -> vector/semantic memory

The MVP focuses on local, deterministic ingestion of text-like sources.
It reuses existing dharma_swarm substrate instead of creating a parallel
RAG stack:

    - SemanticDigester for structural extraction
    - UnifiedIndex for chunked lexical retrieval
    - VectorStore for semantic retrieval
    - LineageGraph for provenance
    - semantic_memory_bridge for concept indexing
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.engine.hybrid_retriever import HybridRetriever
from dharma_swarm.engine.unified_index import UnifiedIndex
from dharma_swarm.engine.chunker import chunk_markdown
from dharma_swarm.lineage import LineageGraph
from dharma_swarm.semantic_digester import (
    ALLOWED_MD_SUFFIXES,
    ALLOWED_PY_SUFFIXES,
    ALLOWED_TEXT_SUFFIXES,
    SemanticDigester,
)
from dharma_swarm.semantic_gravity import ConceptGraph, ConceptNode
from dharma_swarm.semantic_memory_bridge import index_concepts_into_memory
from dharma_swarm.vector_store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path.home() / ".dharma"
DEFAULT_SUFFIXES = tuple(
    sorted(ALLOWED_MD_SUFFIXES | ALLOWED_PY_SUFFIXES | ALLOWED_TEXT_SUFFIXES | {".rst", ".tex"})
)
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "node_modules",
        "dist",
        "build",
        ".next",
    }
)
MAX_READ_BYTES = 256 * 1024


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _dedupe_keep_order(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if limit is not None and len(out) >= limit:
            break
    return out


def _read_text_safe(path: Path, max_bytes: int = MAX_READ_BYTES) -> str | None:
    try:
        raw = path.read_bytes()[:max_bytes]
    except OSError:
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _first_meaningful_paragraph(text: str, *, max_chars: int = 320) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    chunks = chunk_markdown(stripped, max_words=80)
    if chunks:
        return chunks[0].text[:max_chars].strip()
    paragraphs = [part.strip() for part in stripped.split("\n\n") if part.strip()]
    if paragraphs:
        return paragraphs[0][:max_chars].strip()
    return stripped[:max_chars].strip()


def _category_counts(nodes: list[ConceptNode]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        category = (node.category or "uncategorized").strip() or "uncategorized"
        counts[category] = counts.get(category, 0) + 1
    return counts


def _coarse_tags(
    *,
    source_tags: list[str],
    nodes: list[ConceptNode],
    category_counts: dict[str, int],
) -> list[str]:
    tags = list(source_tags)
    tags.extend(category_counts.keys())
    for node in nodes[:12]:
        if node.recognition_type:
            tags.append(str(node.recognition_type))
    return _dedupe_keep_order(tags, limit=24)


@dataclass(slots=True)
class IngestionSourceSpec:
    name: str
    roots: list[str]
    kind: str = "local_path"
    tags: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=lambda: list(DEFAULT_SUFFIXES))
    enabled: bool = True
    recursive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "roots": list(self.roots),
            "kind": self.kind,
            "tags": list(self.tags),
            "suffixes": list(self.suffixes),
            "enabled": self.enabled,
            "recursive": self.recursive,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionSourceSpec":
        return cls(
            name=str(data.get("name") or "").strip(),
            roots=[str(item) for item in data.get("roots", [])],
            kind=str(data.get("kind") or "local_path"),
            tags=[str(item) for item in data.get("tags", [])],
            suffixes=[str(item) for item in data.get("suffixes", list(DEFAULT_SUFFIXES))],
            enabled=bool(data.get("enabled", True)),
            recursive=bool(data.get("recursive", True)),
        )


@dataclass(slots=True)
class DistilledDocument:
    doc_id: str
    source_name: str
    source_path: str
    content_hash: str
    archive_path: str
    title: str
    summary: str
    concepts: list[str]
    claims: list[str]
    structures: list[str]
    category_counts: dict[str, int]
    tags: list[str]
    index_doc_id: str
    vector_doc_id: int
    updated_at: str


@dataclass(slots=True)
class IngestionRunReport:
    run_id: str
    source_names: list[str]
    files_scanned: int = 0
    files_ingested: int = 0
    files_skipped: int = 0
    concept_nodes: int = 0
    concept_edges: int = 0
    indexed_concepts: int = 0
    errors: list[str] = field(default_factory=list)
    graph_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_names": list(self.source_names),
            "files_scanned": self.files_scanned,
            "files_ingested": self.files_ingested,
            "files_skipped": self.files_skipped,
            "concept_nodes": self.concept_nodes,
            "concept_edges": self.concept_edges,
            "indexed_concepts": self.indexed_concepts,
            "errors": list(self.errors),
            "graph_path": self.graph_path,
        }


class SemanticIngestionSpine:
    """Deterministic ingestion spine backed by local sqlite + archive snapshots."""

    def __init__(self, *, state_dir: Path | str | None = None) -> None:
        self.state_dir = Path(state_dir or DEFAULT_STATE_DIR)
        self.semantic_dir = self.state_dir / "semantic"
        self.archive_dir = self.semantic_dir / "ingestion_archive"
        self.registry_path = self.semantic_dir / "ingestion_sources.json"
        self.db_path = self.semantic_dir / "ingestion_spine.db"
        self.graph_path = self.semantic_dir / "ingestion_concept_graph.json"
        self.vector_dir = self.semantic_dir / "vectors"
        self.memory_db_path = self.state_dir / "db" / "memory_plane.db"
        self.lineage_db_path = self.semantic_dir / "ingestion_lineage.db"

        self.semantic_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self._digester = SemanticDigester()
        self._index = UnifiedIndex(self.memory_db_path)
        self._retriever = HybridRetriever(self._index)
        self._vector_store = VectorStore(self.vector_dir)
        self._lineage = LineageGraph(self.lineage_db_path)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    archive_path TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    concepts_json TEXT DEFAULT '[]',
                    claims_json TEXT DEFAULT '[]',
                    structures_json TEXT DEFAULT '[]',
                    categories_json TEXT DEFAULT '{}',
                    tags_json TEXT DEFAULT '[]',
                    metadata_json TEXT DEFAULT '{}',
                    index_doc_id TEXT DEFAULT '',
                    vector_doc_id INTEGER DEFAULT -1,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_ingest_source_path
                ON documents(source_name, source_path);

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    source_names_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    stats_json TEXT DEFAULT '{}'
                );
                """,
            )
            conn.commit()

    def add_source(self, spec: IngestionSourceSpec) -> IngestionSourceSpec:
        if not spec.name.strip():
            raise ValueError("source name is required")
        if not spec.roots:
            raise ValueError("at least one root is required")
        specs = {item.name: item for item in self.list_sources(enabled_only=False)}
        specs[spec.name] = spec
        self._save_sources(list(specs.values()))
        return spec

    def list_sources(self, *, enabled_only: bool = False) -> list[IngestionSourceSpec]:
        if not self.registry_path.exists():
            return []
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("semantic ingestion registry unreadable: %s", self.registry_path)
            return []
        specs = [
            IngestionSourceSpec.from_dict(item)
            for item in payload.get("sources", [])
            if isinstance(item, dict)
        ]
        if enabled_only:
            return [spec for spec in specs if spec.enabled]
        return specs

    def _save_sources(self, specs: list[IngestionSourceSpec]) -> None:
        payload = {
            "updated_at": _utc_now_iso(),
            "sources": [spec.to_dict() for spec in sorted(specs, key=lambda item: item.name.lower())],
        }
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            docs = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            last_run_row = conn.execute(
                "SELECT run_id, started_at, completed_at, status, stats_json"
                " FROM runs ORDER BY started_at DESC LIMIT 1",
            ).fetchone()
        last_run: dict[str, Any] | None = None
        if last_run_row is not None:
            last_run = {
                "run_id": str(last_run_row["run_id"]),
                "started_at": str(last_run_row["started_at"]),
                "completed_at": str(last_run_row["completed_at"] or ""),
                "status": str(last_run_row["status"]),
                "stats": json.loads(last_run_row["stats_json"] or "{}"),
            }
        return {
            "sources_total": len(self.list_sources(enabled_only=False)),
            "sources_enabled": len(self.list_sources(enabled_only=True)),
            "documents": docs,
            "graph_path": str(self.graph_path),
            "registry_path": str(self.registry_path),
            "vector_store": self._vector_store.stats(),
            "index": self._index.stats(),
            "last_run": last_run,
        }

    def register_default_sources(self) -> list[IngestionSourceSpec]:
        """Register the 4 canonical ingestion sources for dharma_swarm.

        Sources are only added if they are not already registered.
        Returns the list of sources that were actually added (may be empty
        if all were already present).
        """
        defaults = [
            IngestionSourceSpec(
                name="shared_notes",
                roots=[str(Path.home() / ".dharma" / "shared")],
                tags=["shared", "notes", "agent-memory"],
                suffixes=[".md", ".txt", ".json", ".jsonl"],
            ),
            IngestionSourceSpec(
                name="stigmergy",
                roots=[str(Path.home() / ".dharma" / "stigmergy")],
                tags=["stigmergy", "pheromone", "colony"],
                suffixes=[".jsonl", ".json"],
            ),
            IngestionSourceSpec(
                name="foundations",
                roots=[str(Path.home() / "dharma_swarm" / "foundations")],
                tags=["foundations", "pillars", "intellectual-genome"],
                suffixes=[".md", ".txt", ".rst"],
            ),
            IngestionSourceSpec(
                name="overnight_garden",
                roots=[str(Path.home() / ".dharma" / "garden")],
                tags=["garden", "overnight", "consciousness"],
                suffixes=[".md", ".txt", ".json"],
            ),
        ]
        existing_names = {spec.name for spec in self.list_sources(enabled_only=False)}
        added: list[IngestionSourceSpec] = []
        for spec in defaults:
            if spec.name not in existing_names:
                self.add_source(spec)
                added.append(spec)
        return added

    def run(
        self,
        *,
        source_names: list[str] | None = None,
        max_files: int = 200,
    ) -> IngestionRunReport:
        selected = self._select_sources(source_names)
        run_id = _sha256(f"{_utc_now_iso()}:{','.join(spec.name for spec in selected)}")[:12]
        report = IngestionRunReport(
            run_id=run_id,
            source_names=[spec.name for spec in selected],
            graph_path=str(self.graph_path),
        )
        started_at = _utc_now_iso()

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, source_names_json, started_at, status, stats_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    _canonical_json(report.source_names),
                    started_at,
                    "running",
                    "{}",
                ),
            )
            conn.commit()

        aggregate_graph = ConceptGraph()

        try:
            for spec in selected:
                self._merge_graph(aggregate_graph, self._digest_source_graph(spec, max_files=max_files))
                paths = self._collect_paths(spec, max_files=max_files)
                for path in paths:
                    report.files_scanned += 1
                    outcome = self._ingest_path(spec, path, run_id=run_id)
                    if outcome is None:
                        report.files_skipped += 1
                    else:
                        report.files_ingested += 1

            report.concept_nodes = aggregate_graph.node_count
            report.concept_edges = aggregate_graph.edge_count
            report.indexed_concepts = index_concepts_into_memory(
                aggregate_graph,
                db_path=self.memory_db_path,
            )
            self.graph_path.write_text(
                json.dumps(aggregate_graph.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._finish_run(run_id, status="completed", report=report)
            return report
        except Exception as exc:
            report.errors.append(str(exc))
            self._finish_run(run_id, status="failed", report=report)
            raise

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        normalized = query.strip()
        if not normalized:
            return []

        lexical_hits = self._retriever.search(
            normalized,
            limit=limit * 2,
            filters={"source_kind": "ingested_source"},
            consumer="semantic_ingestion",
        )
        vector_hits = self._vector_store.search_hybrid(normalized, top_k=limit * 2)

        merged: dict[str, dict[str, Any]] = {}

        for hit in lexical_hits:
            source_path = str(hit.record.metadata.get("source_path", ""))
            if not source_path:
                continue
            slot = self._document_for_path(source_path) or {}
            merged[source_path] = {
                **slot,
                "source_path": source_path,
                "score": float(hit.score),
                "lexical_score": float(hit.score),
                "vector_score": 0.0,
                "matched_text": hit.record.text[:300],
            }

        for hit in vector_hits:
            source_path = str(hit.get("source") or hit.get("metadata", {}).get("source_path") or "")
            if not source_path:
                continue
            slot = merged.get(source_path) or self._document_for_path(source_path) or {}
            merged[source_path] = {
                **slot,
                "source_path": source_path,
                "score": float(slot.get("score", 0.0)) + float(hit.get("score", 0.0)),
                "lexical_score": float(slot.get("lexical_score", 0.0)),
                "vector_score": float(hit.get("score", 0.0)),
                "matched_text": str(slot.get("matched_text", "")) or str(hit.get("content", ""))[:300],
            }

        ranked = sorted(
            merged.values(),
            key=lambda item: (float(item.get("score", 0.0)), str(item.get("updated_at", ""))),
            reverse=True,
        )
        return ranked[: max(1, limit)]

    def _finish_run(self, run_id: str, *, status: str, report: IngestionRunReport) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET completed_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
                (_utc_now_iso(), status, _canonical_json(report.to_dict()), run_id),
            )
            conn.commit()

    def _select_sources(self, source_names: list[str] | None) -> list[IngestionSourceSpec]:
        selected = self.list_sources(enabled_only=True)
        if source_names:
            requested = {name.strip() for name in source_names if name.strip()}
            selected = [spec for spec in selected if spec.name in requested]
        if not selected:
            raise ValueError("no enabled ingestion sources configured")
        return selected

    def _collect_paths(self, spec: IngestionSourceSpec, *, max_files: int) -> list[Path]:
        suffixes = {suffix.lower() for suffix in spec.suffixes or DEFAULT_SUFFIXES}
        collected: list[Path] = []

        for raw_root in spec.roots:
            root = Path(raw_root).expanduser()
            if root.is_file():
                candidates = [root]
            elif root.is_dir():
                iterator = root.rglob("*") if spec.recursive else root.glob("*")
                candidates = []
                for child in iterator:
                    if not child.is_file():
                        continue
                    if any(part in SKIP_DIRS for part in child.parts):
                        continue
                    candidates.append(child)
            else:
                continue

            for path in sorted(candidates):
                if path.suffix.lower() not in suffixes:
                    continue
                collected.append(path)
                if len(collected) >= max_files:
                    return collected
        return collected

    def _digest_source_graph(self, spec: IngestionSourceSpec, *, max_files: int) -> ConceptGraph:
        graph = ConceptGraph()
        for raw_root in spec.roots:
            root = Path(raw_root).expanduser()
            if root.is_dir():
                partial = self._digester.digest_directory(root, include_tests=False, max_files=max_files)
                self._merge_graph(graph, partial)
                continue
            if root.is_file():
                text = _read_text_safe(root)
                if not text:
                    continue
                for node in self._digester.digest_file(text, str(root), suffix=root.suffix.lower()):
                    graph.add_node(node)
        return graph

    def _merge_graph(self, target: ConceptGraph, source: ConceptGraph) -> None:
        for node in source.all_nodes():
            target.add_node(node)
        for edge in source.all_edges():
            target.add_edge(edge)
        for annotation in source.all_annotations():
            target.add_annotation(annotation)

    def _ingest_path(
        self,
        spec: IngestionSourceSpec,
        path: Path,
        *,
        run_id: str,
    ) -> DistilledDocument | None:
        text = _read_text_safe(path)
        if text is None or not text.strip():
            return None

        source_path = str(path.resolve())
        content_hash = _sha256(text)
        existing = self._document_for_path(source_path, source_name=spec.name)
        if existing and str(existing.get("content_hash", "")) == content_hash:
            return None

        if existing and int(existing.get("vector_doc_id", -1)) > 0:
            self._vector_store.invalidate(int(existing["vector_doc_id"]), reason="semantic_ingestion_superseded")

        archive_path = self._snapshot_text(spec.name, path, content_hash, text)
        nodes = self._digester.digest_file(text, source_path, suffix=path.suffix.lower())
        concepts = _dedupe_keep_order([node.name for node in nodes], limit=20)
        claims = _dedupe_keep_order([claim for node in nodes for claim in node.claims], limit=24)
        structures = _dedupe_keep_order(
            [item for node in nodes for item in node.formal_structures],
            limit=20,
        )
        category_counts = _category_counts(nodes)
        tags = _coarse_tags(source_tags=spec.tags, nodes=nodes, category_counts=category_counts)
        summary = _first_meaningful_paragraph(text)
        title = path.stem.replace("_", " ").strip() or path.name

        metadata = {
            "source_kind": "ingested_source",
            "source_name": spec.name,
            "source_path": source_path,
            "content_hash": content_hash,
            "archive_path": str(archive_path),
            "tags": tags,
            "concepts": concepts,
            "structures": structures,
            "category_counts": category_counts,
            "run_id": run_id,
        }
        distilled_text = self._render_distilled_text(
            title=title,
            summary=summary,
            concepts=concepts,
            claims=claims,
            structures=structures,
            excerpt=text[:2000].strip(),
        )
        index_doc_id = self._index.index_document(
            "ingested_source",
            source_path,
            distilled_text,
            metadata,
        )
        vector_doc_id = self._vector_store.upsert(
            distilled_text,
            source=source_path,
            layer="reference",
            metadata=metadata,
        )
        doc_id = _sha256(f"{spec.name}:{source_path}")[:16]
        updated_at = _utc_now_iso()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    doc_id, source_name, source_path, content_hash, archive_path, title, summary,
                    concepts_json, claims_json, structures_json, categories_json, tags_json,
                    metadata_json, index_doc_id, vector_doc_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    spec.name,
                    source_path,
                    content_hash,
                    str(archive_path),
                    title,
                    summary,
                    _canonical_json(concepts),
                    _canonical_json(claims),
                    _canonical_json(structures),
                    _canonical_json(category_counts),
                    _canonical_json(tags),
                    _canonical_json(metadata),
                    index_doc_id,
                    vector_doc_id,
                    updated_at,
                ),
            )
            conn.commit()

        self._lineage.record_transformation(
            task_id=run_id,
            inputs=[source_path],
            outputs=[f"ingested_source:{doc_id}"],
            agent="semantic_ingestion",
            operation="semantic_ingest",
            metadata={
                "source_name": spec.name,
                "content_hash": content_hash,
                "index_doc_id": index_doc_id,
                "vector_doc_id": vector_doc_id,
            },
        )

        return DistilledDocument(
            doc_id=doc_id,
            source_name=spec.name,
            source_path=source_path,
            content_hash=content_hash,
            archive_path=str(archive_path),
            title=title,
            summary=summary,
            concepts=concepts,
            claims=claims,
            structures=structures,
            category_counts=category_counts,
            tags=tags,
            index_doc_id=index_doc_id,
            vector_doc_id=vector_doc_id,
            updated_at=updated_at,
        )

    def _snapshot_text(self, source_name: str, path: Path, content_hash: str, text: str) -> Path:
        target_dir = self.archive_dir / source_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{content_hash}.txt"
        if not target.exists():
            header = {
                "source_path": str(path.resolve()),
                "snapshot_at": _utc_now_iso(),
                "content_hash": content_hash,
            }
            target.write_text(
                json.dumps(header, sort_keys=True) + "\n\n" + text,
                encoding="utf-8",
            )
        return target

    def _document_for_path(
        self,
        source_path: str,
        *,
        source_name: str | None = None,
    ) -> dict[str, Any] | None:
        query = (
            "SELECT * FROM documents WHERE source_path = ?"
            if source_name is None
            else "SELECT * FROM documents WHERE source_path = ? AND source_name = ?"
        )
        params: tuple[Any, ...] = (source_path,) if source_name is None else (source_path, source_name)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            return None
        return {
            "doc_id": str(row["doc_id"]),
            "source_name": str(row["source_name"]),
            "source_path": str(row["source_path"]),
            "content_hash": str(row["content_hash"]),
            "archive_path": str(row["archive_path"]),
            "title": str(row["title"]),
            "summary": str(row["summary"]),
            "concepts": json.loads(row["concepts_json"] or "[]"),
            "claims": json.loads(row["claims_json"] or "[]"),
            "structures": json.loads(row["structures_json"] or "[]"),
            "category_counts": json.loads(row["categories_json"] or "{}"),
            "tags": json.loads(row["tags_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "index_doc_id": str(row["index_doc_id"] or ""),
            "vector_doc_id": int(row["vector_doc_id"] or -1),
            "updated_at": str(row["updated_at"]),
        }

    def _render_distilled_text(
        self,
        *,
        title: str,
        summary: str,
        concepts: list[str],
        claims: list[str],
        structures: list[str],
        excerpt: str,
    ) -> str:
        parts = [f"Title: {title}"]
        if summary:
            parts.append(f"Summary: {summary}")
        if concepts:
            parts.append("Concepts: " + "; ".join(concepts[:12]))
        if claims:
            parts.append("Claims: " + "; ".join(claims[:10]))
        if structures:
            parts.append("Structures: " + ", ".join(structures[:10]))
        if excerpt:
            parts.append("Excerpt:\n" + excerpt[:1600])
        return "\n\n".join(parts)


__all__ = [
    "DEFAULT_SUFFIXES",
    "DistilledDocument",
    "IngestionRunReport",
    "IngestionSourceSpec",
    "SemanticIngestionSpine",
]
