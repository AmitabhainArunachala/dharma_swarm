from __future__ import annotations

from dharma_swarm.models import GateResult
from dharma_swarm.semantic_briefs import build_brief_packet
from dharma_swarm.semantic_gravity import (
    AngleVerdict,
    ClusterFileSpec,
    ConceptGraph,
    ConceptNode,
    FileClusterSpec,
    HardeningAngle,
    HardeningReport,
    ResearchAnnotation,
    ResearchConnectionType,
)


def test_build_brief_packet_promotes_cluster_into_semantic_and_execution_briefs() -> None:
    graph = ConceptGraph()
    concept_a = ConceptNode(name="ShaktiLoop", source_file="dharma_swarm/shakti.py", salience=0.9)
    concept_b = ConceptNode(name="SleepCycle", source_file="dharma_swarm/sleep_cycle.py", salience=0.85)
    graph.add_node(concept_a)
    graph.add_node(concept_b)
    annotation = ResearchAnnotation(
        concept_id=concept_a.id,
        connection_type=ResearchConnectionType.VALIDATION,
        citation="Anthropic multi-agent systems",
        external_source="anthropic",
        field="multi-agent systems",
    )
    graph.add_annotation(annotation)

    cluster = FileClusterSpec(
        id="cluster_1",
        name="Shakti Loop Cluster",
        description="Ground sleep and coordination into one cluster.",
        core_concepts=[concept_a.id, concept_b.id],
        research_annotations=[annotation.id],
        files=[
            ClusterFileSpec(path="dharma_swarm/shakti_loop_cluster.py", file_type="python"),
            ClusterFileSpec(path="tests/test_shakti_loop_cluster.py", file_type="test"),
            ClusterFileSpec(path="docs/clusters/shakti_loop_cluster_spec.md", file_type="markdown"),
        ],
        intersection_type="formal_structure",
        hardening_score=0.72,
    )
    report = HardeningReport(
        cluster_id="cluster_1",
        verdicts=[
            AngleVerdict(
                angle=HardeningAngle.ENGINEERING,
                result=GateResult.PASS,
                score=0.82,
            )
        ],
        overall_score=0.84,
        passed=True,
        gaps_identified=["Need one more integration test"],
        suggested_refinements=["Add one integration test for the cluster."],
    )

    packet = build_brief_packet(
        graph=graph,
        clusters=[cluster],
        reports=[report],
        graph_path="/tmp/graph.json",
        project_root="/tmp/project",
        max_briefs=1,
    )

    assert len(packet.semantic_briefs) == 1
    assert len(packet.execution_briefs) == 1
    semantic = packet.semantic_briefs[0]
    execution = packet.execution_briefs[0]

    assert semantic.title == "Shakti Loop Cluster"
    assert "ShaktiLoop" in semantic.concept_names
    assert "Anthropic multi-agent systems" in semantic.citations
    assert semantic.readiness_score > 0.7
    assert execution.depends_on_briefs == [semantic.brief_id]
    assert any("shakti_loop_cluster.py" in task for task in execution.task_titles)
