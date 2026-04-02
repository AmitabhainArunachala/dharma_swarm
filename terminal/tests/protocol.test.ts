import {describe, expect, test} from "bun:test";

import {
  approvalPaneToLines,
  approvalPaneToPreview,
  agentRoutesToLines,
  agentRoutesPayloadFromEvent,
  agentRoutesToPreview,
  commandGraphToLines,
  commandGraphToPreview,
  resolveCommandTargetPane,
  commandTargetTab,
  evolutionSurfaceToLines,
  evolutionSurfaceToPreview,
  eventToTabPatch,
  inferSlashCommand,
  isSlashCommandPrompt,
  modelPolicyToLines,
  modelPolicyToPreview,
  normalizeCommandName,
  operatorSnapshotToLines,
  operatorSnapshotToPreview,
  permissionDecisionFromEvent,
  permissionHistoryFromEvent,
  permissionResolutionFromEvent,
  resolveEventCommand,
  routingDecisionPayloadFromEvent,
  runtimeSnapshotToLines,
  runtimePayloadToPreview,
  runtimeSnapshotPayloadFromEvent,
  runtimePreviewToLines,
  runtimeSnapshotToPreview,
  sessionCatalogFromEvent,
  sessionPaneToLines,
  sessionPaneToPreview,
  sessionCatalogToLines,
  sessionCatalogToPreview,
  sessionDetailFromEvent,
  sessionDetailToLines,
  sessionDetailToPreview,
  sessionBootstrapToLines,
  sessionBootstrapToPreview,
  workspacePreviewToLines,
  workspacePayloadToPreview,
  workspaceSnapshotPayloadFromEvent,
  workspaceSnapshotToLines,
  workspaceSnapshotToPreview,
} from "../src/protocol";

describe("normalizeCommandName", () => {
  test("strips the slash prefix and trailing arguments", () => {
    expect(normalizeCommandName("/swarm status")).toBe("swarm");
    expect(normalizeCommandName("git")).toBe("git");
  });
});

describe("typed session helpers", () => {
  test("normalizes typed catalog payloads", () => {
    const catalog = sessionCatalogFromEvent({
      type: "session.catalog.result",
      payload: {
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess-1",
              provider_id: "codex",
              model_id: "gpt-5.4",
              cwd: "/repo",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T01:00:00Z",
              status: "completed",
              summary: "overnight build",
              metadata: {total_turns: 1},
            },
            replay_ok: true,
            replay_issues: [],
            total_turns: 1,
            total_cost_usd: 1.5,
          },
        ],
      },
    });

    expect(catalog?.count).toBe(1);
    expect(catalog?.sessions[0]?.session.session_id).toBe("sess-1");
    expect(catalog?.sessions[0]?.total_cost_usd).toBe(1.5);
  });

  test("normalizes typed detail payloads", () => {
    const detail = sessionDetailFromEvent({
      type: "session.detail.result",
      payload: {
        session: {
          session_id: "sess-1",
          provider_id: "codex",
          model_id: "gpt-5.4",
          cwd: "/repo",
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T01:00:00Z",
          status: "completed",
          summary: "overnight build",
        },
        replay_ok: false,
        replay_issues: ["missing session_end"],
        compaction_preview: {
          event_count: 6,
          by_type: {text_delta: 1, tool_result: 1},
          compactable_ratio: 0.167,
          protected_event_types: ["session_start", "session_end"],
          recent_event_types: ["session_start", "text_delta", "session_end"],
        },
        recent_events: [
          {
            event_id: "evt-1",
            event_type: "tool_result",
            source: "provider",
            audience: "all",
            transport: "local",
            session_id: "sess-1",
            created_at: "2026-04-01T00:30:00Z",
            payload: {tool_name: "Read", content: "ok"},
          },
        ],
      },
    });

    expect(detail?.session.session_id).toBe("sess-1");
    expect(detail?.replay_ok).toBe(false);
    expect(detail?.compaction_preview.event_count).toBe(6);
    expect(detail?.recent_events[0]?.event_type).toBe("tool_result");
  });

  test("renders the sessions pane from typed state", () => {
    const sessionPane = {
      catalog: {
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess-1",
              provider_id: "codex",
              model_id: "gpt-5.4",
              cwd: "/repo",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T01:00:00Z",
              status: "completed",
              summary: "overnight build",
              metadata: {},
            },
            replay_ok: true,
            replay_issues: [],
            total_turns: 1,
            total_cost_usd: 1.5,
          },
        ],
      },
      selectedSessionId: "sess-1",
      detailsBySessionId: {
        "sess-1": {
          session: {
            session_id: "sess-1",
            provider_id: "codex",
            model_id: "gpt-5.4",
            cwd: "/repo",
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-01T01:00:00Z",
            status: "completed",
            summary: "overnight build",
            metadata: {},
          },
          replay_ok: true,
          replay_issues: [],
          compaction_preview: {
            event_count: 6,
            by_type: {text_delta: 2},
            compactable_ratio: 0.333,
            protected_event_types: ["session_start", "session_end"],
            recent_event_types: ["session_start", "text_delta", "session_end"],
          },
          recent_events: [
            {
              event_id: "evt-1",
              event_type: "tool_result",
              source: "provider",
              audience: "all",
              transport: "local",
              session_id: "sess-1",
              created_at: "2026-04-01T00:30:00Z",
              payload: {tool_name: "Read", content: "ok"},
            },
          ],
        },
      },
    } as const;

    const lines = sessionPaneToLines(sessionPane).map((line) => line.text);
    const preview = sessionPaneToPreview(sessionPane);

    expect(lines).toContain("# Session Catalog");
    expect(lines).toContain("## Drilldown");
    expect(lines).toContain("# Session Detail");
    expect(lines).toContain("## Recent envelopes");
    expect(preview?.Selected).toBe("sess-1");
    expect(preview?.Compaction).toBe("6 events | 33%");
  });

  test("suppresses legacy text patching when typed session payloads are present", () => {
    expect(
      eventToTabPatch({
        type: "session.catalog.result",
        content: "legacy prose",
        payload: {count: 0, sessions: []},
      }),
    ).toEqual([]);

    expect(
      eventToTabPatch({
        type: "session.detail.result",
        content: "legacy prose",
        payload: {
          session: {
            session_id: "sess-1",
            provider_id: "codex",
            model_id: "gpt-5.4",
            cwd: "/repo",
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-01T01:00:00Z",
            status: "completed",
          },
          replay_ok: true,
          replay_issues: [],
          compaction_preview: {},
          recent_events: [],
        },
      }),
    ).toEqual([]);
  });
});

describe("typed runtime helpers", () => {
  test("normalizes and renders typed runtime payloads", () => {
    const event = {
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-1",
          created_at: "2026-04-01T00:00:00Z",
          repo_root: "/repo",
          runtime_db: "/tmp/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 3,
          active_run_count: 1,
          artifact_count: 5,
          context_bundle_count: 2,
          anomaly_count: 0,
          verification_status: "ok",
          next_task: "ship it",
          active_task: "wire runtime payloads",
          summary: "1 active runs, 2 context bundles, 5 artifacts",
          warnings: [],
          metrics: {
            claims: "4",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "6",
            promoted_facts: "2",
          },
          metadata: {
            overview: {runs: 3},
            supervisor_preview: {
              "Loop state": "cycle 9 running",
              "Loop decision": "continue required",
              "Task progress": "0 done, 1 pending of 1",
              "Result status": "in_progress",
              Acceptance: "pass",
              "Verification summary": "tsc=ok | cycle_acceptance=ok",
              "Verification checks": "tsc ok; cycle_acceptance ok",
              "Durable state": "/tmp/durable",
            },
          },
        },
      },
    };

    const payload = runtimeSnapshotPayloadFromEvent(event);
    const preview = runtimePayloadToPreview(payload!, null);

    expect(payload?.snapshot.active_session_count).toBe(3);
    expect(preview["Runtime DB"]).toBe("/tmp/runtime.db");
    expect(preview["Session state"]).toBe("3 sessions | 4 claims | 1 active claims | 1 acked claims");
    expect(preview["Run state"]).toBe("1 active run | 3 runs total");
    expect(preview["Context state"]).toBe("5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions");
    expect(preview["Loop state"]).toBe("cycle 9 running");
    expect(preview["Active task"]).toBe("wire runtime payloads");
    expect(preview["Next task"]).toBe("ship it");
    expect(preview["Loop decision"]).toBe("continue required");
    expect(preview["Verification summary"]).toBe("tsc=ok | cycle_acceptance=ok");
    expect(preview["Verification status"]).toBe("all 2 checks passing");
    expect(preview["Verification passing"]).toBe("tsc, cycle_acceptance");
    expect(preview["Verification failing"]).toBe("none");
    expect(preview["Control pulse preview"]).toContain("cycle 9 running");
  });
});

