# Cold-Start Growth Engine

Date: 2026-03-13
Purpose: define how DGC acquires customers without a warm network
Status: recommended operating model

## Core decision

Do not wait for a warm graph that does not exist.

Build a `reachability graph` with three valid lanes:

- `warm`
  - real relationship path exists
- `public_signal_cold`
  - pain and timing are visible from public evidence
- `inbound`
  - the buyer came through public proof, content, or tooling

For DGC right now, the first lane is mostly absent.
The second and third lanes are the ones to build.

## The acquisition engine

Use this loop:

`public signals -> score -> mini dossier -> Signal Brief -> tailored outreach -> call -> paid Campaign X-Ray -> case study -> stronger inbound`

This is the bootstrap path.

## Public-signal sources

The first cold graph should come from sources like:

- GitHub repos with dense issue backlogs, stalled releases, or obvious context sprawl
- Y Combinator company pages and recent launches
- Product Hunt launches with active shipping pressure
- company hiring pages for AI platform, evals, agent, infra, or knowledge roles
- engineering posts that reveal a current coordination bottleneck

These are not "warm."
They are simply legitimate, inspectable signals.

## The front-door offer

Do not cold-sell the full `Campaign X-Ray` blind.

Insert a lighter front door:

- `Signal Brief`
  - public-data-only
  - one page or short memo
  - one inferred campaign
  - one blocker pattern
  - one suggested next artifact
  - one clear statement of evidence limits

The goal of the `Signal Brief` is not revenue.
Its goal is reply rate, trust, and permission for the paid diagnostic.

## Offer ladder

Use this sequence:

`Signal Brief -> Campaign X-Ray -> Campaign Sprint -> Campaign Desk`

Notes:

- `Signal Brief` is a lead asset, not the main product
- `Campaign X-Ray` remains the first real paid offer
- `Campaign Sprint` is where proof compounds
- `Campaign Desk` only follows successful delivery

## What 5-10 agents should do

If you put a swarm on growth, the agents should show concrete output, not chatter:

- `Signal scout`
  - finds public triggers and candidate accounts
- `Lead scorer`
  - scores pain, urgency, density, and proof value
- `Dossier builder`
  - compiles repo, docs, launch pages, and hiring evidence
- `Signal Brief writer`
  - drafts the one-page cold-start brief
- `Contradiction hunter`
  - identifies where the account is likely losing continuity
- `Personalizer`
  - converts the brief into one credible email
- `Compliance guard`
  - checks claims, unsubscribe line, and sender rules
- `Sender`
  - schedules and tracks outbound
- `Reply triage`
  - classifies responses and proposes the next move
- `Closer`
  - turns replies into calls, X-Rays, and sprints

## Daily output standard

The swarm should be measured on outputs like:

- `20-30` candidates scanned
- `5-10` scored targets
- `3` high-quality `Signal Briefs`
- `3` tailored outreach sends
- `1` published proof artifact each week

Anything more automated than that before conversion proof exists will drift into spam.

## Guardrails

Do not do any of these:

- send generic AI-written spam at volume
- call cold accounts "warm"
- hide uncertainty in a public-data-only brief
- rely on LinkedIn automation as the core channel
- publish scaled low-value SEO sludge

## What success looks like in 30 days

My operating inference:

- `100-150` accounts scanned from public signals
- `20-30` strong candidates scored
- `10-15` `Signal Briefs` produced
- `20-30` tailored cold emails sent
- `4-8` reply threads
- `2-4` live calls
- `1` paid `Campaign X-Ray`

That is enough to prove the engine.

## Why this is better than trading or random micro-SaaS

- it exercises DGC's real strengths
- it generates buyer conversations directly
- it produces reusable proof assets
- it compounds into a case-study and inbound loop
- it funds the deeper product instead of distracting from it
