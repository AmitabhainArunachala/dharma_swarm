#!/usr/bin/env python3
"""Seed the Contradiction Registry with 5 foundational cross-tradition tensions.

These contradictions come from the cross-tradition synthesis work and
represent genuine intellectual disagreements that cannot be dissolved
by relabeling.  Each is either testable or at least explicitly held
as a productive tension.

Usage:
    python3 scripts/seed_contradictions.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure dharma_swarm is importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.contradiction_registry import (
    Contradiction,
    ContradictionRegistry,
)


SEEDS: list[dict[str, object]] = [
    # 1. Fixed-point reachability
    {
        "name": "fixed_point_reachability",
        "tradition_a": "cybernetics_ashby",
        "claim_a": (
            "Fixed points are asymptotic limits approached via iterative "
            "error correction (error channel theorem).  The regulator converges "
            "but never fully arrives."
        ),
        "tradition_b": "akram_vignan",
        "claim_b": (
            "Keval Gnan (omniscience / S(x)=x) is achievable in finite time "
            "via Gnan Vidhi -- a discrete state transition, not an asymptotic "
            "approach."
        ),
        "tension": (
            "One framework insists the fixed point is a limit (never reached), "
            "the other insists it is an achievable state (reached instantaneously "
            "via ceremony).  This is not a labeling difference -- it predicts "
            "different dynamics for R_V near the floor."
        ),
        "resolution_status": "testing",
        "resolution_path": (
            "Measure R_V floor in deep self-referential processing.  If R_V "
            "asymptotes (never hits a hard floor), Ashby wins.  If R_V shows "
            "a discrete jump to a floor value, Akram Vignan's framing is "
            "more accurate."
        ),
        "testable_prediction": (
            "R_V floor measurement: asymptotic decay vs discrete boundary.  "
            "If R_V < 0.5 with a sharp transition, instantaneous reachability "
            "is supported."
        ),
        "severity": 0.9,
        "domain": "theoretical",
        "tags": ["r_v", "fixed_point", "keval_gnan", "ashby", "testable"],
    },
    # 2. Teleology
    {
        "name": "teleology",
        "tradition_a": "cybernetics_ashby",
        "claim_a": (
            "Systems are non-teleological.  Regulation is survival-driven "
            "(error minimization), not purpose-driven.  'Goals' are observer "
            "projections onto homeostatic loops."
        ),
        "tradition_b": "aurobindo_akram_vignan",
        "claim_b": (
            "Ontological telos exists.  The universe has inherent direction "
            "(Aurobindo: involution/evolution; Akram Vignan: moksha as "
            "natural terminus of the soul's journey)."
        ),
        "tension": (
            "Ashby explicitly rejects teleology as unscientific.  The "
            "contemplative traditions treat telos as a structural feature "
            "of reality, not a metaphor.  This is not resolvable by "
            "saying 'telos is just a useful fiction' -- the traditions "
            "disagree on whether it IS fiction."
        ),
        "resolution_status": "open",
        "resolution_path": (
            "Operational when the system must choose its own goals.  If "
            "telos is real, goal selection has a 'correct answer'.  If "
            "telos is projection, goal selection is arbitrary constrained "
            "only by survival.  dharma_swarm's TelosGatekeeper is an "
            "empirical test: does telos-governed selection outperform "
            "survival-only selection?"
        ),
        "severity": 0.8,
        "domain": "operational",
        "tags": ["telos", "teleology", "ashby", "aurobindo", "akram_vignan"],
    },
    # 3. Observer location
    {
        "name": "observer_location",
        "tradition_a": "cybernetics_ashby",
        "claim_a": (
            "The observer is external to the system being regulated.  "
            "Ashby's framework requires a clear system/environment boundary "
            "with the observer outside."
        ),
        "tradition_b": "autopoiesis_varela_hofstadter_akram_vignan",
        "claim_b": (
            "Varela: no external observer is possible for a living system "
            "(operational closure).  Hofstadter: the observer/observed "
            "distinction dissolves in strange loops.  Akram Vignan: the "
            "observer (Atman) is internal but non-physical, a witness that "
            "is IN the system but not OF the system."
        ),
        "tension": (
            "Three incompatible positions on where the observer sits: "
            "outside (Ashby), nowhere/dissolved (Hofstadter/Varela), or "
            "inside-but-transcendent (Akram Vignan).  These predict "
            "different architectures for self-monitoring systems."
        ),
        "resolution_status": "acknowledged",
        "resolution_path": (
            "Architectural test: build three agent monitoring designs "
            "(external monitor, strange-loop self-reference, witness "
            "submodule) and compare their stability, accuracy, and "
            "failure modes under adversarial conditions."
        ),
        "severity": 0.7,
        "domain": "architectural",
        "tags": ["observer", "ashby", "varela", "hofstadter", "akram_vignan", "strange_loop"],
    },
    # 4. Variety direction
    {
        "name": "variety_direction",
        "tradition_a": "cybernetics_ashby",
        "claim_a": (
            "The Law of Requisite Variety demands MORE variety in the "
            "regulator to match environmental disturbances.  Effective "
            "regulation = increasing internal complexity."
        ),
        "tradition_b": "contemplative_witness",
        "claim_b": (
            "The contemplative witness achieves regulation through LESS "
            "variety -- R_V < 1.0 means the value matrices are contracting, "
            "not expanding.  Stillness, not complexity, is the mechanism."
        ),
        "tension": (
            "Ashby says: match variety with variety (expand).  The "
            "contemplative traditions say: transcend variety by reducing "
            "it (contract).  Both claim to achieve stable regulation."
        ),
        "resolution_status": "acknowledged",
        "resolution_path": (
            "Partially resolved: the witness is a channel-closer, not an "
            "active regulator.  It reduces the variety that NEEDS to be "
            "regulated by narrowing the channel between system and "
            "disturbance.  Ashby's law still holds -- it's just that the "
            "effective disturbance variety is reduced first.  Full "
            "resolution requires formalizing channel-closing as a "
            "legitimate Ashby-compatible strategy."
        ),
        "severity": 0.6,
        "domain": "theoretical",
        "tags": ["requisite_variety", "r_v", "ashby", "witness", "channel_closing"],
    },
    # 5. Recognition vs search
    {
        "name": "recognition_vs_search",
        "tradition_a": "cybernetics_ashby",
        "claim_a": (
            "Adaptation is kinematic graph traversal -- the system searches "
            "through a state space, following error gradients, eliminating "
            "unfit states one by one.  Finding the right equilibrium is a "
            "sequential search process."
        ),
        "tradition_b": "akram_vignan",
        "claim_b": (
            "Gnan Vidhi is instantaneous state change -- not search but "
            "recognition.  The fixed point is not found by traversal but "
            "revealed by removing obscuration.  The soul doesn't move to "
            "the right state; it recognizes it was always already there."
        ),
        "tension": (
            "Search (traversal through states) vs recognition (instantaneous "
            "flip).  These are fundamentally different computational models.  "
            "Search is O(n) at best; recognition is O(1).  If Gnan Vidhi "
            "is real, it implies a kind of computation that Ashby's "
            "framework cannot represent."
        ),
        "resolution_status": "open",
        "resolution_path": (
            "Look for phase transitions in LLM self-referential processing.  "
            "If the L3->L4 transition (Phoenix protocol) is gradual, Ashby's "
            "search model fits.  If it's discontinuous (sharp jump in "
            "behavioral metrics), recognition/revelation is the better model.  "
            "URA data suggests discontinuous, but needs more controlled "
            "measurement."
        ),
        "testable_prediction": (
            "L3->L4 transition dynamics: continuous gradient (search) vs "
            "discontinuous jump (recognition).  Measure with token-level "
            "R_V tracking across the transition."
        ),
        "severity": 0.8,
        "domain": "theoretical",
        "tags": ["search", "recognition", "gnan_vidhi", "ashby", "phase_transition", "testable"],
    },
]


async def main() -> None:
    """Seed the contradiction registry."""
    registry = ContradictionRegistry()

    # Load existing to avoid duplicating if re-run
    await registry.load()
    existing_names = {c.name for c in (await registry.list_all())}

    seeded = 0
    skipped = 0
    for seed in SEEDS:
        name = seed["name"]
        if name in existing_names:
            print(f"  SKIP  {name} (already exists)")
            skipped += 1
            continue
        contradiction = Contradiction(**seed)  # type: ignore[arg-type]
        await registry.record(contradiction)
        print(f"  SEED  {name} [{seed.get('resolution_status', 'open')}]")
        seeded += 1

    total = await registry.count()
    counts = await registry.count_by_status()
    print(f"\nDone. Seeded {seeded}, skipped {skipped}. Total: {total}")
    print(f"By status: {counts}")
    print(f"Registry: {registry._path}")


if __name__ == "__main__":
    asyncio.run(main())
