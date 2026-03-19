"use client";

/**
 * DHARMA COMMAND -- Qwen 3.5 Code Surgeon
 * In-house bug fixer with full tool access.
 * Chat interface (SSE streaming) + agent status sidebar.
 */

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Send,
  ArrowLeft,
  Zap,
  Clock,
  Activity,
  Bug,
  Square,
  Trash2,
  User,
  Loader2,
  Terminal,
  FileText,
  Search,
  Wrench,
  CheckCircle2,
  ListTodo,
  TrendingUp,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import Link from "next/link";
import { colors, glowText, glowBox } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";
import { useAgent } from "@/hooks/useAgent";
import { BASE_URL } from "@/lib/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROFILE_ID = "qwen35_surgeon";
const AGENT_ID = "qwen35-surgeon";
const ACCENT = colors.botan;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ToolEvent {
  type: "call" | "result";
  name: string;
  args?: Record<string, unknown>;
  summary?: string;
  timestamp: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  toolEvents?: ToolEvent[];
}

// ---------------------------------------------------------------------------
// Conversation persistence
// ---------------------------------------------------------------------------

interface SavedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  profileId: string;
}

const CONVERSATIONS_KEY = `dharma_chat_conversations_${PROFILE_ID}`;
const ACTIVE_CONVO_KEY = `dharma_chat_active_${PROFILE_ID}`;
const MAX_CONVERSATIONS = 10;

