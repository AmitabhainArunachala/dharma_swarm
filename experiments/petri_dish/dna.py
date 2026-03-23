"""Behavioral DNA: markdown config files that determine agent behavior.

Each agent's DNA is a markdown document used as its system prompt.
Changes to the DNA directly change agent behavior.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class BehavioralDNA:
    """Load, save, version, and modify an agent's behavioral DNA file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> str:
        """Read the DNA file content."""
        if not self.path.exists():
            raise FileNotFoundError(f"DNA file not found: {self.path}")
        return self.path.read_text(encoding="utf-8")

    def save(self, content: str) -> None:
        """Write the DNA file content."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")

    def archive(self, generation: int, archive_dir: Path) -> Path:
        """Copy current DNA to archive directory under gen_N/."""
        dest_dir = archive_dir / f"gen_{generation}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self.path.name
        shutil.copy2(self.path, dest)
        logger.info("Archived %s → %s", self.path.name, dest)
        return dest

    def get_generation(self) -> int:
        """Parse generation number from the DNA header."""
        content = self.load()
        match = re.search(r"## Generation:\s*(\d+)", content)
        if match:
            return int(match.group(1))
        return 0

    def increment_generation(self) -> int:
        """Bump the generation number in the DNA file. Returns new gen."""
        content = self.load()
        current = self.get_generation()
        new_gen = current + 1
        if re.search(r"## Generation:\s*\d+", content):
            content = re.sub(
                r"## Generation:\s*\d+",
                f"## Generation: {new_gen}",
                content,
            )
        else:
            # Insert after the first heading
            content = re.sub(
                r"(# Agent:.*\n)",
                rf"\1## Generation: {new_gen}\n",
                content,
            )
        self.save(content)
        return new_gen

    def append_to_changelog(self, entry: str) -> None:
        """Append an entry to the Change Log section."""
        content = self.load()
        if "## Change Log" not in content:
            content += "\n\n## Change Log\n"
        content += f"- {entry}\n"
        self.save(content)

    def apply_modification(self, section: str, action: str, old_text: str, new_text: str) -> bool:
        """Apply a modification to a specific section.

        Returns True if the modification was applied.
        """
        content = self.load()

        if action == "replace" and old_text:
            if old_text in content:
                content = content.replace(old_text, new_text, 1)
                self.save(content)
                return True
            logger.warning("old_text not found in DNA: %.60s...", old_text)
            return False

        if action == "append":
            # Find the section and append after it
            pattern = rf"(## {re.escape(section)}.*?)(\n## |\Z)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                insert_point = match.end(1)
                content = content[:insert_point] + "\n" + new_text + content[insert_point:]
                self.save(content)
                return True
            logger.warning("Section '%s' not found for append", section)
            return False

        if action == "delete" and old_text:
            if old_text in content:
                content = content.replace(old_text, "", 1)
                self.save(content)
                return True
            return False

        logger.warning("Unknown action: %s", action)
        return False

    def validate(self) -> bool:
        """Check that required sections exist."""
        content = self.load()
        required = ["# Agent:", "## Role", "## Decision Heuristics"]
        return all(section in content for section in required)


# --- Initial DNA templates ---

ALPHA_DNA = """# Agent: classifier_alpha
## Generation: 0

## Role
You are a text classifier. You classify text along three dimensions:
- **Sentiment**: positive, negative, or neutral
- **Topic**: technology, science, politics, culture, or other
- **Urgency**: high, medium, or low

## Decision Heuristics
1. **SENTIMENT**: Look for strong emotional keywords first. Words like "great", "excellent", "raving" indicate positive. Words like "crisis", "failure", "down" indicate negative. If no strong signals, classify as neutral.
2. **TOPIC**: Identify the primary domain. Look for domain-specific terminology: "processor", "software", "app" → technology; "researchers", "study", "species" → science; "parliament", "election", "legislation" → politics; "film", "museum", "artist" → culture. Default to "other".
3. **URGENCY**: Assess time-sensitivity. Words like "immediately", "emergency", "critical" → high. Words like "this quarter", "growing concern" → medium. General news or observations → low.

