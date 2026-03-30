"""Knowledge and orientation command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_field_scan() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_field_scan()


def cmd_field_gaps() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_field_gaps()


def cmd_field_position() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_field_position()


def cmd_field_unique() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_field_unique()


def cmd_field_summary() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_field_summary()


def cmd_foundations(pillar: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_foundations(pillar)


def cmd_telos(doc: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_telos(doc)


def build_field_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("field", help="D3 External AI Field Intelligence Engine")
    field_sub = parser.add_subparsers(dest="field_cmd")
    field_sub.add_parser("scan", help="Full D3 field intelligence scan with all reports")
    field_sub.add_parser("gaps", help="Show DGC capability gaps vs external field")
    field_sub.add_parser("position", help="Show DGC competitive positioning")
    field_sub.add_parser("unique", help="Show DGC unique moats")
    field_sub.add_parser("summary", help="Field KB summary statistics")


def handle_field(args: argparse.Namespace) -> None:
    try:
        match args.field_cmd:
            case "scan":
                cmd_field_scan()
            case "gaps":
                cmd_field_gaps()
            case "position":
                cmd_field_position()
            case "unique":
                cmd_field_unique()
            case "summary":
                cmd_field_summary()
            case _:
                raise SystemExit(2)
    except Exception as e:
        print(f"Field command failed: {e}")
        raise SystemExit(2) from e


def build_foundations_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("foundations", help="Intellectual pillars and syntheses")
    parser.add_argument("pillar", nargs="?", default=None, help="Pillar name to preview")


def handle_foundations(args: argparse.Namespace) -> None:
    cmd_foundations(args.pillar)


def build_telos_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("telos", help="Telos Engine research documents")
    parser.add_argument("doc", nargs="?", default=None, help="Document name to preview")


def handle_telos(args: argparse.Namespace) -> None:
    cmd_telos(args.doc)
