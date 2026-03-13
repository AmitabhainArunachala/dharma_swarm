"""Repo X-Ray — point it at any codebase, get an actionable analysis.

Produces a structured markdown report with: overview, architecture map,
code quality signals, complexity hotspots, dependency graph, risk flags,
and recommended next steps.

No LLM calls. No API keys. Pure static analysis. Works on any Python repo.

Usage:
    from dharma_swarm.xray import run_xray
    report_path = run_xray(Path("~/projects/my-saas"))
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

# File extensions we analyze
PYTHON_EXTS = {".py"}
JS_EXTS = {".js", ".ts", ".jsx", ".tsx"}
ALL_CODE_EXTS = PYTHON_EXTS | JS_EXTS
DOC_EXTS = {".md", ".rst", ".txt"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}

# Directories to always skip
SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info", ".next", ".nuxt", "coverage", ".coverage",
}

# Max files to prevent runaway on monorepos
MAX_FILES = 2000
# Max file size to read (256KB)
MAX_FILE_SIZE = 256 * 1024


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


# ── Data Models ──────────────────────────────────────────────────────


class FileInfo(BaseModel):
    """Analysis of a single source file."""
    path: str
    language: str = "python"
    lines: int = 0
    non_blank_lines: int = 0
    complexity: int = 0
    max_nesting: int = 0
    docstring_ratio: float = 0.0
    naming_score: float = 0.0
    num_functions: int = 0
    num_classes: int = 0
    imports: list[str] = Field(default_factory=list)
    is_test: bool = False
    has_docstring: bool = False


class FunctionInfo(BaseModel):
    """A function/method with complexity info."""
    name: str
    file: str
    line: int = 0
    complexity: int = 0
    lines: int = 0


class RiskFlag(BaseModel):
    """A potential issue found in the codebase."""
    severity: str = "warning"  # warning, error, info
    category: str = ""
    message: str = ""
    file: str = ""


class XRayReport(BaseModel):
    """Complete X-Ray analysis of a repository."""
    repo_name: str
    repo_path: str
    generated_at: str = Field(default_factory=lambda: _utc_now().isoformat())

    # Overview
    total_files: int = 0
    total_lines: int = 0
    total_non_blank_lines: int = 0
    language_breakdown: dict[str, int] = Field(default_factory=dict)  # lang -> file count
    language_lines: dict[str, int] = Field(default_factory=dict)  # lang -> line count

    # Architecture
    top_modules: list[dict[str, Any]] = Field(default_factory=list)
    module_connections: list[dict[str, str]] = Field(default_factory=list)

    # Quality
    test_file_count: int = 0
    test_ratio: float = 0.0
    avg_docstring_ratio: float = 0.0
    avg_naming_score: float = 0.0
    avg_complexity: float = 0.0
    type_annotation_rate: float = 0.0

    # Hotspots
    complexity_hotspots: list[FunctionInfo] = Field(default_factory=list)
    largest_files: list[dict[str, Any]] = Field(default_factory=list)

    # Dependencies
    external_deps: list[str] = Field(default_factory=list)
    internal_coupling: list[dict[str, Any]] = Field(default_factory=list)

    # Risks
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    # Next steps
    recommendations: list[str] = Field(default_factory=list)


class XRayServicePacket(BaseModel):
    """Productized service packet derived from a repo X-Ray."""

    repo_name: str
    repo_path: str
    generated_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    buyer: str
    grade: str
    quality_score: float
    summary: str
    diagnosis: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    sprint_name: str = "Repo X-Ray Sprint"
    sprint_duration_days: int = 5
    sprint_outcome: str = ""
    deliverables: list[str] = Field(default_factory=list)
    swarm_plan: list[str] = Field(default_factory=list)
    price_floor_usd: int = 0
    price_target_usd: int = 0
    top_risks: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""


# ── File Discovery ───────────────────────────────────────────────────


# Default exclude patterns for noisy directories
DEFAULT_EXCLUDES = {"external", ".worktrees", "migrations", "vendor"}

# Max risk flags to keep reports actionable
MAX_RISK_FLAGS = 15


def discover_files(
    repo_path: Path,
    exclude_patterns: set[str] | None = None,
) -> list[Path]:
    """Walk repo and return all analyzable source files.

    Args:
        repo_path: Root of the repository.
        exclude_patterns: Directory names or path segments to skip
            (in addition to SKIP_DIRS). Defaults to DEFAULT_EXCLUDES.
    """
    excludes = exclude_patterns if exclude_patterns is not None else DEFAULT_EXCLUDES
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        # Filter out skip dirs AND user excludes in-place
        dirs[:] = [
            d for d in dirs
            if not _should_skip_dir(d) and d not in excludes
        ]
        # Also skip if any path segment matches an exclude pattern
        rel_root = Path(root).relative_to(repo_path)
        if any(part in excludes for part in rel_root.parts):
            dirs.clear()
            continue
        for name in filenames:
            if len(files) >= MAX_FILES:
                break
            path = Path(root) / name
            if path.suffix.lower() in ALL_CODE_EXTS | DOC_EXTS | CONFIG_EXTS:
                try:
                    if path.stat().st_size <= MAX_FILE_SIZE:
                        files.append(path)
                except OSError:
                    pass
    return files


# ── Python Analysis ──────────────────────────────────────────────────


def _count_complexity(tree: ast.Module) -> int:
    """Cyclomatic complexity of an entire module."""
    from dharma_swarm.elegance import _ComplexityVisitor
    visitor = _ComplexityVisitor()
    visitor.visit(tree)
    return visitor.complexity


def _max_nesting(tree: ast.Module) -> int:
    from dharma_swarm.elegance import _NestingVisitor
    visitor = _NestingVisitor()
    visitor.visit(tree)
    return visitor.max_depth


def _docstring_ratio(tree: ast.Module) -> float:
    """Fraction of functions/classes with docstrings."""
    total = 0
    with_doc = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            total += 1
            if ast.get_docstring(node):
                with_doc += 1
    return with_doc / total if total > 0 else 1.0


def _naming_score(tree: ast.Module) -> float:
    """Fraction of names following Python conventions."""
    snake_re = re.compile(r"^_*[a-z][a-z0-9_]*$")
    pascal_re = re.compile(r"^_*[A-Z][a-zA-Z0-9]*$")
    dunder_re = re.compile(r"^__[a-z][a-z0-9_]*__$")
    total = 0
    ok = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            if dunder_re.match(node.name) or snake_re.match(node.name):
                ok += 1
        elif isinstance(node, ast.ClassDef):
            total += 1
            if pascal_re.match(node.name):
                ok += 1
    return ok / total if total > 0 else 1.0


def _type_annotation_rate(tree: ast.Module) -> float:
    """Fraction of function args/returns with type annotations."""
    total_args = 0
    annotated_args = 0
    has_return_ann = 0
    total_funcs = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total_funcs += 1
            if node.returns:
                has_return_ann += 1
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                total_args += 1
                if arg.annotation:
                    annotated_args += 1

    total_slots = total_args + total_funcs  # args + return annotations
    annotated_slots = annotated_args + has_return_ann
    return annotated_slots / total_slots if total_slots > 0 else 1.0


def _extract_functions(tree: ast.Module, file_path: str) -> list[FunctionInfo]:
    """Extract function-level complexity info."""
    from dharma_swarm.elegance import _ComplexityVisitor
    functions: list[FunctionInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visitor = _ComplexityVisitor()
            visitor.visit(node)
            end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
            functions.append(FunctionInfo(
                name=node.name,
                file=file_path,
                line=node.lineno,
                complexity=visitor.complexity,
                lines=end_line - node.lineno + 1,
            ))
    return functions


def _extract_imports(source: str) -> list[str]:
    """Extract imported module names (top-level package only)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module.split(".")[0])
    return list(set(modules))


