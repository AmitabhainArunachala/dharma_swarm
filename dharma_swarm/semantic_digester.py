"""Semantic digester — deep reading of source files into a ConceptGraph.

Phase 1 of the Semantic Evolution Engine.  Reads .py and .md files,
extracts structured meaning (concepts, claims, formal structures,
dependencies), profiles behavioral signatures, and populates a
:class:`ConceptGraph`.

Extraction strategy:
  - Python files: AST-parsed docstrings, class/function names, import
    graph, formal pattern detection (Pydantic models, Protocol classes,
    mathematical structures).
  - Markdown files: header hierarchy, bold-defined terms, claim sentences,
    YAML/code-fenced formal blocks.
  - Both: behavioral profiling via :mod:`dharma_swarm.metrics` and
    connection finding via :mod:`dharma_swarm.ouroboros`.

All failures are non-fatal — the digester skips unreadable files and
logs warnings.
"""

from __future__ import annotations

import ast
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer
from dharma_swarm.semantic_gravity import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".venv",
    "node_modules", ".tox", ".eggs", "*.egg-info",
})

ALLOWED_PY_SUFFIXES = frozenset({".py"})
ALLOWED_MD_SUFFIXES = frozenset({".md", ".markdown"})
ALLOWED_TEXT_SUFFIXES = frozenset({".txt"})
ALLOWED_NOTE_SUFFIXES = ALLOWED_MD_SUFFIXES | ALLOWED_TEXT_SUFFIXES

FRONTMATTER_LINK_KEYS = frozenset({"related", "see_also", "backlinks", "links"})

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# Patterns that indicate a formal mathematical/computational structure
FORMAL_PATTERNS: list[tuple[str, str]] = [
    (r"\bmonad\b", "monad"),
    (r"\bcoalgebra\b", "coalgebra"),
    (r"\bsheaf\b", "sheaf"),
    (r"\bcohomolog\w*\b", "cohomology"),
    (r"\bfunctor\b", "functor"),
    (r"\bdistributive\s+law\b", "distributive_law"),
    (r"\bfixed[- ]?point\b", "fixed_point"),
    (r"\bmanifold\b", "manifold"),
    (r"\bgeodesic\b", "geodesic"),
    (r"\bfisher\b", "fisher_metric"),
    (r"\bparticipation\s+ratio\b", "participation_ratio"),
    (r"\bkleisli\b", "kleisli"),
    (r"\bidempoten\w*\b", "idempotent"),
    (r"\bbisimil\w*\b", "bisimulation"),
    (r"\bstigmerg\w*\b", "stigmergy"),
    (r"\banekanta\b", "anekanta"),
    (r"\bdharmic\b", "dharmic"),
    (r"\bouroboros\b", "ouroboros"),
    (r"\bentropy\b", "entropy"),
    (r"\bkolmogorov\b", "kolmogorov_complexity"),
    (r"\bR_V\b", "rv_contraction"),
]

# Patterns that indicate a claim (assertion, hypothesis, invariant)
CLAIM_INDICATORS: list[str] = [
    r"(?:must|shall|always|never|invariant|guarantee|ensure|require)",
    r"(?:implies|therefore|thus|hence|consequently)",
    r"(?:hypothesis|conjecture|claim|assert|proof|theorem|lemma)",
    r"(?:threshold|constraint|bound|limit|floor|ceiling)",
]

CLAIM_RE = re.compile(
    r"(?:^|\.\s+)([A-Z][^.]*?(?:"
    + "|".join(CLAIM_INDICATORS)
    + r")[^.]*\.)",
    re.MULTILINE | re.IGNORECASE,
)

# Category classification keywords
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "mathematical": [
        "monad", "coalgebra", "sheaf", "cohomology", "functor", "manifold",
        "geodesic", "fisher", "metric", "topology", "algebra", "category",
        "morphism", "endofunctor", "kleisli", "idempotent", "bisimulation",
    ],
    "philosophical": [
        "dharma", "anekanta", "gnani", "prakruti", "shakti", "witness",
        "consciousness", "observer", "phenomenological", "epistemic",
        "swabhaav", "telos", "axiom", "principle", "constitution",
    ],
    "measurement": [
        "metric", "score", "fitness", "entropy", "density", "ratio",
        "participation", "contraction", "signature", "behavioral",
        "rv", "measure", "evaluate", "assess", "analyze",
    ],
    "engineering": [
        "pipeline", "runtime", "daemon", "cli", "api", "provider",
        "config", "deploy", "test", "integration", "archive", "store",
        "async", "parallel", "concurrent", "cache", "queue",
    ],
    "coordination": [
        "swarm", "agent", "orchestrat", "stigmergy", "pheromone",
        "lattice", "mark", "channel", "message", "task", "workflow",
        "delegate", "escalat", "coordinate",
    ],
}


