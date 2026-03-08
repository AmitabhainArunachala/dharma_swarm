#!/usr/bin/env python3
"""Test JIKOKU → Fitness integration.

Verifies that performance improvements measured by JIKOKU
are reflected in evolution fitness scores.
"""

import asyncio
import os
from pathlib import Path
import tempfile

# Enable JIKOKU
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.evolution import DarwinEngine
from dharma_swarm.jikoku_samaya import init_tracer, get_global_tracer


async def simulate_baseline_session(log_path: Path) -> str:
    """Simulate a baseline session with slow operations."""
    import time
    session_id = f"baseline-{int(time.time() * 1000)}"
    tracer = init_tracer(log_path=log_path, session_id=session_id)

    # Simulate some slow operations
    with tracer.span("execute.task_create", "Slow task 1"):
        time.sleep(0.05)  # 50ms
    with tracer.span("execute.task_create", "Slow task 2"):
        time.sleep(0.05)  # 50ms
    with tracer.span("execute.task_create", "Slow task 3"):
        time.sleep(0.05)  # 50ms

    return session_id


async def simulate_fast_session(log_path: Path) -> str:
    """Simulate an optimized session with fast operations."""
    import time
    session_id = f"test-{int(time.time() * 1000)}"
    tracer = init_tracer(log_path=log_path, session_id=session_id)

    # Simulate faster operations (batch optimization)
    with tracer.span("execute.task_create_batch", "Fast batch", task_count=3):
        time.sleep(0.01)  # 10ms total (vs 150ms before)

    return session_id


async def main():
    print("=" * 70)
    print("JIKOKU → FITNESS INTEGRATION TEST")
    print("=" * 70)
    print()

    # Initialize tracer
    log_path = Path.home() / ".dharma" / "jikoku" / "fitness_test.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()  # Clean start
    init_tracer(log_path=log_path)
    print(f"Log: {log_path}")
    print()

    # Simulate baseline (slow)
    print("Step 1: Simulating baseline session (slow operations)")
    print("-" * 70)
    baseline_session = await simulate_baseline_session(log_path)
    tracer = get_global_tracer()
    baseline_report = tracer.kaizen_report_for_session(baseline_session)
    if 'error' in baseline_report:
        print(f"  Error: {baseline_report['error']}")
        print("  Falling back to current session spans")
        spans = tracer.get_session_spans(baseline_session)
        print(f"  Found {len(spans)} spans")
        return
    print(f"  Session: {baseline_session}")
    print(f"  Wall clock: {baseline_report['wall_clock_sec']*1000:.1f}ms")
    print(f"  Utilization: {baseline_report['utilization_pct']:.1f}%")
    print()

    # Simulate optimized (fast)
    print("Step 2: Simulating optimized session (fast operations)")
    print("-" * 70)
    test_session = await simulate_fast_session(log_path)
    test_report = tracer.kaizen_report_for_session(test_session)
    print(f"  Session: {test_session}")
    print(f"  Wall clock: {test_report['wall_clock_sec']*1000:.1f}ms")
    print(f"  Utilization: {test_report['utilization_pct']:.1f}%")
    print()

    # Calculate speedup
    speedup = baseline_report['wall_clock_sec'] / test_report['wall_clock_sec']
    util_improvement = test_report['utilization_pct'] - baseline_report['utilization_pct']
    print(f"Performance improvement:")
    print(f"  Speedup: {speedup:.2f}x")
    print(f"  Utilization improvement: {util_improvement:+.1f}%")
    print()

    # Create Darwin Engine
    print("Step 3: Evaluating proposal with JIKOKU metrics")
    print("-" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        engine = DarwinEngine(
            archive_path=tmp_path / "archive.jsonl",
            traces_path=tmp_path / "traces",
            predictor_path=tmp_path / "predictor_data.jsonl",
        )
        await engine.init()

        # Create a proposal
        proposal = await engine.propose(
            component="task_board.py",
            change_type="mutation",
            description="Add batch task creation to eliminate SQLite lock contention",
            diff="+ async def create_batch(...)",
        )
        print(f"  Created proposal: {proposal.id[:8]}")

        # Gate check
        proposal = await engine.gate_check(proposal)
        print(f"  Gate check: {proposal.status.value}")

        # Evaluate WITH JIKOKU metrics
        proposal = await engine.evaluate(
            proposal,
            test_results={"pass_rate": 1.0},  # Tests pass
            code="async def create_batch(): pass",  # Dummy code
            baseline_session_id=baseline_session,
            test_session_id=test_session,
        )
        print(f"  Evaluated with JIKOKU metrics")
        print()

        # Show fitness breakdown
        print("Step 4: Fitness breakdown")
        print("-" * 70)
        fitness = proposal.actual_fitness
        if fitness:
            print(f"  Correctness:       {fitness.correctness:.3f} (30% weight)")
            print(f"  Dharmic alignment: {fitness.dharmic_alignment:.3f} (25% weight)")
            print(f"  Performance:       {fitness.performance:.3f} (15% weight) ← JIKOKU")
            print(f"  Utilization:       {fitness.utilization:.3f} (15% weight) ← JIKOKU")
            print(f"  Elegance:          {fitness.elegance:.3f} (15% weight)")
            print(f"  Efficiency:        {fitness.efficiency:.3f} (15% weight)")
            print(f"  Safety:            {fitness.safety:.3f} (15% weight)")
            print()
            print(f"  WEIGHTED TOTAL:    {fitness.weighted():.3f}")
            print()

            # Verify JIKOKU impact
            print("Step 5: Verifying JIKOKU integration")
            print("-" * 70)
            if fitness.performance > 0.5:
                print(f"  ✅ Performance dimension captures speedup")
                print(f"     ({fitness.performance:.3f} reflects {speedup:.2f}x improvement)")
            else:
                print(f"  ⚠️  Performance dimension didn't capture speedup")
                print(f"     (score={fitness.performance:.3f}, speedup={speedup:.2f}x)")

            if fitness.utilization != 0.5:
                print(f"  ✅ Utilization dimension is active")
                print(f"     ({fitness.utilization:.3f} reflects {util_improvement:+.1f}% change)")
            else:
                print(f"  ⚠️  Utilization dimension is neutral")
                print(f"     (score={fitness.utilization:.3f}, change={util_improvement:+.1f}%)")

            # Show impact on selection
            print()
            print("Step 6: Impact on evolution")
            print("-" * 70)
            old_weights = {
                "correctness": 0.30,
                "dharmic_alignment": 0.25,
                "elegance": 0.15,
                "efficiency": 0.15,
                "safety": 0.15,
            }
            old_fitness_score = (
                fitness.correctness * 0.30 +
                fitness.dharmic_alignment * 0.25 +
                fitness.elegance * 0.15 +
                fitness.efficiency * 0.15 +
                fitness.safety * 0.15
            )
            new_fitness_score = fitness.weighted()

            print(f"  Without JIKOKU metrics: {old_fitness_score:.3f}")
            print(f"  With JIKOKU metrics:    {new_fitness_score:.3f}")
            print(f"  Difference:             {new_fitness_score - old_fitness_score:+.3f}")
            print()

            if new_fitness_score > old_fitness_score:
                print("  ✅ INTEGRATION SUCCESSFUL")
                print("     Performance improvements now increase fitness!")
                print("     Darwin engine will select faster code.")
            else:
                print("  ⚠️  JIKOKU metrics didn't improve fitness")
                print("     Check if session IDs are correct")

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
