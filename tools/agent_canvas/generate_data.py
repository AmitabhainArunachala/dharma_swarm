#!/usr/bin/env python3
"""
generate_data.py -- Build agents.json from real dharma_swarm runtime data.

Reads from:
  1. JIKOKU spans:  ~/.dharma/jikoku/JIKOKU_LOG.jsonl
  2. Conductor logs: ~/.dharma/agent_runs/conductor_*_latest.json
  3. Session dirs:   ~/.dharma/sessions/dgc-*/audit.jsonl
  4. Thinkodynamic:  ~/.dharma/jikoku/THINKODYNAMIC_DIRECTOR_LOG.jsonl

Default: writes real data to agents.json (overwrites curated mock).
Falls back to mock generation if no real data sources exist.

Usage:
    python3 generate_data.py            # overwrite agents.json with real data
    python3 generate_data.py --pretty   # pretty-print output
    python3 generate_data.py --mock     # force mock data generation
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

DHARMA = Path.home() / ".dharma"
JIKOKU_LOG = DHARMA / "jikoku" / "JIKOKU_LOG.jsonl"
JIKOKU_PRE = DHARMA / "jikoku" / "JIKOKU_LOG.20260322_pre_rotation.jsonl"
THINKODYNAMIC_LOG = DHARMA / "jikoku" / "THINKODYNAMIC_DIRECTOR_LOG.jsonl"
CONDUCTOR_DIR = DHARMA / "agent_runs"
SESSIONS_DIR = DHARMA / "sessions"
OUTPUT = Path(__file__).parent / "agents.json"

# ---------- Agent registry ----------

AGENT_REGISTRY = [
    {"name": "CONDUCTOR_CLAUDE", "color": "#8B5CF6", "role": "Opus orchestrator"},
    {"name": "CONDUCTOR_CODEX",  "color": "#3B82F6", "role": "Sonnet orchestrator"},
    {"name": "operator",         "color": "#EF4444", "role": "S2+S3 coordination"},
    {"name": "archivist",        "color": "#F59E0B", "role": "S4 memory hygiene"},
    {"name": "research_director","color": "#10B981", "role": "R_V research"},
    {"name": "systems_architect","color": "#6366F1", "role": "118K lines code"},
    {"name": "strategist",       "color": "#EC4899", "role": "Grants, JK, business"},
    {"name": "witness",          "color": "#94A3B8", "role": "S3* sporadic audit"},
]

AGENT_NAMES = {a["name"] for a in AGENT_REGISTRY}

# Map JIKOKU agent_id values to our canonical names
AGENT_ALIAS = {
    "conductor_claude": "CONDUCTOR_CLAUDE",
    "conductor_codex": "CONDUCTOR_CODEX",
    "thinkodynamic_director": "CONDUCTOR_CLAUDE",
    "archeologist": "archivist",
    "cartographer": "operator",
    "researcher": "research_director",
    "architect": "systems_architect",
    "architect-lead": "systems_architect",
    "builder": "systems_architect",
    "surgeon": "systems_architect",
    "validator": "witness",
    "code-reviewer": "witness",
    "test-writer": "witness",
    "scout": "strategist",
    "sentinel": "operator",
}


def resolve_agent(raw: str | None) -> str | None:
    """Map a raw agent_id to a canonical agent name."""
    if not raw:
        return None
    if raw in AGENT_NAMES:
        return raw
    return AGENT_ALIAS.get(raw)


# ---------- JIKOKU span parser ----------

def read_jsonl(path: Path, max_lines: int = 100_000) -> list[dict]:
    """Read a JSONL file, skip bad lines."""
    items = []
    if not path.exists():
        return items
    with open(path, "r") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def parse_jikoku_sessions() -> list[dict]:
    """
    Group JIKOKU spans by (session_id, agent_id) into sessions.
    Each session = contiguous span group for one agent in one swarm session.
    """
    spans = []
    for path in [JIKOKU_LOG, JIKOKU_PRE]:
        spans.extend(read_jsonl(path))

    if not spans:
        return []

    # Group by session_id + resolved agent
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for sp in spans:
        agent = resolve_agent(sp.get("agent_id"))
        if not agent:
            # Try to infer from category / metadata
            meta = sp.get("metadata", {})
            agent_name = meta.get("agent_name")
            if agent_name:
                agent = resolve_agent(agent_name)
        if not agent:
            # Assign unattributed spans to CONDUCTOR_CLAUDE
            cat = sp.get("category", "")
            if cat.startswith("execute.agent_spawn") or cat.startswith("execute.task_create"):
                agent = "CONDUCTOR_CLAUDE"
            else:
                continue

        sid = sp.get("session_id", "unknown")
        groups[(sid, agent)].append(sp)

    sessions = []
    for (sid, agent), sp_list in groups.items():
        # Compute time range
        starts = []
        ends = []
        for sp in sp_list:
            ts_s = sp.get("ts_start")
            ts_e = sp.get("ts_end")
            if ts_s:
                try:
                    starts.append(datetime.fromisoformat(ts_s))
                except (ValueError, TypeError):
                    pass
            if ts_e:
                try:
                    ends.append(datetime.fromisoformat(ts_e))
                except (ValueError, TypeError):
                    pass

        if not starts or not ends:
            continue

        t0 = min(starts)
        t1 = max(ends)
        dur = (t1 - t0).total_seconds()

        # Skip sub-second spans (test artifacts)
        if dur < 5:
            continue

        # Gather intents for summary
        intents = [sp.get("intent", "") for sp in sp_list if sp.get("intent")]
        summary = "; ".join(intents[:3])
        if len(intents) > 3:
            summary += f" (+{len(intents)-3} more)"
        if not summary:
            summary = f"Session {sid[:20]}"

        # Count tasks
        tasks = sum(1 for sp in sp_list if "task" in sp.get("category", ""))
        tokens = 0
        for sp in sp_list:
            meta = sp.get("metadata", {})
            tokens += meta.get("tokens_in", 0) + meta.get("tokens_out", 0)

        # Determine status
        errors = [sp for sp in sp_list if "error" in sp.get("category", "").lower()]
        if errors:
            status = "failed"
        else:
            status = "completed"

        sessions.append({
            "agent": agent,
            "start": t0.isoformat(),
            "end": t1.isoformat(),
            "summary": summary[:200],
            "status": status,
            "tasks": max(tasks, len(sp_list)),
            "tokens": tokens,
        })

    return sessions


# ---------- Conductor log parser ----------

def parse_conductor_logs() -> list[dict]:
    """Parse conductor_*_latest.json files."""
    sessions = []
    if not CONDUCTOR_DIR.exists():
        return sessions

    for path in CONDUCTOR_DIR.glob("conductor_*_latest.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        agent_raw = data.get("agent", "")
        agent = resolve_agent(agent_raw)
        if not agent:
            continue

        ts_val = data.get("timestamp")
        if not ts_val:
            continue

        dt_end = datetime.fromtimestamp(ts_val, tz=timezone.utc)
        dur_s = data.get("duration_s", 0) or 0
        if dur_s < 1:
            dur_s = data.get("turns", 1) * 30  # estimate 30s per turn
        dt_start = dt_end - timedelta(seconds=dur_s)

        summary = data.get("summary", data.get("task", "Conductor session"))
        errors = data.get("errors", [])
        status = "failed" if errors else "completed"

        tokens = (data.get("tokens_in", 0) or 0) + (data.get("tokens_out", 0) or 0)

        sessions.append({
            "agent": agent,
            "start": dt_start.isoformat(),
            "end": dt_end.isoformat(),
            "summary": summary[:200],
            "status": status,
            "tasks": data.get("turns", 1),
            "tokens": tokens,
        })

    return sessions


# ---------- DGC session parser ----------

def parse_dgc_sessions() -> list[dict]:
    """Parse ~/.dharma/sessions/dgc-*/audit.jsonl for session spans."""
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if not session_dir.is_dir() or not session_dir.name.startswith("dgc-"):
            continue

        audit = session_dir / "audit.jsonl"
        if not audit.exists():
            continue

        spans = read_jsonl(audit, max_lines=5000)
        if not spans:
            continue

        # Extract time range
        starts = []
        ends = []
        for sp in spans:
            for key in ("ts_start", "timestamp", "ts"):
                val = sp.get(key)
                if val:
                    try:
                        if isinstance(val, (int, float)):
                            starts.append(datetime.fromtimestamp(val, tz=timezone.utc))
                        else:
                            starts.append(datetime.fromisoformat(val))
                    except (ValueError, TypeError):
                        pass
            for key in ("ts_end",):
                val = sp.get(key)
                if val:
                    try:
                        ends.append(datetime.fromisoformat(val))
                    except (ValueError, TypeError):
                        pass

        if not starts:
            continue
        if not ends:
            ends = starts

        t0 = min(starts)
        t1 = max(ends)

        # Parse session name for date hint: dgc-YYYYMMDD-HHMMSS-XXXX
        parts = session_dir.name.split("-")
        summary = f"DGC session {session_dir.name}"

        sessions.append({
            "agent": "CONDUCTOR_CLAUDE",
            "start": t0.isoformat(),
            "end": t1.isoformat(),
            "summary": summary,
            "status": "completed",
            "tasks": len(spans),
            "tokens": 0,
        })

    return sessions


# ---------- Thinkodynamic director parser ----------

def parse_thinkodynamic() -> list[dict]:
    """Parse thinkodynamic director log."""
    spans = read_jsonl(THINKODYNAMIC_LOG)
    if not spans:
        return []

    groups: dict[str, list[dict]] = defaultdict(list)
    for sp in spans:
        sid = sp.get("session_id", "unknown")
        groups[sid].append(sp)

    sessions = []
    for sid, sp_list in groups.items():
        starts = []
        ends = []
        for sp in sp_list:
            for val in (sp.get("ts_start"), sp.get("ts_end")):
                if val:
                    try:
                        dt = datetime.fromisoformat(val)
                        starts.append(dt)
                        ends.append(dt)
                    except (ValueError, TypeError):
                        pass

        if not starts:
            continue

        t0 = min(starts)
        t1 = max(ends)
        if (t1 - t0).total_seconds() < 5:
            continue

        intents = [sp.get("intent", "") for sp in sp_list if sp.get("intent")]
        summary = "; ".join(intents[:2]) or f"Thinkodynamic session {sid[:16]}"

        sessions.append({
            "agent": "CONDUCTOR_CLAUDE",
            "start": t0.isoformat(),
            "end": t1.isoformat(),
            "summary": f"[Thinkodynamic] {summary[:180]}",
            "status": "completed",
            "tasks": len(sp_list),
            "tokens": 0,
        })

    return sessions


# ---------- Deduplication ----------

def dedup_sessions(sessions: list[dict]) -> list[dict]:
    """Remove near-duplicate sessions (same agent, overlapping times)."""
    sessions.sort(key=lambda s: (s["agent"], s["start"]))
    result = []
    for s in sessions:
        if result and result[-1]["agent"] == s["agent"]:
            prev = result[-1]
            # Check overlap: if this session starts within 2 min of previous end, merge
            try:
                prev_end = datetime.fromisoformat(prev["end"])
                cur_start = datetime.fromisoformat(s["start"])
                if (cur_start - prev_end).total_seconds() < 120:
                    # Merge: extend previous
                    cur_end = datetime.fromisoformat(s["end"])
                    if cur_end > prev_end:
                        prev["end"] = s["end"]
                    prev["tasks"] += s["tasks"]
                    prev["tokens"] += s["tokens"]
                    if s["status"] == "failed":
                        prev["status"] = "failed"
                    prev["summary"] = prev["summary"][:100] + "; " + s["summary"][:80]
                    continue
            except (ValueError, TypeError):
                pass
        result.append(s)
    return result


# ---------- Mock data ----------

def generate_mock() -> dict:
    """Return the bundled mock data from agents.json if it exists, or generate fresh."""
    mock_path = Path(__file__).parent / "agents.json"
    if mock_path.exists():
        try:
            data = json.loads(mock_path.read_text())
            if data.get("sessions"):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    # Fresh mock: generate 25 sessions across Mar 20-24
    import random
    random.seed(42)

    agents = AGENT_REGISTRY[:]
    sessions = []
    base = datetime(2026, 3, 20, tzinfo=timezone.utc)

    for day in range(5):
        day_base = base + timedelta(days=day)
        # Conductors always start at 04:30
        for cond in ["CONDUCTOR_CLAUDE", "CONDUCTOR_CODEX"]:
            start = day_base + timedelta(hours=4, minutes=30 + random.randint(0, 5))
            dur = timedelta(hours=random.uniform(1.5, 3.5))
            tasks = random.randint(5, 18)
            tokens = random.randint(50000, 200000)
            status = "completed" if random.random() > 0.1 else "failed"
            sessions.append({
                "agent": cond,
                "start": start.isoformat(),
                "end": (start + dur).isoformat(),
                "summary": f"Day {day+1} {'orchestration' if cond == 'CONDUCTOR_CLAUDE' else 'code sprint'}",
                "status": status,
                "tasks": tasks,
                "tokens": tokens,
            })

        # Other agents
        for ag_name in ["operator", "archivist", "research_director",
                        "systems_architect", "strategist", "witness"]:
            if random.random() < 0.25:
                continue  # skip some days
            start = day_base + timedelta(hours=random.uniform(5, 10))
            dur = timedelta(minutes=random.uniform(20, 180))
            sessions.append({
                "agent": ag_name,
                "start": start.isoformat(),
                "end": (start + dur).isoformat(),
                "summary": f"{ag_name} session day {day+1}",
                "status": random.choice(["completed", "completed", "completed", "failed"]),
                "tasks": random.randint(2, 12),
                "tokens": random.randint(8000, 160000),
            })

    return {"agents": agents, "sessions": sessions}


# ---------- Main ----------

def main():
    force_mock = "--mock" in sys.argv
    pretty = "--pretty" in sys.argv

    if force_mock:
        data = generate_mock()
        print(f"[mock] Generated {len(data['sessions'])} mock sessions")
    else:
        all_sessions = []

        print("[jikoku] Parsing JIKOKU spans...", end=" ")
        jk = parse_jikoku_sessions()
        print(f"{len(jk)} sessions")
        all_sessions.extend(jk)

        print("[conductor] Parsing conductor logs...", end=" ")
        cl = parse_conductor_logs()
        print(f"{len(cl)} sessions")
        all_sessions.extend(cl)

        print("[dgc] Parsing DGC sessions...", end=" ")
        dgc = parse_dgc_sessions()
        print(f"{len(dgc)} sessions")
        all_sessions.extend(dgc)

        print("[thinkodynamic] Parsing thinkodynamic director...", end=" ")
        td = parse_thinkodynamic()
        print(f"{len(td)} sessions")
        all_sessions.extend(td)

        if not all_sessions:
            print("[fallback] No real data found, generating mock data")
            data = generate_mock()
        else:
            print(f"[dedup] Deduplicating {len(all_sessions)} raw sessions...", end=" ")
            all_sessions = dedup_sessions(all_sessions)
            print(f"{len(all_sessions)} after dedup")
            data = {"agents": AGENT_REGISTRY, "sessions": all_sessions}

    indent = 2 if pretty else None
    OUTPUT.write_text(json.dumps(data, indent=indent, default=str))
    print(f"[done] Wrote {len(data['sessions'])} sessions to {OUTPUT}")


if __name__ == "__main__":
    main()
