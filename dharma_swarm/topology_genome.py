"""Topology genome contracts and workflow compilation helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex[:12]


class TopologyNode(BaseModel):
    """One executable node in a topology genome."""

    node_id: str
    step_name: str
    runtime_fields: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologyEdge(BaseModel):
    """Directed dependency between two topology nodes."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologyGenome(BaseModel):
    """Serializable genome that compiles into the canonical workflow runtime."""

    genome_id: str = Field(default_factory=_new_id)
    name: str
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def validate_structure(self) -> "TopologyGenome":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for node in self.nodes:
            if node.node_id in seen:
                duplicates.add(node.node_id)
            seen.add(node.node_id)
        if duplicates:
            raise ValueError(f"Duplicate node_id values: {', '.join(sorted(duplicates))}")

        for edge in self.edges:
            if edge.source_node_id not in seen:
                raise ValueError(f"Edge {edge.edge_id} references unknown source node {edge.source_node_id}")
            if edge.target_node_id not in seen:
                raise ValueError(f"Edge {edge.edge_id} references unknown target node {edge.target_node_id}")

        for entrypoint in self.entrypoints:
            if entrypoint not in seen:
                raise ValueError(f"Unknown entrypoint: {entrypoint}")
        return self

    def incoming_edge_ids(self, node_id: str) -> list[str]:
        return [edge.edge_id for edge in self.edges if edge.target_node_id == node_id]

    def input_node_ids(self, node_id: str) -> list[str]:
        return [edge.source_node_id for edge in self.edges if edge.target_node_id == node_id]

    def _ordered_nodes(self) -> list[TopologyNode]:
        node_map = {node.node_id: node for node in self.nodes}
        ordered: list[TopologyNode] = []
        seen: set[str] = set()
        for node_id in self.entrypoints:
            node = node_map.get(node_id)
            if node is not None and node_id not in seen:
                ordered.append(node)
                seen.add(node_id)
        for node in self.nodes:
            if node.node_id not in seen:
                ordered.append(node)
                seen.add(node.node_id)
        return ordered

    def compile(self, node_functions: dict[str, Callable[..., Any]]):
        """Compile the genome into the canonical workflow executor."""
        from dharma_swarm.workflow import CompiledWorkflow, WorkflowStep

        self.validate_structure()
        ordered_nodes = self._ordered_nodes()
        steps: list[WorkflowStep] = []
        funcs: dict[str, Callable[..., Any]] = {}

        for node in ordered_nodes:
            if node.node_id not in node_functions:
                raise ValueError(f"Missing function for topology node {node.node_id}")
            steps.append(
                WorkflowStep(
                    step_id=node.node_id,
                    name=node.step_name,
                    deterministic=bool(node.metadata.get("deterministic", True)),
                    inputs=self.input_node_ids(node.node_id),
                    checkpoint={
                        "topology_genome_id": self.genome_id,
                        "topology_node_id": node.node_id,
                        "topology_edge_ids": self.incoming_edge_ids(node.node_id),
                        "runtime_fields": list(node.runtime_fields),
                    },
                )
            )
            funcs[node.node_id] = node_functions[node.node_id]

        version_payload = json.dumps(
            {
                "name": self.name,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "step_name": node.step_name,
                        "runtime_fields": node.runtime_fields,
                        "metadata": node.metadata,
                    }
                    for node in ordered_nodes
                ],
                "edges": [edge.model_dump() for edge in self.edges],
                "entrypoints": list(self.entrypoints),
            },
            sort_keys=True,
        )
        version = hashlib.sha256(version_payload.encode()).hexdigest()[:12]
        return CompiledWorkflow(name=self.name, steps=steps, funcs=funcs, version=version)


__all__ = ["TopologyEdge", "TopologyGenome", "TopologyNode"]
