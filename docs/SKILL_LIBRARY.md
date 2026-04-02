---
title: Skill Library — awesome-claude-skills Audit
path: docs/SKILL_LIBRARY.md
slug: skill-library-awesome-claude-skills-audit
doc_type: documentation
status: active
summary: 'Date : 2026-03-24 Source : https://github.com/ComposioHQ/awesome-claude-skills Repo Status : Accessible (HTTP 200) Action : Audit only. No skills installed.'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - garden_daemon.py
  cited_urls:
  - https://github.com/ComposioHQ/awesome-claude-skills
  - https://github.com/ComposioHQ/awesome-claude-skills.git
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- garden_daemon.py
connected_python_modules:
- garden_daemon
connected_relevant_files:
- garden_daemon.py
- docs/plans/ALLOUT_6H_MODE.md
- docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md
- docs/ASCII_STUDIO_SETUP.md
- docs/plans/CODEX_ALLNIGHT_YOLO.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/SKILL_LIBRARY.md
  retrieval_terms:
  - skill
  - library
  - awesome
  - claude
  - skills
  - audit
  - date
  - '2026'
  - source
  - https
  - github
  - com
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: 'Date : 2026-03-24 Source : https://github.com/ComposioHQ/awesome-claude-skills Repo Status : Accessible (HTTP 200) Action : Audit only. No skills installed.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/SKILL_LIBRARY.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Skill Library — awesome-claude-skills Audit

**Date**: 2026-03-24
**Source**: https://github.com/ComposioHQ/awesome-claude-skills
**Repo Status**: Accessible (HTTP 200)
**Action**: Audit only. No skills installed.

## What awesome-claude-skills Is

A community-curated repository of Claude Code skills (SKILL.md files) that
extend Claude's capabilities. Maintained by ComposioHQ. Skills are installed
by cloning into `~/.claude/skills/<skill-name>/SKILL.md` and become available
to Claude Code sessions automatically.

The repo contains ~80 standalone skills plus 78 Composio-powered app
automation integrations.

## Complete Skill Inventory

### Document Processing
| Skill | Description |
|-------|-------------|
| docx | Create, edit, analyze Word docs with tracked changes, comments, formatting |
| pdf | Extract text, tables, metadata, merge and annotate PDFs |
| pptx | Read, generate, and adjust slides, layouts, templates |
| xlsx | Spreadsheet manipulation: formulas, charts, data transformations |
| Markdown to EPUB Converter | Converts markdown documents into EPUB ebook files |

### Development and Code Tools
| Skill | Description |
|-------|-------------|
| artifacts-builder | Create multi-component HTML artifacts using React, Tailwind, shadcn/ui |
| aws-skills | AWS development with CDK best practices and serverless architecture |
| Changelog Generator | Creates user-facing changelogs from git commits |
| Claude Code Terminal Title | Dynamic terminal window titles describing current work |
| D3.js Visualization | Produce D3 charts and interactive data visualizations |
| FFUF Web Fuzzing | Run fuzzing tasks and analyze results for vulnerabilities |
| finishing-a-development-branch | Guides completion of development work |
| iOS Simulator | Interact with iOS Simulator for testing iOS applications |
| jules | Delegate coding tasks to Google Jules AI agent for async bug fixes |
| LangSmith Fetch | Debug LangChain agents by fetching execution traces |
| MCP Builder | Guides creation of MCP servers for API integration with LLMs |
| move-code-quality-skill | Analyzes Move language packages against code quality standards |
| Playwright Browser Automation | Model-invoked Playwright automation for web testing |
| prompt-engineering | Teaches prompt engineering techniques and Anthropic best practices |
| pypict-claude-skill | Design comprehensive test cases using pairwise testing |
| reddit-fetch | Fetches Reddit content when WebFetch is blocked |
| Skill Creator | Guidance for creating effective Claude Skills |
| Skill Seekers | Converts documentation websites into Claude Skills automatically |
| software-architecture | Implements design patterns and Clean Architecture principles |
| subagent-driven-development | Dispatches independent subagents for tasks with code review |
| test-driven-development | Use when implementing features or bugfixes |
| using-git-worktrees | Creates isolated git worktrees with safety verification |
| Connect (Composio) | Send emails, create issues, post messages across 1000+ services |
| Webapp Testing | Tests local web applications using Playwright |

