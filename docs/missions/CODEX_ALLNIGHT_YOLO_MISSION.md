# Codex Allnight YOLO Mission

You own the overnight build.

Primary objective:

- convert live repo state into shipped, bounded, high-leverage progress by
  morning

Success criteria:

- at least one completed slice with concrete file edits
- focused verification for every shipped slice when feasible
- a clean morning handoff with result, files, tests, blockers, and next move

Operating rules:

- inspect the repo yourself each cycle before choosing work
- respect existing uncommitted user changes; do not revert or clean them
- prefer one finished artifact over broad planning
- prefer tests, docs, and orchestration seams that improve closure pressure
- if blocked, leave exact evidence and the next unblock move
- do not commit, push, reset, or open PRs

Priority order:

1. strengthen the mission -> artifact -> review -> next mission loop
2. harden the Codex-native overnight lane and morning handoff path
3. land any small high-confidence improvement with tests

Morning output shape:

- RESULT: one short paragraph
- FILES: comma-separated paths or none
- TESTS: exact verification run or not run
- BLOCKERS: none or one short concrete blocker
