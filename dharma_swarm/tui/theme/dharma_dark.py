"""DGC Hokusai theme — mineral pigment palette inspired by ukiyo-e woodblocks
and Kyoto nihonga (日本画) pigment shops.

Colours drawn from traditional Japanese mineral pigments:
  - Ai-iro (藍色): deep indigo-blue, Hokusai's Prussian blue
  - Bengara (弁柄): earthy red-ochre from iron oxide
  - Uguisu (鶯): muted olive-celadon
  - Sumi (墨): ink-wash greys
  - Torinoko (鳥の子): aged paper cream
  - Wasurenagusa (勿忘草): pale forget-me-not blue

Built for Textual 8.x Theme API. Register with ``app.register_theme(DharmaDarkTheme)``
and activate with ``app.theme = "dharma-dark"``.
"""

from __future__ import annotations

from textual.theme import Theme

DharmaDarkTheme = Theme(
    name="dharma-dark",
    primary="#5B7F95",       # Ai-nezu — faded indigo-grey (Hokusai wave crest)
    secondary="#8A7263",     # Kitsune-iro — fox brown, warm muted earth
    accent="#6E8B74",        # Rokusho — verdigris green (copper patina)
    warning="#C2956B",       # Kitsurubami — persimmon-tan, gentle warmth
    error="#B5564E",         # Bengara — iron oxide red-ochre, not neon
    success="#6E8B74",       # Rokusho — same verdigris for harmony
    surface="#1C1B1A",       # Sumi-iro — deep charcoal ink
    panel="#161614",         # Kuro-cha — blackened tea
    dark=True,
    variables={
        "bg-base": "#121110",       # Ro-iro — lacquer black with warm undertone
        "bg-elevated": "#1C1B1A",   # Sumi-iro — ink wash
        "bg-surface": "#232220",    # Hai-iro — ash grey surface
        "bg-overlay": "#2A2927",    # Nezumi — mouse grey
        "text-primary": "#D8D2C4",  # Torinoko — aged paper cream
        "text-secondary": "#9B9284",  # Usuzumi — dilute ink
        "text-disabled": "#5C5650", # Nibi-iro — dull grey
        "accent-bright": "#7B9DAD", # Hanada — washed indigo
        "accent-dim": "#5B7F95",    # Ai-nezu — faded indigo
        "accent-subtle": "#3A4F5A", # Kachi — dark victory indigo
        "thinking": "#8B7BA8",      # Fuji-iro — wisteria purple, soft
        "info": "#7B9DAD",          # Hanada — washed indigo
    },
)
