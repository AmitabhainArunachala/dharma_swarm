"use client";

/**
 * DHARMA COMMAND -- Ontology browser (L4).
 * ReactFlow graph of type nodes, with detail panel on click.
 */

import { useState, useMemo, useCallback } from "react";
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

import { Bot, ListTodo, FileCode2, Brain, Shield, Globe, X } from "lucide-react";
import { useOntologyGraph, useOntologyType } from "@/hooks/useOntology";
import { colors } from "@/lib/theme";

const categoryIcons: Record<string, typeof Bot> = {
  agent: Bot,
  task: ListTodo,
  artifact: FileCode2,
  concept: Brain,
  gate: Shield,
};

const categoryColors: Record<string, string> = {
  agent: colors.aozora,
  task: colors.botan,
  artifact: colors.kinpaku,
  concept: colors.fuji,
  gate: colors.rokusho,
};

export default function OntologyPage() {
  const { graph, isLoading } = useOntologyGraph();
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const { typeDetail, isLoading: detailLoading } = useOntologyType(selectedType);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };

    const rfNodes: Node[] = graph.nodes.map((n, i) => {
      const catColor = categoryColors[n.type] ?? colors.fuji;
      const cols = 5;
      return {
        id: n.id,
        position: n.position,
        data: {
          label: n.data.label,
          nodeType: n.type,
          propertyCount: n.data.propertyCount,
        },
        style: {
          background: colors.sumi[850],
          color: colors.torinoko,
          border: `1.5px solid ${catColor}`,
          borderRadius: 10,
          padding: "10px 14px",
          fontSize: 12,
          fontFamily: "var(--font-heading)",
          boxShadow: `0 0 12px color-mix(in srgb, ${catColor} 15%, transparent)`,
          minWidth: 120,
        },
      };
    });

    const rfEdges: Edge[] = graph.edges.map((e, i) => ({
      id: `oe-${i}`,
      source: e.source,
      target: e.target,
      label: e.label,
      labelStyle: { fill: colors.sumi[600], fontSize: 9 },
      style: { stroke: colors.sumi[600], strokeWidth: 1.2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colors.sumi[600] },
      animated: false,
    }));

    return { nodes: rfNodes, edges: rfEdges };
  }, [graph]);

  const onNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedType(node.data?.label as string ?? null);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <Globe size={24} className="text-fuji" />
          <h1 className="glow-fuji font-heading text-2xl font-bold tracking-tight text-fuji">
            Ontology Browser
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          {isLoading
            ? "Loading type graph..."
            : graph
              ? `${graph.nodes.length} types, ${graph.edges.length} links`
              : "No ontology data available."}
        </p>
      </motion.div>

      {/* Legend */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap gap-4"
      >
        {Object.entries(categoryColors).map(([cat, color]) => {
          const Icon = categoryIcons[cat] ?? Brain;
          return (
            <div key={cat} className="flex items-center gap-1.5">
              <Icon size={12} style={{ color }} />
              <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color }}>
                {cat}
              </span>
            </div>
          );
        })}
      </motion.div>

      {/* Graph */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="glass-panel overflow-hidden"
        style={{ height: 560 }}
      >
        {nodes.length > 0 ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
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
              nodeColor={(n) =>
                categoryColors[n.data?.nodeType as string] ?? colors.fuji
              }
            />
          </ReactFlow>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-sumi-600">
              {isLoading ? "Loading graph..." : "No ontology graph data"}
            </p>
          </div>
        )}
      </motion.div>

      {/* Detail panel */}
      <AnimatePresence>
        {selectedType && (
          <TypeDetailPanel
            typeName={selectedType}
            detail={typeDetail}
            loading={detailLoading}
            onClose={() => setSelectedType(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Type detail side panel
// ---------------------------------------------------------------------------

function TypeDetailPanel({
  typeName,
  detail,
  loading,
  onClose,
}: {
  typeName: string;
  detail: ReturnType<typeof useOntologyType>["typeDetail"];
  loading: boolean;
  onClose: () => void;
}) {
  const catColor = detail
    ? colors.fuji
    : colors.fuji;

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
          <div className="flex items-center gap-2.5">
            <Globe size={16} style={{ color: catColor }} />
            <h2 className="font-heading text-lg font-bold text-torinoko">
              {typeName}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-sumi-600 hover:text-torinoko"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <p className="animate-pulse text-sm text-sumi-600">Loading type details...</p>
          ) : detail ? (
            <div className="space-y-5">
              <div className="space-y-2 text-xs">
                <Row label="Name" value={detail.name} />
                <Row label="Shakti" value={detail.shakti} />
                <Row label="Telos" value={detail.telos_alignment.toFixed(2)} />
                <Row label="Security" value={detail.security_level} />
              </div>

              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                  Description
                </p>
                <p className="text-sm leading-relaxed text-torinoko/80">
                  {detail.description}
                </p>
              </div>

              {detail.properties && detail.properties.length > 0 && (
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                    Properties ({detail.properties.length})
                  </p>
                  <div className="space-y-1.5">
                    {detail.properties.map((prop) => (
                      <div
                        key={prop.name}
                        className="flex items-center justify-between rounded-md bg-sumi-850/50 px-3 py-1.5 text-xs"
                      >
                        <span className="font-mono text-torinoko">{prop.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-sumi-600">{prop.property_type}</span>
                          {prop.required && (
                            <span className="text-[8px] font-bold uppercase text-kinpaku">
                              req
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.links && detail.links.length > 0 && (
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                    Links ({detail.links.length})
                  </p>
                  <div className="space-y-1.5">
                    {detail.links.map((link) => (
                      <div
                        key={link.name}
                        className="flex items-center justify-between rounded-md bg-sumi-850/50 px-3 py-1.5 text-xs"
                      >
                        <span className="font-mono text-aozora">{link.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-sumi-600">{link.target_type}</span>
                          <span className="text-[9px] text-sumi-700">
                            [{link.cardinality}]
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.actions && detail.actions.length > 0 && (
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                    Actions ({detail.actions.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.actions.map((action) => (
                      <span
                        key={action.name}
                        className="rounded-full bg-sumi-800 px-2.5 py-0.5 font-mono text-[10px] text-kitsurubami"
                      >
                        {action.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-sumi-600">No detail found for {typeName}</p>
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
      <span className="font-mono capitalize text-torinoko">{value}</span>
    </div>
  );
}
