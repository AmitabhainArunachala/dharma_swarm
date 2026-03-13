#!/usr/bin/env python3
"""Dimension 3 — Field Intelligence Scan (proof run).

Builds the D3 external field intelligence graph, runs all four
reports, and prints the full 3-dimensional strategic picture.

Usage:
    python scripts/field_scan.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure dharma_swarm is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.field_graph import (
    build_field_graph,
    competitive_position,
    full_field_scan,
    gap_report,
    overlap_report,
    uniqueness_report,
)
from dharma_swarm.field_knowledge_base import ALL_FIELD_ENTRIES, field_summary


def _bar(label: str, count: int, total: int, width: int = 30) -> str:
    frac = count / max(total, 1)
    filled = int(frac * width)
    return f"  {label:<24} [{'█' * filled}{'░' * (width - filled)}] {count}/{total}"


def main() -> None:
    t0 = time.perf_counter()

    # ── Field KB summary ────────────────────────────────────────
    summary = field_summary()
    print("=" * 72)
    print("  D3  EXTERNAL AI FIELD INTELLIGENCE ENGINE")
    print("=" * 72)
    print(f"\n  Knowledge Base: {summary['total_entries']} entries across {len(summary['by_field'])} fields")
    print(f"  DGC unique contributions: {summary['dgc_unique']}")
    print(f"  DGC gaps:                 {summary['dgc_gaps']}")
    print(f"  Direct competitors:       {summary['dgc_competitors']}")
    print()

    # ── Field distribution ──────────────────────────────────────
    print("  FIELD DISTRIBUTION:")
    for field, count in sorted(summary["by_field"].items(), key=lambda x: -x[1]):
        print(_bar(field, count, summary["total_entries"]))
    print()

    print("  RELATION DISTRIBUTION:")
    for rel, count in sorted(summary["by_relation"].items(), key=lambda x: -x[1]):
        print(_bar(rel, count, summary["total_entries"]))
    print()

    # ── Build graph ─────────────────────────────────────────────
    result = full_field_scan()
    stats = result["graph_stats"]
    print("-" * 72)
    print("  D3 CONCEPT GRAPH:")
    print(f"    Nodes:       {stats['nodes']}")
    print(f"    Edges:       {stats['edges']}")
    print(f"    Annotations: {stats['annotations']}")
    print(f"    Components:  {stats['components']}")
    print(f"    Density:     {stats['density']}")
    print()

    # ── Overlap Report ──────────────────────────────────────────
    ov = result["overlap"]
    print("-" * 72)
    print(f"  {ov['title']}")
    print(f"  Total overlapping: {ov['count']}")
    print()
    if ov["validated_by_external"]:
        print("  VALIDATED BY EXTERNAL RESEARCH:")
        for item in ov["validated_by_external"]:
            print(f"    ✓ {item['id']}")
            print(f"      → {item['source']}")
            print(f"      DGC modules: {', '.join(item['dgc_mapping'])}")
            print()
    if ov["dgc_supersedes"]:
        print("  DGC SUPERSEDES:")
        for item in ov["dgc_supersedes"]:
            print(f"    ▲ {item['id']}")
            print(f"      → {item['source']}")
            print(f"      DGC modules: {', '.join(item['dgc_mapping'])}")
            print()

    # ── Gap Report ──────────────────────────────────────────────
    gp = result["gaps"]
    print("-" * 72)
    print(f"  {gp['title']}")
    print(f"  Hard gaps: {gp['hard_gap_count']}  |  Integration opportunities: {gp['integration_count']}")
    print()
    if gp["hard_gaps"]:
        print("  HARD GAPS (DGC lacks these):")
        for item in gp["hard_gaps"]:
            print(f"    ✗ {item['id']} ({item['field']})")
            print(f"      → {item['source']}")
            print(f"      Why: {item['relevance'][:120]}...")
            print()
    if gp["integration_opportunities"]:
        print("  INTEGRATION OPPORTUNITIES:")
        for item in gp["integration_opportunities"]:
            print(f"    ⊕ {item['id']} ({item['field']})")
            print(f"      → {item['source']}")
            print()

    # ── Uniqueness Report ───────────────────────────────────────
    un = result["uniqueness"]
    print("-" * 72)
    print(f"  {un['title']}")
    print(f"  Moat count: {un['count']}")
    print()
    for item in un["moats"]:
        print(f"    ★ {item['id']}")
        print(f"      {item['summary'][:120]}")
        print()

    # ── Competitive Position ────────────────────────────────────
    cp = result["competitive_position"]
    sa = cp["strategic_assessment"]
    print("-" * 72)
    print(f"  {cp['title']}")
    print(f"  Overall assessment: {sa['overall']}")
    print(f"    Moats:     {sa['moat_count']}")
    print(f"    Gaps:      {sa['gap_count']}")
    print(f"    Validated: {sa['validated_count']}")
    print(f"    Threats:   {sa['threat_count']}")
    print()

    if cp["competitive_threats"]:
        print("  COMPETITIVE THREATS:")
        for t in cp["competitive_threats"]:
            print(f"    [{t['threat_level']}] {t['id']}")
            print(f"       {t['source']}")
            print(f"       DGC advantage: {t['dgc_advantage'][:120]}...")
            print()

    print("  DOMAIN STRENGTH:")
    for domain, info in cp["domain_coverage"].items():
        print(f"    {domain:<24} [{info['strength']:<12}] "
              f"unique={info['unique']} gaps={info['gaps']} validated={info['validated']}")
    print()

    elapsed = time.perf_counter() - t0
    print("=" * 72)
    print(f"  D3 Field Scan complete in {elapsed:.2f}s")
    print("=" * 72)


if __name__ == "__main__":
    main()
