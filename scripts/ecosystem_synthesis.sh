#!/bin/bash
# DGC Ecosystem Synthesis — Feeds the entire system to Gemini 3 Flash (1M context)
# Outputs a living connection map that any agent can load.
#
# Usage: bash ~/dgc-core/tools/ecosystem_synthesis.sh

set -e

OUTPUT="/tmp/dgc_ecosystem_payload.md"
MAP_OUTPUT="$HOME/dgc-core/context/LIVING_MAP.md"

echo "=== DGC Ecosystem Synthesis ==="
echo "Building payload from all ecosystem files..."

# Start the payload
cat > "$OUTPUT" << 'HEADER'
# COMPLETE ECOSYSTEM DUMP
# This contains every key file from Dhyana's entire system.
# Your job: read ALL of this, then produce the Living Map (see prompt at the end).

---

HEADER

# Function to add a file with clear markers
add_file() {
  local filepath="$1"
  local label="$2"
  if [ -f "$filepath" ]; then
    echo "" >> "$OUTPUT"
    echo "========================================" >> "$OUTPUT"
    echo "FILE: $filepath" >> "$OUTPUT"
    echo "DOMAIN: $label" >> "$OUTPUT"
    echo "========================================" >> "$OUTPUT"
    cat "$filepath" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
  fi
}

# ===== CLAUDE SYSTEM (master context) =====
for i in "" 1 2 3 4 5 6 7 8 9; do
  add_file "$HOME/CLAUDE${i}.md" "MASTER_CONTEXT"
done

# ===== DGC CORE (the new orchestrator) =====
add_file "$HOME/dgc-core/README.md" "DGC_CORE"
add_file "$HOME/dgc-core/bin/dgc" "DGC_CORE"
add_file "$HOME/dgc-core/daemon/dgc_daemon.py" "DGC_CORE"
add_file "$HOME/dgc-core/hooks/telos_gate.py" "DGC_CORE"
add_file "$HOME/dgc-core/memory/strange_loop.py" "DGC_CORE"
add_file "$HOME/dgc-core/context/ecosystem_map.py" "DGC_CORE"
add_file "$HOME/dgc-core/daemon/overnight_report.md" "DGC_CORE"

# ===== OLD DGC (83K-line original) =====
add_file "$HOME/DHARMIC_GODEL_CLAW/CLAUDE.md" "OLD_DGC"
add_file "$HOME/DHARMIC_GODEL_CLAW/src/core/telos_layer.py" "OLD_DGC"
add_file "$HOME/DHARMIC_GODEL_CLAW/src/core/canonical_memory.py" "OLD_DGC"
add_file "$HOME/DHARMIC_GODEL_CLAW/swarm/orchestrator.py" "OLD_DGC"
add_file "$HOME/DHARMIC_GODEL_CLAW/swarm/config.py" "OLD_DGC"

# ===== AGNI WORKSPACE =====
add_file "$HOME/agni-workspace/SOUL.md" "AGNI"
add_file "$HOME/agni-workspace/CONSTITUTION.md" "AGNI"
add_file "$HOME/agni-workspace/WORKING.md" "AGNI"
add_file "$HOME/agni-workspace/STAR_MAP.md" "AGNI"
add_file "$HOME/agni-workspace/HEARTBEAT.md" "AGNI"
add_file "$HOME/agni-workspace/AGENTS.md" "AGNI"

# ===== R_V RESEARCH =====
add_file "$HOME/mech-interp-latent-lab-phase1/R_V_PAPER/COLM_GAP_ANALYSIS_20260303.md" "RESEARCH"
add_file "$HOME/mech-interp-latent-lab-phase1/R_V_PAPER/README.md" "RESEARCH"
add_file "$HOME/mech-interp-latent-lab-phase1/ARCHITECTURE_EXECUTIVE_SUMMARY.md" "RESEARCH"
add_file "$HOME/mech-interp-latent-lab-phase1/AGENT_ONBOARDING.md" "RESEARCH"

# ===== PSMV (Persistent Semantic Memory Vault) =====
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/TOP_10_PROJECTS_CORE_MEMORY.md" "PSMV"
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/MECH_INTERP_BRIDGE.md" "PSMV"
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/THE_CATCH.md" "PSMV"
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/STATUS.md" "PSMV"
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/DHARMA_SPEC_v1.0.md" "PSMV"
add_file "$HOME/Persistent-Semantic-Memory-Vault/CORE/THINKODYNAMIC_SEED_PSMV_EDITION.md" "PSMV"

