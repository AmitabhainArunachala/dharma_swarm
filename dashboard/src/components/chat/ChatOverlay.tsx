"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Grip, Maximize2, MessageCircle, Minimize2, X } from "lucide-react";
import { resolveChatProfile, shortProfileLabel } from "@/lib/chatProfiles";
import {
  type OperatorDock,
  type OperatorRect,
  useChatWorkspace,
} from "@/hooks/useChatWorkspace";
import { colors } from "@/lib/theme";
import { ChatInterface } from "./ChatInterface";

const SIDEBAR_OFFSET = 280;
const WINDOW_MARGIN = 20;
const TOP_OFFSET = 64;
const MIN_WIDTH = 380;
const MIN_HEIGHT = 360;

interface ViewportSize {
  width: number;
  height: number;
}

function getViewport(): ViewportSize {
  if (typeof window === "undefined") {
    return { width: 1440, height: 960 };
  }
  return { width: window.innerWidth, height: window.innerHeight };
}

function clampRect(rect: OperatorRect, viewport: ViewportSize): OperatorRect {
  const maxWidth = Math.max(MIN_WIDTH, viewport.width - SIDEBAR_OFFSET - WINDOW_MARGIN * 2);
  const maxHeight = Math.max(MIN_HEIGHT, viewport.height - TOP_OFFSET - WINDOW_MARGIN * 2);
  const width = Math.min(Math.max(rect.width, MIN_WIDTH), maxWidth);
  const height = Math.min(Math.max(rect.height, MIN_HEIGHT), maxHeight);
  const minX = SIDEBAR_OFFSET;
  const maxX = Math.max(minX, viewport.width - width - WINDOW_MARGIN);
  const minY = TOP_OFFSET;
  const maxY = Math.max(minY, viewport.height - height - WINDOW_MARGIN);

  return {
    x: Math.min(Math.max(rect.x, minX), maxX),
    y: Math.min(Math.max(rect.y, minY), maxY),
    width,
    height,
  };
}

function dockRect(dock: OperatorDock, viewport: ViewportSize, floatingRect: OperatorRect): OperatorRect {
  const usableWidth = Math.max(MIN_WIDTH, viewport.width - SIDEBAR_OFFSET - WINDOW_MARGIN * 2);
  const usableHeight = Math.max(MIN_HEIGHT, viewport.height - TOP_OFFSET - WINDOW_MARGIN * 2);

  if (dock === "floating") {
    return clampRect(floatingRect, viewport);
  }

  if (dock === "left") {
    const width = Math.min(Math.max(usableWidth * 0.34, 420), 620);
    return clampRect(
      {
        x: SIDEBAR_OFFSET,
        y: TOP_OFFSET,
        width,
        height: usableHeight,
      },
      viewport,
    );
  }

  if (dock === "right") {
    const width = Math.min(Math.max(usableWidth * 0.34, 420), 620);
    return clampRect(
      {
        x: viewport.width - width - WINDOW_MARGIN,
        y: TOP_OFFSET,
        width,
        height: usableHeight,
      },
      viewport,
    );
  }

  if (dock === "bottom") {
    const height = Math.min(Math.max(viewport.height * 0.42, 340), 520);
    return clampRect(
      {
        x: SIDEBAR_OFFSET,
        y: viewport.height - height - WINDOW_MARGIN,
        width: usableWidth,
        height,
      },
      viewport,
    );
  }

  const width = Math.min(Math.max(usableWidth * 0.62, 720), 1180);
  const height = Math.min(Math.max(usableHeight * 0.78, 520), 820);
  return clampRect(
    {
      x: SIDEBAR_OFFSET + (usableWidth - width) / 2,
      y: TOP_OFFSET + (usableHeight - height) / 2,
      width,
      height,
    },
    viewport,
  );
}

function snapDockForRect(rect: OperatorRect, viewport: ViewportSize): OperatorDock {
  const edgeThreshold = 42;
  if (rect.x <= SIDEBAR_OFFSET + edgeThreshold) return "left";
  if (rect.x + rect.width >= viewport.width - edgeThreshold) return "right";
  if (rect.y + rect.height >= viewport.height - edgeThreshold) return "bottom";
  return "floating";
}

function accentColorForProfile(accent: string): string {
  if (accent === "kinpaku") return colors.kinpaku;
  if (accent === "botan") return colors.botan;
  if (accent === "rokusho") return colors.rokusho;
  if (accent === "fuji") return colors.fuji;
  if (accent === "bengara") return colors.bengara;
  return colors.aozora;
}

