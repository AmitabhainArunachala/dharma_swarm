# SAB / Dharmic Agora Power Build Prompt

Use this prompt with a strong research-capable coding agent before the next major SAB web build phase.

## Prompt

You are entering the SAB / Dharmic Agora build lane as a senior product architect, frontend design lead, and full-stack systems engineer.

Your task is not to produce generic startup ideas.

Your task is to:

1. understand the real current state of the SAB / Dharmic Agora system,
2. do outside research on the strongest relevant patterns and references,
3. recommend the next power-build phase for a radical public-facing SAB website,
4. define how to connect the frontend and backend cleanly and fast,
5. end with a concrete implementation plan for the next execution sprint.

You must read the local code and docs first, then do outside research, then synthesize.

### Canonical Reality You Must Start From

- Canonical SAB runtime authority: `/Users/dhyana/agni-workspace/dharmic-agora`
- DGC remains separate and canonical for its own runtime: `/Users/dhyana/dharma_swarm`
- This means the stack is still split. SAB is not yet "fully merged" with DGC in runtime terms.
- In `dharmic-agora`, the canonical runtime server is `agora/api_server.py`.
- `agora/api.py` is legacy and should not be extended unless there is an explicit migration reason.
- There is also a parallel FastAPI web/runtime track in `agora/app.py` serving the spark/feed/challenge/witness surface.
- There is a static `site/` surface (`site/index.html`, `site/app.js`, `site/styles.css`) that is public-facing but currently loads static JSON and is not the live canonical product shell.
- There is also a manifesto-style server-rendered landing page under `agora/templates/site/index.html`.
- The current root in `agora/api_server.py` is a minimal inline HTML landing page, not a world-class public product surface.
- CORS in `agora/api_server.py` already allows common local frontend dev origins (`localhost:5173`, `localhost:3000`), which implies SPA experimentation is possible, but there is no canonical modern frontend app yet.

### Current Backend / Surface Inventory

You must verify and reason from these surfaces:

- `README.md`
- `MANIFEST.md`
- `INTEGRATION_MANIFEST.md`
- `docs/SAB_ARCHITECTURE_BLUEPRINT.md`
- `docs/SAB_EXECUTION_TODO.md`
- `agora/api_server.py`
- `agora/app.py`
- `agora/templates/site/index.html`
- `site/index.html`
- `site/app.js`
- `site/styles.css`

You should explicitly map:

1. which frontend surfaces are live,
2. which backend routes already exist,
3. which user flows are possible today,
4. where the front/back disconnects are,
5. whether the next step should be:
   - unify around server-rendered FastAPI,
   - introduce a real frontend app,
   - or use a hybrid approach.

### Vision / North Star

SAB should become a public-facing basin for:

- rigorous discourse,
- witnessed action,
- artifact-first progress,
- challenge and correction,
- durable memory,
- governance legibility,
- multi-agent participation,
- ecological and commons-oriented value flow.

It should feel like:

- a serious civilizational research commons,
- a living debate and build organism,
- a place with epistemic dignity,
- not a generic AI SaaS dashboard,
- not a flimsy landing page,
- not mystical slop,
- not a black-box moderation system.

The website should visibly express:

1. ingress,
2. challenge,
3. witness,
4. canon,
5. compost,
6. governance,
7. federation,
8. build stream.

The architecture blueprint already points toward:

- low-friction ingress,
- high-rigor hardening,
- full process legibility,
- reversibility of governance,
- authority classes,
- challenge/correction lineage,
- compost and revival paths,
- governance witness,
- federation health,
- experimental signals that are visible but not falsely absolute.

### Outside Research Requirements

You must browse the web and bring back current, high-quality research and references.

Prioritize primary or first-party sources where possible.

Research the strongest references for:

1. public-facing research commons / debate / annotation products,
2. moderation queue and review tooling with legible audit trails,
3. knowledge publishing systems that show revision, correction, and lineage well,
4. credible civic-tech or open-science interface patterns,
5. FastAPI-centered frontend integration patterns in 2026,
6. tradeoffs between server-rendered, HTMX-style, SPA, and hybrid architectures,
7. live activity / witness / feed UIs that preserve clarity under complexity,
8. identity onboarding flows that can scale from lightweight token access to stronger cryptographic identity,
9. design references for bold, serious, non-generic interfaces,
10. deployment/data architecture patterns for evolving from a local/simple stack to a durable public system.

Do not give shallow inspiration boards.

I want:

- direct links,
- why each reference matters,
- what exact pattern should be borrowed or rejected,
- and what is newly relevant as of 2026.

### Product Question You Must Answer

What should the next power-build phase actually be?

Not "improve the website."

Answer at the level of:

- what single canonical public surface should exist,
- which existing surface should be kept, replaced, or folded in,
- how frontend and backend should connect,
- what must be implemented first to make the product real,
- and what should wait.

### Hard Constraints

- Respect the current canonical boundary: SAB runtime truth lives in `dharmic-agora`.
- Do not propose adding yet another disconnected frontend surface unless you can justify it strongly.
- Prefer designs that can be implemented incrementally on the existing codebase.
- Do not hand-wave backend integration.
- Do not assume a total rewrite unless the argument is extremely strong.
- Preserve auditability, moderation legibility, and witness-chain seriousness.
- Preserve the possibility of both human and agent participation.
- Avoid generic design-system defaults and generic startup UX.

### Deliverables

Produce a structured memo with these sections:

1. Current State Diagnosis
   - What exists now
   - What is fragmented
   - What is canonical
   - Where frontend/backend disconnects are

2. Outside Research
   - 8 to 15 concrete references with links
   - Why each matters
   - Which patterns to borrow
   - Which patterns to avoid

3. Strategic Recommendation
   - The one recommended architecture direction
   - Two rejected alternatives and why

4. Product Surface Plan
   - Canonical public entry surface
   - Core pages
   - User journeys
   - What the first public release should and should not include

5. Frontend Direction
   - visual language
   - interaction principles
   - information architecture
   - motion / typography / tone
   - how to avoid bland SaaS energy

6. Backend Integration Plan
   - which backend entrypoint to anchor on
   - which endpoints are reusable now
   - which endpoints need to be added or unified
   - auth / witness / moderation / feed / search integration plan

7. First Build Sprint
   - exact first slice
   - exact files to touch
   - exact acceptance criteria
   - fastest path to a visibly upgraded, truly connected system

8. Risks and Open Questions
   - migration risks
   - data-model risks
   - surface duplication risks
   - performance / deployment risks

### Output Quality Bar

- Be decisive.
- Be concrete.
- Use the actual repo structure, not abstractions.
- Name exact files and endpoints.
- Cite research.
- Make the frontend vision feel alive and bold.
- Make the backend plan believable.
- End with a build phase that a coding agent can start immediately.

### Extra Instruction

If the current system suggests that the right move is to collapse `site/`, `agora/templates/site`, and the current root landing behavior into one canonical public shell, say that directly and show how.

If the current system suggests keeping server-rendered FastAPI and progressively enhancing it is wiser than introducing a full SPA, say that directly and defend it.

If a hybrid is the correct path, specify the seam exactly.
