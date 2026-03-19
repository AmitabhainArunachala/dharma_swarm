"""File Profile — rich metadata layer for every file in the ecosystem.

Phase 2 of the 1000x Stigmergy plan.  Computes semantic density,
connectivity, impact scores, structural metrics, and stigmergy
integration for every file touched by dharma_swarm.

Design:
  - Synchronous (batch operation, not real-time)
  - SQLite-backed at ~/.dharma/file_profiles.db
  - YAML frontmatter parsing inline (no PyYAML dep)
  - Python structural analysis via ast (no external dep)
  - Markdown analysis via regex
  - Stigmergy integration reads marks.jsonl directly (sync)

Does NOT import from xray.py, lineage.py, catalytic_graph.py, or
semantic_gravity.py to avoid circular dependencies.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", ".next", ".nuxt", "coverage", ".coverage", ".worktrees",
}

ANALYZABLE_EXTS = {
    ".py", ".md", ".rst", ".txt", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".js", ".ts", ".jsx", ".tsx",
}

MAX_FILE_SIZE = 512 * 1024  # 512KB
MAX_FILES_PER_DIR = 5000

# English stopwords (compact set, good enough for density calc)
_STOPWORDS = frozenset(
    "a an the and or but if in on at to for of is it its this that "
    "be was were been are am has have had do does did will would could "
    "should may might shall can not no nor so as by from with into "
    "than then them they their there these those he she we you i my "
    "your our his her me us him all any each few more most other some "
    "such only own same too very just because also about between through "
    "during before after above below up down out off over under again "
    "further once here how what which who whom why where when def class "
    "import return self none true false".split()
)

VALID_DOMAINS = {"code", "research", "vault", "config", "state"}
VALID_FACTORY_STAGES = {"Ideation", "Development", "Staging", "Anti-Slop", "Shipping"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _file_id(path: str) -> str:
    """Deterministic 16-char hex ID from absolute path."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FileProfile(BaseModel):
    """Rich metadata profile for a single file in the ecosystem."""

    id: str                             # SHA-256[:16] of absolute path
    path: str                           # Absolute file path
    filename: str                       # Basename
    domain: str                         # code | research | vault | config | state
    last_profiled: datetime             # When profile was last computed

    # Semantic richness
    semantic_density: float = 0.0       # 0.0-1.0 — unique_concepts/total_words
    connectivity_degree: int = 0        # How many other files referenced or reference this
    impact_score: float = 0.0           # 0.0-1.0 — downstream effect estimate
    mission_alignment: float = 0.0      # 0.0-1.0 — distance to active telos goals
    mentions_count: int = 0             # How many other files/sources mentioned IN this file

    # Structural analysis
    lines: int = 0
    complexity: float = 0.0             # Cyclomatic (code) or conceptual density (docs)
    functions_count: int = 0
    imports_count: int = 0

    # Graph position
    scc_id: str | None = None           # Strongly connected component
    concept_count: int = 0              # Named concepts extracted
    edge_types: dict[str, int] = Field(default_factory=dict)

    # Stigmergy integration
    mark_count: int = 0                 # How many marks reference this file
    access_frequency: float = 0.0       # Marks/day over last 7 days
    highest_salience: float = 0.0       # Max salience of any mark on this file
    last_marked: datetime | None = None

    # YAML frontmatter
    frontmatter: dict = Field(default_factory=dict)
    frontmatter_valid: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FRONTMATTER PARSING (inline, no PyYAML)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Profile frontmatter schema — reference for what fields are recognized.
# Not enforced programmatically (frontmatter is optional), but used by
# validate_profile_frontmatter() if needed downstream.
PROFILE_FM_SCHEMA: dict[str, type | tuple[type, ...]] = {
    "title": str,
    "domain": str,
    "semantic_density": float,
    "mission_alignment": float,
    "last_profiled": str,
    "connecting_files": list,
    "telos_tags": list,
    "factory_stage": str,
    "readiness_measure": (int, float),
}


