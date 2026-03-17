"use client";

/**
 * DHARMA COMMAND — Core chat interface with tool activity feed.
 * Reusable across full-page, panel, and overlay modes.
 */

import { useRef, useEffect, useState, type KeyboardEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Square,
  Trash2,
  Sparkles,
  User,
  Loader2,
  Terminal,
  FileText,
  Search,
  Database,
  CheckCircle2,
  Wrench,
} from "lucide-react";
import { useChat, type ChatMessage, type ToolEvent } from "@/hooks/useChat";
import { getChatProfiles, resolveChatProfile, shortProfileLabel } from "@/lib/chatProfiles";
import { colors } from "@/lib/theme";

interface ChatInterfaceProps {
  className?: string;
  showHeader?: boolean;
  compact?: boolean;
  profileId?: string;
  onProfileChange?: (profileId: string) => void;
  allowProfileSwitch?: boolean;
}

const TOOL_ICONS: Record<string, typeof Terminal> = {
  read_file: FileText,
  write_file: FileText,
  edit_file: FileText,
  shell_exec: Terminal,
  grep_search: Search,
  glob_files: Search,
  swarm_status: Database,
  evolution_query: Database,
  stigmergy_query: Database,
  trace_query: Database,
  agent_control: Wrench,
};

function formatTokenCount(value: number | undefined): string {
  if (!value) return "8k";
  if (value >= 1000) {
    const compact = value % 1000 === 0 ? value / 1000 : value / 1000;
    return `${Number(compact.toFixed(1)).toString()}k`;
  }
  return String(value);
}

function profileAccentColor(accent: string): string {
  if (accent === "kinpaku") return colors.kinpaku;
  if (accent === "botan") return colors.botan;
  if (accent === "rokusho") return colors.rokusho;
  if (accent === "fuji") return colors.fuji;
  if (accent === "bengara") return colors.bengara;
  return colors.aozora;
}

