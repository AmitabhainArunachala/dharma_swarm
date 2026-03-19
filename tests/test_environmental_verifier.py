"""Focused tests for environmental_verifier.py."""

from __future__ import annotations

import pytest

from dharma_swarm.environmental_verifier import (
    VerificationStatus,
    verify_action,
)


@pytest.mark.asyncio
async def test_verify_action_auto_checks_write_file_python(tmp_path):
    """Common write_file actions should trigger file validation automatically."""
    target = tmp_path / "module.py"
    target.write_text("answer = 42\n")

    result = await verify_action(
        action_id="act-1",
        action_type="write_file",
        target=str(target),
    )

    assert result.overall == VerificationStatus.PASS
    assert [check.name for check in result.checks] == [
        "file_exists",
        "file_not_empty",
        "valid_python",
    ]
    assert result.prediction_error == 0.0


@pytest.mark.asyncio
async def test_verify_action_auto_checks_edit_file_invalid_python(tmp_path):
    """Syntax failures in edited Python files should not silently pass."""
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n")

    result = await verify_action(
        action_id="act-2",
        action_type="edit_file",
        target=str(target),
    )

    assert result.overall == VerificationStatus.FAIL
    assert result.checks[-1].name == "valid_python"
    assert result.checks[-1].status == VerificationStatus.FAIL
    assert result.prediction_error == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_verify_action_partial_expectations_still_auto_check_python(tmp_path):
    """Partial expectations should not suppress target-file validation."""
    target = tmp_path / "broken_with_expectation.py"
    target.write_text("def broken(:\n")

    result = await verify_action(
        action_id="act-2b",
        action_type="edit_file",
        target=str(target),
        expectations={"file_changed_after": 0},
    )

    assert result.overall == VerificationStatus.FAIL
    assert [check.name for check in result.checks] == [
        "file_changed",
        "file_exists",
        "file_not_empty",
        "valid_python",
    ]
    assert result.checks[-1].status == VerificationStatus.FAIL
    assert result.prediction_error == pytest.approx(1 / 4)


@pytest.mark.asyncio
async def test_verify_action_explicit_syntax_check_is_not_duplicated(tmp_path):
    """Explicit syntax expectations should merge with auto-checks without duplicates."""
    target = tmp_path / "module_with_expectation.py"
    target.write_text("answer = 42\n")

    result = await verify_action(
        action_id="act-2c",
        action_type="write_file",
        target=str(target),
        expectations={"valid_python": str(target)},
    )

    assert result.overall == VerificationStatus.PASS
    assert [check.name for check in result.checks] == [
        "valid_python",
        "file_exists",
        "file_not_empty",
    ]
    assert sum(check.name == "valid_python" for check in result.checks) == 1


@pytest.mark.asyncio
async def test_verify_action_skips_non_file_mutation_without_expectations(tmp_path):
    """Non-file actions should still skip when there is nothing deterministic to check."""
    target = tmp_path / "data.txt"
    target.write_text("payload\n")

    result = await verify_action(
        action_id="act-3",
        action_type="run_tests",
        target=str(target),
    )

    assert result.overall == VerificationStatus.SKIP
    assert result.checks == []


@pytest.mark.asyncio
async def test_verify_action_does_not_treat_directories_as_files(tmp_path):
    """Directory targets should not get file-content checks from generic create_file actions."""
    target = tmp_path / "artifact_dir"
    target.mkdir()

    result = await verify_action(
        action_id="act-4",
        action_type="create_file",
        target=str(target),
    )

    assert result.overall == VerificationStatus.SKIP
    assert result.checks == []
