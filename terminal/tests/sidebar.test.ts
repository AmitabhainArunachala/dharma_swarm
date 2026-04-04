import {describe, expect, test} from "bun:test";

import {buildContextSidebarLines, buildVisibleContextSidebarLines} from "../src/components/Sidebar";
import {workspacePayloadToPreview, workspacePreviewToLines, workspaceSnapshotToPreview} from "../src/protocol";
import type {TabSpec, WorkspaceSnapshotPayload} from "../src/types";

describe("buildContextSidebarLines", () => {
  test("surfaces repo dependency hotspots and durable control previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "95210b1",
          Sync: "origin/main | ahead 0 | behind 0",
          "Branch status": "tracking origin/main in sync",
          Upstream: "origin/main",
          Ahead: "0",
          Behind: "0",
          "Branch sync preview":
            "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
          "Repo risk preview":
            "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
          Dirty: "0 staged, 510 unstaged, 42 untracked",
          "Dirty pressure": "high (552 local changes)",
          Staged: "0",
          Unstaged: "510",
          Untracked: "42",
          "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142)",
          "Hotspot summary":
            "change terminal (274); .dharma_psmv_hyperfile_branch (142) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
          "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
          "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
          "Changed paths":
            "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning severity": "high",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology risk": "sab_canonical_repo_missing",
          "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology preview":
            "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peer drift markers": "dharma_swarm track main...origin/main",
          "Topology peer count": "1",
          "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Primary changed hotspot": "terminal (274)",
          "Primary changed path": "terminal/src/protocol.ts",
          "Primary file hotspot": "dgc_cli.py (6908 lines)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
          Hotspots: "dgc_cli.py (6908 lines)",
          "Inbound hotspots": "dharma_swarm.models | inbound 159",
          Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
          "Language mix": ".py: 1125; .md: 511",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-01",
          "Concept count": "321",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Run state": "0 runs | 0 active runs",
          "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 6 running",
          "Loop decision": "continue required",
          "Active task": "terminal-repo-pane",
          "Task progress": "3 done, 1 pending of 4",
          "Result status": "complete",
          Acceptance: "pass",
          "Next task": "Promote topology warnings into a dedicated repo risk section.",
          "Last result": "complete / pass",
          "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
          "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime freshness":
            "cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Control pulse preview":
            "complete / pass | cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime summary":
            "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
          Updated: "2026-04-01T00:00:00Z",
          Toolchain: "claude, python3, node",
          Alerts: "none",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      undefined,
      new Date("2026-04-01T04:00:00Z"),
    );

    expect(lines).toContain("Repo | bridge connected");
    expect(lines).toContain("Model codex gpt-5.4");
    expect(lines).toContain("Repo Preview");
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (552 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Dirty staged 0 | unstaged 510 | untr"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 |…"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch sync tracking origin/main in sync | +0/-0"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty high (552 local changes) | staged 0 | un"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing |"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot branch divergence local +0/-0 | peer dharma_swarm"))).toBe(true);
    expect(lines).toContain("Snapshot detached peers none");
    expect(lines.some((line) => line.startsWith("Snapshot topology preview sab_canonical_repo_missing | dharma"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology pressure 1 warning | dharma_swarm Δ552"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspots change terminal (274) | path terminal/src"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (274); .dharma"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot summary topology sab_canonical_repo"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot truth branch main@95210b1 | dirty staged 0 | unstaged 510"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot focus ") && line.endsWith("| lead terminal/src/protocol.ts"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Focus /Users/dhyana/dharma_sw"))).toBe(true);
    expect(lines.some((line) => line.endsWith("| terminal/src/protocol.ts"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Topo pressure dharma_swarm Δ552 (510 modified, 42"))).toBe(true);
    expect(lines).toContain("Pressure preview 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)");
    expect(lines).toContain("Hotspot pressure change terminal (274) | dep dharma_swarm.models | inbound 159");
    expect(lines).toContain("Root /Users/dhyana/dharma_swarm");
    expect(lines).toContain("Branch main@95210b1");
    expect(lines.some((line) => line.startsWith("Branch preview tracking origin/main in sync | +0/-0 | topol"))).toBe(
      true,
    );
    expect(lines).toContain("Track tracking origin/main in sync | +0/-0");
    expect(lines).toContain("Sync origin/main | ahead 0 | behind 0");
    expect(lines.some((line) => line.startsWith("Health topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Activity Sessions=18"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | complete/pass | tsc=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo/control verify tsc=ok | py_compile_bridge=ok | bridg"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot truth tsc=ok") && line.includes("| cycle 6 running | next "))).toBe(true);
    expect(lines).toContain("Repo Risk");
    expect(lines.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines).toContain("Count 1 peer | warnings 1 (sab_canonical_repo_missing)");
    expect(lines.some((line) => line.startsWith("Dirty high (552 local changes) | staged 0 | unstaged 510"))).toBe(true);
    expect(lines).toContain("State 0 staged, 510 unstaged, 42 untracked");
    expect(lines.some((line) => line.startsWith("Topo degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Topology signal high | dharma_swarm track main...origin/main");
    expect(lines.some((line) => line.startsWith("Topology preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Risk preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(lines).toContain("Members sab_canonical_repo_missing");
    expect(lines).toContain("Severity high | warning sab_canonical_repo_missing");
    expect(lines).toContain("Lead warn sab_canonical_repo_missing");
    expect(lines).toContain("Peer drift dharma_swarm track main...origin/main");
    expect(lines.some((line) => line.startsWith("Lead peer dharma_swarm (canonical_core, main...origin/main"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Peers dharma_swarm (canonical_core, main...origin/main"))).toBe(true);
    expect(lines).toContain("Pressure dharma_swarm Δ552 (510 modified, 42 untracked)");
    expect(lines).toContain("Changed terminal (274); .dharma_psmv_hyperfile_branch (142)");
    expect(lines.some((line) => line.startsWith("Summary change terminal (274) | path terminal/src/protocol.ts |"))).toBe(true);
    expect(lines).toContain("Lead change terminal (274) | terminal/src/protocol.ts");
    expect(lines).toContain("Lead path terminal/src/protocol.ts");
    expect(lines).toContain("Lead file dgc_cli.py (6908 lines)");
    expect(lines).toContain("Lead dep dharma_swarm.models | inbound 159");
    expect(lines.some((line) => line.startsWith("Paths terminal/src/protocol.ts; terminal/src/components/Sideb"))).toBe(true);
    expect(lines).toContain("Hotspots dgc_cli.py (6908 lines)");
    expect(lines).toContain("Deps dharma_swarm.models | inbound 159");
    expect(lines.some((line) => line.startsWith("Inventory 501 modules | 494 tests | 124 scripts | 239 docs"))).toBe(true);
    expect(lines).toContain("Mix .py: 1125; .md: 511");
    expect(lines).toContain("Ver 2026-04-01 | concepts 321");
    expect(lines).toContain("Control Preview");
    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | complete/pass | tsc=ok | py_"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(
      lines.some(
        (line) =>
          line.startsWith("Repo warn sab_canonical_repo_missing | severity high | pressure 1 warning | dharma_swarm Δ552"),
      ),
    ).toBe(true);
    expect(
      lines.some(
        (line) =>
          line.startsWith("Repo hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models"),
      ),
    ).toBe(true);
    expect(lines).toContain("Snapshot task terminal-repo-pane | complete/pass");
    expect(lines.some((line) => line.startsWith("Snapshot runtime") && line.includes("Sessions=18"))).toBe(true);
    expect(lines).toContain("Snapshot loop fresh | cycle 6 running | continue required");
    expect(lines.some((line) => line.startsWith("Snapshot verify tsc=ok | py_compile_bridge=ok | bridg"))).toBe(true);
    expect(
      lines.some((line) =>
        line.startsWith("Snapshot truth tsc=ok") && line.includes("| cycle 6 running | next "),
      ),
    ).toBe(true);
    expect(lines.some((line) => line.startsWith("Freshness fresh | cycle 6 running | updated 2026-04-01T00:00:00Z |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Runtime summary /Users/dhyana/.dharma/state/runtime.db | 18 sessions"))).toBe(true);
    expect(lines).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(lines).toContain("Outcome complete | accept pass");
    expect(lines).toContain("Runtime /Users/dhyana/.dharma/state/runtime.db");
    expect(lines.some((line) => line.startsWith("Sessions 18 sessions | 0 claims | 0 active claims"))).toBe(true);
    expect(lines).toContain("Runs 0 runs | 0 active runs");
    expect(lines.some((line) => line.startsWith("Context 7 artifacts | 2 promoted facts | 1 context bundles"))).toBe(true);
    expect(lines).toContain("Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions");
    expect(lines.some((line) => line.startsWith("Activity Sessions=18 Runs=0 | Artifacts=7 ContextBund"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Health tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines).toContain("Loop cycle 6 running | continue required");
    expect(lines).toContain("Updated 2026-04-01T00:00:00Z");
    expect(lines.some((line) => line.startsWith("Next Promote topology warnings into a dedicated repo risk"))).toBe(true);
    expect(lines).toContain("Result complete / pass");
    expect(lines.some((line) => line.startsWith("Verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Checks tsc ok; py_compile_bridge ok; bridge_snapshots ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Bundle tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("State /Users/dhyana/.dharma/terminal_supervisor/terminal-2026"))).toBe(true);
    expect(lines).toContain("Tools claude, python3, node | alerts none");
    expect(lines.filter((line) => line.startsWith("Hotspot pressure "))).toHaveLength(1);
    expect(lines).toHaveLength(128);
  });

  test("surfaces authority state when repo and control previews are placeholders", () => {
    const tabs: TabSpec[] = [
      {id: "repo", title: "Repo", kind: "repo", lines: [], preview: {Branch: "main", Head: "abc123"}},
      {id: "control", title: "Control", kind: "control", lines: [], preview: {"Active task": "n/a"}},
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      {id: "models", title: "Models", kind: "models", lines: [], preview: {Active: "Codex 5.4", Strategy: "responsive", Route: "codex:gpt-5.4", Fallbacks: "1"}},
      {id: "agents", title: "Agents", kind: "agents", lines: [], preview: {"Active runs": "0", "Recent actions": "0", Routes: "0", "Primary route": "n/a"}},
      {id: "evolution", title: "Evolution", kind: "evolution", lines: [], preview: {Domains: "1", "Primary domain": "code"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "offline",
      {Branch: "main", Head: "abc123", Authority: "placeholder | bridge offline | awaiting authoritative repo refresh"},
      {Authority: "placeholder | bridge offline | awaiting authoritative control refresh"},
    );

    expect(lines).toContain("Authority placeholder | bridge offline | awaiting authoritative repo refresh");
    expect(lines).toContain("Authority placeholder | bridge offline | awaiting authoritative control refresh");
  });

  test("prefers explicit branch divergence and detached peer fields in visible context", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 0",
          "Branch status": "ahead of origin/main by 2",
          Upstream: "origin/main",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology peer_branch_diverged; elevated (7 local changes)",
          "Repo risk preview": "ahead of origin/main by 2 | peer_branch_diverged | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Dirty pressure": "contained (7 local changes)",
          "Topology warnings": "1 (peer_branch_diverged)",
          "Topology warning severity": "elevated",
          "Topology status": "degraded (1 warning, 2 peers)",
          "Topology risk": "peer_branch_diverged",
          "Primary warning": "peer_branch_diverged",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology peer count": "2",
          "Branch divergence": "local +2/-0 | peer canonical_core drift explicit",
          "Detached peers": "dgc-core detached",
          "Primary changed hotspot": "terminal (4)",
          "Primary changed path": "terminal/src/components/RepoPane.tsx",
          "Hotspot summary": "change terminal (4) | path terminal/src/components/RepoPane.tsx",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Result status": "in_progress",
          Acceptance: "pass",
          "Loop state": "cycle 8 running",
          Updated: "2026-04-03T02:16:08Z",
          "Verification bundle": "tsc=ok",
          "Control pulse preview": "in_progress / pass | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(tabs, "Repo", "codex", "gpt-5.4", "connected");

    expect(lines).toContain("Snapshot branch divergence local +2/-0 | peer canonical_core drift explicit");
    expect(lines).toContain("Snapshot detached peers dgc-core detached");
    expect(lines).toContain("Branch divergence local +2/-0 | peer canonical_core drift explicit");
    expect(lines).toContain("Detached peers dgc-core detached");
  });

  test("derives missing topology pressure preview in full context from partial live repo previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-02T12:00:00Z"),
    );

    expect(lines).toContain("Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(lines.some((line) => line.startsWith("Snapshot topology pressure 1 (sab_canonical_repo_missing) | dharma_swarm Δ563"))).toBe(true);
  });

  test("preserves stored repo/control preview when the live control preview is only a placeholder", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          Branch: "main",
          Head: "abc123",
        },
      },
      {id: "control", title: "Control", kind: "control", lines: [], preview: {}},
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "offline",
      {
        Branch: "main",
        Head: "abc123",
        "Branch status": "tracking origin/main in sync",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159 | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | next hydrate control preview from runtime state",
      },
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
    );

    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@abc123"))).toBe(true);
    expect(lines.some((line) => line.includes("change terminal (274)"))).toBe(true);
    const controlPreviewIndex = lines.findIndex((line) => line === "Control Preview");
    const controlFallbackIndex = lines.findIndex(
      (line, index) =>
        index > controlPreviewIndex &&
        line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@abc123"),
    );
    expect(controlPreviewIndex).toBeGreaterThan(-1);
    expect(controlFallbackIndex).toBeGreaterThan(controlPreviewIndex);
    expect(lines).toContain("Control pulse stale | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok");
    expect(lines.some((line) => line.startsWith("Repo warn sab_canonical_repo_missing | severity high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo hotspot change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models"))).toBe(
      true,
    );
    expect(lines).toContain("Control task terminal-repo-pane");
    expect(lines).toContain("Control verify tsc=ok | next hydrate control preview from runtime state");
    expect(lines.some((line) => line.startsWith("Snapshot control preview stale | cycle 13 ready | updated 2026-04-03T01:15:00Z |"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot repo/control verify tsc=ok | next hydrate control preview from runtime state"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot task "))).toBe(false);
    expect(lines.some((line) => line.startsWith("Snapshot runtime "))).toBe(false);
  });

  test("surfaces runtime facts from stored repo/control previews when control stays placeholder-only", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          Branch: "main",
          Head: "abc123",
        },
      },
      {id: "control", title: "Control", kind: "control", lines: [], preview: {}},
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "offline",
      {
        Branch: "main",
        Head: "abc123",
        "Branch status": "tracking origin/main in sync",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | artifacts Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3 | next hydrate control preview from runtime state",
      },
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
    );

    expect(lines.some((line) => line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot control preview stale | cycle 13 ready | updated 2026-04-03T01:15:00Z |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Runtime summary /Users/dhyana/.dharma/state/runtime.db"))).toBe(true);
    expect(lines).toContain("Inventory 0 claims | 0 active claims | 0 acked claims | 2 promoted facts | 3 operator actions");
    expect(
      lines.some(
        (line) => line.startsWith("Snapshot runtime /Users/dhyana/.dharma/state/runtime.db"),
      ),
    ).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo/control verify tsc=ok | next hydrate control preview from runtime state"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot truth branch main@abc123 | tracking origin/main in sync | war"))).toBe(true);
    const snapshotControlPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot control preview stale | cycle 13 ready | updated 2026-04-03T01:15:00Z |"),
    );
    const snapshotRuntimeIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot runtime /Users/dhyana/.dharma/state/runtime.db"),
    );
    const snapshotVerificationIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control verify tsc=ok | next hydrate control preview from runtime state"),
    );
    expect(snapshotControlPreviewIndex).toBeGreaterThan(-1);
    expect(snapshotRuntimeIndex).toBe(snapshotControlPreviewIndex + 1);
    expect(snapshotVerificationIndex).toBe(snapshotRuntimeIndex + 1);
  });

  test("prefers live runtime inventory over stale repo/control runtime counts in visible context during partial control refreshes", () => {
    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview: {
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
        },
        {
          id: "control",
          title: "Control",
          kind: "control",
          lines: [],
          preview: {
            "Session state": "21 sessions | 5 claims | 2 active claims | 1 acked claims",
            "Run state": "3 runs | 1 active runs",
            "Context state": "9 artifacts | 4 context bundles | 6 operator actions",
          },
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
    );

    expect(lines).toContain("Runtime state Sessions=21 Runs=3 | Artifacts=9 ContextBundles=4");
    expect(lines).toContain("Runtime summary Sessions=21 Runs=3 | Artifacts=9 ContextBundles=4");
    expect(lines).toContain("Snapshot runtime Sessions=21 Runs=3 | Artifacts=9 ContextBundles=4");
    expect(lines).toContain("Control verify tsc=ok | next refresh live runtime state");
    expect(lines).not.toContain("Runtime state /old/runtime.db | Sessions=18 Runs=0 | Artifacts=7 ContextBundles=1");
  });

  test("reconstructs snapshot task rows from compact repo/control previews when control stays placeholder-only", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          Branch: "main",
          Head: "abc123",
        },
      },
      {id: "control", title: "Control", kind: "control", lines: [], preview: {}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "offline",
      {
        Branch: "main",
        Head: "abc123",
        "Branch status": "tracking origin/main in sync",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Primary warning": "sab_canonical_repo_missing",
        "Hotspot summary": "change terminal (274)",
        "Repo/control preview":
          "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | next hydrate control preview from runtime state",
      },
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
    );

    expect(lines).toContain("Snapshot task terminal-repo-pane | in_progress/fail | cycle 13 ready | continue required");
    expect(
      lines.some(
        (line) => line.startsWith("Snapshot truth branch main@abc123 | tracking origin/main in sync | war"),
      ),
    ).toBe(true);
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
  });

  test("surfaces repo and control preview fallbacks from transcript-only repo lines", () => {
    const repoPreview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "abc123",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch status": "tracking origin/main in sync",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (563 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo truth preview":
        "branch main@abc123 | dirty staged 0 | unstaged 517 | untracked 46 | warn sab_canonical_repo_missing | hotspot change terminal (274)",
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@abc123 | tracking origin/main in sync | sab_canonical_repo_missing | dirty high (563 local changes) | hotspot change terminal (274) | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | next hydrate control preview from runtime state",
      "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
      Dirty: "0 staged, 517 unstaged, 46 untracked",
      "Dirty pressure": "high (563 local changes)",
      Staged: "0",
      Unstaged: "517",
      Untracked: "46",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning members": "sab_canonical_repo_missing",
      "Topology warning severity": "high",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Topology pressure preview": "1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology peer count": "2",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
      "Detached peers": "none",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked); dgc-core clean",
      "Changed hotspots": "terminal (274)",
      "Changed paths": "terminal/src/app.tsx",
      "Hotspot summary": "change terminal (274) | path terminal/src/app.tsx",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/app.tsx",
      "Hotspot pressure preview": "change terminal (274)",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/app.tsx",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
      "Primary dependency hotspot": "none",
      Hotspots: "dgc_cli.py (6908 lines)",
      "Inbound hotspots": "none",
      Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
      "Language mix": ".py: 1125; .md: 511",
    };
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: workspacePreviewToLines(repoPreview),
      },
      {id: "control", title: "Control", kind: "control", lines: [], preview: {}},
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "offline",
      undefined,
      {
        Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      },
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | progress 3 done"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse stale | cycle 13 ready | updated 2026-04-03T01:15:00Z"))).toBe(true);
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
  });

  test("prefers an explicit control truth preview over recomputing the snapshot truth row", () => {
    const lines = buildVisibleContextSidebarLines(
      [
        {id: "repo", title: "Repo", kind: "repo", lines: [], preview: {Branch: "main", Head: "abc123"}},
        {
          id: "control",
          title: "Control",
          kind: "control",
          lines: [],
          preview: {
            "Active task": "terminal-repo-pane",
            "Loop state": "cycle 2 running",
            "Verification bundle": "tsc=ok | cycle_acceptance=fail",
            "Next task": "stale fallback next task",
            "Control truth preview": "verify compact | cycle 2 running | next hydrate control truth from disk",
          },
        },
        {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-01T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot truth verify compact | cycle 2 running | next hydra"))).toBe(true);
  });

  test("prefers live repo and control previews over stale tab previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [{id: "repo-1", kind: "system", text: "Branch: stale"}],
        preview: {
          Branch: "stale",
          Head: "old0001",
          "Repo risk": "stale risk",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-01",
          "Concept count": "321",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [{id: "control-1", kind: "system", text: "Active task: stale-task"}],
        preview: {
          "Active task": "stale-task",
          "Result status": "stale",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        Head: "95210b1",
        "Branch status": "tracking origin/main in sync",
        Ahead: "0",
        Behind: "0",
        Sync: "origin/main | ahead 0 | behind 0",
        "Branch sync preview":
          "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (563 local changes)",
        "Repo risk preview":
          "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Repo/control preview":
          "stale | task stale-task | stale repo/control preview that should not survive a live control refresh",
        "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
        "Dirty pressure": "high (563 local changes)",
        Dirty: "0 staged, 517 unstaged, 46 untracked",
        Staged: "0",
        Unstaged: "517",
        Untracked: "46",
        "Topology status": "degraded (1 warning, 2 peers)",
        "Topology risk": "sab_canonical_repo_missing",
        "Topology warnings": "1 (sab_canonical_repo_missing)",
        "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology preview":
          "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Topology pressure preview": "1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Primary warning": "sab_canonical_repo_missing",
        "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Changed hotspots": "terminal (274)",
        "Hotspot summary": "change terminal (274)",
        "Changed paths": "terminal/src/app.tsx",
        "Primary changed path": "terminal/src/app.tsx",
        "Primary file hotspot": "dgc_cli.py (6908 lines)",
        "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        Hotspots: "dgc_cli.py (6908 lines)",
        "Inbound hotspots": "dharma_swarm.models | inbound 159",
        Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
        "Language mix": ".py: 1125; .md: 511",
      },
      {
        "Active task": "terminal-repo-pane",
        "Task progress": "3 done, 1 pending of 4",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
        "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
        "Run state": "0 runs | 0 active runs",
        "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Runtime activity": "Sessions=18  Runs=0",
        "Artifact state": "Artifacts=7  ContextBundles=1",
        "Loop state": "cycle 2 running",
        "Loop decision": "continue required",
        Updated: "2026-04-01T03:44:29Z",
        "Next task": "Wire control preview to the live runtime snapshot source.",
        "Last result": "in_progress / fail",
        "Verification summary": "tsc=ok | cycle_acceptance=fail",
        "Verification checks": "tsc ok; cycle_acceptance fail",
        "Verification bundle": "tsc=ok | cycle_acceptance=fail",
        "Runtime freshness": "cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
        "Control pulse preview":
          "in_progress / fail | cycle 2 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=fail",
        "Runtime summary":
          "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
        Toolchain: "claude, python3, node",
        Alerts: "none",
      },
      new Date("2026-04-02T12:00:00Z"),
    );

    expect(lines).toContain("Root /Users/dhyana/dharma_swarm");
    expect(lines).toContain("Branch main@95210b1");
    expect(lines.some((line) => line.startsWith("Health topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync"))).toBe(true);
    expect(lines).toContain("Repo Risk");
    expect(lines.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (563 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing | drift"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot freshness stale | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
    expect(
      lines.some(
        (line) => line.startsWith("Snapshot truth tsc=ok | cycle_acceptan") && line.includes("| cycle 2 running | next "),
      ),
    ).toBe(true);
    expect(lines.some((line) => line.startsWith("Focus /Users/dhyana/dharma_sw"))).toBe(true);
    expect(lines.some((line) => line.endsWith("| terminal/src/app.tsx"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Freshness stale | cycle 2 running | updated 2026-04-01T03:44:29Z |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pulse stale | in_progress / fail | cycle 2 running | updated 2026-04-01T03:44:29Z | veri"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Runtime summary /Users/dhyana/.dharma/state/runtime.db | 18 sessions"))).toBe(true);
    expect(lines).toContain("Snapshot task terminal-repo-pane | in_progress/fail");
    expect(lines).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(lines).toContain("Outcome in_progress | accept fail");
    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | in_progress/fail | tsc=ok |"))).toBe(true);
    expect(lines).not.toContain("Root n/a");
    expect(lines).not.toContain("Branch stale@old0001");
    expect(lines).not.toContain("Task stale-task | n/a");
    expect(lines.some((line) => line.includes("stale repo/control preview"))).toBe(false);
  });

  test("derives sidebar control verification lines from compact control freshness when expanded fields are absent", () => {
    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview: {
            "Repo root": "/Users/dhyana/dharma_swarm",
            Branch: "main",
            Head: "804d5d1",
          },
        },
        {
          id: "control",
          title: "Control",
          kind: "control",
          lines: [],
          preview: {
            "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
            "Runtime activity": "Sessions=5 Runs=2 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
            "Artifact state": "Artifacts=8 PromotedFacts=3 ContextBundles=2 OperatorActions=4",
            "Control pulse preview":
              "fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            "Runtime freshness":
              "cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          },
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Control pulse fresh | complete / fail | cycle 13 waiting_for_verification"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Control verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | next n/a"))).toBe(
      true,
    );
  });

  test("derives sidebar runtime preview lines from runtime summary when detailed control rows are absent", () => {
    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview: {
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
        },
        {
          id: "control",
          title: "Control",
          kind: "control",
          lines: [],
          preview: {
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
            "Control pulse preview":
              "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          },
        },
        {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(
      lines.some(
        (line) =>
          line.startsWith("Snapshot runtime /Users/dhyana/.dharma/s") &&
          line.includes("Sessions=18 Runs=0") &&
          line.includes("Artifacts=7 ContextBund"),
      ),
    ).toBe(true);
    expect(
      lines.some(
        (line) =>
          line.startsWith("Snapshot control preview stale | in_progress / fai") &&
          line.includes("Sessions=18 Runs=0") &&
          line.includes("Artifacts=7 ContextBund"),
      ),
    ).toBe(true);
    expect(
      lines.some(
        (line) =>
          line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db") &&
          line.includes("Sessions=18 Runs=0") &&
          line.includes("Artifacts=7 ContextBundle"),
      ),
    ).toBe(true);
    expect(
      lines.some(
        (line) =>
          line.startsWith("Runtime summary /Users/dhyana/.dharma/state/runtime.db") &&
          line.includes("18 sessions") &&
          line.includes("0 active claims"),
      ),
    ).toBe(true);
  });

  test("prioritizes repo and control previews in the rendered context subset", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "95210b1",
          Sync: "origin/main | ahead 0 | behind 0",
          "Branch status": "tracking origin/main in sync",
          Ahead: "0",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
          "Repo risk preview":
            "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          Dirty: "0 staged, 510 unstaged, 42 untracked",
          "Dirty pressure": "high (552 local changes)",
          Staged: "0",
          Unstaged: "510",
          Untracked: "42",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology risk": "sab_canonical_repo_missing",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning severity": "high",
          "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology preview":
            "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Peer drift markers": "dharma_swarm track main...origin/main",
          "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked)",
          "Primary changed path": "n/a",
          "Primary file hotspot": "dgc_cli.py (6908 lines)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
          Hotspots: "dgc_cli.py (6908 lines)",
          "Inbound hotspots": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-01",
          "Concept count": "321",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Run state": "0 runs | 0 active runs",
          "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 6 running",
          "Loop decision": "continue required",
          "Active task": "terminal-repo-pane",
          "Task progress": "3 done, 1 pending of 4",
          "Result status": "complete",
          Acceptance: "pass",
          "Next task": "Promote topology warnings into a dedicated repo risk section.",
          "Last result": "complete / pass",
          "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime freshness":
            "cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Control pulse preview":
            "complete / pass | cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Runtime summary":
            "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
          Updated: "2026-04-01T00:00:00Z",
          Toolchain: "claude, python3, node",
          Alerts: "none",
        },
      },
      {
        id: "models",
        title: "Models",
        kind: "models",
        lines: [],
        preview: {
          Active: "codex gpt-5.4",
          Strategy: "balanced",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-01T04:00:00Z"),
    );

    expect(lines).toHaveLength(68);
    expect(lines).toContain("Repo Preview");
    expect(lines).toContain("Hotspot Focus");
    expect(lines).toContain("Repo Risk");
    expect(lines).toContain("Count 1 peer | warnings 1 (sab_canonical_repo_missing)");
    expect(lines).toContain("Control Preview");
    expect(lines.some((line) => line.startsWith("Repo warn sab_canonical_repo_missing | severity high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo hotspot "))).toBe(true);
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (552 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Dirty staged 0 | unstaged 510 | untr"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +0/-0 | origin/main | ahead 0 |…"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot branch sync tracking origin/main in sync | +0/-0"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty high (552 local changes) | staged 0"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology signal high | dharma_swarm track main...origin/main"))).toBe(
      true,
    );
    expect(lines).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch divergence local +0/-0 | peer dharma_swarm"))).toBe(true);
    expect(lines).toContain("Snapshot detached peers none");
    expect(lines.some((line) => line.startsWith("Snapshot topology preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology pressure "))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspots dep dharma_swarm.models | inbound 159"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary dep dharma_swarm.models | inbound 159"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot summary topology sab_canonical_repo"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo risk tracking origin/main in sync | sab_canonical_repo_missi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo/control fresh | task terminal-repo-pane"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot control preview fresh | complete / pass | c…"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync |"))).toBe(true);
    expect(lines).toContain("Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ552 (510 modified, 42 untracked)");
    expect(lines).toContain("Snapshot hotspot pressure dep dharma_swarm.models | inbound 159");
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass");
    expect(lines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot repo/control verify tsc=ok | py_compile_bridge=ok | bridg"))).toBe(true);
    expect(lines).toContain("Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main");
    expect(lines).toContain("Detached peers none");
    expect(lines).toContain("Members sab_canonical_repo_missing");
    const repoRiskPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"),
    );
    const repoControlIndex = lines.findIndex((line) =>
      line.startsWith("Repo/control fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync"),
    );
    const snapshotFocusIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"),
    );
    const snapshotRepoControlIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control fresh | task terminal-repo-pane"),
    );
    const controlPulseIndex = lines.findIndex((line) =>
      line.startsWith("Control pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T00:00:00Z"),
    );
    const snapshotTaskIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot task terminal-repo-pane | complete/pass | cycle 6"),
    );
    const snapshotRuntimeIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot runtime ") && line.includes("Sessions=18"),
    );
    const snapshotControlPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot control preview fresh | complete / pass | c…"),
    );
    const snapshotFreshnessIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot freshness fresh | task terminal-repo-pane | tracking origin/main in sync"),
    );
    const snapshotVerificationIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control verify tsc=ok | py_compile_bridge=ok | bridg"),
    );
    const snapshotTruthIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot truth tsc=ok | py_compile_bri"),
    );
    const controlTaskIndex = lines.findIndex((line) =>
      line.startsWith("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass"),
    );
    const controlVerifyIndex = lines.findIndex((line) =>
      line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"),
    );
    const pressurePreviewIndex = lines.findIndex((line) =>
      line.startsWith("Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ552"),
    );
    const hotspotPressureIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot hotspot pressure dep dharma_swarm.models | inbound 159"),
    );
    const runtimeStateIndex = lines.findIndex((line) =>
      line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7"),
    );
    const hotspotFocusIndex = lines.findIndex((line) => line === "Hotspot Focus");
    const repoRiskSectionIndex = lines.findIndex((line) => line === "Repo Risk");
    const controlPreviewIndex = lines.findIndex((line) => line === "Control Preview");
    expect(repoRiskPreviewIndex).toBeGreaterThan(-1);
    expect(snapshotFocusIndex).toBeGreaterThan(-1);
    expect(snapshotRepoControlIndex).toBeGreaterThan(-1);
    expect(repoRiskPreviewIndex).toBeGreaterThan(snapshotRepoControlIndex);
    expect(repoControlIndex).toBeGreaterThan(Math.max(repoRiskPreviewIndex, snapshotFocusIndex));
    expect(controlPulseIndex).toBe(repoControlIndex + 1);
    expect(runtimeStateIndex).toBe(controlPulseIndex + 1);
    expect(snapshotTaskIndex).toBe(runtimeStateIndex + 1);
    expect(snapshotRuntimeIndex).toBe(snapshotTaskIndex + 1);
    expect(snapshotControlPreviewIndex).toBe(snapshotRuntimeIndex + 1);
    expect(snapshotFreshnessIndex).toBe(snapshotControlPreviewIndex + 1);
    expect(snapshotVerificationIndex).toBe(snapshotFreshnessIndex + 1);
    expect(snapshotTruthIndex).toBe(snapshotVerificationIndex + 1);
    expect(controlTaskIndex).toBe(snapshotTruthIndex + 1);
    expect(controlVerifyIndex).toBe(controlTaskIndex + 1);
    expect(pressurePreviewIndex).toBe(controlVerifyIndex + 1);
    expect(hotspotPressureIndex).toBe(pressurePreviewIndex + 1);
    expect(hotspotFocusIndex).toBe(hotspotPressureIndex + 1);
    expect(repoRiskSectionIndex).toBeGreaterThan(hotspotFocusIndex);
    expect(controlPreviewIndex).toBeGreaterThan(repoRiskSectionIndex);
    expect(lines.some((line) => line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot task terminal-repo-pane | complete/pass | cycle 6"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot runtime ") && line.includes("Sessions=18"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot freshness fresh | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot truth tsc=ok | py_compile_bri"))).toBe(true);
    expect(lines).toContain("Topology signal high | dharma_swarm track main...origin/main");
    expect(lines.some((line) => line.startsWith("Lead peer dharma_swarm (canonical_core, main...origin/main"))).toBe(true);
    expect(lines).toContain("Pressure dharma_swarm Δ552 (510 modified, 42 untracked)");
    expect(lines.some((line) => line.startsWith("Runtime summary /Users/dhyana/.dharma/state/runtime.db | 18 sessions"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | complete/pass | tsc=ok | py_"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Changed n/a"))).toBe(true);
    expect(lines).toContain("Summary dep dharma_swarm.models | inbound 159");
    expect(lines).toContain("Severity high | warning sab_canonical_repo_missing");
    expect(lines).toContain("Lead change n/a | n/a");
    expect(lines).toContain("Lead file dgc_cli.py (6908 lines)");
    expect(lines).toContain("Lead dep dharma_swarm.models | inbound 159");
    expect(lines).toContain("Ontology");
    expect(lines).not.toContain("Models");
    expect(lines).not.toContain("Agents");
    expect(lines).not.toContain("Evolution");
  });

  test("keeps live control preview rows ahead of repo-risk preview boilerplate during active refreshes", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 0",
          "Branch status": "tracking origin/main ahead 2",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo risk preview":
            "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          Dirty: "97 staged, 505 unstaged, 54 untracked",
          "Dirty pressure": "high (656 local changes)",
          Staged: "97",
          Unstaged: "505",
          Untracked: "54",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning members": "sab_canonical_repo_missing",
          "Topology warning severity": "high",
          "Topology risk": "sab_canonical_repo_missing",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked)",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
          "Hotspot summary": "change terminal (281) | deps dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Promote live runtime preview ordering in the sidebar.",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const repoControlIndex = lines.findIndex((line) =>
      line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@804d5d1"),
    );
    const controlPulseIndex = lines.findIndex((line) =>
      line.startsWith("Control pulse stale | in_progress / fail | cycle 20 running"),
    );
    const controlVerifyIndex = lines.findIndex((line) =>
      line.startsWith("Control verify tsc=ok | cycle_acceptance=fail | next Promote"),
    );
    const snapshotRuntimeIndex = lines.findIndex(
      (line) => line.startsWith("Snapshot runtime ") && line.includes("Sessions=18 Runs=1"),
    );
    const snapshotRepoControlIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1"),
    );
    const snapshotVerifyIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Promote"),
    );
    const repoRiskPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Repo risk preview tracking origin/main ahead 2"),
    );

    expect(repoControlIndex).toBeGreaterThan(-1);
    expect(controlPulseIndex).toBe(repoControlIndex + 1);
    expect(snapshotRuntimeIndex).toBeGreaterThan(-1);
    expect(snapshotRepoControlIndex).toBe(snapshotRuntimeIndex + 1);
    expect(snapshotVerifyIndex).toBe(snapshotRepoControlIndex + 1);
    expect(controlVerifyIndex).toBeGreaterThan(controlPulseIndex);
    expect(repoRiskPreviewIndex).toBeGreaterThan(controlVerifyIndex);
    expect(repoRiskPreviewIndex).toBeGreaterThan(snapshotVerifyIndex);
  });

  test("keeps expanded repo snapshot correlation adjacent to runtime and verification during active refreshes", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 0",
          "Branch status": "tracking origin/main ahead 2",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo risk preview":
            "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          Dirty: "97 staged, 505 unstaged, 54 untracked",
          "Dirty pressure": "high (656 local changes)",
          Staged: "97",
          Unstaged: "505",
          Untracked: "54",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning members": "sab_canonical_repo_missing",
          "Topology warning severity": "high",
          "Topology risk": "sab_canonical_repo_missing",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked)",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
          "Hotspot summary": "change terminal (281) | deps dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Promote live runtime preview ordering in the sidebar.",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const snapshotRuntimeIndex = lines.findIndex(
      (line) => line.startsWith("Snapshot runtime ") && line.includes("Sessions=18 Runs=1"),
    );
    const snapshotRepoControlIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control stale | task terminal-repo-pane | branch main@804d5d1"),
    );
    const snapshotVerifyIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control verify tsc=ok | cycle_acceptance=fail | next Promote"),
    );

    expect(snapshotRuntimeIndex).toBeGreaterThan(-1);
    expect(snapshotRepoControlIndex).toBe(snapshotRuntimeIndex + 1);
    expect(snapshotVerifyIndex).toBe(snapshotRepoControlIndex + 1);
  });

  test("mirrors repo pane control-aware hotspot and repo-risk summaries in the visible context subset", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 0",
          "Branch status": "tracking origin/main ahead 2",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo risk preview":
            "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          Dirty: "97 staged, 505 unstaged, 54 untracked",
          "Dirty pressure": "high (656 local changes)",
          Staged: "97",
          Unstaged: "505",
          Untracked: "54",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning members": "sab_canonical_repo_missing",
          "Topology warning severity": "high",
          "Topology risk": "sab_canonical_repo_missing",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked)",
          "Changed hotspots": "terminal (281); dharma_swarm (93)",
          "Hotspot summary":
            "change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
          "Primary file hotspot": "dgc_cli.py (6908 lines)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Promote live runtime preview ordering in the sidebar.",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const hotspotFocusIndex = lines.findIndex((line) => line === "Hotspot Focus");
    const repoRiskSectionIndex = lines.findIndex((line) => line === "Repo Risk");

    expect(hotspotFocusIndex).toBeGreaterThan(-1);
    expect(repoRiskSectionIndex).toBeGreaterThan(hotspotFocusIndex);
    expect(lines.slice(hotspotFocusIndex + 1, repoRiskSectionIndex)).toEqual([
      "Summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx",
      "Control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=1 | Artifacts=7  ContextBundles=1",
      "Verify tsc=ok | cycle_acceptance=fail | next Promote live runtime preview ordering in the sidebar.",
      "Pressure change terminal (281) | dep dharma_swarm.models | inbound 159",
      "Lead dep dharma_swarm.models | inbound 159",
    ]);
    expect(lines.slice(repoRiskSectionIndex + 1, repoRiskSectionIndex + 7)).toEqual([
      "Repo topology sab_canonical_repo_missing; high (656 local changes)",
      "Control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=1 | Artifacts=7  ContextBundles=1",
      "Verify tsc=ok | cycle_acceptance=fail | next Promote live runtime preview ordering in the sidebar.",
      "Topology signal high | dharma_swarm track main...origin/main",
      "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
    ]);
  });

  test("keeps multi-warning topology members in visible repo-risk summaries during live control refreshes", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 1",
          "Branch status": "diverged from origin/main (+2/-1)",
          Ahead: "2",
          Behind: "1",
          "Repo risk": "topology peer_branch_diverged; sab_canonical_repo_missing; high (769 local changes)",
          "Repo risk preview":
            "diverged from origin/main (+2/-1) | peer_branch_diverged | dgc-core (operator_shell, detached, dirty True)",
          Dirty: "112 staged, 545 unstaged, 112 untracked",
          "Dirty pressure": "high (769 local changes)",
          Staged: "112",
          Unstaged: "545",
          Untracked: "112",
          "Topology status": "degraded (2 warnings, 2 peers)",
          "Topology warnings": "2 (peer_branch_diverged, sab_canonical_repo_missing)",
          "Topology warning members": "peer_branch_diverged, sab_canonical_repo_missing",
          "Topology warning severity": "high",
          "Topology risk": "peer_branch_diverged; sab_canonical_repo_missing",
          "Primary warning": "peer_branch_diverged",
          "Primary peer drift": "dharma_swarm drift main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ657 (545 modified, 112 untracked); dgc-core Δ1 (1 modified, 0 untracked)",
          "Topology peers":
            "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True)",
          "Topology peer count": "2",
          "Branch divergence": "local +2/-1",
          "Detached peers": "dgc-core detached",
          "Changed hotspots": "terminal (281)",
          "Hotspot summary":
            "change terminal (281) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/RepoPane.tsx",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/RepoPane.tsx",
          "Primary file hotspot": "dgc_cli.py (6908 lines)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "2 done, 1 pending of 3",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Promote multi-warning topology members in visible repo summaries.",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const repoRiskSectionIndex = lines.findIndex((line) => line === "Repo Risk");

    expect(repoRiskSectionIndex).toBeGreaterThan(-1);
    expect(lines).toContain("Snapshot warning members peer_branch_diverged, sab_canonical_repo_missing");
    expect(lines.slice(repoRiskSectionIndex + 1, repoRiskSectionIndex + 8)).toContain(
      "Warning members peer_branch_diverged, sab_canonical_repo_missing",
    );
  });

  test("mirrors repo pane control-aware hotspot and repo-risk summaries in expanded context mode", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          Sync: "origin/main | ahead 2 | behind 0",
          "Branch status": "tracking origin/main ahead 2",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo risk preview":
            "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          Dirty: "97 staged, 505 unstaged, 54 untracked",
          "Dirty pressure": "high (656 local changes)",
          Staged: "97",
          Unstaged: "505",
          Untracked: "54",
          "Topology status": "degraded (1 warning, 1 peer)",
          "Topology warnings": "1 (sab_canonical_repo_missing)",
          "Topology warning members": "sab_canonical_repo_missing",
          "Topology warning severity": "high",
          "Topology risk": "sab_canonical_repo_missing",
          "Primary warning": "sab_canonical_repo_missing",
          "Primary peer drift": "dharma_swarm track main...origin/main",
          "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Topology pressure": "dharma_swarm Δ559 (505 modified, 54 untracked)",
          "Changed hotspots": "terminal (281); dharma_swarm (93)",
          "Hotspot summary":
            "change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
          "Primary file hotspot": "dgc_cli.py (6908 lines)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Promote live runtime preview ordering in the sidebar.",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const hotspotSummaryIndex = lines.findIndex((line) =>
      line ===
      "Summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx",
    );
    const repoRiskSectionIndex = lines.findIndex((line) => line === "Repo Risk");

    expect(hotspotSummaryIndex).toBeGreaterThan(-1);
    expect(repoRiskSectionIndex).toBeGreaterThan(-1);
    expect(lines.slice(hotspotSummaryIndex, hotspotSummaryIndex + 6)).toEqual([
      "Summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx",
      "Control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=1 | Artifacts=7  ContextBundles=1",
      "Verify tsc=ok | cycle_acceptance=fail | next Promote live runtime preview ordering in the sidebar.",
      "Pressure change terminal (281) | dep dharma_swarm.models | inbound 159",
      "Lead dep dharma_swarm.models | inbound 159",
    ]);
    expect(lines.slice(repoRiskSectionIndex + 1, repoRiskSectionIndex + 7)).toEqual([
      "Repo topology sab_canonical_repo_missing; high (656 local changes)",
      "Control stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence local +2/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); dharma_swarm (93) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/components/Sidebar.tsx | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
      "Runtime /Users/dhyana/.dharma/state/runtime.db | Sessions=18  Runs=1 | Artifacts=7  ContextBundles=1",
      "Verify tsc=ok | cycle_acceptance=fail | next Promote live runtime preview ordering in the sidebar.",
      "Topology signal high | dharma_swarm track main...origin/main",
      "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
    ]);
  });

  test("promotes stable repo snapshot signal ahead of repo-risk boilerplate in the visible context subset", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 0 pending of 1",
          "Result status": "complete",
          Acceptance: "pass",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Next task": "Align stable sidebar snapshot order with repo rail.",
          "Verification bundle": "tsc=ok | cycle_acceptance=ok",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
          "Control pulse preview":
            "complete / pass | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=ok",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-03",
          "Concept count": "321",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    const snapshotDirtyIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot dirty high (656 local changes) | staged 97"),
    );
    const snapshotHotspotSummaryIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot hotspot summary change terminal (281); dharma_swarm (93)"),
    );
    const snapshotFocusIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"),
    );
    const snapshotRepoControlIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo/control ") && line.includes("task terminal-repo-pane"),
    );
    const snapshotRepoRiskIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot repo risk tracking origin/main ahead 2"),
    );
    const snapshotTopologySignalIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot topology signal stable | dharma_swarm track main...origin/main"),
    );
    const snapshotTopologyIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot topology stable (0 warnings, 1 p") && line.includes("| warnings 0"),
    );
    const snapshotWarningMembersIndex = lines.findIndex((line) => line === "Snapshot warning members none");
    const snapshotWarningsIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot warnings none | severity none"),
    );

    expect(snapshotDirtyIndex).toBeGreaterThan(-1);
    expect(snapshotTopologySignalIndex).toBe(snapshotDirtyIndex + 1);
    expect(snapshotHotspotSummaryIndex).toBe(snapshotTopologySignalIndex + 1);
    expect(snapshotFocusIndex).toBe(snapshotHotspotSummaryIndex + 1);
    expect(snapshotRepoControlIndex).toBe(snapshotFocusIndex + 1);
    expect(snapshotRepoRiskIndex).toBe(snapshotRepoControlIndex + 1);
    expect(snapshotTopologyIndex).toBeGreaterThan(snapshotRepoRiskIndex);
    expect(snapshotWarningMembersIndex).toBeGreaterThan(snapshotTopologyIndex);
    expect(snapshotWarningsIndex).toBeGreaterThan(snapshotWarningMembersIndex);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot pressure change terminal (281) | dep dharma_swarm.models"))).toBe(true);
  });

  test("derives missing topology rows in visible context from partial live repo previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "95210b1",
          "Branch status": "tracking origin/main in sync",
          Sync: "origin/main | ahead 0 | behind 0",
          Ahead: "0",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
          "Repo risk preview":
            "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
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
          "Primary changed hotspot": "terminal (274)",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-01",
          "Concept count": "321",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "4 done, 0 pending of 4",
          "Result status": "complete",
          Acceptance: "pass",
          "Last result": "complete / pass",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 7 running",
          "Loop decision": "continue required",
          "Verification bundle": "tsc=ok | cycle_acceptance=ok",
          "Runtime freshness": "cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          "Control pulse preview": "complete / pass | cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          Updated: "2026-04-02T00:00:00Z",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-02T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing | drift"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Topology signal high | dharma_swarm track main...origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)"))).toBe(true);
    expect(lines).toContain("Pressure preview 1 (sab_canonical_repo_missing) | dharma_swarm Δ563 (517 modified, 46 untracked)");
    expect(lines.some((line) => line.startsWith("Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pressure dharma_swarm Δ563 (517 modified, 46 untracked)"))).toBe(true);
  });

  test("derives missing hotspot lead rows in visible context from partial live repo previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
          "Hotspot summary":
            "change terminal (274) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "4 done, 0 pending of 4",
          "Result status": "complete",
          Acceptance: "pass",
          "Last result": "complete / pass",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 7 running",
          "Loop decision": "continue required",
          "Verification bundle": "tsc=ok | cycle_acceptance=ok",
          "Runtime freshness": "cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          "Control pulse preview": "complete / pass | cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          Updated: "2026-04-02T00:00:00Z",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-02T04:00:00Z"),
    );

    expect(lines).toContain("Snapshot hotspots change terminal (274) | path terminal/src/component…");
    expect(lines).toContain("Snapshot hotspot summary change terminal (274) | path terminal/src/components/Si…");
    expect(lines.some((line) => line.startsWith("Snapshot hotspot pressure change terminal (274) | dep dharma_swarm.models |"))).toBe(true);
    expect(lines).toContain("Lead change terminal (274) | terminal/src/components/Sid…");
    expect(lines).toContain("Lead dep dharma_swarm.models | inbound 159");
  });

  test("derives visible snapshot pressure and hotspot summary from partial live repo previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
          "Primary changed hotspot": "terminal (274)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
          "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "4 done, 0 pending of 4",
          "Result status": "complete",
          Acceptance: "pass",
          "Last result": "complete / pass",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 7 running",
          "Loop decision": "continue required",
          "Verification bundle": "tsc=ok | cycle_acceptance=ok",
          "Runtime freshness": "cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          "Control pulse preview": "complete / pass | cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          Updated: "2026-04-02T00:00:00Z",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-02T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology pressure 1 (sab_canonical_repo_missing) | dharma_swarm Δ563"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (274) | path terminal/src/components/Si"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot summary topology sab_canonical_repo"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"))).toBe(true);
  });

  test("derives visible topology warning and peer rows from repo risk preview when topology preview is absent", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "95210b1",
          "Branch status": "tracking origin/main ahead 2",
          Sync: "origin/main | ahead 2 | behind 0",
          Ahead: "2",
          Behind: "0",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo risk preview":
            "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
          "Dirty pressure": "high (656 local changes)",
          "Primary changed hotspot": "terminal (281)",
          "Primary changed path": "terminal/src/components/Sidebar.tsx",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Result status": "complete",
          Acceptance: "pass",
          "Loop state": "cycle 7 running",
          "Loop decision": "continue required",
          "Verification bundle": "tsc=ok | cycle_acceptance=ok",
          "Runtime freshness": "cycle 7 running | updated 2026-04-02T00:00:00Z | verify tsc=ok | cycle_acceptance=ok",
          Updated: "2026-04-02T00:00:00Z",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-02T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(lines.some((line) => line.startsWith("Lead peer dharma_swarm (canonical_core, main...origin/main"))).toBe(true);
    expect(lines).toContain("Topology signal high | dharma_swarm track main...origin/main");
  });

  test("derives visible branch divergence and detached peer rows from compact repo/control preview alone", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
          "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | warn peer_branch_diverged | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | peer dharma_swarm drift main...origin/main | detached dgc-core detached | hotspot change terminal (281) | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {},
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines).toContain("Snapshot branch divergence local +2/-1");
    expect(lines).toContain("Snapshot warnings peer_branch_diverged | severity high");
    expect(lines).toContain("Snapshot detached peers dgc-core detached");
    expect(lines).toContain("Risk topology peer_branch_diverged; high (656 local changes)");
    expect(lines).toContain("Branch divergence local +2/-1");
    expect(lines).toContain("Topology signal high | dharma_swarm drift main...origin/main");
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 2"))).toBe(true);
    expect(lines).toContain("Warnings 1 (peer_branch_diverged)");
    expect(lines).toContain("Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(lines).toContain("Detached peers dgc-core detached");
  });

  test("derives visible branch and head rows from compact repo/control preview alone", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | hotspot change terminal (281)",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {},
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +2/-0 | origin/main | ahead 2"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@804d5d1"))).toBe(true);
  });

  test("derives visible ahead and behind counts from human branch-status phrasing inside compact repo/control previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | ahead of origin/main by 2 | dirty high (7 local changes) | hotspot change terminal (4)",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {},
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | ahead of origin/main by"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +2/-0 | origin/main | ahead 2"))).toBe(true);
    expect(lines).toContain("Snapshot repo risk high (7 local changes)");
    expect(lines).toContain("Repo risk preview high (7 local changes)");
    expect(lines).toContain("Branch divergence local +2/-0");
  });

  test("derives visible ahead and behind counts from git bracket branch-status phrasing inside compact repo/control previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | main...origin/main [ahead 2, behind 1] | dirty high (7 local changes) | hotspot change terminal (4)",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {},
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | main...origin/main [ahe"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +2/-1 | origin/main | ahead 2"))).toBe(true);
    expect(lines).toContain("Branch divergence local +2/-1");
  });

  test("derives visible branch sync counts from git-status previews without a +N/-M token", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "main",
          Head: "804d5d1",
          "Branch sync preview": "main...origin/main [ahead 2]",
          "Repo risk": "topology sab_canonical_repo_missing; high (7 local changes)",
          "Dirty pressure": "high (7 local changes)",
          "Hotspot summary": "change terminal (4)",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {},
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | main...origin/main [ahe"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +2/-0 | origin/main | ahead 2"))).toBe(true);
  });

  test("uses numeric compact peer counts from repo/control preview in visible topology rows", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged | peers 2 | divergence local +2/-1 | hotspot change terminal (281)",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T04:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 2"))).toBe(true);
  });

  test("derives visible dirty and hotspot rows from compact repo/control preview alone", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Dirty pressure": "high (656 local changes)",
          "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 97 | unstaged 505 | untracked 54 | warn 1 (sab_canonical_repo_missing) | hotspot terminal (281) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159 | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot dirty high (656 local changes) | staged 97 | unstaged 505"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (281) | path terminal/src/components/Si"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Summary change terminal (281) | path terminal/src/components/Si"))).toBe(true);
    expect(lines).toContain("Lead dep dharma_swarm.models | inbound 159");
  });

  test("normalizes compact hotspot labels before visible context rows add change prefixes", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Dirty pressure": "high (7 local changes)",
          "Repo risk": "topology peer_branch_diverged; high (7 local changes)",
          "Repo/control preview":
            "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty staged 1 | unstaged 4 | untracked 2 | hotspot change terminal (4) | path terminal/src/components/Sidebar.tsx | dep dharma_swarm.models | inbound 159 | cycle 20 running | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (4) | path terminal/src/components/Side"))).toBe(true);
    expect(lines.some((line) => line.includes("change change terminal (4)"))).toBe(false);
  });

  test("surfaces the warning-bearing peer in visible context when topology warnings point away from the first peer", () => {
    const preview = workspaceSnapshotToPreview(`# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 1 | unstaged 2 | untracked 3
Git hotspots: terminal (4)
Git changed paths: terminal/src/components/Sidebar.tsx
Git sync: origin/main | ahead 2 | behind 1

## Topology
- warning: peer_branch_diverged
- warning: detached_peer
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 3 | untracked 2
- dgc-core | role operator_shell | branch detached | dirty True | modified 1 | untracked 0`);
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview,
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology preview peer_branch_diverged | dgc-core"))).toBe(
      true,
    );
    expect(lines).toContain("Snapshot detached peers dgc-core detached");
    expect(lines).toContain("Lead peer dgc-core (operator_shell, detached, dirty True)");
    expect(lines).toContain("Topology signal high | dgc-core detached");
  });

  test("derives dirty counts in visible context from compact repo truth previews when expanded git rows are absent", () => {
    const preview = {
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
    };

    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview,
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Dirty staged 97 | unstaged 505 | unt"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty high (656 local changes) | staged 97 | unstaged 505 | unt"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot truth branch main@804d5d1 | dirty staged 97 | unstaged 505 |"))).toBe(true);
  });

  test("derives topology warnings and hotspot rows in visible context from compact repo truth previews when expanded rows are absent", () => {
    const preview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Branch status": "tracking origin/main ahead 2",
      Sync: "origin/main | ahead 2 | behind 0",
      Ahead: "2",
      Behind: "0",
      "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
      "Dirty pressure": "high (656 local changes)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    };

    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview,
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Dirty staged 97 | unstaged 505 | unt"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning) | warnings 1"))).toBe(true);
    expect(lines).toContain("Snapshot warning members sab_canonical_repo_missing");
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspots change terminal (281) | path terminal/src"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (281) | path terminal/src"))).toBe(true);
    expect(lines).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(lines).toContain("Risk topology sab_canonical_repo_missing; high (656 local changes)");
    expect(lines.some((line) => line.startsWith("Summary change terminal (281) | path terminal/src/components/Re"))).toBe(true);
    expect(lines).toContain("Lead dep dharma_swarm.models | inbound 159");
  });

  test("derives branch and head labels in visible context from compact repo truth previews when explicit git rows are absent", () => {
    const preview = {
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
    };

    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview,
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Git main@804d5d1 | high (656 local"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot truth branch main@804d5d1 | dirty staged 97 | unstaged 505 |"))).toBe(true);
  });

  test("derives branch sync details in visible context from compact branch sync previews when expanded git sync rows are absent", () => {
    const preview = {
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
    };

    const lines = buildVisibleContextSidebarLines(
      [
        {
          id: "repo",
          title: "Repo",
          kind: "repo",
          lines: [],
          preview,
        },
      ],
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot sync origin/main | +2/-0 | origin/main | ahead 2"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch sync tracking origin/main ahead 2 | +2/-0 | topology sab_"))).toBe(true);
    expect(lines).toContain("Snapshot branch divergence local +2/-0");
  });

  test("derives control outcome from compact pulse previews in visible context when explicit outcome rows are absent", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 0 pending of 1",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=0",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 14 running",
          "Loop decision": "continue required",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview": "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines).toContain("Snapshot task terminal-repo-pane | in_progress/fail | cycle 14 running | continue required");
    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | in_progress/fail | tsc=ok"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pulse stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z"))).toBe(
      true,
    );
  });

  test("derives visible repo/control freshness from runtime freshness when updated is absent", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Runtime freshness":
            "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Loop decision": "continue required",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@804d5d1"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo warn sab_canonical_repo_missing | severity high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo hotspot change terminal (281)"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot control preview stale | in_progress / fai"))).toBe(true);
  });

  test("derives control preview runtime and verification rows from partial live control snapshots", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
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
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Run state": "2 runs | 1 active runs",
          "Context state": "7 artifacts | 2 promoted facts | 3 context bundles | 4 operator actions",
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 1 pending of 2",
          "Runtime freshness":
            "cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Loop decision": "continue required",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Task terminal-repo-pane | in_progress/fail | tsc=ok | cycle_acceptance="))).toBe(true);
    expect(lines.some((line) => line.startsWith("Pulse stale | in_progress / fail | cycle 14 running | updated 2026-04-03T02:00:00Z"))).toBe(true);
    expect(lines).toContain("Snapshot task terminal-repo-pane | in_progress/fail");
    expect(lines.some((line) => line.startsWith("Snapshot runtime /Users/dhyana/.dharma/s") && line.includes("Sessions=18 Runs=2") && line.includes("Artifacts=7 ContextBund"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot loop stale | cycle 14 running | continue required"))).toBe(true);
    expect(lines).toContain("Snapshot verify tsc=ok | cycle_acceptance=fail");
    expect(lines.some((line) => line.startsWith("Snapshot truth tsc=ok | cycle_acceptan") && line.includes("cycle 14 running | next n/a"))).toBe(true);
    expect(lines).toContain("Outcome in_progress | accept fail");
    expect(lines.some((line) => line.startsWith("Activity Sessions=18 Runs=2 | Artifacts=7 ContextBund"))).toBe(true);
    expect(lines).toContain("Updated 2026-04-03T02:00:00Z");
    expect(lines).toContain("Verify tsc=ok | cycle_acceptance=fail");
    expect(lines).toContain("Bundle tsc=ok | cycle_acceptance=fail");
  });

  test("synthesizes numeric peer counts into repo/control preview during partial repo refreshes", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          Branch: "m",
          Head: "1",
          "Branch status": "sync",
          Sync: "o/main | ahead 2 | behind 0",
          Ahead: "2",
          Behind: "0",
          "Topology warnings": "1 (w)",
          "Primary warning": "w",
          "Topology peer count": "2",
          "Branch divergence": "+2/-1",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Runtime freshness": "cycle 20 running",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );
    const expandedLines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot repo/control "))).toBe(true);
    const repoControlRow = expandedLines.find((line) => line.startsWith("Repo/control "));

    expect(repoControlRow).toContain("warn 1 (w)");
    expect(repoControlRow).toContain("peers 2");
    expect(repoControlRow).toContain("divergence +2/-1");
  });

  test("synthesizes topology counts and runtime summary in visible context from compact repo/control previews", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo/control preview":
            "fresh | task terminal-repo-pane | branch feature/repo-pane@804d5d1 | tracking origin/main ahead 2 | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | dirty staged 112 | unstaged 545 | untracked 112 | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=2 ActiveRuns=1 | artifacts Artifacts=7 ContextBundles=1 | verify tsc=ok",
        },
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
        },
      },
      {
        id: "ontology",
        title: "Ontology",
        kind: "ontology",
        lines: [],
        preview: {
          Version: "2026-04-01",
          "Concept count": "321",
        },
      },
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      tabs[1].preview,
    );

    expect(lines).toContain("Count 2 peers | warnings 2 (peer_branch_diverged; sab_canonical_repo_missing)");
    expect(
      lines.some(
        (line) =>
          line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=2 ActiveRuns=1 | Artifacts=7"),
      ),
    ).toBe(true);
  });

  test("counts semicolon-delimited topology warnings in the visible context sidebar", () => {
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: {
          "Repo root": "/Users/dhyana/dharma_swarm",
          "Repo truth preview":
            "branch main@804d5d1 | dirty staged 112 | unstaged 545 | untracked 112 | warn peer_branch_diverged; sab_canonical_repo_missing | hotspot change terminal (281)",
          "Branch status": "tracking origin/main [ahead 2, behind 1]",
        },
      },
      {id: "control", title: "Control", kind: "control", lines: [], preview: {"Active task": "n/a"}},
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      {id: "models", title: "Models", kind: "models", lines: [], preview: {Active: "Codex 5.4", Strategy: "responsive", Route: "codex:gpt-5.4", Fallbacks: "1"}},
      {id: "agents", title: "Agents", kind: "agents", lines: [], preview: {"Active runs": "0", "Recent actions": "0", Routes: "0", "Primary route": "n/a"}},
      {id: "evolution", title: "Evolution", kind: "evolution", lines: [], preview: {Domains: "1", "Primary domain": "code"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
    );

    expect(
      lines.some(
        (line) =>
          line.startsWith("Snapshot topology degraded (2 warnings) | warnings 2 (peer_branch_di"),
      ),
    ).toBe(true);
    expect(lines).toContain("Snapshot warning members peer_branch_diverged, sab_canonical_repo_missing");
    expect(lines).toContain("Warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)");
    expect(lines).toContain("Members peer_branch_diverged, sab_canonical_repo_missing");
  });

  test("keeps multi-warning members in visible context rows from persisted repo/control previews", () => {
    const tabs: TabSpec[] = [
      {id: "repo", title: "Repo", kind: "repo", lines: [], preview: {"Repo root": "/Users/dhyana/dharma_swarm"}},
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "2 done, 1 pending of 3",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Repo/control preview":
            "fresh | task terminal-repo-pane | progress 2 done, 1 pending of 3 | decision continue required | branch main@804d5d1 | diverged from origin/main (+2/-1) | warn peer_branch_diverged; sab_canonical_repo_missing | peers dharma_swarm (canonical_core, main...origin/main [ahead 2, behind 1], dirty true); dgc-core (operator_shell, detached, dirty true) | drift dharma_swarm drift main...origin/main [ahead 2, behind 1] | markers dharma_swarm drift main...origin/main [ahead 2, behind 1]; dgc-core detached | divergence local +2/-1 | peer dharma_swarm (canonical_core, main...origin/main [ahead 2, behind 1], dirty true) | detached dgc-core detached | dirty staged 112 | unstaged 557 | untracked 136 | hotspot change terminal (77) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 161 | updated 2026-04-04T01:00:09.134796+00:00 | verify tsc=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=20 Runs=0 | artifacts Artifacts=0 ContextBundles=0 | next Preserve multi-warning members in persisted previews.",
          "Runtime freshness": "cycle 1 running_cycle | updated 2026-04-04T01:00:09.134796+00:00 | verify tsc=ok",
          "Control pulse preview": "in_progress / fail | cycle 1 running_cycle | updated 2026-04-04T01:00:09.134796+00:00 | verify tsc=ok",
          "Verification bundle": "tsc=ok",
        },
      },
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      {id: "models", title: "Models", kind: "models", lines: [], preview: {Active: "Codex 5.4", Strategy: "responsive", Route: "codex:gpt-5.4", Fallbacks: "1"}},
      {id: "agents", title: "Agents", kind: "agents", lines: [], preview: {"Active runs": "0", "Recent actions": "0", Routes: "0", "Primary route": "n/a"}},
      {id: "evolution", title: "Evolution", kind: "evolution", lines: [], preview: {Domains: "1", "Primary domain": "code"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      undefined,
      undefined,
      new Date("2026-04-04T12:00:00Z"),
    );

    expect(lines).toContain("Snapshot warning members peer_branch_diverged, sab_canonical_repo_missing");
    expect(lines).toContain("Warnings 2 (peer_branch_diverged, sab_canonical_repo_missing)");
    expect(lines).toContain("Warning members peer_branch_diverged, sab_canonical_repo_missing");
  });

  test("hydrates repo preview rows from control-carried repo/control previews when repo preview is absent", () => {
    const tabs: TabSpec[] = [
      {id: "repo", title: "Repo", kind: "repo", lines: [], preview: {}},
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          Authority: "placeholder | bridge booting | awaiting authoritative control refresh",
          "Repo/control preview":
            "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@804d5d1 | tracking origin/main ahead 2 | warn sab_canonical_repo_missing | dirty staged 112 | unstaged 545 | untracked 112 | hotspot terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 4 running | updated 2026-04-03T01:15:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | artifacts Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3 | next Hydrate control preview from runtime state.",
        },
      },
      {id: "ontology", title: "Ontology", kind: "ontology", lines: [], preview: {Version: "2026-04-01", "Concept count": "321"}},
      {id: "models", title: "Models", kind: "models", lines: [], preview: {Active: "Codex 5.4", Strategy: "responsive", Route: "codex:gpt-5.4", Fallbacks: "1"}},
      {id: "agents", title: "Agents", kind: "agents", lines: [], preview: {"Active runs": "0", "Recent actions": "0", Routes: "0", "Primary route": "n/a"}},
      {id: "evolution", title: "Evolution", kind: "evolution", lines: [], preview: {Domains: "1", "Primary domain": "code"}},
    ];

    const lines = buildVisibleContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "booting",
      undefined,
      tabs[1].preview,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty n/a | staged 112 | unstaged 545 | un"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning) | warnings 1"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (281) | path terminal/src/components/Re"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | progress 3 done"))).toBe(true);
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
  });

  test("keeps authoritative typed topology preview text in context sidebar repo summaries", () => {
    const repoPayload: WorkspaceSnapshotPayload = {
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
        changed_paths: ["terminal/src/components/Sidebar.tsx"],
        sync: {summary: "origin/main | ahead 2 | behind 1", status: "tracking", upstream: "origin/main", ahead: 2, behind: 1},
      },
      topology: {
        warnings: ["peer_branch_diverged"],
        preview: "authoritative sidebar topology preview",
        pressure_preview: "authoritative sidebar topology pressure",
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
    const tabs: TabSpec[] = [
      {
        id: "repo",
        title: "Repo",
        kind: "repo",
        lines: [],
        preview: workspacePayloadToPreview(repoPayload),
      },
      {
        id: "control",
        title: "Control",
        kind: "control",
        lines: [],
        preview: {
          "Active task": "terminal-repo-pane",
          "Task progress": "1 done, 0 pending of 1",
          "Result status": "in_progress",
          Acceptance: "fail",
          "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
          "Runtime activity": "Sessions=18  Runs=1",
          "Artifact state": "Artifacts=7  ContextBundles=1",
          "Loop state": "cycle 20 running",
          "Loop decision": "continue required",
          Updated: "2026-04-03T02:16:08Z",
          "Verification bundle": "tsc=ok | cycle_acceptance=fail",
          "Runtime freshness": "cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
          "Control pulse preview":
            "in_progress / fail | cycle 20 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
        },
      },
    ];

    const lines = buildContextSidebarLines(
      tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      tabs[0].preview,
      undefined,
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(lines).toContain(
      "Snapshot topology preview authoritative sidebar topology preview",
    );
    expect(lines).toContain(
      "Pressure preview authoritative sidebar topology pressure",
    );
  });
});
