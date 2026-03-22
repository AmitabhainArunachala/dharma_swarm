export type ChatSessionConnectionPhase =
  | "idle"
  | "pending"
  | "linking"
  | "linked"
  | "degraded";

export interface ChatSessionConnectionState {
  phase: ChatSessionConnectionPhase;
  sessionLabel: string;
  socketLabel: string;
}

export function startPendingChatSession(previousSessionId?: string): string {
  void previousSessionId;
  return "";
}

export function buildChatSessionConnectionState(args: {
  sessionId?: string;
  isStreaming?: boolean;
  wsConnected?: boolean;
  feedAdvertised?: boolean;
}): ChatSessionConnectionState {
  const sessionId = args.sessionId?.trim() ?? "";
  const sessionLabel = sessionId || (args.isStreaming ? "allocating" : "idle");

  if (args.feedAdvertised === false) {
    return {
      phase: "degraded",
      sessionLabel,
      socketLabel: "not advertised",
    };
  }

  if (!sessionId) {
    if (args.isStreaming) {
      return {
        phase: "pending",
        sessionLabel: "allocating",
        socketLabel: "awaiting session",
      };
    }

    return {
      phase: "idle",
      sessionLabel,
      socketLabel: "idle",
    };
  }

  if (args.wsConnected) {
    return {
      phase: "linked",
      sessionLabel: sessionId,
      socketLabel: "linked",
    };
  }

  return {
    phase: "linking",
    sessionLabel: sessionId,
    socketLabel: args.isStreaming ? "linking" : "waiting",
  };
}
