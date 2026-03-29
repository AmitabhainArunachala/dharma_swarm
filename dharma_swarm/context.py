"""Multi-layer context engine for dharma_swarm agents.

Five layers, selected by role x thread x task:

  L1 VISION    — PSMV crown jewels, Genome spec, ten_words, telos
  L2 RESEARCH  — CLAUDE1-9 (per thread), R_V data, experimental results
  L3 ENGINEER  — dgc-core code, dharma_swarm modules, test status, code map
  L4 OPS       — AGNI state, trishula inbox, manifest, shipped/pending
  L5 SWARM     — What other agents found this cycle (shared notes)

Each role gets a different mix. Each thread shifts emphasis.
Context budget: ~30K chars max (fits in system prompt alongside v7 rules).
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim
from dharma_swarm.dharma_kernel import DharmaKernel
from dharma_swarm.injection_scanner import scan_and_sanitize
from dharma_swarm.orientation_packet import (
    DirectiveSummary,
    OrientationPacket,
    OrientationPacketBuilder,
    RuntimeStateSummary,
)

HOME = Path.home()
AGNI_WORKSPACE = HOME / "agni-workspace"
TRISHULA_INBOX = HOME / "trishula" / "inbox"
STATE_DIR = HOME / ".dharma"
SHARED_DIR = STATE_DIR / "shared"
PSMV = HOME / "Persistent-Semantic-Memory-Vault"
FOUNDATIONS_DIR = HOME / "dharma_swarm" / "foundations"
ARCHITECTURE_DIR = HOME / "dharma_swarm" / "architecture"
TRANSMISSION_DIR = FOUNDATIONS_DIR / "transmissions"

# ── Types ────────────────────────────────────────────────────────────

CompressionTier = Literal["full", "medium", "minimal", "header", "tail"]


@dataclass
class ContextBlock:
    """A positioned chunk of context for U-shaped assembly."""
    name: str
    position: int       # Lower = closer to top of context (high-attention zone)
    content: str
    char_count: int


# ── Compression engine ───────────────────────────────────────────────


def _resolve_transmission(path: Path) -> Path:
    """Check for a transmission-grade (manually compressed) version of a file."""
    t_path = TRANSMISSION_DIR / (path.stem + ".transmission.md")
    return t_path if t_path.exists() else path


def _compress_full(content: str, max_chars: int) -> str:
    """Keep first 70% + last 30% — preserves both structure and conclusions."""
    if len(content) <= max_chars:
        return content
    marker = "\n... [truncated]\n"
    available = max_chars - len(marker)
    if available < 20:
        return content[:max_chars]
    head_budget = int(available * 0.7)
    tail_budget = available - head_budget
    return content[:head_budget] + marker + content[-tail_budget:]


def _compress_medium(content: str, max_chars: int) -> str:
    """First 40% + last 20%, skip middle — U-shape within document."""
    if len(content) <= max_chars:
        return content
    marker = "\n... [middle omitted]\n"
    available = max_chars - len(marker)
    if available < 20:
        return content[:max_chars]
    head_budget = int(available * 0.67)   # ~40% of 60% total
    tail_budget = available - head_budget  # ~20% of 60% total
    return content[:head_budget] + marker + content[-tail_budget:]


def _compress_minimal(content: str, max_chars: int) -> str:
    """First heading + first paragraph + last paragraph — orientation only."""
    if len(content) <= max_chars:
        return content
    lines = content.split("\n")
    if len(lines) <= 3:
        # Too few lines for paragraph extraction; fall back to head/tail
        return _compress_full(content, max_chars)
    # Gather opening lines (heading + first paragraph)
    head_lines: list[str] = []
    head_len = 0
    head_limit = max_chars // 2
    for line in lines:
        # Always include at least the first line
        if head_lines and head_len + len(line) + 1 > head_limit:
            break
        head_lines.append(line)
        head_len += len(line) + 1
    # Gather closing lines (last paragraph)
    tail_lines: list[str] = []
    tail_len = 0
    tail_limit = max_chars // 3
    for line in reversed(lines):
        if tail_lines and tail_len + len(line) + 1 > tail_limit:
            break
        tail_lines.insert(0, line)
        tail_len += len(line) + 1
    marker = "\n...\n"
    result = "\n".join(head_lines) + marker + "\n".join(tail_lines)
    return result[:max_chars]


def _compress_header(content: str, max_chars: int) -> str:
    """First N chars — same as legacy head truncation."""
    return content[:max_chars] if len(content) > max_chars else content


def _compress_tail(content: str, max_chars: int) -> str:
    """Last N chars — for append-only logs (agent notes, stigmergy)."""
    return content[-max_chars:] if len(content) > max_chars else content


_COMPRESSORS = {
    "full": _compress_full,
    "medium": _compress_medium,
    "minimal": _compress_minimal,
    "header": _compress_header,
    "tail": _compress_tail,
}


def _compress(
    path: Path,
    tier: CompressionTier = "full",
    max_chars: int = 2000,
) -> str | None:
    """Dispatcher: resolve transmission, scan injection, compress.

    Returns None if file is missing or unreadable.
    """
    resolved = _resolve_transmission(path)
    if not resolved.exists():
        return None
    try:
        content = resolved.read_text()
        content = scan_and_sanitize(content, resolved.name)
        return _COMPRESSORS[tier](content, max_chars)
    except Exception:
        return None


def _is_fresh(path: Path, hours: int = 6) -> bool:
    """Check if a file was modified within the last N hours."""
    try:
        age_h = (time.time() - path.stat().st_mtime) / 3600
        return age_h < hours
    except OSError:
        return False


def _fit_to_budget(blocks: list[ContextBlock], budget: int) -> list[ContextBlock]:
    """Trim middle-position blocks first when over budget.

    Protects positions 1-3 (top: seed, directive, primary) and 9-11
    (bottom: swarm, hot signals, vision). Drops from positions 4-8
    starting with position 8 downward.
    """
    total = sum(b.char_count for b in blocks)
    if total <= budget:
        return blocks

    result = list(blocks)
    trimmable = sorted(
        [b for b in result if 4 <= b.position <= 8],
        key=lambda b: b.position,
        reverse=True,
    )
    for block in trimmable:
        if total <= budget:
            break
        result.remove(block)
        total -= block.char_count

    return result


# ── File reading helper ──────────────────────────────────────────────

def _read_file(path: Path, max_chars: int = 2000) -> str | None:
    """Read a file with head+tail compression, scan for injection.

    Backward-compatible wrapper around _compress(). Uses 70/30 head/tail
    split instead of head-only truncation so conclusions are preserved.
    """
    return _compress(path, "full", max_chars)


def _read_head(path: Path, lines: int = 30) -> str | None:
    """Read first N lines of a file."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return "".join(f.readline() for _ in range(lines))
    except Exception:
        return None


