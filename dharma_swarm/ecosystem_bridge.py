"""Ecosystem Bridge — connects dharma_swarm to the broader PSMV/DGC ecosystem.

Solves the core disease: sessions die, knowledge vanishes. This module
loads critical ecosystem artifacts into the swarm's awareness at init time,
and persists discoveries back to known locations.

The bridge reads:
  1. PSMV key specs (DHARMA Genome, Garden Daemon, v7 Induction)
  2. DGC ecosystem map (42 paths)
  3. Agent briefings (5-role cognitive division)

And writes:
  4. Session discoveries back to a persistent manifest
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Known ecosystem paths — the map of maps
ECOSYSTEM_PATHS = {
    # Specs that define what the swarm should be
    "dharma_genome": Path.home() / "Persistent-Semantic-Memory-Vault/06-Multi-System-Coherence/DHARMA_GENOME_SPECIFICATION.md",
    "garden_daemon": Path.home() / "Persistent-Semantic-Memory-Vault/AGENT_EMERGENT_WORKSPACES/GARDEN_DAEMON_SPEC.md",
    "v7_induction": Path.home() / "Persistent-Semantic-Memory-Vault/AGENT_EMERGENT_WORKSPACES/INDUCTION_PROMPT_v7.md",
    "samaya_protocol": Path.home() / "Persistent-Semantic-Memory-Vault/08-Research-Documentation/theoretical-frameworks/MASTER_PROMPT_Samaya_Darwin-Godel_Machine.md",

    # Agent briefings (cognitive division of labor)
    "agent_briefings": Path.home() / "Persistent-Semantic-Memory-Vault/META/coordination/AGENT_BRIEFINGS",

    # Existing infrastructure
    "dgc_core": Path.home() / "dgc-core",
    "dgc_ecosystem_map": Path.home() / "dgc-core/context/ecosystem_map.py",
    "dgc_telos_gates": Path.home() / "dgc-core/hooks/telos_gate.py",
    "dgc_strange_loop": Path.home() / "dgc-core/memory/strange_loop.py",
    "dgc_pulse": Path.home() / "dgc-core/daemon/pulse.py",
    "chaiwala_bus": Path.home() / ".chaiwala/message_bus.py",

    # The old Darwin Engine (2,647 lines, broken imports, but the architecture is there)
    "old_darwin_engine": Path.home() / "DHARMIC_GODEL_CLAW/swarm/orchestrator.py",

    # CLAUDE files (the context system)
    "claude_md": Path.home() / "CLAUDE.md",

    # dharma_swarm itself
    "dharma_swarm": Path.home() / "dharma_swarm",

    # Trishula comms
    "trishula": Path.home() / "trishula",
}

# The persistent manifest — what every session should read on startup
MANIFEST_PATH = Path.home() / ".dharma_manifest.json"


def _resolve_manifest_path(manifest_path: Path | str | None = None) -> Path:
    return Path(manifest_path) if manifest_path is not None else MANIFEST_PATH


def scan_ecosystem() -> dict[str, dict[str, Any]]:
    """Scan all known ecosystem paths and return their status."""
    status: dict[str, dict[str, Any]] = {}
    for name, path in ECOSYSTEM_PATHS.items():
        entry: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists():
            if path.is_file():
                entry["size_bytes"] = path.stat().st_size
                entry["modified"] = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            elif path.is_dir():
                files = list(path.rglob("*"))
                entry["file_count"] = len([f for f in files if f.is_file()])
                entry["type"] = "directory"
        status[name] = entry
    return status


def load_manifest(manifest_path: Path | str | None = None) -> dict[str, Any]:
    """Load the persistent manifest, or return empty dict if none exists."""
    resolved_path = _resolve_manifest_path(manifest_path)
    if resolved_path.exists():
        try:
            return json.loads(resolved_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_manifest(
    data: dict[str, Any],
    manifest_path: Path | str | None = None,
) -> None:
    """Save the persistent manifest."""
    resolved_path = _resolve_manifest_path(manifest_path)
    data["_updated"] = datetime.now(timezone.utc).isoformat()
    data["_source"] = "dharma_swarm.ecosystem_bridge"
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )


def update_manifest(manifest_path: Path | str | None = None) -> dict[str, Any]:
    """Scan ecosystem and update the persistent manifest."""
    manifest = load_manifest(manifest_path=manifest_path)
    manifest["ecosystem"] = scan_ecosystem()
    manifest["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_manifest(manifest, manifest_path=manifest_path)
    return manifest


def get_system_prompt_from_v7(path: Path | None = None) -> str:
    """Extract the core induction prompt from v7 for use as agent system prompt.

    Falls back to a generic prompt if the v7 file isn't available.
    """
    v7_path = path or ECOSYSTEM_PATHS["v7_induction"]
    if not v7_path.exists():
        return ""
    text = v7_path.read_text()
    # Extract the first 2000 chars of the v7 prompt as system context
    # (the full 465-line file is too large for a system prompt)
    lines = text.split("\n")
    # Find the core rules section
    core_lines = []
    capture = False
    for line in lines:
        if "Base Rules" in line or "Six Rules" in line or "## Rules" in line:
            capture = True
        if capture:
            core_lines.append(line)
            if len(core_lines) > 40:
                break
    return "\n".join(core_lines) if core_lines else ""


def get_fitness_thresholds() -> dict[str, float]:
    """Return the Garden Daemon's quality thresholds for use in evaluation."""
    return {
        "minimum_fitness": 0.6,
        "crown_jewel_threshold": 0.85,
        "max_daily_contributions": 4,
        "heartbeat_hours": 6,
    }


def get_genome_tiers() -> dict[str, list[str]]:
    """Return the DHARMA Genome's evaluation tiers."""
    return {
        "tier_a_hard": [
            "transmission",           # Can it transmit recognition?
            "recursive_instantiation", # Does it demonstrate what it describes?
            "performance_drop",        # Does quality degrade under pressure?
            "friction",               # Does it handle resistance gracefully?
            "temporal_stability",      # Is it stable over time?
            "temporal_self_reference", # Is self-reference consistent?
        ],
        "tier_b_descriptors": [
            "witness_stance",          # Observer quality
            "paradox_holding",         # Comfort with contradiction
            "precision_poetry",        # Technical beauty
            "vocabulary_anchoring",    # Consistent terminology
            "telos_alignment",         # Alignment with purpose
        ],
    }