def _extract_imports_detailed(source: str) -> list[str]:
    """Extract full dotted import paths for coupling analysis."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return list(set(modules))


def analyze_python_file(path: Path, repo_root: Path) -> tuple[FileInfo | None, list[FunctionInfo]]:
    """Analyze a single Python file."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, []

    rel_path = str(path.relative_to(repo_root))
    lines = content.splitlines()
    non_blank = sum(1 for l in lines if l.strip())

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return FileInfo(
            path=rel_path,
            lines=len(lines),
            non_blank_lines=non_blank,
            is_test="test" in path.name.lower(),
        ), []

    num_funcs = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    num_classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    imports = _extract_imports(content)

    info = FileInfo(
        path=rel_path,
        language="python",
        lines=len(lines),
        non_blank_lines=non_blank,
        complexity=_count_complexity(tree),
        max_nesting=_max_nesting(tree),
        docstring_ratio=_docstring_ratio(tree),
        naming_score=_naming_score(tree),
        num_functions=num_funcs,
        num_classes=num_classes,
        imports=imports,
        is_test="test" in path.name.lower(),
        has_docstring=bool(ast.get_docstring(tree)),
    )

    functions = _extract_functions(tree, rel_path)
    return info, functions


# ── JS/TS Analysis (lightweight) ─────────────────────────────────────


