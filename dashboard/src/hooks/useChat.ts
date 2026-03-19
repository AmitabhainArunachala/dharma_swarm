"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { BASE_URL, fetchChatStatus } from "@/lib/api";
import { DEFAULT_CHAT_PROFILE_ID } from "@/lib/chatProfiles";
import type { ChatStatusOut } from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ToolEvent {
  type: "call" | "result";
  name: string;
  args?: Record<string, unknown>;
  summary?: string;
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  toolEvents?: ToolEvent[];
}

// ---------------------------------------------------------------------------
// Zustand store — persists to sessionStorage (survives tab switches)
// ---------------------------------------------------------------------------

interface ChatStore {
  messagesByProfile: Record<string, ChatMessage[]>;
  sessionIdByProfile: Record<string, string>;
  isStreamingByProfile: Record<string, boolean>;
  activeToolsByProfile: Record<string, string[]>;
  errorByProfile: Record<string, string | null>;
  _setMessages: (
    profileId: string,
    fn: (prev: ChatMessage[]) => ChatMessage[],
  ) => void;
  _setStreaming: (profileId: string, v: boolean) => void;
  _setActiveTools: (
    profileId: string,
    fn: (prev: string[]) => string[],
  ) => void;
  _setSessionId: (profileId: string, sessionId: string) => void;
  _setError: (profileId: string, v: string | null) => void;
  clearMessages: (profileId: string) => void;
}

let msgCounter = 0;
function nextId(): string {
  return `msg-${Date.now()}-${++msgCounter}`;
}

const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      messagesByProfile: {},
      sessionIdByProfile: {},
      isStreamingByProfile: {},
      activeToolsByProfile: {},
      errorByProfile: {},

      _setMessages: (profileId, fn) =>
        set((s) => ({
          messagesByProfile: {
            ...s.messagesByProfile,
            [profileId]: fn(s.messagesByProfile[profileId] ?? []),
          },
        })),
      _setStreaming: (profileId, v) =>
        set((s) => ({
          isStreamingByProfile: {
            ...s.isStreamingByProfile,
            [profileId]: v,
          },
        })),
      _setActiveTools: (profileId, fn) =>
        set((s) => ({
          activeToolsByProfile: {
            ...s.activeToolsByProfile,
            [profileId]: fn(s.activeToolsByProfile[profileId] ?? []),
          },
        })),
      _setSessionId: (profileId, sessionId) =>
        set((s) => ({
          sessionIdByProfile: {
            ...s.sessionIdByProfile,
            [profileId]: sessionId,
          },
        })),
      _setError: (profileId, v) =>
        set((s) => ({
          errorByProfile: {
            ...s.errorByProfile,
            [profileId]: v,
          },
        })),

      clearMessages: (profileId) =>
        set((s) => ({
          messagesByProfile: {
            ...s.messagesByProfile,
            [profileId]: [],
          },
          sessionIdByProfile: {
            ...s.sessionIdByProfile,
            [profileId]: "",
          },
          errorByProfile: {
            ...s.errorByProfile,
            [profileId]: null,
          },
          activeToolsByProfile: {
            ...s.activeToolsByProfile,
            [profileId]: [],
          },
          isStreamingByProfile: {
            ...s.isStreamingByProfile,
            [profileId]: false,
          },
        })),
    }),
    {
      name: "dharma-chat",
      storage: createJSONStorage(() => {
        if (typeof window !== "undefined") return sessionStorage;
        // SSR fallback — no-op storage
        return {
          getItem: () => null,
          setItem: () => undefined,
          removeItem: () => undefined,
          length: 0,
          clear: () => undefined,
          key: () => null,
        } satisfies Storage;
      }),
      // Persist messages + server session ids. Streaming/tool state is ephemeral.
      partialize: (state) => ({
        messagesByProfile: state.messagesByProfile,
        sessionIdByProfile: state.sessionIdByProfile,
      }),
      // Reset ephemeral state on rehydrate (prevents stuck spinner)
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isStreamingByProfile = {};
          state.activeToolsByProfile = {};
          state.errorByProfile = {};
        }
      },
    },
  ),
);

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

interface UseChatReturn {
  messages: ChatMessage[];
  sessionId: string;
  isStreaming: boolean;
  activeTools: string[];
  error: string | null;
  status: ChatStatusOut | null;
  profileId: string;
  sendMessage: (content: string, context?: string) => Promise<void>;
  clearMessages: () => void;
  stopStreaming: () => void;
}

const DEFAULT_HISTORY_MESSAGE_LIMIT = 120;

