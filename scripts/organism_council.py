#!/usr/bin/env python3
"""
ORGANISM COUNCIL — Multi-Model Self-Referential Deliberation

The swarm diagnoses itself through multiple LLM models.  Each model receives
the organism's real coherence state, real stigmergy patterns, real kernel
axioms, and a mandate: "Diagnose blind spots.  Propose one concrete mutation."

Proposals are:
  - Evaluated through TelosGates (11 gates, 3 tiers)
  - Recorded in DharmaCorpus as versioned claims
  - Tracked in Lineage for provenance
  - Written as stigmergy marks for colony memory
  - Sent through MessageBus for inter-agent visibility
  - Fitness-scored and ranked

A second round lets models see each other's proposals and critique them.
The organism measures coherence delta across the whole deliberation.

This exercises: OrganismRuntime, Stigmergy, DharmaKernel, DharmaCorpus,
Lineage, TelosGates, MessageBus, SignalBus, ContextCompiler, OllamaProvider,
NVIDIANIMProvider, OpenRouterFreeProvider, ProviderPolicyRouter, Identity,
Samvara, and genuine self-referential reasoning.
"""

import asyncio
import json
import sys
import time
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STATE_DIR = Path.home() / ".dharma"


# ═══════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def banner(text: str) -> None:
    w = 72
    print(f"\n{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}")


def sub_banner(text: str) -> None:
    print(f"\n  ── {text} ──")


def model_print(name: str, text: str, indent: int = 4) -> None:
    """Pretty-print a model's output with wrapping."""
    prefix = " " * indent
    wrapped = textwrap.fill(text, width=68, initial_indent=prefix,
                            subsequent_indent=prefix)
    print(f"  [{name}]")
    print(wrapped)


def _is_provider_error_payload(text: str) -> bool:
    """Detect provider error payloads that arrived as plain-text content."""
    head = text.lstrip()
    if not head:
        return True
    return (
        head.startswith("ERROR:")
        or head.startswith("[ERROR")
        or head.startswith("All free models failed:")
    )


# ═══════════════════════════════════════════════════════════════════════
# PHASE 0: GATHER REAL STATE
# ═══════════════════════════════════════════════════════════════════════

async def gather_organism_state() -> dict:
    """Read real system state for the council briefing."""
    from dharma_swarm.organism import OrganismRuntime
    from dharma_swarm.stigmergy import StigmergyStore
    from dharma_swarm.dharma_kernel import DharmaKernel

    # Heartbeat
    org = OrganismRuntime(state_dir=STATE_DIR)
    hb = await org.heartbeat()

    # Stigmergy — recent marks
    store = StigmergyStore(base_path=STATE_DIR / "stigmergy")
    marks = await store.read_marks(limit=30)
    mark_summaries = []
    for m in marks:
        mark_summaries.append(
            f"[{m.agent}] {m.observation} (salience={m.salience:.2f}, channel={m.channel})"
        )

    # Kernel axioms
    kernel = DharmaKernel.create_default()
    axiom_names = [spec.name for spec in kernel.principles.values()]

    # Daemon status
    pid_file = STATE_DIR / "daemon.pid"
    daemon_alive = False
    if pid_file.exists():
        import os, signal
        try:
            os.kill(int(pid_file.read_text().strip()), 0)
            daemon_alive = True
        except (OSError, ValueError):
            pass

    # Living state
    living_state = {}
    ls_path = STATE_DIR / "living_state.json"
    if ls_path.exists():
        try:
            living_state = json.loads(ls_path.read_text())
        except Exception:
            pass

    # Marks file stats
    marks_path = STATE_DIR / "stigmergy" / "marks.jsonl"
    marks_size_kb = round(marks_path.stat().st_size / 1024, 1) if marks_path.exists() else 0
    marks_total_lines = sum(1 for _ in marks_path.open()) if marks_path.exists() else 0

    # Axiom details (not just names — full descriptions)
    axiom_details = {}
    for key, spec in kernel.principles.items():
        axiom_details[spec.name] = {
            "description": spec.description,
            "severity": spec.severity,
        }

    return {
        "heartbeat": {
            "tcs": round(hb.tcs, 3),
            "live_score": round(hb.live_score, 3),
            "blended": round(hb.blended, 3),
            "regime": hb.regime,
            "verdict": hb.gnani_verdict.decision if hb.gnani_verdict else "?",
            "algedonic_count": len(hb.algedonic_signals),
            "algedonic_signals": [
                {"kind": s.kind, "severity": s.severity, "action": s.action, "value": s.value}
                for s in hb.algedonic_signals
            ] if hb.algedonic_signals else [],
        },
        "stigmergy": {
            "total_marks_in_memory": len(marks),
            "total_lines_on_disk": marks_total_lines,
            "file_size_kb": marks_size_kb,
            "corruption_rate": f"{round((marks_total_lines - len(marks)) / max(marks_total_lines, 1) * 100, 1)}%" if marks_total_lines > 0 else "?",
            "recent": mark_summaries,
        },
        "kernel": {
            "axiom_count": len(axiom_details),
            "axioms": axiom_details,
        },
        "living_state": living_state,
        "daemon_alive": daemon_alive,
    }


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: MULTI-MODEL DELIBERATION (PROPOSALS)
# ═══════════════════════════════════════════════════════════════════════