describe("typed workspace helpers", () => {
  test("suppresses raw repo transcript patches when typed workspace payloads are present", () => {
    expect(
      eventToTabPatch({
        type: "workspace.snapshot.result",
        content: "legacy workspace prose",
        payload: {
          version: "v1",
          domain: "workspace_snapshot",
          repo_root: "/repo",
          git: {
            branch: "main",
            head: "abc1234",
            staged: 0,
            unstaged: 0,
            untracked: 0,
            changed_hotspots: [],
            changed_paths: [],
            sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
          },
          topology: {warnings: [], repos: []},
          inventory: {},
          language_mix: [],
          largest_python_files: [],
          most_imported_modules: [],
        },
      }),
    ).toEqual([]);
  });
});

describe("approval helpers", () => {
  test("normalizes canonical permission decision payloads", () => {
    const decision = permissionDecisionFromEvent({
      type: "permission.decision",
      payload: {
        version: "v1",
        domain: "permission_decision",
        action_id: "perm_1",
        tool_name: "Bash",
        risk: "shell_or_network",
        decision: "require_approval",
        rationale: "Bash is not classified as safe and remains operator-gated",
        policy_source: "legacy-governance",
        requires_confirmation: true,
        command_prefix: "git status",
        metadata: {
          tool_call_id: "tool_1",
          provider_id: "codex",
          session_id: "sess_1",
        },
      },
    });

    expect(decision?.action_id).toBe("perm_1");
    expect(decision?.decision).toBe("require_approval");
    expect(decision?.metadata.session_id).toBe("sess_1");
  });

  test("renders approval queue lines and preview", () => {
    const pane = {
      selectedActionId: "perm_1",
      order: ["perm_1"],
      historyBacked: true,
      entriesByActionId: {
        perm_1: {
          decision: {
            version: "v1" as const,
            domain: "permission_decision" as const,
            action_id: "perm_1",
            tool_name: "Bash",
            risk: "shell_or_network",
            decision: "require_approval",
            rationale: "Bash is not classified as safe and remains operator-gated",
            policy_source: "legacy-governance",
            requires_confirmation: true,
            command_prefix: "git status",
            metadata: {tool_call_id: "tool_1", provider_id: "codex", session_id: "sess_1"},
          },
          status: "pending" as const,
          firstSeenAt: "2026-04-02T00:00:00Z",
          lastSeenAt: "2026-04-02T00:00:00Z",
          lastSourceEventType: "permission.decision",
          seenCount: 1,
          pending: true,
        },
      },
    };

    const lines = approvalPaneToLines(pane);
    const preview = approvalPaneToPreview(pane);

    expect(lines.some((line) => line.text.includes("perm_1 | Bash | shell_or_network | require_approval"))).toBe(true);
    expect(lines.some((line) => line.text.includes("Authority: history"))).toBe(true);
    expect(lines.some((line) => line.text.includes("Status: pending"))).toBe(true);
    expect(lines.some((line) => line.text.includes("Rationale: Bash is not classified as safe"))).toBe(true);
    expect(preview?.Authority).toBe("history");
    expect(preview?.Pending).toBe("1");
    expect(preview?.Status).toBe("pending");
    expect(preview?.Tool).toBe("Bash");
    expect(preview?.Session).toBe("sess_1");
  });

  test("normalizes canonical permission resolution payloads", () => {
    const resolution = permissionResolutionFromEvent({
      type: "permission.resolution",
      payload: {
        version: "v1",
        domain: "permission_resolution",
        action_id: "perm_1",
        resolution: "approved",
        resolved_at: "2026-04-02T00:10:00Z",
        actor: "operator",
        summary: "approved perm_1",
        note: "safe after inspection",
        enforcement_state: "recorded_only",
        metadata: {
          session_id: "sess_1",
        },
      },
    });

    expect(resolution?.action_id).toBe("perm_1");
    expect(resolution?.resolution).toBe("approved");
    expect(resolution?.enforcement_state).toBe("recorded_only");
  });

  test("normalizes canonical permission history payloads", () => {
    const history = permissionHistoryFromEvent({
      type: "permission.history.result",
      payload: {
        version: "v1",
        domain: "permission_history",
        count: 1,
        entries: [
          {
            action_id: "perm_1",
            decision: {
              version: "v1",
              domain: "permission_decision",
              action_id: "perm_1",
              tool_name: "Bash",
              risk: "shell_or_network",
              decision: "require_approval",
              rationale: "Bash is not classified as safe and remains operator-gated",
              policy_source: "legacy-governance",
              requires_confirmation: true,
              command_prefix: "git status",
              metadata: {session_id: "sess_1"},
            },
            resolution: {
              version: "v1",
              domain: "permission_resolution",
              action_id: "perm_1",
              resolution: "approved",
              resolved_at: "2026-04-02T00:10:00Z",
              actor: "operator",
              summary: "approved perm_1",
              enforcement_state: "recorded_only",
              metadata: {session_id: "sess_1"},
            },
            outcome: {
              version: "v1",
              domain: "permission_outcome",
              action_id: "perm_1",
              outcome: "runtime_applied",
              outcome_at: "2026-04-02T00:10:01Z",
              source: "runtime",
              summary: "runtime applied perm_1",
              metadata: {runtime_action_id: "runtime_1"},
            },
            first_seen_at: "2026-04-02T00:00:00Z",
            last_seen_at: "2026-04-02T00:10:00Z",
            seen_count: 2,
            pending: false,
            status: "runtime_applied",
          },
        ],
      },
    });

    expect(history?.count).toBe(1);
    expect(history?.entries[0]?.decision.action_id).toBe("perm_1");
    expect(history?.entries[0]?.resolution?.resolution).toBe("approved");
    expect(history?.entries[0]?.outcome?.outcome).toBe("runtime_applied");
    expect(history?.entries[0]?.status).toBe("runtime_applied");
  });

  test("renders approval outcomes in approval pane lines and preview", () => {
    const pane = {
      historyBacked: true,
      selectedActionId: "perm_1",
      order: ["perm_1"],
      entriesByActionId: {
        perm_1: {
          decision: {
            version: "v1" as const,
            domain: "permission_decision" as const,
            action_id: "perm_1",
            tool_name: "Bash",
            risk: "shell_or_network",
            decision: "require_approval",
            rationale: "Bash is not classified as safe and remains operator-gated",
            policy_source: "legacy-governance",
            requires_confirmation: true,
            command_prefix: "git status",
            metadata: {tool_call_id: "tool_1", provider_id: "codex", session_id: "sess_1"},
          },
          status: "runtime_applied" as const,
          firstSeenAt: "2026-04-02T00:00:00Z",
          lastSeenAt: "2026-04-02T00:10:01Z",
          lastSourceEventType: "permission.outcome",
          seenCount: 3,
          pending: false,
          resolution: {
            version: "v1" as const,
            domain: "permission_resolution" as const,
            action_id: "perm_1",
            resolution: "approved",
            resolved_at: "2026-04-02T00:10:00Z",
            actor: "operator",
            summary: "approved perm_1",
            enforcement_state: "runtime_recorded",
            metadata: {},
          },
          outcome: {
            version: "v1" as const,
            domain: "permission_outcome" as const,
            action_id: "perm_1",
            outcome: "runtime_applied",
            outcome_at: "2026-04-02T00:10:01Z",
            source: "runtime",
            summary: "runtime applied perm_1",
            metadata: {runtime_action_id: "runtime_1"},
          },
        },
      },
    };

    const lines = approvalPaneToLines(pane).map((line) => line.text);
    const preview = approvalPaneToPreview(pane);

    expect(lines).toContain("Status: runtime applied");
    expect(lines).toContain("Runtime outcome: runtime_applied");
    expect(lines).toContain("Outcome source: runtime");
    expect(lines).toContain("Runtime action id: runtime_1");
    expect(preview?.Status).toBe("runtime applied");
    expect(preview?.Outcome).toBe("runtime_applied");
  });
});

