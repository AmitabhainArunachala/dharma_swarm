"""Concept Blast Radius -- cross-graph impact analysis for concepts.

Part of the Graph Nexus architecture.  Given a concept (by ID or name),
computes which nodes, files, temporal terms, objectives, and catalytic
artifacts would be affected if that concept were changed or removed.

This is the "what breaks if I touch X?" question answered across every
graph subsystem in dharma_swarm.

Integration:
    semantic_gravity.py  -- ConceptGraph is the primary lookup source
    bridge_registry.py   -- cross-graph edges reveal transitive impact
    temporal_graph.py    -- co-occurring terms in the temporal graph
    catalytic_graph.py   -- catalytic nodes reachable via bridges
    telos_graph.py       -- strategic objectives connected via bridges

Usage::

    br = ConceptBlastRadius()
    report = await br.compute("abc123def456")
    print(report.total_impact, report.affected_code_files)

    # Or by name:
    report = await br.compute_by_name("autopoiesis")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report model
# ---------------------------------------------------------------------------


class BlastRadiusReport(BaseModel):
    """Result of a conceptual blast radius computation.

    Attributes:
        concept_id: The concept's ID (or ``name:<name>`` for name-based queries).
        concept_name: Human-readable concept name.
        affected_code_files: File paths containing or referencing this concept.
        affected_concepts: Names of neighboring concepts in the semantic graph.
        affected_temporal_terms: Co-occurring or bridged terms in the temporal graph.
        affected_objectives: Telos objective IDs connected via bridges.
        affected_catalytic_nodes: Catalytic graph node IDs connected via bridges.
        bridge_details: Raw bridge edge metadata for deeper inspection.
        total_impact: Sum of all affected items across all dimensions.
    """

    concept_id: str
    concept_name: str = ""
    affected_code_files: list[str] = Field(default_factory=list)
    affected_concepts: list[str] = Field(default_factory=list)
    affected_temporal_terms: list[str] = Field(default_factory=list)
    affected_objectives: list[str] = Field(default_factory=list)
    affected_catalytic_nodes: list[str] = Field(default_factory=list)
    bridge_details: list[dict[str, Any]] = Field(default_factory=list)
    total_impact: int = 0


# ---------------------------------------------------------------------------
# Blast radius engine
# ---------------------------------------------------------------------------


class ConceptBlastRadius:
    """Compute cross-graph impact of changing or removing a concept.

    Aggregates data from:
    1. ConceptGraph -- neighbors (semantic proximity)
    2. BridgeRegistry -- cross-graph edges from this concept
    3. TemporalKnowledgeGraph -- co-occurring terms

    All graph imports are late to avoid circular dependencies.

    Args:
        state_dir: Root state directory.  Defaults to ``~/.dharma``.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"

    # -- primary API ---------------------------------------------------------

    async def compute(self, concept_id: str) -> BlastRadiusReport:
        """Compute blast radius across all graphs for a concept ID.

        Steps:
        1. Look up the concept in ConceptGraph to get its name.
        2. Find semantic neighbors in the ConceptGraph.
        3. Query BridgeRegistry for all edges touching this concept.
        4. Query TemporalKnowledgeGraph for co-occurring terms.

        Each step is fault-isolated so partial results are still useful.

        Args:
            concept_id: The unique concept identifier in the ConceptGraph.

        Returns:
            A BlastRadiusReport with all affected items.
        """
        report = BlastRadiusReport(concept_id=concept_id)

        # Step 1: Find the concept in ConceptGraph
        cg = await self._load_concept_graph()
        node = cg.get_node(concept_id) if cg is not None else None

        if node is not None:
            report.concept_name = node.name

        # Step 2: Find related concepts (neighbors in semantic graph)
        if cg is not None and node is not None:
            try:
                neighbors = cg.neighbors(concept_id)
                report.affected_concepts = [n.name for n in neighbors]
            except Exception as exc:
                logger.debug("Neighbor lookup failed for %s: %s", concept_id, exc)

        # Step 3: Find bridge edges from this concept
        await self._collect_bridge_impacts(concept_id, report)

        # Step 4: Also search temporal graph directly for the concept name
        if node is not None:
            await self._collect_temporal_cooccurrences(node.name, report)

        # Step 5: Find code files from source_file on the node itself
        if node is not None and node.source_file:
            if node.source_file not in report.affected_code_files:
                report.affected_code_files.append(node.source_file)

        # Tally total impact
        report.total_impact = (
            len(report.affected_code_files)
            + len(report.affected_concepts)
            + len(report.affected_temporal_terms)
            + len(report.affected_objectives)
            + len(report.affected_catalytic_nodes)
        )

        logger.info(
            "Blast radius for %s (%s): total_impact=%d",
            concept_id[:12],
            report.concept_name,
            report.total_impact,
        )
        return report

    async def compute_by_name(self, concept_name: str) -> BlastRadiusReport:
        """Compute blast radius by concept name instead of ID.

        Looks up the concept in the ConceptGraph by case-insensitive name
        match.  If multiple nodes share the same name, uses the first match.
        If no match is found, returns a partial report with only temporal
        and bridge data.

        Args:
            concept_name: Human-readable concept name.

        Returns:
            A BlastRadiusReport.
        """
        cg = await self._load_concept_graph()

        if cg is not None:
            matches = cg.find_by_name(concept_name)
            if matches:
                # Use the first match and delegate to compute()
                report = await self.compute(matches[0].id)
                # Ensure the name is set even if the node lookup didn't find it
                if not report.concept_name:
                    report.concept_name = concept_name
                return report

        # Fallback: create a report with just temporal/bridge data
        report = BlastRadiusReport(
            concept_id=f"name:{concept_name}",
            concept_name=concept_name,
        )

        # Still try temporal co-occurrences
        await self._collect_temporal_cooccurrences(concept_name, report)

        report.total_impact = (
            len(report.affected_code_files)
            + len(report.affected_concepts)
            + len(report.affected_temporal_terms)
            + len(report.affected_objectives)
            + len(report.affected_catalytic_nodes)
        )
        return report

    # -- internal helpers ----------------------------------------------------

    async def _load_concept_graph(self) -> Any:
        """Load the ConceptGraph from the default persistence path.

        Returns:
            A ConceptGraph instance, or None if loading fails.
        """
        try:
            from dharma_swarm.semantic_gravity import ConceptGraph

            cg_path = self._state_dir / "semantic" / "concept_graph.json"
            return await ConceptGraph.load(cg_path)
        except Exception as exc:
            logger.debug("ConceptGraph load failed: %s", exc)
            return None

    async def _collect_bridge_impacts(
        self, concept_id: str, report: BlastRadiusReport,
    ) -> None:
        """Query BridgeRegistry for all edges touching this concept.

        Categorizes target nodes into code files, temporal terms,
        objectives, and catalytic nodes based on the target graph origin.

        Args:
            concept_id: The concept node ID to search for.
            report: The report to populate with bridge-derived impacts.
        """
        try:
            from dharma_swarm.bridge_registry import (
                BridgeRegistry,
                GraphOrigin,
            )

            registry = BridgeRegistry(
                db_path=self._state_dir / "db" / "bridges.db",
            )
            await registry.init()

            bridges = await registry.find_bridges(GraphOrigin.SEMANTIC, concept_id)

            for bridge in bridges:
                # Record the raw bridge detail for inspection
                report.bridge_details.append({
                    "source_graph": bridge.source_graph.value,
                    "source_id": bridge.source_id,
                    "target_graph": bridge.target_graph.value,
                    "target_id": bridge.target_id,
                    "edge_type": bridge.edge_type.value,
                    "confidence": bridge.confidence,
                })

                # Determine the "other side" of the bridge relative to our concept
                if bridge.source_id == concept_id:
                    target_graph = bridge.target_graph
                    target_id = bridge.target_id
                else:
                    target_graph = bridge.source_graph
                    target_id = bridge.source_id

                # Categorize by target graph
                if target_id.startswith("file::"):
                    file_path = target_id.removeprefix("file::")
                    if file_path not in report.affected_code_files:
                        report.affected_code_files.append(file_path)
                elif target_graph == GraphOrigin.TEMPORAL:
                    if target_id not in report.affected_temporal_terms:
                        report.affected_temporal_terms.append(target_id)
                elif target_graph == GraphOrigin.TELOS:
                    if target_id not in report.affected_objectives:
                        report.affected_objectives.append(target_id)
                elif target_graph == GraphOrigin.CATALYTIC:
                    if target_id not in report.affected_catalytic_nodes:
                        report.affected_catalytic_nodes.append(target_id)

            await registry.close()
        except Exception as exc:
            logger.debug("Bridge impact collection failed for %s: %s", concept_id, exc)

    async def _collect_temporal_cooccurrences(
        self, concept_name: str, report: BlastRadiusReport,
    ) -> None:
        """Search the TemporalKnowledgeGraph for co-occurring terms.

        Finds terms that frequently appear alongside this concept in
        shared notes.  Adds any new terms to the report's
        ``affected_temporal_terms`` list.

        Args:
            concept_name: The concept name to search for.
            report: The report to populate with temporal terms.
        """
        try:
            from dharma_swarm.temporal_graph import TemporalKnowledgeGraph

            tkg = TemporalKnowledgeGraph(
                db_path=self._state_dir / "db" / "temporal_graph.db",
            )
            co_results = tkg.co_occurring(concept_name.lower(), limit=10)

            for entry in co_results:
                # co_occurring returns list[dict] with "term" key
                term = entry.get("term", "") if isinstance(entry, dict) else str(entry)
                if term and term not in report.affected_temporal_terms:
                    report.affected_temporal_terms.append(term)
        except Exception as exc:
            logger.debug(
                "Temporal co-occurrence lookup failed for %s: %s",
                concept_name,
                exc,
            )

    async def multi_compute(
        self, concept_ids: list[str],
    ) -> dict[str, BlastRadiusReport]:
        """Compute blast radius for multiple concepts.

        Useful for batch impact analysis when considering a refactor
        that touches several concepts at once.

        Args:
            concept_ids: List of concept IDs to analyze.

        Returns:
            Dict mapping concept_id to its BlastRadiusReport.
        """
        results: dict[str, BlastRadiusReport] = {}
        for cid in concept_ids:
            try:
                results[cid] = await self.compute(cid)
            except Exception as exc:
                logger.warning("Blast radius failed for %s: %s", cid, exc)
                results[cid] = BlastRadiusReport(
                    concept_id=cid,
                    affected_code_files=[],
                    affected_concepts=[],
                    total_impact=0,
                )
        return results

    async def highest_impact(self, top_n: int = 10) -> list[BlastRadiusReport]:
        """Find the concepts with the highest blast radius.

        Scans all concepts in the ConceptGraph, computes blast radius for
        each, and returns the top N by total_impact.  This is an expensive
        operation for large graphs -- use sparingly.

        Args:
            top_n: Number of top-impact concepts to return.

        Returns:
            List of BlastRadiusReport sorted by total_impact descending.
        """
        cg = await self._load_concept_graph()
        if cg is None:
            return []

        reports: list[BlastRadiusReport] = []
        for node in cg.all_nodes():
            try:
                report = await self.compute(node.id)
                reports.append(report)
            except Exception as exc:
                logger.debug("Skipping %s in highest_impact: %s", node.id, exc)

        reports.sort(key=lambda r: r.total_impact, reverse=True)
        return reports[:top_n]
