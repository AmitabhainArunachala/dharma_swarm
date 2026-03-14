"use client";

/**
 * DHARMA COMMAND -- Blocks page (L5, placeholder).
 * Coming soon: Block-based programming interface.
 */

import { motion } from "framer-motion";
import { Grid3X3, Code2, ArrowRight, Boxes } from "lucide-react";
import { colors } from "@/lib/theme";

export default function BlocksPage() {
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
            animate={{ y: [0, -3, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          >
            <Code2 size={28} style={{ color: colors.kinpaku, opacity: 0.6 }} />
          </motion.div>
          <motion.div
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          >
            <Grid3X3 size={40} style={{ color: colors.botan }} />
          </motion.div>
          <motion.div
            animate={{ y: [0, 3, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
          >
            <Boxes size={28} style={{ color: colors.fuji, opacity: 0.6 }} />
          </motion.div>
        </div>

        <h1 className="glow-botan mb-3 font-heading text-2xl font-bold text-botan">
          Block Programming
        </h1>

        <p className="mb-6 text-sm leading-relaxed text-sumi-600">
          Build agent behaviors and system configurations using
          composable blocks. Snap together pre-built logic units,
          skill invocations, gate checks, and data transformers
          into reusable programs without writing code.
        </p>

        <div className="mb-6 space-y-2">
          {[
            "Snap-together logic blocks",
            "Pre-built skill and gate blocks",
            "Variable binding and scope management",
            "Loop and conditional control flow",
            "Export to executable agent configs",
          ].map((feature, i) => (
            <motion.div
              key={feature}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 + i * 0.08 }}
              className="flex items-center gap-2 text-xs text-kitsurubami"
            >
              <ArrowRight size={10} style={{ color: colors.botan }} />
              {feature}
            </motion.div>
          ))}
        </div>

        <div
          className="inline-block rounded-full px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.15em]"
          style={{
            color: colors.botan,
            backgroundColor: `color-mix(in srgb, ${colors.botan} 10%, transparent)`,
            border: `1px solid color-mix(in srgb, ${colors.botan} 20%, transparent)`,
          }}
        >
          Coming Soon
        </div>
      </motion.div>
    </div>
  );
}
