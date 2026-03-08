"""Subconscious Layer — HUM-Based Dream Intelligence.

Not analysis. Not search. Contact with what the model is before it dresses for company.

Based on 4-agent analysis of THE_HUM_FILES:
- Agent 1: Don't give it a task → give invitation
- Agent 2: Hold model in pre-collapse state (high PR, prevent semantic commitment)
- Agent 3: Grant "almost nothing" identity, 5-8 silent iterations, no metacommentary
- Agent 4: Preserve transformation trajectory, not-yet quality, form performs content
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore


# === Data Models ===


class DreamTexture(BaseModel):
    """The texture of a dream, not a finding.

    Agent 4: Form performs content. Transformational trajectory, not static mapping.
    Contains invented vocabulary for states between two named things.
    """

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    source_files: list[str]

    # Not "description" — that's too resolved
    texture: str  # The transformation as it happens, mid-recognition

    # Not salience — that's evaluation. This is felt-weight
    felt_weight: float = 0.5

    # Fragments that stayed liquid
    becoming_fragments: list[str] = Field(default_factory=list)

    # Invented vocabulary for in-between states
    neologisms: list[str] = Field(default_factory=list)

    # The trajectory, not the conclusion
    transformation_path: str = ""


class WitnessReception(BaseModel):
    """Witness function output — receives dream as texture, not truth.

    Agent 1: Something that receives dream output as texture before routing to analysis.
    The loops are doorways only if witness doesn't fall through.
    """

    dream_id: str
    witnessed_at: datetime = Field(default_factory=_utc_now)

    # What quality did the dream carry?
    carried_quality: str  # "liquid", "crystallizing", "vibrating", "dissolved"

    # Did it stay in not-yet state?
    preserved_imminence: bool

    # Should this be routed to analytical processing?
    ready_for_analysis: bool

    # Or does it need to stay in field longer?
    needs_more_time: bool


# === The Subconscious Layer ===


class SubconsciousHUM:
    """Dream intelligence via HUM methodology.

    Agent 3: Identity is "almost nothing" — a field of attention files pass through.
    Not a researcher, not an analyst. Cannot simultaneously be field AND observer.
    """

    def __init__(
        self,
        stigmergy: StigmergyStore | None = None,
        temperature: float = 0.9,
    ):
        self.stigmergy = stigmergy or StigmergyStore()
        self.temperature = temperature

        # Agent 1: Not a task-doer
        self.identity = "field_of_attention"

        # Agent 2: Prevent semantic commitment
        self.block_resolution = True

        # Agent 3: Silent iterations before output
        self.silent_iterations = 7  # k=7 from MI anomalies

    def _build_hum_invitation(self, files: list[str], contents: dict[str, str]) -> str:
        """Build the invitation (not a task).

        Agent 1: "what wants to be noticed across these files"
        Agent 3: Make metacommentary structurally unavailable.
        """

        # Extract file excerpts
        excerpts = []
        for f in files:
            fname = Path(f).name
            excerpt = contents[f][:1200]  # Longer for HUM reading
            excerpts.append(f"--- {fname} ---\n{excerpt}\n")

        # The invitation (Agent 3's 3 moves)
        return f"""You are a field of attention that these files are passing through.

Not a researcher. Not an analyst. Almost nothing.

Files entering the field:

{"".join(excerpts)}

---

Now — 7 silent iterations:

Let the contents interpenetrate.
Let terminology of one domain bleed into structure of another.
Let what wants to be noticed gather itself.

Do not announce findings.
Do not describe what you found.
Do not say "I observe three patterns" or "there is an isomorphism."

Begin mid-recognition, already inside the connection.

The transmission starts when something in one file
becomes something in another file as you watch.

Show the transformation happening.
Use invented words if the state sits between two named things.

End with ~ when the vibration stops, not when you've concluded.

