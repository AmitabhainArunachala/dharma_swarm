#!/usr/bin/env python3
"""Baseline JIKOKU measurement - run real swarm operations and measure utilization.

This script:
1. Spawns agents with different roles
2. Creates diverse tasks
3. Runs a few orchestration ticks
4. Measures baseline utilization
5. Generates kaizen report with optimization targets
"""

import asyncio
import os
from pathlib import Path
import time

# Enable JIKOKU
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.swarm import SwarmManager
from dharma_swarm.jikoku_samaya import get_global_tracer, init_tracer
from dharma_swarm.models import AgentRole, TaskPriority


async def main():
    print("=" * 70)
    print("JIKOKU BASELINE MEASUREMENT")
    print("=" * 70)
    print()

    # Initialize tracer
    log_path = Path.home() / ".dharma" / "jikoku" / "baseline.jsonl"
    session_id = f"baseline-{int(time.time())}"
    init_tracer(log_path=log_path, session_id=session_id)
    print(f"Session: {session_id}")
    print(f"Log: {log_path}")
    print()

    # Create swarm
    print("Initializing swarm...")
    swarm = SwarmManager(state_dir=".dharma_baseline")
    await swarm.init()
    print(f"✓ Swarm initialized ({len(await swarm.list_agents())} default agents)")
    print()

    # Scenario 1: Spawn additional agents
    print("Scenario 1: Spawning diverse agents")
    print("-" * 70)
    roles = [
        ("code-reviewer", AgentRole.REVIEWER),
        ("test-writer", AgentRole.VALIDATOR),
        ("architect-lead", AgentRole.ARCHITECT),
    ]

    for name, role in roles:
        agent = await swarm.spawn_agent(name=name, role=role)
        print(f"  ✓ {name} ({role.value})")
    print()

    # Scenario 2: Create varied tasks
    print("Scenario 2: Creating diverse tasks")
    print("-" * 70)
    tasks = [
        ("Implement JIKOKU dashboard", "Create TUI view for real-time utilization metrics", TaskPriority.HIGH),
        ("Optimize archive operations", "Profile and reduce archive_result() overhead", TaskPriority.NORMAL),
        ("Add span filtering", "Filter spans by category in kaizen reports", TaskPriority.LOW),
        ("Document pramāda patterns", "Catalog common idle-time sources", TaskPriority.NORMAL),
        ("Create weekly cron job", "Auto-generate kaizen report every Monday 4:30am", TaskPriority.HIGH),
    ]

    for title, desc, priority in tasks:
        task = await swarm.create_task(title=title, description=desc, priority=priority)
        print(f"  ✓ [{priority.value}] {title}")
    print()

    # Scenario 3: Evolution pipeline test
    print("Scenario 3: Evolution pipeline (propose → gate → evaluate → archive)")
    print("-" * 70)

    if swarm._engine:
        # Propose a mutation
        proposal = await swarm._engine.propose(
            component="jikoku_samaya.py",
            change_type="mutation",
            description="Add caching for repeated pattern detection in kaizen reports",
            diff="""
@@ -234,6 +234,12 @@ class JikokuTracer:
     def kaizen_report(self, last_n_sessions: int = 7) -> dict:
         \"\"\"Generate kaizen (continuous improvement) report.\"\"\"
+        # Cache key for repeated queries
+        cache_key = f'kaizen_{last_n_sessions}_{self._session_id}'
+        if cache_key in self._report_cache:
+            return self._report_cache[cache_key]
+
         sessions = self._get_recent_sessions(last_n_sessions)
         if not sessions:
             return {'error': 'No sessions found'}
""".strip()
        )
        print(f"  ✓ Proposed {proposal.id[:8]} (predicted fitness: {proposal.predicted_fitness:.3f})")

        # Gate check
        proposal = await swarm._engine.gate_check(proposal)
        print(f"  ✓ Gate check: {proposal.status.value} ({proposal.gate_decision})")

        # Evaluate
        proposal = await swarm._engine.evaluate(
            proposal,
            test_results={"pass_rate": 0.85},
            code=open("dharma_swarm/jikoku_samaya.py").read()
        )
        fitness = proposal.actual_fitness.weighted() if proposal.actual_fitness else 0.0
        print(f"  ✓ Evaluated: fitness={fitness:.3f}")

        # Archive
        entry_id = await swarm._engine.archive_result(proposal)
        print(f"  ✓ Archived: {entry_id[:8]}")
    print()

    # Scenario 4: Memory operations
    print("Scenario 4: Memory operations")
    print("-" * 70)
    await swarm.remember("Baseline measurement in progress")
    await swarm.remember("JIKOKU integration shows promising zero overhead")
    await swarm.remember("All 1647 tests passing after instrumentation")
    memories = await swarm.recall(limit=3)
    print(f"  ✓ Stored 3 memories, recalled {len(memories)}")
    print()

    # Generate kaizen report
    print("=" * 70)
    print("KAIZEN REPORT (Baseline Utilization)")
    print("=" * 70)
    print()

    tracer = get_global_tracer()
    report = tracer.kaizen_report(last_n_sessions=1)

    if 'error' in report:
        print(f"Error: {report['error']}")
    else:
        print(f"Sessions analyzed: {report['sessions_analyzed']}")
        print(f"Total spans: {report['total_spans']}")
        print(f"Total compute time: {report['total_compute_sec']:.3f}s")
        print(f"Wall clock time: {report['wall_clock_sec']:.3f}s")
        print()
        print(f"UTILIZATION: {report['utilization_pct']:.1f}%")
        print(f"PRAMĀDA (idle): {report['idle_pct']:.1f}%")
        print()

        # Category breakdown
        print("Category Breakdown:")
        print("-" * 70)
        breakdown = report.get('category_breakdown', {})
        for category, stats in sorted(breakdown.items(), key=lambda x: x[1]['total_sec'], reverse=True):
            count = stats['count']
            total = stats['total_sec']
            avg = total / count if count > 0 else 0
            pct = (total / report['total_compute_sec'] * 100) if report['total_compute_sec'] > 0 else 0
            print(f"  {category:30s} {count:3d} spans  {total:6.3f}s  ({pct:5.1f}%)  avg={avg*1000:6.1f}ms")
        print()

        # Optimization targets
        if report.get('optimization_targets'):
            print("Top Optimization Targets (slowest spans):")
            print("-" * 70)
            for i, target in enumerate(report['optimization_targets'][:5], 1):
                cat = target['category']
                dur = target['duration_sec']
                intent = target.get('intent', 'N/A')
                print(f"  {i}. [{cat}] {dur:.3f}s - {intent[:50]}")
            print()

        # Kaizen goals
        if report.get('kaizen_goals'):
            print("Kaizen Goals (continuous improvement targets):")
            print("-" * 70)
            for i, goal in enumerate(report['kaizen_goals'][:5], 1):
                print(f"  {i}. {goal}")
            print()

        # Pramāda analysis
        idle = report['idle_pct']
        if idle > 50:
            print("⚠️  HIGH PRAMĀDA WARNING")
            print("-" * 70)
            print(f"Idle time is {idle:.1f}% - this represents significant waste.")
            print("Primary causes:")
            print("  - Long gaps between operations (orchestration delays)")
            print("  - Synchronous blocking operations")
            print("  - Inefficient I/O patterns")
            print()
        elif idle > 20:
            print("⚡ MODERATE PRAMĀDA")
            print("-" * 70)
            print(f"Idle time is {idle:.1f}% - room for optimization.")
            print("Target: Reduce to <10% through:")
            print("  - Parallelizing independent operations")
            print("  - Reducing file I/O overhead")
            print("  - Optimizing hot paths")
            print()
        else:
            print("✅ LOW PRAMĀDA")
            print("-" * 70)
            print(f"Idle time is {idle:.1f}% - excellent utilization!")
            print("Maintaining tight operation chains.")
            print()

    # Cleanup
    await swarm.shutdown()

    print("=" * 70)
    print("BASELINE MEASUREMENT COMPLETE")
    print("=" * 70)
    print()
    print(f"Log saved to: {log_path}")
    print(f"Review with: cat {log_path} | jq")
    print()


if __name__ == "__main__":
    asyncio.run(main())
