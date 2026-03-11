"""Retrieval telemetry for the canonical Memory Palace."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dharma_swarm.engine.event_memory import (
    DEFAULT_MEMORY_PLANE_DB,
    ensure_memory_plane_schema_sync,
)
from dharma_swarm.engine.knowledge_store import _jaccard, _tokenize

if TYPE_CHECKING:
    from dharma_swarm.engine.hybrid_retriever import RetrievalHit


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "being",
    "from",
    "have",
    "into",
    "just",
    "more",
    "over",
    "same",
    "some",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "very",
    "what",
    "when",
    "with",
    "would",
}


@dataclass(slots=True)
class FeedbackProfile:
    """Historical retrieval outcome biases for a consumer."""

    record_bias: dict[str, float] = field(default_factory=dict)
    source_kind_bias: dict[str, float] = field(default_factory=dict)


def _bounded_bias(successes: float, failures: float, *, ceiling: float) -> float:
    total = successes + failures
    if total <= 0:
        return 0.0
    raw = (successes - failures) / total
    confidence = min(1.0, total / 5.0)
    return round(ceiling * raw * confidence, 6)


def _query_weight(current_query: str | None, historical_query: str) -> float:
    if not current_query or not current_query.strip():
        return 1.0
    overlap = _jaccard(_tokenize(current_query), _tokenize(historical_query))
    if overlap <= 0:
        return 0.15
    return 0.15 + (0.85 * overlap)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value[:12]]
    return str(value)


def _snapshot_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "source_kind",
        "source_path",
        "source_ref",
        "section_title",
        "header_path",
        "event_type",
        "session_id",
        "trace_id",
    )
    snapshot: dict[str, Any] = {}
    for field_name in fields:
        if field_name in metadata:
            snapshot[field_name] = _json_safe(metadata[field_name])
    return snapshot


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").strip()


def _distinctive_tokens(text: str, *, limit: int = 12) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _tokenize(_normalize(text)):
        if len(token) < 4 or token in _STOPWORDS or token in seen:
            continue
        tokens.append(token)
        seen.add(token)
        if len(tokens) >= limit:
            break
    return tokens


def _metadata_text(metadata: dict[str, Any]) -> str:
    header_path = metadata.get("header_path", [])
    header_text = ""
    if isinstance(header_path, list):
        header_text = " ".join(str(part) for part in header_path)
    elif header_path:
        header_text = str(header_path)
    return " ".join(
        str(part)
        for part in (
            metadata.get("source_ref", ""),
            metadata.get("section_title", ""),
            header_text,
            metadata.get("event_type", ""),
            metadata.get("source_kind", ""),
        )
        if part
    ).strip()


def _path_tokens(path_text: str) -> set[str]:
    if not path_text.strip():
        return set()
    path = Path(path_text)
    parts = [path.stem, path.parent.name]
    return {
        token
        for part in parts
        for token in _tokenize(_normalize(part))
        if len(token) >= 4
    }


def _sentence_bonus(output_text: str, record_text: str) -> tuple[float, str]:
    normalized_output = _normalize(output_text)
    for sentence in re.split(r"[.!?\n]+", record_text):
        candidate = _normalize(sentence)
        if len(candidate) < 28:
            continue
        if candidate in normalized_output:
            return 0.45, sentence.strip()[:140]
    return 0.0, ""


def _uptake_weight(
    *,
    outcome: str,
    uptake_state: str | None,
    uptake_score: float | None,
) -> float:
    state = (uptake_state or "").strip().lower()
    score = max(0.0, float(uptake_score or 0.0))
    if state == "used":
        return 1.0 + (0.45 * max(0.4, score))
    if state == "probably_used":
        return 1.0 + (0.2 * max(0.25, score))
    if state == "not_used":
        return 0.2 if outcome == "failure" else 0.35
    return 1.0


def _citation_signal(
    output_text: str,
    *,
    record_text: str,
    source_path: str,
    query_text: str,
    metadata: dict[str, Any],
) -> tuple[str, float, dict[str, Any]]:
    normalized_output = _normalize(output_text)
    output_tokens = _tokenize(normalized_output)
    if not output_tokens:
        return "not_used", 0.0, {"reason": "empty_output"}

    record_tokens = _tokenize(_normalize(record_text))
    metadata_text = _metadata_text(metadata)
    metadata_tokens = _tokenize(_normalize(metadata_text))
    query_tokens = _tokenize(_normalize(query_text))
    distinctive = _distinctive_tokens(" ".join(part for part in (record_text, metadata_text) if part))
    sentence_bonus, matched_sentence = _sentence_bonus(output_text, record_text)
    record_overlap = _jaccard(output_tokens, record_tokens) if record_tokens else 0.0
    metadata_overlap = _jaccard(output_tokens, metadata_tokens) if metadata_tokens else 0.0
    query_overlap = _jaccard(output_tokens, query_tokens) if query_tokens else 0.0
    distinctive_overlap = (
        len(set(output_tokens) & set(distinctive)) / len(distinctive)
        if distinctive
        else 0.0
    )
    path_hit = 1.0 if _path_tokens(source_path) & output_tokens else 0.0

    score = min(
        1.0,
        sentence_bonus
        + (0.42 * record_overlap)
        + (0.22 * metadata_overlap)
        + (0.12 * query_overlap)
        + (0.18 * distinctive_overlap)
        + (0.08 * path_hit),
    )
    state = "not_used"
    if sentence_bonus > 0 or score >= 0.42:
        state = "used"
    elif score >= 0.22:
        state = "probably_used"

    evidence = {
        "record_overlap": round(record_overlap, 6),
        "metadata_overlap": round(metadata_overlap, 6),
        "query_overlap": round(query_overlap, 6),
        "distinctive_overlap": round(distinctive_overlap, 6),
        "path_hit": bool(path_hit),
    }
    if matched_sentence:
        evidence["matched_sentence"] = matched_sentence
    return state, round(score, 6), evidence


class RetrievalFeedbackStore:
    """Stores retrieval telemetry in the shared memory-plane database."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)

    def log_hits(
        self,
        query: str,
        hits: list["RetrievalHit"],
        *,
        consumer: str = "unknown",
        task_id: str | None = None,
    ) -> int:
        if not query.strip() or not hits:
            return 0

        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            for rank, hit in enumerate(hits, start=1):
                payload = dict(hit.evidence)
                payload["record_metadata"] = _snapshot_metadata(hit.record.metadata)
                payload["record_excerpt"] = hit.record.text[:240]
                db.execute(
                    "INSERT INTO retrieval_log"
                    " (feedback_id, query_text, record_id, source_kind, source_path, task_id,"
                    " record_text, score, rank, consumer, retrieved_at, evidence_json, outcome,"
                    " outcome_recorded_at, uptake_state, uptake_score, uptake_recorded_at, uptake_evidence_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"rfb_{uuid4().hex}",
                        query,
                        hit.record.record_id,
                        str(hit.record.metadata.get("source_kind", "unknown")),
                        str(hit.record.metadata.get("source_path", "")),
                        str(task_id or ""),
                        hit.record.text[:4000],
                        float(hit.score),
                        rank,
                        consumer,
                        _utc_now_iso(),
                        json.dumps(payload, sort_keys=True, ensure_ascii=True),
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                )
            db.commit()
        return len(hits)

    def record_outcome(
        self,
        task_id: str,
        *,
        outcome: str,
        consumer: str | None = None,
    ) -> int:
        normalized = outcome.strip().lower()
        if not task_id.strip() or normalized not in {"success", "failure"}:
            return 0

        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            if consumer:
                cursor = db.execute(
                    "UPDATE retrieval_log SET outcome = ?, outcome_recorded_at = ?"
                    " WHERE task_id = ? AND consumer = ?",
                    (normalized, _utc_now_iso(), task_id, consumer),
                )
            else:
                cursor = db.execute(
                    "UPDATE retrieval_log SET outcome = ?, outcome_recorded_at = ?"
                    " WHERE task_id = ?",
                    (normalized, _utc_now_iso(), task_id),
                )
            db.commit()
        return int(cursor.rowcount or 0)

    def record_citation_uptake(
        self,
        task_id: str,
        *,
        text: str,
        consumer: str | None = None,
    ) -> int:
        if not task_id.strip() or not text.strip():
            return 0

        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            if consumer:
                rows = db.execute(
                    "SELECT feedback_id, query_text, source_path, record_text, evidence_json"
                    " FROM retrieval_log WHERE task_id = ? AND consumer = ?"
                    " ORDER BY retrieved_at DESC, rank ASC",
                    (task_id, consumer),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT feedback_id, query_text, source_path, record_text, evidence_json"
                    " FROM retrieval_log WHERE task_id = ?"
                    " ORDER BY retrieved_at DESC, rank ASC",
                    (task_id,),
                ).fetchall()

            used_count = 0
            for row in rows:
                evidence = json.loads(row["evidence_json"]) if row["evidence_json"] else {}
                metadata = evidence.get("record_metadata", {})
                state, score, uptake_evidence = _citation_signal(
                    text,
                    record_text=str(row["record_text"] or ""),
                    source_path=str(row["source_path"] or ""),
                    query_text=str(row["query_text"] or ""),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
                db.execute(
                    "UPDATE retrieval_log"
                    " SET uptake_state = ?, uptake_score = ?, uptake_recorded_at = ?, uptake_evidence_json = ?"
                    " WHERE feedback_id = ?",
                    (
                        state,
                        score,
                        _utc_now_iso(),
                        json.dumps(uptake_evidence, sort_keys=True, ensure_ascii=True),
                        row["feedback_id"],
                    ),
                )
                if state in {"used", "probably_used"}:
                    used_count += 1
            db.commit()
        return used_count

    def feedback_profile(
        self,
        *,
        consumer: str | None = None,
        limit: int = 500,
        query: str | None = None,
    ) -> FeedbackProfile:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            if consumer:
                rows = db.execute(
                    "SELECT record_id, source_kind, outcome, query_text, uptake_state, uptake_score"
                    " FROM retrieval_log"
                    " WHERE consumer = ? AND outcome IS NOT NULL"
                    " ORDER BY retrieved_at DESC LIMIT ?",
                    (consumer, max(1, limit)),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT record_id, source_kind, outcome, query_text, uptake_state, uptake_score"
                    " FROM retrieval_log"
                    " WHERE outcome IS NOT NULL"
                    " ORDER BY retrieved_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()

        record_counts: dict[str, dict[str, float]] = {}
        kind_counts: dict[str, dict[str, float]] = {}
        for row in rows:
            outcome = str(row["outcome"] or "").strip().lower()
            if outcome not in {"success", "failure"}:
                continue
            weight = _query_weight(query, str(row["query_text"] or "")) * _uptake_weight(
                outcome=outcome,
                uptake_state=str(row["uptake_state"] or ""),
                uptake_score=row["uptake_score"],
            )
            record_slot = record_counts.setdefault(
                str(row["record_id"]),
                {"success": 0.0, "failure": 0.0},
            )
            record_slot[outcome] += weight
            kind_slot = kind_counts.setdefault(
                str(row["source_kind"]),
                {"success": 0.0, "failure": 0.0},
            )
            kind_slot[outcome] += weight

        return FeedbackProfile(
            record_bias={
                record_id: _bounded_bias(
                    counts["success"],
                    counts["failure"],
                    ceiling=0.02,
                )
                for record_id, counts in record_counts.items()
            },
            source_kind_bias={
                source_kind: _bounded_bias(
                    counts["success"],
                    counts["failure"],
                    ceiling=0.01,
                )
                for source_kind, counts in kind_counts.items()
            },
        )

    def recent(
        self,
        *,
        limit: int = 20,
        consumer: str | None = None,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            if consumer:
                rows = db.execute(
                    "SELECT feedback_id, query_text, record_id, source_kind, source_path, task_id, record_text,"
                    " score, rank, consumer, retrieved_at, evidence_json, outcome, outcome_recorded_at,"
                    " uptake_state, uptake_score, uptake_recorded_at, uptake_evidence_json"
                    " FROM retrieval_log WHERE consumer = ?"
                    " ORDER BY retrieved_at DESC, rank ASC LIMIT ?",
                    (consumer, max(1, limit)),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT feedback_id, query_text, record_id, source_kind, source_path, task_id, record_text,"
                    " score, rank, consumer, retrieved_at, evidence_json, outcome, outcome_recorded_at,"
                    " uptake_state, uptake_score, uptake_recorded_at, uptake_evidence_json"
                    " FROM retrieval_log ORDER BY retrieved_at DESC, rank ASC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()

        return [
            {
                "feedback_id": row["feedback_id"],
                "query_text": row["query_text"],
                "record_id": row["record_id"],
                "source_kind": row["source_kind"],
                "source_path": row["source_path"],
                "task_id": row["task_id"],
                "record_text": row["record_text"],
                "score": float(row["score"]),
                "rank": int(row["rank"]),
                "consumer": row["consumer"],
                "retrieved_at": row["retrieved_at"],
                "outcome": row["outcome"],
                "outcome_recorded_at": row["outcome_recorded_at"],
                "uptake_state": row["uptake_state"],
                "uptake_score": float(row["uptake_score"])
                if row["uptake_score"] is not None
                else None,
                "uptake_recorded_at": row["uptake_recorded_at"],
                "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else {},
                "uptake_evidence": json.loads(row["uptake_evidence_json"])
                if row["uptake_evidence_json"]
                else {},
            }
            for row in rows
        ]

    def stats(self) -> dict[str, int]:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            rows = db.execute(
                "SELECT COUNT(*) FROM retrieval_log",
            ).fetchone()
        return {"retrieval_log": int(rows[0])}
