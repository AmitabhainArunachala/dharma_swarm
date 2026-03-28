from __future__ import annotations

from dharma_swarm.archive import FitnessScore
from dharma_swarm.causal_credit import CausalCreditEngine
from dharma_swarm.lineage import LineageEdge
from dharma_swarm.traces import TraceEntry


def test_assign_trace_credit_normalizes_and_prefers_later_successful_steps():
    engine = CausalCreditEngine()
    traces = [
        TraceEntry(agent="planner", action="plan", metadata={"files_touched": 1}),
        TraceEntry(
            agent="coder",
            action="patch",
            fitness=FitnessScore(correctness=0.9, safety=0.8),
            files_changed=["a.py", "b.py"],
        ),
        TraceEntry(
            agent="tester",
            action="verify",
            fitness=FitnessScore(correctness=1.0, performance=0.6),
            metadata={"verified": True},
        ),
    ]

    credit = engine.assign_trace_credit(traces, success_score=1.0)

    assert len(credit) == 3
    assert round(sum(item.score for item in credit), 6) == 1.0
    assert credit[0].subject_id == traces[-1].id
    assert credit[0].score > credit[-1].score


def test_assign_combined_credit_includes_lineage_edges():
    engine = CausalCreditEngine()
    traces = [TraceEntry(agent="coder", action="patch", files_changed=["a.py"])]
    edges = [
        LineageEdge(
            task_id="task-1",
            input_artifacts=["prompt:1"],
            output_artifacts=["result:1", "artifact:2"],
            agent="coder",
            operation="patch",
        )
    ]

    credit = engine.assign_combined_credit(traces=traces, edges=edges, success_score=1.0)

    assert len(credit) == 2
    assert round(sum(item.score for item in credit), 6) == 1.0
    assert {item.subject_kind for item in credit} == {"trace", "lineage_edge"}
