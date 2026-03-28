"""REA temporal runtime primitives for long-horizon autonomous runs.

Adds a durable wait-state model to the existing overnight runtime:
planner/executor work can hibernate around external jobs, budget gates,
or client waits, then resume with the next planned action.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


class EconomicSpoke(str, Enum):
    CODING = "coding"
    RESEARCH_SERVICES = "research_services"
    CONTENT_OPS = "content_ops"
    QUANT_EXPERIMENTAL = "quant_experimental"


class WaitStateKind(str, Enum):
    EXTERNAL_JOB = "external_job"
    CLIENT_REPLY = "client_reply"
    BUDGET_APPROVAL = "budget_approval"
    SLEEP_UNTIL = "sleep_until"


class WaitStateStatus(str, Enum):
    PENDING = "pending"
    RESUMED = "resumed"


class RunProfile(BaseModel):
    profile_id: str
    horizon_hours: float
    primary_spoke: EconomicSpoke
    secondary_spokes: list[EconomicSpoke] = Field(default_factory=list)
    self_evolution_interval_cycles: int = 4
    hibernate_enabled: bool = True
    identity_anchor: str = "dharma_kernel.py"
    notes: str = ""


class TemporalRunManifest(BaseModel):
    run_id: str
    profile: RunProfile
    started_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    current_phase: str = "boot"
    current_cycle: int = 0
    hibernate_count: int = 0
    wake_count: int = 0
    pending_wait_ids: list[str] = Field(default_factory=list)
    last_resume_reason: str = ""


class WaitState(BaseModel):
    wait_id: str = Field(default_factory=_new_id)
    kind: WaitStateKind
    reason: str
    wake_at: datetime
    resume_task_id: str
    resume_goal: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cycle_id: str = ""
    status: WaitStateStatus = WaitStateStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    resumed_at: datetime | None = None
    resume_reason: str = ""


def get_run_profile(profile_id: str) -> RunProfile:
    normalized = str(profile_id or "").strip().lower() or "all_night_build"
    if normalized == "self_evolution_72h":
        return RunProfile(
            profile_id="self_evolution_72h",
            horizon_hours=72.0,
            primary_spoke=EconomicSpoke.CODING,
            secondary_spokes=[
                EconomicSpoke.RESEARCH_SERVICES,
                EconomicSpoke.CONTENT_OPS,
                EconomicSpoke.QUANT_EXPERIMENTAL,
            ],
            self_evolution_interval_cycles=2,
            hibernate_enabled=True,
            notes="Long-horizon harness evolution with coding as the primary spoke.",
        )
    if normalized == "all_night_build":
        return RunProfile(
            profile_id="all_night_build",
            horizon_hours=8.0,
            primary_spoke=EconomicSpoke.CODING,
            secondary_spokes=[
                EconomicSpoke.RESEARCH_SERVICES,
                EconomicSpoke.CONTENT_OPS,
            ],
            self_evolution_interval_cycles=4,
            hibernate_enabled=True,
            notes="Default overnight build lane with bounded economic adjacencies.",
        )
    raise KeyError(f"Unknown run profile: {profile_id}")


class TemporalRunStore:
    """Filesystem-backed state for one long-horizon run."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.manifest_path = self.base_dir / "temporal_manifest.json"
        self.waits_path = self.base_dir / "temporal_waits.jsonl"

    def start_run(self, run_id: str, *, profile: RunProfile) -> TemporalRunManifest:
        manifest = TemporalRunManifest(run_id=run_id, profile=profile)
        self.write_manifest(manifest)
        return manifest

    def load_manifest(self, run_id: str | None = None) -> TemporalRunManifest:
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest = TemporalRunManifest.model_validate(data)
        if run_id and manifest.run_id != run_id:
            raise KeyError(f"Run manifest mismatch: expected {run_id}, found {manifest.run_id}")
        return manifest

    def write_manifest(self, manifest: TemporalRunManifest) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    def update_manifest(self, run_id: str, **changes: Any) -> TemporalRunManifest:
        manifest = self.load_manifest(run_id)
        updated = manifest.model_copy(
            update={**changes, "updated_at": _utc_now()},
        )
        self.write_manifest(updated)
        return updated

    def add_wait_state(self, run_id: str, wait_state: WaitState) -> None:
        manifest = self.load_manifest(run_id)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with self.waits_path.open("a", encoding="utf-8") as handle:
            handle.write(wait_state.model_dump_json() + "\n")
        pending = [*manifest.pending_wait_ids]
        if wait_state.wait_id not in pending:
            pending.append(wait_state.wait_id)
        self.update_manifest(run_id, pending_wait_ids=pending)

    def list_wait_states(self, run_id: str) -> list[WaitState]:
        self.load_manifest(run_id)
        if not self.waits_path.exists():
            return []
        latest: dict[str, WaitState] = {}
        for line in self.waits_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            wait_state = WaitState.model_validate_json(line)
            latest[wait_state.wait_id] = wait_state
        return list(latest.values())

    def ready_wait_states(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> list[WaitState]:
        current = now or _utc_now()
        ready = []
        for wait_state in self.list_wait_states(run_id):
            if wait_state.status is not WaitStateStatus.PENDING:
                continue
            if wait_state.wake_at <= current:
                ready.append(wait_state)
        ready.sort(key=lambda item: item.wake_at)
        return ready

    def next_wake_delay_seconds(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> float | None:
        current = now or _utc_now()
        pending = [
            item for item in self.list_wait_states(run_id)
            if item.status is WaitStateStatus.PENDING
        ]
        if not pending:
            return None
        next_wake = min(item.wake_at for item in pending)
        return max((next_wake - current).total_seconds(), 0.0)

    def mark_resumed(self, run_id: str, wait_id: str, *, reason: str) -> WaitState:
        manifest = self.load_manifest(run_id)
        current = None
        for wait_state in self.list_wait_states(run_id):
            if wait_state.wait_id == wait_id:
                current = wait_state
                break
        if current is None:
            raise KeyError(f"Unknown wait state: {wait_id}")
        resumed = current.model_copy(
            update={
                "status": WaitStateStatus.RESUMED,
                "resumed_at": _utc_now(),
                "resume_reason": reason,
            },
        )
        with self.waits_path.open("a", encoding="utf-8") as handle:
            handle.write(resumed.model_dump_json() + "\n")
        pending = [item for item in manifest.pending_wait_ids if item != wait_id]
        self.update_manifest(
            run_id,
            pending_wait_ids=pending,
            wake_count=manifest.wake_count + 1,
            last_resume_reason=reason,
        )
        return resumed

    def record_hibernate(self, run_id: str, *, phase: str, reason: str) -> TemporalRunManifest:
        manifest = self.load_manifest(run_id)
        return self.update_manifest(
            run_id,
            current_phase=phase,
            hibernate_count=manifest.hibernate_count + 1,
            last_resume_reason=reason,
        )
