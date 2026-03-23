"use client";

/**
 * Eval Harness Dashboard — pass@1, pass@3, individual eval results, trend chart.
 */

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "@/lib/api";

interface EvalResult {
  name: string;
  passed: boolean;
  duration_seconds: number;
  error?: string;
  metrics?: Record<string, unknown>;
}

interface EvalReport {
  timestamp: string;
  total: number;
  passed: number;
  failed: number;
  pass_at_1: number;
  results: EvalResult[];
  duration_seconds: number;
}

export default function EvalPage() {
  const [latest, setLatest] = useState<EvalReport | null>(null);
  const [trend, setTrend] = useState<EvalReport[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    const [latestRes, trendRes] = await Promise.all([
      apiFetch<EvalReport | null>("/api/eval/latest"),
      apiFetch<EvalReport[]>("/api/eval/trend"),
    ]);
    return {
      latest: latestRes ?? null,
      trend: trendRes ?? [],
    };
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const next = await loadData();
      setLatest(next.latest);
      setTrend(next.trend);
    } catch {
      /* API unavailable */
    } finally {
      setLoading(false);
    }
  }, [loadData]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const next = await loadData();
        if (!active) return;
        setLatest(next.latest);
        setTrend(next.trend);
      } catch {
        /* API unavailable */
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [loadData]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            Eval Harness
          </h1>
          <p className="text-sm text-sumi-400">
            9 evals measuring whether dharma_swarm actually works.
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
        <div className="py-12 text-center text-sumi-500">Loading eval results...</div>
      ) : !latest ? (
        <div className="py-12 text-center text-sumi-500">
          No eval results yet. Run: <code className="text-aozora">dgc eval run</code>
        </div>
      ) : (
        <>
          {/* Score cards */}
          <div className="grid grid-cols-4 gap-4">
            <ScoreCard label="PASS@1" value={`${(latest.pass_at_1 * 100).toFixed(0)}%`}
              color={latest.pass_at_1 >= 0.8 ? "green" : latest.pass_at_1 >= 0.5 ? "amber" : "red"} />
            <ScoreCard label="PASSED" value={`${latest.passed}/${latest.total}`} color="green" />
            <ScoreCard label="FAILED" value={String(latest.failed)}
              color={latest.failed === 0 ? "green" : "red"} />
            <ScoreCard label="DURATION" value={`${latest.duration_seconds.toFixed(1)}s`} color="default" />
          </div>

          {/* Individual evals */}
          <div className="rounded-lg border border-sumi-700/50 bg-sumi-800/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-sumi-700/50">
              <h3 className="text-sm font-medium text-sumi-300">Individual Evals</h3>
            </div>
            <div className="divide-y divide-sumi-700/30">
              {latest.results.map((r, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5 hover:bg-sumi-800/50 transition-colors">
                  <div className="flex items-center gap-3">
                    <span className={`inline-block w-2 h-2 rounded-full ${r.passed ? "bg-emerald-400" : "bg-red-400"}`} />
                    <span className="text-sm text-sumi-200 font-mono">{r.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    {r.error && (
                      <span className="text-xs text-red-400 max-w-[300px] truncate">{r.error}</span>
                    )}
                    <span className="text-xs text-sumi-500 font-mono w-16 text-right">
                      {r.duration_seconds.toFixed(3)}s
                    </span>
                    <span className={`text-xs font-bold ${r.passed ? "text-emerald-400" : "text-red-400"}`}>
                      {r.passed ? "PASS" : "FAIL"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Trend */}
          {trend.length > 1 && (
            <div className="rounded-lg border border-sumi-700/50 bg-sumi-800/30 p-4">
              <h3 className="text-sm font-medium text-sumi-300 mb-3">Trend (last {trend.length} runs)</h3>
              <div className="flex items-end gap-1 h-24">
                {trend.map((run, i) => {
                  const pct = (run.pass_at_1 ?? 0) * 100;
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <div
                        className={`w-full rounded-t transition-all ${
                          pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500"
                        }`}
                        style={{ height: `${Math.max(pct, 4)}%` }}
                        title={`${run.timestamp?.slice(0, 16)}: ${pct.toFixed(0)}%`}
                      />
                      <span className="text-[9px] text-sumi-500">{pct.toFixed(0)}</span>
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

function ScoreCard({ label, value, color }: { label: string; value: string; color: string }) {
  const colorClass = {
    green: "border-emerald-900/30 bg-emerald-950/20 text-emerald-400",
    amber: "border-amber-900/30 bg-amber-950/20 text-amber-400",
    red: "border-red-900/30 bg-red-950/20 text-red-400",
    default: "border-sumi-700/50 bg-sumi-800/50 text-sumi-100",
  }[color] ?? "border-sumi-700/50 bg-sumi-800/50 text-sumi-100";

  return (
    <div className={`rounded-lg border p-4 ${colorClass}`}>
      <div className="text-xs font-medium text-sumi-400">{label}</div>
      <div className="text-2xl font-mono">{value}</div>
    </div>
  );
}
