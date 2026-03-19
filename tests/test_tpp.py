"""Tests for the Transmission Prompt Protocol (TPP) module."""

from __future__ import annotations

import pytest

from dharma_swarm.tpp import (
    CompressionLevel,
    ContextReceipt,
    IntentThread,
    PromptScore,
    SiblingSignal,
    TPPLevel,
    TPPPrompt,
    TEMPLATES,
    compose_cascade,
    compose_from_template,
    compose_prompt,
    compress_semantic,
    create_intent_thread,
    evaluate_prompt,
    format_handoff_as_tpp,
    format_stigmergy_tpp,
    quick_check,
    verify_telos_continuity,
)


# ---------------------------------------------------------------------------
# IntentThread
# ---------------------------------------------------------------------------


class TestIntentThread:
    def test_create_basic(self):
        thread = create_intent_thread("Build a trading system", telos="Wealth creation")
        assert thread.operator_intent == "Build a trading system"
        assert thread.telos == "Wealth creation"
        assert thread.trace_id  # Non-empty
        assert thread.timestamp  # Non-empty

    def test_roundtrip_dict(self):
        thread = create_intent_thread("Test intent", context="some context")
        data = thread.to_dict()
        restored = IntentThread.from_dict(data)
        assert restored.operator_intent == thread.operator_intent
        assert restored.telos == thread.telos
        assert restored.trace_id == thread.trace_id

    def test_context_hash(self):
        t1 = create_intent_thread("Intent", context="context A")
        t2 = create_intent_thread("Intent", context="context B")
        assert t1.original_context_hash != t2.original_context_hash

    def test_default_telos(self):
        thread = create_intent_thread("Do something")
        assert "Jagat Kalyan" in thread.telos


# ---------------------------------------------------------------------------
# Semantic Compression
# ---------------------------------------------------------------------------


class TestSemanticCompression:
    @pytest.fixture
    def long_text(self) -> str:
        return (
            "# Research Findings\n\n"
            "## Key Result\n"
            "The R_V metric shows contraction with Hedges' g = -1.47.\n"
            "This proves causal depth in self-referential processing.\n\n"
            "## For Example\n"
            "Consider a simple case where the model processes 'I think'.\n"
            "The value matrices show systematic contraction at layers 25-30.\n\n"
            "## Methodology\n"
            "We used TransformerLens hooks to extract activation patterns.\n"
            "Note that this approach requires careful control conditions.\n\n"
            "## Conclusions\n"
            "The finding validates the bridge hypothesis: R_V contraction\n"
            "maps to behavioral L3→L4 transition.\n"
        )

    def test_full_no_compression(self, long_text: str):
        compressed, receipt = compress_semantic(long_text, "full", budget=10000)
        assert compressed == long_text
        assert receipt.compression_level == "full"
        assert len(receipt.omitted) == 0

    def test_semantic_drops_examples(self, long_text: str):
        compressed, receipt = compress_semantic(long_text, "semantic", budget=300)
        assert "For Example" not in compressed or len(compressed) < len(long_text)
        assert receipt.compression_level == "semantic"

    def test_principled_extracts_key_sentences(self, long_text: str):
        compressed, receipt = compress_semantic(long_text, "principled", budget=200)
        # Should prefer sentences with numbers and technical terms
        assert len(compressed) <= 200
        assert receipt.compression_level == "principled"

    def test_telos_preserves_purpose(self, long_text: str):
        compressed, receipt = compress_semantic(long_text, "telos", budget=200)
        assert receipt.compression_level == "telos"

    def test_seed_is_single_paragraph(self, long_text: str):
        compressed, receipt = compress_semantic(long_text, "seed", budget=200)
        assert compressed.startswith("[Seed:")
        assert receipt.compression_level == "seed"

    def test_receipt_has_hashes(self, long_text: str):
        _, receipt = compress_semantic(long_text, "semantic", budget=300)
        assert receipt.received_context_hash
        assert receipt.compressed_context_hash
        assert receipt.received_context_hash != receipt.compressed_context_hash

    def test_short_text_no_compression(self):
        short = "Brief context."
        compressed, receipt = compress_semantic(short, "semantic", budget=1000)
        assert compressed == short


# ---------------------------------------------------------------------------
# Prompt Composition
# ---------------------------------------------------------------------------


