"use client";

/**
 * DHARMA COMMAND -- Lineage Explorer (L4).
 * Search by artifact ID, dual-view provenance/impact, ReactFlow DAG.
 */

import { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { GitBranch, Search, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { useLineageDag } from "@/hooks/useLineage";
import { colors } from "@/lib/theme";

const relationColors: Record<string, string> = {
  parent: colors.aozora,
  mutation: colors.kinpaku,
  crossover: colors.botan,
  inspired_by: colors.fuji,
};

export default function LineagePage() {
  const [searchInput, setSearchInput] = useState("");
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const { dag, isLoading } = useLineageDag(artifactId);

  const handleSearch = useCallback(() => {
    const trimmed = searchInput.trim();
    if (trimmed) setArtifactId(trimmed);
  }, [searchInput]);

  // Build upstream (provenance) and downstream (impact) from the DAG
  const { upstreamNodes, downstreamNodes, allNodes, allEdges } = useMemo(() => {
    if (!dag || !artifactId) {
      return {
        upstreamNodes: [] as Node[],
        downstreamNodes: [] as Node[],
        allNodes: [] as Node[],
        allEdges: [] as Edge[],
      };
    }

    const nodeMap = new Map(dag.nodes.map((n) => [n.id, n]));

    // Find upstream (sources that point to this artifact)
    const upstreamIds = new Set<string>();
    const downstreamIds = new Set<string>();

    for (const edge of dag.edges) {
      if (edge.target === artifactId) {
        upstreamIds.add(edge.source);
      }
      if (edge.source === artifactId) {
        downstreamIds.add(edge.target);
      }
    }

    // Recursively expand (simplified to direct neighbors)
    for (const edge of dag.edges) {
      if (upstreamIds.has(edge.target)) upstreamIds.add(edge.source);
      if (downstreamIds.has(edge.source)) downstreamIds.add(edge.target);
    }

    const allRfNodes: Node[] = dag.nodes.map((n, i) => {
      const isCenter = n.id === artifactId;
      const isUpstream = upstreamIds.has(n.id);
      const borderColor = isCenter
        ? colors.aozora
        : isUpstream
          ? colors.kinpaku
          : colors.botan;

      return {
        id: n.id,
        position: { x: (i % 5) * 200, y: Math.floor(i / 5) * 120 },
        data: { label: n.label, type: n.type },
        style: {
          background: isCenter ? colors.sumi[800] : colors.sumi[850],
          color: colors.torinoko,
          border: `2px solid ${borderColor}`,
          borderRadius: 8,
          padding: "8px 12px",
          fontSize: 11,
          fontFamily: "var(--font-mono)",
          boxShadow: isCenter
            ? `0 0 16px color-mix(in srgb, ${colors.aozora} 30%, transparent)`
            : "none",
        },
      };
    });

    const allRfEdges: Edge[] = dag.edges.map((e, i) => ({
      id: `le-${i}`,
      source: e.source,
      target: e.target,
      label: e.label,
      labelStyle: { fill: colors.sumi[600], fontSize: 9 },
      style: {
        stroke: relationColors[e.label] ?? colors.sumi[600],
        strokeWidth: 1.5,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: relationColors[e.label] ?? colors.sumi[600],
      },
      animated: true,
    }));

    return {
      upstreamNodes: allRfNodes.filter(
        (n) => upstreamIds.has(n.id) || n.id === artifactId,
      ),
      downstreamNodes: allRfNodes.filter(
        (n) => downstreamIds.has(n.id) || n.id === artifactId,
      ),
      allNodes: allRfNodes,
      allEdges: allRfEdges,
    };
  }, [dag, artifactId]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <GitBranch size={24} className="text-kinpaku" />
          <h1 className="glow-kinpaku font-heading text-2xl font-bold tracking-tight text-kinpaku">
            Lineage Explorer
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          Trace provenance upstream and impact downstream for any artifact.
        </p>
      </motion.div>

      {/* Search */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex gap-3"
      >
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-sumi-600"
          />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Enter artifact ID..."
            className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 py-2.5 pl-9 pr-3 text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-kinpaku/50"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={!searchInput.trim()}
          className="flex items-center gap-2 rounded-lg border border-kinpaku/30 bg-kinpaku/10 px-5 py-2 text-sm font-medium text-kinpaku transition-all hover:border-kinpaku/50 hover:bg-kinpaku/20 disabled:opacity-40"
        >
          <Search size={14} />
          Trace
        </button>
      </motion.div>

      {/* Dual view labels */}
      {artifactId && (
        <div className="flex gap-4">
          <div className="flex items-center gap-2">
            <ArrowUpRight size={14} style={{ color: colors.kinpaku }} />
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kinpaku">
              Provenance (Upstream)
            </span>
            <span className="font-mono text-[10px] text-sumi-600">
              {upstreamNodes.length} nodes
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ArrowDownRight size={14} style={{ color: colors.botan }} />
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-botan">
              Impact (Downstream)
            </span>
            <span className="font-mono text-[10px] text-sumi-600">
              {downstreamNodes.length} nodes
            </span>
          </div>
        </div>
      )}

      {/* DAG */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-panel overflow-hidden"
        style={{ height: 500 }}
      >
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <p className="animate-pulse text-sm text-sumi-600">Loading lineage DAG...</p>
          </div>
        ) : allNodes.length > 0 ? (
          <ReactFlow
            nodes={allNodes}
            edges={allEdges}
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
          </ReactFlow>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <GitBranch size={32} className="text-sumi-700" />
            <p className="text-sm text-sumi-600">
              {artifactId
                ? "No lineage data found for this artifact"
                : "Enter an artifact ID above to explore its lineage"}
            </p>
          </div>
        )}
      </motion.div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {Object.entries(relationColors).map(([rel, color]) => (
          <div key={rel} className="flex items-center gap-1.5">
            <div className="h-2 w-4 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[10px] font-medium capitalize text-sumi-600">
              {rel.replace(/_/g, " ")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
