"""Quality Gates: LLM-as-judge evaluation for agent output.

Evaluates agent work product against domain-specific rubrics.
Blocks promotion of low-quality evolution proposals.
Provides structured feedback for self-improvement.

Lightweight custom evaluator -- no DeepEval dependency.
Uses dharma_swarm's own LLM providers for evaluation calls.

Pipeline integration point:
    EVALUATE FITNESS -> **QUALITY GATE** -> ARCHIVE
    If quality score < threshold, mark proposal REJECTED with feedback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.model_hierarchy import default_model as canonical_default_model
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType, _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD = 60
_CACHE_DIR = Path.home() / ".dharma" / "quality_gates"
_MAX_ARTIFACT_CHARS = 12_000  # Truncate artifacts beyond this for LLM eval


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class QualityDomain(str, Enum):
    """The domain of a quality evaluation."""

    CODE = "code"
    RESEARCH = "research"
    CONTENT = "content"
    PROPOSAL = "proposal"


class QualityVerdict(str, Enum):
    """Overall verdict from a quality gate."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    """Score for a single quality dimension."""

    name: str
    score: float = Field(ge=0.0, le=100.0)
    feedback: str = ""
    weight: float = Field(default=1.0, ge=0.0)


class QualityScore(BaseModel):
    """Structured quality evaluation result."""

    id: str = Field(default_factory=_new_id)
    domain: QualityDomain
    overall: float = Field(ge=0.0, le=100.0)
    verdict: QualityVerdict = QualityVerdict.FAIL
    dimensions: list[DimensionScore] = Field(default_factory=list)
    feedback: str = ""
    improvement_suggestions: list[str] = Field(default_factory=list)
    artifact_hash: str = ""
    evaluated_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    evaluator: str = "lightweight"  # "lightweight" or "llm"
    model_used: str = ""
    latency_ms: float = 0.0


class QualityGateResult(BaseModel):
    """Result of passing an artifact through a quality gate."""

    passed: bool
    score: QualityScore
    threshold: float
    reason: str = ""


# ---------------------------------------------------------------------------
# Rubrics (prompt templates for LLM-as-judge)
# ---------------------------------------------------------------------------

_CODE_RUBRIC = """You are a senior code reviewer. Evaluate the following code artifact on these dimensions.
Score each 0-100. Respond ONLY with valid JSON, no markdown fences.

Dimensions:
1. correctness: Does the code appear logically correct? Are edge cases handled?
2. style: Is the code readable, well-named, properly typed?
3. test_coverage: Does it have or reference tests? Are they meaningful?
4. security: Are there obvious vulnerabilities (injection, hardcoded secrets, unsafe deserialization)?
5. maintainability: Is the code modular, documented, under 500 lines per file?

Response format:
{"dimensions": [{"name": "correctness", "score": N, "feedback": "..."}, ...], "overall": N, "feedback": "summary", "suggestions": ["..."]}

=== ARTIFACT ===
{artifact}

=== CONTEXT ===
Component: {component}
Change type: {change_type}
Description: {description}
"""

_RESEARCH_RUBRIC = """You are a scientific peer reviewer. Evaluate the following research artifact.
Score each 0-100. Respond ONLY with valid JSON, no markdown fences.

Dimensions:
1. claim_support: Are claims backed by evidence or citations?
2. methodology: Is the approach sound and reproducible?
3. novelty: Does this add something new vs existing work?
4. clarity: Is the writing clear, precise, and well-structured?
5. rigor: Are limitations acknowledged? Are results qualified appropriately?

Response format:
{"dimensions": [{"name": "claim_support", "score": N, "feedback": "..."}, ...], "overall": N, "feedback": "summary", "suggestions": ["..."]}

=== ARTIFACT ===
{artifact}

=== CONTEXT ===
{description}
"""

_CONTENT_RUBRIC = """You are a content quality evaluator. Evaluate the following content artifact.
Score each 0-100. Respond ONLY with valid JSON, no markdown fences.

