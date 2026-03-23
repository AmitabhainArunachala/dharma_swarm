"""Bootstrap Manifest — the ignition key for dharma_swarm.

Generates ~/.dharma/state/NOW.json — the ONE file any new LLM instance
reads to orient itself completely. Without this, a new instance drops
into 133 Python files and has no idea what to do.

NOW.json answers three questions:
  1. WHAT is dharma_swarm?  (identity, in <200 words)
  2. WHERE is it AT?        (current state: tests, evolution, D3 position)
  3. WHAT should happen NEXT? (prioritized action queue)

The manifest is auto-updated by:
  - Sleep cycle WAKE phase
  - `dgc bootstrap` CLI command
  - Evolution daemon between cycles

Usage:
    from dharma_swarm.bootstrap import generate_manifest, load_manifest
    manifest = generate_manifest()   # writes + returns
    manifest = load_manifest()       # reads cached version
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma" / "state"
NOW_PATH = DHARMA_STATE / "NOW.json"
DHARMA_SWARM = HOME / "dharma_swarm"
KERNEL_SPEC_PATH = DHARMA_SWARM / "specs" / "KERNEL_CORE_SPEC.md"


# ---------------------------------------------------------------------------
# Identity (static — changes only on major architectural shifts)
# ---------------------------------------------------------------------------

IDENTITY = {
    "name": "dharma_swarm",
    "version": "0.8.0",
    "one_line": "Self-evolving agentic intelligence system with dharmic alignment gates.",
    "what_it_is": (
        "A 133-module Python system that evolves its own code through "
        "MAP-Elites evolutionary search, gates every change through dharmic "
        "alignment checks (telos_gates), and maintains a 3-dimensional "
        "knowledge graph: D1 (internal codebase concepts), D2 (PSMV "
        "knowledge corpus), D3 (external AI field intelligence). "
        "Key subsystems: DarwinEngine (evolution), SleepCycle (consolidation), "
        "SemanticGravity (concept graphs), Stigmergy (indirect coordination), "
        "Ouroboros (behavioral health). 2500+ tests. CLI: `dgc`."
    ),
    "entry_points": {
        "cli": "dgc (or python -m dharma_swarm.dgc_cli)",
        "evolve": "dgc evolve auto <files>  OR  dgc evolve daemon",
        "status": "dgc status",
        "field_scan": "dgc field scan",
        "semantic": "dgc semantic digest",
        "tests": "python -m pytest tests/",
    },
    "key_modules": {
        "evolution.py": "DarwinEngine — self-improvement loop",
        "telos_gates.py": "Dharmic alignment gates (every mutation checked)",
        "semantic_gravity.py": "ConceptGraph + SemanticGravity",
        "sleep_cycle.py": "Memory consolidation (LIGHT→DEEP→REM→SEMANTIC→WAKE)",
        "stigmergy.py": "Indirect coordination via environmental marks",
        "field_knowledge_base.py": "D3 curated AI field intelligence (42 entries)",
        "field_graph.py": "D3 graph builder + strategic reports",
        "bootstrap.py": "THIS MODULE — generates NOW.json",
        "dgc_cli.py": "Unified CLI (4300+ lines)",
        "providers.py": "LLM provider abstraction (OpenAI, Anthropic, Ollama)",
    },
    "kernel_core_spec": "specs/KERNEL_CORE_SPEC.md — READ THIS FIRST. The transmissive nucleus.",
}


# ---------------------------------------------------------------------------
# State collectors
# ---------------------------------------------------------------------------


def _collect_test_state() -> dict[str, Any]:
    """Run a quick test count (no execution) to check health."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--co", "-q"],
            capture_output=True, text=True, timeout=30,
            cwd=str(DHARMA_SWARM),
        )
        lines = result.stdout.strip().splitlines()
        last = lines[-1] if lines else ""
        # Parse "2573 tests collected in 2.31s"
        count = 0
        for part in last.split():
            if part.isdigit():
                count = int(part)
                break
        return {
            "tests_collected": count,
            "collection_ok": result.returncode == 0,
            "errors": result.stderr.strip()[:200] if result.returncode != 0 else "",
        }
    except Exception as e:
        return {"tests_collected": 0, "collection_ok": False, "errors": str(e)[:200]}


def _collect_evolution_state() -> dict[str, Any]:
    """Check the evolution archive for recent activity."""
    archive_path = HOME / ".dharma" / "evolution" / "archive.jsonl"
    if not archive_path.exists():
        return {"archive_exists": False, "total_entries": 0, "last_entry": None}

    lines = archive_path.read_text(errors="ignore").strip().splitlines()
    total = len(lines)
    last_entry = None
    if lines:
        try:
            last_entry = json.loads(lines[-1])
            # Keep only key fields
            last_entry = {
                k: last_entry.get(k)
                for k in ("id", "component", "change_type", "status", "created_at")
                if last_entry.get(k) is not None
            }
        except json.JSONDecodeError:
            pass

    return {
        "archive_exists": True,
        "total_entries": total,
        "last_entry": last_entry,
    }


