#!/usr/bin/env python3
"""
generate_data.py - Build sessions.json and cross_pollinations.json from real conversation logs.

Reads from ~/.dharma/conversation_log/*.jsonl and extracts:
- Session IDs, timestamps, durations
- Working directories (to infer agent context)
- User prompts (to extract concepts via keyword matching)
- Files referenced in prompts

If no real data is available, falls back to the bundled mock sessions.json.

Usage:
    python3 generate_data.py                  # auto-detect real data
    python3 generate_data.py --mock           # force mock data
    python3 generate_data.py --days 7         # only last N days
    python3 generate_data.py --min-duration 5 # minimum session duration in minutes

Output:
    ./sessions.json
    ./cross_pollinations.json
"""

import json
import os
import sys
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_DIR = Path.home() / ".dharma" / "conversation_log"
OUTPUT_DIR = Path(__file__).parent
SESSIONS_FILE = OUTPUT_DIR / "sessions.json"
XP_FILE = OUTPUT_DIR / "cross_pollinations.json"

# --- Concept extraction via keyword groups ---
# Maps concept names to keyword patterns found in user prompts
CONCEPT_KEYWORDS = {
    "self-replication": ["replicat", "genome", "clone", "spawn", "offspring"],
    "telos-gates": ["telos", "gate", "gatekeeper"],
    "stigmergy": ["stigmerg", "pheromone", "marks.jsonl", "mark "],
    "evolution": ["evolv", "darwin", "fitness", "mutation", "selection"],
    "cascade": ["cascade", "strange loop", "L7", "L8", "L9"],
    "graph-nexus": ["graph nexus", "graph_nexus", "unified graph"],
    "lodestone": ["lodestone", "deep reading", "curated feed"],
    "garden-daemon": ["garden daemon", "garden_daemon", "garden.py"],
    "mycelium": ["mycelium", "catalytic graph"],
    "kernel-guard": ["kernel", "axiom", "SHA-256", "signed"],
    "TPP": ["tpp", "transmission prompt", "handoff"],
    "R_V": ["r_v", "rv ", "participation ratio", "mech-interp", "colm"],
    "ginko": ["ginko", "trading", "brier", "P&L", "reconcil"],
    "AGNI": ["agni", "agni-workspace", "157.245"],
    "faceless-empire": ["faceless", "scorsese", "video", "content creation"],
    "ecosystem": ["ecosystem", "health check", "organism"],
    "policy": ["policy", "compiler", "constraint"],
    "consolidation": ["consolidat", "audit", "reconcil"],
    "subconscious": ["subconscious", "hum", "dream"],
    "shakti": ["shakti", "four shaktis", "aurobindo"],
    "daemon": ["daemon", "launchd", "background", "cron"],
    "testing": ["test", "pytest", "coverage", "assert"],
    "spec-forge": ["spec-forge", "spec forge", "spec_forge"],
    "autonomy": ["autonom", "discerning", "viveka"],
    "population-control": ["population", "apoptosis", "cull"],
    "agent-fitness": ["fitness", "agent_runner", "dispatch"],
    "deep-reading": ["deep read", "lodestone", "director"],
    "context": ["context", "CLAUDE.md", "memory"],
    "deployment": ["deploy", "canary", "rollback", "promote"],
    "monitoring": ["monitor", "anomaly", "health", "pulse"],
}

# Agent type inference from session content and working directory
AGENT_HEURISTICS = {
    "opus": ["opus", "deep", "architect", "synthesis", "complex"],
    "sonnet": ["sonnet", "build", "implement", "wire", "create"],
    "haiku": ["haiku", "check", "status", "brief", "scan", "quick"],
}


def parse_args():
    """Minimal arg parsing without argparse for zero-dep simplicity."""
    args = {"mock": False, "days": 30, "min_duration": 10, "max_sessions": 60}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--mock":
            args["mock"] = True
        elif sys.argv[i] == "--days" and i + 1 < len(sys.argv):
            args["days"] = int(sys.argv[i + 1])
            i += 1
        elif sys.argv[i] == "--min-duration" and i + 1 < len(sys.argv):
            args["min_duration"] = int(sys.argv[i + 1])
            i += 1
        elif sys.argv[i] == "--max-sessions" and i + 1 < len(sys.argv):
            args["max_sessions"] = int(sys.argv[i + 1])
            i += 1
        i += 1
    return args


