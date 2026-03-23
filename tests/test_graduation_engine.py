"""Tests for graduation_engine.py — minimal lifecycle scaffold."""

from __future__ import annotations

import pytest

from dharma_swarm.graduation_engine import GraduationEngine


class TestGraduationEngine:
    def test_construction(self, tmp_path):
        db = tmp_path / "grad.db"
        engine = GraduationEngine(db_path=db)
        assert engine.db_path == db

    def test_construction_str(self, tmp_path):
        engine = GraduationEngine(db_path=str(tmp_path / "grad.db"))
        assert engine.db_path == tmp_path / "grad.db"

    @pytest.mark.asyncio
    async def test_init_db(self, tmp_path):
        db = tmp_path / "subdir" / "grad.db"
        engine = GraduationEngine(db_path=db)
        result = await engine.init_db()
        assert result == db
        assert db.parent.exists()

    @pytest.mark.asyncio
    async def test_close(self, tmp_path):
        engine = GraduationEngine(db_path=tmp_path / "grad.db")
        result = await engine.close()
        assert result is None
