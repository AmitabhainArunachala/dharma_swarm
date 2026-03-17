"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  BrainCircuit,
  Command,
  Globe,
  Link2,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Zap,
} from "lucide-react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { AgentCard } from "@/components/dashboard/AgentCard";
import { useAgents } from "@/hooks/useAgents";
import { useHealth } from "@/hooks/useHealth";
import { useOverview } from "@/hooks/useOverview";
import { useOntologyGraph, useOntologyType } from "@/hooks/useOntology";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";
import { colors } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";

const categoryColors: Record<string, string> = {
  agent: colors.aozora,
  task: colors.kinpaku,
  artifact: colors.botan,
  concept: colors.fuji,
  gate: colors.rokusho,
};

export default function ClaudePage() {
  const { overview } = useOverview();
  const { agents } = useAgents();
  const { health } = useHealth();
  const { graph, isLoading } = useOntologyGraph();
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const { typeDetail } = useOntologyType(selectedType);
  const { openOverlay, openPanel } = useChatWorkspace();

  useEffect(() => {
    if (!selectedType && graph?.nodes?.length) {
      setSelectedType(graph.nodes[0].data.label);
    }
  }, [graph, selectedType]);

  const nodes = useMemo<Node[]>(() => {
    if (!graph) return [];
    return graph.nodes.map((node) => {
      const accent = categoryColors[node.type] ?? colors.aozora;
      const isSelected = selectedType === node.data.label;
      return {
        id: node.id,
        position: node.position,
        data: {
          label: (
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-heading text-sm font-semibold text-torinoko">
                    {node.data.label}
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-sumi-600">
                    {node.data.zone ?? "semantic mesh"}
                  </div>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-mono"
                  style={{
                    color: accent,
                    background: `color-mix(in srgb, ${accent} 14%, transparent)`,
                  }}
                >
                  {node.type}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[10px] text-sumi-600">
                <div className="rounded-xl bg-sumi-900/70 px-2 py-1">
                  {node.data.propertyCount} props
                </div>
                <div className="rounded-xl bg-sumi-900/70 px-2 py-1">
                  {node.data.actionCount ?? 0} acts
                </div>
                <div className="rounded-xl bg-sumi-900/70 px-2 py-1">
                  {node.data.runtimeCount ?? 0} live
                </div>
              </div>
            </div>
          ),
          name: node.data.label,
          propertyCount: node.data.propertyCount,
          actionCount: node.data.actionCount ?? 0,
          runtimeCount: node.data.runtimeCount ?? 0,
          zone: node.data.zone ?? "semantic mesh",
          nodeType: node.type,
        },
        style: {
          width: 190,
          borderRadius: 18,
          padding: "14px 16px",
          color: colors.torinoko,
          border: `1.4px solid ${accent}`,
          background: isSelected
            ? `linear-gradient(180deg, color-mix(in srgb, ${accent} 16%, ${colors.sumi[850]}), ${colors.sumi[900]})`
            : `linear-gradient(180deg, ${colors.sumi[850]}, ${colors.sumi[900]})`,
          boxShadow: isSelected
            ? `0 0 24px color-mix(in srgb, ${accent} 24%, transparent)`
            : `0 0 14px color-mix(in srgb, ${accent} 12%, transparent)`,
        },
      };
    });
  }, [graph, selectedType]);

  const edges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      animated: selectedType === edge.source || selectedType === edge.target,
      style: { stroke: colors.sumi[600], strokeWidth: 1.3 },
      labelStyle: { fill: colors.sumi[600], fontSize: 10 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colors.sumi[600] },
    }));
  }, [graph, selectedType]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    const label = typeof node.data?.name === "string" ? node.data.name : null;
    setSelectedType(label);
  };

  const activeAgents = agents.filter((agent) => ["busy", "starting"].includes(agent.status));
  const anomalies = health?.anomalies ?? [];
  const healthStatus = overview?.health_status ?? health?.overall_status ?? "unknown";

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="relative overflow-hidden rounded-[28px] border border-sumi-700/40 bg-sumi-900/90 p-6 shadow-[0_0_30px_rgba(79,209,217,0.06)]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(79,209,217,0.18),transparent_30%),radial-gradient(circle_at_80%_20%,rgba(212,125,181,0.14),transparent_24%),linear-gradient(135deg,rgba(13,14,19,0.35),transparent_65%)]" />
        <div className="relative grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-aozora/30 bg-aozora/10 p-3 text-aozora">
                <BrainCircuit size={24} />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="glow-aozora font-heading text-3xl font-bold tracking-tight text-aozora">
                    Semantic Command Plane
                  </h1>
                  <HealthBadge
                    status={healthStatus as "healthy" | "degraded" | "critical" | "unknown"}
                    label
                    size="md"
                  />
                </div>
                <p className="mt-1 max-w-3xl text-sm text-sumi-600">
                  One live control room for ontology, runtime pressure, agent health, and operator
                  intervention. This is the layer where Palantir-style semantics meets your swarm.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                icon={<Bot size={15} />}
                label="Active Agents"
                value={String(activeAgents.length)}
                subtitle={`${agents.length} total agents`}
                accent={colors.aozora}
              />
              <MetricCard
                icon={<Globe size={15} />}
                label="Ontology Types"
                value={String(graph?.nodes.length ?? 0)}
                subtitle={`${graph?.edges.length ?? 0} semantic links`}
                accent={colors.fuji}
              />
              <MetricCard
                icon={<Zap size={15} />}
                label="Mean Fitness"
                value={(overview?.mean_fitness ?? 0).toFixed(3)}
                subtitle={`${overview?.evolution_entries ?? 0} archive entries`}
                accent={colors.kinpaku}
              />
              <MetricCard
                icon={<TriangleAlert size={15} />}
                label="Anomalies"
                value={String(anomalies.length)}
                subtitle={`${health?.total_traces ?? 0} total traces`}
                accent={anomalies.length > 0 ? colors.bengara : colors.rokusho}
              />
            </div>
          </div>

          <div className="grid gap-3">
            <ActionDock
              title="Operator Lanes"
              subtitle="Launch the embedded agents directly into this control plane."
              actions={[
                {
                  label: "Open Codex Popup",
                  caption: "Implementation agent for edits and wiring",
                  accent: colors.kinpaku,
                  onClick: () => openOverlay("codex_operator"),
                },
                {
                  label: "Open Codex Split View",
                  caption: "Half-screen control console for live steering",
                  accent: colors.kinpaku,
                  onClick: () => openPanel("codex_operator"),
                },
                {
                  label: "Open Claude Strategist",
                  caption: "Strategic operator for diagnosis and system framing",
                  accent: colors.aozora,
                  onClick: () => openOverlay("claude_opus"),
                },
              ]}
            />
          </div>
        </div>
      </motion.section>

      <div className="grid gap-6 xl:grid-cols-[1.7fr_0.95fr]">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08 }}
          className="glass-panel overflow-hidden"
        >
          <div className="flex items-center justify-between border-b border-sumi-700/30 px-5 py-4">
            <div>
              <h2 className="font-heading text-lg font-semibold text-torinoko">
                Ontology World Graph
              </h2>
              <p className="mt-1 text-xs text-sumi-600">
                Click a type to inspect its properties, actions, and role in the operating model.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-sumi-850 px-3 py-1 font-mono text-[10px] text-sumi-600">
                {graph?.nodes.length ?? 0} nodes
              </span>
              <span className="rounded-full bg-sumi-850 px-3 py-1 font-mono text-[10px] text-sumi-600">
                {graph?.edges.length ?? 0} edges
              </span>
            </div>
          </div>

          <div className="relative h-[620px] bg-[radial-gradient(circle_at_top,rgba(79,209,217,0.08),transparent_28%),linear-gradient(180deg,rgba(13,14,19,0.24),rgba(13,14,19,0.88))]">
            {nodes.length > 0 ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodeClick={onNodeClick}
                fitView
                fitViewOptions={{ padding: 0.18 }}
                proOptions={{ hideAttribution: true }}
                style={{ background: "transparent" }}
              >
                <Background color={colors.sumi[700]} gap={28} size={1} />
                <Controls
                  style={{
                    background: colors.sumi[850],
                    borderColor: colors.sumi[700],
                    borderRadius: 12,
                  }}
                />
                <MiniMap
                  style={{ background: colors.sumi[900], borderRadius: 12 }}
                  maskColor="rgba(13, 14, 19, 0.75)"
                  nodeColor={(node) =>
                    categoryColors[String(node.data?.nodeType || "")] ?? colors.fuji
                  }
                />
              </ReactFlow>
            ) : (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-sumi-600">
                  {isLoading ? "Loading semantic topology..." : "No ontology graph available."}
                </p>
              </div>
            )}
          </div>
        </motion.section>

        <div className="grid gap-6">
          <motion.section
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.12 }}
            className="glass-panel p-5"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="font-heading text-lg font-semibold text-torinoko">
                  Semantic Inspector
                </h2>
                <p className="mt-1 text-xs text-sumi-600">
                  Deep read on the currently selected ontology type.
                </p>
              </div>
              {selectedType && (
                <span className="rounded-full border border-aozora/30 bg-aozora/10 px-2.5 py-1 font-mono text-[10px] text-aozora">
                  {selectedType}
                </span>
              )}
            </div>

            {typeDetail ? (
              <div className="space-y-4">
                <div className="rounded-2xl border border-sumi-700/30 bg-sumi-850/80 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-heading text-xl text-torinoko">{typeDetail.name}</h3>
                      <p className="mt-1 text-sm text-sumi-600">{typeDetail.description}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-[11px] text-sumi-600">telos</p>
                      <p className="font-mono text-sm text-kinpaku">
                        {typeDetail.telos_alignment.toFixed(2)}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    <InspectorStat label="Props" value={String(typeDetail.properties.length)} />
                    <InspectorStat label="Links" value={String(typeDetail.links.length)} />
                    <InspectorStat label="Actions" value={String(typeDetail.actions.length)} />
                  </div>
                </div>

                <InspectorList
                  icon={<Sparkles size={14} className="text-fuji" />}
                  title="Properties"
                  items={typeDetail.properties.map(
                    (property) => `${property.name} · ${property.property_type}${property.required ? " · required" : ""}`,
                  )}
                />
                <InspectorList
                  icon={<Link2 size={14} className="text-aozora" />}
                  title="Links"
                  items={typeDetail.links.map(
                    (link) => `${link.name} -> ${link.target_type} (${link.cardinality})`,
                  )}
                />
                <InspectorList
                  icon={<ShieldCheck size={14} className="text-rokusho" />}
                  title="Actions"
                  items={typeDetail.actions.map(
                    (action) =>
                      `${action.name} · ${action.is_deterministic ? "deterministic" : "llm"}${action.telos_gates.length ? ` · ${action.telos_gates.join(", ")}` : ""}`,
                  )}
                />
              </div>
            ) : (
              <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed border-sumi-700/30 bg-sumi-850/40 p-6 text-center text-sm text-sumi-600">
                Select a semantic node to inspect its contract.
              </div>
            )}
          </motion.section>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.16 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-heading text-lg font-semibold text-torinoko">
                Live Agent Pulse
              </h2>
              <p className="mt-1 text-xs text-sumi-600">
                Runtime actors currently driving the graph.
              </p>
            </div>
            <span className="rounded-full bg-sumi-850 px-3 py-1 font-mono text-[10px] text-sumi-600">
              {activeAgents.length} active
            </span>
          </div>

          {agents.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {agents.slice(0, 4).map((agent, index) => (
                <AgentCard key={agent.id} agent={agent} index={index} />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-sumi-700/30 bg-sumi-850/40 p-8 text-center text-sm text-sumi-600">
              No agents registered.
            </div>
          )}
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.2 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-heading text-lg font-semibold text-torinoko">
                Anomaly Watch
              </h2>
              <p className="mt-1 text-xs text-sumi-600">
                Signals that deserve operator attention.
              </p>
            </div>
            <span className="rounded-full bg-bengara/10 px-3 py-1 font-mono text-[10px] text-bengara">
              {anomalies.length} alerts
            </span>
          </div>

          {anomalies.length > 0 ? (
            <div className="space-y-3">
              {anomalies.slice(0, 5).map((anomaly) => (
                <div
                  key={anomaly.id}
                  className="rounded-2xl border border-bengara/20 bg-bengara/5 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-mono text-xs uppercase tracking-[0.14em] text-bengara">
                      {anomaly.anomaly_type}
                    </p>
                    <span className="text-[10px] text-sumi-600">
                      {timeAgo(anomaly.detected_at)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-torinoko">{anomaly.description}</p>
                  <p className="mt-2 text-[11px] text-sumi-600">
                    Severity {anomaly.severity} · {anomaly.related_traces.length} related traces
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-rokusho/20 bg-rokusho/5 p-8 text-center text-sm text-sumi-600">
              No anomalies detected in the current window.
            </div>
          )}
        </motion.section>
      </div>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  subtitle,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtitle: string;
  accent: string;
}) {
  return (
    <div
      className="rounded-2xl border border-sumi-700/30 bg-sumi-850/70 p-4"
      style={{ boxShadow: `0 0 18px color-mix(in srgb, ${accent} 12%, transparent)` }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sumi-600">{icon}</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-600">
          {label}
        </span>
      </div>
      <div className="mt-3 font-heading text-2xl text-torinoko">{value}</div>
      <div className="mt-1 text-xs text-sumi-600">{subtitle}</div>
    </div>
  );
}

function ActionDock({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle: string;
  actions: Array<{
    label: string;
    caption: string;
    accent: string;
    onClick: () => void;
  }>;
}) {
  return (
    <div className="rounded-[24px] border border-sumi-700/30 bg-sumi-850/70 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Command size={15} className="text-kinpaku" />
        <h2 className="font-heading text-lg font-semibold text-torinoko">{title}</h2>
      </div>
      <p className="mb-4 text-sm text-sumi-600">{subtitle}</p>
      <div className="space-y-2.5">
        {actions.map((action) => (
          <button
            key={action.label}
            onClick={action.onClick}
            className="w-full rounded-2xl border border-sumi-700/30 bg-sumi-900/60 px-4 py-3 text-left transition-colors hover:bg-sumi-900"
            style={{ boxShadow: `0 0 16px color-mix(in srgb, ${action.accent} 12%, transparent)` }}
          >
            <div className="font-medium text-torinoko">{action.label}</div>
            <div className="mt-1 text-xs text-sumi-600">{action.caption}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function InspectorStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-sumi-600">{label}</div>
      <div className="mt-1 font-mono text-sm text-torinoko">{value}</div>
    </div>
  );
}

function InspectorList({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
}) {
  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-850/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h3 className="font-heading text-sm font-semibold text-torinoko">{title}</h3>
      </div>
      <div className="space-y-2">
        {items.length > 0 ? (
          items.slice(0, 7).map((item) => (
            <div
              key={item}
              className="rounded-xl border border-sumi-700/20 bg-sumi-900/55 px-3 py-2 text-xs text-kitsurubami"
            >
              {item}
            </div>
          ))
        ) : (
          <div className="text-xs text-sumi-600">No entries recorded.</div>
        )}
      </div>
    </div>
  );
}
