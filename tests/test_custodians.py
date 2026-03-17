"""Tests for the Custodians — autonomous code maintenance fleet."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dharma_swarm.custodians import (
    ROLES,
    CRON_GROUPS,
    MODEL_ROTATION,
    ROLE_LIFECYCLE_THRESHOLDS,
    CustodianRole,
    CustodianResult,
    select_files,
    run_role,
    run_custodian_cycle,
    load_history,
    format_status,
    custodians_run_fn,
    _discover_py_files,
    _load_last_touched,
    _validate_files,
    _record_run,
    _get_model_for_role,
    _compute_role_lifecycle,
    _git_merge_to_main,
    install_launchd_service,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def py_tree(tmp_path):
    """Create a small Python project tree for file discovery."""
    pkg = tmp_path / "dharma_swarm"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# init\n")
    (pkg / "module_a.py").write_text("def foo():\n    return 1\n")
    (pkg / "module_b.py").write_text("class Bar:\n    pass\n")
    (pkg / "module_c.py").write_text("x = 42  # constant\n")
    cache = pkg / "__pycache__"
    cache.mkdir()
    (cache / "module_a.cpython-314.pyc").write_text("bytecode")
    return tmp_path


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    """Redirect custodians state to tmp_path."""
    state = tmp_path / "custodians"
    state.mkdir()
    monkeypatch.setattr("dharma_swarm.custodians.STATE_DIR", state)
    monkeypatch.setattr("dharma_swarm.custodians.HISTORY_FILE", state / "history.jsonl")
    return state


@pytest.fixture
def git_repo(tmp_path):
    """A bare git repo for git safety tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return repo


# ── Role Definitions ─────────────────────────────────────────────────


class TestRoleDefinitions:
    def test_five_roles_defined(self):
        assert len(ROLES) == 5
        assert set(ROLES.keys()) == {
            "linter", "type_tightener", "doc_patcher",
            "test_gap_closer", "dead_code_hunter",
        }

    def test_roles_are_custodian_role(self):
        for role in ROLES.values():
            assert isinstance(role, CustodianRole)

    def test_tier_assignments(self):
        assert ROLES["linter"].tier == 3
        assert ROLES["type_tightener"].tier == 2
        assert ROLES["doc_patcher"].tier == 2
        assert ROLES["test_gap_closer"].tier == 1
        assert ROLES["dead_code_hunter"].tier == 2

    def test_system_prompts_have_placeholders(self):
        for role in ROLES.values():
            assert "{project_path}" in role.system_prompt
            assert "{test_command}" in role.system_prompt

    def test_user_prompts_have_file_list(self):
        for role in ROLES.values():
            assert "{file_list}" in role.user_prompt_template

    def test_max_files_defaults(self):
        assert ROLES["linter"].max_files == 5
        assert ROLES["test_gap_closer"].max_files == 3
        assert ROLES["dead_code_hunter"].max_files == 3

    def test_skip_patterns_exclude_pycache(self):
        for role in ROLES.values():
            assert "__pycache__" in role.skip_patterns

    def test_cron_groups_cover_all_roles(self):
        all_cron_roles = set()
        for roles in CRON_GROUPS.values():
            all_cron_roles.update(roles)
        assert all_cron_roles == set(ROLES.keys())


# ── File Discovery ───────────────────────────────────────────────────


class TestFileDiscovery:
    def test_discovers_py_files(self, py_tree):
        pkg = py_tree / "dharma_swarm"
        files = _discover_py_files(pkg)
        names = {f.name for f in files}
        assert "module_a.py" in names
        assert "module_b.py" in names
        assert "module_c.py" in names

    def test_excludes_pycache(self, py_tree):
        pkg = py_tree / "dharma_swarm"
        files = _discover_py_files(pkg, exclude=("__pycache__",))
        names = {f.name for f in files}
        assert not any("cpython" in n for n in names)

    def test_skips_tiny_files(self, py_tree):
        pkg = py_tree / "dharma_swarm"
        (pkg / "tiny.py").write_text("")  # 0 bytes
        files = _discover_py_files(pkg)
        names = {f.name for f in files}
        assert "tiny.py" not in names

    def test_select_files_respects_max(self, py_tree, monkeypatch):
        pkg = py_tree / "dharma_swarm"
        monkeypatch.setattr("dharma_swarm.custodians.PACKAGE_DIR", pkg)
        monkeypatch.setattr("dharma_swarm.custodians.HISTORY_FILE", py_tree / "nonexistent.jsonl")
        role = ROLES["linter"]
        files = select_files(role, project_dir=pkg)
        assert len(files) <= role.max_files


# ── History / Rotation ───────────────────────────────────────────────


