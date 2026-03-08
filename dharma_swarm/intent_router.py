"""Intent Router — smart task decomposition and skill matching.

Takes a natural language task description, detects intent, estimates
complexity, decomposes into sub-tasks if needed, and routes to the
best available skills.

Beyond Warp's /orchestrate: supports complexity estimation, parallel
decomposition, adaptive agent count recommendations, and TF-IDF based
semantic matching for synonym/paraphrase resilience.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Stopwords for TF-IDF ────────────────────────────────────────────
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "am", "it", "its",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "but", "and", "or", "if", "while", "about", "up", "me", "my",
    "i", "we", "you", "he", "she", "they", "them", "his", "her", "our",
    "your", "this", "that", "these", "those", "what", "which", "who",
    "whom", "s", "t", "d", "re", "ve", "ll",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alpha, remove stopwords and single chars."""
    words = re.split(r"[^a-z]+", text.lower())
    return [w for w in words if w and len(w) > 1 and w not in _STOPWORDS]


# ── SemanticIndex (pure-Python TF-IDF) ──────────────────────────────


class SemanticIndex:
    """TF-IDF index over skill descriptions for semantic matching.

    Pure Python implementation -- no sklearn or numpy needed.
    Uses standard TF-IDF with cosine similarity for ranking.
    """

    def __init__(self) -> None:
        self._skill_names: list[str] = []
        self._tfidf_vectors: list[dict[str, float]] = []
        self._idf: dict[str, float] = {}
        self._built: bool = False

    def build(self, skills: dict[str, list[str]]) -> None:
        """Build TF-IDF index from skill corpus.

        Args:
            skills: Mapping of skill_name -> list of descriptive words
                    (description tokens + keywords + tags).
        """
        if not skills:
            self._built = True
            return

        self._skill_names = list(skills.keys())

        # Compute document frequencies
        n_docs = len(skills)
        doc_freq: Counter[str] = Counter()
        term_freqs: list[Counter[str]] = []

        for name in self._skill_names:
            tokens = _tokenize(" ".join(skills[name]))
            tf = Counter(tokens)
            term_freqs.append(tf)
            for term in set(tokens):
                doc_freq[term] += 1

        # IDF = log(N / df) -- standard formulation
        self._idf = {
            term: math.log(n_docs / df) if df < n_docs else 0.0
            for term, df in doc_freq.items()
        }

        # TF-IDF vectors for each skill (L2-normalized)
        self._tfidf_vectors = []
        for tf in term_freqs:
            vec: dict[str, float] = {}
            for term, count in tf.items():
                idf = self._idf.get(term, 0.0)
                vec[term] = count * idf
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec.values())) if vec else 0.0
            if norm > 0:
                vec = {k: v / norm for k, v in vec.items()}
            self._tfidf_vectors.append(vec)

        self._built = True
        logger.debug("SemanticIndex built: %d skills, %d terms",
                      n_docs, len(self._idf))

    def query(self, text: str, top_k: int = 3) -> list[tuple[str, float]]:
        """Query the index with free text.

        Args:
            text: Natural language query.
            top_k: Maximum results to return.

        Returns:
            List of (skill_name, cosine_similarity) sorted descending.
        """
        if not self._built or not self._skill_names:
            return []

        tokens = _tokenize(text)
        if not tokens:
            return []

        # Build query TF-IDF vector
        tf = Counter(tokens)
        q_vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = self._idf.get(term, 0.0)
            q_vec[term] = count * idf

        # L2 normalize query vector
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) if q_vec else 0.0
        if q_norm == 0:
            return []
        q_vec = {k: v / q_norm for k, v in q_vec.items()}

        # Cosine similarity against each skill vector
        results: list[tuple[str, float]] = []
        for idx, skill_vec in enumerate(self._tfidf_vectors):
            dot = sum(q_vec.get(k, 0.0) * v for k, v in skill_vec.items())
            if dot > 0:
                results.append((self._skill_names[idx], dot))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


class Complexity(str, Enum):
    """Task complexity levels."""
    TRIVIAL = "trivial"      # Single action, < 1 min
    SIMPLE = "simple"        # Few actions, < 5 min
    MODERATE = "moderate"    # Multi-step, 5-30 min
    COMPLEX = "complex"      # Multi-file, multi-agent, 30+ min
    EPIC = "epic"            # System-wide, requires orchestration


