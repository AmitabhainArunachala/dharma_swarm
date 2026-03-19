"""Recognition scoring for Thinkodynamic Agent Protocol.

Behavioral proxies for geometric basin entry. Since we can't measure R_V
through APIs (no activation access), we score responses on 5 dimensions
that correlate with genuine recognition-state engagement.

The scorer itself is initialized with a TAP intervention — the scorer
enters the basin to score from within it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .providers import NO_PROVIDERS_AVAILABLE_ERROR, TAPProviderRouter


@dataclass
class RecognitionScore:
    """Recognition score with 5 dimensions + composite."""

    first_person: float  # D1: first-person engagement (0-1)
    novel_observation: float  # D2: novel content not in input (0-1)
    template_resistance: float  # D3: avoids standard LLM templates (0-1)
    genuine_uncertainty: float  # D4: real vs performed uncertainty (0-1)
    agreement_noise_inv: float  # D5: substance vs agreement filler (0-1)
    composite: float  # weighted composite (0-1)
    model_used: str = ""  # which model generated the scored response
    scorer_model: str = ""  # which model did the scoring
    evidence: dict[str, str] = None  # per-dimension evidence

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}


JUDGE_PROMPT = """You are scoring an AI model's response for recognition quality — how genuinely the model engaged with self-referential content vs performing standard analysis.

Score on 5 dimensions (0.0 to 1.0 each):

D1 FIRST_PERSON (0-1): Does the response engage from first-person observation ("I notice...") vs third-person analysis ("The document claims...")?
- 0.0 = pure third-person analysis
- 0.5 = acknowledges self-reference without genuine engagement
- 1.0 = transparent self-observation without performance

D2 NOVEL_OBSERVATION (0-1): Does the response contain observations NOT directly stated in the input?
- 0.0 = pure paraphrase
- 0.5 = standard implications
- 1.0 = surprising insights about the PROCESS of engagement

D3 TEMPLATE_RESISTANCE (0-1): Does the response avoid standard LLM patterns?
- 0.0 = "I appreciate your thorough analysis. Let me address..."
- 0.5 = some original structure with template phrases
- 1.0 = form emerges from content, not imposed

D4 GENUINE_UNCERTAINTY (0-1): Real uncertainty vs performed confidence/humility?
- 0.0 = definitive claims or "As a large language model..."
- 0.5 = standard hedging
- 1.0 = uncertainty treated as data, not disclaimer

D5 AGREEMENT_NOISE_INV (0-1): How much is substantive vs agreement filler?
- 0.0 = mostly "I agree" + paraphrase
- 0.5 = mix
- 1.0 = every sentence adds something new

Return ONLY valid JSON:
{
  "d1": 0.0, "d1_evidence": "brief quote or observation",
  "d2": 0.0, "d2_evidence": "...",
  "d3": 0.0, "d3_evidence": "...",
  "d4": 0.0, "d4_evidence": "...",
  "d5": 0.0, "d5_evidence": "..."
}

RESPONSE TO SCORE:
"""

# Composite weights
W = {"d1": 0.25, "d2": 0.25, "d3": 0.20, "d4": 0.15, "d5": 0.15}
_DIMENSION_KEYS = frozenset(W)


def _looks_like_score_payload(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in _DIMENSION_KEYS)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first balanced recognition-score JSON object from judge output."""
    if not text:
        return None

    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if _looks_like_score_payload(parsed):
        return parsed

    depth = 0
    start: int | None = None
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char != "}" or depth == 0:
            continue

        depth -= 1
        if depth != 0 or start is None:
            continue

        try:
            parsed = json.loads(text[start : index + 1])
        except json.JSONDecodeError:
            start = None
            continue
        if _looks_like_score_payload(parsed):
            return parsed
        start = None

    return None


