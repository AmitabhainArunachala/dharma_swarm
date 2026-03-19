"""Code elegance evaluator for DHARMA SWARM.

Pure-function module that scores Python code on structural quality metrics
using only the `ast` standard library module. No I/O, no async -- this is
a standalone analysis tool.

Metrics:
    - Cyclomatic complexity (decision-point count)
    - Maximum nesting depth
    - Line count
    - Docstring ratio (fraction of defs/classes with docstrings)
    - Naming score (snake_case functions, PascalCase classes)
    - Overall weighted score (0-1, higher is more elegant)
"""

from __future__ import annotations

import ast
import re
from typing import Any

from pydantic import BaseModel, Field


# === Scoring Weights ===

_WEIGHTS: dict[str, float] = {
    "complexity": 0.25,
    "nesting": 0.20,
    "line_count": 0.10,
    "docstring_ratio": 0.25,
    "naming_score": 0.20,
}

# Normalisation anchors -- code at or beyond these thresholds scores 0.0
# for that dimension.
_MAX_COMPLEXITY: int = 50
_MAX_NESTING: int = 10
_MAX_LINES: int = 500


# === Model ===


class EleganceScore(BaseModel):
    """Result of evaluating a single code snippet for elegance."""

    cyclomatic_complexity: float = Field(
        description="Total cyclomatic complexity (decision points)."
    )
    max_nesting_depth: int = Field(
        description="Deepest nesting level found in the AST."
    )
    line_count: int = Field(
        description="Number of non-blank source lines."
    )
    docstring_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of function/class defs that have a docstring.",
    )
    naming_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of names following Python conventions.",
    )
    overall: float = Field(
        ge=0.0,
        le=1.0,
        description="Weighted combination normalised to 0-1 (higher = more elegant).",
    )


# === AST Visitors ===


class _ComplexityVisitor(ast.NodeVisitor):
    """Count cyclomatic-complexity decision points in an AST."""

    def __init__(self) -> None:
        self.complexity: int = 1  # base path

    # Each of these adds a branch.
    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        # `a and b and c` has 2 decision points (len(values) - 1).
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.complexity += 1
        self.complexity += len(node.ifs)
        self.generic_visit(node)


class _NestingVisitor(ast.NodeVisitor):
    """Walk the AST tracking maximum nesting depth.

    Nesting is incremented for compound statements that introduce a new
    indentation level: If, For, While, With, Try, FunctionDef,
    AsyncFunctionDef, ClassDef.
    """

    _NESTING_NODES: frozenset[type] = frozenset({
        ast.If,
        ast.For,
        ast.While,
        ast.With,
        ast.Try,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    })

    # Python 3.11+ adds ast.TryStar for `except*`.
    if hasattr(ast, "TryStar"):
        _NESTING_NODES = _NESTING_NODES | {ast.TryStar}

    def __init__(self) -> None:
        self.max_depth: int = 0
        self._current_depth: int = 0

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) in self._NESTING_NODES:
            self._current_depth += 1
            if self._current_depth > self.max_depth:
                self.max_depth = self._current_depth
            super().generic_visit(node)
            self._current_depth -= 1
        else:
            super().generic_visit(node)


# === Naming helpers ===

_SNAKE_CASE_RE = re.compile(r"^_*[a-z][a-z0-9_]*$")
_PASCAL_CASE_RE = re.compile(r"^_*[A-Z][a-zA-Z0-9]*$")
_DUNDER_RE = re.compile(r"^__[a-z][a-z0-9_]*__$")


def _is_snake_case(name: str) -> bool:
    """Return True if *name* follows snake_case (or is a dunder)."""
    if _DUNDER_RE.match(name):
        return True
    return bool(_SNAKE_CASE_RE.match(name))


def _is_pascal_case(name: str) -> bool:
    """Return True if *name* follows PascalCase."""
    return bool(_PASCAL_CASE_RE.match(name))


# === Core logic ===


def _count_complexity(tree: ast.Module) -> int:
    visitor = _ComplexityVisitor()
    visitor.visit(tree)
    return visitor.complexity


