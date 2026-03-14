"use client";

/**
 * DHARMA COMMAND -- Stigmergy visualization (L4).
 * Heatmap (file paths x time), hot paths list, high salience marks.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Network, Flame, Zap } from "lucide-react";
import { scaleLinear } from "@visx/scale";
import { HeatmapRect } from "@visx/heatmap";
import {
  useStigmergyHeatmap,
  useHotPaths,
  useHighSalience,
} from "@/hooks/useStigmergy";
import { colors } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";
import type { HeatmapCell } from "@/lib/types";

export default function StigmergyPage() {
  const { heatmap, isLoading: heatmapLoading } = useStigmergyHeatmap();
  const { hotPaths, isLoading: hotLoading } = useHotPaths();
  const { marks, isLoading: marksLoading } = useHighSalience();

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <Network size={24} className="text-bengara" />
          <h1 className="glow-bengara font-heading text-2xl font-bold tracking-tight text-bengara">
            Stigmergy
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          Pheromone marks, hot paths, and salience heatmap.
        </p>
      </motion.div>

      {/* Heatmap */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass-panel p-5"
      >
        <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
          Salience Heatmap
        </h3>
        {heatmapLoading ? (
          <div className="flex items-center justify-center py-12">
            <p className="animate-pulse text-sm text-sumi-600">Loading heatmap...</p>
          </div>
        ) : heatmap.length > 0 ? (
          <StigmergyHeatmap data={heatmap} />
        ) : (
          <div className="flex items-center justify-center py-12">
            <p className="text-sm text-sumi-600">No heatmap data available</p>
          </div>
        )}
      </motion.div>

      {/* Bottom row: Hot paths + High salience */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Hot paths */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Flame size={14} className="text-kinpaku" />
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Hot Paths
            </h3>
          </div>

          {hotLoading ? (
            <p className="animate-pulse text-sm text-sumi-600">Loading...</p>
          ) : hotPaths.length > 0 ? (
            <div className="space-y-2">
              {hotPaths.map((hp, i) => (
                <motion.div
                  key={hp.path}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 + i * 0.04 }}
                  className="flex items-center justify-between rounded-md bg-sumi-850/50 px-3 py-2"
                >
                  <span className="max-w-[200px] truncate font-mono text-xs text-torinoko">
                    {hp.path}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-kinpaku">
                      {hp.count}
                    </span>
                    <div
                      className="h-1.5 rounded-full"
                      style={{
                        width: Math.max(16, Math.min(80, hp.count * 4)),
                        background: `linear-gradient(90deg, ${colors.kinpaku}, ${colors.bengara})`,
                        opacity: Math.min(1, 0.4 + hp.count * 0.06),
                      }}
                    />
                  </div>
                </motion.div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-sumi-600">No hot paths</p>
          )}
        </motion.div>

        {/* High salience marks */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Zap size={14} className="text-aozora" />
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              High Salience Marks
            </h3>
          </div>

          {marksLoading ? (
            <p className="animate-pulse text-sm text-sumi-600">Loading...</p>
          ) : marks.length > 0 ? (
            <div className="space-y-2">
              {marks.slice(0, 12).map((mark, i) => (
                <motion.div
                  key={mark.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.25 + i * 0.04 }}
                  className="rounded-md bg-sumi-850/50 px-3 py-2.5"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-aozora">
                      {mark.action}
                    </span>
                    <span className="font-mono text-[10px] text-sumi-600">
                      {timeAgo(mark.timestamp)}
                    </span>
                  </div>
                  <p className="truncate text-xs text-torinoko/80">{mark.observation}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="font-mono text-[10px] text-sumi-600">
                      {mark.agent}
                    </span>
                    <span
                      className="font-mono text-[10px] font-bold"
                      style={{
                        color:
                          mark.salience > 0.7
                            ? colors.bengara
                            : mark.salience > 0.4
                              ? colors.kinpaku
                              : colors.sumi[600],
                      }}
                    >
                      {mark.salience.toFixed(2)}
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-sumi-600">No high-salience marks</p>
          )}
        </motion.div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Heatmap component (using @visx/heatmap)
// ---------------------------------------------------------------------------

function StigmergyHeatmap({ data }: { data: HeatmapCell[] }) {
  const { bins, rows, cols, maxVal, width, height } = useMemo(() => {
    const rowSet = [...new Set(data.map((d) => d.file_path))];
    const colSet = [...new Set(data.map((d) => String(d.hour)))];
    const maxV = Math.max(...data.map((d) => d.avg_salience), 1);

    // Build bin structure for HeatmapRect
    const valMap = new Map<string, number>();
    for (const d of data) {
      valMap.set(`${d.file_path}::${d.hour}`, d.avg_salience);
    }

    const binData = colSet.map((col, ci) => ({
      bin: ci,
      bins: rowSet.map((row, ri) => ({
        bin: ri,
        count: valMap.get(`${row}::${col}`) ?? 0,
      })),
    }));

    const cellW = 28;
    const cellH = 22;

    return {
      bins: binData,
      rows: rowSet,
      cols: colSet,
      maxVal: maxV,
      width: Math.max(colSet.length * cellW + 140, 400),
      height: Math.max(rowSet.length * cellH + 40, 200),
    };
  }, [data]);

  const xScale = useMemo(
    () => scaleLinear({ domain: [0, cols.length], range: [140, width] }),
    [cols.length, width],
  );

  const yScale = useMemo(
    () => scaleLinear({ domain: [0, rows.length], range: [0, height - 40] }),
    [rows.length, height],
  );

  const colorScale = useMemo(
    () =>
      scaleLinear<string>({
        domain: [0, maxVal * 0.5, maxVal],
        range: [colors.sumi[900], colors.kinpaku, colors.bengara],
      }),
    [maxVal],
  );

  const opacityScale = useMemo(
    () => scaleLinear({ domain: [0, maxVal], range: [0.15, 1] }),
    [maxVal],
  );

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height}>
        {/* Row labels */}
        {rows.map((row, i) => (
          <text
            key={row}
            x={135}
            y={yScale(i) + 16}
            textAnchor="end"
            fill={colors.sumi[600]}
            fontSize={9}
            fontFamily="var(--font-mono)"
          >
            {row.length > 20 ? `...${row.slice(-18)}` : row}
          </text>
        ))}

        <HeatmapRect
          data={bins}
          xScale={(d) => xScale(d) ?? 0}
          yScale={(d) => yScale(d) ?? 0}
          colorScale={colorScale}
          opacityScale={opacityScale}
          binWidth={Math.max(20, (width - 140) / Math.max(cols.length, 1) - 2)}
          binHeight={Math.max(16, (height - 40) / Math.max(rows.length, 1) - 2)}
          gap={2}
        >
          {(heatmap) =>
            heatmap.map((hBins) =>
              hBins.map((bin) => (
                <rect
                  key={`heatmap-rect-${bin.row}-${bin.column}`}
                  x={bin.x}
                  y={bin.y}
                  width={bin.width}
                  height={bin.height}
                  fill={bin.color}
                  fillOpacity={bin.opacity}
                  rx={3}
                />
              )),
            )
          }
        </HeatmapRect>

        {/* Column labels */}
        {cols.map((col, i) => (
          <text
            key={col}
            x={xScale(i) + 10}
            y={height - 5}
            textAnchor="middle"
            fill={colors.sumi[600]}
            fontSize={8}
            fontFamily="var(--font-mono)"
          >
            {col.length > 8 ? col.slice(0, 8) : col}
          </text>
        ))}
      </svg>
    </div>
  );
}
