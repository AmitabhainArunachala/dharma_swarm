from __future__ import annotations

import pytest

from dharma_swarm.agent_registry import AgentRegistry
from dharma_swarm.agent_runner import AgentRunner
from dharma_swarm.auto_grade.engine import AutoGradeEngine
from dharma_swarm.auto_research.engine import AutoResearchEngine
from dharma_swarm.auto_research.models import ResearchBrief
from dharma_swarm.lineage import LineageGraph
from dharma_swarm.models import AgentConfig, AgentRole, ProviderType
from dharma_swarm.runtime_fields import runtime_field_manifest_for_agent_config
from dharma_swarm.traces import TraceStore


class _StubSearchBackend:
    def search(self, brief, queries):
        assert brief.task_id == "task-workflow"
        assert queries[0].intent == "discovery"
        return [
            {
                "source_id": "src-1",
                "url": "https://docs.example.org/workflow",
                "title": "Workflow Spec",
                "authority_score": 0.94,
                "freshness_score": 0.91,
                "source_type": "docs",
                "metadata": {
                    "claims": ["Workflow traces should preserve grading context."],
                },
            },
            {
                "source_id": "src-2",
                "url": "https://research.example.com/lineage",
                "title": "Lineage Notes",
                "authority_score": 0.89,
                "freshness_score": 0.87,
                "source_type": "paper",
                "metadata": {
                    "claims": ["Lineage edges should expose report and grade artifacts."],
                },
            },
            {
                "source_id": "src-3",
                "url": "https://ops.example.net/traces",
                "title": "Trace Notes",
                "authority_score": 0.86,
                "freshness_score": 0.85,
                "source_type": "web",
                "metadata": {
                    "claims": ["Runtime field manifests should remain intact during research runs."],
                },
            },
        ]


@pytest.mark.asyncio
async def test_agent_runner_executes_auto_research_workflow_with_traces_and_lineage(
    tmp_path,
) -> None:
    config = AgentConfig(
        name="Research Workflow Agent",
        role=AgentRole.RESEARCHER,
        provider=ProviderType.LOCAL,
        model="local-model",
        system_prompt="Research carefully and cite every claim.",
    )
    manifest = runtime_field_manifest_for_agent_config(config)
    registry = AgentRegistry(agents_dir=tmp_path / "agents")
    registry.register_agent(
        name=config.name,
        role=config.role.value,
        model=config.model,
        system_prompt=config.system_prompt,
        runtime_fields=manifest,
    )

    runner = AgentRunner(config)
    trace_store = TraceStore(base_path=tmp_path / "traces")
    await trace_store.init()
    lineage_graph = LineageGraph(db_path=tmp_path / "lineage.db")

    brief = ResearchBrief(
        task_id="task-workflow",
        topic="Workflow provenance",
        question="How should research runs preserve provenance?",
        requires_recency=True,
        metadata={"sources_requested": True},
    )
    result = await runner.run_auto_research_workflow(
        brief,
        research_engine=AutoResearchEngine(search_backend=_StubSearchBackend()),
        grade_engine=AutoGradeEngine(),
        trace_store=trace_store,
        lineage_graph=lineage_graph,
        grade_kwargs={
            "latency_ms": 1500,
            "token_cost_usd": 0.05,
            "total_tokens": 1800,
            "cost_budget_usd": 1.0,
            "latency_budget_ms": 6000,
            "token_budget": 6000,
        },
    )

    recent = await trace_store.get_recent(limit=10)
    provenance = lineage_graph.provenance(f"grade:{result.reward_signal.report_id}")

    assert result.workflow.status.value == "completed"
    assert result.report.task_id == "task-workflow"
    assert result.reward_signal.grade_card.final_score >= 0.82
    assert len(result.trace_ids) == 5
    assert any(entry.metadata.get("step_name") == "grade" for entry in recent)
    assert any(
        entry.metadata.get("final_score") == pytest.approx(result.reward_signal.grade_card.final_score)
        for entry in recent
        if entry.metadata.get("step_name") == "grade"
    )
    assert f"brief:{brief.task_id}" in provenance.root_sources
    assert "source:src-1" in provenance.root_sources
    assert result.lineage_edge_id
    assert registry.get_runtime_fields(config.name) == manifest