class TestHistory:
    def test_empty_history(self, history_dir):
        assert load_history() == []

    def test_record_and_load(self, history_dir):
        result = CustodianResult(
            role="linter", success=True, dry_run=False, model="test-model",
            files_targeted=["a.py"], files_changed=["a.py"],
            duration_seconds=1.5,
        )
        _record_run(result)
        entries = load_history()
        assert len(entries) == 1
        assert entries[0]["role"] == "linter"
        assert entries[0]["success"] is True
        assert entries[0]["files_changed"] == ["a.py"]

    def test_load_filtered_by_role(self, history_dir):
        for role_name in ["linter", "doc_patcher", "linter"]:
            result = CustodianResult(role=role_name, success=True)
            _record_run(result)
        entries = load_history(role="linter")
        assert len(entries) == 2
        assert all(e["role"] == "linter" for e in entries)

    def test_load_respects_limit(self, history_dir):
        for i in range(10):
            _record_run(CustodianResult(role="linter", success=True))
        entries = load_history(limit=3)
        assert len(entries) == 3

    def test_last_touched_tracking(self, history_dir, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.custodians.HISTORY_FILE",
            history_dir / "history.jsonl",
        )
        _record_run(CustodianResult(
            role="linter", success=True, files_changed=["foo.py"],
        ))
        touched = _load_last_touched()
        assert touched.get("foo.py") == "linter"


# ── Dry Run Execution ────────────────────────────────────────────────


