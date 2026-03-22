"use client";

import { useState, useEffect, useCallback } from "react";
import { AlertTriangle, RefreshCw, X, WifiOff } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { controlPlaneOfflineMessage } from "@/lib/controlPlaneShell";
import { cn } from "@/lib/utils";
import { apiPath } from "@/lib/api";

interface ErrorBannerProps {
  /** Override the error message */
  message?: string;
  /** Error variant */
  variant?: "error" | "warning" | "offline";
  /** Show retry button */
  onRetry?: () => void;
  /** Dismissible */
  dismissible?: boolean;
}

/**
 * Inline error banner — shown when a specific request fails.
 */
export function ErrorBanner({
  message,
  variant = "error",
  onRetry,
  dismissible = false,
}: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const isOffline = variant === "offline";
  const isWarning = variant === "warning";
  const borderColor = isOffline || !isWarning ? "border-bengara/30" : "border-kinpaku/30";
  const bgColor = isOffline || !isWarning ? "bg-bengara/5" : "bg-kinpaku/5";
  const textColor = isOffline || !isWarning ? "text-bengara" : "text-kinpaku";
  const Icon = isOffline ? WifiOff : AlertTriangle;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, height: 0 }}
      animate={{ opacity: 1, y: 0, height: "auto" }}
      exit={{ opacity: 0, y: -8, height: 0 }}
      className={cn("rounded-lg border px-4 py-3", borderColor, bgColor)}
    >
      <div className="flex items-center gap-3">
        <Icon size={14} className={cn("shrink-0", textColor)} />
        <p className={cn("flex-1 text-xs", textColor)}>
          {message ||
            (isOffline
              ? "Backend unreachable. Check that the API server is running."
              : "Something went wrong.")}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className={cn(
              "flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors",
              textColor,
              "hover:bg-white/5",
            )}
          >
            <RefreshCw size={10} />
            Retry
          </button>
        )}
        {dismissible && (
          <button
            onClick={() => setDismissed(true)}
            className="rounded p-0.5 text-sumi-600 transition-colors hover:text-torinoko"
          >
            <X size={12} />
          </button>
        )}
      </div>
    </motion.div>
  );
}

/**
 * Global backend connectivity banner.
 * Polls the health endpoint and shows a persistent banner when unreachable.
 */
export function BackendStatus() {
  const [offline, setOffline] = useState(false);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(apiPath("/api/health"), {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      setOffline(!res.ok);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    const initialCheck = window.setTimeout(() => {
      void checkHealth();
    }, 0);
    const interval = setInterval(checkHealth, 15_000);
    return () => {
      clearTimeout(initialCheck);
      clearInterval(interval);
    };
  }, [checkHealth]);

  return (
    <AnimatePresence>
      {offline && (
        <ErrorBanner
          variant="offline"
          message={controlPlaneOfflineMessage()}
          onRetry={checkHealth}
        />
      )}
    </AnimatePresence>
  );
}
