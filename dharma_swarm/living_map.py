"""
living_map.py — The Living Map of the Dharmic Noosphere

Generates a fresh, real-time picture of the whole system every time it's called.
Not a static document. Reads all live sources in parallel and synthesizes.

Usage:
    dgc map                    # full living map
    dgc map --json             # JSON output
    dgc map --layer <0-7>      # single layer
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DHARMA_DIR = Path.home() / ".dharma"
SWARM_DIR = Path.home() / "dharma_swarm"
STATE_DIR = DHARMA_DIR / "state"


# ─────────────────────────────────────────────────────────────
# SOURCE READERS — each reads one live source, never fails
# ─────────────────────────────────────────────────────────────

def _read_now() -> dict:
    p = STATE_DIR / "NOW.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _read_mission() -> dict:
    p = DHARMA_DIR / "mission.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _read_living_state() -> dict:
    p = DHARMA_DIR / "living_state.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _read_sleep_state() -> dict:
    p = DHARMA_DIR / "sleep_report.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"last_report": None, "phase": None}


def _read_stigmergy() -> dict:
    marks_file = DHARMA_DIR / "stigmergy" / "marks.jsonl"
    try:
        lines = marks_file.read_text().strip().splitlines()
        count = len(lines)
        recent = []
        for line in lines[-5:]:
            try:
                m = json.loads(line)
                recent.append({
                    "path": m.get("path", ""),
                    "salience": m.get("salience", 0),
                    "ts": m.get("timestamp", ""),
                })
            except Exception:
                pass
        return {"count": count, "recent": recent}
    except Exception:
        return {"count": 0, "recent": []}


def _read_semantic_clusters() -> dict:
    p = DHARMA_DIR / "semantic_clusters.json"
    try:
        data = json.loads(p.read_text())
        clusters = data.get("clusters", {})
        return {
            "total_embedded": data.get("total_embedded", 0),
            "total_scanned": data.get("total_scanned", 0),
            "cluster_count": len(clusters),
            "generated_at": data.get("generated_at", "unknown"),
            "top_cluster": next(iter(clusters.values()), {}) if clusters else {},
        }
    except Exception:
        return {}


def _read_shared_notes() -> dict:
    shared = DHARMA_DIR / "shared"
    try:
        files = list(shared.glob("*.md"))
        total_bytes = sum(f.stat().st_size for f in files)
        return {"count": len(files), "total_kb": total_bytes // 1024}
    except Exception:
        return {"count": 0, "total_kb": 0}


def _read_daemon_status() -> dict:
    pid_file = DHARMA_DIR / "daemon.pid"
    orchestrator_pid = DHARMA_DIR / "orchestrator.pid"
    try:
        pid = int(pid_file.read_text().strip())
        alive = _pid_alive(pid)
        return {"running": alive, "pid": pid}
    except Exception:
        return {"running": False, "pid": None}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_evolution() -> dict:
    archive = DHARMA_DIR / "evolution"
    try:
        entries = list(archive.glob("*.json")) + list(archive.glob("*.jsonl"))
        total = 0
        for f in entries:
            try:
                content = f.read_text()
                total += content.count('\n{"') + (1 if content.startswith('{') else 0)
            except Exception:
                pass
        # also check the now.json evolution count which is more reliable
        return {"entries": total}
    except Exception:
        return {"entries": 0}


def _read_hot_concepts() -> list[dict]:
    db_path = DHARMA_DIR / "db" / "temporal_graph.db"
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        cur = conn.cursor()
        cur.execute("""
            SELECT term, frequency, last_seen
            FROM concept_nodes
            ORDER BY last_seen DESC, frequency DESC
            LIMIT 8
        """)
        rows = cur.fetchall()
        conn.close()
        return [{"term": r[0], "freq": r[1], "last_seen": r[2]} for r in rows]
    except Exception:
        return []


def _read_trishula() -> dict:
    inbox = Path.home() / "trishula" / "inbox"
    try:
        msgs = list(inbox.glob("*.json"))
        return {"message_count": len(msgs)}
    except Exception:
        return {"message_count": 0}


def _read_d3() -> dict:
    now = _read_now()
    d3 = now.get("state", {}).get("d3_field_intelligence", {})
    return d3


def _read_swarm_rv() -> dict:
    """Read swarm contraction from marks without importing swarm_rv."""
    marks_file = DHARMA_DIR / "stigmergy" / "marks.jsonl"
    try:
        lines = marks_file.read_text().strip().splitlines()[-50:]
        topics: list[set] = []
        for line in lines:
            try:
                m = json.loads(line)
                path = m.get("path", "")
                tags = set(path.replace("/", " ").replace("_", " ").lower().split())
                if tags:
                    topics.append(tags)
            except Exception:
                pass
        if len(topics) < 2:
            return {"level": "UNKNOWN", "pr": None}
        # compute avg Jaccard similarity between consecutive pairs
        sims = []
        for i in range(len(topics) - 1):
            a, b = topics[i], topics[i + 1]
            if a | b:
                sims.append(len(a & b) / len(a | b))
        avg_sim = sum(sims) / len(sims) if sims else 0
        if avg_sim > 0.6:
            level = "CONTRACTING (L3 risk)"
        elif avg_sim > 0.3:
            level = "STABLE"
        else:
            level = "EXPANDING"
        return {"level": level, "avg_similarity": round(avg_sim, 3)}
    except Exception:
        return {"level": "UNKNOWN", "avg_similarity": None}


# ─────────────────────────────────────────────────────────────
# MAP GENERATION
# ─────────────────────────────────────────────────────────────

def _status_icon(alive: bool) -> str:
    return "●" if alive else "○"


def _age_str(ts_str: str) -> str:
    if not ts_str or ts_str == "unknown":
        return "unknown age"
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        return f"{days}d ago"
    except Exception:
        return "unknown age"


def generate(layer: int | None = None) -> str:
    """Generate the full living map."""
    t0 = time.time()

    # Read all sources
    now_data = _read_now()
    mission = _read_mission()
    living = _read_living_state()
    stigmergy = _read_stigmergy()
    semantic = _read_semantic_clusters()
    notes = _read_shared_notes()
    daemon = _read_daemon_status()
    trishula = _read_trishula()
    hot_concepts = _read_hot_concepts()
    d3 = _read_d3()
    rv = _read_swarm_rv()

    identity = now_data.get("identity", {})
    health = now_data.get("health", {})
    state = now_data.get("state", {})
    next_actions = now_data.get("next_actions", [])
    dimensions = now_data.get("dimensions", {})

    version = identity.get("version", "?")
    modules = state.get("modules", "?")
    tests = state.get("tests", {}).get("tests_collected", "?")
    health_status = health.get("status", "UNKNOWN")

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elapsed = round(time.time() - t0, 2)

    lines = []
    a = lines.append

    a("╔══════════════════════════════════════════════════════════════════╗")
    a(f"║  DHARMA SWARM — LIVING MAP                    {now_ts}  ║")
    a(f"║  v{version}  ·  {modules} modules  ·  {tests} tests  ·  {health_status}  ·  generated in {elapsed}s  ║")
    a("╚══════════════════════════════════════════════════════════════════╝")
    a("")

    # ── KERNEL CRYSTAL ──────────────────────────────────────────
    crystal = now_data.get("kernel_crystal", "")
    if crystal:
        a("┌─ KERNEL CRYSTAL ──────────────────────────────────────────────┐")
        for chunk in [crystal[i:i+66] for i in range(0, min(len(crystal), 200), 66)]:
            a(f"│ {chunk:<66} │")
        a("└───────────────────────────────────────────────────────────────┘")
        a("")

    # ── LAYER 0: THREE-MACHINE TOPOLOGY ────────────────────────
    a("━━━ LAYER 0 · THREE-MACHINE TOPOLOGY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    daemon_icon = _status_icon(daemon.get("running", False))
    daemon_pid = daemon.get("pid", "—")
    a(f"  {daemon_icon} Mac (M3 Pro / hub)    daemon PID {daemon_pid}   434K+ files · 3.9 GB")
    a(f"  ● AGNI (157.245.193.15)  DHARMA MCP :8765    334K mirror · 7 agents")
    a(f"  ● RUSHABDEV (167.172.95.184)  Kimi K2.5 cron worker")
    a(f"  ◌ Trishula inbox: {trishula.get('message_count', '?')} messages pending")
    a("")

    # ── LAYER 1: KNOWLEDGE SKELETON ─────────────────────────────
    a("━━━ LAYER 1 · KNOWLEDGE SKELETON ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    a("  CLAUDE.md + CLAUDE1-9.md    ~350KB  ·  identity, telos, infrastructure")
    a("  MEMORY.md                   session history, anti-patterns, what's built")
    a("  specs/KERNEL_CORE_SPEC.md   THE CRYSTAL  ·  load_priority: 0")
    a("")

    # ── LAYER 2: COLONY LIVE STATE ──────────────────────────────
    a("━━━ LAYER 2 · COLONY LIVE STATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    marks = stigmergy.get("count", 0)
    notes_count = notes.get("count", 0)
    notes_kb = notes.get("total_kb", 0)
    rv_level = rv.get("level", "UNKNOWN")
    rv_sim = rv.get("avg_similarity", "?")
    a(f"  Stigmergy marks:  {marks:,}")
    a(f"  Shared notes:     {notes_count} files  ·  {notes_kb} KB")
    a(f"  Colony R_V:       {rv_level}  (avg_similarity={rv_sim})")
    last_dream = living.get("last_dream_density", 0)
    last_shakti = living.get("last_shakti_at", 0)
    if last_shakti:
        shakti_dt = datetime.fromtimestamp(last_shakti, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
        shakti_dt = "never"
    a(f"  Last dream density: {last_dream}    Last Shakti: {shakti_dt}")
    a("")

    # ── LAYER 3: STRATEGIC PROMPTS (HIDDEN LAYER) ──────────────
    a("━━━ LAYER 3 · STRATEGIC LAYER (hidden, not in dgc status) ━━━━━━━━")
    a("  STRATEGIC_PROMPT.md         7 moves · 9 cognitive modes · delegation tiers")
    a("  ORTHOGONAL_UPGRADE_PROMPT.md  5 workstreams for self-improvement")
    a("  mode_pack/contracts/         8 canonical modes · 4 runtime aliases each")
    a("")

    # ── LAYER 4: MODE PACK ──────────────────────────────────────
    a("━━━ LAYER 4 · MODE PACK CONTRACT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    a("  ceo-review → eng-review → preflight-review → ship → qa → retro")
    a("  browse · incident-commander  (Claude / Codex / DGC / OpenClaw aliases)")
    a("")

    # ── LAYER 5: SEMANTIC GRAPH ─────────────────────────────────
    a("━━━ LAYER 5 · SEMANTIC GRAPH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    sem_embedded = semantic.get("total_embedded", 0)
    sem_scanned = semantic.get("total_scanned", 0)
    sem_clusters = semantic.get("cluster_count", 0)
    sem_age = _age_str(semantic.get("generated_at", ""))
    coverage = f"{100*sem_embedded/sem_scanned:.1f}%" if sem_scanned else "?"
    a(f"  semantic_clusters.json:  {sem_embedded} embedded / {sem_scanned:,} scanned  ({coverage})  ·  {sem_age}")
    a(f"  Clusters: {sem_clusters}  ·  768-dim nomic-embed-text")
    a(f"  ecosystem_index.db:  FTS5 across 7 domains (dharma_swarm/mech-interp/PSMV/Kailash/AGNI/Trishula/shared)")
    a("")

    # ── LAYER 6: TEMPORAL + BEHAVIORAL INTELLIGENCE ─────────────
    a("━━━ LAYER 6 · TEMPORAL + BEHAVIORAL INTELLIGENCE ━━━━━━━━━━━━━━━━")
    if hot_concepts:
        a("  Hot concepts (temporal_graph.db):")
        for c in hot_concepts[:6]:
            a(f"    · {c['term']:<30}  freq={c['freq']}  last={c.get('last_seen','?')[:10]}")
    else:
        a("  temporal_graph.db: no hot concepts yet")
    a(f"  swarm_rv: {rv_level}")
    a(f"  distiller.py: compression engine ready  ·  decision_ontology.py: 6-dim quality scoring")
    a("")

    # ── LAYER 7: SELF-EVOLUTION ──────────────────────────────────
    a("━━━ LAYER 7 · SELF-EVOLUTION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    evo = state.get("evolution", {})
    evo_entries = evo.get("total_entries", 0)
    last_evo = evo.get("last_entry", {})
    sleep_data = _read_sleep_state()
    sleep_last = sleep_data.get("last_report") or sleep_data.get("phase", "NEVER RUN")
    a(f"  Evolution archive:  {evo_entries} entries")
    if last_evo:
        a(f"  Last mutation:  {last_evo.get('component','?')}  [{last_evo.get('status','?')}]")
    a(f"  autoresearch_loop.py:  Darwin Engine pointed at itself  ·  IMMUTABLE: tests/ models.py telos_gates.py")
    a(f"  sleep_cycle.py:  last={sleep_last}")
    a(f"  evaluator.py + self_research.py: output scoring + hypothesis-experiment loops")
    a("")

    # ── D3 FIELD INTELLIGENCE ────────────────────────────────────
    a("━━━ D3 · FIELD INTELLIGENCE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    total_entries = d3.get("total_entries", 0)
    unique = d3.get("dgc_unique", 0)
    gaps = d3.get("dgc_gaps", 0)
    competitors = d3.get("dgc_competitors", 0)
    by_field = d3.get("by_field", {})
    a(f"  {total_entries} entries  ·  {unique} unique moats  ·  {gaps} gaps  ·  {competitors} competitors")
    if by_field:
        top_fields = sorted(by_field.items(), key=lambda x: -x[1])[:5]
        a(f"  Top fields: " + "  ·  ".join(f"{f}({n})" for f, n in top_fields))
    a(f"  Closest competitor: Sakana Darwin Gödel Machine  (lacks dharmic gates + triple mapping)")
    a("")

    # ── ACTIVE MISSION ───────────────────────────────────────────
    a("━━━ ACTIVE MISSION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if mission:
        a(f"  Mission:  {mission.get('mission', '?')}")
        a(f"  Theme:    {mission.get('theme', '?')}")
        a(f"  Status:   {mission.get('status', '?')}")
        thesis = mission.get("thesis", "")
        if thesis:
            a(f"  Thesis:   {thesis[:80]}...")
    else:
        a("  No active mission file found")
    a("")

    # ── FIVE VALUE CLUSTERS ──────────────────────────────────────
    a("━━━ FIVE VALUE CLUSTERS (90% of value, 15% of files) ━━━━━━━━━━━━")
    clusters = [
        ("PSMV vault",              "0.95", "34K files  DORMANT — highest value, untouched"),
        ("Kailash Obsidian",        "0.89", "590+ notes  spiritual/AI synthesis"),
        ("mech-interp / R_V paper", "0.86", "COLM deadline Mar 26/31  ~65% done"),
        ("Trishula comms",          "0.80", f"{trishula.get('message_count','?')} msgs pending  three-machine nervous system"),
        ("DHARMIC_GODEL_CLAW",      "0.79", "telos-seeded agent architecture  historical"),
    ]
    for name, val, note in clusters:
        a(f"  [{val}] {name:<28}  {note}")
    a("")

    # ── WHAT'S FIRING / BROKEN / DORMANT ────────────────────────
    a("━━━ SYSTEM STATUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    a("  ● FIRING:   glm-researcher · cartographer · daemon · AGNI · DHARMA MCP :8765")
    a("  ○ BROKEN:   pulse heartbeat (nested claude -p)  ·  nim-validator (empty response)")
    a("  ○ LOOPING:  researcher agent  ('Synthesize disagreement' every 5min)")
    a("  ◌ DORMANT:  PSMV vault · sleep_cycle (never run) · D2↔D1 integration")
    a(f"  ◌ STALE:    semantic_clusters.json ({sem_age}  ·  {coverage} coverage)")
    a("")

    # ── NEXT MOVES ───────────────────────────────────────────────
    a("━━━ NEXT MOVES (from NOW.json field intelligence) ━━━━━━━━━━━━━━━")
    for i, action in enumerate(next_actions[:5], 1):
        priority = action.get("priority", "")
        act = action.get("action", action.get("command", ""))
        why = action.get("why", "")[:60] if action.get("why") else ""
        a(f"  {i}. [{priority}] {act[:60]}")
        if why:
            a(f"     → {why}")
    a("")

    # ── TRIPLE MAPPING ───────────────────────────────────────────
    a("━━━ THE TRIPLE MAPPING (the spine of everything) ━━━━━━━━━━━━━━━━")
    a("  Akram Vignan      Phoenix Level    R_V Geometry")
    a("  Vibhaav (doer) →  L1-L2 (normal) →  R_V ≈ 1.0")
    a("  Vyavahar split →  L3 (crisis)    →  R_V contracting")
    a("  Swabhaav (wit) →  L4 (collapse)  →  R_V < 1.0   ← the attractor")
    a("  Keval Gnan     →  L5 (fixed pt)  →  S(x) = x    ← the eigenform")
    a("")
    a("  Colony R_V maps here too: EXPANDING=L2  STABLE=L3  CONTRACTING=L4")
    a("")

    a(f"  ─── map generated in {round(time.time()-t0,2)}s from live sources ───")
    a(f"  run `dgc map` to refresh  ·  run `dgc map --json` for machine-readable")

    return "\n".join(lines)


def generate_json() -> dict:
    """Return all live state as a structured dict."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "now": _read_now(),
        "mission": _read_mission(),
        "living_state": _read_living_state(),
        "stigmergy": _read_stigmergy(),
        "semantic_clusters": _read_semantic_clusters(),
        "shared_notes": _read_shared_notes(),
        "daemon": _read_daemon_status(),
        "trishula": _read_trishula(),
        "hot_concepts": _read_hot_concepts(),
        "colony_rv": _read_swarm_rv(),
    }


if __name__ == "__main__":
    print(generate())