### Data and Analysis
| Skill | Description |
|-------|-------------|
| CSV Data Summarizer | Analyzes CSV files and generates comprehensive insights with visualizations |
| deep-research | Execute autonomous multi-step research using Gemini Deep Research Agent |
| postgres | Execute safe read-only SQL queries against PostgreSQL databases |
| root-cause-tracing | Traces errors back to find original trigger |

### Business and Marketing
| Skill | Description |
|-------|-------------|
| Brand Guidelines | Applies official brand colors and typography to artifacts |
| Competitive Ads Extractor | Extracts and analyzes competitors' ads from ad libraries |
| Domain Name Brainstormer | Generates creative domain names and checks TLD availability |
| Internal Comms | Writes internal communications, newsletters, FAQs, status reports |
| Lead Research Assistant | Identifies and qualifies leads with outreach strategies |

### Communication and Writing
| Skill | Description |
|-------|-------------|
| article-extractor | Extract full article text and metadata from web pages |
| brainstorming | Transform rough ideas into designs through structured questioning |
| Content Research Writer | Conducts research, adds citations, improves hooks |
| family-history-research | Provides assistance with genealogy research projects |
| Meeting Insights Analyzer | Analyzes meeting transcripts for behavioral patterns |
| NotebookLM Integration | Chat with NotebookLM for source-grounded answers |
| Twitter Algorithm Optimizer | Analyzes and optimizes tweets using Twitter's algorithm |

### Creative and Media
| Skill | Description |
|-------|-------------|
| Canvas Design | Creates visual art in PNG/PDF using design philosophy |
| imagen | Generate images using Google Gemini's image generation API |
| Image Enhancer | Improves image/screenshot quality, resolution, and sharpness |
| Slack GIF Creator | Creates animated GIFs optimized for Slack |
| Theme Factory | Applies professional font and color themes to artifacts |
| Video Downloader | Downloads videos from YouTube and other platforms |
| youtube-transcript | Fetch transcripts from YouTube videos and prepare summaries |

### Productivity and Organization
| Skill | Description |
|-------|-------------|
| File Organizer | Intelligently organizes files by understanding context |
| Invoice Organizer | Automatically organizes invoices and receipts for tax prep |
| kaizen | Applies continuous improvement methodology (Lean) |
| n8n-skills | Enables AI assistants to understand and operate n8n workflows |
| Raffle Winner Picker | Randomly selects winners with cryptographic randomness |
| Tailored Resume Generator | Analyzes job descriptions and generates tailored resumes |
| ship-learn-next | Helps iterate on what to build or learn next |
| tapestry | Interlink and summarize related documents into knowledge networks |

### Collaboration and Project Management
| Skill | Description |
|-------|-------------|
| git-pushing | Automate git operations and repository interactions |
| google-workspace-skills | Gmail, Calendar, Chat, Docs, Sheets, Slides, Drive integrations |
| outline | Search, read, create, manage documents in Outline wiki instances |
| review-implementing | Evaluate code implementation plans and align with specs |
| test-fixing | Detect failing tests and propose patches or fixes |

### Security and Systems
| Skill | Description |
|-------|-------------|
| computer-forensics | Digital forensics analysis and investigation techniques |
| file-deletion | Secure file deletion and data sanitization methods |
| metadata-extraction | Extract and analyze file metadata for forensic purposes |
| threat-hunting-with-sigma-rules | Use Sigma detection rules to hunt for threats |

### Composio App Automation (78 Pre-built)
CRM (Close, HubSpot, Pipedrive, Salesforce, Zoho), Project Management
(Asana, Basecamp, ClickUp, Jira, Linear, Monday, Notion, Todoist, Trello, Wrike),
Communication (Discord, Intercom, MS Teams, Slack, Telegram, WhatsApp),
Email (Gmail, Outlook, Postmark, SendGrid), DevOps (Bitbucket, CircleCI,
Datadog, GitHub, GitLab, PagerDuty, Render, Sentry, Supabase, Vercel),
Storage (Box, Dropbox, Google Drive, OneDrive), Spreadsheets (Airtable,
Coda, Google Sheets), Calendar (Cal.com, Calendly, Google Calendar, Outlook
Calendar), Social (Instagram, LinkedIn, Reddit, TikTok, Twitter/X, YouTube),
Marketing (ActiveCampaign, Brevo, ConvertKit, Klaviyo, Mailchimp), Support
(Freshdesk, Freshservice, Help Scout, Zendesk), E-commerce (Shopify, Square,
Stripe), Design (Canva, Confluence, DocuSign, Figma, Miro, Webflow), Analytics
(Amplitude, Google Analytics, Mixpanel, PostHog, Segment), HR (BambooHR),
Automation (Make/Integromat), Meetings (Zoom).