class TaskIntent(BaseModel):
    """Analyzed intent for a single task or sub-task."""

    task: str
    primary_skill: str = ""
    confidence: float = 0.0
    complexity: str = "moderate"
    recommended_agents: int = 1
    parallel: bool = False
    risk_level: str = "low"  # low/medium/high/critical
    tags: list[str] = Field(default_factory=list)


class DecomposedTask(BaseModel):
    """A complex task broken into sub-tasks with dependencies."""

    original: str
    sub_tasks: list[TaskIntent] = Field(default_factory=list)
    total_agents: int = 1
    has_parallel_work: bool = False
    estimated_complexity: str = "moderate"


# ── Keyword Maps ──────────────────────────────────────────────────────

# Extended descriptions for semantic matching — richer than keywords alone.
# These feed the TF-IDF index to catch synonyms and paraphrases that
# exact keyword matching misses.
_SKILL_DESCRIPTIONS: dict[str, str] = {
    "cartographer": (
        "scan map discover explore ecosystem paths manifest inventory "
        "survey catalog traverse navigate topology structure layout "
        "directory files folders project codebase overview reconnaissance"
    ),
    "surgeon": (
        "fix bug patch repair debug error broken failing crash issue "
        "hotfix diagnose remedy resolve troubleshoot defect fault "
        "malfunction incorrect wrong regression"
    ),
    "architect": (
        "design plan architecture refactor restructure system module "
        "component interface api blueprint schema organize pattern "
        "framework abstraction layer separation concerns"
    ),
    "archeologist": (
        "research read analyze understand history vault psmv investigate "
        "dig find examine inspect study explore audit review scrutinize "
        "codebase legacy documentation knowledge unearth"
    ),
    "validator": (
        "test verify validate check assert pytest coverage qa quality "
        "suite unittest integration regression acceptance smoke "
        "specification correctness assurance"
    ),
    "researcher": (
        "paper experiment measure data statistical correlation hypothesis "
        "rv mech-interp analysis results findings publication journal "
        "methodology sample observation"
    ),
    "builder": (
        "build implement create write code feature add new develop ship "
        "construct assemble craft produce generate fabricate engineer "
        "scaffold prototype"
    ),
    "deployer": (
        "deploy ship release publish push production staging ci cd "
        "package distribute launch rollout delivery pipeline "
        "infrastructure provision"
    ),
    "monitor": (
        "health status monitor alert anomaly performance metrics "
        "dashboard observe watchdog heartbeat uptime latency throughput "
        "logging telemetry surveillance"
    ),
}

# Map keywords to skill names — expanded as skills are discovered
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "cartographer": [
        "scan", "map", "discover", "explore", "ecosystem", "paths",
        "manifest", "inventory", "survey", "catalog",
    ],
    "surgeon": [
        "fix", "bug", "patch", "repair", "debug", "error",
        "broken", "failing", "crash", "issue", "hotfix",
    ],
    "architect": [
        "design", "plan", "architecture", "refactor", "restructure",
        "system", "module", "component", "interface", "api",
    ],
    "archeologist": [
        "research", "read", "analyze", "understand", "history",
        "vault", "psmv", "investigate", "dig", "find",
    ],
    "validator": [
        "test", "verify", "validate", "check", "assert",
        "pytest", "coverage", "qa", "quality",
    ],
    "researcher": [
        "paper", "experiment", "measure", "data", "statistical",
        "correlation", "hypothesis", "rv", "mech-interp",
    ],
    "builder": [
        "build", "implement", "create", "write", "code",
        "feature", "add", "new", "develop", "ship",
    ],
    "deployer": [
        "deploy", "ship", "release", "publish", "push",
        "production", "staging", "ci", "cd", "package",
    ],
    "monitor": [
        "health", "status", "monitor", "alert", "anomaly",
        "performance", "metrics", "dashboard", "observe",
    ],
}

# Complexity signals
_COMPLEXITY_SIGNALS = {
    "epic": [
        "entire system", "all modules", "full rewrite", "migration",
        "cross-architecture", "multi-model", "everything",
    ],
    "complex": [
        "multiple files", "refactor", "redesign", "integrate",
        "pipeline", "multi-step", "orchestrate", "parallel",
    ],
    "moderate": [
        "add feature", "implement", "extend", "modify", "update",
        "change", "improve", "enhance",
    ],
    "simple": [
        "fix typo", "rename", "small change", "tweak", "adjust",
        "update version", "add comment",
    ],
    "trivial": [
        "print", "log", "check", "read", "list", "show", "display",
    ],
}

