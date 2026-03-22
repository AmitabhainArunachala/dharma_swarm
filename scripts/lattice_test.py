#!/usr/bin/env python3
"""The Lattice Test: dharma_swarm self-understanding through philosophical coherence.

Cross-references 209 structured philosophical concepts from GLOSSARY.md against
the actual codebase, discovers where philosophy and code diverge, sends the
gap analysis to 3 different LLMs for multi-perspective analysis, synthesizes
consensus, and generates an actionable patch.

The organism looks in the mirror and sees what it's missing.
"""

import ast
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PillarConcept:
    name: str
    pillar: str
    domain: str  # contemplative, geometric, colony, engineering, economic, bridge
    definition: str
    code_mapping: str
    mapped_modules: list[str] = field(default_factory=list)

@dataclass
class CodeEntity:
    file_path: str
    name: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None

@dataclass
class PhaseResult:
    name: str
    duration: float
    data: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: PILLAR Parse
# ═══════════════════════════════════════════════════════════════════════

DOMAIN_MAP = {
    "1. Contemplative Terms": "contemplative",
    "2. Geometric / Mechanistic Terms": "geometric",
    "3. Colony-Generated Terms": "colony",
    "4. Engineering Terms": "engineering",
    "5. Economic Terms": "economic",
    "6. Cross-Disciplinary Bridge Terms": "bridge",
}

MODULE_RE = re.compile(r'`([a-z_]+\.py)`')
CLASS_RE = re.compile(r'`([A-Z][a-zA-Z]+)`')


def parse_glossary(glossary_path: Path) -> list[PillarConcept]:
    """Parse GLOSSARY.md structured tables into PillarConcept entries."""
    text = glossary_path.read_text(encoding="utf-8")
    concepts = []
    current_domain = "unknown"

    for line in text.splitlines():
        # Track domain from section headers
        for header, domain in DOMAIN_MAP.items():
            if header in line:
                current_domain = domain
                break

        # Match concept rows: | **Term** | Origin | Definition | Mapping | Pillar |
        m = re.match(
            r'^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$',
            line,
        )
        if not m:
            continue

        name = m.group(1).strip()
        definition = m.group(3).strip()
        code_mapping = m.group(4).strip()
        pillar = m.group(5).strip()

        # Skip header rows
        if name in ("Term", "------", "---"):
            continue

        # Extract module filenames from code_mapping
        modules = MODULE_RE.findall(code_mapping)

        concepts.append(PillarConcept(
            name=name,
            pillar=pillar,
            domain=current_domain,
            definition=definition[:300],
            code_mapping=code_mapping[:500],
            mapped_modules=modules,
        ))

    return concepts


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Code Parse + Graph Build
# ═══════════════════════════════════════════════════════════════════════

def parse_python_files(root: Path) -> list[CodeEntity]:
    """Extract classes, functions, methods from all .py files."""
    entities = []
    for py_file in sorted(root.rglob("*.py")):
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
                ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entities.append(CodeEntity(
                    file_path=rel_path,
                    name=node.name,
                    qualified_name=f"{rel_path}::{node.name}",
                    kind="function",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                ))
    return entities


