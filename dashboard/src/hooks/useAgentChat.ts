"use client";

import { useCallback, useEffect, useRef } from "react";
import { create } from "zustand";
import { apiPath } from "@/lib/api";

/* ─── Types ───────────────────────────────────────────────── */

export interface ToolEvent {
  type: "call" | "result";
  name: string;
  args?: Record<string, unknown>;
  summary?: string;
}

export interface AgentChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  toolEvents?: ToolEvent[];
}

/* ─── Persistent Store (survives navigation) ──────────────── */

interface AgentChatStore {
  messagesByAgent: Record<string, AgentChatMessage[]>;
  streamingByAgent: Record<string, boolean>;
  errorByAgent: Record<string, string | null>;

  getMessages: (agentId: string) => AgentChatMessage[];
  isStreaming: (agentId: string) => boolean;
  getError: (agentId: string) => string | null;

  addMessage: (agentId: string, msg: AgentChatMessage) => void;
  updateLastAssistant: (agentId: string, updater: (msg: AgentChatMessage) => AgentChatMessage) => void;
  setStreaming: (agentId: string, streaming: boolean) => void;
  setError: (agentId: string, error: string | null) => void;
  clearMessages: (agentId: string) => void;
}

export const useAgentChatStore = create<AgentChatStore>((set, get) => ({
  messagesByAgent: {},
  streamingByAgent: {},
  errorByAgent: {},

  getMessages: (agentId) => get().messagesByAgent[agentId] ?? [],
  isStreaming: (agentId) => get().streamingByAgent[agentId] ?? false,
  getError: (agentId) => get().errorByAgent[agentId] ?? null,

  addMessage: (agentId, msg) =>
    set((state) => ({
      messagesByAgent: {
        ...state.messagesByAgent,
        [agentId]: [...(state.messagesByAgent[agentId] ?? []), msg],
      },
    })),

  updateLastAssistant: (agentId, updater) =>
    set((state) => {
      const msgs = [...(state.messagesByAgent[agentId] ?? [])];
      if (msgs.length === 0) return state;
      const last = msgs[msgs.length - 1];
      if (last.role !== "assistant") return state;
      msgs[msgs.length - 1] = updater(last);
      return {
        messagesByAgent: { ...state.messagesByAgent, [agentId]: msgs },
      };
    }),

  setStreaming: (agentId, streaming) =>
    set((state) => ({
      streamingByAgent: { ...state.streamingByAgent, [agentId]: streaming },
    })),

  setError: (agentId, error) =>
    set((state) => ({
      errorByAgent: { ...state.errorByAgent, [agentId]: error },
    })),

  clearMessages: (agentId) =>
    set((state) => ({
      messagesByAgent: { ...state.messagesByAgent, [agentId]: [] },
      errorByAgent: { ...state.errorByAgent, [agentId]: null },
    })),
}));

/* ─── Hook ────────────────────────────────────────────────── */

export function useAgentChat(agentId: string) {
  const store = useAgentChatStore();
  const abortRef = useRef<AbortController | null>(null);
  const hydratedRef = useRef<Set<string>>(new Set());

  const messages = store.getMessages(agentId);
  const streaming = store.isStreaming(agentId);
  const error = store.getError(agentId);

  // Hydrate from backend on first mount (survives page refresh)
  useEffect(() => {
    if (hydratedRef.current.has(agentId)) return;
    if (store.getMessages(agentId).length > 0) {
      hydratedRef.current.add(agentId);
      return;
    }
    hydratedRef.current.add(agentId);

    fetch(apiPath(`/api/agents/${encodeURIComponent(agentId)}/chat/history`))
      .then((r) => r.json())
      .then((json) => {
        const data = json?.data ?? json;
        const history = data?.messages ?? [];
        if (history.length > 0 && store.getMessages(agentId).length === 0) {
          for (const entry of history) {
            store.addMessage(agentId, {
              id: `history-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              role: entry.role as "user" | "assistant",
              content: entry.content || "",
              timestamp: entry.timestamp || new Date().toISOString(),
            });
          }
        }
      })
      .catch(() => {});
  }, [agentId]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || store.isStreaming(agentId)) return;

      store.setError(agentId, null);

      // Remove any trailing empty assistant messages from previous failed sends
      const currentMsgs = store.getMessages(agentId);
      while (currentMsgs.length > 0 && currentMsgs[currentMsgs.length - 1].role === "assistant" && !currentMsgs[currentMsgs.length - 1].content) {
        currentMsgs.pop();
      }
      store.clearMessages(agentId);
      for (const m of currentMsgs) {
        store.addMessage(agentId, m);
      }

      const userMsg: AgentChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: content.trim(),
        timestamp: new Date().toISOString(),
      };

      const assistantMsg: AgentChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        toolEvents: [],
      };

      store.addMessage(agentId, userMsg);
      store.addMessage(agentId, assistantMsg);
      store.setStreaming(agentId, true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const allMsgs = [...store.getMessages(agentId)].slice(0, -1); // exclude empty assistant
        const apiMessages = allMsgs
          .filter((m) => m.content && m.content.trim().length > 0)
          .map((m) => ({ role: m.role, content: m.content }));
        // Keep only last 20 messages to avoid context overflow
        const trimmedMessages = apiMessages.slice(-20);

        const res = await fetch(
          apiPath(`/api/agents/${encodeURIComponent(agentId)}/chat`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: trimmedMessages }),
            signal: controller.signal,
          },
        );

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`API ${res.status}: ${text || res.statusText}`);
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
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;

            try {
              const data = JSON.parse(raw);

              if (data.content) {
                store.updateLastAssistant(agentId, (msg) => ({
                  ...msg,
                  content: msg.content + data.content,
                }));
              }

              if (data.tool_call) {
                store.updateLastAssistant(agentId, (msg) => ({
                  ...msg,
                  toolEvents: [
                    ...(msg.toolEvents ?? []),
                    { type: "call", name: data.tool_call.name, args: data.tool_call.arguments },
                  ],
                }));
              }

              if (data.tool_result) {
                store.updateLastAssistant(agentId, (msg) => ({
                  ...msg,
                  toolEvents: [
                    ...(msg.toolEvents ?? []),
                    {
                      type: "result",
                      name: data.tool_result.name ?? "tool",
                      summary: data.tool_result.output ?? data.tool_result.summary,
                    },
                  ],
                }));
              }

              if (data.error) {
                store.setError(agentId, data.error);
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          store.setError(agentId, (err as Error).message);
        }
      } finally {
        store.setStreaming(agentId, false);
        abortRef.current = null;
      }
    },
    [agentId, store],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    store.setStreaming(agentId, false);
  }, [agentId, store]);

  const clearMessages = useCallback(() => {
    store.clearMessages(agentId);
  }, [agentId, store]);

  return {
    messages,
    isStreaming: streaming,
    error,
    sendMessage,
    stopStreaming,
    clearMessages,
  };
}
