#!/usr/bin/env python3
"""The Mirror Test: dharma_swarm understands itself.

Scans the entire dharma_swarm codebase for philosophical concept references,
builds a live semantic graph + code-to-concept bridges, runs blast radius
analysis, and has an LLM discover the system's intellectual architecture
purely from code — then compares to what CLAUDE.md claims.

This is not a unit test. It's an organism looking in a mirror.
"""

import ast
import json
import os
import re
import sqlite3
import hashlib
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Seed Ontology: 60 core DHARMA concepts
# ---------------------------------------------------------------------------

SEED_ONTOLOGY = {
    # Cybernetics / VSM (Beer)
    "viable system model": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["vsm", "viable system"]},
    "requisite variety": {"domain": "cybernetics", "source": "Ashby 1956", "aliases": ["variety"]},
    "algedonic": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["algedonic signal", "algedonic channel"]},
    "system 1": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["s1"]},
    "system 2": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["s2"]},
    "system 3": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["s3"]},
    "system 4": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["s4"]},
    "system 5": {"domain": "cybernetics", "source": "Beer 1972", "aliases": ["s5"]},
    "homeostasis": {"domain": "cybernetics", "source": "Ashby 1956", "aliases": ["homeostatic"]},
    "feedback": {"domain": "cybernetics", "source": "Wiener 1948", "aliases": ["feedback loop"]},

    # Autopoiesis (Varela / Maturana)
    "autopoiesis": {"domain": "autopoiesis", "source": "Maturana & Varela 1980", "aliases": ["autopoietic", "self-producing"]},
    "structural coupling": {"domain": "autopoiesis", "source": "Maturana & Varela 1980", "aliases": []},
    "organizational closure": {"domain": "autopoiesis", "source": "Varela 1979", "aliases": ["operational closure"]},
    "enactive": {"domain": "autopoiesis", "source": "Varela 1991", "aliases": ["enaction", "enactive cognition"]},

    # Complexity / Emergence (Kauffman)
    "autocatalytic": {"domain": "complexity", "source": "Kauffman 1993", "aliases": ["autocatalytic set", "autocatalytic network"]},
    "adjacent possible": {"domain": "complexity", "source": "Kauffman 2000", "aliases": []},
    "edge of chaos": {"domain": "complexity", "source": "Kauffman 1993", "aliases": []},
    "fitness landscape": {"domain": "complexity", "source": "Kauffman 1993", "aliases": ["fitness"]},
    "emergence": {"domain": "complexity", "source": "Holland 1995", "aliases": ["emergent"]},
    "dissipative": {"domain": "complexity", "source": "Prigogine 1977", "aliases": ["dissipative structure"]},
    "phase transition": {"domain": "complexity", "source": "Statistical mechanics", "aliases": []},

    # Cognitive Science (Levin)
    "cognitive light cone": {"domain": "cognitive_science", "source": "Levin 2019", "aliases": ["light cone"]},
    "scale-free cognition": {"domain": "cognitive_science", "source": "Levin 2023", "aliases": ["multi-scale cognition"]},
    "morphogenetic": {"domain": "cognitive_science", "source": "Levin 2019", "aliases": ["morphogenetic field"]},
    "basal cognition": {"domain": "cognitive_science", "source": "Levin 2023", "aliases": []},

    # Strange Loops (Hofstadter)
    "strange loop": {"domain": "self_reference", "source": "Hofstadter 1979", "aliases": ["strange_loop", "strangeloop"]},
    "self-reference": {"domain": "self_reference", "source": "Hofstadter 1979", "aliases": ["self-referential", "recursive self"]},
    "tangled hierarchy": {"domain": "self_reference", "source": "Hofstadter 1979", "aliases": []},

    # Absential / Free Energy (Deacon / Friston)
    "absential": {"domain": "teleodynamics", "source": "Deacon 2012", "aliases": ["absential causation"]},
    "teleodynamic": {"domain": "teleodynamics", "source": "Deacon 2012", "aliases": ["teleodynamics"]},
    "active inference": {"domain": "free_energy", "source": "Friston 2010", "aliases": []},
    "free energy": {"domain": "free_energy", "source": "Friston 2006", "aliases": ["free energy principle"]},
    "self-evidencing": {"domain": "free_energy", "source": "Friston 2018", "aliases": []},
    "prediction error": {"domain": "free_energy", "source": "Friston 2010", "aliases": ["prediction_error"]},

    # Jain / Buddhist Epistemology
    "anekanta": {"domain": "jain_epistemology", "source": "Jain tradition", "aliases": ["anekantavada", "many-sidedness"]},
    "syadvada": {"domain": "jain_epistemology", "source": "Jain tradition", "aliases": ["conditional predication"]},
    "pratityasamutpada": {"domain": "buddhist_philosophy", "source": "Buddhist tradition", "aliases": ["dependent origination"]},
    "shuddhatma": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": ["pure self", "pure soul"]},
    "pratishthit atma": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": ["relative self"]},
    "samvara": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": []},
    "nirjara": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": []},
    "pratikraman": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": []},
    "karma": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": ["karmic"]},
    "moksha": {"domain": "akram_vignan", "source": "Dada Bhagwan", "aliases": ["liberation"]},

    # Stigmergy
    "stigmergy": {"domain": "swarm_intelligence", "source": "Grasse 1959", "aliases": ["stigmergic"]},
    "pheromone": {"domain": "swarm_intelligence", "source": "Grasse 1959", "aliases": ["pheromone trail"]},
    "swarm intelligence": {"domain": "swarm_intelligence", "source": "Bonabeau 1999", "aliases": ["swarm"]},

    # Self-Organization (Jantsch / Prigogine)
    "self-organization": {"domain": "self_organization", "source": "Jantsch 1980", "aliases": ["self-organizing", "self_organization"]},
    "involution": {"domain": "integral_philosophy", "source": "Aurobindo", "aliases": []},
    "supramental": {"domain": "integral_philosophy", "source": "Aurobindo", "aliases": ["supermind", "overmind"]},
    "downward causation": {"domain": "integral_philosophy", "source": "Aurobindo / Sperry", "aliases": []},

    # Architecture Patterns
    "telos": {"domain": "architecture", "source": "Aristotle / dharma_swarm", "aliases": ["teleological", "telos gate"]},
    "witness": {"domain": "architecture", "source": "Dada Bhagwan / Observer pattern", "aliases": ["witness chain", "witness separation"]},
    "ontology": {"domain": "architecture", "source": "Palantir pattern", "aliases": ["ontological"]},
    "gate": {"domain": "architecture", "source": "Beer + Dada Bhagwan", "aliases": ["gate array", "telos gate"]},
    "lineage": {"domain": "architecture", "source": "Palantir Funnel", "aliases": ["provenance"]},
    "eigenform": {"domain": "architecture", "source": "von Foerster", "aliases": ["fixed point", "S(x)=x"]},

    # R_V specific
    "participation ratio": {"domain": "mechanistic_interp", "source": "R_V paper", "aliases": ["PR", "R_V"]},
    "geometric contraction": {"domain": "mechanistic_interp", "source": "R_V paper", "aliases": ["contraction"]},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CodeEntity:
    file_path: str
    name: str
    qualified_name: str
    kind: str  # "class", "function", "method"
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    ast_hash: str = ""

