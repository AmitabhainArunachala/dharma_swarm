import {describe, expect, test} from "bun:test";

import {
  deriveWarningFromPreviewSegments,
  extractRepoControlSegment,
  firstDelimitedSegment,
  hasPreviewSignal,
  isBranchStatusSegment,
  isPeerSummary,
  normalizeChangedHotspotLabel,
  normalizePrimaryWarning,
  parseBranchSyncPreview,
  parseBranchTrackingCounts,
  parseRepoControlBranchPreview,
  parseRepoControlPreview,
  parseRepoTruthPreview,
  parseTrackedUpstream,
  splitPreviewPipes,
} from "../src/repoControlPreview";
import type {TabPreview} from "../src/types";

describe("parseRepoControlPreview", () => {
  test("normalizes compact hotspot labels before renderers add display prefixes", () => {
    expect(normalizeChangedHotspotLabel("hotspot change terminal (4)")).toBe("terminal (4)");
    expect(normalizeChangedHotspotLabel("change terminal (4)")).toBe("terminal (4)");
    expect(normalizeChangedHotspotLabel("terminal (4)")).toBe("terminal (4)");
  });

  test("extracts ahead and behind counts from git bracket branch status strings", () => {
    expect(parseBranchTrackingCounts("main...origin/main [ahead 2]")).toEqual({ahead: "2", behind: "0"});
    expect(parseBranchTrackingCounts("tracking origin/main [ahead 2, behind 1]")).toEqual({ahead: "2", behind: "1"});
  });

  test("extracts branch sync counts from git-status branch previews without a separate divergence token", () => {
    expect(parseBranchSyncPreview("main...origin/main [ahead 2, behind 1] | topology peer_branch_diverged")).toEqual({
      branchStatus: "main...origin/main [ahead 2, behind 1]",
      ahead: "2",
      behind: "1",
    });
    expect(parseBranchSyncPreview("main...origin/main [ahead 2] | topology sab_canonical_repo_missing")).toEqual({
      branchStatus: "main...origin/main [ahead 2]",
      ahead: "2",
      behind: "0",
    });
  });

  test("extracts tracked upstream from compact branch-status phrasings", () => {
    expect(parseTrackedUpstream("tracking origin/main in sync")).toBe("origin/main");
    expect(parseTrackedUpstream("ahead of origin/main by 2")).toBe("origin/main");
    expect(parseTrackedUpstream("main...origin/main [ahead 2, behind 1]")).toBe("origin/main");
  });

  test("extracts task, verification, and runtime facts from compact repo/control previews", () => {
    const preview: TabPreview = {
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next hydrate control preview from runtime state",
    };

    expect(parseRepoControlPreview(preview)).toEqual({
      raw: preview["Repo/control preview"],
      freshness: "stale",
      task: "terminal-repo-pane",
      taskProgress: "3 done, 1 pending of 4",
      resultStatus: "in_progress",
      acceptance: "fail",
      loopDecision: "continue required",
      loopState: "cycle 13 ready",
      updated: "2026-04-03T01:15:00Z",
      verificationBundle: "tsc=ok | cycle_acceptance=fail",
      nextTask: "hydrate control preview from runtime state",
      truthPreview:
        "branch main@abc123 | tracking origin/main in sync | warn sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | tsc=ok | cycle_acceptance=fail | cycle 13 ready | next hydrate control preview from runtime state",
      branch: "main@abc123",
      branchName: "main",
      head: "abc123",
      branchStatus: "tracking origin/main in sync",
      upstream: "origin/main",
      ahead: "n/a",
      behind: "n/a",
      warning: "sab_canonical_repo_missing",
      topologyWarningCount: "1",
      topologyWarningMembers: "sab_canonical_repo_missing",
      topologyPeer: "n/a",
      topologyPeers: "n/a",
      topologyPeerCount: "0",
      peerDrift: "n/a",
      peerMarkers: "n/a",
      branchDivergence: "n/a",
      detachedPeers: "n/a",
      dirtyState: "high (563 local changes)",
      staged: "n/a",
      unstaged: "n/a",
      untracked: "n/a",
      hotspot: "hotspot change terminal (274)",
      hotspotSummary: "change terminal (274)",
      primaryHotspot: "change terminal (274)",
      hotspotPath: "n/a",
      hotspotDependency: "n/a",
      hotspotInbound: "n/a",
      runtimeDb: "/Users/dhyana/.dharma/state/runtime.db",
      runtimeActivity: "Sessions=18 Runs=0 ActiveRuns=0",
      artifactState: "Artifacts=7 ContextBundles=1",
      runtimeSummary:
        "/Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 ActiveRuns=0 | Artifacts=7 ContextBundles=1",
      runtimeSessions: "18",
      runtimeRuns: "0",
      runtimeActiveRuns: "0",
      runtimeArtifacts: "7",
      runtimeContextBundles: "1",
    });
  });

  test("tolerates divergence and detached topology tokens in compact repo/control previews", () => {
    const preview: TabPreview = {
      "Repo/control preview":
        "stale | task terminal-repo-pane | branch main@abc123 | tracking origin/main ahead 2 | dirty high (563 local changes) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | peer dharma_swarm drift main...origin/main | detached dgc-core detached | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail",
    };

    expect(parseRepoControlPreview(preview)).toMatchObject({
      freshness: "stale",
      task: "terminal-repo-pane",
      branch: "main@abc123",
      branchStatus: "tracking origin/main ahead 2",
      warning: "n/a",
      topologyPeer: "peer dharma_swarm drift main...origin/main",
      topologyPeers:
        "peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True)",
      peerDrift: "drift dharma_swarm drift main...origin/main",
      peerMarkers: "markers dharma_swarm drift main...origin/main; dgc-core n/a",
      branchDivergence: "divergence local +2/-1",
      detachedPeers: "detached dgc-core detached",
      dirtyState: "high (563 local changes)",
      hotspot: "hotspot change terminal (274)",
      loopState: "cycle 13 ready",
      updated: "2026-04-03T01:15:00Z",
      verificationBundle: "tsc=ok | cycle_acceptance=fail",
      truthPreview:
        "branch main@abc123 | tracking origin/main ahead 2 | peer dharma_swarm drift main...origin/main | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | detached dgc-core detached | dirty high (563 local changes) | hotspot change terminal (274) | tsc=ok | cycle_acceptance=fail | cycle 13 ready | next n/a",
    });
  });

  test("derives structured topology, dirty, hotspot, and runtime counts from compact repo/control previews", () => {
    const parsed = parseRepoControlPreview(
      "fresh | task terminal-repo-pane | branch feature/repo-pane@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | divergence local +2/-1 | dirty staged 112 | unstaged 545 | untracked 112 | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=2 ActiveRuns=1 | artifacts Artifacts=7 ContextBundles=1",
    );

    expect(parsed).toMatchObject({
      branchName: "feature/repo-pane",
      head: "804d5d1",
      upstream: "origin/main",
      ahead: "2",
      behind: "1",
      topologyWarningCount: "2",
      topologyWarningMembers: "peer_branch_diverged; sab_canonical_repo_missing",
      topologyPeerCount: "2",
      staged: "112",
      unstaged: "545",
      untracked: "112",
      hotspotSummary:
        "change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
      primaryHotspot: "change terminal (281)",
      hotspotPath: "terminal/src/components/RepoPane.tsx",
      hotspotDependency: "dharma_swarm.models",
      hotspotInbound: "159",
      runtimeSessions: "18",
      runtimeRuns: "2",
      runtimeActiveRuns: "1",
      runtimeArtifacts: "7",
      runtimeContextBundles: "1",
    });
  });

  test("preserves numeric topology peer counts from compact repo/control previews", () => {
    const parsed = parseRepoControlPreview(
      "fresh | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | warn sab_canonical_repo_missing | peers 2 | dirty staged 112 | unstaged 545 | untracked 112 | hotspot change terminal (281)",
    );

    expect(parsed).toMatchObject({
      topologyPeers: "peers 2",
      topologyPeerCount: "2",
      topologyWarningCount: "1",
    });
  });

  test("returns null when the compact repo/control preview is absent", () => {
    expect(parseRepoControlPreview({})).toBeNull();
  });

  test("shares repo snapshot helper parsing across repo pane and sidebar projections", () => {
    const repoTruth =
      "branch main@804d5d1 | dirty staged 112 | unstaged 545 | untracked 112 | warn peer_branch_diverged; sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx";
    const repoControl =
      "fresh | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main [ahead 2, behind 1] | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | divergence local +2/-1 | dirty staged 112 | unstaged 545 | untracked 112 | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159";

    expect(hasPreviewSignal("fresh")).toBe(true);
    expect(splitPreviewPipes("a | b | c")).toEqual(["a", "b", "c"]);
    expect(firstDelimitedSegment("warn_a; warn_b")).toBe("warn_a");
    expect(normalizePrimaryWarning("2 (warn_a; warn_b)")).toBe("warn_a");
    expect(isPeerSummary("dharma_swarm (canonical_core, main...origin/main, dirty True)")).toBe(true);
    expect(isBranchStatusSegment("tracking origin/main [ahead 2, behind 1]")).toBe(true);
    expect(deriveWarningFromPreviewSegments("warn_a | dharma_swarm (canonical_core, main...origin/main, dirty True)")).toBe("warn_a");
    expect(parseRepoTruthPreview(repoTruth)).toEqual({
      raw: repoTruth,
      branch: "main",
      head: "804d5d1",
      dirtyState: "staged 112 | unstaged 545 | untracked 112",
      warning: "peer_branch_diverged; sab_canonical_repo_missing",
      hotspot: "change terminal (281) | path terminal/src/components/RepoPane.tsx",
    });
    expect(parseBranchSyncPreview("tracking origin/main [ahead 2, behind 1] | +2/-1 | topology peer_branch_diverged")).toEqual({
      branchStatus: "tracking origin/main [ahead 2, behind 1]",
      ahead: "2",
      behind: "1",
    });
    expect(parseRepoControlBranchPreview(repoControl)).toEqual({
      branchStatus: "tracking origin/main [ahead 2, behind 1]",
      ahead: "2",
      behind: "1",
    });
    expect(extractRepoControlSegment(repoControl, "warn")).toBe("peer_branch_diverged; sab_canonical_repo_missing");
  });
});
