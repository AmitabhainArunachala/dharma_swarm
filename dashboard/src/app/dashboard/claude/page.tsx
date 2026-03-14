"use client";

/**
 * DHARMA COMMAND — Claude full-page chat (L1).
 * Full-screen Claude Opus 4.6 interface with swarm context injection.
 */

import { motion } from "framer-motion";
import { ChatInterface } from "@/components/chat/ChatInterface";

export default function ClaudePage() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex h-[calc(100vh-4rem)] flex-col"
    >
      <ChatInterface showHeader />
    </motion.div>
  );
}
