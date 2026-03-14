"use client";

import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useFitnessTrend } from "@/hooks/useEvolution";
import { colors } from "@/lib/theme";

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: { value?: number }[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;

  return (
    <div
      className="glass-panel px-3 py-2"
      style={{
        border: `1px solid color-mix(in srgb, ${colors.aozora} 30%, transparent)`,
      }}
    >
      <p
        className="mb-1 text-[10px] font-medium uppercase tracking-wider"
        style={{ color: colors.kitsurubami }}
      >
        {formatTimestamp(label ?? "")}
      </p>
      <p
        className="text-sm font-bold"
        style={{ color: colors.torinoko, fontFamily: "var(--font-mono)" }}
      >
        {payload[0].value?.toFixed(3)}
      </p>
    </div>
  );
}

interface FitnessTrendProps {
  className?: string;
}

export function FitnessTrend({ className }: FitnessTrendProps) {
  const { trend, isLoading } = useFitnessTrend();

  if (isLoading) {
    return (
      <div
        className={`glass-panel flex items-center justify-center ${className ?? ""}`}
        style={{ minHeight: 280 }}
      >
        <p className="animate-pulse text-sm" style={{ color: colors.sumi[600] }}>
          Loading fitness data...
        </p>
      </div>
    );
  }

  if (!trend.length) {
    return (
      <div
        className={`glass-panel flex items-center justify-center ${className ?? ""}`}
        style={{ minHeight: 280 }}
      >
        <p className="text-sm" style={{ color: colors.sumi[600] }}>
          No fitness data yet
        </p>
      </div>
    );
  }

  const chartData = trend.map((p) => ({
    timestamp: formatTimestamp(p.timestamp),
    fitness: p.fitness,
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className={`glass-panel p-5 ${className ?? ""}`}
    >
      <h3
        className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em]"
        style={{ color: colors.kitsurubami }}
      >
        Fitness Trend
      </h3>

      <ResponsiveContainer width="100%" height={240}>
        <AreaChart
          data={chartData}
          margin={{ top: 4, right: 8, left: -12, bottom: 0 }}
        >
          <defs>
            <linearGradient id="fitnessFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={colors.aozora} stopOpacity={0.3} />
              <stop offset="95%" stopColor={colors.aozora} stopOpacity={0.0} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke={colors.sumi[700]}
            strokeOpacity={0.3}
            vertical={false}
          />

          <XAxis
            dataKey="timestamp"
            tick={{ fill: colors.sumi[600], fontSize: 10 }}
            axisLine={{ stroke: colors.sumi[700], strokeOpacity: 0.4 }}
            tickLine={false}
          />

          <YAxis
            domain={[0, 1]}
            tick={{ fill: colors.sumi[600], fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => v.toFixed(1)}
          />

          <Tooltip content={<CustomTooltip />} />

          <Area
            type="monotone"
            dataKey="fitness"
            stroke={colors.aozora}
            strokeWidth={2}
            fill="url(#fitnessFill)"
            animationDuration={1200}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