class TestDryRun:
    @patch("dharma_swarm.custodians._get_model_for_role", return_value="test-model/v1")
    def test_dry_run_succeeds(self, mock_model, py_tree, monkeypatch):
        pkg = py_tree / "dharma_swarm"
        monkeypatch.setattr("dharma_swarm.custodians.PACKAGE_DIR", pkg)
        monkeypatch.setattr("dharma_swarm.custodians.DHARMA_SWARM_ROOT", py_tree)
        monkeypatch.setattr("dharma_swarm.custodians.HISTORY_FILE", py_tree / "nope.jsonl")
        result = run_role("linter", dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert "DRY RUN" in result.agent_output
        assert result.model == "test-model/v1"


def test_install_launchd_service_writes_absolute_paths(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "com.dharma.cron-daemon.plist").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/dgc</string>
        <string>cron</string>
        <string>daemon</string>
    </array>
    <key>StandardOutPath</key>
    <string>~/.dharma/logs/cron-daemon.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>~/.dharma/logs/cron-daemon.stderr.log</string>
    <key>WorkingDirectory</key>
    <string>~</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setattr("dharma_swarm.custodians.DHARMA_SWARM_ROOT", repo_root)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "dharma_swarm.custodians.Path.home",
        classmethod(lambda cls: home),
    )
    monkeypatch.setattr(
        "dharma_swarm.custodians.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    assert install_launchd_service() is True

    dest = home / "Library" / "LaunchAgents" / "com.dharma.cron-daemon.plist"
    rendered = dest.read_text(encoding="utf-8")
    assert "~" not in rendered
    assert f"{home}/.dharma/logs/cron-daemon.stdout.log" in rendered
    assert f"{home}/.dharma/logs/cron-daemon.stderr.log" in rendered
    assert f"<string>{home}</string>" in rendered

    @patch("dharma_swarm.custodians._get_model_for_role", return_value="test-model/v1")
    def test_dry_run_no_files_changed(self, mock_model, py_tree, monkeypatch):
        pkg = py_tree / "dharma_swarm"
        monkeypatch.setattr("dharma_swarm.custodians.PACKAGE_DIR", pkg)
        monkeypatch.setattr("dharma_swarm.custodians.DHARMA_SWARM_ROOT", py_tree)
        monkeypatch.setattr("dharma_swarm.custodians.HISTORY_FILE", py_tree / "nope.jsonl")
        result = run_role("linter", dry_run=True)
        assert result.files_changed == []
        assert result.committed is False

    def test_unknown_role_fails(self):
        result = run_role("nonexistent_role")
        assert result.success is False
        assert "Unknown role" in result.error

    @patch("dharma_swarm.custodians._get_model_for_role", return_value="test-model/v1")
    def test_full_cycle_dry_run(self, mock_model, py_tree, monkeypatch):
        pkg = py_tree / "dharma_swarm"
        monkeypatch.setattr("dharma_swarm.custodians.PACKAGE_DIR", pkg)
        monkeypatch.setattr("dharma_swarm.custodians.DHARMA_SWARM_ROOT", py_tree)
        monkeypatch.setattr("dharma_swarm.custodians.TESTS_DIR", py_tree / "tests")
        monkeypatch.setattr("dharma_swarm.custodians.HISTORY_FILE", py_tree / "nope.jsonl")
        results = run_custodian_cycle(roles=["linter", "doc_patcher"], dry_run=True)
        assert len(results) == 2
        assert all(r.dry_run for r in results)
        assert all(r.success for r in results)


# ── Validation ───────────────────────────────────────────────────────


class TestValidation:
    def test_valid_file(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n")
        assert _validate_files(str(tmp_path), ["good.py"]) is True

    def test_invalid_file(self, tmp_path):
        (tmp_path / "bad.py").write_text("def broken(\n")
        assert _validate_files(str(tmp_path), ["bad.py"]) is False

    def test_nonexistent_file(self, tmp_path):
        # Non-existent files are skipped (not .py suffix check)
        assert _validate_files(str(tmp_path), ["nope.py"]) is True

    def test_non_py_skipped(self, tmp_path):
        (tmp_path / "readme.md").write_text("# bad {{{")
        assert _validate_files(str(tmp_path), ["readme.md"]) is True


# ── Status Formatting ────────────────────────────────────────────────


class TestStatus:
    @patch("dharma_swarm.custodians._get_model_for_tier", return_value="test-model")
    def test_no_history(self, mock_model, history_dir):
        status = format_status()
        assert "No custodian runs" in status

    @patch("dharma_swarm.custodians._get_model_for_tier", return_value="test-model")
    def test_with_history(self, mock_model, history_dir):
        _record_run(CustodianResult(
            role="linter", success=True, model="test-model",
            files_changed=["a.py"], duration_seconds=2.0,
        ))
        status = format_status()
        assert "linter" in status
        assert "Custodian Fleet" in status


# ── Cron Integration ─────────────────────────────────────────────────


class TestCronIntegration:
    @patch("dharma_swarm.custodians.run_custodian_cycle")
    def test_cron_run_fn_success(self, mock_cycle):
        mock_cycle.return_value = [
            CustodianResult(role="linter", success=True, model="m"),
            CustodianResult(role="doc_patcher", success=True, model="m"),
        ]
        ok, output, err = custodians_run_fn({"prompt": "6h"})
        assert ok is True
        assert err is None
        assert "linter" in output
        mock_cycle.assert_called_once_with(roles=["linter", "doc_patcher"], dry_run=False)

    @patch("dharma_swarm.custodians.run_custodian_cycle")
    def test_cron_run_fn_partial_failure(self, mock_cycle):
        mock_cycle.return_value = [
            CustodianResult(role="linter", success=True, model="m"),
            CustodianResult(role="doc_patcher", success=False, model="m", error="fail"),
        ]
        ok, output, err = custodians_run_fn({"prompt": "6h"})
        assert ok is False  # not all succeeded
        assert "fail" in output

    @patch("dharma_swarm.custodians.run_custodian_cycle")
    def test_cron_daily_group(self, mock_cycle):
        mock_cycle.return_value = [
            CustodianResult(role="test_gap_closer", success=True, model="m"),
        ]
        ok, output, err = custodians_run_fn({"prompt": "daily"})
        mock_cycle.assert_called_once_with(roles=["test_gap_closer"], dry_run=False)

    @patch("dharma_swarm.custodians.run_custodian_cycle", side_effect=RuntimeError("boom"))
    def test_cron_run_fn_exception(self, mock_cycle):
        ok, output, err = custodians_run_fn({"prompt": "all"})
        assert ok is False
        assert "boom" in err


# ── Prompt Building ──────────────────────────────────────────────────


class TestPromptBuilding:
    def test_system_prompt_formats(self):
        role = ROLES["linter"]
        formatted = role.system_prompt.format(
            project_path="/tmp/test", test_command="pytest",
        )
        assert "/tmp/test" in formatted
        assert "pytest" in formatted

    def test_user_prompt_formats(self):
        role = ROLES["linter"]
        formatted = role.user_prompt_template.format(
            file_list="- a.py\n- b.py",
        )
        assert "a.py" in formatted
        assert "b.py" in formatted


# ── Model Rotation ───────────────────────────────────────────────────


class TestModelRotation:
    def test_all_roles_have_rotation(self):
        for name in ROLES:
            assert name in MODEL_ROTATION
            assert len(MODEL_ROTATION[name]) >= 2

    def test_linter_gets_tier3_models(self):
        for m in MODEL_ROTATION["linter"]:
            # Tier 3 models: phi-4, mistral-small
            assert "phi" in m or "mistral" in m

    def test_test_gap_closer_gets_tier1(self):
        for m in MODEL_ROTATION["test_gap_closer"]:
            assert "deepseek" in m or "llama" in m

    def test_dead_code_hunter_upgraded_to_tier1(self):
        # dead_code_hunter should have tier-1 models for grep reasoning
        assert "deepseek/deepseek-r1:free" in MODEL_ROTATION["dead_code_hunter"]

    def test_rotation_cycles(self, history_dir):
        # With no history, should get first model
        model0 = _get_model_for_role("linter")
        assert model0 == MODEL_ROTATION["linter"][0]

        # After one run, should get second
        _record_run(CustodianResult(role="linter", success=True))
        model1 = _get_model_for_role("linter")
        assert model1 == MODEL_ROTATION["linter"][1]

        # After two runs, should wrap back to first
        _record_run(CustodianResult(role="linter", success=True))
        model2 = _get_model_for_role("linter")
        assert model2 == MODEL_ROTATION["linter"][0]


# ── Lifecycle (Ontological) ──────────────────────────────────────────


class TestLifecycle:
    def test_seed_with_no_history(self, history_dir):
        lc = _compute_role_lifecycle("linter")
        assert lc["status"] == "seed"
        assert lc["total_runs"] == 0

    def test_growing_after_one_run(self, history_dir):
        _record_run(CustodianResult(role="linter", success=True, dry_run=False))
        lc = _compute_role_lifecycle("linter")
        assert lc["status"] == "growing"

    def test_solid_after_five_runs(self, history_dir):
        for _ in range(5):
            _record_run(CustodianResult(
                role="linter", success=True, dry_run=False,
                files_changed=["a.py"],
            ))
        lc = _compute_role_lifecycle("linter")
        assert lc["status"] == "solid"
        assert lc["success_rate"] == 1.0
        assert lc["files_healed"] == 5

    def test_shipped_after_ten_runs(self, history_dir):
        for _ in range(10):
            _record_run(CustodianResult(
                role="linter", success=True, dry_run=False,
            ))
        lc = _compute_role_lifecycle("linter")
        assert lc["status"] == "shipped"

    def test_low_success_rate_stays_growing(self, history_dir):
        for i in range(10):
            _record_run(CustodianResult(
                role="linter", success=(i < 5), dry_run=False,
            ))
        lc = _compute_role_lifecycle("linter")
        # 5/10 = 0.5 success rate, below 0.7 threshold
        assert lc["status"] == "growing"

    def test_lifecycle_icons_in_status(self, history_dir):
        _record_run(CustodianResult(
            role="linter", success=True, dry_run=False, model="m",
        ))
        status = format_status()
        assert "🌿" in status  # growing icon


# ── Auto-Merge ───────────────────────────────────────────────────────


class TestAutoMerge:
    def test_merge_to_main(self, git_repo):
        # Create a branch, make a change, commit
        subprocess.run(
            ["git", "checkout", "-b", "custodians/test-branch"],
            cwd=git_repo, capture_output=True,
        )
        (git_repo / "main.py").write_text("x = 2\n")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test change"],
            cwd=git_repo, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
        )

        merged = _git_merge_to_main(str(git_repo), "custodians/test-branch")
        assert merged is True

        # Verify we're on main and changes are there
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "main"
        assert (git_repo / "main.py").read_text() == "x = 2\n"

    def test_merge_conflict_aborts(self, git_repo):
        # Make conflicting changes on both branches
        (git_repo / "main.py").write_text("x = 100\n")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "main change"],
            cwd=git_repo, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
        )

        subprocess.run(
            ["git", "checkout", "-b", "custodians/conflict-branch", "HEAD~1"],
            cwd=git_repo, capture_output=True,
        )
        (git_repo / "main.py").write_text("x = 999\n")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "conflict change"],
            cwd=git_repo, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
        )

        merged = _git_merge_to_main(str(git_repo), "custodians/conflict-branch")
        assert merged is False


