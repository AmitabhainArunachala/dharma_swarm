"""Tests for dharma_swarm.elegance -- code elegance evaluator."""

from dharma_swarm.elegance import (
    EleganceScore,
    evaluate_diff_elegance,
    evaluate_elegance,
)


# --- Basic scoring ---


def test_simple_function_scores_well():
    """A clean, documented one-liner should score high."""
    code = '''
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"
'''
    score = evaluate_elegance(code)
    assert score.overall > 0.7
    assert score.cyclomatic_complexity >= 1
    assert score.max_nesting_depth >= 1  # FunctionDef itself is one level
    assert score.docstring_ratio == 1.0
    assert score.naming_score == 1.0


def test_multiple_simple_functions():
    """Several small, documented functions should score high overall."""
    code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b

class MathHelper:
    """Collection of math utilities."""
    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b
'''
    score = evaluate_elegance(code)
    assert score.overall > 0.7
    assert score.docstring_ratio == 1.0
    assert score.naming_score == 1.0


# --- Complexity and nesting ---


def test_deeply_nested_code_has_high_complexity():
    """Deeply nested control flow should yield high complexity and depth."""
    code = '''
def nightmare(data):
    for item in data:
        if item > 0:
            for sub in item:
                if sub > 10:
                    while sub > 0:
                        if sub % 2 == 0:
                            try:
                                process(sub)
                            except Exception:
                                if recover(sub):
                                    pass
                        sub -= 1
'''
    score = evaluate_elegance(code)
    assert score.cyclomatic_complexity > 5
    assert score.max_nesting_depth >= 5
    # Overall should be lower than simple code.
    assert score.overall < 0.8


def test_boolean_operators_add_complexity():
    """Each `and`/`or` adds a decision point."""
    code = '''
def check(a, b, c, d):
    if a and b and c or d:
        return True
    return False
'''
    score = evaluate_elegance(code)
    # `and b`, `and c` = 2, `or d` = 1, plus If = 1, base = 1 -> >= 5
    assert score.cyclomatic_complexity >= 5


# --- Docstring detection ---


def test_docstring_detection_present():
    """Functions with docstrings should give ratio 1.0."""
    code = '''
def foo():
    """Has a docstring."""
    pass

class Bar:
    """Also documented."""
    def baz(self):
        """All three documented."""
        pass
'''
    score = evaluate_elegance(code)
    assert score.docstring_ratio == 1.0


def test_docstring_detection_missing():
    """Functions without docstrings should lower the ratio."""
    code = '''
def foo():
    pass

def bar():
    pass

def baz():
    """Only one documented."""
    pass
'''
    score = evaluate_elegance(code)
    # 1 out of 3 has a docstring.
    assert abs(score.docstring_ratio - 1.0 / 3.0) < 0.01


def test_async_function_docstring():
    """AsyncFunctionDef nodes should be checked for docstrings too."""
    code = '''
async def fetch(url: str) -> str:
    """Fetch a URL."""
    return ""

async def process():
    pass
'''
    score = evaluate_elegance(code)
    assert abs(score.docstring_ratio - 0.5) < 0.01


# --- Naming conventions ---


def test_naming_snake_case_functions():
    """snake_case function names should score 1.0."""
    code = '''
def my_function():
    pass

def another_one():
    pass
'''
    score = evaluate_elegance(code)
    assert score.naming_score == 1.0


def test_naming_pascal_case_classes():
    """PascalCase class names should score 1.0."""
    code = '''
class MyClass:
    pass

class AnotherWidget:
    pass
'''
    score = evaluate_elegance(code)
    assert score.naming_score == 1.0


def test_naming_bad_conventions():
    """Non-conventional names should lower the naming score."""
    code = '''
class bad_class:
    pass

def BadFunction():
    pass

class another_bad:
    pass
'''
    score = evaluate_elegance(code)
    # None of these follow conventions.
    assert score.naming_score == 0.0


def test_naming_mixed_conventions():
    """A mix of correct and incorrect names should give a partial score."""
    code = '''
class GoodClass:
    pass

class bad_class:
    pass

def good_function():
    pass

def BadFunction():
    pass
'''
    score = evaluate_elegance(code)
    # 2 correct out of 4.
    assert abs(score.naming_score - 0.5) < 0.01


# --- Edge cases ---


def test_empty_code():
    """Empty string should not crash and should score 0 (no code to evaluate)."""
    score = evaluate_elegance("")
    assert score.overall == 0.0
    assert score.line_count == 0


def test_whitespace_only():
    """Whitespace-only code is treated as empty — scores 0."""
    score = evaluate_elegance("   \n\n  \t  \n")
    assert score.overall == 0.0
    assert score.line_count == 0


def test_syntax_error_code():
    """Code with syntax errors should not crash and should score 0."""
    score = evaluate_elegance("def broken(\n    x = ")
    assert score.overall == 0.0
    assert score.docstring_ratio == 0.0
    assert score.naming_score == 0.0


def test_no_functions_or_classes():
    """Top-level code with no defs should give full docstring/naming ratios."""
    code = '''
x = 1
y = 2
z = x + y
print(z)
'''
    score = evaluate_elegance(code)
    # No functions/classes to judge.
    assert score.docstring_ratio == 1.0
    assert score.naming_score == 1.0
    assert score.overall > 0.5


# --- Diff comparison ---


def test_diff_improvement():
    """Improving code should report improved=True with positive delta."""
    old = '''
def f():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        pass
'''
    new = '''
def process():
    """Do processing."""
    return 42
'''
    result = evaluate_diff_elegance(old, new)
    assert isinstance(result["before"], EleganceScore)
    assert isinstance(result["after"], EleganceScore)
    assert result["improved"] is True
    assert result["delta"] > 0


def test_diff_degradation():
    """Making code worse should report improved=False with negative delta."""
    old = '''
def clean():
    """A clean function."""
    return 1
'''
    new = '''
def a():
    if True:
        for x in range(10):
            while x > 0:
                try:
                    if x and x:
                        pass
                except:
                    pass
                x -= 1
'''
    result = evaluate_diff_elegance(old, new)
    assert result["improved"] is False
    assert result["delta"] < 0


def test_diff_same_code():
    """Identical before/after should give delta=0 and improved=False."""
    code = '''
def same():
    """Same."""
    return True
'''
    result = evaluate_diff_elegance(code, code)
    assert result["delta"] == 0.0
    assert result["improved"] is False


# --- Model validation ---


def test_elegance_score_json_roundtrip():
    """EleganceScore should survive Pydantic JSON serialisation."""
    score = evaluate_elegance("x = 1")
    data = score.model_dump_json()
    restored = EleganceScore.model_validate_json(data)
    assert restored.overall == score.overall
    assert restored.line_count == score.line_count


def test_elegance_score_clamped():
    """Overall field must be between 0 and 1."""
    score = EleganceScore(
        cyclomatic_complexity=0,
        max_nesting_depth=0,
        line_count=0,
        docstring_ratio=1.0,
        naming_score=1.0,
        overall=0.95,
    )
    assert 0.0 <= score.overall <= 1.0


# --- Line counting ---


def test_line_count_excludes_blanks():
    """Line count should exclude blank lines."""
    code = '''

def foo():

    pass

'''
    score = evaluate_elegance(code)
    # "def foo():" and "pass" are the non-blank lines.
    assert score.line_count == 2
