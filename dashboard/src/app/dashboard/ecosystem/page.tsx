"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Edge,
  type Node,
  MarkerType,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  FileCode2,
  Network,
  Play,
  Search,
  Sparkles,
  Eye,
  MessageSquare,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { DharmaSocket } from "@/lib/ws";
import { colors } from "@/lib/theme";
import type { AgentOut, FleetAgentConfig, StigmergyMarkOut, TraceOut, WsEvent } from "@/lib/types";

interface GraphNodeOut {
  id: string;
  label: string;
  salience: number;
  count: number;
}

interface GraphEdgeOut {
  source: string;
  target: string;
  agent?: string;
}

interface GraphOut {
  nodes: GraphNodeOut[];
  edges: GraphEdgeOut[];
}

interface SemanticCluster {
  id: string;
  label: string;
  count: number;
  files: string[];
}

interface AgentActivityEvent {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
  state: string;
  commentary: string;
  file_path?: string | null;
}

function clusterLabel(path: string): string {
  const parts = path.split("/").filter(Boolean);
  if (parts.length === 0) return "root";
  if (parts[0] === "dashboard" && parts[1] === "src") return `dashboard/${parts[2] ?? "src"}`;
  if (parts[0] === "api") return `api/${parts[1] ?? "root"}`;
  if (parts[0] === "dharma_swarm") return `dharma_swarm/${parts[1] ?? "core"}`;
  return parts.slice(0, Math.min(2, parts.length)).join("/");
}

function fileNodeColor(salience: number): string {
  if (salience >= 0.8) return colors.bengara;
  if (salience >= 0.55) return colors.kinpaku;
  if (salience >= 0.3) return colors.aozora;
  return colors.sumi[600];
}

function summarizeTrace(trace: TraceOut): string {
  const metadata = trace.metadata ?? {};
  const filePath =
    (metadata.file_path as string | undefined) ??
    (metadata.path as string | undefined) ??
    (metadata.target_file as string | undefined);
  const target = filePath ? ` on ${filePath}` : "";
  return `${trace.agent} ${trace.action}${target} [${trace.state}]`;
}

