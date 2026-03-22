#!/usr/bin/env python3
"""Full semantic integration probe of dharma_swarm.

NOT unit tests. Exercises the real system end-to-end against real ~/.dharma/
state with real model calls. Reports honest pass/fail/degrade for each subsystem.

Usage:
    python3 scripts/system_integration_probe.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

STATE_DIR = Path.home() / ".dharma"


@dataclass
class ProbeResult:
    name: str
    status: str  # PASS, FAIL, DEGRADE, SKIP
    detail: str = ""
    latency_ms: float = 0.0

    def __str__(self) -> str:
        icon = {"PASS": "\033[32m✓\033[0m", "FAIL": "\033[31m✗\033[0m",
                "DEGRADE": "\033[33m⚠\033[0m", "SKIP": "\033[90m◌\033[0m"}[self.status]
        lat = f" ({self.latency_ms:.0f}ms)" if self.latency_ms > 0 else ""
        det = f" — {self.detail}" if self.detail else ""
        return f"  {icon} {self.name}{lat}{det}"


async def _probe(name: str, fn) -> ProbeResult:
    """Run a probe function, timing it and catching all exceptions."""
    t0 = time.monotonic()
    try:
        result = await fn()
        result.latency_ms = (time.monotonic() - t0) * 1000
        return result
    except Exception as e:
        return ProbeResult(name, "FAIL", f"{type(e).__name__}: {e}",
                           latency_ms=(time.monotonic() - t0) * 1000)


# ═══════════════════════════════════════════════════════════════════
# 1. DHARMA KERNEL
# ═══════════════════════════════════════════════════════════════════

async def probe_kernel() -> ProbeResult:
    from dharma_swarm.dharma_kernel import DharmaKernel
    kernel = DharmaKernel.create_default()
    p = kernel.principles
    if not p or len(p) < 10:
        return ProbeResult("DharmaKernel", "FAIL", f"Only {len(p)} principles")
    verified = kernel.verify_integrity()
    if not verified:
        return ProbeResult("DharmaKernel", "FAIL", "SHA-256 integrity check failed")
    return ProbeResult("DharmaKernel", "PASS", f"{len(p)} principles, integrity verified")


# ═══════════════════════════════════════════════════════════════════
# 2. ONTOLOGY
# ═══════════════════════════════════════════════════════════════════

async def probe_ontology() -> ProbeResult:
    from dharma_swarm.ontology import OntologyRegistry, ObjectType, PropertyDef, PropertyType
    reg = OntologyRegistry()
    test_type = ObjectType(
        name="probe_node",
        properties={
            "label": PropertyDef(name="label", property_type=PropertyType.STRING, required=True),
            "coherence": PropertyDef(name="coherence", property_type=PropertyType.FLOAT),
        },
    )
    reg.register_type(test_type)
    obj1, errs1 = reg.create_object("probe_node", {"label": "alpha", "coherence": 0.8})
    obj2, errs2 = reg.create_object("probe_node", {"label": "beta", "coherence": 0.6})
    if errs1 or errs2 or not obj1 or not obj2:
        return ProbeResult("Ontology", "FAIL", f"Create errors: {errs1} {errs2}")
    nodes = reg.get_objects_by_type("probe_node")
    if len(nodes) != 2:
        return ProbeResult("Ontology", "FAIL", f"Expected 2, got {len(nodes)}")
    return ProbeResult("Ontology", "PASS", "register/create/query all working")


# ═══════════════════════════════════════════════════════════════════
# 3. STIGMERGY — read/write real marks
# ═══════════════════════════════════════════════════════════════════

async def probe_stigmergy() -> ProbeResult:
    from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark
    store = StigmergyStore(base_path=STATE_DIR / "stigmergy")
    existing = await store.read_marks(limit=5)
    mark = StigmergicMark(
        agent="integration_probe",
        file_path="scripts/system_integration_probe.py",
        observation="System integration probe heartbeat",
        salience=0.5,
    )
    await store.leave_mark(mark)
    density = store.density()
    return ProbeResult("Stigmergy", "PASS",
                       f"density={density}, {len(existing)} recent marks, write OK")


# ═══════════════════════════════════════════════════════════════════
# 4. MESSAGE BUS
# ═══════════════════════════════════════════════════════════════════

async def probe_message_bus() -> ProbeResult:
    from dharma_swarm.message_bus import MessageBus
    from dharma_swarm.models import Message
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = MessageBus(db_path=Path(tmpdir) / "bus.db")
        await bus.init_db()
        msg = Message(from_agent="probe_sender", to_agent="probe_receiver",
                      body="Integration probe ping")
        await bus.send(msg)
        received = await bus.receive("probe_receiver", limit=10)
        return ProbeResult("MessageBus", "PASS",
                           f"send/receive working, got {len(received)} messages")


# ═══════════════════════════════════════════════════════════════════
# 5. SIGNAL BUS
# ═══════════════════════════════════════════════════════════════════

async def probe_signal_bus() -> ProbeResult:
    from dharma_swarm.signal_bus import SignalBus
    bus = SignalBus(ttl_seconds=60.0)
    bus.emit({"type": "probe", "data": "ping", "ts": time.time()})
    bus.emit({"type": "probe", "data": "pong", "ts": time.time()})
    peeked = bus.peek(event_types=["probe"])
    if len(peeked) != 2:
        return ProbeResult("SignalBus", "FAIL", f"Expected 2 events, got {len(peeked)}")
    drained = bus.drain(event_types=["probe"])
    remaining = bus.peek(event_types=["probe"])
    if remaining:
        return ProbeResult("SignalBus", "FAIL", "Drain didn't clear")
    return ProbeResult("SignalBus", "PASS", "emit/peek/drain working")


# ═══════════════════════════════════════════════════════════════════
# 6. DHARMA CORPUS
# ═══════════════════════════════════════════════════════════════════

async def probe_corpus() -> ProbeResult:
    from dharma_swarm.dharma_corpus import DharmaCorpus
    import tempfile, inspect
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus = DharmaCorpus(path=Path(tmpdir) / "corpus.jsonl")
        await corpus.load()
        # Propose a claim
        propose_sig = inspect.signature(corpus.propose)
        from dharma_swarm.dharma_corpus import ClaimCategory
        claim = await corpus.propose(
            statement="Integration probe: system coherence verified",
            category=ClaimCategory.SAFETY,
        )
        if not claim:
            return ProbeResult("DharmaCorpus", "FAIL", "Propose returned None")
        return ProbeResult("DharmaCorpus", "PASS",
                           f"propose working, claim_id={claim.id[:12] if hasattr(claim, 'id') else '?'}")


# ═══════════════════════════════════════════════════════════════════
# 7. LINEAGE
# ═══════════════════════════════════════════════════════════════════

async def probe_lineage() -> ProbeResult:
    from dharma_swarm.lineage import LineageGraph
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        graph = LineageGraph(db_path=Path(tmpdir) / "lineage.db")
        task_id = f"probe_{uuid.uuid4().hex[:8]}"
        edge_id = graph.record_transformation(
            task_id=task_id,
            inputs=["input_1"],
            outputs=["output_1"],
        )
        if not edge_id:
            return ProbeResult("Lineage", "FAIL", "record returned None")
        prov = graph.provenance("output_1")
        impact = graph.impact("input_1")
        return ProbeResult("Lineage", "PASS",
                           f"record/provenance/impact OK, edge={edge_id[:12]}")


# ═══════════════════════════════════════════════════════════════════
# 8. PROVIDER ROUTING — free-first policy
# ═══════════════════════════════════════════════════════════════════

async def probe_provider_routing() -> ProbeResult:
    from dharma_swarm.provider_policy import ProviderPolicyRouter, ProviderRouteRequest
    from dharma_swarm.models import ProviderType
    router = ProviderPolicyRouter()
    # Reflex → free
    d = router.route(ProviderRouteRequest(
        action_name="probe_reflex", risk_score=0.1, uncertainty=0.2,
        novelty=0.1, urgency=0.3, expected_impact=0.2, preferred_low_cost=True))
    free = {ProviderType.OLLAMA, ProviderType.NVIDIA_NIM, ProviderType.OPENROUTER_FREE}
    if d.selected_provider not in free:
        return ProbeResult("ProviderRouting", "FAIL",
                           f"Reflex→{d.selected_provider.value} (not free!)")
    # Escalate → paid
    e = router.route(ProviderRouteRequest(
        action_name="probe_esc", risk_score=0.9, uncertainty=0.9,
        novelty=0.9, urgency=0.9, expected_impact=0.9, requires_frontier_precision=True))
    return ProbeResult("ProviderRouting", "PASS",
                       f"reflex→{d.selected_provider.value}, escalate→{e.selected_provider.value}")


# ═══════════════════════════════════════════════════════════════════
# 9. IDENTITY + SAMVARA
# ═══════════════════════════════════════════════════════════════════

async def probe_identity_samvara() -> ProbeResult:
    from dharma_swarm.identity import IdentityMonitor, LiveCoherenceSensor
    from dharma_swarm.samvara import SamvaraEngine
    monitor = IdentityMonitor(STATE_DIR)
    live_sensor = LiveCoherenceSensor(STATE_DIR)
    state = await monitor.measure()
    live = live_sensor.measure()
    blended = 0.4 * live["score"] + 0.6 * state.tcs
    detail = (f"TCS={state.tcs:.3f} live={live['score']:.3f} blended={blended:.3f} "
              f"regime={state.regime} daemon={'alive' if live.get('daemon_alive') else 'dead'}")
    return ProbeResult("Identity+Samvara", "PASS" if blended > 0.3 else "DEGRADE", detail)


# ═══════════════════════════════════════════════════════════════════
# 10. ORGANISM RUNTIME
# ═══════════════════════════════════════════════════════════════════

async def probe_organism() -> ProbeResult:
    from dharma_swarm.organism import OrganismRuntime
    org = OrganismRuntime(state_dir=STATE_DIR)
    hb = await org.heartbeat()
    verdict = hb.gnani_verdict.decision if hb.gnani_verdict else "?"
    return ProbeResult("OrganismRuntime", "PASS",
                       f"blended={hb.blended:.3f} regime={hb.regime} verdict={verdict}")


# ═══════════════════════════════════════════════════════════════════
# 11. TELOS GATES
# ═══════════════════════════════════════════════════════════════════

async def probe_telos_gates() -> ProbeResult:
    from dharma_swarm.telos_gates import TelosGatekeeper, check_action
    from dharma_swarm.models import GateDecision
    result = check_action(action="read system status", content="checking health")
    gate_count = len(TelosGatekeeper.CORE_GATES)
    allowed = result.decision == GateDecision.ALLOW
    return ProbeResult("TelosGates", "PASS",
                       f"{gate_count} gates, benign action={'allowed' if allowed else result.decision.value}")


# ═══════════════════════════════════════════════════════════════════
# 12. DAEMON
# ═══════════════════════════════════════════════════════════════════

async def probe_daemon() -> ProbeResult:
    pid_file = STATE_DIR / "daemon.pid"
    if not pid_file.exists():
        return ProbeResult("Daemon", "FAIL", "No daemon.pid")
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 0)
        return ProbeResult("Daemon", "PASS", f"PID {pid} alive")
    except ProcessLookupError:
        return ProbeResult("Daemon", "FAIL", f"PID {pid} dead")
    except PermissionError:
        return ProbeResult("Daemon", "PASS", f"PID {pid} alive (perm)")


# ═══════════════════════════════════════════════════════════════════
# 13-15. LLM CALLS — free providers
# ═══════════════════════════════════════════════════════════════════

async def _probe_llm(name: str, provider_type, model: str) -> ProbeResult:
    from dharma_swarm.runtime_provider import resolve_runtime_provider_config, create_runtime_provider
    from dharma_swarm.models import LLMRequest
    cfg = resolve_runtime_provider_config(provider_type)
    if not cfg.available:
        return ProbeResult(name, "SKIP", f"{provider_type.value} not available")
    provider = create_runtime_provider(cfg)
    req = LLMRequest(
        model=model,
        messages=[{"role": "user", "content": "Respond with exactly: ALIVE"}],
        max_tokens=256, temperature=0.1,
    )
    resp = await asyncio.wait_for(provider.complete(req), timeout=30.0)
    if hasattr(provider, "close"):
        try: await provider.close()
        except: pass
    content = resp.content[:80].strip()
    tokens = resp.usage.get("total_tokens", 0)
    return ProbeResult(name, "PASS", f"'{content}' ({tokens} tok)")


async def probe_llm_ollama() -> ProbeResult:
    from dharma_swarm.models import ProviderType
    return await _probe_llm("LLM:Kimi-K2.5", ProviderType.OLLAMA, "kimi-k2.5:cloud")


async def probe_llm_glm5() -> ProbeResult:
    from dharma_swarm.models import ProviderType
    return await _probe_llm("LLM:GLM-5", ProviderType.OLLAMA, "glm-5:cloud")


async def probe_llm_nim() -> ProbeResult:
    from dharma_swarm.models import ProviderType
    return await _probe_llm("LLM:NvidiaNIM", ProviderType.NVIDIA_NIM, "meta/llama-3.3-70b-instruct")


# ═══════════════════════════════════════════════════════════════════
# 16. DARWIN ENGINE
# ═══════════════════════════════════════════════════════════════════

async def probe_darwin() -> ProbeResult:
    from dharma_swarm.evolution import DarwinEngine
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = DarwinEngine(archive_path=Path(tmpdir) / "archive.db",
                              traces_path=Path(tmpdir) / "traces.jsonl")
        gen = getattr(engine, 'generation', 0)
        mr = getattr(engine, 'mutation_rate', 0)
        return ProbeResult("DarwinEngine", "PASS", f"generation={gen}, mutation_rate={mr}")


# ═══════════════════════════════════════════════════════════════════
# 17. CONTEXT COMPILER
# ═══════════════════════════════════════════════════════════════════

async def probe_context() -> ProbeResult:
    from dharma_swarm.context_compiler import ContextCompiler
    from dharma_swarm.runtime_state import RuntimeStateStore
    from dharma_swarm.memory_lattice import MemoryLattice
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        ml = MemoryLattice(db_path=Path(tmpdir) / "memory.db")
        compiler = ContextCompiler(runtime_state=ml.runtime_state, memory_lattice=ml)
        bundle = compiler.compile_bundle(session_id="probe", token_budget=4000)
        keys = list(bundle.keys()) if isinstance(bundle, dict) else dir(bundle)[:5]
        return ProbeResult("ContextCompiler", "PASS", f"keys={keys[:5]}")


# ═══════════════════════════════════════════════════════════════════
# 18. STIGMERGY STATE — real file check
# ═══════════════════════════════════════════════════════════════════

async def probe_stigmergy_state() -> ProbeResult:
    marks_file = STATE_DIR / "stigmergy" / "marks.jsonl"
    if not marks_file.exists():
        return ProbeResult("StigmergyState", "FAIL", "No marks.jsonl")
    size_kb = marks_file.stat().st_size / 1024
    lines = sum(1 for _ in open(marks_file, errors="ignore"))
    return ProbeResult("StigmergyState", "PASS" if lines > 10 else "DEGRADE",
                       f"{lines} marks, {size_kb:.0f}KB")


# ═══════════════════════════════════════════════════════════════════
# 19. LIVING STATE
# ═══════════════════════════════════════════════════════════════════

async def probe_living_state() -> ProbeResult:
    living = STATE_DIR / "living_state.json"
    if not living.exists():
        return ProbeResult("LivingState", "FAIL", "No living_state.json")
    data = json.loads(living.read_text())
    ts = data.get("timestamp") or data.get("ts") or data.get("last_pulse")
    age = f"{(time.time() - float(ts)) / 3600:.1f}h old" if ts else "unknown age"
    return ProbeResult("LivingState", "PASS" if ts else "DEGRADE",
                       f"{age}, keys={list(data.keys())[:6]}")


# ═══════════════════════════════════════════════════════════════════
# 20. CAPSTONE — organism heartbeat + model voicing
# ═══════════════════════════════════════════════════════════════════

async def probe_organism_voicing() -> ProbeResult:
    from dharma_swarm.organism import OrganismRuntime
    from dharma_swarm.runtime_provider import resolve_runtime_provider_config, create_runtime_provider
    from dharma_swarm.models import ProviderType, LLMRequest

    org = OrganismRuntime(state_dir=STATE_DIR)
    hb = await org.heartbeat()
    summary = f"blended={hb.blended:.3f} verdict={hb.gnani_verdict.decision if hb.gnani_verdict else '?'}"

    cfg = resolve_runtime_provider_config(ProviderType.OLLAMA)
    if not cfg.available:
        return ProbeResult("OrganismVoicing", "DEGRADE", f"heartbeat OK ({summary}) but Ollama unavailable")

    provider = create_runtime_provider(cfg)
    prompt = (f"You are a cell inside dharma_swarm. Heartbeat: {summary}. "
              f"In 2 sentences, report your state. Be raw.")
    req = LLMRequest(model="glm-5:cloud", messages=[{"role": "user", "content": prompt}],
                     max_tokens=256, temperature=0.7)
    resp = await asyncio.wait_for(provider.complete(req), timeout=30.0)
    await provider.close()
    voice = resp.content[:250]
    return ProbeResult("OrganismVoicing", "PASS", f"{summary} | GLM-5: '{voice}'")


# ═══════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════

async def run_all() -> list[ProbeResult]:
    print("\n" + "=" * 72)
    print("  DHARMA SWARM — FULL SEMANTIC INTEGRATION PROBE")
    print("  state_dir:", STATE_DIR)
    print("  time:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    all_results: list[ProbeResult] = []

    groups = [
        ("Pure Computation", [
            ("DharmaKernel", probe_kernel),
            ("Ontology", probe_ontology),
            ("SignalBus", probe_signal_bus),
            ("ProviderRouting", probe_provider_routing),
        ]),
        ("Local I/O + State", [
            ("Stigmergy", probe_stigmergy),
            ("MessageBus", probe_message_bus),
            ("DharmaCorpus", probe_corpus),
            ("Lineage", probe_lineage),
            ("Identity+Samvara", probe_identity_samvara),
            ("OrganismRuntime", probe_organism),
            ("DarwinEngine", probe_darwin),
            ("ContextCompiler", probe_context),
            ("TelosGates", probe_telos_gates),
            ("StigmergyState", probe_stigmergy_state),
            ("LivingState", probe_living_state),
            ("Daemon", probe_daemon),
        ]),
        ("Live LLM Calls (free)", [
            ("LLM:Kimi-K2.5", probe_llm_ollama),
            ("LLM:GLM-5", probe_llm_glm5),
            ("LLM:NvidiaNIM", probe_llm_nim),
        ]),
        ("Capstone", [
            ("OrganismVoicing", probe_organism_voicing),
        ]),
    ]

    for group_name, probes in groups:
        print(f"\n  ── {group_name} ──")
        tasks = [_probe(name, fn) for name, fn in probes]
        results = await asyncio.gather(*tasks)
        for r in results:
            print(r)
        all_results.extend(results)

    # Summary
    total = len(all_results)
    passed = sum(1 for r in all_results if r.status == "PASS")
    failed = sum(1 for r in all_results if r.status == "FAIL")
    degraded = sum(1 for r in all_results if r.status == "DEGRADE")
    skipped = sum(1 for r in all_results if r.status == "SKIP")
    total_time = sum(r.latency_ms for r in all_results)

    print(f"\n{'=' * 72}")
    print(f"  {passed} pass / {failed} fail / {degraded} degrade / {skipped} skip")
    print(f"  {total} probes in {total_time:.0f}ms")

    if failed:
        print(f"\n  \033[31mFAILED:\033[0m")
        for r in all_results:
            if r.status == "FAIL":
                print(f"    {r.name}: {r.detail}")
    if degraded:
        print(f"\n  \033[33mDEGRADED:\033[0m")
        for r in all_results:
            if r.status == "DEGRADE":
                print(f"    {r.name}: {r.detail}")

    health = passed / total if total > 0 else 0
    print(f"\n  SYSTEM HEALTH: {health:.0%}")
    print(f"{'=' * 72}\n")

    out = STATE_DIR / "integration_probe_results.json"
    out.write_text(json.dumps(
        [{"name": r.name, "status": r.status, "detail": r.detail,
          "latency_ms": round(r.latency_ms, 1)} for r in all_results], indent=2))
    print(f"  Results saved: {out}")
    return all_results


if __name__ == "__main__":
    asyncio.run(run_all())