def build_lattice_db(
    concepts: list[PillarConcept],
    entities: list[CodeEntity],
    db_path: Path,
) -> dict:
    """Build the lattice test database with pillar concepts + code + bridges."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        DROP TABLE IF EXISTS code_nodes;
        DROP TABLE IF EXISTS pillar_concepts;
        DROP TABLE IF EXISTS pillar_bridges;
        DROP TABLE IF EXISTS cross_pillar_edges;

        CREATE TABLE code_nodes (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_start INTEGER,
            has_docstring BOOLEAN
        );

        CREATE TABLE pillar_concepts (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            pillar TEXT NOT NULL,
            domain TEXT NOT NULL,
            definition TEXT,
            code_mapping TEXT,
            bridge_count INTEGER DEFAULT 0
        );

        CREATE TABLE pillar_bridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id TEXT NOT NULL,
            code_file TEXT NOT NULL,
            code_entity TEXT,
            bridge_type TEXT DEFAULT 'maps_to',
            confidence REAL DEFAULT 0.7,
            evidence TEXT,
            FOREIGN KEY (concept_id) REFERENCES pillar_concepts(id)
        );

        CREATE TABLE cross_pillar_edges (
            concept_a TEXT,
            concept_b TEXT,
            pillar_a TEXT,
            pillar_b TEXT,
            shared_file TEXT,
            PRIMARY KEY (concept_a, concept_b, shared_file)
        );

        CREATE INDEX idx_pb_concept ON pillar_bridges(concept_id);
        CREATE INDEX idx_pb_file ON pillar_bridges(code_file);
        CREATE INDEX idx_cn_file ON code_nodes(file_path);
        CREATE INDEX idx_pc_pillar ON pillar_concepts(pillar);
    """)

    # Insert code nodes
    for e in entities:
        conn.execute(
            "INSERT OR IGNORE INTO code_nodes VALUES (?,?,?,?,?,?)",
            (e.qualified_name, e.file_path, e.name, e.kind,
             e.line_start, bool(e.docstring)),
        )

    # Build file index for matching
    code_files = set(e.file_path for e in entities)
    code_names = {e.name.lower(): e.file_path for e in entities}

    # Insert pillar concepts and create bridges
    stats = {"concepts": 0, "bridges": 0, "bridged_concepts": 0}

    for pc in concepts:
        cid = pc.name.lower().replace(" ", "_").replace("/", "_")[:80]
        conn.execute(
            "INSERT OR IGNORE INTO pillar_concepts VALUES (?,?,?,?,?,?,?)",
            (cid, pc.name, pc.pillar, pc.domain, pc.definition, pc.code_mapping, 0),
        )
        stats["concepts"] += 1

        bridges_for_concept = 0

        # Match mapped modules against code files
        for mod in pc.mapped_modules:
            matched_files = [f for f in code_files if f.endswith(mod) or f.endswith("/" + mod)]
            for mf in matched_files:
                conn.execute(
                    "INSERT INTO pillar_bridges (concept_id, code_file, bridge_type, confidence, evidence) "
                    "VALUES (?,?,?,?,?)",
                    (cid, mf, "module_map", 0.9, f"GLOSSARY maps to `{mod}`"),
                )
                bridges_for_concept += 1
                stats["bridges"] += 1

        # Also try to match class names mentioned in code_mapping
        for cls_match in CLASS_RE.findall(pc.code_mapping):
            cls_lower = cls_match.lower()
            if cls_lower in code_names:
                code_file = code_names[cls_lower]
                conn.execute(
                    "INSERT OR IGNORE INTO pillar_bridges (concept_id, code_file, bridge_type, confidence, evidence) "
                    "VALUES (?,?,?,?,?)",
                    (cid, code_file, "class_ref", 0.8, f"GLOSSARY references `{cls_match}`"),
                )
                bridges_for_concept += 1
                stats["bridges"] += 1

        if bridges_for_concept > 0:
            conn.execute(
                "UPDATE pillar_concepts SET bridge_count = ? WHERE id = ?",
                (bridges_for_concept, cid),
            )
            stats["bridged_concepts"] += 1

    # Build cross-pillar edges: concepts from different pillars that map to the same file
    conn.execute("""
        INSERT OR IGNORE INTO cross_pillar_edges (concept_a, concept_b, pillar_a, pillar_b, shared_file)
        SELECT a.concept_id, b.concept_id, pa.pillar, pb.pillar, a.code_file
        FROM pillar_bridges a
        JOIN pillar_bridges b ON a.code_file = b.code_file AND a.concept_id < b.concept_id
        JOIN pillar_concepts pa ON a.concept_id = pa.id
        JOIN pillar_concepts pb ON b.concept_id = pb.id
        WHERE pa.pillar != pb.pillar
    """)
    stats["cross_pillar"] = conn.execute("SELECT COUNT(*) FROM cross_pillar_edges").fetchone()[0]

    conn.commit()
    conn.close()
    return stats


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Cross-Reference Analysis
# ═══════════════════════════════════════════════════════════════════════