function generateConvoId(): string {
  return `convo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function truncateTitle(text: string, maxLen = 60): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 3) + "...";
}

function loadConversations(): SavedConversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedConversation[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveConversations(conversations: SavedConversation[]): void {
  if (typeof window === "undefined") return;
  try {
    // Keep only the most recent MAX_CONVERSATIONS, newest first
    const trimmed = conversations.slice(0, MAX_CONVERSATIONS);
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage full or unavailable -- silent fail
  }
}

function loadActiveConvoId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(ACTIVE_CONVO_KEY);
  } catch {
    return null;
  }
}

function saveActiveConvoId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(ACTIVE_CONVO_KEY, id);
  } catch {
    // silent fail
  }
}

// ---------------------------------------------------------------------------
// Tool display helpers
// ---------------------------------------------------------------------------

const TOOL_ICONS: Record<string, typeof Terminal> = {
  read_file: FileText,
  write_file: FileText,
  edit_file: FileText,
  shell_exec: Terminal,
  grep_search: Search,
  glob_files: Search,
  swarm_status: Activity,
  evolution_query: TrendingUp,
  stigmergy_query: Bug,
};

function toolLabel(name: string): string {
  const labels: Record<string, string> = {
    read_file: "Reading file",
    write_file: "Writing file",
    edit_file: "Editing file",
    shell_exec: "Running shell",
    grep_search: "Searching",
    glob_files: "Globbing files",
    swarm_status: "Querying swarm",
    evolution_query: "Querying evolution",
    stigmergy_query: "Querying stigmergy",
    trace_query: "Querying traces",
    agent_control: "Agent control",
  };
  return labels[name] ?? name.replace(/_/g, " ");
}

function formatToolArgs(name: string, args: Record<string, unknown>): string {
  if (name === "read_file" || name === "write_file" || name === "edit_file") {
    return String(args.path || "").split("/").pop() || "";
  }
  if (name === "shell_exec") return String(args.command || "").slice(0, 40);
  if (name === "grep_search") return String(args.pattern || "");
  if (name === "glob_files") return String(args.pattern || "");
  const first = Object.values(args)[0];
  return first != null ? String(first).slice(0, 30) : "";
}

// ---------------------------------------------------------------------------
// Message ID generator
// ---------------------------------------------------------------------------

let msgCounter = 0;
function nextId(): string {
  return `qw35-${Date.now()}-${++msgCounter}`;
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Dispatch task types
// ---------------------------------------------------------------------------

interface DispatchTask {
  id: string;
  title: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  startedAt: string;
  completedAt?: string;
  elapsedMs?: number;
  success?: boolean;
  output: string;
  toolEvents: ToolEvent[];
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

type TabId = "chat" | "tasks";

export default function Qwen35Page() {
  const [activeTab, setActiveTab] = useState<TabId>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Conversation persistence state
  const [conversations, setConversations] = useState<SavedConversation[]>([]);
  const [activeConvoId, setActiveConvoId] = useState<string | null>(null);
  const convoInitialized = useRef(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const {
    agent,
    healthStats,
    assignedTasks,
    fitnessHistory,
    isLoading: agentLoading,
  } = useAgent(AGENT_ID);

  // -------------------------------------------------------------------------
  // Conversation persistence: load on mount
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (convoInitialized.current) return;
    convoInitialized.current = true;

    const saved = loadConversations();
    setConversations(saved);

    const lastActiveId = loadActiveConvoId();
    const target = saved.find((c) => c.id === lastActiveId) ?? saved[0];

    if (target) {
      setActiveConvoId(target.id);
      setMessages(target.messages);
    } else {
      // No saved conversations -- create a fresh one
      const newId = generateConvoId();
      setActiveConvoId(newId);
      saveActiveConvoId(newId);
    }
  }, []);

  // -------------------------------------------------------------------------
  // Conversation persistence: save messages on every change
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (!convoInitialized.current || !activeConvoId) return;

    // Only persist if there are actual messages to save
    if (messages.length === 0) return;

    const now = new Date().toISOString();
    const firstUserMsg = messages.find((m) => m.role === "user");
    const title = firstUserMsg
      ? truncateTitle(firstUserMsg.content)
      : "New conversation";

    setConversations((prev) => {
      const existing = prev.findIndex((c) => c.id === activeConvoId);
      const updated: SavedConversation = {
        id: activeConvoId,
        title,
        createdAt:
          existing >= 0 ? prev[existing].createdAt : now,
        updatedAt: now,
        messages,
        profileId: PROFILE_ID,
      };

      let next: SavedConversation[];
      if (existing >= 0) {
        next = [...prev];
        next[existing] = updated;
      } else {
        next = [updated, ...prev];
      }

      // Sort newest first, trim to max
      next.sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      );
      next = next.slice(0, MAX_CONVERSATIONS);

      saveConversations(next);
      return next;
    });
  }, [messages, activeConvoId]);

  // -------------------------------------------------------------------------
  // Conversation switching
  // -------------------------------------------------------------------------

  const switchConversation = useCallback(
    (convoId: string) => {
      if (convoId === activeConvoId || isStreaming) return;

      const target = conversations.find((c) => c.id === convoId);
      if (!target) return;

      abortRef.current?.abort();
      abortRef.current = null;
      setIsStreaming(false);
      setActiveTools([]);
      setError(null);

      setActiveConvoId(convoId);
      setMessages(target.messages);
      saveActiveConvoId(convoId);
    },
    [activeConvoId, conversations, isStreaming],
  );

  const startNewConversation = useCallback(() => {
    if (isStreaming) return;

    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setActiveTools([]);
    setError(null);

    const newId = generateConvoId();
    setActiveConvoId(newId);
    setMessages([]);
    saveActiveConvoId(newId);
  }, [isStreaming]);

  const deleteConversation = useCallback(
    (convoId: string) => {
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== convoId);
        saveConversations(next);

        // If we deleted the active conversation, switch to the next one or start fresh
        if (convoId === activeConvoId) {
          if (next.length > 0) {
            setActiveConvoId(next[0].id);
            setMessages(next[0].messages);
            saveActiveConvoId(next[0].id);
          } else {
            const newId = generateConvoId();
            setActiveConvoId(newId);
            setMessages([]);
            saveActiveConvoId(newId);
          }
        }

        return next;
      });
    },
    [activeConvoId],
  );

  // Auto-scroll on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTools]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // -------------------------------------------------------------------------
  // Send message + SSE streaming
  // -------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || isStreaming) return;

      setError(null);
      setActiveTools([]);

      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
      };

      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        toolEvents: [],
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // Build history for the API
        const allMessages = [...messages, userMsg];
        const historyForApi = allMessages
          .slice(-120)
          .map((m) => ({ role: m.role, content: m.content }));

        const res = await fetch(`${BASE_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: historyForApi,
            profile_id: PROFILE_ID,
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
                setError(parsed.error);
                break;
              }

              // Tool call event
              if (parsed.tool_call) {
                const toolName: string = parsed.tool_call.name;
                setActiveTools((prev) => [...prev, toolName]);
                setMessages((prev) => {
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

              // Tool result event
              if (parsed.tool_result) {
                const toolName: string = parsed.tool_result.name;
                setActiveTools((prev) => prev.filter((t) => t !== toolName));
                setMessages((prev) => {
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

              // Text content chunk
              if (parsed.content) {
                setMessages((prev) => {
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

              // Also handle OpenAI-style delta format
              const delta = parsed.choices?.[0]?.delta?.content;
              if (delta) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      content: last.content + delta,
                    };
                  }
                  return updated;
                });
              }
            } catch {
              // Skip malformed chunks
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          // User cancelled -- no-op
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        setIsStreaming(false);
        setActiveTools([]);
        abortRef.current = null;
      }
    },
    [isStreaming, messages],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setActiveTools([]);
  }, []);

  const clearMessages = useCallback(() => {
    startNewConversation();
  }, [startNewConversation]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const trimmed = input.trim();
      if (trimmed && !isStreaming) {
        setInput("");
        sendMessage(trimmed);
      }
    }
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    sendMessage(trimmed);
  };

  // -------------------------------------------------------------------------
  // Derive agent status info
  // -------------------------------------------------------------------------

  const agentStatus = agent?.status ?? "unknown";
  const isOnline = ["busy", "idle", "starting"].includes(agentStatus);
  const latestFitness =
    fitnessHistory.length > 0
      ? fitnessHistory[fitnessHistory.length - 1]
      : null;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="flex h-full flex-col">
      {/* ── Identity header ── */}
      <motion.header
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="shrink-0 border-b px-5 py-4"
        style={{ borderColor: `${colors.sumi[700]}66` }}
      >
        <div className="flex items-center gap-4">
          <Link
            href="/dashboard/agents"
            className="flex items-center justify-center rounded-lg p-2 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            aria-label="Back to agents"
          >
            <ArrowLeft size={18} />
          </Link>

          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
            style={{
              background: `color-mix(in srgb, ${ACCENT} 14%, transparent)`,
              border: `1px solid color-mix(in srgb, ${ACCENT} 30%, transparent)`,
              boxShadow: glowBox(ACCENT, 0.25),
            }}
          >
            <Bug size={20} style={{ color: ACCENT }} />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3">
              <h1
                className="font-heading text-xl font-bold tracking-tight"
                style={{ color: ACCENT, textShadow: glowText(ACCENT, 0.5) }}
              >
                Qwen 3.5 Code Surgeon
              </h1>
              <span
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] font-medium"
                style={{
                  color: isOnline ? colors.rokusho : colors.sumi[600],
                  background: isOnline
                    ? `color-mix(in srgb, ${colors.rokusho} 14%, transparent)`
                    : `color-mix(in srgb, ${colors.sumi[600]} 14%, transparent)`,
                }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{
                    backgroundColor: isOnline
                      ? colors.rokusho
                      : colors.sumi[600],
                    boxShadow: isOnline
                      ? `0 0 6px ${colors.rokusho}`
                      : "none",
                  }}
                />
                {agentStatus.toUpperCase()}
              </span>
              <span className="rounded-full bg-sumi-800 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                {agent?.model ?? "qwen3.5-122b"}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-sumi-600">
              In-house code surgeon -- bug fixes, test runs, surgical edits
            </p>
          </div>
        </div>
      </motion.header>

      {/* ── Tab bar ── */}
      <div
        className="flex shrink-0 gap-1 border-b px-5 py-1"
        style={{ borderColor: `${colors.sumi[700]}40` }}
      >
        {(["chat", "tasks"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="rounded-md px-4 py-1.5 font-mono text-xs font-medium transition-all"
            style={{
              color: activeTab === tab ? ACCENT : colors.sumi[600],
              backgroundColor:
                activeTab === tab
                  ? `color-mix(in srgb, ${ACCENT} 12%, transparent)`
                  : "transparent",
            }}
          >
            {tab === "chat" ? "Chat" : "Tasks"}
          </button>
        ))}
      </div>

      {/* ── Main content: Chat/Tasks + Sidebar ── */}
      <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_380px]">
        {activeTab === "tasks" ? (
          <Qwen35TasksTab />
        ) : (
        /* ── Chat column ── */
        <div className="flex min-h-0 flex-col border-r" style={{ borderColor: `${colors.sumi[700]}40` }}>
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto">
            {messages.length === 0 ? (
              <Qwen35EmptyState onSuggestion={sendMessage} />
            ) : (
              <div className="space-y-1 px-4 py-3">
                <AnimatePresence initial={false}>
                  {messages.map((msg) => (
                    <Qwen35MessageBubble key={msg.id} message={msg} />
                  ))}
                </AnimatePresence>

                {/* Active tool indicator */}
                {activeTools.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center gap-2 px-9 py-1"
                  >
                    <Loader2
                      size={12}
                      className="animate-spin"
                      style={{ color: ACCENT }}
                    />
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: ACCENT }}
                    >
                      {activeTools.map((t) => toolLabel(t)).join(", ")}
                    </span>
                  </motion.div>
                )}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Error banner */}
          {error && (
            <div className="px-4 py-2">
              <div className="rounded-lg border border-bengara/30 bg-bengara/10 px-3 py-2 text-xs text-bengara">
                {error}
              </div>
            </div>
          )}

          {/* Input area */}
          <div
            className="shrink-0 border-t px-4 py-3"
            style={{ borderColor: `${colors.sumi[700]}66` }}
          >
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Paste an error, describe a bug, or ask for a code fix..."
                rows={1}
                className="flex-1 resize-none rounded-lg border border-sumi-700/40 bg-sumi-850 px-4 py-3 text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-rokusho/50"
                style={{ maxHeight: "120px", minHeight: "44px" }}
                onInput={(e) => {
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = Math.min(el.scrollHeight, 120) + "px";
                }}
              />
              {isStreaming ? (
                <button
                  onClick={stopStreaming}
                  className="flex shrink-0 items-center justify-center rounded-lg border border-bengara/30 bg-bengara/10 p-2.5 text-bengara transition-all hover:bg-bengara/20"
                  title="Stop generating"
                  aria-label="Stop generating"
                >
                  <Square size={16} />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim()}
                  className="flex shrink-0 items-center justify-center rounded-lg p-2.5 transition-all disabled:opacity-30"
                  style={{
                    backgroundColor: `color-mix(in srgb, ${ACCENT} 20%, transparent)`,
                    color: ACCENT,
                  }}
                  onMouseEnter={(e) => {
                    if (input.trim()) {
                      e.currentTarget.style.backgroundColor = `color-mix(in srgb, ${ACCENT} 30%, transparent)`;
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = `color-mix(in srgb, ${ACCENT} 20%, transparent)`;
                  }}
                  title="Send message (Enter)"
                  aria-label="Send message"
                >
                  <Send size={16} />
                </button>
              )}
            </div>
            <div className="mt-1.5 flex items-center justify-between">
              <p className="font-mono text-[9px] text-sumi-600">
                Shift+Enter newline -- Enter to send -- reads files -- runs shell -- queries swarm
              </p>
              <button
                onClick={clearMessages}
                className="rounded p-1 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
                title="Clear conversation"
                aria-label="Clear conversation"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        </div>
        )}

        {/* ── Sidebar ── */}
        <motion.aside
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.45, delay: 0.1 }}
          className="overflow-y-auto p-4"
          style={{ backgroundColor: `${colors.sumi[950]}80` }}
        >
          <div className="space-y-4">
            {/* Conversations panel */}
            <section className="glass-panel-subtle p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare size={14} style={{ color: ACCENT }} />
                  <h2 className="font-heading text-sm font-semibold text-torinoko">
                    Conversations
                  </h2>
                  <span className="rounded-full bg-sumi-800 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                    {conversations.length}
                  </span>
                </div>
                <button
                  onClick={startNewConversation}
                  disabled={isStreaming}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[10px] font-medium transition-all disabled:opacity-30"
                  style={{
                    color: ACCENT,
                    backgroundColor: `color-mix(in srgb, ${ACCENT} 12%, transparent)`,
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = `color-mix(in srgb, ${ACCENT} 22%, transparent)`;
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = `color-mix(in srgb, ${ACCENT} 12%, transparent)`;
                  }}
                  title="New conversation"
                >
                  <Plus size={11} />
                  New Chat
                </button>
              </div>

              {conversations.length > 0 ? (
                <div className="space-y-1">
                  {conversations.map((convo) => {
                    const isActive = convo.id === activeConvoId;
                    return (
                      <div
                        key={convo.id}
                        className="group flex items-center gap-2 rounded-lg px-3 py-2 transition-all"
                        style={{
                          backgroundColor: isActive
                            ? `color-mix(in srgb, ${ACCENT} 12%, transparent)`
                            : "transparent",
                          border: isActive
                            ? `1px solid color-mix(in srgb, ${ACCENT} 25%, transparent)`
                            : "1px solid transparent",
                          cursor: isStreaming && !isActive ? "not-allowed" : "pointer",
                        }}
                        onMouseEnter={(e) => {
                          if (!isActive) {
                            e.currentTarget.style.backgroundColor = `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isActive) {
                            e.currentTarget.style.backgroundColor = "transparent";
                          }
                        }}
                      >
                        <button
                          onClick={() => switchConversation(convo.id)}
                          disabled={isStreaming && !isActive}
                          className="min-w-0 flex-1 text-left"
                        >
                          <p
                            className="truncate text-xs leading-tight"
                            style={{
                              color: isActive ? colors.torinoko : colors.kitsurubami,
                            }}
                          >
                            {convo.title}
                          </p>
                          <p className="mt-0.5 font-mono text-[9px] text-sumi-600">
                            {timeAgo(convo.updatedAt)}
                            {" -- "}
                            {convo.messages.length} msg{convo.messages.length !== 1 ? "s" : ""}
                          </p>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteConversation(convo.id);
                          }}
                          className="shrink-0 rounded p-1 text-sumi-600 opacity-0 transition-all hover:bg-sumi-800 hover:text-bengara group-hover:opacity-100"
                          title="Delete conversation"
                          aria-label={`Delete conversation: ${convo.title}`}
                        >
                          <X size={11} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="py-3 text-center text-xs text-sumi-600">
                  No saved conversations
                </p>
              )}
            </section>

            {/* Agent stats card */}
            <section className="glass-panel-subtle p-4">
              <div className="mb-3 flex items-center gap-2">
                <Bot size={14} style={{ color: ACCENT }} />
                <h2 className="font-heading text-sm font-semibold text-torinoko">
                  Agent Status
                </h2>
              </div>

              {agentLoading ? (
                <div className="flex items-center gap-2 py-6 text-sumi-600">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-xs">Loading agent data...</span>
                </div>
              ) : agent ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <StatCell
                      icon={<Activity size={12} />}
                      label="Status"
                      value={agent.status}
                      accent={isOnline ? ACCENT : colors.sumi[600]}
                    />
                    <StatCell
                      icon={<Zap size={12} />}
                      label="Role"
                      value={agent.role}
                      accent={colors.fuji}
                    />
                    <StatCell
                      icon={<Clock size={12} />}
                      label="Last Seen"
                      value={
                        agent.last_heartbeat
                          ? timeAgo(agent.last_heartbeat)
                          : "never"
                      }
                      accent={colors.kitsurubami}
                    />
                    <StatCell
                      icon={<CheckCircle2 size={12} />}
                      label="Tasks Done"
                      value={String(agent.tasks_completed)}
                      accent={colors.rokusho}
                    />
                  </div>

                  {agent.current_task && (
                    <div
                      className="rounded-lg p-3"
                      style={{
                        backgroundColor: `color-mix(in srgb, ${ACCENT} 8%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${ACCENT} 20%, transparent)`,
                      }}
                    >
                      <p className="font-mono text-[10px] uppercase tracking-widest text-sumi-600">
                        Current Task
                      </p>
                      <p className="mt-1 text-xs text-torinoko">
                        {agent.current_task}
                      </p>
                    </div>
                  )}

                  {healthStats && (
                    <div className="grid grid-cols-2 gap-2">
                      <StatCell
                        icon={<TrendingUp size={12} />}
                        label="Success Rate"
                        value={`${(healthStats.success_rate * 100).toFixed(0)}%`}
                        accent={
                          healthStats.success_rate > 0.8
                            ? colors.rokusho
                            : colors.kinpaku
                        }
                      />
                      <StatCell
                        icon={<Activity size={12} />}
                        label="Total Actions"
                        value={String(healthStats.total_actions)}
                        accent={colors.aozora}
                      />
                    </div>
                  )}

                  <div className="rounded-lg border border-sumi-700/20 bg-sumi-900/50 px-3 py-2">
                    <p className="font-mono text-[10px] text-sumi-600">Provider</p>
                    <p className="mt-0.5 font-mono text-xs text-torinoko">
                      {agent.provider}
                    </p>
                    <p className="font-mono text-[10px] text-sumi-600 mt-1.5">Model</p>
                    <p className="mt-0.5 font-mono text-xs text-torinoko">
                      {agent.model}
                    </p>
                  </div>

                  {agent.error && (
                    <div className="rounded-lg border border-bengara/20 bg-bengara/5 px-3 py-2">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-bengara">
                        Last Error
                      </p>
                      <p className="mt-1 text-xs text-bengara/80">
                        {agent.error}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-sumi-700/30 bg-sumi-850/40 p-6 text-center">
                  <Bot size={20} className="mx-auto mb-2 text-sumi-600" />
                  <p className="text-xs text-sumi-600">
                    Agent not found. It may not be registered yet.
                  </p>
                  <p className="mt-1 text-[10px] text-sumi-600">
                    The chat interface still works -- messages will be sent to the GLM-5 profile.
                  </p>
                </div>
              )}
            </section>

            {/* Assigned tasks */}
            <section className="glass-panel-subtle p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ListTodo size={14} style={{ color: ACCENT }} />
                  <h2 className="font-heading text-sm font-semibold text-torinoko">
                    Task Queue
                  </h2>
                </div>
                <span className="rounded-full bg-sumi-800 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                  {assignedTasks.length}
                </span>
              </div>

              {assignedTasks.length > 0 ? (
                <div className="space-y-2">
                  {assignedTasks.slice(0, 8).map((task) => (
                    <TaskRow key={task.id} task={task} />
                  ))}
                  {assignedTasks.length > 8 && (
                    <p className="text-center font-mono text-[10px] text-sumi-600">
                      +{assignedTasks.length - 8} more
                    </p>
                  )}
                </div>
              ) : (
                <p className="py-4 text-center text-xs text-sumi-600">
                  No tasks assigned
                </p>
              )}
            </section>

            {/* Fitness data */}
            {latestFitness && (
              <section className="glass-panel-subtle p-4">
                <div className="mb-3 flex items-center gap-2">
                  <TrendingUp size={14} style={{ color: ACCENT }} />
                  <h2 className="font-heading text-sm font-semibold text-torinoko">
                    Fitness
                  </h2>
                </div>

                <div className="space-y-2">
                  <FitnessBar
                    label="Composite"
                    value={latestFitness.composite_fitness}
                    accent={ACCENT}
                  />
                  <FitnessBar
                    label="Success Rate"
                    value={latestFitness.success_rate}
                    accent={colors.rokusho}
                  />
                  <FitnessBar
                    label="Quality"
                    value={latestFitness.avg_quality}
                    accent={colors.fuji}
                  />
                  <FitnessBar
                    label="Speed"
                    value={latestFitness.speed_score}
                    accent={colors.aozora}
                  />

                  <div className="mt-2 grid grid-cols-2 gap-2 pt-2 border-t border-sumi-700/20">
                    <div>
                      <p className="font-mono text-[10px] text-sumi-600">
                        Total Calls
                      </p>
                      <p className="font-mono text-xs text-torinoko">
                        {latestFitness.total_calls}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-[10px] text-sumi-600">
                        Total Tokens
                      </p>
                      <p className="font-mono text-xs text-torinoko">
                        {latestFitness.total_tokens.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-[10px] text-sumi-600">
                        Avg Latency
                      </p>
                      <p className="font-mono text-xs text-torinoko">
                        {latestFitness.avg_latency.toFixed(1)}s
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-[10px] text-sumi-600">
                        Cost
                      </p>
                      <p className="font-mono text-xs text-torinoko">
                        ${latestFitness.total_cost_usd.toFixed(4)}
                      </p>
                    </div>
                  </div>

                  <p className="font-mono text-[9px] text-sumi-600 mt-1">
                    Computed {timeAgo(latestFitness.computed_at)}
                  </p>
                </div>
              </section>
            )}
          </div>
        </motion.aside>
      </div>
    </div>
  );
}

// ===========================================================================
// Sub-components
// ===========================================================================

// ---------------------------------------------------------------------------
// Message Bubble
// ---------------------------------------------------------------------------

function Qwen35MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const hasTools = message.toolEvents && message.toolEvents.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-1"
    >
      {/* Tool event pills above the message */}
      {hasTools && (
        <div className="flex flex-wrap gap-1 pl-9">
          {message.toolEvents!.map((te, i) => (
            <Qwen35ToolPill key={`${te.name}-${te.type}-${i}`} event={te} />
          ))}
        </div>
      )}

      {/* Message */}
      <div
        className={`flex gap-2.5 ${isUser ? "justify-end" : "justify-start"}`}
      >
        {!isUser && (
          <div
            className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
            style={{
              background: `color-mix(in srgb, ${ACCENT} 15%, transparent)`,
            }}
          >
            <Bug size={12} style={{ color: ACCENT }} />
          </div>
        )}

        <div
          className={`max-w-[85%] rounded-xl px-4 py-3 ${
            isUser
              ? "bg-sumi-800 text-torinoko"
              : "text-torinoko/90"
          }`}
          style={
            isUser
              ? undefined
              : {
                  backgroundColor: `color-mix(in srgb, ${colors.sumi[800]} 80%, transparent)`,
                  borderLeft: `2px solid color-mix(in srgb, ${ACCENT} 40%, transparent)`,
                }
          }
        >
          {(message.content || (!isUser && !hasTools)) && (
            <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {message.content || (
                <span className="inline-flex items-center gap-1.5 text-sumi-600">
                  <span
                    className="inline-block h-2 w-2 rounded-full animate-pulse"
                    style={{ backgroundColor: ACCENT }}
                  />
                  Thinking...
                </span>
              )}
            </div>
          )}
        </div>

        {isUser && (
          <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-fuji/15">
            <User size={12} className="text-fuji" />
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Tool Event Pill
// ---------------------------------------------------------------------------

function Qwen35ToolPill({ event }: { event: ToolEvent }) {
  const Icon = TOOL_ICONS[event.name] || Wrench;
  const isCall = event.type === "call";

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-1.5 rounded-md border border-sumi-700/30 bg-sumi-850/80 px-2 py-1"
    >
      {isCall ? (
        <Icon size={11} style={{ color: ACCENT }} />
      ) : (
        <CheckCircle2 size={11} className="text-rokusho" />
      )}
      <span className="font-mono text-[10px] text-kitsurubami">
        {toolLabel(event.name)}
      </span>
      {isCall && event.args && (
        <span className="max-w-[180px] truncate font-mono text-[10px] text-sumi-600">
          {formatToolArgs(event.name, event.args)}
        </span>
      )}
      {!isCall && event.summary && (
        <span className="max-w-[200px] truncate font-mono text-[10px] text-sumi-600">
          {event.summary}
        </span>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function Qwen35EmptyState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  const suggestions = [
    "Run pytest on dharma_swarm and fix any failures",
    "The agent_control tool fails when spawning -- diagnose and fix",
    "Find all TODO and FIXME comments in the codebase and prioritize them",
    "Check the API for unhandled exceptions and add error handling",
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <div
        className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl"
        style={{
          background: `color-mix(in srgb, ${ACCENT} 10%, transparent)`,
          border: `1px solid color-mix(in srgb, ${ACCENT} 25%, transparent)`,
          boxShadow: glowBox(ACCENT, 0.2),
        }}
      >
        <Bug size={28} style={{ color: ACCENT }} />
      </div>
      <h3
        className="font-heading text-lg font-bold"
        style={{ color: ACCENT, textShadow: glowText(ACCENT, 0.4) }}
      >
        Qwen 3.5 Code Surgeon
      </h3>
      <p className="mt-1.5 max-w-sm text-center text-xs text-sumi-600">
        In-house bug fixer with full tool access. Paste errors, describe bugs,
        or ask for surgical code fixes. Reads, edits, tests, verifies.
      </p>
      <div className="mt-6 grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="rounded-lg border border-sumi-700/30 bg-sumi-850/50 px-3 py-2.5 text-left text-xs text-kitsurubami transition-all hover:bg-sumi-800"
            style={{
              borderColor: `color-mix(in srgb, ${ACCENT} 15%, ${colors.sumi[700]})`,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = `color-mix(in srgb, ${ACCENT} 35%, ${colors.sumi[700]})`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = `color-mix(in srgb, ${ACCENT} 15%, ${colors.sumi[700]})`;
            }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat Cell (sidebar)
// ---------------------------------------------------------------------------

function StatCell({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-lg border border-sumi-700/20 bg-sumi-900/50 px-3 py-2">
      <div className="flex items-center gap-1.5">
        <span style={{ color: accent }}>{icon}</span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-sumi-600">
          {label}
        </span>
      </div>
      <p className="mt-1 font-mono text-xs text-torinoko">{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task Row (sidebar)
// ---------------------------------------------------------------------------

function TaskRow({
  task,
}: {
  task: {
    id: string;
    title: string;
    status: string;
    priority: string;
    created_at: string;
    result: string | null;
  };
}) {
  const statusColors: Record<string, string> = {
    pending: colors.kinpaku,
    running: colors.aozora,
    completed: colors.rokusho,
    failed: colors.bengara,
    queued: colors.fuji,
  };
  const accent = statusColors[task.status] ?? colors.sumi[600];

  return (
    <div className="rounded-lg border border-sumi-700/20 bg-sumi-900/50 px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-torinoko leading-tight">{task.title}</p>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 font-mono text-[9px]"
          style={{
            color: accent,
            backgroundColor: `color-mix(in srgb, ${accent} 14%, transparent)`,
          }}
        >
          {task.status}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-sumi-600">
        <span
          className="rounded px-1 py-0.5 font-mono"
          style={{
            backgroundColor: `color-mix(in srgb, ${
              task.priority === "high"
                ? colors.bengara
                : task.priority === "medium"
                  ? colors.kinpaku
                  : colors.sumi[600]
            } 10%, transparent)`,
            color:
              task.priority === "high"
                ? colors.bengara
                : task.priority === "medium"
                  ? colors.kinpaku
                  : colors.sumi[600],
          }}
        >
          {task.priority}
        </span>
        <span>{timeAgo(task.created_at)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fitness Bar (sidebar)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Tasks Tab
// ---------------------------------------------------------------------------

function Qwen35TasksTab() {
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDesc, setTaskDesc] = useState("");
  const [tasks, setTasks] = useState<DispatchTask[]>([]);
  const [isDispatching, setIsDispatching] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const dispatchTask = useCallback(async () => {
    const title = taskTitle.trim();
    if (!title || isDispatching) return;

    const task: DispatchTask = {
      id: `task-${Date.now()}`,
      title,
      description: taskDesc.trim(),
      status: "running",
      startedAt: new Date().toISOString(),
      output: "",
      toolEvents: [],
    };

    setTasks((prev) => [task, ...prev]);
    setTaskTitle("");
    setTaskDesc("");
    setIsDispatching(true);

    try {
      const res = await fetch(`${BASE_URL}/api/agents/${AGENT_ID}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, description: taskDesc.trim() }),
      });

      if (!res.ok) {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === task.id
              ? { ...t, status: "failed" as const, output: `HTTP ${res.status}` }
              : t,
          ),
        );
        setIsDispatching(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) return;

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
              setTasks((prev) =>
                prev.map((t) =>
                  t.id === task.id
                    ? { ...t, status: "failed" as const, output: t.output + "\n" + parsed.error }
                    : t,
                ),
              );
              break;
            }

            if (parsed.tool_call) {
              setTasks((prev) =>
                prev.map((t) =>
                  t.id === task.id
                    ? {
                        ...t,
                        toolEvents: [
                          ...t.toolEvents,
                          {
                            type: "call" as const,
                            name: parsed.tool_call.name,
                            args: parsed.tool_call.args,
                            timestamp: new Date().toISOString(),
                          },
                        ],
                      }
                    : t,
                ),
              );
              continue;
            }

            if (parsed.tool_result) {
              setTasks((prev) =>
                prev.map((t) =>
                  t.id === task.id
                    ? {
                        ...t,
                        toolEvents: [
                          ...t.toolEvents,
                          {
                            type: "result" as const,
                            name: parsed.tool_result.name,
                            summary: parsed.tool_result.summary,
                            timestamp: new Date().toISOString(),
                          },
                        ],
                      }
                    : t,
                ),
              );
              continue;
            }

            if (parsed.content) {
              setTasks((prev) =>
                prev.map((t) =>
                  t.id === task.id ? { ...t, output: t.output + parsed.content } : t,
                ),
              );
            }

            if (parsed.status === "completed") {
              setTasks((prev) =>
                prev.map((t) =>
                  t.id === task.id
                    ? {
                        ...t,
                        status: parsed.success ? ("completed" as const) : ("failed" as const),
                        success: parsed.success,
                        elapsedMs: parsed.elapsed_ms,
                        completedAt: new Date().toISOString(),
                      }
                    : t,
                ),
              );
            }
          } catch {
            // skip
          }
        }
      }
    } catch (err) {
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id
            ? { ...t, status: "failed" as const, output: String(err) }
            : t,
        ),
      );
    } finally {
      setIsDispatching(false);
      // Mark any still-running task as completed
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id && t.status === "running"
            ? { ...t, status: "completed" as const, completedAt: new Date().toISOString() }
            : t,
        ),
      );
    }
  }, [taskTitle, taskDesc, isDispatching]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tasks]);

  return (
    <div className="flex min-h-0 flex-col border-r" style={{ borderColor: `${colors.sumi[700]}40` }}>
      {/* Dispatch form */}
      <div className="shrink-0 border-b p-4" style={{ borderColor: `${colors.sumi[700]}40` }}>
        <div className="mb-3 flex items-center gap-2">
          <Zap size={14} style={{ color: ACCENT }} />
          <h2 className="font-heading text-sm font-semibold text-torinoko">
            Dispatch Task
          </h2>
        </div>
        <input
          value={taskTitle}
          onChange={(e) => setTaskTitle(e.target.value)}
          placeholder="Task title"
          className="mb-2 w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko placeholder-sumi-600 outline-none focus:border-rokusho/50"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              dispatchTask();
            }
          }}
        />
        <textarea
          value={taskDesc}
          onChange={(e) => setTaskDesc(e.target.value)}
          placeholder="Description (optional)"
          rows={2}
          className="mb-2 w-full resize-none rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-xs text-torinoko placeholder-sumi-600 outline-none focus:border-rokusho/50"
        />
        <button
          onClick={dispatchTask}
          disabled={!taskTitle.trim() || isDispatching}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-all disabled:opacity-30"
          style={{
            backgroundColor: `color-mix(in srgb, ${ACCENT} 20%, transparent)`,
            color: ACCENT,
          }}
        >
          {isDispatching ? (
            <>
              <Loader2 size={12} className="animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Send size={12} />
              Dispatch
            </>
          )}
        </button>
      </div>

      {/* Task history */}
      <div className="flex-1 overflow-y-auto p-4">
        {tasks.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-sumi-600">
            <ListTodo size={24} className="mb-2" />
            <p className="text-xs">No tasks dispatched yet</p>
            <p className="mt-1 text-[10px]">
              Assign a task above and watch GLM-5 execute it autonomously
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <DispatchTaskCard key={task.id} task={task} />
            ))}
            <div ref={scrollRef} />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dispatch Task Card
