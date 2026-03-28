"""Shared Claude CLI helpers for unattended/background execution."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Mapping

_MODEL_ALIASES: dict[str, str] = {
    "flash": "haiku",
    "gemini": "haiku",
    "gpt4": "sonnet",
    "gpt-4": "sonnet",
}


def resolve_claude_binary() -> str:
    """Find the Claude CLI binary, checking known install locations."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (
        Path.home() / ".npm-global" / "bin" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ):
        if candidate.exists():
            return str(candidate)
    return "claude"


def build_claude_headless_command(
    prompt: str,
    *,
    model: str | None = None,
    output_format: str = "text",
    permission_mode: str | None = None,
    bare: bool = False,
    tools: str | None = "default",
) -> list[str]:
    """Build a `claude -p` command for unattended/background runs."""
    command = [
        resolve_claude_binary(),
        "-p",
        prompt,
        "--output-format",
        output_format,
    ]
    if model:
        resolved = _MODEL_ALIASES.get(model.lower(), model)
        command.extend(["--model", resolved])
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])
    if bare:
        command.append("--bare")
    if tools:
        command.extend(["--tools", tools])
    return command


def build_claude_headless_env(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Prepare a stable environment for nested/background Claude runs."""
    merged = dict(os.environ if env is None else env)
    merged["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    merged.pop("CLAUDECODE", None)
    merged.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return merged


def unattended_claude_auth_error(
    *,
    bare: bool,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return a fast-fail error when unattended Claude auth is unavailable.

    In `--bare` mode Claude Code skips OAuth/keychain auth entirely and requires
    an Anthropic API credential path. The unattended DGC lanes currently do not
    pass a settings-based apiKeyHelper, so a non-empty `ANTHROPIC_API_KEY` is
    the only supported auth source here.
    """
    if not bare:
        return None
    merged = build_claude_headless_env(env)
    if merged.get("ANTHROPIC_API_KEY", "").strip():
        return None
    return (
        "ERROR: unattended Claude bare mode requires ANTHROPIC_API_KEY; "
        "OAuth/login is ignored in --bare mode"
    )


def run_claude_headless(
    prompt: str,
    *,
    timeout: int = 600,
    model: str | None = None,
    permission_mode: str | None = "bypassPermissions",
    bare: bool = True,
    tools: str | None = "default",
) -> str:
    """Run Claude Code in headless mode for unattended/background work."""
    env = build_claude_headless_env()
    auth_error = unattended_claude_auth_error(bare=bare, env=env)
    if auth_error:
        return auth_error
    try:
        result = subprocess.run(
            build_claude_headless_command(
                prompt,
                model=model,
                permission_mode=permission_mode,
                bare=bare,
                tools=tools,
            ),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout[:5000]
        detail = result.stderr or result.stdout or ""
        return f"Error (rc={result.returncode}): {detail[:500]}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT: Claude Code exceeded limit"
    except FileNotFoundError:
        return "ERROR: claude CLI not found in PATH"
    except Exception as exc:
        return f"ERROR: {exc}"
