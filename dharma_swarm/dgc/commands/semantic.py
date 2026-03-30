"""Semantic command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_semantic_digest(
    *,
    root: str,
    output: str | None = None,
    include_tests: bool = False,
    max_files: int = 500,
) -> None:
    """Delegate to the legacy semantic digest handler during migration."""
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_digest(
        root=root,
        output=output,
        include_tests=include_tests,
        max_files=max_files,
    )


def cmd_semantic_ingest(
    ingest_cmd: str | None,
    *,
    name: str | None = None,
    roots: list[str] | None = None,
    tags: list[str] | None = None,
    suffixes: list[str] | None = None,
    kind: str = "local_path",
    recursive: bool = True,
    enabled_only: bool = True,
    source_names: list[str] | None = None,
    max_files: int = 200,
    state_dir: str | None = None,
    query: str = "",
    limit: int = 10,
) -> None:
    """Delegate to the legacy semantic ingest handler during migration."""
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_ingest(
        ingest_cmd,
        name=name,
        roots=roots,
        tags=tags,
        suffixes=suffixes,
        kind=kind,
        recursive=recursive,
        enabled_only=enabled_only,
        source_names=source_names,
        max_files=max_files,
        state_dir=state_dir,
        query=query,
        limit=limit,
    )


def cmd_semantic_research(*, graph_path: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_research(graph_path=graph_path)


def cmd_semantic_synthesize(*, graph_path: str | None = None, max_clusters: int = 10) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_synthesize(graph_path=graph_path, max_clusters=max_clusters)


def cmd_semantic_harden(*, graph_path: str | None = None, root: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_harden(graph_path=graph_path, root=root)


def cmd_semantic_brief(
    *,
    graph_path: str | None = None,
    root: str,
    max_briefs: int = 3,
    json_output: str | None = None,
    markdown_output: str | None = None,
    state_dir: str | None = None,
    campaign_path: str | None = None,
) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_brief(
        graph_path=graph_path,
        root=root,
        max_briefs=max_briefs,
        json_output=json_output,
        markdown_output=markdown_output,
        state_dir=state_dir,
        campaign_path=campaign_path,
    )


def cmd_semantic_status(*, graph_path: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_status(graph_path=graph_path)


def cmd_semantic_proof(*, root: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_semantic_proof(root=root)


def build_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the semantic command parser."""
    from dharma_swarm import dgc_cli

    parser = subparsers.add_parser("semantic", help="Semantic Evolution Engine commands")
    sem_sub = parser.add_subparsers(dest="semantic_cmd")

    p_sd = sem_sub.add_parser("digest", help="Read codebase and build concept graph")
    p_sd.add_argument("--root", default=str(dgc_cli.DHARMA_SWARM), help="Project root")
    p_sd.add_argument("--output", default=None, help="Graph output path")
    p_sd.add_argument("--max-files", type=int, default=500, help="Safety cap on files processed during digest")
    p_sd.add_argument("--include-tests", action="store_true", help="Include test files in the digest")

    p_si = sem_sub.add_parser("ingest", help="Semantic ingestion spine commands")
    ingest_sub = p_si.add_subparsers(dest="semantic_ingest_cmd")

    p_sia = ingest_sub.add_parser("add-source", help="Register an ingestion source")
    p_sia.add_argument("name", help="Source name")
    p_sia.add_argument("--root", action="append", dest="roots", required=True, help="Source root path")
    p_sia.add_argument("--tag", action="append", dest="tags", default=[], help="Source tag")
    p_sia.add_argument("--suffix", action="append", dest="suffixes", default=[], help="Allowed file suffix")
    p_sia.add_argument("--kind", default="local_path", help="Source kind")
    p_sia.add_argument("--non-recursive", dest="recursive", action="store_false", help="Only scan the immediate directory level")
    p_sia.set_defaults(recursive=True)

    p_sil = ingest_sub.add_parser("list-sources", help="List configured ingestion sources")
    p_sil.add_argument("--all", dest="enabled_only", action="store_false", help="Show disabled sources too")
    p_sil.set_defaults(enabled_only=True)

    p_sird = ingest_sub.add_parser(
        "register-defaults",
        help="Seed the canonical semantic ingestion source registry",
    )
    p_sird.add_argument("--state-dir", default=None, help="Override dharma state root")

    p_sib = ingest_sub.add_parser(
        "bootstrap",
        help="Index the canonical concept graph into semantic ingestion memory",
    )
    p_sib.add_argument("--state-dir", default=None, help="Override dharma state root")

    p_sir = ingest_sub.add_parser("run", help="Run the semantic ingestion spine")
    p_sir.add_argument("--source", action="append", dest="source_names", default=None, help="Only run one source")
    p_sir.add_argument("--max-files", type=int, default=200, help="Per-source safety cap")
    p_sir.add_argument("--state-dir", default=None, help="Override dharma state root")

    p_sis = ingest_sub.add_parser("status", help="Show semantic ingestion spine status")
    p_sis.add_argument("--state-dir", default=None, help="Override dharma state root")

    p_siq = ingest_sub.add_parser("search", help="Search ingested semantic memory")
    p_siq.add_argument("query", nargs="+", help="Search query")
    p_siq.add_argument("--limit", type=int, default=10)
    p_siq.add_argument("--state-dir", default=None, help="Override dharma state root")

    p_sr = sem_sub.add_parser("research", help="Annotate graph with external research")
    p_sr.add_argument("--graph", default=None, help="Path to concept graph JSON")

    p_ss = sem_sub.add_parser("synthesize", help="Generate file cluster specs")
    p_ss.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_ss.add_argument("--max-clusters", type=int, default=10)

    p_sh = sem_sub.add_parser("harden", help="Run 6-angle hardening on clusters")
    p_sh.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_sh.add_argument("--root", default=str(dgc_cli.DHARMA_SWARM), help="Project root")

    p_sb = sem_sub.add_parser("brief", help="Compile semantic clusters into campaign briefs")
    p_sb.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_sb.add_argument("--root", default=str(dgc_cli.DHARMA_SWARM), help="Project root")
    p_sb.add_argument("--max-briefs", type=int, default=3)
    p_sb.add_argument("--json-output", default=None, help="Output path for brief packet JSON")
    p_sb.add_argument("--markdown-output", default=None, help="Output path for brief packet markdown")
    p_sb.add_argument("--state-dir", default=None, help="Override state root for campaign updates")
    p_sb.add_argument("--campaign-path", default=None, help="Explicit campaign.json path")

    p_sst = sem_sub.add_parser("status", help="Semantic graph status overview")
    p_sst.add_argument("--graph", default=None, help="Path to concept graph JSON")

    p_sp = sem_sub.add_parser("proof", help="Run live end-to-end proof of the semantic pipeline")
    p_sp.add_argument("--root", default=str(dgc_cli.DHARMA_SWARM), help="Project root")


