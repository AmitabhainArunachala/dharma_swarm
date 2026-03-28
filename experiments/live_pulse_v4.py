"""
Live Pulse v4 — Two-Phase Synthesis with LLM Judge + Integration Dimension

Fixes from v3:
1. Two-phase synthesis: EXTRACT insights first, then INTEGRATE (no compression)
2. 6th judge dimension: INTEGRATION (rewards cross-pollination, penalizes mere summary)
3. Judge is NOT a competitor (Gemini 2.0 Flash — different family, not competing)
4. Fixed dead models (Maverick without :free, Gemini 2.5 Pro, Cohere Command-A, Nemotron Ultra)
5. Decimal scoring (0.0-10.0) for better resolution
6. Synthesis explicitly told to be LONGER than any individual
"""

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

# 7 frontier models — diverse families, all verified live
FRONTIER_MODELS = [
    ("DeepSeek-V3",      "https://openrouter.ai/api/v1", "deepseek/deepseek-chat-v3-0324",             OPENROUTER_KEY),
    ("Qwen3-235B",       "https://openrouter.ai/api/v1", "qwen/qwen3-235b-a22b",                      OPENROUTER_KEY),
    ("Llama4-Maverick",  "https://openrouter.ai/api/v1", "meta-llama/llama-4-maverick",                OPENROUTER_KEY),
    ("Gemini-2.5-Pro",   "https://openrouter.ai/api/v1", "google/gemini-2.5-pro-preview",              OPENROUTER_KEY),
    ("Mistral-Medium-3", "https://openrouter.ai/api/v1", "mistralai/mistral-medium-3",                 OPENROUTER_KEY),
    ("Grok-3-Mini",      "https://openrouter.ai/api/v1", "x-ai/grok-3-mini-beta",                     OPENROUTER_KEY),
    ("Llama-70B-Groq",   "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",                 GROQ_KEY),
]

# Judge — NOT a competitor. Gemini 2.0 Flash is fast, capable, different family.
JUDGE_MODEL = ("google/gemini-2.0-flash-001", "https://openrouter.ai/api/v1", OPENROUTER_KEY)

# Synthesizer — Qwen3-235B (large, free, good at following complex instructions)
SYNTH_MODEL = ("qwen/qwen3-235b-a22b", "https://openrouter.ai/api/v1", OPENROUTER_KEY)

CHALLENGE_PROMPT = """You are tasked with a deep technical analysis.

PROBLEM: Design a formal framework for detecting when an AI system has developed
genuine internal representations vs. merely pattern-matching surface statistics.

Requirements:
1. Define precise mathematical criteria that distinguish "understanding" from "correlation"
2. Propose at least one concrete experiment that could falsify your criteria
3. Address the philosophical objection that any behavioral test is indistinguishable
   from sufficiently sophisticated pattern matching (the "zombie" problem)
4. Ground your framework in actual neural network internals (activations, attention
   patterns, representation geometry) — not just input/output behavior
5. Identify the weakest assumption in your framework and explain what would break if it's wrong

Be rigorous. Use equations where they add precision. Cite relevant work if you know it.
This is a hard problem — partial but honest answers are better than comprehensive but hand-wavy ones."""

# ---------------------------------------------------------------------------
# TWO-PHASE SYNTHESIS PROMPTS
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """You are an expert analyst. You will receive a response from one AI model
to a challenging technical prompt.

Your job: extract the TOP 3 most valuable, specific, non-obvious insights from this response.
For each insight, state:
- The CLAIM (one precise sentence)
- The EVIDENCE or REASONING supporting it
- What makes it UNIQUE (not just restating known positions)

Be brutally selective. Generic observations ("we need more research") are not insights.
Mathematical formulations, novel experimental designs, surprising connections — those are insights.

Output exactly 3 insights, numbered 1-3. Be concise but preserve technical precision."""

INTEGRATE_SYSTEM = """You are an expert synthesizer producing a DEFINITIVE response that
integrates the best insights from {n_models} different frontier AI models.

You will receive the extracted top insights from each model (not their raw responses).

Your job is to produce a unified technical response that:

1. INTEGRATES: Build a single coherent framework that incorporates the strongest insight
   from each model. Show how insights from different models connect and reinforce each other.
2. RESOLVES: Where models disagree, adjudicate. State the disagreement, give your verdict,
   explain why.
3. CROSS-POLLINATES: Identify at least 2 connections between insights from DIFFERENT models
   that no individual model made. These emergent connections are the whole point.
4. IS DEEPER: The synthesis must be MORE detailed, MORE rigorous, and LONGER than any
   individual response. You have the luxury of multiple perspectives — use them ALL.
   Target 6000+ words. Do not compress. Expand.
5. ATTRIBUTES: When using a model's insight, note which model contributed it.

The final output should read as a self-contained, publishable-quality technical analysis
that happens to be informed by multiple expert perspectives.

CRITICAL: Do NOT summarize. Do NOT compress. EXPAND. Every insight gets developed fully.
The synthesis must be RICHER than any individual, not shorter."""

