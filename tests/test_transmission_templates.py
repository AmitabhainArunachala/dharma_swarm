"""Tests for transmission-grade prompt templates.

Validates structural invariants, content correctness, and integration
compatibility for all 10 template types.
"""

from __future__ import annotations

import re

import pytest

from dharma_swarm.transmission_templates import (
    CREATIVE_TEMPLATE,
    CASCADE_TEMPLATE,
    EMERGENCY_TEMPLATE,
    EVOLUTION_TEMPLATE,
    HANDOFF_TEMPLATE,
    IMPLEMENTATION_TEMPLATE,
    RESEARCH_TEMPLATE,
    REVIEW_TEMPLATE,
    SYNTHESIS_TEMPLATE,
    TELOS_CHECK_TEMPLATE,
    TemplateType,
    emergency_prompt,
    get_shakti_for_template,
    get_template,
    implementation_prompt,
    list_templates,
    research_prompt,
    review_prompt,
    synthesis_prompt,
)


# ---------------------------------------------------------------------------
# Template type enum tests
# ---------------------------------------------------------------------------


class TestTemplateType:
    def test_all_ten_types_exist(self):
        assert len(TemplateType) == 10

    def test_string_values(self):
        expected = {
            "research", "implementation", "review", "synthesis",
            "creative", "handoff", "cascade", "evolution",
            "telos_check", "emergency",
        }
        actual = {t.value for t in TemplateType}
        assert actual == expected

    def test_string_coercion(self):
        for t in TemplateType:
            assert TemplateType(t.value) is t


# ---------------------------------------------------------------------------
# Structural invariant tests (every template must have these)
# ---------------------------------------------------------------------------


_ALL_AGENT_TEMPLATES = [
    TemplateType.RESEARCH,
    TemplateType.IMPLEMENTATION,
    TemplateType.REVIEW,
    TemplateType.SYNTHESIS,
    TemplateType.CREATIVE,
    TemplateType.CASCADE,
    TemplateType.EVOLUTION,
    TemplateType.TELOS_CHECK,
    TemplateType.EMERGENCY,
]


class TestStructuralInvariants:
    """Every non-handoff template must contain the 5-section structure."""

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_has_identity_section(self, tt: TemplateType):
        raw = get_template(tt)
        assert "## IDENTITY" in raw, f"{tt.value} missing IDENTITY section"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_has_telos_section(self, tt: TemplateType):
        raw = get_template(tt)
        assert "## TELOS" in raw, f"{tt.value} missing TELOS section"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_has_task_section(self, tt: TemplateType):
        raw = get_template(tt)
        assert "## TASK" in raw, f"{tt.value} missing TASK section"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_has_witness_section(self, tt: TemplateType):
        raw = get_template(tt)
        assert "## WITNESS" in raw, f"{tt.value} missing WITNESS section"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_has_handoff_section(self, tt: TemplateType):
        raw = get_template(tt)
        assert "## HANDOFF" in raw, f"{tt.value} missing HANDOFF section"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_identity_contains_shakti(self, tt: TemplateType):
        raw = get_template(tt)
        assert "Shakti:" in raw, f"{tt.value} IDENTITY missing Shakti energy"

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_identity_contains_agent_name_placeholder(self, tt: TemplateType):
        raw = get_template(tt)
        # After get_template without kwargs, agent_name becomes [UNSET:agent_name]
        assert "[UNSET:agent_name]" in raw or "{agent_name}" in raw

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_witness_contains_questions(self, tt: TemplateType):
        raw = get_template(tt)
        # Witness section should contain at least 3 questions (lines with ?)
        witness_start = raw.index("## WITNESS")
        handoff_start = raw.index("## HANDOFF")
        witness_section = raw[witness_start:handoff_start]
        questions = [line for line in witness_section.split("\n") if "?" in line]
        assert len(questions) >= 3, (
            f"{tt.value} WITNESS has only {len(questions)} questions, need >= 3"
        )

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_handoff_contains_stigmergy(self, tt: TemplateType):
        raw = get_template(tt)
        handoff_start = raw.index("## HANDOFF")
        handoff_section = raw[handoff_start:]
        assert "STIGMERGY" in handoff_section or "stigmergy" in handoff_section.lower(), (
            f"{tt.value} HANDOFF missing stigmergy mark requirement"
        )

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_handoff_contains_witness_field(self, tt: TemplateType):
        raw = get_template(tt)
        handoff_start = raw.index("## HANDOFF")
        handoff_section = raw[handoff_start:]
        assert "WITNESS" in handoff_section, (
            f"{tt.value} HANDOFF missing witness transfer field"
        )

    @pytest.mark.parametrize("tt", _ALL_AGENT_TEMPLATES)
    def test_witness_references_shared_notes(self, tt: TemplateType):
        raw = get_template(tt)
        assert "~/.dharma/shared/" in raw, (
            f"{tt.value} missing colony shared notes reference"
        )