describe("session payload renderers", () => {
  test("renders session catalog payloads into lines and preview", () => {
    const payload = {
      type: "session.catalog.result",
      payload: {
        version: "v1",
        domain: "session_catalog",
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess_123",
              provider_id: "codex",
              model_id: "gpt-5.4",
              status: "completed",
              branch_label: "main",
              summary: "stabilize terminal shell",
            },
            replay_ok: true,
            replay_issues: [],
            total_turns: 12,
            total_cost_usd: 0.47,
          },
        ],
      },
    };

    const lines = sessionCatalogToLines(payload);
    const preview = sessionCatalogToPreview(payload);

    expect(lines.some((line) => line.text.includes("sess_123 | codex:gpt-5.4 | completed"))).toBe(true);
    expect(lines.some((line) => line.text.includes("stabilize terminal shell"))).toBe(true);
    expect(preview.Sessions).toBe("1");
    expect(preview["Latest route"]).toBe("codex:gpt-5.4");
    expect(preview["Replay state"]).toBe("ok");
  });

  test("renders session detail payloads into lines and preview", () => {
    const payload = {
      type: "session.detail.result",
      session_id: "sess_123",
      payload: {
        version: "v1",
        domain: "session_detail",
        session: {
          session_id: "sess_123",
          provider_id: "codex",
          model_id: "gpt-5.4",
          status: "completed",
          branch_label: "main",
          summary: "stabilize terminal shell",
          cwd: "/Users/dhyana/dharma_swarm",
        },
        replay_ok: false,
        replay_issues: ["missing usage event"],
        compaction_preview: {
          event_count: 80,
          compactable_ratio: 0.42,
          protected_event_types: ["tool_call_complete", "tool_result"],
        },
        recent_events: [
          {
            event_id: "evt_1",
            event_type: "tool_call_complete",
            created_at: "2026-04-02T00:03:00Z",
          },
        ],
        approval_history: {
          version: "v1",
          domain: "permission_history",
          count: 1,
          entries: [
            {
              action_id: "perm_1",
              decision: {
                version: "v1",
                domain: "permission_decision",
                action_id: "perm_1",
                tool_name: "Bash",
                risk: "shell_or_network",
                decision: "require_approval",
                rationale: "Bash is not classified as safe and remains operator-gated",
                policy_source: "legacy-governance",
                requires_confirmation: true,
                command_prefix: "git status",
                metadata: {session_id: "sess_123"},
              },
              resolution: {
                version: "v1",
                domain: "permission_resolution",
                action_id: "perm_1",
                resolution: "approved",
                resolved_at: "2026-04-02T00:10:00Z",
                actor: "operator",
                summary: "approved perm_1",
                enforcement_state: "runtime_recorded",
                metadata: {session_id: "sess_123"},
              },
              outcome: {
                version: "v1",
                domain: "permission_outcome",
                action_id: "perm_1",
                outcome: "runtime_applied",
                outcome_at: "2026-04-02T00:10:01Z",
                source: "runtime",
                summary: "runtime applied perm_1",
                metadata: {runtime_action_id: "runtime_1", runtime_event_id: "evt_runtime_1"},
              },
              first_seen_at: "2026-04-02T00:00:00Z",
              last_seen_at: "2026-04-02T00:10:01Z",
              seen_count: 3,
              pending: false,
              status: "runtime_applied",
            },
          ],
        },
      },
    };

    const lines = sessionDetailToLines(payload);
    const preview = sessionDetailToPreview(payload);

    expect(lines.some((line) => line.text.includes("Replay: issues: missing usage event"))).toBe(true);
    expect(lines.some((line) => line.text.includes("compactable 42%"))).toBe(true);
    expect(lines.some((line) => line.text.includes("tool_call_complete | 2026-04-02T00:03:00Z | evt_1"))).toBe(true);
    expect(lines.some((line) => line.text.includes("runtime_applied"))).toBe(true);
    expect(lines.some((line) => line.text.includes("runtime_1 | evt_runtime_1"))).toBe(true);
    expect(preview["Session id"]).toBe("sess_123");
    expect(preview["Compaction ratio"]).toBe("42%");
    expect(preview.Replay).toBe("issues: missing usage event");
  });
});

describe("inferSlashCommand", () => {
  test("extracts the first slash command from summary text", () => {
    expect(inferSlashCommand("executed /git status")).toBe("/git");
    expect(inferSlashCommand("run /runtime now")).toBe("/runtime");
  });

  test("extracts slash commands wrapped in inline quoting", () => {
    expect(inferSlashCommand("executed `/git status`")).toBe("/git");
    expect(inferSlashCommand("run '/runtime status' next")).toBe("/runtime");
  });

  test("ignores filesystem paths embedded in summaries", () => {
    expect(inferSlashCommand("wrote snapshot to /Users/dhyana/dharma_swarm/state and then executed /git status")).toBe(
      "/git",
    );
    expect(inferSlashCommand("log saved at /tmp/runtime.log")).toBe("");
  });

  test("ignores leading filesystem paths before the first slash command", () => {
    expect(inferSlashCommand("/tmp/runtime.log captured before executed /runtime status")).toBe("/runtime");
    expect(inferSlashCommand("/Users/dhyana/dharma_swarm/terminal/src/app.tsx")).toBe("");
  });
});

describe("isSlashCommandPrompt", () => {
  test("detects slash commands without treating chat prompts as commands", () => {
    expect(isSlashCommandPrompt("/status")).toBe(true);
    expect(isSlashCommandPrompt(" summarize the repo status")).toBe(false);
  });
});

describe("commandTargetTab", () => {
  test("routes repo commands to the repo pane", () => {
    expect(commandTargetTab("/git")).toBe("repo");
  });

  test("routes runtime commands to the runtime pane", () => {
    expect(commandTargetTab("/runtime")).toBe("runtime");
  });

  test("routes dashboard commands to the control pane", () => {
    expect(commandTargetTab("/dashboard")).toBe("control");
  });

  test("routes model, agent, and evolution commands to their dedicated panes", () => {
    expect(commandTargetTab("/model set codex-5.4")).toBe("models");
    expect(commandTargetTab("/swarm status")).toBe("agents");
    expect(commandTargetTab("/hum")).toBe("agents");
    expect(commandTargetTab("/evolve status")).toBe("evolution");
  });

  test("routes ontology commands to the ontology pane", () => {
    expect(commandTargetTab("/context architect")).toBe("ontology");
    expect(commandTargetTab("/foundations")).toBe("ontology");
  });

  test("routes trishula agent inbox commands to the agents pane", () => {
    expect(commandTargetTab("/trishula inbox")).toBe("agents");
  });

  test("routes memory commands to the sessions pane", () => {
    expect(commandTargetTab("/memory")).toBe("sessions");
    expect(commandTargetTab("/logs")).toBe("sessions");
    expect(commandTargetTab("/notes")).toBe("sessions");
    expect(commandTargetTab("/session")).toBe("sessions");
    expect(commandTargetTab("/darwin")).toBe("sessions");
  });

  test("routes operational and unknown commands away from chat", () => {
    expect(commandTargetTab("/status")).toBe("control");
    expect(commandTargetTab("/help")).toBe("control");
    expect(commandTargetTab("/unknown")).toBe("control");
  });

  test("keeps explicit chat control inside the chat pane", () => {
    expect(commandTargetTab("/chat continue")).toBe("chat");
  });

  test("keeps local chat control commands out of the control pane", () => {
    expect(commandTargetTab("/clear")).toBe("chat");
    expect(commandTargetTab("/reset")).toBe("chat");
    expect(commandTargetTab("/copy")).toBe("chat");
    expect(commandTargetTab("/paste")).toBe("chat");
    expect(commandTargetTab("/thread")).toBe("chat");
  });
});

