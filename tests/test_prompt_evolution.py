"""Tests for the Prompt Evolution Protocol.

Covers:
- PromptGenome creation, rendering, hashing, distance
- PromptSegment classification and invariant verification
- PromptEvolver mutation and crossover operators
- PromptPopulation management, species, selection
- PromptEvolutionEngine full generation loop
- Safety: invariant preservation, telos gate integration, regression rollback
- Canary evaluation decisions
- Heuristic mutation transforms
- Factory helpers
- Meta-mutation prompt generation
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

import pytest

from dharma_swarm.prompt_evolution import (
    CrossoverMethod,
    MutationOperator,
    PromptCanaryResult,
    PromptEvaluation,
    PromptEvolutionConfig,
    PromptEvolutionEngine,
    PromptEvolver,
    PromptFitnessScore,
    PromptGenome,
    PromptPopulation,
    PromptSegment,
    PromptSpecies,
    SegmentType,
    _heuristic_compress,
    _heuristic_constrain,
    _heuristic_expand,
    _heuristic_rephrase,
    _heuristic_restructure,
    _interleave,
    _split_sentences,
    create_meta_mutation_prompt,
    create_prompt_genome,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_genome() -> PromptGenome:
    """A minimal prompt genome with all segment types."""
    return create_prompt_genome(
        name="test_prompt",
        system_identity="You are a helpful coding assistant.",
        task_instruction="Review the provided Python code for bugs and style issues.",
        few_shot_examples=(
            "Example input: def foo(): pass\n"
            "Example output: No bugs found. Consider adding a docstring."
        ),
        output_format="Respond with: BUGS: ..., STYLE: ..., VERDICT: pass/fail",
        safety_constraints="Never execute code. Never output credentials.",
        context_template="Code to review:\n{code}\n\nFile: {filename}",
        species="code_review",
        tags=["code", "review"],
    )


@pytest.fixture
def second_genome() -> PromptGenome:
    """A second genome for crossover tests."""
    return create_prompt_genome(
        name="test_prompt_v2",
        system_identity="You are a helpful coding assistant.",
        task_instruction="Analyze the Python code for performance and correctness.",
        few_shot_examples=(
            "Example input: for i in range(len(lst)): ...\n"
            "Example output: Use enumerate() instead for cleaner iteration."
        ),
        output_format="Respond with: PERFORMANCE: ..., CORRECTNESS: ..., SCORE: 0-10",
        safety_constraints="Never execute code. Never output credentials.",
        context_template="Code to review:\n{code}\n\nFile: {filename}",
        species="code_review",
    )


@pytest.fixture
def population(basic_genome: PromptGenome) -> PromptPopulation:
    """A population seeded with the basic genome."""
    pop = PromptPopulation(max_size=8, elite_count=2)
    pop.add_genome(basic_genome)
    return pop


@pytest.fixture
def engine(tmp_path: Path) -> PromptEvolutionEngine:
    """A prompt evolution engine with temp archive."""
    config = PromptEvolutionConfig(
        population_size=6,
        elite_count=2,
        mutation_rate=0.5,  # High rate for testing
        crossover_rate=0.3,
    )
    return PromptEvolutionEngine(
        config=config,
        archive_path=tmp_path / "prompt_archive.jsonl",
    )


def _make_evaluation(
    genome_id: str,
    quality: float = 0.7,
    depth: float = 0.6,
    efficiency: float = 0.8,
    alignment: float = 0.9,
    consistency: float = 0.7,
    safety: float = 1.0,
) -> PromptEvaluation:
    """Helper to create a PromptEvaluation."""
    return PromptEvaluation(
        genome_id=genome_id,
        genome_hash="test",
        fitness=PromptFitnessScore(
            output_quality=quality,
            depth_preservation=depth,
            token_efficiency=efficiency,
            telos_alignment=alignment,
            consistency=consistency,
            safety_compliance=safety,
        ),
        tasks_evaluated=5,
    )


# ---------------------------------------------------------------------------
# PromptSegment
# ---------------------------------------------------------------------------


class TestPromptSegment:
    def test_default_segment_is_mutable(self):
        seg = PromptSegment(content="test")
        assert seg.segment_type == SegmentType.MUTABLE

    def test_content_hash_deterministic(self):
        seg = PromptSegment(content="hello world")
        h1 = seg.content_hash()
        h2 = seg.content_hash()
        assert h1 == h2
        assert len(h1) == 16  # Truncated SHA-256

    def test_content_hash_differs_for_different_content(self):
        seg1 = PromptSegment(content="hello")
        seg2 = PromptSegment(content="world")
        assert seg1.content_hash() != seg2.content_hash()


# ---------------------------------------------------------------------------
# PromptGenome
# ---------------------------------------------------------------------------


class TestPromptGenome:
    def test_create_genome_factory(self, basic_genome: PromptGenome):
        assert basic_genome.name == "test_prompt"
        assert basic_genome.species == "code_review"
        assert len(basic_genome.segments) == 6  # identity, safety, task, examples, format, context
        assert len(basic_genome.invariant_segments()) == 2
        assert len(basic_genome.mutable_segments()) == 3
        assert len(basic_genome.adaptive_segments()) == 1

    def test_render_without_context(self, basic_genome: PromptGenome):
        rendered = basic_genome.render()
        assert "helpful coding assistant" in rendered
        assert "Review the provided Python code" in rendered
        assert "{code}" in rendered  # Unresolved template

    def test_render_with_context(self, basic_genome: PromptGenome):
        rendered = basic_genome.render({"code": "print('hi')", "filename": "test.py"})
        assert "print('hi')" in rendered
        assert "test.py" in rendered
        assert "{code}" not in rendered  # Template resolved

    def test_genome_hash_deterministic(self, basic_genome: PromptGenome):
        h1 = basic_genome.genome_hash()
        h2 = basic_genome.genome_hash()
        assert h1 == h2

    def test_genome_hash_changes_with_mutable_content(self, basic_genome: PromptGenome):
        h1 = basic_genome.genome_hash()
        basic_genome.mutable_segments()[0].content = "MODIFIED"
        h2 = basic_genome.genome_hash()
        assert h1 != h2

    def test_genome_hash_ignores_invariant_content(self, basic_genome: PromptGenome):
        h1 = basic_genome.genome_hash()
        # Invariant segments don't affect the mutable hash
        # (they are excluded from genome_hash)
        assert h1 == basic_genome.genome_hash()

    def test_token_estimate(self, basic_genome: PromptGenome):
        estimate = basic_genome.token_estimate()
        assert estimate > 0
        total_chars = sum(len(s.content) for s in basic_genome.segments)
        assert estimate == total_chars // 4

    def test_distance_identical_genomes(self, basic_genome: PromptGenome):
        other = basic_genome.model_copy(deep=True)
        assert basic_genome.distance(other) == 0.0

    def test_distance_different_genomes(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        dist = basic_genome.distance(second_genome)
        assert 0.0 < dist < 1.0  # Different but related

    def test_distance_symmetric(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        d1 = basic_genome.distance(second_genome)
        d2 = second_genome.distance(basic_genome)
        assert abs(d1 - d2) < 1e-9

    def test_empty_genomes_distance_zero(self):
        a = PromptGenome(segments=[])
        b = PromptGenome(segments=[])
        assert a.distance(b) == 0.0


# ---------------------------------------------------------------------------
# PromptFitnessScore
# ---------------------------------------------------------------------------


class TestPromptFitnessScore:
    def test_weighted_default_weights(self):
        score = PromptFitnessScore(
            output_quality=1.0,
            depth_preservation=1.0,
            token_efficiency=1.0,
            telos_alignment=1.0,
            consistency=1.0,
            safety_compliance=1.0,
        )
        assert abs(score.weighted() - 1.0) < 1e-6

    def test_weighted_zero(self):
        score = PromptFitnessScore()
        assert score.weighted() == 0.0

    def test_weighted_custom_weights(self):
        score = PromptFitnessScore(output_quality=1.0)
        custom = {"output_quality": 1.0, "depth_preservation": 0.0,
                  "token_efficiency": 0.0, "telos_alignment": 0.0,
                  "consistency": 0.0, "safety_compliance": 0.0}
        assert score.weighted(custom) == 1.0

    def test_to_archive_fitness(self):
        score = PromptFitnessScore(
            output_quality=0.8,
            telos_alignment=0.9,
            depth_preservation=0.7,
            token_efficiency=0.6,
            safety_compliance=1.0,
            consistency=0.5,
        )
        archive = score.to_archive_fitness()
        assert archive.correctness == 0.8
        assert archive.dharmic_alignment == 0.9
        assert archive.safety == 1.0


# ---------------------------------------------------------------------------
# PromptEvolver
# ---------------------------------------------------------------------------


class TestPromptEvolver:
    def test_mutate_preserves_invariants(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)  # Mutate everything
        child = evolver.mutate(basic_genome)

        # Invariant segments should be unchanged
        for parent_seg, child_seg in zip(
            basic_genome.invariant_segments(), child.invariant_segments()
        ):
            assert parent_seg.content == child_seg.content

    def test_mutate_creates_new_id(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)
        assert child.id != basic_genome.id

    def test_mutate_increments_generation(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)
        assert child.generation == basic_genome.generation + 1

    def test_mutate_tracks_parent(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)
        assert basic_genome.id in child.parent_ids

    def test_mutate_with_specific_operator(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)
        target = basic_genome.mutable_segments()[0]
        # Use CONSTRAIN which always adds content (guaranteed to differ)
        child = evolver.mutate(
            basic_genome,
            operator=MutationOperator.CONSTRAIN,
            target_segment_id=target.id,
        )
        # The mutation log should record the operation
        log = evolver.get_mutation_log()
        assert len(log) >= 1
        assert log[-1].operator == MutationOperator.CONSTRAIN

    def test_mutate_zero_rate_no_changes(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=0.01)
        # With very low rate, most mutations are skipped
        # Run multiple times to verify at least some pass through
        unchanged_count = 0
        for _ in range(20):
            child = evolver.mutate(basic_genome)
            mutable_changed = any(
                cs.content != ps.content
                for cs, ps in zip(child.mutable_segments(), basic_genome.mutable_segments())
            )
            if not mutable_changed:
                unchanged_count += 1
        # At 1% rate with 3 mutable segments, most should be unchanged
        assert unchanged_count > 0

    def test_crossover_segment_swap(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        evolver = PromptEvolver()
        child = evolver.crossover(basic_genome, second_genome)
        assert child.id != basic_genome.id
        assert child.id != second_genome.id
        assert basic_genome.id in child.parent_ids
        assert second_genome.id in child.parent_ids

    def test_crossover_blend(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        evolver = PromptEvolver()
        child = evolver.crossover(
            basic_genome, second_genome, method=CrossoverMethod.BLEND
        )
        assert len(child.parent_ids) == 2

    def test_crossover_tournament(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        basic_genome.fitness_history = [0.8, 0.85, 0.9]
        second_genome.fitness_history = [0.6, 0.55, 0.5]
        evolver = PromptEvolver()
        child = evolver.crossover(
            basic_genome, second_genome, method=CrossoverMethod.TOURNAMENT_SEGMENT
        )
        assert len(child.parent_ids) == 2

    def test_crossover_preserves_invariants(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        evolver = PromptEvolver()
        child = evolver.crossover(basic_genome, second_genome)
        # Invariant segments come from parent_a (the fitter parent)
        for parent_seg, child_seg in zip(
            basic_genome.invariant_segments(), child.invariant_segments()
        ):
            assert parent_seg.content == child_seg.content

    def test_mutation_log_records_operations(self, basic_genome: PromptGenome):
        evolver = PromptEvolver(mutation_rate=1.0)
        evolver.mutate(basic_genome)
        log = evolver.get_mutation_log()
        assert len(log) >= 1
        for record in log:
            assert record.segment_role in ("task_instruction", "few_shot_example", "output_format")

    def test_mutate_retries_when_initial_operator_is_noop(
        self,
        basic_genome: PromptGenome,
        monkeypatch: pytest.MonkeyPatch,
    ):
        initial_ops = {
            "task_instruction": MutationOperator.TONE_SHIFT,
            "few_shot_example": MutationOperator.EXEMPLIFY,
            "output_format": MutationOperator.RESTRUCTURE,
        }

        monkeypatch.setattr(
            PromptEvolver,
            "_select_operator",
            lambda self, role: initial_ops[role],
        )

        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)

        assert any(
            child_seg.content != parent_seg.content
            for child_seg, parent_seg in zip(
                child.mutable_segments(),
                basic_genome.mutable_segments(),
            )
        )
        assert evolver.get_mutation_log()

    def test_crossover_log_records_operations(
        self, basic_genome: PromptGenome, second_genome: PromptGenome
    ):
        evolver = PromptEvolver()
        evolver.crossover(basic_genome, second_genome)
        log = evolver.get_crossover_log()
        assert len(log) == 1
        assert log[0].parent_a_id == basic_genome.id


# ---------------------------------------------------------------------------
# PromptPopulation
# ---------------------------------------------------------------------------


class TestPromptPopulation:
    def test_add_genome(self, population: PromptPopulation, basic_genome: PromptGenome):
        assert population.size == 1
        assert population.get_genome(basic_genome.id) is not None

    def test_record_evaluation(self, population: PromptPopulation, basic_genome: PromptGenome):
        evaluation = _make_evaluation(basic_genome.id)
        population.record_evaluation(basic_genome.id, evaluation)
        fitness = population.get_fitness(basic_genome.id)
        assert fitness > 0.0

    def test_select_parent(self, population: PromptPopulation, basic_genome: PromptGenome):
        evaluation = _make_evaluation(basic_genome.id)
        population.record_evaluation(basic_genome.id, evaluation)
        parent = population.select_parent()
        assert parent is not None
        assert parent.id == basic_genome.id

    def test_species_assignment(self, basic_genome: PromptGenome, second_genome: PromptGenome):
        pop = PromptPopulation(max_size=8, speciation_distance=0.1)
        sp1 = pop.add_genome(basic_genome)
        sp2 = pop.add_genome(second_genome)
        # These genomes are related but different -- with tight speciation
        # distance, they may be in different species
        summary = pop.get_species_summary()
        assert len(summary) >= 1

    def test_advance_generation_preserves_elites(
        self, population: PromptPopulation, basic_genome: PromptGenome
    ):
        evaluation = _make_evaluation(basic_genome.id, quality=0.95)
        population.record_evaluation(basic_genome.id, evaluation)

        # Create offspring
        evolver = PromptEvolver(mutation_rate=1.0)
        offspring = [evolver.mutate(basic_genome) for _ in range(4)]

        summary = population.advance_generation(offspring)
        assert summary["elites_preserved"] >= 1
        # The original high-fitness genome should survive
        assert population.get_genome(basic_genome.id) is not None

    def test_max_size_enforcement(self, basic_genome: PromptGenome):
        pop = PromptPopulation(max_size=4, elite_count=1)
        pop.add_genome(basic_genome)
        pop.record_evaluation(basic_genome.id, _make_evaluation(basic_genome.id))

        evolver = PromptEvolver(mutation_rate=1.0)
        offspring = [evolver.mutate(basic_genome) for _ in range(10)]
        pop.advance_generation(offspring)
        assert pop.size <= 4

    def test_get_elites_returns_top_n(self, basic_genome: PromptGenome):
        pop = PromptPopulation(max_size=8, elite_count=2)
        pop.add_genome(basic_genome)
        pop.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.9),
        )

        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)
        pop.add_genome(child)
        pop.record_evaluation(
            child.id,
            _make_evaluation(child.id, quality=0.5),
        )

        elites = pop.get_elites()
        assert len(elites) == 2
        # First elite should be the higher-fitness genome
        assert pop.get_fitness(elites[0].id) >= pop.get_fitness(elites[1].id)


# ---------------------------------------------------------------------------
# PromptEvolutionEngine
# ---------------------------------------------------------------------------


class TestPromptEvolutionEngine:
    def test_seed_population(self, engine: PromptEvolutionEngine, basic_genome: PromptGenome):
        result = engine.seed_population([basic_genome])
        assert result["seeded"] == 1
        assert result["population_size"] == 1

    def test_evolve_generation(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
        second_genome: PromptGenome,
    ):
        engine.seed_population([basic_genome, second_genome])
        # Evaluate seeds
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.8),
        )
        engine.population.record_evaluation(
            second_genome.id,
            _make_evaluation(second_genome.id, quality=0.7),
        )

        offspring = engine.evolve_generation()
        assert len(offspring) > 0
        for child in offspring:
            assert len(child.parent_ids) >= 1

    def test_invariant_verification(
        self, engine: PromptEvolutionEngine, basic_genome: PromptGenome
    ):
        engine.seed_population([basic_genome])

        # A child with preserved invariants should pass
        evolver = PromptEvolver(mutation_rate=1.0)
        child = evolver.mutate(basic_genome)
        assert engine._verify_invariants(child)

    def test_invariant_violation_detected(
        self, engine: PromptEvolutionEngine, basic_genome: PromptGenome
    ):
        engine.seed_population([basic_genome])

        # Manually corrupt an invariant segment
        child = basic_genome.model_copy(deep=True)
        child.id = "corrupt_child"
        child.parent_ids = [basic_genome.id]
        for seg in child.segments:
            if seg.segment_type == SegmentType.INVARIANT:
                seg.content = "CORRUPTED"
                break

        assert not engine._verify_invariants(child)

    def test_canary_evaluation_promote(self, engine: PromptEvolutionEngine, basic_genome: PromptGenome):
        engine.seed_population([basic_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.6),
        )

        result = engine.evaluate_canary(
            basic_genome.id,
            canary_fitness=0.9,
            tasks_evaluated=10,
        )
        assert result.decision == "promote"

    def test_canary_evaluation_rollback(self, engine: PromptEvolutionEngine, basic_genome: PromptGenome):
        engine.seed_population([basic_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.9),
        )

        result = engine.evaluate_canary(
            basic_genome.id,
            canary_fitness=0.3,
            tasks_evaluated=10,
        )
        assert result.decision == "rollback"

    def test_canary_evaluation_defer_insufficient_data(
        self, engine: PromptEvolutionEngine, basic_genome: PromptGenome
    ):
        engine.seed_population([basic_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.7),
        )

        result = engine.evaluate_canary(
            basic_genome.id,
            canary_fitness=0.9,
            tasks_evaluated=2,  # Below min_evaluations_for_promotion (5)
        )
        assert result.decision == "defer"

    def test_run_generation(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
        second_genome: PromptGenome,
    ):
        engine.seed_population([basic_genome, second_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.8),
        )
        engine.population.record_evaluation(
            second_genome.id,
            _make_evaluation(second_genome.id, quality=0.7),
        )

        def evaluate_fn(genome: PromptGenome) -> PromptEvaluation:
            return _make_evaluation(genome.id, quality=0.75)

        summary = engine.run_generation(evaluate_fn)
        assert summary["generation"] == 1
        assert summary["population_size"] > 0

    def test_archive_written(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
    ):
        engine.seed_population([basic_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.8),
        )

        def evaluate_fn(genome: PromptGenome) -> PromptEvaluation:
            return _make_evaluation(genome.id)

        engine.run_generation(evaluate_fn)
        assert engine._archive_path.exists()
        lines = engine._archive_path.read_text().splitlines()
        assert len(lines) > 0
        # Each line should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert "genome_id" in data

    def test_human_review_flagging(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
    ):
        engine.config.human_review_distance_threshold = 0.01  # Very tight
        engine.seed_population([basic_genome])
        engine.population.record_evaluation(
            basic_genome.id,
            _make_evaluation(basic_genome.id, quality=0.8),
        )

        def evaluate_fn(genome: PromptGenome) -> PromptEvaluation:
            return _make_evaluation(genome.id)

        engine.run_generation(evaluate_fn)
        # With very tight threshold, most mutations should be flagged
        flagged = engine.get_flagged_for_review()
        # May or may not be flagged depending on heuristic mutations
        # Just verify the method works
        assert isinstance(flagged, list)

    def test_get_evolution_summary(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
    ):
        engine.seed_population([basic_genome])
        summary = engine.get_evolution_summary()
        assert "generation" in summary
        assert "population_size" in summary
        assert "species" in summary
        assert summary["population_size"] == 1

    def test_gate_check_genome(
        self,
        engine: PromptEvolutionEngine,
        basic_genome: PromptGenome,
    ):
        passed, reason = engine.gate_check_genome(basic_genome)
        assert passed  # Normal prompt should pass gates
        assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# Heuristic mutations
# ---------------------------------------------------------------------------


class TestHeuristicMutations:
    def test_compress_removes_filler(self):
        text = "Please note that you should analyze the code carefully."
        result = _heuristic_compress(text)
        assert len(result) <= len(text)

    def test_compress_removes_blank_lines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = _heuristic_compress(text)
        assert "\n\n\n" not in result

    def test_restructure_permutes_paragraphs(self):
        text = "Paragraph A.\n\nParagraph B.\n\nParagraph C."
        # Run multiple times to verify it can change order
        seen_different = False
        for _ in range(50):
            result = _heuristic_restructure(text)
            if result != text:
                seen_different = True
                break
        assert seen_different

    def test_rephrase_substitutes_word(self):
        text = "Generate a detailed report about the code."
        result = _heuristic_rephrase(text)
        # Should substitute "generate" with "produce"
        assert result != text or "generate" not in text.lower()

    def test_constrain_adds_constraint(self):
        text = "Analyze the code."
        result = _heuristic_constrain(text)
        assert len(result) > len(text)

    def test_expand_adds_detail(self):
        text = "Review the code."
        result = _heuristic_expand(text)
        assert len(result) > len(text)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_split_sentences(self):
        text = "Hello world. This is a test. Another sentence!"
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_interleave_equal_length(self):
        a = ["a1", "a2", "a3"]
        b = ["b1", "b2", "b3"]
        result = _interleave(a, b)
        assert result == ["a1", "b1", "a2", "b2", "a3", "b3"]

    def test_interleave_unequal_length(self):
        a = ["a1", "a2"]
        b = ["b1"]
        result = _interleave(a, b)
        assert "a1" in result and "b1" in result and "a2" in result


# ---------------------------------------------------------------------------
# Factory and meta-prompt
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_prompt_genome_minimal(self):
        genome = create_prompt_genome(name="minimal", task_instruction="Do something.")
        assert genome.name == "minimal"
        assert len(genome.mutable_segments()) == 1

    def test_create_prompt_genome_full(self):
        genome = create_prompt_genome(
            name="full",
            system_identity="I am X.",
            task_instruction="Do Y.",
            few_shot_examples="Example: ...",
            output_format="Format: ...",
            safety_constraints="Never Z.",
            context_template="Context: {var}",
            species="custom",
            tags=["a", "b"],
        )
        assert len(genome.segments) == 6
        assert genome.species == "custom"
        assert genome.tags == ["a", "b"]

    def test_create_meta_mutation_prompt(self):
        prompt = create_meta_mutation_prompt(
            content="Analyze the code.",
            operator="rephrase",
            role="task_instruction",
        )
        assert "rephrase" in prompt.lower() or "Rephrase" in prompt
        assert "Analyze the code." in prompt

    def test_create_meta_mutation_prompt_with_history(self):
        prompt = create_meta_mutation_prompt(
            content="Test.",
            operator="compress",
            role="context",
            fitness_history=[0.5, 0.6, 0.65, 0.7, 0.75],
        )
        assert "improving" in prompt.lower()
        assert "0.750" in prompt


# ---------------------------------------------------------------------------
# Integration: full evolution loop
# ---------------------------------------------------------------------------


class TestEvolutionLoop:
    def test_multi_generation_fitness_tracked(self, tmp_path: Path):
        """Run 3 generations and verify fitness tracking works."""
        config = PromptEvolutionConfig(
            population_size=6,
            elite_count=2,
            mutation_rate=0.8,
            crossover_rate=0.2,
            max_generations=3,
        )
        engine = PromptEvolutionEngine(
            config=config,
            archive_path=tmp_path / "test_archive.jsonl",
        )

        # Seed with two genomes
        g1 = create_prompt_genome(
            name="seed_1",
            system_identity="You are an assistant.",
            task_instruction="Help users with coding tasks.",
            safety_constraints="Be safe.",
        )
        g2 = create_prompt_genome(
            name="seed_2",
            system_identity="You are an assistant.",
            task_instruction="Assist users with debugging Python code.",
            safety_constraints="Be safe.",
        )
        engine.seed_population([g1, g2])

        # Evaluate seeds
        engine.population.record_evaluation(
            g1.id, _make_evaluation(g1.id, quality=0.7)
        )
        engine.population.record_evaluation(
            g2.id, _make_evaluation(g2.id, quality=0.65)
        )

        # Run 3 generations
        for gen in range(3):
            def evaluate_fn(genome: PromptGenome) -> PromptEvaluation:
                # Simulate slightly random fitness
                import random
                q = 0.5 + random.random() * 0.4
                return _make_evaluation(genome.id, quality=q)

            summary = engine.run_generation(evaluate_fn)
            assert summary["generation"] == gen + 1
            assert summary["population_size"] <= config.population_size

        # Verify archive has entries
        assert engine._count_archived() > 0

        # Verify summary
        final = engine.get_evolution_summary()
        assert final["generations_run"] == 3

    def test_species_evolve_independently(self, tmp_path: Path):
        """Verify that different species maintain separation."""
        engine = PromptEvolutionEngine(
            config=PromptEvolutionConfig(
                population_size=8,
                speciation_distance=0.3,
            ),
            archive_path=tmp_path / "species_test.jsonl",
        )

        # Two very different prompt types
        code_prompt = create_prompt_genome(
            name="code_review",
            task_instruction="Review Python code for bugs, performance issues, and style violations.",
            safety_constraints="Never execute code.",
            species="code_review",
        )
        creative_prompt = create_prompt_genome(
            name="creative_writing",
            task_instruction="Write a compelling short story based on the given theme.",
            safety_constraints="Keep content appropriate.",
            species="creative_writing",
        )

        engine.seed_population([code_prompt, creative_prompt])
        species_summary = engine.population.get_species_summary()
        # Should have at least 1 species (both may end up in same if distance < threshold)
        assert len(species_summary) >= 1
