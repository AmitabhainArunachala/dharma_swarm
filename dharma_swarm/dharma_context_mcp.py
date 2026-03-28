"""dharma_swarm Context Engine MCP Server.

Exposes dharma_swarm's context, memory, and graph infrastructure to
Claude Code (or any MCP client) via stdio transport.

Tools:
  - codebase-search:   Hybrid FTS5 + neural vector search across indexed code
  - ecosystem-search:  Find relevant files across 42 ecosystem paths
  - graph-query:       Query GraphNexus (6 knowledge graphs unified)
  - git-history:       Search git commit history for recent changes
  - index-workspace:   Index or re-index a workspace directory
  - dependency-map:    Show import/dependency graph for a Python module

Run:
  python3 -m dharma_swarm.dharma_context_mcp
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".dharma"
CODEBASE_INDEX_DB = STATE_DIR / "codebase_index.db"
DHARMA_SWARM_ROOT = Path.home() / "dharma_swarm"

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sh", ".bash", ".zsh", ".sql", ".html", ".css",
    ".tex", ".go", ".rs", ".java", ".kt", ".swift", ".rb", ".lua",
}

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", "dist", "build", "egg-info", ".eggs",
    ".worktrees", "site-packages", ".next", ".nuxt",
}

# ---------------------------------------------------------------------------
# Tree-sitter multi-language symbol extraction
# ---------------------------------------------------------------------------

_TS_PARSERS: dict[str, Any] = {}


def _get_ts_parser(language: str):
    """Get or create a tree-sitter parser for the given language."""
    if language in _TS_PARSERS:
        return _TS_PARSERS[language]
    try:
        import tree_sitter
        lang_mod = None
        if language == "python":
            import tree_sitter_python as lang_mod
        elif language == "javascript":
            import tree_sitter_javascript as lang_mod
        elif language == "typescript":
            import tree_sitter_typescript as ts_mod
            lang_mod = ts_mod  # has .language_typescript()
        elif language == "go":
            import tree_sitter_go as lang_mod
        elif language == "rust":
            import tree_sitter_rust as lang_mod
        elif language == "java":
            import tree_sitter_java as lang_mod

        if lang_mod is None:
            _TS_PARSERS[language] = None
            return None

        parser = tree_sitter.Parser()
        if language == "typescript":
            parser.language = tree_sitter.Language(lang_mod.language_typescript())
        else:
            parser.language = tree_sitter.Language(lang_mod.language())
        _TS_PARSERS[language] = parser
        return parser
    except Exception as exc:
        logger.debug("tree-sitter parser for %s unavailable: %s", language, exc)
        _TS_PARSERS[language] = None
        return None


def _extract_ts_symbols(content: str, language: str) -> list[str]:
    """Extract symbols using tree-sitter for any supported language."""
    parser = _get_ts_parser(language)
    if parser is None:
        return []

    try:
        tree = parser.parse(content.encode("utf-8"))
        symbols = []
        _walk_ts_node(tree.root_node, symbols, language, depth=0)
        return symbols
    except Exception:
        return []


def _walk_ts_node(node, symbols: list[str], lang: str, depth: int) -> None:
    """Recursively walk tree-sitter AST extracting meaningful symbols."""
    if depth > 3:
        return

    ntype = node.type

    # JavaScript / TypeScript
    if lang in ("javascript", "typescript"):
        if ntype == "function_declaration":
            name = _ts_child_text(node, "name") or _ts_child_text(node, "identifier")
            if name:
                symbols.append(f"function {name}")
        elif ntype == "class_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"class {name}")
        elif ntype in ("export_statement", "lexical_declaration"):
            text = node.text.decode("utf-8", errors="replace")[:120]
            if "export" in text or "const " in text or "let " in text:
                # Extract variable name
                m = re.match(r'(?:export\s+)?(?:const|let|var)\s+(\w+)', text)
                if m:
                    symbols.append(f"const {m.group(1)}")
        elif ntype == "import_statement":
            text = node.text.decode("utf-8", errors="replace")[:120]
            symbols.append(text.strip())

    # Go
    elif lang == "go":
        if ntype == "function_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"func {name}")
        elif ntype == "method_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"method {name}")
        elif ntype == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    tname = _ts_child_text(child, "name")
                    if tname:
                        symbols.append(f"type {tname}")

    # Rust
    elif lang == "rust":
        if ntype == "function_item":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"fn {name}")
        elif ntype in ("struct_item", "enum_item", "trait_item"):
            name = _ts_child_text(node, "name")
            if name:
                kind = ntype.replace("_item", "")
                symbols.append(f"{kind} {name}")
        elif ntype == "impl_item":
            text = node.text.decode("utf-8", errors="replace")[:80]
            symbols.append(text.split("{")[0].strip())

    # Java
    elif lang == "java":
        if ntype == "method_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"method {name}")
        elif ntype == "class_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"class {name}")
        elif ntype == "interface_declaration":
            name = _ts_child_text(node, "name")
            if name:
                symbols.append(f"interface {name}")

    for child in node.children:
        _walk_ts_node(child, symbols, lang, depth + 1)


def _ts_child_text(node, field: str) -> str | None:
    """Get text of a named child field."""
    child = node.child_by_field_name(field)
    if child:
        return child.text.decode("utf-8", errors="replace")
    return None


# ---------------------------------------------------------------------------
# Python AST extraction (stdlib — richer than tree-sitter for Python)
# ---------------------------------------------------------------------------

def _extract_python_symbols(content: str) -> list[str]:
    """Extract structured symbols from Python source using stdlib ast."""
    import ast as ast_mod
    symbols = []
    try:
        tree = ast_mod.parse(content)
        for node in ast_mod.iter_child_nodes(tree):
            if isinstance(node, (ast_mod.FunctionDef, ast_mod.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                prefix = "async def" if isinstance(node, ast_mod.AsyncFunctionDef) else "def"
                doc = ast_mod.get_docstring(node)
                symbols.append(f"{prefix} {node.name}({', '.join(args)})")
                if doc:
                    symbols.append(f"  docstring: {doc[:120]}")
            elif isinstance(node, ast_mod.ClassDef):
                bases = []
                for b in node.bases:
                    if isinstance(b, ast_mod.Name):
                        bases.append(b.id)
                    elif isinstance(b, ast_mod.Attribute):
                        bases.append(f"{getattr(b.value, 'id', '?')}.{b.attr}")
                base_str = f"({', '.join(bases)})" if bases else ""
                symbols.append(f"class {node.name}{base_str}")
                doc = ast_mod.get_docstring(node)
                if doc:
                    symbols.append(f"  docstring: {doc[:120]}")
                for item in node.body:
                    if isinstance(item, (ast_mod.FunctionDef, ast_mod.AsyncFunctionDef)):
                        method_args = [a.arg for a in item.args.args if a.arg != "self"]
                        pfx = "async def" if isinstance(item, ast_mod.AsyncFunctionDef) else "def"
                        symbols.append(f"  {pfx} {node.name}.{item.name}({', '.join(method_args)})")
            elif isinstance(node, ast_mod.Import):
                for alias in node.names:
                    symbols.append(f"import {alias.name}")
            elif isinstance(node, ast_mod.ImportFrom):
                module = node.module or ""
                names = [a.name for a in (node.names or [])]
                symbols.append(f"from {module} import {', '.join(names[:5])}")
            elif isinstance(node, ast_mod.Assign):
                for target in node.targets:
                    if isinstance(target, ast_mod.Name) and target.id.isupper():
                        symbols.append(f"const {target.id}")
    except SyntaxError:
        pass
    return symbols


def _extract_python_imports(content: str) -> list[tuple[str, str]]:
    """Extract (module, name) import pairs for dependency graph."""
    import ast as ast_mod
    imports = []
    try:
        tree = ast_mod.parse(content)
        for node in ast_mod.walk(tree):
            if isinstance(node, ast_mod.Import):
                for alias in node.names:
                    imports.append((alias.name, alias.asname or alias.name))
            elif isinstance(node, ast_mod.ImportFrom):
                module = node.module or ""
                for alias in (node.names or []):
                    imports.append((f"{module}.{alias.name}", alias.asname or alias.name))
    except SyntaxError:
        pass
    return imports


# ---------------------------------------------------------------------------
# Code chunking
# ---------------------------------------------------------------------------

def _lang_from_ext(ext: str) -> str:
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".md": "markdown",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".sh": "shell", ".bash": "shell",
        ".sql": "sql", ".html": "html", ".css": "css",
        ".tex": "latex", ".go": "go", ".rs": "rust",
        ".java": "java", ".kt": "kotlin", ".swift": "swift",
        ".rb": "ruby", ".lua": "lua",
    }.get(ext, "text")


def _chunk_code(content: str, max_chars: int = 4000) -> list[str]:
    """Split code into chunks, preferring function/class boundaries."""
    if len(content) <= max_chars:
        return [content]

    lines = content.split("\n")
    chunks = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        elif current_len > max_chars * 0.8:
            stripped = line.strip()
            if (stripped.startswith("def ") or stripped.startswith("class ") or
                    stripped.startswith("async def ") or stripped.startswith("# ---") or
                    stripped.startswith("func ") or stripped.startswith("fn ") or
                    stripped.startswith("export ") or stripped.startswith("type ")):
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    current_len = 0

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def _extract_symbols(content: str, language: str) -> list[str]:
    """Extract symbols using the best available method for the language."""
    if language == "python":
        return _extract_python_symbols(content)
    # Try tree-sitter for other languages
    ts_syms = _extract_ts_symbols(content, language)
    if ts_syms:
        return ts_syms
    return []


# ---------------------------------------------------------------------------
# Git history indexing
# ---------------------------------------------------------------------------

def _index_git_history(repo_path: Path, max_commits: int = 200) -> list[dict]:
    """Extract git log entries for indexing."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_commits}",
             "--pretty=format:%H|%ai|%an|%s", "--no-merges"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, date, author, subject = parts
            commits.append({
                "sha": sha[:12],
                "date": date,
                "author": author,
                "subject": subject,
            })
        return commits
    except Exception:
        return []


