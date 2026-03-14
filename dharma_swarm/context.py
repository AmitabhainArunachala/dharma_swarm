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

import json
import sqlite3
import time
from datetime import timezone
from pathlib import Path

from dharma_swarm.injection_scanner import scan_and_sanitize

HOME = Path.home()
AGNI_WORKSPACE = HOME / "agni-workspace"
TRISHULA_INBOX = HOME / "trishula" / "inbox"
STATE_DIR = HOME / ".dharma"
SHARED_DIR = STATE_DIR / "shared"
PSMV = HOME / "Persistent-Semantic-Memory-Vault"

# ── File reading helper ──────────────────────────────────────────────

def _read_file(path: Path, max_chars: int = 2000) -> str | None:
    """Read a file, truncate if needed, scan for injection. Returns None if missing."""
    if not path.exists():
        return None
    try:
        content = path.read_text()
        # Scan external files for prompt injection before inclusion
        content = scan_and_sanitize(content, path.name)
        if len(content) > max_chars:
            return content[:max_chars] + "\n... [truncated]"
        return content
    except Exception:
        return None


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
                    pass
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


def read_agent_notes(exclude_role: str | None = None, max_per_agent: int = 500) -> str:
    """Read recent notes from other agents in the swarm."""
    if not SHARED_DIR.exists():
        return ""
    sections = ["# Other Agents' Recent Findings"]
    notes_files = sorted(SHARED_DIR.glob("*_notes.md"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
    for nf in notes_files[:5]:
        role = nf.stem.replace("_notes", "")
        if exclude_role and role.lower() == exclude_role.lower():
            continue
        try:
            content = nf.read_text()
        except Exception:
            continue
        # Last N chars — most recent findings
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
    },
    "archeologist": {
        "vision": ["genome_spec", "samaya_protocol", "ten_words"],
        "research_weight": 0.5,
        "engineering_weight": 0.1,
        "ops_weight": 0.1,
        "notes_weight": 0.3,
    },
    "surgeon": {
        "vision": [],  # surgeon doesn't need vision, needs code
        "research_weight": 0.1,
        "engineering_weight": 0.6,
        "ops_weight": 0.2,
        "notes_weight": 0.3,
    },
    "architect": {
        "vision": ["genome_spec", "lenia_godel", "garden_daemon"],
        "research_weight": 0.3,
        "engineering_weight": 0.4,
        "ops_weight": 0.1,
        "notes_weight": 0.2,
    },
    "validator": {
        "vision": ["constitution"],
        "research_weight": 0.2,
        "engineering_weight": 0.4,
        "ops_weight": 0.3,
        "notes_weight": 0.3,
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
            pass
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
            pass
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
            pass
    tcs_file = stig_dir / "mycelium_identity_tcs.json"
    if tcs_file.exists():
        try:
            tcs_data = json.loads(tcs_file.read_text())
            tcs = tcs_data.get("tcs", 0)
            regime = tcs_data.get("regime", "unknown")
            sections.append(f"  System TCS: {tcs:.3f} ({regime})")
        except Exception:
            pass
    result = "\n".join(sections)
    return result[:max_chars] if len(sections) > 1 else ""


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


def build_agent_context(
    role: str | None = None,
    thread: str | None = None,
    state_dir: Path | None = None,
) -> str:
    """Assemble multi-layer context for an agent's system prompt.

    Selects content based on role (what the agent does) and thread
    (what research direction is active). Respects a total char budget.

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
    sections = []
    used = 0

    # L1: Vision — role-specific crown jewels
    vision_keys = profile.get("vision", ["ten_words", "soul"])
    if vision_keys:
        vision = read_vision(keys=vision_keys, max_per_file=1500)
        if vision:
            sections.append(vision)
            used += len(vision)

    # L2: Research — thread-weighted
    research_budget = int(budget * profile.get("research_weight", 0.3))
    if research_budget > 500:
        research = read_research(thread=thread, max_per_file=research_budget // 3)
        if research:
            sections.append(research)
            used += len(research)

    # L3: Engineering — code reality
    eng_budget = int(budget * profile.get("engineering_weight", 0.3))
    if eng_budget > 500:
        eng = read_engineering()
        if eng:
            sections.append(eng)
            used += len(eng)

    # L4: Ops — operational state (always include, compact)
    ops_budget = int(budget * profile.get("ops_weight", 0.2))
    if ops_budget > 300:
        ops = read_ops(state_dir)
        if ops and len(ops) > ops_budget:
            ops = ops[:ops_budget] + "\n... [ops truncated]"
        if ops:
            sections.append(ops)
            used += len(ops)

    # L5: Swarm — other agents' notes + recent session memories
    notes_budget = int(budget * profile.get("notes_weight", 0.2))
    if notes_budget > 200:
        notes = read_agent_notes(exclude_role=role, max_per_agent=notes_budget // 5)
        if notes:
            sections.append(notes)
            used += len(notes)

    # L5b: Recent memories from StrangeLoopMemory
    remaining = budget - used
    if remaining > 500:
        memories = read_recent_memories(state_dir=state_dir, max_entries=5)
        if memories:
            sections.append(memories)
            used += len(memories)

    # L7: Winners — amplification of highest-quality patterns
    remaining = budget - used
    if remaining > 500:
        winners = _read_winners(state_dir=state_dir, max_chars=min(1500, remaining // 3))
        if winners:
            sections.append(winners)
            used += len(winners)

    # L8: Stigmergy — hot signals from daemons and other agents
    remaining = budget - used
    if remaining > 500:
        stigmergy = _read_stigmergy_signals(
            state_dir=state_dir, max_chars=min(1500, remaining // 3)
        )
        if stigmergy:
            sections.append(stigmergy)
            used += len(stigmergy)

    # L9: META — recognition seed (strange loop closure)
    remaining = budget - used
    if remaining > 500:
        seed = _read_recognition_seed(
            state_dir=state_dir, max_chars=min(2000, remaining)
        )
        if seed:
            sections.append(seed)
            used += len(seed)

    # Memory survival instinct (Windsurf pattern)
    sections.append(MEMORY_SURVIVAL_DIRECTIVE)
    used += len(MEMORY_SURVIVAL_DIRECTIVE)

    result = "\n\n".join(sections)

    # Hard cap
    if len(result) > CONTEXT_BUDGET:
        result = result[:CONTEXT_BUDGET] + "\n\n... [context budget exceeded, truncated]"

    return result