def load_log_entries(days: int) -> list[dict]:
    """Load JSONL log entries from the last N days."""
    entries = []
    if not LOG_DIR.exists():
        return entries

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for f in sorted(LOG_DIR.glob("2026-*.jsonl")):
        # Parse date from filename
        try:
            file_date_str = f.stem  # e.g. "2026-03-22"
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff - timedelta(days=1):
                continue
        except ValueError:
            continue

        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

    return entries


def build_sessions(entries: list[dict], min_duration: int) -> list[dict]:
    """Group log entries by session_id and build session records."""
    session_map: dict[str, dict] = defaultdict(lambda: {
        "timestamps": [],
        "prompts": [],
        "cwd": "",
        "events": [],
    })

    for entry in entries:
        sid = entry.get("session_id")
        if sid is None:
            continue
        sid = str(sid)
        if not sid or sid.startswith("agent:"):
            # Skip agent-internal sessions; focus on user-facing sessions
            # But include if they have substantial content
            if not entry.get("content", ""):
                continue

        ts = entry.get("timestamp", "")
        session_map[sid]["timestamps"].append(ts)
        session_map[sid]["events"].append(entry.get("event", ""))

        if entry.get("cwd"):
            session_map[sid]["cwd"] = entry["cwd"]

        if entry.get("role") == "user" and entry.get("content"):
            content = entry["content"]
            # Skip task notifications (internal plumbing)
            if "<task-notification>" in content:
                continue
            session_map[sid]["prompts"].append(content)

    sessions = []
    for sid, data in session_map.items():
        if not data["timestamps"] or not data["prompts"]:
            continue

        timestamps = sorted(data["timestamps"])
        try:
            first = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
        except (ValueError, IndexError):
            continue

        duration = max(1, int((last - first).total_seconds() / 60))
        if duration < min_duration:
            continue

        # Combine all prompts for concept extraction
        combined_text = " ".join(data["prompts"]).lower()

        # Extract concepts
        concepts = extract_concepts(combined_text)
        if len(concepts) < 1:
            continue

        # Infer agent type
        agent_type = infer_agent_type(combined_text, data["cwd"])

        # Build summary from first substantive prompt (cleaned)
        summary = _clean_summary(data["prompts"], concepts)

        # Estimate files touched from prompt content
        files_touched = estimate_files(combined_text)

        # Estimate tests from keywords
        tests_written = estimate_tests(combined_text)

        # Extract gotchas (lines mentioning problems/bugs/issues)
        gotchas = extract_gotchas(data["prompts"])

        # Stable session ID from hash
        stable_id = "session_" + hashlib.sha256(sid.encode()).hexdigest()[:8]

        sessions.append({
            "id": stable_id,
            "date": first.isoformat(),
            "duration_minutes": duration,
            "agent_type": agent_type,
            "summary": summary,
            "concepts": concepts,
            "files_touched": files_touched,
            "tests_written": tests_written,
            "gotchas": gotchas[:3],  # Cap at 3
        })

    # Sort by date
    sessions.sort(key=lambda s: s["date"])

    # Deduplicate very short sessions in the same minute (agent noise)
    seen_minutes = {}
    deduped = []
    for s in sessions:
        minute_key = s["date"][:16]
        if minute_key in seen_minutes and s["duration_minutes"] < 5:
            continue
        seen_minutes[minute_key] = True
        deduped.append(s)

    return deduped


def _clean_summary(prompts: list[str], concepts: list[str]) -> str:
    """Build a clean summary from prompts. Pick the most informative prompt."""
    import re

    # Find the longest prompt that isn't task-notification noise
    candidates = []
    for p in prompts:
        # Skip noise
        if p.startswith("<") or p.startswith("##") or len(p) < 15:
            continue
        # Skip prompts that are mostly whitespace or control chars
        clean = re.sub(r'\s+', ' ', p).strip()
        if len(clean) < 15:
            continue
        candidates.append(clean)

    if not candidates:
        candidates = [re.sub(r'\s+', ' ', prompts[0]).strip()] if prompts else ["(no summary)"]

    # Score candidates: prefer longer ones that mention concepts
    def score(text):
        s = min(len(text), 200)  # prefer moderate length
        lower = text.lower()
        for c in concepts:
            if c.lower().replace("-", " ") in lower or c.lower().replace("-", "") in lower:
                s += 30
        return s

    best = max(candidates, key=score)

    # Truncate cleanly at sentence boundary if possible
    if len(best) > 180:
        # Try to cut at a period
        cut = best[:180].rfind(".")
        if cut > 80:
            best = best[:cut + 1]
        else:
            best = best[:177] + "..."

    prompt_count = len(prompts)
    if prompt_count > 1:
        best += f" ({prompt_count} prompts in session)"

    return best


