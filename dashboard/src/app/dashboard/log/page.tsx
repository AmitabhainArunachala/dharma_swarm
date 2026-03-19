"use client";

/**
 * Conversation Log — every user message and AI response, timestamped.
 * Promise tracking: extracted commitments from assistant responses.
 * The anti-amnesia page.
 */

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";

interface LogEntry {
  timestamp: string;
  role: string;
  interface?: string;
  session_id?: string;
  content: string;
  metadata?: Record<string, unknown>;
}

interface PromiseEntry {
  timestamp: string;
  session_id?: string;
  interface?: string;
  count: number;
  promises: string[];
}

interface LogStats {
  total_entries: number;
  by_role: Record<string, number>;
  by_interface: Record<string, number>;
  unique_sessions: number;
  promises_detected: number;
  hours_covered: number;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8420";

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ConversationLogPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [promises, setPromises] = useState<PromiseEntry[]>([]);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [tab, setTab] = useState<"log" | "promises" | "stats">("log");
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState<string>("all");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const unwrap = (json: Record<string, unknown>) =>
        json && typeof json === "object" && "data" in json ? json.data : json;
      const [logRes, promRes, statRes] = await Promise.all([
        fetch(`${BASE}/api/conversation-log/recent?hours=${hours}`).then(r => r.ok ? r.json() : {data:[]}).then(unwrap),
        fetch(`${BASE}/api/conversation-log/promises?hours=${hours}`).then(r => r.ok ? r.json() : {data:[]}).then(unwrap),
        fetch(`${BASE}/api/conversation-log/stats?hours=${hours}`).then(r => r.ok ? r.json() : {data:null}).then(unwrap),
      ]);
      setEntries((logRes as LogEntry[]) ?? []);
      setPromises((promRes as PromiseEntry[]) ?? []);
      setStats((statRes as LogStats) ?? null);
    } catch {
      // API not available — show empty state
    }
    setLoading(false);
  }, [hours]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh every 30s
  useEffect(() => {
    const id = setInterval(fetchData, 30000);
    return () => clearInterval(id);
  }, [fetchData]);

  const filteredEntries = roleFilter === "all"
    ? entries
    : entries.filter(e => e.role === roleFilter);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            Conversation Log
          </h1>
          <p className="text-sm text-sumi-400">
            Every exchange, timestamped. Every promise, tracked.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="rounded-md border border-sumi-700 bg-sumi-800 px-3 py-1.5 text-sm text-sumi-200"
          >
            <option value={1}>Last hour</option>
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 3 days</option>
            <option value={168}>Last 7 days</option>
          </select>
          <button
            onClick={fetchData}
            className="rounded-md bg-aozora/20 px-3 py-1.5 text-sm text-aozora hover:bg-aozora/30 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="EXCHANGES" value={stats.total_entries} />
          <StatCard label="USER MSGS" value={stats.by_role?.user ?? 0} />
          <StatCard label="AI RESPONSES" value={stats.by_role?.assistant ?? 0} />
          <StatCard label="PROMISES" value={stats.promises_detected} accent />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-sumi-700/50">
        {(["log", "promises", "stats"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-aozora text-aozora"
                : "text-sumi-400 hover:text-sumi-200"
            }`}
          >
            {t === "log" ? "Timeline" : t === "promises" ? "Promises" : "Stats"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading ? (
        <div className="py-12 text-center text-sumi-500">Loading conversation log...</div>
      ) : tab === "log" ? (
        <div className="space-y-2">
          {/* Role filter */}
          <div className="flex gap-2 pb-2">
            {["all", "user", "assistant", "system"].map(r => (
              <button
                key={r}
                onClick={() => setRoleFilter(r)}
                className={`rounded-full px-3 py-1 text-xs transition-colors ${
                  roleFilter === r
                    ? "bg-aozora/20 text-aozora"
                    : "bg-sumi-800 text-sumi-400 hover:text-sumi-200"
                }`}
              >
                {r === "all" ? "All" : r === "user" ? "You" : r === "assistant" ? "AI" : "System"}
              </button>
            ))}
          </div>

          {filteredEntries.length === 0 ? (
            <div className="py-12 text-center text-sumi-500">
              No conversation entries yet. Start talking and they'll appear here.
            </div>
          ) : (
            <div className="max-h-[600px] overflow-y-auto space-y-1">
              {[...filteredEntries].reverse().map((entry, i) => (
                <LogRow key={i} entry={entry} />
              ))}
            </div>
          )}
        </div>
      ) : tab === "promises" ? (
        <div className="space-y-4">
          {promises.length === 0 ? (
            <div className="py-12 text-center text-sumi-500">No promises detected yet.</div>
          ) : (
            [...promises].reverse().map((p, i) => (
              <div key={i} className="rounded-lg border border-amber-900/30 bg-amber-950/20 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-amber-400 font-mono">{p.timestamp?.slice(0, 19)}</span>
                  <span className="text-xs text-sumi-400">
                    {p.count} promise{p.count !== 1 ? "s" : ""} via {p.interface ?? "?"}
                  </span>
                </div>
                <ul className="space-y-1">
                  {p.promises.map((pr, j) => (
                    <li key={j} className="text-sm text-sumi-200 pl-3 border-l-2 border-amber-700/50">
                      {pr.length > 200 ? pr.slice(0, 200) + "..." : pr}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      ) : (
        /* Stats tab */
        <div className="space-y-4">
          {stats ? (
            <>
              <div className="rounded-lg border border-sumi-700/50 bg-sumi-800/50 p-4">
                <h3 className="text-sm font-medium text-sumi-300 mb-3">By Interface</h3>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(stats.by_interface ?? {}).map(([iface, count]) => (
                    <div key={iface} className="flex justify-between text-sm">
                      <span className="text-sumi-400">{iface}</span>
                      <span className="text-sumi-200 font-mono">{String(count)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-sumi-700/50 bg-sumi-800/50 p-4">
                <h3 className="text-sm font-medium text-sumi-300 mb-2">Sessions</h3>
                <p className="text-2xl font-mono text-sumi-200">{stats.unique_sessions}</p>
              </div>
            </>
          ) : (
            <div className="py-12 text-center text-sumi-500">No stats available.</div>
          )}
        </div>
      )}
    </motion.div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 ${
      accent
        ? "border-amber-900/30 bg-amber-950/20"
        : "border-sumi-700/50 bg-sumi-800/50"
    }`}>
      <div className="text-xs font-medium text-sumi-400">{label}</div>
      <div className={`text-2xl font-mono ${accent ? "text-amber-400" : "text-sumi-100"}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function LogRow({ entry }: { entry: LogEntry }) {
  const isUser = entry.role === "user";
  const isSystem = entry.role === "system";
  const [expanded, setExpanded] = useState(false);
  const content = entry.content ?? "";
  const preview = content.length > 300 && !expanded ? content.slice(0, 300) + "..." : content;

  return (
    <div
      className={`rounded-md border px-3 py-2 cursor-pointer transition-colors ${
        isUser
          ? "border-aozora/20 bg-aozora/5 hover:bg-aozora/10"
          : isSystem
          ? "border-sumi-700/30 bg-sumi-900/50"
          : "border-sumi-700/30 bg-sumi-800/30 hover:bg-sumi-800/50"
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className={`inline-block w-8 text-center rounded text-xs font-bold py-0.5 ${
          isUser ? "bg-aozora/20 text-aozora" : isSystem ? "bg-sumi-700 text-sumi-400" : "bg-emerald-900/30 text-emerald-400"
        }`}>
          {isUser ? "YOU" : isSystem ? "SYS" : "AI"}
        </span>
        <span className="text-xs text-sumi-500 font-mono">{entry.timestamp?.slice(0, 19)}</span>
        <span className="text-xs text-sumi-600">{timeAgo(entry.timestamp)}</span>
        {entry.interface && (
          <span className="text-xs text-sumi-600 ml-auto">{entry.interface}</span>
        )}
      </div>
      <div className="text-sm text-sumi-200 whitespace-pre-wrap break-words leading-relaxed">
        {preview}
      </div>
    </div>
  );
}
