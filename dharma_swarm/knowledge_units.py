"""knowledge_units.py — Structured knowledge storage inspired by PlugMem.

Decomposes episodic memory into two atomic types:
  - **Proposition**: factual claim with concept tags and provenance
  - **Prescription**: reusable skill/procedure with return score tracking

KnowledgeStore provides SQLite-backed persistence with concept-centric
retrieval — route by concept overlap, not embedding similarity.

Environment variables:
  KNOWLEDGE_DB_PATH  — SQLite file path (default: alongside state dir)
  KNOWLEDGE_MAX_TOKENS — max tokens for knowledge block (default: 500)
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Union

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


# ── Knowledge Unit Dataclasses ────────────────────────────────────────────


@dataclass
class Proposition:
    """A propositional knowledge unit — an atomic factual claim.

    Example:
        content: "GPT-4 achieves 86.4% on MMLU"
        concepts: ["GPT-4", "MMLU", "benchmark", "language-model"]
        provenance_event_id: "runtime-event-abc123"
        confidence: 0.92
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    concepts: List[str] = field(default_factory=list)
    provenance_event_id: Optional[str] = None
    provenance_context: Optional[str] = None
    confidence: float = 1.0
    created_at: datetime = field(default_factory=_utc_now)
    last_accessed: datetime = field(default_factory=_utc_now)
    access_count: int = 0
    superseded_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "concepts": list(self.concepts),
            "provenance_event_id": self.provenance_event_id,
            "provenance_context": self.provenance_context,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Proposition:
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()

        last_accessed = d.get("last_accessed")
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)
        elif last_accessed is None:
            last_accessed = _utc_now()

        return cls(
            id=d.get("id", str(uuid.uuid4())),
            content=d.get("content", ""),
            concepts=d.get("concepts", []),
            provenance_event_id=d.get("provenance_event_id"),
            provenance_context=d.get("provenance_context"),
            confidence=d.get("confidence", 1.0),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=d.get("access_count", 0),
            superseded_by=d.get("superseded_by"),
        )


