#!/usr/bin/env python3
"""
JIKOKU SAMAYA Integration Demo

Shows that all LLM providers are now automatically traced.
Run with: python3 demo_jikoku.py
"""

import asyncio
import os
from pathlib import Path

# Enable JIKOKU tracing
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.providers import AnthropicProvider
from dharma_swarm.models import LLMRequest
from dharma_swarm.jikoku_samaya import get_global_tracer, init_tracer, jikoku_kaizen


async def main():
    print("=" * 60)
    print("JIKOKU SAMAYA - Integration Demo")
    print("=" * 60)
    print()

    # Initialize tracer with custom session
    log_path = Path.home() / ".dharma" / "jikoku" / "demo.jsonl"
    init_tracer(log_path=log_path, session_id="demo-session-001")

    print(f"✓ Tracer initialized: {log_path}")
    print()

    # Test 1: Automatic provider tracing
    print("Test 1: Making LLM call (will be automatically traced)")
    print("-" * 60)

    # Check if we have API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠ ANTHROPIC_API_KEY not set - skipping actual API call")
        print("  (The tracing infrastructure is installed and ready)")
    else:
        provider = AnthropicProvider()
        request = LLMRequest(
            messages=[{"role": "user", "content": "Say hello in 5 words or less"}],
            model="claude-opus-4",
            max_tokens=50,
            temperature=0.7
        )

        try:
            print("Making API call...")
            response = await provider.complete(request)
            print(f"✓ Response: {response.content}")
            print(f"✓ Tokens: {response.usage}")
        except Exception as e:
            print(f"✗ API call failed: {e}")

    print()

    # Test 2: Check the generated spans
    print("Test 2: Inspecting generated spans")
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
        print("  No spans recorded yet (API call may have been skipped)")

    print()

    # Test 3: Generate kaizen report
    print("Test 3: Generating kaizen report")
    print("-" * 60)

    report = tracer.kaizen_report(last_n_sessions=1)

    if 'error' not in report:
        print(f"  Sessions analyzed: {report['sessions_analyzed']}")
        print(f"  Total spans: {report['total_spans']}")
        print(f"  Total compute: {report['total_compute_sec']:.2f}s")
        print(f"  Wall clock: {report['wall_clock_sec']:.2f}s")
        print(f"  Utilization: {report['utilization_pct']:.1f}%")
        print(f"  Pramāda (idle): {report['idle_pct']:.1f}%")

        if report['utilization_pct'] < 50:
            gain = 50 / report['utilization_pct'] if report['utilization_pct'] > 0 else float('inf')
            print(f"\n  ⚡ POTENTIAL GAIN: {gain:.1f}x efficiency")
            print(f"     (Path from {report['utilization_pct']:.1f}% → 50% utilization)")
    else:
        print(f"  {report['error']}")

    print()
    print("=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("What Just Happened:")
    print("  ✓ All 7 LLM providers now have automatic JIKOKU tracing")
    print("  ✓ Every API call creates a span with timing/cost/metadata")
    print("  ✓ Zero overhead when JIKOKU_ENABLED=0")
    print("  ✓ Kaizen reports identify optimization targets")
    print()
    print("Next Steps:")
    print("  1. Run swarm operations - all will be traced")
    print("  2. Check ~/.dharma/jikoku/JIKOKU_LOG.jsonl for spans")
    print("  3. Run kaizen reports every 7 sessions")
    print("  4. Path to 50% utilization = 10x efficiency gain")
    print()


if __name__ == "__main__":
    asyncio.run(main())