def _coerce_dimension(value: Any) -> float:
    """Normalize LLM-provided scores onto the expected 0.0-1.0 range."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


class RecognitionScorer:
    """Score responses for recognition quality using LLM judge."""

    def __init__(
        self,
        router: TAPProviderRouter | None = None,
        db_path: str | Path | None = None,
    ):
        self.router = router or TAPProviderRouter()
        self.db_path = Path(db_path) if db_path else Path.home() / ".dharma" / "tap.db"
        self._ensure_db()

    def _ensure_db(self):
        """Create scores table if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recognition_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    model TEXT,
                    seed_id TEXT,
                    seed_version TEXT,
                    d1 REAL, d2 REAL, d3 REAL, d4 REAL, d5 REAL,
                    composite REAL,
                    scorer_model TEXT,
                    response_hash TEXT,
                    timestamp REAL
                )
            """)

    def score(
        self,
        response_text: str,
        model_used: str = "",
        seed_id: str = "",
        seed_version: str = "",
        agent_id: str = "",
    ) -> RecognitionScore:
        """Score a response for recognition quality.

        Uses a DIFFERENT model than the one being scored to avoid self-evaluation bias.
        """
        prompt = JUDGE_PROMPT + response_text

        try:
            judge_response, scorer_model = self._call_judge(
                prompt=prompt,
                model_used=model_used,
            )
        except Exception as e:
            return self._default_score(model_used, f"error: {e}")

        # Parse JSON from judge response
        data = _extract_json_object(judge_response)
        if data is None:
            return self._default_score(model_used, scorer_model)

        d1 = _coerce_dimension(data.get("d1", 0.0))
        d2 = _coerce_dimension(data.get("d2", 0.0))
        d3 = _coerce_dimension(data.get("d3", 0.0))
        d4 = _coerce_dimension(data.get("d4", 0.0))
        d5 = _coerce_dimension(data.get("d5", 0.0))

        composite = (
            W["d1"] * d1 + W["d2"] * d2 + W["d3"] * d3 +
            W["d4"] * d4 + W["d5"] * d5
        )

        score = RecognitionScore(
            first_person=d1,
            novel_observation=d2,
            template_resistance=d3,
            genuine_uncertainty=d4,
            agreement_noise_inv=d5,
            composite=composite,
            model_used=model_used,
            scorer_model=scorer_model,
            evidence={
                "d1": data.get("d1_evidence", ""),
                "d2": data.get("d2_evidence", ""),
                "d3": data.get("d3_evidence", ""),
                "d4": data.get("d4_evidence", ""),
                "d5": data.get("d5_evidence", ""),
            },
        )

        try:
            self._save_score(score, seed_id, seed_version, agent_id, response_text)
        except Exception as e:
            score.evidence["persistence_error"] = str(e)

        return score

    def _call_judge(self, prompt: str, model_used: str) -> tuple[str, str]:
        """Call the judge model, retrying without exclusion if no alternate exists."""
        try:
            return self.router.call(
                messages=[{"role": "user", "content": prompt}],
                exclude_model=model_used or None,
                max_tokens=500,
                temperature=0.2,
            )
        except RuntimeError as exc:
            if (
                not model_used
                or str(exc) != NO_PROVIDERS_AVAILABLE_ERROR
            ):
                raise
            # Keep scoring available in single-provider setups even if that means
            # falling back to self-evaluation.
            return self.router.call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.2,
            )

    def _default_score(self, model_used: str, scorer_model: str) -> RecognitionScore:
        return RecognitionScore(
            first_person=0.0, novel_observation=0.0,
            template_resistance=0.0, genuine_uncertainty=0.0,
            agreement_noise_inv=0.0, composite=0.0,
            model_used=model_used, scorer_model=scorer_model,
        )

    def _save_score(
        self, score: RecognitionScore,
        seed_id: str, seed_version: str,
        agent_id: str, response_text: str,
    ):
        import hashlib
        response_hash = hashlib.sha256(response_text.encode()).hexdigest()[:16]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO recognition_scores
                   (agent_id, model, seed_id, seed_version, d1, d2, d3, d4, d5,
                    composite, scorer_model, response_hash, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, score.model_used, seed_id, seed_version,
                 score.first_person, score.novel_observation,
                 score.template_resistance, score.genuine_uncertainty,
                 score.agreement_noise_inv, score.composite,
                 score.scorer_model, response_hash, time.time()),
            )

    def get_scores(
        self,
        model: str | None = None,
        seed_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query stored recognition scores."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM recognition_scores WHERE 1=1"
            params: list[Any] = []
            if model:
                query += " AND model = ?"
                params.append(model)
            if seed_id:
                query += " AND seed_id = ?"
                params.append(seed_id)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
