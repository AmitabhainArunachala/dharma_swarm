"""JSON-ready workspace payload builders for the shared operator core."""

from __future__ import annotations

from typing import Any

WORKSPACE_PAYLOAD_VERSION = "v1"
WORKSPACE_SNAPSHOT_DOMAIN = "workspace_snapshot"


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _serialize_topology_repos(topology: dict[str, Any]) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for domain in ("dgc", "sab"):
        block = topology.get(domain, {})
        if not isinstance(block, dict):
            continue
        for repo in block.get("repos", []):
            if not isinstance(repo, dict):
                continue
            repos.append(
                {
                    "domain": domain,
                    "name": str(repo.get("name", "") or ""),
                    "role": str(repo.get("role", "") or "unknown"),
                    "canonical": bool(repo.get("canonical", False)),
                    "path": str(repo.get("path", "") or ""),
                    "exists": bool(repo.get("exists", False)),
                    "is_git": bool(repo.get("is_git", False)),
                    "branch": repo.get("branch"),
                    "head": repo.get("head"),
                    "dirty": repo.get("dirty"),
                    "modified_count": _coerce_int(repo.get("modified_count")) or 0,
                    "untracked_count": _coerce_int(repo.get("untracked_count")) or 0,
                }
            )
    return repos


def build_workspace_snapshot_payload(
    *,
    repo_root: str,
    git_summary: dict[str, Any],
    topology: dict[str, Any],
    summary: Any | None = None,
) -> dict[str, Any]:
    """Build a versioned workspace snapshot payload from bridge inventory truth."""

    largest_python_files = []
    most_imported_modules = []
    language_mix: list[dict[str, Any]] = []
    inventory = {
        "python_modules": None,
        "python_tests": None,
        "scripts": None,
        "docs": None,
        "workflows": None,
    }

    if summary is not None:
        inventory = {
            "python_modules": _coerce_int(getattr(summary, "python_modules", None)),
            "python_tests": _coerce_int(getattr(summary, "python_tests", None)),
            "scripts": _coerce_int(getattr(summary, "shell_scripts", None)),
            "docs": _coerce_int(getattr(summary, "markdown_docs", None)),
            "workflows": len(getattr(summary, "workflows", []) or []),
        }
        language_mix = [
            {"suffix": str(suffix), "count": int(count)}
            for suffix, count in list((getattr(summary, "language_mix", {}) or {}).items())[:8]
        ]
        largest_python_files = [
            {
                "path": str(getattr(item, "path", "") or ""),
                "lines": int(getattr(item, "lines", 0) or 0),
                "defs": int(getattr(item, "defs", 0) or 0),
                "classes": int(getattr(item, "classes", 0) or 0),
                "imports": int(getattr(item, "imports", 0) or 0),
            }
            for item in list(getattr(summary, "largest_python_files", []) or [])[:5]
        ]
        most_imported_modules = [
            {
                "module": str(getattr(item, "module", "") or ""),
                "count": int(getattr(item, "count", 0) or 0),
            }
            for item in list(getattr(summary, "most_imported_modules", []) or [])[:5]
        ]

    changed_hotspots = []
    for item in list(git_summary.get("changed_hotspots", []) or [])[:4]:
        if not isinstance(item, dict):
            continue
        changed_hotspots.append(
            {
                "name": str(item.get("name", "") or ""),
                "count": _coerce_int(item.get("count")) or 0,
            }
        )

    return {
        "version": WORKSPACE_PAYLOAD_VERSION,
        "domain": WORKSPACE_SNAPSHOT_DOMAIN,
        "repo_root": repo_root,
        "git": {
            "branch": str(git_summary.get("branch", "") or "unavailable"),
            "head": str(git_summary.get("head", "") or "unavailable"),
            "staged": _coerce_int(git_summary.get("staged")),
            "unstaged": _coerce_int(git_summary.get("unstaged")),
            "untracked": _coerce_int(git_summary.get("untracked")),
            "changed_hotspots": changed_hotspots,
            "changed_paths": [str(path) for path in list(git_summary.get("changed_paths", []) or [])[:5] if str(path)],
            "sync": {
                "summary": str(git_summary.get("sync_summary", "") or "unavailable"),
                "status": str(git_summary.get("sync_status", "") or "unavailable"),
                "upstream": git_summary.get("upstream"),
                "ahead": _coerce_int(git_summary.get("ahead")),
                "behind": _coerce_int(git_summary.get("behind")),
            },
        },
        "topology": {
            "warnings": [str(item) for item in list(topology.get("warnings", []) or []) if str(item)],
            "repos": _serialize_topology_repos(topology),
        },
        "inventory": inventory,
        "language_mix": language_mix,
        "largest_python_files": largest_python_files,
        "most_imported_modules": most_imported_modules,
    }