def _coerce_scalar(value: str) -> Any:
    """Coerce a YAML scalar string to Python type."""
    v = value.strip()
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except ValueError:
            return v
    if re.fullmatch(r"-?\d+\.\d+", v):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def parse_frontmatter(text: str) -> tuple[dict[str, Any], list[str]]:
    """Parse YAML frontmatter from file content.

    Returns (frontmatter_dict, errors).  Empty dict if no frontmatter found.
    """
    lines = text.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return {}, []

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, ["Unclosed frontmatter block"]

    fm_text = "".join(lines[1:end_idx])
    return _parse_simple_yaml(fm_text)


def _parse_simple_yaml(yaml_text: str) -> tuple[dict[str, Any], list[str]]:
    """Parse a minimal YAML subset: scalars and lists."""
    errors: list[str] = []
    fm: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None

    for raw_line in yaml_text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        stripped = line.strip()

        # List item
        if stripped.startswith("- "):
            if current_key is None:
                errors.append("List item without preceding key")
                continue
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            item = stripped[2:].strip().strip('"').strip("'")
            current_list.append(_coerce_scalar(item))
            continue

        # New key
        if ":" not in line:
            errors.append(f"Invalid line: {line}")
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        current_key = key
        current_list = None

        if value == "":
            fm[key] = []
            current_list = fm[key]
            continue

        fm[key] = _coerce_scalar(value.strip('"').strip("'"))

    return fm, errors


def validate_profile_frontmatter(fm: dict[str, Any]) -> list[str]:
    """Validate frontmatter against the profile schema.  Returns errors."""
    errors: list[str] = []

    if "domain" in fm and fm["domain"] not in VALID_DOMAINS:
        errors.append(f"Invalid domain: {fm['domain']}")

    if "factory_stage" in fm and fm["factory_stage"] not in VALID_FACTORY_STAGES:
        errors.append(f"Invalid factory_stage: {fm['factory_stage']}")

    if "readiness_measure" in fm:
        rm = fm["readiness_measure"]
        if isinstance(rm, (int, float)) and not (0 <= rm <= 100):
            errors.append(f"readiness_measure out of range [0,100]: {rm}")

    if "semantic_density" in fm:
        sd = fm["semantic_density"]
        if isinstance(sd, (int, float)) and not (0.0 <= sd <= 1.0):
            errors.append(f"semantic_density out of range [0,1]: {sd}")

    if "mission_alignment" in fm:
        ma = fm["mission_alignment"]
        if isinstance(ma, (int, float)) and not (0.0 <= ma <= 1.0):
            errors.append(f"mission_alignment out of range [0,1]: {ma}")

    if "connecting_files" in fm and not isinstance(fm["connecting_files"], list):
        errors.append("connecting_files must be a list")

    if "telos_tags" in fm and not isinstance(fm["telos_tags"], list):
        errors.append("telos_tags must be a list")

    return errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALYSIS HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _detect_domain(path: Path) -> str:
    """Infer domain from file path and extension."""
    s = str(path)
    ext = path.suffix.lower()

    # State: anything under ~/.dharma/
    if "/.dharma/" in s:
        return "state"

    # Config files
    if ext in {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}:
        return "config"

    # Code files
    if ext in {".py", ".js", ".ts", ".jsx", ".tsx"}:
        return "code"

    # Research vs vault for markdown
    if ext in {".md", ".rst", ".txt"}:
        lower = s.lower()
        if "vault" in lower or "psmv" in lower or "kailash" in lower:
            return "vault"
        if "paper" in lower or "research" in lower or "mech-interp" in lower:
            return "research"
        # Default markdown to research
        return "research"

    return "config"


def _semantic_density(text: str) -> float:
    """Compute unique meaningful words / total words, clamped to [0, 1]."""
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
    if not words:
        return 0.0
    meaningful = [w for w in words if w not in _STOPWORDS]
    if not meaningful:
        return 0.0
    unique = set(meaningful)
    # Ratio of unique meaningful words to total words
    density = len(unique) / len(words)
    return min(1.0, max(0.0, density))


