"""CLI entrypoint for scout pipeline health checks."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dharma_swarm.scout_audit import (
    HealthStatus,
    audit_pipeline,
    render_pipeline_markdown,
    write_pipeline_audit,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check scout pipeline health")
    parser.add_argument("--state-dir", default=str(Path.home() / ".dharma"))
    parser.add_argument("--expected-domain", action="append", default=[])
    parser.add_argument("--domain-max-age-hours", type=float, default=26.0)
    parser.add_argument("--synthesis-max-age-hours", type=float, default=26.0)
    parser.add_argument("--queue-max-age-hours", type=float, default=26.0)
    parser.add_argument("--require-synthesis", action="store_true")
    parser.add_argument("--require-queue", action="store_true")
    parser.add_argument("--write", action="store_true", help="Persist latest audit artifacts to ~/.dharma/scouts/health")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of markdown")
    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    audit = audit_pipeline(
        state_dir=Path(args.state_dir),
        expected_domains=tuple(args.expected_domain),
        now=now,
        domain_max_age_seconds=args.domain_max_age_hours * 3600.0,
        synthesis_max_age_seconds=args.synthesis_max_age_hours * 3600.0,
        queue_max_age_seconds=args.queue_max_age_hours * 3600.0,
        require_synthesis=args.require_synthesis,
        require_queue=args.require_queue,
    )
    if args.write:
        write_pipeline_audit(audit, output_dir=Path(args.state_dir) / "scouts" / "health")
    if args.json:
        print(audit.model_dump_json(indent=2))
    else:
        print(render_pipeline_markdown(audit), end="")
    return 1 if audit.status is HealthStatus.FAIL else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
