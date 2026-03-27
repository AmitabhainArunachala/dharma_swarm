"""DGC Terminal UI — chat-first interface to the dharmic swarm.

Plain text talks to Claude. /commands for system operations.
Thinkodynamic features: state injection, Darwin Engine, self-map, thread control.

Usage:
    dgc              (launch TUI)
    dgc --tui        (explicit TUI mode)
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.api_keys import provider_available
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
)

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = HOME / "dharma_swarm"
DGC_ROOT = HOME / "DHARMIC_GODEL_CLAW"


# ─── Helper functions ───────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _file_age_str(path: Path) -> str:
    if not path.exists():
        return "n/a"
    age = time.time() - path.stat().st_mtime
    if age < 60:
        return f"{age:.0f}s ago"
    if age < 3600:
        return f"{age / 60:.0f}m ago"
    if age < 86400:
        return f"{age / 3600:.1f}h ago"
    return f"{age / 86400:.0f}d ago"


def _count_files(path: Path, pattern: str = "*") -> int:
    try:
        return len(list(path.glob(pattern))) if path.exists() else 0
    except Exception:
        return 0


def _get_memory_stats() -> dict[str, Any]:
    """Read memory stats directly from ~/.dharma/db/memory.db."""
    db_path = DHARMA_STATE / "db" / "memory.db"
    if not db_path.exists():
        return {"error": "No memory database"}
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT layer, COUNT(*) as cnt FROM memories GROUP BY layer"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.close()
        stats: dict[str, Any] = {"total": total}
        for layer, cnt in rows:
            stats[layer] = cnt
        return stats
    except Exception as e:
        return {"error": str(e)}


def _get_gate_count_today() -> int:
    """Count gate checks from today's witness log at ~/.dharma/witness/."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gate_log = DHARMA_STATE / "witness" / f"{today}.jsonl"
    if not gate_log.exists():
        return 0
    try:
        with open(gate_log) as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _claude_version() -> str:
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "not found"