class TestComposePrompt:
    def test_basic_composition(self):
        prompt = compose_prompt(
            task_description="Analyze the R_V metric data",
            telos="Validate geometric signatures of self-referential processing",
            identity="You are a mechanistic interpretability researcher.",
        )
        assert prompt.task == "Analyze the R_V metric data"
        assert prompt.telos
        assert prompt.identity

    def test_telos_inherited_from_intent(self):
        thread = create_intent_thread("Find the bug", telos="Code quality")
        prompt = compose_prompt(
            task_description="Review the function",
            intent_thread=thread,
        )
        assert "Code quality" in prompt.telos
        assert "Find the bug" in prompt.telos

    def test_context_compression(self):
        big_context = "x " * 10000
        prompt = compose_prompt(
            task_description="Summarize findings",
            context=big_context,
            context_budget=500,
        )
        assert len(prompt.context) <= 600  # Budget + some overhead

    def test_anti_patterns_included(self):
        prompt = compose_prompt(
            task_description="Build the module",
            anti_patterns=["Don't over-engineer", "Don't skip tests"],
        )
        rendered = prompt.render()
        assert "Don't over-engineer" in rendered
        assert "Don't skip tests" in rendered

    def test_sibling_signals(self):
        signal = SiblingSignal(
            agent_id="agent_1",
            agent_role="researcher",
            finding_summary="Found R_V contraction at L27",
            confidence=0.85,
            telos_alignment=0.9,
        )
        prompt = compose_prompt(
            task_description="Verify the finding",
            sibling_signals=[signal],
        )
        rendered = prompt.render()
        assert "R_V contraction" in rendered
        assert "0.85" in rendered

    def test_cascade_depth(self):
        prompt = compose_prompt(
            task_description="Sub-task",
            cascade_depth=2,
        )
        rendered = prompt.render()
        assert "cascade depth 2" in rendered
        assert "depth=3" in rendered  # Next depth


# ---------------------------------------------------------------------------
# Cascade Composition
# ---------------------------------------------------------------------------


class TestComposeCascade:
    def test_basic_cascade(self):
        parent = compose_prompt(
            task_description="Research prompt engineering",
            telos="Build transmission-grade prompts",
            intent_thread=create_intent_thread("Improve agent depth"),
        )
        children = compose_cascade(
            parent_prompt=parent,
            subtasks=[
                {"task": "Research academic literature", "role": "researcher"},
                {"task": "Research multi-agent protocols", "role": "researcher"},
            ],
        )
        assert len(children) == 2
        for child in children:
            assert child.cascade_depth == parent.cascade_depth + 1
            assert child.intent_thread == parent.intent_thread
            assert child.telos == parent.telos

    def test_sibling_wiring(self):
        parent = compose_prompt(task_description="Parent task")
        children = compose_cascade(
            parent_prompt=parent,
            subtasks=[
                {"task": "Task A", "role": "agent_a"},
                {"task": "Task B", "role": "agent_b"},
                {"task": "Task C", "role": "agent_c"},
            ],
        )
        # First child has no sibling signals
        assert len(children[0].sibling_signals) == 0
        # Second child knows about first
        assert len(children[1].sibling_signals) == 1
        # Third child knows about first and second
        assert len(children[2].sibling_signals) == 2


# ---------------------------------------------------------------------------
# Template Composition
# ---------------------------------------------------------------------------


class TestComposeFromTemplate:
    @pytest.mark.parametrize("template_name", list(TEMPLATES.keys()))
    def test_all_templates_render(self, template_name: str):
        prompt = compose_from_template(
            template_name,
            task_description=f"Test task for {template_name}",
            telos="Testing TPP templates",
        )
        rendered = prompt.render()
        assert len(rendered) > 100
        assert "TELOS" in rendered
        assert "IDENTITY" in rendered

    def test_unknown_template_falls_back(self):
        prompt = compose_from_template(
            "nonexistent",
            task_description="Fallback test",
        )
        # Should use research template as default
        assert "investigated" in prompt.identity.lower()


# ---------------------------------------------------------------------------
# Prompt Evaluation
# ---------------------------------------------------------------------------


class TestEvaluatePrompt:
    def test_complete_prompt_high_tqs(self):
        prompt = compose_prompt(
            task_description="Analyze the R_V metric and produce a statistical report with effect sizes",
            telos="Validate geometric signatures to ship the COLM paper",
            identity="You are a research agent with experience in mechanistic interpretability.",
            context="The R_V metric measures participation ratio contraction in transformers.",
            technical="Use TransformerLens. Output markdown. Budget: 2000 tokens.",
            intent_thread=create_intent_thread("Ship R_V paper"),
            shakti_mode="jnana",
        )
        score = evaluate_prompt(prompt)
        assert score.transmission_quality_score > 0.4
        assert score.structural_completeness == 5.0
        assert score.telos_continuity == 5.0

    def test_empty_prompt_low_tqs(self):
        prompt = TPPPrompt(task="Do stuff")
        score = evaluate_prompt(prompt)
        assert score.transmission_quality_score < 0.3
        assert score.structural_completeness < 3

    def test_metrics_in_range(self):
        prompt = compose_from_template(
            "research",
            task_description="Research R_V contraction patterns",
            telos="Validate findings",
        )
        score = evaluate_prompt(prompt)
        for attr in [
            "information_density", "specificity", "measurability",
            "token_efficiency", "structural_completeness",
            "telos_continuity", "depth_ratio", "shakti_calibration",
        ]:
            val = getattr(score, attr)
            assert 0.0 <= val <= 5.0, f"{attr} = {val} out of range"
        assert 0.0 <= score.transmission_quality_score <= 1.0


# ---------------------------------------------------------------------------
# Quick Check
# ---------------------------------------------------------------------------


