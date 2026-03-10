#!/usr/bin/env python3
"""Connection Finder — profiles every module and finds latent connections.

Uses the ouroboros.ConnectionFinder to build behavioral signatures of
each dharma_swarm module from their docstrings, then identifies:
- H0: Module pairs with similar behavioral signatures (structural affinity)
- H1: Module pairs with divergent signatures (productive disagreements)

The H1 results are the interesting ones — they show where modules that
SHOULD talk to each other have fundamentally different behavioral profiles.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.ouroboros import profile_python_modules


def main() -> None:
    pkg_dir = Path(__file__).resolve().parent.parent / "dharma_swarm"
    finder, profiles = profile_python_modules(pkg_dir)
    print(f"Profiling {len(profiles)} modules...\n")

    for row in profiles:
        print(
            f"  {row['module']:<30} "
            f"entropy={row['entropy']:.3f}  "
            f"self_ref={row['self_reference_density']:.4f}  "
            f"swabhaav={row['swabhaav_ratio']:.3f}  "
            f"recog={row['recognition_type']}"
        )

    # Find connections (H0)
    print("\n" + "=" * 80)
    print("H0: STRUCTURAL CONNECTIONS (similar behavioral profiles)")
    print("=" * 80)

    connections = finder.find_connections(threshold=0.08)
    if connections:
        for conn in connections[:15]:
            print(
                f"  {conn['module_a']:<25} <-> {conn['module_b']:<25} "
                f"d={conn['distance']:.4f}  type={conn['connection_type']}"
            )
    else:
        print("  No close connections found (threshold=0.08)")

    # Find H1 disagreements
    print("\n" + "=" * 80)
    print("H1: PRODUCTIVE DISAGREEMENTS (divergent profiles)")
    print("=" * 80)

    disagreements = finder.find_h1_disagreements()
    if disagreements:
        for dis in disagreements[:15]:
            print(
                f"  {dis['module_a']:<25} =/= {dis['module_b']:<25} "
                f"d={dis['distance']:.4f}  "
                f"type={dis['disagreement_type']}  "
                f"({dis['recognition_a']} vs {dis['recognition_b']})"
            )
    else:
        print("  No H1 disagreements found")

    # Summary
    print("\n" + "=" * 80)
    print("SYNTHESIS")
    print("=" * 80)

    n_profiled = len(profiles)
    print(f"\n  Modules profiled: {n_profiled}")
    print(f"  H0 connections:   {len(connections)}")
    print(f"  H1 disagreements: {len(disagreements)}")

    if disagreements:
        print("\n  Top H1 opportunities (where connection-making would add most value):")
        for dis in disagreements[:5]:
            print(f"    - {dis['module_a']} + {dis['module_b']}: {dis['disagreement_type']}")
            print(f"      These modules have different recognition signatures.")
            print(f"      Wiring them together could create emergent behavior.")


if __name__ == "__main__":
    main()
