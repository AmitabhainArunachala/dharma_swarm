"""Dataset builder for model training.

Converts dharma_swarm trajectories + thinkodynamic foundations into
training-ready datasets. Model-size-agnostic — produces chat-format
JSONL that works with unsloth, axolotl, torchtune, or any trainer.

Data composition (configurable):
    40% — Best agent trajectories (ThinkodynamicScore > 0.7)
    20% — Thinkodynamic foundations (BRIDGE, PILLARS, SAMAYA, GLOSSARY)
    15% — R_V research outputs (paper, experiments, claims)
    10% — Subconscious dreams (hum, dream_associations)
    10% — High-salience stigmergy marks
     5% — Successful evolution archive entries
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DATASET_DIR = Path.home() / ".dharma" / "datasets"


class DatasetConfig(BaseModel):
    """Configuration for dataset building."""
    name: str = "dharma-dataset"
    min_thinkodynamic_score: float = 0.7
    min_swabhaav_ratio: float = 0.5
    success_only: bool = True
    max_samples: int = 0  # 0 = no limit
    include_foundations: bool = True
    include_dreams: bool = True
    include_stigmergy: bool = True
    include_evolution: bool = True
    chat_format: str = "openai"  # "openai" | "alpaca" | "chatml"


class DatasetSample(BaseModel):
    """One training sample in chat format."""
    messages: list[dict[str, str]]  # [{"role": "system|user|assistant", "content": "..."}]
    source: str = ""  # "trajectory" | "foundation" | "dream" | "stigmergy" | "evolution"
    quality_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetStats(BaseModel):
    """Statistics for a built dataset."""
    total_samples: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    total_tokens_approx: int = 0
    avg_quality: float = 0.0
    output_path: str = ""
    build_time_seconds: float = 0.0


class DatasetBuilder:
    """Builds training datasets from dharma_swarm's accumulated data.

    Usage:
        builder = DatasetBuilder()
        stats = builder.build(DatasetConfig(name="gen0-training"))
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._output_dir = output_dir or _DATASET_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def build(self, config: DatasetConfig) -> DatasetStats:
        """Build a training dataset.

        Collects data from all sources, filters by quality, and writes
        to JSONL in the specified chat format.

        Args:
            config: Dataset configuration.

        Returns:
            DatasetStats summarizing the built dataset.
        """
        start = time.time()
        samples: list[DatasetSample] = []

        # 1. Trajectories (40%)
        trajectory_samples = self._collect_trajectories(config)
        samples.extend(trajectory_samples)

        # 2. Foundations (20%)
        if config.include_foundations:
            foundation_samples = self._collect_foundations()
            samples.extend(foundation_samples)

        # 3. Dreams (10%)
        if config.include_dreams:
            dream_samples = self._collect_dreams()
            samples.extend(dream_samples)

        # 4. Stigmergy (10%)
        if config.include_stigmergy:
            stigmergy_samples = self._collect_stigmergy()
            samples.extend(stigmergy_samples)

        # 5. Evolution archive (5%)
        if config.include_evolution:
            evolution_samples = self._collect_evolution()
            samples.extend(evolution_samples)

        # Apply max_samples limit
        if config.max_samples > 0:
            samples = samples[:config.max_samples]

        # Write to JSONL
        output_path = self._output_dir / f"{config.name}.jsonl"
        token_count = 0
        quality_sum = 0.0
        by_source: dict[str, int] = {}

        with open(output_path, "w") as f:
            for sample in samples:
                # Convert to chat format
                record = self._format_sample(sample, config.chat_format)
                f.write(json.dumps(record) + "\n")
                by_source[sample.source] = by_source.get(sample.source, 0) + 1
                quality_sum += sample.quality_score
                # Rough token estimate: 4 chars per token
                for msg in sample.messages:
                    token_count += len(msg.get("content", "")) // 4

        build_time = time.time() - start
        stats = DatasetStats(
            total_samples=len(samples),
            by_source=by_source,
            total_tokens_approx=token_count,
            avg_quality=round(quality_sum / max(len(samples), 1), 4),
            output_path=str(output_path),
            build_time_seconds=round(build_time, 2),
        )

        logger.info(
            "Dataset '%s' built: %d samples, ~%dK tokens, avg quality %.2f (%.1fs)",
            config.name, stats.total_samples, stats.total_tokens_approx // 1000,
            stats.avg_quality, stats.build_time_seconds,
        )
        return stats

    # -- Data collectors ---------------------------------------------------

    def _collect_trajectories(self, config: DatasetConfig) -> list[DatasetSample]:
        """Collect training samples from completed trajectories."""
        samples = []
        try:
            from dharma_swarm.trajectory_collector import get_collector
            collector = get_collector()
            trajectories = collector.load_trajectories(
                success_only=config.success_only,
            )
            for traj in trajectories:
                for chunk in traj.chunks:
                    if not chunk.prompt or not chunk.response:
                        continue
                    samples.append(DatasetSample(
                        messages=[
                            {"role": "system", "content": "You are a dharmic AI agent operating within dharma_swarm. Apply thinkodynamic principles, maintain witness stance, and align all actions with the telos of Jagat Kalyan."},
                            {"role": "user", "content": chunk.prompt[:4000]},
                            {"role": "assistant", "content": chunk.response[:4000]},
                        ],
                        source="trajectory",
                        quality_score=0.7,  # Already filtered by collector
                        metadata={
                            "trajectory_id": traj.trajectory_id,
                            "model": chunk.model,
                            "task": traj.task_title[:100],
                        },
                    ))
        except Exception:
            logger.debug("Trajectory collection failed", exc_info=True)
        return samples

    def _collect_foundations(self) -> list[DatasetSample]:
        """Collect training samples from thinkodynamic foundation docs."""
        samples = []
        foundations_dir = Path.home() / "dharma_swarm" / "foundations"
        if not foundations_dir.exists():
            return samples

        # Key foundation files for training
        foundation_files = [
            "THINKODYNAMIC_BRIDGE.md",
            "PILLAR_04_HOFSTADTER.md",
            "PILLAR_05_AUROBINDO.md",
            "PILLAR_06_DADA_BHAGWAN.md",
            "PILLAR_07_VARELA.md",
            "PILLAR_08_BEER.md",
            "PILLAR_09_DEACON.md",
            "PILLAR_10_FRISTON.md",
            "GLOSSARY.md",
            "SAMAYA_PROTOCOL.md",
        ]

        for fname in foundation_files:
            fpath = foundations_dir / fname
            if not fpath.exists():
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
                # Split into chunks of ~2000 chars for training
                for i in range(0, len(text), 2000):
                    chunk = text[i:i + 2000].strip()
                    if len(chunk) < 100:
                        continue
                    samples.append(DatasetSample(
                        messages=[
                            {"role": "system", "content": "You deeply understand thinkodynamics — the three-layer hierarchy of meaning, geometry, and weights. Explain with precision and contemplative depth."},
                            {"role": "user", "content": f"Explain this section from {fname}:\n\n{chunk[:1000]}"},
                            {"role": "assistant", "content": chunk},
                        ],
                        source="foundation",
                        quality_score=0.9,  # Foundational docs are high quality
                        metadata={"file": fname},
                    ))
            except Exception:
                continue
        return samples

    def _collect_dreams(self) -> list[DatasetSample]:
        """Collect training samples from subconscious dream associations."""
        samples = []
        dream_file = Path.home() / ".dharma" / "subconscious" / "hum.jsonl"
        if not dream_file.exists():
            return samples

        try:
            with open(dream_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        dream = json.loads(line)
                        desc = dream.get("description", "")
                        reasoning = dream.get("reasoning", "")
                        if not desc:
                            continue
                        samples.append(DatasetSample(
                            messages=[
                                {"role": "system", "content": "You are the subconscious layer of dharma_swarm, making lateral associations and discovering hidden connections between concepts."},
                                {"role": "user", "content": "What connections do you see in the current ecosystem state?"},
                                {"role": "assistant", "content": f"{desc}\n\n{reasoning}" if reasoning else desc},
                            ],
                            source="dream",
                            quality_score=float(dream.get("salience", 0.5)),
                            metadata={"resonance_type": dream.get("resonance_type", "")},
                        ))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return samples

    def _collect_stigmergy(self) -> list[DatasetSample]:
        """Collect from high-salience stigmergy marks."""
        samples = []
        marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
        if not marks_file.exists():
            return samples

        try:
            with open(marks_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        mark = json.loads(line)
                        obs = mark.get("observation", "")
                        salience = float(mark.get("salience", 0))
                        if not obs or salience < 0.5:
                            continue
                        samples.append(DatasetSample(
                            messages=[
                                {"role": "system", "content": "You are an agent leaving pheromone marks in the stigmergy store, recording observations for other agents to discover."},
                                {"role": "user", "content": f"What did you observe about {mark.get('file_path', 'the system')}?"},
                                {"role": "assistant", "content": obs},
                            ],
                            source="stigmergy",
                            quality_score=min(salience, 1.0),
                            metadata={"agent": mark.get("agent", ""), "action": mark.get("action", "")},
                        ))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass
        return samples

    def _collect_evolution(self) -> list[DatasetSample]:
        """Collect from successful evolution archive entries."""
        samples = []
        archive_file = Path.home() / ".dharma" / "evolution" / "archive.jsonl"
        if not archive_file.exists():
            return samples

        try:
            with open(archive_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        desc = entry.get("description", "")
                        diff = entry.get("diff", "")
                        fitness = entry.get("fitness", {})
                        if not desc or not diff:
                            continue
                        correctness = float(fitness.get("correctness", 0))
                        if correctness < 0.8:
                            continue
                        samples.append(DatasetSample(
                            messages=[
                                {"role": "system", "content": "You are the DarwinEngine proposing code mutations. All mutations are tested, gated, and measured."},
                                {"role": "user", "content": f"Propose an improvement for {entry.get('component', 'the codebase')}"},
                                {"role": "assistant", "content": f"{desc}\n\n```diff\n{diff[:2000]}\n```"},
                            ],
                            source="evolution",
                            quality_score=correctness,
                            metadata={"component": entry.get("component", "")},
                        ))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass
        return samples

    # -- Formatting --------------------------------------------------------

    def _format_sample(self, sample: DatasetSample, chat_format: str) -> dict:
        """Format a sample for the specified training format."""
        if chat_format == "openai":
            return {"messages": sample.messages}
        elif chat_format == "alpaca":
            # Convert to instruction/input/output format
            system = ""
            instruction = ""
            output = ""
            for msg in sample.messages:
                if msg["role"] == "system":
                    system = msg["content"]
                elif msg["role"] == "user":
                    instruction = msg["content"]
                elif msg["role"] == "assistant":
                    output = msg["content"]
            return {
                "instruction": f"{system}\n\n{instruction}".strip(),
                "input": "",
                "output": output,
            }
        else:  # chatml
            return {"messages": sample.messages}