def _get_commit_diff_summary(repo_path: Path, sha: str) -> str:
    """Get a compact diff summary for a commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", f"{sha}~1..{sha}"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()[:500] if result.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

_watcher_thread: threading.Thread | None = None
_watcher_stop = threading.Event()


def _start_file_watcher(idx: CodebaseIndex, watch_dirs: list[Path]) -> None:
    """Start a background file watcher for real-time index updates."""
    global _watcher_thread
    if _watcher_thread is not None:
        return

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class IndexHandler(FileSystemEventHandler):
            def __init__(self, index: CodebaseIndex):
                self._idx = index
                self._pending: set[str] = set()
                self._last_flush = time.monotonic()

            def _should_index(self, path: str) -> bool:
                p = Path(path)
                if p.suffix not in CODE_EXTENSIONS:
                    return False
                if any(part in SKIP_DIRS for part in p.parts):
                    return False
                return True

            def on_modified(self, event):
                if not event.is_directory and self._should_index(event.src_path):
                    self._pending.add(event.src_path)
                    self._maybe_flush()

            def on_created(self, event):
                if not event.is_directory and self._should_index(event.src_path):
                    self._pending.add(event.src_path)
                    self._maybe_flush()

            def _maybe_flush(self):
                """Batch index updates every 5 seconds."""
                now = time.monotonic()
                if now - self._last_flush < 5.0:
                    return
                self._flush()

            def _flush(self):
                if not self._pending:
                    return
                conn = self._idx._get_conn()
                for fpath in list(self._pending):
                    p = Path(fpath)
                    if not p.exists():
                        conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (fpath,))
                        continue
                    try:
                        content = p.read_text(errors="replace")
                        if len(content) > 500_000:
                            continue
                        lang = _lang_from_ext(p.suffix)
                        mtime = p.stat().st_mtime
                        conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (fpath,))
                        chunks = _chunk_code(content)
                        for i, chunk in enumerate(chunks):
                            chunk_symbols = _extract_symbols(chunk if i > 0 else content, lang)
                            conn.execute(
                                """INSERT OR REPLACE INTO code_chunks
                                   (id, file_path, chunk_index, content, language, symbols, mtime)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (f"{p}:{i}", fpath, i, chunk, lang,
                                 " | ".join(chunk_symbols), mtime),
                            )
                    except Exception:
                        pass
                conn.commit()
                self._pending.clear()
                self._last_flush = time.monotonic()

        observer = Observer()
        handler = IndexHandler(idx)
        for d in watch_dirs:
            if d.is_dir():
                observer.schedule(handler, str(d), recursive=True)

        def run():
            observer.start()
            while not _watcher_stop.is_set():
                _watcher_stop.wait(timeout=5.0)
                handler._flush()
            observer.stop()
            observer.join()

        _watcher_thread = threading.Thread(target=run, daemon=True, name="file-watcher")
        _watcher_thread.start()
        logger.info("File watcher started for %d directories", len(watch_dirs))

    except ImportError:
        logger.debug("watchdog not installed — file watching disabled")
    except Exception as exc:
        logger.warning("File watcher failed to start: %s", exc)