export function useChat(profileId: string = DEFAULT_CHAT_PROFILE_ID): UseChatReturn {
  const {
    messagesByProfile,
    sessionIdByProfile,
    isStreamingByProfile,
    activeToolsByProfile,
    errorByProfile,
    _setMessages,
    _setStreaming,
    _setActiveTools,
    _setSessionId,
    _setError,
    clearMessages,
  } = useChatStore();
  const [status, setStatus] = useState<ChatStatusOut | null>(null);
  const activeProfileId = profileId || status?.default_profile_id || DEFAULT_CHAT_PROFILE_ID;
  const messages = messagesByProfile[activeProfileId] ?? [];
  const sessionId = sessionIdByProfile[activeProfileId] ?? "";
  const isStreaming = isStreamingByProfile[activeProfileId] ?? false;
  const activeTools = activeToolsByProfile[activeProfileId] ?? [];
  const error = errorByProfile[activeProfileId] ?? null;

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    void fetchChatStatus()
      .then((res) => {
        if (!cancelled && res.status === "ok") {
          setStatus(res.data);
        }
      })
      .catch(() => {
        // Ignore status fetch failures; the chat route itself will report runtime errors.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    _setStreaming(activeProfileId, false);
    _setActiveTools(activeProfileId, () => []);
  }, [_setStreaming, _setActiveTools, activeProfileId]);

  const sendMessage = useCallback(
    async (content: string, context?: string) => {
      _setError(activeProfileId, null);
      _setActiveTools(activeProfileId, () => []);

      const currentProfileId = activeProfileId;

      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      };

      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        toolEvents: [],
      };

      _setMessages(currentProfileId, (prev) => [...prev, userMsg, assistantMsg]);
      _setStreaming(currentProfileId, true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // Snapshot current messages for the API payload
        const storeState = useChatStore.getState();
        const currentMessages = storeState.messagesByProfile[currentProfileId] ?? [];
        const currentSessionId = storeState.sessionIdByProfile[currentProfileId] ?? "";
        const historyForApi = currentMessages
          .filter((m) => m.role !== "system")
          .slice(-(status?.history_message_limit ?? DEFAULT_HISTORY_MESSAGE_LIMIT))
          .map((m) => ({ role: m.role, content: m.content }));

        const res = await fetch(`${BASE_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: historyForApi,
            context: context || undefined,
            profile_id: currentProfileId,
            session_id: currentSessionId || undefined,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const body = await res.text().catch(() => "");
          throw new Error(`Chat API error ${res.status}: ${body}`);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6).trim();
            if (data === "[DONE]") break;

            try {
              const parsed = JSON.parse(data);

              if (parsed.error) {
                _setError(currentProfileId, parsed.error);
                break;
              }

              if (parsed.session?.id) {
                _setSessionId(currentProfileId, String(parsed.session.id));
                continue;
              }

              if (parsed.tool_call) {
                const toolName = parsed.tool_call.name;
                _setActiveTools(currentProfileId, (prev) => [...prev, toolName]);
                _setMessages(currentProfileId, (prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      toolEvents: [
                        ...(last.toolEvents || []),
                        {
                          type: "call",
                          name: toolName,
                          args: parsed.tool_call.args,
                          timestamp: new Date().toISOString(),
                        },
                      ],
                    };
                  }
                  return updated;
                });
                continue;
              }

              if (parsed.tool_result) {
                const toolName = parsed.tool_result.name;
                _setActiveTools(currentProfileId, (prev) => prev.filter((t) => t !== toolName));
                _setMessages(currentProfileId, (prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      toolEvents: [
                        ...(last.toolEvents || []),
                        {
                          type: "result",
                          name: toolName,
                          summary: parsed.tool_result.summary,
                          timestamp: new Date().toISOString(),
                        },
                      ],
                    };
                  }
                  return updated;
                });
                continue;
              }

              if (parsed.content) {
                _setMessages(currentProfileId, (prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      content: last.content + parsed.content,
                    };
                  }
                  return updated;
                });
              }
            } catch {
              // skip malformed chunks
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          // User cancelled
        } else {
          _setError(currentProfileId, err instanceof Error ? err.message : String(err));
        }
      } finally {
        _setStreaming(currentProfileId, false);
        _setActiveTools(currentProfileId, () => []);
        abortRef.current = null;
      }
    },
    [
      _setMessages,
      _setStreaming,
      _setActiveTools,
      _setSessionId,
      _setError,
      activeProfileId,
      sessionId,
      status,
    ],
  );

  return {
    messages,
    sessionId,
    isStreaming,
    activeTools,
    error,
    status,
    profileId: activeProfileId,
    sendMessage,
    clearMessages: () => clearMessages(activeProfileId),
    stopStreaming,
  };
}
