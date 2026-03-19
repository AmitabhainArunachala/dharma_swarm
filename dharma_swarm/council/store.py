"""SQLite persistence for Council sessions and responses.

Stores at ~/.dharma/council.db — one row per model response,
one row per session, optional analysis/synthesis.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".dharma" / "council.db"


@dataclass
class StoredSession:
    """A persisted council session summary."""

    session_id: str
    question: str
    mode: str
    model_count: int
    created_at: float
    synthesis: str = ""


class CouncilStore:
    """SQLite store for council sessions and responses."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._ensure_db()

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS council_sessions (
                    session_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    document TEXT DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'quick',
                    tiers TEXT DEFAULT '0,1',
                    thinkodynamic INTEGER DEFAULT 0,
                    rounds INTEGER DEFAULT 1,
                    model_count INTEGER DEFAULT 0,
                    synthesis TEXT DEFAULT '',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS council_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_name TEXT DEFAULT '',
                    persona_name TEXT DEFAULT '',
                    round_num INTEGER DEFAULT 1,
                    response TEXT NOT NULL,
                    latency_ms REAL DEFAULT 0,
                    error TEXT DEFAULT '',
                    recognition_score REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES council_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_responses_session
                    ON council_responses(session_id);
            """)

    def save_session(
        self,
        session_id: str,
        question: str,
        mode: str,
        tiers: list[int],
        thinkodynamic: bool = False,
        rounds: int = 1,
        document: str = "",
    ) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO council_sessions
                   (session_id, question, document, mode, tiers,
                    thinkodynamic, rounds, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, question, document, mode,
                    ",".join(str(t) for t in tiers),
                    int(thinkodynamic), rounds, time.time(),
                ),
            )

    def save_response(
        self,
        session_id: str,
        model_id: str,
        response: str,
        model_name: str = "",
        persona_name: str = "",
        round_num: int = 1,
        latency_ms: float = 0,
        error: str = "",
        recognition_score: float = 0,
    ) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO council_responses
                   (session_id, model_id, model_name, persona_name,
                    round_num, response, latency_ms, error,
                    recognition_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, model_id, model_name, persona_name,
                    round_num, response, latency_ms, error,
                    recognition_score, time.time(),
                ),
            )

    def update_synthesis(
        self, session_id: str, synthesis: str, model_count: int = 0
    ) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE council_sessions
                   SET synthesis = ?, model_count = ?
                   WHERE session_id = ?""",
                (synthesis, model_count, session_id),
            )

    def get_session(self, session_id: str) -> StoredSession | None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM council_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredSession(
            session_id=row["session_id"],
            question=row["question"],
            mode=row["mode"],
            model_count=row["model_count"],
            created_at=row["created_at"],
            synthesis=row["synthesis"],
        )

    def get_responses(
        self, session_id: str, round_num: int | None = None
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM council_responses WHERE session_id = ?"
            params: list[Any] = [session_id]
            if round_num is not None:
                query += " AND round_num = ?"
                params.append(round_num)
            query += " ORDER BY round_num, created_at"
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def list_sessions(self, limit: int = 20) -> list[StoredSession]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM council_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            StoredSession(
                session_id=r["session_id"],
                question=r["question"],
                mode=r["mode"],
                model_count=r["model_count"],
                created_at=r["created_at"],
                synthesis=r["synthesis"],
            )
            for r in rows
        ]
