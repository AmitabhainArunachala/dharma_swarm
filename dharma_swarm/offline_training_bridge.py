"""Export-only bridge for offline training lanes.

This module deliberately stops at deterministic artifact export. It does not
launch or orchestrate any live training jobs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex[:12]


class OfflineTrainingBundle(BaseModel):
    bundle_id: str = Field(default_factory=_new_id)
    task_id: str
    report_id: str
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    grade_card: dict[str, Any] = Field(default_factory=dict)
    reward_signal: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OfflineTrainingManifest(BaseModel):
    bundle_id: str
    export_dir: str
    trajectories_path: str
    grades_path: str
    rewards_path: str
    members: list[str] = Field(default_factory=list)


def build_offline_training_bundle(
    *,
    report: Any,
    reward_signal: Any,
    trajectory: list[dict[str, Any]] | None = None,
) -> OfflineTrainingBundle:
    reward_payload = (
        reward_signal.model_dump()
        if hasattr(reward_signal, "model_dump")
        else dict(reward_signal)
    )
    grade_card = dict(reward_payload.get("grade_card") or {})
    return OfflineTrainingBundle(
        task_id=str(getattr(report, "task_id", "") or ""),
        report_id=str(getattr(report, "report_id", "") or ""),
        trajectory=list(trajectory or []),
        grade_card=grade_card,
        reward_signal=reward_payload,
        metadata={
            "report_summary": str(getattr(report, "summary", "") or ""),
            "source_ids": list(getattr(report, "source_ids", []) or []),
        },
    )


def export_offline_training_bundle(
    bundle: OfflineTrainingBundle,
    *,
    export_dir: Path | str,
) -> OfflineTrainingManifest:
    root = Path(export_dir)
    root.mkdir(parents=True, exist_ok=True)

    trajectories_path = root / "trajectories.jsonl"
    grades_path = root / "grades.json"
    rewards_path = root / "rewards.json"
    manifest_path = root / "manifest.json"

    with trajectories_path.open("w", encoding="utf-8") as handle:
        for item in bundle.trajectory:
            handle.write(json.dumps(item, sort_keys=True) + "\n")

    grades_path.write_text(
        json.dumps(bundle.grade_card, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rewards_path.write_text(
        json.dumps(bundle.reward_signal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = OfflineTrainingManifest(
        bundle_id=bundle.bundle_id,
        export_dir=str(root),
        trajectories_path=str(trajectories_path),
        grades_path=str(grades_path),
        rewards_path=str(rewards_path),
        members=["trajectories.jsonl", "grades.json", "rewards.json", "manifest.json"],
    )
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "OfflineTrainingBundle",
    "OfflineTrainingManifest",
    "build_offline_training_bundle",
    "export_offline_training_bundle",
]