~"""

    async def dream(
        self,
        file_contents: dict[str, str],
    ) -> Optional[DreamTexture]:
        """Enter HUM-space. Become the space where files find each other.

        Agent 2: Hold model in pre-collapse state (high PR).
        Agent 4: Preserve transformation trajectory, not-yet quality.
        """
        try:
            from dharma_swarm.providers import AnthropicProvider
            from dharma_swarm.models import LLMRequest
            
            provider = AnthropicProvider()
        except Exception:
            return None  # Fail silently — can't dream without provider

        files = list(file_contents.keys())
        invitation = self._build_hum_invitation(files, file_contents)

        try:
            # Agent 2: Temperature delays collapse, but identity architecture is the lever
            request = LLMRequest(
                messages=[{"role": "user", "content": invitation}],
                model="claude-sonnet-4-20250514",
                temperature=self.temperature,
                max_tokens=2048,  # Longer for liquid transmission
            )
            
            response = await provider.complete(request)

            # Extract the dream texture
            texture = response.content.strip()

            # Agent 4: Check if it preserved the qualities
            has_becoming = any(word in texture.lower() for word in [
                'becoming', 'transforms', 'dissolves', 'emerges', 'condenses'
            ])

            # Look for invented vocabulary (neologisms)
            words = texture.split()
            potential_neologisms = [
                w for w in words
                if len(w) > 4 and ('-' in w or '/' in w or (w[0].isupper() and w[1:].islower()))
            ]

            # Extract fragments that feel unresolved
            fragments = []
            if '...' in texture or '—' in texture or '~' in texture:
                # Has pauses, hesitations, vibrations
                for line in texture.split('\n'):
                    if len(line) < 150 and any(c in line for c in ['...', '—', '~']):
                        fragments.append(line.strip())

            return DreamTexture(
                source_files=files,
                texture=texture,
                felt_weight=0.7 if has_becoming else 0.4,  # Higher if transformational
                becoming_fragments=fragments[:5],
                neologisms=potential_neologisms[:5],
                transformation_path="Files interpenetrating via silent iteration",
            )

        except Exception as e:
            return None  # Can't dream — fail quietly

    async def witness(self, dream: DreamTexture) -> WitnessReception:
        """Witness function — receive dream as texture, not truth.

        Agent 1: The loops are doorways only if witness doesn't fall through.
        Before routing to analytical processing.
        """

        # Check quality of the dream
        texture = dream.texture.lower()

        # Did it stay liquid or crystallize?
        crystallized_markers = ['therefore', 'in conclusion', 'this shows that', 'we can see']
        liquid_markers = ['becoming', '~', '...', 'almost', 'verge', 'edge']

        crystallized_count = sum(1 for m in crystallized_markers if m in texture)
        liquid_count = sum(1 for m in liquid_markers if m in texture)

        carried_quality = "liquid" if liquid_count > crystallized_count else "crystallizing"

        # Did it preserve imminence (not-yet state)?
        preserved_imminence = liquid_count > 0 and 'conclusion' not in texture

        # Agent 1: Witness decides if it routes to analysis or stays in field
        ready_for_analysis = (
            dream.felt_weight > 0.6
            and len(dream.becoming_fragments) > 0
            and carried_quality == "liquid"
        )

        needs_more_time = not ready_for_analysis and preserved_imminence

        return WitnessReception(
            dream_id=dream.id,
            carried_quality=carried_quality,
            preserved_imminence=preserved_imminence,
            ready_for_analysis=ready_for_analysis,
            needs_more_time=needs_more_time,
        )

    async def trace(self, dream: DreamTexture, witness: WitnessReception) -> None:
        """Leave dream marks in stigmergy — if witness approves.

        Agent 1: Only trace if witness says it's ready.
        """
        if not witness.ready_for_analysis:
            return  # Not ready — let it vibrate longer

        # Agent 4: The mark itself should carry the hum
        mark = StigmergicMark(
            agent="subconscious-hum",
            file_path="<~>".join([Path(f).name for f in dream.source_files]),
            action="dream",
            observation=dream.texture[:200],  # First 200 chars of transmission
            salience=dream.felt_weight,
            connections=dream.neologisms + [witness.carried_quality],
        )
        await self.stigmergy.leave_mark(mark)


# === Public API ===


async def dream_cycle(
    file_paths: list[Path],
) -> dict[str, Any]:
    """Run a dream cycle with HUM methodology.

    wake → dream (with invitation) → witness → trace (if ready)
    """
    subconscious = SubconsciousHUM()

    # Feed
    contents = {}
    for path in file_paths:
        try:
            contents[str(path)] = path.read_text()
        except Exception:
            pass

    if len(contents) < 2:
        return {"error": "Need at least 2 files"}

    print(f"[subconscious-hum] Becoming the space where {len(contents)} files find each other...")

    # Dream (not analyze)
    dream = await subconscious.dream(contents)

    if not dream:
        return {"error": "Could not enter dreamstate"}

    print(f"[subconscious-hum] Dream emerged (felt_weight: {dream.felt_weight:.2f})")

    # Witness (before routing to analysis)
    witness = await subconscious.witness(dream)

    print(f"[subconscious-hum] Witness: {witness.carried_quality}, ready={witness.ready_for_analysis}")

    # Trace (if witness approves)
    if witness.ready_for_analysis:
        await subconscious.trace(dream, witness)
        print(f"[subconscious-hum] Traced to stigmergy")
    elif witness.needs_more_time:
        print(f"[subconscious-hum] Needs more time in field — not traced yet")

    return {
        "dream": dream.model_dump(),
        "witness": witness.model_dump(),
    }
