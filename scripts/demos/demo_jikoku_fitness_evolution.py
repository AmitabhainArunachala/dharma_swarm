#!/usr/bin/env python3
"""Demonstrate JIKOKU → Fitness → Darwin Selection closed loop.

This script proves the integration works end-to-end:
1. Baseline: Sequential operations (slow)
2. Optimized: Batch operations (fast)
3. JIKOKU measures both
4. Fitness includes performance metrics
5. Darwin engine selects faster code

Expected result: Optimized proposal wins due to higher performance fitness.
"""

import asyncio
import os
import time
from pathlib import Path
import tempfile

# Enable JIKOKU
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.evolution import DarwinEngine
from dharma_swarm.jikoku_samaya import init_tracer, get_global_tracer


async def run_baseline_workload(log_path: Path) -> str:
    """Simulate baseline: 5 sequential database writes (slow)."""
    session_id = f"baseline-{int(time.time() * 1000)}"
    tracer = init_tracer(log_path=log_path, session_id=session_id)

    # Simulate sequential writes (what we had before batch optimization)
    for i in range(5):
        with tracer.span("execute.task_create", f"Sequential task {i+1}"):
            time.sleep(0.02)  # 20ms per write = 100ms total

    return session_id


async def run_optimized_workload(log_path: Path) -> str:
    """Simulate optimized: 1 batch write (fast)."""
    session_id = f"optimized-{int(time.time() * 1000)}"
    tracer = init_tracer(log_path=log_path, session_id=session_id)

    # Simulate batch write (single transaction)
    with tracer.span("execute.task_create_batch", "Batch 5 tasks", task_count=5):
        time.sleep(0.005)  # 5ms total (4x faster)

    return session_id


