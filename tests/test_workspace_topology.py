from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_build_workspace_topology_flags_split_repos(monkeypatch):
    from dharma_swarm import workspace_topology as wt

    fake = {
        "/home/test/dharma_swarm": {
            "path": "/home/test/dharma_swarm",
            "exists": True,
            "is_git": True,
            "branch": "main",
            "head": "abc canonical",
            "dirty": False,
            "modified_count": 0,
            "untracked_count": 0,
        },
        "/home/test/dgc-core": {
            "path": "/home/test/dgc-core",
            "exists": True,
            "is_git": True,
            "branch": "main",
            "head": "def shell",
            "dirty": True,
            "modified_count": 2,
            "untracked_count": 1,
        },
        "/home/test/DHARMIC_GODEL_CLAW": {
            "path": "/home/test/DHARMIC_GODEL_CLAW",
            "exists": True,
            "is_git": True,
            "branch": "legacy",
            "head": "ghi legacy",
            "dirty": True,
            "modified_count": 5,
            "untracked_count": 8,
        },
        "/home/test/agni-workspace/dharmic-agora": {
            "path": "/home/test/agni-workspace/dharmic-agora",
            "exists": True,
            "is_git": True,
            "branch": "main",
            "head": "jkl runtime",
            "dirty": False,
            "modified_count": 0,
            "untracked_count": 0,
        },
        "/home/test/SAB": {
            "path": "/home/test/SAB",
            "exists": True,
            "is_git": True,
            "branch": "main",
            "head": "mno strategy",
            "dirty": False,
            "modified_count": 0,
            "untracked_count": 0,
        },
    }

    monkeypatch.setattr(wt, "_inspect_repo", lambda path: fake[str(path)])

    topo = wt.build_workspace_topology(Path("/home/test"))
    assert topo["dgc"]["fully_merged"] is False
    assert topo["sab"]["fully_merged"] is False
    assert topo["operator_answer"]["dgc_code_authority"] == "/home/test/dharma_swarm"
    assert topo["merge_summary"] is None
    assert "legacy_dgc_repo_still_mutating" in topo["warnings"]
    assert "dgc_core_wrapper_dirty" in topo["warnings"]
    assert "sab_strategy_repo_separate_from_runtime" in topo["warnings"]


def test_cmd_canonical_status_prints_operator_answer(monkeypatch, capsys):
    from dharma_swarm import dgc_cli

    topo = {
        "dgc": {
            "canonical_repo": "/tmp/dharma_swarm",
            "fully_merged": False,
            "repos": [
                {
                    "name": "dharma_swarm",
                    "role": "canonical_core",
                    "canonical": True,
                    "path": "/tmp/dharma_swarm",
                    "exists": True,
                    "is_git": True,
                    "branch": "main",
                    "dirty": False,
                    "modified_count": 0,
                    "untracked_count": 0,
                }
            ],
        },
        "sab": {
            "canonical_repo": "/tmp/dharmic-agora",
            "fully_merged": False,
            "repos": [
                {
                    "name": "dharmic-agora",
                    "role": "canonical_runtime",
                    "canonical": True,
                    "path": "/tmp/dharmic-agora",
                    "exists": True,
                    "is_git": True,
                    "branch": "main",
                    "dirty": False,
                    "modified_count": 0,
                    "untracked_count": 0,
                }
            ],
        },
        "warnings": ["legacy_dgc_repo_still_mutating"],
        "merge_summary": {
            "snapshot": "20260308T233449Z",
            "legacy_imported": "786",
            "tracked": "8/8",
        },
        "operator_answer": {
            "dgc_code_authority": "/tmp/dharma_swarm",
            "sab_runtime_authority": "/tmp/dharmic-agora",
            "legacy_dgc_archive": "/tmp/DHARMIC_GODEL_CLAW",
            "sab_strategy_shell": "/tmp/SAB",
        },
    }

    monkeypatch.setattr(
        "dharma_swarm.workspace_topology.build_workspace_topology",
        lambda: topo,
    )

    rc = dgc_cli.cmd_canonical_status()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Use /tmp/dharma_swarm as DGC code authority" in out
    assert "legacy_dgc_repo_still_mutating" in out
    assert "legacy_imported=786" in out


def test_cmd_canonical_status_json(monkeypatch, capsys):
    from dharma_swarm import dgc_cli

    topo = {
        "dgc": {"canonical_repo": "/tmp/dharma_swarm", "fully_merged": True, "repos": []},
        "sab": {"canonical_repo": "/tmp/dharmic-agora", "fully_merged": True, "repos": []},
        "warnings": [],
        "merge_summary": None,
        "operator_answer": {
            "dgc_code_authority": "/tmp/dharma_swarm",
            "sab_runtime_authority": "/tmp/dharmic-agora",
            "legacy_dgc_archive": "/tmp/DHARMIC_GODEL_CLAW",
            "sab_strategy_shell": "/tmp/SAB",
        },
    }

    monkeypatch.setattr(
        "dharma_swarm.workspace_topology.build_workspace_topology",
        lambda: topo,
    )

    rc = dgc_cli.cmd_canonical_status(as_json=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dgc"]["fully_merged"] is True
