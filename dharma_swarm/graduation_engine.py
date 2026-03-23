"""Minimal graduation engine scaffold for resident-operator adoption tests."""

from __future__ import annotations

from pathlib import Path


class GraduationEngine:
    """Placeholder lifecycle surface for runtime adoption wiring."""

    def __init__(self, *, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    async def init_db(self) -> Path:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return self.db_path

    async def close(self) -> None:
        return None
