from __future__ import annotations

import json

import dharma_swarm.dgc_cli as cli


class _FakeMemory:
    async def init_db(self) -> None:
        return None

    async def recall(self, limit: int = 10):
        return []

    async def close(self) -> None:
        return None


class _FakeRoutingMemory:
    def __init__(self, _path) -> None:
        return None

    def top_routes(self, *, limit: int = 5):
        return []


def test_cmd_memory_shows_route_retrospectives(monkeypatch, tmp_path, capsys) -> None:
    retrospective_path = tmp_path / "route_retrospectives.jsonl"
    retrospective_path.write_text(
        json.dumps(
            {
                "severity": "critical",
                "route_record": {
                    "action_name": "jp_design_review",
                    "selected_provider": "openai",
                    "quality_score": 0.18,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DGC_ROUTER_RETROSPECTIVE_LOG", str(retrospective_path))
    monkeypatch.setattr(
        "dharma_swarm.memory.StrangeLoopMemory",
        lambda *args, **kwargs: _FakeMemory(),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_overview",
        lambda **kwargs: "",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.routing_memory.RoutingMemoryStore",
        _FakeRoutingMemory,
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.routing_memory.default_routing_memory_db_path",
        lambda: tmp_path / "missing.sqlite3",
        raising=True,
    )

    cli.cmd_memory()

    output = capsys.readouterr().out
    assert "Memory: empty" in output
    assert "Route Retrospectives" in output
    assert "[critical] jp_design_review -> openai quality=0.18" in output