def handle(args: argparse.Namespace) -> None:
    """Handle semantic commands using the modular parser namespace."""
    match args.semantic_cmd:
        case "digest":
            cmd_semantic_digest(
                root=args.root,
                output=args.output,
                include_tests=args.include_tests,
                max_files=args.max_files,
            )
        case "ingest":
            cmd_semantic_ingest(
                args.semantic_ingest_cmd,
                name=getattr(args, "name", None),
                roots=getattr(args, "roots", None),
                tags=getattr(args, "tags", None),
                suffixes=getattr(args, "suffixes", None),
                kind=getattr(args, "kind", "local_path"),
                recursive=getattr(args, "recursive", True),
                enabled_only=getattr(args, "enabled_only", True),
                source_names=getattr(args, "source_names", None),
                max_files=getattr(args, "max_files", 200),
                state_dir=getattr(args, "state_dir", None),
                query=" ".join(getattr(args, "query", []) or []),
                limit=getattr(args, "limit", 10),
            )
        case "research":
            cmd_semantic_research(graph_path=args.graph)
        case "synthesize":
            cmd_semantic_synthesize(graph_path=args.graph, max_clusters=args.max_clusters)
        case "harden":
            cmd_semantic_harden(graph_path=args.graph, root=args.root)
        case "brief":
            cmd_semantic_brief(
                graph_path=args.graph,
                root=args.root,
                max_briefs=args.max_briefs,
                json_output=args.json_output,
                markdown_output=args.markdown_output,
                state_dir=args.state_dir,
                campaign_path=args.campaign_path,
            )
        case "status":
            cmd_semantic_status(graph_path=args.graph)
        case "proof":
            cmd_semantic_proof(root=args.root)
        case _:
            raise SystemExit(2)