# ---------------------------------------------------------------------------
# Codebase Index
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_chunks (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    symbols TEXT NOT NULL DEFAULT '',
    mtime REAL NOT NULL DEFAULT 0,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_path, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_code_path ON code_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_code_lang ON code_chunks(language);

CREATE VIRTUAL TABLE IF NOT EXISTS code_fts USING fts5(
    content, file_path, symbols, language,
    content='code_chunks',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS code_ai AFTER INSERT ON code_chunks BEGIN
    INSERT INTO code_fts(rowid, content, file_path, symbols, language)
    VALUES (new.rowid, new.content, new.file_path, new.symbols, new.language);
END;
CREATE TRIGGER IF NOT EXISTS code_ad AFTER DELETE ON code_chunks BEGIN
    INSERT INTO code_fts(code_fts, rowid, content, file_path, symbols, language)
    VALUES ('delete', old.rowid, old.content, old.file_path, old.symbols, old.language);
END;
CREATE TRIGGER IF NOT EXISTS code_au AFTER UPDATE ON code_chunks BEGIN
    INSERT INTO code_fts(code_fts, rowid, content, file_path, symbols, language)
    VALUES ('delete', old.rowid, old.content, old.file_path, old.symbols, old.language);
    INSERT INTO code_fts(rowid, content, file_path, symbols, language)
    VALUES (new.rowid, new.content, new.file_path, new.symbols, new.language);
END;

-- Git history table
CREATE TABLE IF NOT EXISTS git_commits (
    sha TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    author TEXT NOT NULL,
    subject TEXT NOT NULL,
    diff_summary TEXT DEFAULT '',
    repo_path TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS git_fts USING fts5(
    subject, author, diff_summary,
    content='git_commits',
    content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS git_ai AFTER INSERT ON git_commits BEGIN
    INSERT INTO git_fts(rowid, subject, author, diff_summary)
    VALUES (new.rowid, new.subject, new.author, new.diff_summary);
END;
CREATE TRIGGER IF NOT EXISTS git_ad AFTER DELETE ON git_commits BEGIN
    INSERT INTO git_fts(git_fts, rowid, subject, author, diff_summary)
    VALUES ('delete', old.rowid, old.subject, old.author, old.diff_summary);
END;
"""


class CodebaseIndex:
    """SQLite FTS5-based codebase index with hybrid neural search,
    tree-sitter multi-language AST, git history, and file watching."""

    def __init__(self, db_path: Path | None = None, use_neural: bool = True):
        self._db_path = db_path or CODEBASE_INDEX_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._embedder: Any = None
        self._use_neural = use_neural

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        return self._conn

    def index_directory(
        self, root: Path,
        extensions: set[str] | None = None,
        skip_dirs: set[str] | None = None,
    ) -> dict[str, int]:
        """Walk a directory and index all matching files."""
        exts = extensions or CODE_EXTENSIONS
        skip = skip_dirs or SKIP_DIRS
        conn = self._get_conn()
        stats = {"files_indexed": 0, "chunks_created": 0, "files_skipped": 0}

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in exts:
                continue
            if any(part in skip for part in path.parts):
                continue

            mtime = path.stat().st_mtime
            existing = conn.execute(
                "SELECT mtime FROM code_chunks WHERE file_path = ? LIMIT 1",
                (str(path),),
            ).fetchone()
            if existing and existing["mtime"] >= mtime:
                stats["files_skipped"] += 1
                continue

            try:
                content = path.read_text(errors="replace")
            except (PermissionError, OSError):
                continue
            if len(content) > 500_000:
                continue

            lang = _lang_from_ext(path.suffix)
            file_symbols = _extract_symbols(content, lang)

            conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (str(path),))

            chunks = _chunk_code(content)
            for i, chunk in enumerate(chunks):
                chunk_symbols = _extract_symbols(chunk, lang) if i > 0 else file_symbols
                conn.execute(
                    """INSERT OR REPLACE INTO code_chunks
                       (id, file_path, chunk_index, content, language, symbols, mtime)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"{path}:{i}", str(path), i, chunk, lang,
                     " | ".join(chunk_symbols), mtime),
                )
                stats["chunks_created"] += 1
            stats["files_indexed"] += 1

        conn.commit()
        return stats

    def index_git_history(self, repo_path: Path, max_commits: int = 200) -> int:
        """Index git commit history for search."""
        commits = _index_git_history(repo_path, max_commits)
        if not commits:
            return 0

        conn = self._get_conn()
        count = 0
        for c in commits:
            existing = conn.execute(
                "SELECT sha FROM git_commits WHERE sha = ?", (c["sha"],)
            ).fetchone()
            if existing:
                continue
            diff = _get_commit_diff_summary(repo_path, c["sha"])
            conn.execute(
                """INSERT OR IGNORE INTO git_commits
                   (sha, date, author, subject, diff_summary, repo_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (c["sha"], c["date"], c["author"], c["subject"],
                 diff, str(repo_path)),
            )
            count += 1
        conn.commit()
        return count

    def search_git(self, query: str, max_results: int = 15) -> list[dict]:
        """Search git commit history."""
        conn = self._get_conn()
        safe_query = query.replace('"', '""')
        terms = safe_query.split()
        fts_query = " OR ".join(f'"{t}"' for t in terms if t.strip())
        if not fts_query:
            return []

        try:
            rows = conn.execute(
                """SELECT g.sha, g.date, g.author, g.subject, g.diff_summary, rank
                   FROM git_fts f
                   JOIN git_commits g ON g.rowid = f.rowid
                   WHERE git_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (fts_query, max_results),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                """SELECT sha, date, author, subject, diff_summary, 0 as rank
                   FROM git_commits WHERE subject LIKE ? LIMIT ?""",
                (f"%{query}%", max_results),
            ).fetchall()

        return [dict(row) for row in rows]

    def search(self, query: str, max_results: int = 10, language: str = "") -> list[dict]:
        """FTS5 keyword search across indexed code."""
        conn = self._get_conn()
        safe_query = query.replace('"', '""')
        terms = safe_query.split()
        fts_query = " OR ".join(f'"{t}"' for t in terms if t.strip())
        if not fts_query:
            return []

        lang_filter = ""
        params: list[Any] = []
        if language:
            lang_filter = "AND c.language = ?"
            params.append(language)

        try:
            rows = conn.execute(
                f"""SELECT c.file_path, c.chunk_index, c.content, c.language,
                           c.symbols, rank
                    FROM code_fts f
                    JOIN code_chunks c ON c.rowid = f.rowid
                    WHERE code_fts MATCH ?
                    {lang_filter}
                    ORDER BY rank LIMIT ?""",
                [fts_query] + params + [max_results],
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                f"""SELECT file_path, chunk_index, content, language, symbols, 0 as rank
                    FROM code_chunks WHERE content LIKE ?
                    {lang_filter} LIMIT ?""",
                [f"%{query}%"] + ([language] if language else []) + [max_results],
            ).fetchall()

        return [{
            "file_path": row["file_path"],
            "chunk_index": row["chunk_index"],
            "content": row["content"][:3000],
            "language": row["language"],
            "symbols": row["symbols"],
            "rank": row["rank"] if "rank" in row.keys() else 0,
        } for row in rows]

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        if not self._use_neural:
            return None
        try:
            from dharma_swarm.vector_store import SentenceTransformerEmbedder
            self._embedder = SentenceTransformerEmbedder()
            return self._embedder
        except Exception as exc:
            logger.warning("Neural embedder unavailable: %s", exc)
            self._use_neural = False
            return None

    def search_hybrid(
        self, query: str, max_results: int = 10, language: str = "",
        fts_weight: float = 0.4, vec_weight: float = 0.6,
        use_reranker: bool = False,
    ) -> list[dict]:
        """Hybrid FTS5 + neural vector similarity fusion search.

        Optionally applies LLM reranking for highest quality results.
        """
        fts_results = self.search(query, max_results=max_results * 3, language=language)

        embedder = self._get_embedder()
        if embedder is None or not fts_results:
            if use_reranker and fts_results:
                return _llm_rerank(query, fts_results, top_k=max_results)
            return fts_results[:max_results]

        try:
            texts = [query] + [r["content"][:1500] for r in fts_results]
            vecs = embedder.embed(texts)
            q_vec = vecs[0]
            r_vecs = vecs[1:]
        except Exception:
            return fts_results[:max_results]

        fts_ranks = [abs(r.get("rank", 0)) for r in fts_results]
        max_fts = max(fts_ranks) if fts_ranks else 1.0
        if max_fts == 0:
            max_fts = 1.0

        for i, result in enumerate(fts_results):
            fts_score = 1.0 - (fts_ranks[i] / (max_fts + 1e-9))
            vec_score = max(0.0, sum(a * b for a, b in zip(q_vec, r_vecs[i]))) if i < len(r_vecs) else 0.0
            fused = fts_weight * fts_score + vec_weight * vec_score
            result["fused_score"] = round(fused, 4)
            result["vec_score"] = round(vec_score, 4)
            result["fts_score"] = round(fts_score, 4)

        fts_results.sort(key=lambda r: r.get("fused_score", 0), reverse=True)

        # Optional LLM reranking on the top candidates
        if use_reranker:
            return _llm_rerank(query, fts_results, top_k=max_results)

        return fts_results[:max_results]

    def get_dependency_map(self, module_path: str) -> dict[str, Any]:
        """Build import dependency map for a Python module."""
        p = Path(module_path).expanduser()
        if not p.exists():
            return {"error": f"File not found: {module_path}"}

        content = p.read_text(errors="replace")
        imports = _extract_python_imports(content)

        # Resolve which imports are from dharma_swarm
        internal = []
        external = []
        for mod, name in imports:
            if mod.startswith("dharma_swarm"):
                internal.append(mod)
            else:
                external.append(mod)

        # Find reverse dependencies (who imports this module?)
        module_name = p.stem
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT DISTINCT file_path FROM code_chunks
               WHERE symbols LIKE ? AND file_path != ?""",
            (f"%import%{module_name}%", str(p)),
        ).fetchall()
        imported_by = [r["file_path"].replace(str(Path.home()), "~") for r in rows]

        return {
            "module": str(p).replace(str(Path.home()), "~"),
            "imports_internal": sorted(set(internal)),
            "imports_external": sorted(set(external)),
            "imported_by": imported_by[:20],
        }

    def stats(self) -> dict[str, int]:
        conn = self._get_conn()
        chunks = conn.execute("SELECT COUNT(*) FROM code_chunks").fetchone()[0]
        files = conn.execute("SELECT COUNT(DISTINCT file_path) FROM code_chunks").fetchone()[0]
        try:
            commits = conn.execute("SELECT COUNT(*) FROM git_commits").fetchone()[0]
        except sqlite3.OperationalError:
            commits = 0
        return {"total_chunks": chunks, "total_files": files, "git_commits": commits}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# LLM Reranker (uses free models via OpenRouter)
# ---------------------------------------------------------------------------

def _llm_rerank(query: str, results: list[dict], top_k: int = 10) -> list[dict]:
    """Rerank search results using a cheap LLM for relevance scoring.

    Uses OpenRouter free tier (llama-3.3-70b or similar).
    Falls back to original order if LLM is unavailable.
    """
    if len(results) <= top_k:
        return results

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return results[:top_k]

    # Build compact representation of results for the LLM
    items = []
    for i, r in enumerate(results[:20]):  # Max 20 items to rerank
        fp = Path(r["file_path"]).name
        snippet = r["content"][:200].replace("\n", " ").strip()
        items.append(f"[{i}] {fp}: {snippet}")

    prompt = (
        f"Given the search query: \"{query}\"\n\n"
        f"Rank these code snippets by relevance. Return ONLY a JSON array of "
        f"indices in order from most to least relevant, e.g. [3, 0, 7, 1].\n\n"
        + "\n".join(items)
    )

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({
                "model": "meta-llama/llama-3.3-70b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.0,
            }).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            text = body["choices"][0]["message"]["content"]

        # Parse the JSON array of indices
        match = re.search(r'\[[\d\s,]+\]', text)
        if not match:
            return results[:top_k]
        indices = json.loads(match.group())

        # Validate and deduplicate indices
        seen = set()
        reranked = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(results) and idx not in seen:
                seen.add(idx)
                r = results[idx]
                r["llm_reranked"] = True
                reranked.append(r)
            if len(reranked) >= top_k:
                break

        # Append any remaining results not in the reranked list
        for i, r in enumerate(results):
            if i not in seen and len(reranked) < top_k:
                reranked.append(r)

        return reranked

    except Exception as exc:
        logger.debug("LLM reranking failed (non-fatal): %s", exc)
        return results[:top_k]


# ---------------------------------------------------------------------------
# Lazy subsystem init
# ---------------------------------------------------------------------------

_codebase_index: CodebaseIndex | None = None
_graph_nexus: Any | None = None
_context_search: Any | None = None


def _get_codebase_index() -> CodebaseIndex:
    global _codebase_index
    if _codebase_index is None:
        _codebase_index = CodebaseIndex()
    return _codebase_index


def _get_context_search():
    global _context_search
    if _context_search is None:
        try:
            from dharma_swarm.context_search import ContextSearchEngine
            from dharma_swarm.ecosystem_map import ECOSYSTEM
            paths = {}
            for category, info in ECOSYSTEM.items():
                for path_tuple in info.get("paths", []):
                    path_str = path_tuple[0] if isinstance(path_tuple, tuple) else path_tuple
                    paths[path_str] = {"category": category}
            _context_search = ContextSearchEngine(ecosystem_paths=paths)
            _context_search.build_index()
        except Exception as exc:
            logger.warning("ContextSearchEngine init failed: %s", exc)
    return _context_search


async def _get_graph_nexus():
    global _graph_nexus
    if _graph_nexus is None:
        try:
            from dharma_swarm.graph_nexus import GraphNexus
            _graph_nexus = GraphNexus()
            await _graph_nexus.init()
        except Exception as exc:
            logger.warning("GraphNexus init failed: %s", exc)
    return _graph_nexus


# ---------------------------------------------------------------------------
# MCP Server + Tools
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "dharma-context",
    instructions=(
        "dharma_swarm Context Engine — hybrid FTS5 + neural vector codebase search, "
        "git history, 6 knowledge graphs, 42 ecosystem paths, dependency mapping. "
        "Use codebase-search as the PRIMARY tool for finding code. "
        "Use git-history for recent changes. Use dependency-map for imports."
    ),
)


@mcp.tool(
    name="codebase-search",
    description=(
        "IMPORTANT: Primary tool for searching the codebase. Uses hybrid FTS5 + "
        "neural vector similarity for high-quality semantic search. "
        "Takes a natural language description of the code you're looking for. "
        "Returns relevant code snippets with file paths, symbols, and scores. "
        "Supports multi-language AST extraction (Python, TypeScript, Go, Rust, Java)."
    ),
)
def codebase_search(
    query: str, language: str = "", max_results: int = 10,
    rerank: bool = False,
) -> str:
    """Hybrid FTS5 + neural vector search across indexed code."""
    idx = _get_codebase_index()
    stats = idx.stats()
    if stats["total_files"] == 0:
        idx.index_directory(DHARMA_SWARM_ROOT / "dharma_swarm")
        mi_path = Path.home() / "mech-interp-latent-lab-phase1"
        if mi_path.is_dir():
            idx.index_directory(mi_path)

    results = idx.search_hybrid(
        query, max_results=max_results, language=language,
        use_reranker=rerank,
    )
    if not results:
        return f"No results found for: {query}"

    parts = [f"Found {len(results)} results for: {query}\n"]
    for r in results:
        fp = r["file_path"].replace(str(Path.home()), "~")
        symbols = r["symbols"]
        sym_line = f"\n  Symbols: {symbols}" if symbols else ""
        scores = ""
        if "fused_score" in r:
            scores = f" | score: {r['fused_score']} (vec: {r['vec_score']}, fts: {r['fts_score']})"
        parts.append(
            f"--- {fp} (chunk {r['chunk_index']}, {r['language']}{scores}){sym_line}\n"
            f"{r['content'][:2000]}\n"
        )
    return "\n".join(parts)


@mcp.tool(
    name="git-history",
    description=(
        "Search git commit history for recent changes. Returns matching commits "
        "with dates, authors, subjects, and file change summaries. Use when you "
        "need to understand what changed recently, who changed it, or find the "
        "commit that introduced a feature or bug."
    ),
)
def git_history(query: str, max_results: int = 15) -> str:
    """Search indexed git commit history."""
    idx = _get_codebase_index()
    # Index git history if not yet done
    stats = idx.stats()
    if stats.get("git_commits", 0) == 0:
        count = idx.index_git_history(DHARMA_SWARM_ROOT)
        if count == 0:
            return "No git history available."

    results = idx.search_git(query, max_results=max_results)
    if not results:
        return f"No git commits found matching: {query}"

    parts = [f"Found {len(results)} commits matching: {query}\n"]
    for c in results:
        diff = c.get("diff_summary", "")
        diff_line = f"\n  Files: {diff[:200]}" if diff else ""
        parts.append(
            f"  {c['sha']} | {c['date'][:10]} | {c['author']}\n"
            f"  {c['subject']}{diff_line}\n"
        )
    return "\n".join(parts)


@mcp.tool(
    name="dependency-map",
    description=(
        "Show the import dependency graph for a Python module. Returns internal "
        "imports (within dharma_swarm), external imports, and reverse dependencies "
        "(which modules import this one). Use to understand module relationships."
    ),
)
def dependency_map(module_path: str) -> str:
    """Show import dependencies for a Python module."""
    idx = _get_codebase_index()
    result = idx.get_dependency_map(module_path)
    if "error" in result:
        return result["error"]

    parts = [f"Dependency map for {result['module']}:\n"]
    if result["imports_internal"]:
        parts.append("Internal imports (dharma_swarm):")
        for m in result["imports_internal"]:
            parts.append(f"  -> {m}")
    if result["imports_external"]:
        parts.append("\nExternal imports:")
        for m in result["imports_external"]:
            parts.append(f"  -> {m}")
    if result["imported_by"]:
        parts.append(f"\nImported by ({len(result['imported_by'])} modules):")
        for m in result["imported_by"]:
            parts.append(f"  <- {m}")
    return "\n".join(parts)


@mcp.tool(
    name="ecosystem-search",
    description=(
        "Search across 42 ecosystem paths covering research, content, ops, "
        "infrastructure, and all active repositories."
    ),
)
def ecosystem_search(query: str, max_results: int = 5) -> str:
    """Search the ecosystem map for relevant paths."""
    engine = _get_context_search()
    if engine is None:
        return "Ecosystem search unavailable."

    results = engine.search(query, max_results=max_results)
    if not results:
        return f"No ecosystem paths found for: {query}"

    parts = [f"Found {len(results)} ecosystem paths for: {query}\n"]
    for r in results:
        path = r.path.replace(str(Path.home()), "~")
        parts.append(
            f"  {path}\n"
            f"    Category: {r.category} | Relevance: {r.relevance:.2f} | "
            f"Size: {r.size_bytes:,}B | Age: {r.age_hours:.0f}h\n"
            f"    {r.snippet[:200]}\n"
        )
    return "\n".join(parts)


@mcp.tool(
    name="graph-query",
    description=(
        "Query 6 interconnected knowledge graphs: Semantic, Catalytic, "
        "Temporal, Lineage, Telos, and Bridge."
    ),
)
async def graph_query(term: str) -> str:
    """Query the GraphNexus for cross-graph knowledge."""
    nexus = await _get_graph_nexus()
    if nexus is None:
        return "GraphNexus unavailable."

    result = await nexus.query_about(term)
    parts = [
        f"GraphNexus query: {term}",
        f"Graphs queried: {', '.join(result.graphs_queried)}",
        f"Total hits: {result.total_hits}",
    ]
    if result.errors:
        parts.append(f"Errors: {'; '.join(result.errors)}")

    for category, hits in [
        ("Semantic", result.semantic_hits),
        ("Temporal", result.temporal_hits),
        ("Telos", result.telos_hits),
        ("Lineage", result.lineage_hits),
        ("Catalytic", result.catalytic_hits),
    ]:
        if hits:
            parts.append(f"\n{category} ({len(hits)} hits):")
            for h in hits[:5]:
                parts.append(f"  [{h.node_type}] {h.name} (relevance: {h.relevance:.2f})")
                if h.metadata:
                    parts.append(f"    {json.dumps(h.metadata, default=str)[:200]}")
    return "\n".join(parts)


@mcp.tool(
    name="index-workspace",
    description="Index or re-index a workspace directory. Also indexes git history.",
)
def index_workspace(directory: str = "") -> str:
    """Index a directory for codebase search."""
    root = Path(directory).expanduser() if directory else DHARMA_SWARM_ROOT
    if not root.is_dir():
        return f"Not a directory: {root}"

    idx = _get_codebase_index()
    t0 = time.monotonic()
    stats = idx.index_directory(root)
    git_count = idx.index_git_history(root)
    elapsed = time.monotonic() - t0
    total = idx.stats()

    # Start file watcher for this directory
    _start_file_watcher(idx, [root])

    return (
        f"Indexed {root}:\n"
        f"  Files indexed: {stats['files_indexed']}\n"
        f"  Chunks created: {stats['chunks_created']}\n"
        f"  Files skipped (unchanged): {stats['files_skipped']}\n"
        f"  Git commits indexed: {git_count}\n"
        f"  Time: {elapsed:.1f}s\n"
        f"  Total: {total['total_files']} files, {total['total_chunks']} chunks, "
        f"{total.get('git_commits', 0)} commits\n"
        f"  File watcher: active"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server via stdio."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
