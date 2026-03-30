"""Status-oriented command pack for the modular DGC CLI."""

from __future__ import annotations


def cmd_status() -> None:
    """Delegate to the legacy status handler during migration."""
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_status()


def cmd_runtime_status(*, limit: int = 5, db_path: str | None = None) -> None:
    """Delegate to the legacy runtime-status handler during migration."""
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_runtime_status(limit=limit, db_path=db_path)