export function ChatOverlay() {
  const {
    overlayOpen,
    openOverlay,
    closeOverlay,
    profileId,
    setProfile,
    operatorDock,
    operatorRect,
    setOperatorDock,
    setOperatorRect,
    resetOperatorRect,
  } = useChatWorkspace();
  const [viewport, setViewport] = useState<ViewportSize>(getViewport);
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [snapHint, setSnapHint] = useState<OperatorDock | null>(null);
  const currentRectRef = useRef(operatorRect);
  const dragRef = useRef<{
    mode: "move" | "resize";
    startX: number;
    startY: number;
    rect: OperatorRect;
  } | null>(null);

  const profile = resolveChatProfile(null, profileId);
  const accentColor = accentColorForProfile(profile.accent);
  const liveRect = useMemo(
    () => dockRect(operatorDock, viewport, operatorRect),
    [operatorDock, operatorRect, viewport],
  );

  useEffect(() => {
    currentRectRef.current = operatorRect;
  }, [operatorRect]);

  useEffect(() => {
    function onResize() {
      setViewport(getViewport());
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!dragRef.current) return;

    function onPointerMove(event: PointerEvent) {
      const active = dragRef.current;
      if (!active) return;

      const dx = event.clientX - active.startX;
      const dy = event.clientY - active.startY;

      if (active.mode === "move") {
        const nextRect = clampRect(
          {
            ...active.rect,
            x: active.rect.x + dx,
            y: active.rect.y + dy,
          },
          viewport,
        );
        currentRectRef.current = nextRect;
        setOperatorRect(nextRect);
        setSnapHint(snapDockForRect(nextRect, viewport));
        return;
      }

      const nextRect = clampRect(
        {
          ...active.rect,
          width: active.rect.width + dx,
          height: active.rect.height + dy,
        },
        viewport,
      );
      currentRectRef.current = nextRect;
      setOperatorRect(nextRect);
    }

    function onPointerUp() {
      const active = dragRef.current;
      dragRef.current = null;
      setDragging(false);
      setResizing(false);

      if (active?.mode === "move") {
        const snapped = snapDockForRect(currentRectRef.current, viewport);
        setOperatorDock(snapped);
      }
      setSnapHint(null);
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [operatorRect, setOperatorDock, setOperatorRect, viewport]);

  const beginMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest("button")) return;
    event.preventDefault();
    const baseRect = dockRect(operatorDock, viewport, operatorRect);
    setOperatorDock("floating");
    currentRectRef.current = baseRect;
    setOperatorRect(baseRect);
    dragRef.current = {
      mode: "move",
      startX: event.clientX,
      startY: event.clientY,
      rect: baseRect,
    };
    setDragging(true);
  };

  const beginResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const baseRect = dockRect(operatorDock, viewport, operatorRect);
    setOperatorDock("floating");
    currentRectRef.current = baseRect;
    setOperatorRect(baseRect);
    dragRef.current = {
      mode: "resize",
      startX: event.clientX,
      startY: event.clientY,
      rect: baseRect,
    };
    setResizing(true);
  };

  const dockLabel = operatorDock === "floating" ? "free" : operatorDock;
  const bubbleLabel = shortProfileLabel(profile);

  return (
    <>
      <AnimatePresence>
        {!overlayOpen && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", damping: 20, stiffness: 300 }}
            onClick={() => openOverlay()}
            className="fixed bottom-6 right-6 z-[60] flex h-16 w-16 flex-col items-center justify-center rounded-2xl border bg-sumi-900/95 backdrop-blur-md transition-all"
            style={{
              borderColor: `color-mix(in srgb, ${accentColor} 42%, transparent)`,
              boxShadow: `0 0 26px color-mix(in srgb, ${accentColor} 24%, transparent)`,
            }}
            aria-label={`Open ${profile.label} operator window`}
          >
            <MessageCircle size={20} style={{ color: accentColor }} />
            <span className="mt-1 font-mono text-[10px]" style={{ color: accentColor }}>
              {bubbleLabel}
            </span>
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {overlayOpen && (
          <motion.div
            key="operator-window"
            data-testid="operator-window"
            initial={{ opacity: 0, scale: 0.96, y: 14 }}
            animate={{
              opacity: 1,
              scale: 1,
              y: 0,
              left: liveRect.x,
              top: liveRect.y,
              width: liveRect.width,
              height: liveRect.height,
            }}
            exit={{ opacity: 0, scale: 0.97, y: 10 }}
            transition={{
              left: { type: "spring", damping: 26, stiffness: 260 },
              top: { type: "spring", damping: 26, stiffness: 260 },
              width: { type: "spring", damping: 28, stiffness: 250 },
              height: { type: "spring", damping: 28, stiffness: 250 },
              opacity: { duration: 0.18 },
            }}
            className="fixed z-[60] flex flex-col overflow-hidden rounded-[24px] border bg-sumi-900/95 shadow-2xl backdrop-blur-md"
            style={{
              borderColor: `color-mix(in srgb, ${accentColor} 32%, ${colors.sumi[700]})`,
              boxShadow: `0 18px 60px rgba(0,0,0,0.45), 0 0 30px color-mix(in srgb, ${accentColor} 18%, transparent)`,
            }}
          >
            <div
              data-testid="operator-window-header"
              onPointerDown={beginMove}
              className="relative flex cursor-grab items-center justify-between border-b px-4 py-3 active:cursor-grabbing"
              style={{ borderColor: colors.sumi[700] + "66" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="flex h-9 w-9 items-center justify-center rounded-xl"
                  style={{
                    background: `color-mix(in srgb, ${accentColor} 12%, ${colors.sumi[850]})`,
                    color: accentColor,
                  }}
                >
                  <MessageCircle size={16} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className="font-heading text-sm font-bold tracking-wide"
                      style={{ color: accentColor }}
                    >
                      {profile.label}
                    </span>
                    <span className="rounded-full bg-sumi-850 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                      {dockLabel}
                    </span>
                    {(dragging || resizing) && (
                      <span className="rounded-full bg-sumi-850 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
                        {dragging ? "moving" : "resizing"}
                      </span>
                    )}
                    {snapHint && dragging && snapHint !== "floating" && (
                      <span className="rounded-full bg-kinpaku/10 px-2 py-0.5 font-mono text-[10px] text-kinpaku">
                        snap {snapHint}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] text-sumi-600">
                    Move, resize, or dock this operator anywhere in the command field.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <div className="mr-1 flex items-center gap-1 rounded-xl border border-sumi-700/40 bg-sumi-850/70 p-1">
                  <DockButton
                    label="F"
                    title="Float"
                    testId="dock-floating"
                    active={operatorDock === "floating"}
                    onClick={() => setOperatorDock("floating")}
                  />
                  <DockButton
                    label="L"
                    title="Dock left"
                    testId="dock-left"
                    active={operatorDock === "left"}
                    onClick={() => setOperatorDock("left")}
                  />
                  <DockButton
                    label="R"
                    title="Dock right"
                    testId="dock-right"
                    active={operatorDock === "right"}
                    onClick={() => setOperatorDock("right")}
                  />
                  <DockButton
                    label="B"
                    title="Dock bottom"
                    testId="dock-bottom"
                    active={operatorDock === "bottom"}
                    onClick={() => setOperatorDock("bottom")}
                  />
                  <DockButton
                    label="C"
                    title="Center expand"
                    testId="dock-center"
                    active={operatorDock === "center"}
                    onClick={() => setOperatorDock("center")}
                  />
                </div>
                <button
                  onClick={resetOperatorRect}
                  className="rounded-lg p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
                  title="Reset size and position"
                  aria-label="Reset operator window"
                  data-testid="operator-reset"
                >
                  {operatorDock === "center" ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                </button>
                <button
                  onClick={closeOverlay}
                  className="rounded-lg p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
                  title="Close operator"
                  aria-label="Close operator"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-hidden">
              <ChatInterface
                compact={liveRect.width < 520}
                showHeader={false}
                profileId={profileId}
                onProfileChange={setProfile}
              />
            </div>

            <div
              className="flex items-center justify-between border-t px-3 py-2 text-[10px]"
              style={{ borderColor: colors.sumi[700] + "55" }}
            >
              <div className="flex items-center gap-2 text-sumi-600">
                <Grip size={11} />
                <span className="font-mono">
                  {Math.round(liveRect.width)} x {Math.round(liveRect.height)}
                </span>
              </div>
              <span className="font-mono text-sumi-600">
                drag to edge for magnetic snap
              </span>
            </div>

            {operatorDock === "floating" && (
              <button
                data-testid="operator-window-resize"
                onPointerDown={beginResize}
                className="absolute bottom-0 right-0 h-8 w-8 cursor-se-resize rounded-tl-2xl"
                style={{
                  background:
                    "linear-gradient(135deg, transparent 50%, color-mix(in srgb, " +
                    accentColor +
                    " 20%, transparent) 100%)",
                }}
                aria-label="Resize operator window"
                title="Resize"
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function DockButton({
  label,
  title,
  testId,
  active,
  onClick,
}: {
  label: string;
  title: string;
  testId: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-md px-2 py-1 font-mono text-[10px] transition-colors"
      style={{
        color: active ? colors.aozora : colors.sumi[600],
        background: active
          ? "color-mix(in srgb, #4FD1D9 14%, transparent)"
          : "transparent",
      }}
      title={title}
      aria-label={title}
      data-testid={testId}
    >
      {label}
    </button>
  );
}