def _find_pids(pattern: str) -> list[int]:
    """Return PIDs matching a process pattern using pgrep -f."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=2
        )
        if proc.returncode not in (0, 1):
            return []
        me = os.getpid()
        pids: list[int] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.isdigit():
                continue
            pid = int(line)
            if pid != me:
                pids.append(pid)
        return pids
    except Exception:
        return []


def _read_pid(path: Path) -> int | None:
    try:
        if not path.exists():
            return None
        raw = path.read_text().strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _get_runtime_state() -> dict[str, Any]:
    """Inspect live runtime across canonical and legacy stacks."""
    daemon_pid = _read_pid(DHARMA_STATE / "daemon.pid")
    overnight_pid = _read_pid(DHARMA_STATE / "overnight.pid")
    sentinel_pid = _read_pid(DHARMA_STATE / "sentinel.pid")
    verify_pid = _read_pid(DHARMA_STATE / "verification_lane.pid")

    legacy_tui_pids = _find_pids("DHARMIC_GODEL_CLAW/src/core/dgc_tui.py")
    legacy_daemon_pids = _find_pids("dgc-core/daemon/dgc_daemon.py")

    return {
        "canonical": {
            "daemon_pid": daemon_pid,
            "daemon_alive": _pid_alive(daemon_pid),
            "overnight_pid": overnight_pid,
            "overnight_alive": _pid_alive(overnight_pid),
            "sentinel_pid": sentinel_pid,
            "sentinel_alive": _pid_alive(sentinel_pid),
            "verification_pid": verify_pid,
            "verification_alive": _pid_alive(verify_pid),
        },
        "legacy": {
            "tui_pids": legacy_tui_pids,
            "daemon_pids": legacy_daemon_pids,
            "tui_alive": bool(legacy_tui_pids),
            "daemon_alive": bool(legacy_daemon_pids),
        },
    }


def _get_exec_guard_status() -> str:
    """Best-effort ExecGuard status for legacy stack."""
    if os.getenv("DGC_GOD_MODE") == "1":
        return "GOD MODE (env)"
    legacy_tui = _get_runtime_state().get("legacy", {}).get("tui_alive")
    return "LEGACY ACTIVE" if legacy_tui else "OFF"


def _get_proxy_status() -> str:
    """Check if claude-max-api proxy is running on localhost:3456."""
    try:
        import httpx
        resp = httpx.get("http://localhost:3456/health", timeout=2)
        if resp.status_code == 200:
            return "ONLINE"
    except Exception:
        pass
    return "OFFLINE"


def _get_openclaw_summary() -> dict[str, Any]:
    """Read OpenClaw config from ~/.openclaw/openclaw.json."""
    cfg = HOME / ".openclaw" / "openclaw.json"
    if not cfg.exists():
        return {}
    try:
        data = json.loads(cfg.read_text())
        return {
            "agent": data.get("agent", {}).get("name", "unknown"),
            "skills": len(data.get("skills", {}).get("allowlist", [])),
            "channels": len(data.get("channels", {}).keys()) if isinstance(data.get("channels"), dict) else 0,
        }
    except Exception:
        return {}


def _get_moltbook_status() -> dict[str, Any]:
    """Read Moltbook swarm status from old DGC data."""
    state_path = DGC_ROOT / "data" / "swarm_state.json"
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text())
        return {
            "comments": len(data.get("our_comment_ids", [])),
            "engaged": len(data.get("engaged_post_ids", [])),
            "tracked": len(data.get("tracked_posts", [])),
            "heartbeat": (data.get("last_heartbeat", "never") or "never")[:19],
        }
    except Exception:
        return {}


def _get_old_memory_total() -> int:
    """Count total entries across old DGC JSONL memory files."""
    total = 0
    mem_dir = DGC_ROOT / "memory"
    if not mem_dir.exists():
        return 0
    for name in ["observations", "meta_observations", "witness_stability", "patterns", "development"]:
        path = mem_dir / f"{name}.jsonl"
        if path.exists():
            try:
                with open(path) as f:
                    total += sum(1 for _ in f)
            except Exception:
                pass
    return total


def _get_swarm_fitness() -> dict[str, Any]:
    """Get swarm fitness from old DGC SwarmOrchestrator (file-based, no imports)."""
    archive = DGC_ROOT / "src" / "dgm" / "archive.jsonl"
    if not archive.exists():
        archive = DGC_ROOT / "swarm" / "archive.jsonl"
    if not archive.exists():
        return {}
    try:
        entries = []
        with open(archive) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        if not entries:
            return {}
        fitnesses = [e.get("fitness", 0) for e in entries if "fitness" in e]
        avg = sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
        return {
            "fitness": avg,
            "cycles": len(entries),
            "trend": "up" if len(fitnesses) > 1 and fitnesses[-1] > fitnesses[-2] else "stable",
        }
    except Exception:
        return {}


def _get_latest_evidence() -> dict[str, Any]:
    """Find latest evidence bundle from old DGC."""
    evidence_dir = DGC_ROOT / "evidence"
    if not evidence_dir.exists():
        return {}
    try:
        candidates = list(evidence_dir.glob("**/gate_results.json"))
        if not candidates:
            return {}
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        data = json.loads(latest.read_text())
        return {
            "overall": data.get("overall_result", "unknown"),
            "hash": data.get("evidence_bundle_hash", "")[:12],
        }
    except Exception:
        return {}


def _get_backup_models() -> str:
    """Check which backup model providers are configured via env vars."""
    parts = []
    if os.getenv("MOONSHOT_API_KEY"):
        parts.append("moonshot")
    if provider_available("openrouter"):
        parts.append("openrouter")
    if os.getenv("OLLAMA_API_KEY"):
        parts.append("ollama")
    return ", ".join(parts) if parts else "none"


def _clipboard_read() -> str:
    """Read text from system clipboard (best-effort)."""
    commands = [
        ["pbpaste"],  # macOS
        ["wl-paste", "-n"],  # Wayland
        ["xclip", "-selection", "clipboard", "-o"],  # X11
    ]
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc.returncode == 0:
                return (proc.stdout or "").rstrip("\n")
        except Exception:
            continue
    return ""


def _clipboard_write(text: str) -> bool:
    """Write text to system clipboard (best-effort)."""
    if not text:
        return False
    commands = [
        ["pbcopy"],  # macOS
        ["wl-copy"],  # Wayland
        ["xclip", "-selection", "clipboard"],  # X11
    ]
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _count_git_status(porcelain: str) -> dict[str, int]:
    staged = 0
    unstaged = 0
    untracked = 0
    for line in porcelain.splitlines():
        if len(line) < 2:
            continue
        x = line[0]
        y = line[1]
        if x == "?" and y == "?":
            untracked += 1
            continue
        if x not in (" ", "?"):
            staged += 1
        if y != " ":
            unstaged += 1
    return {"staged": staged, "unstaged": unstaged, "untracked": untracked}


def _git_repo_summary(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"repo": str(path), "exists": False}
    try:
        branch = subprocess.run(
            ["git", "-C", str(path), "branch", "--show-current"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() or "(detached)"
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() or "unknown"
        porcelain = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        counts = _count_git_status(porcelain)
        return {
            "repo": str(path),
            "exists": True,
            "branch": branch,
            "head": head,
            **counts,
        }
    except Exception as e:
        return {"repo": str(path), "exists": True, "error": str(e)}


def _build_runtime_text() -> str:
    rt = _get_runtime_state()
    can = rt["canonical"]
    leg = rt["legacy"]
    lines = [
        "[bold cyan]Runtime Control Plane[/bold cyan]",
        (
            f"  [bold white]canonical[/bold white] "
            f"daemon={can['daemon_alive']}({can['daemon_pid'] or 'n/a'}) "
            f"overnight={can['overnight_alive']}({can['overnight_pid'] or 'n/a'}) "
            f"sentinel={can['sentinel_alive']}({can['sentinel_pid'] or 'n/a'}) "
            f"verification={can['verification_alive']}({can['verification_pid'] or 'n/a'})"
        ),
        (
            f"  [bold white]legacy[/bold white] "
            f"dgc_tui={leg['tui_alive']}({len(leg['tui_pids'])}) "
            f"dgc_daemon={leg['daemon_alive']}({len(leg['daemon_pids'])})"
        ),
    ]
    if can["daemon_alive"] and leg["tui_alive"]:
        lines.append("  [yellow]Split-brain warning: canonical + legacy both active.[/yellow]")
    return "\n".join(lines)


def _build_git_text() -> str:
    repos = [
        ("dharma_swarm", DHARMA_SWARM),
        ("dgc-core", HOME / "dgc-core"),
        ("DHARMIC_GODEL_CLAW", DGC_ROOT),
    ]
    lines = ["[bold cyan]Git Reality[/bold cyan]"]
    for label, path in repos:
        info = _git_repo_summary(path)
        if not info.get("exists"):
            lines.append(f"  [bold white]{label}[/bold white] missing")
            continue
        if "error" in info:
            lines.append(f"  [bold white]{label}[/bold white] error: {info['error']}")
            continue
        lines.append(
            f"  [bold white]{label}[/bold white] {info['branch']}@{info['head']} "
            f"staged={info['staged']} unstaged={info['unstaged']} untracked={info['untracked']}"
        )
    return "\n".join(lines)


def _build_truth_report() -> str:
    rt = _get_runtime_state()
    can = rt["canonical"]
    leg = rt["legacy"]
    lines = [
        "[bold cyan]Truth Report[/bold cyan]",
        "  Cockpit: [green]dharma_swarm DGC TUI[/green]",
        (
            "  Canonical control plane: "
            f"daemon={can['daemon_alive']} overnight={can['overnight_alive']} "
            f"verification={can['verification_alive']}"
        ),
        (
            "  Legacy stack: "
            f"tui={leg['tui_alive']} daemon={leg['daemon_alive']}"
        ),
    ]
    if leg["tui_alive"]:
        lines.append("  [yellow]Legacy green TUI is running in parallel; treat it as non-canonical.[/yellow]")
    lines.append("")
    lines.append(_build_git_text())
    return "\n".join(lines)


def _build_status_text() -> str:
    """Build rich status panel matching old DGC TUI layout."""
    lines = []
    lines.append("[bold cyan]╔══════════════════ DGC STATUS ══════════════════╗[/bold cyan]")

    # ExecGuard
    eg = _get_exec_guard_status()
    eg_color = "green" if eg == "GOD MODE" else "dim"
    lines.append(f"  [bold white]ExecGuard[/bold white]    [{eg_color}]{eg}[/{eg_color}]")

    # Chat backend
    lines.append("  [bold white]Chat[/bold white]         [cyan]claude -p[/cyan] (bypassPermissions)")

    # Proxy
    proxy = _get_proxy_status()
    p_color = "green" if proxy == "ONLINE" else "red"
    lines.append(f"  [bold white]Proxy[/bold white]        [{p_color}]{proxy}[/{p_color}]")

    # Memory (dharma_swarm SQLite)
    ms = _get_memory_stats()
    if "error" not in ms:
        lines.append(f"  [bold white]Memory[/bold white]       [green]{ms.get('total', 0)} entries[/green] (SQLite)")
    else:
        lines.append(f"  [bold white]Memory[/bold white]       [red]{ms['error']}[/red]")

    # Legacy memory (old DGC JSONL)
    old_mem = _get_old_memory_total()
    if old_mem > 0:
        lines.append(f"  [bold white]Legacy Mem[/bold white]   {old_mem} entries (JSONL)")

    # Runtime truth
    rt = _get_runtime_state()
    can = rt["canonical"]
    leg = rt["legacy"]
    lines.append(
        "  [bold white]Runtime[/bold white]      "
        f"canonical da={can['daemon_alive']} ov={can['overnight_alive']} vf={can['verification_alive']} | "
        f"legacy tui={leg['tui_alive']}"
    )

    # Swarm fitness
    sf = _get_swarm_fitness()
    if sf:
        lines.append(
            f"  [bold white]Swarm[/bold white]        fitness {sf.get('fitness', 0):.2f} | "
            f"{sf.get('cycles', 0)} cycles | trend {sf.get('trend', 'n/a')}"
        )

    # Gates
    gate_count = _get_gate_count_today()
    lines.append(f"  [bold white]Gates[/bold white]        8 telos gates | {gate_count} checks today")

    # Pulse
    ds = _read_json(DHARMA_STATE / "daemon_state.json")
    if not ds:
        ds = _read_json(DHARMA_STATE / "state.json")
    circuit = ds.get("circuit_breaker", "ok")
    c_color = "green" if circuit == "ok" else "red"
    lines.append(
        f"  [bold white]Pulse[/bold white]        count={ds.get('pulse_count', 0)} "
        f"last={ds.get('last_pulse', 'never')} "
        f"circuit=[{c_color}]{circuit}[/{c_color}]"
    )

    # AGNI
    agni = HOME / "agni-workspace"
    if agni.exists():
        lines.append(f"  [bold white]AGNI[/bold white]         [green]synced[/green]  WORKING.md={_file_age_str(agni / 'WORKING.md')}")
    else:
        lines.append("  [bold white]AGNI[/bold white]         [red]NOT SYNCED[/red]")

    # TRISHULA
    t_inbox = HOME / "trishula" / "inbox"
    t_count = _count_files(t_inbox, "*.json") + _count_files(t_inbox, "*.md")
    lines.append(f"  [bold white]Trishula[/bold white]     {t_count} messages")

    # OpenClaw
    oc = _get_openclaw_summary()
    if oc:
        lines.append(f"  [bold white]OpenClaw[/bold white]     {oc.get('agent', '?')} | {oc.get('skills', 0)} skills")

    # Evidence
    ev = _get_latest_evidence()
    if ev:
        lines.append(f"  [bold white]Evidence[/bold white]     {ev.get('overall', 'n/a')} | {ev.get('hash', '')}")

    # Moltbook
    mb = _get_moltbook_status()
    if mb:
        lines.append(f"  [bold white]Moltbook[/bold white]     {mb.get('comments', 0)} comments, {mb.get('engaged', 0)} engagements")

    # Backups
    backups = _get_backup_models()
    lines.append(f"  [bold white]Backups[/bold white]      {backups}")

    # Ecosystem
    mf = _read_json(HOME / ".dharma_manifest.json")
    if mf:
        eco = mf.get("ecosystem", {})
        alive = sum(1 for v in eco.values() if v.get("exists"))
        lines.append(f"  [bold white]Ecosystem[/bold white]    {alive}/{len(eco)} components alive")

    # Shared notes
    shared = DHARMA_STATE / "shared"
    shared_count = _count_files(shared, "*.md")
    if shared_count:
        lines.append(f"  [bold white]Shared[/bold white]       {shared_count} agent notes")

    # Thread
    thread_file = DHARMA_STATE / "thread_state.json"
    if thread_file.exists():
        try:
            ts = json.loads(thread_file.read_text())
            lines.append(f"  [bold white]Thread[/bold white]       [cyan]{ts.get('current_thread', 'unknown')}[/cyan]")
        except Exception:
            pass

    # Claude version
    lines.append(f"  [bold white]Claude[/bold white]       {_claude_version()}")

    lines.append("[bold cyan]╚════════════════════════════════════════════════╝[/bold cyan]")
    return "\n".join(lines)


def _build_context_preview(role: str = "general", thread: str | None = None) -> str:
    try:
        from dharma_swarm.context import build_agent_context
        ctx = build_agent_context(role=role, thread=thread)
        headers = [l for l in ctx.split("\n") if l.startswith("# ") or l.startswith("## ")]
        summary = f"[bold]Context for role={role}[/bold]  [dim]{len(ctx):,} chars[/dim]\n"
        summary += "\n".join(f"  [green]{h}[/green]" for h in headers)
        return summary
    except Exception as e:
        return f"[red]Context error: {e}[/red]"


# ─── Splash Screen ──────────────────────────────────────────────────


class SplashScreen(Screen):
    BINDINGS = [
        Binding("enter", "dismiss_splash", "Enter DGC"),
        Binding("escape", "dismiss_splash", "Enter DGC"),
        Binding("q", "quit", "Quit"),
        Binding("any", "dismiss_splash", show=False),
    ]

    def compose(self) -> ComposeResult:
        from dharma_swarm.splash import get_splash
        yield Static(get_splash(compact=False), id="splash-art", markup=False)
        prompt = Text.from_markup(
            "\n[bold bright_white]  Press any key to enter  |  "
            "[bright_cyan]q[/bright_cyan] to quit[/bold bright_white]"
        )
        yield Static(prompt, id="splash-prompt", markup=False)

    def on_key(self, event) -> None:
        if event.key == "q":
            self.app.exit()
        else:
            self.app.pop_screen()

    def action_dismiss_splash(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


# ─── Main App ────────────────────────────────────────────────────────


class DGCApp(App):
    TITLE = "DGC TUI — Dharmic Godel Claw · Telos: Moksha"
    CSS = """
    Screen {
        background: $surface;
    }

    #splash-art {
        width: 100%;
        content-align: center middle;
        text-align: center;
        padding: 1;
    }

    #splash-prompt {
        dock: bottom;
        height: 3;
        content-align: center middle;
        text-align: center;
        background: $primary-background;
    }

    #chat-log {
        height: 1fr;
        padding: 0 1;
    }

    #cmd-input {
        dock: bottom;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_log", "Clear"),
        Binding("ctrl+s", "show_splash", "Splash"),
        Binding("ctrl+shift+v", "paste_clipboard", "Paste"),
        Binding("meta+v", "paste_clipboard", "Paste"),
        Binding("ctrl+shift+c", "copy_last_reply", "Copy Last"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="Talk to Claude, or /help for commands", id="cmd-input")
        yield Footer()

    def on_mount(self) -> None:
        self._conversation_lock = threading.Lock()
        self._conversation: list[dict[str, str]] = []
        self._conversation_max_pairs = 12
        self._active_proc: subprocess.Popen[str] | None = None
        self._state_cache: str = ""
        self._state_cache_time: float = 0.0
        self._internet_enabled: bool = True
        self.push_screen(SplashScreen())
        # Auto-focus input when dashboard loads
        self.set_timer(0.1, self._focus_input)
        # Show welcome
        self._out("[bold cyan]DGC[/bold cyan] [dim]— Talk to Claude or type /help for system commands[/dim]\n")
        self._out(_build_status_text())
        self._out("")

    def _focus_input(self) -> None:
        try:
            self.query_one("#cmd-input", Input).focus()
        except Exception:
            pass

    def _out(self, msg: str) -> None:
        try:
            self.query_one("#chat-log", RichLog).write(msg)
        except Exception:
            pass

    def _out_thread(self, msg: str) -> None:
        self.call_from_thread(self._out, msg)

    def _reset_conversation(self) -> None:
        with self._conversation_lock:
            self._conversation = []

    def _append_conversation(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            return
        item = {"role": role, "content": content.strip()}
        with self._conversation_lock:
            self._conversation.append(item)
            # Keep a rolling window to avoid runaway prompt size.
            max_messages = self._conversation_max_pairs * 2
            if len(self._conversation) > max_messages:
                self._conversation = self._conversation[-max_messages:]

    def _build_chat_prompt(self, question: str) -> str:
        with self._conversation_lock:
            history = list(self._conversation)

        if history:
            rendered: list[str] = []
            for msg in history:
                speaker = "User" if msg["role"] == "user" else "Assistant"
                rendered.append(f"{speaker}: {msg['content']}")
            transcript = "\n\n".join(rendered)
        else:
            transcript = "(no prior conversation yet)"

        return (
            "You are Claude running inside the DGC TUI. "
            "This is a persistent technical conversation. Continue naturally.\n\n"
            "Conversation transcript (oldest to newest):\n"
            f"{transcript}\n\n"
            "New user message:\n"
            f"{question}\n\n"
            "Respond directly and keep continuity with prior context."
        )

    def _get_state_context(self) -> str:
        """Build live state context for Claude injection. Cached 60s."""
        now = time.time()
        if hasattr(self, "_state_cache_time") and (now - self._state_cache_time) < 60:
            if self._state_cache:
                return self._state_cache

        from dharma_swarm.prompt_builder import build_state_context_snapshot

        result = build_state_context_snapshot(
            state_dir=DHARMA_STATE,
            home=HOME,
            max_chars=6000,
            include_latent_gold=False,
        )
        self._state_cache = result
        self._state_cache_time = now
        return result

    # ─── Input handler ───

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return

        # /commands
        if raw.startswith("/"):
            self._handle_command(raw[1:])
            return

        # Everything else → ask Claude
        self._out(f"\n[bold bright_white]you:[/bold bright_white] {raw}")
        self._run_ask(raw)

    def _handle_command(self, raw: str) -> None:
        parts = raw.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        self._out(f"\n[dim]/{cmd} {arg}[/dim]")

        if cmd == "help":
            self._out(
                "[bold cyan]━━━ System ━━━[/bold cyan]\n"
                "  [cyan]/status[/cyan]          Full system status panel\n"
                "  [cyan]/health[/cyan]          Ecosystem health check\n"
                "  [cyan]/pulse[/cyan]           Run heartbeat\n"
                "  [cyan]/self[/cyan]            System self-map (modules, tests, state)\n"
                "  [cyan]/context[/cyan] [role]  Show agent context layers\n"
                "\n[bold cyan]━━━ Memory & Witness ━━━[/bold cyan]\n"
                "  [cyan]/memory[/cyan]          Strange loop memory\n"
                "  [cyan]/witness[/cyan] <msg>   Record observation\n"
                "  [cyan]/notes[/cyan]           Shared agent notes\n"
                "  [cyan]/archive[/cyan]         Evolution archive (last 10)\n"
                "  [cyan]/logs[/cyan]            Tail system logs\n"
                "\n[bold cyan]━━━ Agents & Swarm ━━━[/bold cyan]\n"
                "  [cyan]/swarm[/cyan] [op]      Swarm: status | start [h] | stop | report | yolo\n"
                "  [cyan]/gates[/cyan] <action>  Test telos gates\n"
                "  [cyan]/evolve[/cyan] <c> <d>  Darwin Engine evolution\n"
                "  [cyan]/agni[/cyan] <cmd>      Run on AGNI VPS\n"
                "  [cyan]/trishula[/cyan]        Trishula inbox\n"
                "\n[bold cyan]━━━ Integrations ━━━[/bold cyan]\n"
                "  [cyan]/openclaw[/cyan]        OpenClaw agent status\n"
                "  [cyan]/moltbook[/cyan]        Moltbook engagement status\n"
                "  [cyan]/evidence[/cyan]        Latest evidence bundle\n"
                "  [cyan]/runtime[/cyan]         Live process/runtime matrix\n"
                "  [cyan]/git[/cyan]             Repo branch/head/dirty counts\n"
                "  [cyan]/truth[/cyan]           Canonical truth report\n"
                "\n[bold cyan]━━━ Dharma & Living Layers ━━━[/bold cyan]\n"
                "  [cyan]/dharma[/cyan] [status]  Dharma kernel/corpus status\n"
                "  [cyan]/corpus[/cyan] [--status S]  List corpus claims (filter by status)\n"
                "  [cyan]/stigmergy[/cyan]       Hot paths and high salience marks\n"
                "  [cyan]/hum[/cyan]             Subconscious dreams\n"
                "\n[bold cyan]━━━ Chat & Control ━━━[/bold cyan]\n"
                "  [cyan]/thread[/cyan] [name]   Show/set research thread\n"
                "  [cyan]/net[/cyan] [on|off]    Internet mode for Claude\n"
                "  [cyan]/chat[/cyan] [continue] Launch full Claude Code UI\n"
                "  [cyan]/paste[/cyan]           Paste system clipboard to input\n"
                "  [cyan]/copy[/cyan]            Copy last Claude reply to clipboard\n"
                "  [cyan]/cancel[/cyan]          Cancel active Claude run\n"
                "  [cyan]/reset[/cyan]           Reset conversation memory\n"
                "  [cyan]/clear[/cyan]           Clear screen\n"
                "  [cyan]/help[/cyan]            This help\n\n"
                "[dim]Plain text (no /) talks to Claude via claude -p.[/dim]"
            )

        elif cmd == "clear":
            try:
                self.query_one("#chat-log", RichLog).clear()
            except Exception:
                pass
            self._reset_conversation()

        elif cmd == "reset":
            self._reset_conversation()
            self._out("[dim]Conversation memory reset.[/dim]")

        elif cmd == "paste":
            self.action_paste_clipboard()

        elif cmd in {"copy", "copylast"}:
            self.action_copy_last_reply()

        elif cmd == "chat":
            mode = arg.strip().lower()
            if mode in {"", "new"}:
                self._launch_chat_shell(continue_last=False)
            elif mode in {"continue", "cont", "resume", "c", "r"}:
                self._launch_chat_shell(continue_last=True)
            else:
                self._out("[red]Usage: /chat [continue][/red]")

        elif cmd == "cancel":
            proc = self._active_proc
            if proc is None:
                self._out("[dim]No active Claude run.[/dim]")
            elif proc.poll() is None:
                try:
                    proc.terminate()
                    self._out("[yellow]Cancel signal sent to active Claude run.[/yellow]")
                except Exception as e:
                    self._out(f"[red]Cancel failed: {e}[/red]")
            else:
                self._out("[dim]Active Claude run already completed.[/dim]")

        elif cmd == "status":
            self._out(_build_status_text())

        elif cmd == "pulse":
            self._run_pulse()

        elif cmd == "health":
            self._run_health()

        elif cmd == "gates":
            self._run_gates(arg or "echo test")

        elif cmd == "memory":
            self._run_memory()

        elif cmd == "witness":
            if not arg:
                self._out("[red]Usage: /witness <observation>[/red]")
            else:
                self._run_witness(arg)

        elif cmd == "context":
            self._out(_build_context_preview(role=arg or "general"))

        elif cmd == "agni":
            if not arg:
                self._out("[red]Usage: /agni <command>[/red]")
            else:
                self._run_agni(arg)

        elif cmd == "swarm":
            if not arg:
                orch = _read_json(DHARMA_STATE / "orchestrator_state.json")
                if orch:
                    for k, v in orch.items():
                        self._out(f"  {k}: {v}")
                else:
                    self._out("[dim]No orchestrator state. Try /swarm status[/dim]")
            else:
                self._run_swarm_control(arg)

        elif cmd == "evolve":
            if not arg or len(arg.split(None, 1)) < 2:
                self._out("[red]Usage: /evolve <component> <description>[/red]")
            else:
                evolve_parts = arg.split(None, 1)
                self._run_evolve(evolve_parts[0], evolve_parts[1])

        elif cmd == "thread":
            if not arg:
                thread_file = DHARMA_STATE / "thread_state.json"
                if thread_file.exists():
                    try:
                        ts = json.loads(thread_file.read_text())
                        self._out(f"Active thread: [cyan]{ts.get('current_thread', 'unknown')}[/cyan]")
                    except Exception:
                        self._out("[dim]Thread state unreadable.[/dim]")
                else:
                    self._out("[dim]No active thread.[/dim]")
            else:
                focus_file = DHARMA_STATE / ".FOCUS"
                DHARMA_STATE.mkdir(parents=True, exist_ok=True)
                focus_file.write_text(arg.strip())
                self._out(f"Thread set to [cyan]{arg.strip()}[/cyan] (wrote .FOCUS)")

        elif cmd == "self":
            self._run_self_map()

        elif cmd == "net":
            mode = arg.strip().lower()
            if not mode or mode == "status":
                status = "ON" if self._internet_enabled else "OFF"
                color = "green" if self._internet_enabled else "yellow"
                self._out(f"Internet mode: [{color}]{status}[/{color}]")
                return
            if mode in {"on", "enable", "enabled", "1", "true"}:
                self._internet_enabled = True
                self._out("[green]Internet mode enabled.[/green]")
                return
            if mode in {"off", "disable", "disabled", "0", "false"}:
                self._internet_enabled = False
                self._out("[yellow]Internet mode disabled (nonessential traffic blocked).[/yellow]")
                return
            self._out("[red]Usage: /net [on|off|status][/red]")

        elif cmd == "notes":
            shared = DHARMA_STATE / "shared"
            if not shared.exists():
                self._out("[dim]No agent notes.[/dim]")
            else:
                for f in sorted(shared.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                    try:
                        content = f.read_text()[:300]
                        self._out(f"[bold cyan]{f.name}[/bold cyan]  [dim]{_file_age_str(f)}[/dim]")
                        for line in content.split("\n")[:3]:
                            self._out(f"  {line}")
                    except Exception:
                        pass

        elif cmd == "trishula":
            inbox = HOME / "trishula" / "inbox"
            if inbox.exists():
                found = False
                for f in sorted(inbox.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    try:
                        self._out(f"[bold magenta]{f.name}[/bold magenta]")
                        for line in f.read_text()[:200].split("\n")[:3]:
                            self._out(f"  {line}")
                        found = True
                    except Exception:
                        pass
                if not found:
                    self._out("[dim]No messages in trishula inbox.[/dim]")
            else:
                self._out("[dim]Trishula inbox not found.[/dim]")
            self._out("[dim]Showing latest 5 messages.[/dim]")

        elif cmd == "archive":
            self._run_archive()

        elif cmd == "logs":
            self._run_logs()

        elif cmd == "openclaw":
            oc = _get_openclaw_summary()
            if oc:
                self._out(
                    f"  [bold white]Agent[/bold white]: {oc.get('agent', '?')}\n"
                    f"  [bold white]Skills[/bold white]: {oc.get('skills', 0)}\n"
                    f"  [bold white]Channels[/bold white]: {oc.get('channels', 0)}"
                )
            else:
                self._out("[dim]OpenClaw not found (~/.openclaw/openclaw.json)[/dim]")

        elif cmd == "moltbook":
            mb = _get_moltbook_status()
            if mb:
                self._out(
                    f"  [bold white]Tracked posts[/bold white]: {mb.get('tracked', 0)}\n"
                    f"  [bold white]Our comments[/bold white]: {mb.get('comments', 0)}\n"
                    f"  [bold white]Engaged posts[/bold white]: {mb.get('engaged', 0)}\n"
                    f"  [bold white]Last heartbeat[/bold white]: {mb.get('heartbeat', 'never')}"
                )
            else:
                self._out("[dim]Moltbook state not found.[/dim]")

        elif cmd == "evidence":
            ev = _get_latest_evidence()
            if ev:
                self._out(
                    f"  [bold white]Result[/bold white]: {ev.get('overall', 'n/a')}\n"
                    f"  [bold white]Hash[/bold white]: {ev.get('hash', 'n/a')}"
                )
            else:
                self._out("[dim]No evidence bundles found.[/dim]")

        elif cmd == "runtime":
            self._out(_build_runtime_text())

        elif cmd == "git":
            self._out(_build_git_text())

        elif cmd == "truth":
            self._out(_build_truth_report())

        elif cmd == "dharma":
            sub = arg.split(None, 1) if arg else []
            subcmd = sub[0].lower() if sub else "status"
            if subcmd == "status":
                self._run_dharma_status()
            elif subcmd == "corpus":
                corpus_arg = sub[1] if len(sub) > 1 else ""
                self._run_dharma_corpus(corpus_arg)
            else:
                self._out("[red]Usage: /dharma [status|corpus][/red]")

        elif cmd == "corpus":
            self._run_dharma_corpus(arg)

        elif cmd == "stigmergy":
            self._run_stigmergy(arg)

        elif cmd == "hum":
            self._run_hum()

        else:
            self._out(f"[red]Unknown command: /{cmd}[/red]  (try /help)")

    def _launch_chat_shell(self, continue_last: bool = False) -> None:
        proc = self._active_proc
        if proc is not None and proc.poll() is None:
            self._out("[yellow]A Claude run is active. Use /cancel first.[/yellow]")
            return

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)

        cmd = ["claude"]
        if continue_last:
            cmd.append("--continue")
        if self._internet_enabled:
            cmd.extend(
                [
                    "--permission-mode",
                    "bypassPermissions",
                    "--allow-dangerously-skip-permissions",
                    "--dangerously-skip-permissions",
                ]
            )
        else:
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

        state_ctx = self._get_state_context()
        if state_ctx:
            # Keep startup payload bounded for fast interactive launch.
            state_ctx = state_ctx[:6000]
            cmd.extend(
                [
                    "--append-system-prompt",
                    "DGC mission-control context snapshot. Treat as hints and verify.\n\n"
                    + state_ctx,
                ]
            )

        self._out(
            "[dim]Launching native Claude Code UI. Exit Claude to return to DGC.[/dim]"
        )
        launched = False
        try:
            with self.suspend():
                launched = True
                subprocess.run(cmd, cwd=str(DHARMA_SWARM), env=env, check=False)
        except SuspendNotSupported:
            self._out("[red]/chat is not supported in this terminal environment.[/red]")
        except FileNotFoundError:
            self._out("[red]claude CLI not found.[/red]")
        except Exception as e:
            self._out(f"[red]/chat failed: {e}[/red]")
        finally:
            self.set_timer(0.05, self._focus_input)
            if launched:
                self._out("[dim]Returned from native Claude Code UI.[/dim]")

    # ─── Claude conversation ───

    @work(thread=True)
    def _run_ask(self, question: str) -> None:
        self._out_thread("[dim]thinking...[/dim]")
        try:
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)
            env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
            prompt = self._build_chat_prompt(question)

            # Inject live state context
            state_ctx = self._get_state_context()
            if state_ctx:
                prompt = state_ctx + "\n\n" + prompt

            cmd = ["claude", "-p", prompt, "--output-format", "text"]
            if self._internet_enabled:
                cmd.extend([
                    "--permission-mode", "bypassPermissions",
                    "--allow-dangerously-skip-permissions",
                    "--dangerously-skip-permissions",
                ])
            else:
                env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

            # Stream output line-by-line instead of blocking with timeout
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(DHARMA_SWARM),
                env=env,
            )
            self._active_proc = proc
            self._out_thread(f"\n[bold cyan]claude:[/bold cyan]")
            lines: list[str] = []
            for line in proc.stdout:  # type: ignore[union-attr]
                text = line.rstrip("\n")
                lines.append(text)
                self._out_thread(f"  {text}")
            proc.wait()
            self._active_proc = None
            output = "\n".join(lines)
            if output.strip():
                self._append_conversation("user", question)
                self._append_conversation("assistant", output)
                self._out_thread("")
            else:
                err = (proc.stderr.read() if proc.stderr else "")[:300]
                self._out_thread(f"[red]No response. {err}[/red]")
        except FileNotFoundError:
            self._out_thread("[red]claude CLI not found.[/red]")
        except Exception as e:
            self._active_proc = None
            self._out_thread(f"[red]Error: {e}[/red]")

    # ─── System commands (threaded) ───

    @work(thread=True)
    def _run_pulse(self) -> None:
        self._out_thread("[dim]Running pulse...[/dim]")
        try:
            from dharma_swarm.pulse import pulse
            result = str(pulse())[:2000]
            for line in result.split("\n"):
                self._out_thread(f"  {line}")
            self._out_thread("[green]Pulse done.[/green]")
        except Exception as e:
            self._out_thread(f"[red]Pulse failed: {e}[/red]")

    @work(thread=True)
    def _run_health(self) -> None:
        """Ecosystem health check using scan_ecosystem from ecosystem_bridge."""
        self._out_thread("[dim]Checking health...[/dim]")
        try:
            from dharma_swarm.ecosystem_bridge import scan_ecosystem
            eco = scan_ecosystem()
            ok = sum(1 for v in eco.values() if v.get("exists"))
            missing = sum(1 for v in eco.values() if not v.get("exists"))
            self._out_thread(f"  [green]{ok} OK[/green]  [red]{missing} missing[/red]")
            for name, info in eco.items():
                if not info.get("exists"):
                    self._out_thread(f"  [red]MISSING[/red] {name} -- {info.get('path', '?')}")
        except Exception as e:
            self._out_thread(f"[red]Health failed: {e}[/red]")

    @work(thread=True)
    def _run_gates(self, action: str) -> None:
        """Test telos gates using dharma_swarm.telos_gates."""
        self._out_thread(f"[dim]Testing gates: {action}[/dim]")
        try:
            from dharma_swarm.telos_gates import check_action
            result = check_action(action=action)
            d = result.decision.value
            color = "green" if d == "allow" else "red"
            self._out_thread(f"  [{color}]{d}[/{color}]: {result.reason}")
        except Exception as e:
            self._out_thread(f"[red]Gates failed: {e}[/red]")

    @work(thread=True)
    def _run_memory(self) -> None:
        """Show recent memory from dharma_swarm's SQLite store."""
        self._out_thread("[dim]Loading memory...[/dim]")
        try:
            from dharma_swarm.context import read_memory_context
            ctx = read_memory_context()
            for line in ctx.split("\n")[:30]:
                self._out_thread(f"  {line}")
        except Exception as e:
            self._out_thread(f"[red]Memory failed: {e}[/red]")

    @work(thread=True)
    def _run_witness(self, msg: str) -> None:
        """Write a witness entry to ~/.dharma/witness/{today}.jsonl."""
        try:
            witness_dir = DHARMA_STATE / "witness"
            witness_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = witness_dir / f"{today}.jsonl"
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "observation": msg,
                "source": "tui",
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            self._out_thread(f"  [green]Witnessed[/green] -> {log_file.name}")
        except Exception as e:
            self._out_thread(f"[red]Witness failed: {e}[/red]")

    @work(thread=True)
    def _run_agni(self, command: str) -> None:
        from dharma_swarm.telos_gates import check_with_reflective_reroute

        gate = check_with_reflective_reroute(
            action=f"agni:{command}",
            content=command,
            tool_name="tui_legacy_agni",
            think_phase="before_complete",
            reflection=(
                "Remote AGNI execution request. Validate blast radius, "
                "rollback path, and least-privilege command intent."
            ),
            max_reroutes=1,
            requirement_refs=["agni:remote_exec"],
        )
        if gate.result.decision.value == "block":
            self._out_thread(f"[red]TELOS BLOCK[/red]: {gate.result.reason}")
            return
        if gate.attempts:
            self._out_thread(
                f"[dim]Witness reroute applied ({gate.attempts} attempts).[/dim]"
            )

        self._out_thread(f"[dim]AGNI: {command}[/dim]")
        try:
            ssh_key = HOME / ".ssh" / "openclaw_do"
            proc = subprocess.run(
                ["ssh", "-i", str(ssh_key), "-o", "ConnectTimeout=10",
                 "root@157.245.193.15", command],
                capture_output=True, text=True, timeout=30,
            )
            if proc.stdout:
                for line in proc.stdout.split("\n")[:30]:
                    self._out_thread(f"  {line}")
            if proc.stderr:
                self._out_thread(f"  [red]{proc.stderr.strip()[:200]}[/red]")
        except subprocess.TimeoutExpired:
            self._out_thread("[red]AGNI timed out.[/red]")
        except Exception as e:
            self._out_thread(f"[red]AGNI failed: {e}[/red]")

    @work(thread=True)
    def _run_swarm_control(self, arg: str) -> None:
        parts = arg.split()
        op = parts[0].lower() if parts else "status"
        rest = parts[1:]
        scripts = DHARMA_SWARM / "scripts"
        start_script = scripts / "start_overnight.sh"
        stop_script = scripts / "stop_overnight.sh"
        run_file = DHARMA_STATE / "overnight_run_dir.txt"

        self._out_thread(f"[dim]swarm {arg}[/dim]")

        try:
            if op in ("status", "state"):
                orch = _read_json(DHARMA_STATE / "orchestrator_state.json")
                if orch:
                    self._out_thread("[bold cyan]orchestrator[/bold cyan]")
                    for k, v in orch.items():
                        self._out_thread(f"  {k}: {v}")

                for label in ("overnight", "daemon", "sentinel"):
                    pid_file = DHARMA_STATE / f"{label}.pid"
                    if not pid_file.exists():
                        self._out_thread(f"  {label}: [dim]no pid[/dim]")
                        continue
                    try:
                        pid = int(pid_file.read_text().strip())
                        alive = False
                        try:
                            os.kill(pid, 0)
                            alive = True
                        except Exception:
                            alive = False
                        self._out_thread(f"  {label}: pid={pid} alive={alive}")
                    except Exception:
                        self._out_thread(f"  {label}: [red]invalid pid[/red]")

                if run_file.exists():
                    run_dir = Path(run_file.read_text().strip())
                    report = run_dir / "report.md"
                    self._out_thread(f"  run_dir: {run_dir}")
                    if report.exists():
                        self._out_thread("[bold cyan]report (tail)[/bold cyan]")
                        tail = "\n".join(report.read_text(errors="ignore").splitlines()[-20:])
                        for line in tail.split("\n"):
                            self._out_thread(f"  {line}")
                return

            if op in ("start", "run", "overnight"):
                hours = "8"
                if rest:
                    try:
                        float(rest[0])
                        hours = rest[0]
                    except ValueError:
                        pass
                env = os.environ.copy()
                if "--aggressive" in rest:
                    env.update({
                        "POLL_SECONDS": "120",
                        "MIN_PENDING": "12",
                        "TASKS_PER_LOOP": "5",
                        "QUALITY_EVERY_LOOPS": "10",
                    })
                proc = subprocess.run(
                    ["bash", str(start_script), hours],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                if out:
                    for line in out.split("\n"):
                        self._out_thread(f"  {line}")
                if err:
                    self._out_thread(f"  [red]{err}[/red]")
                return

            if op in ("stop", "down"):
                proc = subprocess.run(
                    ["bash", str(stop_script)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                if out:
                    for line in out.split("\n"):
                        self._out_thread(f"  {line}")
                if err:
                    self._out_thread(f"  [red]{err}[/red]")
                return

            if op in ("report", "logs"):
                if not run_file.exists():
                    self._out_thread("[dim]No overnight run metadata yet.[/dim]")
                    return
                run_dir = Path(run_file.read_text().strip())
                report = run_dir / "report.md"
                log = run_dir / "autopilot.log"
                self._out_thread(f"  run_dir: {run_dir}")
                if report.exists():
                    self._out_thread("[bold cyan]report (tail)[/bold cyan]")
                    for line in report.read_text(errors="ignore").splitlines()[-30:]:
                        self._out_thread(f"  {line}")
                if log.exists():
                    self._out_thread("[bold cyan]autopilot.log (tail)[/bold cyan]")
                    for line in log.read_text(errors="ignore").splitlines()[-30:]:
                        self._out_thread(f"  {line}")
                return

            if op in ("yolo", "caffeine"):
                env = os.environ.copy()
                env.update({
                    "POLL_SECONDS": "120",
                    "MIN_PENDING": "12",
                    "TASKS_PER_LOOP": "5",
                    "QUALITY_EVERY_LOOPS": "10",
                })
                proc = subprocess.run(
                    ["bash", str(start_script), "10"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                if out:
                    for line in out.split("\n"):
                        self._out_thread(f"  {line}")
                if err:
                    self._out_thread(f"  [red]{err}[/red]")
                return

            self._out_thread(
                "[red]Usage:[/red] /swarm status | /swarm start [hours] | "
                "/swarm stop | /swarm report | /swarm yolo"
            )
        except subprocess.TimeoutExpired:
            self._out_thread("[red]swarm command timed out[/red]")
        except Exception as e:
            self._out_thread(f"[red]swarm command failed: {e}[/red]")

    # ─── Legacy DGC commands ───

    @work(thread=True)
    def _run_archive(self) -> None:
        """Show last entries from evolution archive."""
        self._out_thread("[dim]Loading archive...[/dim]")
        # Try dharma_swarm archive first, fall back to old DGC
        archive_path = DHARMA_STATE / "evolution" / "archive.jsonl"
        if not archive_path.exists():
            archive_path = DGC_ROOT / "src" / "dgm" / "archive.jsonl"
        if not archive_path.exists():
            archive_path = DGC_ROOT / "swarm" / "archive.jsonl"
        if not archive_path.exists():
            self._out_thread("[dim]No evolution archive found.[/dim]")
            return
        try:
            entries = []
            with open(archive_path) as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
            if not entries:
                self._out_thread("[dim]Archive empty.[/dim]")
                return
            self._out_thread(f"[bold cyan]Evolution Archive[/bold cyan] ({len(entries)} total)\n")
            for entry in entries[-10:]:
                ts = entry.get("timestamp", "?")[:19]
                status = entry.get("status", "?")
                component = entry.get("component", "?")
                fitness = entry.get("fitness", 0)
                s_color = "green" if status in ("accepted", "archived") else "yellow"
                self._out_thread(
                    f"  {ts}  [{s_color}]{status:10}[/{s_color}]  {component}  fitness={fitness:.3f}"
                )
        except Exception as e:
            self._out_thread(f"[red]Archive read failed: {e}[/red]")

    @work(thread=True)
    def _run_logs(self) -> None:
        """Tail recent system logs."""
        self._out_thread("[dim]Loading logs...[/dim]")
        log_files = [
            (DHARMA_STATE / "pulse.log", "pulse"),
            (DGC_ROOT / "logs" / "dharmic_claw_heartbeat.log", "heartbeat"),
            (DGC_ROOT / "logs" / "dgm.log", "dgm"),
            (DGC_ROOT / "swarm" / "swarm.log", "swarm"),
        ]
        found_any = False
        for log_path, label in log_files:
            if log_path.exists():
                try:
                    tail = log_path.read_text(errors="ignore").splitlines()[-5:]
                    if tail:
                        found_any = True
                        self._out_thread(f"\n[bold cyan]{label}[/bold cyan] ({log_path.name})")
                        for line in tail:
                            self._out_thread(f"  {line[:160]}")
                except Exception:
                    pass
        if not found_any:
            self._out_thread("[dim]No log files found.[/dim]")

    # ─── Thinkodynamic commands ───

    @work(thread=True)
    def _run_evolve(self, component: str, description: str) -> None:
        """Run Darwin Engine evolution on a component."""
        self._out_thread(f"[dim]Evolving {component}...[/dim]")
        try:
            import asyncio
            from dharma_swarm.swarm import SwarmManager

            async def _do() -> dict:
                swarm = SwarmManager(state_dir=str(DHARMA_STATE))
                await swarm.init()
                result = await swarm.evolve(
                    component=component,
                    change_type="mutation",
                    description=description,
                    diff="",
                )
                await swarm.shutdown()
                return result

            result = asyncio.run(_do())
            if result.get("status") == "rejected":
                self._out_thread(f"[red]REJECTED: {result.get('reason', 'unknown')}[/red]")
            else:
                self._out_thread(
                    f"[green]ARCHIVED: {result.get('entry_id', '?')} "
                    f"(fitness: {result.get('weighted_fitness', 0):.3f})[/green]"
                )
        except Exception as e:
            self._out_thread(f"[red]Evolve failed: {e}[/red]")

    @work(thread=True)
    def _run_self_map(self) -> None:
        """Display system self-map: modules, tests, state, thread."""
        self._out_thread("[bold cyan]DHARMA SWARM Self-Map[/bold cyan]\n")

        # Modules
        ds_dir = DHARMA_SWARM / "dharma_swarm"
        if ds_dir.exists():
            modules = sorted(
                f.name for f in ds_dir.glob("*.py")
                if f.name != "__pycache__" and not f.name.startswith("__pycache__")
            )
            self._out_thread(f"  [green]Modules[/green]: {len(modules)}")
            for m in modules:
                self._out_thread(f"    {m}")

        # Tests
        test_dir = DHARMA_SWARM / "tests"
        if test_dir.exists():
            tests = list(test_dir.glob("test_*.py"))
            self._out_thread(f"\n  [green]Test files[/green]: {len(tests)}")

        # State directory
        state = DHARMA_STATE
        if state.exists():
            self._out_thread(f"\n  [green]State dir[/green]: {state}")
            db = state / "db" / "memory.db"
            if db.exists():
                self._out_thread(f"    memory.db: {db.stat().st_size / 1024:.0f}KB")
            pulse_log = state / "pulse.log"
            if pulse_log.exists():
                self._out_thread(f"    pulse.log: {_file_age_str(pulse_log)}")
            witness_dir = state / "witness"
            if witness_dir.exists():
                witness_files = list(witness_dir.glob("*.jsonl"))
                self._out_thread(f"    witness logs: {len(witness_files)} days")

        # Active thread
        thread_file = state / "thread_state.json"
        if thread_file.exists():
            try:
                ts = json.loads(thread_file.read_text())
                self._out_thread(f"\n  [green]Thread[/green]: {ts.get('current_thread', '?')}")
            except Exception:
                pass

        # Ecosystem summary
        manifest = HOME / ".dharma_manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                eco = data.get("ecosystem", {})
                alive = sum(1 for v in eco.values() if v.get("exists"))
                self._out_thread(f"\n  [green]Ecosystem[/green]: {alive}/{len(eco)} alive")
            except Exception:
                pass

    # ─── Dharma & Living Layer commands ───

    @work(thread=True)
    def _run_dharma_status(self) -> None:
        try:
            import asyncio
            from dharma_swarm.dgc_cli import _get_swarm

            async def _status():
                swarm = await _get_swarm()
                status = await swarm.dharma_status()
                await swarm.shutdown()
                return status

            status = asyncio.run(_status())
            lines = ["[bold cyan]Dharma Status[/bold cyan]"]
            for k, v in status.items():
                lines.append(f"  [bold white]{k}[/bold white]: {v}")
            self._out_thread("\n".join(lines))
        except Exception as e:
            self._out_thread(f"[red]Dharma status error: {e}[/red]")

    @work(thread=True)
    def _run_dharma_corpus(self, arg: str = "") -> None:
        try:
            import asyncio
            from dharma_swarm.dharma_corpus import ClaimStatus
            from dharma_swarm.dgc_cli import _get_swarm

            # Parse --status STATUS filter
            status_filter: ClaimStatus | None = None
            parts = arg.split()
            for i, tok in enumerate(parts):
                if tok == "--status" and i + 1 < len(parts):
                    raw = parts[i + 1].lower()
                    try:
                        status_filter = ClaimStatus(raw)
                    except ValueError:
                        valid = ", ".join(s.value for s in ClaimStatus)
                        self._out_thread(f"[red]Unknown status '{raw}'. Valid: {valid}[/red]")
                        return

            async def _corpus():
                swarm = await _get_swarm()
                if swarm._corpus is None:
                    return []
                claims = await swarm._corpus.list_claims(status=status_filter)
                await swarm.shutdown()
                return claims

            claims = asyncio.run(_corpus())
            if not claims:
                label = f" (status={status_filter.value})" if status_filter else ""
                self._out_thread(f"[dim]No claims in corpus{label}.[/dim]")
            else:
                label = f" [{status_filter.value}]" if status_filter else ""
                self._out_thread(f"[bold cyan]Dharma Corpus{label} ({len(claims)} claims)[/bold cyan]")
                for cl in claims[:20]:
                    self._out_thread(f"  [bold white]{cl.id}[/bold white] [{cl.status.value}] {cl.statement[:60]}")
        except Exception as e:
            self._out_thread(f"[red]Corpus error: {e}[/red]")

    @work(thread=True)
    def _run_stigmergy(self, arg: str = "") -> None:
        try:
            import asyncio
            from dharma_swarm.dgc_cli import _get_swarm

            async def _stig():
                swarm = await _get_swarm()
                if swarm._stigmergy is None:
                    await swarm.shutdown()
                    return None, None
                hot = await swarm._stigmergy.hot_paths(window_hours=48, min_marks=2)
                high = await swarm._stigmergy.high_salience(threshold=0.7, limit=5)
                await swarm.shutdown()
                return hot, high

            hot, high = asyncio.run(_stig())
            if hot is None:
                self._out_thread("[dim]Stigmergy not initialized.[/dim]")
                return
            lines = ["[bold cyan]Stigmergy[/bold cyan]"]
            if hot:
                lines.append("  [bold white]Hot Paths[/bold white]:")
                for path, count in hot:
                    lines.append(f"    {path}: {count} marks")
            else:
                lines.append("  [dim]No hot paths.[/dim]")
            if high:
                lines.append("  [bold white]High Salience[/bold white]:")
                for m in high:
                    lines.append(f"    [{m.agent}] {m.observation[:60]} (s={m.salience:.1f})")
            self._out_thread("\n".join(lines))
        except Exception as e:
            self._out_thread(f"[red]Stigmergy error: {e}[/red]")

    @work(thread=True)
    def _run_hum(self) -> None:
        try:
            import asyncio
            from dharma_swarm.dgc_cli import _get_swarm

            async def _hum():
                swarm = await _get_swarm()
                if swarm._stigmergy is None:
                    await swarm.shutdown()
                    return []
                from dharma_swarm.subconscious import SubconsciousStream
                stream = SubconsciousStream(stigmergy=swarm._stigmergy)
                dreams = await stream.get_recent_dreams(limit=10)
                await swarm.shutdown()
                return dreams

            dreams = asyncio.run(_hum())
            if not dreams:
                self._out_thread("[dim]The HUM is silent. No dreams yet.[/dim]")
            else:
                lines = ["[bold cyan]Subconscious Dreams[/bold cyan]"]
                for d in dreams:
                    lines.append(f"  {d.source_a} <-> {d.source_b}")
                    lines.append(f"    [dim]{d.resonance_type}: {d.description[:60]}[/dim] (strength={d.strength:.2f})")
                self._out_thread("\n".join(lines))
        except Exception as e:
            self._out_thread(f"[red]HUM error: {e}[/red]")

    # ─── Actions ───

    def action_clear_log(self) -> None:
        try:
            self.query_one("#chat-log", RichLog).clear()
        except Exception:
            pass

    def action_show_splash(self) -> None:
        self.push_screen(SplashScreen())

    def action_paste_clipboard(self) -> None:
        text = _clipboard_read()
        if not text:
            self._out("[yellow]Clipboard appears empty or unavailable.[/yellow]")
            return
        try:
            inp = self.query_one("#cmd-input", Input)
            inp.insert_text_at_cursor(text)
            inp.focus()
        except Exception as e:
            self._out(f"[red]Paste failed: {e}[/red]")

    def action_copy_last_reply(self) -> None:
        with self._conversation_lock:
            reply = next(
                (m["content"] for m in reversed(self._conversation) if m["role"] == "assistant"),
                "",
            )
        if not reply:
            self._out("[dim]No Claude reply available to copy.[/dim]")
            return
        if _clipboard_write(reply):
            self._out("[green]Copied last Claude reply to clipboard.[/green]")
        else:
            self._out("[red]Clipboard unavailable (pbcopy/wl-copy/xclip not found).[/red]")

    async def action_quit(self) -> None:
        self.exit()


# ─── Entry point ─────────────────────────────────────────────────────


def run_tui() -> None:
    app = DGCApp()
    app.run()


if __name__ == "__main__":
    run_tui()
