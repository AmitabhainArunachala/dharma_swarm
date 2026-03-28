#!/usr/bin/env python3
"""Onboard the persistent cybernetics steward roster into the live swarm registry."""

from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm.roaming_onboarding import (
    RoamingAgentRegistration,
    onboard_roaming_agent_sync,
)


STATE_DIR = Path.home() / ".dharma"
TEAM_ID = "cybernetics_directive"
DIRECTIVE_DOC = str(Path.home() / "dharma_swarm" / "docs" / "missions" / "CYBERNETIC_DIRECTIVE.md")


REGISTRATIONS = (
    RoamingAgentRegistration(
        callsign="cyber-glm5",
        agent_uid="cyber-glm5",
        harness="ollama",
        role="researcher",
        department="cybernetics",
        squad_id="directive",
        team_id=TEAM_ID,
        model="glm-5:cloud",
        provider="ollama",
        endpoint="ollama://glm-5:cloud",
        description="Variety cartographer for the Cybernetics Directive.",
        capabilities=("cybernetics", "variety-mapping", "governance-diagnosis"),
        registration_source="cybernetics_directive_bootstrap",
        metadata={
            "thread": "cybernetics",
            "founding_seat": "variety_cartographer",
            "directive_doc": DIRECTIVE_DOC,
        },
    ),
    RoamingAgentRegistration(
        callsign="cyber-kimi25",
        agent_uid="cyber-kimi25",
        harness="ollama",
        role="cartographer",
        department="cybernetics",
        squad_id="directive",
        team_id=TEAM_ID,
        model="kimi-k2.5:cloud",
        provider="ollama",
        endpoint="ollama://kimi-k2.5:cloud",
        description="System mapper for the Cybernetics Directive.",
        capabilities=("cybernetics", "system-mapping", "cross-module-tracing"),
        registration_source="cybernetics_directive_bootstrap",
        metadata={
            "thread": "cybernetics",
            "founding_seat": "ecosystem_mapper",
            "directive_doc": DIRECTIVE_DOC,
        },
    ),
    RoamingAgentRegistration(
        callsign="cyber-codex",
        agent_uid="cyber-codex",
        harness="ollama",
        role="surgeon",
        department="cybernetics",
        squad_id="directive",
        team_id=TEAM_ID,
        model="qwen3-coder:480b-cloud",
        provider="ollama",
        endpoint="ollama://qwen3-coder:480b-cloud",
        description="Execution and wiring seat for the Cybernetics Directive.",
        capabilities=("cybernetics", "runtime-wiring", "hot-path-fixes"),
        registration_source="cybernetics_directive_bootstrap",
        metadata={
            "thread": "cybernetics",
            "founding_seat": "execution_surgeon",
            "directive_doc": DIRECTIVE_DOC,
        },
    ),
    RoamingAgentRegistration(
        callsign="cyber-opus",
        agent_uid="cyber-opus",
        harness="ollama",
        role="architect",
        department="cybernetics",
        squad_id="directive",
        team_id=TEAM_ID,
        model="deepseek-v3.2:cloud",
        provider="ollama",
        endpoint="ollama://deepseek-v3.2:cloud",
        description="Identity and architecture seat for the Cybernetics Directive.",
        capabilities=("cybernetics", "constitutional-design", "telos-governance"),
        registration_source="cybernetics_directive_bootstrap",
        metadata={
            "thread": "cybernetics",
            "founding_seat": "constitutional_architect",
            "directive_doc": DIRECTIVE_DOC,
        },
    ),
)


def main() -> int:
    receipts = []
    for registration in REGISTRATIONS:
        receipt = onboard_roaming_agent_sync(registration, dharma_home=STATE_DIR)
        receipts.append(receipt.to_dict())
        print(f"onboarded: {registration.callsign} -> {receipt.receipt_path}")

    latest = STATE_DIR / "shared" / "cybernetics_stewards_latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({"team_id": TEAM_ID, "receipts": receipts}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