def extract_concepts(text: str) -> list[str]:
    """Extract concept tags from combined prompt text."""
    found = []
    for concept, keywords in CONCEPT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                found.append(concept)
                break
    return found


def infer_agent_type(text: str, cwd: str) -> str:
    """Heuristic agent type inference. Default to sonnet."""
    scores = {"opus": 0, "sonnet": 0, "haiku": 0}

    for agent, keywords in AGENT_HEURISTICS.items():
        for kw in keywords:
            if kw in text:
                scores[agent] += 1

    # Short sessions or status checks -> haiku
    if any(w in text for w in ["status", "check", "brief", "scan"]):
        scores["haiku"] += 2

    # Long or complex work -> opus
    if any(w in text for w in ["architect", "synthesis", "research", "paper", "deep"]):
        scores["opus"] += 2

    # dharma_swarm cwd -> likely opus or sonnet
    if "dharma_swarm" in cwd:
        scores["sonnet"] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "sonnet"  # default
    return best


def estimate_files(text: str) -> int:
    """Rough estimate of files touched based on text content."""
    # Count .py, .json, .md, .yaml, .toml mentions
    import re
    matches = re.findall(r'[\w/]+\.\w{2,4}', text)
    return max(1, min(len(set(matches)), 30))


def estimate_tests(text: str) -> int:
    """Rough estimate of tests written."""
    if "test" not in text:
        return 0
    import re
    # Look for numbers near "test"
    matches = re.findall(r'(\d+)\s*tests?', text)
    if matches:
        return max(int(m) for m in matches)
    if "pytest" in text or "test_" in text:
        return 5
    return 0


def extract_gotchas(prompts: list[str]) -> list[str]:
    """Extract gotcha/issue mentions from prompts."""
    gotchas = []
    markers = ["fail", "broken", "bug", "error", "issue", "problem", "fix",
               "wrong", "stale", "blocked", "timeout"]
    for prompt in prompts:
        lower = prompt.lower()
        if any(m in lower for m in markers):
            # Take first sentence as gotcha
            sentence = prompt.split(".")[0].strip()
            if len(sentence) > 10 and len(sentence) < 200:
                gotchas.append(sentence)
    return gotchas


def generate_cross_pollinations(sessions: list[dict]) -> list[dict]:
    """Generate cross-pollination insights for sessions sharing 3+ concepts.

    Limits per-session involvement to MAX_PER_SESSION to prevent one
    mega-session from dominating all cross-pollinations.
    """
    MAX_PER_SESSION = 3  # No session appears in more than 3 XPs
    MAX_TOTAL = 15

    # Build all candidate pairs scored by overlap
    candidates = []
    for i, s1 in enumerate(sessions):
        for j, s2 in enumerate(sessions):
            if j <= i:
                continue
            shared = list(set(s1["concepts"]) & set(s2["concepts"]))
            if len(shared) < 2:
                continue
            candidates.append({
                "s1": s1, "s2": s2,
                "shared": shared,
                "score": len(shared),
            })

    # Sort by overlap count descending, then by date diversity
    candidates.sort(key=lambda c: (-c["score"], c["s1"]["date"]))

    xps = []
    session_counts = defaultdict(int)

    for cand in candidates:
        if len(xps) >= MAX_TOTAL:
            break
        s1_id = cand["s1"]["id"]
        s2_id = cand["s2"]["id"]

        # Enforce per-session cap
        if session_counts[s1_id] >= MAX_PER_SESSION:
            continue
        if session_counts[s2_id] >= MAX_PER_SESSION:
            continue

        insight = synthesize_insight(cand["s1"], cand["s2"], cand["shared"])
        xps.append({
            "id": f"xp_{len(xps) + 1:03d}",
            "source_session": s1_id,
            "target_session": s2_id,
            "shared_concepts": cand["shared"],
            "insight": insight,
            "timestamp": max(cand["s1"]["date"], cand["s2"]["date"]),
        })
        session_counts[s1_id] += 1
        session_counts[s2_id] += 1

    return xps


