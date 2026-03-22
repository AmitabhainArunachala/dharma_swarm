#!/usr/bin/env python3
"""Decompose the organism's coherence readings — see what's really happening.

Not just the final number — what's each sensor actually seeing?
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.identity import (
    IdentityMonitor,
    LiveCoherenceSensor,
    _bsi_proxy_score,
)

STATE = Path.home() / ".dharma"


async def decompose() -> None:
    print("\n" + "="*72)
    print("  ORGANISM DECOMPOSITION — what's each sensor actually seeing?")
    print("="*72)

    monitor = IdentityMonitor(STATE)
    sensor = LiveCoherenceSensor(STATE)

    # -----------------------------------------------------------------------
    # 1. GPR — what are the witness logs actually saying?
    # -----------------------------------------------------------------------
    print("\n--- GPR (Gate Passage Rate) ---")
    witness_dir = STATE / "witness"
    log_files = sorted(
        witness_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    print(f"  JSONL files found: {len(log_files)}")
    total = 0
    passed = 0
    blocked = 0
    other = 0
    for lf in log_files:
        for line in lf.read_text().strip().split("\n")[-50:]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            total += 1
            outcome = entry.get("outcome", entry.get("decision", ""))
            if outcome in ("PASS", "ALLOW", "allow"):
                passed += 1
            elif outcome in ("BLOCKED", "DENY", "deny"):
                blocked += 1
            else:
                other += 1
            if total >= 150:
                break
        if total >= 150:
            break
    gpr = passed / total if total > 0 else 0.5
    print(f"  entries sampled: {total}")
    print(f"  PASS/ALLOW: {passed}  BLOCKED/DENY: {blocked}  other: {other}")
    print(f"  GPR = {gpr:.4f}")

    # Show sample outcomes
    print("  last 5 outcomes:")
    last_file = log_files[0] if log_files else None
    if last_file:
        recent_lines = last_file.read_text().strip().split("\n")[-5:]
        for line in recent_lines:
            try:
                entry = json.loads(line)
                outcome = entry.get("outcome", "?")
                action = entry.get("action", "?")[:60]
                phase = entry.get("phase", "?")
                print(f"    {outcome:8s} | {phase:15s} | {action}")
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # 2. BSI — what quality are the shared notes?
    # -----------------------------------------------------------------------
    print("\n--- BSI (Behavioral Swabhaav Index) ---")
    shared_dir = STATE / "shared"
    notes = sorted(
        shared_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    print(f"  recent .md files sampled: {len(notes)}")
    scores = []
    for note in notes:
        try:
            text = note.read_text()
            if len(text) < 50:
                continue
            score = _bsi_proxy_score(text)
            scores.append((note.name, score, len(text)))
        except Exception:
            continue
    bsi = sum(s for _, s, _ in scores) / len(scores) if scores else 0.5
    print(f"  BSI = {bsi:.4f}")
    for name, score, size in scores:
        bar = "+" * int(score * 40)
        print(f"    {name:45s} {score:.3f} [{bar}] ({size}b)")

    # Show the highest-scoring note's first 200 chars
    if scores:
        best = max(scores, key=lambda x: x[1])
        best_text = (shared_dir / best[0]).read_text()[:200]
        print(f"\n  highest BSI ({best[0]}, {best[1]:.3f}):")
        print(f"    \"{best_text}...\"")

        worst = min(scores, key=lambda x: x[1])
        worst_text = (shared_dir / worst[0]).read_text()[:200]
        print(f"\n  lowest BSI ({worst[0]}, {worst[1]:.3f}):")
        print(f"    \"{worst_text}...\"")

    # -----------------------------------------------------------------------
    # 3. RM — what's the momentum signal?
    # -----------------------------------------------------------------------
    print("\n--- RM (Research Momentum) ---")
    archive_path = STATE / "evolution" / "archive.jsonl"
    marks_path = STATE / "stigmergy" / "marks.jsonl"

    if archive_path.exists():
        archive_lines = archive_path.read_text().strip().split("\n")
        archive_signal = min(1.0, len(archive_lines) / 100.0)
        print(f"  evolution archive: {len(archive_lines)} entries -> signal {archive_signal:.2f}")
    else:
        archive_signal = 0
        print("  evolution archive: MISSING")

    if marks_path.exists():
        marks_content = marks_path.read_text().strip()
        all_lines = marks_content.split("\n")
        valid = 0
        for line in all_lines:
            try:
                json.loads(line)
                valid += 1
            except Exception:
                pass
        marks_signal = min(1.0, valid / 1000.0)
        print(f"  stigmergy: {valid}/{len(all_lines)} valid entries -> signal {marks_signal:.2f}")
    else:
        marks_signal = 0
        print("  stigmergy: MISSING")

    notes_count = len(list(shared_dir.glob("*.md")))
    notes_signal = min(1.0, notes_count / 50.0)
    print(f"  shared notes: {notes_count} files -> signal {notes_signal:.2f}")

    rm = (archive_signal + marks_signal + notes_signal) / 3.0
    print(f"  RM = {rm:.4f}")

    # -----------------------------------------------------------------------
    # 4. TCS computation
    # -----------------------------------------------------------------------
    tcs = 0.35 * gpr + 0.35 * bsi + 0.30 * rm
    print(f"\n--- TCS = 0.35*{gpr:.4f} + 0.35*{bsi:.4f} + 0.30*{rm:.4f} = {tcs:.4f} ---")

    # -----------------------------------------------------------------------
    # 5. Live Coherence
    # -----------------------------------------------------------------------
    print("\n--- Live Coherence Sensor ---")
    live = sensor.measure()
    print(f"  daemon alive: {live['daemon_alive']}")
    print(f"  subsystem freshness:")
    for name, fresh in live["subsystem_freshness"].items():
        path = STATE / LiveCoherenceSensor.SUBSYSTEMS[name]
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            print(f"    {name:12s}: {'FRESH' if fresh else 'STALE':5s} ({age_h:.1f}h old)")
        else:
            print(f"    {name:12s}: MISSING")
    print(f"  freshness ratio: {live['freshness_ratio']:.2f}")
    print(f"  live score: {live['score']:.4f}")

    # -----------------------------------------------------------------------
    # 6. Blended
    # -----------------------------------------------------------------------
    blended = 0.4 * live["score"] + 0.6 * tcs
    print(f"\n--- BLENDED = 0.4*{live['score']:.4f} + 0.6*{tcs:.4f} = {blended:.4f} ---")

    if blended >= 0.4:
        print("  VERDICT: PROCEED")
    else:
        print("  VERDICT: HOLD")

    # -----------------------------------------------------------------------
    # 7. The honest question: is this real coherence?
    # -----------------------------------------------------------------------
    print("\n" + "="*72)
    print("  HONEST ASSESSMENT")
    print("="*72)

    issues = []
    if gpr > 0.5:
        # Check — is high GPR real or just busy agents passing gates trivially?
        if passed > 100 and blocked < 5:
            issues.append(
                f"GPR={gpr:.2f} looks suspiciously high — {passed} PASS vs {blocked} BLOCKED. "
                "Are gates actually filtering anything?"
            )

    if bsi > 0.3:
        # Check — is BSI measuring real quality or just keyword volume?
        avg_len = sum(s for _, _, s in scores) / len(scores) if scores else 0
        if avg_len > 2000:
            issues.append(
                f"BSI={bsi:.2f} — notes average {avg_len:.0f}b. "
                "Length can inflate keyword hits without semantic quality."
            )

    if rm > 0.8:
        issues.append(
            f"RM={rm:.2f} — high momentum from volume ({notes_count} notes, "
            f"{valid} marks). Is this real progress or accumulation?"
        )

    if not issues:
        print("  No obvious inflation detected. Coherence appears genuine.")
    else:
        for issue in issues:
            print(f"  ! {issue}")

    # Check stigmergy for repetition
    if marks_path.exists():
        recent_obs = []
        for line in marks_content.split("\n")[-50:]:
            try:
                entry = json.loads(line)
                obs = entry.get("observation", "")[:80]
                if obs:
                    recent_obs.append(obs)
            except Exception:
                pass
        if recent_obs:
            unique = len(set(recent_obs))
            if unique < len(recent_obs) * 0.6:
                print(
                    f"  ! Stigmergy repetition: {unique}/{len(recent_obs)} unique "
                    "in last 50 — system may be looping"
                )
            else:
                print(f"  Stigmergy diversity: {unique}/{len(recent_obs)} unique — healthy")

    print()


if __name__ == "__main__":
    asyncio.run(decompose())
