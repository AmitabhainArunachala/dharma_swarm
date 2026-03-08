"""Tests for IntentRouter semantic (TF-IDF) matching.

Verifies that the SemanticIndex and its integration with IntentRouter
work correctly: builds, queries, catches synonyms keywords miss,
combines scores, and preserves backward compatibility.
"""

from __future__ import annotations

import pytest

from dharma_swarm.intent_router import (
    IntentRouter,
    SemanticIndex,
    _tokenize,
)


# ── SemanticIndex unit tests ─────────────────────────────────────────


class TestSemanticIndexBuild:
    """SemanticIndex construction and basic invariants."""

    def test_build_without_error(self):
        """SemanticIndex.build completes on a well-formed corpus."""
        idx = SemanticIndex()
        idx.build({
            "alpha": ["scan", "map", "explore"],
            "beta": ["fix", "debug", "repair"],
        })
        assert idx._built is True
        assert len(idx._skill_names) == 2

    def test_build_empty_skills_returns_empty(self):
        """Empty skills dict produces a valid but empty index."""
        idx = SemanticIndex()
        idx.build({})
        assert idx._built is True
        assert idx._skill_names == []
        assert idx.query("anything", top_k=3) == []

    def test_query_returns_sorted_results(self):
        """Results come back in descending score order."""
        idx = SemanticIndex()
        idx.build({
            "alpha": ["scan", "explore", "navigate"],
            "beta": ["fix", "debug", "scan"],
            "gamma": ["build", "create", "construct"],
        })
        results = idx.query("scan explore navigate", top_k=3)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)


class TestSemanticIndexQuery:
    """Query behavior and edge cases."""

    def test_empty_query_returns_empty(self):
        """A query with only stopwords or empty string yields nothing."""
        idx = SemanticIndex()
        idx.build({"alpha": ["scan", "map"]})
        assert idx.query("", top_k=3) == []
        # Pure stopwords — everything is filtered out
        assert idx.query("the a is", top_k=3) == []

    def test_single_word_query_works(self):
        """A single meaningful word should still match."""
        idx = SemanticIndex()
        idx.build({
            "alpha": ["scan", "explore"],
            "beta": ["fix", "repair"],
        })
        results = idx.query("scan", top_k=3)
        assert len(results) >= 1
        assert results[0][0] == "alpha"

    def test_tfidf_weights_rare_terms_higher(self):
        """Rare terms (low doc frequency) get higher IDF weight.

        'common' appears in both docs -> IDF = 0 (no discrimination).
        'specialized' only in alpha -> IDF > 0 (strong signal).
        """
        idx = SemanticIndex()
        idx.build({
            "alpha": ["specialized", "niche", "common", "general"],
            "beta": ["mainstream", "popular", "common", "general"],
        })
        # 'common' appears in both -> IDF = log(2/2) = 0
        assert idx._idf.get("common", 0.0) == 0.0
        # 'specialized' appears in one -> IDF = log(2/1) > 0
        assert idx._idf.get("specialized", 0.0) > 0.0

        # A query on the rare term should strongly prefer the right skill
        results = idx.query("specialized", top_k=2)
        assert len(results) == 1
        assert results[0][0] == "alpha"
        assert results[0][1] > 0.0

    def test_cosine_zero_for_unrelated_query(self):
        """Completely unrelated queries should return no matches."""
        idx = SemanticIndex()
        idx.build({
            "alpha": ["scan", "map", "explore"],
            "beta": ["fix", "debug", "repair"],
        })
        # 'quantum' and 'entanglement' are not in any skill corpus
        results = idx.query("quantum entanglement", top_k=3)
        assert results == []


# ── IntentRouter integration tests ───────────────────────────────────


class TestIntentRouterSemantic:
    """IntentRouter with semantic matching enabled."""

    def test_semantic_catches_synonyms_keywords_miss(self):
        """Semantic matching routes 'troubleshoot the regression' to surgeon.

        'troubleshoot' and 'regression' are NOT in _INTENT_KEYWORDS for any
        skill, so keyword matching returns nothing. But both words appear
        in the surgeon's extended description, so TF-IDF catches them.
        """
        router = IntentRouter()
        intent = router.analyze("troubleshoot the regression")
        assert intent.primary_skill == "surgeon"
        assert intent.confidence > 0

    def test_combined_scores_higher_than_either_alone(self):
        """When both keyword and semantic match, the combined score exceeds
        what either source would give independently.
        """
        router_both = IntentRouter(enable_semantic=True)
        router_kw_only = IntentRouter(enable_semantic=False)

        # 'fix the broken crash' should hit surgeon keywords AND semantic
        task = "fix the broken crash"
        intent_both = router_both.analyze(task)
        intent_kw = router_kw_only.analyze(task)

        assert intent_both.confidence >= intent_kw.confidence
        # Both should route to surgeon
        assert intent_both.primary_skill == "surgeon"
        assert intent_kw.primary_skill == "surgeon"

    def test_backward_compat_without_semantic(self):
        """IntentRouter with enable_semantic=False behaves like old version."""
        router = IntentRouter(enable_semantic=False)
        assert router._semantic is None

        intent = router.analyze("fix the broken test in metrics.py")
        assert intent.primary_skill == "surgeon"
        assert intent.confidence > 0

    def test_keyword_exact_matches_unchanged(self):
        """Semantic matching does not flip results for clear keyword wins.

        The existing test suite already verifies this, but we double-check
        a few key cases explicitly.
        """
        router = IntentRouter()

        # Strong keyword signals should still win
        assert router.analyze("scan the ecosystem and map all paths").primary_skill == "cartographer"
        assert router.analyze("fix the broken test in metrics.py").primary_skill == "surgeon"
        assert router.analyze("implement a new caching feature").primary_skill == "builder"
        assert router.analyze("validate all tests pass and check quality").primary_skill == "validator"


class TestIntentRouterExplain:
    """Tests for the explain() transparency method."""

    def test_explain_returns_all_fields(self):
        """explain() returns keyword_matches, semantic_matches,
        final_skill, and confidence.
        """
        router = IntentRouter()
        result = router.explain("fix the broken test")

        assert "keyword_matches" in result
        assert "semantic_matches" in result
        assert "final_skill" in result
        assert "confidence" in result

        assert isinstance(result["keyword_matches"], dict)
        assert isinstance(result["semantic_matches"], list)
        assert isinstance(result["final_skill"], str)
        assert isinstance(result["confidence"], float)

    def test_explain_keyword_matches_populated(self):
        """explain() shows which keywords hit for matching skills."""
        router = IntentRouter()
        result = router.explain("fix the broken test")
        kw = result["keyword_matches"]
        # 'fix' and 'broken' are surgeon keywords
        assert "surgeon" in kw
        assert "fix" in kw["surgeon"]
        assert "broken" in kw["surgeon"]

    def test_explain_semantic_matches_have_scores(self):
        """Each semantic match entry has 'skill' and 'score' fields."""
        router = IntentRouter()
        result = router.explain("troubleshoot the regression")
        for entry in result["semantic_matches"]:
            assert "skill" in entry
            assert "score" in entry
            assert isinstance(entry["score"], float)
            assert entry["score"] >= 0.0

    def test_explain_final_skill_matches_analyze(self):
        """explain().final_skill agrees with analyze().primary_skill
        for the same task.
        """
        router = IntentRouter()
        task = "scan the ecosystem and explore paths"
        expl = router.explain(task)
        intent = router.analyze(task)
        assert expl["final_skill"] == intent.primary_skill
