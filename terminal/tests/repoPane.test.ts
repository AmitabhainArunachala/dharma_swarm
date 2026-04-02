import {describe, expect, test} from "bun:test";
import React from "react";

import {RepoPane, buildRepoPaneSections} from "../src/components/RepoPane";
import {workspacePreviewToLines, workspaceSnapshotToPreview} from "../src/protocol";
import type {TabPreview, TranscriptLine} from "../src/types";

function flattenElementText(node: React.ReactNode): string[] {
  if (node === null || node === undefined || typeof node === "boolean") {
    return [];
  }
  if (typeof node === "string" || typeof node === "number") {
    return [String(node)];
  }
  if (Array.isArray(node)) {
    return node.flatMap((child) => flattenElementText(child));
  }
  if (React.isValidElement(node)) {
    return flattenElementText(node.props.children);
  }
  return [];
}

describe("buildRepoPaneSections", () => {
  test("renders live workspace snapshot facts in the visible repo pane", () => {
    const workspaceSnapshot = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/src/components/RepoPane.tsx; terminal/tests/repoPane.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511
- .json: 91
- .sh: 68

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36

## Most imported local modules
- dharma_swarm.models | inbound 159
- dharma_swarm.stigmergy | inbound 35`;
    const preview = workspaceSnapshotToPreview(workspaceSnapshot);
    const lines = workspacePreviewToLines(preview);
    const pane = RepoPane({title: "Repo", preview, lines, controlPreview: undefined, controlLines: []});
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain("Operator Snapshot");
    expect(visibleText).toContain("Git main@95210b1 | high (563 local changes) | sync tracking origin/main in sync");
    expect(visibleText).toContain("Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)");
    expect(visibleText).toContain("Snapshot branch main@95210b1 | tracking origin/main in sync");
    expect(visibleText).toContain("Snapshot dirty high (563 local changes) | staged 0 | unstaged 517 | untracked 46");
    expect(visibleText).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)");
    expect(visibleText).toContain(
      "Snapshot topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked); dgc-core clean",
    );
    expect(visibleText).toContain(
      "Snapshot hotspots change terminal (281) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(visibleText).toContain("Snapshot summary topology sab_canonical_repo_missing; high (563 local changes)");
    expect(visibleText).toContain("hotspots change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)");
    expect(visibleText).toContain("Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing");
    expect(visibleText).toContain("Snapshot focus Root /Users/dhyana/dharma_swarm | lead terminal/src/app.tsx");
    expect(visibleText).toContain("Snapshot pressure Topology pressure dharma_swarm Δ563 (517 modified, 46 untracked); dgc-core clean | peers 2");
    expect(visibleText).toContain("Snapshot topology pressure 1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(visibleText).toContain("Snapshot hotspot pressure change terminal (281) | dep dharma_swarm.models | inbound 159");
    expect(visibleText).toContain("Branch main@95210b1");
    expect(visibleText).toContain("Health topology sab_canonical_repo_missing; high (563 local changes) | origin/main | ahead 0 | behind 0");
    expect(visibleText).toContain(
      "Snapshot hotspot summary change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)",
    );
  });

  test("shows authority state when the repo snapshot is a placeholder", () => {
    const sections = buildRepoPaneSections(
      {
        Authority: "placeholder | bridge offline | awaiting authoritative repo refresh",
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        "Repo risk": "unknown",
        "Repo risk preview": "unknown",
        "Dirty pressure": "unknown",
        Staged: "0",
        Unstaged: "0",
        Untracked: "0",
        "Topology status": "unknown",
        "Topology warnings": "0",
        "Primary warning": "none",
        "Topology warning severity": "unknown",
        "Hotspot summary": "none",
        "Primary changed hotspot": "none",
        "Primary changed path": "none",
        "Primary dependency hotspot": "none",
        "Topology pressure": "none",
        "Topology risk": "none",
        "Primary topology peer": "none",
        "Peer drift markers": "none",
        "Topology peers": "none",
        "Topology peer count": "0",
        "Branch sync preview": "unknown",
      },
      [],
    );

    expect(sections[0]?.rows[0]).toBe("Authority placeholder | bridge offline | awaiting authoritative repo refresh");
    expect(sections[1]?.rows[0]).toBe("Authority placeholder | bridge offline | awaiting authoritative repo refresh");
  });

  test("renders structured repo sections from preview fields", () => {
    const preview: TabPreview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch status": "tracking origin/main in sync",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      Dirty: "0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology peer count": "2",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Hotspot summary":
        "change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
      "Changed paths":
        "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      Hotspots: "dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
      "Inbound hotspots": "dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35",
      Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
      "Language mix": ".py: 1125; .md: 511; .json: 91; .sh: 68",
    };
    const controlPreview: TabPreview = {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Runtime activity": "Sessions=18  Runs=0",
      "Artifact state": "Artifacts=7  ContextBundles=1",
      "Loop state": "cycle 23 running",
      "Loop decision": "continue required",
      "Active task": "terminal-repo-pane",
      "Task progress": "3 done, 1 pending of 4",
      "Result status": "complete",
      Acceptance: "pass",
      "Last result": "complete / pass",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Runtime freshness":
        "cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "complete / pass | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
      Toolchain: "claude, python3, node",
      Alerts: "none",
    };

    const sections = buildRepoPaneSections(preview, [], controlPreview, [], new Date("2026-04-01T04:00:00Z"));

    expect(sections).toEqual([
      {
        title: "Operator Snapshot",
        rows: [
          "Git main@95210b1 | high (552 local changes) | sync tracking origin/main in sync",
          "Dirty staged 0 | unstaged 510 | untracked 42 | topo 1 (sab_canonical_repo_missing) | lead terminal (274)",
          "Snapshot branch main@95210b1 | tracking origin/main in sync",
          "Snapshot dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
          "Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)",
          "Snapshot warnings sab_canonical_repo_missing | severity high",
          "Snapshot topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
          "Snapshot hotspots change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
          "Snapshot hotspot summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Snapshot summary topology sab_canonical_repo_missing; high (552 local changes) | hotspots change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Snapshot focus Root /Users/dhyana/dharma_swarm | lead terminal/src/protocol.ts",
          "Snapshot pressure Topology pressure dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean | peers 2",
          "Snapshot topology pressure 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
          "Snapshot repo/control unknown | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Task terminal-repo-pane | complete/pass | tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Control pulse unknown | complete / pass | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass",
          "Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next n/a",
          "Freshness unknown | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Snapshot",
        rows: [
          "Root /Users/dhyana/dharma_swarm",
          "Branch main@95210b1",
          "Track tracking origin/main in sync | upstream origin/main",
          "Branch preview tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
          "Sync origin/main | ahead 0 | behind 0 | +0/-0",
          "Health topology sab_canonical_repo_missing; high (552 local changes) | origin/main | ahead 0 | behind 0",
          "Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Snapshot task terminal-repo-pane | complete/pass | cycle 23 running | continue required",
          "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Snapshot freshness unknown | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Snapshot truth tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 23 running | next n/a",
          "Dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
          "Hotspots change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Warnings sab_canonical_repo_missing | severity high",
          "Lead change terminal (274) | path terminal/src/protocol.ts",
          "Lead file dgc_cli.py (6908 lines)",
          "Lead dep dharma_swarm.models | inbound 159",
        ],
      },
      {
        title: "Repo Risk",
        rows: [
          "Repo topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes) | peers 2",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high | warning sab_canonical_repo_missing",
          "Peer drift dharma_swarm track main...origin/main",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
          "Repo preview tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Risk sab_canonical_repo_missing",
          "State 0 staged, 510 unstaged, 42 untracked",
          "Topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)",
          "Topology signal high | dharma_swarm track main...origin/main",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead warning sab_canonical_repo_missing",
          "Peer drift dharma_swarm track main...origin/main; dgc-core n/a",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
          "Topology dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
        ],
      },
      {
        title: "Git",
        rows: [
          "Branch main@95210b1",
          "Upstream origin/main | +0/-0",
          "Track tracking origin/main in sync",
          "Preview tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
          "Sync origin/main | ahead 0 | behind 0",
          "Risk topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes)",
          "Dirty 0 staged, 510 unstaged, 42 untracked",
          "Counts staged 0 | unstaged 510 | untracked 42",
        ],
      },
      {
        title: "Topology",
        rows: [
          "Status degraded (1 warning, 2 peers) | peers 2",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high",
          "Risk sab_canonical_repo_missing",
          "Signal high | dharma_swarm track main...origin/main",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead sab_canonical_repo_missing",
          "Drift dharma_swarm track main...origin/main; dgc-core n/a",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
        ],
      },
      {
        title: "Hotspots",
        rows: [
          "Changed terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
          "Summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
          "Paths terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
          "Lead path terminal/src/protocol.ts",
          "Files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
          "Lead file dgc_cli.py (6908 lines)",
          "Deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35",
          "Lead dep dharma_swarm.models | inbound 159",
        ],
      },
      {
        title: "Inventory",
        rows: [
          "Inventory 501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
          "Mix .py: 1125; .md: 511; .json: 91; .sh: 68",
        ],
      },
      {
        title: "Control",
        rows: [
          "Task terminal-repo-pane | 3 done, 1 pending of 4",
          "Outcome complete | accept pass",
          "Runtime summary /Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Runtime /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Runs 0 runs | 0 active runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Activity Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Health tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | alerts none",
          "Loop cycle 23 running | continue required",
          "Result complete / pass",
          "Verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Checks tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
          "Bundle tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Tools claude, python3, node | alerts none",
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
          "Next n/a",
          "Updated n/a",
        ],
      },
    ]);
  });

  test("falls back to transcript lines while repo preview is unavailable", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "# Repo Snapshot"},
      {id: "2", kind: "system", text: "Branch: main"},
      {id: "3", kind: "system", text: "Dirty: clean"},
    ];

    expect(buildRepoPaneSections(undefined, lines)).toEqual([
      {
        title: "Repo Snapshot",
        rows: ["# Repo Snapshot", "Branch: main", "Dirty: clean"],
      },
    ]);
  });

  test("fills missing repo and control fields from transcript lines", () => {
    const repoLines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Repo root: /Users/dhyana/dharma_swarm"},
      {id: "2", kind: "system", text: "Branch: main"},
      {id: "3", kind: "system", text: "Head: 95210b1"},
      {id: "4", kind: "system", text: "Upstream: origin/main"},
      {id: "5", kind: "system", text: "Ahead: 0"},
      {id: "6", kind: "system", text: "Behind: 0"},
      {id: "7", kind: "system", text: "Branch status: tracking origin/main in sync"},
      {id: "8", kind: "system", text: "Sync: origin/main | ahead 0 | behind 0"},
      {
        id: "8a",
        kind: "system",
        text: "Branch sync preview: tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      },
      {
        id: "8b",
        kind: "system",
        text: "Repo risk preview: tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      },
      {id: "9", kind: "system", text: "Repo risk: topology sab_canonical_repo_missing; high (552 local changes)"},
      {id: "10", kind: "system", text: "Dirty pressure: high (552 local changes)"},
      {id: "11", kind: "system", text: "Dirty: 0 staged, 510 unstaged, 42 untracked"},
      {id: "12", kind: "system", text: "Staged: 0"},
      {id: "13", kind: "system", text: "Unstaged: 510"},
      {id: "14", kind: "system", text: "Untracked: 42"},
      {id: "15", kind: "system", text: "Topology status: degraded (1 warning, 1 peer)"},
      {id: "16", kind: "system", text: "Topology peer count: 1"},
      {id: "17", kind: "system", text: "Topology warnings: 1 (sab_canonical_repo_missing)"},
      {id: "17a", kind: "system", text: "Topology warning severity: high"},
      {id: "18", kind: "system", text: "Topology risk: sab_canonical_repo_missing"},
      {id: "18a", kind: "system", text: "Primary warning: sab_canonical_repo_missing"},
      {id: "18aa", kind: "system", text: "Primary peer drift: dharma_swarm track main...origin/main"},
      {id: "18b", kind: "system", text: "Primary topology peer: dharma_swarm (canonical_core, main...origin/main, dirty True)"},
      {id: "18c", kind: "system", text: "Peer drift markers: dharma_swarm track main...origin/main"},
      {id: "19", kind: "system", text: "Topology peers: dharma_swarm (canonical_core, main...origin/main, dirty True)"},
      {id: "19a", kind: "system", text: "Topology pressure preview: 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)"},
      {id: "20", kind: "system", text: "Topology pressure: dharma_swarm Δ552 (510 modified, 42 untracked)"},
      {id: "21", kind: "system", text: "Changed hotspots: terminal (274); dharma_swarm (91)"},
      {id: "22", kind: "system", text: "Hotspot summary: change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts"},
      {id: "23", kind: "system", text: "Changed paths: terminal/src/protocol.ts; terminal/src/components/RepoPane.tsx"},
      {id: "23a", kind: "system", text: "Primary changed hotspot: terminal (274)"},
      {id: "23b", kind: "system", text: "Primary changed path: terminal/src/protocol.ts"},
      {id: "23c", kind: "system", text: "Primary file hotspot: dgc_cli.py (6908 lines)"},
      {id: "23d", kind: "system", text: "Primary dependency hotspot: dharma_swarm.models | inbound 159"},
      {id: "24", kind: "system", text: "Hotspots: dgc_cli.py (6908 lines)"},
      {id: "25", kind: "system", text: "Inbound hotspots: dharma_swarm.models | inbound 159"},
      {id: "26", kind: "system", text: "Inventory: 501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows"},
      {id: "27", kind: "system", text: "Language mix: .py: 1125; .md: 511"},
    ];
    const controlLines: TranscriptLine[] = [
      {id: "c1", kind: "system", text: "Active task: terminal-repo-pane"},
      {id: "c2", kind: "system", text: "Task progress: 3 done, 1 pending of 4"},
      {id: "c3", kind: "system", text: "Result status: complete"},
      {id: "c4", kind: "system", text: "Acceptance: pass"},
      {id: "c5", kind: "system", text: "Runtime DB: /Users/dhyana/.dharma/state/runtime.db"},
      {id: "c5a", kind: "system", text: "Session state: 18 sessions | 0 claims | 0 active claims | 0 acked claims"},
      {id: "c5b", kind: "system", text: "Run state: 0 runs | 0 active runs"},
      {id: "c5c", kind: "system", text: "Context state: 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions"},
      {id: "c6", kind: "system", text: "Runtime activity: Sessions=18  Runs=0"},
      {id: "c7", kind: "system", text: "Artifact state: Artifacts=7  ContextBundles=1"},
      {id: "c8", kind: "system", text: "Loop state: cycle 24 running"},
      {id: "c9", kind: "system", text: "Loop decision: continue required"},
      {id: "c10", kind: "system", text: "Verification summary: tsc=ok | cycle_acceptance=ok"},
      {id: "c10a", kind: "system", text: "Verification checks: tsc ok; cycle_acceptance ok"},
      {id: "c11", kind: "system", text: "Verification bundle: tsc=ok | cycle_acceptance=ok"},
      {id: "c12", kind: "system", text: "Toolchain: claude, python3, node"},
      {id: "c13", kind: "system", text: "Alerts: none"},
      {id: "c14", kind: "system", text: "Durable state: /tmp/state"},
    ];

    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
      },
      repoLines,
      {
        "Active task": "terminal-repo-pane",
      },
      controlLines,
      new Date("2026-04-01T04:00:00Z"),
    );

    expect(sections).toEqual([
      {
        title: "Operator Snapshot",
        rows: [
          "Git main@95210b1 | high (552 local changes) | sync tracking origin/main in sync",
          "Dirty staged 0 | unstaged 510 | untracked 42 | topo 1 (sab_canonical_repo_missing) | lead terminal (274)",
          "Snapshot branch main@95210b1 | tracking origin/main in sync",
          "Snapshot dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
          "Snapshot topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)",
          "Snapshot warnings sab_canonical_repo_missing | severity high",
          "Snapshot topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Snapshot hotspots change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
          "Snapshot hotspot summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Snapshot summary topology sab_canonical_repo_missing; high (552 local changes) | hotspots change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Snapshot focus Root /Users/dhyana/dharma_swarm | lead terminal/src/protocol.ts",
          "Snapshot pressure Topology pressure dharma_swarm Δ552 (510 modified, 42 untracked) | peers 1",
          "Snapshot topology pressure 1 (sab_canonical_repo_missing) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
          "Snapshot repo/control unknown | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
          "Task terminal-repo-pane | complete/pass | tsc=ok | cycle_acceptance=ok",
          "Control pulse unknown | n/a | n/a",
          "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass",
          "Control verify tsc=ok | cycle_acceptance=ok | next n/a",
          "Freshness unknown | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Snapshot",
        rows: [
          "Root /Users/dhyana/dharma_swarm",
          "Branch main@95210b1",
          "Track tracking origin/main in sync | upstream origin/main",
          "Branch preview tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
          "Sync origin/main | ahead 0 | behind 0 | +0/-0",
          "Health topology sab_canonical_repo_missing; high (552 local changes) | origin/main | ahead 0 | behind 0",
          "Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Snapshot task terminal-repo-pane | complete/pass | cycle 24 running | continue required",
          "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Snapshot freshness unknown | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
          "Snapshot truth tsc=ok | cycle_acceptance=ok | cycle 24 running | next n/a",
          "Dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
          "Hotspots change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Warnings sab_canonical_repo_missing | severity high",
          "Lead change terminal (274) | path terminal/src/protocol.ts",
          "Lead file dgc_cli.py (6908 lines)",
          "Lead dep dharma_swarm.models | inbound 159",
        ],
      },
      {
        title: "Repo Risk",
        rows: [
          "Repo topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes) | peers 1",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high | warning sab_canonical_repo_missing",
          "Peer drift dharma_swarm track main...origin/main",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Repo preview tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Risk sab_canonical_repo_missing",
          "State 0 staged, 510 unstaged, 42 untracked",
          "Topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)",
          "Topology signal high | dharma_swarm track main...origin/main",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead warning sab_canonical_repo_missing",
          "Peer drift dharma_swarm track main...origin/main",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology dharma_swarm Δ552 (510 modified, 42 untracked)",
        ],
      },
      {
        title: "Git",
        rows: [
          "Branch main@95210b1",
          "Upstream origin/main | +0/-0",
          "Track tracking origin/main in sync",
          "Preview tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
          "Sync origin/main | ahead 0 | behind 0",
          "Risk topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes)",
          "Dirty 0 staged, 510 unstaged, 42 untracked",
          "Counts staged 0 | unstaged 510 | untracked 42",
        ],
      },
      {
        title: "Topology",
        rows: [
          "Status degraded (1 warning, 1 peer) | peers 1",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high",
          "Risk sab_canonical_repo_missing",
          "Signal high | dharma_swarm track main...origin/main",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead sab_canonical_repo_missing",
          "Drift dharma_swarm track main...origin/main",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked)",
        ],
      },
      {
        title: "Hotspots",
        rows: [
          "Changed terminal (274); dharma_swarm (91)",
          "Summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
          "Paths terminal/src/protocol.ts; terminal/src/components/RepoPane.tsx",
          "Lead path terminal/src/protocol.ts",
          "Files dgc_cli.py (6908 lines)",
          "Lead file dgc_cli.py (6908 lines)",
          "Deps dharma_swarm.models | inbound 159",
          "Lead dep dharma_swarm.models | inbound 159",
        ],
      },
      {
        title: "Inventory",
        rows: [
          "Inventory 501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
          "Mix .py: 1125; .md: 511",
        ],
      },
      {
        title: "Control",
        rows: [
          "Task terminal-repo-pane | 3 done, 1 pending of 4",
          "Outcome complete | accept pass",
          "Runtime summary /Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Runtime /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Runs 0 runs | 0 active runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Activity Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Health tsc=ok | cycle_acceptance=ok | alerts none",
          "Loop cycle 24 running | continue required",
          "Result n/a",
          "Verify tsc=ok | cycle_acceptance=ok",
          "Checks tsc ok; cycle_acceptance ok",
          "Bundle tsc=ok | cycle_acceptance=ok",
          "Tools claude, python3, node | alerts none",
          "State /tmp/state",
          "Next n/a",
          "Updated n/a",
        ],
      },
    ]);
  });

  test("prefers live repo and control previews over stale tab previews", () => {
    const repoLines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Branch: stale"},
      {id: "2", kind: "system", text: "Repo risk: stale risk"},
    ];
    const controlLines: TranscriptLine[] = [
      {id: "c1", kind: "system", text: "Active task: stale-task"},
      {id: "c2", kind: "system", text: "Result status: stale"},
    ];

    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        Upstream: "origin/main",
        Ahead: "0",
        Behind: "0",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (563 local changes)",
        "Repo risk preview":
          "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Repo/control preview":
          "stale | task stale-task | stale repo/control preview that should not survive a live control refresh",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        Dirty: "0 staged, 517 unstaged, 46 untracked",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 1 peer)",
        "Topology peer count": "1",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Topology risk": "sab_canonical_repo_missing",
        "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology preview":
          "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Topology pressure preview": "1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Primary warning": "sab_canonical_repo_missing",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Changed hotspots": "terminal (274)",
        "Hotspot summary": "change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
        "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
        "Changed paths": "terminal/src/app.tsx; terminal/src/components/Sidebar.tsx",
        Hotspots: "dgc_cli.py (6908 lines)",
        "Inbound hotspots": "dharma_swarm.models | inbound 159",
        Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
        "Language mix": ".py: 1125; .md: 511",
      },
      repoLines,
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "3 done, 1 pending of 4",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Last result": "in_progress / fail",
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 2 running",
        "Loop decision": "continue required",
        "Verification summary": "tsc=ok | cycle_acceptance=fail",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Runtime freshness": "cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview":
          "in_progress / fail | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
        "Next task": "Wire control preview to the live runtime snapshot source.",
        Updated: "2026-04-01T03:44:29Z",
      },
      controlLines,
      new Date("2026-04-02T12:00:00Z"),
    );

    expect(sections[0]?.rows).toContain("Git main@95210b1 | high (563 local changes) | sync tracking origin/main in sync");
    expect(sections[0]?.rows).toContain(
      "Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead n/a",
    );
    expect(sections[0]?.rows).toContain("Snapshot focus Root /Users/dhyana/dharma_swarm | lead n/a");
    expect(sections[0]?.rows).toContain(
      "Snapshot pressure Topology pressure dharma_swarm Δ563 (517 modified, 46 untracked) | peers 1",
    );
    expect(sections[0]?.rows).toContain("Snapshot topology pressure 1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(sections[0]?.rows).toContain("Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159");
    expect(sections[0]?.rows).toContain(
      "Snapshot summary topology sab_canonical_repo_missing; high (563 local changes) | hotspots change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(sections[0]?.rows).toContain(
      "Freshness stale | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[0]?.rows).toContain("Task terminal-repo-pane | in_progress/fail | tsc=ok | cycle_acceptance=fail");
    expect(sections[0]?.rows).toContain(
      "Control pulse stale | in_progress / fail | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[0]?.rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(sections[0]?.rows).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
    expect(sections[0]?.rows).toContain(
      "Control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[1]?.rows).toContain("Snapshot task terminal-repo-pane | in_progress/fail | cycle 2 running | continue required");
    expect(sections[1]?.rows).toContain("Warnings sab_canonical_repo_missing | severity n/a");
    expect(sections[1]?.rows).toContain(
      "Hotspots change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot freshness stale | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot truth tsc=ok | cycle_acceptance=fail | cycle 2 running | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[2]?.rows).toContain("Repo topology sab_canonical_repo_missing; high (563 local changes)");
    expect(sections[2]?.rows).toContain("Severity n/a | warning sab_canonical_repo_missing");
    expect(sections[2]?.rows).toContain(
      "Repo preview tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(sections[7]?.rows).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(sections[7]?.rows).toContain("Outcome in_progress | accept fail");
    expect(sections[7]?.rows).toContain("Bundle tsc=ok | cycle_acceptance=fail");
    expect(sections[2]?.rows).not.toContain("Repo stale risk");
    expect(sections[7]?.rows).not.toContain("Task stale-task | n/a");
    expect(sections.flatMap((section) => section.rows).some((row) => row.includes("stale repo/control preview"))).toBe(
      false,
    );
  });
});
