"""Canonical workspace topology for the active DGC/SAB stack."""

from __future__ import annotations

import subprocess
from pathlib import Path
import re
from typing import Any


REPO_SPECS: tuple[dict[str, Any], ...] = (
    {
        "domain": "dgc",
        "name": "dharma_swarm",
        "role": "canonical_core",
        "canonical": True,
        "rel_path": "dharma_swarm",
    },
    {
        "domain": "dgc",
        "name": "dgc-core",
        "role": "operator_shell",
        "canonical": False,
        "rel_path": "dgc-core",
    },
    {
        "domain": "dgc",
        "name": "DHARMIC_GODEL_CLAW",
        "role": "legacy_archive",
        "canonical": False,
        "rel_path": "DHARMIC_GODEL_CLAW",
    },
    {
        "domain": "sab",
        "name": "dharmic-agora",
        "role": "canonical_runtime",
        "canonical": True,
        "rel_path": "agni-workspace/dharmic-agora",
    },
    {
        "domain": "sab",
        "name": "SAB",
        "role": "strategy_shell",
        "canonical": False,
        "rel_path": "SAB",
    },
)


def _git_text(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return proc.stdout


def _inspect_repo(repo: Path) -> dict[str, Any]:
    exists = repo.exists()
    is_git = (repo / ".git").exists()
    info: dict[str, Any] = {
        "path": str(repo),
        "exists": exists,
        "is_git": is_git,
        "branch": None,
        "head": None,
        "dirty": None,
        "modified_count": 0,
        "untracked_count": 0,
    }
    if not exists or not is_git:
        return info

    try:
        status = _git_text(repo, "status", "--short", "--branch")
        lines = [line.rstrip("\n") for line in status.splitlines()]
        if lines and lines[0].startswith("## "):
            info["branch"] = lines[0][3:]
        changed = lines[1:] if lines[:1] and lines[0].startswith("## ") else lines
        modified = 0
        untracked = 0
        for line in changed:
            if not line.strip():
                continue
            if line.startswith("?? "):
                untracked += 1
            else:
                modified += 1
        info["dirty"] = bool(modified or untracked)
        info["modified_count"] = modified
        info["untracked_count"] = untracked
    except Exception:
        info["dirty"] = None

    try:
        head = _git_text(repo, "log", "--oneline", "-1").strip()
        info["head"] = head or None
    except Exception:
        info["head"] = None

    return info


def _read_merge_summary(root: Path) -> dict[str, Any] | None:
    ledger = root / "dharma_swarm" / "docs" / "merge" / "MERGE_LEDGER.md"
    if not ledger.exists():
        return None
    try:
        lines = ledger.read_text(errors="ignore").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        if "snapshot=" not in line:
            continue
        summary: dict[str, Any] = {"raw": line.strip()}
        for key in ("snapshot", "branch", "head", "mission_exit", "tracked", "legacy_imported", "predictor_rows"):
            match = re.search(rf"{key}=([^\s]+)", line)
            if match:
                summary[key] = match.group(1)
        return summary
    return None


def build_workspace_topology(home: Path | None = None) -> dict[str, Any]:
    root = Path(home or Path.home())
    domains: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for spec in REPO_SPECS:
        domain = spec["domain"]
        block = domains.setdefault(
            domain,
            {
                "canonical_repo": None,
                "fully_merged": True,
                "repos": [],
            },
        )
        repo_path = root / spec["rel_path"]
        repo_info = _inspect_repo(repo_path)
        row = {
            "name": spec["name"],
            "role": spec["role"],
            "canonical": spec["canonical"],
            **repo_info,
        }
        if spec["canonical"]:
            block["canonical_repo"] = str(repo_path)
        if repo_info["exists"] and repo_info["is_git"] and not spec["canonical"]:
            block["fully_merged"] = False
        if spec["role"] == "legacy_archive" and repo_info["dirty"]:
            warnings.append("legacy_dgc_repo_still_mutating")
        if spec["role"] == "operator_shell" and repo_info["dirty"]:
            warnings.append("dgc_core_wrapper_dirty")
        if spec["role"] == "strategy_shell" and repo_info["exists"] and repo_info["is_git"]:
            warnings.append("sab_strategy_repo_separate_from_runtime")
        block["repos"].append(row)

    for domain, block in domains.items():
        canonical = [r for r in block["repos"] if r["canonical"] and r["exists"]]
        if not canonical:
            block["fully_merged"] = False
            warnings.append(f"{domain}_canonical_repo_missing")

    dgc_block = domains.get("dgc", {})
    sab_block = domains.get("sab", {})

    return {
        "dgc": dgc_block,
        "sab": sab_block,
        "warnings": warnings,
        "merge_summary": _read_merge_summary(root),
        "operator_answer": {
            "dgc_code_authority": str(root / "dharma_swarm"),
            "sab_runtime_authority": str(root / "agni-workspace" / "dharmic-agora"),
            "legacy_dgc_archive": str(root / "DHARMIC_GODEL_CLAW"),
            "sab_strategy_shell": str(root / "SAB"),
        },
    }
