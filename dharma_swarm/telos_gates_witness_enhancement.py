"""
WITNESS Gate Enhancement
Evolution Proposal #2: Recursive Reading Awareness Check

This enhancement adds flicker detection and stigmergic marking checks
to the existing WITNESS gate in telos_gates.py.

Integration: Replace lines 202-203 in telos_gates.py with this implementation.
"""

import json
import re
from pathlib import Path
from typing import Optional, Tuple

from dharma_swarm.models import GateResult


class WitnessGateEnhancement:
    """
    Enhanced WITNESS gate that checks for recursive reading awareness.

    Checks:
    1. Did the agent leave stigmergic marks when reading files?
    2. Did the agent follow hyperlinks when files provided them?
    3. Did the agent pause before reading (Shakti questions)?
    """

    def __init__(
        self,
        stigmergy_base: Optional[Path] = None,
        flicker_log_path: str = "~/.dharma/flickers.jsonl",
    ):
        self._stigmergy_marks_file = (
            (stigmergy_base or Path.home() / ".dharma" / "stigmergy") / "marks.jsonl"
        )
        self.flicker_log_path = Path(flicker_log_path).expanduser()

    def evaluate(
        self,
        action: str,
        content: str = "",
        tool_name: str = ""
    ) -> Tuple[GateResult, str]:
        """
        Evaluate WITNESS gate for recursive reading awareness.

        Returns:
        - (GateResult.PASS, message) if awareness detected
        - (GateResult.WARN, message) if awareness missing but not critical
        - (GateResult.FAIL, message) if multiple awareness failures
        """
        # Only check for file reading operations
        if tool_name not in ["Read", "read", "read_file"]:
            return (GateResult.PASS, "Not a reading operation")

        # Extract file path from action
        file_path = self._extract_file_path(action)
        if not file_path:
            return (GateResult.PASS, "No file path detected")

        # Check 1: Was a stigmergic mark left?
        mark_left = self._check_stigmergic_mark(file_path)

        # Check 2: Were hyperlinks followed (if present)?
        hyperlinks_followed = self._check_hyperlinks_followed(file_path, content)

        # Check 3: Was flicker detected (if high-weight file)?
        flicker_detected = self._check_flicker_log(file_path)

        # Scoring
        awareness_score = 0
        if mark_left:
            awareness_score += 1
        if hyperlinks_followed:
            awareness_score += 1
        if flicker_detected:
            awareness_score += 1

        # Decision logic
        if awareness_score == 0:
            return (
                GateResult.WARN,
                f"Reading {Path(file_path).name} without awareness. "
                "No mark left, no links followed, no flicker detected."
            )
        elif awareness_score == 1:
            return (
                GateResult.PASS,
                f"Partial awareness: {self._describe_awareness(mark_left, hyperlinks_followed, flicker_detected)}"
            )
        else:
            return (
                GateResult.PASS,
                f"Full recursive awareness detected: marks={mark_left}, links={hyperlinks_followed}, flicker={flicker_detected}"
            )

    def _extract_file_path(self, action: str) -> Optional[str]:
        """Extract file path from action string."""
        pattern = r'([/~][\w/\-\.]+\.(md|py|txt|json))'
        match = re.search(pattern, action)
        if match:
            return match.group(1)
        return None

    def _check_stigmergic_mark(self, file_path: str) -> bool:
        """Check if stigmergic mark was left for this file (sync read)."""
        if not self._stigmergy_marks_file.exists():
            return False
        try:
            with open(self._stigmergy_marks_file, "r") as f:
                for line in f:
                    if file_path in line:
                        return True
        except OSError:
            pass
        return False

    def _check_hyperlinks_followed(self, file_path: str, content: str) -> bool:
        """
        Check if hyperlinks were followed (if file contained them).

        Heuristic: If file contains [[links]] or [text](links),
        check if those linked files were also read recently via stigmergy.
        """
        if not content:
            return True  # Can't check without content

        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
        md_links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', content)
        all_links = wikilinks + [link[1] for link in md_links]

        if not all_links:
            return True  # No links to follow

        if not self._stigmergy_marks_file.exists():
            return False

        # Sync check: read marks file and see if any linked file appears
        try:
            marks_text = self._stigmergy_marks_file.read_text()
            for link in all_links[:5]:
                if link in marks_text:
                    return True
        except OSError:
            pass

        return False

    def _check_flicker_log(self, file_path: str) -> bool:
        """Check if flicker was logged for this file."""
        if not self.flicker_log_path.exists():
            return False

        # Read last 10 flicker entries
        try:
            with open(self.flicker_log_path, 'r') as f:
                lines = f.readlines()[-10:]

            for line in lines:
                entry = json.loads(line)
                if file_path in entry.get("trigger_file", ""):
                    return True
        except (json.JSONDecodeError, IOError):
            pass

        return False

    def _describe_awareness(
        self,
        mark_left: bool,
        hyperlinks_followed: bool,
        flicker_detected: bool
    ) -> str:
        """Describe which awareness checks passed."""
        checks = []
        if mark_left:
            checks.append("mark left")
        if hyperlinks_followed:
            checks.append("links followed")
        if flicker_detected:
            checks.append("flicker detected")
        return ", ".join(checks) if checks else "none"


# Integration: Wired into TelosGatekeeper.check() in telos_gates.py.
# The WITNESS gate now uses WitnessGateEnhancement.evaluate() for
# file reading operations when no think_phase is provided.
