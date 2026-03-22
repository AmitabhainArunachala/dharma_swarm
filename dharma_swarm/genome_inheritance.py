"""Genome Inheritance -- what a child agent receives from its parent.

Five layers of inheritance:
1. KERNEL (immutable): 25 MetaPrinciples, SHA-256 verified
2. GATES (immutable): 11 core telos gates
3. PROMPT (differentiated): Parent's prompt + role specialization
4. MEMORY (selective): Domain-filtered parent memory
5. IDENTITY (new): Unique name, role, model, schedule

Biological analogy: kernel = nuclear DNA (never mutates),
gates = immune checkpoint (always inherited),
prompt = epigenetics (modified by environment),
memory = maternal antibodies (selective transfer).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dharma_swarm.agent_constitution import AgentSpec
    from dharma_swarm.dharma_kernel import DharmaKernel

logger = logging.getLogger(__name__)


@dataclass
class GenomeTemplate:
    """The complete genome a child will receive.

    This is the full provenance record: who the parent was, what generation
    the child belongs to, what was inherited, and what was differentiated.
    Persisted to ~/.dharma/replication/genomes/{child_name}.json for audit.
    """

    parent_name: str
    parent_generation: int
    child_name: str
    child_generation: int
    kernel_signature: str  # SHA-256 of inherited kernel
    inherited_gates: list[str]  # Gate names
    system_prompt: str  # Differentiated prompt
    inherited_corpus_claims: list[dict[str, Any]]  # Filtered claims
    inherited_memory_keys: list[str]  # Memory entries to copy
    role_specialization: str  # What makes child different
    model: str
    provider: str
    wake_interval_seconds: float
    spawn_authority: list[str]  # Worker types child can spawn
    metadata: dict[str, Any] = field(default_factory=dict)


class GenomeInheritance:
    """Composes a child AgentSpec from parent + differentiation proposal.

    The core operation is compose_child_spec(), which takes a parent AgentSpec,
    a description of the capability gap, and a spec delta (model, provider,
    prompt additions), then produces:
      - A new AgentSpec for the child (frozen, ready for DynamicRoster.add)
      - A GenomeTemplate with full provenance for audit
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"

    async def compose_child_spec(
        self,
        parent_spec: AgentSpec,
        parent_generation: int,
        capability_gap: str,
        proposed_role: str,
        proposed_spec_delta: dict[str, Any],
        kernel: DharmaKernel,
    ) -> tuple[AgentSpec, GenomeTemplate]:
        """Create a child AgentSpec from parent + differentiation.

        Args:
            parent_spec: The parent's frozen AgentSpec.
            parent_generation: Parent's generation number (0 for founding agents).
            capability_gap: Description of what capability is missing.
            proposed_role: Human-readable name for the new role.
            proposed_spec_delta: Dict with optional keys:
                - domain: str -- child's domain description
                - prompt_suffix: str -- appended to differentiated prompt
                - model: str -- LLM model identifier
                - provider: str -- ProviderType value string
                - wake_interval: float -- seconds between wake cycles
                - spawn_authority: list[str] -- worker types child can spawn
            kernel: The DharmaKernel to inherit (integrity verified before calling).

        Returns:
            Tuple of (child AgentSpec, GenomeTemplate with full provenance).

        Raises:
            ValueError: If kernel integrity check fails.
        """
        if not kernel.verify_integrity():
            raise ValueError("Kernel integrity check failed -- cannot inherit corrupted kernel")

        child_generation = parent_generation + 1
        child_name = self._generate_name(proposed_role, child_generation)

        # Build differentiated system prompt
        system_prompt = self._differentiate_prompt(
            parent_spec.system_prompt,
            capability_gap,
            proposed_spec_delta.get("prompt_suffix", ""),
            proposed_spec_delta.get("domain", ""),
        )

        # Determine model (use delta if provided, else parent's)
        model = proposed_spec_delta.get("model", parent_spec.default_model)

        # Determine provider (use delta if provided, else parent's)
        from dharma_swarm.models import ProviderType

        provider_str = proposed_spec_delta.get("provider", parent_spec.default_provider.value)
        try:
            provider_type = ProviderType(provider_str)
        except ValueError:
            provider_type = parent_spec.default_provider

        # Inherit parent's gates (all core gates are always inherited)
        inherited_gates = list(parent_spec.constitutional_gates)

        # Determine spawn authority (scoped to child's domain)
        spawn_authority = proposed_spec_delta.get(
            "spawn_authority",
            [f"{proposed_role.lower().replace(' ', '_')}_worker", "research_worker"],
        )

        # Filter parent's memory for relevant entries
        inherited_memory_keys = await self._filter_parent_memory(
            parent_spec.name,
            proposed_spec_delta.get("domain", capability_gap),
        )

        # Domain for child
        domain = proposed_spec_delta.get("domain", f"Replicated from {parent_spec.name}: {capability_gap[:80]}")

        # Build the genome template (full provenance record)
        genome = GenomeTemplate(
            parent_name=parent_spec.name,
            parent_generation=parent_generation,
            child_name=child_name,
            child_generation=child_generation,
            kernel_signature=kernel.compute_signature(),
            inherited_gates=inherited_gates,
            system_prompt=system_prompt,
            inherited_corpus_claims=[],  # Populated by caller if needed
            inherited_memory_keys=inherited_memory_keys,
            role_specialization=capability_gap,
            model=model,
            provider=provider_type.value,
            wake_interval_seconds=proposed_spec_delta.get("wake_interval", 3600.0),
            spawn_authority=spawn_authority,
            metadata={
                "born_at": datetime.now(timezone.utc).isoformat(),
                "parent_spec_name": parent_spec.name,
                "capability_gap": capability_gap,
            },
        )

        # Build the child AgentSpec
        from dharma_swarm.agent_constitution import AgentSpec, ConstitutionalLayer

        child_spec = AgentSpec(
            name=child_name,
            role=parent_spec.role,  # Same role enum, different specialization
            layer=ConstitutionalLayer.DIRECTOR,  # Replicated agents are DIRECTOR tier
            vsm_function=f"Replicated from {parent_spec.name} for: {capability_gap[:80]}",
            domain=domain,
            system_prompt=system_prompt,
            default_provider=provider_type,
            default_model=model,
            backup_models=list(parent_spec.backup_models),
            constitutional_gates=inherited_gates,
            max_concurrent_workers=3,  # Conservative for new agents
            memory_namespace=child_name,
            spawn_authority=spawn_authority,
            audit_cycle_seconds=0.0,  # Not an AUDIT layer agent
            metadata={
                "parent": parent_spec.name,
                "generation": child_generation,
                "capability_gap": capability_gap[:200],
            },
        )

        # Save genome provenance
        self._save_genome(genome)

        return child_spec, genome

    def _generate_name(self, proposed_role: str, generation: int) -> str:
        """Generate unique name for child agent.

        Format: {sanitized_role}_g{generation}_{YYYYMMDD}
        """
        clean = re.sub(r"[^a-z0-9_]", "_", proposed_role.lower().strip())
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "agent"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{clean}_g{generation}_{timestamp}"

    def _differentiate_prompt(
        self,
        parent_prompt: str,
        capability_gap: str,
        prompt_suffix: str,
        domain: str,
    ) -> str:
        """Build child's system prompt from parent's + specialization.

        The parent prompt forms the base identity. The capability gap and
        domain-specific suffix differentiate the child's focus.
        """
        parts = [parent_prompt]
        section_header = f"\n\n## Specialization ({domain})" if domain else "\n\n## Specialization"
        parts.append(section_header)
        parts.append(f"You were created to fill a capability gap: {capability_gap}")
        if prompt_suffix:
            parts.append(f"\n{prompt_suffix}")
        parts.append("\nYou inherit all kernel axioms and telos gates from your parent.")
        parts.append("Your actions are monitored during probation.")
        return "\n".join(parts)

    async def _filter_parent_memory(
        self, parent_name: str, domain: str
    ) -> list[str]:
        """Get memory keys from parent relevant to child's domain.

        Loads the parent's AgentMemoryBank from disk and filters all three
        tiers (working, archival, persona) by keyword overlap with the domain.
        Returns at most 20 keys.
        """
        try:
            from dharma_swarm.agent_memory import AgentMemoryBank

            bank = AgentMemoryBank(
                agent_name=parent_name,
                base_path=self._state_dir / "agent_memory",
            )
            await bank.load()

            domain_lower = domain.lower()
            domain_keywords = set(domain_lower.split())
            relevant: list[str] = []

            # Scan all three tiers
            for tier_dict in (bank._working, bank._archival, bank._persona):
                for key, entry in tier_dict.items():
                    text = f"{key} {entry.value}".lower()
                    if domain_lower in text or any(kw in text for kw in domain_keywords):
                        relevant.append(key)

            return relevant[:20]  # Cap at 20 entries
        except Exception:
            logger.debug(
                "Failed to filter parent memory for %s", parent_name, exc_info=True,
            )
            return []

    def _save_genome(self, genome: GenomeTemplate) -> None:
        """Persist genome provenance to disk.

        Writes to ~/.dharma/replication/genomes/{child_name}.json.
        Uses atomic write (tmp + replace) to prevent partial writes.
        """
        genome_dir = self._state_dir / "replication" / "genomes"
        genome_dir.mkdir(parents=True, exist_ok=True)
        path = genome_dir / f"{genome.child_name}.json"
        tmp = path.with_suffix(".tmp")

        data = dataclasses.asdict(genome)
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def load_genome(self, child_name: str) -> GenomeTemplate | None:
        """Load a previously saved genome by child name.

        Returns None if the genome file does not exist.
        """
        path = self._state_dir / "replication" / "genomes" / f"{child_name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return GenomeTemplate(**data)
        except Exception:
            logger.warning("Failed to load genome for %s", child_name, exc_info=True)
            return None