describe("resolveCommandTargetPane", () => {
  test("derives the command from summary text when command is omitted", () => {
    expect(
      resolveEventCommand({
        type: "command.result",
        summary: "executed /git status",
      }),
    ).toBe("/git");
  });

  test("falls back to the slash command embedded in the summary", () => {
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        summary: "executed /git status",
      }),
    ).toBe("repo");
  });

  test("derives the command and target pane from nested action payloads", () => {
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        request: {
          command: "/runtime status",
          target_pane: "registry",
        },
      }),
    ).toBe("runtime");
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        payload: {
          arguments: {
            command: "/memory recent",
          },
          target_pane: "notes",
        },
      }),
    ).toBe("sessions");
  });

  test("derives the command and target pane from nested payload request envelopes", () => {
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        payload: {
          request: {
            command: "/git status",
            target_pane: "workspace",
          },
        },
      }),
    ).toBe("repo");
  });

  test("derives the target pane from an inline-code slash command in the summary", () => {
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        summary: "executed `/git status`",
      }),
    ).toBe("repo");
  });

  test("ignores an explicit chat target for operational slash commands", () => {
    expect(
      resolveCommandTargetPane({
        type: "command.result",
        command: "/git status",
        target_pane: "chat",
      }),
    ).toBe("repo");
  });

  test("ignores launcher-pane targets for operational slash commands", () => {
    expect(
      resolveCommandTargetPane({
        type: "command.result",
        command: "/git status",
        target_pane: "commands",
      }),
    ).toBe("repo");
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        command: "/runtime",
        target_pane: "registry",
      }),
    ).toBe("runtime");
  });

  test("honors explicit approvals targets for slash commands", () => {
    expect(
      resolveCommandTargetPane({
        type: "command.result",
        command: "/git status",
        target_pane: "approvals",
      }),
    ).toBe("approvals");
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        command: "/runtime",
        target_pane: "permissions",
      }),
    ).toBe("approvals");
  });

  test("keeps explicit chat targets for chat control commands", () => {
    expect(
      resolveCommandTargetPane({
        type: "command.result",
        command: "/reset",
        target_pane: "chat",
      }),
    ).toBe("chat");
  });

  test("pins chat control commands to chat even when an explicit non-chat target is provided", () => {
    expect(
      resolveCommandTargetPane({
        type: "command.result",
        command: "/reset",
        target_pane: "repo",
      }),
    ).toBe("chat");
    expect(
      resolveCommandTargetPane({
        type: "action.result",
        action_type: "command.run",
        command: "/chat",
        target_pane: "approvals",
      }),
    ).toBe("chat");
  });
});

