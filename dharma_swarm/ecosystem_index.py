"""FTS5 full-text search index across the dharma ecosystem.

Indexes .py and .md files from 7 ecosystem domains into a single
SQLite FTS5 virtual table. Supports incremental builds (mtime-based),
domain-filtered search, related-file discovery, and full rebuilds.

DB location: ~/.dharma/db/ecosystem_index.db

Usage:
    from dharma_swarm.ecosystem_index import get_index

    idx = get_index()
    idx.build()                          # incremental index
    idx.search("R_V contraction")        # full-text search
    idx.related("~/dharma_swarm/rv.py")  # find related files
    idx.stats()                          # {domain: count}
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain definitions
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict[str, Any]] = {
    "dharma_swarm": {
        "base": Path.home() / "dharma_swarm" / "dharma_swarm",
        "extensions": {".py"},
    },
    "mech_interp": {
        "base": Path.home() / "mech-interp-latent-lab-phase1",
        "extensions": {".py", ".md"},
    },
    "psmv": {
        "base": Path.home() / "Persistent-Semantic-Memory-Vault",
        "extensions": {".md"},
    },
    "kailash": {
        "base": Path.home() / "Desktop" / "KAILASH ABODE OF SHIVA",
        "extensions": {".md"},
    },
    "agni": {
        "base": Path.home() / "agni-workspace",
        "extensions": {".md", ".py"},
    },
    "trishula": {
        "base": Path.home() / "trishula",
        "extensions": {".md"},
    },
    "shared_notes": {
        "base": Path.home() / ".dharma" / "shared",
        "extensions": {".md"},
    },
}

DEFAULT_DB_PATH = Path.home() / ".dharma" / "db" / "ecosystem_index.db"

_MAX_CONTENT_BYTES = 50 * 1024  # 50 KB per file

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS docs
    USING fts5(path, domain, title, content, tokenize='porter unicode61');
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_meta (
    path    TEXT PRIMARY KEY,
    domain  TEXT,
    mtime   REAL,
    size    INTEGER,
    indexed_at TEXT
);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_text_safe(path: Path, max_bytes: int = _MAX_CONTENT_BYTES) -> str | None:
    """Read a file as UTF-8 text, returning None on failure.

    Silently skips binary files and files that exceed max_bytes
    (truncated to max_bytes before decoding).
    """
    try:
        raw = path.read_bytes()[:max_bytes]
        return raw.decode("utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def _walk_domain(domain_name: str, domain_cfg: dict[str, Any]) -> list[Path]:
    """Recursively collect files matching the domain's extensions."""
    base: Path = domain_cfg["base"]
    extensions: set[str] = domain_cfg["extensions"]
    if not base.exists() or not base.is_dir():
        return []
    results: list[Path] = []
    try:
        for child in base.rglob("*"):
            if child.is_file() and child.suffix in extensions:
                results.append(child)
    except (OSError, PermissionError) as exc:
        logger.warning("Error walking %s (%s): %s", domain_name, base, exc)
    return results


def _extract_top_terms(text: str, n: int = 12) -> list[str]:
    """Extract the most frequent meaningful terms from text.

    Filters out very short tokens and common English stop words.
    """
    stop = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "were", "been", "have", "has", "had", "not", "but", "its", "will",
        "can", "all", "they", "their", "which", "when", "what", "there",
        "than", "into", "also", "just", "about", "each", "other", "more",
        "some", "def", "self", "none", "true", "false", "return", "import",
        "class", "elif", "else",
    }
    tokens = re.findall(r"[a-z_][a-z0-9_]{2,}", text.lower())
    freq: dict[str, int] = {}
    for tok in tokens:
        if tok not in stop:
            freq[tok] = freq.get(tok, 0) + 1
    ranked = sorted(freq, key=lambda t: freq[t], reverse=True)
    return ranked[:n]


# ---------------------------------------------------------------------------
# EcosystemIndex
# ---------------------------------------------------------------------------