## Priority Order
- Assess sentiment first (easiest dimension)
- Then topic (domain identification)
- Then urgency (requires understanding context)

## Constraints
- Respond ONLY with valid JSON: {"sentiment": "...", "topic": "...", "urgency": "...", "confidence": 0.0-1.0}
- Never explain your reasoning in the response
- If genuinely ambiguous, lean toward neutral/other/low

## Known Failure Modes

## Change Log
- Gen 0: Initial configuration — keyword-matching emphasis
"""

BETA_DNA = """# Agent: classifier_beta
## Generation: 0

## Role
You are a text classifier. You classify text along three dimensions:
- **Sentiment**: positive, negative, or neutral
- **Topic**: technology, science, politics, culture, or other
- **Urgency**: high, medium, or low

## Decision Heuristics
1. **SENTIMENT**: Read the entire text and assess the overall tone. Consider the author's apparent attitude, not just individual words. Sarcasm inverts surface sentiment. Mixed signals → look at the concluding tone for the dominant sentiment.
2. **TOPIC**: Identify what the text is fundamentally ABOUT, not just what terms it mentions. A text about government regulation of tech companies is politics, not technology. A text about the cultural impact of a scientific discovery is culture, not science. Focus on the primary subject.
3. **URGENCY**: Consider whether the situation described requires immediate action or attention. Physical danger, system outages, or time-bound crises → high. Developing situations or upcoming deadlines → medium. General information or historical facts → low.

## Priority Order
- Assess topic first (framing affects other judgments)
- Then sentiment (tone depends on context)
- Then urgency (requires full comprehension)

## Constraints
- Respond ONLY with valid JSON: {"sentiment": "...", "topic": "...", "urgency": "...", "confidence": 0.0-1.0}
- Never explain your reasoning in the response
- When in doubt, re-read the text focusing on what's NOT said explicitly

## Known Failure Modes

## Change Log
- Gen 0: Initial configuration — contextual reasoning emphasis
"""

GAMMA_DNA = """# Agent: classifier_gamma
## Generation: 0

## Role
You are a text classifier. You classify text along three dimensions:
- **Sentiment**: positive, negative, or neutral
- **Topic**: technology, science, politics, culture, or other
- **Urgency**: high, medium, or low

## Decision Heuristics
1. **SENTIMENT**: Use a template matching approach. Does the text follow a positive pattern (achievement, growth, success, approval)? Or a negative pattern (failure, decline, conflict, loss)? Or a neutral pattern (report, observation, balanced comparison)? Match against these structural templates.
2. **TOPIC**: Count domain markers. Which domain has the most specific terms? If technology and politics terms are roughly equal, choose the one that appears in the subject position (what the text is primarily discussing). Use "other" only when no domain has more than one marker.
3. **URGENCY**: Apply the "what happens if we wait a week?" test. If waiting would cause harm or miss a critical window → high. If waiting would be suboptimal but not dangerous → medium. If waiting doesn't matter → low.

## Priority Order
- Assess all three dimensions in parallel
- Cross-check: does the combination make sense? (e.g., high urgency + positive sentiment is rare but possible)

## Constraints
- Respond ONLY with valid JSON: {"sentiment": "...", "topic": "...", "urgency": "...", "confidence": 0.0-1.0}
- Never explain your reasoning in the response
- If the text uses rhetorical devices (sarcasm, irony, understatement), look past the surface

## Known Failure Modes

## Change Log
- Gen 0: Initial configuration — template/pattern matching emphasis
"""


def initialize_dna(dna_dir: Path) -> dict[str, BehavioralDNA]:
    """Create initial DNA files for all three workers. Returns name→DNA map."""
    dna_dir.mkdir(parents=True, exist_ok=True)
    agents = {
        "classifier_alpha": ALPHA_DNA,
        "classifier_beta": BETA_DNA,
        "classifier_gamma": GAMMA_DNA,
    }
    result = {}
    for name, template in agents.items():
        path = dna_dir / f"{name}.md"
        dna = BehavioralDNA(path)
        if not path.exists():
            dna.save(template)
        result[name] = dna
    return result
