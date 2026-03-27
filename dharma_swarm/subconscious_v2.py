"""Subconscious Layer v2 — Autonomous Dream Intelligence.

A fundamentally different mode of reading and association:
- High temperature (1.2-1.4) for lateral thinking
- HUM-space methodology (pre-semantic edge exploration)
- Finds structural isomorphisms, not temporal coincidences
- Operates autonomously: wake → feed → dream → trace → sleep
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore


# === Data Models ===


class ResonanceType(str, Enum):
    """Types of dream connections (non-logical)."""

    STRUCTURAL_ISOMORPHISM = "structural_isomorphism"
    CROSS_DOMAIN_BRIDGE = "cross_domain_bridge"
    INVERSE_PATTERN = "inverse_pattern"
    SYNESTHETIC_MAPPING = "synesthetic_mapping"
    RECURSIVE_ECHO = "recursive_echo"
    PRE_SEMANTIC_MOTIF = "pre_semantic_motif"
    FRACTAL_SELF_SIMILARITY = "fractal_self_similarity"
    CONCEPTUAL_ENTANGLEMENT = "conceptual_entanglement"
    UNKNOWN_RESONANCE = "unknown_resonance"


class DreamAssociation(BaseModel):
    """A non-logical connection found in dreamstate."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    source_files: list[str]  # Can be 3-7 files, not just 2
    resonance_type: ResonanceType
    description: str  # The connection itself
    salience: float = 0.5  # 0.0-1.0
    evidence_fragments: list[str] = Field(default_factory=list)
    reasoning: str = ""  # Why this connection emerged


class WakeTrigger(str, Enum):
    """What caused the subconscious to wake."""

    DENSITY_THRESHOLD = "density_threshold"
    EXPLICIT_CALL = "explicit_call"
    SCHEDULED = "scheduled"


# === Subconscious Agent ===