@dataclass
class ConceptHit:
    concept: str
    domain: str
    source_file: str
    line: int
    context_type: str  # "docstring", "comment", "name", "string"
    context_snippet: str = ""
    confidence: float = 0.0

@dataclass
class BridgeEdge:
    code_entity: str  # file::qualified_name
    concept: str
    bridge_type: str  # "implements", "references", "name_contains"
    confidence: float = 0.0

@dataclass
class MirrorReport:
    timestamp: str = ""
    files_scanned: int = 0
    code_entities: int = 0
    concept_hits: int = 0
    unique_concepts: int = 0
    bridges: int = 0
    domain_distribution: dict = field(default_factory=dict)
    concept_density_by_file: dict = field(default_factory=dict)  # top 20
    ungrounded_files: list = field(default_factory=list)  # code with no concepts
    unimplemented_concepts: list = field(default_factory=list)  # concepts with no code
    concept_clusters: dict = field(default_factory=dict)  # co-occurrence clusters
    blast_radius_top10: list = field(default_factory=list)
    discovery_vs_claims: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 1: Parse Code
# ---------------------------------------------------------------------------

def parse_python_files(root: Path) -> list[CodeEntity]:
    """Extract all classes, functions, methods from dharma_swarm .py files."""
    entities = []
    py_files = sorted(root.rglob("*.py"))

    for py_file in py_files:
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        rel_path = str(py_file.relative_to(root))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                entities.append(CodeEntity(
                    file_path=rel_path,
                    name=node.name,
                    qualified_name=f"{rel_path}::{node.name}",
                    kind="class",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                    ast_hash=hashlib.sha256(ast.dump(node).encode()).hexdigest()[:16],
                ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if it's a method (inside a class)
                kind = "function"
                qname = f"{rel_path}::{node.name}"
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        for child in ast.iter_child_nodes(parent):
                            if child is node:
                                kind = "method"
                                qname = f"{rel_path}::{parent.name}.{node.name}"
                                break

                entities.append(CodeEntity(
                    file_path=rel_path,
                    name=node.name,
                    qualified_name=qname,
                    kind=kind,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                    ast_hash=hashlib.sha256(ast.dump(node).encode()).hexdigest()[:16],
                ))

    return entities


# ---------------------------------------------------------------------------
# Phase 2: Extract Concepts
# ---------------------------------------------------------------------------

def build_concept_pattern() -> re.Pattern:
    """Build a regex that matches any known concept or alias."""
    all_terms = []
    for concept, meta in SEED_ONTOLOGY.items():
        all_terms.append(concept)
        all_terms.extend(meta["aliases"])
    # Sort by length descending (match longer first)
    all_terms = [t for t in all_terms if len(t) >= 3]
    all_terms.sort(key=len, reverse=True)
    escaped = [re.escape(t) for t in all_terms]
    return re.compile(r'\b(' + '|'.join(escaped) + r')\b', re.IGNORECASE)


def resolve_to_canonical(term: str) -> Optional[str]:
    """Resolve a matched term to its canonical concept name."""
    term_lower = term.lower().strip()
    for concept, meta in SEED_ONTOLOGY.items():
        if term_lower == concept:
            return concept
        if term_lower in [a.lower() for a in meta["aliases"]]:
            return concept
    return None


def extract_concepts(root: Path, entities: list[CodeEntity]) -> list[ConceptHit]:
    """Extract concept references from code: docstrings, comments, names, strings."""
    pattern = build_concept_pattern()
    hits = []
    seen_files = set()

    for entity in entities:
        # Check entity name
        name_lower = entity.name.lower()
        for concept, meta in SEED_ONTOLOGY.items():
            for term in [concept] + meta["aliases"]:
                if len(term) >= 4 and term.lower().replace(" ", "_") in name_lower:
                    hits.append(ConceptHit(
                        concept=concept,
                        domain=meta["domain"],
                        source_file=entity.file_path,
                        line=entity.line_start,
                        context_type="name",
                        context_snippet=entity.name,
                        confidence=0.85,
                    ))

        # Check docstring
        if entity.docstring:
            for match in pattern.finditer(entity.docstring):
                canonical = resolve_to_canonical(match.group())
                if canonical:
                    hits.append(ConceptHit(
                        concept=canonical,
                        domain=SEED_ONTOLOGY[canonical]["domain"],
                        source_file=entity.file_path,
                        line=entity.line_start,
                        context_type="docstring",
                        context_snippet=entity.docstring[max(0, match.start()-40):match.end()+40].strip(),
                        confidence=0.9,
                    ))

    # Also scan raw file content for comments and string literals
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue
        rel_path = str(py_file.relative_to(root))
        if rel_path in seen_files:
            continue
        seen_files.add(rel_path)

        try:
            lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                for match in pattern.finditer(stripped):
                    canonical = resolve_to_canonical(match.group())
                    if canonical:
                        hits.append(ConceptHit(
                            concept=canonical,
                            domain=SEED_ONTOLOGY[canonical]["domain"],
                            source_file=rel_path,
                            line=i,
                            context_type="comment",
                            context_snippet=stripped[:120],
                            confidence=0.7,
                        ))

    return hits


# ---------------------------------------------------------------------------
# Phase 3: Build Graph + Bridges
# ---------------------------------------------------------------------------

def build_sqlite_graph(
    entities: list[CodeEntity],
    hits: list[ConceptHit],
    db_path: Path,
) -> tuple[int, int, int]:
    """Build a live SQLite graph with code nodes, concept nodes, and bridges."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        DROP TABLE IF EXISTS code_nodes;
        DROP TABLE IF EXISTS concept_nodes;
        DROP TABLE IF EXISTS bridges;
        DROP TABLE IF EXISTS concept_cooccurrence;

        CREATE TABLE code_nodes (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_start INTEGER,
            line_end INTEGER,
            has_docstring BOOLEAN,
            ast_hash TEXT
        );

        CREATE TABLE concept_nodes (
            id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            domain TEXT NOT NULL,
            source_attribution TEXT,
            hit_count INTEGER DEFAULT 0,
            file_count INTEGER DEFAULT 0
        );

        CREATE TABLE bridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_entity_id TEXT,
            concept_id TEXT,
            bridge_type TEXT,
            confidence REAL,
            source_file TEXT,
            line_number INTEGER,
            context_snippet TEXT,
            FOREIGN KEY (code_entity_id) REFERENCES code_nodes(id),
            FOREIGN KEY (concept_id) REFERENCES concept_nodes(id)
        );

        CREATE TABLE concept_cooccurrence (
            concept_a TEXT,
            concept_b TEXT,
            file_path TEXT,
            co_count INTEGER DEFAULT 1,
            PRIMARY KEY (concept_a, concept_b, file_path)
        );

        CREATE INDEX idx_bridges_concept ON bridges(concept_id);
        CREATE INDEX idx_bridges_code ON bridges(code_entity_id);
        CREATE INDEX idx_code_file ON code_nodes(file_path);
        CREATE INDEX idx_concept_domain ON concept_nodes(domain);
    """)

    # Insert code nodes
    code_count = 0
    for e in entities:
        conn.execute(
            "INSERT OR IGNORE INTO code_nodes VALUES (?,?,?,?,?,?,?,?)",
            (e.qualified_name, e.file_path, e.name, e.kind,
             e.line_start, e.line_end, bool(e.docstring), e.ast_hash)
        )
        code_count += 1

    # Aggregate concept stats
    concept_hit_counts: dict[str, int] = defaultdict(int)
    concept_file_sets: dict[str, set[str]] = defaultdict(set)
    for h in hits:
        concept_hit_counts[h.concept] += 1
        concept_file_sets[h.concept].add(h.source_file)

    # Insert concept nodes
    concept_count = 0
    for concept, meta in SEED_ONTOLOGY.items():
        hit_count = concept_hit_counts.get(concept, 0)
        file_count = len(concept_file_sets.get(concept, set()))
        if hit_count > 0:
            conn.execute(
                "INSERT OR IGNORE INTO concept_nodes VALUES (?,?,?,?,?,?)",
                (concept, concept, meta["domain"], meta["source"],
                 hit_count, file_count)
            )
            concept_count += 1

    # Insert bridges
    bridge_count = 0
    for h in hits:
        # Find the closest code entity in the same file near this line
        matching_entities = [
            e for e in entities
            if e.file_path == h.source_file
            and e.line_start <= h.line <= (e.line_end or e.line_start + 100)
        ]
        code_id = matching_entities[0].qualified_name if matching_entities else f"file::{h.source_file}"

        bridge_type = "references" if h.context_type in ("docstring", "comment") else "name_contains"
        conn.execute(
            "INSERT INTO bridges (code_entity_id, concept_id, bridge_type, confidence, source_file, line_number, context_snippet) VALUES (?,?,?,?,?,?,?)",
            (code_id, h.concept, bridge_type, h.confidence,
             h.source_file, h.line, h.context_snippet[:200])
        )
        bridge_count += 1

    # Build co-occurrence matrix
    file_concepts = defaultdict(set)
    for h in hits:
        file_concepts[h.source_file].add(h.concept)

    for file_path, concepts in file_concepts.items():
        concept_list = sorted(concepts)
        for i, a in enumerate(concept_list):
            for b in concept_list[i+1:]:
                conn.execute(
                    "INSERT OR REPLACE INTO concept_cooccurrence VALUES (?,?,?,?)",
                    (a, b, file_path, 1)
                )

    conn.commit()
    conn.close()
    return code_count, concept_count, bridge_count


# ---------------------------------------------------------------------------
# Phase 4: Analysis Queries
# ---------------------------------------------------------------------------

def run_analysis(db_path: Path) -> MirrorReport:
    """Run analytical queries on the built graph."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    report = MirrorReport(timestamp=datetime.now().isoformat())

    # Basic counts
    report.code_entities = conn.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0]
    report.concept_hits = conn.execute("SELECT COUNT(*) FROM bridges").fetchone()[0]
    report.unique_concepts = conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0]
    report.bridges = report.concept_hits

    # Domain distribution
    rows = conn.execute(
        "SELECT domain, COUNT(*) as cnt, SUM(hit_count) as total_hits "
        "FROM concept_nodes GROUP BY domain ORDER BY total_hits DESC"
    ).fetchall()
    report.domain_distribution = {
        r["domain"]: {"concepts": r["cnt"], "total_hits": r["total_hits"]}
        for r in rows
    }

    # Concept density by file (top 20)
    rows = conn.execute(
        "SELECT source_file, COUNT(*) as hit_count, COUNT(DISTINCT concept_id) as unique_concepts "
        "FROM bridges GROUP BY source_file ORDER BY unique_concepts DESC LIMIT 20"
    ).fetchall()
    report.concept_density_by_file = {
        r["source_file"]: {"hits": r["hit_count"], "unique_concepts": r["unique_concepts"]}
        for r in rows
    }

    # Blast radius: concepts with most bridges
    rows = conn.execute(
        "SELECT concept_id, COUNT(DISTINCT code_entity_id) as code_refs, "
        "COUNT(DISTINCT source_file) as file_count "
        "FROM bridges GROUP BY concept_id ORDER BY file_count DESC LIMIT 10"
    ).fetchall()
    report.blast_radius_top10 = [
        {"concept": r["concept_id"], "code_refs": r["code_refs"], "file_count": r["file_count"]}
        for r in rows
    ]

    # Co-occurrence clusters
    rows = conn.execute(
        "SELECT concept_a, concept_b, COUNT(*) as shared_files "
        "FROM concept_cooccurrence GROUP BY concept_a, concept_b "
        "ORDER BY shared_files DESC LIMIT 30"
    ).fetchall()
    report.concept_clusters = {
        f"{r['concept_a']} <-> {r['concept_b']}": r["shared_files"]
        for r in rows
    }

    # Unimplemented concepts (in ontology but zero hits)
    implemented = {r[0] for r in conn.execute("SELECT id FROM concept_nodes").fetchall()}
    report.unimplemented_concepts = [
        c for c in SEED_ONTOLOGY if c not in implemented
    ]

    # Files with most code entities but zero concept references
    rows = conn.execute("""
        SELECT cn.file_path, COUNT(*) as entity_count
        FROM code_nodes cn
        LEFT JOIN bridges b ON cn.id = b.code_entity_id
        WHERE b.id IS NULL
        GROUP BY cn.file_path
        ORDER BY entity_count DESC
        LIMIT 15
    """).fetchall()
    report.ungrounded_files = [
        {"file": r["file_path"], "entities": r["entity_count"]}
        for r in rows
    ]

    conn.close()
    return report


# ---------------------------------------------------------------------------
# Phase 5: Generate Report
# ---------------------------------------------------------------------------

def print_report(report: MirrorReport, db_path: Path):
    """Print the mirror test results."""
    print("\n" + "=" * 70)
    print("  THE MIRROR TEST: dharma_swarm understands itself")
    print("=" * 70)
    print(f"\n  Timestamp: {report.timestamp}")
    print(f"  Database:  {db_path}")

    print(f"\n{'─' * 50}")
    print(f"  CODE ENTITIES PARSED:    {report.code_entities:,}")
    print(f"  CONCEPT HITS FOUND:      {report.concept_hits:,}")
    print(f"  UNIQUE CONCEPTS ACTIVE:  {report.unique_concepts} / {len(SEED_ONTOLOGY)}")
    print(f"  BRIDGE EDGES CREATED:    {report.bridges:,}")
    print(f"  CONCEPTS NOT FOUND:      {len(report.unimplemented_concepts)}")
    print(f"{'─' * 50}")

    print("\n  PHILOSOPHICAL DOMAIN DISTRIBUTION")
    print(f"  {'Domain':<25} {'Concepts':>8} {'Total Hits':>10}")
    print(f"  {'─'*25} {'─'*8} {'─'*10}")
    for domain, stats in sorted(report.domain_distribution.items(), key=lambda x: -x[1]["total_hits"]):
        print(f"  {domain:<25} {stats['concepts']:>8} {stats['total_hits']:>10}")

    print("\n  TOP 10 HIGHEST BLAST RADIUS (most widely referenced concepts)")
    print(f"  {'Concept':<30} {'Code Refs':>9} {'Files':>6}")
    print(f"  {'─'*30} {'─'*9} {'─'*6}")
    for item in report.blast_radius_top10:
        print(f"  {item['concept']:<30} {item['code_refs']:>9} {item['file_count']:>6}")

    print("\n  TOP 20 PHILOSOPHICALLY DENSEST FILES")
    print(f"  {'File':<55} {'Hits':>5} {'Uniq':>5}")
    print(f"  {'─'*55} {'─'*5} {'─'*5}")
    for f, stats in list(report.concept_density_by_file.items())[:20]:
        print(f"  {f:<55} {stats['hits']:>5} {stats['unique_concepts']:>5}")

    print("\n  CONCEPT CO-OCCURRENCE (philosophical clusters)")
    print(f"  {'Concept Pair':<55} {'Shared Files':>12}")
    print(f"  {'─'*55} {'─'*12}")
    for pair, count in list(report.concept_clusters.items())[:15]:
        print(f"  {pair:<55} {count:>12}")

    if report.unimplemented_concepts:
        print(f"\n  CONCEPTS IN ONTOLOGY BUT NOT FOUND IN CODE ({len(report.unimplemented_concepts)})")
        for c in report.unimplemented_concepts:
            print(f"    - {c} ({SEED_ONTOLOGY[c]['domain']}, {SEED_ONTOLOGY[c]['source']})")

    if report.ungrounded_files:
        print(f"\n  CODE WITHOUT PHILOSOPHICAL GROUNDING (top 15)")
        print(f"  {'File':<55} {'Entities':>8}")
        print(f"  {'─'*55} {'─'*8}")
        for item in report.ungrounded_files[:15]:
            print(f"  {item['file']:<55} {item['entities']:>8}")

    print("\n" + "=" * 70)
    print("  MIRROR TEST COMPLETE")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 6: LLM Integration — The Loop That Matters
# ---------------------------------------------------------------------------

def build_graph_context(db_path: Path, query_concept: str) -> str:
    """Build rich graph context for an LLM query about a concept.

    This is what makes graph-informed answers different from graph-blind ones.
    The LLM gets: which files implement this concept, what co-occurs with it,
    what the blast radius is, and what's philosophically adjacent.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    sections = []

    # 1. Direct concept info
    row = conn.execute(
        "SELECT * FROM concept_nodes WHERE id = ? OR canonical_name LIKE ?",
        (query_concept, f"%{query_concept}%")
    ).fetchone()
    if row:
        sections.append(
            f"## Concept: {row['canonical_name']}\n"
            f"Domain: {row['domain']} | Source: {row['source_attribution']}\n"
            f"Referenced {row['hit_count']} times across {row['file_count']} files"
        )

    # 2. Code files that implement/reference this concept
    bridges = conn.execute(
        "SELECT DISTINCT source_file, bridge_type, COUNT(*) as refs, "
        "GROUP_CONCAT(context_snippet, ' | ') as snippets "
        "FROM bridges WHERE concept_id LIKE ? "
        "GROUP BY source_file ORDER BY refs DESC LIMIT 15",
        (f"%{query_concept}%",)
    ).fetchall()
    if bridges:
        file_lines = []
        for b in bridges:
            snippets = (b["snippets"] or "")[:200]
            file_lines.append(f"  - `{b['source_file']}` ({b['refs']} refs, {b['bridge_type']}): {snippets}")
        sections.append("## Code Files Touching This Concept\n" + "\n".join(file_lines))

    # 3. Co-occurring concepts (what appears in the same files)
    cooc = conn.execute(
        "SELECT concept_a, concept_b, SUM(co_count) as shared "
        "FROM concept_cooccurrence "
        "WHERE concept_a LIKE ? OR concept_b LIKE ? "
        "GROUP BY concept_a, concept_b ORDER BY shared DESC LIMIT 10",
        (f"%{query_concept}%", f"%{query_concept}%")
    ).fetchall()
    if cooc:
        cooc_lines = [f"  - {r['concept_a']} <-> {r['concept_b']} (shared in {r['shared']} files)" for r in cooc]
        sections.append("## Co-occurring Concepts\n" + "\n".join(cooc_lines))

    # 4. Blast radius — what else this concept touches
    blast = conn.execute(
        "SELECT b.concept_id, COUNT(DISTINCT b.source_file) as files "
        "FROM bridges b "
        "WHERE b.source_file IN (SELECT source_file FROM bridges WHERE concept_id LIKE ?) "
        "AND b.concept_id NOT LIKE ? "
        "GROUP BY b.concept_id ORDER BY files DESC LIMIT 10",
        (f"%{query_concept}%", f"%{query_concept}%")
    ).fetchall()
    if blast:
        blast_lines = [f"  - {r['concept_id']} (shared across {r['files']} of the same files)" for r in blast]
        sections.append("## Blast Radius — Concepts in the Same Files\n" + "\n".join(blast_lines))

    conn.close()
    return "\n\n".join(sections) if sections else f"No graph data found for '{query_concept}'"


def query_llm_with_graph(db_path: Path, question: str, concept: str) -> tuple[str, str]:
    """Ask an LLM the same question WITH and WITHOUT graph context.

    Returns (graph_blind_answer, graph_informed_answer).
    Uses OpenRouter free tier (deepseek or gemini flash).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ("(no OPENROUTER_API_KEY)", "(no OPENROUTER_API_KEY)")

    graph_context = build_graph_context(db_path, concept)

    def call_openrouter(prompt: str) -> str:
        payload = json.dumps({
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://dharma-swarm.dev",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"(LLM call failed: {e})"

    # Query 1: Graph-blind (just the question)
    blind_prompt = (
        f"You are an expert on the dharma_swarm codebase, a multi-agent Python system "
        f"with ~260 modules and 4300+ tests. Answer concisely.\n\n"
        f"Question: {question}"
    )

    # Query 2: Graph-informed (question + live graph data)
    informed_prompt = (
        f"You are an expert on the dharma_swarm codebase. You have access to a live "
        f"semantic graph built by scanning all 324 Python files and extracting "
        f"philosophical concept references, code-to-concept bridges, and co-occurrence data.\n\n"
        f"Here is the graph context for '{concept}':\n\n"
        f"{graph_context}\n\n"
        f"Using this graph data, answer: {question}"
    )

    print(f"\n  Calling LLM (graph-blind)...")
    blind = call_openrouter(blind_prompt)
    print(f"  Calling LLM (graph-informed)...")
    informed = call_openrouter(informed_prompt)

    return blind, informed


def run_live_demo(db_path: Path):
    """Run the live LLM demo — same question, with and without graph context."""
    demos = [
        {
            "concept": "stigmergy",
            "question": (
                "I want to add a new coordination mechanism to dharma_swarm. "
                "Which files should I look at, and what existing patterns should I follow? "
                "What concepts co-occur with the coordination layer?"
            ),
        },
        {
            "concept": "telos",
            "question": (
                "What is the blast radius of changing the telos gate system? "
                "Which files, concepts, and subsystems would be affected?"
            ),
        },
    ]

    print("\n" + "=" * 70)
    print("  PHASE 6: LLM INTEGRATION — GRAPH-INFORMED vs GRAPH-BLIND")
    print("=" * 70)

    for demo in demos:
        print(f"\n{'─' * 60}")
        print(f"  CONCEPT: {demo['concept']}")
        print(f"  QUESTION: {demo['question'][:80]}...")
        print(f"{'─' * 60}")

        # Show the graph context that the LLM will receive
        ctx = build_graph_context(db_path, demo["concept"])
        print(f"\n  GRAPH CONTEXT (what the LLM sees):")
        for line in ctx.split("\n")[:20]:
            print(f"    {line}")
        if ctx.count("\n") > 20:
            print(f"    ... ({ctx.count(chr(10)) - 20} more lines)")

        blind, informed = query_llm_with_graph(db_path, demo["question"], demo["concept"])

        print(f"\n  GRAPH-BLIND ANSWER:")
        print(f"  {'─' * 40}")
        for line in blind.split("\n"):
            print(f"    {line}")

        print(f"\n  GRAPH-INFORMED ANSWER:")
        print(f"  {'─' * 40}")
        for line in informed.split("\n"):
            print(f"    {line}")

        print(f"\n  DELTA: The graph-informed answer has access to {len(ctx)} chars")
        print(f"  of live code-to-concept mapping that the blind answer lacks.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    root = Path.home() / "dharma_swarm"
    code_root = root / "dharma_swarm"
    db_path = Path.home() / ".dharma" / "graphs" / "mirror_test.db"

    print("\n[1/6] Parsing Python files...")
    entities = parse_python_files(code_root)
    print(f"  Found {len(entities)} code entities across {len(set(e.file_path for e in entities))} files")

    print("\n[2/6] Extracting philosophical concepts...")
    hits = extract_concepts(code_root, entities)
    print(f"  Found {len(hits)} concept references")
    print(f"  Unique concepts: {len(set(h.concept for h in hits))}")

    print("\n[3/6] Building SQLite graph...")
    code_n, concept_n, bridge_n = build_sqlite_graph(entities, hits, db_path)
    print(f"  Code nodes: {code_n}, Concept nodes: {concept_n}, Bridges: {bridge_n}")

    print("\n[4/6] Running analysis queries...")
    report = run_analysis(db_path)
    report.files_scanned = len(set(e.file_path for e in entities))

    print("\n[5/6] Generating report...")
    print_report(report, db_path)

    # Save report as JSON
    report_path = db_path.parent / "mirror_test_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": report.timestamp,
            "files_scanned": report.files_scanned,
            "code_entities": report.code_entities,
            "concept_hits": report.concept_hits,
            "unique_concepts": report.unique_concepts,
            "bridges": report.bridges,
            "domain_distribution": report.domain_distribution,
            "blast_radius_top10": report.blast_radius_top10,
            "concept_density_top20": report.concept_density_by_file,
            "concept_clusters_top30": report.concept_clusters,
            "unimplemented_concepts": report.unimplemented_concepts,
            "ungrounded_files": report.ungrounded_files,
        }, f, indent=2)
    print(f"\n  JSON report saved to: {report_path}")

    print("\n[6/6] Live LLM integration...")
    run_live_demo(db_path)

    return report


if __name__ == "__main__":
    main()