# ---------------------------------------------------------------------------
# Python file extraction
# ---------------------------------------------------------------------------


def _extract_python_concepts(
    source: str,
    file_path: str,
    *,
    analyzer: MetricsAnalyzer | None = None,
) -> list[ConceptNode]:
    """Extract concepts from a Python source file via AST parsing."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        logger.debug("Syntax error parsing %s, skipping", file_path)
        return []

    _analyzer = analyzer or MetricsAnalyzer()
    nodes: list[ConceptNode] = []

    # Module-level docstring
    module_doc = ast.get_docstring(tree) or ""
    if module_doc:
        sig = _analyzer.analyze(module_doc)
        formal = _detect_formal_structures(module_doc)
        claims = _extract_claims(module_doc)
        category = _classify_category(module_doc)
        # Module name from file path
        mod_name = Path(file_path).stem
        nodes.append(ConceptNode(
            name=mod_name,
            definition=module_doc[:500],
            source_file=file_path,
            source_line=1,
            category=category,
            claims=claims,
            formal_structures=formal,
            salience=_compute_salience(module_doc, formal, claims, sig),
            semantic_density=_semantic_density(module_doc, len(source.splitlines())),
            behavioral_entropy=sig.entropy,
            behavioral_complexity=sig.complexity,
            recognition_type=sig.recognition_type.value,
        ))

    # Classes and functions
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        name = node.name
        if name.startswith("_") and not name.startswith("__"):
            continue  # skip private helpers

        combined_text = f"{name} {doc}"
        sig = _analyzer.analyze(combined_text) if combined_text.strip() else BehavioralSignature()
        formal = _detect_formal_structures(combined_text)
        claims = _extract_claims(doc)
        category = _classify_category(combined_text)
        line = getattr(node, "lineno", 0)

        # Determine salience: classes > functions, documented > undocumented
        base_salience = 0.6 if isinstance(node, ast.ClassDef) else 0.4
        if doc:
            base_salience += 0.1
        if formal:
            base_salience += 0.15

        nodes.append(ConceptNode(
            name=name,
            definition=doc[:500] if doc else f"{type(node).__name__} in {Path(file_path).stem}",
            source_file=file_path,
            source_line=line,
            category=category,
            claims=claims,
            formal_structures=formal,
            salience=min(1.0, base_salience + len(formal) * 0.05),
            semantic_density=_semantic_density(doc, max(1, (getattr(node, "end_lineno", line) or line) - line)),
            behavioral_entropy=sig.entropy,
            behavioral_complexity=sig.complexity,
            recognition_type=sig.recognition_type.value,
        ))

    return nodes


def _extract_python_imports(source: str) -> list[str]:
    """Extract imported module names from Python source."""
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
    return modules


# ---------------------------------------------------------------------------
# Markdown file extraction
# ---------------------------------------------------------------------------


_MD_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_MD_BOLD_TERM_RE = re.compile(r"\*\*([A-Z][A-Za-z_ /()-]+)\*\*")


def _coerce_frontmatter_value(raw: str) -> Any:
    value = raw.strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [
            part.strip().strip("\"'")
            for part in inner.split(",")
            if part.strip()
        ]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    metadata: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = _coerce_frontmatter_value(value)
    return metadata, text[end + 5 :]


def _normalize_note_link_value(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if "|" in text:
        text = text.split("|", 1)[0].strip()
    if "#" in text:
        text = text.split("#", 1)[0].strip()
    return text.strip()


def _extract_note_links(content: str) -> list[str]:
    frontmatter, body = _split_frontmatter(content)
    links = [
        _normalize_note_link_value(match)
        for match in _WIKILINK_RE.findall(body)
    ]
    links.extend(
        _normalize_note_link_value(match)
        for match in _MD_LINK_RE.findall(body)
    )
    for key in FRONTMATTER_LINK_KEYS:
        raw = frontmatter.get(key)
        if raw is None:
            continue
        if isinstance(raw, list):
            links.extend(_normalize_note_link_value(str(item)) for item in raw)
        else:
            raw_text = str(raw)
            if "," in raw_text:
                links.extend(
                    _normalize_note_link_value(part)
                    for part in raw_text.split(",")
                )
            else:
                links.append(_normalize_note_link_value(raw_text))
    return [link for link in links if link]


def _extract_markdown_concepts(
    content: str,
    file_path: str,
    *,
    analyzer: MetricsAnalyzer | None = None,
) -> list[ConceptNode]:
    """Extract concepts from a Markdown file."""
    _analyzer = analyzer or MetricsAnalyzer()
    nodes: list[ConceptNode] = []
    frontmatter, body = _split_frontmatter(content)
    source_name = (
        str(frontmatter.get("title", "")).strip()
        or Path(file_path).stem.replace("_", " ")
    )
    aliases = frontmatter.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = [aliases] if aliases else []
    tags = frontmatter.get("tags", [])
    if not isinstance(tags, list):
        tags = [tags] if tags else []
    note_links = _extract_note_links(content)

    file_text = body.strip()[:1000]
    if file_text:
        sig = _analyzer.analyze(f"{source_name}\n{file_text}")
        formal = _detect_formal_structures(file_text)
        claims = _extract_claims(file_text)
        category = _classify_category(f"{source_name}\n{file_text}")
        nodes.append(ConceptNode(
            name=source_name,
            definition=file_text[:500],
            source_file=file_path,
            source_line=1,
            category=category,
            claims=claims,
            formal_structures=formal,
            salience=_compute_salience(file_text, formal, claims, sig),
            semantic_density=_semantic_density(file_text, max(1, file_text.count("\n") + 1)),
            behavioral_entropy=sig.entropy,
            behavioral_complexity=sig.complexity,
            recognition_type="note",
            metadata={
                "frontmatter": frontmatter,
                "aliases": [str(alias) for alias in aliases if str(alias).strip()],
                "tags": [str(tag) for tag in tags if str(tag).strip()],
                "note_links": note_links[:80],
            },
        ))

    # Extract from headers
    for match in _MD_HEADER_RE.finditer(body):
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title or len(title) < 3:
            continue

        # Get surrounding text (up to 500 chars after the header)
        start = match.end()
        end = min(start + 500, len(body))
        context = body[start:end].strip()

        combined = f"{title} {context}"
        sig = _analyzer.analyze(combined)
        formal = _detect_formal_structures(combined)
        claims = _extract_claims(context)
        category = _classify_category(combined)

        # Higher-level headers = higher salience
        base_salience = max(0.3, 0.8 - level * 0.1)
        if formal:
            base_salience += 0.1

        line_no = body[:match.start()].count("\n") + 1
        nodes.append(ConceptNode(
            name=title,
            definition=context[:300],
            source_file=file_path,
            source_line=line_no,
            category=category,
            claims=claims,
            formal_structures=formal,
            salience=min(1.0, base_salience),
            semantic_density=_semantic_density(context, max(1, context.count("\n") + 1)),
            behavioral_entropy=sig.entropy,
            behavioral_complexity=sig.complexity,
            recognition_type=sig.recognition_type.value,
        ))

    # Extract bold-defined terms as additional concepts
    for match in _MD_BOLD_TERM_RE.finditer(body):
        term = match.group(1).strip()
        if len(term) < 3 or len(term) > 60:
            continue
        start = match.start()
        # Get sentence context
        sentence_start = max(0, body.rfind(".", 0, start))
        sentence_end = body.find(".", start)
        if sentence_end == -1:
            sentence_end = min(start + 200, len(body))
        context = body[sentence_start:sentence_end].strip(". ")

        line_no = body[:start].count("\n") + 1
        nodes.append(ConceptNode(
            name=term,
            definition=context[:300],
            source_file=file_path,
            source_line=line_no,
            category=_classify_category(context),
            salience=0.4,
            semantic_density=0.0,
        ))

    return nodes


def _extract_text_concepts(
    content: str,
    file_path: str,
    *,
    analyzer: MetricsAnalyzer | None = None,
) -> list[ConceptNode]:
    """Extract a coarse concept from plain-text research notes."""
    _analyzer = analyzer or MetricsAnalyzer()
    text = content.strip()
    if not text:
        return []
    sample = text[:5000]

    sig = _analyzer.analyze(sample)
    formal = _detect_formal_structures(sample)
    claims = _extract_claims(sample)
    name = Path(file_path).stem.replace("_", " ")
    return [ConceptNode(
        name=name,
        definition=sample[:500],
        source_file=file_path,
        source_line=1,
        category=_classify_category(f"{name}\n{sample[:1000]}"),
        claims=claims,
        formal_structures=formal,
        salience=_compute_salience(sample[:1200], formal, claims, sig),
        semantic_density=_semantic_density(sample, max(1, sample.count("\n") + 1)),
        behavioral_entropy=sig.entropy,
        behavioral_complexity=sig.complexity,
        recognition_type="text_note",
        metadata={"note_links": _extract_note_links(sample)[:80]},
    )]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _detect_formal_structures(text: str) -> list[str]:
    """Detect mathematical/computational formal structures in text."""
    lower = text.lower()
    found: list[str] = []
    for pattern, label in FORMAL_PATTERNS:
        if re.search(pattern, lower):
            if label not in found:
                found.append(label)
    return found


def _extract_claims(text: str) -> list[str]:
    """Extract assertion/claim sentences from text."""
    claims: list[str] = []
    for match in CLAIM_RE.finditer(text):
        claim = match.group(1).strip()
        if len(claim) > 20 and claim not in claims:
            claims.append(claim[:300])
    return claims[:10]  # cap at 10 claims per concept


def _classify_category(text: str) -> str:
    """Classify text into a concept category via keyword scoring."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in lower)
    if not scores or max(scores.values()) == 0:
        return "engineering"  # default
    return max(scores, key=lambda k: scores[k])


