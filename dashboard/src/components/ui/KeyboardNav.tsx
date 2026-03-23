"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { buildDashboardKeyboardRouteMap } from "@/lib/controlPlaneShell";

/**
 * Global keyboard shortcuts for dashboard navigation.
 * Only active when no input/textarea is focused.
 *
 *   g a → Agents
 *   g c → Command Post
 *   g t → Tasks
 *   g e → Evolution
 *   g g → Gates
 *   g s → Stigmergy
 *   g o → Overview
 *   g q → Qwen Surgeon
 *   g r → Runtime
 *   g m → Modules
 *   g u → Audit
 *   g v → Observatory
 */
export function KeyboardNav() {
  const router = useRouter();

  useEffect(() => {
    let gPressed = false;
    let gTimer: ReturnType<typeof setTimeout> | null = null;

    function handleKeyDown(e: KeyboardEvent) {
      // Ignore when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toLowerCase();

      if (gPressed) {
        gPressed = false;
        if (gTimer) clearTimeout(gTimer);

        const routes = buildDashboardKeyboardRouteMap();

        if (routes[key]) {
          e.preventDefault();
          router.push(routes[key]);
        }
        return;
      }

      if (key === "g") {
        gPressed = true;
        gTimer = setTimeout(() => {
          gPressed = false;
        }, 500);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [router]);

  return null;
}