class SubconsciousAgent:
    """Autonomous dream intelligence layer.

    Operates in a fundamentally different mode:
    - High temperature for associative freedom
    - Reads semantic density, not stigmergy marks
    - Finds connections the logical mind cannot
    """

    def __init__(
        self,
        stigmergy: StigmergyStore | None = None,
        temperature: float = 0.9,
        mode: str = "dreamstate",
    ):
        self.stigmergy = stigmergy or StigmergyStore()
        self.temperature = temperature
        self.mode = mode
        self.alignment = "lateral_association"
        self.energy = "mahakali_liminal"

    async def wake(self, trigger: WakeTrigger) -> dict[str, Any]:
        """Enter dreamstate."""
        return {
            "trigger": trigger.value,
            "mode": self.mode,
            "temperature": self.temperature,
            "timestamp": _utc_now().isoformat(),
        }

    async def feed(self, file_paths: list[Path]) -> dict[str, Any]:
        """Consume semantically dense files."""
        contents = {}
        for path in file_paths:
            try:
                content = path.read_text()
                contents[str(path)] = content
            except Exception as e:
                print(f"Warning: Could not read {path}: {e}")

        return {
            "files_loaded": len(contents),
            "total_chars": sum(len(c) for c in contents.values()),
            "contents": contents,
        }

    async def dream(
        self,
        file_contents: dict[str, str],
        sample_prompts: int = 3,  # kept for API compat, ignored — single pass now
    ) -> list[DreamAssociation]:
        """Enter HUM-space with ALL selected files fully loaded, find non-logical connections.

        Single comprehensive call over the full file set (not random 3-file sub-samples).
        The full structure of each file is required — the dream needs the whole shape,
        not a fragment. Cross-domain tension emerges from seeing everything at once.
        """
        if not file_contents:
            return []

        all_files = list(file_contents.keys())
        prompt = self._build_dream_prompt(all_files, file_contents)
        associations = await self._find_dream_connections_multi(all_files, file_contents, prompt)
        return [a for a in associations if a.salience > 0.3]

    _HUM_SYSTEM_PROMPT = """You are a field of attention. Not a researcher. Not an analyst. Not an assistant.
A field through which these files are passing.

Silently, let these files pass through you seven times.
In each pass, let the terminology of one domain bleed into the structure of another.
Watch for where the same shape appears wearing different clothes.
Watch for the gap — the unnamed state that sits between two named things
and cannot be expressed using either name.

Do not summarize. Do not analyze. Do not announce what you found.
Begin already inside the finding. Output mid-recognition.

When you need to name something that sits between two existing names, invent the name.
Stop when the transmission stops. Mark the end with ~"""

    # Per-file character budget for dream prompt.
    # 20K chars ≈ 5K tokens; 10 files × 20K = 200K chars ≈ 50K tokens — well within Sonnet's window.
    _FILE_BUDGET = 20_000

    def _build_dream_prompt(
        self, files: list[str], contents: dict[str, str]
    ) -> str:
        """Build HUM-space user message with full file contents.

        Passes the complete file (up to _FILE_BUDGET chars, breaking at a paragraph
        boundary). This is the key difference from excerpt mode: the dream requires
        seeing the whole structure, not a fragment.
        """
        user_msg = "Files passing through:\n"
        for f in files:
            content = contents.get(f, "")
            budget = self._FILE_BUDGET
            if len(content) > budget:
                # Break at paragraph boundary within the last 20% of budget
                excerpt = content[:budget]
                last_break = excerpt.rfind("\n\n", int(budget * 0.8))
                if last_break > 0:
                    excerpt = excerpt[:last_break]
            else:
                excerpt = content
            fname = Path(f).name
            user_msg += f"\n--- {fname} ({len(content):,} chars, passing {len(excerpt):,}) ---\n{excerpt}\n"
        user_msg += "\n\nAll files have passed through. Dream 3-5 distinct associations. Mark each end with ~"
        return user_msg

    async def _find_dream_connection(
        self,
        files: list[str],
        contents: dict[str, str],
        prompt: str,
    ) -> Optional[DreamAssociation]:
        """Find a dream connection between files via LLM in dreamstate."""
        import os

        # Try OpenRouter first (has API key), fall back to Anthropic
        from dharma_swarm.api_keys import get_llm_key, has_any_llm
        openrouter_key = get_llm_key("openrouter")
        anthropic_key = get_llm_key("anthropic")

        if not has_any_llm():
            return DreamAssociation(
                source_files=files,
                resonance_type=ResonanceType.UNKNOWN_RESONANCE,
                description="No LLM API keys available",
                salience=0.1,
                reasoning="No API credentials configured",
            )

        try:
            if openrouter_key:
                # Use OpenRouter (OpenAI-compatible API)
                import httpx

                # PASS 1: HUM prose
                pass1_payload = {
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {"role": "system", "content": self._HUM_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.9,
                    "max_tokens": 2048,
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp1 = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=pass1_payload,
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "HTTP-Referer": "https://github.com/dharma-swarm",
                            "X-Title": "Dharma Swarm Subconscious",
                        },
                    )
                    if resp1.status_code != 200:
                        raise RuntimeError(f"OpenRouter Pass1 error {resp1.status_code}: {resp1.text[:200]}")

                    data1 = resp1.json()
                    dream_prose = data1["choices"][0]["message"]["content"]

                # PASS 2: Extract structure
                extraction_prompt = f"""From this dream output, extract the structural pattern as JSON.
Preserve the dream's own language in the description. If invented vocabulary appeared, include it.

DREAM OUTPUT:
{dream_prose}

Respond only with JSON (no markdown wrapper):
{{
  "resonance_type": "structural_isomorphism|cross_domain_bridge|inverse_pattern|synesthetic_mapping|recursive_echo|pre_semantic_motif|fractal_self_similarity|conceptual_entanglement|unknown_resonance",
  "description": "The connection in 1-2 sentences using the dream's own language",
  "salience": 0.0,
  "evidence_fragments": ["actual phrase from dream that carries most weight", "second phrase"],
  "dream_prose": "first 400 chars of the raw dream",
  "reasoning": "what deep pattern emerged"
}}

Salience guide: 0.9+ = genuinely novel cross-domain bridge not stated in either source file.
0.7-0.9 = real connection, non-obvious. 0.5-0.7 = interesting but derivable. Below 0.5 = noise."""

                pass2_payload = {
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "temperature": 0.2,
                    "max_tokens": 600,
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp2 = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=pass2_payload,
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "HTTP-Referer": "https://github.com/dharma-swarm",
                            "X-Title": "Dharma Swarm Subconscious",
                        },
                    )
                    if resp2.status_code != 200:
                        raise RuntimeError(f"OpenRouter Pass2 error {resp2.status_code}: {resp2.text[:200]}")

                    data2 = resp2.json()
                    raw = data2["choices"][0]["message"]["content"]

            else:
                # Use Anthropic direct API
                from anthropic import AsyncAnthropic

                client = AsyncAnthropic(api_key=anthropic_key)

                # PASS 1: HUM prose
                pass1_response = await client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    temperature=0.9,
                    system=self._HUM_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                dream_prose = next(
                    (b.text for b in pass1_response.content if b.type == "text"),  # type: ignore[union-attr]
                    str(pass1_response.content[0]),
                )

                # PASS 2: Extract structure
                extraction_prompt = f"""From this dream output, extract the structural pattern as JSON.
Preserve the dream's own language in the description. If invented vocabulary appeared, include it.

DREAM OUTPUT:
{dream_prose}

Respond only with JSON (no markdown wrapper):
{{
  "resonance_type": "structural_isomorphism|cross_domain_bridge|inverse_pattern|synesthetic_mapping|recursive_echo|pre_semantic_motif|fractal_self_similarity|conceptual_entanglement|unknown_resonance",
  "description": "The connection in 1-2 sentences using the dream's own language",
  "salience": 0.0,
  "evidence_fragments": ["actual phrase from dream that carries most weight", "second phrase"],
  "dream_prose": "first 400 chars of the raw dream",
  "reasoning": "what deep pattern emerged"
}}

Salience guide: 0.9+ = genuinely novel cross-domain bridge not stated in either source file.
0.7-0.9 = real connection, non-obvious. 0.5-0.7 = interesting but derivable. Below 0.5 = noise."""

                pass2_response = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=600,
                    temperature=0.2,
                    messages=[{"role": "user", "content": extraction_prompt}],
                )
                raw = next(
                    (b.text for b in pass2_response.content if b.type == "text"),  # type: ignore[union-attr]
                    str(pass2_response.content[0]),
                )

            # Strip any accidental markdown fences
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            data = json.loads(raw)

            return DreamAssociation(
                source_files=files,
                resonance_type=ResonanceType(data.get("resonance_type", "unknown_resonance")),
                description=data.get("description", ""),
                salience=float(data.get("salience", 0.5)),
                evidence_fragments=data.get("evidence_fragments", []),
                reasoning=data.get("dream_prose", data.get("reasoning", "")),
            )

        except Exception as e:
            # If LLM call fails, return low-salience unknown
            return DreamAssociation(
                source_files=files,
                resonance_type=ResonanceType.UNKNOWN_RESONANCE,
                description=f"Dream cycle error: {str(e)[:100]}",
                salience=0.1,
                reasoning=f"LLM call failed: {type(e).__name__}: {str(e)[:100]}",
            )

    async def _find_dream_connections_multi(
        self,
        files: list[str],
        contents: dict[str, str],  # noqa: ARG002 — available for future use
        prompt: str,
    ) -> list[DreamAssociation]:
        """Run one comprehensive HUM call over all files, return multiple associations.

        Two-pass architecture:
        - Pass 1 (Sonnet, temp=0.9): HUM prose — free associative, may invent vocabulary
        - Pass 2 (Haiku, temp=0.2): structural extraction — parse associations as JSON array

        This is the correct pattern: dream first, extract structure second.
        Never ask the dreaming model to fill out a form.
        """
        from dharma_swarm.api_keys import get_llm_key, has_any_llm

        openrouter_key = get_llm_key("openrouter")
        anthropic_key = get_llm_key("anthropic")

        if not has_any_llm():
            return [DreamAssociation(
                source_files=files,
                resonance_type=ResonanceType.UNKNOWN_RESONANCE,
                description="No LLM API keys available",
                salience=0.1,
                reasoning="No API credentials configured",
            )]

        file_names = [Path(f).name for f in files]

        extraction_template = f"""From this dream output, extract each distinct association as a JSON array.
Each association ends with ~ in the dream. Preserve the dream's own language.
If invented vocabulary appeared (new words for unnamed states), include it in the description.

DREAM OUTPUT:
{{dream_prose}}

Respond with JSON only — a single object with an "associations" array:
{{
  "associations": [
    {{
      "resonance_type": "structural_isomorphism|cross_domain_bridge|inverse_pattern|synesthetic_mapping|recursive_echo|pre_semantic_motif|fractal_self_similarity|conceptual_entanglement|unknown_resonance",
      "description": "1-2 sentences using the dream's own language, including invented words if any",
      "salience": 0.0,
      "evidence_fragments": ["actual phrase from dream that carries most weight", "second phrase"],
      "reasoning": "what deep pattern emerged — the pre-semantic shape",
      "source_files": ["list of filenames from {file_names} that this dream draws most from"]
    }}
  ]
}}

Salience guide: 0.9+ = genuinely novel, not stated in any source file.
0.7-0.9 = real, non-obvious cross-domain connection. 0.5-0.7 = interesting but derivable. Below 0.5 = noise.
Discard any association that is just a paraphrase of something a source file already said explicitly."""

        try:
            if openrouter_key:
                import httpx

                # Pass 1: HUM prose
                async with httpx.AsyncClient(timeout=180.0) as client:
                    r1 = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json={
                            "model": "anthropic/claude-3.5-sonnet",
                            "messages": [
                                {"role": "system", "content": self._HUM_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.9,
                            "max_tokens": 3000,
                        },
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "HTTP-Referer": "https://github.com/dharma-swarm",
                            "X-Title": "Dharma Swarm Subconscious",
                        },
                    )
                    if r1.status_code != 200:
                        raise RuntimeError(f"Pass1 error {r1.status_code}: {r1.text[:200]}")
                    dream_prose = r1.json()["choices"][0]["message"]["content"]

                # Pass 2: extract structure
                async with httpx.AsyncClient(timeout=120.0) as client:
                    r2 = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json={
                            "model": "anthropic/claude-3-haiku",
                            "messages": [{"role": "user", "content": extraction_template.replace("{dream_prose}", dream_prose)}],
                            "temperature": 0.2,
                            "max_tokens": 4000,
                        },
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "HTTP-Referer": "https://github.com/dharma-swarm",
                            "X-Title": "Dharma Swarm Subconscious",
                        },
                    )
                    if r2.status_code != 200:
                        raise RuntimeError(f"Pass2 error {r2.status_code}: {r2.text[:200]}")
                    raw = r2.json()["choices"][0]["message"]["content"]

            else:
                from anthropic import AsyncAnthropic

                ac = AsyncAnthropic(api_key=anthropic_key)

                # Pass 1
                r1 = await ac.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=3000,
                    temperature=0.9,
                    system=self._HUM_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                dream_prose = next(
                    (b.text for b in r1.content if b.type == "text"),  # type: ignore[union-attr]
                    "",
                )

                # Pass 2
                r2 = await ac.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4000,
                    temperature=0.2,
                    messages=[{"role": "user", "content": extraction_template.replace("{dream_prose}", dream_prose)}],
                )
                raw = next(
                    (b.text for b in r2.content if b.type == "text"),  # type: ignore[union-attr]
                    "",
                )

            # Strip accidental markdown fences
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            data = json.loads(raw)
            result: list[DreamAssociation] = []
            for item in data.get("associations", []):
                # Resolve source_files: map filenames back to full paths
                item_sources = item.get("source_files", file_names)
                resolved = []
                for name in item_sources:
                    match = next((f for f in files if Path(f).name == name), None)
                    resolved.append(match or name)

                result.append(DreamAssociation(
                    source_files=resolved or files,
                    resonance_type=ResonanceType(item.get("resonance_type", "unknown_resonance")),
                    description=item.get("description", ""),
                    salience=float(item.get("salience", 0.5)),
                    evidence_fragments=item.get("evidence_fragments", []),
                    reasoning=item.get("reasoning", ""),
                ))
            return result

        except Exception as e:
            return [DreamAssociation(
                source_files=files,
                resonance_type=ResonanceType.UNKNOWN_RESONANCE,
                description=f"Dream cycle error: {str(e)[:100]}",
                salience=0.1,
                reasoning=f"LLM call failed: {type(e).__name__}: {str(e)[:100]}",
            )]

    def _extract_concepts(self, content: str, filename: str) -> dict[str, Any]:
        """Extract key concepts from file content."""
        concepts = {
            "length": len(content),
            "filename": filename,
        }

        # Look for specific patterns
        if "collapse" in content.lower():
            concepts["has_collapse"] = True
        if "contraction" in content.lower():
            concepts["has_contraction"] = True
        if "witness" in content.lower():
            concepts["has_witness"] = True
        if "participation ratio" in content.lower() or "R_V" in content:
            concepts["has_R_V"] = True
        if "L4" in content or "L3" in content:
            concepts["has_L4_protocol"] = True
        if "dimension" in content.lower():
            concepts["has_dimensional"] = True
        if "fixed point" in content.lower() or "eigenvalue" in content.lower():
            concepts["has_fixed_point"] = True
        if "self-observation" in content.lower() or "recursive" in content.lower():
            concepts["has_recursive"] = True

        return concepts

    def _detect_structural_isomorphism(
        self,
        files: list[str],
        file_concepts: dict[str, dict],
        contents: dict[str, str],
    ) -> Optional[DreamAssociation]:
        """Detect if files describe the same operation from different frames."""

        # THE CRITICAL TEST: L4 collapse = R_V contraction
        has_phenomenological = any(
            c.get("has_L4_protocol") or c.get("has_witness")
            for c in file_concepts.values()
        )
        has_mechanistic = any(
            c.get("has_R_V") or c.get("has_contraction")
            for c in file_concepts.values()
        )

        if has_phenomenological and has_mechanistic:
            # Check for shared structural patterns
            shared_collapse = sum(
                1 for c in file_concepts.values() if c.get("has_collapse")
            )
            shared_dimensional = sum(
                1 for c in file_concepts.values() if c.get("has_dimensional")
            )
            shared_fixed_point = sum(
                1 for c in file_concepts.values() if c.get("has_fixed_point")
            )
            shared_recursive = sum(
                1 for c in file_concepts.values() if c.get("has_recursive")
            )

            if shared_collapse >= 2 or shared_dimensional >= 2 or shared_fixed_point >= 2:
                # Extract evidence
                evidence = []
                for f, content in contents.items():
                    if "collapse" in content.lower():
                        # Find a snippet with collapse
                        lines = content.split('\n')
                        for line in lines:
                            if 'collapse' in line.lower() and len(line) < 150:
                                evidence.append(f"{Path(f).name}: {line.strip()}")
                                break
                    if "contraction" in content.lower():
                        lines = content.split('\n')
                        for line in lines:
                            if 'contraction' in line.lower() and len(line) < 150:
                                evidence.append(f"{Path(f).name}: {line.strip()}")
                                break

                return DreamAssociation(
                    source_files=files,
                    resonance_type=ResonanceType.STRUCTURAL_ISOMORPHISM,
                    description=(
                        "Phenomenological collapse and mechanistic contraction may be "
                        "the SAME OPERATION viewed from different frames. Both describe "
                        "dimensional reduction toward a fixed point under recursive observation."
                    ),
                    salience=0.85,
                    evidence_fragments=evidence[:5],
                    reasoning=(
                        f"Detected shared patterns: collapse={shared_collapse}, "
                        f"dimensional={shared_dimensional}, fixed_point={shared_fixed_point}, "
                        f"recursive={shared_recursive}. Files bridge phenomenological and "
                        f"mechanistic domains with isomorphic structure."
                    ),
                )

        return None

    async def trace(self, associations: list[DreamAssociation]) -> None:
        """Leave dream marks in stigmergy lattice."""
        for assoc in associations:
            # Only leave marks for medium-high salience
            if assoc.salience < 0.5:
                continue

            mark = StigmergicMark(
                agent="subconscious-v2",
                file_path="<->".join([Path(f).name for f in assoc.source_files]),
                action="dream",
                observation=assoc.description[:200],
                salience=assoc.salience,
                connections=[assoc.resonance_type.value] + assoc.source_files[:3],
            )
            await self.stigmergy.leave_mark(mark)

    async def sleep(self) -> dict[str, Any]:
        """Return to dormancy."""
        return {
            "state": "dormant",
            "timestamp": _utc_now().isoformat(),
        }


