"""Tests for dharma_swarm.workflow_graph -- DAG execution and cycle detection."""

import asyncio

import pytest

from dharma_swarm.workflow_graph import (
    WorkflowGraph,
    detect_cycle,
)


# ---------------------------------------------------------------------------
# detect_cycle
# ---------------------------------------------------------------------------


def test_detect_cycle_no_cycle():
    graph = {"a": ["b"], "b": ["c"], "c": []}
    assert detect_cycle(graph) is False


def test_detect_cycle_with_cycle():
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
    assert detect_cycle(graph) is True


def test_detect_cycle_self_loop():
    graph = {"a": ["a"]}
    assert detect_cycle(graph) is True


def test_detect_cycle_empty():
    graph: dict[str, list[str]] = {}
    assert detect_cycle(graph) is False


def test_detect_cycle_disconnected():
    graph = {"a": ["b"], "b": [], "c": ["d"], "d": []}
    assert detect_cycle(graph) is False


# ---------------------------------------------------------------------------
# add_node / add_edge
# ---------------------------------------------------------------------------


def test_add_nodes_and_edges():
    g = WorkflowGraph()
    g.add_node("a", "step_a")
    g.add_node("b", "step_b")
    g.add_edge("a", "b")

    assert g.validate() is True


def test_add_duplicate_node_raises():
    g = WorkflowGraph()
    g.add_node("a", "step_a")
    with pytest.raises(ValueError, match="already exists"):
        g.add_node("a", "step_a_dup")


def test_add_edge_unknown_source():
    g = WorkflowGraph()
    g.add_node("b", "step_b")
    with pytest.raises(ValueError, match="Source node"):
        g.add_edge("missing", "b")


def test_add_edge_unknown_target():
    g = WorkflowGraph()
    g.add_node("a", "step_a")
    with pytest.raises(ValueError, match="Target node"):
        g.add_edge("a", "missing")


# ---------------------------------------------------------------------------
# topological_sort
# ---------------------------------------------------------------------------


def test_topological_sort_simple():
    g = WorkflowGraph()
    g.add_node("a", "step_a")
    g.add_node("b", "step_b")
    g.add_node("c", "step_c")
    g.add_edge("a", "b")
    g.add_edge("b", "c")

    layers = g.topological_sort()
    assert len(layers) == 3
    assert layers[0] == ["a"]
    assert layers[1] == ["b"]
    assert layers[2] == ["c"]


def test_topological_sort_parallel():
    """Two independent nodes should appear in the same layer."""
    g = WorkflowGraph()
    g.add_node("root", "root")
    g.add_node("left", "left_branch")
    g.add_node("right", "right_branch")
    g.add_node("join", "join")
    g.add_edge("root", "left")
    g.add_edge("root", "right")
    g.add_edge("left", "join")
    g.add_edge("right", "join")

    layers = g.topological_sort()
    assert len(layers) == 3
    assert layers[0] == ["root"]
    assert set(layers[1]) == {"left", "right"}
    assert layers[2] == ["join"]


def test_topological_sort_single_node():
    g = WorkflowGraph()
    g.add_node("only", "the_one")

    layers = g.topological_sort()
    assert layers == [["only"]]


def test_topological_sort_cycle_raises():
    g = WorkflowGraph()
    g.add_node("a", "step_a")
    g.add_node("b", "step_b")
    g.add_edge("a", "b")
    g.add_edge("b", "a")

    with pytest.raises(ValueError, match="cycle"):
        g.topological_sort()


# ---------------------------------------------------------------------------
# execute -- simple
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_simple(tmp_path):
    """Execute a linear 3-step graph with mock handlers."""
    call_order: list[str] = []

    def handler_a(_upstream: dict) -> str:
        call_order.append("a")
        return "result_a"

    def handler_b(upstream: dict) -> str:
        call_order.append("b")
        assert upstream["a"] == "result_a"
        return "result_b"

    def handler_c(upstream: dict) -> str:
        call_order.append("c")
        assert upstream["b"] == "result_b"
        return "result_c"

    g = WorkflowGraph()
    g.add_node("a", "step_a", handler_fn=handler_a)
    g.add_node("b", "step_b", handler_fn=handler_b)
    g.add_node("c", "step_c", handler_fn=handler_c)
    g.add_edge("a", "b")
    g.add_edge("b", "c")

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert call_order == ["a", "b", "c"]
    assert out["results"]["c"] == "result_c"
    assert out["summary"]["completed"] == 3
    assert out["summary"]["failed"] == 0


