# Bun TUI Surface Direction

## Product feel

The upgraded Bun TUI should feel like a cleaner elite coding cockpit:

- command-native, not menu-heavy
- keyboard-first, not mouse-led
- crisp and quiet, not atmospheric noise
- highly inspectable, not visually crowded
- session-aware and route-aware at all times

The direct reference is "Claude Code, but cleaner and more callable."

## Interaction rules

- Slash commands are first-class transcript objects, not plain text.
- Important section headers should appear inline in the transcript flow.
- Commands should render in blue so the shell visually distinguishes action surfaces from prose.
- Tool execution should remain visible but compact.
- Subheads should break the transcript into small inspectable slices instead of long undifferentiated logs.
- The shell should bias toward text-driven interaction, with hotkeys and inline actions as acceleration layers.

## Transcript semantics

The transcript should render these classes distinctly:

- headings: major shell or mission sections
- subheadings: local route or action groupings
- commands: slash commands and callable operator actions
- tool calls: active or completed tool actions
- thinking: secondary, dimmed, expandable in future
- errors: explicit and high contrast

## Near-term shell implications

- keep the current multi-pane shell, but make the transcript the primary interaction rail
- enrich transcript rendering before adding more chrome
- attach command and permission semantics to transcript lines instead of hiding them in side panes
- preserve dedicated panes for runtime, repo, agents, models, and evolution as inspectable side rails

## Convergence rule

This surface direction must sit on top of the shared operator-core contracts.
The shell may feel highly specialized, but it must not invent private session,
routing, permission, or runtime truth semantics.
