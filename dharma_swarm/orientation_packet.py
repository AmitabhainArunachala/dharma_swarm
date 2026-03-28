"""Typed orientation packet for agent initialization."""

from __future__ import annotations

from typing import Iterable, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim, ClaimCategory
from dharma_swarm.dharma_kernel import DharmaKernel, PrincipleSpec
from dharma_swarm.models import AgentRole, _new_id, _utc_now


class KernelAxiomSummary(BaseModel):
    principle_id: str
    name: str
    severity: str
    description: str
    formal_constraint: str


class DirectiveSummary(BaseModel):
    directive_id: str
    title: str
    summary: str
    source_ref: str = ""
    priority: str = "normal"


class RuntimeStateSummary(BaseModel):
    mode: str = "unknown"
    active_tasks: int = 0
    running_agents: int = 0
    pending_tasks: int = 0
    status_notes: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class OrientationPacket(BaseModel):
    packet_id: str = Field(default_factory=_new_id)
    role: str
    task: str | None = None
    kernel_axioms: list[KernelAxiomSummary] = Field(default_factory=list)
    active_claims: list[Claim] = Field(default_factory=list)
    active_contradictions: list[Contradiction] = Field(default_factory=list)
    active_directives: list[DirectiveSummary] = Field(default_factory=list)
    runtime_state_summary: RuntimeStateSummary = Field(default_factory=RuntimeStateSummary)
    role_context: str = ""
    provenance: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: _utc_now().isoformat())


_ROLE_LIMITS: dict[str, tuple[int, int]] = {
    AgentRole.OPERATOR.value: (10, 10),
    AgentRole.RESEARCHER.value: (8, 8),
    AgentRole.RESEARCH_DIRECTOR.value: (8, 8),
    AgentRole.CODER.value: (6, 6),
    AgentRole.WORKER.value: (5, 5),
    AgentRole.WITNESS.value: (6, 7),
    AgentRole.GENERAL.value: (6, 6),
}

_ROLE_CATEGORY_PREFS: dict[str, list[ClaimCategory]] = {
    AgentRole.OPERATOR.value: [
        ClaimCategory.SAFETY,
        ClaimCategory.ARCHITECTURAL,
        ClaimCategory.OPERATIONAL,
        ClaimCategory.ETHICS,
    ],
    AgentRole.RESEARCHER.value: [
        ClaimCategory.THEORETICAL,
        ClaimCategory.EMPIRICAL,
        ClaimCategory.CONTEMPLATIVE,
        ClaimCategory.ARCHITECTURAL,
    ],
    AgentRole.WORKER.value: [
        ClaimCategory.OPERATIONAL,
        ClaimCategory.ARCHITECTURAL,
        ClaimCategory.SAFETY,
    ],
}


def _summarize_axioms(principles: dict[str, PrincipleSpec]) -> list[KernelAxiomSummary]:
    summaries = [
        KernelAxiomSummary(
            principle_id=principle_id,
            name=spec.name,
            severity=spec.severity,
            description=spec.description,
            formal_constraint=spec.formal_constraint,
        )
        for principle_id, spec in principles.items()
    ]
    summaries.sort(key=lambda item: (item.severity != "critical", item.name))
    return summaries


def _category_rank(role: str, category: ClaimCategory) -> tuple[int, str]:
    preferences = _ROLE_CATEGORY_PREFS.get(role, [])
    try:
        return (preferences.index(category), str(category))
    except ValueError:
        return (len(preferences), str(category))


class OrientationPacketBuilder:
    """Build role-aware orientation packets from kernel, claims, and directives."""

    def build(
        self,
        *,
        role: str,
        kernel: DharmaKernel,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction] | None = None,
        directives: Iterable[DirectiveSummary | dict] | None = None,
        runtime_state: RuntimeStateSummary | dict | None = None,
        role_context: str = "",
        task: str | None = None,
        provenance: Sequence[str] | None = None,
        stale_sources: Sequence[str] | None = None,
    ) -> OrientationPacket:
        role_value = role or AgentRole.GENERAL.value
        axiom_limit, claim_limit = _ROLE_LIMITS.get(role_value, _ROLE_LIMITS[AgentRole.GENERAL.value])

        axioms = _summarize_axioms(kernel.principles)[:axiom_limit]

        sorted_claims = sorted(
            claims,
            key=lambda claim: (_category_rank(role_value, claim.category), -claim.confidence, claim.id),
        )
        selected_claims = sorted_claims[:claim_limit]

        selected_claim_ids = {claim.id for claim in selected_claims}
        selected_contradictions = [
            contradiction
            for contradiction in (contradictions or [])
            if selected_claim_ids.intersection(contradiction.claim_ids)
        ]

        normalized_directives = [
            directive if isinstance(directive, DirectiveSummary) else DirectiveSummary.model_validate(directive)
            for directive in (directives or [])
        ]

        normalized_runtime = (
            runtime_state
            if isinstance(runtime_state, RuntimeStateSummary)
            else RuntimeStateSummary.model_validate(runtime_state or {})
        )

        packet_provenance = list(provenance or [])
        packet_provenance.extend(f"kernel:{axiom.principle_id}" for axiom in axioms)
        packet_provenance.extend(f"claim:{claim.id}" for claim in selected_claims)

        return OrientationPacket(
            role=role_value,
            task=task,
            kernel_axioms=axioms,
            active_claims=selected_claims,
            active_contradictions=selected_contradictions,
            active_directives=normalized_directives,
            runtime_state_summary=normalized_runtime,
            role_context=role_context,
            provenance=sorted(set(packet_provenance)),
            stale_sources=list(stale_sources or []),
        )

    def render_text(self, packet: OrientationPacket) -> str:
        lines: list[str] = [
            f"Role: {packet.role}",
            f"Task: {packet.task or 'unspecified'}",
            "",
            "Kernel axioms:",
        ]
        for axiom in packet.kernel_axioms:
            lines.append(f"- {axiom.name} [{axiom.severity}] :: {axiom.formal_constraint}")

        lines.extend(["", "Active claims:"])
        for claim in packet.active_claims:
            lines.append(f"- {claim.id} [{claim.category}] ({claim.confidence:.2f}) :: {claim.statement}")

        if packet.active_contradictions:
            lines.extend(["", "Active contradictions:"])
            for contradiction in packet.active_contradictions:
                lines.append(f"- {contradiction.contradiction_id} :: {', '.join(contradiction.claim_ids)}")

        if packet.active_directives:
            lines.extend(["", "Active directives:"])
            for directive in packet.active_directives:
                lines.append(f"- {directive.title} [{directive.priority}] :: {directive.summary}")

        if packet.role_context:
            lines.extend(["", "Role context:", packet.role_context])

        lines.extend(
            [
                "",
                "Runtime state:",
                f"- mode={packet.runtime_state_summary.mode}",
                f"- active_tasks={packet.runtime_state_summary.active_tasks}",
                f"- running_agents={packet.runtime_state_summary.running_agents}",
                f"- pending_tasks={packet.runtime_state_summary.pending_tasks}",
            ]
        )

        if packet.stale_sources:
            lines.extend(["", "Stale sources:", *[f"- {source}" for source in packet.stale_sources]])

        return "\n".join(lines)
