#!/usr/bin/env python3
"""Overnight Summary Generator — aggregates all daemon output into morning brief.

Designed to run at 04:00 via the overnight launcher. Produces a single
markdown file at ~/.dharma/overnight/YYYY-MM-DD-summary.md that Dhyana
reads at 04:30.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


STATE_DIR = Path.home() / ".dharma"
OVERNIGHT_DIR = STATE_DIR / "overnight"
DATE = datetime.now().strftime("%Y-%m-%d")


def count_lines(path: Path) -> int:
    """Count lines in a file, 0 if missing."""
    try:
        return sum(1 for _ in open(path))
    except Exception:
        return 0


def read_json_lines(path: Path, since_hours: float = 12) -> list[dict]:
    """Read JSONL entries from last N hours."""
    cutoff = datetime.now(timezone.utc).timestamp() - (since_hours * 3600)
    entries = []
    try:
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entries.append(entry)
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        pass
    return entries


def garden_summary() -> str:
    """Summarize Garden Daemon overnight output."""
    garden_dir = STATE_DIR / "garden"
    cycles = sorted(garden_dir.glob("cycle_*.json")) if garden_dir.exists() else []
    recent = [c for c in cycles if c.name >= f"cycle_{DATE}"]

    seeds_path = STATE_DIR / "seeds" / "seeds.json"
    seed_count = 0
    if seeds_path.exists():
        try:
            seeds = json.loads(seeds_path.read_text())
            seed_count = len(seeds) if isinstance(seeds, list) else 0
        except Exception:
            pass

    dreams_path = STATE_DIR / "subconscious" / "dream_associations.jsonl"
    dream_count = count_lines(dreams_path)

    return f"""### Garden Daemon
- Cycles tonight: {len(recent)}
- Total seeds: {seed_count}
- Total dream associations: {dream_count}
- Latest cycle: {recent[-1].name if recent else 'none'}"""


def dgc_summary() -> str:
    """Summarize DGC orchestrate-live output."""
    evo_path = STATE_DIR / "evolution" / "archive.jsonl"
    evo_entries = read_json_lines(evo_path, since_hours=12)

    stig_path = STATE_DIR / "stigmergy" / "marks.jsonl"
    stig_count = count_lines(stig_path)

    # Check organism coherence from logs
    log_path = STATE_DIR / "logs" / "orchestrate_overnight.log"
    coherence_lines = []
    if log_path.exists():
        try:
            for line in open(log_path):
                if "blended=" in line and DATE in line:
                    coherence_lines.append(line.strip())
        except Exception:
            pass

    last_coherence = "unknown"
    if coherence_lines:
        last = coherence_lines[-1]
        if "blended=" in last:
            try:
                last_coherence = last.split("blended=")[1].split()[0].rstrip(",|")
            except Exception:
                pass

    return f"""### DGC Orchestrate-Live
- Evolution cycles (12h): {len(evo_entries)}
- Stigmergy marks total: {stig_count}
- Coherence readings tonight: {len(coherence_lines)}
- Latest coherence: {last_coherence}"""


def replication_summary() -> str:
    """Summarize replication protocol activity."""
    proposals_path = STATE_DIR / "replication" / "proposals.jsonl"
    proposals = read_json_lines(proposals_path)

    materialized = sum(1 for p in proposals if p.get("status") == "materialized")
    failed = sum(1 for p in proposals if p.get("status") == "failed")
    pending = sum(1 for p in proposals if p.get("status") == "proposed")

    roster_path = STATE_DIR / "replication" / "dynamic_roster.json"
    dynamic_count = 0
    if roster_path.exists():
        try:
            roster = json.loads(roster_path.read_text())
            dynamic_count = len(roster) if isinstance(roster, list) else 0
        except Exception:
            pass

    probation_path = STATE_DIR / "replication" / "probation.json"
    in_probation = 0
    if probation_path.exists():
        try:
            prob = json.loads(probation_path.read_text())
            in_probation = sum(1 for v in prob.values() if not v.get("graduated") and not v.get("terminated"))
        except Exception:
            pass

    return f"""### Self-Replication System
- Total proposals: {len(proposals)}
- Materialized: {materialized}
- Failed: {failed}
- Pending: {pending}
- Dynamic agents: {dynamic_count}
- In probation: {in_probation}"""


def mycelium_summary() -> str:
    """Summarize Mycelium daemon output."""
    results_dir = STATE_DIR / "mycelium" / "results"
    result_count = len(list(results_dir.glob("*.json"))) if results_dir.exists() else 0

    return f"""### Mycelium Daemon
- Result files: {result_count}"""


def deep_reading_summary() -> str:
    """Summarize Deep Reading daemon output."""
    annotations_dir = STATE_DIR / "deep_reads" / "annotations"
    annotation_count = len(list(annotations_dir.glob("*.yaml"))) if annotations_dir.exists() else 0

    lodestones_dir = Path.home() / "dharma_swarm" / "lodestones"
    lodestone_count = 0
    if lodestones_dir.exists():
        for ext in ("*.md", "*.yaml", "*.json"):
            lodestone_count += len(list(lodestones_dir.rglob(ext)))

    return f"""### Deep Reading Daemon
- Annotations: {annotation_count}
- Lodestones: {lodestone_count}"""


def learning_summary() -> str:
    """Summarize continuous learning instincts."""
    homunculus = Path.home() / ".claude" / "homunculus"
    obs_path = homunculus / "observations.jsonl"
    obs_count = count_lines(obs_path)

    instinct_dir = homunculus / "instincts" / "personal"
    instinct_count = len(list(instinct_dir.glob("*.yaml"))) if instinct_dir.exists() else 0

    # Check project-scoped instincts
    projects_dir = homunculus / "projects"
    project_instincts = 0
    if projects_dir.exists():
        for proj in projects_dir.iterdir():
            pi = proj / "instincts" / "personal"
            if pi.exists():
                project_instincts += len(list(pi.glob("*.yaml")))

    return f"""### Continuous Learning
- Observations: {obs_count}
- Global instincts: {instinct_count}
- Project-scoped instincts: {project_instincts}"""


def generate_summary() -> str:
    """Generate the full overnight summary."""
    sections = [
        f"# Overnight Summary: {DATE}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        garden_summary(),
        "",
        dgc_summary(),
        "",
        replication_summary(),
        "",
        mycelium_summary(),
        "",
        deep_reading_summary(),
        "",
        learning_summary(),
        "",
        "---",
        "",
        "## Action Items",
        "- [ ] Review any replication proposals that materialized",
        "- [ ] Check organism coherence trend (target > 0.6)",
        "- [ ] Review new instincts for promotion",
        f"- [ ] Check overnight log: `~/.dharma/overnight/{DATE}.log`",
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    summary = generate_summary()
    output_path = OVERNIGHT_DIR / f"{DATE}-summary.md"
    OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary)
    print(summary)
    print(f"\nSaved to: {output_path}")
