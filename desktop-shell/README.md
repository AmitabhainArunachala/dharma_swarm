# DHARMA COMMAND Desktop Shell

This is the repo-local macOS app shell for `dharma_swarm`.

It is intentionally thin:

- it does not fork the dashboard UI
- it opens the canonical dashboard routes inside a native window
- it leans on the same launchd-backed runtime used by the browser version

## What stays the same

The route surface stays the same:

- browser: `http://127.0.0.1:3420/dashboard`
- app shell: same dashboard surface, wrapped in a native window

That is the long-term product direction too. The UI can become a packaged app
without creating a second control plane.

## Current scope

This scaffold is intentionally repo-local for now:

- it starts the dashboard runtime through `scripts/dashboard_ctl.sh`
- it opens `http://127.0.0.1:3420/dashboard`
- it is a thin operator shell, not yet a self-contained distributable bundle

That is enough to validate the product architecture before sidecars, embedded
services, or a fully self-contained `.app` bundle.

## Commands

```bash
cd /Users/dhyana/dharma_swarm/desktop-shell
npm install
npm run dev
```

Build the shell binary:

```bash
cd /Users/dhyana/dharma_swarm/desktop-shell
npm run build
```

## Long-term path

The product path is:

1. stable local runtime supervision (`launchd` today)
2. stable same-origin API contract (`/api/...`)
3. native shell around the same dashboard routes
4. later, replace repo-relative startup with bundled sidecars or an embedded runtime
