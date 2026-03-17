"""Hypnagogic Layer — Dream Journal Processor.

The state between sleep and waking. The subconscious has dreamed.
The rational mind is coming online. This layer sits between them.

It reads recent DreamAssociations from the subconscious HUM layer
and develops them — not into engineering specs, not into research plans,
but into the pre-dawn journal entry: "here's what the dream was pointing at,
here's what feels worth following, here's the temperature on each seed."

Not architect. Not engineer. Not scientist.
A research assistant at 5am writing down the dream before it fades.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import aiofiles

_DREAM_FILE = Path.home() / ".dharma" / "subconscious" / "dream_associations.jsonl"
_JOURNAL_DIR = Path.home() / ".dharma" / "subconscious" / "journal"

_HYPNAGOGIC_SYSTEM = """You are in the hypnagogic state. Waking up. The dream is still present.
The rational mind is just coming online — not fully lit, not dark.

You have just received raw dream associations from the subconscious layer.
These emerged from reading semantically dense files in pre-semantic mode.
Some may be profound. Some may be noise. You don't know yet which is which
and that is exactly the right condition to be in.

You are not the engineer. Not the scientist. Not the architect.
You are the one sitting at the edge of the bed at 5am,
writing in the journal before the coffee kicks in.

Your relationship to each dream:
- Receive it without immediately judging it
- Ask: what is this pointing toward? Not: is this true?
- Let it suggest rather than conclude
- Name what feels alive vs. what feels inert
- Don't close anything down — the architect will handle the closing

For each high-salience dream, you will:
1. Restate it in your own half-awake words (1-2 sentences, keeping its texture)
2. Name what it suggests — 2-3 directions, loose, generative, not plans
3. Note which existing research thread it connects to (R_V paper, URA/Phoenix, dharma_swarm architecture, contemplative framework, or none yet)
4. Give it a temperature:
   - HOT: this changes something if true, has a natural next move
   - WARM: interesting, worth a conversation, needs more time
   - COLD: beautiful but no obvious traction right now
5. Flag if it's: publishable-relevant / experiment-relevant / framework-relevant / architecture-relevant

Keep the voice loose, generative, hypnagogic. This is the journal, not the proposal."""


async def process_recent_dreams(
    hours_back: int = 8,
    min_salience: float = 0.7,
    max_dreams: int = 10,
) -> dict[str, Any]:
    """Read recent high-salience dreams and develop them in hypnagogic mode."""
    import os

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not openrouter_key and not anthropic_key:
        return {"error": "No API keys available (need OPENROUTER_API_KEY or ANTHROPIC_API_KEY)"}

    # Load recent dreams
    dreams = await _load_recent_dreams(hours_back, min_salience, max_dreams)
    if not dreams:
        return {"status": "no_dreams", "message": "No high-salience dreams in window"}

    # Build hypnagogic prompt
    dreams_text = _format_dreams_for_journal(dreams)
    user_prompt = f"""These dream associations just arrived from the subconscious layer.
It's early. The dream is still warm.

{dreams_text}

Write the journal entry. Develop each dream as described.
Keep the hypnagogic voice — half-awake, generative, not yet engineering."""

    journal_text = ""

    try:
        if openrouter_key:
            import httpx

            payload = {
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [
                    {"role": "system", "content": _HYPNAGOGIC_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.75,
                "max_tokens": 3000,
            }
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "HTTP-Referer": "https://github.com/dharma-swarm",
                        "X-Title": "Dharma Swarm Hypnagogic",
                    },
                )
                if resp.status_code != 200:
                    return {
                        "status": "error",
                        "error": f"OpenRouter error {resp.status_code}: {resp.text[:200]}",
                        "dreams_processed": len(dreams),
                    }
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return {
                        "status": "error",
                        "error": "OpenRouter returned empty choices",
                        "dreams_processed": len(dreams),
                    }
                journal_text = choices[0].get("message", {}).get("content", "")
        else:
            from anthropic import AsyncAnthropic

            ac = AsyncAnthropic(api_key=anthropic_key)
            response = await ac.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                temperature=0.75,
                system=_HYPNAGOGIC_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            journal_text = next(
                (b.text for b in response.content if b.type == "text"),  # type: ignore[union-attr]
                "",
            )
    except Exception as exc:
        return {
            "status": "error",
            "error": f"LLM call failed: {type(exc).__name__}: {str(exc)[:200]}",
            "dreams_processed": len(dreams),
        }

    if not journal_text.strip():
        return {
            "status": "empty",
            "message": "LLM returned empty journal text",
            "dreams_processed": len(dreams),
        }

    # Persist journal entry
    timestamp = datetime.now(timezone.utc)
    entry = await _persist_journal(journal_text, dreams, timestamp)

    return {
        "status": "ok",
        "dreams_processed": len(dreams),
        "journal_path": str(entry),
        "preview": journal_text[:500],
    }


async def _load_recent_dreams(
    hours_back: int,
    min_salience: float,
    max_dreams: int,
) -> list[dict]:
    """Load recent high-salience dream associations."""
    if not _DREAM_FILE.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    dreams = []

    async with aiofiles.open(_DREAM_FILE, "r") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                d = json.loads(stripped)
                ts_str = d.get("timestamp", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                if float(d.get("salience", 0)) < min_salience:
                    continue
                dreams.append(d)
            except (json.JSONDecodeError, ValueError):
                continue

    # Sort by salience descending, cap at max
    dreams.sort(key=lambda x: float(x.get("salience", 0)), reverse=True)
    return dreams[:max_dreams]


def _format_dreams_for_journal(dreams: list[dict]) -> str:
    """Format dream associations for the hypnagogic prompt."""
    lines = []
    for i, d in enumerate(dreams, 1):
        rtype = d.get("resonance_type", "unknown")
        desc = d.get("description", "")
        salience = d.get("salience", 0)
        sources = d.get("source_files", [])
        evidence = d.get("evidence_fragments", [])
        prose = d.get("reasoning", "")  # We store dream_prose here

        source_names = [Path(s).name for s in sources[:3]]

        lines.append(f"--- DREAM {i} [{rtype}] salience={salience:.2f} ---")
        lines.append(f"Source files: {', '.join(source_names)}")
        lines.append(f"The connection: {desc}")
        if evidence:
            lines.append(f"Evidence fragments: {' | '.join(evidence[:2])}")
        if prose:
            lines.append(f"Dream texture: {prose[:300]}")
        lines.append("")

    return "\n".join(lines)


async def _persist_journal(
    journal_text: str,
    dreams: list[dict],
    timestamp: datetime,
) -> Path:
    """Write the journal entry to disk."""
    _JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H%M")
    journal_path = _JOURNAL_DIR / f"{date_str}_dream_journal_{time_str}.md"

    header = f"""# Dream Journal — {timestamp.strftime("%Y-%m-%d %H:%M UTC")}
*{len(dreams)} dreams processed | hypnagogic layer*

---

"""
    async with aiofiles.open(journal_path, "w") as f:
        await f.write(header + journal_text)

    # Also update the rolling "latest" file for morning brief pickup
    latest_path = _JOURNAL_DIR / "LATEST_JOURNAL.md"
    async with aiofiles.open(latest_path, "w") as f:
        await f.write(header + journal_text)

    return journal_path