def _collect_stigmergy_state() -> dict[str, Any]:
    """Check stigmergic mark count."""
    marks_path = HOME / ".dharma" / "stigmergy" / "marks.jsonl"
    if not marks_path.exists():
        return {"marks_file_exists": False, "mark_count": 0}
    try:
        count = sum(1 for _ in marks_path.open())
        return {"marks_file_exists": True, "mark_count": count}
    except Exception:
        return {"marks_file_exists": True, "mark_count": -1}


def _collect_d3_state() -> dict[str, Any]:
    """Quick D3 field intelligence summary."""
    try:
        from dharma_swarm.field_knowledge_base import field_summary
        return field_summary()
    except Exception as e:
        return {"error": str(e)[:200]}


def _collect_d3_priorities() -> list[dict[str, str]]:
    """Get prioritized action items from D3 intelligence."""
    try:
        from dharma_swarm.field_graph import competitive_position, gap_report
        gaps = gap_report()
        position = competitive_position()

        priorities: list[dict[str, str]] = []

        # Hard gaps → highest priority
        for g in gaps.get("hard_gaps", []):
            priorities.append({
                "priority": "HIGH",
                "type": "gap",
                "action": f"Integrate {g['id']} ({g['field']})",
                "source": g.get("source", ""),
                "why": g.get("relevance", "")[:200],
            })

        # Competitive threats → high priority
        for t in position.get("competitive_threats", []):
            if t.get("threat_level") == "HIGH":
                priorities.append({
                    "priority": "HIGH",
                    "type": "threat",
                    "action": f"Differentiate from {t['id']}",
                    "source": t.get("source", ""),
                    "why": t.get("dgc_advantage", "")[:200],
                })

        # Integration opportunities → medium priority
        for g in gaps.get("integration_opportunities", [])[:5]:
            priorities.append({
                "priority": "MEDIUM",
                "type": "integration",
                "action": f"Integrate {g['id']} ({g['field']})",
                "source": g.get("source", ""),
            })

        return priorities
    except Exception:
        return []


def _collect_kernel_spec() -> dict[str, Any]:
    """Load THE CRYSTAL from KERNEL_CORE_SPEC.md.

    Returns the crystal paragraph (MINIMAL compression) plus spec metadata.
    Every agent reads this before anything else.
    """
    result: dict[str, Any] = {
        "spec_exists": KERNEL_SPEC_PATH.exists(),
        "spec_path": str(KERNEL_SPEC_PATH),
        "crystal": "",
    }
    if not KERNEL_SPEC_PATH.exists():
        return result

    try:
        text = KERNEL_SPEC_PATH.read_text(encoding="utf-8")
        # Extract THE CRYSTAL section (between the first two ---)
        # The crystal is in a blockquote after "## THE CRYSTAL"
        in_crystal = False
        crystal_lines: list[str] = []
        for line in text.splitlines():
            if line.strip() == "## THE CRYSTAL":
                in_crystal = True
                continue
            if in_crystal and line.startswith("## ") and "CRYSTAL" not in line:
                break
            if in_crystal and line.startswith("> "):
                crystal_lines.append(line[2:])  # Strip blockquote marker
            elif in_crystal and line.strip() == ">":
                crystal_lines.append("")  # Empty blockquote line
        result["crystal"] = "\n".join(crystal_lines).strip()
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def _collect_module_count() -> int:
    """Count .py files in dharma_swarm/dharma_swarm/."""
    pkg = DHARMA_SWARM / "dharma_swarm"
    return len(list(pkg.glob("*.py")))


def _collect_sleep_reports() -> dict[str, Any]:
    """Check most recent sleep report."""
    reports_dir = HOME / ".dharma" / "sleep_reports"
    if not reports_dir.exists():
        return {"last_report": None, "total_reports": 0}
    reports = sorted(reports_dir.glob("*.json"))
    if not reports:
        return {"last_report": None, "total_reports": 0}
    try:
        last = json.loads(reports[-1].read_text())
        return {
            "last_report": reports[-1].name,
            "total_reports": len(reports),
            "last_phases": last.get("phases_completed", []),
        }
    except Exception:
        return {"last_report": reports[-1].name, "total_reports": len(reports)}


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