def _compute_salience(
    text: str,
    formal: list[str],
    claims: list[str],
    sig: BehavioralSignature,
) -> float:
    """Compute salience score from multiple signals."""
    # Base: word count signals substance
    words = len(text.split())
    length_score = min(1.0, words / 200)
    # Formal structures boost salience
    formal_score = min(1.0, len(formal) * 0.2)
    # Claims boost salience
    claim_score = min(1.0, len(claims) * 0.15)
    # Behavioral: high entropy + moderate complexity = interesting
    behavioral_score = sig.entropy * 0.3 + min(sig.complexity, 1.0) * 0.2
    # Combine
    raw = length_score * 0.3 + formal_score * 0.3 + claim_score * 0.2 + behavioral_score * 0.2
    return max(0.1, min(1.0, raw))


def _semantic_density(text: str, line_count: int) -> float:
    """Concept density: unique non-trivial words per line."""
    if line_count <= 0:
        return 0.0
    words = set(text.lower().split())
    # Filter trivial words (< 4 chars)
    meaningful = {w for w in words if len(w) >= 4}
    return len(meaningful) / max(line_count, 1)


def _should_skip(path: Path) -> bool:
    """Return True if path should be skipped during scanning."""
    for part in path.parts:
        if part in SKIP_DIRS or part.startswith("."):
            return True
    return False


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def _build_import_edges(
    nodes_by_file: dict[str, list[ConceptNode]],
    file_imports: dict[str, list[str]],
) -> list[ConceptEdge]:
    """Build IMPORTS edges from Python import relationships."""
    edges: list[ConceptEdge] = []
    # Map module stems to their concept node IDs
    stem_to_nodes: dict[str, list[str]] = defaultdict(list)
    for file_path, file_nodes in nodes_by_file.items():
        stem = Path(file_path).stem
        for node in file_nodes:
            stem_to_nodes[stem].append(node.id)

    for file_path, imports in file_imports.items():
        source_nodes = nodes_by_file.get(file_path, [])
        if not source_nodes:
            continue
        source_id = source_nodes[0].id  # use module-level concept as source

        for imp in imports:
            # Extract the last component of the import path
            parts = imp.split(".")
            target_stem = parts[-1]
            target_node_ids = stem_to_nodes.get(target_stem, [])
            for tid in target_node_ids:
                if tid != source_id:
                    edges.append(ConceptEdge(
                        source_id=source_id,
                        target_id=tid,
                        edge_type=EdgeType.IMPORTS,
                        weight=0.5,
                        evidence=f"import {imp}",
                    ))
    return edges


