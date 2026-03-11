"""Conversation flow capture, idea harvesting, and latent-gold recall."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dharma_swarm.engine.event_memory import (
    DEFAULT_MEMORY_PLANE_DB,
    ensure_memory_plane_schema_sync,
)
from dharma_swarm.engine.knowledge_store import _jaccard, _tokenize


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").strip()


def _score(query: str, text: str) -> float:
    normalized_query = _normalize(query)
    normalized_text = _normalize(text)
    tokens = _tokenize(normalized_query)
    score = _jaccard(tokens, _tokenize(normalized_text))
    if normalized_query and normalized_query in normalized_text:
        score += 0.5
    return round(score, 6)


def _detect_flow_score(text: str) -> float:
    normalized = _normalize(text)
    if not normalized:
        return 0.0
    connectors = sum(
        normalized.count(token)
        for token in (
            "maybe",
            "what if",
            "could",
            "should",
            "also",
            "another",
            "or",
            "and",
            "?",
        )
    )
    sentence_count = max(1, len(re.findall(r"[.!?\n]+", normalized)))
    token_count = len(_tokenize(normalized))
    score = min(1.0, (connectors / sentence_count) * 0.18 + (token_count / 120.0))
    return round(score, 6)


def _flow_state(flow_score: float) -> str:
    if flow_score >= 0.8:
        return "frenzied"
    if flow_score >= 0.45:
        return "flow"
    return "steady"


def _split_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip(" -*\t")
        if not line:
            continue
        if len(line) >= 24:
            candidates.append(line)
    if candidates:
        return candidates
    return [
        chunk.strip()
        for chunk in re.split(r"(?<=[.!?])\s+", text)
        if len(chunk.strip()) >= 24
    ]


def _classify_candidate(text: str) -> str:
    normalized = _normalize(text)
    if "?" in text or normalized.startswith(("what if", "why", "how")):
        return "question"
    if any(token in normalized for token in ("warning", "risk", "danger", "don't", "avoid")):
        return "warning"
    if any(token in normalized for token in ("todo", "next", "follow up", "later", "defer")):
        return "todo"
    if any(token in normalized for token in ("could", "should", "build", "add", "use", "implement", "maybe", "we can")):
        return "proposal"
    if any(token in normalized for token in ("because", "implies", "means", "therefore", "suggests")):
        return "hypothesis"
    return "insight"


def _salience_score(text: str, flow_score: float) -> float:
    normalized = _normalize(text)
    token_count = len(_tokenize(normalized))
    keyword_hits = sum(
        1
        for token in (
            "memory",
            "retrieve",
            "index",
            "graph",
            "agent",
            "runtime",
            "prompt",
            "conversation",
            "idea",
            "plan",
            "context",
            "telemetry",
        )
        if token in normalized
    )
    question_bonus = 0.12 if "?" in text else 0.0
    score = min(1.0, 0.18 + (token_count / 48.0) + (keyword_hits * 0.07) + question_bonus + (flow_score * 0.18))
    return round(score, 6)


def _novelty_score(text: str, prior_texts: list[str]) -> float:
    if not prior_texts:
        return 1.0
    similarity = max((_jaccard(_tokenize(_normalize(text)), _tokenize(_normalize(prior))) for prior in prior_texts), default=0.0)
    return round(max(0.0, 1.0 - similarity), 6)


def _turn_threshold(flow_score: float) -> float:
    return 0.46 if flow_score >= 0.45 else 0.62


def _as_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


@dataclass(slots=True)
class ConversationTurn:
    turn_id: str
    session_id: str
    task_id: str
    role: str
    content: str
    flow_state: str
    turn_index: int
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IdeaShard:
    shard_id: str
    turn_id: str
    session_id: str
    task_id: str
    shard_kind: str
    state: str
    text: str
    salience: float
    novelty: float
    flow_score: float
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationMemoryStore:
    """Stores raw conversation turns and harvests atomic idea shards."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)

    def record_turn(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        task_id: str = "",
        turn_index: int = 0,
        metadata: dict[str, Any] | None = None,
        harvest: bool = True,
    ) -> str:
        turn_id = f"turn_{uuid4().hex}"
        flow_score = _detect_flow_score(content)
        payload = dict(metadata or {})
        payload["flow_score"] = flow_score
        created_at = _utc_now_iso()

        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.execute(
                "INSERT INTO conversation_turns"
                " (turn_id, session_id, task_id, role, content, flow_state, turn_index, metadata_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    session_id,
                    task_id,
                    role,
                    content,
                    _flow_state(flow_score),
                    int(turn_index),
                    json.dumps(payload, sort_keys=True, ensure_ascii=True),
                    created_at,
                ),
            )
            db.commit()

        if harvest:
            self.harvest_turn(turn_id)
        return turn_id

    def harvest_turn(self, turn_id: str) -> list[IdeaShard]:
        turn = self.get_turn(turn_id)
        if turn is None:
            return []

        candidates = _split_candidates(turn.content)
        threshold = _turn_threshold(turn.metadata.get("flow_score", _detect_flow_score(turn.content)))
        prior_texts = [row["text"] for row in self._recent_shard_rows(turn.session_id, limit=200)]
        harvested: list[IdeaShard] = []

        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            for candidate in candidates:
                flow_score = float(turn.metadata.get("flow_score", _detect_flow_score(turn.content)))
                salience = _salience_score(candidate, flow_score)
                novelty = _novelty_score(candidate, prior_texts)
                if salience < threshold:
                    continue
                shard_kind = _classify_candidate(candidate)
                shard_id = f"shd_{uuid4().hex}"
                state = "proposed" if shard_kind in {"proposal", "hypothesis", "todo", "question", "insight"} else "connected"
                metadata = {
                    "role": turn.role,
                    "flow_state": turn.flow_state,
                    "candidate_index": len(harvested),
                }
                db.execute(
                    "INSERT INTO idea_shards"
                    " (shard_id, turn_id, session_id, task_id, shard_kind, state, text,"
                    " salience, novelty, flow_score, source_span, metadata_json, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        shard_id,
                        turn.turn_id,
                        turn.session_id,
                        turn.task_id,
                        shard_kind,
                        state,
                        candidate,
                        salience,
                        novelty,
                        flow_score,
                        candidate[:120],
                        json.dumps(metadata, sort_keys=True, ensure_ascii=True),
                        _utc_now_iso(),
                    ),
                )
                harvested.append(
                    IdeaShard(
                        shard_id=shard_id,
                        turn_id=turn.turn_id,
                        session_id=turn.session_id,
                        task_id=turn.task_id,
                        shard_kind=shard_kind,
                        state=state,
                        text=candidate,
                        salience=salience,
                        novelty=novelty,
                        flow_score=flow_score,
                        created_at=datetime.now(timezone.utc),
                        metadata=metadata,
                    )
                )
            db.commit()

        self._link_harvested_shards(turn, harvested)
        return harvested

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT turn_id, session_id, task_id, role, content, flow_state, turn_index, metadata_json, created_at"
                " FROM conversation_turns WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()
        if row is None:
            return None
        return ConversationTurn(
            turn_id=row["turn_id"],
            session_id=row["session_id"],
            task_id=row["task_id"],
            role=row["role"],
            content=row["content"],
            flow_state=row["flow_state"],
            turn_index=int(row["turn_index"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=_as_metadata(row["metadata_json"]),
        )

    def record_uptake_from_text(
        self,
        *,
        task_id: str,
        text: str,
        uptake_kind: str = "implemented",
    ) -> int:
        if not task_id.strip() or not text.strip():
            return 0
        shards = self._task_shards(task_id, states=("proposed", "connected", "orphaned", "deferred"))
        matched_ids: set[str] = set()
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            for shard in shards:
                score = _score(shard.text, text)
                if score < 0.28:
                    continue
                matched_ids.add(shard.shard_id)
                db.execute(
                    "INSERT INTO idea_uptake"
                    " (uptake_id, shard_id, task_id, uptake_kind, evidence_text, metadata_json, recorded_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"iup_{uuid4().hex}",
                        shard.shard_id,
                        task_id,
                        uptake_kind,
                        text[:500],
                        json.dumps({"score": score}, sort_keys=True, ensure_ascii=True),
                        _utc_now_iso(),
                    ),
                )
                db.execute(
                    "UPDATE idea_shards SET state = ? WHERE shard_id = ?",
                    ("implemented" if uptake_kind == "implemented" else "used", shard.shard_id),
                )

            # Preserve high-salience alternatives that were not chosen.
            for shard in shards:
                if shard.shard_id in matched_ids:
                    continue
                if shard.salience < 0.55:
                    continue
                db.execute(
                    "UPDATE idea_shards SET state = ? WHERE shard_id = ? AND state NOT IN ('implemented', 'used')",
                    ("orphaned", shard.shard_id),
                )
            db.commit()
        return len(matched_ids)

    def record_follow_up_task(
        self,
        *,
        shard_id: str,
        follow_up_task_id: str,
        title: str,
    ) -> bool:
        if not shard_id.strip() or not follow_up_task_id.strip():
            return False
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            row = db.execute(
                "SELECT shard_id FROM idea_shards WHERE shard_id = ?",
                (shard_id,),
            ).fetchone()
            if row is None:
                return False
            db.execute(
                "INSERT INTO idea_uptake"
                " (uptake_id, shard_id, task_id, uptake_kind, evidence_text, metadata_json, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"iup_{uuid4().hex}",
                    shard_id,
                    follow_up_task_id,
                    "follow_up_task",
                    title[:500],
                    json.dumps(
                        {"follow_up_task_id": follow_up_task_id},
                        sort_keys=True,
                        ensure_ascii=True,
                    ),
                    _utc_now_iso(),
                ),
            )
            db.execute(
                "UPDATE idea_shards SET state = ? WHERE shard_id = ?",
                ("reopened", shard_id),
            )
            db.commit()
        return True

    def record_follow_up_outcome(
        self,
        *,
        shard_id: str,
        follow_up_task_id: str,
        outcome: str,
        evidence_text: str = "",
    ) -> bool:
        normalized = outcome.strip().lower()
        if (
            not shard_id.strip()
            or not follow_up_task_id.strip()
            or normalized not in {"success", "failure"}
        ):
            return False
        target_state = "implemented" if normalized == "success" else "deferred"
        uptake_kind = (
            "follow_up_completed"
            if normalized == "success"
            else "follow_up_failed"
        )
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            row = db.execute(
                "SELECT shard_id FROM idea_shards WHERE shard_id = ?",
                (shard_id,),
            ).fetchone()
            if row is None:
                return False
            db.execute(
                "INSERT INTO idea_uptake"
                " (uptake_id, shard_id, task_id, uptake_kind, evidence_text, metadata_json, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"iup_{uuid4().hex}",
                    shard_id,
                    follow_up_task_id,
                    uptake_kind,
                    evidence_text[:500],
                    json.dumps(
                        {
                            "follow_up_task_id": follow_up_task_id,
                            "outcome": normalized,
                        },
                        sort_keys=True,
                        ensure_ascii=True,
                    ),
                    _utc_now_iso(),
                ),
            )
            db.execute(
                "UPDATE idea_shards SET state = ? WHERE shard_id = ?",
                (target_state, shard_id),
            )
            db.commit()
        return True

    def mark_task_outcome(self, task_id: str, *, outcome: str) -> int:
        normalized = outcome.strip().lower()
        if normalized not in {"success", "failure"}:
            return 0
        target_state = "orphaned" if normalized == "success" else "deferred"
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            cursor = db.execute(
                "UPDATE idea_shards SET state = ?"
                " WHERE task_id = ? AND state IN ('proposed', 'connected')",
                (target_state, task_id),
            )
            db.commit()
        return int(cursor.rowcount or 0)

    def latent_gold(self, query: str, *, limit: int = 5) -> list[IdeaShard]:
        normalized_query = query.strip()
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT shard_id, turn_id, session_id, task_id, shard_kind, state, text,"
                " salience, novelty, flow_score, metadata_json, created_at"
                " FROM idea_shards"
                " WHERE state IN ('orphaned', 'deferred', 'proposed', 'connected')"
                " ORDER BY created_at DESC LIMIT 500",
            ).fetchall()

        scored: list[tuple[IdeaShard, float]] = []
        for row in rows:
            shard = IdeaShard(
                shard_id=row["shard_id"],
                turn_id=row["turn_id"],
                session_id=row["session_id"],
                task_id=row["task_id"],
                shard_kind=row["shard_kind"],
                state=row["state"],
                text=row["text"],
                salience=float(row["salience"]),
                novelty=float(row["novelty"]),
                flow_score=float(row["flow_score"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                metadata=_as_metadata(row["metadata_json"]),
            )
            retrieval = _score(normalized_query, shard.text) if normalized_query else 0.0
            state_bonus = {"orphaned": 0.12, "deferred": 0.10, "proposed": 0.04, "connected": 0.03}.get(shard.state, 0.0)
            total = retrieval + (0.25 * shard.salience) + (0.12 * shard.novelty) + state_bonus
            if normalized_query and total < 0.35:
                continue
            scored.append((shard, round(total, 6)))
        scored.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
        return [shard for shard, _score_value in scored[: max(1, limit)]]

    def recent_turns(self, *, task_id: str | None = None, limit: int = 20) -> list[ConversationTurn]:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            if task_id:
                rows = db.execute(
                    "SELECT turn_id, session_id, task_id, role, content, flow_state, turn_index, metadata_json, created_at"
                    " FROM conversation_turns WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                    (task_id, max(1, limit)),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT turn_id, session_id, task_id, role, content, flow_state, turn_index, metadata_json, created_at"
                    " FROM conversation_turns ORDER BY created_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
        return [
            ConversationTurn(
                turn_id=row["turn_id"],
                session_id=row["session_id"],
                task_id=row["task_id"],
                role=row["role"],
                content=row["content"],
                flow_state=row["flow_state"],
                turn_index=int(row["turn_index"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                metadata=_as_metadata(row["metadata_json"]),
            )
            for row in rows
        ]

    def _recent_shard_rows(self, session_id: str, *, limit: int) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT text FROM idea_shards WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, max(1, limit)),
            ).fetchall()
        return [{"text": row["text"]} for row in rows]

    def _link_harvested_shards(self, turn: ConversationTurn, shards: list[IdeaShard]) -> None:
        if len(shards) < 2:
            return
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            for index, left in enumerate(shards):
                for right in shards[index + 1 :]:
                    relation = "alternative_to" if left.shard_kind == right.shard_kind else "related_to"
                    weight = 0.4 + (_jaccard(_tokenize(_normalize(left.text)), _tokenize(_normalize(right.text))) * 0.4)
                    db.execute(
                        "INSERT INTO idea_links"
                        " (link_id, from_shard_id, to_shard_id, relation, weight, metadata_json, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            f"lnk_{uuid4().hex}",
                            left.shard_id,
                            right.shard_id,
                            relation,
                            round(weight, 6),
                            json.dumps({"turn_id": turn.turn_id}, sort_keys=True, ensure_ascii=True),
                            _utc_now_iso(),
                        ),
                    )
            db.commit()

    def _task_shards(self, task_id: str, *, states: tuple[str, ...]) -> list[IdeaShard]:
        placeholders = ", ".join("?" for _ in states)
        with sqlite3.connect(str(self.db_path)) as db:
            ensure_memory_plane_schema_sync(db)
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT shard_id, turn_id, session_id, task_id, shard_kind, state, text,"
                " salience, novelty, flow_score, metadata_json, created_at"
                f" FROM idea_shards WHERE task_id = ? AND state IN ({placeholders})"
                " ORDER BY created_at DESC",
                (task_id, *states),
            ).fetchall()
        return [
            IdeaShard(
                shard_id=row["shard_id"],
                turn_id=row["turn_id"],
                session_id=row["session_id"],
                task_id=row["task_id"],
                shard_kind=row["shard_kind"],
                state=row["state"],
                text=row["text"],
                salience=float(row["salience"]),
                novelty=float(row["novelty"]),
                flow_score=float(row["flow_score"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                metadata=_as_metadata(row["metadata_json"]),
            )
            for row in rows
        ]