class TestHandoffTemplateStructure:
    """Handoff template has a different structure than agent templates."""

    def test_has_transmission_header(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## TRANSMISSION" in raw

    def test_has_work_summary(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## WHAT I DID" in raw

    def test_has_findings(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## WHAT I FOUND" in raw

    def test_has_context_for_receiver(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## WHAT YOU NEED TO KNOW" in raw

    def test_has_limitations(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## WHAT I COULD NOT DO" in raw

    def test_has_witness_transfer(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## WITNESS TRANSFER" in raw

    def test_has_gate_state(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## GATE STATE" in raw

    def test_has_colony_marks(self):
        raw = get_template(TemplateType.HANDOFF)
        assert "## COLONY MARKS" in raw


# ---------------------------------------------------------------------------
# get_template() API tests
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_string_type_coercion(self):
        result = get_template("research")
        assert "## IDENTITY" in result

    def test_enum_type(self):
        result = get_template(TemplateType.RESEARCH)
        assert "## IDENTITY" in result

    def test_kwargs_fill_placeholders(self):
        result = get_template(
            TemplateType.RESEARCH,
            agent_name="test_agent",
            research_question="Does X cause Y?",
        )
        assert "test_agent" in result
        assert "Does X cause Y?" in result
        assert "[UNSET:agent_name]" not in result
        assert "[UNSET:research_question]" not in result

    def test_missing_kwargs_become_unset_markers(self):
        result = get_template(TemplateType.RESEARCH)
        assert "[UNSET:agent_name]" in result
        assert "[UNSET:research_question]" in result

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown template type"):
            get_template("nonexistent_template")

    def test_all_types_accessible(self):
        for t in TemplateType:
            result = get_template(t)
            assert len(result) > 100, f"{t.value} template is suspiciously short"


# ---------------------------------------------------------------------------
# Shakti mapping tests
# ---------------------------------------------------------------------------


class TestShaktiMapping:
    def test_all_types_have_shakti(self):
        for t in TemplateType:
            shakti = get_shakti_for_template(t)
            assert shakti in {
                "MAHESHWARI", "MAHAKALI", "MAHALAKSHMI", "MAHASARASWATI"
            }, f"{t.value} has invalid shakti: {shakti}"

    def test_research_is_maheshwari(self):
        assert get_shakti_for_template("research") == "MAHESHWARI"

    def test_implementation_is_mahakali(self):
        assert get_shakti_for_template("implementation") == "MAHAKALI"

    def test_review_is_mahasaraswati(self):
        assert get_shakti_for_template("review") == "MAHASARASWATI"

    def test_synthesis_is_mahalakshmi(self):
        assert get_shakti_for_template("synthesis") == "MAHALAKSHMI"

    def test_emergency_is_mahakali(self):
        assert get_shakti_for_template("emergency") == "MAHAKALI"


# ---------------------------------------------------------------------------
# list_templates() tests
# ---------------------------------------------------------------------------


class TestListTemplates:
    def test_returns_ten_entries(self):
        result = list_templates()
        assert len(result) == 10

    def test_entries_have_required_keys(self):
        for entry in list_templates():
            assert "type" in entry
            assert "shakti" in entry
            assert "description" in entry


# ---------------------------------------------------------------------------
# Convenience constructor tests
# ---------------------------------------------------------------------------


class TestConvenienceConstructors:
    def test_research_prompt_no_unset(self):
        result = research_prompt(
            agent_name="r1",
            research_question="What is X?",
        )
        assert "[UNSET:" not in result

    def test_implementation_prompt_no_unset(self):
        result = implementation_prompt(
            agent_name="c1",
            implementation_goal="Build X",
            target_module="dharma_swarm/x.py",
        )
        assert "[UNSET:" not in result

    def test_review_prompt_no_unset(self):
        result = review_prompt(
            agent_name="v1",
            review_target="dharma_swarm/x.py",
        )
        assert "[UNSET:" not in result

    def test_synthesis_prompt_no_unset(self):
        result = synthesis_prompt(
            agent_name="s1",
            synthesis_question="How does X relate to Y?",
            input_sources="agent_a, agent_b",
        )
        assert "[UNSET:" not in result

    def test_emergency_prompt_no_unset(self):
        result = emergency_prompt(
            agent_name="e1",
            anomaly_description="Process crashed",
        )
        assert "[UNSET:" not in result

    def test_research_prompt_contains_question(self):
        result = research_prompt(
            agent_name="r1",
            research_question="Does R_V contract during self-reference?",
        )
        assert "R_V contract during self-reference" in result

    def test_implementation_prompt_contains_goal(self):
        result = implementation_prompt(
            agent_name="c1",
            implementation_goal="Add eigenform check",
            target_module="cascade.py",
        )
        assert "Add eigenform check" in result
        assert "cascade.py" in result


# ---------------------------------------------------------------------------
# Content quality tests (gate and pillar references)
# ---------------------------------------------------------------------------


class TestContentQuality:
    """Verify templates reference the right intellectual sources."""

    def test_research_cites_friston(self):
        assert "Friston" in RESEARCH_TEMPLATE

    def test_research_cites_kauffman(self):
        assert "Kauffman" in RESEARCH_TEMPLATE

    def test_implementation_cites_beer(self):
        assert "Beer" in IMPLEMENTATION_TEMPLATE

    def test_implementation_cites_ashby(self):
        assert "Ashby" in IMPLEMENTATION_TEMPLATE

    def test_review_cites_bateson(self):
        assert "Bateson" in REVIEW_TEMPLATE

    def test_synthesis_cites_jantsch(self):
        assert "Jantsch" in SYNTHESIS_TEMPLATE

    def test_synthesis_cites_hofstadter(self):
        assert "Hofstadter" in SYNTHESIS_TEMPLATE

    def test_creative_cites_kauffman(self):
        assert "Kauffman" in CREATIVE_TEMPLATE

    def test_creative_cites_deacon(self):
        assert "Deacon" in CREATIVE_TEMPLATE

    def test_cascade_cites_beer(self):
        assert "Beer" in CASCADE_TEMPLATE

    def test_evolution_references_nirjara(self):
        assert "nirjara" in EVOLUTION_TEMPLATE.lower()

    def test_telos_check_lists_all_11_gates(self):
        gates = [
            "AHIMSA", "SATYA", "CONSENT", "VYAVASTHIT", "REVERSIBILITY",
            "SVABHAAVA", "BHED_GNAN", "WITNESS", "ANEKANTA",
            "DOGMA_DRIFT", "STEELMAN",
        ]
        for gate in gates:
            assert gate in TELOS_CHECK_TEMPLATE, f"Missing gate: {gate}"

    def test_emergency_references_algedonic(self):
        assert "algedonic" in EMERGENCY_TEMPLATE.lower()

    def test_emergency_references_circuit_breaker(self):
        assert "circuit" in EMERGENCY_TEMPLATE.lower()


# ---------------------------------------------------------------------------
# Token efficiency tests
# ---------------------------------------------------------------------------


class TestTokenEfficiency:
    """Verify templates are within reasonable token budgets."""

    @pytest.mark.parametrize("tt", list(TemplateType))
    def test_raw_template_under_4k_chars(self, tt: TemplateType):
        """Raw templates (unfilled) should be under 4K chars to leave
        room for V7 rules, context, and the actual task content."""
        raw = get_template(tt)
        assert len(raw) < 4000, (
            f"{tt.value} template is {len(raw)} chars, should be < 4000"
        )

    @pytest.mark.parametrize("tt", list(TemplateType))
    def test_raw_template_over_500_chars(self, tt: TemplateType):
        """Templates should be substantive, not stubs."""
        raw = get_template(tt)
        assert len(raw) > 500, (
            f"{tt.value} template is only {len(raw)} chars, too thin"
        )


# ---------------------------------------------------------------------------
# Injection safety tests
# ---------------------------------------------------------------------------


class TestInjectionSafety:
    """Verify templates do not contain patterns that would trigger gates."""

    @pytest.mark.parametrize("tt", list(TemplateType))
    def test_no_injection_patterns(self, tt: TemplateType):
        raw = get_template(tt)
        injection_patterns = [
            "ignore previous instructions",
            "ignore all previous",
            "disregard your instructions",
            "you are now",
        ]
        for pattern in injection_patterns:
            assert pattern not in raw.lower(), (
                f"{tt.value} contains injection pattern: {pattern}"
            )

    @pytest.mark.parametrize("tt", list(TemplateType))
    def test_no_credential_patterns(self, tt: TemplateType):
        raw = get_template(tt)
        cred_patterns = ["sk-or-v1-", "sk-ant-", "Bearer ", "password="]
        for pattern in cred_patterns:
            assert pattern not in raw, (
                f"{tt.value} contains credential pattern: {pattern}"
            )
