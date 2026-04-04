import {describe, expect, test} from "bun:test";
import React from "react";

import {RepoPane, buildRepoPaneSections, sectionCardSummaries} from "../src/components/RepoPane";
import {workspacePayloadToPreview, workspacePreviewToLines, workspaceSnapshotToPreview} from "../src/protocol";
import type {TabPreview, TranscriptLine, WorkspaceSnapshotPayload} from "../src/types";

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
    const pane = RepoPane({title: "Repo", preview, lines, controlPreview: undefined, controlLines: [], windowSize: 64});
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain("Operator Snapshot");
    expect(visibleText).toContain("Git main@95210b1 | high (563 local changes) | sync tracking origin/main in sync");
    expect(visibleText).toContain("Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)");
    expect(visibleText).toContain("Snapshot branch main@95210b1 | tracking origin/main in sync");
    expect(visibleText).toContain("Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 | behind 0");
    expect(visibleText).toContain(
      "Snapshot branch sync tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (563 local changes)",
    );
    expect(visibleText).toContain("Snapshot dirty high (563 local changes) | staged 0 | unstaged 517 | untracked 46");
    expect(visibleText).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)");
    expect(visibleText).toContain(
      "Snapshot alert high | warning sab_canonical_repo_missing | drift dharma_swarm track main...origin/main",
    );
    expect(visibleText).toContain(
      "Snapshot topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked); dgc-core clean",
    );
    expect(visibleText).toContain(
      "Snapshot hotspots change terminal (281) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(visibleText).toContain("Snapshot summary topology sab_canonical_repo_missing; high (563 local changes)");
    expect(visibleText).toContain("hotspots change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)");
    expect(visibleText).toContain(
      "Snapshot truth branch main@95210b1 | dirty staged 0 | unstaged 517 | untracked 46 | warn sab_canonical_repo_missing | hotspot change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)",
    );
    expect(visibleText).toContain("Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing");
    expect(visibleText).toContain("Snapshot focus Root /Users/dhyana/dharma_swarm | lead terminal/src/app.tsx");
    expect(visibleText).toContain(
      "Snapshot topology pulse Topology pressure dharma_swarm Δ563 (517 modified, 46 untracked); dgc-core clean | peers 2",
    );
    expect(visibleText).toContain("Snapshot topology pressure 1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(visibleText).toContain("Snapshot hotspot pressure change terminal (281) | dep dharma_swarm.models | inbound 159");
    expect(visibleText).toContain("Git main@95210b1");
    expect(visibleText).toContain("Snapshot warnings sab_canonical_repo_missing | severity high");
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

  test("prefers an explicit repo truth preview over recomputing snapshot truth rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Repo truth preview": "branch main@804d5d1 | dirty compact | warn sab_canonical_repo_missing | hotspot terminal focus",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 2 | behind 0",
        "Dirty pressure": "high (552 local changes)",
        Staged: "1",
        Unstaged: "2",
        Untracked: "3",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (4) | paths terminal/src/components/RepoPane.tsx",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot truth branch main@804d5d1 | dirty compact | warn sab_canonical_repo_missing | hotspot terminal focus",
    );
  });

  test("prefers explicit branch divergence and detached peer fields when present", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology peer_branch_diverged; elevated (7 local changes)",
        "Dirty pressure": "contained (7 local changes)",
        "Topology warnings": "1 (peer_branch_diverged)",
        "Primary warning": "peer_branch_diverged",
        "Primary peer drift": "dharma_swarm track main...origin/main",
        "Branch divergence": "local +2/-0 | peer canonical_core drift explicit",
        "Detached peers": "dgc-core detached",
        "Hotspot summary": "change terminal (4)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch divergence local +2/-0 | peer canonical_core drift explicit");
    expect(sections[0]?.rows).toContain("Snapshot detached peers dgc-core detached");
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-0 | peer canonical_core drift explicit");
    expect(sections[2]?.rows).toContain("Detached peers dgc-core detached");
  });

  test("derives dirty counts from compact repo truth previews when expanded git count rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Dirty staged 97 | unstaged 505 | untracked 54 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)",
    );
    expect(sections[1]?.rows).toContain("Dirty high (656 local changes) | staged 97 | unstaged 505 | untracked 54");
    expect(sections[3]?.rows).toContain("Counts staged 97 | unstaged 505 | untracked 54");
  });

  test("derives topology warnings and hotspot rows from compact repo truth previews when expanded rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Dirty staged 97 | unstaged 505 | untracked 54 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)",
    );
    expect(sections[0]?.rows).toContain("Snapshot topology degraded (1 warning) | warnings 1 (sab_canonical_repo_missing)");
    expect(sections[0]?.rows).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(sections[0]?.rows).toContain("Snapshot warnings sab_canonical_repo_missing | severity high");
    expect(sections[0]?.rows).toContain(
      "Snapshot hotspots change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot hotspot summary change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[1]?.rows).toContain(
      "Hotspots change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[2]?.rows).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(sections[2]?.rows).toContain("Risk sab_canonical_repo_missing");
    expect(sections[4]?.rows).toContain("Status degraded (1 warning) | peers n/a");
    expect(sections[5]?.rows).toContain(
      "Summary change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[5]?.rows).toContain("Lead dep dharma_swarm.models | inbound 159");
  });

  test("counts semicolon-delimited topology warnings from compact repo truth previews", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Branch status": "tracking origin/main [ahead 2, behind 1]",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 112 | unstaged 545 | untracked 112 | warn peer_branch_diverged; sab_canonical_repo_missing | hotspot change terminal (281)",
      },
      [],
    );
    const allRows = sections.flatMap((section) => section.rows);

    expect(sections[1]?.rows).toContain("Snapshot topology degraded (2 warnings) | warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)");
    expect(sections[1]?.rows).toContain("Snapshot warning members peer_branch_diverged, sab_canonical_repo_missing");
    expect(sections[2]?.rows).toContain("Warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)");
    expect(allRows).toContain("Members peer_branch_diverged, sab_canonical_repo_missing");
  });

  test("synthesizes topology counts and runtime summary from compact repo/control previews", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "fresh | task terminal-repo-pane | branch feature/repo-pane@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | dirty staged 112 | unstaged 545 | untracked 112 | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=2 ActiveRuns=1 | artifacts Artifacts=7 ContextBundles=1 | verify tsc=ok",
      },
      [],
    );

    expect(sections[3]?.rows).toContain("Counts staged 112 | unstaged 545 | untracked 112");
    expect(sections[4]?.rows).toContain(
      "Count 2 peers | warnings 2 (peer_branch_diverged; sab_canonical_repo_missing)",
    );
    expect(sections[7]?.rows).toContain(
      "Runtime summary /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=2 ActiveRuns=1 | Artifacts=7 ContextBundles=1",
    );
  });

  test("keeps multi-warning members in operator snapshot rows when only repo/control preview is persisted", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "fresh | task terminal-repo-pane | branch main@804d5d1 | diverged from origin/main (+2/-1) | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main [ahead 2, behind 1], dirty true); dgc-core (operator_shell, detached, dirty true) | drift dharma_swarm drift main...origin/main [ahead 2, behind 1] | detached dgc-core detached | dirty staged 112 | unstaged 557 | untracked 136 | hotspot change terminal (77) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 161 | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=20 Runs=0 | artifacts Artifacts=0 ContextBundles=0 | verify tsc=ok",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Dirty staged 112 | unstaged 557 | untracked 136 | topo 2 (peer_branch_diverged, sab_canonical_repo_missing) | lead terminal (77)",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot topology degraded (2 warnings, 2 peers) | warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)",
    );
    expect(sections[1]?.rows).toContain("Snapshot warning members peer_branch_diverged, sab_canonical_repo_missing");
    expect(sections[2]?.rows).toContain("Warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)");
    expect(sections[2]?.rows).toContain("Warning members peer_branch_diverged, sab_canonical_repo_missing");
  });

  test("derives branch and head labels from compact repo truth previews when explicit git rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | tracking origin/main ahead 2");
    expect(sections[0]?.rows).toContain(
      "Snapshot truth branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
    );
    expect(sections[3]?.rows).toContain("Branch main@804d5d1");
  });

  test("derives branch sync details from compact branch sync previews when expanded git sync rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch sync preview": "tracking origin/main ahead 2 | +2/-0 | topology sab_canonical_repo_missing; high (656 local changes)",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | tracking origin/main ahead 2");
    expect(sections[0]?.rows).toContain(
      "Snapshot branch sync tracking origin/main ahead 2 | +2/-0 | topology sab_canonical_repo_missing; high (656 local changes)",
    );
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-0");
    expect(sections[3]?.rows).toContain("Upstream origin/main | +2/-0");
    expect(sections[3]?.rows).toContain("Track tracking origin/main ahead 2");
  });

  test("derives branch sync counts from git-status branch sync previews without a +N/-M token", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch sync preview": "main...origin/main [ahead 2]",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | main...origin/main [ahead 2]");
    expect(sections[0]?.rows).toContain(
      "Snapshot sync origin/main | +2/-0 | origin/main | ahead 2 | behind 0",
    );
    expect(sections[3]?.rows).toContain("Upstream origin/main | +2/-0");
    expect(sections[3]?.rows).toContain("Track main...origin/main [ahead 2]");
  });

  test("prefers an explicit control truth preview over recomputing control snapshot truth rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Loop state": "cycle 2 running",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Next task": "stale fallback next task",
        "Control truth preview": "verify compact | cycle 2 running | next hydrate control truth from disk",
      },
      [],
    );

    expect(sections.flatMap((section) => section.rows)).toContain(
      "Snapshot truth verify compact | cycle 2 running | next hydrate control truth from disk",
    );
  });

  test("derives repo control snapshot rows from compact control freshness when expanded verification fields are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
      },
      [],
      {
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime activity": "Sessions=5 Runs=2 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
        "Artifact state": "Artifacts=8 PromotedFacts=3 ContextBundles=2 OperatorActions=4",
        "Control pulse preview":
          "fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        "Runtime freshness":
          "cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain(
      "Control pulse fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(rows).toContain(
      "Control verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | next n/a",
    );
    expect(rows).toContain(
      "Snapshot truth tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | cycle 13 waiting_for_verification | next n/a",
    );
    expect(
      rows.some(
        (row) =>
          row.startsWith("Snapshot freshness ") &&
          row.includes("cycle 13 waiting_for_verification") &&
          row.includes("updated 2026-04-03T02:00:00Z") &&
          row.includes("verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail"),
      ),
    ).toBe(true);
  });

  test("derives compact runtime activity labels from partial live control state rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
      {
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
        "Run state": "0 runs | 0 active runs",
        "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Loop state": "cycle 14 running",
        "Loop decision": "continue required",
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Runtime freshness": "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview": "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain(
      "Snapshot control preview stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain("Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions");
    expect(rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain("Activity Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1");
  });

  test("enriches compact repo/control snapshot truth rows with repo facts", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "abc123",
        "Repo/control preview":
          "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | next hydrate control preview from runtime state",
      },
      [],
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      [],
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain(
      "Snapshot truth branch main@abc123 | tracking origin/main in sync | warn sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | tsc=ok | cycle_acceptance=fail | cycle 13 ready | next hydrate control preview from runtime state",
    );
  });

  test("derives compact runtime activity labels from runtime summary when detailed control rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
      {
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime summary":
          "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Loop state": "cycle 14 running",
        "Loop decision": "continue required",
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Runtime freshness": "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview": "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain(
      "Snapshot control preview stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(rows).toContain("Activity Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1");
  });

  test("derives control outcome from compact pulse previews when explicit outcome rows are absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
      {
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 14 running",
        "Loop decision": "continue required",
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Runtime freshness": "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview": "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain("Task terminal-repo-pane | in_progress/fail | tsc=ok | cycle_acceptance=fail");
    expect(rows).toContain("Control task terminal-repo-pane | 1 done, 0 pending of 1 | in_progress/fail");
    expect(rows).toContain("Snapshot task terminal-repo-pane | in_progress/fail | cycle 14 running | continue required");
  });

  test("preserves stored repo/control preview when the live control preview is only a placeholder", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
        "Repo risk preview":
          "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Dirty pressure": "high (552 local changes)",
        Staged: "0",
        Unstaged: "510",
        Untracked: "42",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | next hydrate control preview from runtime state",
      },
      [],
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      [],
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | next hydrate control preview from runtime state",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | next hydrate control preview from runtime state",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot control preview stale | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok",
    );
    expect(sections[0]?.rows).toContain("Control pulse stale | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok");
    expect(sections[0]?.rows).toContain("Control task terminal-repo-pane");
    expect(sections[0]?.rows).toContain("Control verify tsc=ok | next hydrate control preview from runtime state");
    expect(sections[1]?.rows).toContain(
      "Snapshot control preview stale | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot repo/control verify tsc=ok | next hydrate control preview from runtime state",
    );
    expect(sections[0]?.rows.some((row) => row.startsWith("Snapshot runtime "))).toBe(false);
    expect(sections[1]?.rows.some((row) => row.startsWith("Snapshot task "))).toBe(false);
    expect(sections[1]?.rows.some((row) => row.startsWith("Snapshot freshness "))).toBe(false);
    expect(sections[7]?.title).toBe("Control");
    expect(sections[7]?.rows).toContain("Task terminal-repo-pane");
    expect(sections[7]?.rows).toContain("Loop cycle 13 ready");
    expect(sections[7]?.rows).toContain("Health tsc=ok");
    expect(sections[7]?.rows).toContain("Verify tsc=ok");
    expect(sections[7]?.rows).toContain("Next hydrate control preview from runtime state");
    expect(sections[7]?.rows).toContain("Updated 2026-04-03T01:15:00Z");
  });

  test("reconstructs snapshot task rows from compact repo/control previews during placeholder-only control intervals", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
        "Dirty pressure": "high (552 local changes)",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | next hydrate control preview from runtime state",
      },
      [],
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      [],
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot task terminal-repo-pane | in_progress/fail | cycle 13 ready | continue required",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot truth branch main@95210b1 | tracking origin/main in sync | warn sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | tsc=ok | cycle_acceptance=fail | cycle 13 ready | next hydrate control preview from runtime state",
    );
    expect(sections[0]?.rows).toContain(
      "Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot task terminal-repo-pane | in_progress/fail | cycle 13 ready | continue required",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot truth branch main@95210b1 | tracking origin/main in sync | warn sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | tsc=ok | cycle_acceptance=fail | cycle 13 ready | next hydrate control preview from runtime state",
    );
  });

  test("promotes live snapshot rows to the top of the snapshot section before structural detail rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Repo risk preview":
          "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Dirty pressure": "high (656 local changes)",
        Staged: "97",
        Unstaged: "505",
        Untracked: "54",
        "Topology status": "degraded (1 warning, 1 peer)",
        "Topology peer count": "1",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Topology warning severity": "high",
        "Topology risk": "sab_canonical_repo_missing",
        "Primary warning": "sab_canonical_repo_missing",
        "Primary peer drift": "dharma_swarm track main...origin/main",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology pressure": "dharma_swarm Δ656 (505 modified, 54 untracked)",
        "Changed hotspots": "terminal (281); dharma_swarm (91)",
        "Hotspot summary":
          "change terminal (281); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary file hotspot": "dgc_cli.py (6908 lines)",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "3 done, 1 pending of 4",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Loop state": "cycle 19 running",
        "Loop decision": "continue required",
        Updated: "2026-04-03T02:16:08Z",
        "Verification bundle": "tsc=ok | cycle_acceptance=ok",
        "Runtime freshness": "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
        "Control pulse preview": "in_progress / fail | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const snapshotRows = sections[1]?.rows ?? [];
    expect(snapshotRows.slice(0, 6)).toEqual([
      "Snapshot branch main@804d5d1 | tracking origin/main ahead 2",
      "Snapshot sync origin/main | +2/-0 | origin/main | ahead 2 | behind 0",
      "Snapshot branch sync tracking origin/main ahead 2 | +2/-0 | topology sab_canonical_repo_missing; high (656 local changes)",
      "Snapshot dirty high (656 local changes) | staged 97 | unstaged 505 | untracked 54",
      "Snapshot topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)",
      "Snapshot warning members sab_canonical_repo_missing",
    ]);
    expect(snapshotRows.indexOf("Root /Users/dhyana/dharma_swarm")).toBeGreaterThan(
      snapshotRows.indexOf(
        "Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
      ),
    );
  });

  test("uses fallback-aware repo/control summaries in section cards during placeholder-only control intervals", () => {
    const pane = RepoPane({
      title: "Repo",
      preview: {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
        "Repo risk preview":
          "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Dirty pressure": "high (552 local changes)",
        Staged: "0",
        Unstaged: "510",
        Untracked: "42",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok",
      },
      lines: [],
      controlPreview: {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      controlLines: [],
      selectedSectionIndex: 1,
    });
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok",
    );
    expect(visibleText).not.toContain("  Root /Users/dhyana/dharma_swarm");
  });

  test("surfaces runtime rows from stored repo/control previews during placeholder-only control intervals", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
        "Dirty pressure": "high (552 local changes)",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (552 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | artifacts Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3 | next hydrate control preview from runtime state",
      },
      [],
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      [],
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[0]?.rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[0]?.rows).toContain(
      "Runtime summary /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[7]?.title).toBe("Control");
    expect(sections[7]?.rows).toContain(
      "Runtime summary /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[7]?.rows).toContain("Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions");
    expect(sections[7]?.rows).toContain(
      "Activity Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3",
    );
    expect(sections[7]?.rows).toContain("Verify tsc=ok");
  });

  test("prefers live runtime inventory over stale repo/control runtime counts during partial control refreshes", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | hotspot terminal (281) | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | db /old/runtime.db | activity Sessions=18 Runs=0 | artifacts Artifacts=7 ContextBundles=1 | next refresh live runtime state",
      },
      [],
      {
        "Session state": "21 sessions | 5 claims | 2 active claims | 1 acked claims",
        "Run state": "3 runs | 1 active runs",
        "Context state": "9 artifacts | 4 context bundles | 6 operator actions",
      },
      [],
    );

    const rows = sections.flatMap((section) => section.rows);
    expect(rows).toContain("Snapshot runtime Sessions=21  Runs=3 | Artifacts=9  ContextBundles=4");
    expect(rows).toContain("Runtime summary Sessions=21  Runs=3 | Artifacts=9  ContextBundles=4");
    expect(rows).toContain("Activity Sessions=21  Runs=3 | Artifacts=9  ContextBundles=4");
    expect(rows).toContain("Control verify tsc=ok | next refresh live runtime state");
    expect(rows).not.toContain("Snapshot runtime /old/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1");
  });

  test("uses fallback-aware summaries for repo risk and hotspots section cards", () => {
    const pane = RepoPane({
      title: "Repo",
      preview: {
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
        "Dirty pressure": "high (552 local changes)",
        Staged: "0",
        Unstaged: "510",
        Untracked: "42",
        "Topology status": "degraded (1 warning, 1 peer)",
        "Topology peer count": "1",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Topology warning severity": "high",
        "Topology risk": "sab_canonical_repo_missing",
        "Primary warning": "sab_canonical_repo_missing",
        "Primary peer drift": "dharma_swarm track main...origin/main",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked)",
        "Changed hotspots": "terminal (274); dharma_swarm (91)",
        "Hotspot summary":
          "change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
        "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
        "Changed paths": "terminal/src/protocol.ts; terminal/src/components/RepoPane.tsx",
        "Primary changed hotspot": "terminal (274)",
        "Primary changed path": "terminal/src/protocol.ts",
        Hotspots: "dgc_cli.py (6908 lines)",
        "Primary file hotspot": "dgc_cli.py (6908 lines)",
        "Inbound hotspots": "dharma_swarm.models | inbound 159",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      lines: [],
      selectedSectionIndex: 2,
    });
    const visibleText = flattenElementText(pane).join("\n");
    const sidebarText = visibleText.split("selected repo card")[0] ?? visibleText;

    expect(sidebarText).toContain("Repo topology sab_canonical_repo_missing; high (552 local changes)");
    expect(sidebarText).toContain("Topology signal high | dharma_swarm track main...origin/main");
    expect(sidebarText).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(sidebarText).toContain(
      "Summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    );
    expect(sidebarText).not.toContain("Changed terminal (274); dharma_swarm (91)");
  });

  test("surfaces branch, dirty, hotspot, and control facts in section rail summaries", () => {
    const pane = RepoPane({
      title: "Repo",
      preview: {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        Upstream: "origin/main",
        Ahead: "2",
        Behind: "0",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Repo risk preview":
          "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        Dirty: "97 staged, 505 unstaged, 54 untracked",
        "Dirty pressure": "high (656 local changes)",
        Staged: "97",
        Unstaged: "505",
        Untracked: "54",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Topology warning severity": "high",
        "Primary warning": "sab_canonical_repo_missing",
        "Primary peer drift": "dharma_swarm track main...origin/main",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
        "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked); dgc-core clean",
        "Changed hotspots": "terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)",
        "Hotspot summary":
          "change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary file hotspot": "dgc_cli.py (6908 lines)",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        "Repo/control preview":
          "fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main ahead 2 | sab_canonical_repo_missing | lead terminal (281) | cycle 1 running | updated 2026-04-03T00:30:00Z | verify tsc=ok",
      },
      lines: [],
      controlPreview: {
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
        "Run state": "0 runs | 0 active runs",
        "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 1 running",
        "Loop decision": "continue required",
        Updated: "2026-04-03T00:30:00Z",
        "Next task": "Polish visible context rows for repo risk pressure.",
        "Last result": "in_progress / fail",
        "Verification summary": "tsc=ok",
        "Verification checks": "tsc ok",
        "Verification bundle": "tsc=ok",
        "Runtime freshness": "cycle 1 running | updated 2026-04-03T00:30:00Z | verify tsc=ok",
        "Control pulse preview": "in_progress / fail | cycle 1 running | updated 2026-04-03T00:30:00Z | verify tsc=ok",
        "Runtime summary":
          "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260403T003000Z/state",
        Toolchain: "claude, python3, node",
        Alerts: "none",
      },
      controlLines: [],
      selectedSectionIndex: 3,
    });
    const visibleText = flattenElementText(pane).join("\n");
    const sidebarText = visibleText.split("selected repo card")[0] ?? visibleText;

    expect(sidebarText).toContain("Snapshot branch main@95210b1 | tracking origin/main ahead 2");
    expect(sidebarText).toContain("Snapshot dirty high (656 local changes) | staged 97 | unstaged 505 | untracked 54");
    expect(sidebarText).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)");
    expect(sidebarText).toContain(
      "Snapshot hotspot summary change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
    );
    expect(sidebarText).toContain(
      "Snapshot branch divergence local +2/-0 | peer dharma_swarm track main...origin/main",
    );
    expect(sidebarText).toContain(
      "Snapshot topology pressure 1 (sab_canonical_repo_missing) | dharma_swarm Δ559 (505 modified, 54 untracked)",
    );
    expect(sidebarText).toContain(
      "Snapshot repo risk tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(sidebarText).toContain("Task terminal-repo-pane | 1 done, 0 pending of 1");
    expect(sidebarText).toContain("Outcome in_progress | accept fail");
    expect(sidebarText).toContain("Health tsc=ok | alerts none");
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

    expect(sections.map((section) => section.title)).toEqual([
      "Operator Snapshot",
      "Snapshot",
      "Repo Risk",
      "Git",
      "Topology",
      "Hotspots",
      "Inventory",
      "Control",
    ]);
    expect(sections[0]?.rows).toContain("Git main@95210b1 | high (552 local changes) | sync tracking origin/main in sync");
    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(sections[1]?.rows.slice(0, 4)).toEqual([
      "Snapshot branch main@95210b1 | tracking origin/main in sync",
      "Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 | behind 0",
      "Snapshot branch sync tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Snapshot dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
    ]);
    expect(sections[1]?.rows).toContain("Root /Users/dhyana/dharma_swarm");
    expect(sections[1]?.rows).toContain(
      "Snapshot truth tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 23 running | next n/a",
    );
    expect(sections[7]?.rows).toContain("Outcome complete | accept pass");
    expect(sections[7]?.rows).toContain("State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state");

    /* legacy full-structure expectation retained below for non-snapshot sections */
    expect(sections.slice(2)).toEqual([
      {
        title: "Repo Risk",
        rows: [
          "Repo topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes) | peers 2",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high | warning sab_canonical_repo_missing",
          "Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main",
          "Detached peers none",
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
          "Control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next n/a",
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
          "Count 2 peers | warnings 1 (sab_canonical_repo_missing)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean | peers 2",
          "Pressure preview 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Members sab_canonical_repo_missing",
          "Severity high",
          "Risk sab_canonical_repo_missing",
          "Signal high | dharma_swarm track main...origin/main",
          "Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main",
          "Detached peers none",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead sab_canonical_repo_missing",
          "Drift dharma_swarm track main...origin/main; dgc-core n/a",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
          "Hotspot summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
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
          "Control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 23 running | updated n/a | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next n/a",
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
          "Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions",
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

    expect(sections.map((section) => section.title)).toEqual([
      "Operator Snapshot",
      "Snapshot",
      "Repo Risk",
      "Git",
      "Topology",
      "Hotspots",
      "Inventory",
      "Control",
    ]);
    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
    );
    expect(sections[1]?.rows.slice(0, 5)).toEqual([
      "Snapshot branch main@95210b1 | tracking origin/main in sync",
      "Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 | behind 0",
      "Snapshot branch sync tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Snapshot dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
      "Snapshot topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)",
    ]);
    expect(sections[1]?.rows).toContain("Lead dep dharma_swarm.models | inbound 159");
    expect(sections.slice(2)).toEqual([
      {
        title: "Repo Risk",
        rows: [
          "Repo topology sab_canonical_repo_missing; high (552 local changes)",
          "Pressure high (552 local changes) | peers 1",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Severity high | warning sab_canonical_repo_missing",
          "Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main",
          "Detached peers none",
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
          "Control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
          "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Verify tsc=ok | cycle_acceptance=ok | next n/a",
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
          "Count 1 peer | warnings 1 (sab_canonical_repo_missing)",
          "Pressure dharma_swarm Δ552 (510 modified, 42 untracked) | peers 1",
          "Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Warnings 1 (sab_canonical_repo_missing)",
          "Members sab_canonical_repo_missing",
          "Severity high",
          "Risk sab_canonical_repo_missing",
          "Signal high | dharma_swarm track main...origin/main",
          "Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main",
          "Detached peers none",
          "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Lead sab_canonical_repo_missing",
          "Drift dharma_swarm track main...origin/main",
          "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peers dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Hotspot summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159",
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
          "Control unknown | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 510 | untracked 42 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts | cycle 24 running | updated n/a | verify tsc=ok | cycle_acceptance=ok",
          "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
          "Verify tsc=ok | cycle_acceptance=ok | next n/a",
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
          "Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions",
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

  test("derives hotspot summary fallback in repo sections from partial live hotspot fields", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Topology risk": "sab_canonical_repo_missing",
        "Topology preview":
          "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Changed hotspots": "terminal (274)",
        "Primary changed hotspot": "terminal (274)",
        "Primary changed path": "terminal/src/components/Sidebar.tsx",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot hotspot summary change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot summary topology sab_canonical_repo_missing; high (563 local changes) | hotspots change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[1]?.rows).toContain(
      "Hotspots change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot hotspot summary change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[5]?.rows).toContain(
      "Summary change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
  });

  test("normalizes compact hotspot labels before repo summary rows add change prefixes", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Dirty pressure": "high (7 local changes)",
        "Repo risk": "topology peer_branch_diverged; high (7 local changes)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 1 | unstaged 4 | untracked 2 | hotspot change terminal (4) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 20 running | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Snapshot hotspot summary change terminal (4) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[0]?.rows).not.toContain(
      "Snapshot hotspot summary change change terminal (4) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
  });

  test("surfaces detached peer anomalies separately from branch divergence", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        Upstream: "origin/main",
        Ahead: "2",
        Behind: "1",
        "Branch status": "tracking origin/main diverged",
        Sync: "origin/main | ahead 2 | behind 1",
        "Repo risk": "topology peer_branch_diverged; high (6 local changes)",
        "Dirty pressure": "contained (6 local changes)",
        Staged: "1",
        Unstaged: "2",
        Untracked: "3",
        "Topology status": "degraded (2 warnings, 2 peers)",
        "Topology warnings": "2 (peer_branch_diverged, detached_peer)",
        "Topology warning severity": "high",
        "Topology risk": "peer_branch_diverged",
        "Primary warning": "peer_branch_diverged",
        "Primary peer drift": "dharma_swarm drift main...origin/main",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True)",
        "Topology pressure": "dharma_swarm Δ6 (2 modified, 3 untracked); dgc-core Δ1 (1 modified, 0 untracked)",
        "Changed hotspots": "terminal (4)",
        "Primary changed hotspot": "terminal (4)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch divergence local +2/-1 | peer dharma_swarm drift main...origin/main");
    expect(sections[0]?.rows).toContain("Snapshot detached peers dgc-core detached");
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-1 | peer dharma_swarm drift main...origin/main");
    expect(sections[2]?.rows).toContain("Detached peers dgc-core detached");
    expect(sections[4]?.rows).toContain("Branch divergence local +2/-1 | peer dharma_swarm drift main...origin/main");
    expect(sections[4]?.rows).toContain("Drift dharma_swarm drift main...origin/main; dgc-core n/a");
    expect(sections[4]?.rows).toContain("Detached peers dgc-core detached");
  });

  test("surfaces the warning-bearing peer in repo sections when workspace snapshot topology warnings point away from the first peer", () => {
    const preview = workspaceSnapshotToPreview(`# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 1 | unstaged 2 | untracked 3
Git hotspots: terminal (4)
Git changed paths: terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 2 | behind 1

## Topology
- warning: peer_branch_diverged
- warning: detached_peer
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 3 | untracked 2
- dgc-core | role operator_shell | branch detached | dirty True | modified 1 | untracked 0`);
    const sections = buildRepoPaneSections(preview, workspacePreviewToLines(preview));

    expect(sections[0]?.rows).toContain(
      "Snapshot topology preview peer_branch_diverged | dgc-core (operator_shell, detached, dirty True) | dharma_swarm Δ5 (3 modified, 2 untracked); dgc-core Δ1 (1 modified, 0 untracked)",
    );
    expect(sections[0]?.rows).toContain("Snapshot detached peers dgc-core detached");
    expect(sections[2]?.rows).toContain("Lead peer dgc-core (operator_shell, detached, dirty True)");
    expect(sections[2]?.rows).toContain("Peer drift dgc-core detached");
  });

  test("surfaces detached warning-bearing peer facts in section rail summaries", () => {
    const preview = workspaceSnapshotToPreview(`# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 1 | unstaged 2 | untracked 3
Git hotspots: terminal (4)
Git changed paths: terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 2 | behind 1

## Topology
- warning: peer_branch_diverged
- warning: detached_peer
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 3 | untracked 2
- dgc-core | role operator_shell | branch detached | dirty True | modified 1 | untracked 0`);
    const lines = workspacePreviewToLines(preview);
    const pane = RepoPane({title: "Repo", preview, lines, selectedSectionIndex: 0, windowSize: 48});
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain("Topology signal high | dgc-core detached");
    expect(visibleText).toContain("Lead peer dgc-core (operator_shell, detached, dirty True)");
    expect(visibleText).toContain("Signal high | dgc-core detached");
  });

  test("promotes detached divergence and topology pressure into snapshot rail summaries", () => {
    const preview = workspaceSnapshotToPreview(`# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 1 | unstaged 2 | untracked 3
Git hotspots: terminal (4)
Git changed paths: terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 2 | behind 1

## Topology
- warning: peer_branch_diverged
- warning: detached_peer
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 3 | untracked 2
- dgc-core | role operator_shell | branch detached | dirty True | modified 1 | untracked 0`);
    const lines = workspacePreviewToLines(preview);
    const pane = RepoPane({title: "Repo", preview, lines, selectedSectionIndex: 6, windowSize: 48});
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain("Snapshot topology pressure 2 warnings | dharma_swarm Δ5 (3 modified, 2 untracked)");
    expect(visibleText).toContain(
      "Snapshot repo risk diverged from origin/main (+2/-1) | peer_branch_diverged | dgc-core (operator_shell, detached, dirty True)",
    );
    expect(visibleText).toContain("Branch divergence local +2/-1 | peer dgc-core detached");
    expect(visibleText).toContain("Detached peers dgc-core detached");
  });

  test("promotes dirty and hotspot signal into snapshot rail summaries when topology is stable", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        Upstream: "origin/main",
        Ahead: "2",
        Behind: "0",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        "Repo risk": "tracking origin/main ahead 2; high (656 local changes)",
        "Repo risk preview": "tracking origin/main ahead 2",
        Dirty: "97 staged, 505 unstaged, 54 untracked",
        "Dirty pressure": "high (656 local changes)",
        Staged: "97",
        Unstaged: "505",
        Untracked: "54",
        "Topology status": "stable (0 warnings, 1 peer)",
        "Topology peer count": "1",
        "Topology warnings": "0",
        "Topology warning members": "none",
        "Topology warning severity": "none",
        "Primary warning": "none",
        "Primary peer drift": "none",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked)",
        "Changed hotspots": "terminal (281); dharma_swarm (93)",
        "Hotspot summary":
          "change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary file hotspot": "dgc_cli.py (6908 lines)",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Result status": "complete",
        Acceptance: "pass",
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 19 running",
        "Loop decision": "continue required",
        Updated: "2026-04-03T02:16:08Z",
        "Next task": "Keep stable snapshot card signal-dense.",
        "Verification bundle": "tsc=ok | cycle_acceptance=ok",
        "Runtime freshness": "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
        "Control pulse preview": "complete / pass | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );
    const snapshotSummary = sectionCardSummaries(sections[1]!);

    expect(snapshotSummary).toContain("Dirty high (656 local changes) | staged 97 | unstaged 505 | untracked 54");
    expect(snapshotSummary).toContain(
      "Snapshot hotspot summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
    );
    expect(snapshotSummary).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
    );
    expect(snapshotSummary).not.toContain("Warnings none | severity none");
  });

  test("derives topology warning and peer rows from repo risk preview when topology preview is absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        Upstream: "origin/main",
        Ahead: "2",
        Behind: "0",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Repo risk preview":
          "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Dirty pressure": "high (656 local changes)",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)");
    expect(sections[0]?.rows).toContain("Snapshot warnings sab_canonical_repo_missing | severity high");
    expect(sections[2]?.rows).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(sections[2]?.rows).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(sections[4]?.rows).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(sections[4]?.rows).toContain("Drift dharma_swarm track main...origin/main");
  });

  test("derives branch divergence and detached peer rows from compact repo/control preview alone", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
        "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | warn peer_branch_diverged | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | peer dharma_swarm drift main...origin/main | detached dgc-core detached | hotspot change terminal (281) | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch divergence local +2/-1");
    expect(sections[0]?.rows).toContain("Snapshot warnings peer_branch_diverged | severity high");
    expect(sections[0]?.rows).toContain("Snapshot detached peers dgc-core detached");
    expect(sections[0]?.rows).toContain(
      "Snapshot truth branch main@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | detached dgc-core detached | dirty high (656 local changes) | hotspot change terminal (281) | tsc=ok | cycle_acceptance=fail | cycle 8 running | next n/a",
    );
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-1");
    expect(sections[2]?.rows).toContain("Warnings 1 (peer_branch_diverged)");
    expect(sections[2]?.rows).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(sections[2]?.rows).toContain("Detached peers dgc-core detached");
    expect(sections[4]?.rows).toContain(
      "Peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True)",
    );
    expect(sections[4]?.rows).toContain("Branch divergence local +2/-1");
    expect(sections[4]?.rows).toContain("Signal high | dharma_swarm drift main...origin/main");
    expect(sections[4]?.rows).toContain("Drift dharma_swarm drift main...origin/main; dgc-core n/a");
    expect(sections[4]?.rows).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(sections[4]?.rows).toContain("Detached peers dgc-core detached");
  });

  test("derives branch and head rows from compact repo/control preview alone", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | hotspot change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | tracking origin/main ahead 2");
    expect(sections[3]?.rows).toContain("Branch main@804d5d1");
    expect(sections[3]?.rows).toContain("Track tracking origin/main ahead 2");
    expect(sections[3]?.rows).toContain("Upstream origin/main | +2/-0");
  });

  test("derives ahead and behind counts from human branch-status phrasing inside compact repo/control previews", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | ahead of origin/main by 2 | dirty high (7 local changes) | hotspot change terminal (4)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | ahead of origin/main by 2");
    expect(sections[0]?.rows).toContain("Snapshot sync origin/main | +2/-0 | origin/main | ahead 2 | behind 0");
    expect(sections[1]?.rows).toContain("Snapshot repo risk high (7 local changes)");
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-0");
    expect(sections[2]?.rows).toContain("Repo preview high (7 local changes)");
    expect(sections[3]?.rows).toContain("Track ahead of origin/main by 2");
    expect(sections[3]?.rows).toContain("Upstream origin/main | +2/-0");
  });

  test("derives ahead and behind counts from git bracket branch-status phrasing inside compact repo/control previews", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | main...origin/main [ahead 2, behind 1] | dirty high (7 local changes) | hotspot change terminal (4)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot branch main@804d5d1 | main...origin/main [ahead 2, behind 1]");
    expect(sections[0]?.rows).toContain("Snapshot sync origin/main | +2/-1 | origin/main | ahead 2 | behind 1");
    expect(sections[2]?.rows).toContain("Branch divergence local +2/-1");
    expect(sections[3]?.rows).toContain("Track main...origin/main [ahead 2, behind 1]");
    expect(sections[3]?.rows).toContain("Upstream origin/main | +2/-1");
  });

  test("uses numeric compact peer counts from repo/control preview in topology rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged | peers 2 | divergence local +2/-1 | hotspot change terminal (281)",
      },
      [],
    );

    expect(sections[0]?.rows).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (peer_branch_diverged)");
    expect(sections[4]?.rows).toContain("Status degraded (1 warning, 2 peers) | peers 2");
    expect(sections[4]?.rows).toContain("Pressure n/a | peers 2");
    expect(sections[4]?.rows).toContain("Peers 2");
  });

  test("derives dirty and hotspot rows from compact repo/control preview alone", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        "Dirty pressure": "high (656 local changes)",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | hotspot terminal (281) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159 | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      },
      [],
    );

    expect(sections[0]?.rows).toContain(
      "Dirty staged 97 | unstaged 505 | untracked 54 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)",
    );
    expect(sections[1]?.rows).toContain("Dirty high (656 local changes) | staged 97 | unstaged 505 | untracked 54");
    expect(sections[1]?.rows).toContain("Lead change terminal (281) | path terminal/src/components/Sidebar.tsx");
    expect(sections[1]?.rows).toContain("Lead dep dharma_swarm.models | inbound 159");
    expect(sections[1]?.rows).toContain(
      "Hotspots change terminal (281) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(sections[5]?.rows).toContain(
      "Summary change terminal (281) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
    );
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
      "Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead terminal (274)",
    );
    expect(sections[0]?.rows).toContain("Snapshot focus Root /Users/dhyana/dharma_swarm | lead terminal/src/app.tsx");
    expect(sections[0]?.rows).toContain(
      "Snapshot topology pulse Topology pressure dharma_swarm Δ563 (517 modified, 46 untracked) | peers 1",
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
    expect(sections[0]?.rows).toContain(
      "Snapshot truth tsc=ok | cycle_acceptance=fail | cycle 2 running | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[0]?.rows).toContain("Task terminal-repo-pane | in_progress/fail | tsc=ok | cycle_acceptance=fail");
    expect(sections[0]?.rows).toContain(
      "Control pulse stale | in_progress / fail | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    const allRows = sections.flatMap((section) => section.rows);
    expect(allRows).toContain("Lead change terminal (274) | path terminal/src/app.tsx");
    expect(allRows).toContain("Lead dep dharma_swarm.models | inbound 159");
    expect(allRows).toContain("Lead path terminal/src/app.tsx");
    expect(sections[0]?.rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(sections[0]?.rows).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
    expect(sections[0]?.rows).toContain(
      "Control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[0]?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 517 | untracked 46 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[1]?.rows).toContain("Snapshot task terminal-repo-pane | in_progress/fail | cycle 2 running | continue required");
    expect(sections[1]?.rows).toContain(
      "Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(sections[1]?.rows).toContain("Warnings sab_canonical_repo_missing | severity high");
    expect(sections[1]?.rows).toContain(
      "Hotspots change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot hotspot summary change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot freshness stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 517 | untracked 46 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (274) | summary change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(sections[1]?.rows).toContain(
      "Snapshot truth tsc=ok | cycle_acceptance=fail | cycle 2 running | next Wire control preview to the live runtime snapshot source.",
    );
    const snapshotTaskIndex = sections[1]?.rows.findIndex((row) =>
      row.startsWith("Snapshot task terminal-repo-pane | in_progress/fail | cycle 2 running"),
    ) ?? -1;
    const snapshotRuntimeIndex = sections[1]?.rows.findIndex((row) =>
      row.startsWith("Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0"),
    ) ?? -1;
    const snapshotRepoControlIndex = sections[1]?.rows.findIndex((row) =>
      row.startsWith("Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1"),
    ) ?? -1;
    const snapshotVerifyIndex = sections[1]?.rows.findIndex((row) =>
      row.startsWith("Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Wire control preview"),
    ) ?? -1;
    expect(snapshotTaskIndex).toBeGreaterThan(-1);
    expect(snapshotRuntimeIndex).toBe(snapshotTaskIndex + 1);
    expect(snapshotRepoControlIndex).toBe(snapshotRuntimeIndex + 1);
    expect(snapshotVerifyIndex).toBe(snapshotRepoControlIndex + 1);
    expect(sections[2]?.rows).toContain("Repo topology sab_canonical_repo_missing; high (563 local changes)");
    expect(sections[2]?.rows).toContain("Severity high | warning sab_canonical_repo_missing");
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

  test("derives repo/control freshness from runtime freshness when updated is absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Repo truth preview":
          "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 1 pending of 2",
        "Runtime freshness":
          "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview":
          "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        "Loop decision": "continue required",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(
      sections[0]?.rows.some((row) =>
        row.startsWith(
          "Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2",
        ),
      ),
    ).toBe(true);
    expect(
      sections[0]?.rows.some((row) =>
        row.startsWith(
          "Snapshot control preview stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z",
        ),
      ),
    ).toBe(true);
    expect(
      sections.flatMap((section) => section.rows).some((row) =>
        row.startsWith(
          "Control pulse stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z",
        ),
      ),
    ).toBe(true);
  });

  test("promotes fallback runtime and verification rows into snapshot card summaries", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Sync: "origin/main | ahead 0 | behind 0",
        Ahead: "0",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 1 peer)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary":
          "change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 517 | untracked 46 | warn 1 (sab_canonical_repo_missing) | hotspot terminal (274) | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 | artifacts Artifacts=7 ContextBundles=1 | next Wire control preview to the live runtime snapshot source.",
      },
      [],
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      [],
      new Date("2026-04-02T12:00:00Z"),
    );

    const operatorSnapshotSummary = sectionCardSummaries(sections[0]!);
    const snapshotSummary = sectionCardSummaries(sections[1]!);
    const repoRiskSummary = sectionCardSummaries(sections[2]!);
    const hotspotsSummary = sectionCardSummaries(sections[5]!);

    expect(operatorSnapshotSummary).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1",
    );
    expect(operatorSnapshotSummary).toContain(
      "Snapshot control preview stale | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
    );
    expect(operatorSnapshotSummary).toContain(
      "Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(snapshotSummary).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1",
    );
    expect(snapshotSummary).toContain(
      "Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(repoRiskSummary).toContain(
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1",
    );
    expect(repoRiskSummary).toContain(
      "Verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
    expect(hotspotsSummary).toContain(
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1",
    );
    expect(hotspotsSummary).toContain(
      "Verify tsc=ok | cycle_acceptance=fail | next Wire control preview to the live runtime snapshot source.",
    );
  });

  test("promotes live control runtime and verification rows into snapshot and repo rail summaries", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
        "Dirty pressure": "high (656 local changes)",
        "Topology status": "degraded (1 warning, 1 peer)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (281)",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "1 done, 0 pending of 1",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 19 running",
        "Loop decision": "continue required",
        Updated: "2026-04-03T02:16:08Z",
        "Verification bundle": "tsc=ok | cycle_acceptance=ok",
        "Runtime freshness": "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
        "Control pulse preview": "in_progress / fail | cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const operatorSnapshotSummary = sectionCardSummaries(sections[0]!);
    const snapshotSummary = sectionCardSummaries(sections[1]!);
    const repoRiskSummary = sectionCardSummaries(sections[2]!);
    const hotspotsSummary = sectionCardSummaries(sections[5]!);

    expect(operatorSnapshotSummary).toContain("Snapshot repo/control verify tsc=ok | cycle_acceptance=ok | next n/a");
    expect(snapshotSummary).toContain(
      "Snapshot runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(snapshotSummary).toContain("Snapshot repo/control verify tsc=ok | cycle_acceptance=ok | next n/a");
    expect(repoRiskSummary).toContain(
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(repoRiskSummary).toContain("Verify tsc=ok | cycle_acceptance=ok | next n/a");
    expect(hotspotsSummary).toContain(
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=0 | Artifacts=7  ContextBundles=1",
    );
    expect(hotspotsSummary).toContain("Verify tsc=ok | cycle_acceptance=ok | next n/a");
  });

  test("carries hotspot summary into repo/control correlation rows", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        "Hotspot summary":
          "change terminal (281); terminal/src/components/RepoPane.tsx (11); terminal/src/components/Sidebar.tsx (7)",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        "Result status": "in_progress",
        Acceptance: "pass",
        "Loop state": "cycle 8 running",
        Updated: "2026-04-03T02:16:08Z",
        "Verification bundle": "tsc=ok",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const operatorSnapshot = sections.find((section) => section.title === "Operator Snapshot");

    expect(operatorSnapshot?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | hotspot terminal (281) | summary change terminal (281); terminal/src/components/RepoPane.tsx (11); terminal/src/components/Sidebar.tsx (7) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok",
    );
  });

  test("derives missing topology rows from partial live repo previews", () => {
    const preview: TabPreview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Ahead: "0",
      Behind: "0",
      "Branch status": "tracking origin/main in sync",
      Sync: "origin/main | ahead 0 | behind 0",
      "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
      "Dirty pressure": "high (563 local changes)",
      Dirty: "0 staged, 517 unstaged, 46 untracked",
      Staged: "0",
      Unstaged: "517",
      Untracked: "46",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology risk": "sab_canonical_repo_missing",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Changed hotspots": "terminal (274)",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159",
      "Hotspot summary":
        "change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    };

    const sections = buildRepoPaneSections(preview, []);
    const rows = sections.flatMap((section) => section.rows);

    expect(rows).toContain("Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 | behind 0");
    expect(rows).toContain("Track tracking origin/main in sync | upstream origin/main");
    expect(rows).toContain("Upstream origin/main | +0/-0");
    expect(rows).toContain("Snapshot topology degraded (1 warning, 1 peer) | warnings 1 (sab_canonical_repo_missing)");
    expect(rows).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(rows).toContain("Snapshot alert high | warning sab_canonical_repo_missing | drift dharma_swarm track main...origin/main");
    expect(rows).toContain("Snapshot hotspots change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159");
    expect(rows).toContain("Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159");
    expect(rows).toContain(
      "Topology preview sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
    );
    expect(rows).toContain("Status degraded (1 warning, 1 peer) | peers 1");
    expect(rows).toContain("Count 1 peer | warnings 1 (sab_canonical_repo_missing)");
    expect(rows).toContain("Pressure dharma_swarm Δ563 (517 modified, 46 untracked) | peers 1");
    expect(rows).toContain("Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(rows).toContain("Members sab_canonical_repo_missing");
    expect(rows).toContain("Drift dharma_swarm track main...origin/main");
    expect(rows).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(rows).toContain("Peers dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(rows).toContain(
      "Hotspot summary change terminal (274) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/app.tsx",
    );
    expect(rows).toContain("Hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159");
  });

  test("synthesizes numeric peer counts into live repo/control preview when peer roster is absent", () => {
    const sections = buildRepoPaneSections(
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "804d5d1",
        "Branch status": "tracking origin/main ahead 2",
        Sync: "origin/main | ahead 2 | behind 0",
        Ahead: "2",
        Behind: "0",
        "Dirty pressure": "high (656 local changes)",
        Staged: "97",
        Unstaged: "505",
        Untracked: "54",
        "Topology warnings": "1 (peer_branch_diverged)",
        "Primary warning": "peer_branch_diverged",
        "Topology peer count": "2",
        "Branch divergence": "local +2/-1",
        "Primary changed hotspot": "terminal (281)",
        "Primary changed path": "terminal/src/components/RepoPane.tsx",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      },
      [],
      {
        "Active task": "terminal-repo-pane",
        Updated: "2026-04-03T02:16:08Z",
        "Loop state": "cycle 20 running",
        "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      },
      [],
      new Date("2026-04-03T12:00:00Z"),
    );

    const repoControlRow = sections
      .flatMap((section) => section.rows)
      .find((row) => row.startsWith("Snapshot repo/control "));

    expect(repoControlRow).toContain("warn 1 (peer_branch_diverged)");
    expect(repoControlRow).toContain("peers 2");
    expect(repoControlRow).toContain("divergence local +2/-1");
  });

  test("keeps authoritative typed topology preview text in repo pane snapshot summaries", () => {
    const payload: WorkspaceSnapshotPayload = {
      version: "v1",
      domain: "workspace_snapshot",
      repo_root: "/repo",
      git: {
        branch: "main",
        head: "abc1234",
        staged: 1,
        unstaged: 2,
        untracked: 3,
        changed_hotspots: [{name: "terminal", count: 4}],
        changed_paths: ["terminal/src/components/RepoPane.tsx"],
        sync: {summary: "origin/main | ahead 2 | behind 1", status: "tracking", upstream: "origin/main", ahead: 2, behind: 1},
      },
      topology: {
        warnings: ["peer_branch_diverged"],
        preview: "authoritative repo topology preview",
        pressure_preview: "authoritative repo topology pressure",
        repos: [
          {
            name: "dharma_swarm",
            role: "canonical_core",
            path: "/repo",
            domain: "workspace_repo",
            canonical: true,
            exists: true,
            branch: "main...origin/main",
            head: "abc1234",
            dirty: true,
            is_git: true,
            modified_count: 3,
            untracked_count: 2,
          },
          {
            name: "dgc-core",
            role: "operator_shell",
            path: "/repo/dgc-core",
            domain: "workspace_repo",
            canonical: false,
            exists: true,
            branch: "detached",
            head: "def5678",
            dirty: true,
            is_git: true,
            modified_count: 1,
            untracked_count: 0,
          },
        ],
      },
      inventory: {python_modules: 1, python_tests: 1, scripts: 1, docs: 1, workflows: 0},
      language_mix: [],
      largest_python_files: [],
      most_imported_modules: [],
    };

    const preview = workspacePayloadToPreview(payload);
    const sections = buildRepoPaneSections(preview, workspacePreviewToLines(preview));
    const rows = sections.flatMap((section) => section.rows);

    expect(rows).toContain("Snapshot topology preview authoritative repo topology preview");
    expect(rows).toContain("Pressure preview authoritative repo topology pressure");
  });
});