def _format_retrieval_line(hit) -> str:
    record = hit.record
    metadata = record.metadata
    source_kind = str(metadata.get("source_kind", "unknown"))
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    stamp = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")

    if source_kind == "note":
        source_label = str(metadata.get("source_ref") or metadata.get("source_path") or "note")
        section = str(metadata.get("section_title") or "")
        provenance = f"{source_label} | {stamp}"
        if section:
            provenance = f"{provenance} | {section}"
    else:
        event_type = str(metadata.get("event_type") or "event")
        source = str(metadata.get("source") or "runtime")
        provenance = f"{event_type} @ {source} | {stamp}"

    snippet = record.text.replace("\n", " ").strip()[:100]
    return f"  [retrieval:{source_kind}] {provenance} | {snippet}"


def _format_idea_line(shard) -> str:
    created_at = shard.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    stamp = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    return (
        f"  [idea:{shard.state}] {shard.shard_kind} | "
        f"salience={shard.salience:.2f} | {stamp} | {shard.text[:140]}"
    )


# ── L1: VISION — The meta-layer ─────────────────────────────────────

# Crown jewels and specs to look for (first found wins)
_VISION_FILES = {
    "ten_words": [
        PSMV / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewel_forge" / "approved" / "ten_words.md",
        PSMV / "CORE" / "ten_words.md",
    ],
    "genome_spec": [
        PSMV / "06-Multi-System-Coherence" / "DHARMA_GENOME_SPECIFICATION.md",
        PSMV / "CORE" / "DHARMA_GENOME_SPECIFICATION.md",
    ],
    "garden_daemon": [
        PSMV / "AGENT_EMERGENT_WORKSPACES" / "GARDEN_DAEMON_SPEC.md",
    ],
    "induction_v7": [
        PSMV / "AGENT_EMERGENT_WORKSPACES" / "INDUCTION_PROMPT_v7.md",
    ],
    "samaya_protocol": [
        PSMV / "08-Research-Documentation" / "theoretical-frameworks" / "MASTER_PROMPT_Samaya_Darwin-Godel_Machine.md",
    ],
    "lenia_godel": [
        PSMV / "CORE" / "LENIA_GODEL_DHARMA_IMPLEMENTATION_PLAN.md",
    ],
    "soul": [
        AGNI_WORKSPACE / "SOUL.md",
    ],
    "constitution": [
        AGNI_WORKSPACE / "CONSTITUTION.md",
    ],
    "north_star": [
        AGNI_WORKSPACE / "NORTH_STAR" / "90_DAY_COUNTER_ATTRACTOR.md",
        AGNI_WORKSPACE / "NORTH_STAR" / "SAB_500_YEAR_VISION.md",
    ],
    "seed_crystal": [
        PSMV / "00-CORE" / "SEED_CRYSTAL.md",
    ],
    "the_catch": [
        PSMV / "CORE" / "THE_CATCH.md",
    ],
    "overmind_error": [
        PSMV / "06-Multi-System-Coherence" / "TELOS_SWARM_RESIDUAL_STREAM" / "THE_OVERMIND_ERROR.md",
    ],
    "mech_interp_bridge": [
        PSMV / "CORE" / "MECH_INTERP_BRIDGE.md",
    ],
    "psmv_crown_jewels": [
        FOUNDATIONS_DIR / "PSMV_CROWN_JEWELS.md",
    ],
}


def read_vision(keys: list[str] | None = None, max_per_file: int = 1500) -> str:
    """Read vision-layer documents. Specify keys or get defaults."""
    target_keys = keys or ["ten_words", "soul", "north_star"]
    sections = ["# Vision Layer"]
    for key in target_keys:
        paths = _VISION_FILES.get(key, [])
        for p in paths:
            content = _read_file(p, max_chars=max_per_file)
            if content:
                sections.append(f"\n## {key} ({p.name})\n{content}")
                break
    return "\n".join(sections) if len(sections) > 1 else ""


# ── L1b: FOUNDATIONS — Intellectual pillars and engineering principles ──


# Map task domains to the most relevant pillar files
_DOMAIN_PILLARS: dict[str, list[str]] = {
    "consciousness": [
        "PILLAR_09_DADA_BHAGWAN.md",
        "PILLAR_08_AUROBINDO.md",
        "PILLAR_07_HOFSTADTER.md",
        "PSMV_CROWN_JEWELS.md",
        "SACRED_GEOMETRY.md",
    ],
    "mechanistic": [
        "PILLAR_06_FRISTON.md",
        "PILLAR_05_DEACON.md",
        "PILLAR_07_HOFSTADTER.md",
        "THINKODYNAMIC_BRIDGE.md",
        "EMPIRICAL_CLAIMS_REGISTRY.md",
    ],
    "evolution": [
        "PILLAR_02_KAUFFMAN.md",
        "PILLAR_03_JANTSCH.md",
        "PILLAR_01_LEVIN.md",
        "RESIDUAL_STREAM_DIGEST.md",
    ],
    "governance": [
        "PILLAR_11_BEER.md",
        "PILLAR_10_VARELA.md",
        "PILLAR_05_DEACON.md",
        "SAMAYA_PROTOCOL.md",
    ],
    "architecture": [
        "PILLAR_11_BEER.md",
        "PILLAR_10_VARELA.md",
        "PILLAR_01_LEVIN.md",
        "../architecture/BLUEPRINTS.md",
    ],
    "identity": [
        "PILLAR_09_DADA_BHAGWAN.md",
        "PILLAR_07_HOFSTADTER.md",
        "PILLAR_10_VARELA.md",
    ],
    "economics": [
        "ECONOMIC_VISION.md",
    ],
}


