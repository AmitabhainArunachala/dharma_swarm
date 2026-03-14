"""System command handlers -- ported from old monolithic tui.py.

This module is decoupled from Textual. Every handler returns plain text
(with optional Rich markup) that the app routes to StreamOutput.
"""

from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = Path(__file__).resolve().parent.parent.parent.parent
INDIGO = "#9C7444"
INDIGO_DIM = "#8C8278"
VERDIGRIS = "#62725D"
OCHRE = "#A17A47"
BENGARA = "#8C5448"
WISTERIA = "#74677D"

_SYNC_COMMANDS = frozenset(
    {
        "help",
        "clear",
        "reset",
        "cancel",
        "chat",
        "paste",
        "copy",
        "copylast",
        "btw",
        "net",
        "plan",
        "model",
        "thread",
        "notes",
        "trishula",
        "openclaw",
        "moltbook",
        "evidence",
        "dashboard",
    }
)
_ASYNC_COMMANDS = frozenset(
    {
        "status",
        "pulse",
        "health",
        "self",
        "context",
        "memory",
        "witness",
        "gates",
        "agni",
        "swarm",
        "evolve",
        "darwin",
        "archive",
        "logs",
        "runtime",
        "git",
        "truth",
        "dharma",
        "corpus",
        "stigmergy",
        "hum",
    }
)
_ALL_COMMANDS = _SYNC_COMMANDS | _ASYNC_COMMANDS
_SAFE_AUTOCORRECT_COMMANDS = frozenset(
    {
        "status",
        "pulse",
        "health",
        "self",
        "context",
        "memory",
        "darwin",
        "archive",
        "logs",
        "runtime",
        "git",
        "truth",
        "dharma",
        "corpus",
        "stigmergy",
        "hum",
        "notes",
        "trishula",
        "openclaw",
        "moltbook",
        "evidence",
    }
)
_COMMAND_ALIASES = {
    "darkwin": "darwin",
}


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
                return f"[{BENGARA}]Usage: /chat [continue][/{BENGARA}]", None
        elif cmd == "btw":
            return "", "btw:open"
        elif cmd == "dashboard":
            return "", "dashboard:open"
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
        elif cmd in _ASYNC_COMMANDS:
            return "", f"async:{cmd}:{arg}"
        else:
            suggestion = self.suggest_command(cmd)
            if suggestion:
                return (
                    f"[{BENGARA}]Unknown command: /{cmd}[/{BENGARA}]  "
                    f"[{OCHRE}](did you mean /{suggestion}?)[/{OCHRE}]",
                    None,
                )
            return f"[{BENGARA}]Unknown command: /{cmd}[/{BENGARA}]  (try /help)", None

    def suggest_command(self, raw: str) -> str | None:
        """Return the nearest known command for typo recovery, if any."""
        cmd = raw.strip().lower()
        if not cmd:
            return None
        alias = _COMMAND_ALIASES.get(cmd)
        if alias:
            return alias
        if cmd in _ALL_COMMANDS:
            return cmd
        matches = difflib.get_close_matches(cmd, sorted(_ALL_COMMANDS), n=1, cutoff=0.8)
        return matches[0] if matches else None

    def resolve_bare_command(self, raw: str) -> tuple[str | None, str | None]:
        """Resolve a bare single-word input into a slash command or suggestion."""
        text = raw.strip()
        if not text or text.startswith("/") or len(text.split()) != 1:
            return None, None

        cmd = text.lower()
        if cmd in _ALL_COMMANDS:
            return cmd, None

        suggestion = self.suggest_command(cmd)
        if not suggestion or suggestion == cmd:
            return None, None

        if suggestion in _SAFE_AUTOCORRECT_COMMANDS:
            return suggestion, f"[dim]Assuming /{suggestion}.[/dim]"

        return None, f"[{OCHRE}]Did you mean /{suggestion}?[/{OCHRE}]"

    # ------------------------------------------------------------------
    # Synchronous command implementations
    # ------------------------------------------------------------------

    def _help(self) -> str:
        return (
            f"[bold {INDIGO}]--- System ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/status[/{INDIGO}]          Full system status panel\n"
            f"  [{INDIGO}]/health[/{INDIGO}]          Ecosystem health check\n"
            f"  [{INDIGO}]/pulse[/{INDIGO}]           Run heartbeat\n"
            f"  [{INDIGO}]/self[/{INDIGO}]            System self-map (modules, tests, state)\n"
            f"  [{INDIGO}]/context[/{INDIGO}] [role]  Show agent context layers\n"
            f"\n[bold {INDIGO}]--- Memory & Witness ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/memory[/{INDIGO}]          Strange loop memory + latent gold\n"
            f"  [{INDIGO}]/witness[/{INDIGO}] <msg>   Record observation\n"
            f"  [{INDIGO}]/notes[/{INDIGO}]           Shared agent notes\n"
            f"  [{INDIGO}]/archive[/{INDIGO}]         Evolution archive (last 10)\n"
            f"  [{INDIGO}]/darwin[/{INDIGO}]          Darwin experiment memory + trust ladder\n"
            f"  [{INDIGO}]/logs[/{INDIGO}]            Tail system logs\n"
            f"\n[bold {INDIGO}]--- Agents & Swarm ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/swarm[/{INDIGO}] [op]      Swarm: status | start [h] | stop | report | yolo\n"
            f"  [{INDIGO}]/gates[/{INDIGO}] <action>  Test telos gates\n"
            f"  [{INDIGO}]/evolve[/{INDIGO}] <c> <d>  Darwin Engine evolution\n"
            f"  [{INDIGO}]/evolve status[/{INDIGO}]   Darwin operator visibility\n"
            f"  [{INDIGO}]/agni[/{INDIGO}] <cmd>      Run on AGNI VPS\n"
            f"  [{INDIGO}]/trishula[/{INDIGO}]        Trishula inbox\n"
            f"\n[bold {INDIGO}]--- Integrations ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/openclaw[/{INDIGO}]        OpenClaw agent status\n"
            f"  [{INDIGO}]/evidence[/{INDIGO}]        Latest evidence bundle\n"
            f"  [{INDIGO}]/runtime[/{INDIGO}]         Live process/runtime matrix\n"
            f"  [{INDIGO}]/git[/{INDIGO}]             Repo branch/head/dirty counts\n"
            f"\n[bold {INDIGO}]--- Dharma & Living Layers ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/dharma[/{INDIGO}] [status]  Dharma kernel/corpus status\n"
            f"  [{INDIGO}]/corpus[/{INDIGO}]          List corpus claims\n"
            f"  [{INDIGO}]/stigmergy[/{INDIGO}]       Hot paths and high salience marks\n"
            f"  [{INDIGO}]/hum[/{INDIGO}]             Subconscious dreams\n"
            f"\n[bold {INDIGO}]--- Chat & Control ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]/thread[/{INDIGO}] [name]   Show/set research thread\n"
            f"  [{INDIGO}]/net[/{INDIGO}] [on|off]    Internet access for the active route\n"
            f"  [{INDIGO}]/plan[/{INDIGO}] [on|off]   Enforce plan-first mode policy\n"
            f"  [{INDIGO}]/model[/{INDIGO}] [op]      Model routing: status | list | set <alias|index> | auto on|off|responsive|cost|genius | metrics | cooldown status|clear\n"
            f"  [{INDIGO}]/chat[/{INDIGO}] [continue] Launch native Claude Code UI\n"
            f"  [{INDIGO}]/btw[/{INDIGO}] [topic]     Open a parallel side-thread window with merge-back\n"
            f"  [{INDIGO}]/cancel[/{INDIGO}]          Cancel active provider run\n"
            f"  [{INDIGO}]/reset[/{INDIGO}]           Reset conversation memory\n"
            f"  [{INDIGO}]/clear[/{INDIGO}]           Clear screen\n"
            f"  [{INDIGO}]/help[/{INDIGO}]            This help\n\n"
            f"[bold {INDIGO}]--- Keyboard ---[/bold {INDIGO}]\n"
            f"  [{INDIGO}]Ctrl+O[/{INDIGO}]          Cycle mode: N(ormal) → A(uto) → P(lan) → S(age)\n"
            f"  [{INDIGO}]Ctrl+L[/{INDIGO}]          Clear output\n"
            f"  [{INDIGO}]Ctrl+N[/{INDIGO}]          New session\n"
            f"  [{INDIGO}]Ctrl+C[/{INDIGO}]          Cancel active run / copy last reply when idle\n"
            f"  [{INDIGO}]Ctrl+P[/{INDIGO}]          Command palette\n"
            f"  [{INDIGO}]Ctrl+Y[/{INDIGO}]          Copy last reply\n"
            f"  [{INDIGO}]Shift+click[/{INDIGO}]     Select text for copy (terminal native)\n\n"
            "[dim]Plain text (no /) sends to the active route with live tools, usage, and cost telemetry.[/dim]"
        )

    def _handle_plan(self, arg: str) -> tuple[str, str | None]:
        """Enable/disable/status for hard Plan Mode."""
        mode = arg.strip().lower()
        if not mode or mode == "status":
            on = self._mode == "P"
            color = INDIGO if on else OCHRE
            state = "ON" if on else "OFF"
            return (
                f"Plan mode: [{color}]{state}[/{color}] "
                "(use /plan on or /plan off)",
                None,
            )
        if mode in {"on", "enable", "1", "true"}:
            return (
                f"[{INDIGO}]Plan mode enabled.[/{INDIGO}] "
                "Execution will wait for explicit approval.",
                "mode:set:P",
            )
        if mode in {"off", "disable", "0", "false"}:
            return (
                f"[{OCHRE}]Plan mode disabled.[/{OCHRE}] Returning to Normal mode.",
                "mode:set:N",
            )
        return f"[{BENGARA}]Usage: /plan [on|off|status][/{BENGARA}]", None

    def _handle_net(self, arg: str) -> str:
        mode = arg.strip().lower()
        if not mode or mode == "status":
            status = "ON" if self.internet_enabled else "OFF"
            color = VERDIGRIS if self.internet_enabled else OCHRE
            return f"Internet mode: [{color}]{status}[/{color}]"
        if mode in {"on", "enable", "1", "true"}:
            self.internet_enabled = True
            return f"[{VERDIGRIS}]Internet mode enabled.[/{VERDIGRIS}]"
        if mode in {"off", "disable", "0", "false"}:
            self.internet_enabled = False
            return f"[{OCHRE}]Internet mode disabled.[/{OCHRE}]"
        return f"[{BENGARA}]Usage: /net [on|off|status][/{BENGARA}]"

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
            return f"[{BENGARA}]Usage: /model cooldown [status|clear][/{BENGARA}]", None
        if raw.lower() in {"reset", "clear-cooldowns", "clear"}:
            return "", "model:cooldown clear"
        if raw.lower().startswith("set "):
            target = raw[4:].strip()
            if not target:
                return f"[{BENGARA}]Usage: /model set <alias|index>[/{BENGARA}]", None
            return "", f"model:set {target}"
        if raw.lower().startswith("auto "):
            mode = raw[5:].strip().lower()
            if mode in {"on", "off", "status", "responsive", "cost", "genius"}:
                return "", f"model:auto {mode}"
            return (
                f"[{BENGARA}]Usage: /model auto [on|off|status|responsive|cost|genius][/{BENGARA}]",
                None,
            )
        if raw.lower().startswith("strategy "):
            mode = raw[9:].strip().lower()
            if mode in {"responsive", "cost", "genius"}:
                return "", f"model:auto {mode}"
            return f"[{BENGARA}]Usage: /model strategy [responsive|cost|genius][/{BENGARA}]", None
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
                    return (
                        f"Active thread: "
                        f"[{INDIGO}]{ts.get('current_thread', 'unknown')}[/{INDIGO}]"
                    )
                except Exception:
                    return "[dim]Thread state unreadable.[/dim]"
            return "[dim]No active thread.[/dim]"
        focus_file = DHARMA_STATE / ".FOCUS"
        DHARMA_STATE.mkdir(parents=True, exist_ok=True)
        focus_file.write_text(arg.strip())
        return f"Thread set to [{INDIGO}]{arg.strip()}[/{INDIGO}] (wrote .FOCUS)"

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
                    f"[bold {INDIGO}]{f.name}[/bold {INDIGO}]  [dim]{_file_age_str(f)}[/dim]"
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
                lines.append(f"[bold {WISTERIA}]{f.name}[/bold {WISTERIA}]")
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
                f"  [bold {INDIGO_DIM}]Version[/bold {INDIGO_DIM}]: {meta['lastTouchedVersion']}"
            )

        # Agents
        agents = oc.get("agents", {})
        if isinstance(agents, dict):
            ag_list = agents.get("list", [])
            defaults = agents.get("defaults", {})
            primary = defaults.get("model", {}).get("primary", "?") if isinstance(defaults.get("model"), dict) else "?"
            lines.append(
                f"  [bold {INDIGO_DIM}]Agents[/bold {INDIGO_DIM}]: {len(ag_list)}  "
                f"(primary: [{INDIGO}]{primary}[/{INDIGO}])"
            )
            for ag in ag_list[:5]:
                name = ag.get("id", "?") if isinstance(ag, dict) else str(ag)
                model = ag.get("model", "") if isinstance(ag, dict) else ""
                lines.append(f"    [{INDIGO}]{name}[/{INDIGO}]  {model}")

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
                    f"  [bold {INDIGO_DIM}]Providers[/bold {INDIGO_DIM}]: {prov_summary}"
                )

        # Skills
        skills = oc.get("skills", {})
        if isinstance(skills, dict) and skills:
            lines.append(
                f"  [bold {INDIGO_DIM}]Skills[/bold {INDIGO_DIM}]: {len(skills)}"
            )

        # Channels
        channels = oc.get("channels", {})
        if isinstance(channels, dict) and channels:
            lines.append(
                f"  [bold {INDIGO_DIM}]Channels[/bold {INDIGO_DIM}]: {', '.join(channels.keys())}"
            )

        # Gateway
        gw = oc.get("gateway", {})
        if isinstance(gw, dict) and gw.get("port"):
            lines.append(
                f"  [bold {INDIGO_DIM}]Gateway[/bold {INDIGO_DIM}]: "
                f"port={gw['port']} mode={gw.get('mode', '?')}"
            )

        return "\n".join(lines) if lines else "[dim]OpenClaw config empty.[/dim]"

    def _handle_moltbook(self) -> str:
        state_file = DHARMA_STATE / "moltbook" / "state.json"
        mb = _read_json(state_file)
        if mb:
            return (
                f"  [bold {INDIGO_DIM}]Tracked posts[/bold {INDIGO_DIM}]: {mb.get('tracked', 0)}\n"
                f"  [bold {INDIGO_DIM}]Our comments[/bold {INDIGO_DIM}]: {mb.get('comments', 0)}\n"
                f"  [bold {INDIGO_DIM}]Engaged posts[/bold {INDIGO_DIM}]: {mb.get('engaged', 0)}\n"
                f"  [bold {INDIGO_DIM}]Last heartbeat[/bold {INDIGO_DIM}]: {mb.get('heartbeat', 'never')}"
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
                f"  [bold {INDIGO_DIM}]Result[/bold {INDIGO_DIM}]: {ev.get('overall', 'n/a')}\n"
                f"  [bold {INDIGO_DIM}]Hash[/bold {INDIGO_DIM}]: {ev.get('hash', 'n/a')}"
            )
        return "[dim]Evidence bundle unreadable.[/dim]"