def analyze_js_file(path: Path, repo_root: Path) -> FileInfo | None:
    """Lightweight analysis of JS/TS files (line counts + imports)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    rel_path = str(path.relative_to(repo_root))
    lines = content.splitlines()
    non_blank = sum(1 for l in lines if l.strip())

    # Extract imports (rough regex)
    import_re = re.compile(r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))""")
    imports = list({m.group(1) or m.group(2) for m in import_re.finditer(content)})

    lang = "typescript" if path.suffix in {".ts", ".tsx"} else "javascript"

    return FileInfo(
        path=rel_path,
        language=lang,
        lines=len(lines),
        non_blank_lines=non_blank,
        imports=imports,
        is_test="test" in path.name.lower() or "spec" in path.name.lower(),
    )


# ── Report Generation ────────────────────────────────────────────────


def _identify_stdlib(module: str) -> bool:
    """Check if a module is likely a Python stdlib module."""
    import sys
    return module in sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else False


def _classify_import(module: str, repo_packages: set[str]) -> str:
    """Classify import as 'internal', 'stdlib', or 'external'."""
    if module in repo_packages:
        return "internal"
    if _identify_stdlib(module):
        return "stdlib"
    return "external"


def analyze_repo(
    repo_path: Path,
    exclude_patterns: set[str] | None = None,
) -> XRayReport:
    """Run full X-Ray analysis on a repository.

    Args:
        repo_path: Root of the repository.
        exclude_patterns: Directory names to skip. Defaults to DEFAULT_EXCLUDES.
    """
    repo_path = repo_path.resolve()
    repo_name = repo_path.name

    files = discover_files(repo_path, exclude_patterns=exclude_patterns)
    if not files:
        return XRayReport(
            repo_name=repo_name,
            repo_path=str(repo_path),
            risk_flags=[RiskFlag(
                severity="error",
                category="empty",
                message="No analyzable files found in this directory.",
            )],
            recommendations=["Ensure this is a valid project directory with source files."],
        )

    # Detect repo packages (top-level Python packages)
    repo_packages: set[str] = set()
    for child in repo_path.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            repo_packages.add(child.name)
    # Also add repo name as potential package
    repo_packages.add(repo_name.replace("-", "_"))

    all_file_infos: list[FileInfo] = []
    all_functions: list[FunctionInfo] = []
    language_counts: Counter[str] = Counter()
    language_lines: Counter[str] = Counter()
    all_imports: list[str] = []

    for path in files:
        suffix = path.suffix.lower()

        if suffix in PYTHON_EXTS:
            info, funcs = analyze_python_file(path, repo_path)
            if info:
                all_file_infos.append(info)
                all_functions.extend(funcs)
                language_counts["python"] += 1
                language_lines["python"] += info.lines
                all_imports.extend(info.imports)

        elif suffix in JS_EXTS:
            info = analyze_js_file(path, repo_path)
            if info:
                all_file_infos.append(info)
                language_counts[info.language] += 1
                language_lines[info.language] += info.lines
                all_imports.extend(info.imports)

        elif suffix in DOC_EXTS:
            language_counts["docs"] += 1
        elif suffix in CONFIG_EXTS:
            language_counts["config"] += 1

    code_files = [f for f in all_file_infos if f.language in ("python", "javascript", "typescript")]
    python_files = [f for f in all_file_infos if f.language == "python"]
    test_files = [f for f in code_files if f.is_test]
    src_files = [f for f in code_files if not f.is_test]

    # ── Overview ──
    total_lines = sum(f.lines for f in all_file_infos)
    total_non_blank = sum(f.non_blank_lines for f in all_file_infos)

    # ── Architecture: top modules ──
    module_info: dict[str, dict[str, Any]] = {}
    for f in all_file_infos:
        parts = Path(f.path).parts
        top_module = parts[0] if len(parts) > 1 else "(root)"
        if top_module not in module_info:
            module_info[top_module] = {
                "name": top_module, "files": 0, "lines": 0,
                "classes": 0, "functions": 0, "description": "",
            }
        module_info[top_module]["files"] += 1
        module_info[top_module]["lines"] += f.lines
        module_info[top_module]["classes"] += f.num_classes
        module_info[top_module]["functions"] += f.num_functions
        # Use first file's docstring as module description
        if not module_info[top_module]["description"] and f.has_docstring:
            module_info[top_module]["description"] = f"Contains {f.num_classes} classes, {f.num_functions} functions"

    top_modules = sorted(module_info.values(), key=lambda m: m["lines"], reverse=True)[:15]

    # Module connections (which modules import from which)
    connections: list[dict[str, str]] = []
    seen_connections: set[tuple[str, str]] = set()
    for f in python_files:
        src_parts = Path(f.path).parts
        src_mod = src_parts[0] if len(src_parts) > 1 else "(root)"
        for imp in f.imports:
            if imp in repo_packages:
                conn = (src_mod, imp)
                if conn not in seen_connections and src_mod != imp:
                    seen_connections.add(conn)
                    connections.append({"from": src_mod, "to": imp})

    # ── Quality Signals ──
    test_ratio = len(test_files) / len(src_files) if src_files else 0.0
    avg_docstring = (
        sum(f.docstring_ratio for f in python_files) / len(python_files)
        if python_files else 0.0
    )
    avg_naming = (
        sum(f.naming_score for f in python_files) / len(python_files)
        if python_files else 0.0
    )
    avg_complexity = (
        sum(f.complexity for f in python_files) / len(python_files)
        if python_files else 0.0
    )

    # Type annotation rate (re-parse is expensive, sample top files)
    type_ann_rates: list[float] = []
    for f in python_files[:50]:  # Sample for speed
        try:
            content = (repo_path / f.path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            type_ann_rates.append(_type_annotation_rate(tree))
        except (OSError, SyntaxError):
            pass
    avg_type_ann = sum(type_ann_rates) / len(type_ann_rates) if type_ann_rates else 0.0

    # ── Complexity Hotspots ──
    hotspots = sorted(all_functions, key=lambda f: f.complexity, reverse=True)[:10]

    # ── Largest files ──
    largest = sorted(all_file_infos, key=lambda f: f.non_blank_lines, reverse=True)[:10]
    largest_dicts = [
        {"path": f.path, "lines": f.non_blank_lines, "complexity": f.complexity}
        for f in largest
    ]

    # ── Dependencies ──
    import_counts = Counter(all_imports)
    external_deps = sorted([
        mod for mod in import_counts
        if _classify_import(mod, repo_packages) == "external"
    ])

    # Internal coupling: count detailed from X.Y import Z style imports
    coupling: list[dict[str, Any]] = []
    for f in python_files:
        try:
            content = (repo_path / f.path).read_text(encoding="utf-8", errors="replace")
            detailed = _extract_imports_detailed(content)
            # Count imports that reference any repo package at any depth
            internal = [
                imp for imp in detailed
                if imp.split(".")[0] in repo_packages
            ]
            if internal:
                coupling.append({
                    "file": f.path,
                    "internal_imports": len(internal),
                    "imports": internal,
                })
        except OSError:
            pass
    coupling.sort(key=lambda c: c["internal_imports"], reverse=True)

    # ── Risk Flags ──
    risks: list[RiskFlag] = []

    # No tests
    if not test_files:
        risks.append(RiskFlag(
            severity="error",
            category="testing",
            message="No test files found. Critical modules have zero test coverage.",
        ))
    elif test_ratio < 0.3:
        risks.append(RiskFlag(
            severity="warning",
            category="testing",
            message=f"Low test ratio: {test_ratio:.0%} (test files / source files). Target: >50%.",
        ))

    # Oversized files
    for f in all_file_infos:
        if f.non_blank_lines > 500:
            risks.append(RiskFlag(
                severity="warning",
                category="size",
                message=f"Large file ({f.non_blank_lines} lines). Consider splitting.",
                file=f.path,
            ))

    # High complexity functions
    for func in all_functions:
        if func.complexity > 20:
            risks.append(RiskFlag(
                severity="warning",
                category="complexity",
                message=f"Function `{func.name}` has complexity {func.complexity} (>20). Refactor.",
                file=func.file,
            ))

    # Low docstring coverage
    if python_files and avg_docstring < 0.3:
        risks.append(RiskFlag(
            severity="warning",
            category="documentation",
            message=f"Low docstring coverage: {avg_docstring:.0%}. Most functions lack documentation.",
        ))

    # Circular dependency check (simple: A imports B, B imports A)
    import_graph: dict[str, set[str]] = defaultdict(set)
    for f in python_files:
        src_mod = Path(f.path).parts[0] if len(Path(f.path).parts) > 1 else f.path
        for imp in f.imports:
            if imp in repo_packages:
                import_graph[src_mod].add(imp)

    for mod_a, deps_a in import_graph.items():
        for mod_b in deps_a:
            if mod_a in import_graph.get(mod_b, set()):
                risks.append(RiskFlag(
                    severity="info",
                    category="architecture",
                    message=f"Circular dependency: {mod_a} ↔ {mod_b}",
                ))

    # Deduplicate and cap risks
    seen_risks: set[str] = set()
    unique_risks: list[RiskFlag] = []
    for r in risks:
        key = f"{r.category}:{r.message}"
        if key not in seen_risks:
            seen_risks.add(key)
            unique_risks.append(r)

    # Prioritize: errors first, then warnings by impact (larger files first)
    severity_order = {"error": 0, "warning": 1, "info": 2}
    unique_risks.sort(key=lambda r: severity_order.get(r.severity, 9))
    risk_count_omitted = max(0, len(unique_risks) - MAX_RISK_FLAGS)
    unique_risks = unique_risks[:MAX_RISK_FLAGS]

    # ── Recommendations ──
    recs: list[str] = []

    if not test_files:
        recs.append("Add tests. Start with the most complex modules to catch regressions.")
    elif test_ratio < 0.5:
        untested_complex = [
            f for f in src_files
            if f.complexity > 10 and not any(
                t.path.replace("test_", "") == f.path or f.path.split("/")[-1] in t.path
                for t in test_files
            )
        ]
        if untested_complex:
            recs.append(
                f"Add tests for complex untested modules: "
                f"{', '.join(f.path for f in untested_complex[:3])}"
            )

    if avg_docstring < 0.5:
        recs.append("Improve documentation. Add docstrings to public functions and classes.")

    if avg_type_ann < 0.3 and python_files:
        recs.append("Add type annotations. Current coverage is low — start with public APIs.")

    if hotspots and hotspots[0].complexity > 15:
        recs.append(
            f"Refactor `{hotspots[0].name}` in `{hotspots[0].file}` "
            f"(complexity={hotspots[0].complexity}). Extract helper functions."
        )

    oversized = [f for f in all_file_infos if f.non_blank_lines > 500]
    if oversized:
        recs.append(
            f"Split large files: {', '.join(f.path for f in oversized[:3])} "
            f"({oversized[0].non_blank_lines}+ lines each)."
        )

    if not recs:
        recs.append("Codebase looks healthy. Consider adding integration tests and CI/CD if not present.")

    return XRayReport(
        repo_name=repo_name,
        repo_path=str(repo_path),
        total_files=len(all_file_infos),
        total_lines=total_lines,
        total_non_blank_lines=total_non_blank,
        language_breakdown=dict(language_counts),
        language_lines=dict(language_lines),
        top_modules=top_modules,
        module_connections=connections,
        test_file_count=len(test_files),
        test_ratio=round(test_ratio, 3),
        avg_docstring_ratio=round(avg_docstring, 3),
        avg_naming_score=round(avg_naming, 3),
        avg_complexity=round(avg_complexity, 1),
        type_annotation_rate=round(avg_type_ann, 3),
        complexity_hotspots=hotspots,
        largest_files=largest_dicts,
        external_deps=external_deps,
        internal_coupling=coupling[:10],
        risk_flags=unique_risks,
        recommendations=recs,
    )


# ── Markdown Rendering ───────────────────────────────────────────────


def render_markdown(report: XRayReport) -> str:
    """Render an XRayReport as clean, readable markdown."""
    lines: list[str] = []

    # Header
    lines.append(f"# Repo X-Ray: {report.repo_name}")
    lines.append(f"*Generated {report.generated_at[:19]} UTC*")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append(f"- **Path**: `{report.repo_path}`")
    lines.append(f"- **Files analyzed**: {report.total_files}")
    lines.append(f"- **Total lines**: {report.total_lines:,} ({report.total_non_blank_lines:,} non-blank)")

    if report.language_breakdown:
        lang_parts = []
        for lang, count in sorted(report.language_breakdown.items(), key=lambda x: -x[1]):
            line_count = report.language_lines.get(lang, 0)
            lang_parts.append(f"{lang}: {count} files ({line_count:,} lines)")
        lines.append(f"- **Languages**: {' | '.join(lang_parts)}")
    lines.append("")

    # Architecture
    lines.append("## Architecture")
    if report.top_modules:
        lines.append("### Top Modules")
        for mod in report.top_modules:
            desc = f" — {mod['description']}" if mod.get("description") else ""
            lines.append(
                f"- **{mod['name']}**: {mod['files']} files, {mod['lines']:,} lines, "
                f"{mod['classes']} classes, {mod['functions']} functions{desc}"
            )
    if report.module_connections:
        lines.append("\n### Module Connections")
        for conn in report.module_connections:
            lines.append(f"- `{conn['from']}` → `{conn['to']}`")
    lines.append("")

    # Quality Signals
    lines.append("## Code Quality Signals")

    # Quality grade
    quality_score = (
        (min(report.test_ratio, 1.0) * 0.3) +
        (report.avg_docstring_ratio * 0.2) +
        (report.avg_naming_score * 0.15) +
        (report.type_annotation_rate * 0.15) +
        (max(0, 1.0 - report.avg_complexity / 50) * 0.2)
    )
    grade = (
        "A" if quality_score >= 0.8 else
        "B" if quality_score >= 0.6 else
        "C" if quality_score >= 0.4 else
        "D" if quality_score >= 0.2 else "F"
    )
    lines.append(f"**Overall Grade: {grade}** (score: {quality_score:.2f})")
    lines.append("")

    lines.append(f"- **Test ratio**: {report.test_ratio:.0%} ({report.test_file_count} test files)")
    lines.append(f"- **Docstring coverage**: {report.avg_docstring_ratio:.0%}")
    lines.append(f"- **Naming conventions**: {report.avg_naming_score:.0%}")
    lines.append(f"- **Type annotation rate**: {report.type_annotation_rate:.0%}")
    lines.append(f"- **Avg complexity per file**: {report.avg_complexity:.1f}")
    lines.append("")

    # Complexity Hotspots
    if report.complexity_hotspots:
        lines.append("## Complexity Hotspots")
        lines.append("Functions with the highest cyclomatic complexity:")
        lines.append("")
        for func in report.complexity_hotspots:
            if func.complexity > 1:
                lines.append(
                    f"- `{func.name}` in `{func.file}:{func.line}` — "
                    f"complexity={func.complexity}, {func.lines} lines"
                )
        lines.append("")

    # Largest Files
    if report.largest_files:
        lines.append("## Largest Files")
        for f in report.largest_files[:7]:
            lines.append(f"- `{f['path']}` — {f['lines']:,} lines (complexity={f['complexity']})")
        lines.append("")

    # Dependencies
    if report.external_deps:
        lines.append("## External Dependencies")
        lines.append(f"{len(report.external_deps)} external packages: "
                     f"`{', '.join(report.external_deps[:20])}`")
        if len(report.external_deps) > 20:
            lines.append(f"*...and {len(report.external_deps) - 20} more*")
        lines.append("")

    if report.internal_coupling:
        lines.append("## Internal Coupling")
        lines.append("Files with the most internal imports:")
        lines.append("")
        for c in report.internal_coupling[:7]:
            lines.append(f"- `{c['file']}` imports {c['internal_imports']} internal modules")
        lines.append("")

    # Risk Flags
    if report.risk_flags:
        lines.append("## Risk Flags")
        for risk in report.risk_flags:
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(risk.severity, "⚪")
            file_ref = f" (`{risk.file}`)" if risk.file else ""
            lines.append(f"- {icon} **{risk.category}**: {risk.message}{file_ref}")
        lines.append("")

    # Recommendations
    if report.recommendations:
        lines.append("## Recommended Next Steps")
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    return "\n".join(lines)


def _quality_score_and_grade(report: XRayReport) -> tuple[float, str]:
    score = (
        (min(report.test_ratio, 1.0) * 0.3)
        + (report.avg_docstring_ratio * 0.2)
        + (report.avg_naming_score * 0.15)
        + (report.type_annotation_rate * 0.15)
        + (max(0.0, 1.0 - report.avg_complexity / 50.0) * 0.2)
    )
    grade = (
        "A" if score >= 0.8 else
        "B" if score >= 0.6 else
        "C" if score >= 0.4 else
        "D" if score >= 0.2 else "F"
    )
    return round(score, 3), grade


def build_service_packet(
    report: XRayReport,
    *,
    buyer: str = "CTO or founder under shipping pressure",
) -> XRayServicePacket:
    """Translate an X-Ray report into a sellable fixed-scope service packet."""

    quality_score, grade = _quality_score_and_grade(report)
    diagnosis: list[str] = []
    proof_points: list[str] = []

    src_files = max(1, report.total_files - report.test_file_count)
    proof_points.append(
        f"Analyzed {report.total_files} files and {report.total_non_blank_lines:,} non-blank lines."
    )
    proof_points.append(
        f"Test surface: {report.test_file_count} test files for roughly {src_files} non-test files "
        f"({report.test_ratio:.0%} ratio)."
    )
    proof_points.append(
        f"Quality grade {grade} with score {quality_score:.3f}; average complexity {report.avg_complexity:.1f}."
    )
    if report.complexity_hotspots:
        hotspot = report.complexity_hotspots[0]
        proof_points.append(
            f"Top hotspot: {hotspot.name} in {hotspot.file}:{hotspot.line} "
            f"(complexity {hotspot.complexity})."
        )
    if report.largest_files:
        largest = report.largest_files[0]
        proof_points.append(
            f"Largest file: {largest['path']} at {largest['lines']:,} non-blank lines."
        )

    if report.test_ratio < 0.3:
        diagnosis.append(
            "Release risk is elevated because the test surface is too thin for confident iteration."
        )
    if report.avg_complexity >= 12:
        diagnosis.append(
            "Change velocity is being taxed by concentrated complexity in a few functions or modules."
        )
    if report.largest_files and report.largest_files[0]["lines"] > 400:
        diagnosis.append(
            "Context is trapped in oversized files, which slows onboarding, review, and safe edits."
        )
    if report.internal_coupling and report.internal_coupling[0]["internal_imports"] >= 5:
        diagnosis.append(
            "Internal coupling suggests small changes may ripple across the codebase."
        )
    if not diagnosis:
        diagnosis.append(
            "The repo is healthy enough that the highest-value offer is optimization and proof-hardening, not rescue work."
        )

    severity_score = 0
    severity_score += sum(2 for risk in report.risk_flags if risk.severity == "error")
    severity_score += sum(1 for risk in report.risk_flags if risk.severity == "warning")
    severity_score += 2 if report.test_ratio < 0.2 else 0
    severity_score += 2 if report.avg_complexity >= 15 else 0
    severity_score += 1 if report.largest_files and report.largest_files[0]["lines"] > 500 else 0
    price_floor = min(18000, 3500 + severity_score * 750)
    price_target = min(25000, price_floor + 3000 + max(0, len(report.risk_flags) - 3) * 250)

    sprint_outcome = (
        "Deliver a source-grounded risk map, a prioritized remediation brief, "
        "one verified implementation slice, and a buyer-ready next-step recommendation."
    )
    deliverables = [
        "repo_xray_report.md",
        "service_brief.md",
        "mission_brief.md",
        "risk_register.json",
        "verified_change_slice.md",
    ]
    if report.test_ratio < 0.5:
        deliverables.append("focused_regression_plan.md")
    if report.complexity_hotspots:
        deliverables.append("hotspot_refactor_plan.md")

    swarm_plan = [
        "codex-primus: lead builder, patch closer, and implementation owner",
        "opus-primus: diagnosis, contradiction hunting, and scope control",
        "glm-researcher: dependency and evidence synthesis",
        "kimi-cartographer: file graph and artifact mapping",
        "qwen-builder: broad low-cost implementation support",
        "nim-validator: verification, regression checks, and result gating",
    ]

    summary = (
        f"{report.repo_name} is a viable fixed-scope Repo X-Ray Sprint candidate for {buyer}. "
        f"The repo currently grades {grade} and shows {len(report.risk_flags)} visible risk signals, "
        "which is enough to justify a paid hardening sprint instead of a generic advisory call."
    )

    top_risks = [
        f"{risk.category}: {risk.message}" + (f" ({risk.file})" if risk.file else "")
        for risk in report.risk_flags[:5]
    ]
    recommended_next_step = (
        "Run the paid Repo X-Ray Sprint on the live repository, then convert the first verified fix "
        "into a case study and recurring maintenance offer."
    )

    return XRayServicePacket(
        repo_name=report.repo_name,
        repo_path=report.repo_path,
        buyer=buyer,
        grade=grade,
        quality_score=quality_score,
        summary=summary,
        diagnosis=diagnosis,
        proof_points=proof_points,
        sprint_outcome=sprint_outcome,
        deliverables=deliverables,
        swarm_plan=swarm_plan,
        price_floor_usd=price_floor,
        price_target_usd=price_target,
        top_risks=top_risks,
        recommended_next_step=recommended_next_step,
    )


def render_service_brief(packet: XRayServicePacket) -> str:
    """Render a buyer-facing service brief from a service packet."""

    lines = [
        f"# Repo X-Ray Sprint Brief: {packet.repo_name}",
        f"*Generated {packet.generated_at[:19]} UTC*",
        "",
        "## Executive Summary",
        packet.summary,
        "",
        "## Buyer",
        f"- {packet.buyer}",
        "",
        "## Diagnosis",
    ]
    for item in packet.diagnosis:
        lines.append(f"- {item}")
    lines.extend(["", "## Proof Points"])
    for item in packet.proof_points:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Fixed-Scope Offer",
            f"- Name: {packet.sprint_name}",
            f"- Duration: {packet.sprint_duration_days} business days",
            f"- Outcome: {packet.sprint_outcome}",
            f"- Price floor: ${packet.price_floor_usd:,}",
            f"- Target price: ${packet.price_target_usd:,}",
            "",
            "## Deliverables",
        ]
    )
    for item in packet.deliverables:
        lines.append(f"- {item}")
    lines.extend(["", "## Swarm Plan"])
    for item in packet.swarm_plan:
        lines.append(f"- {item}")
    lines.extend(["", "## Top Risks"])
    for item in packet.top_risks:
        lines.append(f"- {item}")
    lines.extend(["", "## Next Step", packet.recommended_next_step, ""])
    return "\n".join(lines)