async def main():
    print("=" * 70)
    print("JIKOKU → FITNESS → DARWIN SELECTION DEMO")
    print("=" * 70)
    print()

    # Setup JIKOKU logging
    log_path = Path.home() / ".dharma" / "jikoku" / "demo_evolution.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()
    init_tracer(log_path=log_path)
    print(f"JIKOKU log: {log_path}")
    print()

    # Step 1: Run baseline workload
    print("Step 1: Running BASELINE workload (sequential writes)")
    print("-" * 70)
    baseline_session = await run_baseline_workload(log_path)
    tracer = get_global_tracer()
    baseline_report = tracer.kaizen_report_for_session(baseline_session)
    baseline_wall = baseline_report['wall_clock_sec'] * 1000
    baseline_util = baseline_report['utilization_pct']
    print(f"  Session: {baseline_session}")
    print(f"  Wall clock: {baseline_wall:.1f}ms")
    print(f"  Utilization: {baseline_util:.1f}%")
    print()

    # Step 2: Run optimized workload
    print("Step 2: Running OPTIMIZED workload (batch write)")
    print("-" * 70)
    optimized_session = await run_optimized_workload(log_path)
    optimized_report = tracer.kaizen_report_for_session(optimized_session)
    optimized_wall = optimized_report['wall_clock_sec'] * 1000
    optimized_util = optimized_report['utilization_pct']
    print(f"  Session: {optimized_session}")
    print(f"  Wall clock: {optimized_wall:.1f}ms")
    print(f"  Utilization: {optimized_util:.1f}%")
    print()

    # Calculate performance improvement
    speedup = baseline_wall / optimized_wall
    util_improvement = optimized_util - baseline_util
    print(f"Performance improvement:")
    print(f"  Speedup: {speedup:.2f}x")
    print(f"  Utilization: {util_improvement:+.1f}%")
    print()

    # Step 3: Create Darwin Engine
    print("Step 3: Creating Darwin Engine proposals")
    print("-" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        engine = DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
            predictor_path=tmp_path / "predictor_data.jsonl",
        )
        await engine.init()

        # Proposal A: Baseline (slow) code
        baseline_proposal = await engine.propose(
            component="task_board.py",
            change_type="mutation",
            description="Sequential task creation (baseline)",
            diff="+ for task in tasks:\n+     await create(task)",
        )
        baseline_proposal = await engine.gate_check(baseline_proposal)
        baseline_proposal = await engine.evaluate(
            baseline_proposal,
            test_results={"pass_rate": 1.0},
            code="for task in tasks: await create(task)",
            baseline_session_id=baseline_session,
            test_session_id=baseline_session,  # Compare to itself (neutral)
        )

        # Proposal B: Optimized (fast) code
        optimized_proposal = await engine.propose(
            component="task_board.py",
            change_type="mutation",
            description="Batch task creation (optimized)",
            diff="+ await create_batch(tasks)",
        )
        optimized_proposal = await engine.gate_check(optimized_proposal)
        optimized_proposal = await engine.evaluate(
            optimized_proposal,
            test_results={"pass_rate": 1.0},
            code="await create_batch(tasks)",
            baseline_session_id=baseline_session,
            test_session_id=optimized_session,  # Compare to baseline
        )

        print(f"  Baseline proposal:  {baseline_proposal.id[:8]}")
        print(f"  Optimized proposal: {optimized_proposal.id[:8]}")
        print()

        # Step 4: Compare fitness
        print("Step 4: Fitness comparison")
        print("-" * 70)

        baseline_fitness = baseline_proposal.actual_fitness
        optimized_fitness = optimized_proposal.actual_fitness

        if not baseline_fitness or not optimized_fitness:
            print("  ❌ Fitness evaluation failed")
            return

        print("BASELINE (Sequential):")
        print(f"  Correctness:       {baseline_fitness.correctness:.3f}")
        print(f"  Dharmic alignment: {baseline_fitness.dharmic_alignment:.3f}")
        print(f"  Performance:       {baseline_fitness.performance:.3f} ← JIKOKU")
        print(f"  Utilization:       {baseline_fitness.utilization:.3f} ← JIKOKU")
        print(f"  Elegance:          {baseline_fitness.elegance:.3f}")
        print(f"  Efficiency:        {baseline_fitness.efficiency:.3f}")
        print(f"  Safety:            {baseline_fitness.safety:.3f}")
        print(f"  WEIGHTED TOTAL:    {baseline_fitness.weighted():.3f}")
        print()

        print("OPTIMIZED (Batch):")
        print(f"  Correctness:       {optimized_fitness.correctness:.3f}")
        print(f"  Dharmic alignment: {optimized_fitness.dharmic_alignment:.3f}")
        print(f"  Performance:       {optimized_fitness.performance:.3f} ← JIKOKU")
        print(f"  Utilization:       {optimized_fitness.utilization:.3f} ← JIKOKU")
        print(f"  Elegance:          {optimized_fitness.elegance:.3f}")
        print(f"  Efficiency:        {optimized_fitness.efficiency:.3f}")
        print(f"  Safety:            {optimized_fitness.safety:.3f}")
        print(f"  WEIGHTED TOTAL:    {optimized_fitness.weighted():.3f}")
        print()

        # Step 5: Darwin selection
        print("Step 5: Darwin Engine selection")
        print("-" * 70)

        baseline_total = baseline_fitness.weighted()
        optimized_total = optimized_fitness.weighted()

        if optimized_total > baseline_total:
            winner = "OPTIMIZED"
            delta = optimized_total - baseline_total
            perf_contribution = (
                (optimized_fitness.performance - baseline_fitness.performance) * 0.15 +
                (optimized_fitness.utilization - baseline_fitness.utilization) * 0.15
            )
            print(f"  ✅ WINNER: {winner}")
            print(f"  Fitness delta: +{delta:.3f}")
            print(f"  JIKOKU contribution: +{perf_contribution:.3f} (30% weight)")
            print()
            print(f"  Darwin engine selects OPTIMIZED proposal")
            print(f"  Reason: {speedup:.2f}x speedup → +{perf_contribution:.3f} fitness")
            print()
            print("  ✅ CLOSED LOOP CONFIRMED")
            print("     JIKOKU measures → Fitness rewards → Darwin selects → Fast code wins")
        else:
            winner = "BASELINE"
            delta = baseline_total - optimized_total
            print(f"  ⚠️  WINNER: {winner}")
            print(f"  Fitness delta: +{delta:.3f}")
            print()
            print(f"  ❌ UNEXPECTED: Baseline won despite being slower")
            print(f"  Check: Did JIKOKU metrics integrate correctly?")

    print()
    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
