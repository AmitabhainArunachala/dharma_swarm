"""System command handlers -- ported from old monolithic tui.py.

This module is decoupled from Textual. Every handler returns plain text
(with optional Rich markup) that the app routes to StreamOutput.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = Path(__file__).resolve().parent.parent.parent.parent


def _read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _file_age_str(path: Path) -> str:
    """Human-readable age string for a file's last modification time."""
    try:
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age < 60:
            return "just now"
        if age < 3600:
            return f"{int(age / 60)}m ago"
        if age < 86400:
            return f"{int(age / 3600)}h ago"
        return f"{int(age / 86400)}d ago"
    except Exception:
        return "?"


class SystemCommandHandler:
    """Handles all /commands, returning text output for the stream output widget.

    This class is decoupled from the TUI -- it just returns text.
    The app routes command output to StreamOutput.
    """

    def __init__(self) -> None:
        self.internet_enabled: bool = True
        self._conversation: list[dict[str, str]] = []
        self._conversation_max_pairs: int = 12
        self._mode: str = "N"

    @property
    def mode(self) -> str:
        """Current UI mode marker (N/A/P/S) mirrored from the app."""
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Set current mode marker used by command status output."""
        self._mode = mode if mode in {"N", "A", "P", "S"} else "N"

    def handle(self, raw: str) -> tuple[str, str | None]:
        """Handle a slash command.

        Args:
            raw: The raw command string (without leading '/').

        Returns:
            A tuple of (output_text, action).
            - output_text: Rich-markup string to display, or empty string.
            - action: None for immediate output, or a string signal:
              "clear", "cancel", "chat:new", "chat:continue",
              "paste", "copy", "copylast", "mode:set:<N|A|P|S>",
              "async:<cmd>:<arg>" for threaded commands.
        """
        parts = raw.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            return self._help(), None
        elif cmd == "clear":
            return "", "clear"
        elif cmd == "reset":
            self._conversation = []
            return "[dim]Conversation memory reset.[/dim]", None
        elif cmd == "cancel":
            return "", "cancel"
        elif cmd == "chat":
            mode = arg.strip().lower()
            if mode in {"", "new"}:
                return "", "chat:new"
            elif mode in {"continue", "cont", "resume", "c", "r"}:
                return "", "chat:continue"
            else:
                return "[red]Usage: /chat [continue][/red]", None
        elif cmd in {"paste", "copy", "copylast"}:
            return "", cmd
        elif cmd == "net":
            return self._handle_net(arg), None
        elif cmd == "plan":
            return self._handle_plan(arg)
        elif cmd == "model":
            return self._handle_model(arg)
        elif cmd == "thread":
            return self._handle_thread(arg), None
        elif cmd == "notes":
            return self._handle_notes(), None
        elif cmd == "trishula":
            return self._handle_trishula(), None
        elif cmd == "openclaw":
            return self._handle_openclaw(), None
        elif cmd == "moltbook":
            return self._handle_moltbook(), None
        elif cmd == "evidence":
            return self._handle_evidence(), None
        # Threaded commands (need @work in the app layer)
        elif cmd in {
            "status", "pulse", "health", "self", "context", "memory",
            "witness", "gates", "agni", "swarm", "evolve", "archive",
            "logs", "runtime", "git", "truth", "dharma", "corpus",
            "stigmergy", "hum",
        }:
            return "", f"async:{cmd}:{arg}"
        else:
            return f"[red]Unknown command: /{cmd}[/red]  (try /help)", None

    # ------------------------------------------------------------------
    # Synchronous command implementations
    # ------------------------------------------------------------------

    def _help(self) -> str:
        return (
            "[bold cyan]--- System ---[/bold cyan]\n"
            "  [cyan]/status[/cyan]          Full system status panel\n"
            "  [cyan]/health[/cyan]          Ecosystem health check\n"
            "  [cyan]/pulse[/cyan]           Run heartbeat\n"
            "  [cyan]/self[/cyan]            System self-map (modules, tests, state)\n"
            "  [cyan]/context[/cyan] [role]  Show agent context layers\n"
            "\n[bold cyan]--- Memory & Witness ---[/bold cyan]\n"
            "  [cyan]/memory[/cyan]          Strange loop memory + latent gold\n"
            "  [cyan]/witness[/cyan] <msg>   Record observation\n"
            "  [cyan]/notes[/cyan]           Shared agent notes\n"
            "  [cyan]/archive[/cyan]         Evolution archive (last 10)\n"
            "  [cyan]/logs[/cyan]            Tail system logs\n"
            "\n[bold cyan]--- Agents & Swarm ---[/bold cyan]\n"
            "  [cyan]/swarm[/cyan] [op]      Swarm: status | start [h] | stop | report | yolo\n"
            "  [cyan]/gates[/cyan] <action>  Test telos gates\n"
            "  [cyan]/evolve[/cyan] <c> <d>  Darwin Engine evolution\n"
            "  [cyan]/agni[/cyan] <cmd>      Run on AGNI VPS\n"
            "  [cyan]/trishula[/cyan]        Trishula inbox\n"
            "\n[bold cyan]--- Integrations ---[/bold cyan]\n"
            "  [cyan]/openclaw[/cyan]        OpenClaw agent status\n"
            "  [cyan]/evidence[/cyan]        Latest evidence bundle\n"
            "  [cyan]/runtime[/cyan]         Live process/runtime matrix\n"
            "  [cyan]/git[/cyan]             Repo branch/head/dirty counts\n"
            "\n[bold cyan]--- Dharma & Living Layers ---[/bold cyan]\n"
            "  [cyan]/dharma[/cyan] [status]  Dharma kernel/corpus status\n"
            "  [cyan]/corpus[/cyan]          List corpus claims\n"
            "  [cyan]/stigmergy[/cyan]       Hot paths and high salience marks\n"
            "  [cyan]/hum[/cyan]             Subconscious dreams\n"
            "\n[bold cyan]--- Chat & Control ---[/bold cyan]\n"
            "  [cyan]/thread[/cyan] [name]   Show/set research thread\n"
            "  [cyan]/net[/cyan] [on|off]    Internet mode for Claude\n"
            "  [cyan]/plan[/cyan] [on|off]   Enforce plan-first mode policy\n"
            "  [cyan]/model[/cyan] [op]      Model routing: status | list | set <alias|index> | auto on|off|responsive|cost|genius | metrics | cooldown status|clear\n"
            "  [cyan]/chat[/cyan] [continue] Launch full Claude Code UI\n"
            "  [cyan]/cancel[/cyan]          Cancel active Claude run\n"
            "  [cyan]/reset[/cyan]           Reset conversation memory\n"
            "  [cyan]/clear[/cyan]           Clear screen\n"
            "  [cyan]/help[/cyan]            This help\n\n"
            "[bold cyan]--- Keyboard ---[/bold cyan]\n"
            "  [cyan]Ctrl+O[/cyan]          Cycle mode: N(ormal) → A(uto) → P(lan) → S(age)\n"
            "  [cyan]Ctrl+L[/cyan]          Clear output\n"
            "  [cyan]Ctrl+N[/cyan]          New session\n"
            "  [cyan]Ctrl+C[/cyan]          Cancel active Claude run\n"
            "  [cyan]Ctrl+P[/cyan]          Command palette\n"
            "  [cyan]Shift+click[/cyan]     Select text for copy (terminal native)\n\n"
            "[dim]Plain text (no /) talks to Claude via stream-json.[/dim]"
        )

    def _handle_plan(self, arg: str) -> tuple[str, str | None]:
        """Enable/disable/status for hard Plan Mode."""
        mode = arg.strip().lower()
        if not mode or mode == "status":
            on = self._mode == "P"
            color = "blue" if on else "yellow"
            state = "ON" if on else "OFF"
            return (
                f"Plan mode: [{color}]{state}[/{color}] "
                "(use /plan on or /plan off)",
                None,
            )
        if mode in {"on", "enable", "1", "true"}:
            return (
                "[blue]Plan mode enabled.[/blue] "
                "Execution will wait for explicit approval.",
                "mode:set:P",
            )
        if mode in {"off", "disable", "0", "false"}:
            return (
                "[yellow]Plan mode disabled.[/yellow] Returning to Normal mode.",
                "mode:set:N",
            )
        return "[red]Usage: /plan [on|off|status][/red]", None

    def _handle_net(self, arg: str) -> str:
        mode = arg.strip().lower()
        if not mode or mode == "status":
            status = "ON" if self.internet_enabled else "OFF"
            color = "green" if self.internet_enabled else "yellow"
            return f"Internet mode: [{color}]{status}[/{color}]"
        if mode in {"on", "enable", "1", "true"}:
            self.internet_enabled = True
            return "[green]Internet mode enabled.[/green]"
        if mode in {"off", "disable", "0", "false"}:
            self.internet_enabled = False
            return "[yellow]Internet mode disabled.[/yellow]"
        return "[red]Usage: /net [on|off|status][/red]"

    def _handle_model(self, arg: str) -> tuple[str, str | None]:
        raw = arg.strip()
        if not raw or raw.lower() in {"status", "s"}:
            return "", "model:status"
        if raw.lower() in {"list", "ls"}:
            return "", "model:list"
        if raw.lower() in {"metrics", "health"}:
            return "", "model:metrics"
        if raw.lower().startswith("cooldown "):
            mode = raw[9:].strip().lower()
            if mode in {"status", "clear"}:
                return "", f"model:cooldown {mode}"
            return "[red]Usage: /model cooldown [status|clear][/red]", None
        if raw.lower() in {"reset", "clear-cooldowns", "clear"}:
            return "", "model:cooldown clear"
        if raw.lower().startswith("set "):
            target = raw[4:].strip()
            if not target:
                return "[red]Usage: /model set <alias|index>[/red]", None
            return "", f"model:set {target}"
        if raw.lower().startswith("auto "):
            mode = raw[5:].strip().lower()
            if mode in {"on", "off", "status", "responsive", "cost", "genius"}:
                return "", f"model:auto {mode}"
            return (
                "[red]Usage: /model auto [on|off|status|responsive|cost|genius][/red]",
                None,
            )
        if raw.lower().startswith("strategy "):
            mode = raw[9:].strip().lower()
            if mode in {"responsive", "cost", "genius"}:
                return "", f"model:auto {mode}"
            return "[red]Usage: /model strategy [responsive|cost|genius][/red]", None
        if raw.lower() in {"responsive", "cost", "genius"}:
            return "", f"model:auto {raw.lower()}"
        # Shortcut: /model opus
        return "", f"model:set {raw}"

    def _handle_thread(self, arg: str) -> str:
        if not arg:
            thread_file = DHARMA_STATE / "thread_state.json"
            if thread_file.exists():
                try:
                    ts = json.loads(thread_file.read_text())
                    return f"Active thread: [cyan]{ts.get('current_thread', 'unknown')}[/cyan]"
                except Exception:
                    return "[dim]Thread state unreadable.[/dim]"
            return "[dim]No active thread.[/dim]"
        focus_file = DHARMA_STATE / ".FOCUS"
        DHARMA_STATE.mkdir(parents=True, exist_ok=True)
        focus_file.write_text(arg.strip())
        return f"Thread set to [cyan]{arg.strip()}[/cyan] (wrote .FOCUS)"

    def _handle_notes(self) -> str:
        shared = DHARMA_STATE / "shared"
        if not shared.exists():
            return "[dim]No agent notes.[/dim]"
        lines: list[str] = []
        for f in sorted(
            shared.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:10]:
            try:
                content = f.read_text()[:300]
                lines.append(
                    f"[bold cyan]{f.name}[/bold cyan]  [dim]{_file_age_str(f)}[/dim]"
                )
                for line in content.split("\n")[:3]:
                    lines.append(f"  {line}")
            except Exception:
                pass
        return "\n".join(lines) if lines else "[dim]No agent notes.[/dim]"

    def _handle_trishula(self) -> str:
        inbox = HOME / "trishula" / "inbox"
        if not inbox.exists():
            return "[dim]Trishula inbox not found.[/dim]"
        lines: list[str] = []
        found = False
        for f in sorted(
            inbox.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:5]:
            try:
                lines.append(f"[bold magenta]{f.name}[/bold magenta]")
                for line in f.read_text()[:200].split("\n")[:3]:
                    lines.append(f"  {line}")
                found = True
            except Exception:
                pass
        if not found:
            return "[dim]No messages in trishula inbox.[/dim]"
        lines.append("[dim]Showing latest 5 messages.[/dim]")
        return "\n".join(lines)

    def _handle_openclaw(self) -> str:
        oc_path = HOME / ".openclaw" / "openclaw.json"
        oc = _read_json(oc_path)
        if not oc:
            return "[dim]OpenClaw not found (~/.openclaw/openclaw.json)[/dim]"

        lines: list[str] = []

        # Meta
        meta = oc.get("meta", {})
        if isinstance(meta, dict) and meta.get("lastTouchedVersion"):
            lines.append(
                f"  [bold white]Version[/bold white]: {meta['lastTouchedVersion']}"
            )

        # Agents
        agents = oc.get("agents", {})
        if isinstance(agents, dict):
            ag_list = agents.get("list", [])
            defaults = agents.get("defaults", {})
            primary = defaults.get("model", {}).get("primary", "?") if isinstance(defaults.get("model"), dict) else "?"
            lines.append(
                f"  [bold white]Agents[/bold white]: {len(ag_list)}  "
                f"(primary: [cyan]{primary}[/cyan])"
            )
            for ag in ag_list[:5]:
                name = ag.get("id", "?") if isinstance(ag, dict) else str(ag)
                model = ag.get("model", "") if isinstance(ag, dict) else ""
                lines.append(f"    [cyan]{name}[/cyan]  {model}")

        # Models/providers
        models = oc.get("models", {})
        if isinstance(models, dict):
            providers = models.get("providers", {})
            if isinstance(providers, dict):
                prov_summary = ", ".join(
                    f"{k}({len(v.get('models', []))})"
                    for k, v in providers.items()
                    if isinstance(v, dict)
                )
                lines.append(
                    f"  [bold white]Providers[/bold white]: {prov_summary}"
                )

        # Skills
        skills = oc.get("skills", {})
        if isinstance(skills, dict) and skills:
            lines.append(
                f"  [bold white]Skills[/bold white]: {len(skills)}"
            )

        # Channels
        channels = oc.get("channels", {})
        if isinstance(channels, dict) and channels:
            lines.append(
                f"  [bold white]Channels[/bold white]: {', '.join(channels.keys())}"
            )

        # Gateway
        gw = oc.get("gateway", {})
        if isinstance(gw, dict) and gw.get("port"):
            lines.append(
                f"  [bold white]Gateway[/bold white]: "
                f"port={gw['port']} mode={gw.get('mode', '?')}"
            )

        return "\n".join(lines) if lines else "[dim]OpenClaw config empty.[/dim]"

    def _handle_moltbook(self) -> str:
        state_file = DHARMA_STATE / "moltbook" / "state.json"
        mb = _read_json(state_file)
        if mb:
            return (
                f"  [bold white]Tracked posts[/bold white]: {mb.get('tracked', 0)}\n"
                f"  [bold white]Our comments[/bold white]: {mb.get('comments', 0)}\n"
                f"  [bold white]Engaged posts[/bold white]: {mb.get('engaged', 0)}\n"
                f"  [bold white]Last heartbeat[/bold white]: {mb.get('heartbeat', 'never')}"
            )
        return "[dim]Moltbook state not found.[/dim]"

    def _handle_evidence(self) -> str:
        ev_dir = DHARMA_STATE / "evidence"
        if not ev_dir.exists():
            return "[dim]No evidence bundles found.[/dim]"
        bundles = sorted(
            ev_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not bundles:
            return "[dim]No evidence bundles found.[/dim]"
        ev = _read_json(bundles[0])
        if ev:
            return (
                f"  [bold white]Result[/bold white]: {ev.get('overall', 'n/a')}\n"
                f"  [bold white]Hash[/bold white]: {ev.get('hash', 'n/a')}"
            )
        return "[dim]Evidence bundle unreadable.[/dim]"
