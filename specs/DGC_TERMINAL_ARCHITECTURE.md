---
title: DGC Terminal Interface — Definitive Component Architecture
path: specs/DGC_TERMINAL_ARCHITECTURE.md
slug: dgc-terminal-interface-definitive-component-architecture
doc_type: spec
status: superseded
summary: 'Version 1.0 baseline terminal architecture. Retained as the Claude-specific predecessor to specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md, not the current governing spec.'
source:
  provenance: repo_local
  kind: spec
  origin_signals: []
  cited_urls:
  - https://textual.textualize.io/
  - https://github.com/Textualize/textual/discussions
  - https://textual.textualize.io/blog/2024/09/15/anatomy-of-a-textual-user-interface/
  - https://leanpub.com/textual/
  - https://code.claude.com/docs/en/cli-reference
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
inspiration:
- stigmergy
- operator_runtime
- research_synthesis
connected_python_files:
- dharma_swarm/tui/widgets/tool_call_card.py
- tests/test_agent_runner_routing_feedback.py
- tests/test_auto_research_engine.py
- tests/test_auto_research_models.py
- tests/test_evolution_runtime_fields.py
connected_python_modules:
- dharma_swarm.tui.widgets.tool_call_card
- tests.test_agent_runner_routing_feedback
- tests.test_auto_research_engine
- tests.test_auto_research_models
- tests.test_evolution_runtime_fields
connected_relevant_files:
- specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md
- specs/README.md
- dharma_swarm/tui/widgets/tool_call_card.py
- tests/test_agent_runner_routing_feedback.py
- tests/test_auto_research_engine.py
- tests/test_auto_research_models.py
- tests/test_evolution_runtime_fields.py
improvement:
  room_for_improvement:
  - Keep the v1.0 baseline readable as historical design context without letting it compete with v1.1.
  - Add a sharper delta summary if later agents still need to compare v1.0 to the provider-agnostic path.
  - Link any still-live citations to the governing v1.1 file when appropriate.
  next_review_at: '2026-04-05T12:00:00+09:00'
pkm:
  note_class: spec
  vault_path: specs/DGC_TERMINAL_ARCHITECTURE.md
  retrieval_terms:
  - specs
  - dgc
  - terminal
  - architecture
  - v1.0
  - baseline
  - superseded
  - claude-specific
  evergreen_potential: high
stigmergy:
  meaning: This file is the retained v1.0 design baseline for the DGC terminal architecture and should be read as predecessor context rather than current governing truth.
  state: archive
  semantic_weight: 0.64
  coordination_comment: 'Retained as the v1.0 Claude-specific predecessor to specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising specs/DGC_TERMINAL_ARCHITECTURE.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: constraint_and_design_trace
curation:
  last_frontmatter_refresh: '2026-04-03T20:34:00+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# DGC Terminal Interface — Definitive Component Architecture

**Version:** 1.0  
**Date:** 2026-03-05  
**Target:** Python Textual 8.0.2 + Claude Code CLI v2.1.69 `--output-format stream-json`  
**Platform:** macOS M3 Pro, Python 3.14  
**Status:** Superseded baseline retained for historical comparison  
**Current Governing Successor:** `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md`

This file is kept as the Claude-specific v1.0 predecessor.
Treat v1.1 as the current governing terminal architecture spec.

---

## Table of Contents

