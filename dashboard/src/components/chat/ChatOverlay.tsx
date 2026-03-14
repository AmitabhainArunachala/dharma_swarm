"use client";

/**
 * DHARMA COMMAND — Floating chat overlay.
 * Renders a bubble button + expandable chat panel.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X } from "lucide-react";
import { ChatInterface } from "./ChatInterface";

export function ChatOverlay() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Floating button */}
      <AnimatePresence>
        {!open && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", damping: 20, stiffness: 300 }}
            onClick={() => setOpen(true)}
            className="fixed bottom-6 right-6 z-[60] flex h-14 w-14 items-center justify-center rounded-full border border-aozora/30 bg-sumi-900/95 shadow-[0_0_20px_rgba(79,209,217,0.15)] backdrop-blur-md transition-all hover:border-aozora/50 hover:shadow-[0_0_30px_rgba(79,209,217,0.25)]"
            aria-label="Open Claude chat"
          >
            <MessageCircle size={22} className="text-aozora" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-[59] bg-black/20"
            />

            {/* Panel */}
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.95 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="fixed bottom-6 right-6 z-[60] flex h-[520px] w-[380px] flex-col overflow-hidden rounded-2xl border border-sumi-700/40 bg-sumi-900/95 shadow-2xl backdrop-blur-md"
            >
              {/* Close button overlaid on header */}
              <button
                onClick={() => setOpen(false)}
                className="absolute right-3 top-3 z-10 rounded p-1 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
                aria-label="Close chat"
              >
                <X size={14} />
              </button>

              <ChatInterface compact showHeader />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
