# DGC TUI Cleanup — Claude Code Quality

**Date**: 2026-03-23
**Status**: Design approved
**Priority**: BEAUTIFUL first. Fix broken fundamentals. Polish > features.

---

## Problem

The DGC TUI (9,365 lines, Textual 7.3.0) has three broken fundamentals:

1. **Double output**: Every message prints twice — text appears on consecutive lines verbatim
2. **No text selection**: Textual captures mouse globally, killing native terminal copy/paste/highlight
3. **Raw JSON exposed**: Tool calls display as `{"command": "...", "description": "..."}` in yellow bordered boxes instead of clean inline indicators

The user's standard is Claude Code: clean monospace output, spinner-style tool indicators, working text selection, zero visual noise.

---

## Design

### Priority 1: Kill Double Output

**What to fix**: Trace write path in `tui/app.py` → `tui/widgets/stream_output.py`. Find where the same text is written twice. Likely causes:
- Both `DGCApp` event handler AND `MainScreen` event handler writing to StreamOutput
- ProviderRunner emitting duplicate events (TextDelta fired twice)
- StreamOutput.write() being called from multiple code paths for the same content

**Approach**: Add a dedup guard — hash the last N writes, skip if duplicate within 100ms window. Also trace all callers of StreamOutput.write() and eliminate the architectural duplicate.

### Priority 2: Enable Text Selection

**What to fix**: Textual's default mouse capture prevents native terminal selection.

**Approach**: In `tui/theme/dharma_dark.py`, add CSS:
```css
StreamOutput {
    allow-select: true;
}
```

Also set `ALLOW_IN_MAXIMIZED_VIEW = True` on the StreamOutput widget class if needed. For the prompt input, keep mouse capture (cursor positioning needs it). This gives the user native selection on the output pane.

Fallback: honor `DGC_TUI_NO_MOUSE=1` env var to disable ALL mouse capture.

### Priority 3: Clean Tool Call Display

**Current**: Yellow bordered boxes showing raw JSON:
```
┌─── Tool: Bash ────────────────────────────────────
│ {"command": "python3 -m pytest...", "description": "Run tests"}
└─── ✓ Bash ────────────────────────────────────────
```

**Target**: Claude Code style inline indicators:
```
⠋ Running tests...
✓ 134 passed (2.3s)
```

**Approach**: Modify `tui/widgets/tool_call_card.py`:
- Extract `description` field from tool call JSON
- Display as single indented line with spinner while running
- Show ✓/✗ + summary on completion
- Hide the raw JSON entirely
- No borders, no "Tool: Bash" headers

### Priority 4: Visual Declutter

**Changes to `tui/theme/dharma_dark.py`**:
- Strip decorative borders from StreamOutput
- Mute color palette — use sumi grays + one accent color (aozora blue)
- Reduce status bar to single minimal line
- Remove or minimize footer chrome

**Changes to `tui/screens/splash.py`**:
- Reduce splash to <300ms or skip entirely
- No animation delay on startup

**Changes to `tui/widgets/status_bar.py`**:
- Single line: `mode | model | thread | time`
- No borders, no background panels
- Dim text, only highlights on active state changes

**Target aesthetic**: Dark background, monospace text, minimal chrome, muted colors. The content IS the interface. Like Claude Code but with dharma_swarm's intelligence.

### Priority 5 (Secondary): Organism Sidebar

Only after 1-4 are solid. Compact sidebar toggled via `Ctrl+G`:
- 20-char wide, right side
- Agent dots, trajectory count, balance
- Refreshes every 10s
- Can be fully hidden

---

## Files to Modify

| File | Change | Lines affected |
|------|--------|---------------|
| `tui/app.py` | Fix dual event routing, dedup writes | ~30 lines |
| `tui/widgets/stream_output.py` | Add dedup guard, enable selection | ~20 lines |
| `tui/widgets/tool_call_card.py` | Replace JSON boxes with inline spinners | ~60 lines rewrite |
| `tui/widgets/status_bar.py` | Simplify to single minimal line | ~40 lines |
| `tui/theme/dharma_dark.py` | allow-select, muted colors, strip borders | ~30 lines |
| `tui/screens/splash.py` | Speed up or skip | ~10 lines |
| `tui/screens/main.py` | Adjust layout for cleaner composition | ~15 lines |

**No new files for priorities 1-4.** All changes are in existing TUI code.

---

## Verification

```bash
# TUI launches cleanly
dgc

# No double output on any command
/status
/health
/stigmergy

# Text can be selected with mouse
# (highlight text in output pane, Cmd+C copies)

# Tool calls show clean spinners, not JSON
# (trigger a tool call via chat)

# Visual: dark, clean, minimal chrome
# (screenshot comparison with Claude Code)
```

---

## Success Criteria

1. Zero duplicated lines in output
2. Native text selection works in output pane
3. No raw JSON visible to operator
4. Tool calls display as inline `⠋ description...` → `✓ result`
5. Status bar is one clean line
6. Splash screen < 300ms
7. Overall aesthetic matches Claude Code quality bar
