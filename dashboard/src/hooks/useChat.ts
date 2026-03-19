"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { BASE_URL, fetchChatStatus } from "@/lib/api";
import {
  CHAT_CONTRACT_VERSION_STORAGE_KEY,
  DEFAULT_CHAT_PROFILE_ID,
  resolveChatProfileId,
} from "@/lib/chatProfiles";
import type { ChatStatusOut } from "@/lib/types";

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

const CHAT_RETRY_DELAY_MS = 1200;
const RETRYABLE_CHAT_STATUS_CODES = new Set([502, 503, 504]);
const CHAT_STORE_STORAGE_KEY = "dharma-chat";
const DEFAULT_HISTORY_MESSAGE_LIMIT = 120;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function isRetryableChatStatus(status: number): boolean {
  return RETRYABLE_CHAT_STATUS_CODES.has(status);
}

function looksLikeTransportFailure(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("failed to fetch") ||
    normalized.includes("networkerror") ||
    normalized.includes("load failed") ||
    normalized.includes("network request failed")
  );
}

function formatChatError(message: string): string {
  if (looksLikeTransportFailure(message)) {
    return "Backend unreachable. The operator API is down or restarting. Retry in a moment.";
  }

  const retryableMatch = message.match(/^Chat API error (\d{3}):/);
  if (retryableMatch && isRetryableChatStatus(Number(retryableMatch[1]))) {
    return "Backend unavailable. The operator API is restarting or overloaded. Retry in a moment.";
  }

  return message;
}

