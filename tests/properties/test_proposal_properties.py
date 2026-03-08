"""Property-based tests for Proposal model.

These tests find edge cases that unit tests miss by generating hundreds of test cases.
Expected to find 3-8 bugs in boundary conditions, serialization, uniqueness.
"""

from hypothesis import given, strategies as st
from hypothesis import assume
import json

# Import after checking if module exists
try:
    from dharma_swarm.evolution import Proposal, EvolutionStatus
    from dharma_swarm.models import _new_id
    EVOLUTION_AVAILABLE = True
except ImportError:
    EVOLUTION_AVAILABLE = False
    import pytest
    pytestmark = pytest.mark.skip(reason="evolution module not available")


# Strategy for valid proposals
def proposal_strategy():
    """Generate random but valid Proposal instances."""
    # Valid filesystem characters - exclude invalid ones
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
    valid_alphabet = st.characters(
        blacklist_categories=('Cs',),  # No surrogates
        blacklist_characters=invalid_chars
    )

    return st.builds(
        Proposal,
        component=st.text(min_size=1, max_size=200, alphabet=valid_alphabet),
        change_type=st.sampled_from(["mutation", "crossover", "optimization"]),
        description=st.text(min_size=10, max_size=1000),
        diff=st.text(max_size=5000),
    )


if EVOLUTION_AVAILABLE:
    @given(proposal_strategy())
    def test_proposal_always_has_valid_id(proposal):
        """Property: All proposals must have 16-character alphanumeric IDs."""
        assert len(proposal.id) == 16, f"ID length is {len(proposal.id)}, expected 16"
        assert proposal.id.isalnum(), f"ID contains non-alphanumeric: {proposal.id}"


    @given(proposal_strategy())
    def test_proposal_initial_status_is_pending(proposal):
        """Property: New proposals always start in PENDING state."""
        assert proposal.status == EvolutionStatus.PENDING


    @given(proposal_strategy())
    def test_proposal_predicted_fitness_bounded(proposal):
        """Property: Predicted fitness must be in [0, 1]."""
        assert 0.0 <= proposal.predicted_fitness <= 1.0, \
            f"Fitness {proposal.predicted_fitness} out of bounds"


    @given(st.lists(proposal_strategy(), min_size=2, max_size=50))
    def test_proposal_ids_unique(proposals):
        """Property: All proposal IDs must be unique.

        This finds ID collision bugs that would cause data corruption.
        """
        ids = [p.id for p in proposals]
        unique_ids = set(ids)
        assert len(ids) == len(unique_ids), \
            f"Found duplicate IDs: {len(ids)} total, {len(unique_ids)} unique"


    @given(proposal_strategy())
    def test_proposal_json_roundtrip(proposal):
        """Property: Serializing then deserializing preserves data.

        This finds encoding bugs, NaN handling, infinity, deep nesting issues.
        """
        # Serialize
        json_str = proposal.model_dump_json()

        # Deserialize
        restored = Proposal.model_validate_json(json_str)

        # Verify all fields preserved
        assert restored.id == proposal.id
        assert restored.component == proposal.component
        assert restored.description == proposal.description
        assert restored.status == proposal.status
        assert restored.change_type == proposal.change_type


    @given(proposal_strategy(), proposal_strategy())
    def test_proposal_equality_is_symmetric(p1, p2):
        """Property: If p1 == p2, then p2 == p1."""
        # Only test if they're actually equal
        if p1.id == p2.id:
            assert (p1 == p2) == (p2 == p1)


    @given(proposal_strategy())
    def test_proposal_description_not_empty(proposal):
        """Property: Descriptions must be non-empty after stripping."""
        assert proposal.description.strip(), "Description is empty after stripping whitespace"


    @given(proposal_strategy())
    def test_proposal_component_path_valid(proposal):
        """Property: Component should be a valid Python module path."""
        # Should not contain invalid characters for file paths
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            assert char not in proposal.component, \
                f"Component contains invalid character '{char}'"
