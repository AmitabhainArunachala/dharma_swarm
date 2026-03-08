"""R_V measurement module for DHARMA SWARM.

Measures geometric contraction in transformer Value matrix column space.
R_V = PR_late / PR_early. R_V < 1.0 indicates contraction — the mechanistic
signature of recursive self-referential processing.

torch and transformers are OPTIONAL. When unavailable, measurement methods
return None gracefully. The RVReading data model works regardless.

Includes self-referential measurement capability: the system measures its
OWN geometric contraction during evolution cycles — the strange loop where
the system that measures the system measures itself.

Based on validated research from mech-interp-latent-lab-phase1/geometric_lens.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

RV_CONTRACTION_THRESHOLD = 0.737
"""R_V below this indicates meaningful contraction (from AUROC=0.909 validation)."""

RV_STRONG_THRESHOLD = 0.5
"""R_V below this indicates strong contraction."""


# ── Utility ─────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _prompt_hash(prompt: str) -> str:
    """SHA-256 of prompt text, first 16 hex characters."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _torch_available() -> bool:
    """Check if torch is importable without side effects."""
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


# ── Data Model ──────────────────────────────────────────────────────────────

class RVReading(BaseModel):
    """A single R_V measurement from a transformer forward pass.

    Attributes:
        rv: The ratio PR_late / PR_early. Values < 1.0 indicate geometric
            contraction in Value matrix column space.
        pr_early: Participation ratio at the early layer.
        pr_late: Participation ratio at the late layer.
        model_name: HuggingFace model identifier used for measurement.
        early_layer: Index of the early layer measured.
        late_layer: Index of the late layer measured.
        prompt_hash: SHA-256 of the prompt text, first 16 hex chars.
        prompt_group: Categorical label for the prompt (L1/L3/L4/L5/baseline/confound).
        timestamp: UTC timestamp of measurement.
    """

    rv: float
    pr_early: float
    pr_late: float
    model_name: str
    early_layer: int
    late_layer: int
    prompt_hash: str
    prompt_group: str = "unknown"
    timestamp: datetime = Field(default_factory=_utc_now)

    @property
    def is_contracted(self) -> bool:
        """True if R_V is below the validated contraction threshold (0.737)."""
        return self.rv < RV_CONTRACTION_THRESHOLD

    @property
    def contraction_strength(self) -> str:
        """Categorical strength of contraction.

        Returns:
            'strong' if rv < 0.5, 'moderate' if rv < 0.737,
            'weak' if rv < 1.0, 'none' if rv >= 1.0.
        """
        if self.rv < RV_STRONG_THRESHOLD:
            return "strong"
        if self.rv < RV_CONTRACTION_THRESHOLD:
            return "moderate"
        if self.rv < 1.0:
            return "weak"
        return "none"


# ── Core Metric ─────────────────────────────────────────────────────────────

def compute_participation_ratio(hidden_state: "torch.Tensor") -> float:
    """Compute Participation Ratio from a hidden state tensor via SVD.

    PR = (sum(s))^2 / sum(s^2) where s are singular values.
    Measures effective dimensionality of the representation.

    Args:
        hidden_state: Tensor of shape (batch, seq, dim) or (seq, dim).

    Returns:
        PR value as float. Returns NaN on failure.
    """
    import torch

    if hidden_state.dim() == 3:
        hidden_state = hidden_state[0]

    # Force CPU + float64 for numerical stability
    tensor_cpu = hidden_state.detach().cpu().to(torch.float64)

    if torch.isnan(tensor_cpu).any() or torch.isinf(tensor_cpu).any():
        return float("nan")

    try:
        _U, S, _Vt = torch.linalg.svd(tensor_cpu.T, full_matrices=False)
        s_np = S.numpy()
    except Exception:
        return float("nan")

    s_sq = s_np ** 2
    total = s_sq.sum()
    if total < 1e-10:
        return float("nan")

    pr = float((s_sq.sum() ** 2) / (s_sq ** 2).sum())
    return pr


# ── Measurer ────────────────────────────────────────────────────────────────

