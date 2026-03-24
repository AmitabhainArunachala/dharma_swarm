"""run_concept_extraction.py — Phase 7.6: Run the full concept extraction pipeline.

Populates the Semantic Graph with concepts and creates Code↔Semantic bridges
by scanning the entire DHARMA SWARM codebase.

Usage:
    python scripts/run_concept_extraction.py [--db-path PATH]

Output:
    - dharma_graphs.db: SQLite database with Semantic Graph + Code nodes + Bridge edges
    - Prints summary statistics
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dharma_swarm.concept_parser import ConceptIndexer, ConceptParser, ConceptRegistry
from dharma_swarm.graph_store import SQLiteGraphStore


def main():
    parser = argparse.ArgumentParser(description="Run DHARMA concept extraction pipeline")
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).parent.parent / "dharma_graphs.db"),
        help="Path for the graph database (default: dharma_graphs.db in repo root)",
    )
    parser.add_argument(
        "--concepts-path",
        default=str(Path(__file__).parent.parent / "dharma_swarm" / "dharma_concepts.json"),
        help="Path to dharma_concepts.json",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    code_dir = repo_root / "dharma_swarm"

    print("=" * 60)
    print("DHARMA SWARM — Phase 7.6: Concept Extraction Pipeline")
    print("=" * 60)

    # Step 1: Load concept registry
    t0 = time.time()
    registry = ConceptRegistry(args.concepts_path)
    print(f"\n[1/4] Loaded {len(registry)} concepts from registry ({time.time()-t0:.2f}s)")

    # Step 2: Parse all Python files
    t1 = time.time()
    concept_parser = ConceptParser(registry)
    extractions = concept_parser.parse_directory(code_dir, repo_root=repo_root)
    print(f"[2/4] Extracted {len(extractions)} concept references ({time.time()-t1:.2f}s)")

    # Quick stats
    from collections import Counter
    concept_counts = Counter(e.concept_id for e in extractions)
    file_counts = Counter(e.source_file for e in extractions)
    type_counts = Counter(e.source_type for e in extractions)

    print(f"\n  By source type:")
    for st, count in type_counts.most_common():
        print(f"    {st:15s} {count:5d}")

    print(f"\n  Top 15 concepts:")
    for concept_id, count in concept_counts.most_common(15):
        name = registry.get(concept_id).canonical_name if registry.get(concept_id) else concept_id
        print(f"    {name:35s} {count:5d} refs")

    print(f"\n  Top 10 conceptually dense files:")
    for filepath, count in file_counts.most_common(10):
        print(f"    {filepath:55s} {count:4d} hits")

    # Step 3: Initialize graph store and index
    t2 = time.time()
    store = SQLiteGraphStore(args.db_path)
    indexer = ConceptIndexer(store, registry)
    stats = indexer.full_index(extractions)
    print(f"\n[3/4] Indexed into graph database ({time.time()-t2:.2f}s)")
    print(f"  Concept nodes:      {stats['concept_nodes']}")
    print(f"  Relationship edges: {stats['relationship_edges']}")
    print(f"  Bridge edges:       {stats['bridge_edges']}")
    print(f"  Files indexed:      {stats['files_indexed']}")

    # Step 4: Verify
    t3 = time.time()
    print(f"\n[4/4] Verification")
    print(f"  Semantic graph nodes: {store.count_nodes('semantic')}")
    print(f"  Semantic graph edges: {store.count_edges('semantic')}")
    print(f"  Code graph nodes:     {store.count_nodes('code')}")
    print(f"  Bridge edges:         {len(store.get_bridges(None, None, None, None))}")

    # Test a sample query
    autopoiesis = store.get_node("semantic", "autopoiesis")
    if autopoiesis:
        bridges = store.get_bridges(
            source_graph=None, source_id=None,
            target_graph="semantic", target_id="autopoiesis",
        )
        print(f"\n  Sample query: 'autopoiesis'")
        print(f"    Definition: {json.loads(autopoiesis['data']).get('definition', '')[:80]}...")
        print(f"    Referenced in {len(bridges)} locations")
        if bridges:
            for b in bridges[:5]:
                print(f"      → {b['description'][:80]}")

    store.close()

    total_time = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete in {total_time:.2f}s")
    print(f"Database: {args.db_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
