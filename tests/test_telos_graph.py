"""Tests for TelosGraph -- strategic objective DAG."""

from __future__ import annotations

import pytest

from dharma_swarm.telos_graph import (
    HypothesisStatus,
    ObjectiveStatus,
    TelosEdge,
    TelosGraph,
    TelosHypothesis,
    TelosKeyResult,
    TelosObjective,
    TelosPerspective,
    TelosStrategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(tmp_path) -> TelosGraph:
    return TelosGraph(telos_dir=tmp_path / "telos")


def _obj(name: str = "test-obj", **kw) -> TelosObjective:
    return TelosObjective(name=name, **kw)


def _kr(obj_id: str, name: str = "test-kr", **kw) -> TelosKeyResult:
    return TelosKeyResult(objective_id=obj_id, name=name, **kw)


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_objective_defaults(self):
        obj = _obj()
        assert obj.perspective == TelosPerspective.PROCESS
        assert obj.status == ObjectiveStatus.PROPOSED
        assert obj.progress == 0.0
        assert obj.priority == 5
        assert obj.id  # auto-generated

    def test_key_result_defaults(self):
        kr = _kr("obj-1")
        assert kr.objective_id == "obj-1"
        assert kr.current_value == 0.0
        assert kr.target_value == 1.0

    def test_strategy_defaults(self):
        s = TelosStrategy(objective_id="obj-1", name="test-strategy")
        assert s.status == ObjectiveStatus.PROPOSED
        assert s.actions == []

    def test_hypothesis_defaults(self):
        h = TelosHypothesis(statement="test hypothesis")
        assert h.status == HypothesisStatus.UNTESTED
        assert h.confidence == 0.5

    def test_edge_defaults(self):
        e = TelosEdge(source_id="a", target_id="b", edge_type="enables")
        assert e.strength == 1.0
        assert e.confidence == 1.0


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_add_objective(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("viveka"))
        assert obj.name == "viveka"
        assert tg.list_objectives() == [obj]

    @pytest.mark.asyncio
    async def test_get_objective(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("dharma"))
        found = await tg.get_objective(obj.id)
        assert found is not None
        assert found.name == "dharma"

    @pytest.mark.asyncio
    async def test_get_objective_not_found(self, tmp_path):
        tg = _make_graph(tmp_path)
        assert await tg.get_objective("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_objective(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("test", progress=0.0))
        updated = await tg.update_objective(obj.id, progress=0.75, status=ObjectiveStatus.ACTIVE)
        assert updated is not None
        assert updated.progress == 0.75
        assert updated.status == ObjectiveStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, tmp_path):
        tg = _make_graph(tmp_path)
        assert await tg.update_objective("ghost", progress=1.0) is None

    @pytest.mark.asyncio
    async def test_add_key_result(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("parent"))
        kr = await tg.add_key_result(_kr(obj.id, "measure-1"))
        assert kr.objective_id == obj.id
        assert tg.key_results_for(obj.id) == [kr]

    @pytest.mark.asyncio
    async def test_update_key_result(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("parent"))
        kr = await tg.add_key_result(_kr(obj.id))
        updated = await tg.update_key_result(kr.id, current_value=0.9)
        assert updated is not None
        assert updated.current_value == 0.9

    @pytest.mark.asyncio
    async def test_add_strategy(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("parent"))
        strat = await tg.add_strategy(TelosStrategy(objective_id=obj.id, name="action plan"))
        assert strat.name == "action plan"
        assert tg.strategies_for(obj.id) == [strat]

    @pytest.mark.asyncio
    async def test_add_hypothesis(self, tmp_path):
        tg = _make_graph(tmp_path)
        hyp = await tg.add_hypothesis(TelosHypothesis(statement="if X then Y"))
        assert hyp.statement == "if X then Y"

    @pytest.mark.asyncio
    async def test_update_hypothesis(self, tmp_path):
        tg = _make_graph(tmp_path)
        hyp = await tg.add_hypothesis(TelosHypothesis(statement="if X then Y"))
        updated = await tg.update_hypothesis(hyp.id, status=HypothesisStatus.SUPPORTED, confidence=0.9)
        assert updated is not None
        assert updated.status == HypothesisStatus.SUPPORTED

    @pytest.mark.asyncio
    async def test_add_edge(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj_a = await tg.add_objective(_obj("A"))
        obj_b = await tg.add_objective(_obj("B"))
        await tg.add_edge(TelosEdge(source_id=obj_a.id, target_id=obj_b.id, edge_type="enables"))
        assert len(tg.edges_from(obj_a.id)) == 1
        assert len(tg.edges_to(obj_b.id)) == 1


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------


class TestQueries:
    @pytest.mark.asyncio
    async def test_list_objectives_with_filters(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("a", perspective=TelosPerspective.PURPOSE))
        await tg.add_objective(_obj("b", perspective=TelosPerspective.PROCESS))
        await tg.add_objective(_obj("c", perspective=TelosPerspective.PURPOSE, status=ObjectiveStatus.ACHIEVED))

        purpose = tg.list_objectives(perspective=TelosPerspective.PURPOSE)
        assert len(purpose) == 2
        process = tg.list_objectives(perspective=TelosPerspective.PROCESS)
        assert len(process) == 1
        achieved = tg.list_objectives(status=ObjectiveStatus.ACHIEVED)
        assert len(achieved) == 1

    @pytest.mark.asyncio
    async def test_highest_leverage(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("low-pri", priority=2, progress=0.9))
        await tg.add_objective(_obj("high-pri-done", priority=9, progress=1.0))
        await tg.add_objective(_obj("high-pri-start", priority=9, progress=0.1))

        top = tg.highest_leverage(top_n=1)
        assert len(top) == 1
        assert top[0].name == "high-pri-start"  # highest priority × lowest progress

    @pytest.mark.asyncio
    async def test_blocked_objectives(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("healthy", status=ObjectiveStatus.ACTIVE))
        await tg.add_objective(_obj("stuck", status=ObjectiveStatus.BLOCKED))

        blocked = tg.blocked_objectives()
        assert len(blocked) == 1
        assert blocked[0].name == "stuck"

    @pytest.mark.asyncio
    async def test_active_objectives(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("active-1", status=ObjectiveStatus.ACTIVE))
        await tg.add_objective(_obj("proposed-1"))

        active = tg.active_objectives()
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_untested_hypotheses(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("a", priority=8))
        hyp = TelosHypothesis(statement="test", source_id=obj.id)
        await tg.add_hypothesis(hyp)

        untested = tg.untested_hypotheses(min_priority=5)
        assert len(untested) >= 1

    @pytest.mark.asyncio
    async def test_objective_progress_from_key_results(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("measured"))
        await tg.add_key_result(_kr(obj.id, "kr1", current_value=0.5, target_value=1.0))
        await tg.add_key_result(_kr(obj.id, "kr2", current_value=1.0, target_value=1.0))

        progress = tg.objective_progress(obj.id)
        assert progress == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_objective_progress_without_krs_uses_own(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("no-kr", progress=0.42))
        assert tg.objective_progress(obj.id) == pytest.approx(0.42)

    @pytest.mark.asyncio
    async def test_domain_summary(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("a", metadata={"domain": "viveka"}))
        await tg.add_objective(_obj("b", metadata={"domain": "viveka"}))
        await tg.add_objective(_obj("c", metadata={"domain": "tapas"}))

        summary = tg.domain_summary()
        assert summary.get("viveka") == 2
        assert summary.get("tapas") == 1

    @pytest.mark.asyncio
    async def test_causal_chain(self, tmp_path):
        tg = _make_graph(tmp_path)
        a = await tg.add_objective(_obj("A"))
        b = await tg.add_objective(_obj("B"))
        c = await tg.add_objective(_obj("C"))
        await tg.add_edge(TelosEdge(source_id=a.id, target_id=b.id, edge_type="enables"))
        await tg.add_edge(TelosEdge(source_id=b.id, target_id=c.id, edge_type="enables"))

        paths = tg.causal_chain(a.id)
        # Returns list of paths (list[list[str]]) — should have one path: a→b→c
        assert len(paths) == 1
        assert paths[0] == [a.id, b.id, c.id]

    @pytest.mark.asyncio
    async def test_strategy_map_summary(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("p", perspective=TelosPerspective.PURPOSE))
        await tg.add_objective(_obj("s", perspective=TelosPerspective.STAKEHOLDER))

        summary = tg.strategy_map_summary()
        assert "purpose" in summary
        assert len(summary["purpose"]) == 1
        assert summary["_totals"]["objectives"] == 2


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("persist-me", priority=9))
        await tg.add_key_result(_kr(obj.id, "kr-persist"))
        await tg.add_edge(TelosEdge(source_id=obj.id, target_id=obj.id, edge_type="self"))
        await tg.save()

        tg2 = _make_graph(tmp_path)
        await tg2.load()
        objs = tg2.list_objectives()
        assert len(objs) == 1
        assert objs[0].name == "persist-me"
        assert objs[0].priority == 9
        assert len(tg2.key_results_for(obj.id)) == 1
        assert len(tg2.edges_from(obj.id)) == 1

    @pytest.mark.asyncio
    async def test_load_empty_dir_is_safe(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.load()  # should not raise
        assert tg.list_objectives() == []

    @pytest.mark.asyncio
    async def test_propose_objective(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.propose_objective(
            name="new-idea",
            description="something interesting",
            perspective=TelosPerspective.STAKEHOLDER,
            priority=7,
        )
        assert obj.name == "new-idea"
        assert obj.status == ObjectiveStatus.PROPOSED
        assert obj.priority == 7


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_list_by_domain(self, tmp_path):
        tg = _make_graph(tmp_path)
        await tg.add_objective(_obj("a", metadata={"domain": "viveka"}))
        await tg.add_objective(_obj("b", metadata={"domain": "tapas"}))

        viveka = tg.list_by_domain("viveka")
        assert len(viveka) == 1
        assert viveka[0].name == "a"

    @pytest.mark.asyncio
    async def test_edges_from_nonexistent(self, tmp_path):
        tg = _make_graph(tmp_path)
        assert tg.edges_from("ghost") == []
        assert tg.edges_to("ghost") == []

    @pytest.mark.asyncio
    async def test_causal_chain_single_node(self, tmp_path):
        tg = _make_graph(tmp_path)
        obj = await tg.add_objective(_obj("lone"))
        paths = tg.causal_chain(obj.id)
        assert len(paths) == 1
        assert paths[0] == [obj.id]

    @pytest.mark.asyncio
    async def test_key_results_for_nonexistent(self, tmp_path):
        tg = _make_graph(tmp_path)
        assert tg.key_results_for("ghost") == []

    @pytest.mark.asyncio
    async def test_strategies_for_nonexistent(self, tmp_path):
        tg = _make_graph(tmp_path)
        assert tg.strategies_for("ghost") == []
