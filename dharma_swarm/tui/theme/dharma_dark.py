"""DGC Hokusai theme — mineral pigment palette inspired by ukiyo-e woodblocks
and Kyoto nihonga (日本画) pigment shops.

Colours drawn from traditional Japanese mineral pigments:
  - Ai-iro (藍色): deep indigo-blue, Hokusai's Prussian blue
  - Bengara (弁柄): earthy red-ochre from iron oxide
  - Rokusho (緑青): verdigris green, copper patina on temple roofs
  - Sumi (墨): ink-wash greys, the backbone of suiboku-ga
  - Torinoko (鳥の子): aged washi paper cream
  - Fuji (藤): wisteria purple, late spring Kyoto
  - Kitsurubami (黄橡): persimmon tan, autumn warmth
  - Wasurenagusa (勿忘草): pale forget-me-not blue
  - Shironeri (白練): undyed silk white, clean reading surface

Built for Textual 8.x Theme API. Register with ``app.register_theme(DharmaDarkTheme)``
and activate with ``app.theme = "dharma-dark"``.
"""

from __future__ import annotations

from textual.theme import Theme

DharmaDarkTheme = Theme(
    name="dharma-dark",
    primary="#4A7B9D",       # Ai-iro — Hokusai's signature indigo
    secondary="#8A7263",     # Kitsune-iro — fox-brown, warm muted earth
    accent="#5D8C6E",        # Rokusho — verdigris green, temple patina
    warning="#C2956B",       # Kitsurubami — persimmon-tan
    error="#C25B52",         # Bengara — iron oxide red-ochre
    success="#5D8C6E",       # Rokusho — verdigris for harmony
    surface="#18171A",       # Sumi-iro — deep charcoal with cool undertone
    panel="#131215",         # Kuro-cha — blackened tea
    dark=True,
    variables={
        "bg-base": "#0E0D10",       # Ro-iro — lacquer black, true dark
        "bg-elevated": "#18171A",   # Sumi-iro — ink wash
        "bg-surface": "#1F1E22",    # Hai-iro — ash grey surface
        "bg-overlay": "#272630",    # Nezumi — mouse grey with indigo tint
        "text-primary": "#DCD5C4",  # Torinoko — aged washi cream
        "text-secondary": "#9B928A", # Usuzumi — dilute ink
        "text-disabled": "#5A5560", # Nibi-iro — dull grey-purple
        "accent-bright": "#6B9BB5", # Hanada — washed indigo, brighter
        "accent-dim": "#4A7B9D",    # Ai-iro — Hokusai blue
        "accent-subtle": "#2D3D4F", # Kachi — dark victory indigo
        "thinking": "#9B85B8",      # Fuji-iro — wisteria purple
        "info": "#6B9BB5",          # Hanada — washed indigo
    },
)