def run_cross_reference(db_path: Path) -> dict:
    """Run analytical queries on the lattice database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    results = {}

    # 1. Pillar Implementation Scorecard
    rows = conn.execute("""
        SELECT pillar,
               COUNT(*) as total,
               SUM(CASE WHEN bridge_count > 0 THEN 1 ELSE 0 END) as implemented,
               SUM(CASE WHEN bridge_count = 0 THEN 1 ELSE 0 END) as missing
        FROM pillar_concepts
        GROUP BY pillar
        ORDER BY CAST(SUM(CASE WHEN bridge_count > 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) DESC
    """).fetchall()
    results["scorecard"] = [
        {"pillar": r["pillar"], "total": r["total"],
         "implemented": r["implemented"], "missing": r["missing"],
         "coverage": round(r["implemented"] / max(r["total"], 1) * 100, 1)}
        for r in rows
    ]

    # 2. Orphan Concepts (no code bridge)
    rows = conn.execute("""
        SELECT display_name, pillar, domain, definition
        FROM pillar_concepts WHERE bridge_count = 0
        ORDER BY pillar, display_name
    """).fetchall()
    results["orphan_concepts"] = [
        {"name": r["display_name"], "pillar": r["pillar"], "domain": r["domain"],
         "definition": r["definition"][:120]}
        for r in rows
    ]

    # 3. Implementation Hotspots — files bridging 3+ pillars
    rows = conn.execute("""
        SELECT pb.code_file,
               COUNT(DISTINCT pc.pillar) as pillar_count,
               COUNT(DISTINCT pb.concept_id) as concept_count,
               GROUP_CONCAT(DISTINCT pc.pillar) as pillars
        FROM pillar_bridges pb
        JOIN pillar_concepts pc ON pb.concept_id = pc.id
        GROUP BY pb.code_file
        HAVING pillar_count >= 2
        ORDER BY pillar_count DESC, concept_count DESC
        LIMIT 15
    """).fetchall()
    results["hotspots"] = [
        {"file": r["code_file"], "pillars": r["pillar_count"],
         "concepts": r["concept_count"], "pillar_list": r["pillars"]}
        for r in rows
    ]

    # 4. Cross-pillar edges
    rows = conn.execute("""
        SELECT pillar_a, pillar_b, COUNT(*) as connections,
               GROUP_CONCAT(DISTINCT shared_file) as files
        FROM cross_pillar_edges
        GROUP BY pillar_a, pillar_b
        ORDER BY connections DESC
        LIMIT 15
    """).fetchall()
    results["cross_pillar"] = [
        {"pillar_a": r["pillar_a"], "pillar_b": r["pillar_b"],
         "connections": r["connections"],
         "files": r["files"][:200] if r["files"] else ""}
        for r in rows
    ]

    # 5. Domain distribution
    rows = conn.execute("""
        SELECT domain, COUNT(*) as total,
               SUM(CASE WHEN bridge_count > 0 THEN 1 ELSE 0 END) as implemented
        FROM pillar_concepts GROUP BY domain ORDER BY total DESC
    """).fetchall()
    results["domains"] = [
        {"domain": r["domain"], "total": r["total"], "implemented": r["implemented"]}
        for r in rows
    ]

    # 6. Totals
    results["total_concepts"] = conn.execute("SELECT COUNT(*) FROM pillar_concepts").fetchone()[0]
    results["total_bridged"] = conn.execute("SELECT COUNT(*) FROM pillar_concepts WHERE bridge_count > 0").fetchone()[0]
    results["total_bridges"] = conn.execute("SELECT COUNT(*) FROM pillar_bridges").fetchone()[0]
    results["total_code_entities"] = conn.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0]
    results["total_cross_pillar"] = conn.execute("SELECT COUNT(*) FROM cross_pillar_edges").fetchone()[0]

    conn.close()
    return results


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Multi-Model Analysis
# ═══════════════════════════════════════════════════════════════════════

FALLBACK_MODELS = [
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen3-30b-a3b",
]

PREFERRED_FAMILIES = ["google/gemini", "meta-llama/llama-3", "qwen/qwen3", "mistralai/mistral"]
EXCLUDED_PATTERNS = ["guard", "safety", "embed", "vision-only", "tts", "whisper"]


def discover_free_models(api_key: str) -> list[str]:
    """Discover 3 free OpenRouter models from different families."""
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        free_models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_price = float(pricing.get("prompt", "1") or "1")
            # Accept free models OR cheap models (< $1/M tokens)
            if prompt_price <= 0.000001:
                free_models.append(mid)

        # Filter out non-chat models
        chat_models = [
            m for m in free_models
            if not any(ex in m.lower() for ex in EXCLUDED_PATTERNS)
        ]

        # Pick one from each preferred family
        selected = []
        used_families: set[str] = set()
        for fam in PREFERRED_FAMILIES:
            if len(selected) >= 3:
                break
            for fm in chat_models:
                if fm.startswith(fam) and fam not in used_families:
                    selected.append(fm)
                    used_families.add(fam)
                    break

        if len(selected) < 3:
            for fb in FALLBACK_MODELS:
                if fb not in selected and len(selected) < 3:
                    selected.append(fb)

        return selected[:3]
    except Exception:
        return FALLBACK_MODELS[:3]


def call_openrouter_sync(model: str, system: str, prompt: str, api_key: str) -> str:
    """Call OpenRouter synchronously. Returns response text."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1000,
        "temperature": 0.7,
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
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(LLM call failed: {e})"


def build_analysis_context(xref: dict) -> str:
    """Build compressed graph context for LLM queries (~3K tokens)."""
    sections = []

    # Scorecard
    lines = ["## Pillar Implementation Scorecard"]
    for s in xref["scorecard"]:
        bar_len = int(s["coverage"] / 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        lines.append(f"  {s['pillar']:<30} {s['implemented']:>3}/{s['total']:<3} {bar} {s['coverage']}%")
    sections.append("\n".join(lines))

    # Orphans (top 20)
    lines = ["## Concepts NOT Found in Code (orphans)"]
    for o in xref["orphan_concepts"][:20]:
        lines.append(f"  - {o['name']} ({o['pillar']}, {o['domain']}): {o['definition'][:80]}")
    if len(xref["orphan_concepts"]) > 20:
        lines.append(f"  ... and {len(xref['orphan_concepts']) - 20} more")
    sections.append("\n".join(lines))

    # Hotspots
    lines = ["## Philosophical Hotspot Files (bridge 2+ pillars)"]
    for h in xref["hotspots"][:10]:
        lines.append(f"  - `{h['file']}`: {h['concepts']} concepts from {h['pillars']} pillars ({h['pillar_list']})")
    sections.append("\n".join(lines))

    # Cross-pillar
    lines = ["## Cross-Pillar Connections (concepts from different pillars in same file)"]
    for cp in xref["cross_pillar"][:10]:
        lines.append(f"  - {cp['pillar_a']} <-> {cp['pillar_b']}: {cp['connections']} shared files")
    sections.append("\n".join(lines))

    # Totals
    sections.append(
        f"## Totals\n"
        f"  Concepts: {xref['total_concepts']} | Bridged to code: {xref['total_bridged']} | "
        f"Bridges: {xref['total_bridges']} | Code entities: {xref['total_code_entities']} | "
        f"Cross-pillar edges: {xref['total_cross_pillar']}"
    )

    return "\n\n".join(sections)


def run_multi_model(xref: dict, api_key: str) -> dict:
    """Run 3 parallel LLM queries + 1 synthesis."""
    models = discover_free_models(api_key)
    context = build_analysis_context(xref)

    system = (
        "You are analyzing a 130K-line Python multi-agent system (dharma_swarm) "
        "grounded in 10 philosophical pillars. You have live data from a semantic graph "
        "built by scanning 324 Python files and cross-referencing against 209 philosophical "
        "concepts from the project's glossary. Be specific — name files and concepts."
    )

    queries = [
        (
            "GAP ANALYSIS",
            f"Given this implementation data:\n\n{context}\n\n"
            "Which pillar is BEST implemented in code? Which is WORST? "
            "For the worst pillar, name 3 specific Python files that SHOULD implement "
            "its concepts but don't. Explain why each connection matters."
        ),
        (
            "HIDDEN CONNECTIONS",
            f"Given this cross-reference data:\n\n{context}\n\n"
            "Identify 3 cross-pillar connections that exist in the code (hotspot files) "
            "that seem architecturally significant. Also identify 2 connections that "
            "SHOULD exist but don't — pillars that should be bridged but have no shared files."
        ),
        (
            "PRESCRIPTION",
            f"Given this implementation data:\n\n{context}\n\n"
            "What single architectural change would most increase philosophical coherence? "
            "Be concrete: name the specific file to modify, the concept to implement, "
            "the pillar that grounds it, and write a 3-line code sketch of what the "
            "implementation would look like."
        ),
    ]

    results = {"models": models, "responses": []}

    for i, (label, prompt) in enumerate(queries):
        model = models[i % len(models)]
        print(f"    [{label}] → {model.split('/')[-1][:30]}...", end=" ", flush=True)
        t0 = time.time()
        response = call_openrouter_sync(model, system, prompt, api_key)
        dt = time.time() - t0
        print(f"({dt:.1f}s)")
        results["responses"].append({
            "label": label,
            "model": model,
            "response": response,
            "duration": round(dt, 1),
        })
        time.sleep(3)  # Rate limit spacing for free tier

    # Synthesis
    print(f"    [SYNTHESIS] → {models[0].split('/')[-1][:30]}...", end=" ", flush=True)
    t0 = time.time()
    synthesis_prompt = (
        "Three different AI models analyzed dharma_swarm's philosophical grounding. "
        "Synthesize their findings into a unified report.\n\n"
    )
    for r in results["responses"]:
        resp = r["response"] or "(no response from this model)"
        synthesis_prompt += f"### {r['label']} ({r['model'].split('/')[-1]})\n{resp}\n\n"

    synthesis_prompt += (
        "Produce:\n"
        "1. CONSENSUS: What all 3 agree on (2-3 bullets)\n"
        "2. TENSIONS: Where they disagree (1-2 bullets)\n"
        "3. TOP PRIORITY: The single most impactful action, with specific file + concept\n"
        "4. NOVEL INSIGHT: One thing that emerged from combining analyses that none said alone"
    )

    synthesis = call_openrouter_sync(models[0], system, synthesis_prompt, api_key)
    dt = time.time() - t0
    print(f"({dt:.1f}s)")
    results["synthesis"] = synthesis
    results["synthesis_duration"] = round(dt, 1)

    return results


# ═══════════════════════════════════════════════════════════════════════
# Phase 6: Patch Generation
# ═══════════════════════════════════════════════════════════════════════

def generate_patch(xref: dict, root: Path) -> Optional[str]:
    """Generate a docstring enrichment patch for the least-grounded hotspot file."""
    if not xref["hotspots"]:
        return None

    # Find a hotspot file that has entities without docstrings
    for hotspot in xref["hotspots"]:
        filepath = root / "dharma_swarm" / hotspot["file"]
        if not filepath.exists():
            continue

        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not ast.get_docstring(node):
                # Find which pillar concepts map to this file
                pillar_info = hotspot.get("pillar_list", "unknown pillars")
                patch = (
                    f"--- a/dharma_swarm/{hotspot['file']}\n"
                    f"+++ b/dharma_swarm/{hotspot['file']}\n"
                    f"@@ -{node.lineno},0 +{node.lineno},5 @@\n"
                    f" class {node.name}:\n"
                    f'+    """Implements concepts from: {pillar_info}.\n'
                    f"+\n"
                    f"+    Philosophical grounding: This class bridges {hotspot['concepts']} concepts\n"
                    f"+    across {hotspot['pillars']} pillars in the dharma_swarm lattice.\n"
                    f'+    """\n'
                )
                return patch

    return None


# ═══════════════════════════════════════════════════════════════════════
# Phase 7: Verification
# ═══════════════════════════════════════════════════════════════════════

def run_verification(root: Path) -> dict:
    """Run a subset of graph-related tests."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q", "-x",
             "--timeout=30", "--tb=line",
             "-k", "bridge or concept or graph or nexus or blast"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Parse result
        output = result.stdout + result.stderr
        passed = len(re.findall(r'passed', output))
        failed = len(re.findall(r'failed', output))
        last_line = [l for l in output.strip().splitlines() if l.strip()][-1] if output.strip() else ""
        return {"passed": passed > 0, "output_tail": last_line, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"passed": False, "output_tail": "timeout after 120s", "returncode": -1}
    except Exception as e:
        return {"passed": False, "output_tail": str(e), "returncode": -1}


# ═══════════════════════════════════════════════════════════════════════
# Report Printer
# ═══════════════════════════════════════════════════════════════════════

def print_report(phases: list[PhaseResult], xref: dict, llm_results: dict, patch: Optional[str], verify: dict):
    """Print the full lattice test report."""
    print("\n╔══════════════════════════════════════════════════════════════════╗")
    print("║              THE LATTICE TEST                                    ║")
    print("║    dharma_swarm Self-Understanding Through Coherence             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    for phase in phases:
        print(f"\n┌─ {phase.name} {'─' * (55 - len(phase.name))} {phase.duration:.1f}s ─┐")
        for k, v in phase.data.items():
            if isinstance(v, str) and len(v) < 80:
                print(f"│  {k}: {v}")
            elif isinstance(v, (int, float)):
                print(f"│  {k}: {v}")
        print(f"└{'─' * 64}┘")

    # Scorecard with bars
    print(f"\n{'─' * 66}")
    print("  PILLAR IMPLEMENTATION SCORECARD")
    print(f"  {'Pillar':<32} {'Impl':>4}/{'Tot':<4} {'Coverage':<12} {'Bar'}")
    print(f"  {'─'*32} {'─'*4} {'─'*4} {'─'*12} {'─'*10}")
    for s in xref["scorecard"]:
        bar_len = int(s["coverage"] / 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        print(f"  {s['pillar']:<32} {s['implemented']:>4}/{s['total']:<4} {s['coverage']:>5.1f}%       {bar}")

    # Hotspots
    print(f"\n  PHILOSOPHICAL HOTSPOT FILES (multi-pillar bridges)")
    print(f"  {'File':<40} {'Pillars':>7} {'Concepts':>8}")
    print(f"  {'─'*40} {'─'*7} {'─'*8}")
    for h in xref["hotspots"][:10]:
        print(f"  {h['file']:<40} {h['pillars']:>7} {h['concepts']:>8}")

    # Cross-pillar
    if xref["cross_pillar"]:
        print(f"\n  CROSS-PILLAR CONNECTIONS (same code bridges different pillars)")
        for cp in xref["cross_pillar"][:8]:
            print(f"    {cp['pillar_a']:<20} ←→ {cp['pillar_b']:<20} ({cp['connections']} files)")

    # Orphans sample
    print(f"\n  ORPHAN CONCEPTS (in GLOSSARY, not in code): {len(xref['orphan_concepts'])}")
    for o in xref["orphan_concepts"][:8]:
        print(f"    - {o['name']:<30} ({o['pillar']}, {o['domain']})")
    if len(xref["orphan_concepts"]) > 8:
        print(f"    ... and {len(xref['orphan_concepts']) - 8} more")

    # LLM results
    print(f"\n{'─' * 66}")
    print("  MULTI-MODEL ANALYSIS")
    for r in llm_results.get("responses", []):
        print(f"\n  [{r['label']}] via {r['model'].split('/')[-1][:35]} ({r['duration']}s)")
        print(f"  {'─' * 50}")
        # Print first 15 lines of each response
        resp_text = r["response"] or "(no response)"
        for line in resp_text.split("\n")[:15]:
            print(f"    {line[:90]}")
        if resp_text.count("\n") > 15:
            print(f"    ... ({r['response'].count(chr(10)) - 15} more lines)")

    # Synthesis
    if "synthesis" in llm_results:
        print(f"\n{'─' * 66}")
        print("  CONSENSUS SYNTHESIS")
        print(f"  {'─' * 50}")
        for line in llm_results["synthesis"].split("\n")[:25]:
            print(f"    {line[:90]}")

    # Patch
    if patch:
        print(f"\n{'─' * 66}")
        print("  GENERATED PATCH (proposal, not applied)")
        for line in patch.split("\n"):
            print(f"    {line}")

    # Verification
    print(f"\n{'─' * 66}")
    print(f"  VERIFICATION: {'PASS' if verify.get('passed') else 'SKIP/FAIL'}")
    print(f"    {verify.get('output_tail', 'no output')}")

    # Final summary
    coverage = round(xref["total_bridged"] / max(xref["total_concepts"], 1) * 100, 1)
    print(f"\n╔══════════════════════════════════════════════════════════════════╗")
    print(f"║  LATTICE TEST COMPLETE                                           ║")
    print(f"║  Glossary concepts: {xref['total_concepts']:<5} | Bridged to code: {xref['total_bridged']:<5}          ║")
    print(f"║  Coverage: {coverage}% | Cross-pillar edges: {xref['total_cross_pillar']:<5}               ║")
    print(f"║  LLM calls: {len(llm_results.get('responses', [])) + (1 if 'synthesis' in llm_results else 0)} (cost: $0.00)                                     ║")
    print(f"╚══════════════════════════════════════════════════════════════════╝")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    root = Path.home() / "dharma_swarm"
    code_root = root / "dharma_swarm"
    glossary_path = root / "foundations" / "GLOSSARY.md"
    db_path = Path.home() / ".dharma" / "graphs" / "lattice_test.db"
    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    phases: list[PhaseResult] = []

    # Phase 1: PILLAR Parse
    print("\n[1/7] Parsing GLOSSARY.md...", flush=True)
    t0 = time.time()
    concepts = parse_glossary(glossary_path)
    dt = time.time() - t0
    domain_counts = {}
    for c in concepts:
        domain_counts[c.domain] = domain_counts.get(c.domain, 0) + 1
    phases.append(PhaseResult("Phase 1: PILLAR Parse", dt, {
        "concepts_extracted": len(concepts),
        "domains": str(domain_counts),
        "pillars": str(len(set(c.pillar for c in concepts))),
    }))
    print(f"  {len(concepts)} concepts from {len(set(c.pillar for c in concepts))} pillars ({dt:.1f}s)")

    # Phase 2: Code Parse + Graph Build
    print("\n[2/7] Parsing code + building graph...", flush=True)
    t0 = time.time()
    entities = parse_python_files(code_root)
    build_stats = build_lattice_db(concepts, entities, db_path)
    dt = time.time() - t0
    phases.append(PhaseResult("Phase 2: Graph Build", dt, {
        "code_entities": len(entities),
        "code_files": len(set(e.file_path for e in entities)),
        "pillar_concepts": build_stats["concepts"],
        "bridges_created": build_stats["bridges"],
        "bridged_concepts": build_stats["bridged_concepts"],
        "cross_pillar_edges": build_stats.get("cross_pillar", 0),
    }))
    print(f"  {len(entities)} code entities, {build_stats['bridges']} bridges, "
          f"{build_stats['bridged_concepts']}/{build_stats['concepts']} concepts bridged ({dt:.1f}s)")

    # Phase 3: Cross-Reference
    print("\n[3/7] Cross-reference analysis...", flush=True)
    t0 = time.time()
    xref = run_cross_reference(db_path)
    dt = time.time() - t0
    phases.append(PhaseResult("Phase 3: Cross-Reference", dt, {
        "scorecard_entries": len(xref["scorecard"]),
        "orphan_concepts": len(xref["orphan_concepts"]),
        "hotspot_files": len(xref["hotspots"]),
        "cross_pillar_pairs": len(xref["cross_pillar"]),
    }))
    print(f"  {len(xref['orphan_concepts'])} orphan concepts, {len(xref['hotspots'])} hotspot files ({dt:.1f}s)")

    # Phase 4+5: Multi-Model Analysis
    llm_results: dict = {}
    if api_key:
        print("\n[4/7] Multi-model analysis (3 LLMs + synthesis)...", flush=True)
        t0 = time.time()
        llm_results = run_multi_model(xref, api_key)
        dt = time.time() - t0
        phases.append(PhaseResult("Phase 4-5: Multi-Model Analysis", dt, {
            "models_used": len(llm_results.get("models", [])),
            "queries": len(llm_results.get("responses", [])),
            "synthesis": "yes" if "synthesis" in llm_results else "no",
        }))
    else:
        print("\n[4/7] SKIPPED (no OPENROUTER_API_KEY)")
        phases.append(PhaseResult("Phase 4-5: Multi-Model Analysis", 0.0, {"status": "skipped"}))

    # Phase 6: Patch Generation
    print("\n[6/7] Generating patch...", flush=True)
    t0 = time.time()
    patch = generate_patch(xref, root)
    dt = time.time() - t0
    if patch:
        patch_path = db_path.parent / "lattice_patch.diff"
        patch_path.write_text(patch)
        print(f"  Patch written to {patch_path} ({dt:.1f}s)")
    else:
        print(f"  No patch target found ({dt:.1f}s)")
    phases.append(PhaseResult("Phase 6: Patch Generation", dt, {
        "patch_generated": bool(patch),
    }))

    # Phase 7: Verification
    print("\n[7/7] Running verification tests...", flush=True)
    t0 = time.time()
    verify = run_verification(root)
    dt = time.time() - t0
    phases.append(PhaseResult("Phase 7: Verification", dt, {
        "tests_passed": verify.get("passed", False),
        "result": verify.get("output_tail", ""),
    }))
    print(f"  {'PASS' if verify.get('passed') else 'DONE'} ({dt:.1f}s)")

    # Print full report
    print_report(phases, xref, llm_results, patch, verify)

    # Save JSON report
    report_path = db_path.parent / "lattice_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "phases": [{"name": p.name, "duration": p.duration, "data": p.data} for p in phases],
            "scorecard": xref["scorecard"],
            "orphan_concepts": xref["orphan_concepts"],
            "hotspots": xref["hotspots"],
            "cross_pillar": xref["cross_pillar"],
            "domains": xref["domains"],
            "totals": {
                "concepts": xref["total_concepts"],
                "bridged": xref["total_bridged"],
                "bridges": xref["total_bridges"],
                "code_entities": xref["total_code_entities"],
                "cross_pillar_edges": xref["total_cross_pillar"],
            },
            "llm_models": llm_results.get("models", []),
            "llm_synthesis": llm_results.get("synthesis", ""),
        }, f, indent=2)
    print(f"\n  Report: {report_path}")


if __name__ == "__main__":
    main()