export function ChatInterface({
  className = "",
  showHeader = true,
  compact = false,
  profileId,
  onProfileChange,
  allowProfileSwitch = true,
}: ChatInterfaceProps) {
  const {
    messages,
    isStreaming,
    activeTools,
    error,
    status,
    sendMessage,
    clearMessages,
    stopStreaming,
  } = useChat(profileId);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const profiles = getChatProfiles(status);
  const activeProfile = resolveChatProfile(
    status,
    profileId ?? status?.default_profile_id ?? profiles[0]?.id ?? "claude_opus",
  );
  const accentColor = profileAccentColor(activeProfile.accent);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTools]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    sendMessage(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`flex h-full flex-col ${className}`}>
      {showHeader && (
        <div
          className="flex items-center justify-between border-b px-4 py-3"
          style={{ borderColor: colors.sumi[700] + "66" }}
        >
          <div className="flex items-center gap-2.5">
            <Sparkles size={16} className="text-aozora" />
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="font-heading text-sm font-bold tracking-wide"
                style={{ color: accentColor }}
              >
                {activeProfile.label}
              </span>
              <span className="rounded-full bg-rokusho/15 px-2 py-0.5 font-mono text-[10px] text-rokusho">
                {status?.tools ?? 11} tools
              </span>
              <span className="rounded-full bg-aozora/15 px-2 py-0.5 font-mono text-[10px] text-aozora">
                {status?.max_tool_rounds ?? 40} rounds
              </span>
              <span className="rounded-full bg-kinpaku/15 px-2 py-0.5 font-mono text-[10px] text-kinpaku">
                {formatTokenCount(status?.max_tokens)} out
              </span>
              <span className="rounded-full bg-sumi-800 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                {activeProfile.model}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {allowProfileSwitch && profiles.length > 1 && onProfileChange && (
              <div className="flex items-center gap-1 rounded-lg border border-sumi-700/40 bg-sumi-850/70 p-1">
                {profiles.map((profile) => {
                  const isActive = profile.id === activeProfile.id;
                  const profileAccent = profileAccentColor(profile.accent);
                  return (
                    <button
                      key={profile.id}
                      onClick={() => onProfileChange(profile.id)}
                      className="rounded-md px-2 py-1 font-mono text-[10px] transition-colors"
                      style={{
                        color: isActive ? profileAccent : colors.sumi[600],
                        background: isActive
                          ? `color-mix(in srgb, ${profileAccent} 14%, transparent)`
                          : "transparent",
                      }}
                      title={profile.summary}
                    >
                      {shortProfileLabel(profile)}
                    </button>
                  );
                })}
              </div>
            )}
            <button
              onClick={clearMessages}
              className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
              title="Clear conversation"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Messages + tool activity */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState
            compact={compact}
            profileLabel={activeProfile.label}
            onSuggestion={(s) => sendMessage(s)}
          />
        ) : (
          <div className="space-y-1 px-4 py-3">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} compact={compact} />
              ))}
            </AnimatePresence>

            {/* Active tool indicator */}
            {activeTools.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 px-9 py-1"
              >
                <Loader2 size={12} className="animate-spin text-kinpaku" />
                <span className="font-mono text-[11px] text-kinpaku">
                  {activeTools.map((t) => t.replace("_", " ")).join(", ")}
                </span>
              </motion.div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {error && (
        <div className="px-4 py-2">
          <div className="rounded-lg border border-bengara/30 bg-bengara/10 px-3 py-2 text-xs text-bengara">
            {error}
          </div>
        </div>
      )}

      {/* Input */}
      <div
        className="border-t px-4 py-3"
        style={{ borderColor: colors.sumi[700] + "66" }}
      >
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask ${shortProfileLabel(activeProfile)} — it can inspect, edit, and steer the swarm...`}
            rows={1}
            className={`flex-1 resize-none rounded-lg border border-sumi-700/40 bg-sumi-850 ${
              compact ? "px-3 py-2" : "px-4 py-3"
            } text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-aozora/50`}
            style={{ maxHeight: "120px", minHeight: compact ? "36px" : "44px" }}
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
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="flex shrink-0 items-center justify-center rounded-lg bg-aozora/20 p-2.5 text-aozora transition-all hover:bg-aozora/30 disabled:opacity-30"
              title="Send message (Enter)"
            >
              <Send size={16} />
            </button>
          )}
        </div>
        <p className="mt-1.5 text-center font-mono text-[9px] text-sumi-600">
          Shift+Enter newline · {status?.history_message_limit ?? 120} msg context ·{" "}
          {status?.timeout_seconds ?? 300}s timeout · reads files · runs shell · queries swarm
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tool event badge
// ---------------------------------------------------------------------------

function ToolEventBadge({ event }: { event: ToolEvent }) {
  const Icon = TOOL_ICONS[event.name] || Wrench;
  const isCall = event.type === "call";

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-1.5 rounded-md border border-sumi-700/30 bg-sumi-850/80 px-2 py-1"
    >
      {isCall ? (
        <Icon size={11} className="text-kinpaku" />
      ) : (
        <CheckCircle2 size={11} className="text-rokusho" />
      )}
      <span className="font-mono text-[10px] text-kitsurubami">
        {event.name.replace(/_/g, " ")}
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
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ message, compact }: { message: ChatMessage; compact: boolean }) {
  const isUser = message.role === "user";
  const px = compact ? "px-3 py-2" : "px-4 py-3";
  const hasTools = message.toolEvents && message.toolEvents.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-1"
    >
      {/* Tool events (above the message) */}
      {hasTools && (
        <div className="flex flex-wrap gap-1 pl-9">
          {message.toolEvents!.map((te, i) => (
            <ToolEventBadge key={`${te.name}-${te.type}-${i}`} event={te} />
          ))}
        </div>
      )}

      {/* Message */}
      <div className={`flex gap-2.5 ${isUser ? "justify-end" : "justify-start"}`}>
        {!isUser && (
          <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-aozora/15">
            <Sparkles size={12} className="text-aozora" />
          </div>
        )}
        <div
          className={`max-w-[85%] rounded-xl ${px} ${
            isUser
              ? "bg-aozora/15 text-torinoko"
              : "bg-sumi-800/80 text-torinoko/90"
          }`}
        >
          {/* Only show bubble if there's content or it's streaming */}
          {(message.content || (!isUser && !hasTools)) && (
            <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {message.content || (
                <span className="inline-flex items-center gap-1 text-sumi-600">
                  <Loader2 size={12} className="animate-spin" />
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
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({
  compact,
  profileLabel,
  onSuggestion,
}: {
  compact: boolean;
  profileLabel: string;
  onSuggestion: (text: string) => void;
}) {
  const suggestions = [
    "What's the swarm health? Check traces and anomalies.",
    "Read swarm.py and summarize the architecture",
    "Which agents are silent? Dig into the traces.",
    "Run the test suite and report results",
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-aozora/10">
        <Sparkles size={24} className="text-aozora" />
      </div>
      <h3 className="font-heading text-lg font-bold text-torinoko">
        DHARMA COMMAND Console
      </h3>
      <p className="mt-1 text-center text-xs text-sumi-600">
        {profileLabel} with full system access — files, shell, swarm, evolution
      </p>
      {!compact && (
        <div className="mt-6 grid w-full max-w-md grid-cols-2 gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => onSuggestion(s)}
              className="rounded-lg border border-sumi-700/30 bg-sumi-850/50 px-3 py-2.5 text-left text-xs text-kitsurubami transition-all hover:border-aozora/30 hover:bg-sumi-800"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
