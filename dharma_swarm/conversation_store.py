"""Minimal conversation store scaffold for resident-operator bootstraps."""

from __future__ import annotations

from pathlib import Path


class ConversationStore:
    """Small SQLite-backed placeholder until the fuller store is restored."""

    def __init__(self, *, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    async def init_db(self) -> Path:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return self.db_path

    async def close(self) -> None:
        return None
