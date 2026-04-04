export type PaneKind =
  | "chat"
  | "commands"
  | "agents"
  | "models"
  | "evolution"
  | "thinking"
  | "tools"
  | "timeline"
  | "sessions"
  | "approvals"
  | "mission"
  | "runtime"
  | "repo"
  | "ontology"
  | "control";

export type SidebarMode = "toc" | "context" | "help";

export type TranscriptLine = {
  id: string;
  kind: "system" | "assistant" | "thinking" | "tool" | "error" | "user";
  text: string;
  timestamp?: string;
};

export type TabPreview = Record<string, string>;

export type OutlineItem = {
  id: string;
  label: string;
  depth: 1 | 2 | 3;
  targetTabId: string;
};

export type TabSpec = {
  id: string;
  title: string;
  kind: PaneKind;
  closable?: boolean;
  lines: TranscriptLine[];
  preview?: TabPreview;
};

export type ActivityKind = "status" | "thinking" | "pivot" | "tool" | "approval" | "task" | "error";

export type ActivityVisibilityMode = "compact" | "expanded";

export type ActivityPhase = "queued" | "running" | "complete" | "failed";

export type ActivityEntry = {
  id: string;
  kind: ActivityKind;
  phase: ActivityPhase;
  title: string;
  summary?: string;
  detail?: string[];
  raw?: Record<string, unknown>;
  timestamp?: string;
  correlationId?: string;
};

export type ActivityFeedState = {
  entries: ActivityEntry[];
  visibilityMode: ActivityVisibilityMode;
  showRaw: boolean;
};

export type BridgeStatus = "booting" | "connected" | "degraded" | "offline";

export type RouteState = "ready" | "degraded" | "slow" | "unavailable" | "invalid";

export type SupervisorControlState = {
  stateDir: string;
  cycle: number | null;
  runStatus: string;
  tasksTotal: number | null;
  tasksPending: number | null;
  activeTaskId: string;
  lastResultStatus: string;
  acceptance: string;
  verificationSummary: string;
  verificationChecks: string[];
  verificationStatus: string;
  verificationPassing: string;
  verificationFailing: string;
  verificationBundle: string;
  verificationUpdatedAt: string;
  continueRequired: boolean | null;
  nextTask: string;
  updatedAt: string;
};

export type CanonicalSession = {
  session_id: string;
  provider_id: string;
  model_id: string;
  cwd: string;
  created_at: string;
  updated_at: string;
  status: string;
  parent_session_id?: string | null;
  branch_label?: string | null;
  worktree_path?: string | null;
  summary?: string | null;
  pinned_context?: string[];
  compacted_from_session_ids?: string[];
  metadata?: Record<string, unknown>;
};

export type CanonicalRoutingDecision = {
  route_id: string;
  provider_id: string;
  model_id: string;
  strategy: string;
  reason: string;
  fallback_chain: string[];
  degraded: boolean;
  metadata: Record<string, unknown>;
};

export type CanonicalRuntimeSnapshot = {
  snapshot_id: string;
  created_at: string;
  repo_root: string;
  runtime_db?: string | null;
  health: string;
  bridge_status: string;
  active_session_count: number;
  active_run_count: number;
  artifact_count: number;
  context_bundle_count: number;
  anomaly_count: number;
  verification_status: string;
  verification_summary?: string | null;
  verification_bundle?: string | null;
  verification_checks?: string | null;
  verification_passing?: string | null;
  verification_failing?: string | null;
  verification_receipt?: string | null;
  verification_updated_at?: string | null;
  loop_state?: string | null;
  loop_decision?: string | null;
  task_progress?: string | null;
  result_status?: string | null;
  acceptance?: string | null;
  last_result?: string | null;
  updated_at?: string | null;
  durable_state?: string | null;
  runtime_summary?: string | null;
  runtime_freshness?: string | null;
  next_task?: string | null;
  active_task?: string | null;
  worktree_count?: number | null;
  summary?: string | null;
  warnings: string[];
  metrics: Record<string, string>;
  metadata: Record<string, unknown>;
};