export default function EcosystemPage() {
  const qc = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [agentCommentary, setAgentCommentary] = useState("");
  const [graphExpanded, setGraphExpanded] = useState(false);
  const [search, setSearch] = useState("");

  const { data: graph, isLoading: graphLoading } = useQuery<GraphOut>({
    queryKey: ["ecosystem-graph"],
    queryFn: () => apiFetch<GraphOut>("/api/stigmergy/graph"),
    refetchInterval: 15_000,
  });

  const { data: marks = [] } = useQuery<StigmergyMarkOut[]>({
    queryKey: ["ecosystem-marks"],
    queryFn: () => apiFetch<StigmergyMarkOut[]>("/api/stigmergy/marks?limit=120"),
    refetchInterval: 10_000,
  });

  const { data: traces = [] } = useQuery<TraceOut[]>({
    queryKey: ["ecosystem-traces"],
    queryFn: () => apiFetch<TraceOut[]>("/api/commands/traces?limit=60"),
    refetchInterval: 8_000,
  });

  const { data: agents = [] } = useQuery<AgentOut[]>({
    queryKey: ["agents"],
    queryFn: () => apiFetch<AgentOut[]>("/api/agents"),
    refetchInterval: 5_000,
  });

  const { data: fleet = [] } = useQuery<FleetAgentConfig[]>({
    queryKey: ["fleet-config"],
    queryFn: () => apiFetch<FleetAgentConfig[]>("/api/fleet/config"),
    refetchInterval: 10_000,
  });

  useEffect(() => {
    const socket = new DharmaSocket("agents", {
      onMessage: (event: WsEvent) => {
        if (event.event === "agents_update") {
          qc.invalidateQueries({ queryKey: ["agents"] });
        }
      },
    });
    socket.connect();
    return () => socket.close();
  }, [qc]);

  const activityFeed = useMemo(
    () =>
      traces.slice(0, 20).map((trace) => {
        const metadata = trace.metadata ?? {};
        const filePath =
          (metadata.file_path as string | undefined) ??
          (metadata.path as string | undefined) ??
          (metadata.target_file as string | undefined) ??
          null;
        return {
          id: trace.id,
          timestamp: trace.timestamp,
          agent: trace.agent,
          action: trace.action,
          state: trace.state,
          commentary: summarizeTrace(trace),
          file_path: filePath,
        } satisfies AgentActivityEvent;
      }),
    [traces],
  );

  const clusters = useMemo<SemanticCluster[]>(() => {
    const groups = new Map<string, Set<string>>();
    for (const node of graph?.nodes ?? []) {
      const label = clusterLabel(node.id);
      if (!groups.has(label)) groups.set(label, new Set());
      groups.get(label)?.add(node.id);
    }
    return [...groups.entries()]
      .map(([label, files]) => ({
        id: label,
        label,
        count: files.size,
        files: [...files].sort(),
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12);
  }, [graph]);

  const filteredNodes = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return graph?.nodes ?? [];
    return (graph?.nodes ?? []).filter(
      (node) => node.id.toLowerCase().includes(q) || node.label.toLowerCase().includes(q),
    );
  }, [graph, search]);

  const visibleNodeIds = useMemo(() => new Set(filteredNodes.map((node) => node.id)), [filteredNodes]);

  const flowNodes = useMemo<Node[]>(() => {
    return filteredNodes.map((node, index) => ({
      id: node.id,
      position: {
        x: (index % 6) * 220,
        y: Math.floor(index / 6) * 110,
      },
      data: {
        label: node.label,
        path: node.id,
        count: node.count,
        salience: node.salience,
      },
      style: {
        background: selectedFile === node.id ? colors.sumi[800] : colors.sumi[850],
        color: colors.torinoko,
        border: `1.5px solid ${fileNodeColor(node.salience)}`,
        borderRadius: 10,
        padding: "10px 12px",
        minWidth: 180,
        boxShadow:
          selectedFile === node.id
            ? `0 0 18px color-mix(in srgb, ${colors.aozora} 30%, transparent)`
            : `0 0 10px color-mix(in srgb, ${fileNodeColor(node.salience)} 12%, transparent)`,
      },
    }));
  }, [filteredNodes, selectedFile]);

  const flowEdges = useMemo<Edge[]>(() => {
    return (graph?.edges ?? [])
      .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
      .slice(0, 240)
      .map((edge, index) => ({
        id: `ecosystem-edge-${index}`,
        source: edge.source,
        target: edge.target,
        animated: edge.agent === selectedAgent && !!selectedAgent,
        style: {
          stroke: edge.agent === selectedAgent && !!selectedAgent ? colors.aozora : colors.sumi[600],
          strokeWidth: edge.agent === selectedAgent && !!selectedAgent ? 1.8 : 1.1,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edge.agent === selectedAgent && !!selectedAgent ? colors.aozora : colors.sumi[600],
        },
      }));
  }, [graph, visibleNodeIds, selectedAgent]);

  const selectedMarks = useMemo(
    () => marks.filter((mark) => !selectedFile || mark.file_path === selectedFile).slice(0, 12),
    [marks, selectedFile],
  );

  const selectedFileActivity = useMemo(
    () => activityFeed.filter((entry) => !selectedFile || entry.file_path === selectedFile),
    [activityFeed, selectedFile],
  );

  const selectedFleetAgent = fleet.find((item) => item.name === selectedAgent);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    setSelectedFile(node.id);
  };

  async function askAgentToInspectFile() {
    if (!selectedFile || !selectedAgent) return;
    await apiFetch("/api/commands/task", {
      method: "POST",
      body: JSON.stringify({
        title: `Inspect file: ${selectedFile}`,
        description:
          `Inspect ${selectedFile}. Produce semantic commentary, identify risks/opportunities, and propose or make high-leverage changes if warranted. Operator note: ${agentCommentary || "none"}`,
        assigned_to: selectedAgent,
        priority: "high",
        metadata: {
          file_path: selectedFile,
          mode: "ecosystem_inspection",
          operator_commentary: agentCommentary,
        },
      }),
      headers: { "Content-Type": "application/json" },
    });
    qc.invalidateQueries({ queryKey: ["ecosystem-traces"] });
  }

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <Network size={24} className="text-aozora" />
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            Ecosystem Map
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          Living semantic map of files, agent touch patterns, and real-time swarm movement.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
        <section className="glass-panel p-4">
          <div className="mb-3 flex items-center gap-2">
            <Sparkles size={14} className="text-fuji" />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Semantic Clusters
            </h2>
          </div>
          <div className="space-y-2">
            {clusters.map((cluster) => (
              <button
                key={cluster.id}
                onClick={() => setSearch(cluster.label)}
                className="w-full rounded-lg border border-sumi-700/30 bg-sumi-850/50 px-3 py-2 text-left transition-colors hover:border-aozora/30 hover:bg-sumi-800/70"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-xs text-torinoko">{cluster.label}</span>
                  <span className="font-mono text-[10px] text-aozora">{cluster.count}</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="glass-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-sumi-700/30 px-4 py-3">
            <div className="flex items-center gap-2">
              <FileCode2 size={14} className="text-kinpaku" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Interactive File Graph
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-sumi-600" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter files..."
                  className="rounded-md border border-sumi-700/40 bg-sumi-850 py-1.5 pl-7 pr-2 text-xs text-torinoko outline-none focus:border-aozora/40"
                />
              </div>
              <button
                onClick={() => setGraphExpanded((v) => !v)}
                className="rounded-md border border-aozora/30 bg-aozora/10 px-2.5 py-1.5 text-xs text-aozora"
              >
                {graphExpanded ? "Compact" : "Expand"}
              </button>
            </div>
          </div>
          <div style={{ height: graphExpanded ? 760 : 520 }}>
            {graphLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-sumi-600">
                Loading ecosystem graph...
              </div>
            ) : flowNodes.length > 0 ? (
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                onNodeClick={onNodeClick}
                fitView
                proOptions={{ hideAttribution: true }}
                style={{ background: colors.sumi[950] }}
              >
                <Background color={colors.sumi[700]} gap={20} size={1} />
                <Controls
                  style={{
                    background: colors.sumi[850],
                    borderColor: colors.sumi[700],
                    borderRadius: 8,
                  }}
                />
                <MiniMap
                  style={{ background: colors.sumi[900], borderRadius: 8 }}
                  maskColor="rgba(13, 14, 19, 0.7)"
                  nodeColor={(node) => fileNodeColor((node.data?.salience as number) ?? 0.2)}
                />
              </ReactFlow>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-sumi-600">
                No graph data available.
              </div>
            )}
          </div>
        </section>

        <section className="glass-panel p-4">
          <div className="mb-4 flex items-center gap-2">
            <Bot size={14} className="text-rokusho" />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              File / Agent Console
            </h2>
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-sumi-700/30 bg-sumi-850/50 p-3">
              <div className="text-[10px] uppercase tracking-wider text-sumi-600">Selected file</div>
              <div className="mt-1 break-all font-mono text-xs text-torinoko">
                {selectedFile ?? "Click a node to inspect a file."}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-wider text-sumi-600">
                Dispatch agent
              </label>
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko outline-none focus:border-aozora/40"
              >
                <option value="">Select agent...</option>
                {fleet.map((agent) => (
                  <option key={agent.name} value={agent.name}>
                    {agent.display_name || agent.name}
                  </option>
                ))}
              </select>
              {selectedFleetAgent && (
                <div className="mt-2 rounded-md bg-sumi-850/60 p-2 text-[11px] text-sumi-600">
                  <div>{selectedFleetAgent.model}</div>
                  <div>{selectedFleetAgent.tool_name || "tool pending"}</div>
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-wider text-sumi-600">
                Operator commentary
              </label>
              <textarea
                value={agentCommentary}
                onChange={(e) => setAgentCommentary(e.target.value)}
                rows={4}
                placeholder="Tell the agent what to notice, change, or explain about this file..."
                className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko outline-none focus:border-aozora/40"
              />
            </div>

            <button
              onClick={askAgentToInspectFile}
              disabled={!selectedFile || !selectedAgent}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-aozora/30 bg-aozora/10 px-4 py-2 text-sm font-medium text-aozora transition-all hover:border-aozora/50 hover:bg-aozora/20 disabled:opacity-40"
            >
              <Play size={14} />
              Ask agent to inspect / act
            </button>

            <div>
              <div className="mb-2 flex items-center gap-2">
                <Eye size={13} className="text-kinpaku" />
                <span className="text-[10px] uppercase tracking-wider text-sumi-600">
                  Live navigation commentary
                </span>
              </div>
              <div className="max-h-[220px] space-y-2 overflow-y-auto">
                {selectedFileActivity.length > 0 ? (
                  selectedFileActivity.map((entry) => (
                    <div key={entry.id} className="rounded-md bg-sumi-850/50 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-aozora">{entry.agent}</span>
                        <span className="text-[10px] text-sumi-600">{entry.state}</span>
                      </div>
                      <p className="mt-1 text-xs text-torinoko/80">{entry.commentary}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-sumi-600">No live file-specific activity yet.</p>
                )}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2">
                <MessageSquare size={13} className="text-fuji" />
                <span className="text-[10px] uppercase tracking-wider text-sumi-600">
                  Recent marks on this file
                </span>
              </div>
              <div className="max-h-[220px] space-y-2 overflow-y-auto">
                {selectedMarks.length > 0 ? (
                  selectedMarks.map((mark) => (
                    <div key={mark.id} className="rounded-md bg-sumi-850/50 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-rokusho">{mark.agent}</span>
                        <span className="text-[10px] text-sumi-600">{mark.action}</span>
                      </div>
                      <p className="mt-1 text-xs text-torinoko/80">{mark.observation}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-sumi-600">No stigmergy marks for the current selection.</p>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="glass-panel p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot size={14} className="text-botan" />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Persistent Agent Personas
            </h2>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-sumi-600">
            Fleet-visible long-term identities
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
          {fleet.slice(0, 10).map((agent) => {
            const live = agents.find((a) => a.name === agent.name);
            return (
              <div key={agent.name} className="rounded-lg border border-sumi-700/30 bg-sumi-850/50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-torinoko">
                      {agent.display_name || agent.name}
                    </div>
                    <div className="font-mono text-[10px] text-sumi-600">{agent.name}</div>
                  </div>
                  <div
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: live?.status === "busy" ? colors.aozora : live?.status === "idle" ? colors.rokusho : colors.sumi[600] }}
                  />
                </div>
                <div className="mt-3 space-y-1 text-[11px] text-sumi-600">
                  <div>{agent.role}</div>
                  <div>{agent.model}</div>
                  <div>{agent.tool_name || "tool pending"}</div>
                  <div>{agent.thread}</div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
