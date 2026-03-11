"""Hybrid retrieval over the canonical Memory Palace index."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from dharma_swarm.engine.knowledge_store import (
    KnowledgeRecord,
    _hash_embed,
    _jaccard,
    _tokenize,
)
from dharma_swarm.engine.retrieval_feedback import FeedbackProfile, RetrievalFeedbackStore
from dharma_swarm.engine.unified_index import UnifiedIndex, _search_text_for_record


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(left * right for left, right in zip(a, b))


def _token_overlap(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(_normalize(text))
    if not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


@dataclass(slots=True)
class RetrievalHit:
    """Ranked retrieval result with fused evidence."""

    record: KnowledgeRecord
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TemporalQuery:
    """Time-window interpretation of a retrieval query."""

    since: datetime | None = None
    until: datetime | None = None
    recency_bias: float = 0.0
    matched_phrases: tuple[str, ...] = ()


def infer_temporal_query(query: str, *, now: datetime | None = None) -> TemporalQuery:
    normalized = _normalize(query)
    if not normalized:
        return TemporalQuery()

    current = now or _utc_now()
    matched: list[str] = []
    since: datetime | None = None
    until: datetime | None = None
    recency_bias = 0.0

    def _apply_window(start: datetime, end: datetime | None, phrase: str) -> None:
        nonlocal since, until
        if since is None or start > since:
            since = start
        if end is not None:
            until = end if until is None or end < until else until
        matched.append(phrase)

    if "today" in normalized:
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        _apply_window(start, current, "today")
    if "yesterday" in normalized:
        end = current.replace(hour=0, minute=0, second=0, microsecond=0)
        _apply_window(end - timedelta(days=1), end, "yesterday")
    if "this week" in normalized:
        start = (current - timedelta(days=current.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        _apply_window(start, current, "this week")
    for phrase, delta in (
        ("last hour", timedelta(hours=1)),
        ("past hour", timedelta(hours=1)),
        ("last 24 hours", timedelta(hours=24)),
        ("past 24 hours", timedelta(hours=24)),
        ("last day", timedelta(days=1)),
        ("past day", timedelta(days=1)),
        ("last week", timedelta(days=7)),
        ("past week", timedelta(days=7)),
        ("last 7 days", timedelta(days=7)),
        ("past 7 days", timedelta(days=7)),
        ("last month", timedelta(days=30)),
        ("past month", timedelta(days=30)),
        ("last 30 days", timedelta(days=30)),
        ("past 30 days", timedelta(days=30)),
    ):
        if phrase in normalized:
            _apply_window(current - delta, current, phrase)
    if any(token in normalized for token in ("latest", "recent", "newest")):
        recency_bias = max(recency_bias, 0.01)
        matched.append("recency_bias")

    return TemporalQuery(
        since=since,
        until=until,
        recency_bias=recency_bias,
        matched_phrases=tuple(dict.fromkeys(matched)),
    )


class HybridRetriever:
    """Fused lexical + overlap + lightweight vector retrieval."""

    def __init__(self, index: UnifiedIndex, *, rrf_k: int = 60) -> None:
        self._index = index
        self._rrf_k = max(1, rrf_k)
        self._feedback = RetrievalFeedbackStore(index.db_path)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        recency_bias: float = 0.0,
        consumer: str | None = None,
    ) -> list[RetrievalHit]:
        normalized_query = _normalize(query)
        if not normalized_query:
            return []

        records = self._index.records(filters=filters)
        records = [
            record
            for record in records
            if self._within_time_window(record, since=since, until=until)
        ]
        if not records:
            return []

        by_id = {record.record_id: record for record in records}
        fused_scores: dict[str, float] = {}
        evidence: dict[str, dict[str, Any]] = {}
        feedback_profile = (
            self._feedback.feedback_profile(
                consumer=consumer,
                query=normalized_query,
            )
            if consumer
            else FeedbackProfile()
        )

        for lane_name, lane_weight, scorer in (
            ("lexical", 1.2, self._lexical_score),
            ("overlap", 1.0, self._overlap_score),
            ("semantic", 0.9, self._semantic_score),
        ):
            ranked: list[tuple[KnowledgeRecord, float]] = []
            for record in records:
                lane_score = scorer(normalized_query, record)
                if lane_score <= 0:
                    continue
                ranked.append((record, lane_score))
            ranked.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)

            for rank, (record, lane_score) in enumerate(ranked, start=1):
                fused_scores[record.record_id] = (
                    fused_scores.get(record.record_id, 0.0)
                    + lane_weight / (self._rrf_k + rank)
                )
                slot = evidence.setdefault(
                    record.record_id,
                    {
                        "source_kind": record.metadata.get("source_kind", "unknown"),
                        "lane_scores": {},
                        "lane_ranks": {},
                    },
                )
                slot["lane_scores"][lane_name] = round(lane_score, 6)
                slot["lane_ranks"][lane_name] = rank

        hits: list[RetrievalHit] = []
        for record_id, fused_score in fused_scores.items():
            hit_evidence = evidence.get(record_id, {})
            hit_evidence["matched_query"] = normalized_query
            structural_boost = self._structural_boost(normalized_query, by_id[record_id])
            temporal_boost = self._temporal_boost(
                by_id[record_id],
                recency_bias=recency_bias,
            )
            feedback_boost = self._feedback_boost(
                by_id[record_id],
                profile=feedback_profile,
            )
            if structural_boost > 0:
                hit_evidence["structural_boost"] = round(structural_boost, 6)
            if temporal_boost > 0:
                hit_evidence["temporal_boost"] = round(temporal_boost, 6)
            if feedback_boost != 0:
                hit_evidence["feedback_boost"] = round(feedback_boost, 6)
            if consumer:
                hit_evidence["consumer"] = consumer
            if since is not None or until is not None:
                hit_evidence["time_window"] = {
                    "since": since.isoformat() if since is not None else None,
                    "until": until.isoformat() if until is not None else None,
                }
            hits.append(
                RetrievalHit(
                    record=by_id[record_id],
                    score=round(
                        fused_score + structural_boost + temporal_boost + feedback_boost,
                        6,
                    ),
                    evidence=hit_evidence,
                )
            )

        hits.sort(key=lambda item: (item.score, item.record.created_at), reverse=True)
        return hits[: max(1, limit)]

    def _lexical_score(self, query: str, record: KnowledgeRecord) -> float:
        structured = _normalize(_search_text_for_record(record))
        title_text = _normalize(self._title_text(record))
        query_tokens = _tokenize(query)
        if not structured or not query_tokens:
            return 0.0

        exact_phrase = 1.0 if query in structured else 0.0
        title_phrase = 1.1 if title_text and query in title_text else 0.0
        structured_overlap = _token_overlap(query_tokens, structured)
        title_overlap = _token_overlap(query_tokens, title_text)
        return round(
            exact_phrase + title_phrase + (0.8 * structured_overlap) + (0.9 * title_overlap),
            6,
        )

    def _overlap_score(self, query: str, record: KnowledgeRecord) -> float:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return 0.0
        body_tokens = _tokenize(_normalize(record.text))
        structured_tokens = _tokenize(_normalize(_search_text_for_record(record)))
        score = (1.1 * _jaccard(query_tokens, body_tokens)) + (
            0.4 * _jaccard(query_tokens, structured_tokens)
        )
        return round(score, 6)

    def _semantic_score(self, query: str, record: KnowledgeRecord) -> float:
        structured = _normalize(_search_text_for_record(record))
        if not structured:
            return 0.0
        score = max(0.0, _dot(_hash_embed(query), _hash_embed(structured)))
        if query in structured:
            score += 0.1
        return round(score, 6)

    def _title_text(self, record: KnowledgeRecord) -> str:
        metadata = record.metadata
        header_path = metadata.get("header_path", [])
        if isinstance(header_path, list):
            header_text = " ".join(str(part) for part in header_path)
        else:
            header_text = str(header_path or "")
        return " ".join(
            str(part)
            for part in (
                metadata.get("section_title", ""),
                header_text,
                metadata.get("source_ref", ""),
                metadata.get("event_type", ""),
            )
            if part
        )

    def _structural_boost(self, query: str, record: KnowledgeRecord) -> float:
        title_text = _normalize(self._title_text(record))
        query_tokens = _tokenize(query)
        if not title_text or not query_tokens:
            return 0.0
        boost = 0.0
        if query in title_text:
            boost += 0.01
        boost += 0.005 * _token_overlap(query_tokens, title_text)
        return round(boost, 6)

    def search_with_temporal_query(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        now: datetime | None = None,
        consumer: str | None = None,
    ) -> list[RetrievalHit]:
        temporal = infer_temporal_query(query, now=now)
        hits = self.search(
            query,
            limit=limit,
            filters=filters,
            since=temporal.since,
            until=temporal.until,
            recency_bias=temporal.recency_bias,
            consumer=consumer,
        )
        if temporal.matched_phrases:
            for hit in hits:
                hit.evidence["temporal_query"] = list(temporal.matched_phrases)
        return hits

    def _within_time_window(
        self,
        record: KnowledgeRecord,
        *,
        since: datetime | None,
        until: datetime | None,
    ) -> bool:
        created_at = record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if since is not None and created_at < since:
            return False
        if until is not None and created_at > until:
            return False
        return True

    def _temporal_boost(self, record: KnowledgeRecord, *, recency_bias: float) -> float:
        if recency_bias <= 0:
            return 0.0
        created_at = record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (_utc_now() - created_at).total_seconds() / 3600.0)
        freshness = 1.0 / (1.0 + (age_hours / 24.0))
        return round(recency_bias * freshness, 6)

    def _feedback_boost(self, record: KnowledgeRecord, *, profile: FeedbackProfile) -> float:
        record_bias = profile.record_bias.get(record.record_id, 0.0)
        kind_bias = profile.source_kind_bias.get(
            str(record.metadata.get("source_kind", "unknown")),
            0.0,
        )
        return round(record_bias + kind_bias, 6)