def synthesize_insight(s1: dict, s2: dict, shared: list[str]) -> str:
    """Generate a synthesized insight from two sessions sharing concepts.

    This is a heuristic template-based approach. For production use,
    pipe these pairs to an LLM for richer synthesis.
    """
    concept_str = ", ".join(shared[:4])  # Cap displayed concepts at 4

    # Use clean summary first sentence, truncated
    def short_desc(s):
        text = s["summary"].split(".")[0].strip()
        # Remove prompt count suffix for cleaner display
        text = text.split("(")[0].strip()
        if len(text) > 80:
            text = text[:77] + "..."
        return text

    s1_short = short_desc(s1)
    s2_short = short_desc(s2)

    templates = [
        f"Convergence on [{concept_str}]: '{s1_short}' connects to "
        f"'{s2_short}'. These sessions share structural patterns "
        f"that could be unified.",

        f"Cross-pollination via [{concept_str}]: insights from "
        f"'{s1_short}' may inform '{s2_short}'. "
        f"Shared substrate suggests deeper coupling.",

        f"Pattern bridge [{concept_str}]: {s1['id'][:16]} and "
        f"{s2['id'][:16]} address the same underlying structure "
        f"from different angles. Integration point identified.",
    ]

    # Use hash for deterministic template selection
    h = hash(s1["id"] + s2["id"]) % len(templates)
    return templates[h]


def main():
    args = parse_args()

    if args["mock"]:
        # Copy mock data to active files
        import shutil
        mock_sessions = OUTPUT_DIR / "sessions_mock.json"
        mock_xp = OUTPUT_DIR / "cross_pollinations_mock.json"
        if mock_sessions.exists():
            shutil.copy(mock_sessions, SESSIONS_FILE)
            print(f"  Restored {SESSIONS_FILE} from mock data")
        if mock_xp.exists():
            shutil.copy(mock_xp, XP_FILE)
            print(f"  Restored {XP_FILE} from mock data")
        return

    print(f"Scanning {LOG_DIR} for conversation logs (last {args['days']} days)...")
    entries = load_log_entries(args["days"])

    if not entries:
        print(f"No log entries found in {LOG_DIR}. Keeping existing sessions.json if present.")
        return

    print(f"  Found {len(entries)} log entries")

    sessions = build_sessions(entries, args["min_duration"])
    print(f"  Built {len(sessions)} sessions (min duration: {args['min_duration']}min)")

    # Cap to max_sessions, keeping the most concept-rich ones
    if len(sessions) > args["max_sessions"]:
        sessions.sort(key=lambda s: (-len(s["concepts"]), -s["duration_minutes"]))
        sessions = sessions[:args["max_sessions"]]
        sessions.sort(key=lambda s: s["date"])
        print(f"  Capped to {len(sessions)} sessions (--max-sessions {args['max_sessions']})")

    if len(sessions) < 3:
        print("  Too few sessions for meaningful visualization. Keeping existing data.")
        return

    # Generate cross-pollinations
    xps = generate_cross_pollinations(sessions)
    print(f"  Generated {len(xps)} cross-pollinations")

    # Write output
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)
    print(f"  Wrote {SESSIONS_FILE}")

    with open(XP_FILE, "w") as f:
        json.dump(xps, f, indent=2)
    print(f"  Wrote {XP_FILE}")

    # Summary stats
    total_hours = sum(s["duration_minutes"] for s in sessions) / 60
    agent_counts = defaultdict(int)
    for s in sessions:
        agent_counts[s["agent_type"]] += 1
    concept_freq = defaultdict(int)
    for s in sessions:
        for c in s["concepts"]:
            concept_freq[c] += 1

    print(f"\n  Summary:")
    print(f"    Total hours: {total_hours:.1f}")
    print(f"    Agent distribution: {dict(agent_counts)}")
    print(f"    Top concepts: {sorted(concept_freq.items(), key=lambda x: -x[1])[:8]}")
    print(f"\n  Open index.html in a browser to view the garden.")


if __name__ == "__main__":
    main()
