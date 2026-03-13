"""Semantic Memory Bridge — wires Semantic Evolution into the Memory System.

Five bridges connecting structural understanding (ConceptGraph) to
operational memory (MemoryLattice, RetrievalFeedback, ConversationMemory,
SleepCycle, ExperimentMemory):

1. **Concepts → UnifiedIndex**: Makes concepts searchable by agents
2. **Retrieval Uptake → Salience**: Agent usage bumps concept importance
3. **Idea Shards → Research**: Conversation insights become research candidates
4. **Sleep Semantic Phase**: Consolidation runs one semantic evolution cycle
5. **Experiment Memory → Hardening**: Failure patterns inform hardening gaps
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dharma_swarm.semantic_gravity import (
    ConceptGraph,
    ConceptNode,
    FileClusterSpec,
    HardeningReport,
    ResearchAnnotation,
    ResearchConnectionType,
    SemanticGravity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge 1: Concepts → UnifiedIndex
# ---------------------------------------------------------------------------


def index_concepts_into_memory(
    graph: ConceptGraph,
    *,
    db_path: Path | str | None = None,
) -> int:
    """Index every ConceptNode into the UnifiedIndex for hybrid retrieval.

    After calling this, agents can search for concepts via the
    HybridRetriever (lexical + overlap + semantic lanes).

    Returns the number of concepts indexed.
    """
    from dharma_swarm.engine.unified_index import UnifiedIndex

    index = UnifiedIndex(db_path)
    count = 0

    for node in graph.all_nodes():
        text = _concept_to_searchable_text(node)
        metadata = {
            "source_kind": "semantic_concept",
            "concept_id": node.id,
            "concept_name": node.name,
            "category": node.category,
            "salience": node.salience,
            "formal_structures": node.formal_structures,
            "source_file": node.source_file,
            "semantic_density": node.semantic_density,
            "recognition_type": node.recognition_type,
        }
        index.index_document(
            "semantic_concept",
            f"concept://{node.id}",
            text,
            metadata,
        )
        count += 1

    logger.info("Indexed %d concepts into UnifiedIndex", count)
    return count


def _concept_to_searchable_text(node: ConceptNode) -> str:
    """Build rich searchable text from a concept node."""
    parts = [f"{node.name}: {node.definition}"]
    if node.claims:
        parts.append("Claims: " + "; ".join(node.claims[:5]))
    if node.formal_structures:
        parts.append("Structures: " + ", ".join(node.formal_structures))
    if node.category:
        parts.append(f"Category: {node.category}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Bridge 2: Retrieval Uptake → Concept Salience
# ---------------------------------------------------------------------------


def apply_retrieval_uptake_to_salience(
    graph: ConceptGraph,
    *,
    db_path: Path | str | None = None,
    boost_amount: float = 0.05,
    decay_amount: float = 0.02,
) -> dict[str, float]:
    """Adjust concept salience based on retrieval feedback.

    - Concepts that were retrieved AND used: salience += boost_amount
    - Concepts that were retrieved but NOT used: salience -= decay_amount

    Returns a dict of {concept_id: new_salience} for changed concepts.
    """
    import sqlite3
    from dharma_swarm.engine.event_memory import DEFAULT_MEMORY_PLANE_DB

    db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)
    if not db_path.exists():
        return {}

    changes: dict[str, float] = {}

    with sqlite3.connect(str(db_path)) as db:
        db.row_factory = sqlite3.Row
        # Find recent retrieval feedback for semantic_concept records
        rows = db.execute(
            """
            SELECT record_id, source_kind, outcome, uptake_state
            FROM retrieval_log
            WHERE source_kind = 'semantic_concept'
            ORDER BY retrieved_at DESC
            LIMIT 200
            """,
        ).fetchall()

    # Aggregate per concept
    concept_signals: dict[str, list[str]] = {}
    for row in rows:
        record_id = str(row["record_id"])
        # record_id format is chunk_id, but source_path has concept://...
        uptake = str(row["uptake_state"] or "")
        outcome = str(row["outcome"] or "")

        # Try to extract concept_id from record_id
        if record_id.startswith("concept://"):
            cid = record_id[len("concept://"):]
        else:
            cid = record_id

        if cid not in concept_signals:
            concept_signals[cid] = []
        concept_signals[cid].append(uptake or outcome)

    for cid, signals in concept_signals.items():
        node = graph.get_node(cid)
        if node is None:
            continue

        used = sum(1 for s in signals if s in ("used", "probably_used", "success"))
        not_used = sum(1 for s in signals if s in ("not_used", "failure"))

        delta = (used * boost_amount) - (not_used * decay_amount)
        if abs(delta) > 0.001:
            new_salience = max(0.0, min(1.0, node.salience + delta))
            node.salience = round(new_salience, 4)
            changes[cid] = node.salience

    if changes:
        logger.info(
            "Adjusted salience for %d concepts from retrieval feedback",
            len(changes),
        )
    return changes


# ---------------------------------------------------------------------------
# Bridge 3: Idea Shards → Research Candidates
# ---------------------------------------------------------------------------


def harvest_idea_shards_as_research(
    graph: ConceptGraph,
    *,
    db_path: Path | str | None = None,
    min_salience: float = 0.6,
    shard_kinds: set[str] | None = None,
    limit: int = 20,
) -> list[ResearchAnnotation]:
    """Convert high-salience idea shards into research annotations.

    Reads idea_shards from the memory plane and creates
    ResearchAnnotation objects linked to the most relevant concept.

    Returns annotations (caller should add them to the graph).
    """
    import sqlite3
    from dharma_swarm.engine.event_memory import DEFAULT_MEMORY_PLANE_DB

    db_path = Path(db_path or DEFAULT_MEMORY_PLANE_DB)
    if not db_path.exists():
        return []

    kinds = shard_kinds or {"hypothesis", "proposal"}
    placeholders = ",".join("?" for _ in kinds)

    with sqlite3.connect(str(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            f"""
            SELECT shard_id, text, shard_kind, salience, metadata_json
            FROM idea_shards
            WHERE salience >= ? AND shard_kind IN ({placeholders})
              AND state != 'dismissed'
            ORDER BY salience DESC
            LIMIT ?
            """,
            [min_salience, *sorted(kinds), limit],
        ).fetchall()

    annotations: list[ResearchAnnotation] = []
    for row in rows:
        shard_text = str(row["text"])
        # Find the most relevant concept in the graph
        best_concept = _find_best_matching_concept(graph, shard_text)
        if best_concept is None:
            continue

        annotations.append(ResearchAnnotation(
            concept_id=best_concept.id,
            connection_type=ResearchConnectionType.ORTHOGONAL,
            external_source=f"idea_shard:{row['shard_id']}",
            summary=shard_text[:300],
            confidence=min(1.0, float(row["salience"]) * 0.8),
            field="conversation_insight",
            year=2026,
            metadata={
                "shard_id": row["shard_id"],
                "shard_kind": row["shard_kind"],
                "source": "conversation_memory",
            },
        ))

    logger.info(
        "Harvested %d idea shards as research annotations from %d candidates",
        len(annotations), len(rows),
    )
    return annotations


def _find_best_matching_concept(
    graph: ConceptGraph,
    text: str,
) -> ConceptNode | None:
    """Find the concept node whose name/definition best matches text."""
    text_lower = text.lower()
    best: ConceptNode | None = None
    best_score = 0.0

    for node in graph.all_nodes():
        score = 0.0
        if node.name.lower() in text_lower:
            score += 0.5
        for struct in node.formal_structures:
            if struct.lower() in text_lower:
                score += 0.3
        if node.category and node.category.lower() in text_lower:
            score += 0.1
        # Weight by salience
        score *= (0.5 + node.salience * 0.5)

        if score > best_score:
            best_score = score
            best = node

    return best if best_score > 0.1 else None


# ---------------------------------------------------------------------------
# Bridge 4: Sleep Cycle Semantic Phase
# ---------------------------------------------------------------------------


async def run_semantic_sleep_phase(
    *,
    project_root: Path | None = None,
    graph_path: Path | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run one semantic evolution cycle during sleep consolidation.

    DIGEST → RESEARCH → SYNTHESIZE → HARDEN → GRAVITIZE

    Returns a summary dict for the sleep report.
    """
    from dharma_swarm.semantic_digester import SemanticDigester
    from dharma_swarm.semantic_hardener import SemanticHardener
    from dharma_swarm.semantic_researcher import SemanticResearcher
    from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

    root = project_root or Path.home() / "dharma_swarm"
    gp = graph_path or (Path.home() / ".dharma" / "semantic" / "concept_graph.json")
    result: dict[str, Any] = {
        "phase": "semantic",
        "concepts_digested": 0,
        "annotations_added": 0,
        "clusters_generated": 0,
        "clusters_passed": 0,
        "gravity_snapshot": None,
    }

    # 1. DIGEST
    package_dir = root / "dharma_swarm"
    if not package_dir.is_dir():
        package_dir = root

    digester = SemanticDigester()
    graph = digester.digest_directory(package_dir)
    result["concepts_digested"] = graph.node_count

    # 2. Index into memory
    indexed = index_concepts_into_memory(graph, db_path=db_path)

    # 3. Apply retrieval feedback
    apply_retrieval_uptake_to_salience(graph, db_path=db_path)

    # 4. Harvest idea shards
    shard_anns = harvest_idea_shards_as_research(graph, db_path=db_path)
    for ann in shard_anns:
        graph.add_annotation(ann)

    # 5. RESEARCH
    researcher = SemanticResearcher()
    annotations = researcher.annotate_graph(graph)
    for ann in annotations:
        graph.add_annotation(ann)
    result["annotations_added"] = len(annotations) + len(shard_anns)

    # 6. SYNTHESIZE
    synth = SemanticSynthesizer()
    clusters = synth.synthesize(graph)
    result["clusters_generated"] = len(clusters)

    # 7. HARDEN
    hardener = SemanticHardener(project_root=root)
    reports = hardener.harden_batch(clusters, graph)
    result["clusters_passed"] = sum(1 for r in reports if r.passed)

    # 8. GRAVITIZE
    gravity = SemanticGravity(graph)
    for cluster in clusters:
        gravity.register_cluster(cluster)
    for report in reports:
        gravity.record_hardening(report)
    snap = gravity.snapshot()
    result["gravity_snapshot"] = {
        "nodes": snap.total_nodes,
        "edges": snap.total_edges,
        "annotations": snap.total_annotations,
        "clusters": snap.total_clusters,
        "density": round(snap.mean_density, 4),
        "hardening": round(snap.mean_hardening_score, 3),
        "components": snap.component_count,
        "convergence": round(snap.convergence_score, 3),
    }

    # 9. Persist
    await graph.save(gp)

    logger.info(
        "Semantic sleep phase: %d concepts, %d annotations, %d/%d clusters passed",
        result["concepts_digested"],
        result["annotations_added"],
        result["clusters_passed"],
        result["clusters_generated"],
    )
    return result


