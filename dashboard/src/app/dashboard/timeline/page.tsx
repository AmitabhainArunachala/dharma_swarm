"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Clock, History, Activity, Zap } from "lucide-react";
import { useTimeline } from "@/hooks/useTimeline";
import { useVizSnapshot } from "@/hooks/useVizSnapshot";
import { TimelineControls } from "@/components/timeline/TimelineControls";
import { colors } from "@/lib/theme";
import type { VizEvent } from "@/hooks/useVizEvents";

// Time range presets
const RANGES = [
  { label: "1h", seconds: 3600 },
  { label: "6h", seconds: 6 * 3600 },
  { label: "24h", seconds: 24 * 3600 },
  { label: "7d", seconds: 7 * 24 * 3600 },
] as const;

function eventIcon(type: string): string {
  switch (type) {
    case "mark_added": return "🔵";
    case "trajectory_completed": return "⚡";
    case "revenue": return "💚";
    case "expense": return "🔴";
    case "agent_status": return "🤖";
    default: return "·";
  }
}

function eventColor(type: string): string {
  switch (type) {
    case "mark_added": return colors.fuji;
    case "trajectory_completed": return colors.kinpaku;
    case "revenue": return colors.rokusho;
    case "expense": return colors.bengara;
    default: return colors.sumi[600];
  }
}

export default function TimelinePage() {
  const now = useMemo(() => Math.floor(Date.now() / 1000), []);
  const [rangeIdx, setRangeIdx] = useState(0);
  const [currentTime, setCurrentTime] = useState(now);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const playRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const rangeSeconds = RANGES[rangeIdx].seconds;
  const startTime = now - rangeSeconds;
  const endTime = now;

  const { data: timeline } = useTimeline(startTime, endTime, true);
  const { data: liveSnapshot } = useVizSnapshot(30_000);

  // Events visible up to currentTime
  const visibleEvents = useMemo(() => {
    if (!timeline?.events) return [];
    return timeline.events.filter((e) => e.timestamp <= currentTime);
  }, [timeline, currentTime]);

  // Event counts by type for the sparkline
  const eventCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of visibleEvents) {
      counts[e.event_type] = (counts[e.event_type] ?? 0) + 1;
    }
    return counts;
  }, [visibleEvents]);

  // Play/pause timer
  useEffect(() => {
    if (playing) {
      playRef.current = setInterval(() => {
        setCurrentTime((t) => {
          const next = t + speed * 60; // Advance by speed * 60 seconds per tick
          if (next >= endTime) {
            setPlaying(false);
            return endTime;
          }
          return next;
        });
      }, 1000);
    }
    return () => {
      if (playRef.current) clearInterval(playRef.current);
    };
  }, [playing, speed, endTime]);

  const handleReset = useCallback(() => {
    setPlaying(false);
    setCurrentTime(startTime);
  }, [startTime]);

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <History size={24} className="text-kinpaku" />
          <h1 className="glow-kinpaku font-heading text-2xl font-bold tracking-tight text-kinpaku">
            Temporal Playback
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          Replay system state changes. If you can&apos;t replay it, you don&apos;t understand it.
        </p>
      </motion.div>

      {/* Time range selector */}
      <div className="flex items-center gap-2">
        {RANGES.map((range, idx) => (
          <button
            key={range.label}
            onClick={() => { setRangeIdx(idx); setCurrentTime(now - range.seconds); }}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              idx === rangeIdx
                ? "border border-kinpaku/40 bg-kinpaku/10 text-kinpaku"
                : "border border-sumi-700/30 bg-sumi-850/50 text-sumi-600 hover:text-torinoko"
            }`}
          >
            {range.label}
          </button>
        ))}
        <div className="ml-auto text-[10px] text-sumi-600">
          {timeline?.events.length ?? 0} events in range
        </div>
      </div>

      {/* Controls */}
      <TimelineControls
        currentTime={currentTime}
        startTime={startTime}
        endTime={endTime}
        playing={playing}
        speed={speed}
        onTimeChange={setCurrentTime}
        onPlayPause={() => setPlaying((p) => !p)}
        onSpeedChange={setSpeed}
        onReset={handleReset}
      />

      {/* Event type counters */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          { type: "mark_added", label: "Marks", icon: Activity },
          { type: "trajectory_completed", label: "Trajectories", icon: Zap },
          { type: "revenue", label: "Revenue", icon: Activity },
          { type: "expense", label: "Expenses", icon: Activity },
          { type: "agent_status", label: "Agent Events", icon: Clock },
        ].map(({ type, label, icon: Icon }) => (
          <div key={type} className="glass-panel-subtle flex items-center gap-2 px-3 py-2">
            <Icon size={14} style={{ color: eventColor(type) }} />
            <div>
              <div className="text-[10px] uppercase tracking-wider text-sumi-600">{label}</div>
              <div className="font-mono text-sm font-bold" style={{ color: eventColor(type) }}>
                {eventCounts[type] ?? 0}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Event stream */}
      <div className="glass-panel p-4">
        <div className="mb-3 flex items-center gap-2">
          <Clock size={14} className="text-kinpaku" />
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
            Event Stream (up to playhead)
          </h2>
          <span className="ml-auto font-mono text-[10px] text-sumi-600">
            {visibleEvents.length} events
          </span>
        </div>
        <div className="max-h-[400px] space-y-1 overflow-y-auto">
          {visibleEvents.length > 0 ? (
            [...visibleEvents].reverse().slice(0, 50).map((evt, i) => (
              <motion.div
                key={`timeline-evt-${i}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.02 }}
                className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-sumi-850/50"
              >
                <span className="mt-0.5 text-sm">{eventIcon(evt.event_type)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-sumi-600">
                      {new Date(evt.timestamp * 1000).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                    <span
                      className="text-[11px] font-medium"
                      style={{ color: eventColor(evt.event_type) }}
                    >
                      {evt.event_type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-torinoko/60">
                    {evt.node_id && <span className="font-mono">{evt.node_id} </span>}
                    {typeof evt.data?.observation === "string" && evt.data.observation}
                    {typeof evt.data?.task === "string" && evt.data.task}
                    {typeof evt.data?.description === "string" && evt.data.description}
                    {typeof evt.data?.amount === "number" && `$${(evt.data.amount as number).toFixed(4)}`}
                  </div>
                </div>
              </motion.div>
            ))
          ) : (
            <p className="text-sm text-sumi-600">No events in this time range yet.</p>
          )}
        </div>
      </div>

      {/* Snapshot summary at current time */}
      {liveSnapshot && (
        <div className="glass-panel-subtle p-3">
          <div className="text-[10px] uppercase tracking-wider text-sumi-600">
            System State at Playhead
          </div>
          <div className="mt-2 grid grid-cols-3 gap-4 md:grid-cols-6">
            {Object.entries(liveSnapshot.summary)
              .filter(([, v]) => typeof v === "number")
              .slice(0, 6)
              .map(([key, value]) => (
                <div key={key}>
                  <div className="text-[10px] text-sumi-600">{key.replace(/_/g, " ")}</div>
                  <div className="font-mono text-sm text-torinoko">
                    {typeof value === "number" && value < 100
                      ? (value as number).toFixed(2)
                      : String(value)}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
