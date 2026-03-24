"""concept_parser.py — Pattern-matching concept extraction for the Semantic GitNexus.

Phase 7.5: Extracts concept references from Python source files using the
seed ontology (dharma_concepts.json). Three extraction strategies:

1. Pattern matching: Regex against docstrings, comments, string literals
2. Name analysis: CamelCase/snake_case identifier matching
3. (Future — Phase 9.8) LLM-based inference during SleepTime

This is the READ side of the Semantic Graph's indexing pipeline.
It answers: "Where in the code does concept X appear?"

Ground: Kythe's anchor→definition pattern (connecting source locations
to semantic nodes), adapted for philosophical rather than type-system semantics.

Design:
    - ConceptRegistry: loads dharma_concepts.json, provides lookup
    - ConceptParser: scans Python files, emits ConceptExtraction records
    - ConceptIndexer: uses GraphStore to populate Semantic Graph + Code↔Semantic bridges
"""

from __future__ import annotations

import ast
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConceptExtraction:
    """A single concept reference found in source code."""
    concept_id: str              # ID from dharma_concepts.json
    canonical_name: str          # Human-readable name
    source_file: str             # Relative path from repo root
    source_type: str             # "docstring", "comment", "identifier", "code"
    line_number: int
    context: str                 # Surrounding text (for evidence)
    confidence: float            # 0-1
    extraction_method: str       # "pattern_match", "name_analysis"


@dataclass
class ConceptRegistryEntry:
    """A concept from the seed ontology."""
    id: str
    canonical_name: str
    aliases: list[str]
    definition: str
    domain: str
    source_attribution: str
    dharma_interpretation: str
    related_concepts: list[str]
    codebase_frequency: int = 0
    codebase_files: int = 0


# ---------------------------------------------------------------------------
# ConceptRegistry — loads and indexes the seed ontology
# ---------------------------------------------------------------------------

class ConceptRegistry:
    """Loads dharma_concepts.json and provides fast concept lookup.

    The registry is the ground truth for what concepts exist.
    It provides:
    - exact name/alias lookup
    - all-terms list for regex building
    - concept metadata access
    """

    def __init__(self, concepts_path: str | Path | None = None):
        if concepts_path is None:
            # Default: same directory as this file
            concepts_path = Path(__file__).parent / "dharma_concepts.json"
        self.concepts_path = Path(concepts_path)
        self.concepts: dict[str, ConceptRegistryEntry] = {}
        self._alias_to_id: dict[str, str] = {}
        self._pattern: Optional[re.Pattern] = None
        self._camel_pattern: Optional[re.Pattern] = None
        self._load()

    def _load(self) -> None:
        """Load concepts from JSON file."""
        if not self.concepts_path.exists():
            logger.warning("Concept registry not found at %s", self.concepts_path)
            return

        with open(self.concepts_path, encoding="utf-8") as f:
            data = json.load(f)

        for entry in data.get("concepts", []):
            concept = ConceptRegistryEntry(
                id=entry["id"],
                canonical_name=entry["canonical_name"],
                aliases=entry.get("aliases", []),
                definition=entry.get("definition", ""),
                domain=entry.get("domain", ""),
                source_attribution=entry.get("source_attribution", ""),
                dharma_interpretation=entry.get("dharma_interpretation", ""),
                related_concepts=entry.get("related_concepts", []),
                codebase_frequency=entry.get("codebase_frequency", 0),
                codebase_files=entry.get("codebase_files", 0),
            )
            self.concepts[concept.id] = concept

            # Build alias → id mapping (lowercase)
            self._alias_to_id[concept.canonical_name.lower()] = concept.id
            for alias in concept.aliases:
                self._alias_to_id[alias.lower()] = concept.id

        self._build_patterns()
        logger.info("Loaded %d concepts from %s", len(self.concepts), self.concepts_path)

    def _build_patterns(self) -> None:
        """Build compiled regex patterns from all concept names and aliases."""
        all_terms: list[str] = []
        camel_terms: list[str] = []

        for concept in self.concepts.values():
            # Lowercase terms for general pattern matching
            all_terms.append(concept.canonical_name.lower())
            for alias in concept.aliases:
                all_terms.append(alias.lower())

            # CamelCase terms for identifier matching
            # Convert canonical name to CamelCase
            camel = concept.canonical_name.replace(" ", "")
            if camel[0].isupper() if camel else False:
                camel_terms.append(camel)
            # Also add aliases that look like CamelCase
            for alias in concept.aliases:
                if alias and alias[0].isupper() and "_" not in alias and " " not in alias:
                    camel_terms.append(alias)

        # Sort longest first for greedy matching
        all_terms = sorted(set(all_terms), key=len, reverse=True)
        camel_terms = sorted(set(camel_terms), key=len, reverse=True)

        if all_terms:
            self._pattern = re.compile(
                r'\b(' + '|'.join(re.escape(t) for t in all_terms) + r')\b',
                re.IGNORECASE
            )
        if camel_terms:
            self._camel_pattern = re.compile(
                r'\b(' + '|'.join(re.escape(t) for t in camel_terms) + r')\b'
            )

    def resolve(self, term: str) -> Optional[str]:
        """Resolve a term to its canonical concept ID. Returns None if unknown."""
        return self._alias_to_id.get(term.lower())

    def get(self, concept_id: str) -> Optional[ConceptRegistryEntry]:
        """Get a concept by ID."""
        return self.concepts.get(concept_id)

    def __len__(self) -> int:
        return len(self.concepts)

    def __contains__(self, concept_id: str) -> bool:
        return concept_id in self.concepts


