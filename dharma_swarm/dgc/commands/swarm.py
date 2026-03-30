"""Swarm-oriented command pack for the modular DGC CLI."""

from __future__ import annotations


def cmd_swarm(extra_args: list[str]) -> None:
    """Delegate to the legacy swarm handler during migration."""
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_swarm(extra_args)