def _concept_count(text: str) -> int:
    """Count named concepts: CamelCase identifiers, UPPER_CONSTANTS, key terms."""
    camel = set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    upper = set(re.findall(r"\b[A-Z][A-Z_]{2,}\b", text))
    return len(camel) + len(upper)


def _count_file_references(text: str) -> int:
    """Count references to other files: imports, paths, wikilinks."""
    count = 0
    # Python imports
    count += len(re.findall(r"^(?:from|import)\s+\S+", text, re.MULTILINE))
    # File paths (anything that looks like a relative/absolute path to a file)
    count += len(re.findall(r"(?:~/|/[\w.]+/|\./)[\w./-]+\.\w+", text))
    # Wikilinks [[...]]
    count += len(re.findall(r"\[\[.+?\]\]", text))
    # Markdown links to files [text](path)
    count += len(re.findall(r"\]\((?!http)[^\)]+\.\w+\)", text))
    return count


# ── Python analysis ──────────────────────────────────────────────────────


def _analyze_python(text: str) -> dict[str, Any]:
    """Analyze a Python file using the ast module.

    Returns dict with: functions_count, imports_count, complexity, classes_count.
    """
    result = {
        "functions_count": 0,
        "imports_count": 0,
        "complexity": 0.0,
        "classes_count": 0,
    }
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return result

    # Count functions (including async), classes, imports
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions_count"] += 1
        elif isinstance(node, ast.ClassDef):
            result["classes_count"] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            result["imports_count"] += 1

    # Cyclomatic complexity: count decision points + 1
    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(node, ast.ExceptHandler):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # Each 'and'/'or' adds a path
            complexity += len(node.values) - 1
        elif isinstance(node, (ast.IfExp,)):  # ternary
            complexity += 1
        elif isinstance(node, ast.Assert):
            complexity += 1
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            complexity += 1
    result["complexity"] = float(complexity)

    return result


# ── Markdown analysis ────────────────────────────────────────────────────


def _analyze_markdown(text: str) -> dict[str, Any]:
    """Analyze a Markdown file for structure and density.

    Returns dict with: headers, links_count, conceptual_complexity.
    """
    headers = len(re.findall(r"^#{1,6}\s+", text, re.MULTILINE))
    links = len(re.findall(r"\[.+?\]\(.+?\)", text))
    wikilinks = len(re.findall(r"\[\[.+?\]\]", text))
    code_blocks = len(re.findall(r"^```", text, re.MULTILINE))

    # Conceptual complexity: headers * 2 + code_blocks + links
    complexity = float(headers * 2 + code_blocks + links + wikilinks)
    return {
        "headers": headers,
        "links_count": links + wikilinks,
        "complexity": complexity,
    }


# ── Stigmergy integration (sync) ────────────────────────────────────────


def _load_marks_sync(marks_file: Path) -> list[dict[str, Any]]:
    """Load marks from JSONL file synchronously.  Tolerant of bad lines."""
    if not marks_file.exists():
        return []
    marks: list[dict[str, Any]] = []
    try:
        with open(marks_file, "r") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    marks.append(json.loads(stripped))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        pass
    return marks


def _marks_for_file(all_marks: list[dict[str, Any]], file_path: str) -> list[dict[str, Any]]:
    """Filter marks that reference a specific file path."""
    return [m for m in all_marks if m.get("file_path") == file_path]


