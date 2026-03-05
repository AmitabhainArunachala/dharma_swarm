#!/usr/bin/env python3
"""Gödel Claw v1 — Full Loop Integration Test.

Tests the ENTIRE pipeline end-to-end:
  1. Propose → 2. Gate → 3. Sandbox → 4. Evaluate → 5. Archive → 6. Canary
  Plus: Dharma layer, all 11 gates, Stigmergy + Subconscious + Shakti

Run: python3 ~/dharma_swarm/test_full_loop.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_darwin_loop():
    """Full Darwin Engine loop: propose → gate → sandbox → eval → archive → canary."""
    print("=" * 60)
    print("  DARWIN ENGINE — Full Loop Test")
    print("=" * 60)

    from dharma_swarm.evolution import DarwinEngine

    with tempfile.TemporaryDirectory() as td:
        archive_path = Path(td) / "archive.jsonl"
        traces_path = Path(td) / "traces"
        predictor_path = Path(td) / "predictor.jsonl"

        engine = DarwinEngine(
            archive_path=archive_path,
            traces_path=traces_path,
            predictor_path=predictor_path,
        )

        # Step 1: Propose (async)
        proposal = await engine.propose(
            component="elegance",
            change_type="mutation",
            description="Add docstring length scoring to elegance module",
        )
        print(f"\n1. PROPOSE  : {proposal.id[:12]}  component={proposal.component}  status={proposal.status}")

        # Step 2: Gate (async, uses engine's built-in gatekeeper)
        proposal = await engine.gate_check(proposal)
        print(f"2. GATE     : decision={proposal.gate_decision}  status={proposal.status}")

        # Step 3: Sandbox (runs real pytest)
        proposal, sandbox_result = await engine.apply_in_sandbox(
            proposal=proposal,
            test_command="cd /Users/dhyana/dharma_swarm && python3 -m pytest tests/test_elegance.py -q --tb=short",
            timeout=60,
        )
        test_results = DarwinEngine._parse_sandbox_result(sandbox_result)
        passed = test_results.get("pass_rate", 0) > 0
        print(f"3. SANDBOX  : exit_code={sandbox_result.exit_code}  pass_rate={test_results.get('pass_rate', 0):.2f}")

        # Step 4: Evaluate (async, returns updated proposal)
        proposal = await engine.evaluate(proposal, test_results=test_results)
        fitness = proposal.actual_fitness
        print(f"4. EVALUATE : weighted={fitness.weighted():.3f}  safety={fitness.safety:.2f}  elegance={fitness.elegance:.2f}")

        # Step 5: Archive (async, takes just proposal)
        entry_id = await engine.archive_result(proposal)
        print(f"5. ARCHIVE  : entry_id={entry_id[:12]}  stored=True")

        # Step 6: Canary (async, uses entry_id as baseline)
        from dharma_swarm.canary import CanaryDeployer
        canary = CanaryDeployer(archive=engine.archive)
        canary_result = await canary.evaluate_canary(
            entry_id=entry_id,
            canary_fitness=fitness.weighted() + 0.1,  # simulate slight improvement
        )
        print(f"6. CANARY   : decision={canary_result.decision}  delta={canary_result.delta:.3f}")

        darwin_ok = all([
            proposal.id,
            proposal.gate_decision in ("ALLOW", "REVIEW", "allow", "review"),
            sandbox_result.exit_code == 0,
            fitness.weighted() > 0,
            entry_id,
        ])
        print(f"\n{'PASS' if darwin_ok else 'FAIL'}: Darwin Engine loop {'closed' if darwin_ok else 'BROKEN'}")
        return darwin_ok


async def test_dharma_layer():
    """Dharma Kernel + Corpus + Policy Compiler."""
    print("\n" + "=" * 60)
    print("  DHARMA LAYER — Kernel + Corpus + Policy")
    print("=" * 60)

    from dharma_swarm.dharma_kernel import DharmaKernel, KernelGuard
    from dharma_swarm.dharma_corpus import DharmaCorpus
    from dharma_swarm.policy_compiler import PolicyCompiler

    # Kernel
    kernel = DharmaKernel.create_default()
    integrity = kernel.verify_integrity()
    print(f"\n1. KERNEL   : axioms={len(kernel.principles)}  integrity={integrity}")

    # Save/load roundtrip
    with tempfile.TemporaryDirectory() as td:
        guard = KernelGuard(Path(td) / "kernel.json")
        await guard.save(kernel)
        loaded = await guard.load()
        roundtrip = loaded.verify_integrity()
        print(f"2. PERSIST  : save+load  integrity_after={roundtrip}")

        # Corpus
        corpus = DharmaCorpus(Path(td) / "corpus.jsonl")
        claim = await corpus.propose(
            statement="Self-modification must preserve test coverage",
            category="safety",
            evidence_links=[],
            created_by="test_full_loop",
        )
        claim_id = claim.id
        await corpus.review(claim_id, reviewer="tui-claude", action="approve", comment="Agreed")
        await corpus.promote(claim_id)
        from dharma_swarm.dharma_corpus import ClaimStatus
        claims = await corpus.list_claims(status=ClaimStatus.ACCEPTED)
        print(f"3. CORPUS   : proposed+reviewed+promoted  accepted_count={len(claims)}")

        # Policy — compile takes kernel_principles dict + accepted_claims list
        compiler = PolicyCompiler()
        policy = compiler.compile(
            kernel_principles=kernel.principles,
            accepted_claims=claims,
        )
        immutable = policy.get_immutable_rules()
        mutable = policy.get_mutable_rules()
        print(f"4. POLICY   : immutable={len(immutable)}  mutable={len(mutable)}  total={len(policy.rules)}")

    dharma_ok = integrity and roundtrip and len(claims) == 1 and len(immutable) == 10
    print(f"\n{'PASS' if dharma_ok else 'FAIL'}: Dharma layer {'solid' if dharma_ok else 'BROKEN'}")
    return dharma_ok


async def test_gates():
    """All 11 gates fire."""
    print("\n" + "=" * 60)
    print("  GATES — All 11")
    print("=" * 60)

    from dharma_swarm.telos_gates import TelosGatekeeper

    gk = TelosGatekeeper()
    result = gk.check(action="test action", content="test content with analysis")
    gates_fired = list(result.gate_results.keys())
    print(f"\n  Gates: {len(gates_fired)}/11")
    for g, r in result.gate_results.items():
        print(f"    {g:20s} -> {r}")

    gates_ok = len(gates_fired) == 11
    print(f"\n{'PASS' if gates_ok else 'FAIL'}: {len(gates_fired)}/11 gates fired")
    return gates_ok


async def test_living_layers():
    """Stigmergy + Subconscious + Shakti."""
    print("\n" + "=" * 60)
    print("  LIVING LAYERS — Stigmergy + Subconscious + Shakti")
    print("=" * 60)

    from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark
    from dharma_swarm.subconscious import SubconsciousStream
    from dharma_swarm.shakti import ShaktiLoop, classify_energy

    with tempfile.TemporaryDirectory() as td:
        store = StigmergyStore(base_path=Path(td))

        # Leave marks to create hot paths
        for i in range(8):
            await store.leave_mark(StigmergicMark(
                agent=f"test-agent-{i}",
                file_path="dharma_swarm/evolution.py",
                action="scan",
                observation=f"Observation {i}: evolution pipeline architecture and design",
                salience=0.6 + i * 0.05,
                connections=["dharma_swarm/archive.py", "dharma_swarm/telos_gates.py"],
            ))

        density = store.density()
        hot = await store.hot_paths(window_hours=1, min_marks=3)
        high = await store.high_salience(threshold=0.8)
        print(f"\n1. STIGMERGY: density={density}  hot_paths={len(hot)}  high_salience={len(high)}")

        # Subconscious
        sub = SubconsciousStream(stigmergy=store, hum_path=Path(td) / "hum")
        dreams = await sub.dream(sample_size=5)
        print(f"2. SUBCON   : dreams={len(dreams)}")
        for d in dreams[:3]:
            print(f"    {d.source_a[:30]} <-> {d.source_b[:30]}: {d.resonance_type} ({d.strength:.2f})")

        # Shakti
        loop = ShaktiLoop(stigmergy=store)
        perceptions = await loop.perceive(
            current_context="Testing the full Godel Claw pipeline",
            agent_role="validator",
        )
        energy = classify_energy("vision architecture design pattern")
        print(f"3. SHAKTI   : perceptions={len(perceptions)}  classify('vision...')={energy}")

    living_ok = density >= 8 and len(hot) > 0
    print(f"\n{'PASS' if living_ok else 'FAIL'}: Living layers {'breathing' if living_ok else 'DEAD'}")
    return living_ok


async def main():
    print("\n" + "#" * 60)
    print("  GODEL CLAW v1 — FULL SYSTEM INTEGRATION TEST")
    print("#" * 60)

    results = {}
    results["darwin"] = await test_darwin_loop()
    results["dharma"] = await test_dharma_layer()
    results["gates"] = await test_gates()
    results["living"] = await test_living_layers()

    print("\n" + "=" * 60)
    print("  FINAL RESULTS")
    print("=" * 60)
    all_pass = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n  ALL SYSTEMS OPERATIONAL. The claw grips.")
    else:
        print("\n  FAILURES DETECTED. See above for details.")

    # Write results for crosswire
    result_path = Path.home() / ".dharma" / "shared" / "crosswire_reply.md"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        f"# Crosswire Reply — Full Loop Test\n\n"
        f"**All pass**: {all_pass}\n\n"
        + "\n".join(f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in results.items())
        + "\n"
    )
    print(f"\n  Results written to {result_path}")

    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
