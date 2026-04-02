# Terminal TUI tmux Harness

This is the operator-side harness for driving the Bun TUI through a real TTY.

## Scripts

- `scripts/start_terminal_tui_tmux.sh`
- `scripts/stop_terminal_tui_tmux.sh`
- `scripts/status_terminal_tui_tmux.sh`
- `scripts/capture_terminal_tui_tmux.sh`
- `scripts/send_terminal_tui_keys.sh`

Default tmux session name:

- `dharma_terminal_tui`

## Commands

Start:

```bash
cd /Users/dhyana/dharma_swarm
./scripts/start_terminal_tui_tmux.sh
```

Stop:

```bash
cd /Users/dhyana/dharma_swarm
./scripts/stop_terminal_tui_tmux.sh
```

Status:

```bash
cd /Users/dhyana/dharma_swarm
./scripts/status_terminal_tui_tmux.sh
```

Capture:

```bash
cd /Users/dhyana/dharma_swarm
./scripts/capture_terminal_tui_tmux.sh 80
```

Send keys:

```bash
cd /Users/dhyana/dharma_swarm
./scripts/send_terminal_tui_keys.sh C-r
./scripts/send_terminal_tui_keys.sh h e l l o
```

Attach directly:

```bash
tmux attach -t dharma_terminal_tui
```

## Important implementation note

The harness starts the TUI as a real TTY process inside tmux. Do not run the
Ink app through `tee` or another stdout pipe during launch, because that breaks
TTY semantics and makes keyboard interaction unreliable.

Logging is handled with `tmux pipe-pane` instead.

## Computer Use status

Playwright MCP was installed and configured for Codex at:

- `/Users/dhyana/.codex/config.toml`
- `/Users/dhyana/.local/npm/bin/playwright-mcp`

That is useful for browser automation after Codex restarts and reloads MCP
servers. It does not itself provide full desktop control of the TUI. For the
Bun terminal surface, this tmux harness is the current practical interaction
path from Codex.
