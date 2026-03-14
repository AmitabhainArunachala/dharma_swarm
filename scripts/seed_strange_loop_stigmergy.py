#!/usr/bin/env python3
"""Seed high-salience stigmergy marks for Strange Loop files.

Run once to embed the Strange Loop into the colony's awareness.
Marks are written to ~/.dharma/stigmergy/marks.jsonl.
"""
import asyncio
from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

MARKS = [
    # Phase 0: Control Truth
    {
        "file_path": "dharma_swarm/swarm.py",
        "observation": "STRANGE LOOP: tick() is the ONE control path. All swarm state advances through here. Do NOT bypass with _orchestrator.tick().",
        "salience": 0.95,
        "action": "connect",
        "connections": ["dharma_swarm/orchestrate_live.py"],
    },
    {
        "file_path": "dharma_swarm/orchestrate_live.py",
        "observation": "STRANGE LOOP: 5 loops (was 8). swarm.tick() not _orchestrator.tick(). Signal bus wired. daemon.pid not orchestrator.pid.",
        "salience": 0.95,
        "action": "connect",
        "connections": ["dharma_swarm/swarm.py", "dharma_swarm/signal_bus.py"],
    },
    # Phase 1: Amplification Loop
    {
        "file_path": "dharma_swarm/context.py",
        "observation": "STRANGE LOOP: L7 WINNERS + L8 STIGMERGY PULL. Agents see what worked before + colony signals. Closes Quality->Production feedback loop.",
        "salience": 0.92,
        "action": "connect",
        "connections": ["dharma_swarm/archive.py", "dharma_swarm/stigmergy.py"],
    },
    {
        "file_path": "dharma_swarm/archive.py",
        "observation": "STRANGE LOOP: get_best_approaches() = PULL interface. compact() = forgetting law. Winners feed context.py L7.",
        "salience": 0.90,
        "action": "connect",
        "connections": ["dharma_swarm/context.py", "dharma_swarm/fitness_predictor.py"],
    },
    {
        "file_path": "dharma_swarm/stigmergy.py",
        "observation": "STRANGE LOOP: query_relevant() = PULL protocol. access_count tracks reads. access_decay() = unused marks fade faster. Feeds context.py L8.",
        "salience": 0.90,
        "action": "connect",
        "connections": ["dharma_swarm/context.py", "dharma_swarm/sleep_cycle.py"],
    },
    # Phase 2: Shared Downbeat
    {
        "file_path": "dharma_swarm/signal_bus.py",
        "observation": "STRANGE LOOP CORE: The shared downbeat. In-process event bus for inter-loop temporal coherence. emit/drain/peek. TTL-based expiry.",
        "salience": 0.98,
        "action": "connect",
        "connections": ["dharma_swarm/orchestrate_live.py", "dharma_swarm/engine/events.py"],
    },
    {
        "file_path": "dharma_swarm/engine/events.py",
        "observation": "STRANGE LOOP: 6 new EventTypes -- FITNESS_IMPROVED, FITNESS_DEGRADED, ANOMALY_DETECTED, CASCADE_EIGENFORM_DISTANCE, GATE_REJECTION_SPIKE.",
        "salience": 0.85,
        "action": "connect",
        "connections": ["dharma_swarm/signal_bus.py"],
    },
    # Phase 3: Honest Gates
    {
        "file_path": "dharma_swarm/telos_gates.py",
        "observation": "STRANGE LOOP: DOGMA_DRIFT calls check_dogma_drift(). STEELMAN calls check_steelman(). _is_reflection_sufficient() needs substance. No rubber stamps.",
        "salience": 0.93,
        "action": "connect",
        "connections": ["dharma_swarm/dogma_gate.py", "dharma_swarm/steelman_gate.py", "dharma_swarm/evolution.py"],
    },
    {
        "file_path": "dharma_swarm/monitor.py",
        "observation": "STRANGE LOOP: _is_failure() now catches rejected/blocked/rolled_back states. Gate rejections count in health metrics.",
        "salience": 0.82,
        "action": "connect",
        "connections": ["dharma_swarm/telos_gates.py"],
    },
    # Phase 4: Substrate Curdling
    {
        "file_path": "dharma_swarm/fitness_predictor.py",
        "observation": "STRANGE LOOP: record_rejection() + rejection penalty in predict(). Groups with >30% rejection rate get penalized. The medium curdles.",
        "salience": 0.88,
        "action": "connect",
        "connections": ["dharma_swarm/evolution.py", "dharma_swarm/archive.py"],
    },
    {
        "file_path": "dharma_swarm/evolution.py",
        "observation": "STRANGE LOOP: _build_propose_system() injects top-3 rejection patterns. gate_check() records rejections to fitness_predictor.",
        "salience": 0.91,
        "action": "connect",
        "connections": ["dharma_swarm/fitness_predictor.py", "dharma_swarm/telos_gates.py", "dharma_swarm/archive.py"],
    },
    # Phase 5: Forgetting Law
    {
        "file_path": "dharma_swarm/sleep_cycle.py",
        "observation": "STRANGE LOOP: LIGHT phase runs access_decay(). DEEP phase runs archive.compact(). Nirjara: karma sheds because binding force is removed.",
        "salience": 0.87,
        "action": "connect",
        "connections": ["dharma_swarm/stigmergy.py", "dharma_swarm/archive.py"],
    },
    # Tests
    {
        "file_path": "tests/test_signal_bus.py",
        "observation": "STRANGE LOOP: 8 tests for signal bus -- emit/drain, type filtering, TTL expiry, peek, pending count.",
        "salience": 0.75,
        "action": "scan",
        "connections": ["dharma_swarm/signal_bus.py"],
    },
    {
        "file_path": "tests/test_strange_loop.py",
        "observation": "STRANGE LOOP: 35 tests across all 6 phases. Catalytic closure verified. Every module feeds and is fed.",
        "salience": 0.80,
        "action": "scan",
        "connections": ["dharma_swarm/signal_bus.py", "dharma_swarm/archive.py", "dharma_swarm/stigmergy.py"],
    },
    # The vision document
    {
        "file_path": "dharma_swarm/signal_bus.py",
        "observation": "THE TORUS: Two loops -- trophic (produce->consume->decompose->recycle) and immune (act->gate->reject->compress->identity->modulate). F(torus) = torus.",
        "salience": 0.99,
        "action": "dream",
        "connections": [
            "dharma_swarm/swarm.py", "dharma_swarm/orchestrate_live.py",
            "dharma_swarm/context.py", "dharma_swarm/archive.py",
            "dharma_swarm/stigmergy.py", "dharma_swarm/telos_gates.py",
            "dharma_swarm/evolution.py", "dharma_swarm/fitness_predictor.py",
            "dharma_swarm/monitor.py", "dharma_swarm/sleep_cycle.py",
        ],
    },
]


async def main():
    store = StigmergyStore()
    count = 0
    for m in MARKS:
        mark = StigmergicMark(
            agent="strange_loop_seed",
            file_path=m["file_path"],
            action=m.get("action", "connect"),
            observation=m["observation"],
            salience=m["salience"],
            connections=m.get("connections", []),
        )
        await store.leave_mark(mark)
        count += 1
        print(f"  [{m['salience']:.2f}] {m['file_path'][:50]}")
    print(f"\n{count} Strange Loop stigmergy marks seeded.")


if __name__ == "__main__":
    asyncio.run(main())