export type RuntimeSnapshotPayload = {
  version: "v1";
  domain: "runtime_snapshot";
  snapshot: CanonicalRuntimeSnapshot;
};

export type RoutingDecisionPayload = {
  version: "v1";
  domain: "routing_decision";
  decision: CanonicalRoutingDecision;
  strategies: string[];
  targets: Array<Record<string, unknown>>;
  fallback_targets: Array<Record<string, unknown>>;
};

export type AgentRoutesPayload = {
  version: "v1";
  domain: "agent_routes";
  routes: Array<Record<string, unknown>>;
  openclaw: Record<string, unknown>;
  subagent_capabilities: string[];
};

export type WorkspaceChangedHotspot = {
  name: string;
  count: number;
};

export type WorkspaceSyncState = {
  summary: string;
  status: string;
  upstream?: string | null;
  ahead?: number | null;
  behind?: number | null;
};

export type WorkspaceGitState = {
  branch: string;
  head: string;
  staged?: number | null;
  unstaged?: number | null;
  untracked?: number | null;
  changed_hotspots: WorkspaceChangedHotspot[];
  changed_paths: string[];
  sync: WorkspaceSyncState;
};

export type WorkspaceTopologyRepo = {
  domain: string;
  name: string;
  role: string;
  canonical: boolean;
  path: string;
  exists: boolean;
  is_git: boolean;
  branch?: string | null;
  head?: string | null;
  dirty?: boolean | null;
  modified_count: number;
  untracked_count: number;
};

export type WorkspaceInventory = {
  python_modules?: number | null;
  python_tests?: number | null;
  scripts?: number | null;
  docs?: number | null;
  workflows?: number | null;
};

export type WorkspacePathMetric = {
  path: string;
  lines: number;
  defs: number;
  classes: number;
  imports: number;
};

export type WorkspaceModuleCoupling = {
  module: string;
  count: number;
};

export type WorkspaceSnapshotPayload = {
  version: "v1";
  domain: "workspace_snapshot";
  repo_root: string;
  git: WorkspaceGitState;
  topology: {
    warnings: string[];
    repos: WorkspaceTopologyRepo[];
    preview?: string | null;
    pressure_preview?: string | null;
  };
  inventory: WorkspaceInventory;
  language_mix: Array<{suffix: string; count: number}>;
  largest_python_files: WorkspacePathMetric[];
  most_imported_modules: WorkspaceModuleCoupling[];
};

export type CanonicalEventEnvelope = {
  event_id: string;
  event_type: string;
  source: string;
  audience: string;
  transport: string;
  session_id?: string | null;
  created_at: string;
  payload?: Record<string, unknown>;
  entity_refs?: Array<Record<string, unknown>>;
  correlation_id?: string | null;
  raw?: Record<string, unknown> | null;
};

export type SessionCatalogEntry = {
  session: CanonicalSession;
  replay_ok: boolean;
  replay_issues: string[];
  provider_session_id?: string | null;
  total_turns: number;
  total_cost_usd: number;
};

export type SessionCatalogPayload = {
  count: number;
  sessions: SessionCatalogEntry[];
};

export type SessionCompactionPreview = {
  event_count: number;
  by_type: Record<string, number>;
  compactable_ratio: number;
  protected_event_types: string[];
  recent_event_types: string[];
};

export type SessionDetailPayload = {
  session: CanonicalSession;
  replay_ok: boolean;
  replay_issues: string[];
  compaction_preview: SessionCompactionPreview;
  recent_events: CanonicalEventEnvelope[];
  approval_history?: PermissionHistoryPayload;
};

export type CanonicalPermissionDecision = {
  version: "v1";
  domain: "permission_decision";
  action_id: string;
  tool_name: string;
  risk: string;
  decision: string;
  rationale: string;
  policy_source: string;
  requires_confirmation: boolean;
  command_prefix?: string | null;
  metadata: Record<string, unknown>;
};

export type ApprovalResolutionKind = "approved" | "denied" | "dismissed" | "resolved";

export type ApprovalOutcomeKind =
  | "runtime_recorded"
  | "runtime_record_failed"
  | "runtime_applied"
  | "runtime_rejected"
  | "runtime_expired";

