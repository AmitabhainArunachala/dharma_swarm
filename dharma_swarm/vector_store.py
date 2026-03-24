"""vector_store.py — Bi-temporal vector store for DHARMA SWARM.

Architecture:
    TFIDFEmbedder (scikit-learn) → sqlite-vec (vec0 virtual table) + FTS5
    Bi-temporal design: event_time (when it happened) + ingestion_time (when we learned it)
    Hybrid retrieval: vector similarity + full-text search fusion
    Confidence decay: age-based decay, soft-delete via valid_until

Design borrowed from:
    - OpenClaw's hybrid memory (vec + FTS5 combination)
    - Zep's bi-temporal model (event_time vs ingestion_time)
    - Mem0's layer design (access tracking, confidence decay)
    - CogniLayer (confidence decay formula)

Protocol: Embedder interface allows drop-in replacement with sentence-transformers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import sqlite3
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


# ---------------------------------------------------------------------------
# Embedder protocol — swappable TF-IDF now, sentence-transformers later
# ---------------------------------------------------------------------------

@runtime_checkable
class Embedder(Protocol):
    """Pluggable embedding interface.

    TF-IDF now; sentence-transformers as drop-in replacement later.
    Both must implement embed() and dim.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into fixed-dimension dense vectors."""
        ...

    @property
    def dim(self) -> int:
        """Embedding dimensionality."""
        ...


class TFIDFEmbedder:
    """Lightweight embedder using scikit-learn TF-IDF + TruncatedSVD.

    Produces fixed-dimension dense vectors from TF-IDF sparse matrices.
    Uses TruncatedSVD to reduce to `dim` dimensions (default 128).
    Fits incrementally — call fit_add() to expand vocabulary.

    Pickle-persisted alongside the SQLite database so vocab survives restarts.
    """

    def __init__(self, dim: int = 128, state_path: Path | None = None) -> None:
        self._dim = dim
        self._state_path = state_path  # Path for pickle persistence
        self._vectorizer: Any = None   # TfidfVectorizer
        self._svd: Any = None          # TruncatedSVD
        self._corpus: list[str] = []
        self._corpus_hash: str = ""
        self._fitted = False
        self._load_state()

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts. Fits on first call if not already fitted."""
        if not texts:
            return []
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
        except ImportError as exc:
            logger.debug("scikit-learn not available: %s", exc)
            # Fallback: zero vectors
            return [[0.0] * self._dim for _ in texts]

        try:
            # Bootstrap: if not fitted, use the texts themselves as initial corpus
            if not self._fitted or self._vectorizer is None:
                self._fit(texts)

            # Transform
            tfidf_matrix = self._vectorizer.transform(texts)
            if tfidf_matrix.shape[1] == 0:
                # Empty vocabulary — refit with current texts
                self._fit(texts)
                tfidf_matrix = self._vectorizer.transform(texts)

            # Project to lower dimension via SVD
            n_features = tfidf_matrix.shape[1]
            if n_features == 0:
                return [[0.0] * self._dim for _ in texts]

            # SVD may need refit if feature count changed
            actual_dim = min(self._dim, n_features)
            if self._svd is None or self._svd.n_components != actual_dim:
                self._fit(texts)
                tfidf_matrix = self._vectorizer.transform(texts)
                n_features = tfidf_matrix.shape[1]
                actual_dim = min(self._dim, n_features)

            dense = self._svd.transform(tfidf_matrix)

            # Pad or trim to exactly self._dim
            result: list[list[float]] = []
            for row in dense:
                vec = list(map(float, row))
                if len(vec) < self._dim:
                    vec = vec + [0.0] * (self._dim - len(vec))
                else:
                    vec = vec[:self._dim]
                # L2-normalize
                norm = (sum(v * v for v in vec) ** 0.5) or 1.0
                result.append([v / norm for v in vec])
            return result

        except Exception as exc:
            logger.debug("TFIDFEmbedder.embed failed: %s", exc)
            return [[0.0] * self._dim for _ in texts]

    def fit_add(self, texts: list[str]) -> None:
        """Expand vocabulary with new texts and refit."""
        if not texts:
            return
        self._corpus.extend(texts)
        # Keep corpus bounded
        if len(self._corpus) > 10000:
            self._corpus = self._corpus[-10000:]
        self._fit(self._corpus)

    def _fit(self, texts: list[str]) -> None:
        """Fit TF-IDF + SVD on provided texts."""
        if not texts:
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD

            corpus = list(set(texts))  # Deduplicate
            if not corpus:
                return

            vec = TfidfVectorizer(
                max_features=5000,
                sublinear_tf=True,
                min_df=1,
                token_pattern=r"(?u)\b\w+\b",
            )
            tfidf = vec.fit_transform(corpus)
            n_features = tfidf.shape[1]

            if n_features == 0:
                return

            actual_dim = min(self._dim, n_features, len(corpus) - 1)
            if actual_dim < 1:
                actual_dim = 1

            svd = TruncatedSVD(n_components=actual_dim, random_state=42)
            svd.fit(tfidf)

            self._vectorizer = vec
            self._svd = svd
            self._fitted = True

            # Update corpus and hash
            self._corpus = list(corpus)
            corpus_str = " ".join(sorted(corpus))
            self._corpus_hash = hashlib.md5(corpus_str.encode()).hexdigest()[:16]

            self._save_state()

        except Exception as exc:
            logger.debug("TFIDFEmbedder._fit failed: %s", exc)

    def _save_state(self) -> None:
        """Persist fitted state to disk."""
        if self._state_path is None:
            return
        try:
            state = {
                "vectorizer": self._vectorizer,
                "svd": self._svd,
                "corpus": self._corpus[-2000:],  # Save last 2000 for space
                "corpus_hash": self._corpus_hash,
                "dim": self._dim,
                "fitted": self._fitted,
            }
            with open(self._state_path, "wb") as fh:
                pickle.dump(state, fh, protocol=4)
        except Exception as exc:
            logger.debug("TFIDFEmbedder._save_state failed: %s", exc)

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if self._state_path is None or not Path(self._state_path).exists():
            return
        try:
            with open(self._state_path, "rb") as fh:
                state = pickle.load(fh)
            self._vectorizer = state.get("vectorizer")
            self._svd = state.get("svd")
            self._corpus = state.get("corpus", [])
            self._corpus_hash = state.get("corpus_hash", "")
            self._fitted = state.get("fitted", False)
        except Exception as exc:
            logger.debug("TFIDFEmbedder._load_state failed: %s", exc)


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """SQLite-vec backed vector store with bi-temporal, hybrid retrieval.

    Storage: SQLite database at state_dir/vectors.db
    Bi-temporal: event_time (when it happened) + ingestion_time (when we stored it)
    Hybrid retrieval: vector similarity (L2) + FTS5 full-text search fusion
    Confidence decay: age-based, capped at min_confidence
    Access tracking: access_count + last_accessed updated on every retrieval
    Edge invalidation: valid_until instead of hard delete

    Thread safety: creates a new connection per call (no shared connection).
    """

    _SCHEMA_VERSION = 1

    def __init__(
        self,
        state_dir: Path,
        embedder: Embedder | None = None,
        dim: int = 128,
    ) -> None:
        self._state_dir = state_dir
        self._db_path = state_dir / "vectors.db"
        self._embedder_path = state_dir / "tfidf_embedder.pkl"
        self._dim = dim

        # Embedder — TFIDFEmbedder by default, swappable
        if embedder is not None:
            self._embedder = embedder
        else:
            self._embedder = TFIDFEmbedder(dim=dim, state_path=self._embedder_path)

        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._init_db()
        except Exception as exc:
            logger.debug("VectorStore init failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # DB init
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh SQLite connection with sqlite-vec loaded."""
        try:
            import sqlite_vec
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            sqlite_vec.load(conn)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except ImportError:
            # sqlite_vec not installed — fall back to plain sqlite
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except Exception as exc:
            logger.debug("VectorStore _connect error: %s", exc)
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vec_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    layer TEXT DEFAULT 'working',
                    metadata_json TEXT DEFAULT '{}',
                    event_time TEXT,
                    ingestion_time TEXT NOT NULL,
                    valid_until TEXT,
                    confidence REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT
                )
            """)
            # FTS5 table for lexical search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_fts
                USING fts5(
                    content,
                    source,
                    content='vec_documents',
                    content_rowid='id'
                )
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS vec_fts_insert
                AFTER INSERT ON vec_documents BEGIN
                    INSERT INTO vec_fts(rowid, content, source)
                    VALUES (new.id, new.content, new.source);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS vec_fts_delete
                AFTER DELETE ON vec_documents BEGIN
                    INSERT INTO vec_fts(vec_fts, rowid, content, source)
                    VALUES ('delete', old.id, old.content, old.source);
                END
            """)
            # Try to create vec0 virtual table (requires sqlite-vec)
            try:
                conn.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings
                    USING vec0(
                        embedding float[{self._dim}]
                    )
                """)
            except Exception as vec_exc:
                logger.debug("vec0 table creation failed (sqlite-vec may not support this syntax): %s", vec_exc)
                # Fallback: store embeddings in a plain table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS vec_embeddings_fallback (
                        rowid INTEGER PRIMARY KEY,
                        embedding BLOB
                    )
                """)
            conn.commit()
        except Exception as exc:
            logger.debug("VectorStore _init_db error: %s", exc)
        finally:
            conn.close()

    def _has_vec0(self, conn: sqlite3.Connection) -> bool:
        """Check if vec_embeddings (vec0) virtual table is available."""
        try:
            conn.execute("SELECT * FROM vec_embeddings LIMIT 0")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def upsert(
        self,
        content: str,
        source: str = "",
        layer: str = "working",
        metadata: dict[str, Any] | None = None,
        event_time: datetime | None = None,
    ) -> int:
        """Insert (or update) a document. Returns the doc_id."""
        if not content or not content.strip():
            return -1
        conn = self._connect()
        try:
            now_iso = _utc_now_iso()
            event_iso = event_time.isoformat() if event_time else now_iso
            meta_json = json.dumps(metadata or {})

            # Fit embedder on new content (incremental vocabulary expansion)
            try:
                self._embedder.fit_add([content])
            except Exception:
                pass

            cursor = conn.execute("""
                INSERT INTO vec_documents
                    (content, source, layer, metadata_json, event_time, ingestion_time, confidence)
                VALUES (?, ?, ?, ?, ?, ?, 1.0)
            """, (content, source, layer, meta_json, event_iso, now_iso))
            doc_id = cursor.lastrowid

            # Store vector embedding
            try:
                vecs = self._embedder.embed([content])
                if vecs and vecs[0]:
                    vec = vecs[0]
                    packed = struct.pack(f"{self._dim}f", *vec)
                    if self._has_vec0(conn):
                        conn.execute("""
                            INSERT INTO vec_embeddings(rowid, embedding) VALUES (?, ?)
                        """, (doc_id, packed))
                    else:
                        conn.execute("""
                            INSERT INTO vec_embeddings_fallback(rowid, embedding) VALUES (?, ?)
                        """, (doc_id, packed))
            except Exception as vec_exc:
                logger.debug("VectorStore: embedding storage failed (non-fatal): %s", vec_exc)

            conn.commit()
            return doc_id or -1
        except Exception as exc:
            logger.debug("VectorStore.upsert failed: %s", exc)
            return -1
        finally:
            conn.close()

    def invalidate(self, doc_id: int, reason: str = "") -> bool:
        """Soft-delete: set valid_until = now. Does NOT remove the record."""
        conn = self._connect()
        try:
            now_iso = _utc_now_iso()
            meta_note = json.dumps({"invalidated_reason": reason, "invalidated_at": now_iso})
            conn.execute("""
                UPDATE vec_documents
                SET valid_until = ?,
                    metadata_json = json_patch(metadata_json, ?)
                WHERE id = ?
            """, (now_iso, meta_note, doc_id))
            conn.commit()
            return True
        except Exception as exc:
            logger.debug("VectorStore.invalidate failed: %s", exc)
            return False
        finally:
            conn.close()

    def decay_confidence(
        self,
        max_age_days: float = 30.0,
        decay_rate: float = 0.95,
    ) -> int:
        """Apply age-based confidence decay. Returns number of rows updated."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT id, confidence, ingestion_time
                FROM vec_documents
                WHERE valid_until IS NULL
            """).fetchall()

            now = _utc_now().timestamp()
            updated = 0
            for row in rows:
                try:
                    ingestion_ts = datetime.fromisoformat(row["ingestion_time"]).timestamp()
                    age_days = (now - ingestion_ts) / 86400.0
                    if age_days > 0:
                        # decay^(age_days): exponential decay
                        decayed = row["confidence"] * (decay_rate ** age_days)
                        decayed = max(0.0, min(1.0, decayed))
                        if abs(decayed - row["confidence"]) > 1e-6:
                            conn.execute(
                                "UPDATE vec_documents SET confidence = ? WHERE id = ?",
                                (decayed, row["id"]),
                            )
                            updated += 1
                except Exception:
                    pass

            conn.commit()
            return updated
        except Exception as exc:
            logger.debug("VectorStore.decay_confidence failed: %s", exc)
            return 0
        finally:
            conn.close()

    def gc(self, min_confidence: float = 0.01) -> int:
        """Remove documents below confidence threshold. Returns removed count."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id FROM vec_documents WHERE confidence < ?",
                (min_confidence,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if not ids:
                return 0

            placeholders = ",".join("?" * len(ids))

            # Drop the FTS delete trigger temporarily so the trigger doesn't
            # conflict with the FTS sync we do manually below.
            try:
                conn.execute("DROP TRIGGER IF EXISTS vec_fts_delete")
            except Exception:
                pass

            # Remove from FTS manually
            try:
                for doc_id in ids:
                    conn.execute("""
                        INSERT INTO vec_fts(vec_fts, rowid, content, source)
                        SELECT 'delete', id, content, source FROM vec_documents WHERE id = ?
                    """, (doc_id,))
            except Exception:
                pass

            # Remove embeddings
            try:
                if self._has_vec0(conn):
                    conn.execute(
                        f"DELETE FROM vec_embeddings WHERE rowid IN ({placeholders})", ids
                    )
                else:
                    conn.execute(
                        f"DELETE FROM vec_embeddings_fallback WHERE rowid IN ({placeholders})", ids
                    )
            except Exception:
                pass

            conn.execute(
                f"DELETE FROM vec_documents WHERE id IN ({placeholders})", ids
            )

            # Recreate the FTS delete trigger
            try:
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS vec_fts_delete
                    AFTER DELETE ON vec_documents BEGIN
                        INSERT INTO vec_fts(vec_fts, rowid, content, source)
                        VALUES ('delete', old.id, old.content, old.source);
                    END
                """)
            except Exception:
                pass

            conn.commit()
            return len(ids)
        except Exception as exc:
            logger.debug("VectorStore.gc failed: %s", exc)
            return 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def search_vector(
        self,
        query_text: str,
        top_k: int = 10,
        include_invalid: bool = False,
    ) -> list[dict[str, Any]]:
        """Vector similarity search. Returns list of result dicts."""
        if not query_text.strip():
            return []
        conn = self._connect()
        try:
            # Embed the query
            try:
                vecs = self._embedder.embed([query_text])
            except Exception:
                vecs = [[0.0] * self._dim]
            if not vecs or not vecs[0]:
                return []
            query_vec = vecs[0]
            packed_query = struct.pack(f"{self._dim}f", *query_vec)

            has_vec0 = self._has_vec0(conn)
            results: list[dict[str, Any]] = []

            if has_vec0:
                try:
                    # vec0 KNN search
                    rows = conn.execute("""
                        SELECT d.id, d.content, d.source, d.layer,
                               d.metadata_json, d.event_time, d.ingestion_time,
                               d.valid_until, d.confidence, d.access_count,
                               d.last_accessed,
                               e.distance
                        FROM vec_embeddings e
                        JOIN vec_documents d ON d.id = e.rowid
                        WHERE e.embedding MATCH ?
                          AND k = ?
                    """, (packed_query, top_k * 2)).fetchall()

                    for row in rows:
                        if not include_invalid and row["valid_until"] is not None:
                            continue
                        results.append(self._row_to_dict(row, distance=row["distance"]))
                except Exception as vec_exc:
                    logger.debug("vec0 search failed, falling back: %s", vec_exc)
                    results = self._fallback_vector_search(conn, query_vec, top_k, include_invalid)
            else:
                results = self._fallback_vector_search(conn, query_vec, top_k, include_invalid)

            # Update access tracking
            for r in results[:top_k]:
                self._touch(conn, r["id"])

            conn.commit()
            return results[:top_k]

        except Exception as exc:
            logger.debug("VectorStore.search_vector failed: %s", exc)
            return []
        finally:
            conn.close()

    def _fallback_vector_search(
        self,
        conn: sqlite3.Connection,
        query_vec: list[float],
        top_k: int,
        include_invalid: bool,
    ) -> list[dict[str, Any]]:
        """Manual cosine similarity when vec0 is unavailable."""
        try:
            # Try the fallback embeddings table first
            try:
                rows = conn.execute("""
                    SELECT d.id, d.content, d.source, d.layer,
                           d.metadata_json, d.event_time, d.ingestion_time,
                           d.valid_until, d.confidence, d.access_count,
                           d.last_accessed,
                           f.embedding
                    FROM vec_embeddings_fallback f
                    JOIN vec_documents d ON d.id = f.rowid
                """).fetchall()
            except Exception:
                # Neither vec table exists — return empty
                return []

            query_arr = np.array(query_vec, dtype=np.float32)
            scored: list[tuple[float, dict[str, Any]]] = []

            for row in rows:
                if not include_invalid and row["valid_until"] is not None:
                    continue
                try:
                    blob = row["embedding"]
                    n = len(blob) // 4
                    vec_vals = list(struct.unpack(f"{n}f", blob))
                    # Pad/trim to query dim
                    if len(vec_vals) < self._dim:
                        vec_vals += [0.0] * (self._dim - len(vec_vals))
                    vec_arr = np.array(vec_vals[:self._dim], dtype=np.float32)
                    # Cosine similarity → distance = 1 - sim
                    dot = float(np.dot(query_arr, vec_arr))
                    norm_q = float(np.linalg.norm(query_arr)) or 1.0
                    norm_v = float(np.linalg.norm(vec_arr)) or 1.0
                    sim = dot / (norm_q * norm_v)
                    distance = 1.0 - sim
                    scored.append((distance, self._row_to_dict(row, distance=distance)))
                except Exception:
                    pass

            scored.sort(key=lambda x: x[0])
            return [r for _, r in scored[:top_k]]
        except Exception as exc:
            logger.debug("_fallback_vector_search failed: %s", exc)
            return []

    def search_fts(
        self,
        query_text: str,
        top_k: int = 10,
        include_invalid: bool = False,
    ) -> list[dict[str, Any]]:
        """Full-text search using FTS5."""
        if not query_text.strip():
            return []
        conn = self._connect()
        try:
            # Sanitize query for FTS5
            fts_query = " OR ".join(
                w for w in query_text.split() if len(w) > 1
            ) or query_text

            rows = conn.execute("""
                SELECT d.id, d.content, d.source, d.layer,
                       d.metadata_json, d.event_time, d.ingestion_time,
                       d.valid_until, d.confidence, d.access_count,
                       d.last_accessed,
                       bm25(vec_fts) AS bm25_score
                FROM vec_fts
                JOIN vec_documents d ON d.id = vec_fts.rowid
                WHERE vec_fts MATCH ?
                ORDER BY bm25_score
                LIMIT ?
            """, (fts_query, top_k * 2)).fetchall()

            results = []
            for row in rows:
                if not include_invalid and row["valid_until"] is not None:
                    continue
                # bm25() returns negative values (lower = better match)
                bm25 = float(row["bm25_score"] or 0.0)
                # Normalize to [0,1] where 1 = best match
                distance = max(0.0, min(1.0, 1.0 + bm25 / 20.0))
                results.append(self._row_to_dict(row, distance=distance))

            # Update access tracking
            for r in results[:top_k]:
                self._touch(conn, r["id"])

            conn.commit()
            return results[:top_k]

        except Exception as exc:
            logger.debug("VectorStore.search_fts failed: %s", exc)
            return []
        finally:
            conn.close()

    def search_hybrid(
        self,
        query_text: str,
        top_k: int = 10,
        vector_weight: float = 0.6,
        fts_weight: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval: combine vector + FTS5 results using RRF-style fusion.

        Returns ranked list of result dicts with fused 'score' field.
        score is similarity (higher = more relevant), not distance.
        """
        if not query_text.strip():
            return []

        try:
            vec_results = self.search_vector(query_text, top_k=top_k * 2)
            fts_results = self.search_fts(query_text, top_k=top_k * 2)

            # Build score map: doc_id → (vec_score, fts_score)
            scores: dict[int, dict[str, Any]] = {}

            # Vector results: distance [0, ∞) → similarity score [0, 1]
            for rank, r in enumerate(vec_results):
                doc_id = r["id"]
                # Convert distance to similarity (closer = higher score)
                dist = r.get("distance", 1.0)
                vec_sim = max(0.0, 1.0 - dist)
                if doc_id not in scores:
                    scores[doc_id] = {**r, "vec_score": 0.0, "fts_score": 0.0}
                scores[doc_id]["vec_score"] = vec_sim

            # FTS results: distance already normalized [0, 1]
            for rank, r in enumerate(fts_results):
                doc_id = r["id"]
                fts_sim = max(0.0, 1.0 - r.get("distance", 1.0))
                if doc_id not in scores:
                    scores[doc_id] = {**r, "vec_score": 0.0, "fts_score": 0.0}
                scores[doc_id]["fts_score"] = fts_sim

            # Fuse
            fused: list[tuple[float, dict[str, Any]]] = []
            for doc_id, r in scores.items():
                fused_score = (
                    vector_weight * r.get("vec_score", 0.0) +
                    fts_weight * r.get("fts_score", 0.0)
                )
                result = dict(r)
                result["score"] = round(fused_score, 4)
                fused.append((fused_score, result))

            fused.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in fused[:top_k]]

        except Exception as exc:
            logger.debug("VectorStore.search_hybrid failed: %s", exc)
            return []

    def get_document(self, doc_id: int) -> dict[str, Any] | None:
        """Fetch a single document by ID."""
        conn = self._connect()
        try:
            row = conn.execute("""
                SELECT id, content, source, layer, metadata_json,
                       event_time, ingestion_time, valid_until,
                       confidence, access_count, last_accessed
                FROM vec_documents WHERE id = ?
            """, (doc_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)
        except Exception as exc:
            logger.debug("VectorStore.get_document failed: %s", exc)
            return None
        finally:
            conn.close()

    def stats(self) -> dict[str, Any]:
        """Return store statistics."""
        conn = self._connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM vec_documents"
            ).fetchone()[0]
            valid = conn.execute(
                "SELECT COUNT(*) FROM vec_documents WHERE valid_until IS NULL"
            ).fetchone()[0]
            avg_conf_row = conn.execute(
                "SELECT AVG(confidence) FROM vec_documents WHERE valid_until IS NULL"
            ).fetchone()
            avg_conf = float(avg_conf_row[0] or 0.0)
            by_layer = {}
            for row in conn.execute(
                "SELECT layer, COUNT(*) as cnt FROM vec_documents GROUP BY layer"
            ).fetchall():
                by_layer[row[0]] = row[1]
            return {
                "total_documents": total,
                "valid_documents": valid,
                "invalidated_documents": total - valid,
                "avg_confidence": round(avg_conf, 3),
                "by_layer": by_layer,
                "db_path": str(self._db_path),
                "embedder_dim": self._embedder.dim,
                "embedder_fitted": getattr(self._embedder, "_fitted", False),
            }
        except Exception as exc:
            logger.debug("VectorStore.stats failed: %s", exc)
            return {"total_documents": 0, "error": str(exc)}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_dict(
        self,
        row: sqlite3.Row,
        distance: float | None = None,
    ) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict."""
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except Exception:
            meta = {}
        result: dict[str, Any] = {
            "id": row["id"],
            "content": row["content"],
            "source": row["source"] or "",
            "layer": row["layer"] or "working",
            "metadata": meta,
            "event_time": row["event_time"],
            "ingestion_time": row["ingestion_time"],
            "valid_until": row["valid_until"],
            "confidence": float(row["confidence"] or 1.0),
            "access_count": int(row["access_count"] or 0),
            "last_accessed": row["last_accessed"],
        }
        if distance is not None:
            result["distance"] = distance
            # Derived similarity score
            result["score"] = max(0.0, round(1.0 - distance, 4))
        return result

    def _touch(self, conn: sqlite3.Connection, doc_id: int) -> None:
        """Update access tracking for a retrieved document."""
        try:
            now_iso = _utc_now_iso()
            conn.execute("""
                UPDATE vec_documents
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE id = ?
            """, (now_iso, doc_id))
        except Exception:
            pass


__all__ = [
    "Embedder",
    "TFIDFEmbedder",
    "VectorStore",
]