# ---------------------------------------------------------------------------
# Bridge 5: Experiment Memory → Hardening Gaps
# ---------------------------------------------------------------------------


def map_experiment_cautions_to_hardening(
    experiment_snapshot: Any,
    graph: ConceptGraph,
    clusters: list[FileClusterSpec],
) -> dict[str, list[str]]:
    """Map ExperimentMemory caution_components to cluster hardening gaps.

    When the Darwin Engine identifies modules that repeatedly fail,
    flag the corresponding concept clusters for re-hardening.

    Returns {cluster_id: [gap_descriptions]}.
    """
    caution = getattr(experiment_snapshot, "caution_components", [])
    if not caution:
        return {}

    caution_set = set(str(c).lower() for c in caution)
    cluster_gaps: dict[str, list[str]] = {}

    for cluster in clusters:
        for cid in cluster.core_concepts:
            node = graph.get_node(cid)
            if node is None:
                continue
            # Match if the concept's source file contains a caution component
            source_lower = node.source_file.lower()
            for caution_comp in caution_set:
                if caution_comp in source_lower or caution_comp in node.name.lower():
                    gaps = cluster_gaps.setdefault(cluster.id, [])
                    gaps.append(
                        f"Darwin Engine flagged '{caution_comp}' as caution "
                        f"component (linked via concept '{node.name}')"
                    )

    if cluster_gaps:
        logger.info(
            "Mapped %d caution components to %d cluster gaps",
            len(caution_set),
            sum(len(g) for g in cluster_gaps.values()),
        )
    return cluster_gaps


__all__ = [
    "apply_retrieval_uptake_to_salience",
    "harvest_idea_shards_as_research",
    "index_concepts_into_memory",
    "map_experiment_cautions_to_hardening",
    "run_semantic_sleep_phase",
]
