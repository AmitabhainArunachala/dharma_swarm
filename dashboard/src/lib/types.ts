/**
 * DHARMA COMMAND -- TypeScript types matching the FastAPI backend models.
 * These types match the `data` field unwrapped from ApiResponse.
 */

// ---------------------------------------------------------------------------
// Generic API wrapper (raw response before unwrap)
// ---------------------------------------------------------------------------

export interface ApiResponse<T> {
  status: string;
  data: T;
  error: string;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Chat status (GET /api/chat/status)
// ---------------------------------------------------------------------------

export interface ChatStatusOut {
  ready: boolean;
  model: string;
  provider: string;
  tools: number;
  max_tool_rounds: number;
  max_tokens: number;
  timeout_seconds: number;
  tool_result_max_chars: number;
  history_message_limit: number;
  temperature: number;
  persistent_sessions?: boolean;
  chat_ws_path_template?: string;
  default_profile_id?: string;
  profiles?: ChatProfileOut[];
}

export interface ChatProfileOut {
  id: string;
  label: string;
  provider: string;
  model: string;
  accent: string;
  summary: string;
}

// ---------------------------------------------------------------------------
// Swarm overview (GET /api/overview)
// ---------------------------------------------------------------------------

export interface SwarmOverview {
  agent_count: number;
  task_count: number;
  tasks_pending: number;
  tasks_running: number;
  tasks_completed: number;
  tasks_failed: number;
  mean_fitness: number;
  uptime_seconds: number;
  health_status: string;
  stigmergy_density: number;
  evolution_entries: number;
}

// ---------------------------------------------------------------------------
// Truth modules (GET /api/modules)
// ---------------------------------------------------------------------------

export interface ModuleProcessOut {
  pid: number;
  live: boolean;
  source: string;
  command: string | null;
  observed_paths: string[];
}

export interface ModuleProjectOut {
  label: string;
  path: string;
  exists: boolean;
  kind: string;
  modified_at: string | null;
}

export interface ModuleWireOut {
  direction: string;
  target: string;
  detail: string;
}

export interface ModuleHistoryOut {
  timestamp: string | null;
  title: string;
  detail: string;
  source: string;
  status: string;
}

export interface ModuleSalientOut {
  kind: string;
  title: string;
  detail: string;
  path: string | null;
  timestamp: string | null;
  reason: string;
  score: number;
}

export interface ModuleTruthOut {
  id: string;
  name: string;
  status: string;
  live: boolean;
  summary: string;
  status_reason: string;
  last_activity: string | null;
  metrics: Record<string, string>;
  processes: ModuleProcessOut[];
  projects: ModuleProjectOut[];
  wiring: ModuleWireOut[];
  history: ModuleHistoryOut[];
  salient: ModuleSalientOut[];
}

// ---------------------------------------------------------------------------
// Agents (GET /api/agents)
// ---------------------------------------------------------------------------

export interface AgentOut {
  id: string;
  name: string;
  role: string;
  status: string;
  current_task: string | null;
  started_at: string | null;
  last_heartbeat: string | null;
  turns_used: number;
  tasks_completed: number;
  provider: string;
  model: string;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Fleet (GET /api/fleet/config)
// ---------------------------------------------------------------------------

export interface FleetAgentConfig {
  name: string;
  role: string;
  provider: string;
  model: string;
  display_name: string;
  model_display_name: string;
  tier: string;
  strengths: string[];
  available: boolean;
  tool_name: string;
  thread: string;
}

// ---------------------------------------------------------------------------
// Provider Status (GET /api/providers/status)
// ---------------------------------------------------------------------------

export interface ProviderStatusOut {
  provider: string;
  available: boolean;
  model_count?: number;
  availability_kind?: string;
}

// ---------------------------------------------------------------------------
// Agent Detail Extended (GET /api/agents/{id}/detail)
// ---------------------------------------------------------------------------

export interface AgentConfigOut {
  provider: string;
  model: string;
  role: string;
  thread: string;
  display_name: string;
  tier: string;
  strengths: string[];
}

export interface AgentCostOut {
  daily_spent: number;
  weekly_spent: number;
  budget_status: string;
}

export interface CoreFileOut {
  file_path: string;
  count: number;
  last_touch: string;
  salience: number;
}

export interface AvailableModelOut {
  provider: string;
  model_id: string;
  label: string;
  tier: string;
  strengths: string[];
}

export interface ModelVerificationOut {
  status: string;
  route: string;
  latency_ms: number;
  verified_at: string;
  response_preview: string;
  error: string;
}

export interface TopModelOut {
  id: string;
  display_name: string;
  ui_label: string;
  custom_label: string;
  short_name: string;
  provider: string;
  routes: string[];
  available_routes: string[];
  available: boolean;
  tier: string;
  strengths: string[];
  max_context: number;
  cost_per_mtok: number;
  notes: string;
  aliases: string[];
  source: string;
  power_rank: number | null;
  rank: number;
  fallbacks: string[];
  docs_url: string;
  provider_url: string;
  profile_updated_at: string;
  verification: ModelVerificationOut;
}

export interface ModelProfileOut {
  model_id: string;
  display_name: string;
  custom_label: string;
  short_name: string;
  ui_label: string;
  docs_url: string;
  provider_url: string;
  updated_at: string;
}

export interface VerifyTop10Out {
  verified_at: string;
  ok_count: number;
  results: Array<{
    model_id: string;
    display_name: string;
    status: string;
    route: string;
    latency_ms: number;
    verified_at: string;
    response_preview: string;
    error: string;
  }>;
}

export interface FitnessHistoryEntry {
  name: string;
  success_rate: number;
  avg_latency: number;
  avg_quality: number;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  speed_score: number;
  composite_fitness: number;
  computed_at: string;
}

export interface TaskLogEntry {
  task: string;
  success: boolean;
  tokens: number;
  latency_ms: number;
  cost_usd: number;
  timestamp: string;
  response_preview: string;
}

// ---------------------------------------------------------------------------
// Tasks (GET /api/commands/tasks)
// ---------------------------------------------------------------------------

export interface TaskOut {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  result: string | null;
}

// ---------------------------------------------------------------------------
// Health (GET /api/health)
// ---------------------------------------------------------------------------

export interface AgentHealthOut {
  agent_name: string;
  total_actions: number;
  failures: number;
  success_rate: number;
  last_seen: string | null;
  status: string;
}

export interface AnomalyOut {
  id: string;
  detected_at: string;
  anomaly_type: string;
  severity: string;
  description: string;
  related_traces: string[];
}

export interface HealthOut {
  overall_status: string;
  agent_health: AgentHealthOut[];
  anomalies: AnomalyOut[];
  total_traces: number;
  traces_last_hour: number;
  failure_rate: number;
  mean_fitness: number | null;
}

// ---------------------------------------------------------------------------
// Evolution (GET /api/evolution/*)
// ---------------------------------------------------------------------------

export interface FitnessOut {
  correctness: number;
  dharmic_alignment: number;
  performance: number;
  utilization: number;
  economic_value: number;
  elegance: number;
  efficiency: number;
  safety: number;
  weighted: number;
}

export interface ArchiveEntryOut {
  id: string;
  timestamp: string;
  parent_id: string | null;
  component: string;
  change_type: string;
  description: string;
  fitness: FitnessOut;
  status: string;
  gates_passed: string[];
  gates_failed: string[];
  agent_id: string;
  model: string;
}

export interface FitnessTrendPoint {
  timestamp: string;
  fitness: number;
  correctness: number;
  elegance: number;
  component: string;
  id: string;
}

export interface DagNode {
  id: string;
  type: string;
  data: {
    label: string;
    fitness: number;
    status: string;
    change_type: string;
    timestamp: string;
  };
  position: { x: number; y: number };
}

export interface DagEdge {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
  label?: string;
}

export interface DagData {
  nodes: DagNode[];
  edges: DagEdge[];
}

// ---------------------------------------------------------------------------
// Traces (GET /api/commands/traces)
// ---------------------------------------------------------------------------

export interface TraceOut {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
  state: string;
  parent_id: string | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Ontology (GET /api/ontology/*)
// ---------------------------------------------------------------------------

export interface OntologyTypeOut {
  name: string;
  description: string;
  telos_alignment: number;
  shakti: string;
  property_count: number;
  link_count: number;
  action_count: number;
  icon: string;
}

export interface PropertyOut {
  name: string;
  property_type: string;
  required: boolean;
  description: string;
  searchable: boolean;
}

export interface LinkDefOut {
  name: string;
  source_type: string;
  target_type: string;
  cardinality: string;
  description: string;
}

export interface ActionDefOut {
  name: string;
  description: string;
  requires_approval: boolean;
  telos_gates: string[];
  is_deterministic: boolean;
}

export interface OntologyDetailOut {
  name: string;
  description: string;
  properties: PropertyOut[];
  links: LinkDefOut[];
  actions: ActionDefOut[];
  security_level: string;
  telos_alignment: number;
  shakti: string;
}

export interface OntologyGraphData {
  nodes: {
    id: string;
    type: string;
    data: {
      label: string;
      description: string;
      propertyCount: number;
      shakti: string;
      telos: number;
      icon: string;
      actionCount?: number;
      linkCount?: number;
      runtimeCount?: number;
      zone?: string;
    };
    position: { x: number; y: number };
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    label: string;
    data: { cardinality: string };
  }[];
}

// ---------------------------------------------------------------------------
// Lineage (GET /api/lineage/*)
// ---------------------------------------------------------------------------

export interface LineageEdgeOut {
  edge_id: string;
  task_id: string;
  input_artifacts: string[];
  output_artifacts: string[];
  agent: string;
  operation: string;
  timestamp: string;
}

export interface ProvenanceOut {
  artifact_id: string;
  chain: LineageEdgeOut[];
  root_sources: string[];
  depth: number;
}

export interface ImpactOut {
  root_artifact: string;
  affected_artifacts: string[];
  affected_tasks: string[];
  depth: number;
  total_descendants: number;
}

// ---------------------------------------------------------------------------
// Stigmergy (GET /api/stigmergy/*)
// ---------------------------------------------------------------------------

export interface StigmergyMarkOut {
  id: string;
  timestamp: string;
  agent: string;
  file_path: string;
  action: string;
  observation: string;
  salience: number;
  connections: string[];
}

export interface HeatmapCell {
  file_path: string;
  hour: number;
  count: number;
  avg_salience: number;
}

export interface HotPath {
  path: string;
  count: number;
}

// ---------------------------------------------------------------------------
// WebSocket events
// ---------------------------------------------------------------------------

export interface WsEvent<T = unknown> {
  event: string;
  data?: T;
  agents?: AgentOut[];
  agent?: AgentOut;
  agent_id?: string;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export interface NavSection {
  label: string;
  level: number;
  items: NavItem[];
}

export interface NavItem {
  label: string;
  href: string;
  icon: string;
  level: number;
  badge?: string | number;
}
