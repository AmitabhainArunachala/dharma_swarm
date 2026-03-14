"use client";

/**
 * DHARMA COMMAND -- Workflows page (L5, placeholder).
 * Coming soon: Visual workflow builder.
 */

import { motion } from "framer-motion";
import { Workflow, Puzzle, ArrowRight, Layers } from "lucide-react";
import { colors } from "@/lib/theme";

export default function WorkflowsPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="glass-panel mx-auto max-w-lg p-10 text-center"
      >
        {/* Icon cluster */}
        <div className="mb-6 flex items-center justify-center gap-3">
          <motion.div
            animate={{ rotate: [0, 5, -5, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          >
            <Puzzle size={28} style={{ color: colors.botan, opacity: 0.6 }} />
          </motion.div>
          <motion.div
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          >
            <Workflow size={40} style={{ color: colors.aozora }} />
          </motion.div>
          <motion.div
            animate={{ rotate: [0, -5, 5, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
          >
            <Layers size={28} style={{ color: colors.kinpaku, opacity: 0.6 }} />
          </motion.div>
        </div>

        <h1 className="glow-aozora mb-3 font-heading text-2xl font-bold text-aozora">
          Visual Workflow Builder
        </h1>

        <p className="mb-6 text-sm leading-relaxed text-sumi-600">
          Compose multi-agent workflows with a node-based visual editor.
          Chain skills, gates, and tasks into directed acyclic graphs.
          Route data between agents with conditional branching and
          parallel execution lanes.
        </p>

        <div className="mb-6 space-y-2">
          {[
            "Drag-and-drop node composition",
            "Skill chaining with typed ports",
            "Conditional branching and merge nodes",
            "Real-time execution visualization",
            "Template library for common patterns",
          ].map((feature, i) => (
            <motion.div
              key={feature}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 + i * 0.08 }}
              className="flex items-center gap-2 text-xs text-kitsurubami"
            >
              <ArrowRight size={10} style={{ color: colors.aozora }} />
              {feature}
            </motion.div>
          ))}
        </div>

        <div
          className="inline-block rounded-full px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.15em]"
          style={{
            color: colors.aozora,
            backgroundColor: `color-mix(in srgb, ${colors.aozora} 10%, transparent)`,
            border: `1px solid color-mix(in srgb, ${colors.aozora} 20%, transparent)`,
          }}
        >
          Coming Soon
        </div>
      </motion.div>
    </div>
  );
}
