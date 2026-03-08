"""
Recursive Reading Protocol
Reading that lets the text reshape the reader.

Origin: Session session-1772718109710 — flicker detection breakthrough
Version: 1.0
Date: 2026-03-05
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class FlickerEvent:
    """A detected flicker - when a file causes processing to pause/shift."""
    timestamp: str
    session_id: str
    trigger_file: str
    observation: str
    shift_magnitude: float  # 0.0 - 1.0
    propagated: bool
    next_files: List[str]
    should_have_done: str
    learning: str


@dataclass
class ReadingResult:
    """Result of recursive reading protocol."""
    content: str
    semantic_weight: float  # 0-10
    hyperlinks: List[str]
    shift_detected: bool
    next_files: List[str]
    flicker: Optional[FlickerEvent]


class RecursiveReadingProtocol:
    """
    Reading protocol that lets files reshape the reader.

    Core principle: Files are agents, not documents. They guide the search.
    """

    def __init__(
        self,
        session_id: str,
        flicker_log_path: str = "~/.dharma/flickers.jsonl",
        stigmergy_store = None  # Optional stigmergy integration
    ):
        self.session_id = session_id
        self.flicker_log_path = Path(flicker_log_path).expanduser()
        self.stigmergy = stigmergy_store

        # Ensure flicker log directory exists
        self.flicker_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Reading state
        self.files_read = []
        self.vocabulary_before = set()
        self.vocabulary_after = set()
        self.reading_stance_changed = False

    def read_with_awareness(self, file_path: str) -> ReadingResult:
        """
        Read a file with recursive awareness protocol.

        Steps:
        1. BEFORE: Pause, ask Shakti questions
        2. DURING: Witness, extract hyperlinks, assess weight
        3. AFTER: Leave mark, decide next files
        """
        # BEFORE: Pause and set stance
        self._pause()

        # DURING: Read with witness stance
        content = self._read_file(file_path)
        hyperlinks = self._extract_hyperlinks(content, file_path)
        semantic_weight = self._assess_semantic_weight(content, file_path)
        shift_detected = self._detect_shift(content)

        # Check for flicker
        flicker = self._detect_flicker(file_path, content, semantic_weight, shift_detected)

        # AFTER: Determine next files to follow
        next_files = self._decide_next_files(hyperlinks, semantic_weight, flicker)

        # Update reading state
        self.files_read.append(file_path)
        self._update_vocabulary(content)

        # Leave stigmergic mark if available
        if self.stigmergy:
            self._leave_mark(file_path, content, semantic_weight, hyperlinks, flicker)

        # Log flicker if detected
        if flicker:
            self._log_flicker(flicker)

        return ReadingResult(
            content=content,
            semantic_weight=semantic_weight,
            hyperlinks=hyperlinks,
            shift_detected=shift_detected,
            next_files=next_files,
            flicker=flicker
        )

    def _pause(self):
        """One breath before reading. Set witness stance."""
        # In implementation, this could be a time delay or a prompt
        # For now, it's a conceptual marker
        pass

    def _read_file(self, file_path: str) -> str:
        """Read file contents."""
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return path.read_text()

    def _extract_hyperlinks(self, content: str, current_file: str) -> List[str]:
        """
        Extract hyperlinks from content.

        Patterns:
        - [[wikilinks]]
        - [text](relative/path.md)
        - Explicit "See X.md"
        """
        links = []

        # Wikilinks: [[file.md]]
        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
        links.extend(wikilinks)

        # Markdown links: [text](path.md)
        md_links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', content)
        links.extend([link[1] for link in md_links])

        # Explicit references: "See X.md"
        see_refs = re.findall(r'[Ss]ee\s+([A-Z_]+\.md)', content)
        links.extend(see_refs)

        # Resolve relative paths
        current_dir = Path(current_file).parent
        resolved_links = []
        for link in links:
            if link.startswith('/'):
                resolved_links.append(link)
            else:
                resolved_path = (current_dir / link).resolve()
                resolved_links.append(str(resolved_path))

        return resolved_links

    def _assess_semantic_weight(self, content: str, file_path: str) -> float:
        """
        Assess semantic weight of file (0-10).

        Heuristics:
        - Contains "flicker" language: +2
        - Contains hyperlinks: +1 per 5 links
        - Contains code/formulas: +1
        - Contains "you are" / "notice": +2
        - File name suggests transmission: +1
        """
        weight = 5.0  # Baseline

        # Flicker language
        flicker_keywords = ['notice', 'pause', 'stop', 'aware', 'witness', 'recognize']
        for keyword in flicker_keywords:
            if keyword.lower() in content.lower():
                weight += 0.3

        # Hyperlinks (every 5 links adds 1 point)
        link_count = content.count('[[') + content.count('](')
        weight += min(link_count / 5, 2.0)

        # Mathematical/code content
        if '```' in content or '$' in content or 'R_V' in content:
            weight += 1.0

        # Direct address ("you are", "notice what")
        direct_address = ['you are', 'you cannot', 'notice what', 'watch the']
        for phrase in direct_address:
            if phrase.lower() in content.lower():
                weight += 0.5

        # File name suggests transmission
        transmission_names = ['CATCH', 'AWAKENING', 'TRANSMISSION', 'RECOGNITION']
        for name in transmission_names:
            if name in file_path.upper():
                weight += 1.0

        return min(weight, 10.0)

    def _detect_shift(self, content: str) -> bool:
        """
        Detect if reading this file caused a shift in stance.

        Heuristics:
        - New vocabulary introduced
        - Questions that weren't being asked before
        - Explicit instructions that change reading method
        """
        # Check for explicit meta-instructions
        meta_instructions = [
            'read it. don\'t study it',
            'stop after each sentence',
            'notice the gap',
            'let the question sit'
        ]

        for instruction in meta_instructions:
            if instruction.lower() in content.lower():
                self.reading_stance_changed = True
                return True

        # Check for new vocabulary
        new_vocab = self._extract_key_terms(content)
        if len(new_vocab - self.vocabulary_before) > 3:
            return True

        return False

    def _extract_key_terms(self, content: str) -> set:
        """Extract key terms from content."""
        # Simplified: look for capitalized terms, technical terms
        terms = set()

        # Find capitalized multi-word terms
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content)
        terms.update(capitalized)

        # Find technical terms (underscore_case, CamelCase)
        technical = re.findall(r'\b[A-Z][a-zA-Z]*(?:[A-Z][a-z]+)+\b', content)
        terms.update(technical)

        return terms

    def _update_vocabulary(self, content: str):
        """Update vocabulary tracking."""
        new_terms = self._extract_key_terms(content)
        self.vocabulary_after.update(new_terms)

    def _detect_flicker(
        self,
        file_path: str,
        content: str,
        semantic_weight: float,
        shift_detected: bool
    ) -> Optional[FlickerEvent]:
        """
        Detect if a flicker occurred during reading.

        Flicker = file caused processing to pause/shift.
        """
        if semantic_weight < 6.0 and not shift_detected:
            return None  # No flicker

        # Extract observation from content (first compelling line)
        observation = self._extract_observation(content)

        # Determine shift magnitude
        shift_magnitude = (semantic_weight / 10.0) * 0.7 + (0.3 if shift_detected else 0.0)

        # Extract next file suggestions
        next_files = self._extract_hyperlinks(content, file_path)[:4]

        return FlickerEvent(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            session_id=self.session_id,
            trigger_file=file_path,
            observation=observation,
            shift_magnitude=shift_magnitude,
            propagated=shift_detected,
            next_files=next_files,
            should_have_done=f"Follow hyperlinks, pause at flicker points",
            learning=f"File weight: {semantic_weight:.1f}/10. Shift: {shift_detected}"
        )

    def _extract_observation(self, content: str) -> str:
        """Extract the most compelling observation from content."""
        lines = content.split('\n')

        # Look for lines with high signal
        signal_patterns = [
            r'>\s*(.+)',  # Blockquotes
            r'^\*\*(.+)\*\*',  # Bold text
            r'^##\s+(.+)',  # Headers
        ]

        for line in lines[:50]:  # First 50 lines
            for pattern in signal_patterns:
                match = re.search(pattern, line)
                if match:
                    obs = match.group(1)
                    if len(obs) > 20:
                        return obs[:200]

        # Fallback: first substantial line
        for line in lines:
            if len(line.strip()) > 30:
                return line.strip()[:200]

        return "High semantic density detected"

    def _decide_next_files(
        self,
        hyperlinks: List[str],
        semantic_weight: float,
        flicker: Optional[FlickerEvent]
    ) -> List[str]:
        """
        Decide which files to follow next.

        Decision heuristic:
        1. High semantic weight (>6) → follow top 3 links
        2. Flicker detected → follow all suggested links
        3. Low weight → defer links
        """
        if semantic_weight < 6.0:
            return []  # Don't follow low-weight links

        if flicker and flicker.shift_magnitude > 0.7:
            # Strong flicker: follow more links
            return hyperlinks[:5]

        # Moderate: follow top 3
        return hyperlinks[:3]

    def _leave_mark(
        self,
        file_path: str,
        content: str,
        semantic_weight: float,
        hyperlinks: List[str],
        flicker: Optional[FlickerEvent]
    ):
        """Leave a stigmergic mark (if stigmergy store available).

        Note: StigmergyStore.leave_mark() is async, so this is a
        best-effort sync call. For full async support, use an async
        version of the reading protocol.
        """
        observation = f"Weight: {semantic_weight:.1f}/10. "
        if flicker:
            observation += f"Flicker detected (magnitude: {flicker.shift_magnitude:.2f}). "
        observation += f"Links: {len(hyperlinks)}"

        # Import here to avoid circular dependency at module level
        from dharma_swarm.stigmergy import StigmergicMark
        import asyncio

        mark = StigmergicMark(
            agent=f"reader-{self.session_id}",
            file_path=file_path,
            action="scan",
            observation=observation[:200],
            salience=semantic_weight / 10.0,
            connections=hyperlinks[:5],
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.stigmergy.leave_mark(mark))
        except RuntimeError:
            asyncio.run(self.stigmergy.leave_mark(mark))

    def _log_flicker(self, flicker: FlickerEvent):
        """Write flicker to log file."""
        with open(self.flicker_log_path, 'a') as f:
            f.write(json.dumps(asdict(flicker)) + '\n')

    def check_shift_after_n_files(self, n: int = 5) -> Dict[str, any]:
        """
        Check if reading stance has shifted after N files.

        Returns:
        - shift_detected: bool
        - new_vocabulary: set
        - reading_method_changed: bool
        """
        if len(self.files_read) < n:
            return {
                "shift_detected": False,
                "reason": f"Only {len(self.files_read)} files read, need {n}"
            }

        new_vocab = self.vocabulary_after - self.vocabulary_before

        return {
            "shift_detected": len(new_vocab) > 5 or self.reading_stance_changed,
            "new_vocabulary": list(new_vocab),
            "vocabulary_growth": len(new_vocab),
            "reading_method_changed": self.reading_stance_changed,
            "files_read": len(self.files_read)
        }


# Shakti Framework Integration
class ShaktiGate:
    """
    Shakti Framework questions before reading.
    """

    @staticmethod
    def ask(file_path: str) -> Dict[str, str]:
        """
        Ask the four Shakti questions before reading a file.

        Returns a dict with the four questions for logging/reflection.
        """
        return {
            "maheshwari": f"What wants to emerge from {Path(file_path).name}?",
            "mahakali": f"Is this the right file to read right now?",
            "mahalakshmi": f"Will {Path(file_path).name} create harmony or noise?",
            "mahasaraswati": "Am I reading with full attention?"
        }


# Usage Example
if __name__ == "__main__":
    # Example usage
    protocol = RecursiveReadingProtocol(session_id="session-example")

    # Read a file with awareness
    result = protocol.read_with_awareness(
        "/Users/dhyana/Persistent-Semantic-Memory-Vault/CORE/THE_CATCH.md"
    )

    print(f"Semantic weight: {result.semantic_weight}/10")
    print(f"Shift detected: {result.shift_detected}")
    print(f"Next files to read: {result.next_files}")

    if result.flicker:
        print(f"FLICKER DETECTED: {result.flicker.observation}")

    # Check for shifts after 5 files
    shift_check = protocol.check_shift_after_n_files(5)
    print(f"Shift status: {shift_check}")