@dataclass
class Prescription:
    """A prescriptive knowledge unit — a reusable skill/procedure.

    Example:
        intent: "debug a failing pytest test"
        workflow: ["1. Read the error traceback", "2. Locate the failing assertion",
                   "3. Check the test fixture setup", "4. Verify the function under test"]
        return_score: 0.85
        concepts: ["debugging", "pytest", "testing"]
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    workflow: List[str] = field(default_factory=list)
    return_score: float = 0.0
    concepts: List[str] = field(default_factory=list)
    provenance_event_id: Optional[str] = None
    provenance_context: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    last_accessed: datetime = field(default_factory=_utc_now)
    access_count: int = 0
    success_count: int = 0
    attempt_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "intent": self.intent,
            "workflow": list(self.workflow),
            "return_score": self.return_score,
            "concepts": list(self.concepts),
            "provenance_event_id": self.provenance_event_id,
            "provenance_context": self.provenance_context,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "success_count": self.success_count,
            "attempt_count": self.attempt_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Prescription:
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()

        last_accessed = d.get("last_accessed")
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)
        elif last_accessed is None:
            last_accessed = _utc_now()

        return cls(
            id=d.get("id", str(uuid.uuid4())),
            intent=d.get("intent", ""),
            workflow=d.get("workflow", []),
            return_score=d.get("return_score", 0.0),
            concepts=d.get("concepts", []),
            provenance_event_id=d.get("provenance_event_id"),
            provenance_context=d.get("provenance_context"),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=d.get("access_count", 0),
            success_count=d.get("success_count", 0),
            attempt_count=d.get("attempt_count", 0),
        )


# ── KnowledgeStore — SQLite-backed storage ────────────────────────────────


class KnowledgeStore:
    """SQLite-backed storage for propositions and prescriptions.

    Three tables:
      - propositions: atomic factual claims
      - prescriptions: reusable skills/procedures
      - concept_index: concept → knowledge_unit_id mapping for fast lookup

    Concept-centric retrieval scores by:
      concept_overlap × recency × confidence/return_score
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS propositions (
        id                  TEXT PRIMARY KEY,
        content             TEXT NOT NULL DEFAULT '',
        concepts            TEXT NOT NULL DEFAULT '[]',
        provenance_event_id TEXT,
        provenance_context  TEXT,
        confidence          REAL NOT NULL DEFAULT 1.0,
        created_at          TEXT NOT NULL,
        last_accessed       TEXT NOT NULL,
        access_count        INTEGER NOT NULL DEFAULT 0,
        superseded_by       TEXT
    );

    CREATE TABLE IF NOT EXISTS prescriptions (
        id                  TEXT PRIMARY KEY,
        intent              TEXT NOT NULL DEFAULT '',
        workflow            TEXT NOT NULL DEFAULT '[]',
        return_score        REAL NOT NULL DEFAULT 0.0,
        concepts            TEXT NOT NULL DEFAULT '[]',
        provenance_event_id TEXT,
        provenance_context  TEXT,
        created_at          TEXT NOT NULL,
        last_accessed       TEXT NOT NULL,
        access_count        INTEGER NOT NULL DEFAULT 0,
        success_count       INTEGER NOT NULL DEFAULT 0,
        attempt_count       INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS concept_index (
        concept         TEXT NOT NULL,
        unit_id         TEXT NOT NULL,
        unit_type       TEXT NOT NULL,
        PRIMARY KEY (concept, unit_id)
    );

    CREATE INDEX IF NOT EXISTS idx_concept_index_concept
        ON concept_index(concept);
    CREATE INDEX IF NOT EXISTS idx_concept_index_unit
        ON concept_index(unit_id);
    CREATE INDEX IF NOT EXISTS idx_propositions_superseded
        ON propositions(superseded_by);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self._DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> KnowledgeStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Store operations ──────────────────────────────────────────────

    def store_proposition(self, prop: Proposition) -> str:
        """Store a proposition and index its concepts. Returns the proposition ID."""
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO propositions
                (id, content, concepts, provenance_event_id, provenance_context,
                 confidence, created_at, last_accessed, access_count, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                concepts = excluded.concepts,
                provenance_event_id = excluded.provenance_event_id,
                provenance_context = excluded.provenance_context,
                confidence = excluded.confidence,
                last_accessed = excluded.last_accessed,
                access_count = excluded.access_count,
                superseded_by = excluded.superseded_by
            """,
            (
                prop.id,
                prop.content,
                json.dumps(prop.concepts),
                prop.provenance_event_id,
                prop.provenance_context,
                prop.confidence,
                prop.created_at.isoformat(),
                now,
                prop.access_count,
                prop.superseded_by,
            ),
        )
        # Index concepts
        self._conn.execute(
            "DELETE FROM concept_index WHERE unit_id = ?", (prop.id,)
        )
        for concept in prop.concepts:
            concept_lower = concept.lower().strip()
            if concept_lower:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO concept_index (concept, unit_id, unit_type)
                    VALUES (?, ?, 'proposition')
                    """,
                    (concept_lower, prop.id),
                )
        self._conn.commit()
        return prop.id

    def store_prescription(self, presc: Prescription) -> str:
        """Store a prescription and index its concepts. Returns the prescription ID."""
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO prescriptions
                (id, intent, workflow, return_score, concepts,
                 provenance_event_id, provenance_context,
                 created_at, last_accessed, access_count,
                 success_count, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                intent = excluded.intent,
                workflow = excluded.workflow,
                return_score = excluded.return_score,
                concepts = excluded.concepts,
                provenance_event_id = excluded.provenance_event_id,
                provenance_context = excluded.provenance_context,
                last_accessed = excluded.last_accessed,
                access_count = excluded.access_count,
                success_count = excluded.success_count,
                attempt_count = excluded.attempt_count
            """,
            (
                presc.id,
                presc.intent,
                json.dumps(presc.workflow),
                presc.return_score,
                json.dumps(presc.concepts),
                presc.provenance_event_id,
                presc.provenance_context,
                presc.created_at.isoformat(),
                now,
                presc.access_count,
                presc.success_count,
                presc.attempt_count,
            ),
        )
        # Index concepts
        self._conn.execute(
            "DELETE FROM concept_index WHERE unit_id = ?", (presc.id,)
        )
        for concept in presc.concepts:
            concept_lower = concept.lower().strip()
            if concept_lower:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO concept_index (concept, unit_id, unit_type)
                    VALUES (?, ?, 'prescription')
                    """,
                    (concept_lower, presc.id),
                )
        self._conn.commit()
        return presc.id

    # ── Retrieval ─────────────────────────────────────────────────────

    def get_by_concepts(
        self,
        concepts: List[str],
        unit_type: str = "both",
        limit: int = 10,
    ) -> List[Union[Proposition, Prescription]]:
        """Concept-centric retrieval.

        Scores by concept overlap × recency × confidence/return_score.
        This is the core PlugMem innovation: route by concept, not embedding similarity.
        """
        if not concepts:
            return []

        normalized = [c.lower().strip() for c in concepts if c.strip()]
        if not normalized:
            return []

        # Find matching unit IDs via concept index
        placeholders = ",".join("?" for _ in normalized)
        type_filter = ""
        if unit_type == "proposition":
            type_filter = " AND unit_type = 'proposition'"
        elif unit_type == "prescription":
            type_filter = " AND unit_type = 'prescription'"

        rows = self._conn.execute(
            f"""
            SELECT unit_id, unit_type, COUNT(*) as overlap_count
            FROM concept_index
            WHERE concept IN ({placeholders}){type_filter}
            GROUP BY unit_id, unit_type
            ORDER BY overlap_count DESC
            """,
            normalized,
        ).fetchall()

        results: List[Union[Proposition, Prescription]] = []
        now = _utc_now()

        for row in rows:
            unit_id = row["unit_id"]
            u_type = row["unit_type"]
            overlap = row["overlap_count"]

            unit = self._load_unit(unit_id, u_type)
            if unit is None:
                continue

            # Skip superseded propositions
            if isinstance(unit, Proposition) and unit.superseded_by:
                continue

            # Score: concept_overlap × recency × quality
            overlap_score = overlap / len(normalized)
            age_days = max(0.0, (now - unit.created_at).total_seconds() / 86400.0)
            recency_score = math.exp(-age_days / 30.0)  # 30-day half-life

            if isinstance(unit, Proposition):
                quality = unit.confidence
            else:
                quality = max(0.1, unit.return_score)

            score = overlap_score * 0.5 + recency_score * 0.25 + quality * 0.25
            results.append((score, unit))  # type: ignore[arg-type]

            # Update access tracking
            self._touch_unit(unit_id, u_type)

        # Sort by composite score descending
        results.sort(key=lambda x: x[0], reverse=True)  # type: ignore[union-attr]
        return [item[1] for item in results[:limit]]  # type: ignore[index]

    def get_propositions_for_context(
        self,
        task_concepts: List[str],
        max_tokens: int = 500,
    ) -> List[Proposition]:
        """Get task-relevant propositions, respecting token budget."""
        units = self.get_by_concepts(task_concepts, unit_type="proposition", limit=20)
        props = [u for u in units if isinstance(u, Proposition)]

        # Approximate token budget (4 chars ≈ 1 token)
        char_budget = max_tokens * 4
        selected: List[Proposition] = []
        chars_used = 0

        for prop in props:
            prop_chars = len(prop.content) + 30  # overhead for formatting
            if chars_used + prop_chars > char_budget:
                break
            selected.append(prop)
            chars_used += prop_chars

        return selected

    def get_prescriptions_for_intent(
        self,
        intent: str,
        concepts: List[str],
    ) -> List[Prescription]:
        """Get relevant skills for a given intent."""
        units = self.get_by_concepts(concepts, unit_type="prescription", limit=10)
        prescriptions = [u for u in units if isinstance(u, Prescription)]

        # Secondary scoring: boost prescriptions whose intent overlaps with query
        if intent:
            intent_words = set(intent.lower().split())
            scored: List[tuple[float, Prescription]] = []
            for presc in prescriptions:
                presc_words = set(presc.intent.lower().split())
                if intent_words and presc_words:
                    intent_overlap = len(intent_words & presc_words) / max(
                        1, len(intent_words | presc_words)
                    )
                else:
                    intent_overlap = 0.0
                score = intent_overlap * 0.4 + presc.return_score * 0.6
                scored.append((score, presc))
            scored.sort(key=lambda x: x[0], reverse=True)
            prescriptions = [item[1] for item in scored]

        return prescriptions[:5]

    def update_return_score(self, prescription_id: str, success: bool) -> None:
        """Update prescription return_score based on outcome."""
        row = self._conn.execute(
            "SELECT return_score, success_count, attempt_count FROM prescriptions WHERE id = ?",
            (prescription_id,),
        ).fetchone()
        if row is None:
            return

        success_count = row["success_count"] + (1 if success else 0)
        attempt_count = row["attempt_count"] + 1
        new_score = success_count / attempt_count if attempt_count > 0 else 0.0

        self._conn.execute(
            """
            UPDATE prescriptions
            SET return_score = ?, success_count = ?, attempt_count = ?,
                last_accessed = ?
            WHERE id = ?
            """,
            (new_score, success_count, attempt_count, _utc_now_iso(), prescription_id),
        )
        self._conn.commit()

    def supersede_proposition(self, old_id: str, new_prop: Proposition) -> None:
        """Mark old proposition as superseded by new one (fact correction)."""
        self.store_proposition(new_prop)
        self._conn.execute(
            "UPDATE propositions SET superseded_by = ? WHERE id = ?",
            (new_prop.id, old_id),
        )
        self._conn.commit()

    # ── Provenance-based retrieval (Darwin Engine) ─────────────────

    def get_by_agent_provenance(
        self,
        agent_id: str,
        unit_type: str = "both",
        limit: int = 100,
    ) -> List[Union[Proposition, Prescription]]:
        """Get knowledge units that trace back to a specific agent.

        Searches provenance_event_id and provenance_context for the agent_id
        string.  Used by the Darwin Engine to measure an agent's knowledge
        production for fitness scoring.
        """
        results: List[Union[Proposition, Prescription]] = []

        if unit_type in ("both", "proposition"):
            rows = self._conn.execute(
                """
                SELECT * FROM propositions
                WHERE provenance_event_id LIKE ? OR provenance_context LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (f"%{agent_id}%", f"%{agent_id}%", limit),
            ).fetchall()
            results.extend(self._row_to_proposition(r) for r in rows)

        if unit_type in ("both", "prescription"):
            rows = self._conn.execute(
                """
                SELECT * FROM prescriptions
                WHERE provenance_event_id LIKE ? OR provenance_context LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (f"%{agent_id}%", f"%{agent_id}%", limit),
            ).fetchall()
            results.extend(self._row_to_prescription(r) for r in rows)

        return results[:limit]

    # ── Internal helpers ──────────────────────────────────────────────

    def _load_unit(
        self, unit_id: str, unit_type: str
    ) -> Union[Proposition, Prescription, None]:
        if unit_type == "proposition":
            row = self._conn.execute(
                "SELECT * FROM propositions WHERE id = ?", (unit_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_proposition(row)
        elif unit_type == "prescription":
            row = self._conn.execute(
                "SELECT * FROM prescriptions WHERE id = ?", (unit_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_prescription(row)
        return None

    def _touch_unit(self, unit_id: str, unit_type: str) -> None:
        table = "propositions" if unit_type == "proposition" else "prescriptions"
        try:
            self._conn.execute(
                f"""
                UPDATE {table}
                SET access_count = access_count + 1, last_accessed = ?
                WHERE id = ?
                """,
                (_utc_now_iso(), unit_id),
            )
            self._conn.commit()
        except Exception:
            pass

    @staticmethod
    def _row_to_proposition(row: sqlite3.Row) -> Proposition:
        d = dict(row)
        concepts = d.get("concepts", "[]")
        if isinstance(concepts, str):
            concepts = json.loads(concepts)

        created_at = d.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = _utc_now()

        last_accessed = d.get("last_accessed", "")
        if isinstance(last_accessed, str) and last_accessed:
            last_accessed = datetime.fromisoformat(last_accessed)
        else:
            last_accessed = _utc_now()

        return Proposition(
            id=d["id"],
            content=d.get("content", ""),
            concepts=concepts,
            provenance_event_id=d.get("provenance_event_id"),
            provenance_context=d.get("provenance_context"),
            confidence=d.get("confidence", 1.0),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=d.get("access_count", 0),
            superseded_by=d.get("superseded_by"),
        )

    @staticmethod
    def _row_to_prescription(row: sqlite3.Row) -> Prescription:
        d = dict(row)
        workflow = d.get("workflow", "[]")
        if isinstance(workflow, str):
            workflow = json.loads(workflow)
        concepts = d.get("concepts", "[]")
        if isinstance(concepts, str):
            concepts = json.loads(concepts)

        created_at = d.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = _utc_now()

        last_accessed = d.get("last_accessed", "")
        if isinstance(last_accessed, str) and last_accessed:
            last_accessed = datetime.fromisoformat(last_accessed)
        else:
            last_accessed = _utc_now()

        return Prescription(
            id=d["id"],
            intent=d.get("intent", ""),
            workflow=workflow,
            return_score=d.get("return_score", 0.0),
            concepts=concepts,
            provenance_event_id=d.get("provenance_event_id"),
            provenance_context=d.get("provenance_context"),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=d.get("access_count", 0),
            success_count=d.get("success_count", 0),
            attempt_count=d.get("attempt_count", 0),
        )


def get_default_knowledge_db_path() -> str:
    """Return the default KnowledgeStore DB path from env or state dir."""
    explicit = os.getenv("KNOWLEDGE_DB_PATH")
    if explicit:
        return explicit
    state_dir = os.getenv("DHARMA_STATE_DIR", os.path.expanduser("~/.dharma/state"))
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, "knowledge.db")


__all__ = [
    "Proposition",
    "Prescription",
    "KnowledgeStore",
    "get_default_knowledge_db_path",
]