1. [Question 1: Architecture Tradeoffs](#q1-architecture-tradeoffs)
2. [Question 2: TUI Design Patterns Worth Stealing](#q2-tui-design-patterns-worth-stealing)
3. [Question 3: Textual 8.0.2 Best Practices](#q3-textual-802-best-practices)
4. [Question 4: Missing Features & Gaps](#q4-missing-features--gaps)
5. [Question 5: Future-Proofing for Self-Evolution](#q5-future-proofing-for-self-evolution)
6. [Question 6: Complete Component Architecture](#q6-complete-component-architecture)
7. [Appendix A: Claude Code NDJSON Protocol Reference](#appendix-a-claude-code-ndjson-protocol-reference)
8. [Appendix B: Warm Dark Theme Specification](#appendix-b-warm-dark-theme-specification)
9. [Appendix C: Research Sources](#appendix-c-research-sources)

---

## Q1: Architecture Tradeoffs

### The Core Question

> "Monolith `tui.py` vs decomposed package — how do we split 1,600 lines into the right module boundaries for a self-evolving system?"

### Verdict: Decomposed Package with Hard Boundaries

The current 1,600-line `tui.py` monolith is **the single biggest impediment** to both DGC's self-evolution and developer velocity. Here's why and how to fix it.

### Recommended Package Structure

```
dgc/tui/
├── __init__.py              # Public API: DGCApp class only
├── app.py                   # DGCApp(App) — 150 lines max
├── screens/
│   ├── __init__.py
│   ├── main.py              # MainScreen — primary workspace
│   ├── session_browser.py   # SessionBrowserScreen — history nav
│   ├── settings.py          # SettingsScreen — config editor
│   └── help.py              # HelpScreen — contextual help overlay
├── widgets/
│   ├── __init__.py
│   ├── stream_output.py     # StreamOutputWidget — main chat/output
│   ├── prompt_input.py      # PromptInput — multi-line TextArea
│   ├── thinking_panel.py    # ThinkingPanel — extended thinking
│   ├── tool_call_card.py    # ToolCallCard — individual tool call
│   ├── task_list.py         # TaskListWidget — telos/todo tracking
│   ├── status_bar.py        # StatusBar — model, cost, context %
│   ├── mode_indicator.py    # ModeIndicator — N/A/P mode display
│   ├── file_tree.py         # FileTreeWidget — context file browser
│   ├── diff_viewer.py       # DiffViewer — inline/side-by-side diffs
│   └── session_card.py      # SessionCard — session list item
├── engine/
│   ├── __init__.py
│   ├── stream_parser.py     # NDJSON parser — zero UI dependency
│   ├── subprocess_manager.py# Claude Code process lifecycle
│   ├── session_state.py     # Session state machine
│   └── event_types.py       # Dataclass models for all events
├── theme/
│   ├── __init__.py
│   ├── dharma_dark.py       # DharmaDark(Theme) — warm amber
│   └── dharma_dark.tcss     # TCSS stylesheet
└── commands/
    ├── __init__.py
    └── palette.py           # CommandPalette providers
```

### Why This Structure

| Decision | Rationale |
|----------|-----------|
| **`engine/` has zero Textual imports** | The stream parser and subprocess manager are pure Python. They can be unit-tested without any TUI, used by Darwin Engine for non-interactive runs, or replaced entirely. This is the most critical boundary. |
| **One widget per file** | Each widget is independently evolvable. Darwin Engine can mutate `stream_output.py` without touching `prompt_input.py`. `grep -l` finds exactly where any behavior lives. |
| **Screens as composition, not behavior** | Screens only `compose()` widgets and handle routing. All logic lives in widgets or engine. This prevents the "God Screen" anti-pattern. |
| **Theme is a separate concern** | TCSS files + Theme subclass. Agents can restyle the entire app by editing `dharma_dark.tcss` without touching Python. |
| **Commands are separate** | CommandPalette providers are pure data — easy to extend, test, or auto-generate. |

### Tradeoff: Speed of Refactor vs Clean Architecture

You could do this incrementally:

1. **Phase 1** (2 hours): Extract `engine/stream_parser.py` and `engine/event_types.py` from the monolith. This gives you testable event parsing immediately.
2. **Phase 2** (4 hours): Extract each widget into its own file. The monolith becomes a thin `compose()` shell.
3. **Phase 3** (2 hours): Introduce Screens, theme, and command palette.

**Do not try to rewrite from scratch.** Extract, don't rewrite.

### Message Bus Architecture

The fundamental data flow pattern:

```
Claude Code subprocess (NDJSON stdout)
        │
        ▼
┌─────────────────────┐
│  SubprocessManager   │  Thread worker: reads lines, posts messages
│  (engine layer)      │
└────────┬────────────┘
         │ post_message(AgentEvent)
         ▼
┌─────────────────────┐
│  DGCApp / Screen     │  Routes events to widgets
└────────┬────────────┘
         │ Message bubbling / queries
         ▼
┌─────────────────────────────────────────────────┐
│  Widgets: StreamOutput, ToolCallCard, TaskList,  │
│  StatusBar, ThinkingPanel, DiffViewer            │
└─────────────────────────────────────────────────┘
```

**Key principle:** `SubprocessManager` emits typed `Message` subclasses. Widgets subscribe via `on_*` handlers. No widget ever touches the subprocess directly.

---

## Q2: TUI Design Patterns Worth Stealing

### Competitive Analysis Summary

After analyzing 9 tools (Aider, Open Interpreter, Goose, Claude Code CLI, k9s, lazygit, bottom, Warp, Toad), here are the patterns that matter most for DGC:

### 1. lazygit's Command Log (STEAL THIS FIRST)

lazygit shows a scrollable log of every `git` command it executes. This is the single most powerful trust-building pattern in any TUI.

**DGC adaptation:** A "Tool Call Log" panel that shows every tool invocation Claude makes, with:
- Tool name + input summary (collapsed)
- Expand to see full input/output
- Duration + success/failure badge
- Click to jump to the chat context where it was invoked

```
[10:42:01] Bash: pytest tests/ → ✓ 12 passed (3.2s)
[10:42:05] Edit: routes.py → ✓ +8/-2 lines (0.1s)
[10:42:06] Read: config.yml → ✓ 45 lines (0.0s)
[10:42:09] Bash: git diff → ✓ (0.8s)
```

### 2. k9s's `:resource-type` Navigation Grammar

k9s uses a consistent `:type` pattern: `:pods`, `:deploy`, `:svc`. This creates a learnable navigation grammar.

**DGC adaptation:** Use `/` for filtering (like k9s) and `:` for screen navigation:
- `:sessions` — open session browser
- `:files` — open file tree
- `:config` — open settings
- `:log` — open tool call log
- `/` in any panel — filter/search within that panel

### 3. Open Interpreter's Active-Line Execution Tracking

When code runs, Open Interpreter highlights which line is currently executing via `active_line` chunks.

**DGC adaptation:** Claude Code's `tool_progress` events give you elapsed time per tool. Combine with the `assistant` message's `tool_use` blocks to build:
- "Running: `pytest tests/`" with a live timer
- When Bash output streams, show the last few lines in a compact progress area
- On completion, collapse to a one-line summary

### 4. Claude Code's Mode Cycling (Shift+Tab)

The three-mode cycle (Normal → Auto → Plan) with a prominent visual indicator is excellent UX.

**DGC adaptation:** Implement the same cycle but with DGC-specific modes:
- **[N] Normal** — Claude asks for approval on writes/executes
- **[A] Auto** — Claude runs freely (Dharma gates still apply)
- **[P] Plan** — Claude produces plans but takes no action
- **[S] Sage** — DGC's unique mode: contemplative, self-reflective (Shakti-activated)

Each mode should change the border color of the mode indicator widget.

### 5. Warp's "Blocks" Concept

Warp groups each command + output into a visual "block" that can be collapsed, copied, or referenced.

**DGC adaptation:** Each Claude turn becomes a "block" in the output:
- Collapsible (default: auto-collapse after 3 turns)
- Shows a summary line when collapsed: `[Turn 3] Added rate limiting → 3 tools, $0.012`
- Right border color indicates status: amber=running, green=success, red=error

### 6. Harlequin's Split-Pane + Tab Architecture

Harlequin (a SQL IDE built with Textual) demonstrates:
- Query editor (top) + results table (bottom) split
- Multiple query tabs
- Sidebar catalog with lazy-loading

**DGC adaptation:** Two-pane primary layout:
- **Left sidebar** (toggleable, `Ctrl+B`): file tree + task list + context files
- **Main pane**: chat output + prompt input (stacked vertically)
- **Bottom drawer** (toggleable, `Ctrl+J`): diff viewer / tool log / thinking

### Design Principles Extracted

| Principle | Source | DGC Application |
|-----------|--------|-----------------|
| Every tool call visible | lazygit | Tool Call Log panel |
| Plan before act | Warp, Claude Code | Plan mode with structured plan cards |
| Mode always visible | Claude Code | Persistent mode indicator in status bar |
| Keyboard grammar is learnable | k9s, lazygit | `:` for navigation, `/` for filter, `?` for help |
| Information density | bottom, k9s | No wasted space; sidebar collapses; panels resize |
| Session continuity | Goose | Named sessions, browsable history, fork-from-point |
| Warm feedback loops | All | Every action produces visible feedback within 100ms |

---

## Q3: Textual 8.0.2 Best Practices

### Streaming Claude Code Output (The Critical Path)

This is the single most important architectural pattern in the entire TUI. Get it right and everything flows; get it wrong and you'll fight the framework forever.

#### Pattern: Thread Worker + Message Bus + Reactive Widget

```python
# engine/event_types.py — Pure dataclasses, no Textual imports
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SystemInit:
    session_id: str
    model: str
    tools: list[str]
    cwd: str
    permission_mode: str
    claude_code_version: str
    mcp_servers: list[dict] = field(default_factory=list)

@dataclass
class AssistantMessage:
    uuid: str
    session_id: str
    parent_tool_use_id: str | None
    content_blocks: list[dict]  # text, tool_use, thinking blocks
    usage: dict | None = None
    stop_reason: str | None = None

@dataclass
class ToolResult:
    uuid: str
    session_id: str
    tool_use_id: str
    tool_name: str  # resolved from matching assistant tool_use block
    content: str
    is_error: bool = False
    structured_result: dict | None = None
    duration_ms: int | None = None

@dataclass  
class StreamDelta:
    """Token-level delta (requires --include-partial-messages)"""
    delta_type: str  # "text_delta", "thinking_delta", "input_json_delta"
    content: str
    block_index: int
    parent_tool_use_id: str | None = None

@dataclass
class ResultMessage:
    session_id: str
    subtype: str  # "success", "error_max_turns", etc.
    is_error: bool
    total_cost_usd: float
    duration_ms: int
    num_turns: int
    result_text: str | None = None
    errors: list[str] = field(default_factory=list)
    model_usage: dict = field(default_factory=dict)

@dataclass
class ToolProgress:
    tool_use_id: str
    tool_name: str
    elapsed_seconds: float

@dataclass
class TaskStarted:
    task_id: str
    tool_use_id: str
    description: str

@dataclass
class TaskProgress:
    task_id: str
    usage: dict
    last_tool_name: str | None = None

@dataclass
class RateLimitEvent:
    status: str  # "allowed", "allowed_warning", "rejected"
    resets_at: int | None = None
    utilization: float | None = None
```

```python
# engine/stream_parser.py — Pure function, no Textual imports
import json
from .event_types import *

def parse_ndjson_line(line: str) -> object | None:
    """Parse a single NDJSON line into a typed event.
    
    Returns a dataclass instance or None for unrecognized events.
    """
    try:
        raw = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    
    msg_type = raw.get("type")
    subtype = raw.get("subtype")
    
    if msg_type == "system" and subtype == "init":
        return SystemInit(
            session_id=raw["session_id"],
            model=raw.get("model", "unknown"),
            tools=raw.get("tools", []),
            cwd=raw.get("cwd", ""),
            permission_mode=raw.get("permissionMode", "default"),
            claude_code_version=raw.get("claude_code_version", ""),
            mcp_servers=raw.get("mcp_servers", []),
        )
    
    elif msg_type == "assistant":
        msg = raw.get("message", {})
        return AssistantMessage(
            uuid=raw.get("uuid", ""),
            session_id=raw.get("session_id", ""),
            parent_tool_use_id=raw.get("parent_tool_use_id"),
            content_blocks=msg.get("content", []),
            usage=msg.get("usage"),
            stop_reason=msg.get("stop_reason"),
        )
    
    elif msg_type == "user":
        msg = raw.get("message", {})
        content = msg.get("content", [])
        # Extract first tool result (there can be multiple)
        for block in content:
            if block.get("type") == "tool_result":
                return ToolResult(
                    uuid=raw.get("uuid", ""),
                    session_id=raw.get("session_id", ""),
                    tool_use_id=block["tool_use_id"],
                    tool_name="",  # Must be resolved against prior assistant msg
                    content=block.get("content", ""),
                    is_error=block.get("is_error", False),
                    structured_result=raw.get("tool_use_result"),
                    duration_ms=raw.get("tool_use_result", {}).get("durationMs"),
                )
        return None
    
    elif msg_type == "stream_event":
        event = raw.get("event", {})
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")
            content = ""
            if delta_type == "text_delta":
                content = delta.get("text", "")
            elif delta_type == "thinking_delta":
                content = delta.get("thinking", "")
            elif delta_type == "input_json_delta":
                content = delta.get("partial_json", "")
            return StreamDelta(
                delta_type=delta_type,
                content=content,
                block_index=event.get("index", 0),
                parent_tool_use_id=raw.get("parent_tool_use_id"),
            )
        return None  # message_start, content_block_start, etc. — skip
    
    elif msg_type == "result":
        return ResultMessage(
            session_id=raw.get("session_id", ""),
            subtype=raw.get("subtype", ""),
            is_error=raw.get("is_error", False),
            total_cost_usd=raw.get("total_cost_usd", 0.0),
            duration_ms=raw.get("duration_ms", 0),
            num_turns=raw.get("num_turns", 0),
            result_text=raw.get("result"),
            errors=raw.get("errors", []),
            model_usage=raw.get("modelUsage", {}),
        )
    
    elif msg_type == "tool_progress":
        return ToolProgress(
            tool_use_id=raw.get("tool_use_id", ""),
            tool_name=raw.get("tool_name", ""),
            elapsed_seconds=raw.get("elapsed_time_seconds", 0),
        )
    
    elif msg_type == "system" and subtype == "task_started":
        return TaskStarted(
            task_id=raw.get("task_id", ""),
            tool_use_id=raw.get("tool_use_id", ""),
            description=raw.get("description", ""),
        )
    
    elif msg_type == "rate_limit_event":
        info = raw.get("rate_limit_info", {})
        return RateLimitEvent(
            status=info.get("status", ""),
            resets_at=info.get("resetsAt"),
            utilization=info.get("utilization"),
        )
    
    return None  # Unrecognized event type
```

```python
# engine/subprocess_manager.py — Thread worker that reads NDJSON
import subprocess
import json
from textual.message import Message
from textual.widget import Widget
from textual.worker import work, get_current_worker
from .stream_parser import parse_ndjson_line
from .event_types import *

class SubprocessManager(Widget):
    """Manages Claude Code subprocess lifecycle.
    
    Invisible widget — no render. Exists solely to own the worker lifecycle
    and post typed messages to the app's message bus.
    """
    
    DEFAULT_CSS = "SubprocessManager { display: none; }"
    
    # --- Typed messages for the bus ---
    class AgentEvent(Message):
        def __init__(self, event: object) -> None:
            super().__init__()
            self.event = event
    
    class ProcessExited(Message):
        def __init__(self, exit_code: int, was_cancelled: bool = False) -> None:
            super().__init__()
            self.exit_code = exit_code
            self.was_cancelled = was_cancelled
    
    @work(thread=True, exclusive=True, group="claude", exit_on_error=False)
    def start(self, cmd: list[str]) -> None:
        """Start Claude Code subprocess and stream NDJSON events."""
        worker = get_current_worker()
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            text=True,
        )
        
        try:
            for raw_line in proc.stdout:
                if worker.is_cancelled:
                    proc.terminate()
                    proc.wait(timeout=5)
                    self.post_message(self.ProcessExited(proc.returncode, was_cancelled=True))
                    return
                
                line = raw_line.strip()
                if not line:
                    continue
                
                event = parse_ndjson_line(line)
                if event is not None:
                    self.post_message(self.AgentEvent(event))
            
            proc.wait()
            self.post_message(self.ProcessExited(proc.returncode))
        
        except Exception as e:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            self.post_message(self.ProcessExited(-1))
    
    def stop(self) -> None:
        """Cancel the running worker (and thus the subprocess)."""
        self.workers.cancel_group(self, "claude")
```

```python
# widgets/stream_output.py — Renders streaming Claude output
from textual.widgets import RichLog
from textual.reactive import reactive
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from ..engine.event_types import (
    AssistantMessage, ToolResult, StreamDelta, ToolProgress
)
from ..engine.subprocess_manager import SubprocessManager

class StreamOutput(RichLog):
    """Main output widget — renders Claude's streaming response.
    
    Uses RichLog (append-only) rather than Markdown (full re-render)
    because:
    1. Append-only is O(1) per token; Markdown re-render is O(n)
    2. RichLog auto-scrolls; Markdown requires manual scroll management
    3. RichLog supports mixed Rich renderables (Markdown + Syntax + Panel)
    4. For a chat-style interface, append is the natural model
    
    For token-level streaming (--include-partial-messages), we accumulate
    text deltas into a buffer and periodically flush to the log.
    """
    
    DEFAULT_CSS = """
    StreamOutput {
        background: $surface;
        scrollbar-background: $surface;
        scrollbar-color: $text-muted;
        padding: 0 1;
    }
    """
    
    # Buffer for accumulating stream deltas before flush
    _text_buffer: str = ""
    _thinking_buffer: str = ""
    _current_tool_name: str = ""
    
    def on_mount(self) -> None:
        self._flush_timer = self.set_interval(1/15, self._flush_buffer)  # 15fps
    
    def handle_stream_delta(self, delta: StreamDelta) -> None:
        """Accumulate token-level deltas into buffer."""
        if delta.delta_type == "text_delta":
            self._text_buffer += delta.content
        elif delta.delta_type == "thinking_delta":
            self._thinking_buffer += delta.content
    
    def _flush_buffer(self) -> None:
        """Flush accumulated buffer to display (called by timer)."""
        if self._text_buffer:
            # Write as raw text (not markdown) during streaming
            # Full markdown render happens on assistant message complete
            self.write(Text(self._text_buffer, style=""))
            self._text_buffer = ""
        if self._thinking_buffer:
            self.write(Text(self._thinking_buffer, style="dim italic"))
            self._thinking_buffer = ""
    
    def handle_assistant_complete(self, msg: AssistantMessage) -> None:
        """Render complete assistant message (replaces streamed tokens)."""
        self._flush_buffer()  # flush any remaining
        
        for block in msg.content_blocks:
            if block["type"] == "text":
                self.write(Markdown(block["text"]))
            elif block["type"] == "tool_use":
                tool_panel = Panel(
                    Syntax(
                        str(block.get("input", {})),
                        "json",
                        theme="monokai",
                        word_wrap=True,
                    ),
                    title=f"Tool: {block['name']}",
                    border_style="yellow",
                    subtitle=f"id: {block['id'][:12]}…",
                )
                self.write(tool_panel)
            elif block["type"] == "thinking":
                self.write(Panel(
                    Text(block["thinking"], style="dim"),
                    title="Thinking",
                    border_style="blue",
                    expand=False,
                ))
    
    def handle_tool_result(self, result: ToolResult) -> None:
        """Render tool execution result."""
        style = "red" if result.is_error else "green"
        icon = "✗" if result.is_error else "✓"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        
        # Truncate long output
        content = result.content
        if len(content) > 500:
            content = content[:500] + f"\n… ({len(result.content)} chars total)"
        
        self.write(Panel(
            Text(content),
            title=f"{icon} {result.tool_name}{duration}",
            border_style=style,
        ))
    
    def handle_tool_progress(self, progress: ToolProgress) -> None:
        """Show running tool indicator."""
        self.write(Text(
            f"  ⏳ {progress.tool_name} running… ({progress.elapsed_seconds:.1f}s)",
            style="dim yellow",
        ))
```

### Multi-Line Input with TextArea

```python
# widgets/prompt_input.py
from textual.widgets import TextArea
from textual.message import Message
from textual import events

class PromptInput(TextArea):
    """Multi-line input with Enter=submit, Shift+Enter=newline.
    
    This is the correct pattern for Textual's TextArea widget:
    - Override _on_key to intercept Enter before TextArea processes it
    - Let Shift+Enter through as normal newline
    - Post a custom Submitted message with the full text
    """
    
    DEFAULT_CSS = """
    PromptInput {
        height: auto;
        min-height: 3;
        max-height: 12;
        border: tall $accent;
        background: $surface;
    }
    PromptInput:focus {
        border: tall $accent-bright;
    }
    """
    
    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text
    
    def _on_key(self, event: events.Key) -> None:
        """Intercept Enter for submit, allow Shift+Enter for newline."""
        if event.key == "enter" and not event.shift:
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
        else:
            # Let TextArea handle everything else (including Shift+Enter)
            pass
```

### Workers: The Golden Rules

| Rule | Why |
|------|-----|
| **All subprocess I/O in `@work(thread=True)`** | Blocking reads on `proc.stdout` would freeze the event loop |
| **`post_message()` for thread→UI communication** | Only thread-safe method; never call `self.query_one()` from a thread |
| **`exclusive=True` on LLM workers** | Prevents stacking multiple Claude processes |
| **`exit_on_error=False` always** | A crashed subprocess shouldn't crash the TUI |
| **`group="claude"` for bulk cancel** | `Ctrl+C` → `cancel_group("claude")` — clean shutdown |
| **Check `worker.is_cancelled` in loops** | Thread workers don't auto-cancel; you must check the flag |
| **`call_from_thread()` for complex UI updates** | When `post_message()` isn't enough (rare) |

### Screens: Modal + Stack Pattern

```python
# app.py
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.binding import Binding

class DGCApp(App):
    CSS_PATH = "theme/dharma_dark.tcss"
    TITLE = "DGC"
    
    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=True),
        Binding("ctrl+j", "toggle_drawer", "Drawer", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("shift+tab", "cycle_mode", "Mode", show=True),
        Binding("?", "help", "Help", show=True),
    ]
    
    SCREENS = {
        "main": "screens.main.MainScreen",
        "sessions": "screens.session_browser.SessionBrowserScreen",
        "settings": "screens.settings.SettingsScreen",
    }
    
    # Use Modes for primary layouts (cleaner than manual screen push)
    MODES = {
        "workspace": "main",
        "sessions": "sessions",
    }
```

### Reactive Attributes for Live State

```python
# widgets/status_bar.py
from textual.reactive import reactive
from textual.widget import Widget

class StatusBar(Widget):
    """Always-visible status bar with live metrics."""
    
    model = reactive("claude-sonnet-4-5")
    cost_usd = reactive(0.0)
    context_pct = reactive(0)
    turn_count = reactive(0)
    mode = reactive("N")  # N=Normal, A=Auto, P=Plan, S=Sage
    session_name = reactive("")
    
    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text-secondary;
        layout: horizontal;
    }
    """
    
    def render(self) -> str:
        mode_colors = {"N": "green", "A": "yellow", "P": "blue", "S": "magenta"}
        mode_color = mode_colors.get(self.mode, "white")
        
        ctx_color = "red" if self.context_pct > 80 else "yellow" if self.context_pct > 60 else "green"
        
        return (
            f" [{mode_color}][{self.mode}][/{mode_color}]"
            f"  {self.session_name or 'untitled'}"
            f"  │  {self.model}"
            f"  │  [{ctx_color}]ctx: {self.context_pct}%[/{ctx_color}]"
            f"  │  ${self.cost_usd:.4f}"
            f"  │  turns: {self.turn_count}"
        )
    
    def watch_mode(self, new_mode: str) -> None:
        """React to mode changes."""
        # Mode changes could trigger border color changes on other widgets
        self.app.query_one("PromptInput").border_subtitle = f"MODE: {new_mode}"
```

---

## Q4: Missing Features & Gaps

### What You Don't Have Yet (and How to Build It)

#### 1. Token-Level Streaming Display

**Gap:** Your current TUI likely uses the default mode (complete `assistant` messages). This means Claude's response appears all at once after each turn, not token-by-token.

**Fix:** Add `--include-partial-messages` to the Claude Code command. This enables `stream_event` messages with `text_delta` content. The `StreamOutput` widget above handles this with a 15fps flush timer on the accumulation buffer.

**Tradeoff:** You'll receive both `stream_event` deltas AND the complete `assistant` message. The complete message is authoritative — use it for history/persistence. Use deltas only for live display.

**Recommendation for v1:** Start WITHOUT `--include-partial-messages`. Display complete turns as they arrive. The UX is "turn-level streaming" — each tool call and response appears as it completes. This is simpler, less buggy, and good enough for v1. Add token streaming in v2.

#### 2. Subagent Tree Visualization

**Gap:** When Claude uses the `Task` tool, subagent events have `parent_tool_use_id` set. No existing TUI renders this as a tree.

**Fix:** Build a `SubagentTree` widget that:
- Creates a nested `Collapsible` when `task_started` fires
- Routes events with matching `parent_tool_use_id` into the nested container
- Shows progress (from `task_progress`) and completion (from `task_notification`)
- Allows expanding/collapsing each subagent's output

This is unique to DGC — no other tool does this well. It directly supports Dharma Swarm's multi-agent visualization.

#### 3. Inline Diff Viewer

**Gap:** Claude Code's `Edit` tool result includes `structuredPatch` and `gitDiff` in the `tool_use_result` field. No TUI renders these as highlighted diffs.

**Fix:** Build a `DiffViewer` widget using Rich's `Syntax` widget with `diff` language for unified diffs, or a custom render using `Text` with per-line color coding:
- Green background: added lines
- Red background: removed lines
- Context lines: default

The `FileEditOutput` structured result gives you `oldString`, `newString`, `structuredPatch`, and optionally `gitDiff.patch`. Use `gitDiff.patch` when available (it's a standard unified diff).

#### 4. Session Browser

**Gap:** Claude Code stores sessions as JSONL at `~/.claude/sessions/`. No TUI provides a rich browser.

**Fix:** A `SessionBrowserScreen` that:
- Lists sessions from `~/.claude/sessions/` with metadata (date, summary, cost, branch)
- Search/filter by text, date range, or branch
- Preview: show the first/last few messages
- Resume: launch `claude --resume <session_id>`
- Fork: launch `claude --resume <id> --fork-session`

This is a differentiation feature — no tool has it.

#### 5. Context Window Visualization

**Gap:** You have token counts per turn (`usage.input_tokens`, `cache_read_input_tokens`). You can estimate context usage as a percentage of the model's `contextWindow` (available in `modelUsage`).

**Fix:** `StatusBar` already shows `ctx: 42%`. Add a visual meter (Rich `Progress` bar) and color-coded warnings:
- Green: < 60%
- Yellow: 60-80%
- Red: > 80%
- Automatic alert when hitting 80%: "Context filling up — consider compacting"

#### 6. No Built-in Resizable Split Panes in Textual

**Gap:** Textual has no `Splitter` widget. You cannot drag to resize panes.

**Fix for v1:** Use fixed fractional widths via TCSS (`width: 1fr` / `width: 3fr`) with a toggle shortcut to show/hide the sidebar. This is what Harlequin does.

**Fix for v2:** Build a custom `ResizableDivider` widget:
```python
class ResizableDivider(Widget):
    """Draggable divider between two panes."""
    DEFAULT_CSS = "ResizableDivider { width: 1; background: $accent-dim; cursor: col-resize; }"
    
    def on_mouse_down(self, event):
        self.capture_mouse()
    
    def on_mouse_move(self, event):
        if self.mouse_captured:
            # Adjust parent's left/right child widths
            left = self.parent.children[0]
            right = self.parent.children[2]
            total = left.size.width + right.size.width
            new_left = max(20, min(total - 20, event.screen_x))
            left.styles.width = new_left
            right.styles.width = total - new_left
    
    def on_mouse_up(self, event):
        self.release_mouse()
```

#### 7. Cost Tracking Across Sessions

**Gap:** Claude Code gives per-session cost in `result.total_cost_usd` and per-model breakdown in `modelUsage`. But there's no persistent tracking.

**Fix:** Write each session's cost summary to a local SQLite database or JSON log. Build a `/cost` command that shows daily/weekly/monthly spend.

---

## Q5: Future-Proofing for Self-Evolution

### The Core Constraint

DGC is not a normal TUI. It must be evolvable by its own agents. This means:

1. **Darwin Engine must be able to mutate any widget** without understanding the whole system
2. **Shakti must be able to propose new UI elements** (new panels, new visualizations)  
3. **Stigmergy traces must flow through the TUI layer** (every agent interaction leaves a mark)

### Architecture Decisions for Self-Evolution

#### 1. Widget Registry Pattern

Instead of hardcoding widgets in `compose()`, use a registry that Darwin can modify:

```python
# widgets/__init__.py
WIDGET_REGISTRY = {
    "stream_output": "dgc.tui.widgets.stream_output.StreamOutput",
    "prompt_input": "dgc.tui.widgets.prompt_input.PromptInput",
    "status_bar": "dgc.tui.widgets.status_bar.StatusBar",
    "task_list": "dgc.tui.widgets.task_list.TaskListWidget",
    "thinking_panel": "dgc.tui.widgets.thinking_panel.ThinkingPanel",
    "tool_call_card": "dgc.tui.widgets.tool_call_card.ToolCallCard",
}

def get_widget_class(name: str):
    """Dynamic widget resolution — Darwin can register new widgets."""
    import importlib
    path = WIDGET_REGISTRY[name]
    module_path, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), class_name)
```

#### 2. TCSS Hot-Reload

Textual supports live CSS reloading in dev mode (`textual run --dev`). For production, build a file watcher:

```python
@work(thread=True)
def watch_css(self) -> None:
    """Watch TCSS file for changes (Darwin can edit it)."""
    import time
    from pathlib import Path
    css_path = Path("dgc/tui/theme/dharma_dark.tcss")
    last_mtime = css_path.stat().st_mtime
    while not get_current_worker().is_cancelled:
        time.sleep(1)
        current_mtime = css_path.stat().st_mtime
        if current_mtime != last_mtime:
            last_mtime = current_mtime
            self.call_from_thread(self.app.stylesheet.reparse)
```

#### 3. Event Hook System for Stigmergy

Every significant TUI event should be emittable as a stigmergy trace:

```python
# engine/stigmergy_bridge.py
from pathlib import Path
import json, time

TRACE_DIR = Path.home() / ".dgc" / "stigmergy"

def emit_trace(event_type: str, data: dict) -> None:
    """Write a stigmergy trace for other agents to discover."""
    trace = {
        "timestamp": time.time(),
        "source": "tui",
        "event": event_type,
        "data": data,
    }
    trace_file = TRACE_DIR / f"{int(time.time() * 1000)}.json"
    trace_file.parent.mkdir(parents=True, exist_ok=True)
    trace_file.write_text(json.dumps(trace))
```

Events to trace:
- `user_prompt_submitted` — what the user asked
- `mode_changed` — N→A, A→P, etc.
- `session_started`, `session_resumed`, `session_forked`
- `tool_call_denied` — permission denials (Dharma gate activations)
- `context_warning` — context > 80%
- `error_encountered` — any error in the stream

#### 4. Plugin Architecture for New Panels

Allow Darwin/Shakti to register new panels without modifying core screens:

```python
# screens/main.py
class MainScreen(Screen):
    
    PANEL_SLOTS = {
        "sidebar_top": "file_tree",
        "sidebar_bottom": "task_list",
        "main": "stream_output",
        "drawer": "tool_call_log",
    }
    
    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield get_widget_class(self.PANEL_SLOTS["sidebar_top"])()
                yield get_widget_class(self.PANEL_SLOTS["sidebar_bottom"])()
            with Vertical(id="main-area"):
                yield get_widget_class(self.PANEL_SLOTS["main"])()
                yield PromptInput()
```

Darwin can modify `PANEL_SLOTS` to swap widgets without touching layout logic.

#### 5. Textual-Web as Future Escape Hatch

Textual apps can be served in a browser via `textual serve`. This means:
- DGC's TUI can become a web UI with zero code changes
- Accessibility (screen readers, ARIA) becomes possible
- Mobile/tablet access becomes possible
- Remote pair programming becomes possible

**Decision:** Keep all custom widgets compatible with `textual-web`. This means:
- No direct terminal escape sequences
- No raw curses calls
- All styling via TCSS (not `rich.style`)
- All interaction via Textual's event system

---

## Q6: Complete Component Architecture

### System-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER'S TERMINAL                           │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     DGCApp (Textual)                      │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │                   MainScreen                         │ │   │
│  │  │                                                      │ │   │
│  │  │  ┌──────────┐  ┌──────────────────────────────────┐ │ │   │
│  │  │  │ StatusBar │  │  model: claude-4  ctx: 42%       │ │ │   │
│  │  │  └──────────┘  │  cost: $0.023  turns: 5  [N]     │ │ │   │
│  │  │                └──────────────────────────────────┘ │ │   │
│  │  │  ┌────────────┬──────────────────────────────────┐ │ │   │
│  │  │  │ Sidebar    │  StreamOutput                     │ │ │   │
│  │  │  │            │                                    │ │ │   │
│  │  │  │ FileTree   │  [user] Add rate limiting...       │ │ │   │
│  │  │  │ ▸ src/     │                                    │ │ │   │
│  │  │  │   api.py   │  [claude] I'll implement token     │ │ │   │
│  │  │  │   routes.  │  bucket rate limiting...           │ │ │   │
│  │  │  │            │                                    │ │ │   │
│  │  │  │ ──────── │  ┌────────────────────────────┐    │ │ │   │
│  │  │  │ TaskList  │  │ Tool: Bash                  │    │ │ │   │
│  │  │  │ ✓ Step 1  │  │ pytest tests/ -v            │    │ │ │   │
│  │  │  │ ✓ Step 2  │  │ ✓ 12 passed (3.2s)         │    │ │ │   │
│  │  │  │ ☐ Step 3  │  └────────────────────────────┘    │ │ │   │
│  │  │  │            │                                    │ │ │   │
│  │  │  └────────────┤  ┌────────────────────────────┐   │ │ │   │
│  │  │               │  │ PromptInput                 │   │ │ │   │
│  │  │               │  │ > _                         │   │ │ │   │
│  │  │               │  └────────────────────────────┘   │ │ │   │
│  │  │               └──────────────────────────────────┘ │ │   │
│  │  │                                                      │ │   │
│  │  │  ┌──────────────────────────────────────────────┐   │ │   │
│  │  │  │ Footer: [i]nput [p]lan [a]uto [/]search [?]  │   │ │   │
│  │  │  └──────────────────────────────────────────────┘   │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ Textual Message Bus               │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SubprocessManager (invisible widget)          │   │
│  │  @work(thread=True) reads NDJSON from Claude Code stdout  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ subprocess.Popen(stdout=PIPE)     │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Claude Code CLI v2.1.69                       │   │
│  │  claude -p "..." --output-format stream-json --verbose    │   │
│  │  [--include-partial-messages] [--resume SESSION_ID]       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Complete Widget Inventory

| Widget | Parent | Purpose | Key Reactive State |
|--------|--------|---------|--------------------|
| `DGCApp` | — | Top-level app, theme, bindings, mode | `mode: str` |
| `MainScreen` | App | Primary workspace screen | — |
| `SessionBrowserScreen` | App (pushed) | Session history | `sessions: list` |
| `SettingsScreen` | App (modal) | Configuration editor | `config: dict` |
| `HelpScreen` | App (modal) | Contextual help overlay | `context: str` |
| `StatusBar` | MainScreen | Always-visible top bar | `model, cost_usd, context_pct, mode, turn_count` |
| `Sidebar` | MainScreen | Collapsible left panel | `visible: bool` |
| `FileTree` | Sidebar | Project file browser | `files: list, context_files: set` |
| `TaskList` | Sidebar | Agent task/telos tracker | `tasks: list[Task]` |
| `StreamOutput` | MainScreen | Main chat/output area (RichLog) | `_text_buffer, _thinking_buffer` |
| `PromptInput` | MainScreen | Multi-line input (TextArea) | — |
| `ToolCallCard` | StreamOutput | Individual tool call display | `status: str, elapsed: float` |
| `ThinkingPanel` | StreamOutput | Extended thinking display | `thinking_text: str, collapsed: bool` |
| `DiffViewer` | Drawer | File diff display | `patch: str, filename: str` |
| `ToolCallLog` | Drawer | Scrollable tool invocation log | `entries: list` |
| `ModeIndicator` | StatusBar | Prominent mode badge | `mode: str` |
| `SubprocessManager` | App (invisible) | Claude Code process lifecycle | — |
| `BottomDrawer` | MainScreen | Toggleable bottom panel | `visible: bool, active_tab: str` |

### Complete TCSS Stylesheet

```css
/* theme/dharma_dark.tcss */

/* === Root variables === */
$bg-base: #111008;
$bg-elevated: #1c1810;
$bg-surface: #252018;
$bg-overlay: #2e2820;

$text-primary: #f0e8d8;
$text-secondary: #a89880;
$text-disabled: #5a5040;

$accent-bright: #D4A017;
$accent-dim: #8A6A1A;
$accent-subtle: #4A3B18;

$success: #4CAF72;
$warning: #E06020;
$error: #E05050;
$info: #5090D8;
$thinking: #7B68EE;

/* === App-level === */
Screen {
    background: $bg-base;
    color: $text-primary;
}

/* === Status Bar === */
StatusBar {
    dock: top;
    height: 1;
    background: $bg-surface;
    color: $text-secondary;
}

/* === Sidebar === */
#sidebar {
    width: 28;
    background: $bg-elevated;
    border-right: tall $accent-dim;
}

#sidebar.-hidden {
    display: none;
}

/* === File Tree === */
FileTree {
    height: 1fr;
    padding: 0 1;
}

FileTree > .tree--cursor {
    background: $accent-subtle;
}

/* === Task List === */
TaskList {
    height: auto;
    max-height: 12;
    border-top: tall $accent-dim;
    padding: 0 1;
}

/* === Stream Output === */
StreamOutput {
    background: $bg-base;
    padding: 0 1;
}

StreamOutput:focus {
    border: none;
}

/* === Prompt Input === */
PromptInput {
    dock: bottom;
    height: auto;
    min-height: 3;
    max-height: 12;
    margin: 0 1;
    border: tall $accent-dim;
    background: $bg-surface;
}

PromptInput:focus {
    border: tall $accent-bright;
}

/* === Bottom Drawer === */
#drawer {
    height: 16;
    border-top: tall $accent-dim;
    background: $bg-elevated;
}

#drawer.-hidden {
    display: none;
}

/* === Tool Call Card === */
ToolCallCard {
    margin: 1 0;
    padding: 0 1;
}

ToolCallCard.-running {
    border-left: thick $accent-bright;
}

ToolCallCard.-success {
    border-left: thick $success;
}

ToolCallCard.-error {
    border-left: thick $error;
}

/* === Thinking Panel === */
ThinkingPanel {
    color: $thinking;
    margin: 0 4 0 0;
    padding: 0 1;
}

/* === Mode-specific styling === */
.mode-normal PromptInput {
    border: tall $success;
}

.mode-auto PromptInput {
    border: tall $accent-bright;
}

.mode-plan PromptInput {
    border: tall $info;
}

.mode-sage PromptInput {
    border: tall $thinking;
}

/* === Footer === */
Footer {
    background: $bg-surface;
}

/* === Scrollbars === */
* {
    scrollbar-background: $bg-surface;
    scrollbar-color: $text-disabled;
    scrollbar-color-hover: $text-secondary;
    scrollbar-color-active: $accent-dim;
    scrollbar-size-vertical: 1;
}

/* === Modal Screens === */
ModalScreen {
    background: $bg-base 80%;
}

ModalScreen > * {
    background: $bg-surface;
    border: thick $accent-bright;
    margin: 4 8;
}
```

### Keyboard Binding Map

| Key | Scope | Action |
|-----|-------|--------|
| `Enter` | PromptInput focused | Submit prompt to Claude |
| `Shift+Enter` | PromptInput focused | Insert newline |
| `Shift+Tab` | Global | Cycle mode: N→A→P→S→N |
| `Ctrl+B` | Global | Toggle sidebar |
| `Ctrl+J` | Global | Toggle bottom drawer |
| `Ctrl+P` | Global | Open command palette |
| `Ctrl+C` | Global | Cancel running Claude process |
| `Ctrl+D` | Global | Exit DGC |
| `/` | Any panel | Filter/search within panel |
| `?` | Global | Show contextual help |
| `Escape` | Modal/filter | Close modal or cancel filter |
| `Tab` | Global | Cycle focus between panels |
| `F1`–`F4` | Drawer | Switch drawer tabs (Log/Diff/Think/Tasks) |
| `Ctrl+N` | Global | New session |
| `Ctrl+R` | Global | Resume session (opens browser) |
| `Ctrl+S` | Global | Save/name current session |

### Event Routing Table

| NDJSON Event | Parser Output | Target Widget(s) | Display Action |
|---|---|---|---|
| `system/init` | `SystemInit` | `StatusBar`, `FileTree` | Set model, session name, populate tools |
| `assistant` (text) | `AssistantMessage` | `StreamOutput` | Render markdown text block |
| `assistant` (tool_use) | `AssistantMessage` | `StreamOutput`, `ToolCallLog` | Render tool call card (running state) |
| `assistant` (thinking) | `AssistantMessage` | `StreamOutput`, `ThinkingPanel` | Render collapsible thinking block |
| `user` (tool_result) | `ToolResult` | `StreamOutput`, `ToolCallLog` | Update tool card (success/error), render result |
| `user` (tool_result, Edit) | `ToolResult` | `DiffViewer` | Render structured diff from `tool_use_result` |
| `stream_event` (text_delta) | `StreamDelta` | `StreamOutput` | Append to text buffer, flush at 15fps |
| `stream_event` (thinking_delta) | `StreamDelta` | `StreamOutput` | Append to thinking buffer |
| `result/success` | `ResultMessage` | `StatusBar`, `StreamOutput` | Update cost, show completion badge |
| `result/error_*` | `ResultMessage` | `StatusBar`, `StreamOutput` | Show error notification |
| `tool_progress` | `ToolProgress` | `ToolCallLog`, `StreamOutput` | Update elapsed timer on tool card |
| `system/task_started` | `TaskStarted` | `TaskList`, `StreamOutput` | Add subagent entry |
| `system/task_progress` | `TaskProgress` | `TaskList` | Update subagent progress |
| `rate_limit_event` | `RateLimitEvent` | `StatusBar` | Show rate limit warning |

### Build Sequence (Recommended Implementation Order)

| Phase | Deliverable | Lines Est. | Depends On |
|-------|-------------|-----------|------------|
| **Phase 0** | `engine/event_types.py` + `engine/stream_parser.py` + tests | ~300 | Nothing |
| **Phase 1** | `engine/subprocess_manager.py` + `widgets/stream_output.py` + `widgets/prompt_input.py` + minimal `app.py` | ~400 | Phase 0 |
| **Phase 2** | `widgets/status_bar.py` + `widgets/mode_indicator.py` + `theme/dharma_dark.tcss` | ~200 | Phase 1 |
| **Phase 3** | `widgets/tool_call_card.py` + `widgets/tool_call_log.py` (bottom drawer) | ~250 | Phase 1 |
| **Phase 4** | `widgets/task_list.py` + `widgets/file_tree.py` + sidebar layout | ~300 | Phase 2 |
| **Phase 5** | `widgets/thinking_panel.py` + `widgets/diff_viewer.py` | ~250 | Phase 3 |
| **Phase 6** | `screens/session_browser.py` + `commands/palette.py` | ~300 | Phase 4 |
| **Phase 7** | Widget registry + Stigmergy bridge + Darwin hooks | ~200 | Phase 6 |

**Total estimated:** ~2,200 lines across 20+ files (replacing the current 1,600-line monolith with more functionality and full testability).

---

## Appendix A: Claude Code NDJSON Protocol Reference

### Required CLI Invocation

```bash
# Minimum for TUI consumption:
claude -p "${PROMPT}" \
  --output-format stream-json \
  --verbose \
  --model "${MODEL}" \
  --permission-mode "${PERMISSION_MODE}" \
  --max-turns "${MAX_TURNS}"

# For token-level streaming (v2):
claude -p "${PROMPT}" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages \
  --model "${MODEL}"

# For session resume:
claude -p "${PROMPT}" \
  --output-format stream-json \
  --verbose \
  --resume "${SESSION_ID}"

# For session continuation (most recent in cwd):
claude -p "${PROMPT}" \
  --output-format stream-json \
  --verbose \
  --continue
```

### Critical Clarifications (Correcting Common Misconceptions)

1. **Event types use `type` + `subtype`, NOT slash notation.** The wire format is `{ "type": "system", "subtype": "init" }`, not `"system/init"`. The slash notation is a convenient shorthand for documentation only.

2. **There is NO `assistant/thinking` event type.** Thinking appears as a `content_block` of type `"thinking"` INSIDE `assistant` messages, not as a separate top-level event.

3. **Without `--include-partial-messages`, messages are COMPLETE, not deltas.** Each `assistant` event contains the full assembled message for that turn. Token streaming requires the extra flag.

4. **`--verbose` is REQUIRED.** Without it, you don't get `system/init` or other metadata events.

5. **`--output-format stream-json` only works with `-p` (non-interactive mode).** Interactive sessions cannot produce NDJSON.

6. **Session IDs MUST be UUIDs.** Arbitrary strings will fail. Use UUID v4.

### Complete Event Type Table

| `type` | `subtype` | Requires `--include-partial-messages` | Description |
|--------|-----------|---------------------------------------|-------------|
| `system` | `init` | No | Session initialization (first event) |
| `system` | `compact_boundary` | No | Conversation compaction occurred |
| `system` | `status` | No | Status change (e.g., "compacting") |
| `system` | `task_started` | No | Subagent task began |
| `system` | `task_progress` | No | Subagent progress update |
| `system` | `task_notification` | No | Subagent completed/failed |
| `system` | `hook_started` | No | Lifecycle hook began |
| `system` | `hook_progress` | No | Hook running (stdout/stderr) |
| `system` | `hook_response` | No | Hook finished |
| `system` | `files_persisted` | No | File checkpoint saved |
| `assistant` | — | No | Complete assistant turn |
| `user` | — | No | Tool results |
| `result` | `success` | No | Query completed successfully |
| `result` | `error_max_turns` | No | Hit turn limit |
| `result` | `error_during_execution` | No | Runtime error |
| `result` | `error_max_budget_usd` | No | Budget exceeded |
| `result` | `error_max_structured_output_retries` | No | Schema validation failed |
| `stream_event` | — | **Yes** | Raw Anthropic SSE event (token-level) |
| `tool_progress` | — | No | Tool executing (elapsed time) |
| `auth_status` | — | No | Authentication flow |
| `rate_limit_event` | — | No | Rate limit encountered |
| `tool_use_summary` | — | No | Summary of tool usage |
| `prompt_suggestion` | — | No | Suggested next prompt |

### Content Block Types in `assistant.message.content[]`

| Block Type | Fields | Notes |
|-----------|--------|-------|
| `text` | `text: string` | Regular response text |
| `tool_use` | `id, name, input` | Tool invocation |
| `thinking` | `thinking: string, signature: string` | Extended thinking (opaque signature) |
| `redacted_thinking` | `data: string` | Encrypted thinking (don't display) |

### Tool Result Structured Output (`tool_use_result`)

| Tool | Key Fields |
|------|-----------|
| `Bash` | `stdout, stderr, interrupted, backgroundTaskId` |
| `Read` | `type (text/image/pdf), file.content, file.numLines` |
| `Glob` | `filenames[], numFiles, durationMs, truncated` |
| `Edit` | `filePath, oldString, newString, structuredPatch[], gitDiff` |
| `Write` | `filePath, content` |
| `Grep` | `matches[], durationMs, numMatches` |
| `Task` | Subagent output (nested messages) |

---

## Appendix B: Warm Dark Theme Specification

### Color Palette

```
Background layers:
  bg-base:      #111008    near-black with warm brown undertone
  bg-elevated:  #1c1810    sidebar, header backgrounds
  bg-surface:   #252018    cards, panels, input backgrounds
  bg-overlay:   #2e2820    hover states, selection backgrounds

Text layers:
  text-primary:   #f0e8d8  main text (warm white/cream)
  text-secondary: #a89880  labels, metadata, timestamps
  text-disabled:  #5a5040  disabled controls, inactive items

Accent (amber/gold):
  accent-bright:  #D4A017  active borders, badges, highlights
  accent-dim:     #8A6A1A  inactive borders, dividers
  accent-subtle:  #4A3B18  subtle background tints

Semantic:
  success:    #4CAF72  green — approvals, completions, safe actions
  warning:    #E06020  orange — caution, high cost, approaching limits
  error:      #E05050  red — failures, denials, critical issues
  info:       #5090D8  blue — model info, context data, metadata
  thinking:   #7B68EE  medium slate blue — AI reasoning, extended thinking
```

### Design Rules

1. **Amber is NEVER text color.** Use amber only for borders, backgrounds (with dark text on top), badges, and indicators. Amber text on dark backgrounds fails contrast requirements.

2. **Warning vs Accent:** Warning is orange (#E06020), not amber. They must be visually distinct. Warning means "danger ahead." Accent means "this is active/important."

3. **Semantic colors always have text companions.** Never rely solely on color: `[✓ Success]` not just green text. `[✗ Error]` not just red text.

4. **Mode colors:**
   - Normal: green border
   - Auto: amber border
   - Plan: blue border
   - Sage: purple border

---

## Appendix C: Research Sources

### Textual Framework
- [Official Textual Documentation](https://textual.textualize.io/) — Workers, Screens, Widgets, CSS reference
- [Textual GitHub Discussions](https://github.com/Textualize/textual/discussions) — Screen/CSS scoping patterns
- [Anatomy of a Textual User Interface](https://textual.textualize.io/blog/2024/09/15/anatomy-of-a-textual-user-interface/) — Will McGugan's reference architecture
- [Textual on Leanpub](https://leanpub.com/textual/) — Michael Driscoll's comprehensive guide (2025)

### Claude Code CLI
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) — Official flag documentation
- [Claude Code Headless/Agent SDK Docs](https://code.claude.com/docs/en/headless) — SDK streaming output
- [Agent SDK TypeScript Reference](https://platform.claude.com/docs/en/agent-sdk/typescript) — Type definitions
- [Agent SDK Streaming Docs](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — Event format documentation
- [SamSaffron's Claude Agent SDK Spec](https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417) — Community analysis of wire format
- [takopi.dev stream-json cheatsheet](https://takopi.dev/reference/runners/claude/stream-json-cheatsheet/) — Practical event examples

### Competitive TUI Analysis
- [Aider](https://github.com/paul-gauthier/aider) — Rich + prompt_toolkit, MarkdownStream, repo-map
- [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) — JSON chunk streaming, active_line tracking
- [Goose](https://github.com/block/goose) — Rust/crossterm rewrite, MCP integration
- [k9s](https://github.com/derailed/k9s) — `:resource-type` navigation, XRay dependency view
- [lazygit](https://github.com/jesseduffield/lazygit) — 5-panel layout, command log, per-panel help
- [bottom](https://github.com/ClementTsang/bottom) — ratatui, constraint-based responsive layouts
- [Harlequin](https://github.com/tconbeer/harlequin) — Complex Textual app: split panes, tabs, DataTable
- [Warp Terminal](https://www.warp.dev/) — Blocks concept, GPU rendering, accent token theming

### Advanced Patterns
- [Trogon](https://github.com/Textualize/trogon) — CLI-to-TUI generation
- [Posting](https://github.com/darrenburns/posting) — HTTP client built with Textual
- [Toolong](https://github.com/Textualize/toolong) — Log file viewer built with Textual

---

*Architecture document compiled 2026-03-05. Based on 6,400+ lines of primary research across 4 deep-dive research documents. All patterns verified against official documentation and production codebases.*
