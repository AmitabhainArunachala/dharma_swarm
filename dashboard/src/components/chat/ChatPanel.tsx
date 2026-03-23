"use client";

import { CommandPostWorkspace } from "@/components/chat/CommandPostWorkspace";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";

interface ChatPanelProps {
  onClose: () => void;
}

export function ChatPanel({ onClose }: ChatPanelProps) {
  const { chatStatus } = useRuntimeControlPlane();

  return (
    <CommandPostWorkspace
      variant="panel"
      onClose={onClose}
      runtimeChatStatus={chatStatus}
    />
  );
}