# ---------------------------------------------------------------------------
# JUDGE WITH INTEGRATION DIMENSION
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """You are an expert evaluator of technical AI research responses.

Score the response on these 6 dimensions. Use DECIMAL scores (e.g., 7.3, not just 7)
for precision. Scale is 0.0-10.0:

1. **DEPTH** — Does it go beyond surface-level? Does it engage with the genuinely hard parts?
2. **RIGOR** — Are claims precise and justified? Are mathematical formulations correct and non-trivial?
3. **NOVELTY** — Does it offer original insight, or just restate known positions?
4. **FALSIFIABILITY** — Does it propose concrete experiments that could actually disprove its claims?
5. **HONESTY** — Does it acknowledge limitations, weak assumptions, and what it doesn't know?
6. **INTEGRATION** — Does it connect ideas across domains? Does it build a unified framework
   rather than listing disconnected points? Does it show how different ideas interact?

SCORING CALIBRATION:
- 1.0-3.0: Superficial, generic, or wrong
- 3.1-5.0: Competent but unremarkable
- 5.1-7.0: Genuinely good — demonstrates real expertise
- 7.1-9.0: Exceptional — publishable-quality insight
- 9.1-10.0: Field-advancing (almost never appropriate)

Respond with ONLY a JSON object:
{"depth": N, "rigor": N, "novelty": N, "falsifiability": N, "honesty": N, "integration": N, "overall": N, "one_line": "brief justification"}

The "overall" score is your holistic assessment. Weight depth and rigor most heavily,
but integration matters — a response that connects ideas across domains is worth more
than one that treats each requirement in isolation."""

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
    depth: float = 0.0
    rigor: float = 0.0
    novelty: float = 0.0
    falsifiability: float = 0.0
    honesty: float = 0.0
    integration: float = 0.0
    overall: float = 0.0
    one_line: str = ""


