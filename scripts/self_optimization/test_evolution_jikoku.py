#!/usr/bin/env python3
"""Test JIKOKU instrumentation in evolution operations."""

import asyncio
import os
from pathlib import Path
import tempfile

# Enable JIKOKU
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.evolution import DarwinEngine
from dharma_swarm.jikoku_samaya import get_global_tracer, init_tracer


async def main():
    print("=" * 60)
    print("JIKOKU EVOLUTION PIPELINE TEST")
    print("=" * 60)
    print()

    # Initialize tracer with custom session
    log_path = Path.home() / ".dharma" / "jikoku" / "evolution_test.jsonl"
    init_tracer(log_path=log_path, session_id="evolution-test-001")
    print(f"✓ Tracer initialized: {log_path}")
    print()

    # Create temporary directories for evolution engine
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        archive_path = tmp_path / "archive.jsonl"
        traces_path = tmp_path / "traces"
        predictor_path = tmp_path / "predictor_data.jsonl"

        # Create evolution engine
        print("Creating Darwin Engine...")
        engine = DarwinEngine(
            archive_path=archive_path,
            traces_path=traces_path,
            predictor_path=predictor_path,
        )
        await engine.init()
        print("✓ Darwin Engine initialized")
        print()

        # Test: Full evolution pipeline (propose → gate → evaluate → archive)
        print("Test: Full evolution pipeline (should create 4 spans)")
        print("-" * 60)

        # Step 1: Propose
        proposal = await engine.propose(
            component="test_module.py",
            change_type="mutation",
            description="Test mutation for JIKOKU tracing",
            diff="+ print('hello')\n- print('goodbye')",
        )
        print(f"✓ Step 1: Proposed {proposal.id[:8]}")

        # Step 2: Gate check
        proposal = await engine.gate_check(proposal)
        print(f"✓ Step 2: Gate checked - {proposal.status.value}")

        # Step 3: Evaluate
        proposal = await engine.evaluate(
            proposal,
            test_results={"pass_rate": 0.9},
            code="def hello(): print('hello')",
        )
        fitness_val = proposal.actual_fitness.weighted() if proposal.actual_fitness else 0.0
        print(f"✓ Step 3: Evaluated - fitness={fitness_val:.3f}")

        # Step 4: Archive
        entry_id = await engine.archive_result(proposal)
        print(f"✓ Step 4: Archived - entry_id={entry_id[:8]}")
        print()

        # Check the generated spans
        print("Inspecting generated spans")
        print("-" * 60)
        tracer = get_global_tracer()
        spans = tracer.get_session_spans()

        if spans:
            print(f"✓ Found {len(spans)} span(s) in this session:")
            for i, span in enumerate(spans, 1):
                print(f"\n  Span {i}:")
                print(f"    Category: {span.category}")
                print(f"    Intent: {span.intent}")
                print(f"    Duration: {span.duration_sec:.3f}s")
                if span.metadata:
                    print(f"    Metadata: {span.metadata}")
        else:
            print("  No spans recorded")
        print()

        # Generate kaizen report
        print("Generating kaizen report")
        print("-" * 60)
        report = tracer.kaizen_report(last_n_sessions=1)
        if 'error' not in report:
            print(f"  Sessions analyzed: {report['sessions_analyzed']}")
            print(f"  Total spans: {report['total_spans']}")
            print(f"  Total compute: {report['total_compute_sec']:.3f}s")
            print(f"  Wall clock: {report['wall_clock_sec']:.3f}s")
            print(f"  Utilization: {report['utilization_pct']:.1f}%")
            print(f"  Pramāda (idle): {report['idle_pct']:.1f}%")
        else:
            print(f"  {report['error']}")

    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