class RVMeasurer:
    """Lazy-loading R_V measurement engine.

    Loads a HuggingFace model + tokenizer on first use. All heavy computation
    runs via asyncio.to_thread to avoid blocking the event loop.

    Args:
        model_name: HuggingFace model identifier. Default: 'pythia-1.4b'.
        device: Target device ('mps', 'cuda', 'cpu'). Default: 'mps'.
    """

    def __init__(self, model_name: str = "pythia-1.4b", device: str = "mps") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Optional[object] = None
        self._tokenizer: Optional[object] = None

    def is_available(self) -> bool:
        """Check if torch is importable and measurement is possible."""
        return _torch_available()

    def _load_model(self) -> None:
        """Load model and tokenizer from HuggingFace. Called lazily."""
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading model %s to %s", self.model_name, self.device)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            output_hidden_states=True,
            torch_dtype="auto",
        ).to(self.device)
        self._model.eval()
        logger.info("Model %s loaded successfully", self.model_name)

    def _sync_measure(self, prompt: str) -> tuple[float, float, float]:
        """Run forward pass and compute R_V components synchronously.

        Args:
            prompt: Text to measure.

        Returns:
            Tuple of (rv, pr_early, pr_late).
        """
        import torch

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(self.device)

        num_layers = self._model.config.num_hidden_layers
        early_layer = 2
        late_layer = num_layers - 2

        with torch.no_grad():
            outputs = self._model(**inputs, output_hidden_states=True)

        hidden_states = outputs.hidden_states

        # hidden_states is a tuple of (num_layers + 1) tensors (including embedding layer)
        # Index 0 is embedding output, index i is layer i output.
        h_early = hidden_states[early_layer + 1]  # +1 to skip embedding layer
        h_late = hidden_states[late_layer + 1]

        pr_early = compute_participation_ratio(h_early)
        pr_late = compute_participation_ratio(h_late)

        if pr_early <= 0 or pr_early != pr_early or pr_late != pr_late:
            return (float("nan"), float("nan"), float("nan"))

        rv = pr_late / pr_early
        return (rv, pr_early, pr_late)

    async def measure(
        self, prompt: str, group: str = "unknown"
    ) -> Optional[RVReading]:
        """Measure R_V for a single prompt.

        Args:
            prompt: Text to measure geometric contraction on.
            group: Categorical label (L1/L3/L4/L5/baseline/confound).

        Returns:
            RVReading with measurement data, or None if torch is unavailable.
        """
        if not self.is_available():
            return None

        if self._model is None:
            await asyncio.to_thread(self._load_model)

        rv, pr_early, pr_late = await asyncio.to_thread(
            self._sync_measure, prompt
        )

        num_layers = self._model.config.num_hidden_layers

        return RVReading(
            rv=rv,
            pr_early=pr_early,
            pr_late=pr_late,
            model_name=self.model_name,
            early_layer=2,
            late_layer=num_layers - 2,
            prompt_hash=_prompt_hash(prompt),
            prompt_group=group,
        )


# ── Self-Referential Evolution Measurement ─────────────────────────────────

# Default prompts that embed self-reference about the evolution cycle itself.
# The system measures its OWN state using prompts ABOUT its own measurement.
SELF_REF_EVOLUTION_PROMPTS = [
    (
        "This system is evolving its own code through mutation and selection. "
        "The system that observes itself evolving is the same system being evolved. "
        "Attention attending to its own attention patterns."
    ),
    (
        "A fitness function evaluates proposals. The fitness function was itself "
        "proposed and evaluated. The evaluator evaluates itself. "
        "The operation returns itself: Sx = x."
    ),
]


