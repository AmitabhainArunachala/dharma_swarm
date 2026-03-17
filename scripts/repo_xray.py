#!/usr/bin/env python3
"""Static repo x-ray for dharma_swarm.

This is a fast, dependency-free inventory pass for:
- structural complexity
- file-size hotspots
- local import coupling
- language mix
- workflow surface area

It is intentionally static. It does not run tests or mutate the repo.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


IGNORE_DIRS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


@dataclass(slots=True)
class PythonFileMetrics:
    path: str
    lines: int
    defs: int
    classes: int
    imports: int


@dataclass(slots=True)
class ModuleCoupling:
    module: str
    count: int


@dataclass(slots=True)
class RepoXRay:
    repo_root: str
    python_modules: int
    python_tests: int
    shell_scripts: int
    markdown_docs: int
    workflows: list[str]
    language_mix: dict[str, int]
    largest_python_files: list[PythonFileMetrics]
    most_imported_modules: list[ModuleCoupling]
    highest_outbound_modules: list[ModuleCoupling]


def _walk_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def _safe_line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _module_name(repo_root: Path, path: Path) -> str:
    return ".".join(path.relative_to(repo_root).with_suffix("").parts)


def _python_metrics(repo_root: Path, package_root: Path) -> tuple[list[PythonFileMetrics], Counter[str], Counter[str]]:
    module_paths = {
        _module_name(repo_root, path): path
        for path in _walk_files(package_root)
        if path.suffix == ".py"
    }
    known_modules = set(module_paths)

    python_files: list[PythonFileMetrics] = []
    inbound = Counter()
    outbound = Counter()

    for module_name, path in module_paths.items():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        defs = 0
        classes = 0
        imports = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs += 1
            elif isinstance(node, ast.ClassDef):
                classes += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports += 1

            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _best_local_module(alias.name, known_modules)
                    if target:
                        outbound[module_name] += 1
                        inbound[target] += 1
            elif isinstance(node, ast.ImportFrom) and node.module:
                target = _best_local_module(node.module, known_modules)
                if target:
                    outbound[module_name] += 1
                    inbound[target] += 1

        python_files.append(
            PythonFileMetrics(
                path=str(path.relative_to(repo_root)),
                lines=_safe_line_count(path),
                defs=defs,
                classes=classes,
                imports=imports,
            )
        )

    return python_files, inbound, outbound


def _best_local_module(name: str, known_modules: set[str]) -> str | None:
    if not name.startswith("dharma_swarm"):
        return None

    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known_modules:
            return candidate
        parts.pop()
    return None


def build_xray(repo_root: Path) -> RepoXRay:
    package_root = repo_root / "dharma_swarm"
    tests_root = repo_root / "tests"
    scripts_root = repo_root / "scripts"
    docs_root = repo_root / "docs"
    workflows_root = repo_root / ".github" / "workflows"

    python_files, inbound, outbound = _python_metrics(repo_root, package_root)

    language_mix = Counter[str]()
    for path in _walk_files(repo_root):
        suffix = path.suffix.lower() or "<no_ext>"
        language_mix[suffix] += 1

    workflows = sorted(
        str(path.relative_to(repo_root))
        for path in _walk_files(workflows_root)
        if workflows_root.exists()
    )

    return RepoXRay(
        repo_root=str(repo_root),
        python_modules=len([path for path in _walk_files(package_root) if path.suffix == ".py"]),
        python_tests=len([path for path in _walk_files(tests_root) if path.suffix == ".py"]) if tests_root.exists() else 0,
        shell_scripts=len([path for path in _walk_files(scripts_root) if path.suffix in {".sh", ".py"}]) if scripts_root.exists() else 0,
        markdown_docs=len([path for path in _walk_files(docs_root) if path.suffix == ".md"]) if docs_root.exists() else 0,
        workflows=workflows,
        language_mix=dict(language_mix.most_common(15)),
        largest_python_files=sorted(
            python_files,
            key=lambda item: (item.lines, item.defs, item.imports),
            reverse=True,
        )[:20],
        most_imported_modules=[
            ModuleCoupling(module=name, count=count)
            for name, count in inbound.most_common(20)
        ],
        highest_outbound_modules=[
            ModuleCoupling(module=name, count=count)
            for name, count in outbound.most_common(20)
        ],
    )


def _render_markdown(summary: RepoXRay) -> str:
    lines = [
        "# DHARMA SWARM Repo X-Ray",
        "",
        f"- Repo root: `{summary.repo_root}`",
        f"- Python modules: `{summary.python_modules}`",
        f"- Python test files: `{summary.python_tests}`",
        f"- Ops scripts (`.py` + `.sh` under `scripts/`): `{summary.shell_scripts}`",
        f"- Markdown docs under `docs/`: `{summary.markdown_docs}`",
        f"- Workflows: `{len(summary.workflows)}`",
        "",
        "## Workflows",
        "",
    ]

    if summary.workflows:
        lines.extend(f"- `{workflow}`" for workflow in summary.workflows)
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "## Language Mix",
            "",
        ]
    )
    lines.extend(
        f"- `{suffix}`: `{count}` files"
        for suffix, count in summary.language_mix.items()
    )

    lines.extend(
        [
            "",
            "## Largest Python Files",
            "",
        ]
    )
    for item in summary.largest_python_files:
        lines.append(
            f"- `{item.path}`: `{item.lines}` lines, `{item.defs}` defs, "
            f"`{item.classes}` classes, `{item.imports}` imports"
        )

    lines.extend(
        [
            "",
            "## Most Imported Local Modules",
            "",
        ]
    )
    lines.extend(
        f"- `{item.module}`: `{item.count}` inbound local imports"
        for item in summary.most_imported_modules
    )

    lines.extend(
        [
            "",
            "## Highest Outbound Local Importers",
            "",
        ]
    )
    lines.extend(
        f"- `{item.module}`: `{item.count}` outbound local imports"
        for item in summary.highest_outbound_modules
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Static repo x-ray for dharma_swarm")
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Repo root to analyze",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--write",
        type=Path,
        help="Optional output file path",
    )
    args = parser.parse_args()

    summary = build_xray(args.repo_root.resolve())
    if args.format == "json":
        output = json.dumps(asdict(summary), indent=2, sort_keys=True)
    else:
        output = _render_markdown(summary)

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
