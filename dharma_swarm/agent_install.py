"""Explicit installer for rendered agent artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dharma_swarm.agent_export import CanonicalAgentSpec, ExportArtifact, ExportTarget, render_all


@dataclass(frozen=True)
class InstallEntry:
    target: ExportTarget
    artifact: ExportArtifact
    destination: Path


@dataclass(frozen=True)
class InstallPlan:
    destination_root: Path
    entries: tuple[InstallEntry, ...]


@dataclass(frozen=True)
class InstalledFile:
    target: ExportTarget
    destination: Path
    checksum: str
    changed: bool


@dataclass(frozen=True)
class InstallManifest:
    destination_root: Path
    manifest_path: Path
    files: tuple[InstalledFile, ...]


def plan_agent_install(
    spec: CanonicalAgentSpec,
    *,
    targets: Iterable[ExportTarget] | None = None,
    destination_root: Path | str,
) -> InstallPlan:
    artifacts = render_all(spec, targets=targets)
    return plan_install(artifacts, destination_root=destination_root)


def plan_install(
    artifacts: Iterable[ExportArtifact],
    *,
    destination_root: Path | str,
) -> InstallPlan:
    root = Path(destination_root)
    entries = tuple(
        InstallEntry(
            target=artifact.target,
            artifact=artifact,
            destination=root / _install_relative_path(artifact),
        )
        for artifact in artifacts
    )
    return InstallPlan(destination_root=root, entries=entries)


def execute_install_plan(plan: InstallPlan) -> InstallManifest:
    files: list[InstalledFile] = []
    for entry in plan.entries:
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = entry.artifact.content
        checksum = _checksum(rendered)
        changed = True
        if entry.destination.exists():
            changed = _checksum(entry.destination.read_text(encoding="utf-8")) != checksum
        if changed:
            entry.destination.write_text(rendered, encoding="utf-8")
        files.append(
            InstalledFile(
                target=entry.target,
                destination=entry.destination,
                checksum=checksum,
                changed=changed,
            )
        )

    manifest_path = plan.destination_root / ".dharma" / "agent_install_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "destination_root": str(plan.destination_root),
        "files": [
            {
                "target": record.target.value,
                "destination": str(record.destination),
                "checksum": record.checksum,
                "changed": record.changed,
            }
            for record in files
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return InstallManifest(
        destination_root=plan.destination_root,
        manifest_path=manifest_path,
        files=tuple(files),
    )


def _install_relative_path(artifact: ExportArtifact) -> Path:
    name = artifact.relative_path.name
    if artifact.target is ExportTarget.CLAUDE_CODE:
        return Path(".claude") / "agents" / name
    if artifact.target is ExportTarget.COPILOT:
        return Path(".github") / "chatmodes" / name
    if artifact.target is ExportTarget.OPENCODE:
        return Path(".opencode") / "agents" / name
    if artifact.target is ExportTarget.CURSOR:
        return Path(".cursor") / "rules" / name
    if artifact.target is ExportTarget.QWEN:
        return Path(".qwen") / "agents" / name
    raise ValueError(f"Unsupported install target: {artifact.target}")


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "InstallEntry",
    "InstallManifest",
    "InstallPlan",
    "InstalledFile",
    "execute_install_plan",
    "plan_agent_install",
    "plan_install",
]
