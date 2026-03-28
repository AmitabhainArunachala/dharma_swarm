"use client";

import { Pause, Play, Rewind, FastForward, SkipBack } from "lucide-react";

interface TimelineControlsProps {
  currentTime: number;
  startTime: number;
  endTime: number;
  playing: boolean;
  speed: number;
  onTimeChange: (time: number) => void;
  onPlayPause: () => void;
  onSpeedChange: (speed: number) => void;
  onReset: () => void;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

export function TimelineControls({
  currentTime,
  startTime,
  endTime,
  playing,
  speed,
  onTimeChange,
  onPlayPause,
  onSpeedChange,
  onReset,
}: TimelineControlsProps) {
  const progress = endTime > startTime
    ? ((currentTime - startTime) / (endTime - startTime)) * 100
    : 0;

  return (
    <div className="glass-panel px-4 py-3">
      {/* Time range label */}
      <div className="mb-2 flex items-center justify-between text-[10px] text-sumi-600">
        <span>{formatDate(startTime)} {formatTime(startTime)}</span>
        <span className="font-mono text-xs text-kinpaku">{formatTime(currentTime)}</span>
        <span>{formatDate(endTime)} {formatTime(endTime)}</span>
      </div>

      {/* Slider */}
      <input
        type="range"
        min={startTime}
        max={endTime}
        step={1}
        value={currentTime}
        onChange={(e) => onTimeChange(Number(e.target.value))}
        className="mb-3 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-sumi-700 accent-aozora"
        style={{
          background: `linear-gradient(to right, var(--color-aozora) 0%, var(--color-aozora) ${progress}%, var(--color-sumi-700) ${progress}%, var(--color-sumi-700) 100%)`,
        }}
      />

      {/* Controls */}
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={onReset}
          className="rounded-md p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
          title="Reset to start"
        >
          <SkipBack size={16} />
        </button>

        <button
          onClick={() => onSpeedChange(Math.max(speed / 2, 0.25))}
          className="rounded-md p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
          title="Slower"
        >
          <Rewind size={16} />
        </button>

        <button
          onClick={onPlayPause}
          className="rounded-lg border border-aozora/30 bg-aozora/10 p-2 text-aozora transition-all hover:border-aozora/50 hover:bg-aozora/20"
          title={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={20} /> : <Play size={20} />}
        </button>

        <button
          onClick={() => onSpeedChange(Math.min(speed * 2, 16))}
          className="rounded-md p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
          title="Faster"
        >
          <FastForward size={16} />
        </button>

        <span className="min-w-[40px] text-center font-mono text-xs text-sumi-600">
          {speed}x
        </span>
      </div>
    </div>
  );
}