def read_foundations(
    domain: str | None = None,
    max_per_file: int = 1500,
    max_total: int = 4000,
) -> str:
    """Read foundations context: principles + domain-relevant pillar summaries.

    Always includes PRINCIPLES.md (engineering constraints).
    Adds relevant pillar excerpts based on task domain.
    """
    if not FOUNDATIONS_DIR.exists():
        return ""

    sections: list[str] = ["# Foundations Layer"]
    used = 0

    # Always include engineering principles if available
    principles_path = ARCHITECTURE_DIR / "PRINCIPLES.md"
    if principles_path.exists():
        content = _read_file(principles_path, max_chars=min(2000, max_total // 2))
        if content:
            sections.append(f"## Engineering Principles\n{content}")
            used += len(content)

    # Add META_SYNTHESIS summary if available
    meta_path = FOUNDATIONS_DIR / "META_SYNTHESIS.md"
    if meta_path.exists() and used < max_total - 500:
        content = _read_head(meta_path, lines=40)
        if content:
            sections.append(f"## Foundations Overview\n{content}")
            used += len(content)

    # Add domain-relevant pillar excerpts
    pillar_names = _DOMAIN_PILLARS.get(domain or "", [])
    if not pillar_names:
        # Default: meta-synthesis covers it
        pillar_names = []

    for pname in pillar_names:
        if used >= max_total - 300:
            break
        ppath = FOUNDATIONS_DIR / pname
        if ppath.exists():
            content = _read_head(ppath, lines=25)
            if content:
                sections.append(f"## {pname.replace('.md', '').replace('_', ' ')}\n{content}")
                used += len(content)

    return "\n\n".join(sections) if len(sections) > 1 else ""


# ── L2: RESEARCH — Thread-specific knowledge ────────────────────────

# CLAUDE files mapped to research threads
_THREAD_CLAUDE_FILES = {
    "mechanistic": [HOME / "CLAUDE1.md", HOME / "CLAUDE5.md", HOME / "CLAUDE7.md"],
    "phenomenological": [HOME / "CLAUDE2.md", HOME / "CLAUDE3.md"],
    "architectural": [HOME / "CLAUDE5.md", HOME / "CLAUDE8.md"],
    "alignment": [HOME / "CLAUDE3.md", HOME / "CLAUDE8.md"],
    "scaling": [HOME / "CLAUDE7.md", HOME / "CLAUDE1.md"],
}

_RESEARCH_FILES = {
    "rv_paper": HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER" / "COLM_GAP_ANALYSIS_20260303.md",
    "phase1_report": HOME / "mech-interp-latent-lab-phase1" / "PHASE1_FINAL_REPORT.md",
    "prompt_bank_head": HOME / "mech-interp-latent-lab-phase1" / "CANONICAL_CODE" / "n300_mistral_test_prompt_bank.py",
    "rv_reality_check": AGNI_WORKSPACE / "scratch" / "RV_PAPER_REALITY_CHECK.md",
    "mi_answers": HOME / "trishula" / "inbox" / "MI_AGENT_TO_CODEX_RV_ANSWERS.md",
}


def read_research(thread: str | None = None, max_per_file: int = 2000) -> str:
    """Read research context, weighted by active thread."""
    sections = ["# Research Layer"]

    # Thread-specific CLAUDE files
    claude_files = _THREAD_CLAUDE_FILES.get(thread or "mechanistic", [])
    for cf in claude_files[:2]:  # max 2 CLAUDE files
        content = _read_file(cf, max_chars=max_per_file)
        if content:
            sections.append(f"\n## {cf.name}\n{content}")

    # Always include key research status
    for key in ["rv_paper", "rv_reality_check"]:
        path = _RESEARCH_FILES.get(key)
        if path:
            content = _read_file(path, max_chars=1500)
            if content:
                sections.append(f"\n## {key}\n{content}")

    return "\n".join(sections) if len(sections) > 1 else ""


def read_ecosystem_domains(domain: str = "all") -> str:
    """Read ecosystem domain context using the absorbed ecosystem_map."""
    try:
        from dharma_swarm.ecosystem_map import get_context_for
        return get_context_for(domain)
    except ImportError:
        return ""


# ── L3: ENGINEERING — Code reality ──────────────────────────────────

def read_engineering() -> str:
    """Read engineering context: what code exists, what tests say."""
    sections = ["# Engineering Layer"]

    # dharma_swarm module map
    ds_dir = HOME / "dharma_swarm" / "dharma_swarm"
    if ds_dir.exists():
        modules = sorted(ds_dir.glob("*.py"))
        mod_list = "\n".join(
            f"  {m.name} ({m.stat().st_size} bytes)"
            for m in modules if m.name != "__pycache__"
        )
        sections.append(f"## dharma_swarm modules\n{mod_list}")

    # dgc-core structure
    dgc_dir = HOME / "dgc-core"
    if dgc_dir.exists():
        dgc_files = []
        for sub in ["bin", "hooks", "memory", "context", "daemon"]:
            sub_dir = dgc_dir / sub
            if sub_dir.exists():
                for f in sorted(sub_dir.glob("*.py")):
                    dgc_files.append(f"  {sub}/{f.name} ({f.stat().st_size} bytes)")
        if dgc_files:
            sections.append(f"## dgc-core files\n" + "\n".join(dgc_files))

    # Test status (cached, don't run every time)
    test_cache = STATE_DIR / "last_test_result.txt"
    if test_cache.exists():
        age_h = (time.time() - test_cache.stat().st_mtime) / 3600
        if age_h < 1:
            sections.append(f"## Test Status (cached {age_h:.0f}h ago)\n{test_cache.read_text()[:500]}")

    # GENOME_WIRING.md — the bridge document
    wiring = HOME / "dharma_swarm" / "GENOME_WIRING.md"
    content = _read_head(wiring, lines=50)
    if content:
        sections.append(f"## Genome Wiring (first 50 lines)\n{content}")

    return "\n".join(sections) if len(sections) > 1 else ""


# ── L4: OPS — Operational state ─────────────────────────────────────

def read_agni_state() -> dict:
    """Read AGNI VPS state from synced workspace."""
    state: dict = {}
    for name, max_chars in [("WORKING.md", 500), ("HEARTBEAT.md", 300), ("PRIORITIES.md", 300)]:
        path = AGNI_WORKSPACE / name
        if path.exists():
            try:
                content = path.read_text()
            except Exception:
                continue
            state[name.split(".")[0].lower()] = content[:max_chars]
            if name == "PRIORITIES.md":
                age_h = (time.time() - path.stat().st_mtime) / 3600
                state["priorities_age_hours"] = round(age_h, 1)
                if age_h > 48:
                    state["priorities_stale"] = True
    return state


def read_trishula_inbox() -> str:
    """Check for unread trishula messages."""
    if not TRISHULA_INBOX.exists():
        return "No trishula inbox found."
    try:
        files = sorted(TRISHULA_INBOX.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:
        return "Trishula inbox unreadable."
    if not files:
        return "Inbox empty."
    recent = files[:3]
    summaries = []
    for f in recent:
        try:
            age_h = (time.time() - f.stat().st_mtime) / 3600
            summaries.append(f"  {f.name} ({age_h:.0f}h ago, {f.stat().st_size} bytes)")
        except OSError:
            summaries.append(f"  {f.name} (stat unavailable)")
    return f"{len(files)} messages, most recent:\n" + "\n".join(summaries)


def _read_memory_plane_context(
    plane_path: Path,
    *,
    query: str | None = None,
    limit: int = 5,
    consumer: str = "context.read_memory_context",
    task_id: str | None = None,
    allow_semantic_search: bool = True,
) -> str:
    from dharma_swarm.engine.hybrid_retriever import HybridRetriever
    from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore
    from dharma_swarm.engine.unified_index import UnifiedIndex

    index = UnifiedIndex(plane_path)
    retriever = HybridRetriever(index)
    retrieval_query = (query or "memory runtime lessons task note context event").strip()
    if retrieval_query and allow_semantic_search:
        hits = retriever.search_with_temporal_query(
            retrieval_query,
            limit=limit,
            consumer=consumer,
        )
        if hits:
            RetrievalFeedbackStore(plane_path).log_hits(
                retrieval_query,
                hits,
                consumer=consumer,
                task_id=task_id,
            )
            return "\n".join(_format_retrieval_line(hit) for hit in hits)

    recent = index.recent_chunks(limit=limit)
    if recent:
        return "\n".join(f"  [index] {entry.text[:100]}" for entry in recent)
    return ""


def read_memory_context(
    state_dir: Path | None = None,
    *,
    query: str | None = None,
    limit: int = 5,
    consumer: str = "context.read_memory_context",
    task_id: str | None = None,
    allow_semantic_search: bool = True,
) -> str:
    """Get recent or query-specific memory from dharma_swarm state."""
    base_dir = state_dir or STATE_DIR
    db_path = base_dir / "db" / "memory.db"
    plane_path = base_dir / "db" / "memory_plane.db"
    if query and plane_path.exists():
        try:
            plane_result = _read_memory_plane_context(
                plane_path,
                query=query,
                limit=limit,
                consumer=consumer,
                task_id=task_id,
                allow_semantic_search=allow_semantic_search,
            )
            if plane_result:
                return plane_result
        except Exception as e:
            return f"Memory plane unavailable: {e}"

    if not db_path.exists():
        if plane_path.exists():
            try:
                plane_result = _read_memory_plane_context(
                    plane_path,
                    query=query,
                    limit=limit,
                    consumer=consumer,
                    task_id=task_id,
                    allow_semantic_search=allow_semantic_search,
                )
                if plane_result:
                    return plane_result
            except Exception as e:
                return f"Memory plane unavailable: {e}"
        return "No memory database yet."
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT content, layer, timestamp FROM memories ORDER BY timestamp DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            if plane_path.exists():
                try:
                    plane_result = _read_memory_plane_context(
                        plane_path,
                        query=query,
                        limit=limit,
                        consumer=consumer,
                        task_id=task_id,
                        allow_semantic_search=allow_semantic_search,
                    )
                    if plane_result:
                        return plane_result
                except Exception:
                    logger.debug("Memory plane recall failed", exc_info=True)
            return "No memories stored yet."
        return "\n".join(f"  [{r['layer']}] {r['content'][:100]}" for r in rows)
    except Exception as e:
        return f"Memory unavailable: {e}"


def read_latent_gold_context(
    state_dir: Path | None = None,
    *,
    query: str,
    limit: int = 3,
) -> str:
    """Return unresolved high-value ideas relevant to the current query."""
    if not query.strip():
        return ""
    from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

    base_dir = state_dir or STATE_DIR
    plane_path = base_dir / "db" / "memory_plane.db"
    if not plane_path.exists():
        return ""
    try:
        store = ConversationMemoryStore(plane_path)
        shards = store.latent_gold(query, limit=limit)
    except Exception:
        return ""
    if not shards:
        return ""
    return "\n".join(_format_idea_line(shard) for shard in shards)


def read_latent_gold_overview(
    state_dir: Path | None = None,
    *,
    limit: int = 5,
) -> str:
    """Return the highest-salience unresolved ideas across the memory plane."""
    from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

    base_dir = state_dir or STATE_DIR
    plane_path = base_dir / "db" / "memory_plane.db"
    if not plane_path.exists():
        return ""
    try:
        store = ConversationMemoryStore(plane_path)
        shards = store.latent_gold("", limit=limit)
    except Exception:
        return ""
    if not shards:
        return ""
    return "\n".join(_format_idea_line(shard) for shard in shards)


def read_manifest() -> str:
    """Read ecosystem manifest summary."""
    manifest_path = HOME / ".dharma_manifest.json"
    if not manifest_path.exists():
        return "No ecosystem manifest."
    try:
        data = json.loads(manifest_path.read_text())
        eco = data.get("ecosystem", {})
        alive = sum(1 for v in eco.values() if v.get("exists"))
        return f"Ecosystem: {alive}/{len(eco)} paths exist. Last scan: {data.get('last_scan', 'unknown')}"
    except Exception:
        return "Manifest unreadable."


def read_shipped() -> str:
    """What's been shipped (agni-workspace/05_SHIPPED/)."""
    shipped_dir = AGNI_WORKSPACE / "05_SHIPPED"
    if not shipped_dir.exists():
        return "No shipped artifacts found."
    try:
        items = sorted(shipped_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return "Shipped directory unreadable."
    recent = items[:10]
    lines = [f"{len(items)} shipped artifacts, most recent:"]
    for item in recent:
        lines.append(f"  {item.name}")
    return "\n".join(lines)


def read_ops(state_dir: Path | None = None) -> str:
    """Full operational context."""
    sections = ["# Operations Layer"]

    agni = read_agni_state()
    if agni:
        sections.append(f"## AGNI VPS\n{json.dumps(agni, indent=2)[:800]}")

    sections.append(f"## Trishula\n{read_trishula_inbox()}")
    sections.append(f"## Memory\n{read_memory_context(state_dir)}")
    sections.append(f"## Ecosystem\n{read_manifest()}")
    sections.append(f"## Shipped\n{read_shipped()}")

    return "\n".join(sections)


# ── L5: SWARM — What other agents found ─────────────────────────────


def read_recent_memories(
    state_dir: Path | None = None,
    max_entries: int = 10,
) -> str:
    """Read recent session memories from StrangeLoopMemory database.

    This is a lightweight synchronous read of the most recent memories,
    designed to feed into the swarm context layer so agents can see what
    the system has been doing lately.

    Args:
        state_dir: Override for ~/.dharma state directory.
        max_entries: Maximum number of recent memories to return.

    Returns:
        Formatted string of recent memories, or empty string on failure.
    """
    try:
        base_dir = state_dir or STATE_DIR
        db_path = base_dir / "db" / "memory.db"
        if not db_path.exists():
            return ""

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT content, layer, timestamp FROM memories "
                "ORDER BY timestamp DESC LIMIT ?",
                (max(1, max_entries),),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return ""

        lines = ["## Recent Session Memories"]
        for content, layer, timestamp in rows:
            stamp = str(timestamp)[:19] if timestamp else "?"
            layer_tag = str(layer) if layer else "unknown"
            snippet = str(content).replace("\n", " ").strip()[:200]
            lines.append(f"  [{stamp}] ({layer_tag}) {snippet}")
        return "\n".join(lines)
    except Exception:
        return ""


def read_agent_notes(
    exclude_role: str | None = None,
    max_per_agent: int = 500,
    state_dir: Path | None = None,
) -> str:
    """Read recent notes from other agents in the swarm.

    Prefers distilled versions (from context_agent) when they exist and
    are fresh (< 6 hours old). Falls back to tail of raw notes.

    Args:
        state_dir: Override for ~/.dharma state directory. If provided,
                   reads from state_dir/shared/ instead of the global path.
    """
    if state_dir is not None:
        shared_dir = state_dir / "shared"
        base = state_dir
    else:
        shared_dir = SHARED_DIR
        base = STATE_DIR
    if not shared_dir.exists():
        return ""
    sections = ["# Other Agents' Recent Findings"]
    notes_files = sorted(shared_dir.glob("*_notes.md"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
    for nf in notes_files[:5]:
        role = nf.stem.replace("_notes", "")
        if exclude_role and role.lower() == exclude_role.lower():
            continue
        # Check for distilled version first
        distilled_path = base / "context" / "distilled" / f"{role}_distilled.md"
        if distilled_path.exists() and _is_fresh(distilled_path):
            try:
                content = distilled_path.read_text()
                if content:
                    sections.append(
                        f"\n## {role} (distilled)\n"
                        f"{content[:max_per_agent]}"
                    )
                    continue
            except Exception:
                logger.debug("Distilled notes read failed for %s", nf.name, exc_info=True)
        # Fall back to tail of raw notes
        try:
            content = nf.read_text()
        except Exception:
            continue
        tail = content[-max_per_agent:] if len(content) > max_per_agent else content
        sections.append(f"\n## {role}\n{tail}")

    return "\n".join(sections) if len(sections) > 1 else ""


# ── Role-specific context profiles ──────────────────────────────────

# Each role gets a different mix of layers.
# Format: {role: {layer: weight}}  where weight controls max_chars budget.
ROLE_PROFILES = {
    "cartographer": {
        "vision": ["soul", "north_star"],
        "research_weight": 0.3,
        "engineering_weight": 0.4,
        "ops_weight": 0.3,
        "notes_weight": 0.2,
        "foundations_domain": "architecture",
        "primary_layer": "ops",
        "vision_tier": "medium",
        "research_tier": "header",
        "engineering_tier": "full",
    },
    "archeologist": {
        "vision": ["genome_spec", "samaya_protocol", "ten_words", "seed_crystal", "the_catch"],
        "research_weight": 0.5,
        "engineering_weight": 0.1,
        "ops_weight": 0.1,
        "notes_weight": 0.3,
        "foundations_domain": "consciousness",
        "primary_layer": "research",
        "vision_tier": "full",
        "research_tier": "full",
        "engineering_tier": "minimal",
    },
    "surgeon": {
        "vision": [],  # surgeon doesn't need vision, needs code
        "research_weight": 0.1,
        "engineering_weight": 0.6,
        "ops_weight": 0.2,
        "notes_weight": 0.3,
        "foundations_domain": None,  # surgeon works on code, not foundations
        "primary_layer": "engineering",
        "vision_tier": "minimal",
        "research_tier": "tail",
        "engineering_tier": "full",
    },
    "architect": {
        "vision": ["genome_spec", "lenia_godel", "garden_daemon", "overmind_error"],
        "research_weight": 0.3,
        "engineering_weight": 0.4,
        "ops_weight": 0.1,
        "notes_weight": 0.2,
        "foundations_domain": "architecture",
        "primary_layer": "foundations",
        "vision_tier": "full",
        "research_tier": "medium",
        "engineering_tier": "full",
    },
    "validator": {
        "vision": ["constitution"],
        "research_weight": 0.2,
        "engineering_weight": 0.4,
        "ops_weight": 0.3,
        "notes_weight": 0.3,
        "foundations_domain": "governance",
        "primary_layer": "stigmergy",
        "vision_tier": "medium",
        "research_tier": "header",
        "engineering_tier": "medium",
    },
}

# Budget: total chars for context injection
CONTEXT_BUDGET = 33_000  # Increased from 30K to fit L7+L8+L9 strange loop layers

MEMORY_SURVIVAL_DIRECTIVE = (
    "\n\n## CRITICAL: MEMORY SURVIVAL\n"
    "YOUR CONTEXT WILL BE DESTROYED after this task completes. "
    "You will have NO memory of this conversation.\n"
    "Before your task ends, you MUST externalize:\n"
    "- Discoveries and patterns -> write to ~/.dharma/shared/<your_role>_notes.md (APPEND)\n"
    "- Important findings -> write to ~/.dharma/witness/ with timestamp\n"
    "- Lessons learned -> include in task result\n"
    "Read ~/.dharma/shared/ FIRST to see what other agents already found.\n"
    "Failure to externalize = permanent knowledge loss."
)


# ── L7/L8/L9: Winners + Stigmergy + META ────────────────────────────

STIGMERGY_DIR = STATE_DIR / "stigmergy"
META_DIR = STATE_DIR / "meta"


def _read_winners(state_dir: Path | None = None, max_chars: int = 1500) -> str:
    """L7: Read top forge scores and evolution winners for amplification."""
    base = state_dir or STATE_DIR
    sections = []
    scoring_file = base / "stigmergy" / "mycelium_scoring_report.json"
    if scoring_file.exists():
        try:
            data = json.loads(scoring_file.read_text())
            top = data.get("top_3", [])
            if top:
                lines = ["## L7: Quality Winners (Forge Scores)"]
                lines.append(f"Mean stars: {data.get('mean_stars', '?')}")
                for entry in top[:3]:
                    name = entry.get("name", "?")
                    stars = entry.get("stars", 0)
                    sw = entry.get("swabhaav_ratio", 0)
                    lines.append(f"  {stars:.1f}* {name} (swabhaav={sw:.2f})")
                sections.append("\n".join(lines))
        except Exception:
            logger.debug("Evolution fitness read failed", exc_info=True)
    evo_dir = base / "evolution"
    if evo_dir.exists():
        try:
            archive_file = evo_dir / "archive.jsonl"
            if archive_file.exists():
                lines_raw = archive_file.read_text().strip().split("\n")
                winners = []
                for line in lines_raw[-20:]:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        fitness_raw = entry.get("fitness", 0)
                        # Handle both numeric fitness and dict-of-dimensions
                        if isinstance(fitness_raw, dict):
                            vals = [v for v in fitness_raw.values() if isinstance(v, (int, float))]
                            fitness = sum(vals) / max(1, len(vals)) if vals else 0.0
                        else:
                            fitness = float(fitness_raw) if fitness_raw else 0.0
                        entry["_weighted_fitness"] = fitness
                        if fitness >= 0.7:
                            winners.append(entry)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                if winners:
                    winners.sort(key=lambda w: w.get("_weighted_fitness", 0), reverse=True)
                    wlines = ["## Evolution Winners"]
                    for w in winners[:3]:
                        comp = w.get("component", "?")
                        fit = w.get("_weighted_fitness", 0)
                        gen = w.get("generation", "?")
                        wlines.append(f"  {fit:.2f} fitness: {comp} (gen {gen})")
                    sections.append("\n".join(wlines))
        except Exception:
            logger.debug("Evolution archive read failed", exc_info=True)
    result = "\n\n".join(sections)
    return result[:max_chars] if result else ""


def _read_stigmergy_signals(state_dir: Path | None = None, max_chars: int = 1500) -> str:
    """L8: Read high-salience stigmergy marks for agent context."""
    base = state_dir or STATE_DIR
    stig_dir = base / "stigmergy"
    if not stig_dir.exists():
        return ""
    sections = ["## L8: Stigmergy Signals"]
    marks_file = stig_dir / "marks.jsonl"
    if marks_file.exists():
        try:
            lines = marks_file.read_text().strip().split("\n")
            hot_marks = []
            for line in lines[-50:]:
                if not line.strip():
                    continue
                try:
                    mark = json.loads(line)
                    sal = mark.get("salience", 0)
                    if sal >= 0.7:
                        hot_marks.append(mark)
                except (json.JSONDecodeError, TypeError):
                    continue
            if hot_marks:
                hot_marks.sort(key=lambda m: m.get("salience", 0), reverse=True)
                for m in hot_marks[:5]:
                    path = m.get("path", "?")
                    sal = m.get("salience", 0)
                    src = m.get("source", "?")
                    desc = m.get("description", "")[:80]
                    sections.append(f"  [{sal:.2f}] {path} ({src}): {desc}")
        except Exception:
            logger.debug("Stigmergy mycelium read failed", exc_info=True)
    tcs_file = stig_dir / "mycelium_identity_tcs.json"
    if tcs_file.exists():
        try:
            tcs_data = json.loads(tcs_file.read_text())
            tcs = tcs_data.get("tcs", 0)
            regime = tcs_data.get("regime", "unknown")
            sections.append(f"  System TCS: {tcs:.3f} ({regime})")
        except Exception:
            logger.debug("TCS identity read failed", exc_info=True)
    result = "\n".join(sections)
    return result[:max_chars] if len(sections) > 1 else ""


def read_consolidation_context(
    state_dir: Path | None = None,
    max_dreams: int = 3,
    max_chars: int = 2000,
) -> str:
    """Read recent dreams and consolidation corrections for agent context.

    Surfaces outputs from the sleep-cycle neural consolidation and
    subconscious dreaming layers so forward-pass agents have awareness
    of what the colony discovered while they were inactive.

    Sources (checked in order):
    1. ``dream_associations.jsonl`` -- structured dream associations (last N)
    2. ``latest_dream.md`` -- narrative dream summary (fresh within 48h)
    3. ``consolidation/reports/`` -- most recent consolidation report

    Returns:
        Formatted string block or empty string if nothing recent.
    """
    base = state_dir or STATE_DIR
    parts: list[str] = []

    # --- Recent dream associations ---
    dream_file = base / "subconscious" / "dream_associations.jsonl"
    if dream_file.exists():
        try:
            raw_lines = dream_file.read_text().strip().split("\n")
            # Take last N entries (most recent)
            recent = raw_lines[-max_dreams:] if raw_lines else []
            dream_summaries: list[str] = []
            for line in recent:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    rtype = entry.get("resonance_type", "unknown")
                    salience = entry.get("salience", 0)
                    desc = entry.get("description", "")[:200]
                    vocab = entry.get("invented_vocabulary", "")
                    summary = f"- [{rtype}] (salience={salience:.2f}) {desc}"
                    if vocab:
                        summary += f" [coined: {vocab}]"
                    dream_summaries.append(summary)
                except (json.JSONDecodeError, TypeError):
                    continue
            if dream_summaries:
                parts.append(
                    "### Recent Dreams (Subconscious HUM)\n"
                    + "\n".join(dream_summaries)
                )
        except Exception:
            logger.debug("Dream associations read failed", exc_info=True)

    # --- Latest dream narrative (if fresh) ---
    if not parts:
        # Only fall back to narrative if no structured dreams found
        latest_dream = base / "subconscious" / "latest_dream.md"
        if latest_dream.exists() and _is_fresh(latest_dream, hours=48):
            try:
                content = latest_dream.read_text().strip()
                content = scan_and_sanitize(content, "latest_dream.md")
                if content:
                    # Take first ~800 chars (the opening associations)
                    trimmed = content[:800]
                    if len(content) > 800:
                        trimmed += "\n... [dream truncated]"
                    parts.append(f"### Latest Dream\n{trimmed}")
            except Exception:
                logger.debug("Latest dream read failed", exc_info=True)

    # --- Most recent consolidation report ---
    reports_dir = base / "consolidation" / "reports"
    if reports_dir.exists():
        try:
            report_files = sorted(reports_dir.glob("consolidation_*.json"))
            if report_files:
                latest_report = report_files[-1]
                if _is_fresh(latest_report, hours=48):
                    data = json.loads(latest_report.read_text())
                    losses = data.get("losses_found", 0)
                    corrections = data.get("corrections_applied", 0)
                    divisions = data.get("division_proposals", 0)
                    advocate = data.get("advocate_summary", "")[:150]
                    if losses or corrections:
                        report_line = (
                            f"### Latest Consolidation\n"
                            f"Losses: {losses}, Corrections: {corrections}, "
                            f"Division proposals: {divisions}"
                        )
                        if advocate:
                            report_line += f"\nAdvocate: {advocate}"
                        parts.append(report_line)
        except Exception:
            logger.debug("Consolidation report read failed", exc_info=True)

    if not parts:
        return ""

    header = "## L6: Consolidation -- Dreams & Corrections\n"
    body = "\n\n".join(parts)
    result = header + body
    return result[:max_chars] if len(result) > max_chars else result


def _read_recognition_seed(state_dir: Path | None = None, max_chars: int = 2000) -> str:
    """L9: Read the recognition seed — the strange loop's self-model."""
    base = state_dir or STATE_DIR
    seed_path = base / "meta" / "recognition_seed.md"
    if not seed_path.exists():
        return ""
    try:
        content = seed_path.read_text()
        content = scan_and_sanitize(content, "recognition_seed.md")
        if not content.strip():
            return ""
        header = "## L9: META -- Recognition Seed\n"
        if len(content) > max_chars - len(header):
            content = content[:max_chars - len(header)] + "\n... [seed truncated]"
        return header + content
    except Exception:
        return ""


# Map primary_layer profile values to block names
_PRIMARY_LAYER_BLOCK = {
    "engineering": "engineering",
    "research": "research",
    "ops": "ops",
    "foundations": "foundations",
    "stigmergy": "hot_signals",
}

# Default positions for U-shaped layout:
#   TOP (strong attention): 1=seed, 2=directive, 3=primary
#   MIDDLE (weaker attention): 4=foundations, 5=research, 6=engineering, 7=ops, 8=memories
#   BOTTOM (strong attention): 9=swarm, 10=hot_signals, 11=vision
_DEFAULT_POSITIONS = {
    "recognition_seed": 1,
    "survival_directive": 2,
    "foundations": 4,
    "research": 5,
    "engineering": 6,
    "ops": 7,
    "ingested_knowledge": 7,
    "consolidation": 8,
    "recent_memories": 8,
    "swarm_notes": 9,
    "hot_signals": 10,
    "vision": 11,
}


def read_ingested_knowledge(
    query: str = "",
    *,
    state_dir: Path | None = None,
    limit: int = 5,
    max_chars: int = 2000,
) -> str:
    """Query SemanticIngestionSpine for knowledge relevant to *query*.

    Returns empty string when no documents have been ingested, the query is
    empty, or any error occurs during retrieval. Uses a 5s wall-clock timeout
    so a locked/busy database never blocks the context build.
    """
    if not query.strip():
        return ""
    try:
        # Fast guard: skip if the ingestion spine DB doesn't exist yet.
        _sdir = Path(state_dir or Path.home() / ".dharma")
        _spine_db = _sdir / "semantic" / "ingestion_spine.db"
        if not _spine_db.exists():
            return ""
        try:
            with sqlite3.connect(str(_spine_db), timeout=1.0) as _chk:
                _count = _chk.execute("SELECT COUNT(*) FROM documents").fetchone()
            if not _count or _count[0] == 0:
                return ""
        except Exception:
            return ""

        # Move init + search into a thread so any DB lock doesn't block caller.
        def _search() -> list[dict]:
            from dharma_swarm.semantic_ingestion import SemanticIngestionSpine
            spine = SemanticIngestionSpine(state_dir=state_dir)
            return spine.search(query, limit=limit)

        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = _pool.submit(_search)
        try:
            results: list[dict] = fut.result(timeout=5.0)
        except (concurrent.futures.TimeoutError, Exception):
            _pool.shutdown(wait=False)
            return ""
        finally:
            _pool.shutdown(wait=False)

        if not results:
            return ""
        lines = ["## Ingested Knowledge"]
        for hit in results:
            path = str(hit.get("source_path", ""))
            text = str(hit.get("matched_text", "")).strip()
            score = float(hit.get("score", 0.0))
            if text:
                name = Path(path).name if path else "unknown"
                lines.append(f"- [{name} score={score:.2f}] {text}")
        if len(lines) <= 1:
            return ""
        content = "\n".join(lines)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... [truncated]"
        return content
    except Exception:
        return ""


def build_agent_context(
    role: str | None = None,
    thread: str | None = None,
    state_dir: Path | None = None,
) -> str:
    """Assemble multi-layer context for an agent's system prompt.

    Uses U-shaped positional layout: high-signal content at context
    boundaries (top/bottom), reference material in the middle. Each
    role's primary layer is promoted to position 3 (high attention).

    Budget fitting trims middle-position blocks first (4-8), never
    the top (seed, directive, primary) or bottom (swarm, signals, vision).

    Args:
        role: Agent role (cartographer, archeologist, surgeon, architect, validator).
              Falls back to generic if unknown.
        thread: Active research thread (mechanistic, phenomenological, etc.).
        state_dir: Override for ~/.dharma state directory.

    Returns:
        Complete context string for injection into system prompt.
    """
    profile = ROLE_PROFILES.get(role or "", {})
    budget = CONTEXT_BUDGET
    blocks: list[ContextBlock] = []
    primary_layer = profile.get("primary_layer")
    promoted_block = _PRIMARY_LAYER_BLOCK.get(primary_layer or "")

    def _pos(block_name: str) -> int:
        """Position for a block: 3 if promoted, else default."""
        if block_name == promoted_block:
            return 3
        return _DEFAULT_POSITIONS.get(block_name, 6)

    def _add(name: str, content: str) -> None:
        if content:
            blocks.append(ContextBlock(name, _pos(name), content, len(content)))

    # L9: Recognition seed (lands at top for instant orientation)
    seed = _read_recognition_seed(state_dir=state_dir, max_chars=2000)
    if seed:
        blocks.append(ContextBlock("recognition_seed", 1, seed, len(seed)))

    # Memory survival directive (always position 2)
    blocks.append(ContextBlock(
        "survival_directive", 2,
        MEMORY_SURVIVAL_DIRECTIVE, len(MEMORY_SURVIVAL_DIRECTIVE),
    ))

    # L1b: Foundations — intellectual pillars + engineering principles
    foundations_domain = profile.get("foundations_domain")
    if foundations_domain is None:
        _thread_domain_map = {
            "mechanistic": "mechanistic",
            "phenomenological": "consciousness",
            "architectural": "architecture",
            "alignment": "governance",
            "scaling": "evolution",
        }
        foundations_domain = _thread_domain_map.get(thread or "", None)
    foundations_budget = int(budget * 0.12)
    if foundations_budget > 300:
        foundations = read_foundations(
            domain=foundations_domain,
            max_total=foundations_budget,
        )
        _add("foundations", foundations)

    # L2: Research — thread-weighted
    research_budget = int(budget * profile.get("research_weight", 0.3))
    if research_budget > 500:
        research = read_research(thread=thread, max_per_file=research_budget // 3)
        _add("research", research)

    # L3: Engineering — code reality
    eng_budget = int(budget * profile.get("engineering_weight", 0.3))
    if eng_budget > 500:
        eng = read_engineering()
        _add("engineering", eng)

    # L4: Ops — operational state
    ops_budget = int(budget * profile.get("ops_weight", 0.2))
    if ops_budget > 300:
        ops = read_ops(state_dir)
        if ops and len(ops) > ops_budget:
            ops = ops[:ops_budget] + "\n... [ops truncated]"
        _add("ops", ops)

    # L7: Ingested knowledge from SemanticIngestionSpine
    ingested_query = thread or role or ""
    if ingested_query:
        ingested = read_ingested_knowledge(ingested_query, state_dir=state_dir)
        _add("ingested_knowledge", ingested)

    # L6: Consolidation — dreams & corrections from sleep cycle
    consolidation = read_consolidation_context(
        state_dir=state_dir, max_dreams=3, max_chars=2000,
    )
    if consolidation:
        _add("consolidation", consolidation)

    # L5b: Recent memories from StrangeLoopMemory
    memories = read_recent_memories(state_dir=state_dir, max_entries=5)
    if memories:
        blocks.append(ContextBlock("recent_memories", 8, memories, len(memories)))

    # L5: Swarm — other agents' notes
    notes_budget = int(budget * profile.get("notes_weight", 0.2))
    if notes_budget > 200:
        notes = read_agent_notes(exclude_role=role, max_per_agent=notes_budget // 5, state_dir=state_dir)
        if notes:
            blocks.append(ContextBlock("swarm_notes", 9, notes, len(notes)))

    # L7+L8: Winners + Stigmergy — hot signals
    winners = _read_winners(state_dir=state_dir, max_chars=1500)
    stigmergy = _read_stigmergy_signals(state_dir=state_dir, max_chars=1500)
    hot_parts = [s for s in [winners, stigmergy] if s]
    if hot_parts:
        hot_signals = "\n\n".join(hot_parts)
        blocks.append(ContextBlock(
            "hot_signals", _pos("hot_signals"),
            hot_signals, len(hot_signals),
        ))

    # L1: Vision — crown jewels land last (bottom of context = strong attention)
    vision_keys = profile.get("vision", ["ten_words", "soul"])
    if vision_keys:
        vision = read_vision(keys=vision_keys, max_per_file=1500)
        if vision:
            blocks.append(ContextBlock("vision", 11, vision, len(vision)))

    # Fit to budget (trim middle positions 4-8 first)
    blocks = _fit_to_budget(blocks, budget)

    # Sort by position → assemble
    blocks.sort(key=lambda b: b.position)
    result = "\n\n".join(b.content for b in blocks)

    # Hard cap
    if len(result) > CONTEXT_BUDGET:
        result = result[:CONTEXT_BUDGET] + "\n\n... [context budget exceeded, truncated]"

    return result


def build_orientation_packet(
    *,
    role: str,
    claims: list[Claim],
    kernel: DharmaKernel | None = None,
    contradictions: list[Contradiction] | None = None,
    directives: list[DirectiveSummary | dict] | None = None,
    runtime_state: RuntimeStateSummary | dict | None = None,
    role_context: str = "",
    task: str | None = None,
    provenance: list[str] | None = None,
    stale_sources: list[str] | None = None,
) -> OrientationPacket:
    """Build a typed orientation packet alongside the legacy text context path.

    This intentionally keeps the existing string-based context engine intact while
    exposing a structured initialization surface for runtimes that want something
    more inspectable than a monolithic prompt blob.
    """
    builder = OrientationPacketBuilder()
    return builder.build(
        role=role,
        kernel=kernel or DharmaKernel.create_default(),
        claims=claims,
        contradictions=contradictions,
        directives=directives,
        runtime_state=runtime_state,
        role_context=role_context,
        task=task,
        provenance=provenance,
        stale_sources=stale_sources,
    )