def _build_reference_edges(
    all_nodes: list[ConceptNode],
) -> list[ConceptEdge]:
    """Build REFERENCES edges when one concept's definition mentions another's name."""
    edges: list[ConceptEdge] = []
    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        key = node.name.lower().replace("_", " ").strip()
        if len(key) >= 4:  # skip very short names
            name_to_ids[key].append(node.id)

    seen: set[tuple[str, str]] = set()
    for node in all_nodes:
        tokens = re.findall(r"[a-z0-9_]{4,}", node.definition.lower().replace("_", " "))
        candidates: set[str] = set(tokens)
        max_ngram = min(4, len(tokens))
        for size in range(2, max_ngram + 1):
            for idx in range(0, len(tokens) - size + 1):
                candidates.add(" ".join(tokens[idx : idx + size]))

        for name in candidates:
            for tid in name_to_ids.get(name, []):
                if tid != node.id and (node.id, tid) not in seen:
                    seen.add((node.id, tid))
                    edges.append(ConceptEdge(
                        source_id=node.id,
                        target_id=tid,
                        edge_type=EdgeType.REFERENCES,
                        weight=0.3,
                        evidence=f"'{name}' mentioned in definition of '{node.name}'",
                    ))
    return edges


def _build_formal_edges(
    all_nodes: list[ConceptNode],
) -> list[ConceptEdge]:
    """Build EXTENDS/IMPLEMENTS edges between concepts sharing formal structures."""
    edges: list[ConceptEdge] = []
    # Group nodes by formal structure
    structure_to_nodes: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        for struct in node.formal_structures:
            structure_to_nodes[struct].append(node.id)

    seen: set[tuple[str, str]] = set()
    for struct, node_ids in structure_to_nodes.items():
        if len(node_ids) < 2:
            continue
        for i, a_id in enumerate(node_ids):
            for b_id in node_ids[i + 1:]:
                pair = (min(a_id, b_id), max(a_id, b_id))
                if pair not in seen:
                    seen.add(pair)
                    edges.append(ConceptEdge(
                        source_id=a_id,
                        target_id=b_id,
                        edge_type=EdgeType.EXTENDS,
                        weight=0.7,
                        evidence=f"shared formal structure: {struct}",
                    ))
    return edges


