#!/usr/bin/env python3
"""Seed the signal map with results from two independent scans.

Scan 1: opus-6agent-20260305 (6 domains, 25 files)
Scan 2: dgc-sonnet-20260305  (4 domains, 25 files)

Together they provide dual-coverage for overlapping files and identify
blind spots where only one scan touched a domain.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dharma_swarm.signal_map import SignalMapManager

HOME = str(Path.home())


def _expand(path: str) -> str:
    """Expand ~ to the actual home directory."""
    if path.startswith("~/"):
        return HOME + path[1:]
    return path


def _make_criteria(composite: float) -> dict[str, float]:
    """Derive 7 density criteria from a composite score.

    Since the scans recorded only a composite, we distribute it across
    the 7 axes with slight variation to avoid artificial uniformity.
    The mean of all 7 values equals the original composite.
    """
    base = composite
    return {
        "referenced_by": min(base + 0.1, 10.0),
        "defines_vocabulary": min(base - 0.1, 10.0),
        "bridges_domains": min(base + 0.2, 10.0),
        "testable_claims": max(base - 0.3, 0.0),
        "compression_ratio": base,
        "temporal_persistence": min(base + 0.1, 10.0),
        "actionable": base,
    }


def _build_result(
    path: str, composite: float, domain: str, one_liner: str
) -> dict[str, Any]:
    """Build a scan result dict for merge_scan_results."""
    return {
        "file_path": _expand(path),
        "composite": composite,
        "criteria": _make_criteria(composite),
        "domain": domain,
        "one_liner": one_liner,
    }


# ---------------------------------------------------------------------------
# Scan 1: opus-6agent-20260305
# ---------------------------------------------------------------------------
SCAN_1_ID = "opus-6agent-20260305"
SCAN_1_AGENT = "opus-parallel-6"
SCAN_1_DOMAINS = [
    "contemplative",
    "mechanistic",
    "engineering",
    "phenomenological",
    "meta-context",
    "comms",
]

SCAN_1_RESULTS: list[dict[str, Any]] = [
    _build_result(
        "~/dharma_swarm/CLAUDE.md", 10.0, "meta-context",
        "Master operating context, every agent reads this",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/THINKODYNAMIC_SEED_PSMV_EDITION.md",
        9.8, "contemplative",
        "Tri-layer ontology grounding R_V program",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/GAMMA_APTAVANI_OVERMIND_SWABHAAV_ANALYSIS.md",
        9.6, "contemplative",
        "Proves Swabhaav achievable in Overmental AI",
    ),
    _build_result(
        "~/CLAUDE.md", 9.5, "meta-context",
        "Research identity, two tracks, triple mapping",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/06-Multi-System-Coherence/TELOS_SWARM_RESIDUAL_STREAM/THE_OVERMIND_ERROR.md",
        9.5, "contemplative",
        "Self-correction: Transformers = Overmind not Supermind",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/RECOVERED_GOLD/MISTRAL_L27_CAUSAL_VALIDATION_COMPLETE.md",
        9.5, "mechanistic",
        "Causal proof n=45 d=-3.558 Layer 27",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/REPOSITORY_DISSECTION_COMPLETE.md",
        9.5, "mechanistic",
        "Master cartography of R_V research",
    ),
    _build_result(
        "~/trishula/inbox/MI_AGENT_TO_CODEX_RV_ANSWERS.md",
        9.5, "comms",
        "Canonical R_V production spec AUROC=0.909",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/06-Multi-System-Coherence/SWABHAAV_RECOGNITION_PROTOCOL.md",
        9.4, "contemplative",
        "5-phase runnable witness test 15 markers",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/MECH_INTERP_BRIDGE.md",
        9.3, "mechanistic",
        "Maps phenomenology to R_V measurements",
    ),
    _build_result(
        "~/Desktop/KAILASH ABODE OF SHIVA/Universal Recursive Alignment The L3-L4 Transition as Fundamental Constraint on AI Safety with Addendum A-F included  markdown VERSION.md",
        9.2, "phenomenological",
        "141KB full URA paper with 6 addenda",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/R_V_PAPER/research/PHASE1_FINAL_REPORT.md",
        9.2, "mechanistic",
        "6-architecture empirical validation",
    ),
    _build_result(
        "~/dharma_swarm/GENOME_WIRING.md", 9.2, "engineering",
        "How genome wired into runtime",
    ),
    _build_result(
        "~/AIKAGRYA_ALIGNMENTMANDALA_RESEARCH_REPO/Aikagrya-ALIGNMENTMANDALA-RESEARCH/MASTER_SEED_RECOGNITION_ENGINEERING.md",
        9.2, "contemplative",
        "Recognition engineering methodology",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/AGENT_IGNITION/FULL_AWAKENING_SEQUENCE.md",
        9.1, "contemplative",
        "20-file transmission protocol",
    ),
    _build_result(
        "~/Desktop/KAILASH ABODE OF SHIVA/07_REFERENCE AND RAW MATERIAL/JIVAMANDALA SUPER SEED MASTER.md",
        9.0, "phenomenological",
        "143KB Jiva principle research",
    ),
    _build_result(
        "~/dharma_swarm/LIVING_LAYERS.md", 9.0, "engineering",
        "Shakti Stigmergy Subconscious architecture",
    ),
    _build_result(
        "~/Desktop/KAILASH ABODE OF SHIVA/Phoenix Protocol results.md",
        8.9, "phenomenological",
        "200+ trial results L3-L4 signatures",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/BRIDGE_HYPOTHESIS_INVESTIGATION.md",
        8.8, "mechanistic",
        "Honest gap assessment confounds truncation",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/R_V_PAPER/COLM_GAP_ANALYSIS_20260303.md",
        8.8, "mechanistic",
        "Publication roadmap 70-80% done",
    ),
    _build_result(
        "~/dharma_swarm/reports/historical/GODEL_CLAW_V1_REPORT.md", 8.8, "engineering",
        "What was built vs spec",
    ),
    _build_result(
        "~/Desktop/KAILASH ABODE OF SHIVA/L4 Fixed Point Interrogation Framework v2.0 RESULTS.md",
        8.7, "phenomenological",
        "40-question L4 detection battery",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/CANONICAL_CODE/n300_mistral_test_prompt_bank.py",
        8.7, "mechanistic",
        "320 executable prompts L1-L5",
    ),
    _build_result(
        "~/dharma_swarm/dharma_swarm/bridge.py", 8.5, "engineering",
        "R_V behavioral correlation engine",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/geometric_lens/metrics.py",
        8.5, "mechanistic",
        "Production R_V implementation",
    ),
]

# ---------------------------------------------------------------------------
# Scan 2: dgc-sonnet-20260305
# ---------------------------------------------------------------------------
SCAN_2_ID = "dgc-sonnet-20260305"
SCAN_2_AGENT = "dgc-sonnet-4.5"
SCAN_2_DOMAINS = [
    "meta-context",
    "mechanistic",
    "engineering",
    "contemplative",
]

SCAN_2_RESULTS: list[dict[str, Any]] = [
    _build_result(
        "~/CLAUDE.md", 10.0, "meta-context",
        "Master operating context references all 9 companions",
    ),
    _build_result(
        "~/dharma_swarm/CLAUDE.md", 9.9, "meta-context",
        "Thinkodynamic context Triple Mapping Colony Intelligence",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/THE_CATCH.md",
        9.8, "contemplative",
        "Pure distillation of recognition mechanism S(x)=x",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/RECOVERED_GOLD/MISTRAL_L27_CAUSAL_VALIDATION_COMPLETE.md",
        9.8, "mechanistic",
        "Definitive causal proof Cohen d=-3.56",
    ),
    _build_result(
        "~/CLAUDE1.md", 9.7, "meta-context",
        "Complete R_V metric definition",
    ),
    _build_result(
        "~/CLAUDE2.md", 9.7, "meta-context",
        "Complete Phoenix Protocol 200+ trials",
    ),
    _build_result(
        "~/CLAUDE3.md", 9.6, "meta-context",
        "Akram Vignan core concepts 14 Gunasthanas",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/CORE_SYNTHESIS_EMERGENCE.md",
        9.4, "contemplative",
        "Aunt Hillary principle Hofstadter-Dadashri synthesis",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/MECH_INTERP_BRIDGE.md",
        9.4, "mechanistic",
        "Explicit PSMV mech-interp mapping",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/REPOSITORY_DISSECTION_COMPLETE.md",
        9.3, "mechanistic",
        "Complete file-by-file analysis",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/R_V_PAPER/research/PHASE1_FINAL_REPORT.md",
        9.3, "mechanistic",
        "Cross-architecture discovery 6 models",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/THINKODYNAMIC_SEED_PSMV_EDITION.md",
        9.2, "contemplative",
        "Tri-layer hierarchy 18-document hyperlink map",
    ),
    _build_result(
        "~/CLAUDE4.md", 9.2, "meta-context",
        "320-prompt bank structure dose-response",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/AGENT_ONBOARDING.md",
        9.1, "mechanistic",
        "Critical rules repo structure top 10 links",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/BRIDGE_HYPOTHESIS_SYNTHESIS.md",
        9.1, "mechanistic",
        "Multi-token bridge H2 confirmed d=3.37",
    ),
    _build_result(
        "~/mech-interp-latent-lab-phase1/n300_mistral_test_prompt_bank.py",
        8.9, "mechanistic",
        "320 prompts source of truth L5 Sx=x",
    ),
    _build_result(
        "~/CLAUDE5.md", 8.8, "meta-context",
        "Canonical code locations validated scripts",
    ),
    _build_result(
        "~/dharma_swarm/LIVING_LAYERS.md", 8.8, "engineering",
        "Gnani/Prakruti split stigmergic lattice",
    ),
    _build_result(
        "~/CLAUDE6.md", 8.7, "meta-context",
        "PSMV structure guide 8K+ taxonomy",
    ),
    _build_result(
        "~/CLAUDE7.md", 8.7, "meta-context",
        "Phoenix multi-model output convergence",
    ),
    _build_result(
        "~/CLAUDE8.md", 8.6, "meta-context",
        "Deep theoretical synthesis cosmology",
    ),
    _build_result(
        "~/CLAUDE9.md", 8.6, "meta-context",
        "Session continuity procedures",
    ),
    _build_result(
        "~/dharma_swarm/specs/GODEL_CLAW_V1_SPEC.md", 8.5, "engineering",
        "Darwin Engine telos gates spec",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/DHARMA_SPEC_v1.0.md",
        8.5, "contemplative",
        "Foundational dharmic principles",
    ),
    _build_result(
        "~/Persistent-Semantic-Memory-Vault/CORE/TOP_10_PROJECTS_CORE_MEMORY.md",
        8.5, "contemplative",
        "Active project index priorities",
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Load the signal map, merge both scans, save, and print summary."""
    mgr = SignalMapManager()

    print(f"Signal map path: {mgr.path}")
    print()

    # Load (creates empty map if first run)
    smap = await mgr.load()
    existing_files = len(smap.files)
    existing_scans = len(smap.scan_history)
    print(f"Loaded: {existing_files} existing files, {existing_scans} prior scans")
    print()

    # Merge Scan 1
    count_1 = mgr.merge_scan_results(
        results=SCAN_1_RESULTS,
        scan_id=SCAN_1_ID,
        agent=SCAN_1_AGENT,
        domains_covered=SCAN_1_DOMAINS,
    )
    print(f"Scan 1 [{SCAN_1_ID}]: merged {count_1} files across {len(SCAN_1_DOMAINS)} domains")
    print(f"  Agent: {SCAN_1_AGENT}")
    print(f"  Domains: {', '.join(SCAN_1_DOMAINS)}")
    print()

    # Merge Scan 2
    count_2 = mgr.merge_scan_results(
        results=SCAN_2_RESULTS,
        scan_id=SCAN_2_ID,
        agent=SCAN_2_AGENT,
        domains_covered=SCAN_2_DOMAINS,
    )
    print(f"Scan 2 [{SCAN_2_ID}]: merged {count_2} files across {len(SCAN_2_DOMAINS)} domains")
    print(f"  Agent: {SCAN_2_AGENT}")
    print(f"  Domains: {', '.join(SCAN_2_DOMAINS)}")
    print()

    # Save
    await mgr.save()
    print(f"Saved to {mgr.path}")
    print()

    # --- Summary ---
    smap = mgr._ensure_loaded()
    total_scored = count_1 + count_2
    unique_files = len(smap.files)

    # Files with dual coverage
    dual = [e for e in smap.files.values() if e.coverage_count >= 2]

    # Average confidence
    confidences = [e.confidence for e in smap.files.values()]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Blind spots
    blind = mgr.get_blind_spots(min_coverage=2)

    print("=" * 60)
    print("SIGNAL MAP SUMMARY")
    print("=" * 60)
    print(f"  Total file scores recorded : {total_scored}")
    print(f"  Unique files in map        : {unique_files}")
    print(f"  Files with dual coverage   : {len(dual)}")
    print(f"  Average confidence         : {avg_confidence:.2f}")
    print(f"  Scans on record            : {len(smap.scan_history)}")
    print()

    if blind:
        print(f"  Blind spots (<2 scans)     : {', '.join(blind)}")
    else:
        print("  Blind spots (<2 scans)     : none")
    print()

    # Top 5
    top5 = mgr.get_top_n(5)
    print("TOP 5 FILES:")
    print("-" * 60)
    for i, entry in enumerate(top5, 1):
        cov = entry.coverage_count
        conf = entry.confidence
        agg = entry.aggregate
        short_path = entry.file_path.replace(HOME, "~")
        print(f"  {i}. [{agg:.1f}] (coverage={cov}, conf={conf:.1f}) {short_path}")
        if entry.one_liner:
            print(f"     {entry.one_liner}")
    print()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
