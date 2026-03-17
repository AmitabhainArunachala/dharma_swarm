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
  isStreaming: boolean;
  activeTools: string[];
  error: string | null;
  _setMessages: (
    profileId: string,
    fn: (prev: ChatMessage[]) => ChatMessage[],
  ) => void;
  _setStreaming: (v: boolean) => void;
  _setActiveTools: (fn: (prev: string[]) => string[]) => void;
  _setError: (v: string | null) => void;
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
      isStreaming: false,
      activeTools: [],
      error: null,

      _setMessages: (profileId, fn) =>
        set((s) => ({
          messagesByProfile: {
            ...s.messagesByProfile,
            [profileId]: fn(s.messagesByProfile[profileId] ?? []),
          },
        })),
      _setStreaming: (v) => set({ isStreaming: v }),
      _setActiveTools: (fn) => set((s) => ({ activeTools: fn(s.activeTools) })),
      _setError: (v) => set({ error: v }),

      clearMessages: (profileId) =>
        set((s) => ({
          messagesByProfile: {
            ...s.messagesByProfile,
            [profileId]: [],
          },
          error: null,
          activeTools: [],
          isStreaming: false,
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
      // Only persist messages — streaming/activeTools are ephemeral
      partialize: (state) => ({
        messagesByProfile: state.messagesByProfile,
      }),
      // Reset ephemeral state on rehydrate (prevents stuck spinner)
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isStreaming = false;
          state.activeTools = [];
          state.error = null;
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
    isStreaming,
    activeTools,
    error,
    _setMessages,
    _setStreaming,
    _setActiveTools,
    _setError,
    clearMessages,
  } = useChatStore();
  const [status, setStatus] = useState<ChatStatusOut | null>(null);
  const messages = messagesByProfile[profileId] ?? [];

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
    _setStreaming(false);
    _setActiveTools(() => []);
  }, [_setStreaming, _setActiveTools]);

  const sendMessage = useCallback(
    async (content: string, context?: string) => {
      _setError(null);
      _setActiveTools(() => []);

      const currentProfileId = profileId || status?.default_profile_id || DEFAULT_CHAT_PROFILE_ID;

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
      _setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // Snapshot current messages for the API payload
        const currentMessages =
          useChatStore.getState().messagesByProfile[currentProfileId] ?? [];
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
                _setError(parsed.error);
                break;
              }

              if (parsed.tool_call) {
                const toolName = parsed.tool_call.name;
                _setActiveTools((prev) => [...prev, toolName]);
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
                _setActiveTools((prev) => prev.filter((t) => t !== toolName));
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
          _setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        _setStreaming(false);
        _setActiveTools(() => []);
        abortRef.current = null;
      }
    },
    [_setMessages, _setStreaming, _setActiveTools, _setError, profileId, status],
  );

  return {
    messages,
    isStreaming,
    activeTools,
    error,
    status,
    profileId,
    sendMessage,
    clearMessages: () => clearMessages(profileId),
    stopStreaming,
  };
}
