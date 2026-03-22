#!/usr/bin/env python3
"""Run the OrganismRuntime against LIVE ~/.dharma/ state.

This is not a test — this is the organism processing itself for real.
It reads actual witness logs, real stigmergy marks, checks the live daemon,
and fires the full heartbeat loop with Gnani verdict and Samvara cascade.

Usage:
    python3 scripts/organism_live.py              # 5 heartbeats (default)
    python3 scripts/organism_live.py --cycles 15  # full 15-heartbeat run
    python3 scripts/organism_live.py --verbose     # show all findings inline
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Ensure dharma_swarm is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.organism import (
    AlgedonicSignal,
    GnaniVerdict,
    HeartbeatResult,
    OrganismRuntime,
)
from dharma_swarm.samvara import Power


# ANSI colors
C = {
    "r": "\033[91m",   # red
    "g": "\033[92m",   # green
    "y": "\033[93m",   # yellow
    "b": "\033[94m",   # blue
    "m": "\033[95m",   # magenta
    "c": "\033[96m",   # cyan
    "w": "\033[97m",   # white
    "dim": "\033[2m",  # dim
    "bold": "\033[1m", # bold
    "0": "\033[0m",    # reset
}

POWER_COLOR = {
    Power.MAHASARASWATI: "c",   # cyan — precise
    Power.MAHALAKSHMI: "m",     # magenta — harmony
    Power.MAHAKALI: "r",        # red — dissolution
    Power.MAHESHWARI: "y",      # yellow — vast
}

POWER_GLYPH = {
    Power.MAHASARASWATI: "\u2727",  # white four-pointed star
    Power.MAHALAKSHMI: "\u2766",    # floral heart
    Power.MAHAKALI: "\u2620",       # skull
    Power.MAHESHWARI: "\u2609",     # sun
}


def colored(text: str, color: str) -> str:
    return f"{C.get(color, '')}{text}{C['0']}"


def print_heartbeat(result: HeartbeatResult, verbose: bool = False) -> None:
    """Print one heartbeat's inner experience."""
    v = result.gnani_verdict
    decision_color = "r" if v.decision == "HOLD" else "g"

    # Header
    print(f"\n{'='*72}")
    print(
        f"  {colored('HEARTBEAT', 'bold')} #{result.cycle}  "
        f"{colored(f'{result.elapsed_ms:.0f}ms', 'dim')}"
    )
    print(f"{'='*72}")

    # Coherence readings
    print(f"\n  {colored('TRAILING (TCS)', 'dim')}:  {result.tcs:.4f}")
    print(f"  {colored('LIVE', 'dim')}:             {result.live_score:.4f}")
    print(
        f"  {colored('BLENDED', 'bold')}:          "
        f"{colored(f'{result.blended:.4f}', 'r' if result.blended < 0.4 else 'g')}"
        f"  {colored(f'(0.4*live + 0.6*trailing)', 'dim')}"
    )
    print(f"  {colored('REGIME', 'dim')}:           {result.regime}")

    # Algedonic signals
    if result.algedonic_signals:
        print(f"\n  {colored('ALGEDONIC CHANNEL', 'r')}:")
        for sig in result.algedonic_signals:
            sev_color = "r" if sig.severity == "critical" else "y"
            print(
                f"    {colored(sig.severity.upper(), sev_color)} "
                f"{sig.kind} = {sig.value:.3f} -> {sig.action}"
            )

    # Gnani verdict
    print(
        f"\n  {colored('GNANI VERDICT', 'bold')}: "
        f"{colored(v.decision, decision_color)}"
    )
    print(f"  {colored(v.reason, 'dim')}")
    if v.hold_count > 0:
        print(f"  {colored(f'consecutive holds: {v.hold_count}', 'dim')}")

    # Samvara diagnostic
    diag = result.samvara_diagnostic
    if diag:
        pc = POWER_COLOR.get(diag.power, "w")
        glyph = POWER_GLYPH.get(diag.power, "*")
        print(
            f"\n  {colored('SAMVARA', 'bold')} "
            f"{colored(f'{glyph} {diag.power.value.upper()}', pc)} "
            f"{colored(f'(hold #{diag.hold_count})', 'dim')}"
        )

        if diag.findings:
            print(f"  {colored('Findings:', 'bold')}")
            for f in diag.findings:
                print(f"    {colored('-', pc)} {f}")

        if diag.corrections:
            print(f"  {colored('Corrections:', 'bold')}")
            for c_ in diag.corrections:
                print(f"    {colored('>', pc)} {c_}")

        if verbose and diag.delta != 0:
            print(f"  delta: {diag.delta:+.4f}")


