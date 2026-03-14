"use client";

/**
 * DHARMA COMMAND -- CRT scan-line overlay.
 *
 * This is a secondary scan-line layer that can be toggled independently
 * of the body::after scan lines defined in globals.css.
 * Fixed position, pointer-events-none, 3% opacity.
 */

export function ScanLines() {
  return (
    <div
      className="pointer-events-none fixed inset-0 z-[9997]"
      aria-hidden="true"
      style={{
        opacity: 0.03,
        background:
          "repeating-linear-gradient(to bottom, transparent 0px, transparent 2px, rgba(0,0,0,0.4) 2px, rgba(0,0,0,0.4) 4px)",
      }}
    />
  );
}
