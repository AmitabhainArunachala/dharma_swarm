"use client";

import { AnimatePresence } from "framer-motion";
import { Header } from "@/components/layout/Header";
import { OperatorMicrographics } from "@/components/layout/OperatorMicrographics";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { BackendStatus } from "@/components/ui/ErrorBanner";
import { KeyboardNav } from "@/components/ui/KeyboardNav";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";

/**
 * Dashboard layout wrapper.
 * Renders breadcrumb header, page content, and optional split chat panel.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { panelOpen, togglePanel, closePanel } = useChatWorkspace();

  return (
    <div className="flex min-h-screen flex-col">
      <KeyboardNav />
      <Header onToggleChat={() => togglePanel()} chatOpen={panelOpen} />
      <div className="flex flex-1">
        <div className={`flex-1 p-6 transition-all ${panelOpen ? "pr-3" : ""}`}>
          <div className="flex flex-col gap-6">
            <BackendStatus />
            <OperatorMicrographics />
            {children}
          </div>
        </div>
      </div>

      {/* Half-screen split chat panel */}
      <AnimatePresence>
        {panelOpen && <ChatPanel onClose={closePanel} />}
      </AnimatePresence>
    </div>
  );
}