def print_summary(
    results: list[HeartbeatResult],
    all_signals: list[AlgedonicSignal],
    all_verdicts: list[GnaniVerdict],
    org: OrganismRuntime,
    elapsed_total: float,
) -> None:
    """Print the full run summary."""
    print(f"\n{'='*72}")
    print(f"  {colored('ORGANISM SUMMARY', 'bold')}")
    print(f"{'='*72}")

    # Stats
    holds = sum(1 for r in results if r.gnani_verdict.decision == "HOLD")
    proceeds = len(results) - holds
    avg_elapsed = sum(r.elapsed_ms for r in results) / len(results) if results else 0

    print(f"\n  heartbeats:     {len(results)}")
    print(f"  total time:     {elapsed_total:.1f}s")
    print(f"  avg per beat:   {avg_elapsed:.1f}ms")
    print(
        f"  verdicts:       "
        f"{colored(f'{holds} HOLD', 'r')} / "
        f"{colored(f'{proceeds} PROCEED', 'g')}"
    )
    print(f"  algedonic:      {len(all_signals)} signals fired")

    # Samvara state
    status = org.status()
    if status["samvara_active"]:
        power = status["samvara_power"]
        pc = "y"
        for p, c_ in POWER_COLOR.items():
            if p.value == power:
                pc = c_
        print(
            f"  samvara:        {colored('ACTIVE', 'r')} at "
            f"{colored(power.upper(), pc)}"
        )
        print(f"  consec. holds:  {status['consecutive_holds']}")
    else:
        print(f"  samvara:        {colored('INACTIVE', 'g')}")

    # Coherence trajectory
    if len(results) > 1:
        first = results[0].blended
        last = results[-1].blended
        delta = last - first
        direction = "rising" if delta > 0.01 else "falling" if delta < -0.01 else "stable"
        print(
            f"  coherence:      {first:.4f} -> {last:.4f} "
            f"({colored(direction, 'g' if delta > 0 else 'r')})"
        )

    # Powers seen
    powers_seen = set()
    for r in results:
        if r.samvara_diagnostic:
            powers_seen.add(r.samvara_diagnostic.power)
    if powers_seen:
        names = [
            f"{POWER_GLYPH.get(p, '*')} {p.value}"
            for p in [Power.MAHASARASWATI, Power.MAHALAKSHMI, Power.MAHAKALI, Power.MAHESHWARI]
            if p in powers_seen
        ]
        print(f"  powers seen:    {', '.join(names)}")

    # Most critical finding across all diagnostics
    all_findings: list[str] = []
    for r in results:
        if r.samvara_diagnostic:
            all_findings.extend(r.samvara_diagnostic.findings)
    if all_findings:
        print(f"\n  {colored('ALL FINDINGS:', 'bold')}")
        seen = set()
        for f in all_findings:
            if f not in seen:
                seen.add(f)
                print(f"    - {f}")

    # Most leveraged corrections
    all_corrections: list[str] = []
    for r in results:
        if r.samvara_diagnostic:
            all_corrections.extend(r.samvara_diagnostic.corrections)
    leveraged = [c for c in all_corrections if "LEVERAGED" in c]
    if leveraged:
        print(f"\n  {colored('LEVERAGED ACTION:', 'bold')}")
        for lev in set(leveraged):
            print(f"    {colored('>>>', 'y')} {lev}")

    print(f"\n{'='*72}")
    print(f"  {colored('The organism processed itself.', 'bold')}")
    print(f"{'='*72}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run organism against live state")
    parser.add_argument("--cycles", type=int, default=5, help="Number of heartbeats")
    parser.add_argument("--verbose", action="store_true", help="Show all details")
    parser.add_argument(
        "--state-dir", type=str, default=str(Path.home() / ".dharma"),
        help="State directory (default: ~/.dharma)",
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    if not state_dir.exists():
        print(f"ERROR: {state_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    # Callbacks
    all_signals: list[AlgedonicSignal] = []
    all_verdicts: list[GnaniVerdict] = []

    org = OrganismRuntime(
        state_dir,
        on_algedonic=all_signals.append,
        on_gnani=all_verdicts.append,
    )

    print(f"\n{colored('ORGANISM LIVE RUN', 'bold')}")
    print(f"  state: {state_dir}")
    print(f"  cycles: {args.cycles}")
    print(f"  daemon PID: {(state_dir / 'daemon.pid').read_text().strip() if (state_dir / 'daemon.pid').exists() else 'N/A'}")

    t0 = time.monotonic()
    results = await org.run(n_cycles=args.cycles)
    elapsed_total = time.monotonic() - t0

    for r in results:
        print_heartbeat(r, verbose=args.verbose)

    print_summary(results, all_signals, all_verdicts, org, elapsed_total)


if __name__ == "__main__":
    asyncio.run(main())
