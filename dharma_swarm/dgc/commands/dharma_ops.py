"""Dharma, stigmergy, and cascade command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_dharma(
    dharma_cmd: str | None,
    *,
    corpus_status: str | None = None,
    corpus_category: str | None = None,
    claim_id: str | None = None,
) -> None:
    from dharma_swarm import dgc_cli

    match dharma_cmd:
        case "status":
            dgc_cli.cmd_dharma_status()
        case "corpus":
            dgc_cli.cmd_dharma_corpus(corpus_status, corpus_category)
        case "review":
            if claim_id is None:
                raise SystemExit(2)
            dgc_cli.cmd_dharma_review(claim_id)
        case _:
            raise SystemExit(2)


def cmd_stigmergy(file_path: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_stigmergy(file_path)


def cmd_hum() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_hum()


def cmd_cascade(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_cascade(**kwargs)


def cmd_forge(path: str | None = None, batch: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_forge(path=path, batch=batch)


def cmd_loops() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_loops()


def build_dharma_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("dharma", help="Dharma subsystem commands")
    dharma_sub = parser.add_subparsers(dest="dharma_cmd")
    dharma_sub.add_parser("status", help="Dharma subsystem status")
    corpus = dharma_sub.add_parser("corpus", help="List corpus claims")
    corpus.add_argument("--status", dest="corpus_status", default=None)
    corpus.add_argument("--category", dest="corpus_category", default=None)
    review = dharma_sub.add_parser("review", help="Review a claim")
    review.add_argument("claim_id")


def handle_dharma(args: argparse.Namespace) -> None:
    cmd_dharma(
        args.dharma_cmd,
        corpus_status=getattr(args, "corpus_status", None),
        corpus_category=getattr(args, "corpus_category", None),
        claim_id=getattr(args, "claim_id", None),
    )


def build_stigmergy_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stigmergy", help="Stigmergy marks and hot paths")
    parser.add_argument("--file", dest="stig_file", default=None)


def handle_stigmergy(args: argparse.Namespace) -> None:
    cmd_stigmergy(args.stig_file)


def build_hum_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("hum", help="Subconscious associations")


def handle_hum(_args: argparse.Namespace) -> None:
    cmd_hum()


def build_cascade_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("cascade", help="Run strange loop cascade domain")
    parser.add_argument("domain", nargs="?", default="code")
    parser.add_argument("--seed-path", default=None)
    parser.add_argument("--seed-skill", default=None)
    parser.add_argument("--seed-project", default=None)
    parser.add_argument("--track", default=None)
    parser.add_argument("--max-iter", type=int, default=None)


def handle_cascade(args: argparse.Namespace) -> None:
    cmd_cascade(
        domain=args.domain,
        seed_path=args.seed_path,
        seed_skill=args.seed_skill,
        seed_project=args.seed_project,
        track=args.track,
        max_iter=args.max_iter,
    )


def build_forge_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("forge", help="Score artifact through quality forge")
    parser.add_argument("path", nargs="?", default=None)
    parser.add_argument("--batch", default=None)


def handle_forge(args: argparse.Namespace) -> None:
    cmd_forge(path=args.path, batch=args.batch)


def build_loops_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("loops", help="Show strange loop status and cascade history")


def handle_loops(_args: argparse.Namespace) -> None:
    cmd_loops()