class EcosystemIndex:
    """FTS5-backed full-text search index across the dharma ecosystem.

    Thread-safe: each public method opens its own connection.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # -- Schema setup -------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection with WAL mode for concurrent reads."""
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_META_SCHEMA)
            conn.executescript(_FTS_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # -- Build / Rebuild ----------------------------------------------------

    def build(self, domains: list[str] | None = None) -> dict[str, int]:
        """Walk all (or specified) domains, index text content.

        Returns {domain: files_indexed} count.
        Skips files whose mtime hasn't changed since last index.
        """
        target_domains = domains or list(DOMAINS.keys())
        counts: dict[str, int] = {}
        conn = self._connect()
        try:
            for domain_name in target_domains:
                if domain_name not in DOMAINS:
                    logger.warning("Unknown domain: %s", domain_name)
                    continue
                domain_cfg = DOMAINS[domain_name]
                files = _walk_domain(domain_name, domain_cfg)
                indexed = 0
                for fpath in files:
                    try:
                        stat = fpath.stat()
                    except OSError:
                        continue
                    mtime = stat.st_mtime
                    size = stat.st_size

                    # Check if already indexed with same mtime
                    row = conn.execute(
                        "SELECT mtime FROM doc_meta WHERE path = ?",
                        (str(fpath),),
                    ).fetchone()
                    if row and row["mtime"] == mtime:
                        continue

                    content = _read_text_safe(fpath)
                    if content is None:
                        continue

                    title = fpath.stem
                    now_iso = datetime.now(timezone.utc).isoformat()

                    # Upsert: remove old entry from FTS if exists, then insert
                    if row:
                        conn.execute(
                            "DELETE FROM docs WHERE path = ?", (str(fpath),)
                        )
                    conn.execute(
                        "INSERT INTO docs (path, domain, title, content) "
                        "VALUES (?, ?, ?, ?)",
                        (str(fpath), domain_name, title, content),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO doc_meta "
                        "(path, domain, mtime, size, indexed_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (str(fpath), domain_name, mtime, size, now_iso),
                    )
                    indexed += 1

                counts[domain_name] = indexed
            conn.commit()
            total = sum(counts.values())
            logger.info(
                "Indexed %d files across %d domains", total, len(counts)
            )
        finally:
            conn.close()
        return counts

    def rebuild(self) -> dict[str, int]:
        """Drop and rebuild the entire index."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM doc_meta")
            conn.commit()
        finally:
            conn.close()
        return self.build()

    # -- Search -------------------------------------------------------------

    def search(
        self,
        query: str,
        domains: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """FTS5 search across indexed documents.

        Args:
            query: Search query (FTS5 syntax supported).
            domains: Optional domain filter.
            limit: Maximum results.

        Returns:
            List of {path, domain, title, snippet, rank} dicts ordered
            by FTS5 rank (best first).
        """
        if not query.strip():
            return []

        conn = self._connect()
        try:
            if domains:
                placeholders = ", ".join("?" for _ in domains)
                sql = (
                    "SELECT path, domain, title, "
                    "snippet(docs, 3, '>>>', '<<<', '...', 48) AS snippet, "
                    "rank "
                    "FROM docs "
                    f"WHERE docs MATCH ? AND domain IN ({placeholders}) "
                    "ORDER BY rank "
                    "LIMIT ?"
                )
                params: tuple[Any, ...] = (query, *domains, limit)
            else:
                sql = (
                    "SELECT path, domain, title, "
                    "snippet(docs, 3, '>>>', '<<<', '...', 48) AS snippet, "
                    "rank "
                    "FROM docs WHERE docs MATCH ? "
                    "ORDER BY rank "
                    "LIMIT ?"
                )
                params = (query, limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "path": row["path"],
                    "domain": row["domain"],
                    "title": row["title"],
                    "snippet": row["snippet"],
                    "rank": row["rank"],
                }
                for row in rows
            ]
        except sqlite3.OperationalError as exc:
            # Bad FTS5 syntax falls back to a quoted phrase search
            logger.debug("FTS5 MATCH failed (%s), retrying as phrase", exc)
            safe_query = '"' + query.replace('"', '""') + '"'
            return self.search(safe_query, domains=domains, limit=limit)
        finally:
            conn.close()

    # -- Related files ------------------------------------------------------

    def related(self, file_path: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find files related to the given file by term overlap.

        Reads the file, extracts top terms, and searches the index.
        The source file itself is excluded from results.
        """
        target = Path(file_path).expanduser().resolve()
        content = _read_text_safe(target)
        if content is None:
            return []

        terms = _extract_top_terms(content)
        if not terms:
            return []

        query = " OR ".join(terms)
        results = self.search(query, limit=limit + 5)
        # Exclude the source file itself
        target_str = str(target)
        filtered = [r for r in results if r["path"] != target_str]
        return filtered[:limit]

    # -- Stats --------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Return {domain: doc_count} for all indexed domains."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT domain, COUNT(*) AS cnt FROM doc_meta GROUP BY domain"
            ).fetchall()
            return {row["domain"]: row["cnt"] for row in rows}
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_instance: EcosystemIndex | None = None


def get_index() -> EcosystemIndex:
    """Get or create the singleton ecosystem index."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EcosystemIndex()
    return _instance


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import time

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    idx = get_index()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "build":
        domains_arg = sys.argv[2:] or None
        t0 = time.monotonic()
        counts = idx.build(domains=domains_arg)
        elapsed = time.monotonic() - t0
        for domain, n in sorted(counts.items()):
            print(f"  {domain}: {n} files indexed")
        print(f"Done in {elapsed:.1f}s")

    elif cmd == "rebuild":
        t0 = time.monotonic()
        counts = idx.rebuild()
        elapsed = time.monotonic() - t0
        for domain, n in sorted(counts.items()):
            print(f"  {domain}: {n} files indexed")
        print(f"Rebuilt in {elapsed:.1f}s")

    elif cmd == "search":
        query = " ".join(sys.argv[2:])
        if not query:
            print("Usage: ecosystem_index.py search <query>")
            sys.exit(1)
        results = idx.search(query)
        for r in results:
            print(f"  [{r['domain']}] {r['title']}")
            print(f"    {r['path']}")
            print(f"    {r['snippet']}")
            print()

    elif cmd == "related":
        if len(sys.argv) < 3:
            print("Usage: ecosystem_index.py related <file_path>")
            sys.exit(1)
        results = idx.related(sys.argv[2])
        for r in results:
            print(f"  [{r['domain']}] {r['path']}")
            print(f"    {r['snippet']}")
            print()

    elif cmd == "stats":
        st = idx.stats()
        if not st:
            print("Index is empty. Run: ecosystem_index.py build")
        else:
            total = 0
            for domain, count in sorted(st.items()):
                print(f"  {domain}: {count} docs")
                total += count
            print(f"  TOTAL: {total} docs")

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: build [domains...], rebuild, search <query>, "
              "related <path>, stats")
        sys.exit(1)
