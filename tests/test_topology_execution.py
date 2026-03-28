from __future__ import annotations

from typing import Any

import pytest

from dharma_swarm.lineage import LineageGraph
from dharma_swarm.models import AgentRole, AgentState, Task, TopologyType
from dharma_swarm.orchestrator import Orchestrator
from dharma_swarm.traces import TraceStore


def _fan_in_genome():
    from dharma_swarm.topology_genome import TopologyEdge, TopologyGenome, TopologyNode

    return TopologyGenome(
        genome_id="genome-fan-in",
        name="fan_in_topology",
        nodes=[
            TopologyNode(node_id="report", step_name="report"),
            TopologyNode(node_id="plan", step_name="plan"),
            TopologyNode(node_id="sources", step_name="sources"),
        ],
        edges=[
            TopologyEdge(
                edge_id="edge-plan-report",
                source_node_id="plan",
                target_node_id="report",
            ),
            TopologyEdge(
                edge_id="edge-sources-report",
                source_node_id="sources",
                target_node_id="report",
            ),
        ],
        entrypoints=["sources", "plan"],
    )


def test_topology_genome_compiles_into_workflow_steps() -> None:
    genome = _fan_in_genome()
    functions = {
        "plan": lambda _inputs, _ctx: {"brief": "done"},
        "sources": lambda _inputs, _ctx: ["s1", "s2"],
        "report": lambda inputs, _ctx: {
            "plan": inputs["plan"]["brief"],
            "source_count": len(inputs["sources"]),
        },
    }

    compiled = genome.compile(functions)
    step_map = {step.step_id: step for step in compiled.steps}

    assert [step.step_id for step in compiled.steps[:2]] == ["sources", "plan"]
    assert step_map["report"].inputs == ["plan", "sources"]
    assert step_map["sources"].checkpoint["topology_node_id"] == "sources"
    assert step_map["report"].checkpoint["topology_edge_ids"] == [
        "edge-plan-report",
        "edge-sources-report",
    ]


@pytest.mark.asyncio
async def test_execute_topology_genome_projects_node_and_edge_ids_into_traces_and_lineage(
    tmp_path,
) -> None:
    from dharma_swarm.workflow import execute_topology_genome_workflow

    genome = _fan_in_genome()
    trace_store = TraceStore(base_path=tmp_path / "traces")
    await trace_store.init()
    lineage_graph = LineageGraph(db_path=tmp_path / "lineage.db")

    async def _plan(_inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, str]:
        return {"brief": "plan"}

    async def _sources(_inputs: dict[str, Any], _ctx: dict[str, Any]) -> list[str]:
        return ["source-a", "source-b"]

    async def _report(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"brief": inputs["plan"]["brief"], "sources": list(inputs["sources"])}

    outcome = await execute_topology_genome_workflow(
        genome=genome,
        node_functions={
            "plan": _plan,
            "sources": _sources,
            "report": _report,
        },
        agent_name="topology-agent",
        trace_store=trace_store,
        lineage_graph=lineage_graph,
    )

    recent = await trace_store.get_recent(limit=10)
    provenance = lineage_graph.provenance("topology_output:report")

    assert outcome.workflow.status.value == "completed"
    assert outcome.outputs["report"]["brief"] == "plan"
    assert any(entry.metadata.get("topology_node_id") == "report" for entry in recent)
    assert any(
        entry.metadata.get("topology_edge_ids") == ["edge-plan-report", "edge-sources-report"]
        for entry in recent
        if entry.metadata.get("topology_node_id") == "report"
    )
    assert "topology_entry:plan" in provenance.root_sources
    assert "topology_entry:sources" in provenance.root_sources
    assert any(edge.metadata.get("topology_node_id") == "report" for edge in provenance.chain)


@pytest.mark.asyncio
async def test_orchestrator_accepts_topology_genome_without_breaking_enum_dispatch() -> None:
    genome = _fan_in_genome()
    task = Task(title="Topology task")

    class _Pool:
        async def get_idle_agents(self) -> list[AgentState]:
            return [
                AgentState(id="agent-1", name="Agent 1", role=AgentRole.RESEARCHER),
                AgentState(id="agent-2", name="Agent 2", role=AgentRole.RESEARCHER),
            ]

        async def assign(self, agent_id: str, task_id: str) -> None:
            return None

        async def release(self, agent_id: str) -> None:
            return None

        async def get_result(self, agent_id: str) -> str | None:
            return None

        async def get(self, agent_id: str) -> Any:
            return None

    orchestrator = Orchestrator(agent_pool=_Pool())

    async def _record_only(td):
        return None

    orchestrator._assign_dispatch = _record_only  # type: ignore[method-assign]

    genome_dispatches = await orchestrator.dispatch(task, topology=genome)
    enum_dispatches = await orchestrator.dispatch(Task(title="Enum task"), topology=TopologyType.PIPELINE)

    assert len(genome_dispatches) == 2
    assert {dispatch.metadata["topology_node_id"] for dispatch in genome_dispatches} == {
        "plan",
        "sources",
    }
    assert all(dispatch.metadata["topology_genome_id"] == genome.genome_id for dispatch in genome_dispatches)
    assert all(dispatch.topology == TopologyType.FAN_OUT for dispatch in genome_dispatches)
    assert len(enum_dispatches) == 1
    assert "topology_genome_id" not in enum_dispatches[0].metadata
    assert enum_dispatches[0].topology == TopologyType.PIPELINE
