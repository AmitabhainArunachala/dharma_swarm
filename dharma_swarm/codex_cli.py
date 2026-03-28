"""Shared Codex CLI launch defaults for DGC-owned execution paths."""

from __future__ import annotations

import os

DGC_CODEX_PROFILE_ENV = "DGC_CODEX_PROFILE"


def dgc_codex_exec_prefix(*, cli_path: str = "codex") -> list[str]:
    """Return the Codex exec prefix for DGC-owned launches.

    DGC runs Codex with the most permissive execution surface available.
    An optional profile can still be layered on via ``DGC_CODEX_PROFILE``.
    """

    cmd = [cli_path, "exec"]
    profile = os.environ.get(DGC_CODEX_PROFILE_ENV, "").strip()
    if profile:
        cmd.extend(["-p", profile])
    cmd.append("--dangerously-bypass-approvals-and-sandbox")
    return cmd