Dimensions:
1. clarity: Is the message clear and well-structured?
2. accuracy: Are factual claims correct?
3. engagement: Would the target audience find this compelling?
4. originality: Does this bring a fresh perspective?
5. actionability: Does it give the reader something concrete to do or think about?

Response format:
{"dimensions": [{"name": "clarity", "score": N, "feedback": "..."}, ...], "overall": N, "feedback": "summary", "suggestions": ["..."]}

=== ARTIFACT ===
{artifact}

=== CONTEXT ===
{description}
"""

_PROPOSAL_RUBRIC = """You are an evolution proposal evaluator for an autonomous agent system.
Evaluate whether this proposal should be promoted. Score each 0-100.
Respond ONLY with valid JSON, no markdown fences.

Dimensions:
1. feasibility: Can this actually be implemented with available resources?
2. impact: If implemented, how much would it improve the system?
3. risk: What's the blast radius if it goes wrong? (100=low risk, 0=high risk)
4. specificity: Is the proposal concrete enough to act on?
5. alignment: Does it serve the system's goals (not just local optimization)?

Response format:
{"dimensions": [{"name": "feasibility", "score": N, "feedback": "..."}, ...], "overall": N, "feedback": "summary", "suggestions": ["..."]}

=== PROPOSAL ===
Component: {component}
Change type: {change_type}
Description: {description}
Diff preview: {diff_preview}
"""

_RUBRICS: dict[QualityDomain, str] = {
    QualityDomain.CODE: _CODE_RUBRIC,
    QualityDomain.RESEARCH: _RESEARCH_RUBRIC,
    QualityDomain.CONTENT: _CONTENT_RUBRIC,
    QualityDomain.PROPOSAL: _PROPOSAL_RUBRIC,
}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    """SHA-256 hash of artifact content for cache keying."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(domain: QualityDomain, artifact_hash: str) -> Path:
    return _CACHE_DIR / domain.value / f"{artifact_hash}.json"


def _load_cached(domain: QualityDomain, artifact_hash: str) -> QualityScore | None:
    """Load a cached quality score, returning None on miss or error."""
    path = _cache_path(domain, artifact_hash)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return QualityScore.model_validate(data)
    except Exception:
        logger.debug("Cache miss (corrupt): %s", path)
        return None


