"use client";

/**
 * DHARMA COMMAND -- Evolution page (L3).
 * Fitness trend, XP bar, ReactFlow DAG of lineage, archive table.
 */

import { useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeMouseHandler,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  useEvolutionArchive,
  useFitnessTrend,
  useEvolutionDag,
} from "@/hooks/useEvolution";
import { FitnessTrend } from "@/components/dashboard/FitnessTrend";
import { XPBar } from "@/components/game/XPBar";
import { colors } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";
import type { ArchiveEntryOut } from "@/lib/types";

function fitnessColor(f: number): string {
  if (f >= 0.8) return colors.rokusho;
  if (f >= 0.5) return colors.kinpaku;
  return colors.bengara;
}

export default function EvolutionPage() {
  const { archive, isLoading: archiveLoading } = useEvolutionArchive();
  const { trend } = useFitnessTrend();
  const { dag } = useEvolutionDag();
  const [selectedEntry, setSelectedEntry] = useState<ArchiveEntryOut | null>(null);

  // Mean fitness for XP bar
  const meanFitness = useMemo(() => {
    if (!archive.length) return 0;
    return archive.reduce((sum, e) => sum + e.fitness.weighted, 0) / archive.length;
  }, [archive]);

  // ReactFlow nodes + edges
  const { nodes, edges } = useMemo(() => {
    if (!dag) return { nodes: [] as Node[], edges: [] as Edge[] };

    const rfNodes: Node[] = dag.nodes.map((n) => ({
      id: n.id,
      position: n.position,
      data: {
        label: n.data.label,
        fitness: n.data.fitness,
      },
      style: {
        background: colors.sumi[850],
        color: colors.torinoko,
        border: `2px solid ${fitnessColor(n.data.fitness)}`,
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 11,
        fontFamily: "var(--font-mono)",
        boxShadow: `0 0 8px color-mix(in srgb, ${fitnessColor(n.data.fitness)} 25%, transparent)`,
      },
    }));

    const rfEdges: Edge[] = dag.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      animated: e.animated ?? true,
      style: { stroke: colors.sumi[600], strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colors.sumi[600] },
      label: e.label ?? "",
      labelStyle: { fill: colors.sumi[600], fontSize: 9 },
    }));

    return { nodes: rfNodes, edges: rfEdges };
  }, [dag]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const entry = archive.find((e) => e.id === node.id);
      if (entry) setSelectedEntry(entry);
    },
    [archive],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="glow-kinpaku font-heading text-2xl font-bold tracking-tight text-kinpaku">
          Evolution
        </h1>
        <p className="mt-1 text-sm text-sumi-600">
          Darwin Engine -- {archive.length} entries, mean fitness{" "}
          {meanFitness.toFixed(3)}
        </p>
      </motion.div>

      {/* Fitness trend + XP bar */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <FitnessTrend className="lg:col-span-2" />
        <div className="flex flex-col gap-4">
          <div className="glass-panel p-5">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Mean Fitness
            </h3>
            <XPBar value={meanFitness} max={1} label="Fitness Score" />
          </div>
          <div className="glass-panel flex-1 p-5">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Stats
            </h3>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-sumi-600">Total Entries</span>
                <span className="font-mono text-torinoko">{archive.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sumi-600">Passed Gates</span>
                <span className="font-mono text-rokusho">
                  {archive.filter((e) => e.status === "accepted").length}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sumi-600">Trend Points</span>
                <span className="font-mono text-torinoko">{trend.length}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* DAG visualization */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-panel overflow-hidden"
        style={{ height: 480 }}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Lineage DAG
            </h3>
          </div>
          <div className="flex-1">
            {nodes.length > 0 ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodeClick={onNodeClick}
                fitView
                proOptions={{ hideAttribution: true }}
                style={{ background: colors.sumi[950] }}
              >
                <Background
                  color={colors.sumi[700]}
                  gap={24}
                  size={1}
                />
                <Controls
                  style={{
                    background: colors.sumi[850],
                    borderColor: colors.sumi[700],
                    borderRadius: 8,
                  }}
                />
                <MiniMap
                  style={{
                    background: colors.sumi[900],
                    borderRadius: 8,
                  }}
                  maskColor="rgba(13, 14, 19, 0.7)"
                  nodeColor={(n) => fitnessColor((n.data as Record<string, number>)?.fitness ?? 0.5)}
                />
              </ReactFlow>
            ) : (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-sumi-600">
                  {archiveLoading ? "Loading DAG..." : "No evolution data yet"}
                </p>
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Archive table */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass-panel overflow-hidden"
      >
        <div className="border-b border-sumi-700/30 px-5 py-3">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
            Archive Entries
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr
                className="border-b text-[10px] font-semibold uppercase tracking-wider"
                style={{ borderColor: colors.sumi[700], color: colors.sumi[600] }}
              >
                <th className="px-5 py-2.5">Component</th>
                <th className="px-5 py-2.5">Type</th>
                <th className="px-5 py-2.5">Fitness</th>
                <th className="px-5 py-2.5">Status</th>
                <th className="px-5 py-2.5">Time</th>
              </tr>
            </thead>
            <tbody>
              {archive.slice(0, 20).map((entry, i) => (
                <motion.tr
                  key={entry.id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.03 }}
                  onClick={() => setSelectedEntry(entry)}
                  className="cursor-pointer border-b transition-colors hover:bg-white/[0.02]"
                  style={{
                    borderColor: `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`,
                  }}
                >
                  <td className="px-5 py-2.5 font-mono text-xs text-torinoko">
                    {entry.component}
                  </td>
                  <td className="px-5 py-2.5 text-xs capitalize text-kitsurubami">
                    {entry.change_type}
                  </td>
                  <td className="px-5 py-2.5">
                    <span
                      className="font-mono text-xs font-bold"
                      style={{ color: fitnessColor(entry.fitness.weighted) }}
                    >
                      {entry.fitness.weighted.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-xs capitalize text-sumi-600">
                    {entry.status}
                  </td>
                  <td className="px-5 py-2.5 text-xs text-sumi-600">
                    {timeAgo(entry.timestamp)}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* Entry detail panel */}
      <AnimatePresence>
        {selectedEntry && (
          <EntryDetailPanel
            entry={selectedEntry}
            onClose={() => setSelectedEntry(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Entry detail side panel
// ---------------------------------------------------------------------------

function EntryDetailPanel({
  entry,
  onClose,
}: {
  entry: ArchiveEntryOut;
  onClose: () => void;
}) {
  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
      />
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="fixed right-0 top-0 z-50 flex h-full w-[400px] flex-col border-l border-sumi-700/40 bg-sumi-900/95 backdrop-blur-md"
      >
        <div className="flex items-center justify-between border-b border-sumi-700/30 px-6 py-4">
          <h2 className="font-heading text-lg font-bold text-torinoko">
            Entry Detail
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-sumi-600 hover:text-torinoko"
            aria-label="Close"
          >
            <span className="text-lg">&times;</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="space-y-2.5 text-xs">
            <Row label="ID" value={entry.id} />
            <Row label="Component" value={entry.component} />
            <Row label="Type" value={entry.change_type} />
            <Row label="Status" value={entry.status} />
            <Row label="Agent" value={entry.agent_id} />
            <Row label="Model" value={entry.model} />
            <Row label="Time" value={new Date(entry.timestamp).toLocaleString()} />
          </div>

          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Description
            </p>
            <p className="text-sm leading-relaxed text-torinoko/80">
              {entry.description}
            </p>
          </div>

          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Fitness Breakdown
            </p>
            <div className="space-y-1.5 text-xs">
              <FitnessRow label="Weighted" value={entry.fitness.weighted} />
              <FitnessRow label="Correctness" value={entry.fitness.correctness} />
              <FitnessRow label="Elegance" value={entry.fitness.elegance} />
              <FitnessRow label="Performance" value={entry.fitness.performance} />
              <FitnessRow label="Safety" value={entry.fitness.safety} />
              <FitnessRow label="Dharmic Alignment" value={entry.fitness.dharmic_alignment} />
            </div>
          </div>

          {entry.parent_id && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Parent
              </p>
              <p className="font-mono text-[10px] text-sumi-600">
                {entry.parent_id}
              </p>
            </div>
          )}

          {entry.gates_passed.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Gates Passed ({entry.gates_passed.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {entry.gates_passed.map((g) => (
                  <span
                    key={g}
                    className="rounded-full bg-rokusho/10 px-2 py-0.5 font-mono text-[10px] text-rokusho"
                  >
                    {g}
                  </span>
                ))}
              </div>
            </div>
          )}

          {entry.gates_failed.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Gates Failed ({entry.gates_failed.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {entry.gates_failed.map((g) => (
                  <span
                    key={g}
                    className="rounded-full bg-bengara/10 px-2 py-0.5 font-mono text-[10px] text-bengara"
                  >
                    {g}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sumi-600">{label}</span>
      <span className="font-mono text-torinoko">{value}</span>
    </div>
  );
}

function FitnessRow({ label, value }: { label: string; value: number }) {
  const fColor =
    value >= 0.8 ? colors.rokusho : value >= 0.5 ? colors.kinpaku : colors.bengara;
  return (
    <div className="flex items-center justify-between">
      <span className="text-sumi-600">{label}</span>
      <span className="font-mono font-bold" style={{ color: fColor }}>
        {value.toFixed(3)}
      </span>
    </div>
  );
}
