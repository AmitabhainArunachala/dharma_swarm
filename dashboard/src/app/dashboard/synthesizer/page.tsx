"use client";

/**
 * DHARMA COMMAND -- ECOSYSTEM SYNTHESIZER Panel.
 * Palantir-level visibility: identity, stigmergy marks, synthesis reports,
 * audit reports, KaizenOps metrics, connection graph.
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  Sparkles,
  Eye,
  Shield,
  Network,
  Activity,
  TrendingUp,
  FileCode2,
  MessageSquare,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { colors } from "@/lib/theme";

interface SynthesizerIdentity {
  id: string;
  name: string;
  kaizenops_id: string;
  roles: string[];
  status: string;
  telos_alignment: number;
  witness_quality: number;
  shakti_energy: number;
  tasks_completed: number;
  avg_quality: number;
  created_at: string;
  last_active: string;
}

interface StigmergyMark {
  id: string;
  agent: string;
  file_path: string;
  action: string;
  observation: string;
  salience: number;
  semantic_type: string;
  pillar_refs: string[];
  confidence: number;
  impact_score: number;
  timestamp: string;
}

interface SynthesisReport {
  id: string;
  title: string;
  synthesis_type: string;
  key_insights: string[];
  pillar_refs: string[];
  salience: number;
  confidence: number;
  timestamp: string;
}

interface AuditReport {
  id: string;
  title: string;
  audit_type: string;
  findings: string[];
  status: string;
  salience: number;
  confidence: number;
  timestamp: string;
}

interface ConnectionNode {
  id: string;
  label: string;
  type: string;
  salience: number;
}

interface ConnectionEdge {
  source: string;
  target: string;
  label: string;
}

interface ConnectionGraph {
  nodes: ConnectionNode[];
  edges: ConnectionEdge[];
}

const typeColors: Record<string, string> = {
  synthesizer: colors.bengara,
  pillar: colors.kinpaku,
  file: colors.aozora,
  agent: colors.botan,
  report: colors.fuji,
  audit: colors.rokusho,
  mark: colors.sumi[600],
};

const typeIcons: Record<string, typeof Bot> = {
  synthesizer: Sparkles,
  pillar: Shield,
  file: FileCode2,
  agent: Bot,
  report: FileCode2,
  audit: Eye,
  mark: Activity,
};

export default function SynthesizerPage() {
  const [selectedTab, setSelectedTab] = useState<"identity" | "marks" | "reports" | "audits" | "graph">("identity");
  const [selectedMark, setSelectedMark] = useState<StigmergyMark | null>(null);
  const [selectedReport, setSelectedReport] = useState<SynthesisReport | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<AuditReport | null>(null);

  // Fetch synthesizer identity
  const { data: identity, isLoading: identityLoading } = useQuery<SynthesizerIdentity>({
    queryKey: ["synthesizer-identity"],
    queryFn: () => apiFetch<SynthesizerIdentity>("/api/ontology/objects/agent_identity_ecosystem_synthesizer"),
    refetchInterval: 30_000,
  });

  // Fetch stigmergy marks
  const { data: marks = [], isLoading: marksLoading } = useQuery<StigmergyMark[]>({
    queryKey: ["synthesizer-marks"],
    queryFn: () => apiFetch<StigmergyMark[]>("/api/stigmergy/marks?agent=glm5-researcher&limit=50"),
    refetchInterval: 10_000,
  });

  // Fetch synthesis reports
  const { data: reports = [], isLoading: reportsLoading } = useQuery<SynthesisReport[]>({
    queryKey: ["synthesizer-reports"],
    queryFn: () => apiFetch<SynthesisReport[]>("/api/ontology/objects?type=synthesis_report"),
    refetchInterval: 30_000,
  });

  // Fetch audit reports
  const { data: audits = [], isLoading: auditsLoading } = useQuery<AuditReport[]>({
    queryKey: ["synthesizer-audits"],
    queryFn: () => apiFetch<AuditReport[]>("/api/ontology/objects?type=audit_report"),
    refetchInterval: 30_000,
  });

  // Fetch connection graph
  const { data: graph, isLoading: graphLoading } = useQuery<ConnectionGraph>({
    queryKey: ["synthesizer-graph"],
    queryFn: () => apiFetch<ConnectionGraph>("/api/ontology/graph?root=ecosystem_synthesizer"),
    refetchInterval: 60_000,
  });

  // ReactFlow nodes and edges
  const flowNodes = useMemo<Node[]>(() => {
    if (!graph) return [];
    return graph.nodes.map((node, i) => {
      const typeColor = typeColors[node.type] ?? colors.fuji;
      const Icon = typeIcons[node.type] ?? Bot;
      return {
        id: node.id,
        position: { x: (i % 6) * 200, y: Math.floor(i / 6) * 120 },
        data: {
          label: node.label,
          type: node.type,
          salience: node.salience,
          icon: Icon,
        },
        style: {
          background: colors.sumi[850],
          color: colors.torinoko,
          border: `2px solid ${typeColor}`,
          borderRadius: 12,
          padding: "12px 16px",
          fontSize: 11,
          fontFamily: "var(--font-heading)",
          boxShadow: `0 0 16px color-mix(in srgb, ${typeColor} 20%, transparent)`,
        },
      };
    });
  }, [graph]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((edge, i) => ({
      id: `se-${i}`,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      labelStyle: { fill: colors.sumi[600], fontSize: 9 },
      style: { stroke: colors.sumi[600], strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colors.sumi[600] },
      animated: true,
    }));
  }, [graph]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <Sparkles size={28} className="text-bengara" />
          <h1 className="glow-bengara font-heading text-3xl font-bold tracking-tight text-bengara">
            ECOSYSTEM SYNTHESIZER
          </h1>
          <span className="ml-2 rounded-full bg-sumi-800 px-3 py-1 text-xs font-medium text-sumi-300">
            KOP-001
          </span>
        </div>
        <p className="mt-2 text-sm text-sumi-600">
          Palantir-level visibility: identity, stigmergy marks, synthesis reports, audit reports, connection graph
        </p>
      </motion.div>

      {/* Tab Navigation */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="flex gap-2"
      >
        {[
          { key: "identity", label: "Identity", icon: Bot },
          { key: "marks", label: "Stigmergy Marks", icon: Activity },
          { key: "reports", label: "Synthesis Reports", icon: FileCode2 },
          { key: "audits", label: "Audit Reports", icon: Eye },
          { key: "graph", label: "Connection Graph", icon: Network },
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setSelectedTab(tab.key as typeof selectedTab)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                selectedTab === tab.key
                  ? "bg-bengara/20 text-bengara glow-bengara"
                  : "bg-sumi-800 text-sumi-400 hover:bg-sumi-700"
              }`}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </motion.div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {selectedTab === "identity" && (
          <motion.div
            key="identity"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="glass-panel space-y-4 p-6"
          >
            {identityLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-bengara/30 border-t-bengara" />
              </div>
            ) : identity ? (
              <>
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <MetricCard
                    label="Tasks Completed"
                    value={identity.tasks_completed}
                    icon={CheckCircle2}
                    color={colors.rokusho}
                  />
                  <MetricCard
                    label="Avg Quality"
                    value={`${(identity.avg_quality * 100).toFixed(0)}%`}
                    icon={TrendingUp}
                    color={colors.kinpaku}
                  />
                  <MetricCard
                    label="Telos Alignment"
                    value={`${(identity.telos_alignment * 100).toFixed(0)}%`}
                    icon={Zap}
                    color={colors.bengara}
                  />
                  <MetricCard
                    label="Witness Quality"
                    value={`${(identity.witness_quality * 100).toFixed(0)}%`}
                    icon={Eye}
                    color={colors.aozora}
                  />
                </div>

                <div className="mt-6 space-y-3">
                  <h3 className="font-heading text-lg font-semibold text-torinoko">Roles</h3>
                  <div className="flex flex-wrap gap-2">
                    {identity.roles.map((role) => (
                      <span
                        key={role}
                        className="rounded-full bg-sumi-800 px-3 py-1 text-xs font-medium text-sumi-300"
                      >
                        {role}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-6 grid grid-cols-2 gap-4">
                  <div>
                    <h3 className="font-heading text-sm font-semibold text-sumi-400">KaizenOps ID</h3>
                    <p className="mt-1 text-lg font-medium text-torinoko">{identity.kaizenops_id}</p>
                  </div>
                  <div>
                    <h3 className="font-heading text-sm font-semibold text-sumi-400">Status</h3>
                    <p className="mt-1 text-lg font-medium text-rokusho">{identity.status}</p>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-center py-12">
                <p className="text-sm text-sumi-600">No identity data available</p>
              </div>
            )}
          </motion.div>
        )}

        {selectedTab === "marks" && (
          <motion.div
            key="marks"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="space-y-4"
          >
            {marksLoading ? (
              <div className="glass-panel flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-aozora/30 border-t-aozora" />
              </div>
            ) : marks.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {marks.slice(0, 20).map((mark) => (
                  <motion.div
                    key={mark.id}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="glass-panel cursor-pointer p-4 transition-all hover:border-aozora/50"
                    onClick={() => setSelectedMark(mark)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-aozora/20 px-2 py-0.5 text-xs font-medium text-aozora">
                            {mark.semantic_type}
                          </span>
                          <span className="text-xs text-sumi-500">{mark.action}</span>
                        </div>
                        <p className="mt-2 text-sm text-sumi-300 line-clamp-2">{mark.observation}</p>
                        <div className="mt-2 flex items-center gap-2 text-xs text-sumi-500">
                          <span>{mark.file_path.split("/").slice(-2).join("/")}</span>
                          <span>•</span>
                          <span>{new Date(mark.timestamp).toLocaleTimeString()}</span>
                        </div>
                      </div>
                      <div className="ml-4 flex flex-col items-end gap-1">
                        <span className="text-xs font-medium text-kimpaku">
                          {(mark.salience * 100).toFixed(0)}%
                        </span>
                        <span className="text-xs text-sumi-500">
                          {(mark.confidence * 100).toFixed(0)}% conf
                        </span>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="glass-panel flex items-center justify-center py-12">
                <p className="text-sm text-sumi-600">No stigmergy marks available</p>
              </div>
            )}
          </motion.div>
        )}

        {selectedTab === "reports" && (
          <motion.div
            key="reports"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="space-y-4"
          >
            {reportsLoading ? (
              <div className="glass-panel flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-fuji/30 border-t-fuji" />
              </div>
            ) : reports.length > 0 ? (
              <div className="grid gap-4">
                {reports.map((report) => (
                  <motion.div
                    key={report.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="glass-panel p-5"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-heading text-lg font-semibold text-torinoko">
                          {report.title}
                        </h3>
                        <span className="mt-1 inline-block rounded-full bg-fuji/20 px-2 py-0.5 text-xs font-medium text-fuji">
                          {report.synthesis_type}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm font-medium text-kimpaku">
                          {(report.salience * 100).toFixed(0)}% salience
                        </span>
                        <p className="text-xs text-sumi-500">
                          {new Date(report.timestamp).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="mt-4 space-y-2">
                      {report.key_insights.slice(0, 3).map((insight, i) => (
                        <p key={i} className="text-sm text-sumi-300">
                          • {insight}
                        </p>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="glass-panel flex items-center justify-center py-12">
                <p className="text-sm text-sumi-600">No synthesis reports available</p>
              </div>
            )}
          </motion.div>
        )}

        {selectedTab === "audits" && (
          <motion.div
            key="audits"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="space-y-4"
          >
            {auditsLoading ? (
              <div className="glass-panel flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-rokusho/30 border-t-rokusho" />
              </div>
            ) : audits.length > 0 ? (
              <div className="grid gap-4">
                {audits.map((audit) => (
                  <motion.div
                    key={audit.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="glass-panel p-5"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-heading text-lg font-semibold text-torinoko">
                          {audit.title}
                        </h3>
                        <span className="mt-1 inline-block rounded-full bg-rokusho/20 px-2 py-0.5 text-xs font-medium text-rokusho">
                          {audit.audit_type}
                        </span>
                        <span className="ml-2 inline-block rounded-full bg-sumi-700 px-2 py-0.5 text-xs font-medium text-sumi-300">
                          {audit.status}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm font-medium text-bengara">
                          {(audit.salience * 100).toFixed(0)}% salience
                        </span>
                        <p className="text-xs text-sumi-500">
                          {new Date(audit.timestamp).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="mt-4 space-y-2">
                      {audit.findings.slice(0, 3).map((finding, i) => (
                        <p key={i} className="text-sm text-sumi-300">
                          • {finding}
                        </p>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="glass-panel flex items-center justify-center py-12">
                <p className="text-sm text-sumi-600">No audit reports available</p>
              </div>
            )}
          </motion.div>
        )}

        {selectedTab === "graph" && (
          <motion.div
            key="graph"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="glass-panel overflow-hidden"
            style={{ height: 600 }}
          >
            {graphLoading ? (
              <div className="flex h-full items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-bengara/30 border-t-bengara" />
              </div>
            ) : flowNodes.length > 0 ? (
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
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
                  nodeColor={(n) => typeColors[n.data?.type as string] ?? colors.fuji}
                />
              </ReactFlow>
            ) : (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-sumi-600">No connection graph data available</p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Metric Card Component
function MetricCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: typeof CheckCircle2;
  color: string;
}) {
  return (
    <div className="glass-panel flex items-center gap-3 p-4">
      <div
        className="flex h-10 w-10 items-center justify-center rounded-lg"
        style={{ background: color + "20" }}
      >
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <p className="text-xs font-medium text-sumi-500">{label}</p>
        <p className="text-lg font-bold text-torinoko">{value}</p>
      </div>
    </div>
  );
}