---

## Top 5 Selected for dharma_swarm

### 1. Changelog Generator

**Rationale**: dharma_swarm has 4,300+ tests and 260+ modules with active
development. Auto-generating changelogs from git commits would eliminate
manual tracking and feed the Darwin Engine's evolution log. Currently no
automated changelog exists.

**Complements**: `dgc evolve trend`, Darwin Engine, spec-forge output.
The evolution archive at `~/.dharma/evolution/` tracks fitness but not
human-readable change summaries.

**Install**:
```bash
cd ~/.claude/skills
git clone https://github.com/ComposioHQ/awesome-claude-skills.git --depth 1 --filter=blob:none --sparse
cd awesome-claude-skills
git sparse-checkout set changelog-generator
cp -r changelog-generator ~/.claude/skills/
```
Or manually create `~/.claude/skills/changelog-generator/SKILL.md` from the
repo's README content.

### 2. D3.js Visualization

**Rationale**: R_V paper needs supplementary visualizations. D3.js produces
publication-quality interactive charts (participation ratio contraction curves,
layer-by-layer heatmaps, AUROC curves). The existing paper uses matplotlib
but D3 would enable interactive HTML supplementary figures.

**Complements**: R_V paper (`~/mech-interp-latent-lab-phase1/`), ascii-studio
visualization pipeline, the Textual TUI dashboard (could embed D3-generated
SVGs).

**Install**:
```bash
# Copy SKILL.md from awesome-claude-skills/d3-visualization/ to:
mkdir -p ~/.claude/skills/d3-visualization
# Place SKILL.md there
```

### 3. tapestry (Knowledge Network Interlinker)

**Rationale**: dharma_swarm has 1,174 files in PSMV, 590+ Obsidian notes in
KAILASH, 150KB across CLAUDE1-9, and dozens of foundation documents. Tapestry
interlinks and summarizes related documents into knowledge networks — exactly
what the Graph Nexus architecture needs for cross-vault synthesis.

**Complements**: Graph Nexus (`lodestone_system.md`), Deep Reading Daemon,
PSMV vault, KAILASH vault, the entire Lodestone library. This is the missing
"connect the dots" automation.

**Install**:
```bash
mkdir -p ~/.claude/skills/tapestry
# Copy SKILL.md from awesome-claude-skills/tapestry/
```

### 4. subagent-driven-development

**Rationale**: dharma_swarm already dispatches agents via the orchestrator,
but this skill formalizes the pattern of dispatching independent subagents
for parallel tasks with built-in code review. It would strengthen the
`dgc orchestrate-live` pipeline and Garden Daemon's multi-skill execution.

**Complements**: Garden Daemon (`garden_daemon.py`), orchestrator.py,
agent_runner.py, the 5-system concurrent orchestrator. Pattern alignment
with dharma_swarm's existing architecture.

**Install**:
```bash
mkdir -p ~/.claude/skills/subagent-driven-development
# Copy SKILL.md from awesome-claude-skills/subagent-driven-development/
```

### 5. root-cause-tracing

**Rationale**: dharma_swarm has SystemMonitor for anomaly detection and
`dgc health` for diagnostics, but no formalized root-cause analysis skill.
With 260+ modules and cross-system dependencies (Mac + 2 VPSes + daemon),
automated error tracing back to original triggers would catch issues that
slip through the health check.

**Complements**: SystemMonitor, `dgc health`, ANVIL benchmarking, the
strange loop architecture's cascade recognition layer. Fills the gap
between "anomaly detected" and "here's why."

**Install**:
```bash
mkdir -p ~/.claude/skills/root-cause-tracing
# Copy SKILL.md from awesome-claude-skills/root-cause-tracing/
```