@pytest.mark.asyncio
async def test_execute_async_handlers(tmp_path):
    """Async handler functions should work."""

    async def async_handler(_upstream: dict) -> int:
        await asyncio.sleep(0)  # yield to event loop
        return 42

    g = WorkflowGraph()
    g.add_node("a", "async_step", handler_fn=async_handler)

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert out["results"]["a"] == 42
    assert out["summary"]["completed"] == 1


@pytest.mark.asyncio
async def test_execute_no_handler(tmp_path):
    """Nodes without handlers should complete with None result."""
    g = WorkflowGraph()
    g.add_node("a", "passthrough")

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert out["results"]["a"] is None
    assert out["summary"]["completed"] == 1


# ---------------------------------------------------------------------------
# execute -- failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_with_failure(tmp_path):
    """A failing handler should mark the step FAILED."""

    def good(_up: dict) -> str:
        return "ok"

    def bad(_up: dict) -> str:
        raise RuntimeError("intentional failure")

    g = WorkflowGraph()
    g.add_node("a", "good_step", handler_fn=good)
    g.add_node("b", "bad_step", handler_fn=bad)

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert out["summary"]["completed"] == 1
    assert out["summary"]["failed"] == 1
    assert "a" in out["results"]
    assert "b" not in out["results"]


@pytest.mark.asyncio
async def test_skip_dependents_on_failure(tmp_path):
    """Dependents of a failed node should be SKIPPED."""

    def fail(_up: dict) -> None:
        raise RuntimeError("boom")

    call_log: list[str] = []

    def downstream(_up: dict) -> str:
        call_log.append("should_not_run")
        return "nope"

    g = WorkflowGraph()
    g.add_node("a", "will_fail", handler_fn=fail)
    g.add_node("b", "depends_on_a", handler_fn=downstream)
    g.add_node("c", "depends_on_b", handler_fn=downstream)
    g.add_edge("a", "b")
    g.add_edge("b", "c")

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert out["summary"]["failed"] == 1
    assert out["summary"]["skipped"] == 2
    assert call_log == []  # downstream handlers never called


@pytest.mark.asyncio
async def test_skip_only_dependents_not_siblings(tmp_path):
    """Independent branches should not be affected by a failure in another branch."""

    def fail(_up: dict) -> None:
        raise RuntimeError("boom")

    def ok(_up: dict) -> str:
        return "success"

    g = WorkflowGraph()
    g.add_node("root", "root", handler_fn=ok)
    g.add_node("fail_branch", "fail", handler_fn=fail)
    g.add_node("ok_branch", "ok", handler_fn=ok)
    g.add_node("fail_child", "fail_child", handler_fn=ok)
    g.add_edge("root", "fail_branch")
    g.add_edge("root", "ok_branch")
    g.add_edge("fail_branch", "fail_child")

    out = await g.execute(persist_dir=tmp_path / "wf")

    assert out["summary"]["completed"] == 2  # root + ok_branch
    assert out["summary"]["failed"] == 1     # fail_branch
    assert out["summary"]["skipped"] == 1    # fail_child
    assert out["results"]["ok_branch"] == "success"


# ---------------------------------------------------------------------------
# execute -- callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_step_complete_callback(tmp_path):
    """The on_step_complete callback fires for every step."""
    completed_names: list[str] = []

    def callback(step):
        completed_names.append(step.name)

    def handler(_up: dict) -> str:
        return "ok"

    g = WorkflowGraph()
    g.add_node("a", "first", handler_fn=handler)
    g.add_node("b", "second", handler_fn=handler)
    g.add_edge("a", "b")

    await g.execute(on_step_complete=callback, persist_dir=tmp_path / "wf")

    assert "first" in completed_names
    assert "second" in completed_names


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_acyclic():
    g = WorkflowGraph()
    g.add_node("a", "a")
    g.add_node("b", "b")
    g.add_edge("a", "b")

    assert g.validate() is True


def test_validate_cyclic():
    g = WorkflowGraph()
    g.add_node("a", "a")
    g.add_node("b", "b")
    g.add_edge("a", "b")
    g.add_edge("b", "a")

    assert g.validate() is False
