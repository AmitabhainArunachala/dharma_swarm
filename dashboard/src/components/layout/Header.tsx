"use client";

/**
 * DHARMA COMMAND -- Breadcrumb header with Cmd+K trigger and split chat toggle.
 */

import { usePathname } from "next/navigation";
import { Command, ChevronRight, MessageCircle } from "lucide-react";
import { useCallback, useEffect } from "react";

interface HeaderProps {
  onToggleChat?: () => void;
  chatOpen?: boolean;
}

export function Header({ onToggleChat, chatOpen }: HeaderProps) {
  const pathname = usePathname();

  // Build breadcrumb segments from the path.
  const segments = pathname
    .split("/")
    .filter(Boolean)
    .map((seg) => seg.charAt(0).toUpperCase() + seg.slice(1));

  const handleCmdK = useCallback(() => {
    // Dispatch a custom event that a command-palette component can listen to.
    window.dispatchEvent(new CustomEvent("dharma:cmd-k"));
  }, []);

  // Listen for Cmd+K / Ctrl+K globally.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        handleCmdK();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleCmdK]);

  return (
    <header className="flex h-12 items-center justify-between border-b border-sumi-700/30 bg-sumi-900/40 px-6 backdrop-blur-sm">
      {/* Breadcrumbs */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm">
        {segments.map((seg, i) => (
          <span key={`${seg}-${i}`} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={12} className="text-sumi-700" />}
            <span
              className={
                i === segments.length - 1
                  ? "font-medium text-torinoko"
                  : "text-sumi-600"
              }
            >
              {seg}
            </span>
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-2">
        {/* Split chat toggle */}
        {onToggleChat && (
          <button
            onClick={onToggleChat}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all ${
              chatOpen
                ? "border-aozora/40 bg-aozora/15 text-aozora"
                : "border-sumi-700/40 bg-sumi-850/60 text-sumi-600 hover:border-aozora/30 hover:text-aozora/80"
            }`}
            title="Toggle split chat panel"
          >
            <MessageCircle size={12} />
            <span className="font-mono">Claude</span>
          </button>
        )}

        {/* Cmd+K trigger */}
        <button
          onClick={handleCmdK}
          className="flex items-center gap-2 rounded-lg border border-sumi-700/40 bg-sumi-850/60 px-3 py-1.5 text-xs text-sumi-600 transition-colors hover:border-sumi-600/50 hover:text-torinoko/80"
          aria-label="Open command palette"
        >
          <Command size={12} />
          <span className="font-mono">K</span>
        </button>
      </div>
    </header>
  );
}
