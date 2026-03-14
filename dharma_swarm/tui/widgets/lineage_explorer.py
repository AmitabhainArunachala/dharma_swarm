"""Lineage explorer widget — dual tree with artifact search.

Shows provenance (ancestors) and impact (descendants) trees
for a given artifact ID, with a search input at the top.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static, Tree

INDIGO = "#94A3B8"
VERDIGRIS = "#8FA89B"
OCHRE = "#C5B198"
ASH = "#A7AEBE"


class ProvenanceTree(Tree):
    """Tree showing provenance chain (ancestors) for an artifact."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("Provenance", *args, **kwargs)

    def show_provenance(self, graph: Any, artifact_id: str) -> None:
        """Populate tree from LineageGraph.provenance()."""
        self.clear()
        self.root.set_label(f"⬆ Provenance: {artifact_id}")
        self.root.expand()

        try:
            chain = graph.provenance(artifact_id)
        except Exception:
            self.root.add_leaf(f"[{ASH}]Error loading provenance[/{ASH}]")
            return

        if not chain.chain:
            self.root.add_leaf(f"[{ASH}]No provenance found[/{ASH}]")
            return

        # Show root sources
        if chain.root_sources:
            roots_node = self.root.add(
                f"Root sources ({len(chain.root_sources)})",
                data={"kind": "roots"},
            )
            roots_node.expand()
            for src in chain.root_sources:
                roots_node.add_leaf(f"📄 {src}", data={"artifact": src})

        # Show chain edges
        for edge in chain.chain:
            inputs = ", ".join(edge.input_artifacts[:3])
            outputs = ", ".join(edge.output_artifacts[:3])
            label = f"{edge.operation or 'op'} ({edge.agent or '?'})"
            edge_node = self.root.add(label, data={"edge_id": edge.edge_id})
            if inputs:
                edge_node.add_leaf(f"← {inputs}")
            if outputs:
                edge_node.add_leaf(f"→ {outputs}")

        # Show depth
        self.root.add_leaf(f"[{ASH}]Depth: {chain.depth}[/{ASH}]")


class ImpactTree(Tree):
    """Tree showing impact (descendants) for an artifact."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("Impact", *args, **kwargs)

    def show_impact(self, graph: Any, artifact_id: str) -> None:
        """Populate tree from LineageGraph.impact()."""
        self.clear()
        self.root.set_label(f"⬇ Impact: {artifact_id}")
        self.root.expand()

        try:
            report = graph.impact(artifact_id)
        except Exception:
            self.root.add_leaf(f"[{ASH}]Error loading impact[/{ASH}]")
            return

        if not report.affected_artifacts:
            self.root.add_leaf(f"[{ASH}]No downstream impact[/{ASH}]")
            return

        # Affected artifacts
        arts_node = self.root.add(
            f"Affected artifacts ({report.total_descendants})",
            data={"kind": "artifacts"},
        )
        arts_node.expand()
        for art in report.affected_artifacts[:20]:
            arts_node.add_leaf(f"📄 {art}", data={"artifact": art})

        # Affected tasks
        if report.affected_tasks:
            tasks_node = self.root.add(
                f"Affected tasks ({len(report.affected_tasks)})",
                data={"kind": "tasks"},
            )
            for task in report.affected_tasks[:20]:
                tasks_node.add_leaf(f"⚙ {task}", data={"task": task})

        self.root.add_leaf(f"[{ASH}]Depth: {report.depth}[/{ASH}]")


class LineageStatsBar(Static):
    """Bottom stats bar for lineage graph."""

    def update_stats(self, stats: dict[str, int] | None = None) -> None:
        if not stats:
            self.update(f"[{ASH}]Lineage: no data[/{ASH}]")
            return
        edges = stats.get("total_edges", 0)
        artifacts = stats.get("unique_artifacts", 0)
        pipelines = stats.get("unique_pipelines", 0)
        self.update(
            f"[{ASH}]Edges: {edges}  Artifacts: {artifacts}  Pipelines: {pipelines}[/{ASH}]"
        )


class LineageTab(Vertical):
    """Composite widget for the Lineage tab."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Enter artifact ID to trace…",
            id="lineage-search",
        )
        with Horizontal(id="lineage-trees"):
            yield ProvenanceTree(id="lineage-provenance")
            yield ImpactTree(id="lineage-impact")
        yield LineageStatsBar(id="lineage-stats")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle artifact search submission."""
        artifact_id = event.value.strip()
        if not artifact_id:
            return
        graph = getattr(self.screen, "_lineage_graph", None)
        if graph is None:
            return
        prov_tree = self.query_one("#lineage-provenance", ProvenanceTree)
        impact_tree = self.query_one("#lineage-impact", ImpactTree)
        prov_tree.show_provenance(graph, artifact_id)
        impact_tree.show_impact(graph, artifact_id)
