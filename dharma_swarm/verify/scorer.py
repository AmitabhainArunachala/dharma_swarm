"""Score code diffs against thinkodynamic quality dimensions.

Heuristic-only scorer (no LLM calls) for the base path.
An LLM-enhanced scorer is available via score_diff_with_llm().

Dimensions:
    correctness  - ratio of lines with tests / total lines changed
    clarity      - line length, magic numbers, meaningful names
    safety       - common antipatterns (eval, exec, hardcoded secrets)
    completeness - docstrings, error handling, type hints
    efficiency   - O(n^2) patterns, unnecessary imports
    governance   - telos gate compliance (protected file touches)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


# Protected files from dharma_swarm governance layer
_PROTECTED_FILES = frozenset({
    "telos_gates.py",
    "dharma_kernel.py",
    "evolution.py",
    "config.py",
})


@dataclass
class FileScore:
    """Per-file thinkodynamic score payload used by the verify API."""

    path: str = ""
    semantic_density: float = 0.0
    recursive_depth: float = 0.0
    witness_quality: float = 0.0
    swabhaav_ratio: float = 0.0
    holographic_efficiency: float = 0.0
    telos_alignment: float = 0.0
    composite: float = 0.0
    risk_level: str = "low"
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        """Pydantic-style compatibility helper used by API tests."""
        return asdict(self)


FileDiff = FileScore


@dataclass
class DiffScore:
    """Aggregate score for a code diff.

    Attributes:
        overall: Weighted composite score in [0.0, 1.0].
        dimensions: Per-dimension scores, each in [0.0, 1.0].
        issues: Problems detected in the diff.
        suggestions: Actionable improvement recommendations.
    """

    files: list[FileScore] = field(default_factory=list)
    overall_composite: float = 0.0
    overall_risk: str = ""
    total_files: int = 0
    high_risk_files: int = 0
    summary: str = ""
    comprehension_debt: float | None = None
    overall: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Keep legacy and current score fields in sync."""
        if self.overall == 0.0 and self.overall_composite != 0.0:
            self.overall = self.overall_composite
        else:
            self.overall_composite = self.overall

        if not self.overall_risk:
            self.overall_risk = _risk_level_from_issues(self.overall, self.issues)

        if self.total_files == 0:
            self.total_files = len(self.files)

        if self.high_risk_files == 0 and self.files:
            self.high_risk_files = sum(
                1 for file_score in self.files if file_score.risk_level in {"high", "critical"}
            )

        if self.summary == "":
            self.summary = (
                f"{self.total_files} files scored. "
                f"Avg quality: {self.overall:.2f}. Risk: {self.overall_risk or 'low'}."
            )

        if self.comprehension_debt is None:
            self.comprehension_debt = round(1.0 - self.overall, 4)

    def model_dump(self) -> dict[str, Any]:
        """Pydantic-style compatibility helper used by API tests."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Dimension weights
# ---------------------------------------------------------------------------

_DIMENSION_WEIGHTS: dict[str, float] = {
    "correctness": 0.25,
    "clarity": 0.15,
    "safety": 0.20,
    "completeness": 0.15,
    "efficiency": 0.10,
    "governance": 0.15,
}


def _risk_level_from_issues(overall: float, issues: list[str]) -> str:
    """Classify overall diff risk for the API-facing compatibility payload."""
    joined = " ".join(issues).upper()
    if "CRITICAL" in joined:
        return "high"
    if "WARNING" in joined or overall < 0.5:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Diff parsing helpers
# ---------------------------------------------------------------------------

def _parse_diff(diff_text: str) -> dict[str, Any]:
    """Extract structured info from a unified diff string.

    Returns:
        Dict with keys: files_changed, lines_added, lines_removed,
        added_content, functions_modified, raw_additions.
    """
    files_changed: list[str] = []
    lines_added: int = 0
    lines_removed: int = 0
    added_lines: list[str] = []
    functions_modified: list[str] = []

    current_file = ""
    for line in diff_text.splitlines():
        # File header
        m = re.match(r"^diff --git a/(.*?) b/(.*?)$", line)
        if m:
            current_file = m.group(2)
            if current_file not in files_changed:
                files_changed.append(current_file)
            continue

        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            current_file = m.group(1)
            if current_file not in files_changed:
                files_changed.append(current_file)
            continue

        if line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
            content = line[1:]
            added_lines.append(content)
            # Detect function/method definitions
            func_match = re.match(r"^\s*(?:def|async def|class)\s+(\w+)", content)
            if func_match:
                functions_modified.append(func_match.group(1))
        elif line.startswith("-") and not line.startswith("---"):
            lines_removed += 1

    return {
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "added_content": "\n".join(added_lines),
        "functions_modified": functions_modified,
        "raw_additions": added_lines,
    }


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_correctness(parsed: dict[str, Any], context: str) -> tuple[float, list[str], list[str]]:
    """Score based on presence of test code relative to implementation."""
    issues: list[str] = []
    suggestions: list[str] = []
    content = parsed["added_content"]
    lines = parsed["raw_additions"]

    if not lines:
        return 0.5, issues, suggestions

    test_lines = sum(
        1 for ln in lines
        if re.search(r"\b(assert|pytest|unittest|mock|patch|def test_)\b", ln)
    )
    total = len(lines)
    ratio = test_lines / total if total > 0 else 0.0

    # Check if any test file is in the diff
    has_test_file = any("test" in f.lower() for f in parsed["files_changed"])

    score = min(ratio * 3.0, 0.6)  # Test lines ratio contributes up to 0.6
    if has_test_file:
        score += 0.3
    if re.search(r"\bdef test_\w+", content):
        score += 0.1

    score = min(score, 1.0)

    if score < 0.3:
        issues.append("No tests accompany this change")
        suggestions.append("Add tests covering the new/modified code paths")

    return round(score, 4), issues, suggestions


def _score_clarity(parsed: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score based on line length, magic numbers, and naming."""
    issues: list[str] = []
    suggestions: list[str] = []
    lines = parsed["raw_additions"]

    if not lines:
        return 0.8, issues, suggestions

    # Line length check (target < 88 chars)
    long_lines = sum(1 for ln in lines if len(ln) > 88)
    long_ratio = long_lines / len(lines) if lines else 0.0
    length_score = max(0.0, 1.0 - long_ratio * 2.0)

    if long_ratio > 0.2:
        issues.append(f"{long_lines} lines exceed 88 characters")
        suggestions.append("Break long lines for readability")

    # Magic number check (bare numeric literals outside common ones)
    magic_pattern = re.compile(
        r"(?<![a-zA-Z_])(?<!\.)\b(\d{2,})\b(?!\s*[=:]\s*#)"
    )
    content = parsed["added_content"]
    magic_numbers = [
        m.group(1) for m in magic_pattern.finditer(content)
        if m.group(1) not in {"10", "16", "32", "64", "100", "128", "256", "512", "1024"}
    ]
    magic_penalty = min(len(magic_numbers) * 0.05, 0.3)

    if magic_numbers:
        suggestions.append("Extract magic numbers into named constants")

    # Single-char variable names (excluding i, j, k, x, y, _, e, f)
    short_var_pattern = re.compile(r"\b([a-zA-Z])\s*=")
    short_vars = {
        m.group(1) for m in short_var_pattern.finditer(content)
        if m.group(1) not in {"i", "j", "k", "x", "y", "z", "_", "e", "f", "s", "n", "m"}
    }
    naming_penalty = min(len(short_vars) * 0.05, 0.2)

    score = max(0.0, length_score - magic_penalty - naming_penalty)
    return round(score, 4), issues, suggestions