// ---------------------------------------------------------------------------

function DispatchTaskCard({ task }: { task: DispatchTask }) {
  const [expanded, setExpanded] = useState(task.status === "running");
  const statusColor =
    task.status === "completed"
      ? colors.rokusho
      : task.status === "failed"
        ? colors.bengara
        : task.status === "running"
          ? colors.aozora
          : colors.sumi[600];

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-sumi-700/30 bg-sumi-900/60"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start justify-between gap-2 px-3 py-2.5 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{
                backgroundColor: statusColor,
                boxShadow:
                  task.status === "running"
                    ? `0 0 6px ${statusColor}`
                    : "none",
              }}
            />
            <span className="truncate text-xs font-medium text-torinoko">
              {task.title}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-3 pl-4">
            <span
              className="rounded-full px-2 py-0.5 font-mono text-[9px]"
              style={{
                color: statusColor,
                backgroundColor: `color-mix(in srgb, ${statusColor} 14%, transparent)`,
              }}
            >
              {task.status}
            </span>
            {task.elapsedMs != null && (
              <span className="font-mono text-[10px] text-sumi-600">
                {(task.elapsedMs / 1000).toFixed(1)}s
              </span>
            )}
            <span className="font-mono text-[10px] text-sumi-600">
              {task.toolEvents.length} tool calls
            </span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-sumi-700/20 px-3 py-2">
          {/* Tool events */}
          {task.toolEvents.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {task.toolEvents.map((te, i) => (
                <Qwen35ToolPill key={`${te.name}-${te.type}-${i}`} event={te} />
              ))}
            </div>
          )}
          {/* Output */}
          {task.output && (
            <div className="max-h-48 overflow-y-auto rounded-lg bg-sumi-950/60 p-2">
              <pre className="whitespace-pre-wrap break-words text-[11px] leading-relaxed text-kitsurubami">
                {task.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Fitness Bar (sidebar)
// ---------------------------------------------------------------------------

function FitnessBar({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  // Clamp between 0 and 1 for display
  const clamped = Math.max(0, Math.min(1, value));
  const pct = (clamped * 100).toFixed(0);

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] text-sumi-600">{label}</span>
        <span className="font-mono text-[10px] text-torinoko">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-sumi-800">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{
            backgroundColor: accent,
            boxShadow: `0 0 6px color-mix(in srgb, ${accent} 50%, transparent)`,
          }}
        />
      </div>
    </div>
  );
}
