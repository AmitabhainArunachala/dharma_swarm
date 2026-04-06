"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Send, Square, Trash2, MessageSquare } from "lucide-react";
import { useAgentWorkspace } from "../layout";
import { useAgentChat } from "@/hooks/useAgentChat";
import { stagger } from "@/components/agent-workspace/shared";
import { colors } from "@/lib/theme";

export default function AgentChatPage() {
  const { agent, config } = useAgentWorkspace();
  const agentId = agent?.agent_slug || agent?.name || "";
  const displayName = config?.display_name || agent?.name || "Agent";

  const {
    messages,
    isStreaming,
    error,
    sendMessage,
    stopStreaming,
    clearMessages,
  } = useAgentChat(agentId);

  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (!agent) return null;

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim());
    setInput("");
  };

  const suggestions = [
    "What are you working on?",
    "Show me your recent traces",
    "What\u2019s your current task?",
    "Describe your role",
  ];

  return (
    <motion.div
      className="flex flex-col glass-panel overflow-hidden"
      style={{ height: "calc(100vh - 380px)", minHeight: 400 }}
      variants={stagger.container}
      initial="hidden"
      animate="show"
    >
      {/* ── Messages ──────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div
              className="flex h-16 w-16 items-center justify-center rounded-2xl"
              style={{ backgroundColor: `color-mix(in srgb, ${colors.aozora} 10%, transparent)` }}
            >
              <MessageSquare size={32} style={{ color: colors.aozora }} />
            </div>
            <div className="text-center">
              <h3 className="font-heading text-lg font-bold text-torinoko">
                Chat with {displayName}
              </h3>
              <p className="mt-1 text-xs text-sumi-600">
                Ask about tasks, inspect state, or give direct instructions
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 mt-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setInput(s);
                    textareaRef.current?.focus();
                  }}
                  className="rounded-lg border border-sumi-700/30 px-3 py-1.5 text-xs text-kitsurubami transition-colors hover:border-aozora/30 hover:text-aozora"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-aozora/15 text-torinoko"
                    : "bg-sumi-800 text-torinoko"
                }`}
              >
                {msg.toolEvents && msg.toolEvents.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {msg.toolEvents.map((te, i) => (
                      <span
                        key={i}
                        className="rounded-full px-2 py-0.5 text-[9px] font-medium"
                        style={{
                          color: te.type === "call" ? colors.kinpaku : colors.rokusho,
                          backgroundColor:
                            te.type === "call"
                              ? `color-mix(in srgb, ${colors.kinpaku} 12%, transparent)`
                              : `color-mix(in srgb, ${colors.rokusho} 12%, transparent)`,
                        }}
                      >
                        {te.type === "call" ? "\u25B6" : "\u2713"} {te.name}
                      </span>
                    ))}
                  </div>
                )}
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {msg.content}
                </div>
                {msg.role === "assistant" &&
                  isStreaming &&
                  msg === messages[messages.length - 1] &&
                  !msg.content && (
                    <div className="flex gap-1 py-1">
                      <span
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-aozora"
                        style={{ animationDelay: "0ms" }}
                      />
                      <span
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-aozora"
                        style={{ animationDelay: "150ms" }}
                      />
                      <span
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-aozora"
                        style={{ animationDelay: "300ms" }}
                      />
                    </div>
                  )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Error ─────────────────────────────────────────── */}
      {error && (
        <div className="mx-5 mb-2 rounded-lg border border-bengara/30 bg-bengara/5 px-4 py-2 text-xs text-bengara">
          {error}
        </div>
      )}

      {/* ── Input ─────────────────────────────────────────── */}
      <div className="border-t border-sumi-700/30 px-5 py-3">
        <div className="flex items-end gap-2">
          <button
            onClick={clearMessages}
            disabled={messages.length === 0}
            className="shrink-0 rounded-lg p-2 text-sumi-600 transition-colors hover:text-bengara disabled:opacity-30"
            title="Clear conversation"
          >
            <Trash2 size={16} />
          </button>
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={`Message ${displayName}...`}
              rows={1}
              className="w-full resize-none rounded-xl border border-sumi-700/40 bg-sumi-900 px-4 py-2.5 text-sm text-torinoko placeholder-sumi-600 transition-colors focus:border-aozora/50 focus:outline-none"
              style={{ maxHeight: 120 }}
            />
          </div>
          {isStreaming ? (
            <button
              onClick={stopStreaming}
              className="shrink-0 rounded-xl bg-bengara/20 p-2.5 text-bengara transition-colors hover:bg-bengara/30"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="shrink-0 rounded-xl bg-aozora/20 p-2.5 text-aozora transition-colors hover:bg-aozora/30 disabled:opacity-30"
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