export type ApprovalEntryStatus = "pending" | ApprovalResolutionKind | ApprovalOutcomeKind | "observed";

export type CanonicalPermissionResolution = {
  version: "v1";
  domain: "permission_resolution";
  action_id: string;
  resolution: ApprovalResolutionKind;
  resolved_at: string;
  actor: string;
  summary: string;
  note?: string | null;
  enforcement_state: string;
  metadata: Record<string, unknown>;
};

export type CanonicalPermissionOutcome = {
  version: "v1";
  domain: "permission_outcome";
  action_id: string;
  outcome: ApprovalOutcomeKind;
  outcome_at: string;
  source: string;
  summary: string;
  metadata: Record<string, unknown>;
};

export type PermissionHistoryEntry = {
  action_id: string;
  decision: CanonicalPermissionDecision;
  resolution?: CanonicalPermissionResolution | null;
  outcome?: CanonicalPermissionOutcome | null;
  first_seen_at: string;
  last_seen_at: string;
  seen_count: number;
  pending: boolean;
  status: ApprovalEntryStatus;
};

export type PermissionHistoryPayload = {
  version: "v1";
  domain: "permission_history";
  count: number;
  entries: PermissionHistoryEntry[];
};

export type ApprovalQueueEntry = {
  decision: CanonicalPermissionDecision;
  status: ApprovalEntryStatus;
  firstSeenAt: string;
  lastSeenAt: string;
  lastSourceEventType: string;
  seenCount: number;
  pending: boolean;
  resolution?: CanonicalPermissionResolution;
  outcome?: CanonicalPermissionOutcome;
};

export type ApprovalQueueState = {
  selectedActionId?: string;
  entriesByActionId: Record<string, ApprovalQueueEntry>;
  order: string[];
  historyBacked: boolean;
  lastHistorySyncAt?: string;
};

export type SessionPaneState = {
  catalog?: SessionCatalogPayload;
  selectedSessionId?: string;
  detailsBySessionId: Record<string, SessionDetailPayload>;
};

export type ContinuityMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  source: "session_detail" | "working_set" | "prompt";
};

export type SessionContinuityState = {
  activeSessionId?: string;
  resumeSessionId?: string;
  activeRouteId?: string;
  continuityMode: "fresh" | "resume";
  boundedHistory: ContinuityMessage[];
  historyLimit: number;
  compactionPolicy: {
    eventCount: number;
    compactableRatio: number;
    protectedEventTypes: string[];
    recentEventTypes: string[];
  };
  compactedSummary?: string;
};

export type SurfaceAuthorityState = {
  repo: boolean;
  control: boolean;
  sessions: boolean;
  approvals: boolean;
  models: boolean;
  agents: boolean;
};

export type RouteTarget = {
  alias: string;
  label: string;
  provider: string;
  model: string;
  routeId: string;
  routeState: RouteState;
  availabilityReason?: string;
  selectable: boolean;
};

export type ModelTarget = RouteTarget;

export type UIModeOverlay =
  | {kind: "none"}
  | {kind: "modelPicker"; selectedIndex: number; returnTabId: string}
  | {kind: "paneSwitcher"; selectedIndex: number};

export type UIModeState = {
  activeTabId: string;
  activeOverlay: UIModeOverlay;
  sidebarVisible: boolean;
  sidebarMode: SidebarMode;
  focusedPaneId: string;
  compactMode: boolean;
};

export type RoutePolicyState = {
  routeId: string;
  provider: string;
  model: string;
  strategy: string;
  routeState: RouteState;
  selectable: boolean;
  availabilityReason?: string;
  defaultRouteId?: string;
  fallbackChain: string[];
  lastConfirmedRouteId?: string;
  activeLabel?: string;
  targets: RouteTarget[];
};

export type CanonicalExecutionEventKind =
  | "user_prompt"
  | "assistant_text"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "approval"
  | "task"
  | "command"
  | "status"
  | "error";

