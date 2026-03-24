"""Mission-state contract and reader utilities for DGC director continuity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


MISSION_CONTRACT_VERSION = "1.0.0"
CAMPAIGN_CONTRACT_VERSION = "1.0.0"
DEFAULT_STATE_DIR = Path.home() / ".dharma"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    items: list[str] = []
    for item in value:
        text = _normalize_text(item)
        if text:
            items.append(text)
    return items


def _normalize_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"mission state file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"mission state file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"mission state file must contain a JSON object: {path}")
    return payload


class MissionHistoryEntry(BaseModel):
    title: str = ""
    cycle_id: str = ""
    status: str = ""

    @field_validator("title", "cycle_id", "status", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> str:
        return _normalize_text(value)


class MissionState(BaseModel):
    contract_version: str = Field(default=MISSION_CONTRACT_VERSION)
    mission_title: str
    mission_thesis: str = ""
    mission_theme: str = "general"
    last_cycle_id: str = ""
    last_cycle_ts: str = ""
    status: str = "planned"
    task_count: int = 0
    task_titles: list[str] = Field(default_factory=list)
    delegated_task_ids: list[str] = Field(default_factory=list)
    review_summary: str = ""
    blockers: list[str] = Field(default_factory=list)
    rapid_ascent: bool = False
    previous_missions: list[MissionHistoryEntry] = Field(default_factory=list)

    @field_validator(
        "contract_version",
        "mission_title",
        "mission_thesis",
        "mission_theme",
        "last_cycle_id",
        "last_cycle_ts",
        "status",
        "review_summary",
        mode="before",
    )
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalize_text(value)

    @field_validator("task_count", mode="before")
    @classmethod
    def _normalize_task_count(cls, value: Any) -> int:
        if value in (None, ""):
            return 0
        try:
            return max(int(value), 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_count must be an integer") from exc

    @field_validator("task_titles", "delegated_task_ids", "blockers", mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("rapid_ascent", mode="before")
    @classmethod
    def _normalize_rapid_ascent(cls, value: Any) -> bool:
        return _normalize_bool(value)

    @field_validator("previous_missions", mode="before")
    @classmethod
    def _normalize_previous_missions(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("previous_missions must be a list")
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def _validate_and_derive(self) -> "MissionState":
        if not self.contract_version:
            self.contract_version = MISSION_CONTRACT_VERSION
        if not self.mission_title:
            raise ValueError("mission_title is required")
        self.task_count = max(self.task_count, len(self.task_titles))
        if len(self.previous_missions) > 10:
            self.previous_missions = self.previous_missions[-10:]
        return self


class MissionStateArtifact(BaseModel):
    source_kind: str
    source_path: str
    state: MissionState


class CampaignArtifact(BaseModel):
    artifact_kind: str = ""
    title: str = ""
    path: str = ""
    summary: str = ""
    source: str = ""
    citations: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_kind", "title", "path", "summary", "source", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalize_text(value)

    @field_validator("citations", "depends_on", mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        return _normalize_dict(value)


class SemanticBrief(BaseModel):
    brief_id: str = ""
    title: str = ""
    cluster_name: str = ""
    thesis: str = ""
    readiness_score: float = 0.0
    concept_names: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("brief_id", "title", "cluster_name", "thesis", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalize_text(value)

    @field_validator(
        "concept_names",
        "evidence_paths",
        "citations",
        "gaps",
        "next_actions",
        mode="before",
    )
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        return _normalize_dict(value)


class ExecutionBrief(BaseModel):
    brief_id: str = ""
    title: str = ""
    goal: str = ""
    readiness_score: float = 0.0
    task_titles: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    depends_on_briefs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    promotion_count: int = 0
    last_promoted_at: float = 0.0
    status: str = "active"  # active | completed | exhausted

    @field_validator("brief_id", "title", "goal", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalize_text(value)

    @field_validator(
        "task_titles",
        "acceptance",
        "evidence_paths",
        "depends_on_briefs",
        mode="before",
    )
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        return _normalize_dict(value)


class CampaignState(BaseModel):
    contract_version: str = Field(default=CAMPAIGN_CONTRACT_VERSION)
    campaign_id: str
    mission_title: str
    mission_thesis: str = ""
    mission_theme: str = "general"
    last_cycle_id: str = ""
    last_cycle_ts: str = ""
    status: str = "planned"
    task_count: int = 0
    task_titles: list[str] = Field(default_factory=list)
    delegated_task_ids: list[str] = Field(default_factory=list)
    review_summary: str = ""
    blockers: list[str] = Field(default_factory=list)
    rapid_ascent: bool = False
    evidence_paths: list[str] = Field(default_factory=list)
    semantic_briefs: list[SemanticBrief] = Field(default_factory=list)
    execution_briefs: list[ExecutionBrief] = Field(default_factory=list)
    artifacts: list[CampaignArtifact] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    previous_missions: list[MissionHistoryEntry] = Field(default_factory=list)

    @field_validator(
        "contract_version",
        "campaign_id",
        "mission_title",
        "mission_thesis",
        "mission_theme",
        "last_cycle_id",
        "last_cycle_ts",
        "status",
        "review_summary",
        mode="before",
    )
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalize_text(value)

    @field_validator("task_count", mode="before")
    @classmethod
    def _normalize_task_count(cls, value: Any) -> int:
        if value in (None, ""):
            return 0
        try:
            return max(int(value), 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_count must be an integer") from exc

    @field_validator(
        "task_titles",
        "delegated_task_ids",
        "blockers",
        "evidence_paths",
        mode="before",
    )
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("rapid_ascent", mode="before")
    @classmethod
    def _normalize_rapid_ascent(cls, value: Any) -> bool:
        return _normalize_bool(value)

    @field_validator("metrics", mode="before")
    @classmethod
    def _normalize_metrics(cls, value: Any) -> dict[str, Any]:
        return _normalize_dict(value)

    @field_validator("previous_missions", mode="before")
    @classmethod
    def _normalize_previous_missions(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("previous_missions must be a list")
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def _validate_and_derive(self) -> "CampaignState":
        if not self.contract_version:
            self.contract_version = CAMPAIGN_CONTRACT_VERSION
        if not self.campaign_id:
            raise ValueError("campaign_id is required")
        if not self.mission_title:
            raise ValueError("mission_title is required")
        self.task_count = max(self.task_count, len(self.task_titles))
        self.evidence_paths = _dedupe_keep_order(self.evidence_paths)
        if len(self.previous_missions) > 10:
            self.previous_missions = self.previous_missions[-10:]
        return self


class CampaignStateArtifact(BaseModel):
    source_kind: str
    source_path: str
    state: CampaignState


def default_mission_state_path(state_dir: str | Path | None = None) -> Path:
    root = Path(state_dir).expanduser() if state_dir is not None else DEFAULT_STATE_DIR
    return root / "mission.json"


def default_campaign_state_path(state_dir: str | Path | None = None) -> Path:
    root = Path(state_dir).expanduser() if state_dir is not None else DEFAULT_STATE_DIR
    return root / "campaign.json"


def default_latest_snapshot_path(state_dir: str | Path | None = None) -> Path:
    root = Path(state_dir).expanduser() if state_dir is not None else DEFAULT_STATE_DIR
    return root / "logs" / "thinkodynamic_director" / "latest.json"


def _coerce_snapshot_to_mission(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = payload.get("workflow")
    if not isinstance(workflow, dict):
        return payload
    tasks = workflow.get("tasks")
    task_titles: list[str] = []
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, dict):
                title = _normalize_text(item.get("title"))
            else:
                title = _normalize_text(item)
            if title:
                task_titles.append(title)
    review = payload.get("review")
    if not isinstance(review, dict):
        review = {}
    return {
        "mission_title": workflow.get("opportunity_title") or "",
        "mission_thesis": workflow.get("thesis") or "",
        "mission_theme": workflow.get("theme") or "",
        "last_cycle_id": payload.get("cycle_id") or "",
        "last_cycle_ts": payload.get("ts") or "",
        "status": "delegated" if payload.get("delegated") else "planned",
        "task_count": len(task_titles),
        "task_titles": task_titles,
        "delegated_task_ids": payload.get("delegated_task_ids") or [],
        "review_summary": review.get("note") or "",
        "blockers": review.get("blockers") or [],
        "rapid_ascent": payload.get("rapid_ascent", False),
        "previous_missions": [],
    }


def load_mission_state(path: str | Path) -> MissionState:
    source_path = Path(path).expanduser()
    payload = _read_json(source_path)
    if "mission_title" not in payload:
        payload = _coerce_snapshot_to_mission(payload)
    try:
        return MissionState.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid mission state in {source_path}: {exc}") from exc


def load_campaign_state(path: str | Path) -> CampaignState:
    source_path = Path(path).expanduser()
    payload = _read_json(source_path)
    try:
        return CampaignState.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid campaign state in {source_path}: {exc}") from exc


def load_active_mission_state(
    *,
    state_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> MissionStateArtifact | None:
    if path is not None:
        resolved = Path(path).expanduser()
        source_kind = "mission_file" if resolved.name == "mission.json" else "snapshot"
        return MissionStateArtifact(
            source_kind=source_kind,
            source_path=str(resolved),
            state=load_mission_state(resolved),
        )

    mission_path = default_mission_state_path(state_dir)
    if mission_path.exists():
        return MissionStateArtifact(
            source_kind="mission_file",
            source_path=str(mission_path),
            state=load_mission_state(mission_path),
        )

    latest_path = default_latest_snapshot_path(state_dir)
    if latest_path.exists():
        return MissionStateArtifact(
            source_kind="latest_snapshot",
            source_path=str(latest_path),
            state=load_mission_state(latest_path),
        )
    return None


def load_active_campaign_state(
    *,
    state_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> CampaignStateArtifact | None:
    if path is not None:
        resolved = Path(path).expanduser()
        return CampaignStateArtifact(
            source_kind="campaign_file",
            source_path=str(resolved),
            state=load_campaign_state(resolved),
        )

    campaign_path = default_campaign_state_path(state_dir)
    if campaign_path.exists():
        return CampaignStateArtifact(
            source_kind="campaign_file",
            source_path=str(campaign_path),
            state=load_campaign_state(campaign_path),
        )
    return None


def save_mission_state(path: str | Path, state: MissionState) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def save_campaign_state(path: str | Path, state: CampaignState) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def build_campaign_state(
    *,
    mission_state: MissionState,
    previous: CampaignState | None = None,
    semantic_briefs: list[SemanticBrief] | None = None,
    execution_briefs: list[ExecutionBrief] | None = None,
    artifacts: list[CampaignArtifact] | None = None,
    evidence_paths: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> CampaignState:
    semantic = (
        semantic_briefs
        if semantic_briefs is not None
        else (previous.semantic_briefs if previous is not None else [])
    )
    execution = (
        execution_briefs
        if execution_briefs is not None
        else (previous.execution_briefs if previous is not None else [])
    )
    campaign_artifacts = (
        artifacts
        if artifacts is not None
        else (previous.artifacts if previous is not None else [])
    )
    merged_evidence = _dedupe_keep_order(
        _normalize_text_list(evidence_paths)
        + [path for brief in semantic for path in brief.evidence_paths]
        + [path for brief in execution for path in brief.evidence_paths]
        + [artifact.path for artifact in campaign_artifacts if artifact.path]
        + (previous.evidence_paths if previous is not None else [])
    )
    merged_metrics: dict[str, Any] = {}
    if previous is not None:
        merged_metrics.update(previous.metrics)
    if metrics:
        merged_metrics.update(metrics)

    campaign_id = (
        previous.campaign_id
        if previous is not None and previous.mission_title == mission_state.mission_title
        else (
            f"campaign-{mission_state.last_cycle_id}"
            if mission_state.last_cycle_id
            else "campaign-active"
        )
    )
    return CampaignState(
        campaign_id=campaign_id,
        mission_title=mission_state.mission_title,
        mission_thesis=mission_state.mission_thesis,
        mission_theme=mission_state.mission_theme,
        last_cycle_id=mission_state.last_cycle_id,
        last_cycle_ts=mission_state.last_cycle_ts,
        status=mission_state.status,
        task_count=mission_state.task_count,
        task_titles=list(mission_state.task_titles),
        delegated_task_ids=list(mission_state.delegated_task_ids),
        review_summary=mission_state.review_summary,
        blockers=list(mission_state.blockers),
        rapid_ascent=mission_state.rapid_ascent,
        evidence_paths=merged_evidence,
        semantic_briefs=list(semantic),
        execution_briefs=list(execution),
        artifacts=list(campaign_artifacts),
        metrics=merged_metrics,
        previous_missions=list(mission_state.previous_missions),
    )


def render_mission_brief(
    artifact: MissionStateArtifact,
    *,
    max_tasks: int = 8,
    max_history: int = 5,
) -> str:
    state = artifact.state
    lines = [
        f"Mission: {state.mission_title}",
        f"Theme: {state.mission_theme or 'general'}",
        f"Status: {state.status}",
        f"Last cycle: {state.last_cycle_id or '?'} @ {state.last_cycle_ts or '?'}",
        f"Rapid ascent: {'yes' if state.rapid_ascent else 'no'}",
        f"Task count: {state.task_count}",
    ]
    if state.mission_thesis:
        lines.append(f"Thesis: {state.mission_thesis}")
    if state.task_titles:
        lines.append("Tasks:")
        for title in state.task_titles[:max_tasks]:
            lines.append(f"  - {title}")
        remaining = len(state.task_titles) - max_tasks
        if remaining > 0:
            lines.append(f"  - ... {remaining} more")
    if state.delegated_task_ids:
        lines.append(f"Delegated: {', '.join(state.delegated_task_ids[:max_tasks])}")
    if state.review_summary:
        lines.append(f"Review: {state.review_summary}")
    if state.blockers:
        lines.append("Blockers:")
        for blocker in state.blockers[:max_tasks]:
            lines.append(f"  - {blocker}")
    if state.previous_missions:
        lines.append("History:")
        for item in state.previous_missions[-max_history:]:
            lines.append(
                f"  - {item.title or '?'} [{item.status or '?'}] cycle {item.cycle_id or '?'}"
            )
    lines.append(f"Source: {artifact.source_kind} @ {artifact.source_path}")
    return "\n".join(lines)


def render_campaign_brief(
    artifact: CampaignStateArtifact,
    *,
    max_briefs: int = 3,
    max_artifacts: int = 5,
) -> str:
    state = artifact.state
    lines = [
        f"Campaign: {state.mission_title}",
        f"Campaign ID: {state.campaign_id}",
        f"Theme: {state.mission_theme or 'general'}",
        f"Status: {state.status}",
        f"Last cycle: {state.last_cycle_id or '?'} @ {state.last_cycle_ts or '?'}",
        f"Semantic briefs: {len(state.semantic_briefs)}",
        f"Execution briefs: {len(state.execution_briefs)}",
        f"Artifacts: {len(state.artifacts)}",
        f"Rapid ascent: {'yes' if state.rapid_ascent else 'no'}",
    ]
    if state.review_summary:
        lines.append(f"Review: {state.review_summary}")
    if state.semantic_briefs:
        lines.append("Top semantic briefs:")
        for brief in state.semantic_briefs[:max_briefs]:
            lines.append(
                f"  - {brief.title or brief.cluster_name or brief.brief_id} "
                f"(readiness={brief.readiness_score:.2f})"
            )
    if state.execution_briefs:
        lines.append("Top execution briefs:")
        for brief in state.execution_briefs[:max_briefs]:
            lines.append(
                f"  - {brief.title or brief.brief_id} "
                f"({len(brief.task_titles)} tasks, readiness={brief.readiness_score:.2f})"
            )
    if state.artifacts:
        lines.append("Artifacts:")
        for item in state.artifacts[:max_artifacts]:
            lines.append(f"  - {item.title or item.artifact_kind}: {item.path}")
    if state.blockers:
        lines.append("Blockers:")
        for blocker in state.blockers[:max_briefs]:
            lines.append(f"  - {blocker}")
    lines.append(f"Source: {artifact.source_kind} @ {artifact.source_path}")
    return "\n".join(lines)
