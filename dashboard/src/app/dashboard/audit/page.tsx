"use client";

/**
 * Harness Audit — 7-dimension system health scorecard.
 */

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";

interface AuditCategory {
  name: string;
  score: number;
  max_score: number;
  details: Record<string, unknown>;
}

interface AuditReport {
  timestamp: string;
  categories: AuditCategory[];
  overall_score: number;
  duration_seconds: number;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8420";

const CATEGORY_LABELS: Record<string, string> = {
  tool_coverage: "Tool Coverage",
  context_efficiency: "Context Efficiency",
  quality_gates: "Quality Gates",
  memory_persistence: "Memory Persistence",
  eval_coverage: "Eval Coverage",
  security_guardrails: "Security Guardrails",
  cost_efficiency: "Cost Efficiency",
};

function scoreColor(score: number): string {
  if (score >= 7) return "emerald";
  if (score >= 4) return "amber";
  return "red";
}

export default function AuditPage() {
  const [latest, setLatest] = useState<AuditReport | null>(null);
  const [trend, setTrend] = useState<AuditReport[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const unwrap = (json: Record<string, unknown>) =>
        json && typeof json === "object" && "data" in json ? json.data : json;
      const [latestRes, trendRes] = await Promise.all([
        fetch(`${BASE}/api/audit/latest`).then(r => r.ok ? r.json() : {data:null}).then(unwrap),
        fetch(`${BASE}/api/audit/trend`).then(r => r.ok ? r.json() : {data:[]}).then(unwrap),
      ]);
      setLatest(latestRes as AuditReport | null);
      setTrend((trendRes as AuditReport[]) ?? []);
    } catch { /* API unavailable */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            System Audit
          </h1>
          <p className="text-sm text-sumi-400">
            7-dimension scorecard tracking system health over time.
          </p>
        </div>
        <button
          onClick={fetchData}
          className="rounded-md bg-aozora/20 px-3 py-1.5 text-sm text-aozora hover:bg-aozora/30 transition-colors"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-12 text-center text-sumi-500">Loading audit...</div>
      ) : !latest ? (
        <div className="py-12 text-center text-sumi-500">
          No audit results yet. Run: <code className="text-aozora">dgc audit</code>
        </div>
      ) : (
        <>
          {/* Overall score */}
          <div className="flex items-center gap-6">
            <div className={`rounded-xl border p-6 text-center ${
              latest.overall_score >= 7 ? "border-emerald-900/30 bg-emerald-950/20"
              : latest.overall_score >= 4 ? "border-amber-900/30 bg-amber-950/20"
              : "border-red-900/30 bg-red-950/20"
            }`}>
              <div className="text-4xl font-mono font-bold text-sumi-100">
                {latest.overall_score.toFixed(1)}
              </div>
              <div className="text-xs text-sumi-400 mt-1">OVERALL / 10</div>
            </div>
            <div className="text-sm text-sumi-400">
              <p>Last run: {latest.timestamp?.slice(0, 19)}</p>
              <p>Duration: {latest.duration_seconds.toFixed(2)}s</p>
              <p>{latest.categories.length} categories evaluated</p>
            </div>
          </div>

          {/* Category bars */}
          <div className="space-y-3">
            {latest.categories.map((cat, i) => {
              const pct = (cat.score / 10) * 100;
              const color = scoreColor(cat.score);
              const barColor = {
                emerald: "bg-emerald-500",
                amber: "bg-amber-500",
                red: "bg-red-500",
              }[color];
              const textColor = {
                emerald: "text-emerald-400",
                amber: "text-amber-400",
                red: "text-red-400",
              }[color];

              return (
                <div key={i} className="rounded-lg border border-sumi-700/50 bg-sumi-800/30 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-sumi-200">
                      {CATEGORY_LABELS[cat.name] ?? cat.name}
                    </span>
                    <span className={`text-sm font-mono font-bold ${textColor}`}>
                      {cat.score.toFixed(1)}/10
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-sumi-700/50 overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${barColor}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.6, delay: i * 0.05 }}
                    />
                  </div>
                  {cat.details && Object.keys(cat.details).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                      {Object.entries(cat.details).filter(([k]) => k !== "error").map(([k, v]) => (
                        <span key={k} className="text-xs text-sumi-500">
                          {k}: <span className="text-sumi-300">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Trend */}
          {trend.length > 1 && (
            <div className="rounded-lg border border-sumi-700/50 bg-sumi-800/30 p-4">
              <h3 className="text-sm font-medium text-sumi-300 mb-3">
                Trend (last {trend.length} audits)
              </h3>
              <div className="flex items-end gap-1 h-24">
                {trend.map((run, i) => {
                  const pct = ((run.overall_score ?? 0) / 10) * 100;
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <div
                        className={`w-full rounded-t transition-all ${
                          pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500"
                        }`}
                        style={{ height: `${Math.max(pct, 4)}%` }}
                        title={`${run.timestamp?.slice(0, 16)}: ${(run.overall_score ?? 0).toFixed(1)}/10`}
                      />
                      <span className="text-[9px] text-sumi-500">{(run.overall_score ?? 0).toFixed(1)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
}
