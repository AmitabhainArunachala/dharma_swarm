"use client";

import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Header } from "@/components/layout/Header";
import { ChatPanel } from "@/components/chat/ChatPanel";

/**
 * Dashboard layout wrapper.
 * Renders breadcrumb header, page content, and optional split chat panel.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <Header onToggleChat={() => setChatOpen((o) => !o)} chatOpen={chatOpen} />
      <div className="flex flex-1">
        <div className={`flex-1 p-6 transition-all ${chatOpen ? "pr-3" : ""}`}>
          {children}
        </div>
      </div>

      {/* Half-screen split chat panel */}
      <AnimatePresence>
        {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}
