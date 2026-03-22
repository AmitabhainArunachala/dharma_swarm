"""Tests for conversation_store.py — minimal SQLite-backed scaffold."""

from __future__ import annotations

import pytest

from dharma_swarm.conversation_store import ConversationStore


class TestConversationStore:
    def test_construction(self, tmp_path):
        db = tmp_path / "conv.db"
        store = ConversationStore(db_path=db)
        assert store.db_path == db

    def test_construction_str(self, tmp_path):
        store = ConversationStore(db_path=str(tmp_path / "conv.db"))
        assert store.db_path == tmp_path / "conv.db"

    @pytest.mark.asyncio
    async def test_init_db(self, tmp_path):
        db = tmp_path / "subdir" / "conv.db"
        store = ConversationStore(db_path=db)
        result = await store.init_db()
        assert result == db
        assert db.parent.exists()

    @pytest.mark.asyncio
    async def test_close(self, tmp_path):
        store = ConversationStore(db_path=tmp_path / "conv.db")
        result = await store.close()
        assert result is None
