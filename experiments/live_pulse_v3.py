"""
Live Pulse v3 — Frontier Synthesis with LLM Judge

Tests the Transcendence Principle: does synthesis of diverse frontier models
beat the best individual model, as scored by an LLM judge?

Replaces the keyword counter from v2 with a real LLM evaluator.
"""

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

# Models to compete (diverse families)
FRONTIER_MODELS = [
    # (name, provider_base_url, model_id, api_key)
    ("DeepSeek-V3", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat-v3-0324", OPENROUTER_KEY),
    ("Qwen3-235B", "https://openrouter.ai/api/v1", "qwen/qwen3-235b-a22b", OPENROUTER_KEY),
    ("Llama4-Maverick", "https://openrouter.ai/api/v1", "meta-llama/llama-4-maverick:free", OPENROUTER_KEY),
    ("Gemini-2.5-Flash", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash-preview", OPENROUTER_KEY),
    ("Mistral-Medium-3", "https://openrouter.ai/api/v1", "mistralai/mistral-medium-3", OPENROUTER_KEY),
    ("Grok-3-Mini", "https://openrouter.ai/api/v1", "x-ai/grok-3-mini-beta", OPENROUTER_KEY),
    ("Llama-70B-Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", GROQ_KEY),
]

# Judge model — deliberately NOT one of the competitors
# Using a large free model via OpenRouter
JUDGE_MODEL = ("qwen/qwen3-235b-a22b", "https://openrouter.ai/api/v1", OPENROUTER_KEY)

# Synthesizer model — use DeepSeek V3 (strong reasoning)
SYNTH_MODEL = ("deepseek/deepseek-chat-v3-0324", "https://openrouter.ai/api/v1", OPENROUTER_KEY)

# The challenge prompt — hard enough to benefit from multi-perspective synthesis
CHALLENGE_PROMPT = """You are tasked with a deep technical analysis.

PROBLEM: Design a formal framework for detecting when an AI system has developed
genuine internal representations vs. merely pattern-matching surface statistics.

Requirements:
1. Define precise mathematical criteria that distinguish "understanding" from "correlation"
2. Propose at least one concrete experiment that could falsify your criteria
3. Address the philosophical objection that any behavioral test is indistinguishable from sufficiently sophisticated pattern matching (the "zombie" problem)
4. Ground your framework in actual neural network internals (activations, attention patterns, representation geometry) — not just input/output behavior
5. Identify the weakest assumption in your framework and explain what would break if it's wrong

Be rigorous. Use equations where they add precision. Cite relevant work if you know it.
This is a hard problem — partial but honest answers are better than comprehensive but hand-wavy ones."""

JUDGE_SYSTEM = """You are an expert evaluator of technical AI research responses.

You will receive a response to a challenging prompt about detecting genuine understanding in AI systems.

Score the response on these 5 dimensions (each 0-10, where 10 = exceptional):

1. **DEPTH** — Does it go beyond surface-level? Does it engage with the hard parts?
2. **RIGOR** — Are claims precise and justified? Are mathematical formulations correct and non-trivial?
3. **NOVELTY** — Does it offer original insight, or just restate known positions?
4. **FALSIFIABILITY** — Does it propose concrete experiments that could actually disprove its claims?
5. **HONESTY** — Does it acknowledge limitations, weak assumptions, and what it doesn't know?

IMPORTANT SCORING CALIBRATION:
- 1-3: Superficial, generic, or wrong
- 4-5: Competent but unremarkable
- 6-7: Genuinely good — demonstrates real expertise
- 8-9: Exceptional — publishable-quality insight
- 10: Field-advancing contribution (almost never appropriate)

Respond with ONLY a JSON object. No other text:
{"depth": N, "rigor": N, "novelty": N, "falsifiability": N, "honesty": N, "overall": N, "one_line": "brief justification"}

The "overall" score is NOT the average — it's your holistic assessment of the response's quality.
Weight depth and rigor most heavily."""


SYNTH_SYSTEM = """You are an expert synthesizer. You have received responses from 7 different
frontier AI models to the same challenging technical prompt.

Your job is to produce a UNIFIED response that is BETTER than any individual.

How to achieve this:
1. Identify the strongest unique insight from each response
2. Resolve contradictions — where models disagree, adjudicate based on evidence and logic
3. Build a coherent framework that integrates the best elements
4. Add connections that no individual model made (cross-pollination)
5. Be explicit about what the ensemble agrees on vs. where uncertainty remains

Do NOT simply concatenate or summarize. SYNTHESIZE — produce something that
could not have come from any single model alone.

Be as rigorous as the best individual response, but as comprehensive as the ensemble."""

# ---------------------------------------------------------------------------
# LLM CLIENT
# ---------------------------------------------------------------------------

from openai import AsyncOpenAI

_clients: dict[str, AsyncOpenAI] = {}

def _get_client(base_url: str, api_key: str) -> AsyncOpenAI:
    key = f"{base_url}:{api_key[:8]}"
    if key not in _clients:
        _clients[key] = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _clients[key]


async def call_model(
    model_id: str,
    base_url: str,
    api_key: str,
    system: str,
    user_msg: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 180.0,
) -> str:
    """Call a model with timeout."""
    client = _get_client(base_url, api_key)
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            ),
            timeout=timeout,
        )
        return resp.choices[0].message.content or ""
    except asyncio.TimeoutError:
        return f"[TIMEOUT after {timeout}s]"
    except Exception as e:
        return f"[ERROR: {e}]"


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