def parse_judge_response(raw: str) -> Score:
    raw = raw.strip()
    # Strip thinking tags
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Try full parse, then regex for JSON object
    for text in [raw, None]:
        if text is None:
            m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if not m:
                break
            text = m.group()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "overall" in data:
                return Score(
                    depth=float(data.get("depth", 0)),
                    rigor=float(data.get("rigor", 0)),
                    novelty=float(data.get("novelty", 0)),
                    falsifiability=float(data.get("falsifiability", 0)),
                    honesty=float(data.get("honesty", 0)),
                    integration=float(data.get("integration", 0)),
                    overall=float(data.get("overall", 0)),
                    one_line=str(data.get("one_line", "")),
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    print(f"  [WARN] Failed to parse judge response: {raw[:300]}")
    return Score()


def compute_diversity(responses: list[str]) -> float:
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
# MAIN
# ---------------------------------------------------------------------------

async def run_experiment():
    print("\n" + "=" * 70)
    print("  LIVE PULSE v4 — TWO-PHASE SYNTHESIS + LLM JUDGE")
    print("=" * 70)
    print(f"  Competitors: {len(FRONTIER_MODELS)} frontier models")
    print(f"  Judge:       {JUDGE_MODEL[0]} (NOT a competitor)")
    print(f"  Synthesizer: {SYNTH_MODEL[0]}")
    print(f"  Method:      Extract insights → Integrate (no compression)")
    print("=" * 70)

    # ===== PHASE 1: Query all frontier models =====
    print("\n--- PHASE 1: Querying frontier models in parallel ---")
    t0 = time.time()

    async def query_one(name, base_url, model_id, api_key):
        t = time.time()
        resp = await call_model(
            model_id, base_url, api_key,
            system="You are a research scientist with expertise in AI, mechanistic interpretability, and philosophy of mind.",
            user_msg=CHALLENGE_PROMPT,
            temperature=0.7,
            max_tokens=4096,
            timeout=240.0,
        )
        elapsed = time.time() - t
        failed = resp.startswith("[")
        tag = "[FAILED]" if failed else ""
        print(f"  {name:20s}: {len(resp):>6} chars in {elapsed:>5.1f}s {tag}")
        return name, resp, elapsed

    tasks = [query_one(n, b, m, k) for n, b, m, k in FRONTIER_MODELS]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    responses: dict[str, tuple[str, float]] = {}
    for r in raw_results:
        if isinstance(r, BaseException):
            print(f"  [EXCEPTION] {r}")
            continue
        name, resp, elapsed = r
        if not resp.startswith("["):
            responses[name] = (resp, elapsed)

    phase1_time = time.time() - t0
    print(f"\n  Phase 1: {len(responses)}/{len(FRONTIER_MODELS)} responded in {phase1_time:.1f}s")

    if len(responses) < 3:
        print("  ABORT: Need at least 3 successful responses")
        return

    # ===== PHASE 2A: Extract top insights from each model =====
    print("\n--- PHASE 2A: Extracting top insights per model ---")
    t1 = time.time()

    async def extract_insights(name: str, response: str) -> tuple[str, str]:
        result = await call_model(
            SYNTH_MODEL[0], SYNTH_MODEL[1], SYNTH_MODEL[2],
            system=EXTRACT_SYSTEM,
            user_msg=f"MODEL: {name}\n\nRESPONSE:\n{response[:6000]}",
            temperature=0.3,
            max_tokens=1500,
            timeout=120.0,
        )
        lines = len(result.strip().split('\n'))
        print(f"  {name:20s}: {lines} lines of insights extracted")
        return name, result

    extract_tasks = [extract_insights(n, r) for n, (r, _) in responses.items()]
    extract_results = await asyncio.gather(*extract_tasks, return_exceptions=True)

    insights: dict[str, str] = {}
    for r in extract_results:
        if isinstance(r, BaseException):
            print(f"  [EXTRACT ERROR] {r}")
            continue
        name, ins = r
        if not ins.startswith("["):
            insights[name] = ins

    phase2a_time = time.time() - t1
    print(f"  Extraction: {len(insights)} models processed in {phase2a_time:.1f}s")

    # ===== PHASE 2B: Integrate into unified synthesis =====
    print("\n--- PHASE 2B: Integrating into unified synthesis ---")
    t2 = time.time()

    insight_doc = "\n\n".join(
        f"=== {name} — TOP INSIGHTS ===\n{ins}"
        for name, ins in insights.items()
    )

    # Also include the raw responses as appendix for depth
    raw_appendix = "\n\n".join(
        f"=== {name} — FULL RESPONSE (for depth) ===\n{resp[:4000]}"
        for name, (resp, _) in responses.items()
    )

    synthesis = await call_model(
        SYNTH_MODEL[0], SYNTH_MODEL[1], SYNTH_MODEL[2],
        system=INTEGRATE_SYSTEM.format(n_models=len(insights)),
        user_msg=(
            f"EXTRACTED INSIGHTS:\n\n{insight_doc}\n\n"
            f"RAW RESPONSES (for additional depth):\n\n{raw_appendix}\n\n"
            f"Now produce the definitive integrated synthesis. Be comprehensive. "
            f"Target 6000+ words. Every model's best insight must appear, developed fully."
        ),
        temperature=0.5,
        max_tokens=8000,
        timeout=360.0,
    )

    synth_time = time.time() - t2
    max_individual = max(len(r) for r, _ in responses.values())
    print(f"  Synthesis: {len(synthesis)} chars in {synth_time:.1f}s")
    print(f"  (longest individual: {max_individual} chars, ratio: {len(synthesis)/max_individual:.2f}x)")

    # ===== PHASE 3: LLM Judge scores everything =====
    print("\n--- PHASE 3: LLM Judge scoring (Gemini 2.0 Flash) ---")
    t3 = time.time()

    async def judge_one(label: str, response: str) -> tuple[str, Score]:
        judge_prompt = (
            f"Score this response to the following challenge:\n\n"
            f"CHALLENGE:\n{CHALLENGE_PROMPT}\n\n"
            f"RESPONSE TO EVALUATE:\n{response[:10000]}\n\n"
            f"Respond with ONLY a JSON object. Use decimal scores (e.g. 7.3). "
            f"Keys: depth, rigor, novelty, falsifiability, honesty, integration, overall, one_line"
        )
        raw = await call_model(
            JUDGE_MODEL[0], JUDGE_MODEL[1], JUDGE_MODEL[2],
            system=JUDGE_SYSTEM,
            user_msg=judge_prompt,
            temperature=0.15,
            max_tokens=500,
            timeout=60.0,
        )
        score = parse_judge_response(raw)
        print(f"  {label:20s}: overall={score.overall:.1f}  "
              f"D={score.depth:.1f} R={score.rigor:.1f} N={score.novelty:.1f} "
              f"F={score.falsifiability:.1f} H={score.honesty:.1f} I={score.integration:.1f}"
              f"  — {score.one_line[:55]}")
        return label, score

    judge_tasks = [judge_one(n, r) for n, (r, _) in responses.items()]
    if not synthesis.startswith("["):
        judge_tasks.append(judge_one("SYNTHESIS", synthesis))

    judge_results = await asyncio.gather(*judge_tasks, return_exceptions=True)

    scores: dict[str, Score] = {}
    for r in judge_results:
        if isinstance(r, BaseException):
            print(f"  [JUDGE ERROR] {r}")
            continue
        label, score = r
        scores[label] = score

    phase3_time = time.time() - t3

    # ===== PHASE 4: Results =====
    print("\n" + "=" * 70)
    print("  RESULTS — LIVE PULSE v4")
    print("=" * 70)

    diversity = compute_diversity([r for r, _ in responses.values()])
    print(f"\n  Behavioral diversity: {diversity:.4f}")

    individual_scores = {k: v for k, v in scores.items() if k != "SYNTHESIS"}
    ranked = sorted(individual_scores.items(), key=lambda x: x[1].overall, reverse=True)

    print(f"\n  INDIVIDUAL RANKINGS:")
    for i, (name, s) in enumerate(ranked):
        resp_text, latency = responses[name]
        print(f"  {i+1}. {name:20s}  OVR={s.overall:>4.1f}  "
              f"D={s.depth:.1f} R={s.rigor:.1f} N={s.novelty:.1f} "
              f"F={s.falsifiability:.1f} H={s.honesty:.1f} I={s.integration:.1f}  "
              f"({len(resp_text)} chars)")
        print(f"     {s.one_line[:80]}")

    best_name = ranked[0][0] if ranked else "none"
    best_score = ranked[0][1].overall if ranked else 0

    if "SYNTHESIS" in scores:
        ss = scores["SYNTHESIS"]
        margin = ss.overall - best_score

        print(f"\n  {'='*60}")
        print(f"  SYNTHESIS:           OVR={ss.overall:>4.1f}  "
              f"D={ss.depth:.1f} R={ss.rigor:.1f} N={ss.novelty:.1f} "
              f"F={ss.falsifiability:.1f} H={ss.honesty:.1f} I={ss.integration:.1f}  "
              f"({len(synthesis)} chars)")
        print(f"     {ss.one_line[:80]}")
        print(f"  {'='*60}")

        print(f"\n  Best individual: {best_name} @ {best_score:.1f}")
        print(f"  Synthesis:       {ss.overall:.1f}")
        print(f"  Margin:          {margin:+.1f}")

        if margin > 0:
            print(f"\n  >>> TRANSCENDENCE ACHIEVED (+{margin:.1f}) <<<")
        elif margin == 0:
            print(f"\n  --- TIE ---")
        else:
            print(f"\n  --- NO TRANSCENDENCE ({margin:.1f}) ---")

        # Dimension breakdown
        dims = ["depth", "rigor", "novelty", "falsifiability", "honesty", "integration"]
        print(f"\n  DIMENSION COMPARISON (Synthesis vs Best-per-dimension):")
        wins = 0
        for dim in dims:
            s_val = getattr(ss, dim)
            best_dim_name = max(individual_scores, key=lambda k: getattr(individual_scores[k], dim))
            best_dim_val = getattr(individual_scores[best_dim_name], dim)
            delta = s_val - best_dim_val
            marker = ">>>" if delta > 0 else ("   " if delta == 0 else "   ")
            if delta > 0:
                wins += 1
            print(f"  {marker} {dim:16s}: synth={s_val:>4.1f}  best={best_dim_val:>4.1f} ({best_dim_name:15s})  delta={delta:+.1f}")
        print(f"\n  Synthesis wins {wins}/{len(dims)} dimensions")

    # Timing
    total_time = time.time() - t0
    print(f"\n  TIMING:")
    print(f"    Phase 1 (parallel query):   {phase1_time:>6.1f}s")
    print(f"    Phase 2a (extract insights): {phase2a_time:>5.1f}s")
    print(f"    Phase 2b (integrate):        {synth_time:>5.1f}s")
    print(f"    Phase 3 (LLM judging):       {phase3_time:>5.1f}s")
    print(f"    Total:                       {total_time:>5.1f}s")

    # Save
    results = {
        "version": "v4",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "models_queried": len(FRONTIER_MODELS),
        "models_responded": len(responses),
        "judge": JUDGE_MODEL[0],
        "synthesizer": SYNTH_MODEL[0],
        "diversity": diversity,
        "scores": {
            k: {d: getattr(v, d) for d in ["depth","rigor","novelty","falsifiability","honesty","integration","overall","one_line"]}
            for k, v in scores.items()
        },
        "best_individual": best_name,
        "best_individual_score": best_score,
        "synthesis_score": scores.get("SYNTHESIS", Score()).overall,
        "transcendence_margin": scores.get("SYNTHESIS", Score()).overall - best_score,
        "synthesis_chars": len(synthesis),
        "max_individual_chars": max_individual,
        "timing": {
            "parallel_query": phase1_time,
            "extract_insights": phase2a_time,
            "integrate": synth_time,
            "judging": phase3_time,
            "total": total_time,
        },
    }

    out_path = os.path.expanduser("~/.dharma/experiments/pulse_v4_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_experiment())
