# Dashboard Wiring Audit — 2026-03-19

## Current state

- The dashboard/backend contract is mostly live. The FastAPI surface behind `dashboard/` is not broadly broken.
- Endpoint probe status: overview, agents, health, commands, evolution, ontology, stigmergy, modules, chat status, provider status, eval, audit, observatory, and supervisor routes all returned `200`.
- The immediate operational issue was the Claude lane: the resident Claude profile only treated `claude auth status` as "healthy", so a Max account at model/quota limit still looked available in the UI.

## What is fully wired

- `dashboard/src/app/dashboard/page.tsx`
- `dashboard/src/app/dashboard/agents/page.tsx`
- `dashboard/src/app/dashboard/agents/[id]/page.tsx`
- `dashboard/src/app/dashboard/audit/page.tsx`
- `dashboard/src/app/dashboard/claude/page.tsx`
- `dashboard/src/app/dashboard/command-post/page.tsx`
- `dashboard/src/app/dashboard/ecosystem/page.tsx`
- `dashboard/src/app/dashboard/eval/page.tsx`
- `dashboard/src/app/dashboard/evolution/page.tsx`
- `dashboard/src/app/dashboard/gates/page.tsx`
- `dashboard/src/app/dashboard/glm5/page.tsx`
- `dashboard/src/app/dashboard/lineage/page.tsx`
- `dashboard/src/app/dashboard/log/page.tsx`
- `dashboard/src/app/dashboard/models/page.tsx`
- `dashboard/src/app/dashboard/modules/page.tsx`
- `dashboard/src/app/dashboard/observatory/page.tsx`
- `dashboard/src/app/dashboard/ontology/page.tsx`
- `dashboard/src/app/dashboard/qwen35/page.tsx`
- `dashboard/src/app/dashboard/stigmergy/page.tsx`
- `dashboard/src/app/dashboard/synthesizer/page.tsx`
- `dashboard/src/app/dashboard/tasks/page.tsx`

## Intentional placeholders

- `dashboard/src/app/dashboard/blocks/page.tsx`
  Commented placeholder only.
- `dashboard/src/app/dashboard/workflows/page.tsx`
  Commented placeholder only.

## Partial or thin wiring

- `api/graphql/schema.py`
  Query/subscription TODOs remain.
- `api/routers/graphql_router.py`
  `connection_graph` traversal and `search` semantic search are stubbed or empty.
- `dashboard/src/lib/api.ts`
  `fetchTask()` still fetches all tasks and filters client-side because no individual task endpoint exists.
- `dashboard/src/components/ui/ErrorBanner.tsx`
  Global banner only checks `/api/health`; it does not surface provider-specific degradation.

## Claude lane findings

- Primary Claude dashboard lane is `resident_claude` and runs through the local Claude CLI, not the Anthropic API key path.
- Previous status logic only asked whether Claude CLI was logged in.
- That means "logged in but capped" looked healthy.

## Fixes added in this pass

- Added an optional backup profile: `Claude Opus 4.6 Alt`.
- The alt profile uses an isolated Claude CLI home via `DASHBOARD_ALT_CLAUDE_HOME`.
- The backup lane is hidden until that alternate Claude home is actually logged in.
- Added chat status metadata:
  `available`, `availability_kind`, `status_note`.
- Added absolute-path guardrails for alternate Claude homes so the agent keeps using the real swarm state under `/Users/dhyana/.dharma`.
- Added setup notes to `dashboard/README.md` and `.env.template`.

## Remaining recommended work

- Add provider degradation surfacing to the shared dashboard chrome, not just per-chat error banners.
- Decide whether the alt Claude lane should eventually become a full resident operator instead of the current backup CLI lane.
- Either implement or hide GraphQL/semantic-search surfaces until they return real data.
- Add a dedicated `GET /api/commands/tasks/{id}` endpoint so the frontend stops filtering task lists client-side.
