"""Tests for dharma_swarm.diff_applier -- unified diff application with rollback."""

import asyncio
from pathlib import Path

import pytest

from dharma_swarm.diff_applier import (
    ApplyResult,
    ApplyTestResult,
    DiffApplier,
    parse_unified_diff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_simple_diff(old_name: str = "a/hello.py", new_name: str = "b/hello.py") -> str:
    """Single-file, single-hunk diff replacing line 1."""
    return (
        f"--- {old_name}\n"
        f"+++ {new_name}\n"
        "@@ -1,3 +1,3 @@\n"
        " # header\n"
        "-old_value = 1\n"
        "+new_value = 2\n"
        " # footer\n"
    )


# ---------------------------------------------------------------------------
# 1. Apply simple single-file diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_simple_diff(tmp_path: Path):
    """A single-hunk diff should modify the target file correctly."""
    target = tmp_path / "hello.py"
    target.write_text("# header\nold_value = 1\n# footer\n")

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(_make_simple_diff())

    assert result.success is True
    assert "hello.py" in result.files_changed
    content = target.read_text()
    assert "new_value = 2" in content
    assert "old_value = 1" not in content


# ---------------------------------------------------------------------------
# 2. Apply multi-file diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_multi_file_diff(tmp_path: Path):
    """A diff touching two files should modify both."""
    (tmp_path / "a.py").write_text("line1\nline2\n")
    (tmp_path / "b.py").write_text("alpha\nbeta\n")

    diff = (
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " line1\n"
        "-line2\n"
        "+line2_modified\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-alpha\n"
        "+ALPHA\n"
        " beta\n"
    )
    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(diff)

    assert result.success is True
    assert len(result.files_changed) == 2
    assert "line2_modified" in (tmp_path / "a.py").read_text()
    assert "ALPHA" in (tmp_path / "b.py").read_text()


# ---------------------------------------------------------------------------
# 3. Dry run doesn't modify files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_modification(tmp_path: Path):
    """dry_run=True should report files but not change them."""
    target = tmp_path / "hello.py"
    original = "# header\nold_value = 1\n# footer\n"
    target.write_text(original)

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(_make_simple_diff(), dry_run=True)

    assert result.success is True
    assert "hello.py" in result.files_changed
    # File content must be unchanged
    assert target.read_text() == original
    # No backups created
    assert result.backup_paths == {}


# ---------------------------------------------------------------------------
# 4. Rollback restores original content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_restores_content(tmp_path: Path):
    """After apply + rollback, the file should be back to original."""
    target = tmp_path / "hello.py"
    original = "# header\nold_value = 1\n# footer\n"
    target.write_text(original)

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(_make_simple_diff())
    assert result.success is True
    assert "new_value = 2" in target.read_text()

    await applier.rollback(result)
    assert target.read_text() == original
    # Backup file should be cleaned up
    assert not Path(result.backup_paths[str(target)]).exists()


# ---------------------------------------------------------------------------
# 5. apply_and_test keeps changes when tests pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_and_test_keeps_on_pass(tmp_path: Path):
    """When test command succeeds (exit 0), changes should be kept."""
    target = tmp_path / "hello.py"
    target.write_text("# header\nold_value = 1\n# footer\n")

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply_and_test(
        _make_simple_diff(),
        test_command="python3 -c \"exit(0)\"",
    )

    assert result.applied is True
    assert result.tests_passed is True
    assert result.rolled_back is False
    assert "new_value = 2" in target.read_text()


# ---------------------------------------------------------------------------
# 6. apply_and_test rolls back when tests fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_and_test_rollback_on_fail(tmp_path: Path):
    """When test command fails (exit 1), changes should be rolled back."""
    target = tmp_path / "hello.py"
    original = "# header\nold_value = 1\n# footer\n"
    target.write_text(original)

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply_and_test(
        _make_simple_diff(),
        test_command="python3 -c \"exit(1)\"",
    )

    assert result.applied is True
    assert result.tests_passed is False
    assert result.rolled_back is True
    assert target.read_text() == original


# ---------------------------------------------------------------------------
# 7. Invalid diff returns error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_diff_target_missing(tmp_path: Path):
    """A diff referencing a nonexistent file (non-new) should fail gracefully."""
    diff = (
        "--- a/missing.py\n"
        "+++ b/missing.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(diff)

    assert result.success is False
    assert "does not exist" in result.error


# ---------------------------------------------------------------------------
# 8. Diff to nonexistent file creates new file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_file_creation(tmp_path: Path):
    """A diff with /dev/null as old path should create a new file."""
    diff = (
        "--- /dev/null\n"
        "+++ b/brand_new.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+# new file\n"
        "+x = 42\n"
        "+print(x)\n"
    )
    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(diff)

    assert result.success is True
    assert "brand_new.py" in result.files_changed
    created = tmp_path / "brand_new.py"
    assert created.exists()
    content = created.read_text()
    assert "x = 42" in content
    assert "# new file" in content


# ---------------------------------------------------------------------------
# 9. Empty diff returns success with no changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_diff(tmp_path: Path):
    """An empty diff string should succeed with no files changed."""
    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply("")

    assert result.success is True
    assert result.files_changed == []
    assert result.backup_paths == {}


# ---------------------------------------------------------------------------
# 10. Backup paths are correct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_paths_correct(tmp_path: Path):
    """Backup paths should map original -> .bak correctly."""
    target = tmp_path / "hello.py"
    target.write_text("# header\nold_value = 1\n# footer\n")

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(_make_simple_diff())

    assert result.success is True
    assert str(target) in result.backup_paths
    backup = Path(result.backup_paths[str(target)])
    assert backup.suffix == ".bak"
    assert backup.exists()
    # Backup should contain original content
    assert "old_value = 1" in backup.read_text()


# ---------------------------------------------------------------------------
# 11. Multi-hunk diff applies correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_hunk_diff(tmp_path: Path):
    """A diff with two hunks in one file should apply both."""
    target = tmp_path / "multi.py"
    target.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")

    diff = (
        "--- a/multi.py\n"
        "+++ b/multi.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-line1\n"
        "+LINE1\n"
        " line2\n"
        " line3\n"
        "@@ -6,3 +6,3 @@\n"
        " line6\n"
        "-line7\n"
        "+LINE7\n"
        " line8\n"
    )
    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply(diff)

    assert result.success is True
    content = target.read_text()
    assert "LINE1" in content
    assert "LINE7" in content
    assert "line1" not in content
    assert "line7" not in content
    # Unchanged lines preserved
    assert "line2" in content
    assert "line6" in content


# ---------------------------------------------------------------------------
# 12. Timeout handling for test command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_and_test_timeout(tmp_path: Path):
    """A test command that exceeds timeout should trigger rollback."""
    target = tmp_path / "hello.py"
    original = "# header\nold_value = 1\n# footer\n"
    target.write_text(original)

    applier = DiffApplier(workspace=tmp_path)
    result = await applier.apply_and_test(
        _make_simple_diff(),
        test_command="python3 -c \"import time; time.sleep(10)\"",
        timeout=0.5,
    )

    assert result.applied is True
    assert result.tests_passed is False
    assert result.rolled_back is True
    assert "timed out" in result.error.lower()
    # File should be restored
    assert target.read_text() == original


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------


def test_parse_unified_diff_basic():
    """The parser should extract file paths and hunk lines."""
    diff = _make_simple_diff()
    patches = parse_unified_diff(diff)

    assert len(patches) == 1
    p = patches[0]
    assert p.target_path == "hello.py"
    assert len(p.hunks) == 1
    assert any("+new_value = 2" in line for line in p.hunks[0].lines)


def test_parse_empty_diff():
    """Empty string should produce no patches."""
    assert parse_unified_diff("") == []
    assert parse_unified_diff("   \n\n") == []


def test_parse_new_file_diff():
    """A diff creating a new file should set is_new_file."""
    diff = (
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+hello\n"
    )
    patches = parse_unified_diff(diff)
    assert len(patches) == 1
    assert patches[0].is_new_file is True
    assert patches[0].target_path == "new.py"