def _build_note_link_edges(
    nodes_by_file: dict[str, list[ConceptNode]],
    file_links: dict[str, list[str]],
    file_paths: dict[str, Path],
    alias_to_files: dict[str, list[str]],
) -> list[ConceptEdge]:
    """Build note-link edges across markdown/txt notes and Obsidian-style aliases."""
    edges: list[ConceptEdge] = []
    seen: set[tuple[str, str, str]] = set()

    for file_path, links in file_links.items():
        source_nodes = nodes_by_file.get(file_path, [])
        source_abs = file_paths.get(file_path)
        if not source_nodes or source_abs is None:
            continue
        source_id = source_nodes[0].id
        current_dir = source_abs.parent

        for raw_link in links:
            normalized = _normalize_note_link_value(raw_link)
            if not normalized:
                continue

            candidate_files: list[str] = []
            target_path = Path(normalized).expanduser()
            if target_path.suffix:
                resolved = (current_dir / target_path).resolve() if not target_path.is_absolute() else target_path
                for rel_path, abs_path in file_paths.items():
                    if abs_path == resolved:
                        candidate_files.append(rel_path)
                        break
            else:
                lookup_keys = {
                    normalized.lower(),
                    Path(normalized).stem.lower(),
                    normalized.replace("_", " ").lower(),
                }
                for key in lookup_keys:
                    candidate_files.extend(alias_to_files.get(key, []))

            for target_file in dict.fromkeys(candidate_files):
                target_nodes = nodes_by_file.get(target_file, [])
                if not target_nodes:
                    continue
                target_id = target_nodes[0].id
                if target_id == source_id:
                    continue
                edge_key = (source_id, target_id, normalized.lower())
                if edge_key in seen:
                    continue
                seen.add(edge_key)
                edges.append(ConceptEdge(
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=EdgeType.REFERENCES,
                    weight=0.45,
                    evidence=f"note link: {raw_link}",
                    metadata={"link_type": "note_link"},
                ))
    return edges


# ---------------------------------------------------------------------------
# SemanticDigester
# ---------------------------------------------------------------------------


