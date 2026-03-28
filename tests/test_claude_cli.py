from __future__ import annotations

from dharma_swarm.claude_cli import (
    build_claude_headless_command,
    build_claude_headless_env,
    unattended_claude_auth_error,
)


def test_build_claude_headless_command_uses_bare_builtin_tools() -> None:
    command = build_claude_headless_command(
        "summarize",
        model="haiku",
        permission_mode="bypassPermissions",
        bare=True,
    )

    assert command[1:4] == ["-p", "summarize", "--output-format"]
    assert "--model" in command
    assert "--permission-mode" in command
    assert "--bare" in command
    assert "--tools" in command
    tools_index = command.index("--tools")
    assert command[tools_index + 1] == "default"


def test_build_claude_headless_env_clears_nested_session_markers() -> None:
    env = build_claude_headless_env(
        {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_ENTRYPOINT": "nested",
            "PATH": "/bin",
        }
    )

    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"


def test_unattended_claude_auth_error_requires_key_in_bare_mode() -> None:
    error = unattended_claude_auth_error(
        bare=True,
        env={"PATH": "/bin", "ANTHROPIC_API_KEY": ""},
    )

    assert error is not None
    assert "ANTHROPIC_API_KEY" in error


def test_unattended_claude_auth_error_allows_non_bare_without_key() -> None:
    assert unattended_claude_auth_error(
        bare=False,
        env={"PATH": "/bin", "ANTHROPIC_API_KEY": ""},
    ) is None


def test_unattended_claude_auth_error_allows_bare_with_key() -> None:
    assert unattended_claude_auth_error(
        bare=True,
        env={"PATH": "/bin", "ANTHROPIC_API_KEY": "sk-ant-test"},
    ) is None