# ---------------------------------------------------------------------------
# ConceptParser — extracts concept references from Python files
# ---------------------------------------------------------------------------

class ConceptParser:
    """Extracts concept references from Python source files.

    Uses the ConceptRegistry to identify known concepts in:
    - Docstrings (highest confidence: 0.9)
    - Comments (confidence: 0.85)
    - Identifiers — class/function/variable names (confidence: 0.8)
    - Code — string literals and other references (confidence: 0.7)

    The parser is deterministic — no LLM calls. That's Phase 9.8.
    """

    def __init__(self, registry: ConceptRegistry):
        self.registry = registry

    def parse_file(self, filepath: str | Path, repo_root: str | Path | None = None) -> list[ConceptExtraction]:
        """Parse a single Python file for concept references.

        Args:
            filepath: Absolute or relative path to the .py file
            repo_root: If provided, file paths in results will be relative to this

        Returns:
            List of ConceptExtraction records, deduplicated by (concept_id, line, source_type)
        """
        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning("File not found: %s", filepath)
            return []

        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Failed to read %s: %s", filepath, e)
            return []

        rel_path = str(filepath.relative_to(repo_root)) if repo_root else str(filepath)
        results: list[ConceptExtraction] = []
        seen: set[tuple[str, int, str]] = set()  # (concept_id, line, source_type)

        def _add(extraction: ConceptExtraction) -> None:
            key = (extraction.concept_id, extraction.line_number, extraction.source_type)
            if key not in seen:
                seen.add(key)
                results.append(extraction)

        # Phase 1: Docstrings
        self._extract_docstrings(source, rel_path, results=results, seen=seen, add=_add)

        # Phase 2: Comments
        self._extract_comments(source, rel_path, add=_add)

        # Phase 3: Identifiers (name analysis)
        self._extract_identifiers(source, rel_path, add=_add)

        # Phase 4: Code lines (catch remaining references)
        self._extract_code_lines(source, rel_path, seen=seen, add=_add)

        return results

    def parse_directory(
        self, directory: str | Path, repo_root: str | Path | None = None
    ) -> list[ConceptExtraction]:
        """Parse all Python files in a directory tree."""
        directory = Path(directory)
        if repo_root is None:
            repo_root = directory

        all_results: list[ConceptExtraction] = []
        for py_file in sorted(directory.rglob("*.py")):
            if "__pycache__" in str(py_file) or ".git" in str(py_file):
                continue
            extractions = self.parse_file(py_file, repo_root=repo_root)
            all_results.extend(extractions)

        logger.info(
            "Parsed %d files, found %d concept references",
            len(list(directory.rglob("*.py"))),
            len(all_results),
        )
        return all_results

    # --- Extraction phases ---

    def _extract_docstrings(
        self, source: str, rel_path: str, *, results: list, seen: set,
        add: callable,
    ) -> None:
        """Phase 1: Extract concepts from docstrings."""
        if not self.registry._pattern:
            return
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                docstring = ast.get_docstring(node)
                if not docstring:
                    continue
                lineno = getattr(node, "lineno", 0)
                for match in self.registry._pattern.finditer(docstring):
                    concept_id = self.registry.resolve(match.group())
                    if concept_id:
                        ctx_start = max(0, match.start() - 60)
                        ctx_end = min(len(docstring), match.end() + 60)
                        add(ConceptExtraction(
                            concept_id=concept_id,
                            canonical_name=self.registry.concepts[concept_id].canonical_name,
                            source_file=rel_path,
                            source_type="docstring",
                            line_number=lineno,
                            context=docstring[ctx_start:ctx_end].strip(),
                            confidence=0.9,
                            extraction_method="pattern_match",
                        ))

    def _extract_comments(
        self, source: str, rel_path: str, *, add: callable,
    ) -> None:
        """Phase 2: Extract concepts from # comments."""
        if not self.registry._pattern:
            return
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if "#" not in stripped:
                continue
            comment_idx = stripped.index("#")
            comment = stripped[comment_idx + 1:].strip()
            if not comment:
                continue
            for match in self.registry._pattern.finditer(comment):
                concept_id = self.registry.resolve(match.group())
                if concept_id:
                    add(ConceptExtraction(
                        concept_id=concept_id,
                        canonical_name=self.registry.concepts[concept_id].canonical_name,
                        source_file=rel_path,
                        source_type="comment",
                        line_number=i,
                        context=comment[:120],
                        confidence=0.85,
                        extraction_method="pattern_match",
                    ))

    def _extract_identifiers(
        self, source: str, rel_path: str, *, add: callable,
    ) -> None:
        """Phase 3: Extract concepts from class/function/variable names."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            name = None
            lineno = 0
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                lineno = node.lineno
            elif isinstance(node, ast.ClassDef):
                name = node.name
                lineno = node.lineno
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        lineno = node.lineno

            if not name:
                continue

            # CamelCase matching
            if self.registry._camel_pattern:
                for match in self.registry._camel_pattern.finditer(name):
                    concept_id = self.registry.resolve(match.group())
                    if concept_id:
                        add(ConceptExtraction(
                            concept_id=concept_id,
                            canonical_name=self.registry.concepts[concept_id].canonical_name,
                            source_file=rel_path,
                            source_type="identifier",
                            line_number=lineno,
                            context=name,
                            confidence=0.8,
                            extraction_method="name_analysis",
                        ))

            # snake_case matching: convert to space-separated and match
            name_spaced = name.lower().replace("_", " ")
            if self.registry._pattern:
                for match in self.registry._pattern.finditer(name_spaced):
                    concept_id = self.registry.resolve(match.group())
                    if concept_id:
                        add(ConceptExtraction(
                            concept_id=concept_id,
                            canonical_name=self.registry.concepts[concept_id].canonical_name,
                            source_file=rel_path,
                            source_type="identifier",
                            line_number=lineno,
                            context=name,
                            confidence=0.8,
                            extraction_method="name_analysis",
                        ))

    def _extract_code_lines(
        self, source: str, rel_path: str, *, seen: set, add: callable,
    ) -> None:
        """Phase 4: Extract concepts from remaining code lines."""
        if not self.registry._pattern:
            return
        for i, line in enumerate(source.splitlines(), 1):
            for match in self.registry._pattern.finditer(line):
                concept_id = self.registry.resolve(match.group())
                if concept_id:
                    # Only add if not already found on this line with this concept
                    key = (concept_id, i, "code")
                    docstring_key = (concept_id, i, "docstring")
                    comment_key = (concept_id, i, "comment")
                    ident_key = (concept_id, i, "identifier")
                    if (key not in seen and docstring_key not in seen
                            and comment_key not in seen and ident_key not in seen):
                        add(ConceptExtraction(
                            concept_id=concept_id,
                            canonical_name=self.registry.concepts[concept_id].canonical_name,
                            source_file=rel_path,
                            source_type="code",
                            line_number=i,
                            context=line.strip()[:120],
                            confidence=0.7,
                            extraction_method="pattern_match",
                        ))


# ---------------------------------------------------------------------------
# ConceptIndexer — populates GraphStore with extraction results
# ---------------------------------------------------------------------------

class ConceptIndexer:
    """Populates the Semantic Graph and Code↔Semantic bridges from extractions.

    Takes ConceptExtraction results and:
    1. Ensures all concepts exist as nodes in the Semantic Graph
    2. Creates concept relationship edges in the Semantic Graph
    3. Creates bridge edges linking code files to the concepts they reference

    This is the WRITE side of the Semantic GitNexus indexing pipeline.
    """

    def __init__(self, graph_store, registry: ConceptRegistry):
        """
        Args:
            graph_store: A GraphStore instance (SQLiteGraphStore)
            registry: The ConceptRegistry with all concept definitions
        """
        self.store = graph_store
        self.registry = registry

    def index_concepts(self) -> dict:
        """Populate the Semantic Graph with all concepts from the registry.

        Returns:
            Stats dict with counts of nodes and edges created
        """
        node_count = 0
        edge_count = 0

        # Upsert all concept nodes
        for concept in self.registry.concepts.values():
            self.store.upsert_node("semantic", {
                "id": concept.id,
                "kind": "concept",
                "name": concept.canonical_name,
                "data": json.dumps({
                    "definition": concept.definition,
                    "domain": concept.domain,
                    "source_attribution": concept.source_attribution,
                    "dharma_interpretation": concept.dharma_interpretation,
                    "aliases": concept.aliases,
                    "codebase_frequency": concept.codebase_frequency,
                    "codebase_files": concept.codebase_files,
                }),
            })
            node_count += 1

        # Load relationships from the JSON
        concepts_data = json.loads(self.registry.concepts_path.read_text())
        for rel in concepts_data.get("relationships", []):
            source_id = rel.get("source", "")
            target_id = rel.get("target", "")
            if source_id in self.registry.concepts and target_id in self.registry.concepts:
                self.store.upsert_edge("semantic", {
                    "source_id": source_id,
                    "target_id": target_id,
                    "kind": rel.get("kind", "related_to"),
                    "data": json.dumps({
                        "description": rel.get("description", ""),
                    }),
                })
                edge_count += 1

        # Also create edges from related_concepts on each concept
        for concept in self.registry.concepts.values():
            for related_id in concept.related_concepts:
                if related_id in self.registry.concepts:
                    # Don't duplicate if already in relationships
                    self.store.upsert_edge("semantic", {
                        "source_id": concept.id,
                        "target_id": related_id,
                        "kind": "related_to",
                        "data": json.dumps({}),
                    })
                    edge_count += 1

        logger.info("Indexed %d concept nodes, %d relationship edges", node_count, edge_count)
        return {"concept_nodes": node_count, "relationship_edges": edge_count}

    def index_extractions(self, extractions: list[ConceptExtraction]) -> dict:
        """Create Code↔Semantic bridge edges from concept extractions.

        For each extraction, creates a bridge edge:
            source_graph="code", source_id="{file_path}::{line}"
            target_graph="semantic", target_id=concept_id

        Also ensures file nodes exist in a lightweight form.

        Returns:
            Stats dict with bridge count
        """
        bridge_count = 0
        files_indexed: set[str] = set()

        for ext in extractions:
            # Ensure file node exists in code graph (lightweight — full AST is Phase 8)
            if ext.source_file not in files_indexed:
                self.store.upsert_node("code", {
                    "id": f"file::{ext.source_file}",
                    "kind": "file",
                    "name": ext.source_file,
                    "data": json.dumps({"indexed_by": "concept_parser"}),
                })
                files_indexed.add(ext.source_file)

            # Create bridge edge
            bridge_id = f"bridge-{ext.source_file}::{ext.line_number}-{ext.concept_id}"
            self.store.upsert_bridge({
                "id": bridge_id,
                "source_graph": "code",
                "source_id": f"file::{ext.source_file}",
                "target_graph": "semantic",
                "target_id": ext.concept_id,
                "kind": "references_concept",
                "description": f"{ext.source_file}:{ext.line_number} ({ext.source_type}) references {ext.canonical_name}",
                "confidence": ext.confidence,
                "evidence": json.dumps([{
                    "type": ext.source_type,
                    "line": ext.line_number,
                    "context": ext.context,
                    "method": ext.extraction_method,
                }]),
                "inferred_by": f"concept_parser.{ext.extraction_method}",
            })
            bridge_count += 1

        logger.info(
            "Created %d bridge edges across %d files",
            bridge_count, len(files_indexed),
        )
        return {"bridge_edges": bridge_count, "files_indexed": len(files_indexed)}

    def full_index(self, extractions: list[ConceptExtraction]) -> dict:
        """Run the complete indexing pipeline.

        1. Index all concepts from registry → Semantic Graph
        2. Index all extractions → Code↔Semantic bridges

        Returns combined stats.
        """
        concept_stats = self.index_concepts()
        bridge_stats = self.index_extractions(extractions)
        return {**concept_stats, **bridge_stats}
