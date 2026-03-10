"""Persistent routing memory for cross-session provider learning.

This module grounds the "router as learning substrate" work in a simple,
durable store:
- per-lane EWMA quality / latency / token cost
- success and failure pheromone traces
- append-only routing events for later audit and policy evolution
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dharma_swarm.models import ProviderType

_DEFAULT_DB = Path.home() / ".dharma" / "logs" / "router" / "routing_memory.sqlite3"
_GLOBAL_SIGNATURE = "*"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str, *, default: str = "unknown") -> str:
    normalized = _SLUG_RE.sub("-", str(text).strip().lower()).strip("-")
    return normalized or default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def default_routing_memory_db_path() -> Path:
    return _DEFAULT_DB


def build_task_signature(*, action_name: str, context: dict[str, Any]) -> str:
    """Build a stable routing bucket for provider-memory lookup."""
    language = _slug(context.get("language_code", "en"), default="en")
    complexity = _slug(context.get("complexity_tier", "medium"), default="medium")
    context_tier = _slug(context.get("context_tier", "short"), default="short")
    tooling = "tooling" if context.get("requires_tooling") else "plain"
    return "|".join((_slug(action_name), complexity, language, context_tier, tooling))


@dataclass(frozen=True, slots=True)
class RoutingLaneScore:
    provider: ProviderType
    model: str
    task_signature: str
    blended_score: float
    exact_score: float | None
    global_score: float | None
    similar_score: float | None
    sample_count: int
    similar_matches: int
    success_pheromone: float
    failure_pheromone: float


class RoutingMemoryStore:
    """SQLite-backed routing memory with light pheromone dynamics."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        ewma_alpha: float = 0.25,
        success_decay: float = 0.95,
        failure_decay: float = 0.70,
    ) -> None:
        self.db_path = Path(db_path or _DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ewma_alpha = max(0.01, min(1.0, float(ewma_alpha)))
        self._success_decay = max(0.0, min(0.999, float(success_decay)))
        self._failure_decay = max(0.0, min(0.999, float(failure_decay)))
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS routing_stats (
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_signature TEXT NOT NULL,
                    ewma_quality REAL NOT NULL DEFAULT 0.5,
                    ewma_latency_ms REAL NOT NULL DEFAULT 0.0,
                    ewma_tokens REAL NOT NULL DEFAULT 0.0,
                    success_pheromone REAL NOT NULL DEFAULT 0.0,
                    failure_pheromone REAL NOT NULL DEFAULT 0.0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, model, task_signature)
                );

                CREATE TABLE IF NOT EXISTS routing_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_signature TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    route_path TEXT,
                    outcome TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_routing_events_sig
                    ON routing_events(task_signature, provider, model, timestamp);
                """
            )

    def _load_lane(
        self,
        db: sqlite3.Connection,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
    ) -> sqlite3.Row | None:
        return db.execute(
            """
            SELECT provider, model, task_signature, ewma_quality, ewma_latency_ms,
                   ewma_tokens, success_pheromone, failure_pheromone,
                   success_count, failure_count, last_error, updated_at
            FROM routing_stats
            WHERE provider = ? AND model = ? AND task_signature = ?
            """,
            (provider.value, model, task_signature),
        ).fetchone()

    def _score_row(self, row: sqlite3.Row) -> float:
        total = int(row["success_count"]) + int(row["failure_count"])
        success_rate = 0.5 if total <= 0 else (float(row["success_count"]) / total)
        latency_penalty = min(max(float(row["ewma_latency_ms"]), 0.0) / 8000.0, 1.0) * 0.12
        token_penalty = min(max(float(row["ewma_tokens"]), 0.0) / 200000.0, 1.0) * 0.08
        success_pheromone = min(max(float(row["success_pheromone"]), 0.0), 6.0)
        failure_pheromone = min(max(float(row["failure_pheromone"]), 0.0), 6.0)
        exploration_bonus = 0.04 if total < 3 else 0.0
        score = (
            0.60 * _clamp01(float(row["ewma_quality"]))
            + 0.20 * success_rate
            + 0.04 * success_pheromone
            + exploration_bonus
            - 0.08 * failure_pheromone
            - latency_penalty
            - token_penalty
        )
        return round(score, 6)

    @staticmethod
    def _blended_score(
        *,
        exact_score: float | None,
        global_score: float | None,
        similar_score: float | None,
        exact_samples: int,
    ) -> float | None:
        components: list[tuple[float, float]] = []
        if exact_score is not None:
            exact_weight = 0.65 if exact_samples >= 3 else 0.50
            components.append((exact_weight, exact_score))
        if similar_score is not None:
            similar_weight = 0.25 if exact_score is not None else 0.65
            components.append((similar_weight, similar_score))
        if global_score is not None:
            if exact_score is not None:
                global_weight = 0.10
            elif similar_score is not None:
                global_weight = 0.35
            else:
                global_weight = 1.0
            components.append((global_weight, global_score))
        if not components:
            return None
        total_weight = sum(weight for weight, _ in components)
        return round(
            sum(weight * value for weight, value in components) / total_weight,
            6,
        )

    @staticmethod
    def _signature_similarity(left: str, right: str) -> float:
        try:
            left_action, left_complexity, left_language, left_context, left_tooling = (
                left.split("|", 4)
            )
            right_action, right_complexity, right_language, right_context, right_tooling = (
                right.split("|", 4)
            )
        except ValueError:
            return 0.0

        def _token_overlap(a: str, b: str) -> float:
            a_tokens = {token for token in a.split("-") if token}
            b_tokens = {token for token in b.split("-") if token}
            if not a_tokens or not b_tokens:
                return 0.0
            return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)

        score = 0.0
        score += 0.40 * _token_overlap(left_action, right_action)
        score += 0.20 * float(left_complexity == right_complexity)
        score += 0.15 * float(left_language == right_language)
        score += 0.15 * float(left_context == right_context)
        score += 0.10 * float(left_tooling == right_tooling)
        return round(score, 6)

    def _similar_score(
        self,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
        threshold: float = 0.45,
        limit: int = 12,
    ) -> tuple[float | None, int]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT provider, model, task_signature, ewma_quality, ewma_latency_ms,
                       ewma_tokens, success_pheromone, failure_pheromone,
                       success_count, failure_count
                FROM routing_stats
                WHERE provider = ? AND model = ? AND task_signature NOT IN (?, ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (
                    provider.value,
                    model,
                    task_signature,
                    _GLOBAL_SIGNATURE,
                    limit,
                ),
            ).fetchall()

        weighted_scores: list[tuple[float, float, float]] = []
        for row in rows:
            similarity = self._signature_similarity(
                task_signature,
                str(row["task_signature"]),
            )
            if similarity < threshold:
                continue
            sample_count = int(row["success_count"]) + int(row["failure_count"])
            confidence = min(1.0, sample_count / 3.0)
            weight = similarity * max(confidence, 0.2)
            weighted_scores.append((weight, self._score_row(row), similarity))

        if not weighted_scores:
            return (None, 0)

        total_weight = sum(weight for weight, _, _ in weighted_scores)
        aggregate = (
            sum(weight * score for weight, score, _ in weighted_scores) / total_weight
        )
        avg_similarity = (
            sum(weight * similarity for weight, _, similarity in weighted_scores)
            / total_weight
        )
        aggregate = min(1.0, aggregate + (0.06 * avg_similarity))
        return (round(aggregate, 6), len(weighted_scores))

    def lane_score(
        self,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
    ) -> RoutingLaneScore | None:
        with self._connect() as db:
            exact = self._load_lane(
                db,
                provider=provider,
                model=model,
                task_signature=task_signature,
            )
            global_row = self._load_lane(
                db,
                provider=provider,
                model=model,
                task_signature=_GLOBAL_SIGNATURE,
            )

        exact_score = self._score_row(exact) if exact is not None else None
        global_score = self._score_row(global_row) if global_row is not None else None
        similar_score, similar_matches = self._similar_score(
            provider=provider,
            model=model,
            task_signature=task_signature,
        )
        row = exact or global_row
        blended = self._blended_score(
            exact_score=exact_score,
            global_score=global_score,
            similar_score=similar_score,
            exact_samples=(
                int(row["success_count"]) + int(row["failure_count"])
                if row is not None
                else 0
            ),
        )
        if blended is None:
            return None
        return RoutingLaneScore(
            provider=provider,
            model=model,
            task_signature=task_signature,
            blended_score=blended,
            exact_score=exact_score,
            global_score=global_score,
            similar_score=similar_score,
            sample_count=(
                int(row["success_count"]) + int(row["failure_count"])
                if row is not None
                else 0
            ),
            similar_matches=similar_matches,
            success_pheromone=float(row["success_pheromone"]) if row is not None else 0.0,
            failure_pheromone=float(row["failure_pheromone"]) if row is not None else 0.0,
        )

    def rank_candidates(
        self,
        task_signature: str,
        candidates: Iterable[ProviderType],
        *,
        model_hints: dict[ProviderType, str | None],
    ) -> tuple[list[ProviderType], dict[ProviderType, RoutingLaneScore]]:
        ranked: list[tuple[float, int, ProviderType]] = []
        scores: dict[ProviderType, RoutingLaneScore] = {}
        for index, provider in enumerate(candidates):
            lane = self.lane_score(
                provider=provider,
                model=model_hints.get(provider) or "",
                task_signature=task_signature,
            )
            if lane is not None:
                scores[provider] = lane
            score = lane.blended_score if lane is not None else float("-inf")
            ranked.append((score, -index, provider))
        ranked.sort(reverse=True)
        return ([provider for _, _, provider in ranked], scores)

    def _upsert_lane(
        self,
        db: sqlite3.Connection,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
        success: bool,
        quality_score: float,
        latency_ms: float,
        total_tokens: int,
        error: str | None,
    ) -> None:
        existing = self._load_lane(
            db,
            provider=provider,
            model=model,
            task_signature=task_signature,
        )
        if existing is None:
            ewma_quality = quality_score
            ewma_latency_ms = latency_ms
            ewma_tokens = float(total_tokens)
            success_pheromone = 1.0 if success else 0.0
            failure_pheromone = self._failure_deposit(error) if not success else 0.0
            success_count = 1 if success else 0
            failure_count = 0 if success else 1
        else:
            alpha = self._ewma_alpha
            ewma_quality = (
                (1.0 - alpha) * float(existing["ewma_quality"])
                + alpha * quality_score
            )
            ewma_latency_ms = (
                (1.0 - alpha) * float(existing["ewma_latency_ms"])
                + alpha * latency_ms
            )
            ewma_tokens = (
                (1.0 - alpha) * float(existing["ewma_tokens"])
                + alpha * float(total_tokens)
            )
            success_pheromone = float(existing["success_pheromone"]) * self._success_decay
            failure_pheromone = float(existing["failure_pheromone"]) * self._failure_decay
            if success:
                success_pheromone += 1.0
            else:
                failure_pheromone += self._failure_deposit(error)
            success_count = int(existing["success_count"]) + (1 if success else 0)
            failure_count = int(existing["failure_count"]) + (0 if success else 1)

        db.execute(
            """
            INSERT INTO routing_stats (
                provider, model, task_signature, ewma_quality, ewma_latency_ms,
                ewma_tokens, success_pheromone, failure_pheromone,
                success_count, failure_count, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, model, task_signature) DO UPDATE SET
                ewma_quality = excluded.ewma_quality,
                ewma_latency_ms = excluded.ewma_latency_ms,
                ewma_tokens = excluded.ewma_tokens,
                success_pheromone = excluded.success_pheromone,
                failure_pheromone = excluded.failure_pheromone,
                success_count = excluded.success_count,
                failure_count = excluded.failure_count,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                provider.value,
                model,
                task_signature,
                round(ewma_quality, 6),
                round(ewma_latency_ms, 3),
                round(ewma_tokens, 3),
                round(success_pheromone, 6),
                round(failure_pheromone, 6),
                success_count,
                failure_count,
                error,
                _utc_now_iso(),
            ),
        )

    @staticmethod
    def _failure_deposit(error: str | None) -> float:
        if not error:
            return 1.0
        normalized = error.strip().lower()
        if normalized in {"circuit_open", "provider_timeout", "provider_error"}:
            return 1.5
        return 1.0

    def record_outcome(
        self,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
        action_name: str,
        route_path: str | None,
        success: bool,
        latency_ms: float,
        total_tokens: int,
        quality_score: float | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        quality = (
            _clamp01(float(quality_score))
            if quality_score is not None
            else (1.0 if success else 0.0)
        )
        payload = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        latency = max(0.0, float(latency_ms))
        tokens = max(0, int(total_tokens))
        with self._connect() as db:
            for signature in (task_signature, _GLOBAL_SIGNATURE):
                self._upsert_lane(
                    db,
                    provider=provider,
                    model=model,
                    task_signature=signature,
                    success=success,
                    quality_score=quality,
                    latency_ms=latency,
                    total_tokens=tokens,
                    error=error,
                )
            db.execute(
                """
                INSERT INTO routing_events (
                    timestamp, provider, model, task_signature, action_name,
                    route_path, outcome, quality_score, latency_ms, total_tokens,
                    error, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    provider.value,
                    model,
                    task_signature,
                    action_name,
                    route_path,
                    "success" if success else "failure",
                    quality,
                    round(latency, 3),
                    tokens,
                    error,
                    payload,
                ),
            )
            db.commit()

    def snapshot(self, *, task_signature: str | None = None) -> list[RoutingLaneScore]:
        where = ""
        params: tuple[Any, ...] = ()
        if task_signature:
            where = "WHERE task_signature = ?"
            params = (task_signature,)
        with self._connect() as db:
            rows = db.execute(
                f"""
                SELECT provider, model, task_signature
                FROM routing_stats
                {where}
                ORDER BY provider, model, task_signature
                """,
                params,
            ).fetchall()

        scores: list[RoutingLaneScore] = []
        for row in rows:
            provider = ProviderType(str(row["provider"]))
            lane = self.lane_score(
                provider=provider,
                model=str(row["model"]),
                task_signature=str(row["task_signature"]),
            )
            if lane is not None:
                scores.append(lane)
        return scores

    def top_routes(self, *, limit: int = 8) -> list[RoutingLaneScore]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT provider, model, task_signature
                FROM routing_stats
                WHERE task_signature != ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (_GLOBAL_SIGNATURE, limit * 4),
            ).fetchall()

        ranked: list[RoutingLaneScore] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (str(row["provider"]), str(row["model"]), str(row["task_signature"]))
            if key in seen:
                continue
            seen.add(key)
            lane = self.lane_score(
                provider=ProviderType(str(row["provider"])),
                model=str(row["model"]),
                task_signature=str(row["task_signature"]),
            )
            if lane is not None:
                ranked.append(lane)
        ranked.sort(
            key=lambda lane: (lane.blended_score, lane.sample_count, lane.similar_matches),
            reverse=True,
        )
        return ranked[:limit]