function trimTrailingEmptyAssistant(messages: ChatMessage[]): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (
    last?.role === "assistant" &&
    !last.content.trim() &&
    (!last.toolEvents || last.toolEvents.length === 0)
  ) {
    return messages.slice(0, -1);
  }
  return messages;
}

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
  _setSessionId: (profileId: string, sessionId: string) => void;
  _setStreaming: (profileId: string, value: boolean) => void;
  _setActiveTools: (
    profileId: string,
    fn: (prev: string[]) => string[],
  ) => void;
  _setError: (profileId: string, value: string | null) => void;
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
        set((state) => ({
          messagesByProfile: {
            ...state.messagesByProfile,
            [profileId]: fn(state.messagesByProfile[profileId] ?? []),
          },
        })),
      _setSessionId: (profileId, sessionId) =>
        set((state) => ({
          sessionIdByProfile: {
            ...state.sessionIdByProfile,
            [profileId]: sessionId,
          },
        })),
      _setStreaming: (profileId, value) =>
        set((state) => ({
          isStreamingByProfile: {
            ...state.isStreamingByProfile,
            [profileId]: value,
          },
        })),
      _setActiveTools: (profileId, fn) =>
        set((state) => ({
          activeToolsByProfile: {
            ...state.activeToolsByProfile,
            [profileId]: fn(state.activeToolsByProfile[profileId] ?? []),
          },
        })),
      _setError: (profileId, value) =>
        set((state) => ({
          errorByProfile: {
            ...state.errorByProfile,
            [profileId]: value,
          },
        })),
      clearMessages: (profileId) =>
        set((state) => ({
          messagesByProfile: {
            ...state.messagesByProfile,
            [profileId]: [],
          },
          sessionIdByProfile: {
            ...state.sessionIdByProfile,
            [profileId]: "",
          },
          isStreamingByProfile: {
            ...state.isStreamingByProfile,
            [profileId]: false,
          },
          activeToolsByProfile: {
            ...state.activeToolsByProfile,
            [profileId]: [],
          },
          errorByProfile: {
            ...state.errorByProfile,
            [profileId]: null,
          },
        })),
    }),
    {
      name: CHAT_STORE_STORAGE_KEY,
      storage: createJSONStorage(() => {
        if (typeof window !== "undefined") return sessionStorage;
        return {
          getItem: () => null,
          setItem: () => undefined,
          removeItem: () => undefined,
          length: 0,
          clear: () => undefined,
          key: () => null,
        } satisfies Storage;
      }),
      partialize: (state) => ({
        messagesByProfile: state.messagesByProfile,
        sessionIdByProfile: state.sessionIdByProfile,
      }),
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

function resetChatStoreState() {
  useChatStore.setState({
    messagesByProfile: {},
    sessionIdByProfile: {},
    isStreamingByProfile: {},
    activeToolsByProfile: {},
    errorByProfile: {},
  });
  useChatStore.persist.clearStorage();
}

function syncChatContractVersion(status: ChatStatusOut) {
  if (typeof window === "undefined") return;
  const version = status.chat_contract_version?.trim();
  if (!version) return;

  const previous = window.sessionStorage.getItem(CHAT_CONTRACT_VERSION_STORAGE_KEY);
  if (previous === version) return;

  resetChatStoreState();
  window.sessionStorage.setItem(CHAT_CONTRACT_VERSION_STORAGE_KEY, version);
}

interface UseChatReturn {
  messages: ChatMessage[];
  sessionId: string;
  isStreaming: boolean;
  activeTools: string[];
  error: string | null;
  status: ChatStatusOut | null;
  profileId: string;
  sendMessage: (content: string, context?: string) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  canRetry: boolean;
  clearMessages: () => void;
  stopStreaming: () => void;
}

export function useChat(profileId: string = DEFAULT_CHAT_PROFILE_ID): UseChatReturn {
  const {
    messagesByProfile,
    sessionIdByProfile,
    isStreamingByProfile,
    activeToolsByProfile,
    errorByProfile,
    _setMessages,
    _setSessionId,
    _setStreaming,
    _setActiveTools,
    _setError,
    clearMessages,
  } = useChatStore();
  const [status, setStatus] = useState<ChatStatusOut | null>(null);
  const activeProfileId = resolveChatProfileId(status, profileId);
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
          syncChatContractVersion(res.data);
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
    _setMessages(activeProfileId, trimTrailingEmptyAssistant);
  }, [_setActiveTools, _setMessages, _setStreaming, activeProfileId]);

  const fetchChatResponse = useCallback(
    async (body: string, signal: AbortSignal): Promise<Response> => {
      let attempt = 0;

      while (true) {
        try {
          const res = await fetch(`${BASE_URL}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
            signal,
          });

          if (!res.ok && isRetryableChatStatus(res.status) && attempt === 0) {
            attempt += 1;
            await delay(CHAT_RETRY_DELAY_MS);
            continue;
          }

          return res;
        } catch (err) {
          if (
            err instanceof Error &&
            err.name !== "AbortError" &&
            looksLikeTransportFailure(err.message) &&
            attempt === 0
          ) {
            attempt += 1;
            await delay(CHAT_RETRY_DELAY_MS);
            continue;
          }
          throw err;
        }
      }
    },
    [],
  );

  const streamAssistantReply = useCallback(
    async ({
      currentProfileId,
      content,
      context,
      appendUser,
    }: {
      currentProfileId: string;
      content: string;
      context?: string;
      appendUser: boolean;
    }) => {
      _setError(currentProfileId, null);
      _setActiveTools(currentProfileId, () => []);
      _setSessionId(currentProfileId, `dash-local-${currentProfileId}-${Date.now()}`);

      const now = new Date().toISOString();
      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content,
        timestamp: now,
      };

      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        timestamp: now,
        toolEvents: [],
      };

      _setMessages(currentProfileId, (prev) => {
        const base = trimTrailingEmptyAssistant(prev);
        return appendUser ? [...base, userMsg, assistantMsg] : [...base, assistantMsg];
      });
      _setStreaming(currentProfileId, true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const currentMessages =
          useChatStore.getState().messagesByProfile[currentProfileId] ?? [];
        const historyForApi = currentMessages
          .filter((message) => message.role !== "system")
          .slice(-(status?.history_message_limit ?? DEFAULT_HISTORY_MESSAGE_LIMIT))
          .map((message) => ({ role: message.role, content: message.content }));

        const res = await fetchChatResponse(
          JSON.stringify({
            messages: historyForApi,
            context: context || undefined,
            profile_id: currentProfileId,
          }),
          controller.signal,
        );

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

              if (typeof parsed.session_id === "string" && parsed.session_id) {
                _setSessionId(currentProfileId, parsed.session_id);
              }

              if (parsed.error) {
                _setMessages(currentProfileId, trimTrailingEmptyAssistant);
                _setError(currentProfileId, formatChatError(parsed.error));
                break;
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
                _setActiveTools(currentProfileId, (prev) =>
                  prev.filter((entry) => entry !== toolName),
                );
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
              // Skip malformed chunks.
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          _setMessages(currentProfileId, trimTrailingEmptyAssistant);
        } else {
          _setMessages(currentProfileId, trimTrailingEmptyAssistant);
          _setError(
            currentProfileId,
            formatChatError(err instanceof Error ? err.message : String(err)),
          );
        }
      } finally {
        _setStreaming(currentProfileId, false);
        _setActiveTools(currentProfileId, () => []);
        abortRef.current = null;
      }
    },
    [
      _setActiveTools,
      _setError,
      _setMessages,
      _setSessionId,
      _setStreaming,
      fetchChatResponse,
      status?.history_message_limit,
    ],
  );

  const sendMessage = useCallback(
    async (content: string, context?: string) => {
      const currentProfileId = resolveChatProfileId(status, profileId);
      await streamAssistantReply({
        currentProfileId,
        content,
        context,
        appendUser: true,
      });
    },
    [profileId, status, streamAssistantReply],
  );

  const retryLastMessage = useCallback(async () => {
    if (isStreaming) return;

    const currentProfileId = resolveChatProfileId(status, profileId);
    const currentMessages =
      useChatStore.getState().messagesByProfile[currentProfileId] ?? [];
    const lastUserMessage = [...currentMessages]
      .reverse()
      .find((message) => message.role === "user");

    if (!lastUserMessage) return;

    await streamAssistantReply({
      currentProfileId,
      content: lastUserMessage.content,
      appendUser: false,
    });
  }, [isStreaming, profileId, status, streamAssistantReply]);

  const canRetry = !isStreaming && messages.some((message) => message.role === "user");

  return {
    messages,
    sessionId,
    isStreaming,
    activeTools,
    error,
    status,
    profileId: activeProfileId,
    sendMessage,
    retryLastMessage,
    canRetry,
    clearMessages: () => clearMessages(activeProfileId),
    stopStreaming,
  };
}
