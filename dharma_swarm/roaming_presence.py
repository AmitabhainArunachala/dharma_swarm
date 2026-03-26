"""Project roaming mailbox heartbeats into canonical swarm presence surfaces."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import BRIDGE_STATUS_IN_PROGRESS, OperatorBridge
from dharma_swarm.roaming_mailbox import RoamingHeartbeat, RoamingMailbox
from dharma_swarm.telemetry_plane import AgentIdentityRecord, TelemetryPlaneStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dharma_home() -> Path:
    return Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, default=str) + "\n"


def _safe_name(raw: str) -> str:
    return raw.replace("/", "_").replace("\\", "_")


@dataclass(frozen=True)
class PresenceProjectionResult:
    agent_id: str
    recorded_at: str
    projected_status: str
    bridge_task_id: str = ""
    living_agent_path: str = ""
    card_path: str = ""


class RoamingPresenceProjector:
    def __init__(
        self,
        *,
        mailbox: RoamingMailbox,
        bridge: OperatorBridge,
        dharma_home: Path | None = None,
        telemetry: TelemetryPlaneStore | None = None,
        stale_after_seconds: float = 900.0,
    ) -> None:
        self.mailbox = mailbox
        self.bridge = bridge
        self.dharma_home = dharma_home or _dharma_home()
        self.telemetry = telemetry or TelemetryPlaneStore(self.dharma_home / "state" / "runtime.db")
        self.stale_after_seconds = max(60.0, float(stale_after_seconds))

    def _receipt_path(self, agent_id: str) -> Path:
        return self.mailbox.receipts_dir / f"heartbeat.{_safe_name(agent_id)}.projected.json"

    def _load_receipt(self, agent_id: str) -> dict[str, Any]:
        path = self._receipt_path(agent_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_receipt(self, agent_id: str, payload: dict[str, Any]) -> None:
        self._receipt_path(agent_id).write_text(_json_dump(payload), encoding="utf-8")

    def _living_agent_path(self, agent_id: str) -> Path:
        return self.dharma_home / "agents" / agent_id / "living_agent.json"

    def _card_path(self, callsign: str) -> Path:
        return self.dharma_home / "a2a" / "cards" / f"{_safe_name(callsign)}.json"

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dump(payload), encoding="utf-8")

    def _projected_status(self, heartbeat: RoamingHeartbeat) -> str:
        recorded = _parse_dt(heartbeat.recorded_at) or _utc_now()
        age = (_utc_now() - recorded).total_seconds()
        if age > self.stale_after_seconds:
            return "stale"
        return heartbeat.status or "online"

    async def _project_bridge_progress(self, heartbeat: RoamingHeartbeat) -> str:
        mailbox_task_id = heartbeat.current_task_id.strip()
        if not mailbox_task_id:
            return ""
        task = self.mailbox.load_task(mailbox_task_id)
        bridge_task_id = str(task.metadata.get("bridge_task_id", "")).strip()
        if not bridge_task_id:
            return ""
        bridge_task = await self.bridge.get_task(bridge_task_id)
        if bridge_task is None or bridge_task.status != BRIDGE_STATUS_IN_PROGRESS:
            return bridge_task_id
        await self.bridge.heartbeat_task(
            task_id=bridge_task_id,
            heartbeat_by=heartbeat.agent_id,
            summary=heartbeat.summary,
            progress=heartbeat.progress,
            metadata={
                "mailbox_task_id": mailbox_task_id,
                "roaming_status": heartbeat.status,
                **dict(heartbeat.metadata),
            },
        )
        return bridge_task_id

    async def project_heartbeat(self, heartbeat: RoamingHeartbeat) -> PresenceProjectionResult | None:
        receipt = self._load_receipt(heartbeat.agent_id)
        if receipt.get("recorded_at") == heartbeat.recorded_at:
            return None

        projected_status = self._projected_status(heartbeat)
        living_agent_path = self._living_agent_path(heartbeat.agent_id)
        dock = self._load_json(living_agent_path)
        if dock:
            dock["status"] = projected_status
            dock["last_seen_at"] = heartbeat.recorded_at
            metadata = dict(dock.get("metadata") or {})
            metadata["last_roaming_heartbeat"] = heartbeat.to_dict()
            dock["metadata"] = metadata
            dock["updated_at"] = _utc_now().isoformat()
            self._write_json(living_agent_path, dock)

        card_path = self._card_path(heartbeat.callsign or heartbeat.agent_id)
        card = self._load_json(card_path)
        if card:
            card["status"] = projected_status
            card["updated_at"] = _utc_now().isoformat()
            metadata = dict(card.get("metadata") or {})
            metadata["last_roaming_heartbeat"] = heartbeat.to_dict()
            card["metadata"] = metadata
            self._write_json(card_path, card)

        existing_identity = await self.telemetry.get_agent_identity(heartbeat.agent_id)
        if existing_identity is not None:
            await self.telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=existing_identity.agent_id,
                    codename=existing_identity.codename,
                    serial=existing_identity.serial,
                    avatar_id=existing_identity.avatar_id,
                    department=existing_identity.department,
                    squad_id=existing_identity.squad_id,
                    specialization=existing_identity.specialization,
                    level=existing_identity.level,
                    xp=existing_identity.xp,
                    status=projected_status,
                    last_active=_parse_dt(heartbeat.recorded_at) or _utc_now(),
                    metadata=dict(existing_identity.metadata) | {
                        "last_roaming_heartbeat": heartbeat.to_dict(),
                    },
                    created_at=existing_identity.created_at,
                    updated_at=_utc_now(),
                )
            )

        await self.bridge._bus.heartbeat(  # noqa: SLF001 - intentional projection into canonical bus
            heartbeat.agent_id,
            metadata={
                "source": "roaming_mailbox",
                "callsign": heartbeat.callsign,
                "projected_status": projected_status,
                "current_task_id": heartbeat.current_task_id,
                **dict(heartbeat.metadata),
            },
        )

        bridge_task_id = await self._project_bridge_progress(heartbeat)
        self._write_receipt(
            heartbeat.agent_id,
            {
                "agent_id": heartbeat.agent_id,
                "callsign": heartbeat.callsign,
                "recorded_at": heartbeat.recorded_at,
                "projected_status": projected_status,
                "bridge_task_id": bridge_task_id,
                "projected_at": _utc_now().isoformat(),
            },
        )
        return PresenceProjectionResult(
            agent_id=heartbeat.agent_id,
            recorded_at=heartbeat.recorded_at,
            projected_status=projected_status,
            bridge_task_id=bridge_task_id,
            living_agent_path=str(living_agent_path),
            card_path=str(card_path),
        )

    async def project_all(self) -> list[PresenceProjectionResult]:
        results: list[PresenceProjectionResult] = []
        for heartbeat in self.mailbox.list_heartbeats():
            projected = await self.project_heartbeat(heartbeat)
            if projected is not None:
                results.append(projected)
        return results