def _score_safety(parsed: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score based on dangerous patterns: eval, exec, subprocess, secrets."""
    issues: list[str] = []
    suggestions: list[str] = []
    content = parsed["added_content"]

    if not content.strip():
        return 1.0, issues, suggestions

    penalties = 0.0

    # eval / exec
    if re.search(r"\beval\s*\(", content):
        issues.append("CRITICAL: Use of eval() is a code injection risk")
        suggestions.append("Replace eval() with ast.literal_eval() or a safe parser")
        penalties += 0.4

    if re.search(r"\bexec\s*\(", content):
        issues.append("CRITICAL: Use of exec() is a code injection risk")
        suggestions.append("Replace exec() with explicit function dispatch")
        penalties += 0.4

    # subprocess with shell=True
    if re.search(r"subprocess\.\w+\([^)]*shell\s*=\s*True", content):
        issues.append("WARNING: subprocess with shell=True is a command injection risk")
        suggestions.append("Use subprocess with shell=False and pass args as a list")
        penalties += 0.25

    # Hardcoded secrets
    secret_patterns = [
        (r'(?i)(api[_-]?key|secret|password|token|credential)\s*=\s*["\'][^"\']{8,}["\']',
         "Possible hardcoded secret/credential"),
        (r'(?i)Bearer\s+[A-Za-z0-9\-_.]{20,}', "Possible hardcoded bearer token"),
        (r'sk-[A-Za-z0-9]{20,}', "Possible OpenAI API key"),
        (r'ghp_[A-Za-z0-9]{36}', "Possible GitHub personal access token"),
    ]
    for pattern, msg in secret_patterns:
        if re.search(pattern, content):
            issues.append(f"CRITICAL: {msg}")
            suggestions.append("Move secrets to environment variables or a vault")
            penalties += 0.35
            break  # One secret finding is enough to penalize

    # Broad exception handling
    if re.search(r"except\s*:", content):
        issues.append("Bare except clause catches all exceptions including SystemExit")
        suggestions.append("Catch specific exceptions (e.g., except ValueError:)")
        penalties += 0.1

    score = max(0.0, 1.0 - penalties)
    return round(score, 4), issues, suggestions


def _score_completeness(parsed: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score based on docstrings, error handling, and type hints."""
    issues: list[str] = []
    suggestions: list[str] = []
    content = parsed["added_content"]
    funcs = parsed["functions_modified"]

    if not content.strip():
        return 0.5, issues, suggestions

    score = 0.0
    checks = 0

    # Docstrings
    has_docstrings = bool(re.search(r'""".*?"""|\'\'\'.*?\'\'\'', content, re.DOTALL))
    checks += 1
    if has_docstrings:
        score += 1.0
    else:
        if funcs:
            issues.append("No docstrings found in new functions/classes")
            suggestions.append("Add Google-style docstrings to public functions")

    # Type hints
    has_type_hints = bool(re.search(r"def\s+\w+\([^)]*:\s*\w+", content))
    has_return_type = bool(re.search(r"\)\s*->\s*\w+", content))
    checks += 1
    if has_type_hints or has_return_type:
        score += 1.0 if (has_type_hints and has_return_type) else 0.5
    else:
        if funcs:
            suggestions.append("Add type hints to function parameters and return types")

    # Error handling
    has_error_handling = bool(re.search(r"\b(try|raise|except)\b", content))
    checks += 1
    if has_error_handling:
        score += 1.0
    else:
        if len(parsed["raw_additions"]) > 20:
            suggestions.append("Consider adding error handling for edge cases")

    final = score / checks if checks > 0 else 0.5
    return round(final, 4), issues, suggestions


def _score_efficiency(parsed: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score based on algorithmic complexity and import hygiene."""
    issues: list[str] = []
    suggestions: list[str] = []
    content = parsed["added_content"]

    if not content.strip():
        return 0.8, issues, suggestions

    penalties = 0.0

    # Nested loops (potential O(n^2))
    nested_loop_pattern = re.compile(
        r"for\s+\w+\s+in\b.*:\s*\n(?:\s+.*\n)*?\s+for\s+\w+\s+in\b",
        re.MULTILINE,
    )
    if nested_loop_pattern.search(content):
        issues.append("Nested loops detected (potential O(n^2) complexity)")
        suggestions.append("Consider using sets, dicts, or itertools for better complexity")
        penalties += 0.2

    # Star imports
    if re.search(r"from\s+\S+\s+import\s+\*", content):
        issues.append("Star import pollutes namespace")
        suggestions.append("Import specific names instead of using wildcard imports")
        penalties += 0.15

    # Repeated string concatenation in loops
    if re.search(r"for\s+.*:.*\n\s+\w+\s*\+?=\s*[\"']", content, re.MULTILINE):
        suggestions.append("Use str.join() or io.StringIO instead of repeated string concatenation")
        penalties += 0.1

    score = max(0.0, 1.0 - penalties)
    return round(score, 4), issues, suggestions


def _score_governance(parsed: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Score telos gate compliance: check if protected files are modified."""
    issues: list[str] = []
    suggestions: list[str] = []
    files = parsed["files_changed"]

    touched_protected = [
        f for f in files
        if any(f.endswith(p) for p in _PROTECTED_FILES)
    ]

    if touched_protected:
        issues.append(
            f"Protected files modified: {', '.join(touched_protected)} "
            f"-- requires explicit governance review"
        )
        suggestions.append("Changes to governance files need manual approval from a maintainer")
        return 0.2, issues, suggestions

    return 1.0, issues, suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_diff(diff_text: str, context: str = "") -> DiffScore:
    """Score a unified diff string against quality dimensions.

    Parses the diff to extract files changed, lines added/removed,
    and functions modified. Then scores each dimension heuristically.

    Args:
        diff_text: Unified diff string (output of git diff).
        context: Optional additional context (PR description, commit messages).

    Returns:
        DiffScore with overall weighted score, per-dimension breakdown,
        issues found, and improvement suggestions.
    """
    if not diff_text.strip():
        return DiffScore(
            overall=0.0,
            dimensions={d: 0.0 for d in _DIMENSION_WEIGHTS},
            issues=["Empty diff provided"],
            suggestions=[],
        )

    parsed = _parse_diff(diff_text)
    dimensions: dict[str, float] = {}
    all_issues: list[str] = []
    all_suggestions: list[str] = []

    # Score each dimension
    scorers = {
        "correctness": lambda: _score_correctness(parsed, context),
        "clarity": lambda: _score_clarity(parsed),
        "safety": lambda: _score_safety(parsed),
        "completeness": lambda: _score_completeness(parsed),
        "efficiency": lambda: _score_efficiency(parsed),
        "governance": lambda: _score_governance(parsed),
    }

    for dim_name, scorer_fn in scorers.items():
        dim_score, dim_issues, dim_suggestions = scorer_fn()
        dimensions[dim_name] = dim_score
        all_issues.extend(dim_issues)
        all_suggestions.extend(dim_suggestions)

    # Weighted average
    overall = sum(
        dimensions[d] * _DIMENSION_WEIGHTS[d]
        for d in _DIMENSION_WEIGHTS
    )
    overall = round(min(max(overall, 0.0), 1.0), 4)

    overall_risk = _risk_level_from_issues(overall, all_issues)
    file_scores = [
        FileScore(
            path=path,
            semantic_density=dimensions.get("clarity", 0.0),
            recursive_depth=dimensions.get("correctness", 0.0),
            witness_quality=dimensions.get("safety", 0.0),
            swabhaav_ratio=dimensions.get("completeness", 0.0),
            holographic_efficiency=dimensions.get("efficiency", 0.0),
            telos_alignment=dimensions.get("governance", 0.0),
            composite=overall,
            risk_level=overall_risk,
            issues=list(all_issues),
            suggestions=list(all_suggestions),
        )
        for path in parsed["files_changed"]
    ]

    return DiffScore(
        files=file_scores,
        overall_composite=overall,
        overall_risk=overall_risk,
        total_files=len(file_scores),
        high_risk_files=sum(
            1 for file_score in file_scores if file_score.risk_level in {"high", "critical"}
        ),
        summary=(
            f"{len(file_scores)} files scored. "
            f"Avg quality: {overall:.2f}. Risk: {overall_risk}."
        ),
        comprehension_debt=round(1.0 - overall, 4),
        overall=overall,
        dimensions=dimensions,
        issues=all_issues,
        suggestions=all_suggestions,
    )


def score_diff_with_llm(
    diff_text: str,
    context: str,
    provider_fn: Callable[[str], str],
) -> DiffScore:
    """Score a diff using an LLM for deeper analysis.

    Sends the diff and a scoring rubric to the LLM, parses the
    structured response. Falls back to the heuristic scorer on failure.

    Args:
        diff_text: Unified diff string.
        context: PR description or commit messages for context.
        provider_fn: Callable that takes a prompt string and returns
            the LLM's response string.

    Returns:
        DiffScore with LLM-enhanced analysis.
    """
    rubric = (
        "Score this code diff on 6 dimensions (each 0.0-1.0):\n"
        "1. correctness - Does the code do what it claims? Are there tests?\n"
        "2. clarity - Is the code readable, well-named, properly formatted?\n"
        "3. safety - Are there injection risks, hardcoded secrets, unsafe patterns?\n"
        "4. completeness - Docstrings, type hints, error handling present?\n"
        "5. efficiency - Reasonable algorithmic complexity? Clean imports?\n"
        "6. governance - Does it touch protected/governance files?\n\n"
        "Respond in this exact format (one line per dimension):\n"
        "correctness: <score>\n"
        "clarity: <score>\n"
        "safety: <score>\n"
        "completeness: <score>\n"
        "efficiency: <score>\n"
        "governance: <score>\n"
        "issues: <comma-separated list>\n"
        "suggestions: <comma-separated list>\n\n"
        f"Context: {context}\n\n"
        f"Diff:\n{diff_text[:4000]}"
    )

    try:
        response = provider_fn(rubric)
        return _parse_llm_response(response)
    except Exception:
        # Fall back to heuristic scorer
        return score_diff(diff_text, context)


def _parse_llm_response(response: str) -> DiffScore:
    """Parse the structured LLM response into a DiffScore."""
    dimensions: dict[str, float] = {}
    issues: list[str] = []
    suggestions: list[str] = []

    for line in response.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key in _DIMENSION_WEIGHTS:
            try:
                score = float(value)
                dimensions[key] = min(max(score, 0.0), 1.0)
            except ValueError:
                pass
        elif key == "issues":
            issues = [i.strip() for i in value.split(",") if i.strip()]
        elif key == "suggestions":
            suggestions = [s.strip() for s in value.split(",") if s.strip()]

    # Fill missing dimensions with 0.5
    for dim in _DIMENSION_WEIGHTS:
        if dim not in dimensions:
            dimensions[dim] = 0.5

    overall = sum(
        dimensions[d] * _DIMENSION_WEIGHTS[d]
        for d in _DIMENSION_WEIGHTS
    )
    overall = round(min(max(overall, 0.0), 1.0), 4)

    return DiffScore(
        overall=overall,
        dimensions=dimensions,
        issues=issues,
        suggestions=suggestions,
    )
