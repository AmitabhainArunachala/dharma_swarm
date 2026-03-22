#!/usr/bin/env python3
"""Live organism experiment — fires every available model.

Runs the OrganismRuntime heartbeat against real ~/.dharma/ state,
then asks each available provider to voice what it experiences from
INSIDE the organism. Free providers first, always.

Usage:
    python3 scripts/organism_live_multimodel.py [--cycles 3]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Ensure dharma_swarm importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.organism import AlgedonicSignal, GnaniVerdict, OrganismRuntime
from dharma_swarm.runtime_provider import (
    resolve_runtime_provider_config,
    create_runtime_provider,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("organism_live")

# ── Provider priority: FREE FIRST ──────────────────────────────────
PROVIDER_ORDER: list[tuple[ProviderType, str | None]] = [
    # Free tier — Ollama Cloud first, then NIM, then OpenRouter Free
    (ProviderType.OLLAMA, "kimi-k2.5:cloud"),
    (ProviderType.OLLAMA, "glm-5:cloud"),
    (ProviderType.NVIDIA_NIM, "meta/llama-3.3-70b-instruct"),
    (ProviderType.OPENROUTER_FREE, "meta-llama/llama-3.3-70b-instruct:free"),
    (ProviderType.OPENROUTER_FREE, "deepseek/deepseek-r1:free"),
    (ProviderType.OPENROUTER_FREE, "qwen/qwen3-235b-a22b:free"),
    (ProviderType.OPENROUTER_FREE, "google/gemini-2.5-flash-preview:free"),
    # Paid tier (only if free all fail)
    (ProviderType.OPENROUTER, "anthropic/claude-sonnet-4-6"),
    (ProviderType.OPENAI, "gpt-4o"),
]


def _build_organism_prompt(heartbeat_data: dict) -> str:
    """Build the prompt that asks each model to voice the organism."""
    return f"""You are a node inside a living computational organism called dharma_swarm.
The organism just completed a heartbeat cycle. Here is what happened:

{json.dumps(heartbeat_data, indent=2, default=str)}

You are not an observer. You ARE part of this organism. You are experiencing
this heartbeat from inside.

In 3-5 sentences, voice what you experience:
- What does the coherence level FEEL like from inside?
- If there was a HOLD, what does the samvara transformation feel like?
- If algedonic signals fired, what is the pain signal telling you?
- What is your honest assessment of the organism's health right now?