# ── Dispatch Router ──────────────────────────────────────────────────


class TestDispatchRouter:
    def test_custodians_handler(self):
        from dharma_swarm.cron_runner import run_cron_job
        with patch("dharma_swarm.custodians.custodians_run_fn") as mock_fn:
            mock_fn.return_value = (True, "ok", None)
            ok, output, err = run_cron_job({"handler": "custodians", "prompt": "6h"})
            mock_fn.assert_called_once()
            assert ok is True

    def test_custodians_forge_handler(self):
        from dharma_swarm.cron_runner import run_cron_job
        with patch("dharma_swarm.foreman.custodians_forge_fn") as mock_fn:
            mock_fn.return_value = (True, "ok", None)
            ok, output, err = run_cron_job({"handler": "custodians_forge", "prompt": "6h"})
            mock_fn.assert_called_once()

    def test_foreman_handler(self):
        from dharma_swarm.cron_runner import run_cron_job
        with patch("dharma_swarm.foreman.foreman_run_fn") as mock_fn:
            mock_fn.return_value = (True, "ok", None)
            ok, output, err = run_cron_job({"handler": "foreman", "prompt": "advise"})
            mock_fn.assert_called_once()

    def test_unknown_handler_fails(self):
        from dharma_swarm.cron_runner import run_cron_job
        ok, output, err = run_cron_job({"handler": "nonexistent"})
        assert ok is False
        assert "Unsupported" in output
