# Publish Tomorrow Checklist

Canonical repo target:
- `https://github.com/shakti-saraswati/dharma_swarm`

## One command
From `/Users/dhyana/dharma_swarm`:

```bash
bash scripts/publish_canonical.sh
```

## If auth is stale
Run:

```bash
env -u GITHUB_TOKEN -u GH_TOKEN gh auth login --hostname github.com --git-protocol https --web
```

Then run:

```bash
bash scripts/publish_canonical.sh
```

## What this script does
1. Verifies `gh` auth is valid.
2. Creates `shakti-saraswati/dharma_swarm` as private if missing.
3. Sets local `origin` to the canonical URL.
4. Pushes `main` with upstream tracking.
