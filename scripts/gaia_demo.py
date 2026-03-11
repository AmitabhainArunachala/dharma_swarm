#!/usr/bin/env python3
"""GAIA Demo: One complete ecological accountability loop.

Demonstrates the full categorical accounting pipeline:
1. Record AI compute footprint (Anthropic training cluster)
2. Fund a mangrove restoration project
3. Employ displaced workers
4. Record ecological labor and output
5. Run 3-of-5 oracle verification
6. Check conservation laws
7. Detect Goodhart drift
8. Observe the system observing itself (strange loop)
9. Print full audit trail

Usage:
    python3 scripts/gaia_demo.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.gaia_ledger import (
    ComputeUnit,
    FundingUnit,
    GaiaLedger,
    LaborUnit,
    Morphism,
    MorphismType,
    OffsetUnit,
    UnitType,
    VerificationUnit,
)
from dharma_swarm.gaia_verification import OracleVerdict, verify_offset
from dharma_swarm.gaia_fitness import (
    EcologicalFitness,
    detect_goodhart_drift,
    gaia_observer_function,
    observe_ledger,
)


def hr(title: str = "") -> None:
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
    else:
        print(f"{'─' * 60}")


def main() -> None:
    ledger = GaiaLedger()

    # ── Step 1: Record AI Compute ────────────────────────────────
    hr("STEP 1: Record AI Compute Footprint")

    compute = ComputeUnit(
        provider="anthropic",
        energy_mwh=50_000.0,  # One large training run
        carbon_intensity=0.385,  # US average grid (tons CO2e/MWh)
        workload_type="training",
        metadata={"model": "claude-next", "cluster": "us-east-1"},
    )
    ledger.record_compute(compute)
    print(f"  Recorded: {compute.energy_mwh:,.0f} MWh training run")
    print(f"  CO2e: {compute.co2e_tons:,.0f} tons")
    print(f"  (Equivalent: San Francisco for ~3 days)")

    # Also record ongoing inference
    inference = ComputeUnit(
        provider="anthropic",
        energy_mwh=8_760.0,  # 1 MW continuous for a year
        carbon_intensity=0.385,
        workload_type="inference",
        metadata={"service": "claude-api", "period": "2026-Q1"},
    )
    ledger.record_compute(inference)
    print(f"  Recorded: {inference.energy_mwh:,.0f} MWh inference (1yr)")
    print(f"  CO2e: {inference.co2e_tons:,.0f} tons")

    total_co2e = ledger.total_compute_co2e()
    print(f"\n  TOTAL COMPUTE CO2e: {total_co2e:,.0f} tons")

    # ── Step 2: Fund Restoration Project ─────────────────────────
    hr("STEP 2: Fund Mangrove Restoration Project")

    funding = FundingUnit(
        amount_usd=2_500_000.0,
        source="anthropic",
        destination="coastal-louisiana-restoration-coop",
        purpose="mangrove_restoration",
        metadata={"project": "bayou-lafourche-mangroves"},
    )
    ledger.record_funding(funding)
    print(f"  Funded: ${funding.amount_usd:,.0f}")
    print(f"  Source: {funding.source}")
    print(f"  Destination: {funding.destination}")

    # ── Step 3: Record Offset Claims ─────────────────────────────
    hr("STEP 3: Register Offset Claims (Pending Verification)")

    # Mangrove restoration sequesters ~10 tons CO2e/hectare/year
    # 500 hectares * 10 tons * estimated 5 years = 25,000 tons
    offset = OffsetUnit(
        project_id="bayou-lafourche-mangroves",
        co2e_tons=25_000.0,
        method="mangrove_restoration",
        metadata={
            "hectares": 500,
            "sequestration_rate": "10 tCO2e/ha/yr",
            "vintage_years": 5,
            "location": "Lafourche Parish, Louisiana",
        },
    )
    ledger.record_offset(offset)
    print(f"  Claimed: {offset.co2e_tons:,.0f} tons CO2e")
    print(f"  Method: {offset.method}")
    print(f"  Verified: {offset.is_verified} (pending oracle verification)")

    # Check conservation: should flag unverified claims
    violations = ledger.conservation_check()
    print(f"\n  Conservation check: {len(violations)} violation(s)")
    for v in violations:
        print(f"    [{v.law}] {v.description}")

    # ── Step 4: Employ Workers ───────────────────────────────────
    hr("STEP 4: Employ Displaced Workers")

    workers = [
        ("W001", "planting", 30.0, 2000, "seedlings"),
        ("W002", "planting", 30.0, 1800, "seedlings"),
        ("W003", "monitoring", 32.0, 50, "survey_plots"),
        ("W004", "drone_survey", 35.0, 200, "hectares_mapped"),
        ("W005", "soil_sampling", 28.0, 100, "samples"),
    ]

    for wid, skill, wage, output, unit in workers:
        labor = LaborUnit(
            worker_id=wid,
            project_id="bayou-lafourche-mangroves",
            hours=160.0,  # Full month
            skill_type=skill,
            location="Lafourche Parish, LA",
            output_metric=float(output),
            output_unit=unit,
            wage_rate=wage,
        )
        ledger.record_labor(labor)

    print(f"  Workers employed: {ledger.worker_count()}")
    print(f"  Total hours: {ledger.total_labor_hours():,.0f}")
    print(f"  Monthly payroll: ${sum(w[2] * 160 for w in workers):,.0f}")
    print(f"  Skills: {', '.join(set(w[1] for w in workers))}")

    # ── Step 5: Run 3-of-5 Oracle Verification ──────────────────
    hr("STEP 5: Oracle Verification (3-of-5 Threshold)")

    verdicts = [
        OracleVerdict(
            oracle_type="satellite",
            target_id=offset.id,
            confidence=0.88,
            agrees_with_claim=True,
            evidence_summary="Sentinel-2 NDVI analysis shows 487/500 hectares with mangrove canopy growth consistent with claimed restoration",
            evidence_hash="a1b2c3d4e5f6",
        ),
        OracleVerdict(
            oracle_type="iot_sensor",
            target_id=offset.id,
            confidence=0.82,
            agrees_with_claim=True,
            evidence_summary="12 soil carbon sensors across site report avg 45 tC/ha, above 38 tC/ha baseline",
            evidence_hash="b2c3d4e5f6a1",
        ),
        OracleVerdict(
            oracle_type="human_auditor",
            target_id=offset.id,
            confidence=0.91,
            agrees_with_claim=True,
            evidence_summary="Third-party auditor (Bureau Veritas) conducted 3-day site visit, confirmed species diversity and biomass estimates",
            evidence_hash="c3d4e5f6a1b2",
        ),
        OracleVerdict(
            oracle_type="community",
            target_id=offset.id,
            confidence=0.75,
            agrees_with_claim=True,
            evidence_summary="Community council (12 members) attests to project employment and ecological improvement; notes concerns about water access",
            evidence_hash="d4e5f6a1b2c3",
        ),
        OracleVerdict(
            oracle_type="statistical_model",
            target_id=offset.id,
            confidence=0.79,
            agrees_with_claim=False,  # Dissent!
            evidence_summary="Bayesian model estimates 18,200 tons (not 25,000) based on regional mangrove growth curves and climate adjustment",
            evidence_hash="e5f6a1b2c3d4",
        ),
    ]

    session, coordination = verify_offset(ledger, offset.id, verdicts)

    print(f"  Oracles polled: {session.oracle_count}")
    print(f"  Agreeing: {session.agreement_count} ({', '.join(session.agreeing_oracles)})")
    print(f"  Dissenting: {len(session.dissenting_oracles)} ({', '.join(session.dissenting_oracles)})")
    print(f"  Threshold met: {session.meets_threshold}")
    print(f"  Final confidence: {session.final_confidence:.2%}")
    print(f"  Offset now verified: {offset.is_verified}")

    if coordination:
        print(f"\n  Sheaf Cohomology:")
        print(f"    H0 (global truths): {len(coordination.global_truths)}")
        print(f"    H1 (disagreements): {len(coordination.productive_disagreements)}")
        print(f"    Globally coherent: {coordination.is_globally_coherent}")
        for d in coordination.productive_disagreements:
            print(f"    Disagreement: {d.claim_key}")
            for agent_id, content in d.conflicting_contents.items():
                print(f"      [{agent_id}] {content[:80]}")

    # ── Step 6: Post-Verification Audit ──────────────────────────
    hr("STEP 6: Post-Verification Conservation Audit")

    violations = ledger.conservation_check()
    print(f"  Conservation violations: {len(violations)}")
    for v in violations:
        print(f"    [{v.law}] severity={v.severity:.2f}: {v.description}")

    print(f"\n  Net carbon position: {ledger.net_carbon_position():,.0f} tons")
    if ledger.net_carbon_position() > 0:
        print(f"  (Still emitting — need {ledger.net_carbon_position():,.0f} more tons offset)")
    else:
        print(f"  NET NEGATIVE!")

    # ── Step 7: Goodhart Drift Detection ─────────────────────────
    hr("STEP 7: Goodhart Drift Detection")

    drift = detect_goodhart_drift(ledger)
    print(f"  Drifting: {drift['is_drifting']}")
    print(f"  Verification ratio: {drift['verification_ratio']:.2%}")
    print(f"  Coverage: {drift['coverage']:.2%}")
    print(f"  Oracle diversity: {drift['diversity']:.2%}")
    print(f"  Self-referential fitness: {drift['self_referential_fitness']:.3f}")
    print(f"  Diagnosis: {drift['diagnosis']}")

    # ── Step 8: Self-Observation (Strange Loop) ──────────────────
    hr("STEP 8: Self-Observation — The Strange Loop")

    reading = gaia_observer_function(ledger)
    print(f"  R_V-like reading: {reading.rv:.3f}")
    print(f"  PR_early (before observation): {reading.pr_early:.1f}")
    print(f"  PR_late (after observation): {reading.pr_late:.3f}")
    print(f"  Contraction: {'YES' if reading.rv < 0.737 else 'NO'}")
    print(f"  Strength: {reading.contraction_strength}")

    observed = observe_ledger(ledger)
    print(f"\n  ObservedState wrapping:")
    print(f"    Observation depth: {observed.observation_depth}")
    print(f"    Has R_V reading: {observed.rv_reading is not None}")
    if observed.rv_reading:
        print(f"    R_V: {observed.rv_reading.rv:.3f}")
    print(f"    Introspection keys: {list(observed.introspection.keys())}")

    # ── Step 9: Ecological Fitness Score ─────────────────────────
    hr("STEP 9: Darwin Engine Fitness Score")

    fitness = EcologicalFitness()
    score = fitness.score(ledger)
    weighted = fitness.weighted_score(ledger)
    print(f"  Correctness (conservation integrity): {score.correctness:.2f}")
    print(f"  Elegance (oracle diversity): {score.elegance:.2f}")
    print(f"  Safety (verification coverage): {score.safety:.2f}")
    print(f"  Dharmic alignment (carbon progress): {score.dharmic_alignment:.2f}")
    print(f"  Weighted ecological fitness: {weighted:.3f}")

    # ── Step 10: Full Ledger Summary ─────────────────────────────
    hr("STEP 10: Full Categorical Audit Trail")

    summary = ledger.summary()
    print(f"  Ledger entries: {summary['entries']}")
    print(f"  Hash chain valid: {summary['chain_valid']}")
    print(f"  Compute units: {summary['compute_units']}")
    print(f"  Offset units: {summary['offset_units']}")
    print(f"  Funding units: {summary['funding_units']}")
    print(f"  Labor units: {summary['labor_units']}")
    print(f"  Verification units: {summary['verification_units']}")
    print(f"  Morphisms: {summary['morphisms']}")
    hr()
    print(f"  TOTAL COMPUTE CO2e:     {summary['total_compute_co2e']:>12,.0f} tons")
    print(f"  TOTAL VERIFIED OFFSET:  {summary['total_verified_offset']:>12,.0f} tons")
    print(f"  NET CARBON POSITION:    {summary['net_carbon_position']:>+12,.0f} tons")
    print(f"  TOTAL LABOR HOURS:      {summary['total_labor_hours']:>12,.0f} hours")
    print(f"  TOTAL FUNDING:          ${summary['total_funding_usd']:>11,.0f}")
    print(f"  UNIQUE WORKERS:         {summary['worker_count']:>12}")
    print(f"  CONSERVATION VIOLATIONS:{summary['conservation_violations']:>12}")
    hr()

    print("\n  The system that measures ecological integrity")
    print("  measures its own measuring.")
    print("  R_V < 1.0: contraction detected. The strange loop holds.")
    print("\n  JSCA!")


if __name__ == "__main__":
    main()
