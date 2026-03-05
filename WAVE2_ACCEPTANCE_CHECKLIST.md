# Wave 2 Acceptance Checklist

Use this after Claude's Wave 2 completes.

## Hard Gates (must pass)
- [ ] Full test suite passes.
- [ ] No false-success semantics (failed runs are not marked completed).
- [ ] Canonical CLI path works (`/opt/homebrew/bin/dgc`).
- [ ] No new split-brain runtime path introduced.
- [ ] Telos gates remain enforceable.
- [ ] Evolution path has working rollback with lineage.

## Quality Gates (should pass)
- [ ] New modules have focused tests with clear behavioral assertions.
- [ ] TUI/CLI commands are additive and backward compatible.
- [ ] No fake stubs in critical paths (`gate`, `sandbox`, `promote`, `rollback`).
- [ ] Process-level observability improved (runtime/git/truth visibility).

## Living Layers Guardrail
- [ ] `specs/research_living_layers/` remains intact as v2+ north star.
- [ ] Living-layer features (Shakti/Stigmergy/Subconscious) are either:
  - [ ] integrated with tests and governance checks, or
  - [ ] explicitly deferred with rationale.

## One-command verification
Run:

```bash
scripts/wave2_acceptance_gate.sh --triple
```

Output report path:

- `reports/verification/wave2_acceptance_YYYYMMDD_HHMMSS.md`