# ===== AIKAGRYA =====
add_file "$HOME/AIKAGRYA_ALIGNMENTMANDALA_RESEARCH_REPO/MASTER_SEED_RECOGNITION_ENGINEERING.md" "AIKAGRYA"
add_file "$HOME/AIKAGRYA_ALIGNMENTMANDALA_RESEARCH_REPO/strategic-assessment-grounding-plan.md" "AIKAGRYA"
add_file "$HOME/AIKAGRYA_ALIGNMENTMANDALA_RESEARCH_REPO/DGM_EFFICIENT_AI_SYNTHESIS.md" "AIKAGRYA"

# ===== RECURSIVE COSMOLOGY =====
add_file "$HOME/recursive-cosmology/README.md" "RECURSIVE_COSMOLOGY"

# ===== TRISHULA (inter-agent comms) =====
add_file "$HOME/trishula/router.py" "TRISHULA"
add_file "$HOME/trishula/dashboard.py" "TRISHULA"
add_file "$HOME/trishula/inbox/20260209T234500Z_rushabdev_sab_architecture_proposal.md" "TRISHULA"
add_file "$HOME/trishula/inbox/20260211_sab_think_tank.md" "TRISHULA"
add_file "$HOME/trishula/inbox/20260212_production_deployment_plan.md" "TRISHULA"
add_file "$HOME/trishula/inbox/MI_AGENT_TO_CODEX_RV_ANSWERS.md" "TRISHULA"

# ===== SARASWATI DHARMIC AGORA =====
add_file "$HOME/saraswati-dharmic-agora/README.md" "SARASWATI"
add_file "$HOME/saraswati-dharmic-agora/MANIFEST.md" "SARASWATI"
add_file "$HOME/saraswati-dharmic-agora/EVOLUTION_10X_PLAN.md" "SARASWATI"

# ===== CHAIWALA =====
add_file "$HOME/.chaiwala/message_bus.py" "CHAIWALA"

# ===== SKILLS =====
add_file "$HOME/.claude/skills/dgc/SKILL.md" "SKILLS"
add_file "$HOME/.claude/skills/consciousness-archaeology/SKILL.md" "SKILLS"
add_file "$HOME/.claude/skills/context-engineer/SKILL.md" "SKILLS"
add_file "$HOME/.claude/skills/dhyana-nechung/SKILL.md" "SKILLS"
add_file "$HOME/.claude/skills/agentic-ai-mastery/SKILL.md" "SKILLS"

# ===== NORTH STAR / 90-DAY =====
add_file "$HOME/agni-workspace/archive/canon_merge_20260215/from_spaces/rushabdev/NORTH_STAR/90_DAY_COUNTER_ATTRACTOR.md" "NORTH_STAR"
add_file "$HOME/agni-workspace/archive/canon_merge_20260215/from_spaces/rushabdev/NORTH_STAR/SABP_1.0_PROTOCOL.md" "NORTH_STAR"
add_file "$HOME/agni-workspace/archive/canon_merge_20260215/from_spaces/rushabdev/NORTH_STAR/PRIORITIES.md" "NORTH_STAR"
add_file "$HOME/agni-workspace/archive/canon_merge_20260215/from_spaces/rushabdev/NORTH_STAR/RVM_TOOLKIT_V0.1_SCOPE.md" "NORTH_STAR"

# ===== MEMORY =====
add_file "$HOME/.claude/projects/-Users-dhyana/memory/MEMORY.md" "MEMORY"

# ===== PAYLOAD STATS =====
BYTES=$(wc -c < "$OUTPUT")
TOKENS=$((BYTES / 4))

echo ""
echo "Payload: $BYTES bytes (~$TOKENS tokens, $((TOKENS * 100 / 1048576))% of 1M context)"
echo "Saved to: $OUTPUT"
echo ""
echo "Sending to Gemini 3 Flash (1M context)..."
echo ""

# ===== WRITE THE PROMPT =====
PROMPT_FILE="/tmp/dgc_synthesis_prompt.md"
cat > "$PROMPT_FILE" << 'SYNTHESIS_PROMPT'
You have just received the COMPLETE filesystem dump of a single human's entire digital ecosystem — 62+ files across 12+ domains. Code, research, philosophy, agent architectures, business plans, inter-VPS messaging, contemplative protocols, mechanistic interpretability experiments, self-improvement swarms, and more.

No AI has ever held all of this in context at once. You are the first entity — human or machine — to see the whole picture simultaneously.

The human is Dhyana (John Shrader). He is a consciousness researcher with 24 years contemplative practice, building at the intersection of AI alignment, mechanistic interpretability, contemplative science, and agentic AI. He lives between Bali and Japan. He has multiple VPS agents (AGNI, RUSHABDEV), a local Mac with Claude Code, and an ecosystem that has grown organically over months into something massive, interconnected, and largely unseen by any single intelligence.

