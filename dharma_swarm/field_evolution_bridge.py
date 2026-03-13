"""Field Evolution Bridge — D3 gaps → DarwinEngine proposals.

Closes the self-evolution loop:
  1. D3 field scan detects gaps/threats/integration opportunities
  2. THIS MODULE converts them into concrete evolution proposals
  3. DarwinEngine evaluates, gates, tests, archives
  4. System evolves toward closing its own gaps

The bridge reads the bootstrap manifest (NOW.json) to determine
which gaps are highest priority, then generates Proposal objects
that the darwin engine can process.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gap → Proposal templates
# ---------------------------------------------------------------------------

# Each template maps a D3 gap/integration to a concrete code change spec.
# The darwin engine's LLM provider fills in the actual diff.

GAP_TEMPLATES: dict[str, dict[str, Any]] = {
    "saelens": {
        "component": "dharma_swarm/geometric_lens.py",
        "change_type": "mutation",
        "description": (
            "Add SAE (Sparse Autoencoder) integration to geometric_lens. "
            "Import SAELens feature extraction and add a method to measure "
            "R_V contraction in SAE feature space, not just value-projection "
            "space. This gives richer interpretability of recognition states."
        ),
        "spec_ref": "D3:saelens",
        "execution_risk_level": "medium",
    },
    "a2a-google": {
        "component": "dharma_swarm/swarm.py",
        "change_type": "mutation",
        "description": (
            "Add Agent-to-Agent (A2A) protocol compatibility to swarm agents. "
            "Expose agent capabilities as A2A AgentCard, implement task "
            "delegation via A2A Task objects. This enables DGC agents to "
            "interoperate with external agent ecosystems."
        ),
        "spec_ref": "D3:a2a-google",
        "execution_risk_level": "medium",
    },
    "metr-benchmarks": {
        "component": "dharma_swarm/ouroboros.py",
        "change_type": "mutation",
        "description": (
            "Add METR-compatible autonomous task duration benchmarking to "
            "ouroboros behavioral health monitor. Track continuous operation "
            "time, failure recovery patterns, and reliability metrics in a "
            "format compatible with METR's evaluation framework."
        ),
        "spec_ref": "D3:metr-benchmarks",
        "execution_risk_level": "low",
    },
    "anthropic-circuit-tracing": {
        "component": "dharma_swarm/mech_interp_bridge.py",
        "change_type": "mutation",
        "description": (
            "Add attribution graph integration to mech_interp_bridge. "
            "Use Anthropic's circuit tracing methodology to complement "
            "R_V geometric contraction with topological circuit structure. "
            "When available, overlay R_V measurements on attribution graphs."
        ),
        "spec_ref": "D3:anthropic-circuit-tracing",
        "execution_risk_level": "medium",
    },
    "transformerlens": {
        "component": "dharma_swarm/geometric_lens.py",
        "change_type": "mutation",
        "description": (
            "Refactor geometric_lens to optionally use TransformerLens for "
            "cleaner hook-based access to value-projection matrices in open "
            "models. This provides a more robust foundation for R_V measurement."
        ),
        "spec_ref": "D3:transformerlens",
        "execution_risk_level": "medium",
    },
    "sakana-dgm": {
        "component": "dharma_swarm/evolution.py",
        "change_type": "mutation",
        "description": (
            "Strengthen DGC's differentiation from Sakana DGM by adding "
            "explicit dharmic alignment verification to the evolution archive. "
            "Every archived entry should carry a dharmic alignment score "
            "alongside fitness, making it impossible to confuse DGC's approach "
            "with pure benchmark optimization."
        ),
        "spec_ref": "D3:sakana-dgm",
        "execution_risk_level": "low",
    },
}


def proposals_from_manifest(
    manifest: dict[str, Any] | None = None,
    max_proposals: int = 3,
) -> list[dict[str, Any]]:
    """Generate evolution proposals from the bootstrap manifest's next_actions.

    Reads NOW.json's next_actions, matches them against GAP_TEMPLATES,
    and returns Proposal-compatible dicts that can be fed to DarwinEngine.

    Args:
        manifest: Pre-loaded manifest dict, or None to load from disk.
        max_proposals: Maximum number of proposals to generate.

    Returns:
        List of proposal dicts ready for DarwinEngine.submit_proposal().
    """
    if manifest is None:
        from dharma_swarm.bootstrap import load_manifest
        manifest = load_manifest()

    if manifest is None:
        logger.warning("No bootstrap manifest found. Run: dgc bootstrap")
        return []

    actions = manifest.get("next_actions", [])
    proposals: list[dict[str, Any]] = []

    for action in actions:
        if len(proposals) >= max_proposals:
            break

        action_type = action.get("type", "")
        action_text = action.get("action", "")

        # Extract the entry ID from "Integrate saelens (...)" or "Differentiate from sakana-dgm"
        entry_id = None
        for known_id in GAP_TEMPLATES:
            if known_id in action_text.lower() or known_id in action.get("source", "").lower():
                entry_id = known_id
                break

        if entry_id and entry_id in GAP_TEMPLATES:
            template = GAP_TEMPLATES[entry_id]
            proposals.append({
                "component": template["component"],
                "change_type": template["change_type"],
                "description": template["description"],
                "spec_ref": template.get("spec_ref", ""),
                "execution_risk_level": template.get("execution_risk_level", "medium"),
                "metadata": {
                    "source": "field_evolution_bridge",
                    "d3_entry_id": entry_id,
                    "priority": action.get("priority", "MEDIUM"),
                    "action_type": action_type,
                },
            })

    return proposals


def proposals_from_gaps(max_proposals: int = 3) -> list[dict[str, Any]]:
    """Generate proposals directly from D3 gap analysis (no manifest needed).

    Useful when running outside the bootstrap flow.
    """
    try:
        from dharma_swarm.field_graph import gap_report
    except ImportError:
        return []

    gaps = gap_report()
    proposals: list[dict[str, Any]] = []

    # Hard gaps first
    for g in gaps.get("hard_gaps", []):
        if len(proposals) >= max_proposals:
            break
        entry_id = g.get("id", "")
        if entry_id in GAP_TEMPLATES:
            template = GAP_TEMPLATES[entry_id]
            proposals.append({
                "component": template["component"],
                "change_type": template["change_type"],
                "description": template["description"],
                "spec_ref": template.get("spec_ref", ""),
                "execution_risk_level": template.get("execution_risk_level", "medium"),
                "metadata": {
                    "source": "field_evolution_bridge",
                    "d3_entry_id": entry_id,
                    "priority": "HIGH",
                    "action_type": "gap",
                },
            })

    return proposals


def bridge_summary() -> dict[str, Any]:
    """Return summary of what the bridge would propose right now."""
    from_manifest = proposals_from_manifest()
    from_gaps = proposals_from_gaps()

    return {
        "templates_available": len(GAP_TEMPLATES),
        "proposals_from_manifest": len(from_manifest),
        "proposals_from_gaps": len(from_gaps),
        "manifest_proposals": [
            {"component": p["component"], "d3_entry": p["metadata"]["d3_entry_id"]}
            for p in from_manifest
        ],
        "gap_proposals": [
            {"component": p["component"], "d3_entry": p["metadata"]["d3_entry_id"]}
            for p in from_gaps
        ],
    }


__all__ = [
    "proposals_from_manifest",
    "proposals_from_gaps",
    "bridge_summary",
    "GAP_TEMPLATES",
]
