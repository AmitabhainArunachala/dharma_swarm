"""Runtime bridge for governed local and external agent runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim
from dharma_swarm.dharma_kernel import DharmaKernel
from dharma_swarm.models import _new_id
from dharma_swarm.orientation_packet import (
    DirectiveSummary,
    OrientationPacket,
    OrientationPacketBuilder,
    RuntimeStateSummary,
)
from dharma_swarm.semantic_governance import ActionEnvelope, GovernanceVerdict, SemanticGovernanceKernel


class RuntimeDescriptor(BaseModel):
    runtime_id: str = Field(default_factory=_new_id)
    name: str
    runtime_type: str
    capabilities: list[str] = Field(default_factory=list)


class RuntimeAdapter(ABC):
    descriptor: RuntimeDescriptor

    @abstractmethod
    def normalize_action(self, payload: object) -> ActionEnvelope:
        raise NotImplementedError


class RuntimeBridge:
    """Registry and bridge layer for governed runtimes."""

    def __init__(
        self,
        *,
        kernel: SemanticGovernanceKernel | None = None,
        orientation_builder: OrientationPacketBuilder | None = None,
    ) -> None:
        self.kernel = kernel or SemanticGovernanceKernel()
        self.orientation_builder = orientation_builder or OrientationPacketBuilder()
        self._adapters: dict[str, RuntimeAdapter] = {}

    def register(self, adapter: RuntimeAdapter) -> RuntimeDescriptor:
        self._adapters[adapter.descriptor.runtime_id] = adapter
        return adapter.descriptor

    def get(self, runtime_id: str) -> RuntimeAdapter:
        return self._adapters[runtime_id]

    def list_descriptors(self) -> list[RuntimeDescriptor]:
        return [adapter.descriptor for adapter in self._adapters.values()]

    def issue_orientation(
        self,
        runtime_id: str,
        *,
        role: str,
        kernel: DharmaKernel,
        claims: list[Claim],
        contradictions: list[Contradiction] | None = None,
        directives: list[DirectiveSummary | dict] | None = None,
        runtime_state: RuntimeStateSummary | dict | None = None,
        role_context: str = "",
        task: str | None = None,
        provenance: list[str] | None = None,
    ) -> OrientationPacket:
        adapter = self.get(runtime_id)
        packet = self.orientation_builder.build(
            role=role,
            kernel=kernel,
            claims=claims,
            contradictions=contradictions,
            directives=directives,
            runtime_state=runtime_state,
            role_context=role_context,
            task=task,
            provenance=(provenance or []) + [f"runtime:{adapter.descriptor.runtime_id}"],
        )
        return packet

    def govern_action(
        self,
        runtime_id: str,
        payload: object,
        *,
        claims: list[Claim],
    ) -> tuple[ActionEnvelope, GovernanceVerdict]:
        adapter = self.get(runtime_id)
        envelope = adapter.normalize_action(payload)
        verdict = self.kernel.evaluate_action(envelope, claims)
        return envelope, verdict
