import {describe, expect, test} from "bun:test";

import {buildContextSidebarLines, buildVisibleContextSidebarLines} from "../src/components/Sidebar";
import type {TabSpec} from "../src/types";

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
      undefined,
      undefined,
      new Date("2026-04-01T04:00:00Z"),
    );

    expect(lines).toContain("Repo | bridge connected");
    expect(lines).toContain("Model codex gpt-5.4");
    expect(lines).toContain("Repo Preview");
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (552 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Dirty staged 0 | unstaged 510 | untr"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty high (552 local changes) | staged 0 | un"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing |"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot topology preview sab_canonical_repo_missing | dharma"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot pressure 1 warning | dharma_swarm Δ552"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspots change terminal (274) | path terminal/src"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (274); .dharma"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot summary topology sab_canonical_repo"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | tracking origin/main in sync |"))).toBe(true);
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
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Activity Sessions=18"))).toBe(true);
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass");
    expect(lines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    expect(lines).toContain("Repo Risk");
    expect(lines.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Dirty high (552 local changes) | staged 0 | unstaged 510"))).toBe(true);
    expect(lines).toContain("State 0 staged, 510 unstaged, 42 untracked");
    expect(lines.some((line) => line.startsWith("Topo degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Topology signal high | dharma_swarm track main...origin/main");
    expect(lines.some((line) => line.startsWith("Topology preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Risk preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines).toContain("Warnings 1 (sab_canonical_repo_missing)");
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
    expect(lines).toHaveLength(101);
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
    expect(lines.some((line) => line.startsWith("Repo/control stale | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
    expect(lines).toContain("Repo Risk");
    expect(lines.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (563 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert n/a | warning sab_canonical_repo_missing | drift"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot freshness stale | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
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

    expect(lines).toHaveLength(47);
    expect(lines).toContain("Repo Preview");
    expect(lines).toContain("Hotspot Focus");
    expect(lines).toContain("Repo Risk");
    expect(lines).toContain("Control Preview");
    expect(lines.some((line) => line.startsWith("Git main@95210b1 | high (552 local changes) | sync tracking"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Dirty staged 0 | unstaged 510 | untr"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot dirty high (552 local changes) | staged 0"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot warnings sab_canonical_repo_missing | severity hi"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot alert high | warning sab_canonical_repo_missing |"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot topology preview sab_canonical_repo_missing | dharma_swarm"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot pressure "))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspots dep dharma_swarm.models | inbound 159"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot hotspot summary dep dharma_swarm.models | inbound 159"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot summary topology sab_canonical_repo"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | tracking origin/main in sync |"))).toBe(true);
    expect(lines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass");
    expect(lines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"))).toBe(true);
    const repoRiskPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"),
    );
    const repoControlIndex = lines.findIndex((line) =>
      line.startsWith("Repo/control fresh | task terminal-repo-pane | tracking origin/main in sync"),
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
    const snapshotFreshnessIndex = lines.findIndex((line) =>
      line.startsWith("Snapshot freshness fresh | task terminal-repo-pane | tracking origin/main in sync"),
    );
    const controlTaskIndex = lines.findIndex((line) =>
      line.startsWith("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/pass"),
    );
    const controlVerifyIndex = lines.findIndex((line) =>
      line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok"),
    );
    const runtimeStateIndex = lines.findIndex((line) =>
      line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7"),
    );
    const hotspotFocusIndex = lines.findIndex((line) => line === "Hotspot Focus");
    const repoRiskSectionIndex = lines.findIndex((line) => line === "Repo Risk");
    const controlPreviewIndex = lines.findIndex((line) => line === "Control Preview");
    expect(repoRiskPreviewIndex).toBeGreaterThan(-1);
    expect(repoControlIndex).toBe(repoRiskPreviewIndex + 1);
    expect(controlPulseIndex).toBe(repoControlIndex + 1);
    expect(runtimeStateIndex).toBe(controlPulseIndex + 1);
    expect(snapshotTaskIndex).toBe(runtimeStateIndex + 1);
    expect(snapshotRuntimeIndex).toBe(snapshotTaskIndex + 1);
    expect(snapshotFreshnessIndex).toBe(snapshotRuntimeIndex + 1);
    expect(controlTaskIndex).toBe(snapshotFreshnessIndex + 1);
    expect(controlVerifyIndex).toBe(controlTaskIndex + 1);
    expect(hotspotFocusIndex).toBe(controlVerifyIndex + 1);
    expect(repoRiskSectionIndex).toBeGreaterThan(hotspotFocusIndex);
    expect(controlPreviewIndex).toBeGreaterThan(repoRiskSectionIndex);
    expect(lines.some((line) => line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Repo/control fresh | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Control pulse fresh | complete / pass | cycle 6 running | updated 2026-04-01T"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=0 | Artifacts=7"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot task terminal-repo-pane | complete/pass | cycle 6"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot runtime ") && line.includes("Sessions=18"))).toBe(true);
    expect(lines.some((line) => line.startsWith("Snapshot freshness fresh | task terminal-repo-pane | tracking origin/main in sync"))).toBe(true);
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
});