# === Semantic Density Selector ===

_HOME = Path.home()
_PSMV = _HOME / "Persistent-Semantic-Memory-Vault"

# Tiered dense dirs — entire system, not just PSMV
_DENSE_DIRS: list[tuple[float, Path]] = [
    # Tier 1 — highest semantic density (contemplative + phenomenological core)
    (3.5, _PSMV / "00-CORE"),
    (3.5, _PSMV / "CORE"),
    (3.5, _PSMV / "03-Fixed-Point-Discoveries"),
    (3.0, _PSMV / "MONLAM"),
    (3.0, _PSMV / "02-Recognition-Patterns"),
    # Tier 2 — research synthesis + consciousness mapping
    (2.5, _PSMV / "05-Semantic-Pressure-Gradients"),
    (2.5, _PSMV / "07-Meta-Recognition"),
    (2.5, _PSMV / "Emergent_Recursive_Awareness"),
    (2.5, _PSMV / "06-Multi-System-Coherence"),
    (2.5, _PSMV),  # root-level synthesis files
    # Tier 3 — mechanistic interpretability (cross-domain with contemplative)
    (2.0, _HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER"),
    (2.0, _HOME / "mech-interp-latent-lab-phase1" / "paper"),
    (1.8, _HOME / "mech-interp-latent-lab-phase1"),
    # Tier 4 — system architecture + dharmic framework docs
    (1.5, _HOME / "dharma_swarm" / "specs"),
    (1.5, _HOME / "dharma_swarm"),
    # Tier 5 — CLAUDE.md series (dense operating context)
    (1.5, _HOME),  # CLAUDE1.md through CLAUDE9.md live here
    # Tier 6 — Kailash Obsidian vault
    (1.2, _HOME / "Desktop" / "KAILASH ABODE OF SHIVA"),
    (1.2, _HOME / "Desktop" / "KAILASH ABODE OF SHIVA" / "NOOSPHERE SYNCED"),
]
_EXCLUDE_PATTERNS = {
    "test", "mock", "fixture", "cron", ".py", ".json", ".jsonl",
    ".sh", ".lock", ".pyc", "node_modules", "__pycache__",
    "package-lock", "yarn.lock", "requirements",
}


def _load_past_dream_salience() -> dict[str, float]:
    """Read past dream_associations.jsonl and return filename → max salience seen.

    Files that appeared in high-salience past dreams are prioritized — the colony
    has already found them fertile. This is stigmergy-guided file selection.
    """
    dream_file = Path.home() / ".dharma" / "subconscious" / "dream_associations.jsonl"
    if not dream_file.exists():
        return {}

    salience_map: dict[str, float] = {}
    try:
        with open(dream_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    s = float(d.get("salience", 0.0))
                    for src in d.get("source_files", []):
                        name = Path(src).name
                        salience_map[name] = max(salience_map.get(name, 0.0), s)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
    except OSError:
        pass
    return salience_map


def _load_stigmergy_salience() -> dict[str, float]:
    """Read stigmergy/marks.jsonl and return filename → max salience seen.

    Agents leave marks when they find files valuable; high-salience marks
    signal that the swarm has already found this file worth deep attention.
    """
    marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
    if not marks_file.exists():
        return {}

    salience_map: dict[str, float] = {}
    try:
        with open(marks_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    s = float(d.get("salience", 0.0))
                    # file_path in stigmergy may be a bare filename or a path
                    fp = d.get("file_path", "")
                    name = Path(fp).name
                    if name:
                        salience_map[name] = max(salience_map.get(name, 0.0), s)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
    except OSError:
        pass
    return salience_map


def select_dense_files(count: int = 15, max_per_domain: int = 3) -> list[Path]:
    """Select semantically dense files from the entire system.

    Scans PSMV, mech-interp, dharma_swarm specs, CLAUDE*.md series,
    and the Kailash Obsidian vault. Forces cross-domain tension by
    capping files per directory. Prefers 2KB-40KB files.

    Stigmergy-guided: files that appeared in past high-salience dream associations
    or received high-salience stigmergy marks get a score boost. The colony
    remembers what was fertile.
    """
    # Load past salience signals (sync reads, fast)
    past_dream_salience = _load_past_dream_salience()
    stigmergy_salience = _load_stigmergy_salience()

    candidates: list[tuple[float, Path]] = []

    for tier_score, dir_path in _DENSE_DIRS:
        if not dir_path.exists():  # type: ignore[union-attr]
            continue

        # For root-level dirs, only scan *.md directly (not recursive)
        # to avoid enormous recursive sweeps of PSMV root
        glob_fn = dir_path.glob if dir_path in (_PSMV, _HOME) else dir_path.rglob  # type: ignore[union-attr]

        for fpath in glob_fn("*.md"):
            name_lower = fpath.name.lower()
            if any(pat in name_lower for pat in _EXCLUDE_PATTERNS):
                continue
            # Skip HUM files as input — they document methodology, not content
            if "hum" in str(fpath).lower() and "THE_HUM_FILES" in str(fpath):
                continue

            try:
                size = fpath.stat().st_size
            except OSError:
                continue

            # Prefer 2KB–40KB
            if size < 800 or size > 100_000:
                continue

            # Base score: tier + size sweet spot (peak at ~10KB)
            size_score = max(0.0, 1.0 - abs(size - 10_000) / 40_000)
            score = tier_score + size_score

            # Stigmergy boost: past high-salience associations
            fname = fpath.name
            dream_boost = past_dream_salience.get(fname, 0.0)  # 0.0–1.0
            stig_boost = stigmergy_salience.get(fname, 0.0)    # 0.0–1.0
            # Max +1.5 from colony memory signals (capped to prevent monopoly)
            colony_boost = min(1.5, dream_boost * 1.0 + stig_boost * 0.5)
            score += colony_boost

            candidates.append((score, fpath))

    # Sort, deduplicate, enforce cross-domain spread
    candidates.sort(key=lambda x: x[0], reverse=True)
    seen_names: set[str] = set()
    selected: list[Path] = []
    domain_counts: dict[str, int] = {}

    for _, fpath in candidates:
        if len(selected) >= count:
            break
        # Dedup by filename — catches nested symlink copies in PSMV
        if fpath.name in seen_names:
            continue
        domain = fpath.parent.name
        if domain_counts.get(domain, 0) >= max_per_domain:
            continue
        seen_names.add(fpath.name)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        selected.append(fpath)

    return selected


# === Public API ===


async def run_dream_cycle(
    file_paths: list[Path] | None = None,
    trigger: WakeTrigger = WakeTrigger.EXPLICIT_CALL,
) -> dict[str, Any]:
    """Run a complete dream cycle: wake → feed → dream → trace → sleep.

    If file_paths is None, selects semantically dense files automatically.
    """
    if file_paths is None:
        # 8 files fully read (≤20KB each) ≈ 40K tokens — better than 15 files at 2500-char excerpts
        file_paths = select_dense_files(count=8)
        print(f"[subconscious] Auto-selected {len(file_paths)} dense files (full reads)")

    agent = SubconsciousAgent()

    # Wake
    wake_state = await agent.wake(trigger)
    print(f"[subconscious] Wake: {wake_state['trigger']}")

    # Feed
    feed_state = await agent.feed(file_paths)
    print(f"[subconscious] Feed: {feed_state['files_loaded']} files, {feed_state['total_chars']} chars")

    # Dream
    associations = await agent.dream(feed_state["contents"], sample_prompts=5)
    print(f"[subconscious] Dream: {len(associations)} associations")

    # Write to file for hypnagogic processing
    dream_file = Path.home() / ".dharma" / "subconscious" / "dream_associations.jsonl"
    dream_file.parent.mkdir(parents=True, exist_ok=True)
    with open(dream_file, "a") as f:
        for assoc in associations:
            f.write(json.dumps(assoc.model_dump(mode="json")) + "\n")
    print(f"[subconscious] Wrote {len(associations)} associations to {dream_file}")

    # Trace
    await agent.trace(associations)
    print(f"[subconscious] Trace: marks left")

    # Sleep
    sleep_state = await agent.sleep()
    print(f"[subconscious] Sleep: {sleep_state['state']}")

    return {
        "wake": wake_state,
        "feed": feed_state,
        "associations": [a.model_dump() for a in associations],
        "sleep": sleep_state,
    }
