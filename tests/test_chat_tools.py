from __future__ import annotations

import pytest

from api.chat_tools import exec_stigmergy_query
from dharma_swarm.stigmergy import StigmergicMark


@pytest.mark.asyncio
async def test_exec_stigmergy_query_awaits_async_store_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStore:
        def density(self) -> int:
            return 1

        async def read_marks(self, *, limit: int = 20, **_kwargs):
            return [
                StigmergicMark(
                    agent="tester",
                    file_path="core.py",
                    action="observe",
                    observation=f"recent-{limit}",
                    salience=0.8,
                )
            ]

        async def hot_paths(self, **_kwargs):
            return [("core.py", 4), ("other.py", 2)]

        async def high_salience(self, *, limit: int = 20, **_kwargs):
            return [
                StigmergicMark(
                    agent="tester",
                    file_path=f"high-{limit}.py",
                    action="observe",
                    observation="important",
                    salience=0.95,
                )
            ]

    monkeypatch.setattr("dharma_swarm.stigmergy.StigmergyStore", FakeStore)

    recent = await exec_stigmergy_query({"action": "recent", "limit": 3})
    assert "core.py" in recent
    assert "recent-3" in recent

    hot_paths = await exec_stigmergy_query({"action": "hot_paths", "limit": 1})
    assert "core.py" in hot_paths
    assert "other.py" not in hot_paths

    high = await exec_stigmergy_query({"action": "high_salience", "limit": 2})
    assert "high-2.py" in high
