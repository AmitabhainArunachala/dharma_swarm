from __future__ import annotations

from unittest.mock import patch


def test_modular_maintenance_pack_delegates_to_legacy_handler() -> None:
    from dharma_swarm.dgc.commands.ops import cmd_maintenance

    with patch("dharma_swarm.dgc_cli.cmd_maintenance") as legacy_mock:
        cmd_maintenance(dry_run=True, max_mb=12.0)

    legacy_mock.assert_called_once_with(dry_run=True, max_mb=12.0)