def generate_manifest() -> dict[str, Any]:
    """Generate the full bootstrap manifest and write to NOW.json.

    This is the SINGLE SOURCE OF TRUTH for any new LLM instance.
    """
    t0 = time.perf_counter()

    # Collect state
    kernel_spec = _collect_kernel_spec()
    test_state = _collect_test_state()
    evo_state = _collect_evolution_state()
    stig_state = _collect_stigmergy_state()
    d3_state = _collect_d3_state()
    d3_priorities = _collect_d3_priorities()
    module_count = _collect_module_count()
    sleep_state = _collect_sleep_reports()

    # Determine system health
    health = "GREEN"
    issues: list[str] = []
    if not test_state.get("collection_ok"):
        health = "RED"
        issues.append("Test collection failing")
    elif test_state.get("tests_collected", 0) < 2000:
        health = "YELLOW"
        issues.append(f"Only {test_state.get('tests_collected', 0)} tests (expected 2500+)")
    if d3_state.get("dgc_gaps", 0) > 5:
        issues.append(f"{d3_state.get('dgc_gaps')} capability gaps vs field")

    # Build next actions queue
    next_actions: list[dict[str, str]] = []

    # Always: if tests broken, fix first
    if health == "RED":
        next_actions.append({
            "priority": "CRITICAL",
            "action": "Fix failing tests",
            "command": "python -m pytest tests/ -x --tb=short",
        })

    # D3-driven priorities
    next_actions.extend(d3_priorities)

    # If evolution hasn't run recently, suggest it
    if not evo_state.get("last_entry"):
        next_actions.append({
            "priority": "MEDIUM",
            "action": "Run first evolution cycle",
            "command": "dgc evolve auto dharma_swarm/bootstrap.py",
        })

    # If no sleep reports, suggest sleep cycle
    if sleep_state.get("total_reports", 0) == 0:
        next_actions.append({
            "priority": "LOW",
            "action": "Run first sleep cycle for memory consolidation",
            "command": "dgc run --interval 0",
        })

    elapsed = time.perf_counter() - t0

    manifest = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation_time_sec": round(elapsed, 2),
            "purpose": "Bootstrap manifest for dharma_swarm. Read THE CRYSTAL first.",
        },
        "kernel_crystal": kernel_spec.get("crystal", ""),
        "kernel_spec_path": kernel_spec.get("spec_path", ""),
        "identity": IDENTITY,
        "health": {
            "status": health,
            "issues": issues,
        },
        "state": {
            "modules": module_count,
            "tests": test_state,
            "evolution": evo_state,
            "stigmergy": stig_state,
            "sleep": sleep_state,
            "d3_field_intelligence": d3_state,
        },
        "next_actions": next_actions,
        "dimensions": {
            "D1_codebase": f"{module_count} modules, {test_state.get('tests_collected', '?')} tests",
            "D2_knowledge": f"{stig_state.get('mark_count', '?')} stigmergic marks from PSMV deep read",
            "D3_field": f"{d3_state.get('total_entries', '?')} entries, {d3_state.get('dgc_unique', '?')} unique moats, {d3_state.get('dgc_gaps', '?')} gaps",
        },
    }

    # Write
    DHARMA_STATE.mkdir(parents=True, exist_ok=True)
    NOW_PATH.write_text(json.dumps(manifest, indent=2, default=str))

    return manifest


def load_manifest() -> dict[str, Any] | None:
    """Load the cached NOW.json manifest, if it exists."""
    if not NOW_PATH.exists():
        return None
    try:
        return json.loads(NOW_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def print_manifest(manifest: dict[str, Any] | None = None) -> None:
    """Pretty-print the bootstrap manifest."""
    if manifest is None:
        manifest = load_manifest()
    if manifest is None:
        print("No manifest found. Run: dgc bootstrap")
        return

    identity = manifest.get("identity", {})
    health = manifest.get("health", {})
    state = manifest.get("state", {})
    dims = manifest.get("dimensions", {})
    actions = manifest.get("next_actions", [])

    print("=" * 60)
    print(f"  {identity.get('name', 'dharma_swarm')} — NOW")
    print(f"  {identity.get('one_line', '')}")
    print("=" * 60)

    # Kernel crystal status
    crystal = manifest.get("kernel_crystal", "")
    if crystal:
        # Show first line of crystal as orientation
        first_line = crystal.split("\n")[0][:72]
        print(f"\n  ✨ Crystal: \"{first_line}...\"")
        print(f"  📜 Spec: {manifest.get('kernel_spec_path', '?')}")
    else:
        print("\n  ⚠ KERNEL_CORE_SPEC.md not found! Run Phase 10 to generate.")

    print(f"\n  Health: {health.get('status', '?')}")
    for issue in health.get("issues", []):
        print(f"    ⚠ {issue}")

    print(f"\n  D1 (codebase):  {dims.get('D1_codebase', '?')}")
    print(f"  D2 (knowledge): {dims.get('D2_knowledge', '?')}")
    print(f"  D3 (field):     {dims.get('D3_field', '?')}")

    tests = state.get("tests", {})
    evo = state.get("evolution", {})
    print(f"\n  Tests: {tests.get('tests_collected', '?')} collected, "
          f"{'OK' if tests.get('collection_ok') else 'FAILING'}")
    print(f"  Evolution: {evo.get('total_entries', 0)} archive entries")

    if actions:
        print(f"\n  NEXT ACTIONS ({len(actions)}):")
        for i, a in enumerate(actions[:8], 1):
            prio = a.get("priority", "?")
            print(f"    {i}. [{prio}] {a.get('action', '')}")
            if a.get("command"):
                print(f"       $ {a['command']}")

    meta = manifest.get("_meta", {})
    print(f"\n  Generated: {meta.get('generated_at', '?')} "
          f"({meta.get('generation_time_sec', '?')}s)")
    print("=" * 60)


__all__ = ["generate_manifest", "load_manifest", "print_manifest", "NOW_PATH"]