def _compute_mark_stats(marks: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute stigmergy stats from marks for a single file."""
    if not marks:
        return {
            "mark_count": 0,
            "access_frequency": 0.0,
            "highest_salience": 0.0,
            "last_marked": None,
        }

    now = _utc_now()
    seven_days_ago = now.timestamp() - (7 * 86400)
    recent_count = 0
    highest_salience = 0.0
    last_marked: datetime | None = None

    for m in marks:
        salience = m.get("salience", 0.5)
        if salience > highest_salience:
            highest_salience = salience

        ts_str = m.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if last_marked is None or ts > last_marked:
                    last_marked = ts
                if ts.timestamp() >= seven_days_ago:
                    recent_count += 1
            except (ValueError, TypeError):
                pass

    return {
        "mark_count": len(marks),
        "access_frequency": round(recent_count / 7.0, 4),
        "highest_salience": round(highest_salience, 4),
        "last_marked": last_marked,
    }


# ── Mission alignment ────────────────────────────────────────────────────

# Telos keywords map: each telos star has associated keywords
_TELOS_KEYWORDS: dict[str, list[str]] = {
    "T1": ["truth", "satya", "verifiable", "honest", "evidence", "proof"],
    "T2": ["resilience", "tapas", "robust", "fault", "recovery", "stress"],
    "T3": ["flourishing", "ahimsa", "welfare", "wellbeing", "kalyan", "benefit"],
    "T4": ["sovereignty", "swaraj", "autonomy", "self-govern", "independent"],
    "T5": ["coherence", "dharma", "consistent", "pattern", "aligned", "unified"],
    "T6": ["emergence", "shakti", "novel", "creative", "adjacent", "evolve"],
    "T7": ["liberation", "moksha", "karma", "binding", "witness", "release"],
}


def _mission_alignment(text: str) -> float:
    """Estimate mission alignment from telos keyword presence.

    Score: fraction of telos stars that have at least one keyword match.
    """
    lower = text.lower()
    hits = 0
    for keywords in _TELOS_KEYWORDS.values():
        if any(kw in lower for kw in keywords):
            hits += 1
    return round(hits / len(_TELOS_KEYWORDS), 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SQLITE SCHEMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_profiles (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT,
    domain TEXT,
    last_profiled TEXT,
    semantic_density REAL DEFAULT 0.0,
    connectivity_degree INTEGER DEFAULT 0,
    impact_score REAL DEFAULT 0.0,
    mission_alignment REAL DEFAULT 0.0,
    mentions_count INTEGER DEFAULT 0,
    lines INTEGER DEFAULT 0,
    complexity REAL DEFAULT 0.0,
    functions_count INTEGER DEFAULT 0,
    imports_count INTEGER DEFAULT 0,
    scc_id TEXT,
    concept_count INTEGER DEFAULT 0,
    edge_types TEXT DEFAULT '{}',
    mark_count INTEGER DEFAULT 0,
    access_frequency REAL DEFAULT 0.0,
    highest_salience REAL DEFAULT 0.0,
    last_marked TEXT,
    frontmatter TEXT DEFAULT '{}',
    frontmatter_valid INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_profiles_domain ON file_profiles(domain);
CREATE INDEX IF NOT EXISTS idx_profiles_density ON file_profiles(semantic_density);
CREATE INDEX IF NOT EXISTS idx_profiles_impact ON file_profiles(impact_score);
CREATE INDEX IF NOT EXISTS idx_profiles_connectivity ON file_profiles(connectivity_degree);
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROFILE ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ProfileEngine:
    """Computes and caches FileProfile metadata for every file in the ecosystem.

    Synchronous — designed for batch profiling, not real-time.  Reads
    stigmergy marks from the JSONL file directly (no async dep).

    Usage::

        engine = ProfileEngine()
        profile = engine.profile_file("~/dharma_swarm/dharma_swarm/models.py")
        richest = engine.richest_files(limit=10)
        stale = engine.stale_profiles(max_age_hours=12)
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        stigmergy_path: Path | str | None = None,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".dharma" / "file_profiles.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if stigmergy_path is None:
            stigmergy_path = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
        self._stigmergy_path = Path(stigmergy_path)

        self._init_db()
        # Lazily loaded marks cache (reset per profile_directory call)
        self._marks_cache: list[dict[str, Any]] | None = None

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_marks_loaded(self) -> list[dict[str, Any]]:
        if self._marks_cache is None:
            self._marks_cache = _load_marks_sync(self._stigmergy_path)
        return self._marks_cache

    # ── Core profiling ─────────────────────────────────────────────────

    def profile_file(self, path: str | Path) -> FileProfile:
        """Compute a full profile for a single file and save to SQLite."""
        p = Path(path).expanduser().resolve()
        abs_path = str(p)

        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {abs_path}")

        now = _utc_now()
        fid = _file_id(abs_path)
        domain = _detect_domain(p)

        # Read file content
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Cannot read %s: %s", abs_path, e)
            text = ""

        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

        # Structural analysis based on file type
        ext = p.suffix.lower()
        functions_count = 0
        imports_count = 0
        complexity = 0.0

        if ext == ".py":
            py_info = _analyze_python(text)
            functions_count = py_info["functions_count"]
            imports_count = py_info["imports_count"]
            complexity = py_info["complexity"]
        elif ext in {".md", ".rst", ".txt"}:
            md_info = _analyze_markdown(text)
            complexity = md_info["complexity"]

        # Semantic density
        density = _semantic_density(text)

        # Concept count
        concepts = _concept_count(text)

        # File references (connectivity seed)
        mentions = _count_file_references(text)

        # Mission alignment
        alignment = _mission_alignment(text)

        # Frontmatter
        fm: dict[str, Any] = {}
        fm_valid = False
        if ext in {".md", ".rst", ".txt"}:
            fm, fm_errors = parse_frontmatter(text)
            if fm:
                validation_errors = validate_profile_frontmatter(fm)
                fm_valid = len(validation_errors) == 0 and len(fm_errors) == 0

        # Stigmergy integration
        all_marks = self._ensure_marks_loaded()
        file_marks = _marks_for_file(all_marks, abs_path)
        mark_stats = _compute_mark_stats(file_marks)

        # Edge types from imports and references
        edge_types: dict[str, int] = {}
        if imports_count > 0:
            edge_types["import"] = imports_count
        wikilink_count = len(re.findall(r"\[\[.+?\]\]", text))
        if wikilink_count > 0:
            edge_types["wikilink"] = wikilink_count
        path_ref_count = len(re.findall(r"(?:~/|/[\w.]+/|\./)[\w./-]+\.\w+", text))
        if path_ref_count > 0:
            edge_types["path_ref"] = path_ref_count

        # Connectivity = imports + mentions (references to/from other files)
        connectivity = imports_count + mentions

        # Impact score: combination of connectivity, mark activity, and density
        # Files that are highly connected AND semantically rich AND actively marked
        # have the highest downstream impact potential
        conn_factor = min(1.0, connectivity / 50.0)    # saturates at 50 refs
        mark_factor = min(1.0, mark_stats["mark_count"] / 10.0)  # saturates at 10
        impact = round(0.5 * conn_factor + 0.3 * density + 0.2 * mark_factor, 4)

        profile = FileProfile(
            id=fid,
            path=abs_path,
            filename=p.name,
            domain=domain,
            last_profiled=now,
            semantic_density=round(density, 4),
            connectivity_degree=connectivity,
            impact_score=impact,
            mission_alignment=alignment,
            mentions_count=mentions,
            lines=line_count,
            complexity=round(complexity, 2),
            functions_count=functions_count,
            imports_count=imports_count,
            concept_count=concepts,
            edge_types=edge_types,
            mark_count=mark_stats["mark_count"],
            access_frequency=mark_stats["access_frequency"],
            highest_salience=mark_stats["highest_salience"],
            last_marked=mark_stats["last_marked"],
            frontmatter=fm,
            frontmatter_valid=fm_valid,
        )

        self._save_profile(profile)
        return profile

    def profile_directory(
        self,
        path: str | Path,
        recursive: bool = True,
    ) -> list[FileProfile]:
        """Profile all analyzable files in a directory.

        Resets the marks cache to get a consistent snapshot, then profiles
        each discovered file.
        """
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

        # Reset marks cache for consistent snapshot
        self._marks_cache = None

        profiles: list[FileProfile] = []
        file_count = 0

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip noise directories
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not d.endswith(".egg-info")]
            if not recursive:
                dirnames.clear()

            for name in filenames:
                if file_count >= MAX_FILES_PER_DIR:
                    logger.warning("Hit max files limit (%d) in %s", MAX_FILES_PER_DIR, root)
                    return profiles

                fp = Path(dirpath) / name
                if fp.suffix.lower() not in ANALYZABLE_EXTS:
                    continue
                try:
                    if fp.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue

                try:
                    profile = self.profile_file(fp)
                    profiles.append(profile)
                    file_count += 1
                except (OSError, FileNotFoundError) as e:
                    logger.debug("Skipping %s: %s", fp, e)

        return profiles

    # ── Retrieval ──────────────────────────────────────────────────────

    def get_profile(self, path: str | Path) -> FileProfile | None:
        """Retrieve a cached profile from SQLite.  None if not found."""
        p = Path(path).expanduser().resolve()
        fid = _file_id(str(p))
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM file_profiles WHERE id = ?", (fid,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_profile(row)

    def stale_profiles(self, max_age_hours: float = 24) -> list[str]:
        """Return paths of profiles older than max_age_hours."""
        cutoff = _utc_now().timestamp() - (max_age_hours * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT path FROM file_profiles WHERE last_profiled < ?",
                (cutoff_iso,),
            ).fetchall()
        return [r[0] for r in rows]

    def all_profiles(self) -> list[FileProfile]:
        """Return all cached profiles."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles ORDER BY semantic_density DESC"
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    # ── Ranked queries ─────────────────────────────────────────────────

    def richest_files(self, limit: int = 20) -> list[FileProfile]:
        """Files with highest semantic_density."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles ORDER BY semantic_density DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def most_connected(self, limit: int = 20) -> list[FileProfile]:
        """Files with highest connectivity_degree."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles ORDER BY connectivity_degree DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def highest_impact(self, limit: int = 20) -> list[FileProfile]:
        """Files with highest impact_score."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles ORDER BY impact_score DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def most_active(self, limit: int = 20) -> list[FileProfile]:
        """Files with highest recent stigmergy activity."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles ORDER BY access_frequency DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def by_domain(self, domain: str) -> list[FileProfile]:
        """All profiles for a given domain."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM file_profiles WHERE domain = ? ORDER BY impact_score DESC",
                (domain,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def gaps(self) -> list[FileProfile]:
        """High connectivity but low semantic_density — curiosity targets.

        These are files that many other files reference but that have
        relatively thin content.  Prime targets for enrichment.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM file_profiles
                   WHERE connectivity_degree > 5 AND semantic_density < 0.3
                   ORDER BY connectivity_degree DESC""",
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Aggregate statistics across all profiled files."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM file_profiles").fetchone()[0]
            if total == 0:
                return {
                    "total_profiled": 0,
                    "domains": {},
                    "avg_density": 0.0,
                    "avg_impact": 0.0,
                    "avg_connectivity": 0.0,
                    "total_lines": 0,
                    "total_marks": 0,
                }

            domains = dict(conn.execute(
                "SELECT domain, COUNT(*) FROM file_profiles GROUP BY domain"
            ).fetchall())

            avg_density = conn.execute(
                "SELECT AVG(semantic_density) FROM file_profiles"
            ).fetchone()[0] or 0.0

            avg_impact = conn.execute(
                "SELECT AVG(impact_score) FROM file_profiles"
            ).fetchone()[0] or 0.0

            avg_connectivity = conn.execute(
                "SELECT AVG(connectivity_degree) FROM file_profiles"
            ).fetchone()[0] or 0.0

            total_lines = conn.execute(
                "SELECT SUM(lines) FROM file_profiles"
            ).fetchone()[0] or 0

            total_marks = conn.execute(
                "SELECT SUM(mark_count) FROM file_profiles"
            ).fetchone()[0] or 0

        return {
            "total_profiled": total,
            "domains": domains,
            "avg_density": round(avg_density, 4),
            "avg_impact": round(avg_impact, 4),
            "avg_connectivity": round(avg_connectivity, 2),
            "total_lines": total_lines,
            "total_marks": total_marks,
        }

    def summary(self) -> str:
        """Human-readable summary of the profile database."""
        s = self.stats()
        if s["total_profiled"] == 0:
            return "File Profiles: empty (no files profiled yet)"
        domain_str = ", ".join(f"{d}={c}" for d, c in sorted(s["domains"].items()))
        return (
            f"File Profiles: {s['total_profiled']} files, "
            f"{s['total_lines']} lines, "
            f"avg density={s['avg_density']:.3f}, "
            f"avg impact={s['avg_impact']:.3f} | "
            f"domains: {domain_str}"
        )

    # ── Persistence ────────────────────────────────────────────────────

    def _save_profile(self, profile: FileProfile) -> None:
        """Upsert a profile into SQLite."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO file_profiles
                   (id, path, filename, domain, last_profiled,
                    semantic_density, connectivity_degree, impact_score,
                    mission_alignment, mentions_count, lines, complexity,
                    functions_count, imports_count, scc_id, concept_count,
                    edge_types, mark_count, access_frequency,
                    highest_salience, last_marked, frontmatter,
                    frontmatter_valid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile.id,
                    profile.path,
                    profile.filename,
                    profile.domain,
                    profile.last_profiled.isoformat(),
                    profile.semantic_density,
                    profile.connectivity_degree,
                    profile.impact_score,
                    profile.mission_alignment,
                    profile.mentions_count,
                    profile.lines,
                    profile.complexity,
                    profile.functions_count,
                    profile.imports_count,
                    profile.scc_id,
                    profile.concept_count,
                    json.dumps(profile.edge_types),
                    profile.mark_count,
                    profile.access_frequency,
                    profile.highest_salience,
                    profile.last_marked.isoformat() if profile.last_marked else None,
                    json.dumps(profile.frontmatter),
                    1 if profile.frontmatter_valid else 0,
                ),
            )

    def _row_to_profile(self, row: tuple) -> FileProfile:
        """Convert a SQLite row to a FileProfile.

        Column order matches the CREATE TABLE statement.
        """
        last_marked_str = row[20]
        last_marked: datetime | None = None
        if last_marked_str:
            try:
                last_marked = datetime.fromisoformat(last_marked_str)
            except (ValueError, TypeError):
                pass

        last_profiled_str = row[4]
        try:
            last_profiled = datetime.fromisoformat(last_profiled_str)
        except (ValueError, TypeError):
            last_profiled = _utc_now()

        edge_types_raw = row[16]
        try:
            edge_types = json.loads(edge_types_raw) if edge_types_raw else {}
        except (json.JSONDecodeError, TypeError):
            edge_types = {}

        fm_raw = row[21]
        try:
            frontmatter = json.loads(fm_raw) if fm_raw else {}
        except (json.JSONDecodeError, TypeError):
            frontmatter = {}

        return FileProfile(
            id=row[0],
            path=row[1],
            filename=row[2] or "",
            domain=row[3] or "config",
            last_profiled=last_profiled,
            semantic_density=row[5] or 0.0,
            connectivity_degree=row[6] or 0,
            impact_score=row[7] or 0.0,
            mission_alignment=row[8] or 0.0,
            mentions_count=row[9] or 0,
            lines=row[10] or 0,
            complexity=row[11] or 0.0,
            functions_count=row[12] or 0,
            imports_count=row[13] or 0,
            scc_id=row[14],
            concept_count=row[15] or 0,
            edge_types=edge_types,
            mark_count=row[17] or 0,
            access_frequency=row[18] or 0.0,
            highest_salience=row[19] or 0.0,
            last_marked=last_marked,
            frontmatter=frontmatter,
            frontmatter_valid=bool(row[22]),
        )

    def clear(self) -> None:
        """Delete all profiles.  Use with caution."""
        with self._conn() as conn:
            conn.execute("DELETE FROM file_profiles")

    def delete_profile(self, path: str | Path) -> bool:
        """Delete a single profile by file path.  Returns True if found."""
        p = Path(path).expanduser().resolve()
        fid = _file_id(str(p))
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM file_profiles WHERE id = ?", (fid,))
            return cursor.rowcount > 0