def _max_nesting(tree: ast.Module) -> int:
    visitor = _NestingVisitor()
    visitor.visit(tree)
    return visitor.max_depth


def _count_lines(code: str) -> int:
    """Count non-blank lines."""
    return sum(1 for line in code.splitlines() if line.strip())


def _docstring_ratio(tree: ast.Module) -> float:
    """Fraction of FunctionDef / AsyncFunctionDef / ClassDef nodes with docstrings."""
    total = 0
    with_docstring = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            total += 1
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                with_docstring += 1
    if total == 0:
        return 1.0  # No defs => nothing to document; full score.
    return with_docstring / total


def _naming_score(tree: ast.Module) -> float:
    """Fraction of function/class names that follow Python conventions.

    Functions and methods: snake_case (or dunder).
    Classes: PascalCase.
    """
    total = 0
    conforming = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            if _is_snake_case(node.name):
                conforming += 1
        elif isinstance(node, ast.ClassDef):
            total += 1
            if _is_pascal_case(node.name):
                conforming += 1
    if total == 0:
        return 1.0  # No names to judge.
    return conforming / total


def _normalise(value: float, maximum: float) -> float:
    """Map *value* from [0, maximum] to [1.0, 0.0] (lower raw value = better)."""
    if maximum <= 0:
        return 1.0
    return max(0.0, 1.0 - value / maximum)


def _compute_overall(
    complexity: float,
    nesting: int,
    lines: int,
    doc_ratio: float,
    naming: float,
) -> float:
    """Weighted combination of normalised sub-scores."""
    scores: dict[str, float] = {
        "complexity": _normalise(complexity, _MAX_COMPLEXITY),
        "nesting": _normalise(nesting, _MAX_NESTING),
        "line_count": _normalise(lines, _MAX_LINES),
        "docstring_ratio": doc_ratio,
        "naming_score": naming,
    }
    total = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS)
    return round(max(0.0, min(1.0, total)), 4)


# === Public API ===


def evaluate_elegance(code: str) -> EleganceScore:
    """Evaluate the elegance of a Python code string.

    Args:
        code: Python source code to analyse.

    Returns:
        An ``EleganceScore`` with all sub-metrics and an overall 0-1 score.

    Raises:
        Nothing -- syntax errors and empty strings are handled gracefully.
    """
    if not code or not code.strip():
        return EleganceScore(
            cyclomatic_complexity=0,
            max_nesting_depth=0,
            line_count=0,
            docstring_ratio=0.0,
            naming_score=0.0,
            overall=0.0,
        )

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Unparseable code gets the worst possible score.
        lines = _count_lines(code)
        return EleganceScore(
            cyclomatic_complexity=0,
            max_nesting_depth=0,
            line_count=lines,
            docstring_ratio=0.0,
            naming_score=0.0,
            overall=0.0,
        )

    complexity = _count_complexity(tree)
    nesting = _max_nesting(tree)
    lines = _count_lines(code)
    doc_ratio = _docstring_ratio(tree)
    naming = _naming_score(tree)
    overall = _compute_overall(complexity, nesting, lines, doc_ratio, naming)

    return EleganceScore(
        cyclomatic_complexity=complexity,
        max_nesting_depth=nesting,
        line_count=lines,
        docstring_ratio=doc_ratio,
        naming_score=naming,
        overall=overall,
    )


def evaluate_diff_elegance(
    old_code: str,
    new_code: str,
) -> dict[str, Any]:
    """Compare elegance before and after a code change.

    Args:
        old_code: The original Python source.
        new_code: The modified Python source.

    Returns:
        A dict with keys ``before``, ``after`` (``EleganceScore``),
        ``improved`` (bool), and ``delta`` (float, positive = improvement).
    """
    before = evaluate_elegance(old_code)
    after = evaluate_elegance(new_code)
    delta = round(after.overall - before.overall, 4)
    return {
        "before": before,
        "after": after,
        "improved": delta > 0,
        "delta": delta,
    }
