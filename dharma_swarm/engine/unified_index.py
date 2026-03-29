"""Unified note and event retrieval substrate for the Memory Palace."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dharma_swarm.db_utils import connect_sync
from dharma_swarm.engine.chunker import Chunk, chunk_markdown
from dharma_swarm.engine.event_memory import (
    DEFAULT_MEMORY_PLANE_DB,
    ensure_memory_plane_schema_sync,
)
from dharma_swarm.engine.knowledge_store import (
    KnowledgeRecord,
    _jaccard,
    _metadata_match,
    _tokenize,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _coerce_frontmatter_value(raw: str) -> Any:
    value = raw.strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter_text = text[4:end]
    body = text[end + 5 :]
    metadata: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = _coerce_frontmatter_value(value)
    return metadata, body


def _score(query: str, text: str) -> float:
    normalized_query = query.replace("_", " ")
    normalized_text = text.replace("_", " ")
    tokens = _tokenize(normalized_query)
    score = _jaccard(tokens, _tokenize(normalized_text))
    if normalized_query and normalized_query.lower() in normalized_text.lower():
        score += 0.5
    return round(score, 4)


def _fts5_query(query: str) -> str:
    """Build a safe FTS5 match expression from a raw query string."""
    tokens = _tokenize(query.replace("_", " "))
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def _decode_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def _build_chunk_record(row: sqlite3.Row) -> KnowledgeRecord:
    chunk_meta = _decode_metadata(row["metadata_json"])
    doc_meta = _decode_metadata(row["doc_metadata_json"])
    metadata = {
        **doc_meta,
        **chunk_meta,
        "source_kind": row["source_kind"],
        "source_path": row["source_path"],
        "source_ref": row["source_ref"],
    }
    return KnowledgeRecord(
        text=row["text"],
        metadata=metadata,
        record_id=row["chunk_id"],
        created_at=datetime.fromisoformat(row["updated_at"]),
    )


def _build_event_record(row: sqlite3.Row) -> KnowledgeRecord:
    payload = _decode_metadata(row["payload_json"])
    text = " ".join(
        [
            row["event_type"],
            row["source"],
            row["agent_id"],
            json.dumps(payload, sort_keys=True, ensure_ascii=True).replace("_", " "),
        ]
    ).strip()
    metadata = {
        "source_kind": "runtime_event",
        "event_id": row["event_id"],
        "session_id": row["session_id"],
        "trace_id": row["trace_id"],
        "event_type": row["event_type"],
        "source": row["source"],
        "agent_id": row["agent_id"],
    }
    return KnowledgeRecord(
        text=text,
        metadata=metadata,
        record_id=row["event_id"],
        created_at=datetime.fromisoformat(row["emitted_at"]),
    )


def _search_text_for_record(record: KnowledgeRecord) -> str:
    metadata = record.metadata
    header_path = metadata.get("header_path", [])
    if isinstance(header_path, list):
        header_text = " ".join(str(part) for part in header_path)
    else:
        header_text = str(header_path or "")
    pieces = [
        metadata.get("section_title", ""),
        header_text,
        metadata.get("source_ref", ""),
        metadata.get("source_path", ""),
        metadata.get("event_type", ""),
        metadata.get("source", ""),
        metadata.get("agent_id", ""),
        record.text,
    ]
    return " ".join(str(piece) for piece in pieces if piece)


class UnifiedIndex:
    """Deterministic file-backed unified index for notes and runtime events."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)

    def index_document(
        self,
        source_kind: str,
        source_path: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str:
        """Index a text document deterministically by source kind and path."""
        doc_id, _changed = self._index_document(
            source_kind=source_kind,
            source_path=source_path,
            text=text,
            metadata=metadata,
        )
        return doc_id

    def index_note_file(
        self,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Index a markdown note file, parsing simple frontmatter when present."""
        raw_text = path.read_text()
        parsed_frontmatter, body = _split_frontmatter(raw_text)
        merged_metadata = {**parsed_frontmatter, **(metadata or {})}
        doc_id, _changed = self._index_document(
            source_kind="note",
            source_path=str(path),
            text=body,
            metadata=merged_metadata,
        )
        return doc_id

    def reindex_changed(self, paths: list[Path]) -> dict[str, int]:
        """Reindex changed note files and record a run ledger row."""
        run_id = f"run_{uuid4().hex[:12]}"
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        started = _utc_now_iso()

        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            db.execute(
                "INSERT INTO index_runs (run_id, source_kind, started_at, completed_at, status, stats_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, "note", started, None, "running", "{}"),
            )
            db.commit()

        status = "completed"
        for path in paths:
            try:
                raw_text = path.read_text()
                parsed_frontmatter, body = _split_frontmatter(raw_text)
                _doc_id, changed = self._index_document(
                    source_kind="note",
                    source_path=str(path),
                    text=body,
                    metadata=parsed_frontmatter,
                )
                stats["indexed" if changed else "skipped"] += 1
            except Exception:
                stats["errors"] += 1
                status = "completed_with_errors"

        completed = _utc_now_iso()
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            db.execute(
                "UPDATE index_runs SET completed_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
                (completed, status, json.dumps(stats, sort_keys=True), run_id),
            )
            db.commit()
        return stats

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeRecord, float]]:
        """Search indexed chunks and runtime events through one retrieval surface.

        Uses FTS5 for candidate selection on source_chunks (top 100),
        then reranks with Jaccard/overlap scoring.  Events are scanned
        directly (typically low volume).
        """
        fts_expr = _fts5_query(query)
        results: list[tuple[KnowledgeRecord, float]] = []

        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)

            # FTS5 candidate selection for chunks (top 100)
            if fts_expr:
                try:
                    chunk_rows = db.execute(
                        "SELECT c.chunk_id, c.text, c.metadata_json,"
                        " d.source_kind, d.source_path, d.source_ref,"
                        " d.metadata_json AS doc_metadata_json, d.updated_at"
                        " FROM source_chunks c"
                        " JOIN source_documents d ON d.doc_id = c.doc_id"
                        " WHERE c.rowid IN ("
                        "  SELECT rowid FROM source_chunks_fts"
                        "  WHERE source_chunks_fts MATCH ? LIMIT 100"
                        ")",
                        (fts_expr,),
                    ).fetchall()
                except sqlite3.OperationalError:
                    # FTS5 unavailable — fall back to full scan
                    chunk_rows = db.execute(
                        "SELECT c.chunk_id, c.text, c.metadata_json,"
                        " d.source_kind, d.source_path, d.source_ref,"
                        " d.metadata_json AS doc_metadata_json, d.updated_at"
                        " FROM source_chunks c"
                        " JOIN source_documents d ON d.doc_id = c.doc_id"
                    ).fetchall()
            else:
                chunk_rows = []

            # Events: direct scan (typically small volume)
            event_rows = db.execute(
                "SELECT event_id, session_id, trace_id, event_type, source, agent_id,"
                " emitted_at, payload_json FROM event_log"
            ).fetchall()

        for row in chunk_rows:
            record = _build_chunk_record(row)
            if filters and not _metadata_match(record.metadata, filters):
                continue
            score = _score(query, _search_text_for_record(record))
            if score > 0:
                results.append((record, score))

        for row in event_rows:
            record = _build_event_record(row)
            if filters and not _metadata_match(record.metadata, filters):
                continue
            score = _score(query, _search_text_for_record(record))
            if score > 0:
                results.append((record, score))

        results.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
        return results[: max(1, limit)]

    def records(
        self,
        filters: dict[str, Any] | None = None,
    ) -> list[KnowledgeRecord]:
        """Return all indexed records with optional metadata filters."""
        filters = filters or {}
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            chunk_rows = db.execute(
                "SELECT c.chunk_id, c.text, c.metadata_json, d.source_kind, d.source_path,"
                " d.source_ref, d.metadata_json AS doc_metadata_json, d.updated_at"
                " FROM source_chunks c JOIN source_documents d ON d.doc_id = c.doc_id"
            ).fetchall()
            event_rows = db.execute(
                "SELECT event_id, session_id, trace_id, event_type, source, agent_id,"
                " emitted_at, payload_json FROM event_log"
            ).fetchall()

        out: list[KnowledgeRecord] = []
        for row in chunk_rows:
            record = _build_chunk_record(row)
            if filters and not _metadata_match(record.metadata, filters):
                continue
            out.append(record)

        for row in event_rows:
            record = _build_event_record(row)
            if filters and not _metadata_match(record.metadata, filters):
                continue
            out.append(record)
        return out

    def recent_chunks(self, limit: int = 5) -> list[KnowledgeRecord]:
        """Return recent indexed chunks for context fallback."""
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            rows = db.execute(
                "SELECT c.chunk_id, c.text, c.metadata_json, d.source_kind, d.source_path,"
                " d.updated_at, d.metadata_json AS doc_metadata_json"
                " FROM source_chunks c JOIN source_documents d ON d.doc_id = c.doc_id"
                " ORDER BY d.updated_at DESC, c.chunk_index ASC LIMIT ?",
                (max(1, limit),),
            ).fetchall()

        out: list[KnowledgeRecord] = []
        for row in rows:
            chunk_meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            doc_meta = json.loads(row["doc_metadata_json"]) if row["doc_metadata_json"] else {}
            metadata = {
                **doc_meta,
                **chunk_meta,
                "source_kind": row["source_kind"],
                "source_path": row["source_path"],
            }
            out.append(
                KnowledgeRecord(
                    text=row["text"],
                    metadata=metadata,
                    record_id=row["chunk_id"],
                    created_at=datetime.fromisoformat(row["updated_at"]),
                )
            )
        return out

    def stats(self) -> dict[str, int]:
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            docs = int(db.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0])
            chunks = int(db.execute("SELECT COUNT(*) FROM source_chunks").fetchone()[0])
            events = int(db.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
            runs = int(db.execute("SELECT COUNT(*) FROM index_runs").fetchone()[0])
        return {
            "source_documents": docs,
            "source_chunks": chunks,
            "event_log": events,
            "index_runs": runs,
        }

    def decay_confidence(
        self,
        decay_rate: float = 0.95,
        min_confidence: float = 0.01,
    ) -> int:
        """Apply age-based confidence decay to source_documents.

        Formula: confidence *= decay_rate^age_days.
        Documents below min_confidence get their chunks soft-deleted.
        Returns count of rows updated.
        """
        now = datetime.now(timezone.utc).timestamp()
        updated = 0
        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            rows = db.execute(
                "SELECT doc_id, source_confidence, updated_at FROM source_documents"
            ).fetchall()
            for row in rows:
                try:
                    updated_ts = datetime.fromisoformat(row["updated_at"]).timestamp()
                    age_days = (now - updated_ts) / 86400.0
                    if age_days <= 0:
                        continue
                    decayed = row["source_confidence"] * (decay_rate**age_days)
                    decayed = max(0.0, min(1.0, decayed))
                    if abs(decayed - row["source_confidence"]) > 1e-6:
                        db.execute(
                            "UPDATE source_documents SET source_confidence = ? WHERE doc_id = ?",
                            (decayed, row["doc_id"]),
                        )
                        updated += 1
                    if decayed < min_confidence:
                        db.execute(
                            "DELETE FROM source_chunks WHERE doc_id = ?",
                            (row["doc_id"],),
                        )
                except Exception:
                    pass
            db.commit()
        return updated

    def _index_document(
        self,
        *,
        source_kind: str,
        source_path: str,
        text: str,
        metadata: dict[str, Any],
    ) -> tuple[str, bool]:
        doc_id = _sha256(f"{source_kind}:{source_path}")[:16]
        normalized_metadata = dict(metadata)
        source_hash = _sha256(
            f"{source_kind}\n{source_path}\n{_canonical_json(normalized_metadata)}\n{text}"
        )
        updated_at = _utc_now_iso()
        chunks = chunk_markdown(text)
        if not chunks and text.strip():
            chunks = [
                Chunk(
                    text=text.strip(),
                    metadata={"header_path": [], "section_title": "", "section_depth": 0},
                )
            ]

        with connect_sync(self.db_path, row_factory=sqlite3.Row) as db:
            ensure_memory_plane_schema_sync(db)
            row = db.execute(
                "SELECT source_hash FROM source_documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is not None and row[0] == source_hash:
                return doc_id, False

            db.execute("DELETE FROM source_chunks WHERE doc_id = ?", (doc_id,))
            db.execute(
                "INSERT OR REPLACE INTO source_documents"
                " (doc_id, source_kind, source_path, source_hash, source_ref, metadata_json, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    source_kind,
                    source_path,
                    source_hash,
                    Path(source_path).name,
                    _canonical_json(normalized_metadata),
                    updated_at,
                ),
            )

            for idx, chunk in enumerate(chunks):
                chunk_metadata = {
                    **chunk.metadata,
                    "chunk_index": idx,
                }
                chunk_hash = _sha256(f"{chunk.text}\n{_canonical_json(chunk_metadata)}")
                chunk_id = _sha256(f"{doc_id}:{idx}:{chunk_hash}")[:16]
                db.execute(
                    "INSERT OR REPLACE INTO source_chunks"
                    " (chunk_id, doc_id, chunk_index, text, metadata_json, chunk_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        chunk_id,
                        doc_id,
                        idx,
                        chunk.text,
                        _canonical_json(chunk_metadata),
                        chunk_hash,
                    ),
                )
            db.commit()

        return doc_id, True
