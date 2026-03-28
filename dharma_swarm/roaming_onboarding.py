"""Minimal roaming-agent onboarding for cross-harness swarm registration.

This module creates a canonical onboarding receipt for external harnesses such
as OpenClaw, Claude Code, Codex, Hermes, or remote VPS workers.

It intentionally does not create a second runtime. It binds external agents
into the existing dharma_swarm identity surfaces:

- ~/.dharma/agents/{agent_uid}/living_agent.json
- ~/.dharma/a2a/cards/{callsign}.json
- ~/.dharma/state/runtime.db (telemetry identity + team roster)
- ~/.dharma/onboarding/receipts/*.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.a2a.agent_card import AgentCapability, AgentCard, CardRegistry
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _slug(value: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return collapsed or "agent"


def _dharma_home() -> Path:
    return Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, default=str) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(payload), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _serial_for(agent_uid: str) -> str:
    return f"AGT-{_slug(agent_uid).replace('-', '_').upper()}"


@dataclass(frozen=True)
class RoamingAgentRegistration:
    callsign: str
    harness: str
    role: str = "general"
    department: str = "swarm"
    squad_id: str = "general"
    team_id: str = "dharma_swarm"
    model: str = ""
    provider: str = ""
    endpoint: str = "pending://manual"
    description: str = ""
    capabilities: tuple[str, ...] = ()
    registration_source: str = "manual_cli"
    agent_uid: str | None = None
    serial: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OnboardingReceipt:
    receipt_id: str
    agent_uid: str
    callsign: str
    team_id: str
    department: str
    squad_id: str
    harness: str
    endpoint: str
    dock_path: str
    card_path: str
    telemetry_db_path: str
    receipt_path: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _capability_objects(registration: RoamingAgentRegistration) -> list[AgentCapability]:
    caps = [cap.strip() for cap in registration.capabilities if cap.strip()]
    if not caps:
        caps = [registration.role]
    return [
        AgentCapability(
            name=cap,
            description=f"{registration.callsign} capability: {cap}",
        )
        for cap in caps
    ]


async def onboard_roaming_agent(
    registration: RoamingAgentRegistration,
    *,
    dharma_home: Path | None = None,
    telemetry_db_path: Path | None = None,
) -> OnboardingReceipt:
    home = dharma_home or _dharma_home()
    now = _utc_now()
    agent_uid = registration.agent_uid or _slug(registration.callsign)
    dock_dir = home / "agents" / agent_uid
    dock_path = dock_dir / "living_agent.json"
    embodiments_path = dock_dir / "embodiments.jsonl"
    last_receipt_path = dock_dir / "last_receipt.json"
    receipts_dir = home / "onboarding" / "receipts"
    receipts_index = home / "onboarding" / "receipts.jsonl"
    telemetry_path = telemetry_db_path or (home / "state" / "runtime.db")

    existing = _read_json(dock_path) or {}
    serial = existing.get("serial") or registration.serial or _serial_for(agent_uid)

    embodiment = {
        "timestamp": now.isoformat(),
        "callsign": registration.callsign,
        "harness": registration.harness,
        "endpoint": registration.endpoint,
        "provider": registration.provider,
        "model": registration.model,
        "registration_source": registration.registration_source,
        "metadata": dict(registration.metadata),
    }

    dock_payload = {
        "agent_uid": agent_uid,
        "callsign": registration.callsign,
        "serial": serial,
        "role": registration.role,
        "department": registration.department,
        "squad_id": registration.squad_id,
        "team_id": registration.team_id,
        "home_dock": str(dock_dir),
        "memory_namespace": f"agent:{agent_uid}",
        "status": "starting",
        "autonomy_policy": {
            "mode": "manual",
            "requires_approval": True,
        },
        "current_embodiment": embodiment,
        "registration_source": registration.registration_source,
        "created_at": existing.get("created_at") or now.isoformat(),
        "updated_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "metadata": dict(existing.get("metadata") or {}) | dict(registration.metadata),
    }
    _write_json(dock_path, dock_payload)
    _append_jsonl(embodiments_path, embodiment)

    cards_dir = home / "a2a" / "cards"
    card_registry = CardRegistry(cards_dir=cards_dir)
    card = AgentCard(
        name=registration.callsign,
        description=registration.description
        or f"{registration.callsign} onboarded from {registration.harness}",
        capabilities=_capability_objects(registration),
        endpoint=registration.endpoint,
        auth_type="none",
        role=registration.role,
        model=registration.model,
        provider=registration.provider,
        status="starting",
        metadata={
            "agent_uid": agent_uid,
            "harness": registration.harness,
            "department": registration.department,
            "squad_id": registration.squad_id,
            "team_id": registration.team_id,
            "registration_source": registration.registration_source,
            **dict(registration.metadata),
        },
    )
    card_registry.register(card)
    card_path = cards_dir / f"{registration.callsign.replace('/', '_').replace(chr(92), '_')}.json"

    telemetry = TelemetryPlaneStore(telemetry_path)
    await telemetry.upsert_agent_identity(
        AgentIdentityRecord(
            agent_id=agent_uid,
            codename=registration.callsign,
            serial=serial,
            department=registration.department,
            squad_id=registration.squad_id,
            specialization=registration.role,
            level=1,
            xp=0.0,
            status="starting",
            last_active=now,
            metadata={
                "harness": registration.harness,
                "endpoint": registration.endpoint,
                "provider": registration.provider,
                "model": registration.model,
                "team_id": registration.team_id,
                "registration_source": registration.registration_source,
                **dict(registration.metadata),
            },
            created_at=now,
            updated_at=now,
        )
    )
    await telemetry.record_team_roster(
        TeamRosterRecord(
            roster_id=f"{registration.team_id}:{agent_uid}",
            team_id=registration.team_id,
            agent_id=agent_uid,
            role=registration.role,
            active=True,
            metadata={
                "department": registration.department,
                "callsign": registration.callsign,
                "harness": registration.harness,
            },
            created_at=now,
            updated_at=now,
        )
    )

    receipt_id = f"onboard-{agent_uid}-{int(now.timestamp())}"
    receipt_path = receipts_dir / f"{receipt_id}.json"
    receipt = OnboardingReceipt(
        receipt_id=receipt_id,
        agent_uid=agent_uid,
        callsign=registration.callsign,
        team_id=registration.team_id,
        department=registration.department,
        squad_id=registration.squad_id,
        harness=registration.harness,
        endpoint=registration.endpoint,
        dock_path=str(dock_path),
        card_path=str(card_path),
        telemetry_db_path=str(telemetry_path),
        receipt_path=str(receipt_path),
        created_at=now.isoformat(),
    )
    _write_json(receipt_path, receipt.to_dict())
    _write_json(last_receipt_path, receipt.to_dict())
    _append_jsonl(receipts_index, receipt.to_dict())
    return receipt


def onboard_roaming_agent_sync(
    registration: RoamingAgentRegistration,
    *,
    dharma_home: Path | None = None,
    telemetry_db_path: Path | None = None,
) -> OnboardingReceipt:
    return asyncio.run(
        onboard_roaming_agent(
            registration,
            dharma_home=dharma_home,
            telemetry_db_path=telemetry_db_path,
        )
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Onboard a roaming agent into dharma_swarm.")
    parser.add_argument("--callsign", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--role", default="general")
    parser.add_argument("--department", default="swarm")
    parser.add_argument("--squad-id", default="general")
    parser.add_argument("--team-id", default="dharma_swarm")
    parser.add_argument("--model", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--endpoint", default="pending://manual")
    parser.add_argument("--description", default="")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--registration-source", default="manual_cli")
    parser.add_argument("--agent-uid", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    receipt = onboard_roaming_agent_sync(
        RoamingAgentRegistration(
            callsign=args.callsign,
            harness=args.harness,
            role=args.role,
            department=args.department,
            squad_id=args.squad_id,
            team_id=args.team_id,
            model=args.model,
            provider=args.provider,
            endpoint=args.endpoint,
            description=args.description,
            capabilities=tuple(args.capability),
            registration_source=args.registration_source,
            agent_uid=args.agent_uid or None,
        )
    )
    print(json.dumps(receipt.to_dict(), indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