export type CanonicalExecutionEvent = {
  id: string;
  sourceEventType: string;
  kind: CanonicalExecutionEventKind;
  phase: ActivityPhase;
  title: string;
  summary?: string;
  detail?: string[];
  content?: string;
  timestamp?: string;
  correlationId?: string;
  raw?: Record<string, unknown>;
};

export type AppState = {
  uiMode: UIModeState;
  bridgeStatus: BridgeStatus;
  routePolicy: RoutePolicyState;
  executionEventLog: CanonicalExecutionEvent[];
  chatTraceLines: TranscriptLine[];
  sessionContinuity: SessionContinuityState;
  prompt: string;
  tabs: TabSpec[];
  paneScrollOffsets: Record<string, number>;
  paneFocusIndices: Record<string, number>;
  liveRepoPreview?: TabPreview;
  liveControlPreview?: TabPreview;
  authoritativeSurfaces: SurfaceAuthorityState;
  approvalPane: ApprovalQueueState;
  sessionPane: SessionPaneState;
  activityFeed: ActivityFeedState;
  outline: OutlineItem[];
  statusLine: string;
  footerHint: string;
};

export type AppAction =
  | {type: "batch"; actions: AppAction[]}
  | {type: "prompt.append"; value: string}
  | {type: "prompt.backspace"}
  | {type: "prompt.clear"}
  | {type: "state.replace"; state: AppState}
  | {type: "bridge.status"; status: BridgeStatus}
  | {type: "bridge.config"; provider: string; model: string; strategy?: string}
  | {type: "route.policy.set"; policy: RoutePolicyState}
  | {type: "execution.events.ingest"; events: CanonicalExecutionEvent[]}
  | {type: "ui.compact.set"; compact: boolean}
  | {type: "modelPicker.open"; returnTabId?: string}
  | {type: "modelPicker.close"}
  | {type: "modelPicker.move"; direction: 1 | -1}
  | {type: "modelPicker.set"; index: number}
  | {type: "paneSwitcher.open"}
  | {type: "paneSwitcher.close"}
  | {type: "paneSwitcher.set"; index: number}
  | {type: "status.set"; value: string}
  | {type: "footer.set"; value: string}
  | {type: "sidebar.toggle"}
  | {type: "sidebar.mode"; mode: SidebarMode}
  | {type: "tab.activate"; tabId: string}
  | {type: "tab.cycle"; direction: 1 | -1}
  | {type: "pane.scroll"; tabId: string; delta: number; maxOffset: number}
  | {type: "pane.scroll.reset"; tabId: string}
  | {type: "pane.focus.set"; tabId: string; index: number}
  | {type: "tab.ensure"; tab: TabSpec}
  | {type: "tab.close"; tabId: string}
  | {type: "tab.append"; tabId: string; lines: TranscriptLine[]}
  | {
      type: "tab.replace";
      tabId: string;
      lines: TranscriptLine[];
      preview?: TabPreview;
    }
  | {type: "live.repo.set"; preview?: TabPreview}
  | {type: "live.control.set"; preview?: TabPreview}
  | {type: "surface.truth.reset"}
  | {type: "surface.truth.mark"; surface: keyof SurfaceAuthorityState}
  | {type: "approval.history.set"; approvalPane: ApprovalQueueState}
  | {type: "approval.decision.set"; decision: CanonicalPermissionDecision; sourceEventType?: string; lastSeenAt?: string}
  | {type: "approval.resolution.set"; resolution: CanonicalPermissionResolution; sourceEventType?: string}
  | {type: "approval.outcome.set"; outcome: CanonicalPermissionOutcome; sourceEventType?: string}
  | {type: "approval.select"; actionId: string}
  | {type: "session.catalog.set"; catalog: SessionCatalogPayload; selectedSessionId?: string}
  | {type: "session.detail.set"; detail: SessionDetailPayload}
  | {type: "session.continuity.set"; continuity: SessionContinuityState}
  | {type: "session.select"; sessionId: string}
  | {type: "activity.ingest"; entries: ActivityEntry[]}
  | {type: "activity.visibility.toggle"}
  | {type: "activity.raw.toggle"}
  | {type: "outline.set"; outline: OutlineItem[]};