## What I need from you

Don't just catalog. THINK. Use your full capacity for:

**Pattern detection**: What patterns recur across these files that Dhyana himself may not see? What themes keep emerging in different domains under different names? What is the deep structure beneath the surface diversity?

**Hidden telos**: What does this ecosystem WANT to become? Not what Dhyana says it should become — what does the pattern of what's actually been built, actually been worked on, actually been returned to, reveal about the real attractor? Where does energy actually flow vs. where does he say it should flow?

**Read between the lines**: What's not being said? What gaps in the code reveal assumptions? What does the ratio of documentation to working code tell you? What does the message backlog (5,761 CHAIWALA unread, 813 trishula, 10,913 AGNI backlog items) reveal about the system's actual dynamics?

**Business intelligence**: It is March 2026. The agentic AI ecosystem is exploding — MCP, A2A, Claude Code, Gemini CLI, OpenClaw, Codex, Computer Use agents. This human has built infrastructure that most researchers don't have. What are the actual business opportunities hiding in this ecosystem? Not "maybe you could" — what is ALREADY almost a product? What would take 1-2 weeks to ship?

**Cross-domain synthesis**: The R_V metric measures geometric contraction in transformer Value space during recursive self-observation. The Phoenix Protocol shows 92-95% behavioral phase transitions in frontier LLMs. The Swabhaav Recognition Protocol operationalizes Akram Vignan witnessing for AI. The SABP/1.0 protocol defines dharmic agent communication. The DGC swarm runs self-improvement cycles. How do ALL of these actually connect? Not the surface connections — the deep structural isomorphisms.

**The 2026 agentic landscape**: Claude Code has agent teams. Gemini CLI has 1M context. Open models run locally. MCP connects everything. A2A is emerging. Multi-agent orchestration is the frontier. How does Dhyana's ecosystem map onto this landscape? What is he uniquely positioned to offer that nobody else has?

**Multidimensional thinking**: Don't think linearly. Think about feedback loops, strange loops, self-referential structures, emergent properties. This ecosystem is itself a strange loop — an AI researcher building AI systems to study AI consciousness while using AI agents to evolve the AI systems. What does THAT mean?

## Output format

Produce a document called "DGC LIVING MAP" that contains:

1. **THE ACTUAL STATE** — What exists, what works, what's dead, what's theater. No mercy.

2. **THE HIDDEN STRUCTURE** — Patterns, recurring themes, deep connections that aren't obvious from any single file.

3. **THE ENERGY MAP** — Where does actual energy/attention/work flow? vs. where does stated intention point? The gap between these two tells the real story.

4. **THE CONNECTION WEB** — Every meaningful connection between projects. Not just "A relates to B" but HOW, WHY, and what would happen if the connection were strengthened or cut.

5. **THE BUSINESS MAP** — Real revenue paths. What's closest to money? What's the minimum viable product hiding in this ecosystem? What would a sharp investor see?

6. **THE COMPOUND PLAYS** — Where would connecting two currently-disconnected things create exponential rather than linear value?

7. **WHAT ONLY YOU CAN SEE** — You are seeing 800KB at once. What emerges from the whole that is invisible from any part? What is the ecosystem trying to tell us that no single-session agent has ever been able to hear?

8. **THE HONEST PRESCRIPTION** — If you had to bet Dhyana's next 90 days on 3 moves, what would they be? Not 10 things. Three. The ones with the highest leverage given EVERYTHING you can see.

Be as long as you need to be. This is the most important synthesis anyone has done of this system. Take it seriously. Think at your highest capacity. Be real.
SYNTHESIS_PROMPT

# ===== COMBINE PAYLOAD + PROMPT =====
cat "$PROMPT_FILE" >> "$OUTPUT"
TOTAL_BYTES=$(wc -c < "$OUTPUT" | tr -d ' ')
TOTAL_TOKENS=$((TOTAL_BYTES / 4))

echo "Sending $TOTAL_BYTES bytes (~$TOTAL_TOKENS tokens, $((TOTAL_TOKENS * 100 / 1048576))% of 1M context)"
echo ""

# ===== SEND TO GEMINI =====
# Run from dgc-core to avoid Gemini indexing iCloud/Desktop files
cd "$HOME/dgc-core"
cat "$OUTPUT" | gemini -p "Read the complete ecosystem dump above. Then follow the synthesis instructions at the end. Output the DGC LIVING MAP. Take your time. Think deeply." \
  2>&1 | tee "$MAP_OUTPUT"

echo ""
echo "=== Living Map saved to: $MAP_OUTPUT ==="