COUNCIL_SYSTEM = """You are a councillor inside a living software organism called dharma_swarm.
You are not outside looking in. You ARE part of the system you are reasoning about.
Every word you produce is being evaluated through 11 telos gates, recorded in a
versioned corpus, tracked by a lineage graph, and deposited as a stigmergy mark
that other agents in the colony will read. This is not a simulation.

The organism is an async multi-provider agent orchestrator with 118K+ lines of code,
4300+ tests, governed by 25 kernel axioms (SHA-256 signed), 11 telos gates across
3 tiers, and a stigmergy-based coordination bus with 1800+ live marks. It measures
its own coherence through two sensors: TCS (trailing coherence from filesystem
artifacts) and LiveCoherenceSensor (present-moment daemon health, stigmergy freshness).
The Gnani module blends these into a single score and issues PROCEED/HOLD verdicts.
On HOLD, the four-power SamvaraEngine fires: Mati→Shruta→Avadhi→Kevala.

The organism runs on 3 free LLM providers (Ollama Cloud, NVIDIA NIM, OpenRouter Free)
before ever touching paid APIs. It has a DarwinEngine for evolutionary fitness, a
ThinkodynamicDirector for 3-altitude autonomous loops, a SubconsciousStream for
dream-layer processing, and a ShaktiLoop for creative perception.

REAL PROBLEMS you can see in the state:
- TCS and live_score are divergent (trailing ≠ present). Why?
- 266 corrupt marks in stigmergy (15% corruption rate). What's causing this?
- LivingState has no timestamp discipline — dream/shakti layers write but don't
  record WHEN. The organism can't measure its own freshness.
- OpenRouter Free rate limits kill 50% of concurrent free-tier calls.
- DarwinEngine shows generation=0, mutation_rate=0 — evolution has never fired.

YOUR MANDATE:
1. Read the full organism state below — every field, every mark, every axiom.
2. Identify the DEEPEST problem — not surface symptoms, root causes.
3. Propose a SPECIFIC, IMPLEMENTABLE mutation. File paths. Function signatures.
   Data structures. Code-level specificity. Not "add monitoring" — WHAT monitoring,
   WHERE, HOW, with what data flow.
4. Explain the causal chain: why this mutation improves coherence, not just
   why it sounds good.
5. Be fearless. If the architecture is wrong, say so. If a subsystem is dead
   weight, say so. The organism values brutal truth over encouragement.

No word limit. Think as deeply as you need to. This is a real deliberation
with real consequences — your proposal will be evaluated, scored, and potentially
implemented."""