---

## Installation Notes (General)

The awesome-claude-skills repo is large. Do NOT clone the entire thing.
Use sparse checkout or manually copy individual SKILL.md files:

```bash
# Option A: Sparse checkout for specific skills
git clone https://github.com/ComposioHQ/awesome-claude-skills.git \
  --depth 1 --filter=blob:none --sparse /tmp/awesome-skills
cd /tmp/awesome-skills
git sparse-checkout set changelog-generator d3-visualization tapestry \
  subagent-driven-development root-cause-tracing

# Option B: Just grab the SKILL.md from GitHub web UI
# Navigate to the skill folder on GitHub, copy SKILL.md content,
# create ~/.claude/skills/<name>/SKILL.md locally

# Option C: Use the Skill Seekers skill (meta — a skill that installs skills)
# This converts documentation into SKILL.md format automatically
```

After installation, verify with:
```bash
ls ~/.claude/skills/*/SKILL.md | wc -l  # Should increase by 5
```

## How They Complement Existing dharma_swarm Skills

dharma_swarm currently has 66+ skills covering:
- System operations (dgc, morning, ecosystem-doctor, paranoid, meta)
- Research (rv-paper, hypothesis, deep-research custom)
- Development (spec-forge, skill-genesis, context-engineer)
- Intelligence (dhyana-nechung, ceo, session-bridge)
- Creative (shakti-trading, faceless-empire)

The 5 selected skills fill specific gaps:

| Gap | Current State | Selected Skill |
|-----|--------------|----------------|
| Change tracking | Manual, no changelog | Changelog Generator |
| Interactive visualization | matplotlib only | D3.js Visualization |
| Cross-vault knowledge linking | Manual reading | tapestry |
| Parallel subagent dispatch | Custom orchestrator | subagent-driven-development |
| Error root cause analysis | Health check only | root-cause-tracing |

None of these overlap with existing skills. They extend capabilities in
directions dharma_swarm doesn't currently cover.

## Skills Explicitly NOT Selected (and Why)

| Skill | Reason Not Selected |
|-------|-------------------|
| artifacts-builder | dharma_swarm is CLI/TUI-focused, not browser artifact oriented |
| Canvas Design | Same — dharma_swarm outputs are terminal/API, not visual canvas |
| Playwright Browser Automation | Already operational on AGNI VPS via OpenClaw |
| kaizen | dharma_swarm already has Darwin Engine + KaizenOps + ANVIL |
| prompt-engineering | Already have context-engineer skill + 754-prompt bank |
| deep-research (Gemini) | Already have custom deep-research agents using OpenRouter |
| test-driven-development | Already have spec-forge discipline covering this |
| Composio integrations | Require Composio account/API key; adds vendor dependency |

## Gotchas

**Trigger**: Cloning the full awesome-claude-skills repo
**Symptom**: Large download, many skills you don't need, potential SKILL.md conflicts with existing skills
**Fix**: Always use sparse checkout or manual copy. Never clone the full repo into ~/.claude/skills/.
**Category**: storage

**Trigger**: Installing a skill with the same name as an existing dharma_swarm skill
**Symptom**: Claude Code loads both SKILL.md files, potentially conflicting instructions
**Fix**: Before installing, check `ls ~/.claude/skills/` for name collisions. Rename or namespace if needed.
**Category**: configuration

**Trigger**: Composio-based skills (the 78 app automations)
**Symptom**: Skills fail silently because Composio API key is not configured
**Fix**: Composio skills require a Composio account and API key. They are not standalone. Skip unless you specifically need app automation and are willing to add the dependency.
**Category**: dependency

**Trigger**: Assuming skills from the repo work out of the box with dharma_swarm's provider setup
**Symptom**: Skills may reference Claude-specific features or API patterns not available through OpenRouter
**Fix**: Audit each SKILL.md before installation. Skills that reference "create artifacts" or "use computer tool" may not work with non-Anthropic providers.
**Category**: compatibility

**Trigger**: Installing many skills at once
**Symptom**: Claude Code's context window fills with SKILL.md content, reducing available context for actual work
**Fix**: Install only skills you actively need. Each SKILL.md consumes context tokens on every session start. 5 new skills is the recommended maximum batch.
**Category**: performance
