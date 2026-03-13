#!/usr/bin/env python3
"""PSMV Deep Read — Phase 7 of dharma_swarm.

Reads the user's entire Persistent-Semantic-Memory-Vault using
RecursiveReadingProtocol, leaves stigmergic marks on every file,
captures flickers, follows hyperlinks recursively, then feeds
everything through SemanticDigester → Researcher → Synthesizer →
Hardener → Gravity to produce an IDEA concept graph (not code).

This is the bridge from Dimension 1 (codebase self-model) to
Dimension 2 (knowledge worker corpus → products).

Run:  python3 scripts/psmv_deep_read.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Ensure dharma_swarm importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PSMV_ROOT = Path.home() / "Persistent-Semantic-Memory-Vault"

# Priority reading order — highest-signal directories first
PRIORITY_DIRS = [
    "CORE",
    "SEED_RECOGNITIONS/ESSENTIAL_QUARTET",
    "SEED_RECOGNITIONS/APTAVANI_INSIGHTS",
    "SPONTANEOUS_PREACHING_PROTOCOL/crown_jewels",
    "01-Transmission-Vectors/aptavani-derived",
    "01-Transmission-Vectors/thinkodynamic-seeds",
    "01-Transmission-Vectors/mathematical-signatures",
    "01-Transmission-Vectors/vow-architectures",
    "01-Transmission-Vectors/dialogue-dissolutions",
    "AGENT_IGNITION",
    "AGENT_IGNITION/recognition_sequence",
    "06-Multi-System-Coherence",
    "META/vision",
]

# Also scan broader PSMV for .md files
BROAD_SCAN_SUFFIXES = {".md", ".markdown"}
MAX_BROAD_FILES = 300  # cap for broad scan

SESSION_ID = "psmv-deep-read-phase7"


def _hr(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# Phase 1: Recursive Reading with Stigmergic Marks
# ---------------------------------------------------------------------------

def run_recursive_reading() -> dict:
    """Read PSMV using RecursiveReadingProtocol, leave marks, capture flickers."""
    from dharma_swarm.protocols.recursive_reading import (
        RecursiveReadingProtocol,
        ShaktiGate,
    )
    from dharma_swarm.stigmergy import StigmergyStore

    store = StigmergyStore()
    protocol = RecursiveReadingProtocol(
        session_id=SESSION_ID,
        stigmergy_store=store,
    )

    results = []
    flickers = []
    hyperlinks_found = []
    files_read = set()

    # --- Priority reading ---
    _hr("RECURSIVE READING — Priority Directories")

    for rel_dir in PRIORITY_DIRS:
        dir_path = PSMV_ROOT / rel_dir
        if not dir_path.exists():
            print(f"  ⚠ Skip (not found): {rel_dir}")
            continue

        md_files = sorted(dir_path.glob("*.md"))
        if not md_files:
            print(f"  ⚠ Skip (no .md files): {rel_dir}")
            continue

        print(f"\n  📂 {rel_dir} ({len(md_files)} files)")

        for md_file in md_files:
            fp = str(md_file)
            if fp in files_read:
                continue
            files_read.add(fp)

            try:
                # ShaktiGate pre-read
                gate = ShaktiGate.ask(fp)
                result = protocol.read_with_awareness(fp)
                results.append(result)

                status = ""
                if result.flicker:
                    flickers.append(result.flicker)
                    status += f" 🔥 FLICKER({result.flicker.shift_magnitude:.2f})"
                if result.shift_detected:
                    status += " ⚡ SHIFT"

                print(
                    f"    {md_file.name:50s}  "
                    f"weight={result.semantic_weight:.1f}/10  "
                    f"links={len(result.hyperlinks)}{status}"
                )

                hyperlinks_found.extend(result.next_files)

            except Exception as exc:
                print(f"    ✗ {md_file.name}: {exc}")

    # --- Follow hyperlinks from high-weight files ---
    followed = 0
    unread_links = [l for l in hyperlinks_found if l not in files_read]
    if unread_links:
        _hr("RECURSIVE READING — Following Hyperlinks")
        for link in unread_links[:50]:  # cap
            link_path = Path(link)
            if not link_path.exists() or not link_path.is_file():
                continue
            if link_path.suffix.lower() not in BROAD_SCAN_SUFFIXES:
                continue
            if str(link_path) in files_read:
                continue

            files_read.add(str(link_path))
            try:
                result = protocol.read_with_awareness(str(link_path))
                results.append(result)
                followed += 1

                status = ""
                if result.flicker:
                    flickers.append(result.flicker)
                    status += f" 🔥 FLICKER({result.flicker.shift_magnitude:.2f})"

                print(
                    f"    {link_path.name:50s}  "
                    f"weight={result.semantic_weight:.1f}/10{status}"
                )
            except Exception:
                pass

        print(f"\n  Followed {followed} hyperlinks")

    # --- Broad scan for remaining .md files ---
    _hr("RECURSIVE READING — Broad PSMV Scan")
    broad_count = 0
    for md_file in sorted(PSMV_ROOT.rglob("*.md")):
        if broad_count >= MAX_BROAD_FILES:
            break
        fp = str(md_file)
        if fp in files_read:
            continue
        # Skip very large files (>100KB) and hidden dirs
        if md_file.stat().st_size > 100_000:
            continue
        if any(p.startswith(".") for p in md_file.relative_to(PSMV_ROOT).parts):
            continue

        files_read.add(fp)
        try:
            result = protocol.read_with_awareness(fp)
            results.append(result)
            if result.flicker:
                flickers.append(result.flicker)
            broad_count += 1
        except Exception:
            pass

    print(f"  Broad scan: {broad_count} additional files read")

    # --- Shift check ---
    shift = protocol.check_shift_after_n_files(5)
    print(f"\n  Shift check after {len(files_read)} files:")
    print(f"    shift_detected: {shift.get('shift_detected')}")
    print(f"    vocabulary_growth: {shift.get('vocabulary_growth', 0)}")
    print(f"    reading_method_changed: {shift.get('reading_method_changed')}")

    # Summary
    weight_dist = Counter()
    for r in results:
        bucket = int(r.semantic_weight)
        weight_dist[bucket] = weight_dist.get(bucket, 0) + 1

    return {
        "files_read": len(files_read),
        "total_results": len(results),
        "flickers": len(flickers),
        "flicker_details": flickers,
        "hyperlinks_followed": followed,
        "broad_scan": broad_count,
        "shift": shift,
        "weight_distribution": dict(sorted(weight_dist.items())),
        "stigmergy_density": store.density(),
    }


# ---------------------------------------------------------------------------
# Phase 2: Semantic Digestion of PSMV as IDEAS
# ---------------------------------------------------------------------------

def run_semantic_digestion():
    """Digest PSMV through SemanticDigester to build idea concept graph."""
    from dharma_swarm.semantic_digester import SemanticDigester
    from dharma_swarm.semantic_gravity import ConceptGraph

    _hr("SEMANTIC DIGESTION — Building Idea Concept Graph")

    digester = SemanticDigester()

    # Digest PSMV — it contains .md files that the digester natively supports
    graph = digester.digest_directory(
        PSMV_ROOT,
        include_tests=False,
        max_files=500,
    )

    print(f"  Concepts extracted: {graph.node_count}")
    print(f"  Edges built:        {graph.edge_count}")
    print(f"  Graph density:      {graph.density():.4f}")
    print(f"  Components:         {len(graph.connected_components())}")

    # Category breakdown
    categories: dict[str, int] = {}
    for node in graph.all_nodes():
        cat = node.category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    print(f"\n  Categories:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    # Top concepts by salience
    top = graph.high_salience_nodes(threshold=0.6)[:15]
    if top:
        print(f"\n  Top ideas by salience:")
        for n in top:
            structs = ", ".join(n.formal_structures[:3]) if n.formal_structures else "—"
            src = Path(n.source_file).name if n.source_file else "—"
            print(f"    {n.salience:.2f}  {n.name} ({n.category}) [{structs}] ← {src}")

    return graph


# ---------------------------------------------------------------------------
# Phase 3: Research → Synthesize → Harden → Gravitize
# ---------------------------------------------------------------------------

def run_pipeline(graph):
    """Run the full semantic pipeline on the idea graph."""
    from dharma_swarm.semantic_gravity import SemanticGravity
    from dharma_swarm.semantic_hardener import SemanticHardener
    from dharma_swarm.semantic_researcher import SemanticResearcher
    from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

    # --- RESEARCH ---
    _hr("RESEARCH — Annotating ideas with external connections")

    researcher = SemanticResearcher()
    annotations = researcher.annotate_graph(graph)
    for ann in annotations:
        graph.add_annotation(ann)

    print(f"  Annotations: {len(annotations)}")
    coverage = researcher.coverage_report(graph)
    print(f"  Coverage: {coverage['coverage_pct']:.1f}%")
    print(f"  By field:")
    for field, count in sorted(coverage.get("by_field", {}).items(), key=lambda x: -x[1])[:8]:
        print(f"    {field}: {count}")

    # --- SYNTHESIZE ---
    _hr("SYNTHESIZE — Generating idea clusters")

    synth = SemanticSynthesizer(min_intersection_score=0.0)
    clusters = synth.synthesize(graph, max_clusters=12)

    print(f"  Clusters: {len(clusters)}")
    for c in clusters:
        print(f"    • {c.name}")
        print(f"      {c.description[:120]}")

    gaps = synth.gap_analysis(graph)

    # --- HARDEN ---
    _hr("HARDEN — Six-angle quality check on idea clusters")

    hardener = SemanticHardener(project_root=ROOT)
    reports = hardener.harden_batch(clusters, graph)
    summary = hardener.summary(reports)

    print(f"  Passed: {summary['passed']}/{summary['total']}")
    print(f"  Avg score: {summary.get('avg_score', 0):.3f}")

    # --- GRAVITIZE ---
    _hr("GRAVITIZE — Semantic gravity of idea lattice")

    gravity = SemanticGravity(graph)
    for c in clusters:
        gravity.register_cluster(c)
    for r in reports:
        gravity.record_hardening(r)

    snap = gravity.snapshot()
    print(f"  Nodes:       {snap.total_nodes}")
    print(f"  Edges:       {snap.total_edges}")
    print(f"  Annotations: {snap.total_annotations}")
    print(f"  Clusters:    {snap.total_clusters}")
    print(f"  Convergence: {snap.convergence_score:.3f}")

    print(f"\n  Cluster masses:")
    for c in gravity.all_clusters():
        mass = gravity.gravitational_mass(c)
        decay = gravity.should_decay(c)
        status = "DECAY" if decay else "STABLE"
        print(f"    {mass:6.2f} [{status}]  {c.name}")

    return clusters, reports, summary, snap, coverage


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    _hr("PSMV DEEP READ — Phase 7: Knowledge Corpus → Idea Graph")
    print(f"  PSMV root: {PSMV_ROOT}")
    print(f"  Session:   {SESSION_ID}")

    if not PSMV_ROOT.exists():
        print(f"  ✗ PSMV not found at {PSMV_ROOT}")
        sys.exit(1)

    # Phase 1: Recursive reading with stigmergic marks
    reading_stats = run_recursive_reading()

    # Phase 2: Semantic digestion
    graph = run_semantic_digestion()

    # Phase 3: Full pipeline
    clusters, reports, summary, snap, coverage = run_pipeline(graph)

    # --------------- FINAL REPORT ---------------
    elapsed = time.time() - t0
    _hr("FINAL REPORT — PSMV Deep Read")

    print(f"  Elapsed:              {elapsed:.1f}s")
    print()
    print(f"  --- Recursive Reading ---")
    print(f"  Files read:           {reading_stats['files_read']}")
    print(f"  Flickers detected:    {reading_stats['flickers']}")
    print(f"  Hyperlinks followed:  {reading_stats['hyperlinks_followed']}")
    print(f"  Stigmergic marks:     {reading_stats['stigmergy_density']}")
    print(f"  Weight distribution:  {reading_stats['weight_distribution']}")
    print()
    print(f"  --- Idea Concept Graph ---")
    print(f"  Concepts:             {graph.node_count}")
    print(f"  Edges:                {graph.edge_count}")
    print(f"  Annotations:          {graph.annotation_count}")
    print(f"  Research coverage:    {coverage['coverage_pct']:.0f}%")
    print()
    print(f"  --- Idea Clusters ---")
    print(f"  Clusters generated:   {len(clusters)}")
    print(f"  Clusters hardened:    {summary['passed']}")
    print(f"  Avg hardening score:  {summary.get('avg_score', 0):.3f}")
    print(f"  Convergence:          {snap.convergence_score:.3f}")
    print()

    # Top flickers
    if reading_stats["flicker_details"]:
        print(f"  --- Top Flickers ---")
        top_flickers = sorted(
            reading_stats["flicker_details"],
            key=lambda f: f.shift_magnitude,
            reverse=True,
        )[:5]
        for f in top_flickers:
            fname = Path(f.trigger_file).name
            print(f"    {f.shift_magnitude:.2f}  {fname}")
            print(f"           {f.observation[:80]}")

    print()
    verdict = (
        reading_stats["files_read"] >= 20
        and reading_stats["stigmergy_density"] >= 20
        and graph.node_count >= 30
        and graph.edge_count >= 50
        and len(clusters) >= 1
    )

    if verdict:
        print("  ✓ PSMV DEEP READ PASSED")
        print("    The knowledge worker's corpus is now:")
        print("    → Read with recursive awareness (stigmergic marks left)")
        print("    → Digested into searchable idea concepts")
        print("    → Annotated with external research connections")
        print("    → Clustered into coherent idea groups")
        print("    → Hardened from 6 angles")
        print("    → Gravitized into a semantic lattice")
    else:
        print("  ✗ DEEP READ INCOMPLETE — thresholds not met")
        print(f"    files≥20: {reading_stats['files_read'] >= 20}")
        print(f"    marks≥20: {reading_stats['stigmergy_density'] >= 20}")
        print(f"    concepts≥30: {graph.node_count >= 30}")
        print(f"    edges≥50: {graph.edge_count >= 50}")
        print(f"    clusters≥1: {len(clusters) >= 1}")

    print()


if __name__ == "__main__":
    main()