def _save_cache(score: QualityScore) -> None:
    """Persist a quality score to the cache."""
    path = _cache_path(QualityDomain(score.domain), score.artifact_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(score.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Lightweight structural evaluators (no LLM needed)
# ---------------------------------------------------------------------------


def _structural_code_score(code: str) -> QualityScore:
    """Evaluate code quality using pure structural analysis (no LLM).

    Uses AST parsing for Python, heuristics for other languages.
    """
    import ast

    dimensions: list[DimensionScore] = []

    # Try Python AST parse
    try:
        tree = ast.parse(code)
        parse_ok = True
    except SyntaxError:
        parse_ok = False
        tree = None

    # 1. Correctness proxy: does it parse?
    if parse_ok:
        correctness = 80.0  # Parses = baseline correct
    else:
        correctness = 30.0  # Syntax error
    dimensions.append(DimensionScore(
        name="correctness", score=correctness,
        feedback="Parses cleanly" if parse_ok else "Syntax error detected",
    ))

    # 2. Style: docstring ratio + naming
    if tree:
        defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        has_doc = sum(1 for d in defs if ast.get_docstring(d)) if defs else 0
        doc_ratio = has_doc / len(defs) if defs else 0.5
        style_score = 40.0 + doc_ratio * 60.0
    else:
        style_score = 40.0
    dimensions.append(DimensionScore(
        name="style", score=min(100.0, style_score),
        feedback=f"Docstring coverage: {doc_ratio:.0%}" if tree else "Cannot analyze (non-Python or syntax error)",
    ))

    # 3. Test coverage proxy: presence of test-like patterns
    has_tests = bool(re.search(r"(def test_|pytest|unittest|assert )", code))
    test_score = 70.0 if has_tests else 30.0
    dimensions.append(DimensionScore(
        name="test_coverage", score=test_score,
        feedback="Test patterns detected" if has_tests else "No test patterns found",
    ))

    # 4. Security: look for common red flags
    security_flags = []
    if re.search(r"(eval\(|exec\(|os\.system\(|subprocess\.call\()", code):
        security_flags.append("dangerous function call")
    if re.search(r"(password|secret|api_key)\s*=\s*['\"]", code, re.IGNORECASE):
        security_flags.append("potential hardcoded secret")
    if re.search(r"pickle\.loads?\(", code):
        security_flags.append("unsafe deserialization")
    security_score = max(0.0, 100.0 - len(security_flags) * 30.0)
    dimensions.append(DimensionScore(
        name="security", score=security_score,
        feedback="; ".join(security_flags) if security_flags else "No obvious security issues",
    ))

    # 5. Maintainability: line count + nesting depth
    lines = [l for l in code.splitlines() if l.strip()]
    line_count = len(lines)
    if line_count <= 300:
        maint_score = 90.0
    elif line_count <= 500:
        maint_score = 70.0
    else:
        maint_score = max(20.0, 100.0 - (line_count - 500) * 0.1)
    dimensions.append(DimensionScore(
        name="maintainability", score=maint_score,
        feedback=f"{line_count} non-blank lines",
    ))

    total_weight = sum(d.weight for d in dimensions)
    overall = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight > 0 else 0.0

    return QualityScore(
        domain=QualityDomain.CODE,
        overall=round(overall, 1),
        verdict=_verdict_from_score(overall),
        dimensions=dimensions,
        feedback=f"Structural analysis: {line_count} lines, {'parses' if parse_ok else 'syntax errors'}",
        evaluator="structural",
    )


def _structural_proposal_score(
    description: str,
    diff: str,
    component: str,
) -> QualityScore:
    """Evaluate a proposal using heuristic analysis (no LLM)."""
    dimensions: list[DimensionScore] = []

    # 1. Specificity: description length and detail
    word_count = len(description.split())
    if word_count >= 50:
        spec_score = 80.0
    elif word_count >= 20:
        spec_score = 60.0
    else:
        spec_score = 30.0
    dimensions.append(DimensionScore(
        name="specificity", score=spec_score,
        feedback=f"{word_count} words in description",
    ))

    # 2. Feasibility: has a diff (concrete change)
    has_diff = bool(diff.strip())
    diff_lines = len(diff.splitlines()) if has_diff else 0
    if has_diff and diff_lines <= 200:
        feas_score = 85.0
    elif has_diff:
        feas_score = 60.0
    else:
        feas_score = 40.0
    dimensions.append(DimensionScore(
        name="feasibility", score=feas_score,
        feedback=f"Diff: {diff_lines} lines" if has_diff else "No diff provided",
    ))

    # 3. Impact proxy: does description reference metrics or tests
    impact_signals = sum([
        bool(re.search(r"(test|metric|benchmark|performance|fitness)", description, re.I)),
        bool(re.search(r"(fix|bug|regression|error|crash)", description, re.I)),
        bool(re.search(r"(feature|capability|new|add)", description, re.I)),
    ])
    impact_score = 40.0 + impact_signals * 20.0
    dimensions.append(DimensionScore(
        name="impact", score=min(100.0, impact_score),
        feedback=f"{impact_signals}/3 impact signals detected",
    ))

    # 4. Risk: large diffs = more risk
    if diff_lines > 500:
        risk_score = 30.0
    elif diff_lines > 200:
        risk_score = 60.0
    else:
        risk_score = 85.0
    dimensions.append(DimensionScore(
        name="risk", score=risk_score,
        feedback=f"{'High' if risk_score < 50 else 'Moderate' if risk_score < 75 else 'Low'} risk based on diff size",
    ))

    # 5. Alignment: does it reference a component that exists
    alignment_score = 70.0 if component else 40.0
    dimensions.append(DimensionScore(
        name="alignment", score=alignment_score,
        feedback=f"Targets component: {component}" if component else "No component specified",
    ))

    total_weight = sum(d.weight for d in dimensions)
    overall = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight > 0 else 0.0

    return QualityScore(
        domain=QualityDomain.PROPOSAL,
        overall=round(overall, 1),
        verdict=_verdict_from_score(overall),
        dimensions=dimensions,
        feedback=f"Structural proposal analysis: {word_count} word description, {diff_lines} line diff",
        evaluator="structural",
    )


def _verdict_from_score(score: float, threshold: float = _DEFAULT_THRESHOLD) -> QualityVerdict:
    """Map a numeric score to a verdict."""
    if score >= threshold:
        return QualityVerdict.PASS
    elif score >= threshold * 0.75:
        return QualityVerdict.WARN
    return QualityVerdict.FAIL


# ---------------------------------------------------------------------------
# LLM-as-judge evaluator
# ---------------------------------------------------------------------------


def _parse_llm_response(raw: str, domain: QualityDomain) -> QualityScore | None:
    """Parse JSON response from LLM judge into a QualityScore.

    Tolerant of markdown fences and minor formatting issues.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (possibly with language tag)
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM judge response as JSON")
                return None
        else:
            logger.warning("No JSON found in LLM judge response")
            return None

    dimensions = []
    for dim in data.get("dimensions", []):
        dimensions.append(DimensionScore(
            name=dim.get("name", "unknown"),
            score=max(0.0, min(100.0, float(dim.get("score", 0)))),
            feedback=str(dim.get("feedback", "")),
        ))

    overall = float(data.get("overall", 0))
    overall = max(0.0, min(100.0, overall))

    suggestions = data.get("suggestions", [])
    if isinstance(suggestions, str):
        suggestions = [suggestions]

    return QualityScore(
        domain=domain,
        overall=round(overall, 1),
        verdict=_verdict_from_score(overall),
        dimensions=dimensions,
        feedback=str(data.get("feedback", "")),
        improvement_suggestions=suggestions,
        evaluator="llm",
    )


async def _llm_evaluate(
    artifact: str,
    domain: QualityDomain,
    context: dict[str, str],
    provider: Any = None,
    provider_type: ProviderType = ProviderType.OPENROUTER_FREE,
    model: str = "",
) -> QualityScore | None:
    """Run LLM-as-judge evaluation.

    Args:
        artifact: The text artifact to evaluate.
        domain: Which rubric to use.
        context: Template variables for the rubric.
        provider: An LLM provider instance (or ProviderManager).
            If None, falls back to structural evaluation.
        provider_type: Which provider to use for the call.
        model: Model override. Empty string uses provider default.

    Returns:
        QualityScore or None if LLM call fails.
    """
    rubric = _RUBRICS[domain]

    # Truncate artifact for cost control
    truncated = artifact[:_MAX_ARTIFACT_CHARS]
    if len(artifact) > _MAX_ARTIFACT_CHARS:
        truncated += f"\n\n[... truncated, {len(artifact) - _MAX_ARTIFACT_CHARS} chars omitted ...]"

    context["artifact"] = truncated

    # Build prompt from rubric template
    try:
        prompt = rubric.format(**context)
    except KeyError:
        # Fill missing template vars with empty string
        prompt = rubric
        for key, val in context.items():
            prompt = prompt.replace(f"{{{key}}}", val)

    request = LLMRequest(
        model=model or canonical_default_model(ProviderType.OPENROUTER_FREE),
        messages=[{"role": "user", "content": prompt}],
        system="You are a quality evaluation judge. Respond only with valid JSON.",
        max_tokens=1024,
        temperature=0.1,
    )

    start = time.monotonic()
    try:
        if hasattr(provider, "complete") and callable(provider.complete):
            # Could be a ProviderManager or direct LLMProvider
            import inspect
            sig = inspect.signature(provider.complete)
            params = list(sig.parameters.keys())
            if len(params) >= 2 and params[0] != "self":
                # ProviderManager.complete(provider_type, request)
                response: LLMResponse = await provider.complete(provider_type, request)
            elif len(params) >= 2 and params[0] == "self":
                # ProviderManager.complete(provider_type, request)
                # Check if first non-self param expects ProviderType
                first_param = params[1] if len(params) > 1 else params[0]
                if first_param == "provider_type":
                    response = await provider.complete(provider_type, request)
                else:
                    response = await provider.complete(request)
            else:
                response = await provider.complete(request)
        else:
            logger.debug("No LLM provider available, skipping LLM evaluation")
            return None
    except Exception as exc:
        logger.warning("LLM quality evaluation failed: %s", exc)
        return None

    latency = (time.monotonic() - start) * 1000

    result = _parse_llm_response(response.content, domain)
    if result:
        result.model_used = response.model or model
        result.latency_ms = round(latency, 1)

    return result


# ---------------------------------------------------------------------------
# Public Evaluator Classes
# ---------------------------------------------------------------------------


class QualityGate:
    """Base quality gate that combines structural + LLM evaluation.

    Attributes:
        domain: The quality domain this gate evaluates.
        threshold: Score below which artifacts are rejected (0-100).
        use_llm: Whether to attempt LLM-as-judge evaluation.
        provider: LLM provider for judge calls.
        provider_type: Which provider to route to.
        cache_enabled: Whether to cache evaluations.
    """

    def __init__(
        self,
        domain: QualityDomain,
        threshold: float = _DEFAULT_THRESHOLD,
        use_llm: bool = True,
        provider: Any = None,
        provider_type: ProviderType = ProviderType.OPENROUTER_FREE,
        model: str = "",
        cache_enabled: bool = True,
    ) -> None:
        self.domain = domain
        self.threshold = max(0.0, min(100.0, float(threshold)))
        self.use_llm = use_llm
        self.provider = provider
        self.provider_type = provider_type
        self.model = model
        self.cache_enabled = cache_enabled

    async def evaluate(
        self,
        artifact: str,
        context: dict[str, str] | None = None,
    ) -> QualityGateResult:
        """Evaluate an artifact against this gate's rubric.

        Args:
            artifact: The text content to evaluate.
            context: Additional context for the rubric template.

        Returns:
            QualityGateResult with pass/fail, score, and feedback.
        """
        context = context or {}
        artifact_hash = _content_hash(artifact)

        # Check cache
        if self.cache_enabled:
            cached = _load_cached(self.domain, artifact_hash)
            if cached is not None:
                logger.debug("Quality gate cache hit: %s/%s", self.domain.value, artifact_hash)
                return QualityGateResult(
                    passed=cached.overall >= self.threshold,
                    score=cached,
                    threshold=self.threshold,
                    reason="cached evaluation",
                )

        score: QualityScore | None = None

        # Try LLM evaluation first (more nuanced)
        if self.use_llm and self.provider is not None:
            score = await _llm_evaluate(
                artifact=artifact,
                domain=self.domain,
                context=context,
                provider=self.provider,
                provider_type=self.provider_type,
                model=self.model,
            )

        # Fall back to structural evaluation
        if score is None:
            score = self._structural_evaluate(artifact, context)

        score.artifact_hash = artifact_hash

        # Cache the result
        if self.cache_enabled:
            try:
                _save_cache(score)
            except Exception:
                logger.debug("Failed to cache quality score", exc_info=True)

        # Log evaluation
        _log_evaluation(score, self.threshold)

        passed = score.overall >= self.threshold
        reason = ""
        if not passed:
            failing = [d for d in score.dimensions if d.score < self.threshold]
            if failing:
                reason = f"Failed dimensions: {', '.join(f'{d.name}={d.score:.0f}' for d in failing)}"
            else:
                reason = f"Overall score {score.overall:.1f} below threshold {self.threshold:.1f}"

        return QualityGateResult(
            passed=passed,
            score=score,
            threshold=self.threshold,
            reason=reason,
        )

    def _structural_evaluate(
        self,
        artifact: str,
        context: dict[str, str],
    ) -> QualityScore:
        """Domain-specific structural evaluation. Override in subclasses."""
        # Generic: just score on length and structure
        word_count = len(artifact.split())
        score = min(100.0, 30.0 + word_count * 0.5)
        return QualityScore(
            domain=self.domain,
            overall=round(score, 1),
            verdict=_verdict_from_score(score, self.threshold),
            dimensions=[DimensionScore(
                name="substance", score=score,
                feedback=f"{word_count} words",
            )],
            feedback="Generic structural evaluation",
            evaluator="structural",
        )


class CodeQualityGate(QualityGate):
    """Quality gate specialized for code artifacts."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("domain", QualityDomain.CODE)
        super().__init__(**kwargs)

    def _structural_evaluate(
        self,
        artifact: str,
        context: dict[str, str],
    ) -> QualityScore:
        return _structural_code_score(artifact)


class ResearchQualityGate(QualityGate):
    """Quality gate specialized for research artifacts."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("domain", QualityDomain.RESEARCH)
        super().__init__(**kwargs)

    def _structural_evaluate(
        self,
        artifact: str,
        context: dict[str, str],
    ) -> QualityScore:
        dimensions: list[DimensionScore] = []

        # Citation presence
        citation_count = len(re.findall(r"\[[\d,\s]+\]|\(\w+\s+et\s+al\.?,?\s*\d{4}\)", artifact))
        cite_score = min(100.0, 20.0 + citation_count * 15.0)
        dimensions.append(DimensionScore(
            name="claim_support", score=cite_score,
            feedback=f"{citation_count} citation patterns found",
        ))

        # Methodology signals
        method_signals = sum([
            bool(re.search(r"(method|approach|experiment|protocol|procedure)", artifact, re.I)),
            bool(re.search(r"(dataset|corpus|sample|n\s*=\s*\d)", artifact, re.I)),
            bool(re.search(r"(p\s*[<>=]\s*0\.\d|confidence|significant|effect size)", artifact, re.I)),
        ])
        method_score = 30.0 + method_signals * 23.0
        dimensions.append(DimensionScore(
            name="methodology", score=min(100.0, method_score),
            feedback=f"{method_signals}/3 methodology signals",
        ))

        # Clarity: sentence length, structure signals
        sentences = re.split(r"[.!?]+", artifact)
        avg_sentence_len = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        if 10 <= avg_sentence_len <= 25:
            clarity_score = 80.0
        elif avg_sentence_len < 10:
            clarity_score = 60.0
        else:
            clarity_score = max(30.0, 100.0 - (avg_sentence_len - 25) * 2.0)
        dimensions.append(DimensionScore(
            name="clarity", score=clarity_score,
            feedback=f"Avg sentence length: {avg_sentence_len:.0f} words",
        ))

        # Rigor: hedging language (good for research!)
        hedge_count = len(re.findall(
            r"(limitation|caveat|however|although|we note|future work|may not|caution)", artifact, re.I
        ))
        rigor_score = min(100.0, 40.0 + hedge_count * 12.0)
        dimensions.append(DimensionScore(
            name="rigor", score=rigor_score,
            feedback=f"{hedge_count} qualification/limitation markers",
        ))

        # Novelty proxy: presence of "novel", "first", "new", "unlike"
        novelty_markers = len(re.findall(
            r"(novel|first|new approach|unlike|in contrast|we propose|contribution)", artifact, re.I
        ))
        novelty_score = min(100.0, 30.0 + novelty_markers * 15.0)
        dimensions.append(DimensionScore(
            name="novelty", score=novelty_score,
            feedback=f"{novelty_markers} novelty markers",
        ))

        total_weight = sum(d.weight for d in dimensions)
        overall = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight > 0 else 0.0

        return QualityScore(
            domain=QualityDomain.RESEARCH,
            overall=round(overall, 1),
            verdict=_verdict_from_score(overall, self.threshold),
            dimensions=dimensions,
            feedback=f"Structural research analysis: {len(artifact.split())} words, {citation_count} citations",
            evaluator="structural",
        )


class ContentQualityGate(QualityGate):
    """Quality gate specialized for content artifacts."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("domain", QualityDomain.CONTENT)
        super().__init__(**kwargs)

    def _structural_evaluate(
        self,
        artifact: str,
        context: dict[str, str],
    ) -> QualityScore:
        dimensions: list[DimensionScore] = []

        word_count = len(artifact.split())

        # Clarity: readability heuristics
        sentences = re.split(r"[.!?]+", artifact)
        non_empty = [s for s in sentences if s.strip()]
        avg_len = sum(len(s.split()) for s in non_empty) / max(len(non_empty), 1)
        if 8 <= avg_len <= 20:
            clarity = 85.0
        else:
            clarity = max(30.0, 85.0 - abs(avg_len - 15) * 3.0)
        dimensions.append(DimensionScore(
            name="clarity", score=clarity,
            feedback=f"Avg sentence: {avg_len:.0f} words",
        ))

        # Accuracy: presence of specific claims vs vague language
        specific_count = len(re.findall(r"\d+\.?\d*%|\$[\d,.]+|\d{4}", artifact))
        vague_count = len(re.findall(r"(many|some|various|several|often|sometimes)", artifact, re.I))
        accuracy = min(100.0, 50.0 + specific_count * 10.0 - vague_count * 5.0)
        dimensions.append(DimensionScore(
            name="accuracy", score=max(20.0, accuracy),
            feedback=f"{specific_count} specific claims, {vague_count} vague markers",
        ))

        # Engagement: questions, calls to action, hooks
        engagement_signals = sum([
            len(re.findall(r"\?", artifact)) > 0,
            bool(re.search(r"(imagine|consider|think about|here's why|the key)", artifact, re.I)),
            bool(re.search(r"(you|your|we|our)", artifact, re.I)),
        ])
        engagement = 30.0 + engagement_signals * 23.0
        dimensions.append(DimensionScore(
            name="engagement", score=min(100.0, engagement),
            feedback=f"{engagement_signals}/3 engagement signals",
        ))

        # Originality proxy: vocabulary richness
        words = re.findall(r"[a-z]+", artifact.lower())
        unique_ratio = len(set(words)) / max(len(words), 1)
        originality = min(100.0, unique_ratio * 150.0)
        dimensions.append(DimensionScore(
            name="originality", score=originality,
            feedback=f"Vocabulary richness: {unique_ratio:.2f}",
        ))

        # Actionability
        action_signals = len(re.findall(
            r"(step \d|first,|next,|try|start|implement|build|create|use)", artifact, re.I
        ))
        actionability = min(100.0, 30.0 + action_signals * 15.0)
        dimensions.append(DimensionScore(
            name="actionability", score=actionability,
            feedback=f"{action_signals} action markers",
        ))

        total_weight = sum(d.weight for d in dimensions)
        overall = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight > 0 else 0.0

        return QualityScore(
            domain=QualityDomain.CONTENT,
            overall=round(overall, 1),
            verdict=_verdict_from_score(overall, self.threshold),
            dimensions=dimensions,
            feedback=f"Structural content analysis: {word_count} words",
            evaluator="structural",
        )


class ProposalQualityGate(QualityGate):
    """Quality gate specialized for evolution proposals."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("domain", QualityDomain.PROPOSAL)
        super().__init__(**kwargs)

    def _structural_evaluate(
        self,
        artifact: str,
        context: dict[str, str],
    ) -> QualityScore:
        return _structural_proposal_score(
            description=artifact,
            diff=context.get("diff_preview", ""),
            component=context.get("component", ""),
        )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log_evaluation(score: QualityScore, threshold: float) -> None:
    """Persist evaluation to the quality gate log directory."""
    log_dir = _CACHE_DIR / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "id": score.id,
        "domain": score.domain,
        "overall": score.overall,
        "verdict": score.verdict,
        "threshold": threshold,
        "evaluator": score.evaluator,
        "model_used": score.model_used,
        "latency_ms": score.latency_ms,
        "artifact_hash": score.artifact_hash,
        "evaluated_at": score.evaluated_at,
        "dimension_scores": {d.name: d.score for d in score.dimensions},
    }

    log_file = log_dir / "evaluations.jsonl"
    try:
        with open(log_file, "a") as fh:
            fh.write(json.dumps(log_entry) + "\n")
    except Exception:
        logger.debug("Failed to log quality evaluation", exc_info=True)


# ---------------------------------------------------------------------------
# Darwin Engine integration helper
# ---------------------------------------------------------------------------


async def run_quality_gate(
    proposal_description: str,
    proposal_diff: str = "",
    proposal_component: str = "",
    proposal_change_type: str = "",
    code: str | None = None,
    domain: QualityDomain | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
    provider: Any = None,
    provider_type: ProviderType = ProviderType.OPENROUTER_FREE,
    use_llm: bool = True,
    cache_enabled: bool = True,
) -> QualityGateResult:
    """Convenience function: run a quality gate on a proposal or artifact.

    Auto-detects domain from artifact content if not specified.
    Used by DarwinEngine to gate proposals after fitness evaluation.

    Args:
        proposal_description: The proposal description or artifact text.
        proposal_diff: The diff (for proposal/code domains).
        proposal_component: Target component path.
        proposal_change_type: mutation/crossover/ablation.
        code: Explicit code content (uses code gate instead of proposal gate).
        domain: Force a specific quality domain.
        threshold: Minimum score to pass (0-100).
        provider: LLM provider for judge calls.
        provider_type: Which provider to use.
        use_llm: Whether to attempt LLM evaluation.
        cache_enabled: Whether to use evaluation cache.

    Returns:
        QualityGateResult with pass/fail decision, score, and feedback.
    """
    # Auto-detect domain
    if domain is None:
        if code:
            domain = QualityDomain.CODE
        else:
            domain = QualityDomain.PROPOSAL

    # Select gate class
    gate_cls: type[QualityGate]
    if domain == QualityDomain.CODE:
        gate_cls = CodeQualityGate
    elif domain == QualityDomain.RESEARCH:
        gate_cls = ResearchQualityGate
    elif domain == QualityDomain.CONTENT:
        gate_cls = ContentQualityGate
    else:
        gate_cls = ProposalQualityGate

    gate = gate_cls(
        threshold=threshold,
        use_llm=use_llm,
        provider=provider,
        provider_type=provider_type,
        cache_enabled=cache_enabled,
    )

    # Choose artifact and context
    if code:
        artifact = code
        context = {
            "component": proposal_component,
            "change_type": proposal_change_type,
            "description": proposal_description,
        }
    else:
        artifact = proposal_description
        context = {
            "component": proposal_component,
            "change_type": proposal_change_type,
            "description": proposal_description,
            "diff_preview": proposal_diff[:2000] if proposal_diff else "",
        }

    return await gate.evaluate(artifact, context)