def render_swarm_mission(packet: XRayServicePacket) -> str:
    """Render the swarm mission brief for delivering the X-Ray sprint."""

    lines = [
        f"# Swarm Mission: {packet.sprint_name} for {packet.repo_name}",
        "",
        "## Objective",
        (
            "Turn static repo evidence into a buyer-ready diagnostic, a verified implementation slice, "
            "and the shortest credible path to a paid follow-on sprint."
        ),
        "",
        "## Success Criteria",
        "- Source-grounded X-Ray completed",
        "- Service brief written",
        "- Top risks ranked and scoped",
        "- One verified implementation slice proposed or shipped",
        "- Clear next paid step identified",
        "",
        "## Agent Lanes",
    ]
    for item in packet.swarm_plan:
        lines.append(f"- {item}")
    lines.extend(["", "## Proof Surfaces"])
    for item in packet.proof_points:
        lines.append(f"- {item}")
    lines.extend(["", "## Close Condition", packet.recommended_next_step, ""])
    return "\n".join(lines)


# ── Public API ───────────────────────────────────────────────────────


def run_xray(
    repo_path: Path | str,
    output_path: Path | str | None = None,
    as_json: bool = False,
    exclude_patterns: set[str] | None = None,
) -> Path:
    """Run a full X-Ray analysis on a repository.

    Args:
        repo_path: Path to the repository root.
        output_path: Where to save the report. Defaults to xray_report.md in the repo.
        as_json: If True, output JSON instead of markdown.
        exclude_patterns: Directory names to skip.

    Returns:
        Path to the generated report file.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")

    logger.info("Running X-Ray on %s", repo)
    report = analyze_repo(repo, exclude_patterns=exclude_patterns)

    if as_json:
        ext = ".json"
        content = report.model_dump_json(indent=2)
    else:
        ext = ".md"
        content = render_markdown(report)

    if output_path:
        out = Path(output_path)
    else:
        out = repo / f"xray_report{ext}"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    logger.info("X-Ray report saved to %s", out)
    return out


def run_xray_packet(
    repo_path: Path | str,
    output_dir: Path | str | None = None,
    *,
    buyer: str = "CTO or founder under shipping pressure",
    exclude_patterns: set[str] | None = None,
) -> dict[str, Path]:
    """Generate a productized X-Ray packet suitable for a paid service offer."""

    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")

    report = analyze_repo(repo, exclude_patterns=exclude_patterns)
    packet = build_service_packet(report, buyer=buyer)

    out_dir = Path(output_dir) if output_dir else repo / "xray_packet"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_md = out_dir / "xray_report.md"
    report_json = out_dir / "xray_report.json"
    service_md = out_dir / "service_brief.md"
    packet_json = out_dir / "service_packet.json"
    mission_md = out_dir / "mission_brief.md"

    report_md.write_text(render_markdown(report), encoding="utf-8")
    report_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    service_md.write_text(render_service_brief(packet), encoding="utf-8")
    packet_json.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    mission_md.write_text(render_swarm_mission(packet), encoding="utf-8")

    return {
        "output_dir": out_dir,
        "report_markdown": report_md,
        "report_json": report_json,
        "service_brief": service_md,
        "service_packet": packet_json,
        "mission_brief": mission_md,
    }


def analyze_repo_summary(
    repo_path: Path | str,
    exclude_patterns: set[str] | None = None,
) -> dict[str, Any]:
    """Compact analysis summary for the Foreman quality forge.

    Returns a dict with: grade, score, per-dimension quality scores,
    top 3 risks, top 3 recommended actions, and basic stats.
    Much faster than full render — no markdown generation.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return {"error": f"Not a directory: {repo}", "grade": "F", "score": 0.0}

    report = analyze_repo(repo, exclude_patterns=exclude_patterns)

    quality_score, grade = _quality_score_and_grade(report)

    # Count files with error handling (try/except or raise)
    error_handling_count = 0
    src_file_count = 0
    for f in report.complexity_hotspots:  # rough proxy
        pass
    # Re-scan for error handling — iterate code files from the report
    all_code_files = [
        f for f in []
    ]  # We need the file infos — extract from the report data
    # Use the internal coupling data which has file paths
    # Simpler: count from risk flags + test ratio
    src_count = max(1, report.total_files - report.test_file_count)

    return {
        "repo_name": report.repo_name,
        "repo_path": report.repo_path,
        "grade": grade,
        "score": quality_score,
        "total_files": report.total_files,
        "total_lines": report.total_lines,
        "dimensions": {
            "has_tests": min(1.0, round(report.test_ratio, 3)),
            "tests_pass": None,  # Requires running tests — filled by Foreman
            "error_handling": None,  # Requires AST scan — filled by Foreman
            "documented": round(report.avg_docstring_ratio, 3),
            "edge_cases_covered": None,  # Requires test analysis — filled by Foreman
        },
        "test_file_count": report.test_file_count,
        "avg_complexity": report.avg_complexity,
        "type_annotation_rate": round(report.type_annotation_rate, 3),
        "top_risks": [
            {"severity": r.severity, "category": r.category,
             "message": r.message, "file": r.file}
            for r in report.risk_flags[:3]
        ],
        "top_actions": report.recommendations[:3],
    }
