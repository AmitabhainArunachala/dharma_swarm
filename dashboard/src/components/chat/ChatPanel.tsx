"use client";

/**
 * DHARMA COMMAND — Half-screen split chat panel.
 * Slides in from the right, takes 50% width.
 */

import { motion } from "framer-motion";
import { X, Maximize2, Minimize2 } from "lucide-react";
import { useState } from "react";
import { ChatInterface } from "./ChatInterface";
import { colors } from "@/lib/theme";

interface ChatPanelProps {
  onClose: () => void;
}

export function ChatPanel({ onClose }: ChatPanelProps) {
  const [wide, setWide] = useState(false);

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 25, stiffness: 200 }}
      className={`fixed right-0 top-0 z-50 flex h-screen flex-col border-l bg-sumi-900/98 backdrop-blur-md ${
        wide ? "w-[60%]" : "w-[50%]"
      }`}
      style={{ borderColor: colors.sumi[700] + "66" }}
    >
      {/* Panel header */}
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: colors.sumi[700] + "66" }}
      >
        <span className="font-heading text-sm font-bold tracking-wide text-aozora">
          Claude Opus 4.6 — Split View
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setWide((w) => !w)}
            className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            title={wide ? "Narrow" : "Widen"}
          >
            {wide ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            onClick={onClose}
            className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            title="Close panel"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Chat */}
      <ChatInterface showHeader={false} />
    </motion.div>
  );
}