class SemanticDigester:
    """Reads source files and populates a ConceptGraph.

    Usage::

        digester = SemanticDigester()
        graph = digester.digest_directory(Path("dharma_swarm"))
        print(f"Extracted {graph.node_count} concepts, {graph.edge_count} edges")

    The digester is stateless — each call to ``digest_directory`` or
    ``digest_file`` returns fresh results.  Merge into an existing graph
    by adding nodes/edges manually.
    """

    def __init__(self, *, analyzer: MetricsAnalyzer | None = None) -> None:
        self._analyzer = analyzer or MetricsAnalyzer()

    def digest_directory(
        self,
        root: Path,
        *,
        include_tests: bool = False,
        max_files: int = 500,
    ) -> ConceptGraph:
        """Recursively digest all .py and .md files under *root*.

        Args:
            root: Directory to scan.
            include_tests: Whether to include test files.
            max_files: Safety cap on files processed.

        Returns:
            A populated :class:`ConceptGraph`.
        """
        graph = ConceptGraph()
        nodes_by_file: dict[str, list[ConceptNode]] = {}
        file_imports: dict[str, list[str]] = {}
        file_links: dict[str, list[str]] = {}
        file_paths: dict[str, Path] = {}
        alias_to_files: dict[str, list[str]] = defaultdict(list)
        files_processed = 0

        for path in sorted(root.rglob("*")):
            if files_processed >= max_files:
                break
            if not path.is_file():
                continue
            scan_path = path.relative_to(root)
            if _should_skip(scan_path):
                continue
            if not include_tests and "test" in path.name.lower():
                continue

            suffix = path.suffix.lower()
            if suffix not in ALLOWED_PY_SUFFIXES | ALLOWED_NOTE_SUFFIXES:
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                logger.debug("Cannot read %s, skipping", path)
                continue

            rel_path = str(path.relative_to(root.parent) if root.parent != path.parent else path.name)
            file_nodes = self.digest_file(content, rel_path, suffix=suffix)

            if file_nodes:
                nodes_by_file[rel_path] = file_nodes
                file_paths[rel_path] = path.resolve()
                for node in file_nodes:
                    graph.add_node(node)
                alias_candidates = {
                    Path(rel_path).stem.lower(),
                    Path(rel_path).stem.replace("_", " ").lower(),
                }
                for node in file_nodes[:1]:
                    alias_candidates.add(node.name.lower())
                    aliases = node.metadata.get("aliases", []) if isinstance(node.metadata, dict) else []
                    for alias in aliases:
                        alias_candidates.add(str(alias).lower())
                for alias in alias_candidates:
                    if alias and rel_path not in alias_to_files[alias]:
                        alias_to_files[alias].append(rel_path)

            if suffix in ALLOWED_PY_SUFFIXES:
                file_imports[rel_path] = _extract_python_imports(content)
            elif suffix in ALLOWED_NOTE_SUFFIXES:
                file_links[rel_path] = _extract_note_links(content)

            files_processed += 1

        # Build edges
        all_nodes = graph.all_nodes()
        for edge in _build_import_edges(nodes_by_file, file_imports):
            graph.add_edge(edge)
        for edge in _build_reference_edges(all_nodes):
            graph.add_edge(edge)
        for edge in _build_formal_edges(all_nodes):
            graph.add_edge(edge)
        for edge in _build_note_link_edges(
            nodes_by_file,
            file_links,
            file_paths,
            alias_to_files,
        ):
            graph.add_edge(edge)

        logger.info(
            "Digested %d files → %d concepts, %d edges",
            files_processed,
            graph.node_count,
            graph.edge_count,
        )
        return graph

    def digest_file(
        self,
        content: str,
        file_path: str,
        *,
        suffix: str = "",
    ) -> list[ConceptNode]:
        """Digest a single file and return extracted concept nodes."""
        if not suffix:
            suffix = Path(file_path).suffix.lower()

        if suffix in ALLOWED_PY_SUFFIXES:
            return _extract_python_concepts(
                content, file_path, analyzer=self._analyzer
            )
        if suffix in ALLOWED_MD_SUFFIXES:
            return _extract_markdown_concepts(
                content, file_path, analyzer=self._analyzer
            )
        if suffix in ALLOWED_TEXT_SUFFIXES:
            return _extract_text_concepts(
                content, file_path, analyzer=self._analyzer
            )
        return []

    def digest_text(self, text: str, name: str) -> ConceptNode:
        """Create a single concept node from arbitrary text."""
        sig = self._analyzer.analyze(text)
        formal = _detect_formal_structures(text)
        claims = _extract_claims(text)
        category = _classify_category(text)
        return ConceptNode(
            name=name,
            definition=text[:500],
            category=category,
            claims=claims,
            formal_structures=formal,
            salience=_compute_salience(text, formal, claims, sig),
            semantic_density=_semantic_density(text, max(1, text.count("\n") + 1)),
            behavioral_entropy=sig.entropy,
            behavioral_complexity=sig.complexity,
            recognition_type=sig.recognition_type.value,
        )


__all__ = [
    "SemanticDigester",
]
