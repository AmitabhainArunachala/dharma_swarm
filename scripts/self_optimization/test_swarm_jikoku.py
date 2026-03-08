#!/usr/bin/env python3
"""Test JIKOKU instrumentation in swarm operations."""

import asyncio
import os
from pathlib import Path

# Enable JIKOKU
os.environ['JIKOKU_ENABLED'] = '1'

from dharma_swarm.swarm import SwarmManager
from dharma_swarm.jikoku_samaya import get_global_tracer, init_tracer
from dharma_swarm.models import AgentRole, TaskPriority


async def main():
    print("=" * 60)
    print("JIKOKU SWARM OPERATIONS TEST")
    print("=" * 60)
    print()

    # Initialize tracer with custom session
    log_path = Path.home() / ".dharma" / "jikoku" / "swarm_test.jsonl"
    init_tracer(log_path=log_path, session_id="swarm-test-001")
    print(f"✓ Tracer initialized: {log_path}")
    print()

    # Create swarm manager
    print("Creating swarm manager...")
    swarm = SwarmManager(state_dir=".dharma_test")
    await swarm.init()
    print("✓ Swarm initialized")
    print()

    # Test 1: Spawn an agent (should create span)
    print("Test 1: Spawning agent (should create span)")
    print("-" * 60)
    try:
        agent = await swarm.spawn_agent(
            name="test-agent",
            role=AgentRole.RESEARCHER,
        )
        print(f"✓ Agent spawned: {agent.name}")
    except Exception as e:
        print(f"✗ Agent spawn failed: {e}")
    print()

    # Test 2: Create a task (should create span)
    print("Test 2: Creating task (should create span)")
    print("-" * 60)
    try:
        task = await swarm.create_task(
            title="Test task",
            description="Test JIKOKU instrumentation",
            priority=TaskPriority.NORMAL,
        )
        print(f"✓ Task created: {task.title}")
    except Exception as e:
        print(f"✗ Task creation failed: {e}")
    print()

    # Check the generated spans
    print("Test 3: Inspecting generated spans")
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

    # Cleanup
    await swarm.shutdown()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