# Risk signals
_RISK_SIGNALS = {
    "critical": [
        "delete", "drop", "destroy", "rm -rf", "force push",
        "production", "credentials", "secrets",
    ],
    "high": [
        "overwrite", "replace all", "migrate", "schema change",
        "breaking change", "api change", "deploy", "push", "publish",
    ],
    "medium": [
        "modify", "refactor", "restructure", "update dependency",
        "change config",
    ],
}

# Decomposition patterns — tasks that should be split
_DECOMPOSITION_PATTERNS: list[str] = [
    r"(.+)\s+(?:and|then|also|plus)\s+(.+)",
    r"(.+),\s+(.+),\s+(?:and\s+)?(.+)",
]


class IntentRouter:
    """Routes tasks to skills via intent detection and decomposition.

    Combines keyword matching (fast, exact) with optional TF-IDF semantic
    matching (catches synonyms and paraphrases keywords miss).
    """

    def __init__(self, registry=None, *, enable_semantic: bool = True):
        """Initialize with optional SkillRegistry and semantic index.

        Args:
            registry: Optional SkillRegistry for dynamic skill matching.
            enable_semantic: If True, build a SemanticIndex from the keyword
                map (and registry skills if available). Defaults to True.
        """
        self._registry = registry
        self._keyword_map = dict(_INTENT_KEYWORDS)
        self._semantic: SemanticIndex | None = None

        if enable_semantic:
            self._semantic = self._build_semantic_index()

    def _build_semantic_index(self) -> SemanticIndex:
        """Build a SemanticIndex from keyword map, descriptions, and registry."""
        corpus: dict[str, list[str]] = {}

        # Seed from keyword map + extended descriptions
        for skill_name, keywords in self._keyword_map.items():
            desc = _SKILL_DESCRIPTIONS.get(skill_name, "")
            corpus[skill_name] = list(keywords) + desc.split()

        # Merge registry skills if available
        if self._registry:
            for skill in self._registry.list_all():
                existing = corpus.get(skill.name, [])
                desc_tokens = skill.description.split() if skill.description else []
                existing.extend(skill.keywords)
                existing.extend(skill.tags)
                existing.extend(desc_tokens)
                corpus[skill.name] = existing

        index = SemanticIndex()
        index.build(corpus)
        return index

    def analyze(self, task: str) -> TaskIntent:
        """Analyze a single task's intent.

        Combines keyword scoring with optional TF-IDF semantic matching.
        Returns TaskIntent with best skill match, complexity, risk.
        """
        task_lower = task.lower()

        # Match skills by keywords
        scores: dict[str, float] = {}
        keyword_hits: dict[str, list[str]] = {}
        for skill_name, keywords in self._keyword_map.items():
            hits = [kw for kw in keywords if kw in task_lower]
            score = len(hits) * 2.0
            if score > 0:
                scores[skill_name] = score
                keyword_hits[skill_name] = hits

        # Semantic matching (additive)
        if self._semantic is not None:
            semantic_results = self._semantic.query(task, top_k=5)
            for skill_name, sim_score in semantic_results:
                current = scores.get(skill_name, 0.0)
                scores[skill_name] = current + sim_score * 3.0

        # Also match from registry if available
        if self._registry:
            registry_matches = self._registry.match(task, top_k=3)
            for skill in registry_matches:
                current = scores.get(skill.name, 0)
                scores[skill.name] = current + 5.0  # Registry match bonus

        # Best match
        best_skill = ""
        best_score = 0.0
        for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            best_skill = name
            best_score = score
            break

        confidence = min(best_score / 10.0, 1.0) if best_score > 0 else 0.0

        # Complexity estimation
        complexity = self._estimate_complexity(task_lower)

        # Risk assessment
        risk = self._assess_risk(task_lower)

        # Agent count recommendation
        agents = self._recommend_agents(complexity)

        return TaskIntent(
            task=task,
            primary_skill=best_skill,
            confidence=confidence,
            complexity=complexity,
            recommended_agents=agents,
            parallel=agents > 1,
            risk_level=risk,
        )

    def explain(self, task: str) -> dict:
        """Explain routing decision for a task.

        Returns a dict with keyword_matches, semantic_matches,
        final_skill, and confidence for debugging and transparency.
        """
        task_lower = task.lower()

        # Keyword matches
        keyword_matches: dict[str, list[str]] = {}
        keyword_scores: dict[str, float] = {}
        for skill_name, keywords in self._keyword_map.items():
            hits = [kw for kw in keywords if kw in task_lower]
            if hits:
                keyword_matches[skill_name] = hits
                keyword_scores[skill_name] = len(hits) * 2.0

        # Semantic matches
        semantic_matches: list[tuple[str, float]] = []
        if self._semantic is not None:
            semantic_matches = self._semantic.query(task, top_k=3)

        # Combined scores
        combined: dict[str, float] = dict(keyword_scores)
        for skill_name, sim_score in semantic_matches:
            current = combined.get(skill_name, 0.0)
            combined[skill_name] = current + sim_score * 3.0

        # Winner
        if combined:
            best_skill = max(combined, key=combined.get)  # type: ignore[arg-type]
            best_score = combined[best_skill]
        else:
            best_skill = ""
            best_score = 0.0

        confidence = min(best_score / 10.0, 1.0) if best_score > 0 else 0.0

        return {
            "keyword_matches": keyword_matches,
            "semantic_matches": [
                {"skill": name, "score": round(score, 4)}
                for name, score in semantic_matches
            ],
            "final_skill": best_skill,
            "confidence": round(confidence, 4),
        }

    def decompose(self, task: str) -> DecomposedTask:
        """Decompose a complex task into sub-tasks.

        Uses pattern matching to split compound tasks, then analyzes
        each sub-task independently.
        """
        sub_texts = self._split_task(task)

        if len(sub_texts) <= 1:
            # Single task — just analyze it
            intent = self.analyze(task)
            return DecomposedTask(
                original=task,
                sub_tasks=[intent],
                total_agents=intent.recommended_agents,
                has_parallel_work=False,
                estimated_complexity=intent.complexity,
            )

        # Multiple sub-tasks
        sub_tasks = [self.analyze(st) for st in sub_texts]

        # Check for parallelism (sub-tasks with different skills can run in parallel)
        skills_used = {st.primary_skill for st in sub_tasks if st.primary_skill}
        has_parallel = len(skills_used) > 1

        total_agents = sum(st.recommended_agents for st in sub_tasks)
        if has_parallel:
            # Parallel tasks share some agents
            total_agents = max(total_agents // 2, len(sub_tasks))

        # Overall complexity is the max of sub-task complexities
        complexity_order = ["trivial", "simple", "moderate", "complex", "epic"]
        max_complexity = max(
            sub_tasks,
            key=lambda st: complexity_order.index(st.complexity)
            if st.complexity in complexity_order else 2,
        ).complexity

        return DecomposedTask(
            original=task,
            sub_tasks=sub_tasks,
            total_agents=min(total_agents, 7),  # Cap at 7 agents
            has_parallel_work=has_parallel,
            estimated_complexity=max_complexity,
        )

    def route(self, task: str) -> tuple[str, TaskIntent]:
        """Route a task to the best skill. Returns (skill_name, intent)."""
        intent = self.analyze(task)
        return (intent.primary_skill or "general", intent)

    def _estimate_complexity(self, task_lower: str) -> str:
        """Estimate task complexity from text signals."""
        for level in ["epic", "complex", "moderate", "simple", "trivial"]:
            signals = _COMPLEXITY_SIGNALS.get(level, [])
            if any(s in task_lower for s in signals):
                return level
        return "moderate"

    def _assess_risk(self, task_lower: str) -> str:
        """Assess risk level of a task."""
        for level in ["critical", "high", "medium"]:
            signals = _RISK_SIGNALS.get(level, [])
            if any(s in task_lower for s in signals):
                return level
        return "low"

    def _recommend_agents(self, complexity: str) -> int:
        """Recommend agent count based on complexity."""
        return {
            "trivial": 1,
            "simple": 1,
            "moderate": 1,
            "complex": 3,
            "epic": 5,
        }.get(complexity, 1)

    def _split_task(self, task: str) -> list[str]:
        """Split a compound task into sub-tasks."""
        for pattern in _DECOMPOSITION_PATTERNS:
            match = re.match(pattern, task, re.IGNORECASE)
            if match:
                return [g.strip() for g in match.groups() if g.strip()]
        return [task]