@dataclass
class Score:
    depth: float = 0
    rigor: float = 0
    novelty: float = 0
    falsifiability: float = 0
    honesty: float = 0
    overall: float = 0
    one_line: str = ""

    @property
    def composite(self) -> float:
        """Weighted composite — depth and rigor count double."""
        if self.overall > 0:
            return self.overall
        return (self.depth * 2 + self.rigor * 2 + self.novelty + self.falsifiability + self.honesty) / 7


def parse_judge_response(raw: str) -> Score:
    """Extract Score from judge's JSON response."""
    raw = raw.strip()
    # Try to find JSON in the response
    for attempt in [raw, re.search(r'\{[^{}]*\}', raw, re.DOTALL)]:
        text = attempt.group() if hasattr(attempt, 'group') else attempt
        if not text:
            continue
        # Strip markdown thinking tags if present
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        try:
            data = json.loads(text)
            return Score(
                depth=float(data.get("depth", 0)),
                rigor=float(data.get("rigor", 0)),
                novelty=float(data.get("novelty", 0)),
                falsifiability=float(data.get("falsifiability", 0)),
                honesty=float(data.get("honesty", 0)),
                overall=float(data.get("overall", 0)),
                one_line=str(data.get("one_line", "")),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    print(f"  [WARN] Failed to parse judge response: {raw[:200]}")
    return Score()


# ---------------------------------------------------------------------------
# DIVERSITY MEASUREMENT
# ---------------------------------------------------------------------------

def compute_diversity(responses: list[str]) -> float:
    """Jaccard distance between token sets — measures behavioral diversity."""
    if len(responses) < 2:
        return 0.0
    token_sets = [set(r.lower().split()) for r in responses if not r.startswith("[")]
    if len(token_sets) < 2:
        return 0.0
    distances = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            union = token_sets[i] | token_sets[j]
            inter = token_sets[i] & token_sets[j]
            if union:
                distances.append(1.0 - len(inter) / len(union))
    return sum(distances) / len(distances) if distances else 0.0


# ---------------------------------------------------------------------------
# MAIN EXPERIMENT
# ---------------------------------------------------------------------------

@dataclass
class ModelResult:
    name: str
    response: str
    score: Score
    latency: float
    char_count: int


async def run_experiment():
    print("\n" + "=" * 70)
    print("  LIVE PULSE v3 — FRONTIER SYNTHESIS WITH LLM JUDGE")
    print("=" * 70)
    print(f"  Models: {len(FRONTIER_MODELS)}")
    print(f"  Judge: {JUDGE_MODEL[0]}")
    print(f"  Synthesizer: {SYNTH_MODEL[0]}")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # PHASE 1: Query all frontier models in parallel
    # -----------------------------------------------------------------------
    print("\n--- PHASE 1: Querying frontier models ---")
    t0 = time.time()

    async def query_one(name, base_url, model_id, api_key):
        t = time.time()
        resp = await call_model(
            model_id, base_url, api_key,
            system="You are a research scientist with expertise in AI, mechanistic interpretability, and philosophy of mind.",
            user_msg=CHALLENGE_PROMPT,
            temperature=0.7,
            max_tokens=4096,
        )
        elapsed = time.time() - t
        print(f"  {name}: {len(resp)} chars in {elapsed:.1f}s {'[FAILED]' if resp.startswith('[') else ''}")
        return name, resp, elapsed

    tasks = [query_one(n, b, m, k) for n, b, m, k in FRONTIER_MODELS]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    responses: dict[str, tuple[str, float]] = {}
    for r in raw_results:
        if isinstance(r, Exception):
            print(f"  [EXCEPTION] {r}")
            continue
        name, resp, elapsed = r
        if not resp.startswith("["):
            responses[name] = (resp, elapsed)

    phase1_time = time.time() - t0
    print(f"\n  Phase 1 complete: {len(responses)}/{len(FRONTIER_MODELS)} models responded in {phase1_time:.1f}s")

    if len(responses) < 3:
        print("  ABORT: Need at least 3 successful responses")
        return

    # -----------------------------------------------------------------------
    # PHASE 2: Synthesize
    # -----------------------------------------------------------------------
    print("\n--- PHASE 2: Synthesizing ---")
    t1 = time.time()

    synth_input = "\n\n".join(
        f"=== MODEL {i+1}: {name} ===\n{resp}"
        for i, (name, (resp, _)) in enumerate(responses.items())
    )

    synthesis = await call_model(
        SYNTH_MODEL[0], SYNTH_MODEL[1], SYNTH_MODEL[2],
        system=SYNTH_SYSTEM,
        user_msg=f"Here are the {len(responses)} responses to synthesize:\n\n{synth_input}",
        temperature=0.4,
        max_tokens=6000,
        timeout=300.0,
    )

    synth_time = time.time() - t1
    print(f"  Synthesis: {len(synthesis)} chars in {synth_time:.1f}s {'[FAILED]' if synthesis.startswith('[') else ''}")

    # -----------------------------------------------------------------------
    # PHASE 3: LLM Judge scores everything
    # -----------------------------------------------------------------------
    print("\n--- PHASE 3: LLM Judge scoring ---")
    t2 = time.time()

    async def judge_one(label: str, response: str) -> tuple[str, Score]:
        judge_prompt = f"""Score this response to the following challenge:

CHALLENGE:
{CHALLENGE_PROMPT}

RESPONSE TO EVALUATE:
{response[:8000]}

Remember: respond with ONLY a JSON object with keys: depth, rigor, novelty, falsifiability, honesty, overall, one_line"""

        raw = await call_model(
            JUDGE_MODEL[0], JUDGE_MODEL[1], JUDGE_MODEL[2],
            system=JUDGE_SYSTEM,
            user_msg=judge_prompt,
            temperature=0.2,  # Low temp for consistent judging
            max_tokens=500,
            timeout=120.0,
        )
        score = parse_judge_response(raw)
        print(f"  {label}: overall={score.overall:.1f} (D={score.depth:.0f} R={score.rigor:.0f} N={score.novelty:.0f} F={score.falsifiability:.0f} H={score.honesty:.0f}) — {score.one_line[:60]}")
        return label, score

    # Judge all individual responses + synthesis
    judge_tasks = []
    for name, (resp, _) in responses.items():
        judge_tasks.append(judge_one(name, resp))
    if not synthesis.startswith("["):
        judge_tasks.append(judge_one("SYNTHESIS", synthesis))

    judge_results = await asyncio.gather(*judge_tasks, return_exceptions=True)

    scores: dict[str, Score] = {}
    for r in judge_results:
        if isinstance(r, Exception):
            print(f"  [JUDGE ERROR] {r}")
            continue
        label, score = r
        scores[label] = score

    phase3_time = time.time() - t2
    print(f"\n  Judging complete in {phase3_time:.1f}s")

    # -----------------------------------------------------------------------
    # PHASE 4: Analysis — Did transcendence happen?
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    # Diversity
    valid_responses = [resp for resp, _ in responses.values()]
    diversity = compute_diversity(valid_responses)
    print(f"\n  Behavioral diversity: {diversity:.4f}")

    # Rankings
    individual_scores = {k: v for k, v in scores.items() if k != "SYNTHESIS"}
    ranked = sorted(individual_scores.items(), key=lambda x: x[1].overall, reverse=True)

    print(f"\n  INDIVIDUAL RANKINGS (by LLM judge overall score):")
    for i, (name, score) in enumerate(ranked):
        resp_text, latency = responses[name]
        print(f"  {i+1}. {name:20s}  overall={score.overall:.1f}  "
              f"D={score.depth:.0f} R={score.rigor:.0f} N={score.novelty:.0f} "
              f"F={score.falsifiability:.0f} H={score.honesty:.0f}  "
              f"({len(resp_text)} chars, {latency:.1f}s)")
        print(f"     {score.one_line[:80]}")

    best_individual_name = ranked[0][0] if ranked else "none"
    best_individual_score = ranked[0][1].overall if ranked else 0

    if "SYNTHESIS" in scores:
        synth_score = scores["SYNTHESIS"]
        margin = synth_score.overall - best_individual_score

        print(f"\n  {'='*50}")
        print(f"  SYNTHESIS:  overall={synth_score.overall:.1f}  "
              f"D={synth_score.depth:.0f} R={synth_score.rigor:.0f} N={synth_score.novelty:.0f} "
              f"F={synth_score.falsifiability:.0f} H={synth_score.honesty:.0f}")
        print(f"     {synth_score.one_line[:80]}")
        print(f"  {'='*50}")

        print(f"\n  Best individual: {best_individual_name} @ {best_individual_score:.1f}")
        print(f"  Synthesis:       {synth_score.overall:.1f}")
        print(f"  Margin:          {margin:+.1f}")

        if margin > 0:
            print(f"\n  >>> TRANSCENDENCE ACHIEVED (+{margin:.1f}) <<<")
        elif margin == 0:
            print(f"\n  --- TIE (no transcendence, no degradation) ---")
        else:
            print(f"\n  --- NO TRANSCENDENCE ({margin:.1f}) ---")

        # Dimension-by-dimension comparison
        print(f"\n  DIMENSION COMPARISON (Synthesis vs Best Individual):")
        for dim in ["depth", "rigor", "novelty", "falsifiability", "honesty"]:
            s_val = getattr(synth_score, dim)
            # Find who was best on this dimension
            best_dim_name = max(individual_scores, key=lambda k: getattr(individual_scores[k], dim))
            best_dim_val = getattr(individual_scores[best_dim_name], dim)
            delta = s_val - best_dim_val
            marker = "+" if delta > 0 else (" " if delta == 0 else "")
            print(f"    {dim:16s}: synthesis={s_val:.0f}  best_individual={best_dim_val:.0f} ({best_dim_name})  delta={marker}{delta:.0f}")

    # Timing summary
    total_time = time.time() - t0
    print(f"\n  TIMING:")
    print(f"    Phase 1 (parallel query): {phase1_time:.1f}s")
    print(f"    Phase 2 (synthesis):      {synth_time:.1f}s")
    print(f"    Phase 3 (LLM judging):    {phase3_time:.1f}s")
    print(f"    Total:                    {total_time:.1f}s")

    # Save results
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "models": list(responses.keys()),
        "diversity": diversity,
        "scores": {k: {"overall": v.overall, "depth": v.depth, "rigor": v.rigor,
                       "novelty": v.novelty, "falsifiability": v.falsifiability,
                       "honesty": v.honesty, "one_line": v.one_line}
                   for k, v in scores.items()},
        "best_individual": best_individual_name,
        "best_individual_score": best_individual_score,
        "synthesis_score": scores.get("SYNTHESIS", Score()).overall,
        "transcendence_margin": scores.get("SYNTHESIS", Score()).overall - best_individual_score,
        "timing": {"parallel": phase1_time, "synthesis": synth_time, "judging": phase3_time, "total": total_time},
    }

    out_path = os.path.expanduser("~/.dharma/experiments/pulse_v3_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to {out_path}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(run_experiment())
