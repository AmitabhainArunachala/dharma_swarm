"""Command registry primitives for the modular DGC command system."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

ParserBuilder = Callable[[argparse._SubParsersAction], None]
Handler = Callable[[argparse.Namespace], int | None]


@dataclass(frozen=True)
class DgcCommand:
    """Metadata for one modular DGC command."""

    name: str
    handler: Handler
    build_parser: ParserBuilder
    aliases: tuple[str, ...] = ()
    pack: str = "core"
    read_only: bool = False


class DgcCommandRegistry:
    """Registry for modular DGC commands and aliases."""

    def __init__(self) -> None:
        self._commands: dict[str, DgcCommand] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: DgcCommand) -> None:
        if command.name in self._commands or command.name in self._aliases:
            raise ValueError(f"command {command.name!r} already registered")
        for alias in command.aliases:
            if alias in self._commands or alias in self._aliases:
                raise ValueError(f"command alias {alias!r} already registered")
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def resolve(self, name: str) -> DgcCommand | None:
        command = self._commands.get(name)
        if command is not None:
            return command
        canonical = self._aliases.get(name)
        if canonical is None:
            return None
        return self._commands[canonical]

    def build_parser(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest="command")
        self.populate_subparsers(subparsers)

    def populate_subparsers(self, subparsers: argparse._SubParsersAction) -> None:
        for command in self._commands.values():
            command.build_parser(subparsers)

    def dispatch(self, args: argparse.Namespace) -> bool:
        command_name = getattr(args, "command", None)
        if not command_name:
            return False
        command = self.resolve(command_name)
        if command is None:
            return False
        rc = command.handler(args)
        if isinstance(rc, int) and rc != 0:
            raise SystemExit(rc)
        return True
