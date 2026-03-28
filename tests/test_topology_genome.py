from __future__ import annotations

import pytest


def _valid_genome():
    from dharma_swarm.topology_genome import TopologyEdge, TopologyGenome, TopologyNode

    return TopologyGenome(
        genome_id="genome-research",
        name="research_topology",
        nodes=[
            TopologyNode(
                node_id="plan",
                step_name="plan",
                runtime_fields=[{"name": "system_prompt"}],
                metadata={"agent_role": "researcher"},
            ),
            TopologyNode(
                node_id="report",
                step_name="report",
                runtime_fields=[{"name": "temperature"}],
                metadata={"agent_role": "writer"},
            ),
        ],
        edges=[
            TopologyEdge(
                edge_id="edge-plan-report",
                source_node_id="plan",
                target_node_id="report",
            )
        ],
        entrypoints=["plan"],
    )


def test_topology_genome_contracts_roundtrip() -> None:
    from dharma_swarm.topology_genome import TopologyGenome

    genome = _valid_genome()
    clone = TopologyGenome.model_validate_json(genome.model_dump_json())

    assert clone.genome_id == "genome-research"
    assert clone.nodes[0].node_id == "plan"
    assert clone.edges[0].edge_id == "edge-plan-report"
    assert clone.entrypoints == ["plan"]


def test_topology_genome_rejects_duplicate_node_ids() -> None:
    from dharma_swarm.topology_genome import TopologyNode

    genome = _valid_genome()
    genome.nodes.append(TopologyNode(node_id="plan", step_name="plan_copy"))

    with pytest.raises(ValueError, match="Duplicate node_id"):
        genome.validate_structure()


def test_topology_genome_rejects_missing_edge_endpoints() -> None:
    genome = _valid_genome()
    genome.edges[0].target_node_id = "missing"

    with pytest.raises(ValueError, match="unknown target node"):
        genome.validate_structure()


def test_topology_genome_rejects_unknown_entrypoints() -> None:
    genome = _valid_genome()
    genome.entrypoints = ["missing"]

    with pytest.raises(ValueError, match="Unknown entrypoint"):
        genome.validate_structure()
