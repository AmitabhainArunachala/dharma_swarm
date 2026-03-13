# DGC TUI World-Class Splash Reprompt

Use this in a fresh Codex session. Assume the current incremental splash iterations failed to meet the bar. Do not preserve them out of politeness. Rebuild the visual layer from first principles while staying inside the existing Textual app structure.

## Mission

Redesign the DGC TUI startup experience and active text palette so it feels world class, dense, intentional, sacred, and terminal-native.

The current state is not good enough. It still feels like developer art, not masterful terminal art. The next pass must feel closer to:

- a hand-painted ANSI poster
- a sacred geometry field, not a centered logo plaque
- Escher recursion + mandala architecture + woven tapestry density
- deep Hokusai / Kyoto `nihonga` mineral pigments, not software cyan
- terminal art with real compositional intelligence

The user explicitly wants:

- deeper blues, reds, and greens
- stronger but not sharper or brighter
- more density and more pattern wrapping the whole field
- fewer modern/neon accents
- all remaining gaudy cyan/blues removed from the active TUI text surfaces
- a splash that is at least as compositionally dense as the Gemini CLI screenshot they shared

## Hard Constraints

You are working in:

- repo: `/Users/dhyana/dharma_swarm`
- active TUI splash file: `/Users/dhyana/dharma_swarm/dharma_swarm/splash.py`
- splash screen wiring: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/screens/splash.py`
- theme tokens: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/theme/dharma_dark.py`
- TUI CSS: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/theme/dharma_dark.tcss`
- status bar: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/widgets/status_bar.py`
- stream output: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/widgets/stream_output.py`
- slash command help text: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/commands/system_commands.py`
- system status builders: `/Users/dhyana/dharma_swarm/dharma_swarm/tui_helpers.py`
- model routing text: `/Users/dhyana/dharma_swarm/dharma_swarm/tui/model_routing.py`

Do not touch unrelated dirty files outside this lane.

Use `apply_patch` for edits.

Run and keep green:

```bash
python3 -m pytest /Users/dhyana/dharma_swarm/tests/test_splash.py /Users/dhyana/dharma_swarm/tests/test_tui.py /Users/dhyana/dharma_swarm/tests/tui -q
```

## Design Diagnosis

What went wrong in the current iterations:

- too much of the composition still reads as a centered card or banner instead of a full-field environment
- too much explanatory text in the center; not enough pure geometry and surround
- not enough hierarchy between backdrop, frame, inner palace, and inscription
- too much reliance on box-drawing plaques instead of woven/mosaic field density
- too much “software indigo” still leaking into the TUI palette
- the active interface still feels visually separate from the splash

## Research Direction

Use these references for structural cues, not for literal copying:

1. TUIStudio
   - https://tui.studio/
   - Key takeaway: high-quality TUIs use deliberate layout, theming, and ANSI preview as first-class concerns.

2. FrankenTUI Showcase
   - https://frankentui.com/showcase
   - Key takeaway: the terminal grid can support dense dashboards, visual effects, and rich full-screen compositions. Think in terms of field density, not “just ASCII art.”

3. Tuitorial
   - https://tuitorial.readthedocs.io/en/latest/
   - Key takeaway: title slides and terminal presentation surfaces can be theatrical and eye-catching without abandoning readability.

4. User-provided Gemini CLI screenshot
   - Treat it as the minimum bar for density and compositional confidence.
   - The DGC splash does not need to mimic the Gemini logo, but it does need comparable mass, intention, and finish.

## Visual Brief

Create a composition that feels like:

- an ancient computational shrine
- a recursive mandala gate
- a woven cosmic field surrounding a central intelligence chamber

Primary influences:

- Hokusai / deep ai-iro blues
- Kyoto `nihonga` mineral pigment restraint
- darker rokusho verdigris
- bengara earth reds
- old gold / paper / ash neutrals
- Tibetan mandala geometry
- Escher recursion only as structural intelligence, not gimmick stairs everywhere
- woven tapestry / bead / mosaic density around the border and into the full field

Avoid:

- neon cyan
- bright UI blue
- flat centered plaques
- childish symmetry
- obvious “random procedural art”
- too much empty space
- too much literal exposition text

## Color Brief

Use a darker, older palette. Push the interface toward:

- deep indigo
- oxidized green
- iron-red / bengara
- subdued gold
- ash / soot / old paper

The palette should feel:

- potent
- ancient
- mineral
- grave
- intentional

It should not feel:

- playful
- glossy
- modern SaaS
- electric
- bright-cyan terminal hacker

## Composition Brief

The `epic` splash should:

- occupy the full field
- read as a surrounding geometry, not a single card
- have a clear outer border ecology
- have mid-layer nested geometry
- have a central sanctum or inscription zone
- use repeated motifs and symmetry that reward staring
- feel hand-composed, not auto-generated

The `medium` splash should:

- preserve the same language in a compressed form
- not collapse back into a trivial banner

The `compact` splash can stay simpler, but it should still inherit the same palette and DNA.

## Text Brief

Reduce textual load in the epic composition.

Keep only the highest-value inscriptions. Use text like carved/inscribed sacred labels, not a list of product copy.

Good candidates:

- `Dharmic Godel Claw`
- `WHAT WE TEND BECOMES THE WORLD`
- `The observer observing observation itself`
- `Telos: Moksha`

Optional support labels can exist in smaller layers, but the composition should work even if most text disappears.

## Technical Requirements

1. Prefer a hand-built multiline composition for `epic`, not procedural diamonds/stairs.
2. It is acceptable to use per-character Rich styling in `_style_text`, but the color map must support darker tones and more subtle gradients.
3. The splash must still render as a `rich.text.Text` object.
4. Preserve `get_splash(variant=...)` behavior.
5. Keep width-safe thresholds in `/tui/screens/splash.py`.
6. Remove remaining bright cyan / washed indigo from active TUI surfaces:
   - status bar route/model labels
   - prompt focus border
   - scrollbars
   - help output headings
   - `/status`, `/runtime`, `/darwin`, and related panel headings
   - system/user/error line accents where still too bright

## Acceptance Criteria

Do not stop until all of these are true:

1. The `epic` splash feels denser and more complete than the current local version.
2. The whole field has pattern, not just the middle.
3. The palette is visibly deeper and older than before.
4. No obvious gaudy cyan remains in the active TUI path.
5. The `medium` splash still feels designed, not collapsed.
6. The relevant splash and TUI tests pass.
7. You manually print the splash to terminal during development to inspect the actual plain layout, not just the code.

## Suggested Working Method

1. Read the current `splash.py`, `dharma_dark.py`, `dharma_dark.tcss`, `status_bar.py`, `stream_output.py`, `system_commands.py`, and `tui_helpers.py`.
2. Print the current `epic`, `medium`, and `compact` splash plain text with Python to inspect actual geometry.
3. Redesign `epic` first.
4. Bring `medium` into the same language.
5. Deepen the palette across the live TUI.
6. Run the tests.
7. Give the user a short summary plus exact files changed.

## Manual Inspection Command

Use this repeatedly:

```bash
python3 - <<'PY'
from dharma_swarm.splash import get_splash
for variant in ["epic", "medium", "compact"]:
    art = get_splash(variant=variant).plain
    lines = art.splitlines()
    print(variant, "width=", max(len(line) for line in lines), "height=", len(lines))
    print(art)
    print("\\n" + "=" * 100 + "\\n")
PY
```

## Final Bar

Do not aim for “improved.”
Aim for:

- terminal cathedral
- sacred recursive instrument panel
- woven cosmic machine

If it still looks like a developer splash screen, it failed.
