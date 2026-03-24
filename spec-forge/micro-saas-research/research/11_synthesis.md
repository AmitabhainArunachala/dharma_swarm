# Micro-SaaS Opportunity Synthesis

**Date**: 2026-03-25
**Based on**: 5-agent parallel research swarm (1.27M chars of raw research)
**Convergence level**: STRONG — all 5 agents independently identified the same gap

---

## The Signal

Every research angle converges on ONE structural insight:

> AI coding tools create more code than humans can verify. The verification layer — between "AI wrote code" and "code ships" — is a multi-billion dollar gap with no dominant player.

### Evidence from each agent:

1. **Landscape**: CodeRabbit ($15M ARR, 24 people, 20% MoM) proves the market. Greptile got $25M Series A from Benchmark for code review. Graphite acquired by Cursor for $81M. Code review is the hottest vertical.

2. **Architecture**: Every winning product has a verification loop (generate→execute→test→iterate). Products without it die. Replit's Playwright self-testing = 90% autonomous success rate. Cursor's Shadow Workspace = safe iteration.

3. **Gaps**: "AI Code Health Platform" scored 560 on opportunity matrix. 76% of devs generate code they don't understand. AI creates 1.7x more bugs, 2x concurrency bugs, 8x excessive I/O. Comprehension debt is structural.

4. **Pain Points**: #1 developer pain = debugging "almost right" AI code (84% of devs, daily). Review bottleneck worsened 91%. Trust in AI dropped from 43% to 29% even as adoption rose to 84%.

5. **Daily Problems**: Beyond dev tools, invoice processing (#1), AI SDR (#2), email triage (#3) scored highest. But "meeting notes to action items to follow-ups" (#4) is the best dharma_swarm fit.

---

## Two Paths

### Path A: "dharma_verify" — AI Code Verification Platform
**The CodeRabbit killer with dharma_swarm's governance brain**

- GitHub App that reviews AI-generated PRs
- 9-dimensional thinkodynamic scoring (not just style/lint)
- Comprehension debt tracking per module
- Telos-gated merge approval
- Pricing: $15-30/user/month (matches CodeRabbit)
- dharma_swarm advantage: thinkodynamic_scorer + telos_gates + guardrails + trajectory_collector already built
- Time to MVP: 2-3 weeks (the scoring engine exists, need GitHub webhook + UI)
- Revenue target: $5K MRR in 3 months, $50K MRR in 12 months

### Path B: "dharma_flow" — Meeting → Action → Follow-up Agent
**The meeting aftermath tool that nobody's built right**

- Transcription is commoditized (Whisper). The gap is AFTER.
- Agent extracts action items, creates tasks, sends follow-ups, tracks completion
- Multi-agent: transcriber → extractor → router → reminder → tracker
- Pricing: $20-50/user/month
- dharma_swarm advantage: multi-agent orchestration, strategy reinforcement, self-improvement
- Time to MVP: 4-6 weeks (more greenfield)
- Revenue target: $3K MRR in 3 months, $30K MRR in 12 months

### Path C: Combine Both
Use dharma_swarm as the engine. Path A is the wedge (developer tool, existing codebase). Path B is the expansion (business tool, wider market). Same underlying intelligence, different interfaces.

---

## Recommendation

**Ship Path A first. It's the 80/20 play.**

Why:
1. The scoring engine already exists (thinkodynamic_scorer.py)
2. The governance layer already exists (telos_gates.py, guardrails.py)
3. The trajectory capture already exists (trajectory_collector.py)
4. CodeRabbit proves $15M ARR is achievable with 24 people
5. Time to first revenue is weeks, not months
6. It dogfoods dharma_swarm — the system reviews its own output
7. The R_V research provides unique credentialing ("we measure computational consciousness")

**Path B can follow once Path A proves revenue.**

---

## dharma_swarm's Unfair Advantages for Path A

| Capability | What It Does | Competitor Equivalent |
|-----------|-------------|----------------------|
| thinkodynamic_scorer | 6-dimension quality scoring with IPA-like chunk weighting | Nobody has this |
| telos_gates | 11-gate governance with reflective reroute | CodeRabbit has basic rule engine |
| trajectory_collector | Full provenance of every code change | Nobody tracks trajectories |
| strategy_reinforcer | UCB-based learning from past reviews | Nobody self-improves |
| economic_engine | Tracks cost of reviews, ROI per gate | Nobody does economic analysis |
| viz_projection | Dashboard showing codebase health | CodeScene has this, others don't |
| R_V research | Academic credibility re: computational self-reference | Nobody else has published research |

The system doesn't just review code. It UNDERSTANDS code through a governance framework that no competitor has.

---

## Next Steps

1. **This week**: Build GitHub webhook + PR review endpoint using existing thinkodynamic_scorer
2. **Next week**: Deploy as GitHub App, test on dharma_swarm's own PRs
3. **Week 3**: Open beta, 10 repos from Twitter/HN outreach
4. **Month 2**: Launch on ProductHunt, target $5K MRR
5. **Month 3**: Add comprehension debt dashboard (uses existing viz_projection)
6. **Month 6**: $50K MRR milestone, begin Path B expansion