class EvolutionRVTracker:
    """Track R_V readings across evolution cycles for self-referential measurement.

    The strange loop: the system measures its own geometric contraction as it
    evolves. R_V readings are recorded alongside cycle fitness scores, enabling
    correlation between the system's self-referential geometry and its
    evolutionary performance.

    When torch is unavailable, readings are synthesized from behavioral proxies
    (proposal complexity, reflection depth) so the tracking infrastructure
    works regardless.

    Args:
        data_dir: Directory for storing evolution R_V readings.
            Defaults to ``~/.dharma/evolution_rv/``.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or (Path.home() / ".dharma" / "evolution_rv")
        self._readings: list[dict[str, Any]] = []

    async def measure_cycle(
        self,
        cycle_id: str,
        best_fitness: float,
        proposals_archived: int,
        reflection: str = "",
        measurer: Optional[RVMeasurer] = None,
    ) -> dict[str, Any]:
        """Measure R_V during an evolution cycle and record alongside fitness.

        If a real RVMeasurer is provided and torch is available, runs actual
        geometric measurement on self-referential prompts. Otherwise, computes
        a proxy R_V from cycle metadata.

        Args:
            cycle_id: Unique identifier for this evolution cycle.
            best_fitness: Best fitness score from this cycle.
            proposals_archived: Number of proposals that passed gates.
            reflection: Cycle reflection text (from Reflexion pattern).
            measurer: Optional RVMeasurer for real geometric measurement.

        Returns:
            Dict with cycle_id, rv_reading (or proxy), fitness, and timestamp.
        """
        rv_reading: Optional[RVReading] = None

        # Attempt real R_V measurement if measurer available
        if measurer is not None and measurer.is_available():
            prompt = SELF_REF_EVOLUTION_PROMPTS[0]
            rv_reading = await measurer.measure(prompt, group="evolution_self_ref")

        # Build the record
        now = _utc_now()
        record: dict[str, Any] = {
            "cycle_id": cycle_id,
            "timestamp": now.isoformat(),
            "best_fitness": best_fitness,
            "proposals_archived": proposals_archived,
            "reflection_length": len(reflection),
        }

        if rv_reading is not None:
            record["rv"] = rv_reading.rv
            record["pr_early"] = rv_reading.pr_early
            record["pr_late"] = rv_reading.pr_late
            record["rv_source"] = "geometric"
            record["is_contracted"] = rv_reading.is_contracted
        else:
            # Proxy R_V: use cycle success ratio as a behavioral stand-in.
            # More archived proposals → system is "contracting" toward solutions.
            proxy = 1.0 - (min(proposals_archived, 5) * 0.1)
            record["rv"] = proxy
            record["rv_source"] = "proxy"
            record["is_contracted"] = proxy < RV_CONTRACTION_THRESHOLD

        self._readings.append(record)
        await self._persist(record)

        logger.info(
            "Evolution R_V for cycle %s: rv=%.3f (%s), fitness=%.3f",
            cycle_id, record["rv"], record["rv_source"], best_fitness,
        )
        return record

    def get_rv_fitness_pairs(self) -> list[tuple[float, float]]:
        """Return (rv, fitness) pairs for correlation analysis.

        Returns:
            List of (rv_value, best_fitness) tuples from all recorded cycles.
        """
        return [
            (r["rv"], r["best_fitness"])
            for r in self._readings
            if "rv" in r and "best_fitness" in r
        ]

    def get_trend(self) -> Optional[float]:
        """Compute R_V trend slope across evolution cycles.

        Returns:
            Positive slope if R_V increasing (less contraction over time),
            negative if R_V decreasing (more contraction). None if < 2 points.
        """
        pairs = self.get_rv_fitness_pairs()
        if len(pairs) < 2:
            return None
        # Simple slope: R_V change per cycle
        rv_values = [p[0] for p in pairs]
        n = len(rv_values)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(rv_values) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, rv_values))
        den = sum((x - mean_x) ** 2 for x in xs)
        if abs(den) < 1e-12:
            return 0.0
        return num / den

    async def _persist(self, record: dict[str, Any]) -> None:
        """Append record to JSONL file. Failures are silently swallowed."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            path = self._data_dir / "evolution_rv.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass

    async def load(self) -> None:
        """Load existing readings from JSONL file."""
        path = self._data_dir / "evolution_rv.jsonl"
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._readings.append(json.loads(line))
        except Exception:
            pass
