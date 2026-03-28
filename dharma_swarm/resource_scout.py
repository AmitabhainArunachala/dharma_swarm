"""Resource scout for GPU compute procurement.

Scans providers for cheapest available GPU time. Budget-aware — only
recommends instances the system can afford. Integrates with EconomicEngine
for budget checking and expense recording.

Supported providers:
    - RunPod (runpod.io) — A100/H100, spot and on-demand
    - vast.ai — Marketplace, variable pricing
    - Lambda Labs (lambda.ai) — On-demand cloud GPUs
    - Local (Mac M-series) — Free but limited VRAM

Future: AWS spot, GCP preemptible, Azure spot
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GPUProvider(str, Enum):
    """Supported GPU providers."""
    RUNPOD = "runpod"
    VAST_AI = "vast_ai"
    LAMBDA = "lambda"
    LOCAL = "local"


class GPUType(str, Enum):
    """Common GPU types for training/inference."""
    A100_40GB = "a100_40gb"
    A100_80GB = "a100_80gb"
    H100_80GB = "h100_80gb"
    A6000 = "a6000"
    RTX_4090 = "rtx_4090"
    RTX_3090 = "rtx_3090"
    M3_PRO = "m3_pro"  # Local Mac


class GPUInstance(BaseModel):
    """A available GPU instance from a provider."""
    provider: GPUProvider
    gpu_type: GPUType
    gpu_count: int = 1
    vram_gb: int = 40
    price_per_hour: float = 0.0  # USD
    spot: bool = False  # Spot/preemptible pricing
    available: bool = True
    region: str = ""
    instance_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def price_per_day(self) -> float:
        return self.price_per_hour * 24

    @property
    def effective_vram(self) -> int:
        """Total VRAM across all GPUs."""
        return self.vram_gb * self.gpu_count


class TrainingEstimate(BaseModel):
    """Estimated cost and time for a training job."""
    model_size_b: float  # Billion parameters
    method: str = "qlora"  # "qlora" | "lora" | "full"
    dataset_size_mb: float = 50.0
    estimated_hours: float = 0.0
    estimated_cost_usd: float = 0.0
    recommended_gpu: Optional[GPUType] = None
    recommended_provider: Optional[GPUProvider] = None
    fits_in_budget: bool = False
    notes: str = ""


# Static pricing table (updated periodically)
# Real-time pricing would require API calls to each provider
_GPU_PRICING: list[GPUInstance] = [
    GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.A100_40GB,
        vram_gb=40, price_per_hour=1.44, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.A100_80GB,
        vram_gb=80, price_per_hour=2.49, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.H100_80GB,
        vram_gb=80, price_per_hour=3.99, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.RTX_4090,
        vram_gb=24, price_per_hour=0.69, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.VAST_AI, gpu_type=GPUType.A100_40GB,
        vram_gb=40, price_per_hour=1.10, spot=True,
    ),
    GPUInstance(
        provider=GPUProvider.VAST_AI, gpu_type=GPUType.RTX_4090,
        vram_gb=24, price_per_hour=0.40, spot=True,
    ),
    GPUInstance(
        provider=GPUProvider.VAST_AI, gpu_type=GPUType.RTX_3090,
        vram_gb=24, price_per_hour=0.25, spot=True,
    ),
    GPUInstance(
        provider=GPUProvider.LAMBDA, gpu_type=GPUType.A100_40GB,
        vram_gb=40, price_per_hour=1.29, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.LAMBDA, gpu_type=GPUType.H100_80GB,
        vram_gb=80, price_per_hour=2.49, spot=False,
    ),
    GPUInstance(
        provider=GPUProvider.LOCAL, gpu_type=GPUType.M3_PRO,
        vram_gb=18, price_per_hour=0.0, spot=False,
        metadata={"note": "Shared with system RAM, inference only for 7B quantized"},
    ),
]

# Model size → minimum VRAM requirements (QLoRA 4-bit)
_VRAM_REQUIREMENTS: dict[str, int] = {
    "7b": 8,    # 7B QLoRA fits in 8GB
    "14b": 16,  # 14B QLoRA needs 16GB
    "32b": 24,  # 32B QLoRA needs 24GB
    "70b": 40,  # 70B QLoRA needs 40GB
    "120b": 80, # 120B+ needs 80GB
}

# Approximate training hours per model size (QLoRA, ~10K samples)
_TRAINING_HOURS: dict[str, float] = {
    "7b": 2.0,
    "14b": 4.0,
    "32b": 8.0,
    "70b": 16.0,
    "120b": 36.0,
}


class ResourceScout:
    """Finds cheapest GPU time across providers for training jobs.

    Usage:
        scout = ResourceScout()

        # Find cheapest GPU for 7B training
        options = scout.find_cheapest(min_vram_gb=8)

        # Estimate training cost
        estimate = scout.estimate_training_cost(model_size_b=7.0, budget_usd=50.0)

        # Get recommendation
        rec = scout.recommend_for_generation(gen=0, budget_usd=10.0)
    """

    def __init__(self) -> None:
        self._pricing = list(_GPU_PRICING)
        self._last_refresh = time.time()

    def find_cheapest(
        self,
        min_vram_gb: int = 8,
        max_price_per_hour: float = 100.0,
        prefer_spot: bool = True,
        exclude_local: bool = False,
    ) -> list[GPUInstance]:
        """Find cheapest GPU instances meeting requirements.

        Args:
            min_vram_gb: Minimum VRAM needed.
            max_price_per_hour: Maximum acceptable hourly rate.
            prefer_spot: Prefer spot/preemptible pricing.
            exclude_local: Exclude local Mac GPU.

        Returns:
            List of GPUInstance sorted by price (cheapest first).
        """
        candidates = [
            g for g in self._pricing
            if g.vram_gb >= min_vram_gb
            and g.price_per_hour <= max_price_per_hour
            and g.available
            and (not exclude_local or g.provider != GPUProvider.LOCAL)
        ]

        # Sort: spot instances first if preferred, then by price
        if prefer_spot:
            candidates.sort(key=lambda g: (not g.spot, g.price_per_hour))
        else:
            candidates.sort(key=lambda g: g.price_per_hour)

        return candidates

    def estimate_training_cost(
        self,
        model_size_b: float,
        method: str = "qlora",
        dataset_size_mb: float = 50.0,
        budget_usd: float = 0.0,
    ) -> TrainingEstimate:
        """Estimate training cost for a model size.

        Args:
            model_size_b: Model size in billions of parameters.
            method: Training method ("qlora", "lora", "full").
            dataset_size_mb: Training dataset size in MB.
            budget_usd: Available budget (0 = unlimited).

        Returns:
            TrainingEstimate with cost, time, and recommendations.
        """
        # Determine VRAM requirement
        size_key = self._size_to_key(model_size_b)
        min_vram = _VRAM_REQUIREMENTS.get(size_key, 80)
        base_hours = _TRAINING_HOURS.get(size_key, 24.0)

        # Adjust hours by method
        if method == "full":
            base_hours *= 4.0
            min_vram *= 3  # Full fine-tune needs much more VRAM
        elif method == "lora":
            base_hours *= 1.5
            min_vram = int(min_vram * 1.5)

        # Adjust by dataset size (linear scaling beyond 50MB baseline)
        dataset_factor = max(dataset_size_mb / 50.0, 1.0)
        estimated_hours = base_hours * min(dataset_factor, 3.0)

        # Find cheapest GPU that fits
        options = self.find_cheapest(min_vram_gb=min_vram, exclude_local=True)
        if not options:
            return TrainingEstimate(
                model_size_b=model_size_b,
                method=method,
                dataset_size_mb=dataset_size_mb,
                estimated_hours=estimated_hours,
                notes=f"No GPU found with {min_vram}GB+ VRAM",
            )

        cheapest = options[0]
        estimated_cost = estimated_hours * cheapest.price_per_hour

        return TrainingEstimate(
            model_size_b=model_size_b,
            method=method,
            dataset_size_mb=dataset_size_mb,
            estimated_hours=round(estimated_hours, 1),
            estimated_cost_usd=round(estimated_cost, 2),
            recommended_gpu=cheapest.gpu_type,
            recommended_provider=cheapest.provider,
            fits_in_budget=budget_usd <= 0 or estimated_cost <= budget_usd,
            notes=f"{cheapest.gpu_type.value} on {cheapest.provider.value} "
                  f"@ ${cheapest.price_per_hour:.2f}/hr"
                  f"{' (spot)' if cheapest.spot else ''}",
        )

    def recommend_for_generation(
        self,
        gen: int,
        budget_usd: float,
    ) -> TrainingEstimate:
        """Recommend training config for a model generation.

        Args:
            gen: Generation number (0=seed, 1=usable, 2+=frontier).
            budget_usd: Available training budget.

        Returns:
            TrainingEstimate sized to the budget.
        """
        # Generation → target model size
        gen_targets = {
            0: 7.0,    # Seed: 7B
            1: 14.0,   # Usable: 14B
            2: 32.0,   # Strong: 32B
            3: 70.0,   # Frontier: 70B
        }
        target_size = gen_targets.get(gen, 70.0)

        # Try target size first, then fall back to smaller
        for size in [target_size, target_size / 2, 7.0]:
            estimate = self.estimate_training_cost(
                model_size_b=size,
                budget_usd=budget_usd,
            )
            if estimate.fits_in_budget:
                return estimate

        # Even 7B doesn't fit — return the 7B estimate anyway
        return self.estimate_training_cost(model_size_b=7.0, budget_usd=budget_usd)

    def _size_to_key(self, size_b: float) -> str:
        """Map model size in billions to pricing key."""
        if size_b <= 7:
            return "7b"
        elif size_b <= 14:
            return "14b"
        elif size_b <= 32:
            return "32b"
        elif size_b <= 70:
            return "70b"
        else:
            return "120b"

    def pricing_table(self) -> list[dict[str, Any]]:
        """Return pricing table for display."""
        return [
            {
                "provider": g.provider.value,
                "gpu": g.gpu_type.value,
                "vram_gb": g.vram_gb,
                "price_hr": g.price_per_hour,
                "spot": g.spot,
            }
            for g in sorted(self._pricing, key=lambda g: g.price_per_hour)
        ]
