"""Canonical runtime context compiler for DGC vNext."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dharma_swarm.memory_lattice import MemoryLattice, MemoryRecallHit
from dharma_swarm.provider_policy import ProviderPolicyRouter, ProviderRouteRequest
from dharma_swarm.runtime_state import (
    ArtifactRecord,
    ContextBundleRecord,
    DelegationRun,
    MemoryFact,
    RuntimeStateStore,
    SessionState,
    WorkspaceLease,
)

logger = logging.getLogger(__name__)


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _approx_char_budget(token_budget: int) -> int:
    return max(800, max(1, int(token_budget)) * 4)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    return text[: max_chars - 15].rstrip() + "\n... [truncated]"


@dataclass(frozen=True)
class ContextSection:
    name: str
    priority: int
    content: str
    source_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "priority": self.priority,
            "content": self.content,
            "source_refs": list(self.source_refs),
            "metadata": dict(self.metadata),
        }


class ContextCompiler:
    """Compile reproducible, budgeted context bundles from canonical state.

    Supports frozen snapshots for prompt-cache-friendly operation:
    call ``freeze(session_id)`` after the first compile to lock the
    bundle for that session.  Subsequent ``compile_bundle()`` calls
    return the frozen snapshot (avoiding prompt cache invalidation)
    unless ``force_refresh=True`` is passed.
    """

    _SECTION_WEIGHTS = {
        "Governance": 0.09,
        "Operator Intent": 0.10,
        "Task State": 0.10,
        "Always-On Memory": 0.12,
        "Relevant Knowledge": 0.10,  # Sprint 2: PlugMem knowledge block
        "Recent Session": 0.09,
        "Retrieved Recall": 0.09,
        "Memory Palace": 0.09,
        "Semantic Context": 0.05,
        "Durable Facts": 0.08,
        "Artifacts": 0.05,
        "Workspace": 0.04,
    }

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore,
        memory_lattice: MemoryLattice,
        provider_policy: ProviderPolicyRouter | None = None,
        memory_palace: Any = None,
        graph_store: Any = None,
        knowledge_store: Any = None,
    ) -> None:
        self.runtime_state = runtime_state
        self.memory_lattice = memory_lattice
        self.provider_policy = provider_policy or ProviderPolicyRouter()
        self.memory_palace = memory_palace
        self.graph_store = graph_store  # Phase 7b: semantic graph
        self.knowledge_store = knowledge_store  # Sprint 2: PlugMem knowledge store
        # Frozen snapshot cache: session_id -> ContextBundleRecord
        self._frozen_bundles: dict[str, ContextBundleRecord] = {}

    # ── Frozen snapshot API ─────────────────────────────────────────

    def freeze(self, session_id: str, bundle: ContextBundleRecord) -> None:
        """Freeze a bundle for *session_id*, enabling prompt cache reuse."""
        self._frozen_bundles[session_id] = bundle

    def thaw(self, session_id: str) -> ContextBundleRecord | None:
        """Remove and return the frozen bundle for *session_id*, or None."""
        return self._frozen_bundles.pop(session_id, None)

    def is_frozen(self, session_id: str) -> bool:
        """Check whether a frozen snapshot exists for *session_id*."""
        return session_id in self._frozen_bundles

    async def compile_bundle(
        self,
        *,
        session_id: str,
        task_id: str = "",
        run_id: str = "",
        operator_intent: str = "",
        task_description: str = "",
        query: str | None = None,
        token_budget: int = 1200,
        policy_constraints: list[str] | None = None,
        provider_request: ProviderRouteRequest | None = None,
        workspace_root: Path | str | None = None,
        active_paths: list[Path | str] | None = None,
        metadata: dict[str, Any] | None = None,
        force_refresh: bool = False,
        previous_mem: Any = None,
    ) -> ContextBundleRecord:
        # ── MemPO-style truncation ──────────────────────────────────
        # When ENABLE_MEM_TRUNCATION is set and a previous_mem is provided,
        # replace the full context assembly with a compact summary.
        import os as _os
        _mem_truncation = _os.getenv("ENABLE_MEM_TRUNCATION", "false").strip().lower()
        if (
            _mem_truncation in ("1", "true", "yes", "on")
            and previous_mem is not None
            and getattr(previous_mem, "content", "")
        ):
            from dharma_swarm.mem_action import build_truncated_context

            truncated = build_truncated_context(
                system_prompt=operator_intent,
                previous_mem=previous_mem,
                current_query=task_description,
            )
            if truncated:
                created_at = _utc_now()
                section = ContextSection(
                    name="MemPO Truncated Context",
                    priority=1,
                    content=truncated,
                    metadata={"mem_truncated": True},
                )
                checksum = _sha256(
                    _canonical_json({
                        "session_id": session_id,
                        "task_id": task_id,
                        "run_id": run_id,
                        "rendered_text": truncated,
                        "source_refs": [],
                    })
                )
                bundle = ContextBundleRecord(
                    bundle_id=self.runtime_state.new_bundle_id(),
                    session_id=session_id,
                    task_id=task_id,
                    run_id=run_id,
                    token_budget=int(token_budget),
                    rendered_text=truncated,
                    sections=[section.as_dict()],
                    source_refs=[],
                    checksum=checksum,
                    created_at=created_at,
                    metadata={**(metadata or {}), "mem_truncated": True},
                )
                await self.runtime_state.init_db()
                saved = await self.runtime_state.record_context_bundle(bundle)
                return saved

        # Return frozen snapshot if available (preserves prompt cache)
        if not force_refresh and session_id in self._frozen_bundles:
            return self._frozen_bundles[session_id]
        await self.runtime_state.init_db()
        await self.memory_lattice.init_db()

        session = await self.runtime_state.get_session(session_id)
        runs = await self.runtime_state.list_delegation_runs(
            session_id=session_id,
            task_id=task_id or None,
            limit=5,
        )
        facts = await self.runtime_state.list_memory_facts(
            session_id=session_id,
            task_id=task_id or None,
            truth_state="promoted",
            limit=6,
        )
        artifacts = await self.runtime_state.list_artifacts(
            session_id=session_id,
            task_id=task_id or None,
            run_id=run_id or None,
            limit=6,
        )
        leases = await self.runtime_state.list_workspace_leases(
            holder_run_id=run_id or None,
            active_only=True,
            limit=6,
        )
        recent_events = await self.memory_lattice.replay_session(session_id, limit=6)
        recall_query = self._compose_recall_query(
            operator_intent=operator_intent,
            task_description=task_description,
            query=query,
            task_id=task_id,
        )
        recall_hits = (
            await self.memory_lattice.recall(
                recall_query,
                limit=6,
                session_id=session_id,
                task_id=task_id or None,
            )
            if recall_query
            else []
        )
        always_on = await self.memory_lattice.always_on_context(max_chars=_approx_char_budget(token_budget) // 4)
        palace_hits: list[dict[str, Any]] = []
        if self.memory_palace is not None:
            try:
                if recall_query:
                    palace_hits = self.memory_palace.search(recall_query, top_k=5)
            except Exception as exc:
                logger.debug("Memory Palace search failed: %s", exc)

        # Phase 7b: Semantic graph concept search
        semantic_hits: list[dict[str, Any]] = []
        if self.graph_store is not None and recall_query:
            try:
                semantic_hits = self._query_semantic_graph(recall_query)
            except Exception as exc:
                logger.debug("Semantic graph search failed: %s", exc)

        # Sprint 2: Concept-centric knowledge retrieval
        knowledge_block = ""
        if self.knowledge_store is not None and recall_query:
            try:
                knowledge_block = self._retrieve_knowledge_block(
                    task_description=task_description or recall_query,
                )
            except Exception as exc:
                logger.debug("Knowledge block retrieval failed: %s", exc)

        sections = self._build_sections(
            session=session,
            task_id=task_id,
            run_id=run_id,
            operator_intent=operator_intent,
            task_description=task_description,
            policy_constraints=policy_constraints or [],
            provider_request=provider_request,
            always_on=always_on,
            recent_events=recent_events,
            recall_hits=recall_hits,
            palace_hits=palace_hits,
            semantic_hits=semantic_hits,
            knowledge_block=knowledge_block,
            facts=facts,
            artifacts=artifacts,
            workspace_root=Path(workspace_root).expanduser() if workspace_root else None,
            active_paths=[Path(item).expanduser() for item in (active_paths or [])],
            runs=runs,
            leases=leases,
        )

        char_budget = _approx_char_budget(token_budget)
        rendered_text, trimmed_sections = self._fit_sections(sections, char_budget)
        source_refs = _dedupe(
            ref
            for section in trimmed_sections
            for ref in section.source_refs
        )
        created_at = _utc_now()
        checksum = _sha256(
            _canonical_json(
                {
                    "session_id": session_id,
                    "task_id": task_id,
                    "run_id": run_id,
                    "rendered_text": rendered_text,
                    "source_refs": source_refs,
                }
            )
        )
        bundle = ContextBundleRecord(
            bundle_id=self.runtime_state.new_bundle_id(),
            session_id=session_id,
            task_id=task_id,
            run_id=run_id,
            token_budget=int(token_budget),
            rendered_text=rendered_text,
            sections=[section.as_dict() for section in trimmed_sections],
            source_refs=source_refs,
            checksum=checksum,
            created_at=created_at,
            metadata=dict(metadata or {}),
        )
        saved = await self.runtime_state.record_context_bundle(bundle)
        if session is not None:
            await self.runtime_state.upsert_session(
                SessionState(
                    session_id=session.session_id,
                    operator_id=session.operator_id,
                    status=session.status,
                    current_task_id=task_id or session.current_task_id,
                    active_bundle_id=saved.bundle_id,
                    metadata=session.metadata,
                    created_at=session.created_at,
                    updated_at=created_at,
                )
            )
        return saved

    def _compose_recall_query(
        self,
        *,
        operator_intent: str,
        task_description: str,
        query: str | None,
        task_id: str,
    ) -> str:
        if query:
            return str(query).strip()
        parts = [operator_intent.strip(), task_description.strip(), task_id.strip()]
        return " ".join(part for part in parts if part).strip()

    def _build_sections(
        self,
        *,
        session: SessionState | None,
        task_id: str,
        run_id: str,
        operator_intent: str,
        task_description: str,
        policy_constraints: list[str],
        provider_request: ProviderRouteRequest | None,
        always_on: str,
        recent_events: list[dict[str, Any]],
        recall_hits: list[MemoryRecallHit],
        palace_hits: list[dict[str, Any]],
        semantic_hits: list[dict[str, Any]],
        knowledge_block: str = "",
        facts: list[MemoryFact] | None = None,
        artifacts: list[ArtifactRecord] | None = None,
        workspace_root: Path | None = None,
        active_paths: list[Path] | None = None,
        runs: list[DelegationRun] | None = None,
        leases: list[WorkspaceLease] | None = None,
    ) -> list[ContextSection]:
        facts = facts or []
        artifacts = artifacts or []
        active_paths = active_paths or []
        runs = runs or []
        leases = leases or []
        sections: list[ContextSection] = []

        governance_lines = [f"- {item}" for item in policy_constraints if str(item).strip()]
        if provider_request is not None:
            decision = self.provider_policy.route(provider_request)
            governance_lines.extend(
                [
                    f"- provider_path={decision.path.value}",
                    f"- provider_selected={decision.selected_provider.value}",
                    f"- provider_confidence={decision.confidence:.2f}",
                ]
            )
            if decision.reasons:
                governance_lines.append(
                    f"- provider_reasons={', '.join(str(reason) for reason in decision.reasons)}"
                )
        if governance_lines:
            sections.append(
                ContextSection(
                    name="Governance",
                    priority=1,
                    content="\n".join(governance_lines),
                    source_refs=[],
                )
            )

        if operator_intent.strip():
            sections.append(
                ContextSection(
                    name="Operator Intent",
                    priority=2,
                    content=operator_intent.strip(),
                    source_refs=[],
                )
            )

        task_lines: list[str] = []
        if task_id:
            task_lines.append(f"- task_id={task_id}")
        if run_id:
            task_lines.append(f"- run_id={run_id}")
        if task_description.strip():
            task_lines.append(f"- task={task_description.strip()}")
        if session is not None:
            task_lines.append(f"- session_status={session.status}")
            if session.current_task_id:
                task_lines.append(f"- session_current_task={session.current_task_id}")
        for run in runs[:3]:
            task_lines.append(
                f"- delegation_run {run.run_id} status={run.status} assigned_to={run.assigned_to}"
            )
        for lease in leases[:3]:
            task_lines.append(
                f"- workspace_lease {lease.mode} {lease.zone_path} holder={lease.holder_run_id or 'n/a'}"
            )
        if task_lines:
            sections.append(
                ContextSection(
                    name="Task State",
                    priority=3,
                    content="\n".join(task_lines),
                    source_refs=[],
                )
            )

        if always_on.strip():
            sections.append(
                ContextSection(
                    name="Always-On Memory",
                    priority=4,
                    content=always_on.strip(),
                    source_refs=[],
                )
            )

        # Sprint 2: Knowledge block — structured facts + skills before raw memories
        if knowledge_block and knowledge_block.strip():
            sections.append(
                ContextSection(
                    name="Relevant Knowledge",
                    priority=4,  # Same priority as Always-On, placed right after
                    content=knowledge_block.strip(),
                    source_refs=[],
                    metadata={"source": "knowledge_store"},
                )
            )

        if recent_events:
            event_lines = []
            for event in recent_events[:6]:
                payload = event.get("payload", {})
                event_lines.append(
                    "- "
                    + " | ".join(
                        [
                            str(event.get("emitted_at", "")),
                            str(event.get("event_type", "")),
                            str(payload.get("action_name", payload.get("summary", "")))[:120],
                        ]
                    ).strip(" |")
                )
            sections.append(
                ContextSection(
                    name="Recent Session",
                    priority=5,
                    content="\n".join(event_lines),
                    source_refs=[f"session:{session.session_id}"] if session is not None else [],
                )
            )

        if recall_hits:
            recall_lines = []
            refs: list[str] = []
            for hit in recall_hits[:6]:
                refs.append(str(hit.metadata.get("source_path") or hit.record_id))
                recall_lines.append(
                    f"- [{hit.source_kind}] score={hit.score:.3f} | {hit.text[:180].replace(chr(10), ' ')}"
                )
            sections.append(
                ContextSection(
                    name="Retrieved Recall",
                    priority=6,
                    content="\n".join(recall_lines),
                    source_refs=_dedupe(refs),
                )
            )

        if palace_hits:
            palace_lines = []
            for hit in palace_hits[:5]:
                score = hit.get("score", 0.0)
                text = str(hit.get("text", ""))[:180].replace("\n", " ")
                source = hit.get("source", "palace")
                palace_lines.append(f"- [{source}] score={score:.3f} | {text}")
            sections.append(
                ContextSection(
                    name="Memory Palace",
                    priority=6,
                    content="\n".join(palace_lines),
                    source_refs=[],
                )
            )

        # Phase 7b: Semantic Context from GraphStore
        if semantic_hits:
            sem_lines = []
            for hit in semantic_hits[:5]:
                name = hit.get("name", "")
                description = str(hit.get("description", ""))[:120].replace("\n", " ")
                related = hit.get("related", [])
                loc = hit.get("code_locations", [])
                line = f"- {name}"
                if description:
                    line += f": {description}"
                if related:
                    line += f" (related: {', '.join(str(r) for r in related[:3])})"
                if loc:
                    line += f" [files: {', '.join(str(l) for l in loc[:2])}]"
                sem_lines.append(line)
            sections.append(
                ContextSection(
                    name="Semantic Context",
                    priority=6,
                    content="\n".join(sem_lines),
                    source_refs=[],
                )
            )

        if facts:
            fact_lines = []
            refs = []
            for fact in facts[:6]:
                refs.append(f"memory://{fact.fact_id}")
                fact_lines.append(
                    f"- [{fact.truth_state}] {fact.fact_kind} ({fact.confidence:.2f}) {fact.text[:180]}"
                )
            sections.append(
                ContextSection(
                    name="Durable Facts",
                    priority=7,
                    content="\n".join(fact_lines),
                    source_refs=refs,
                )
            )

        if artifacts:
            artifact_lines = []
            refs = []
            for artifact in artifacts[:6]:
                refs.extend(
                    [
                        item
                        for item in (artifact.payload_path, artifact.manifest_path)
                        if item
                    ]
                )
                payload_label = Path(artifact.payload_path).name if artifact.payload_path else "-"
                artifact_lines.append(
                    f"- [{artifact.promotion_state}] {artifact.artifact_kind} payload={payload_label}"
                )
            sections.append(
                ContextSection(
                    name="Artifacts",
                    priority=8,
                    content="\n".join(artifact_lines),
                    source_refs=_dedupe(refs),
                )
            )

        workspace_content, workspace_refs = self._workspace_section(
            workspace_root=workspace_root,
            active_paths=active_paths,
        )
        if workspace_content:
            sections.append(
                ContextSection(
                    name="Workspace",
                    priority=9,
                    content=workspace_content,
                    source_refs=workspace_refs,
                )
            )

        return sections

    def _fit_sections(
        self,
        sections: list[ContextSection],
        char_budget: int,
    ) -> tuple[str, list[ContextSection]]:
        kept: list[ContextSection] = []
        for section in sorted(sections, key=lambda item: item.priority):
            weight = self._SECTION_WEIGHTS.get(section.name, 0.08)
            header = f"## {section.name}\n"
            section_budget = max(180, int(char_budget * weight))
            content = _truncate(section.content.strip(), max(80, section_budget - len(header)))
            if not content:
                continue
            kept.append(
                ContextSection(
                    name=section.name,
                    priority=section.priority,
                    content=content,
                    source_refs=section.source_refs,
                    metadata=section.metadata,
                )
            )

        rendered = self._render(kept)
        while kept and len(rendered) > char_budget:
            last = kept[-1]
            available = max(40, len(last.content) - (len(rendered) - char_budget) - 20)
            if available < 60 and len(kept) > 1:
                kept.pop()
            else:
                kept[-1] = ContextSection(
                    name=last.name,
                    priority=last.priority,
                    content=_truncate(last.content, available),
                    source_refs=last.source_refs,
                    metadata=last.metadata,
                )
            rendered = self._render(kept)
        return rendered, kept

    def _render(self, sections: list[ContextSection]) -> str:
        parts = ["# DGC Context Bundle"]
        for section in sections:
            parts.append(f"\n## {section.name}\n{section.content}")
        return "\n".join(parts).strip()

    def _search_semantic_graph(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the GraphStore's semantic graph for concepts related to query.

        Returns list of dicts with name, definition, related concepts,
        and code locations from bridges.
        """
        if self.graph_store is None:
            return []

        results: list[dict[str, Any]] = []
        try:
            nodes = self.graph_store.search_nodes("semantic", query, limit=limit)
        except Exception:
            return []

        for node in nodes[:limit]:
            entry: dict[str, Any] = {
                "name": node.get("name", ""),
                "definition": "",
                "related": [],
                "code_locations": [],
            }
            data = node.get("data", {})
            if isinstance(data, dict):
                entry["definition"] = data.get("definition", "")[:200]

            # Get related concepts via edges
            try:
                edges = self.graph_store.get_edges(
                    "semantic", node["id"], direction="out"
                )
                for edge in edges[:5]:
                    target = self.graph_store.get_node("semantic", edge["target_id"])
                    if target:
                        entry["related"].append(target.get("name", edge["target_id"]))
            except Exception:
                pass

            # Get code locations via bridges
            try:
                bridges = self.graph_store.get_bridges(
                    target_graph="semantic", target_id=node["id"]
                )
                for bridge in bridges[:3]:
                    src_id = bridge.get("source_id", "")
                    if src_id.startswith("file::"):
                        entry["code_locations"].append(src_id.removeprefix("file::"))
            except Exception:
                pass

            results.append(entry)
        return results

    def _workspace_section(
        self,
        *,
        workspace_root: Path | None,
        active_paths: list[Path],
    ) -> tuple[str, list[str]]:
        refs: list[str] = []
        lines: list[str] = []

        candidates: list[Path] = []
        if active_paths:
            candidates.extend(active_paths)
        elif workspace_root and workspace_root.exists():
            files = [path for path in workspace_root.rglob("*") if path.is_file()]
            files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            candidates.extend(files[:6])

        for path in candidates[:6]:
            try:
                refs.append(str(path))
                snippet = path.read_text(errors="ignore")[:180].replace("\n", " ")
            except Exception:
                snippet = ""
            lines.append(f"- {path.name}: {snippet}")

        return ("\n".join(lines), _dedupe(refs))

    # ── Sprint 2: Knowledge-centric retrieval ────────────────────────

    def _retrieve_knowledge_block(self, task_description: str) -> str:
        """Retrieve and format a knowledge block from KnowledgeStore.

        Extracts concepts from the task description (algorithmically, not via LLM)
        and retrieves relevant propositions and prescriptions.
        """
        if self.knowledge_store is None or not task_description.strip():
            return ""

        import os as _os
        max_tokens = int(_os.getenv("KNOWLEDGE_MAX_TOKENS", "500"))

        # Extract concepts algorithmically (no LLM needed at query time)
        task_concepts = self._extract_concepts_simple(task_description)
        if not task_concepts:
            return ""

        props = self.knowledge_store.get_propositions_for_context(
            task_concepts, max_tokens=max_tokens
        )
        prescs = self.knowledge_store.get_prescriptions_for_intent(
            task_description, task_concepts
        )

        return self._format_knowledge_block(props, prescs)

    @staticmethod
    def _extract_concepts_simple(text: str) -> list[str]:
        """Extract concepts from text using simple keyword extraction.

        No LLM needed — uses stopword filtering + frequency heuristic.
        """
        _STOPWORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "because",
            "but", "and", "or", "if", "while", "about", "up", "this",
            "that", "these", "those", "it", "its", "i", "me", "my", "we",
            "our", "you", "your", "he", "she", "they", "them", "what",
            "which", "who", "whom", "make", "need", "use", "get", "set",
        }
        words = text.lower().split()
        # Filter stopwords and short words
        candidates = [w.strip(".,;:!?()[]{}\"'") for w in words]
        candidates = [w for w in candidates if w and len(w) > 2 and w not in _STOPWORDS]
        # Deduplicate while preserving order
        seen: set[str] = set()
        concepts: list[str] = []
        for w in candidates:
            if w not in seen:
                seen.add(w)
                concepts.append(w)
        return concepts[:7]

    @staticmethod
    def _format_knowledge_block(
        propositions: list[Any],
        prescriptions: list[Any],
    ) -> str:
        """Format knowledge units into a context block.

        Example output:
        ### Facts
        - GPT-4 achieves 86.4% on MMLU [confidence: 0.92]

        ### Applicable Skills
        **Debug a failing pytest test** (success rate: 85%)
        1. Read the error traceback
        2. Locate the failing assertion
        """
        if not propositions and not prescriptions:
            return ""

        parts: list[str] = []

        if propositions:
            parts.append("### Facts")
            for prop in propositions:
                conf = getattr(prop, "confidence", 1.0)
                content = getattr(prop, "content", str(prop))
                parts.append(f"- {content} [confidence: {conf:.2f}]")

        if prescriptions:
            if parts:
                parts.append("")
            parts.append("### Applicable Skills")
            for presc in prescriptions:
                intent = getattr(presc, "intent", str(presc))
                score = getattr(presc, "return_score", 0.0)
                workflow = getattr(presc, "workflow", [])
                parts.append(f"**{intent}** (success rate: {int(score * 100)}%)")
                for i, step in enumerate(workflow[:6], 1):
                    parts.append(f"  {i}. {step}")

        return "\n".join(parts)

    # ── Phase 7b: Semantic Graph integration ─────────────────────────

    def _query_semantic_graph(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Query the GraphStore's semantic graph for task-relevant concepts.

        Returns a list of dicts with:
            name, description, related (list of concept names),
            code_locations (list of file paths from code↔semantic bridges)
        """
        if self.graph_store is None or not query.strip():
            return []

        results: list[dict[str, Any]] = []
        try:
            nodes = self.graph_store.search_nodes("semantic", query, limit=limit)
            for node in nodes:
                node_id = node.get("id", "")
                name = node.get("name", "")
                data = node.get("data", {})
                if isinstance(data, str):
                    try:
                        import json as _json
                        data = _json.loads(data)
                    except Exception:
                        data = {}
                description = data.get("description", "")

                # Get related concepts (edges in semantic graph)
                related_names: list[str] = []
                try:
                    edges = self.graph_store.get_edges("semantic", node_id)
                    for edge in edges[:5]:
                        target_id = edge.get("target_id", "")
                        if target_id and target_id != node_id:
                            target = self.graph_store.get_node("semantic", target_id)
                            if target:
                                related_names.append(target.get("name", target_id))
                        source_id = edge.get("source_id", "")
                        if source_id and source_id != node_id:
                            source = self.graph_store.get_node("semantic", source_id)
                            if source:
                                related_names.append(source.get("name", source_id))
                except Exception:
                    pass

                # Get code locations (bridges from code to this concept)
                code_locations: list[str] = []
                try:
                    bridges = self.graph_store.get_bridges(
                        target_graph="semantic", target_id=node_id, limit=3
                    )
                    for br in bridges:
                        src_id = br.get("source_id", "")
                        if "::" in src_id:
                            # format: filepath::line
                            code_locations.append(src_id.split("::")[0])
                        elif src_id:
                            code_locations.append(src_id)
                except Exception:
                    pass

                results.append({
                    "name": name,
                    "description": description,
                    "related": related_names[:3],
                    "code_locations": code_locations[:2],
                })
        except Exception as exc:
            logger.debug("Semantic graph query failed: %s", exc)

        return results
