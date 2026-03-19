"use client";

import { CommandPostWorkspace } from "@/components/chat/CommandPostWorkspace";

interface ChatPanelProps {
  onClose: () => void;
}

export function ChatPanel({ onClose }: ChatPanelProps) {
  return <CommandPostWorkspace variant="panel" onClose={onClose} />;
}
