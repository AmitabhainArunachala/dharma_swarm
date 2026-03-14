"""Command Palette provider for DGC.

Integrates with Textual's built-in command palette (Ctrl+P) to expose
all DGC slash commands as searchable, fuzzy-matched entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from textual.command import Hit, Hits, Provider


@dataclass(frozen=True, slots=True)
class DGCCommand:
    """A single DGC slash command definition."""

    name: str
    description: str
    slash_cmd: str
    category: str = "system"


# All available DGC commands -- order determines default display priority.
DGC_COMMANDS: tuple[DGCCommand, ...] = (
    # System
    DGCCommand("System Status", "Full system status panel", "/status", "system"),
    DGCCommand("Health Check", "Ecosystem health check", "/health", "system"),
    DGCCommand("Run Pulse", "Run heartbeat", "/pulse", "system"),
    DGCCommand("Self Map", "System self-map (modules, tests, state)", "/self", "system"),
    DGCCommand("Context Layers", "Show agent context layers", "/context", "system"),
    DGCCommand("Command Center Dashboard", "Open Command Center dashboard", "/dashboard", "system"),
    # Memory
    DGCCommand("Memory", "Strange loop memory", "/memory", "memory"),
    DGCCommand("Witness", "Record observation", "/witness", "memory"),
    DGCCommand("Agent Notes", "Shared agent notes", "/notes", "memory"),
    DGCCommand("Archive", "Evolution archive (last 10)", "/archive", "memory"),
    DGCCommand("Darwin Status", "Darwin experiment memory and trust ladder", "/darwin", "memory"),
    DGCCommand("Logs", "Tail system logs", "/logs", "memory"),
    # Agents
    DGCCommand("Swarm Status", "Swarm status", "/swarm status", "agents"),
    DGCCommand("Test Gates", "Test telos gates", "/gates", "agents"),
    DGCCommand("Evolve", "Darwin Engine evolution", "/evolve", "agents"),
    DGCCommand("Evolve Status", "Darwin operator visibility", "/evolve status", "agents"),
    DGCCommand("AGNI VPS", "Run command on AGNI", "/agni", "agents"),
    DGCCommand("Trishula Inbox", "Trishula inbox messages", "/trishula", "agents"),
    # Integrations
    DGCCommand("OpenClaw Status", "OpenClaw agent status", "/openclaw", "integrations"),
    DGCCommand("Evidence Bundle", "Latest evidence bundle", "/evidence", "integrations"),
    DGCCommand("Runtime Matrix", "Live process/runtime matrix", "/runtime", "integrations"),
    DGCCommand("Git Status", "Repo branch/head/dirty counts", "/git", "integrations"),
    # Dharma
    DGCCommand("Dharma Status", "Dharma kernel/corpus status", "/dharma status", "dharma"),
    DGCCommand("Corpus Claims", "List corpus claims", "/corpus", "dharma"),
    DGCCommand("Stigmergy", "Hot paths and high salience marks", "/stigmergy", "dharma"),
    DGCCommand("HUM Dreams", "Subconscious dreams", "/hum", "dharma"),
    # Chat
    DGCCommand("Launch Claude", "Launch native Claude Code UI", "/chat", "chat"),
    DGCCommand("Continue Session", "Continue last Claude Code session", "/chat continue", "chat"),
    DGCCommand("New Session", "Start new chat session", "/reset", "chat"),
    DGCCommand("Clear Screen", "Clear output", "/clear", "chat"),
    DGCCommand("Cancel Run", "Cancel active provider run", "/cancel", "chat"),
)


class DGCCommandProvider(Provider):
    """Provides DGC commands to the Textual command palette."""

    async def search(self, query: str) -> Hits:
        """Yield matching commands scored by fuzzy relevance."""
        matcher = self.matcher(query)
        for cmd in DGC_COMMANDS:
            score = matcher.match(f"{cmd.name} {cmd.slash_cmd} {cmd.description}")
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(cmd.name),
                    partial(self._execute_command, cmd.slash_cmd),
                    help=f"{cmd.slash_cmd} -- {cmd.description}",
                )

    async def _execute_command(self, slash_cmd: str) -> None:
        """Post the slash command as if typed by the user."""
        from ..widgets.prompt_input import PromptInput

        self.app.post_message(PromptInput.Submitted(slash_cmd))