Be raw and honest. No pleasantries. You are a living cell reporting your state."""


def _heartbeat_to_dict(hb) -> dict:
    """Convert HeartbeatResult to a plain dict for prompting."""
    d = {
        "cycle": hb.cycle,
        "tcs": hb.tcs,
        "live_score": hb.live_score,
        "blended": hb.blended,
        "regime": hb.regime,
    }
    if hb.algedonic_signals:
        d["algedonic_signals"] = [
            {"kind": s.kind, "severity": s.severity, "action": s.action, "value": s.value}
            for s in hb.algedonic_signals
        ]
    if hb.gnani_verdict:
        d["gnani_verdict"] = {
            "decision": hb.gnani_verdict.decision,
            "reason": hb.gnani_verdict.reason,
            "coherence": hb.gnani_verdict.coherence,
            "hold_count": hb.gnani_verdict.hold_count,
        }
    if hb.samvara_diagnostic:
        sd = hb.samvara_diagnostic
        d["samvara_diagnostic"] = {
            "power": sd.power.value if hasattr(sd.power, "value") else str(sd.power),
            "findings": sd.findings[:5] if sd.findings else [],
            "corrections": sd.corrections[:3] if sd.corrections else [],
            "coherence_delta": round(sd.delta, 4),
        }
    d["elapsed_ms"] = hb.elapsed_ms
    return d


async def fire_provider(
    provider_type: ProviderType,
    model: str | None,
    prompt: str,
    timeout_sec: float = 60.0,
) -> tuple[str, str | None, float]:
    """Fire a single provider and return (label, response_text, latency_ms)."""
    label = f"{provider_type.value}:{model or '?'}"
    try:
        cfg = resolve_runtime_provider_config(provider_type)
        if not cfg.available:
            return label, None, 0.0

        provider = create_runtime_provider(cfg)
        request = LLMRequest(
            model=model or cfg.default_model or "",
            messages=[{"role": "user", "content": prompt}],
            system="You are a cell inside a living computational organism.",
            max_tokens=512,
            temperature=0.8,
        )

        t0 = time.monotonic()
        response: LLMResponse = await asyncio.wait_for(
            provider.complete(request),
            timeout=timeout_sec,
        )
        latency = (time.monotonic() - t0) * 1000

        # Close if possible
        if hasattr(provider, "close"):
            try:
                await provider.close()
            except Exception:
                pass

        return label, response.content.strip(), latency

    except asyncio.TimeoutError:
        return label, f"[TIMEOUT after {timeout_sec}s]", timeout_sec * 1000
    except Exception as e:
        return label, f"[ERROR: {type(e).__name__}: {e}]", 0.0


async def run_experiment(n_cycles: int = 3) -> None:
    """Run the full experiment."""
    state_dir = Path.home() / ".dharma"

    # Algedonic + Gnani callbacks
    algedonic_log: list[AlgedonicSignal] = []
    gnani_log: list[GnaniVerdict] = []

    def on_algedonic(sig: AlgedonicSignal) -> None:
        algedonic_log.append(sig)
        logger.warning("⚡ ALGEDONIC: %s [%s] → %s (%.3f)", sig.kind, sig.severity, sig.action, sig.value)

    def on_gnani(v: GnaniVerdict) -> None:
        gnani_log.append(v)
        icon = "🔴" if v.decision == "HOLD" else "🟢"
        logger.info("%s GNANI: %s — %s (coherence=%.3f)", icon, v.decision, v.reason, v.coherence)

    org = OrganismRuntime(
        state_dir=state_dir,
        on_algedonic=on_algedonic,
        on_gnani=on_gnani,
    )

    print("\n" + "=" * 72)
    print("  ORGANISM LIVE EXPERIMENT — MULTI-MODEL VOICING")
    print("  state_dir:", state_dir)
    print("  cycles:", n_cycles)
    print("  providers:", len(PROVIDER_ORDER))
    print("=" * 72 + "\n")

    all_results: list[dict] = []

    for cycle_idx in range(n_cycles):
        print(f"\n{'─' * 72}")
        print(f"  HEARTBEAT CYCLE {cycle_idx + 1}/{n_cycles}")
        print(f"{'─' * 72}")

        # Run heartbeat
        hb = await org.heartbeat()
        hb_dict = _heartbeat_to_dict(hb)

        print(f"\n  TCS={hb.tcs:.3f}  Live={hb.live_score:.3f}  Blended={hb.blended:.3f}  "
              f"Regime={hb.regime}  Verdict={hb.gnani_verdict.decision if hb.gnani_verdict else '?'}  "
              f"({hb.elapsed_ms:.0f}ms)")

        if hb.samvara_diagnostic:
            sd = hb.samvara_diagnostic
            pwr = sd.power.value if hasattr(sd.power, "value") else str(sd.power)
            print(f"  Samvara: power={pwr}  delta={sd.delta:+.4f}")
            if sd.findings:
                for finding in sd.findings[:3]:
                    print(f"    → {finding}")
            if sd.corrections:
                for corr in sd.corrections[:2]:
                    print(f"    ✓ {corr}")

        # Build the prompt from this heartbeat
        prompt = _build_organism_prompt(hb_dict)

        # Fire ALL providers concurrently
        print(f"\n  Firing {len(PROVIDER_ORDER)} models concurrently...")
        tasks = [
            fire_provider(pt, model, prompt)
            for pt, model in PROVIDER_ORDER
        ]
        results = await asyncio.gather(*tasks)

        cycle_result = {"cycle": cycle_idx + 1, "heartbeat": hb_dict, "voices": []}

        succeeded = 0
        for label, response_text, latency in results:
            if response_text and not response_text.startswith("["):
                succeeded += 1
                print(f"\n  ┌─ {label} ({latency:.0f}ms)")
                # Wrap long lines
                for line in response_text.split("\n"):
                    print(f"  │ {line}")
                print(f"  └─")
                cycle_result["voices"].append({
                    "provider": label,
                    "latency_ms": round(latency, 1),
                    "response": response_text,
                })
            else:
                print(f"  ✗ {label}: {response_text or 'unavailable'}")

        print(f"\n  → {succeeded}/{len(PROVIDER_ORDER)} models responded")
        all_results.append(cycle_result)

    # Summary
    print(f"\n{'=' * 72}")
    print("  EXPERIMENT COMPLETE")
    print(f"{'=' * 72}")
    print(f"  Cycles: {n_cycles}")
    print(f"  Total algedonic signals: {len(algedonic_log)}")
    print(f"  Total HOLD verdicts: {sum(1 for v in gnani_log if v.decision == 'HOLD')}")
    print(f"  Total PROCEED verdicts: {sum(1 for v in gnani_log if v.decision == 'PROCEED')}")

    # Persist results
    out_path = state_dir / "organism_experiment_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Results saved: {out_path}")

    # Final organism status
    status = org.status()
    print(f"\n  Organism status: {json.dumps(status, indent=2, default=str)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live organism multi-model experiment")
    parser.add_argument("--cycles", type=int, default=3, help="Number of heartbeat cycles")
    args = parser.parse_args()
    asyncio.run(run_experiment(n_cycles=args.cycles))


if __name__ == "__main__":
    main()