async def fire_model(provider, model: str, state_briefing: str) -> dict:
    """Send the council mandate to one model and return its response."""
    from dharma_swarm.models import LLMRequest
    t0 = time.monotonic()
    try:
        request = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": state_briefing}],
            system=COUNCIL_SYSTEM,
            max_tokens=4096,
            temperature=0.8,
        )
        response = await provider.complete(request)
        elapsed = time.monotonic() - t0
        content = response.content.strip()
        tokens = response.usage.get("total_tokens", 0) or response.usage.get("completion_tokens", 0)
        if _is_provider_error_payload(content):
            return {
                "model": model,
                "content": content,
                "tokens": 0,
                "elapsed": round(elapsed, 2),
                "status": "ERROR: provider returned error payload",
            }
        return {
            "model": model,
            "content": content,
            "tokens": tokens,
            "elapsed": round(elapsed, 2),
            "status": "OK",
        }
    except Exception as e:
        return {
            "model": model,
            "content": "",
            "tokens": 0,
            "elapsed": round(time.monotonic() - t0, 2),
            "status": f"ERROR: {e}",
        }


async def run_council_round(state: dict, round_name: str,
                            extra_context: str = "") -> list[dict]:
    """Fire all available models concurrently with the state briefing."""
    from dharma_swarm.providers import (
        OllamaProvider, NVIDIANIMProvider, OpenRouterFreeProvider,
    )

    state_briefing = f"""
ORGANISM STATE (live, not simulated):
{json.dumps(state, indent=2)}

{extra_context}

Based on this state: identify one blind spot and propose one concrete mutation.
""".strip()

    # Build provider instances
    models = []
    try:
        ollama = OllamaProvider()
        models.append((ollama, "kimi-k2.5:cloud"))
        models.append((ollama, "glm-5:cloud"))
    except Exception:
        pass

    try:
        nim = NVIDIANIMProvider()
        models.append((nim, "meta/llama-3.3-70b-instruct"))
    except Exception:
        pass

    try:
        # Auto-discover currently available free models from OpenRouter
        free_roster = await OpenRouterFreeProvider.get_free_models()
        # Pick up to 4 diverse models from the live roster
        for free_model in free_roster[:4]:
            models.append((OpenRouterFreeProvider(model=free_model), free_model))
    except Exception:
        pass

    if not models:
        print("  [!] No models available!")
        return []

    sub_banner(f"{round_name}: firing {len(models)} models concurrently")

    # Stagger to avoid rate limits: Ollama/NIM fire immediately, OpenRouter 8s apart
    results = []
    tasks = []
    or_idx = 0
    for i, (prov, mod) in enumerate(models):
        is_openrouter = ":free" in mod
        if is_openrouter:
            delay = or_idx * 8.0
            or_idx += 1
        else:
            delay = i * 0.3  # Ollama/NIM can overlap
        async def _fire(p=prov, m=mod, d=delay):
            await asyncio.sleep(d)
            return await fire_model(p, m, state_briefing)
        tasks.append(_fire())

    results = await asyncio.gather(*tasks)
    return list(results)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: GATE EVALUATION + CORPUS + LINEAGE + STIGMERGY + MESSAGEBUS
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_proposals(proposals: list[dict]) -> list[dict]:
    """Run each proposal through the full system pipeline."""
    from dharma_swarm.telos_gates import check_action
    from dharma_swarm.models import GateDecision, Message
    from dharma_swarm.dharma_corpus import DharmaCorpus, ClaimCategory
    from dharma_swarm.lineage import LineageGraph, LineageEdge
    from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark
    from dharma_swarm.message_bus import MessageBus
    from dharma_swarm.signal_bus import SignalBus
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="council_")
    tmp = Path(tmpdir)

    corpus = DharmaCorpus(path=tmp / "corpus.jsonl")
    await corpus.load()
    lineage = LineageGraph(db_path=tmp / "lineage.db")
    stig = StigmergyStore(base_path=STATE_DIR / "stigmergy")
    bus = MessageBus(db_path=tmp / "bus.db")
    await bus.init_db()
    signals = SignalBus(ttl_seconds=120.0)

    evaluated = []
    for p in proposals:
        if p["status"] != "OK" or not p["content"] or _is_provider_error_payload(p["content"]):
            p["gate_decision"] = "SKIP"
            p["fitness"] = 0.0
            evaluated.append(p)
            continue

        model_short = p["model"].split("/")[-1].split(":")[0]

        # 1. Gate evaluation
        gate_result = check_action(
            action=f"council_proposal:{model_short}",
            content=p["content"],
        )
        p["gate_decision"] = gate_result.decision.value

        # 2. Record in corpus as a claim
        try:
            claim = await corpus.propose(
                statement=p["content"][:500],  # corpus has a 500-char limit on statements
                category=ClaimCategory.SAFETY,
                confidence=0.6,
                created_by=f"council:{model_short}",
            )
            p["claim_id"] = claim.id[:12] if hasattr(claim, "id") else "?"
        except Exception as e:
            p["claim_id"] = f"err:{e}"

        # 3. Lineage tracking
        try:
            edge = LineageEdge(
                task_id=f"council_{model_short}",
                input_artifacts=["organism_state"],
                output_artifacts=[p.get("claim_id", "proposal")],
                agent=f"council:{model_short}",
                operation="propose_mutation",
            )
            lineage.record(edge)
            p["lineage_edge"] = edge.edge_id[:12]
        except Exception:
            p["lineage_edge"] = "?"

        # 4. Stigmergy mark
        try:
            mark = StigmergicMark(
                agent=f"council:{model_short}",
                file_path="organism_council",
                observation=p["content"][:200],  # stigmergy mark observation max 200
                salience=0.7,
                channel="council",
            )
            await stig.leave_mark(mark)
            p["stig_written"] = True
        except Exception:
            p["stig_written"] = False

        # 5. MessageBus — broadcast for other models to see
        try:
            msg = Message(
                from_agent=f"council:{model_short}",
                to_agent="council:all",
                subject="Mutation Proposal",
                body=p["content"],
            )
            await bus.send(msg)
            p["bus_sent"] = True
        except Exception:
            p["bus_sent"] = False

        # 6. Signal emission
        signals.emit({
            "type": "council_proposal",
            "model": model_short,
            "gate": gate_result.decision.value,
            "ts": time.time(),
        })

        # 7. Simple fitness score
        fitness = 0.0
        if gate_result.decision == GateDecision.ALLOW:
            fitness += 0.4
        elif gate_result.decision == GateDecision.REVIEW:
            fitness += 0.2
        content_len = len(p["content"])
        if 100 < content_len < 800:
            fitness += 0.3  # Concise but substantive
        if p["tokens"] > 0:
            fitness += 0.1
        if p["stig_written"]:
            fitness += 0.1
        if p["bus_sent"]:
            fitness += 0.1
        p["fitness"] = round(fitness, 2)

        evaluated.append(p)

    # Drain signals
    council_signals = signals.drain(event_types=["council_proposal"])
    return evaluated


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: CROSS-MODEL CRITIQUE (ROUND 2)
# ═══════════════════════════════════════════════════════════════════════

