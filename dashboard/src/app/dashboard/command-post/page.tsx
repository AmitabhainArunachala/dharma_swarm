"use client";

import { motion } from "framer-motion";
import { CommandPostWorkspace } from "@/components/chat/CommandPostWorkspace";

export default function CommandPostPage() {
  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h1 className="glow-aozora font-heading text-3xl font-bold tracking-tight text-aozora">
          Live Command Post
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-sumi-600">
          Resident Claude and resident Codex side by side, with explicit relay controls and a live
          session telemetry rail beneath them.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.05 }}
      >
        <CommandPostWorkspace variant="page" />
      </motion.div>
    </div>
  );
}