describe("eventToTabPatch", () => {
  test("routes chat control command output into chat", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "reset",
      output: "Conversation memory reset.",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("chat");
    expect(patches[0]?.lines[0]?.text).toBe("Conversation memory reset.");
  });

  test("keeps chat control command output in chat when explicit non-chat targets arrive", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/reset",
      target_pane: "repo",
      output: "Conversation memory reset.",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("chat");
    expect(patches[0]?.lines[0]?.text).toBe("Conversation memory reset.");
  });

  test("prefers an explicit target pane on command results", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/git status",
      target_pane: "control",
      output: "Command override landed in control.",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("control");
    expect(patches[0]?.lines[0]?.text).toBe("Command override landed in control.");
  });

  test("ignores an explicit chat target on operational command results", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/runtime",
      target_pane: "chat",
      output: "Loop state: cycle 3 running",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("runtime");
    expect(patches[0]?.lines[0]?.text).toBe("Loop state: cycle 3 running");
  });

  test("normalizes workspace target pane aliases onto the repo pane", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/git status",
      target_pane: "workspace",
      output: "Command override landed in repo.",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("repo");
    expect(patches[0]?.lines[0]?.text).toBe("Command override landed in repo.");
  });

  test("normalizes legacy notes targets onto the sessions pane", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/memory",
      target_pane: "notes",
      output: "Session memory lane",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("sessions");
    expect(patches[0]?.lines[0]?.text).toBe("Session memory lane");
  });

  test("routes explicit approvals targets into the approvals pane", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/git status",
      target_pane: "approvals",
      output: "Review pending: repo write requires approval",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("approvals");
    expect(patches[0]?.lines[0]?.text).toBe("Review pending: repo write requires approval");
  });

  test("ignores invalid explicit target panes and falls back to command inference", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/runtime",
      target_pane: "not-a-real-pane",
      output: "Loop state: cycle 3 running",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("runtime");
    expect(patches[0]?.lines[0]?.text).toBe("Loop state: cycle 3 running");
  });

  test("routes dashboard command output into control", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/dashboard",
      output: "Loop state: cycle 3 running",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("control");
    expect(patches[0]?.lines[0]?.text).toBe("Loop state: cycle 3 running");
  });

  test("routes hum command output into agents", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/hum",
      target_pane: "agents",
      output: "Hum lane: 2 pending dispatches",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("agents");
    expect(patches[0]?.lines[0]?.text).toBe("Hum lane: 2 pending dispatches");
  });

  test("does not synthesize transcript rows for summary-only operational command results", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      summary: "executed /git status",
    });

    expect(patches).toEqual([]);
  });

  test("suppresses raw repo transcript patches for workspace snapshot command results", () => {
    const patches = eventToTabPatch({
      type: "command.result",
      command: "/git",
      output: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48`,
    });

    expect(patches).toEqual([]);
  });

  test("suppresses raw repo transcript patches for authoritative workspace snapshot refreshes", () => {
    const patches = eventToTabPatch({
      type: "workspace.snapshot.result",
      content: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46`,
    });

    expect(patches).toEqual([]);
  });

  test("routes slash command action results through the same pane patch logic", () => {
    const patches = eventToTabPatch({
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      target_pane: "chat",
      output: "Loop state: cycle 3 running",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("runtime");
    expect(patches[0]?.lines[0]?.text).toBe("Loop state: cycle 3 running");
  });

  test("routes nested slash command action payloads through the same pane patch logic", () => {
    const patches = eventToTabPatch({
      type: "action.result",
      action_type: "command.run",
      request: {
        command: "/git status",
        target_pane: "workspace",
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("repo");
    expect(patches[0]?.lines[0]?.text).toBe("Repo dirty: 517 unstaged, 47 untracked");
  });

  test("routes payload-wrapped slash command action results through the inferred pane patch logic", () => {
    const patches = eventToTabPatch({
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          target_pane: "workspace",
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(patches).toHaveLength(1);
    expect(patches[0]?.tabId).toBe("repo");
    expect(patches[0]?.lines[0]?.text).toBe("Repo dirty: 517 unstaged, 47 untracked");
  });

  test("suppresses structured runtime transcript patches for slash command action results", () => {
    const patches = eventToTabPatch({
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      output: `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1`,
    });

    expect(patches).toEqual([]);
  });
});

describe("sessionBootstrap helpers", () => {
  test("renders mission lines from bootstrap payload", () => {
    const lines = sessionBootstrapToLines({
      prompt: "show me runtime status",
      active_tab: "chat",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        command: "runtime",
        reason: "plain-language operator command",
      },
      workspace_preview: {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        "Repo risk": "sab_canonical_repo_missing",
        Dirty: "0 staged, 1 unstaged, 0 untracked",
      },
      runtime_preview: {
        "Runtime activity": "Sessions=18  Claims=0",
        "Artifact state": "Artifacts=7  PromotedFacts=2",
      },
      repo_guidance: "Behavioral Rules: obey CLAUDE.md",
      session_context_hint: "Active thread: terminal-v3",
      working_memory: "Active mission: stabilize terminal operator shell",
    }).map((line) => line.text);

    expect(lines).toContain("# Session Bootstrap");
    expect(lines).toContain("Intent: command -> /runtime (plain-language operator command)");
    expect(lines).toContain("Route: codex:gpt-5.4");
    expect(lines).toContain("Repo risk: sab_canonical_repo_missing");
    expect(lines).toContain("Runtime activity: Sessions=18  Claims=0");
    expect(lines).toContain("Repo guidance: loaded");
    expect(lines).toContain("Session hint: Active thread: terminal-v3");
  });

  test("builds preview fields from bootstrap payload", () => {
    const preview = sessionBootstrapToPreview({
      selected_provider: "claude",
      selected_model: "claude-sonnet-4-5",
      routing_strategy: "genius",
      intent: {
        kind: "model_switch",
        provider: "claude",
        model: "claude-sonnet-4-5",
        strategy: "genius",
        reason: "explicit model-routing request",
      },
      workspace_preview: {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "main",
        "Repo risk": "stable",
        Dirty: "clean",
      },
      runtime_preview: {
        "Runtime activity": "Sessions=4",
        "Artifact state": "Artifacts=1",
      },
      repo_guidance: "Behavioral Rules: obey CLAUDE.md",
      session_context_hint: "Active thread: terminal-v3",
      working_memory: "Active mission: stabilize terminal operator shell",
    });

    expect(preview.Intent).toContain("model switch");
    expect(preview.Route).toBe("claude:claude-sonnet-4-5");
    expect(preview.Strategy).toBe("genius");
    expect(preview["Repo root"]).toBe("/Users/dhyana/dharma_swarm");
    expect(preview["Runtime activity"]).toBe("Sessions=4");
    expect(preview["Repo guidance"]).toBe("loaded");
    expect(preview["Session hint"]).toBe("Active thread: terminal-v3");
  });
});

describe("commandGraph helpers", () => {
  test("renders command graph lines and preview", () => {
    const payload = {
      graph: {
        count: 42,
        async_count: 21,
        categories: {
          chat: ["chat", "clear"],
          repo: ["git", "runtime"],
        },
        async_commands: ["runtime", "swarm"],
      },
    };

    const lines = commandGraphToLines(payload).map((line) => line.text);
    const preview = commandGraphToPreview(payload);

    expect(lines).toContain("# Command Graph");
    expect(lines).toContain("Command count: 42");
    expect(lines).toContain("- repo: git, runtime");
    expect(preview.Commands).toBe("42");
    expect(preview["Async lanes"]).toBe("21");
    expect(preview["Chat commands"]).toBe("chat, clear");
  });
});

describe("operatorSnapshot helpers", () => {
  test("renders operator snapshot lines and preview", () => {
    const payload = {
      snapshot: {
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        overview: {
          sessions: 3,
          claims: 2,
          active_claims: 1,
          acknowledged_claims: 1,
          runs: 4,
          active_runs: 2,
          artifacts: 5,
          promoted_facts: 2,
          context_bundles: 1,
          operator_actions: 6,
        },
        runs: [
          {assigned_to: "agent-alpha", status: "running", task_id: "task-123", run_id: "run-1234567890"},
        ],
        actions: [
          {action_name: "reroute", actor: "operator", task_id: "task-123", reason: "better frontier model"},
        ],
      },
    };

    const lines = operatorSnapshotToLines(payload).map((line) => line.text);
    const preview = operatorSnapshotToPreview(payload);

    expect(lines).toContain("# Operator Snapshot");
    expect(lines).toContain("Sessions: 3");
    expect(lines.some((line) => line.includes("agent-alpha | running"))).toBe(true);
    expect(preview["Runtime DB"]).toBe("/Users/dhyana/.dharma/state/runtime.db");
    expect(preview["Run state"]).toBe("4 runs | 2 active runs");
    expect(preview["Active runs detail"]).toContain("agent-alpha (running) task task-123");
    expect(preview["Recent operator actions"]).toContain("reroute by operator (better frontier model)");
    expect(preview.Sessions).toBe("3");
    expect(preview["Active runs"]).toBe("2");
    expect(preview.Agents).toContain("agent-alpha");
  });
});

describe("modelPolicy helpers", () => {
  test("renders model policy lines and preview", () => {
    const payload = {
      policy: {
        active_label: "Codex 5.4",
        selected_route: "codex:gpt-5.4",
        strategy: "responsive",
        default_route: "ollama:glm-5:cloud",
        fallback_chain: [{label: "Claude Haiku 4.5", provider: "claude"}],
        targets: [{alias: "codex-5.4", label: "Codex 5.4", provider: "codex", model: "gpt-5.4"}],
      },
    };
    const lines = modelPolicyToLines(payload).map((line) => line.text);
    const preview = modelPolicyToPreview(payload);

    expect(lines).toContain("# Model Policy");
    expect(lines).toContain("Active: Codex 5.4");
    expect(lines.some((line) => line.includes("Claude Haiku 4.5"))).toBe(true);
    expect(lines.some((line) => line.includes("codex-5.4 -> Codex 5.4 (codex:gpt-5.4)"))).toBe(true);
    expect(preview.Active).toBe("Codex 5.4");
    expect(preview.Fallbacks).toBe("1");
    expect(preview.Targets).toBe("1");
  });

  test("prefers typed routing payloads when present", () => {
    const event = {
      type: "model.policy.result",
      payload: {
        version: "v1",
        domain: "routing_decision",
        decision: {
          route_id: "codex:gpt-5.4",
          provider_id: "codex",
          model_id: "gpt-5.4",
          strategy: "responsive",
          reason: "selected by current routing policy",
          fallback_chain: ["claude:sonnet-4.6"],
          degraded: false,
          metadata: {
            active_label: "Codex 5.4",
            default_route: "codex:gpt-5.4",
          },
        },
        strategies: ["responsive", "genius"],
        fallback_targets: [{label: "Claude Sonnet 4.6", provider: "claude"}],
        targets: [{alias: "codex-5.4", label: "Codex 5.4", provider: "codex", model: "gpt-5.4"}],
      },
    };

    const payload = routingDecisionPayloadFromEvent(event);
    const lines = modelPolicyToLines(event).map((line) => line.text);
    const preview = modelPolicyToPreview(event);

    expect(payload?.decision.route_id).toBe("codex:gpt-5.4");
    expect(lines).toContain("Active: Codex 5.4");
    expect(lines.some((line) => line.includes("Claude Sonnet 4.6"))).toBe(true);
    expect(preview.Route).toBe("codex:gpt-5.4");
    expect(preview.Targets).toBe("1");
  });

  test("does not truncate expanded target rosters", () => {
    const event = {
      type: "model.policy.result",
      payload: {
        version: "v1",
        domain: "routing_decision",
        decision: {
          route_id: "openrouter:deepseek/deepseek-r1",
          provider_id: "openrouter",
          model_id: "deepseek/deepseek-r1",
          strategy: "responsive",
          reason: "expanded target roster",
          fallback_chain: [],
          degraded: false,
          metadata: {
            active_label: "deepseek/deepseek-r1",
            default_route: "codex:gpt-5.4",
          },
        },
        strategies: ["responsive", "genius"],
        fallback_targets: [],
        targets: Array.from({length: 12}, (_, index) => ({
          alias: `lane-${index + 1}`,
          label: `Lane ${index + 1}`,
          provider: index % 2 === 0 ? "openrouter" : "codex",
          model: `model-${index + 1}`,
        })),
      },
    };

    const lines = modelPolicyToLines(event).map((line) => line.text);

    expect(lines.some((line) => line.includes("lane-12 -> Lane 12 (codex:model-12)"))).toBe(true);
  });
});

describe("agentRoutes helpers", () => {
  test("renders route profiles and openclaw summary", () => {
    const payload = {
      routes: {
        routes: [{intent: "deep_code_work", provider: "codex", model_alias: "codex-5.4", reasoning: "high", role: "builder"}],
        openclaw: {present: true, readable: true, agents_count: 3, providers: ["codex", "claude"]},
      },
    };
    const lines = agentRoutesToLines(payload).map((line) => line.text);
    const preview = agentRoutesToPreview(payload);

    expect(lines).toContain("# Agent Routes");
    expect(lines.some((line) => line.includes("deep_code_work -> codex:codex-5.4"))).toBe(true);
    expect(preview.Routes).toBe("1");
    expect(preview["OpenClaw agents"]).toBe("3");
  });

  test("prefers typed agent routes payloads when present", () => {
    const event = {
      type: "agent.routes.result",
      payload: {
        version: "v1",
        domain: "agent_routes",
        routes: [{intent: "deep_code_work", provider: "codex", model_alias: "codex-5.4", reasoning: "high", role: "builder"}],
        openclaw: {present: true, readable: true, agents_count: 3, providers: ["codex", "claude"]},
        subagent_capabilities: ["route by task type"],
      },
    };

    const payload = agentRoutesPayloadFromEvent(event);
    const lines = agentRoutesToLines(event).map((line) => line.text);
    const preview = agentRoutesToPreview(event);

    expect(payload?.routes[0]?.intent).toBe("deep_code_work");
    expect(lines.some((line) => line.includes("deep_code_work -> codex:codex-5.4"))).toBe(true);
    expect(preview.Routes).toBe("1");
    expect(preview["OpenClaw agents"]).toBe("3");
  });
});

describe("evolutionSurface helpers", () => {
  test("renders evolution surface and preview", () => {
    const payload = {
      surface: {
        domains: [{name: "code", fitness_threshold: 0.9, max_iterations: 12, max_duration_seconds: 600}],
        entry_commands: ["/cascade code", "/loops"],
        principles: ["self-improvement should stay inspectable"],
      },
    };
    const lines = evolutionSurfaceToLines(payload).map((line) => line.text);
    const preview = evolutionSurfaceToPreview(payload);

    expect(lines).toContain("# Evolution Surface");
    expect(lines.some((line) => line.includes("code | threshold 0.9"))).toBe(true);
    expect(preview.Domains).toBe("1");
    expect(preview["Primary domain"]).toBe("code");
  });
});

describe("workspaceSnapshotToLines", () => {
  test("renders a bounded repo summary with dirty counts, topology warnings, and hotspots", () => {
    const content = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 510 | untracked 42
Git hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)
Git changed paths: terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts
Git sync: origin/main | ahead 0 | behind 0

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 510 | untracked 42
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36`;

    const lines = workspaceSnapshotToLines(content).map((line) => line.text);

    expect(lines).toEqual([
      "# Repo Snapshot",
      "## Git status",
      "Repo root: /Users/dhyana/dharma_swarm",
      "Branch: main",
      "Head: 95210b1",
      "Sync: origin/main | ahead 0 | behind 0",
      "Branch status: tracking origin/main in sync",
      "Upstream: origin/main",
      "Ahead: 0",
      "Behind: 0",
      "Branch sync preview: tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview: tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk: topology sab_canonical_repo_missing; high (552 local changes)",
      "Dirty: 0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure: high (552 local changes)",
      "Staged: 0",
      "Unstaged: 510",
      "Untracked: 42",
      "## Topology risk",
      "Topology warnings: 1 (sab_canonical_repo_missing)",
      "Topology warning severity: high",
      "Topology risk: sab_canonical_repo_missing",
      "Risk preview: sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview: sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview: 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Topology status: degraded (1 warning, 2 peers)",
      "Primary warning: sab_canonical_repo_missing",
      "Primary peer drift: dharma_swarm track main...origin/main",
      "Primary topology peer: dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers: dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers: dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure: dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "## Hotspots",
      "Changed hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Changed paths: terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
      "Hotspot summary: change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | paths terminal/src/protocol.ts",
      "Lead hotspot preview: change terminal (274) | path terminal/src/protocol.ts",
      "Hotspot pressure preview: change terminal (274)",
      "Primary changed hotspot: terminal (274)",
      "Primary changed path: terminal/src/protocol.ts",
      "Primary file hotspot: dgc_cli.py (6908 lines)",
      "Primary dependency hotspot: none",
      "File hotspots: dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
      "Dependency hotspots: none",
      "## Inventory",
      "Inventory: n/a modules | n/a tests | n/a scripts | n/a docs | n/a workflows",
      "Language mix: none",
    ]);
    expect(lines).toHaveLength(47);
    expect(lines.indexOf("## Topology risk")).toBeLessThan(lines.indexOf("## Hotspots"));
  });
});

describe("workspacePreviewToLines", () => {
  test("renders the same bounded repo transcript from preview fields alone", () => {
    const preview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch status": "tracking origin/main in sync",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview": "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      Dirty: "0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Changed paths": "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
      "Hotspot summary":
        "change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | paths terminal/src/protocol.ts",
      "Hotspot pressure preview": "change terminal (274)",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
      "Primary dependency hotspot": "none",
      Hotspots: "dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
      "Inbound hotspots": "none",
      Inventory: "n/a modules | n/a tests | n/a scripts | n/a docs | n/a workflows",
      "Language mix": "none",
    };

    expect(workspacePreviewToLines(preview).map((line) => line.text)).toEqual([
      "# Repo Snapshot",
      "## Git status",
      "Repo root: /Users/dhyana/dharma_swarm",
      "Branch: main",
      "Head: 95210b1",
      "Sync: origin/main | ahead 0 | behind 0",
      "Branch status: tracking origin/main in sync",
      "Upstream: origin/main",
      "Ahead: 0",
      "Behind: 0",
      "Branch sync preview: tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview: tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk: topology sab_canonical_repo_missing; high (552 local changes)",
      "Dirty: 0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure: high (552 local changes)",
      "Staged: 0",
      "Unstaged: 510",
      "Untracked: 42",
      "## Topology risk",
      "Topology warnings: 1 (sab_canonical_repo_missing)",
      "Topology warning severity: high",
      "Topology risk: sab_canonical_repo_missing",
      "Risk preview: sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview: sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview: 1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Topology status: degraded (1 warning, 2 peers)",
      "Primary warning: sab_canonical_repo_missing",
      "Primary peer drift: dharma_swarm track main...origin/main",
      "Primary topology peer: dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers: dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers: dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure: dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "## Hotspots",
      "Changed hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Changed paths: terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
      "Hotspot summary: change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | paths terminal/src/protocol.ts",
      "Lead hotspot preview: change terminal (274) | path terminal/src/protocol.ts",
      "Hotspot pressure preview: change terminal (274)",
      "Primary changed hotspot: terminal (274)",
      "Primary changed path: terminal/src/protocol.ts",
      "Primary file hotspot: dgc_cli.py (6908 lines)",
      "Primary dependency hotspot: none",
      "File hotspots: dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
      "Dependency hotspots: none",
      "## Inventory",
      "Inventory: n/a modules | n/a tests | n/a scripts | n/a docs | n/a workflows",
      "Language mix: none",
    ]);
  });
});

describe("workspaceSnapshotToPreview", () => {
  test("normalizes typed workspace payloads into repo previews", () => {
    const payload = workspaceSnapshotPayloadFromEvent({
      type: "workspace.snapshot.result",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "95210b1",
          staged: 0,
          unstaged: 510,
          untracked: 42,
          changed_hotspots: [
            {name: "terminal", count: 274},
            {name: ".dharma_psmv_hyperfile_branch", count: 142},
            {name: "dharma_swarm", count: 91},
          ],
          changed_paths: [
            "terminal/src/protocol.ts",
            "terminal/src/components/Sidebar.tsx",
            "terminal/tests/protocol.test.ts",
          ],
          sync: {
            summary: "origin/main | ahead 0 | behind 0",
            status: "tracking",
            upstream: "origin/main",
            ahead: 0,
            behind: 0,
          },
        },
        topology: {
          warnings: ["sab_canonical_repo_missing"],
          repos: [
            {
              domain: "dgc",
              name: "dharma_swarm",
              role: "canonical_core",
              canonical: true,
              path: "/Users/dhyana/dharma_swarm",
              exists: true,
              is_git: true,
              branch: "main...origin/main",
              head: "95210b1",
              dirty: true,
              modified_count: 510,
              untracked_count: 42,
            },
            {
              domain: "dgc",
              name: "dgc-core",
              role: "operator_shell",
              canonical: false,
              path: "/Users/dhyana/dgc-core",
              exists: true,
              is_git: false,
              branch: "n/a",
              dirty: null,
              modified_count: 0,
              untracked_count: 0,
            },
          ],
        },
        inventory: {
          python_modules: 501,
          python_tests: 494,
          scripts: 124,
          docs: 239,
          workflows: 1,
        },
        language_mix: [
          {suffix: ".py", count: 1125},
          {suffix: ".md", count: 511},
          {suffix: ".json", count: 91},
          {suffix: ".sh", count: 68},
        ],
        largest_python_files: [
          {path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208},
          {path: "dharma_swarm/thinkodynamic_director.py", lines: 5167, defs: 108, classes: 0, imports: 36},
        ],
        most_imported_modules: [
          {module: "dharma_swarm.models", count: 159},
          {module: "dharma_swarm.stigmergy", count: 35},
        ],
      },
    });

    expect(payload?.domain).toBe("workspace_snapshot");
    const preview = workspacePayloadToPreview(payload!);

    expect(preview["Repo root"]).toBe("/Users/dhyana/dharma_swarm");
    expect(preview.Branch).toBe("main");
    expect(preview["Primary changed path"]).toBe("terminal/src/protocol.ts");
    expect(preview["Topology risk"]).toBe("sab_canonical_repo_missing");
    expect(preview["Primary dependency hotspot"]).toBe("dharma_swarm.models | inbound 159");
    expect(preview.Inventory).toBe("501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows");
  });

  test("extracts explicit repo preview fields for the context sidebar", () => {
    const content = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 510 | untracked 42
Git hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)
Git changed paths: terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 494
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 510 | untracked 42
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

    const preview = workspaceSnapshotToPreview(content);

    expect(preview["Repo root"]).toBe("/Users/dhyana/dharma_swarm");
    expect(preview.Branch).toBe("main");
    expect(preview.Head).toBe("95210b1");
    expect(preview.Sync).toBe("origin/main | ahead 0 | behind 0");
    expect(preview["Branch status"]).toBe("tracking origin/main in sync");
    expect(preview.Upstream).toBe("origin/main");
    expect(preview.Ahead).toBe("0");
    expect(preview.Behind).toBe("0");
    expect(preview["Branch sync preview"]).toBe(
      "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
    );
    expect(preview["Repo risk preview"]).toBe(
      "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(preview["Repo risk"]).toBe("topology sab_canonical_repo_missing; high (552 local changes)");
    expect(preview.Dirty).toBe("0 staged, 510 unstaged, 42 untracked");
    expect(preview["Dirty pressure"]).toBe("high (552 local changes)");
    expect(preview.Staged).toBe("0");
    expect(preview.Unstaged).toBe("510");
    expect(preview.Untracked).toBe("42");
    expect(preview["Changed hotspots"]).toBe("terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)");
    expect(preview["Changed paths"]).toBe(
      "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
    );
    expect(preview["Hotspot summary"]).toBe(
      "change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35 | paths terminal/src/protocol.ts",
    );
    expect(preview["Lead hotspot preview"]).toBe(
      "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
    );
    expect(preview["Hotspot pressure preview"]).toBe("change terminal (274) | dep dharma_swarm.models | inbound 159");
    expect(preview["Topology warnings"]).toBe("1 (sab_canonical_repo_missing)");
    expect(preview["Topology warning severity"]).toBe("high");
    expect(preview["Topology status"]).toBe("degraded (1 warning, 2 peers)");
    expect(preview["Topology risk"]).toBe("sab_canonical_repo_missing");
    expect(preview["Risk preview"]).toBe(
      "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    );
    expect(preview["Topology preview"]).toBe(
      "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
    );
    expect(preview["Topology pressure preview"]).toBe("1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)");
    expect(preview["Primary warning"]).toBe("sab_canonical_repo_missing");
    expect(preview["Primary peer drift"]).toBe("dharma_swarm track main...origin/main");
    expect(preview["Primary topology peer"]).toBe("dharma_swarm (canonical_core, main...origin/main, dirty True)");
    expect(preview["Topology peer count"]).toBe("2");
    expect(preview["Peer drift markers"]).toBe("dharma_swarm track main...origin/main; dgc-core n/a");
    expect(preview["Topology pressure"]).toBe(
      "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
    );
    expect(preview["Primary changed hotspot"]).toBe("terminal (274)");
    expect(preview["Primary changed path"]).toBe("terminal/src/protocol.ts");
    expect(preview["Primary file hotspot"]).toBe("dgc_cli.py (6908 lines)");
    expect(preview["Primary dependency hotspot"]).toBe("dharma_swarm.models | inbound 159");
    expect(preview.Hotspots).toBe("dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)");
    expect(preview.Inventory).toBe("501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows");
    expect(preview["Language mix"]).toBe(".py: 1125; .md: 511; .json: 91; .sh: 68");
    expect(preview["Inbound hotspots"]).toBe("dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35");
  });

  test("keeps sync fields readable when upstream facts are unavailable", () => {
    const content = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: (detached)@95210b1 | staged 1 | unstaged 2 | untracked 3
Git hotspots: terminal (3)
Git changed paths: terminal/src/protocol.ts
Git sync: detached HEAD

## Topology
- dharma_swarm | role canonical_core | branch detached | dirty True | modified 2 | untracked 3`;

    const preview = workspaceSnapshotToPreview(content);

    expect(preview.Sync).toBe("detached HEAD");
    expect(preview["Branch status"]).toBe("detached HEAD");
    expect(preview.Upstream).toBe("detached HEAD");
    expect(preview.Ahead).toBe("n/a");
    expect(preview.Behind).toBe("n/a");
    expect(preview["Branch sync preview"]).toBe("detached HEAD | +n/a/-n/a | contained (6 local changes)");
    expect(preview["Repo risk preview"]).toBe("detached HEAD | stable | dharma_swarm (canonical_core, detached, dirty True)");
    expect(preview["Repo risk"]).toBe("contained (6 local changes)");
    expect(preview["Dirty pressure"]).toBe("contained (6 local changes)");
    expect(preview["Changed paths"]).toBe("terminal/src/protocol.ts");
    expect(preview["Topology status"]).toBe("connected (1 peer)");
    expect(preview["Topology peer count"]).toBe("1");
    expect(preview["Topology warning severity"]).toBe("stable");
    expect(preview["Primary peer drift"]).toBe("dharma_swarm detached");
    expect(preview["Primary topology peer"]).toBe("dharma_swarm (canonical_core, detached, dirty True)");
    expect(preview["Peer drift markers"]).toBe("dharma_swarm detached");
    expect(preview["Topology pressure"]).toBe("dharma_swarm Δ5 (2 modified, 3 untracked)");
    expect(preview["Risk preview"]).toBe("stable | dharma_swarm (canonical_core, detached, dirty True)");
    expect(preview["Topology preview"]).toBe(
      "stable | dharma_swarm (canonical_core, detached, dirty True) | dharma_swarm Δ5 (2 modified, 3 untracked)",
    );
    expect(preview["Topology pressure preview"]).toBe("stable | dharma_swarm Δ5 (2 modified, 3 untracked)");
    expect(preview["Primary warning"]).toBe("none");
    expect(preview["Hotspot pressure preview"]).toBe("change terminal (3)");
    expect(preview["Primary changed hotspot"]).toBe("terminal (3)");
    expect(preview["Primary changed path"]).toBe("terminal/src/protocol.ts");
  });
});

describe("runtimeSnapshotToLines", () => {
  test("extracts control preview details from runtime status text", () => {
    const content = `--- Runtime Control Plane ---
  Runtime DB: /Users/dhyana/.dharma/state/runtime.db
  Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0
  Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3
  Toolchain
    claude: /usr/local/bin/claude
    python3: /opt/homebrew/bin/python3
    node: /usr/local/bin/node`;

    const lines = runtimeSnapshotToLines(content).map((line) => line.text);

    expect(lines.slice(0, 9)).toEqual([
      "# Control Preview",
      "Runtime DB: /Users/dhyana/.dharma/state/runtime.db",
      "Session state: 18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state: 0 runs | 0 active runs",
      "Active runs detail: none",
      "Context state: 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Recent operator actions: none",
      "Runtime activity: Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state: Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
    ]);
    expect(lines).toContain("Toolchain: claude, python3, node");
    expect(lines).toContain("Alerts: none");
  });

  test("appends durable loop and verification state when supervisor data is present", () => {
    const content = `--- Runtime Control Plane ---
  Runtime DB: /Users/dhyana/.dharma/state/runtime.db
  Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0
  Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3`;

    const lines = runtimeSnapshotToLines(content, {
      stateDir: "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
      cycle: 3,
      runStatus: "running",
      tasksTotal: 3,
      tasksPending: 1,
      activeTaskId: "terminal-control-surface",
      lastResultStatus: "in_progress",
      acceptance: "pass",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance ok"],
      continueRequired: false,
      nextTask: "Route /runtime and /dashboard to more precise panes.",
      updatedAt: "2026-03-31T22:46:35.466340+00:00",
    }, new Date("2026-04-01T00:00:00Z")).map((line) => line.text);

    expect(lines).toContain("Loop state: cycle 3 running");
    expect(lines).toContain("Task progress: 2 done, 1 pending of 3");
    expect(lines).toContain("Active task: terminal-control-surface");
    expect(lines).toContain("Last result: in_progress / pass");
    expect(lines).toContain(
      "Verification summary: tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(lines).toContain(
      "Verification checks: tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
    );
    expect(lines).toContain(
      "Control pulse preview: fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(lines).toContain("Loop decision: ready to stop");
  });
});

describe("runtimePreviewToLines", () => {
  test("renders the control transcript from preview fields alone", () => {
    const lines = runtimePreviewToLines({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state": "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      Toolchain: "claude, python3, node",
      Alerts: "none",
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Verification summary": "tsc=ok | py_compile_bridge=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok",
      "Verification status": "all 2 checks passing",
      "Verification passing": "tsc, py_compile_bridge",
      "Verification failing": "none",
      "Loop decision": "ready to stop",
      "Next task": "Route /runtime and /dashboard to more precise panes.",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
    }, null, new Date("2026-04-01T00:00:00Z")).map((line) => line.text);

    expect(lines).toEqual([
      "# Control Preview",
      "Runtime DB: /Users/dhyana/.dharma/state/runtime.db",
      "Session state: 18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state: 0 runs | 0 active runs",
      "Active runs detail: none",
      "Context state: 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Recent operator actions: none",
      "Runtime activity: Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state: Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      "Toolchain: claude, python3, node",
      "Alerts: none",
      "Control pulse preview: fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok",
      "",
      "Loop state: cycle 3 running",
      "Task progress: 2 done, 1 pending of 3",
      "Active task: terminal-control-surface",
      "Result status: in_progress",
      "Acceptance: pass",
      "Last result: in_progress / pass",
      "Verification summary: tsc=ok | py_compile_bridge=ok",
      "Verification checks: tsc ok; py_compile_bridge ok",
      "Verification status: all 2 checks passing",
      "Verification passing: tsc, py_compile_bridge",
      "Verification failing: none",
      "Verification bundle: tsc=ok | py_compile_bridge=ok",
      "Loop decision: ready to stop",
      "Next task: Route /runtime and /dashboard to more precise panes.",
      "Updated: 2026-03-31T22:46:35.466340+00:00",
      "Durable state: /Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
    ]);
  });
});

describe("runtimeSnapshotToPreview", () => {
  test("captures runtime and durable control fields for sidebar preview", () => {
    const content = `--- Runtime Control Plane ---
  Runtime DB: /Users/dhyana/.dharma/state/runtime.db
  Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0
  Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3
  Toolchain
    claude: /usr/local/bin/claude
    python3: /opt/homebrew/bin/python3
    node: /usr/local/bin/node`;

    const preview = runtimeSnapshotToPreview(content, {
      stateDir: "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260331T223607Z/state",
      cycle: 4,
      runStatus: "running",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "complete",
      acceptance: "fail",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Promote repo snapshot preview into dedicated rows inside the repo pane.",
      updatedAt: "2026-04-01T00:00:00Z",
    }, new Date("2026-04-01T04:00:00Z"));

    expect(preview["Runtime DB"]).toBe("/Users/dhyana/.dharma/state/runtime.db");
    expect(preview["Session state"]).toBe("18 sessions | 0 claims | 0 active claims | 0 acked claims");
    expect(preview["Run state"]).toBe("0 runs | 0 active runs");
    expect(preview["Context state"]).toBe("7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions");
    expect(preview["Runtime activity"]).toContain("Sessions=18");
    expect(preview["Artifact state"]).toContain("Artifacts=7");
    expect(preview.Toolchain).toBe("claude, python3, node");
    expect(preview["Loop state"]).toBe("cycle 4 running");
    expect(preview["Task progress"]).toBe("3 done, 1 pending of 4");
    expect(preview["Active task"]).toBe("terminal-repo-pane");
    expect(preview["Result status"]).toBe("complete");
    expect(preview.Acceptance).toBe("fail");
    expect(preview["Last result"]).toBe("complete / fail");
    expect(preview["Verification summary"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(preview["Verification status"]).toBe("1 failing, 3/4 passing");
    expect(preview["Verification passing"]).toBe("tsc, py_compile_bridge, bridge_snapshots");
    expect(preview["Verification failing"]).toBe("cycle_acceptance");
    expect(preview["Loop decision"]).toBe("continue required");
    expect(preview.Updated).toBe("2026-04-01T00:00:00Z");
    expect(preview["Runtime freshness"]).toBe(
      "cycle 4 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(preview["Control pulse preview"]).toBe(
      "fresh | complete / fail | cycle 4 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(preview["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    );
  });

  test("omits unknown metric fragments when snapshots only report aggregate counts", () => {
    const content = `--- Runtime Control Plane ---
  Runtime DB: /Users/dhyana/.dharma/state/runtime.db
  Sessions=23  Runs=3  ActiveRuns=1
  Artifacts=9  ContextBundles=2
  Toolchain
    python3: /opt/homebrew/bin/python3`;

    const preview = runtimeSnapshotToPreview(content);
    const lines = runtimePreviewToLines(preview).map((line) => line.text);

    expect(preview["Session state"]).toBe("23 sessions");
    expect(preview["Run state"]).toBe("3 runs | 1 active runs");
    expect(preview["Context state"]).toBe("9 artifacts | 2 context bundles");
    expect(preview["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 23 sessions | 3 runs | 1 active runs | 9 artifacts | 2 context bundles",
    );
    expect(lines).toContain("Session state: 23 sessions");
    expect(lines).toContain("Run state: 3 runs | 1 active runs");
    expect(lines).toContain("Context state: 9 artifacts | 2 context bundles");
    expect(lines.some((line) => line.includes("n/a"))).toBe(false);
  });
});