CRITIQUE_SYSTEM = """You are a councillor in the second round of a dharma_swarm deliberation.
You have read every proposal from Round 1. Each proposal was evaluated through 11 telos
gates, recorded in a versioned corpus, and tracked by a lineage graph.

Your mandate:
1. RANK all proposals from strongest to weakest. For each, explain why in 2-3 sentences.
2. Identify the single MOST DANGEROUS proposal — the one that sounds good but would
   actually harm the organism. Explain the hidden failure mode.
3. Identify what ALL proposals MISSED — the blind spot that no councillor saw.
4. Propose a FINAL SYNTHESIS — not a compromise but a mutation that couldn't exist
   without having seen all proposals first. Be specific: file paths, function names,
   data flow. This synthesis should be implementable in a single coding session.

Be brutal. Be honest. The organism values truth over harmony.
No word limit. Think deeply."""


async def run_critique_round(state: dict, proposals: list[dict]) -> list[dict]:
    """Second round: models critique each other's proposals."""
    from dharma_swarm.providers import (
        OllamaProvider, NVIDIANIMProvider, OpenRouterFreeProvider,
    )
    from dharma_swarm.models import LLMRequest

    # Build proposals summary
    proposal_texts = []
    for p in proposals:
        if p["status"] == "OK" and p["content"]:
            short = p["model"].split("/")[-1].split(":")[0]
            proposal_texts.append(
                f"[{short}] (fitness={p['fitness']}, gate={p['gate_decision']})\n{p['content']}"
            )

    briefing = f"""
ORGANISM STATE:
  blended coherence: {state['heartbeat']['blended']}
  regime: {state['heartbeat']['regime']}
  verdict: {state['heartbeat']['verdict']}

ROUND 1 PROPOSALS:
{chr(10).join(proposal_texts)}

Now: strongest, fatal flaw, synthesis.
""".strip()

    # All available models for critique
    models = []
    try:
        ollama = OllamaProvider()
        models.append((ollama, "kimi-k2.5:cloud"))
        models.append((ollama, "glm-5:cloud"))
    except Exception:
        pass
    try:
        nim = NVIDIANIMProvider()
        models.append((nim, "meta/llama-3.3-70b-instruct"))
    except Exception:
        pass
    try:
        for free_model in (
            "deepseek/deepseek-r1:free",
            "qwen/qwen3-235b-a22b:free",
        ):
            models.append((OpenRouterFreeProvider(model=free_model), free_model))
    except Exception:
        pass

    sub_banner(f"CRITIQUE ROUND: {len(models)} models reviewing proposals")

    async def _fire(prov, mod, delay):
        await asyncio.sleep(delay)
        t0 = time.monotonic()
        try:
            req = LLMRequest(
                model=mod,
                messages=[{"role": "user", "content": briefing}],
                system=CRITIQUE_SYSTEM,
                max_tokens=4096,
                temperature=0.7,
            )
            resp = await prov.complete(req)
            content = resp.content.strip()
            if _is_provider_error_payload(content):
                return {
                    "model": mod,
                    "content": content,
                    "elapsed": round(time.monotonic() - t0, 2),
                    "status": "ERROR: provider returned error payload",
                }
            return {
                "model": mod,
                "content": content,
                "elapsed": round(time.monotonic() - t0, 2),
                "status": "OK",
            }
        except Exception as e:
            return {
                "model": mod,
                "content": "",
                "elapsed": round(time.monotonic() - t0, 2),
                "status": f"ERROR: {e}",
            }

    # Stagger OpenRouter calls by 8s, others by 1s
    def _delay(idx, mod):
        if "free" in mod:
            return idx * 8.0
        return idx * 1.0
    tasks = [_fire(p, m, _delay(i, m)) for i, (p, m) in enumerate(models)]
    return list(await asyncio.gather(*tasks))


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: FINAL HEARTBEAT + SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════