class TestQuickCheck:
    def test_complete_prompt_passes(self):
        prompt = compose_prompt(
            task_description="Analyze the R_V metric data across layers 20-30 of Mistral-7B and report effect sizes",
            telos="Validate geometric signatures",
            identity="MI researcher",
            context="Background info",
        )
        result = quick_check(prompt)
        assert result["passes"]
        assert result["telos"]
        assert result["structure"]

    def test_empty_prompt_fails(self):
        prompt = TPPPrompt(task="stuff")
        result = quick_check(prompt)
        assert not result["passes"]
        assert not result["telos"]


# ---------------------------------------------------------------------------
# Telos Continuity
# ---------------------------------------------------------------------------


class TestTelosContinuity:
    def test_passes_with_thread_and_telos(self):
        thread = create_intent_thread("Build the trading system")
        prompt = compose_prompt(
            task_description="Implement order router",
            telos="Build the trading system's core routing layer",
            intent_thread=thread,
        )
        passes, reason = verify_telos_continuity(prompt)
        assert passes

    def test_fails_without_telos(self):
        prompt = TPPPrompt(task="Do something")
        passes, reason = verify_telos_continuity(prompt)
        assert not passes

    def test_depth_0_ok_without_thread(self):
        prompt = TPPPrompt(telos="Root purpose", cascade_depth=0)
        passes, reason = verify_telos_continuity(prompt)
        assert passes

    def test_depth_1_fails_without_thread(self):
        prompt = TPPPrompt(telos="Child purpose", cascade_depth=1)
        passes, reason = verify_telos_continuity(prompt)
        assert not passes


# ---------------------------------------------------------------------------
# Handoff & Stigmergy Integration
# ---------------------------------------------------------------------------


class TestHandoffIntegration:
    def test_format_handoff(self):
        result = format_handoff_as_tpp(
            from_agent="researcher_1",
            from_role="researcher",
            findings="Found R_V contraction at layer 27 with d=-3.56",
            confidence=0.9,
            telos_alignment=0.85,
        )
        assert "researcher_1" in result
        assert "R_V contraction" in result
        assert "0.90" in result

    def test_format_handoff_with_thread(self):
        thread = create_intent_thread("Ship paper")
        result = format_handoff_as_tpp(
            from_agent="agent_1",
            from_role="writer",
            findings="Draft complete",
            intent_thread=thread,
        )
        assert thread.trace_id in result

    def test_format_stigmergy_tpp(self):
        mark = format_stigmergy_tpp(
            agent="builder_1",
            observation="Implemented semantic compression in context.py",
            telos_tag="transmission_depth",
            salience=0.8,
            connections=["context.py", "tpp.py"],
        )
        assert mark["agent"] == "builder_1"
        assert mark["telos_tag"] == "transmission_depth"
        assert mark["salience"] == 0.8
        assert len(mark["connections"]) == 2
        assert "tpp_version" in mark


# ---------------------------------------------------------------------------
# TPPPrompt rendering
# ---------------------------------------------------------------------------


class TestTPPPromptRender:
    def test_render_all_sections(self):
        prompt = compose_prompt(
            task_description="Full test",
            telos="Test telos",
            identity="Test identity",
            context="Test context",
            technical="Test technical",
            cascade_depth=1,
        )
        rendered = prompt.render()
        assert "## TELOS" in rendered
        assert "## IDENTITY" in rendered
        assert "## CONTEXT" in rendered
        assert "## TASK" in rendered
        assert "## TECHNICAL" in rendered

    def test_render_minimal(self):
        prompt = TPPPrompt(task="Just a task")
        rendered = prompt.render()
        assert "## TASK" in rendered
        assert "## TELOS" not in rendered  # No telos set

    def test_token_estimate(self):
        prompt = compose_prompt(
            task_description="A moderate length task description for token estimation",
            telos="Purpose",
            identity="Identity",
        )
        est = prompt.token_estimate()
        assert est > 10
        assert est < 10000

    def test_to_dict_roundtrip(self):
        prompt = compose_prompt(
            task_description="Dict test",
            telos="Test",
            intent_thread=create_intent_thread("Operator intent"),
        )
        data = prompt.to_dict()
        assert data["telos"] == "Test"
        assert data["intent_thread"]["operator_intent"] == "Operator intent"
        assert data["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# SiblingSignal
# ---------------------------------------------------------------------------


class TestSiblingSignal:
    def test_to_prompt_fragment(self):
        signal = SiblingSignal(
            agent_id="a1",
            agent_role="researcher",
            finding_summary="Important finding about X",
            confidence=0.8,
            telos_alignment=0.9,
        )
        frag = signal.to_prompt_fragment()
        assert "researcher" in frag
        assert "0.80" in frag
        assert "Important finding" in frag

    def test_max_chars_respected(self):
        signal = SiblingSignal(
            agent_id="a1",
            agent_role="researcher",
            finding_summary="x" * 1000,
        )
        frag = signal.to_prompt_fragment(max_chars=100)
        # Summary truncated but header always present
        assert len(frag) < 300
