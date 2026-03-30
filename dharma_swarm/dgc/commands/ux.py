"""Operator UX command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _build_chat_context_snapshot(*, state_dir: Path, home: Path) -> str:
    """Build a compact DGC context snapshot for chat sessions."""
    from dharma_swarm.prompt_builder import build_state_context_snapshot

    return build_state_context_snapshot(
        state_dir=state_dir,
        home=home,
        max_chars=6000,
    )


def cmd_chat(
    continue_last: bool = False,
    offline: bool = False,
    model: str | None = None,
    effort: str | None = None,
    include_context: bool = True,
) -> None:
    """Launch native Claude Code interactive UI."""
    from dharma_swarm import dgc_cli

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
    if offline:
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    cmd = ["claude"]
    if continue_last:
        cmd.append("--continue")
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])

    if include_context:
        snapshot = _build_chat_context_snapshot(state_dir=dgc_cli.DHARMA_STATE, home=dgc_cli.HOME)
        if snapshot:
            cmd.extend(
                [
                    "--append-system-prompt",
                    "DGC mission-control context snapshot. Treat as hints and verify.\n\n" + snapshot,
                ]
            )

    try:
        os.execvpe("claude", cmd, env)
    except FileNotFoundError:
        print("claude CLI not found. Install Claude Code first.")
        sys.exit(1)
    except Exception as exc:
        print(f"Failed to launch Claude Code: {exc}")
        sys.exit(1)


def cmd_tui() -> None:
    """Launch the interactive TUI dashboard."""
    try:
        from dharma_swarm.tui import run

        run()
    except Exception:
        from dharma_swarm.tui_legacy import run_tui

        run_tui()


def cmd_ui(surface: str = "list") -> None:
    """Print the canonical operator-surface map."""
    root = Path.home() / "dharma_swarm"
    dashboard_dir = root / "dashboard"
    lines: list[str] = []

    if surface == "tui":
        lines.extend(
            [
                "TUI",
                "- primary operator cockpit: dgc dashboard",
                f"- direct module: python3 -m dharma_swarm.tui",
                f"- code: {root / 'dharma_swarm' / 'tui' / 'app.py'}",
            ]
        )
    elif surface == "api":
        lines.extend(
            [
                "API",
                f"- command: cd {root} && python3 -m uvicorn api.main:app --port 8000",
                "- url: http://127.0.0.1:8000",
                "- docs: http://127.0.0.1:8000/docs",
            ]
        )
    elif surface == "next":
        lines.extend(
            [
                "DHARMA COMMAND",
                f"- command: cd {dashboard_dir} && npm run dev",
                "- url: http://127.0.0.1:3000/dashboard",
                "- backend dependency: api.main on port 8000",
                f"- frontend root: {dashboard_dir}",
            ]
        )
    elif surface == "lens":
        lines.extend(
            [
                "SWARMLENS",
                f"- command: cd {root} && python3 -m uvicorn dharma_swarm.swarmlens_app:app --port 8080",
                "- url: http://127.0.0.1:8080",
                "- likely the older website you remember",
                f"- code: {root / 'dharma_swarm' / 'swarmlens_app.py'}",
            ]
        )
    else:
        lines.extend(
            [
                "Operator surfaces",
                "- `dgc dashboard` -> primary terminal TUI",
                f"  code: {root / 'dharma_swarm' / 'tui' / 'app.py'}",
                "- `dgc ui next` -> newer web control plane",
                f"  launch: cd {dashboard_dir} && npm run dev",
                "  url: http://127.0.0.1:3000/dashboard",
                "  needs backend: python3 -m uvicorn api.main:app --port 8000",
                "- `dgc ui lens` -> older SwarmLens website",
                f"  launch: cd {root} && python3 -m uvicorn dharma_swarm.swarmlens_app:app --port 8080",
                "  url: http://127.0.0.1:8080",
                "  note: this is likely the older website you remember",
                "- `dgc ui api` -> backend API only",
                "  url: http://127.0.0.1:8000/docs",
            ]
        )

    print("\n".join(lines))


def build_chat_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("chat", help="Launch native Claude Code interactive UI")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue the most recent Claude session in this directory")
    parser.add_argument("--offline", action="store_true", help="Disable nonessential network traffic for Claude session")
    parser.add_argument("--model", default=None, help="Claude model alias/name")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default=None, help="Reasoning effort level")
    parser.add_argument("--no-context", action="store_true", help="Do not append DGC state snapshot to Claude system prompt")


def handle_chat(args: argparse.Namespace) -> None:
    cmd_chat(
        continue_last=args.continue_last,
        offline=args.offline,
        model=args.model,
        effort=args.effort,
        include_context=not args.no_context,
    )


def build_dashboard_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("dashboard", help="Launch DGC dashboard (TUI)")


def handle_dashboard(_args: argparse.Namespace) -> None:
    cmd_tui()


def build_ui_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ui", help="Show canonical operator-surface launch paths")
    parser.add_argument("surface", nargs="?", default="list", choices=("list", "tui", "api", "next", "lens"))


def handle_ui(args: argparse.Namespace) -> None:
    cmd_ui(args.surface)