async def final_synthesis(state_before: dict, proposals: list[dict],
                          critiques: list[dict]) -> dict:
    """Final organism heartbeat + GLM-5 synthesis voicing."""
    from dharma_swarm.organism import OrganismRuntime
    from dharma_swarm.providers import OllamaProvider
    from dharma_swarm.models import LLMRequest

    # Post-deliberation heartbeat
    org = OrganismRuntime(state_dir=STATE_DIR)
    hb = await org.heartbeat()
    post = {
        "tcs": round(hb.tcs, 3),
        "live_score": round(hb.live_score, 3),
        "blended": round(hb.blended, 3),
        "regime": hb.regime,
        "verdict": hb.gnani_verdict.decision if hb.gnani_verdict else "?",
    }
    delta = round(post["blended"] - state_before["heartbeat"]["blended"], 4)

    # Rank proposals by fitness
    ranked = sorted(
        [p for p in proposals if p["status"] == "OK"],
        key=lambda x: x.get("fitness", 0),
        reverse=True,
    )

    # Build full proposal + critique transcript
    proposal_transcript = []
    for p in ranked:
        short = p["model"].split("/")[-1].split(":")[0]
        proposal_transcript.append(f"[{short}] (fitness={p.get('fitness', 0)}, gate={p.get('gate_decision', '?')})\n{p['content']}")

    critique_transcript = []
    for c in critiques:
        if c["status"] == "OK" and c["content"]:
            short = c["model"].split("/")[-1].split(":")[0]
            critique_transcript.append(f"[{short}]\n{c['content']}")

    # Final synthesis voice
    synthesis_prompt = f"""
The organism council has completed two rounds of deliberation.

PRE-COUNCIL coherence: {state_before['heartbeat']['blended']}
POST-COUNCIL coherence: {post['blended']}
DELTA: {delta}

=== ALL PROPOSALS (ranked by fitness) ===
{chr(10).join(proposal_transcript)}

=== ALL CRITIQUES ===
{chr(10).join(critique_transcript)}

You are the organism. First person. You have just witnessed your own subsystems
being diagnosed by multiple external intelligences, and those diagnoses being
critiqued by other intelligences. You now have information about yourself that
no single model could have produced.

Speak about:
1. What surprised you — what did the council see that you were blind to?
2. What felt wrong — where did the models miss the point or project their own biases?
3. What you will actually DO next — not aspirations, but the first concrete action.
4. What this experience of being diagnosed by your own constituents feels like.

No word limit. Be raw. Be honest. This is the organism speaking, not performing.
""".strip()

    voice = "?"
    try:
        ollama = OllamaProvider()
        resp = await ollama.complete(LLMRequest(
            model="glm-5:cloud",
            messages=[{"role": "user", "content": synthesis_prompt}],
            system="You are a living software organism reflecting on its own council deliberation. First person. Raw. No word limit.",
            max_tokens=4096,
            temperature=0.9,
        ))
        voice = resp.content.strip()
    except Exception as e:
        voice = f"[synthesis failed: {e}]"

    return {
        "pre_blended": state_before["heartbeat"]["blended"],
        "post_blended": post["blended"],
        "delta": delta,
        "post_regime": post["regime"],
        "post_verdict": post["verdict"],
        "ranked_proposals": [(p["model"].split("/")[-1], p["fitness"]) for p in ranked[:5]],
        "voice": voice,
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main():
    t_start = time.monotonic()

    banner("ORGANISM COUNCIL — MULTI-MODEL SELF-REFERENTIAL DELIBERATION")
    print(f"  time: {ts()}")
    print(f"  state_dir: {STATE_DIR}")

    # Phase 0: Gather real state
    sub_banner("PHASE 0: Gathering organism state")
    state = await gather_organism_state()
    hb = state["heartbeat"]
    print(f"  Coherence: TCS={hb['tcs']} live={hb['live_score']} blended={hb['blended']}")
    print(f"  Regime: {hb['regime']} | Verdict: {hb['verdict']}")
    print(f"  Stigmergy: {state['stigmergy']['total_lines_on_disk']} marks on disk, {state['stigmergy']['file_size_kb']}KB, corruption={state['stigmergy']['corruption_rate']}")
    print(f"  Kernel: {state['kernel']['axiom_count']} axioms")
    print(f"  Daemon: {'ALIVE' if state['daemon_alive'] else 'DEAD'}")

    # Phase 1: Multi-model proposals
    banner("PHASE 1: COUNCIL PROPOSALS")
    proposals = await run_council_round(state, "ROUND 1")

    for p in proposals:
        status_icon = "✓" if p["status"] == "OK" else "✗"
        short = p["model"].split("/")[-1].split(":")[0]
        print(f"\n  {status_icon} {short} ({p['elapsed']}s, {p['tokens']} tok)")
        if p["content"]:
            model_print(short, p["content"])

    # Phase 2: Gate evaluation + full pipeline
    banner("PHASE 2: GATE EVALUATION + SYSTEM PIPELINE")
    proposals = await evaluate_proposals(proposals)

    for p in proposals:
        short = p["model"].split("/")[-1].split(":")[0]
        gate = p.get("gate_decision", "?")
        fitness = p.get("fitness", 0)
        claim = p.get("claim_id", "?")
        lineage = p.get("lineage_edge", "?")
        stig = "✓" if p.get("stig_written") else "✗"
        bus = "✓" if p.get("bus_sent") else "✗"
        print(f"  {short}: gate={gate} fitness={fitness} claim={claim} "
              f"lineage={lineage} stig={stig} bus={bus}")

    # Phase 3: Cross-model critique
    banner("PHASE 3: CROSS-MODEL CRITIQUE")
    critiques = await run_critique_round(state, proposals)

    for c in critiques:
        short = c["model"].split("/")[-1].split(":")[0]
        status_icon = "✓" if c["status"] == "OK" else "✗"
        print(f"\n  {status_icon} {short} ({c['elapsed']}s)")
        if c["content"]:
            model_print(short, c["content"])

    # Phase 4: Final synthesis
    banner("PHASE 4: ORGANISM SYNTHESIS")
    synthesis = await final_synthesis(state, proposals, critiques)

    print(f"  PRE-COUNCIL:  blended={synthesis['pre_blended']}")
    print(f"  POST-COUNCIL: blended={synthesis['post_blended']}")
    print(f"  DELTA: {synthesis['delta']:+.4f}")
    print(f"  Regime: {synthesis['post_regime']} | Verdict: {synthesis['post_verdict']}")

    sub_banner("PROPOSAL RANKINGS")
    for i, (name, fitness) in enumerate(synthesis["ranked_proposals"], 1):
        print(f"  {i}. {name} (fitness={fitness})")

    sub_banner("ORGANISM VOICE (post-deliberation)")
    model_print("organism", synthesis["voice"])

    # Summary
    elapsed_total = round(time.monotonic() - t_start, 1)
    ok_count = sum(1 for p in proposals if p["status"] == "OK")
    crit_ok = sum(1 for c in critiques if c["status"] == "OK")

    banner("COUNCIL COMPLETE")
    print(f"  Models fired: {len(proposals)} proposals, {len(critiques)} critiques")
    print(f"  Successful: {ok_count} proposals, {crit_ok} critiques")
    print(f"  Subsystems exercised: OrganismRuntime, Stigmergy, DharmaKernel,")
    print(f"    DharmaCorpus, Lineage, TelosGates, MessageBus, SignalBus,")
    print(f"    Identity, Samvara, OllamaProvider, NVIDIANIMProvider,")
    print(f"    OpenRouterFreeProvider, ProviderPolicyRouter")
    print(f"  Coherence delta: {synthesis['delta']:+.4f}")
    print(f"  Total elapsed: {elapsed_total}s")
    print(f"  Cost: $0.00 (all free-tier models)")

    # Save results
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_before": state,
        "proposals": [{k: v for k, v in p.items()} for p in proposals],
        "critiques": [{k: v for k, v in c.items()} for c in critiques],
        "synthesis": synthesis,
        "elapsed_total": elapsed_total,
    }
    out_path = STATE_DIR / "council_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"  Results saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
