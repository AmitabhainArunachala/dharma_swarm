"use client";

/**
 * DHARMA COMMAND -- Navigation sidebar (260px fixed).
 *
 * Sections are level-gated: items above the user's current level
 * render dimmed and non-interactive.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLevel } from "@/hooks/useLevel";
import {
  buildDashboardNavSections,
  isDashboardPathActive,
  type DashboardNavItem,
  type DashboardNavSection,
} from "@/lib/dashboardNav";
import {
  Activity,
  Bot,
  Brain,
  BrainCircuit,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Dna,
  GitBranch,
  Globe,
  Grid3X3,
  HeartPulse,
  LayoutDashboard,
  ListTodo,
  MessageSquare,
  Microscope,
  Network,
  Orbit,
  Settings2,
  Shield,
  Sparkles,
  Workflow,
} from "lucide-react";
import { type ComponentType, type ReactNode } from "react";

// ---------------------------------------------------------------------------
// Icon map
// ---------------------------------------------------------------------------

const iconMap: Record<string, ComponentType<{ className?: string; size?: number }>> = {
  LayoutDashboard,
  Bot,
  Brain,
  BrainCircuit,
  ListTodo,
  Activity,
  Dna,
  Shield,
  Microscope,
  GitBranch,
  Network,
  Globe,
  Workflow,
  Grid3X3,
  Orbit,
  Sparkles,
  MessageSquare,
  ClipboardCheck,
  HeartPulse,
  Settings2,
};

// ---------------------------------------------------------------------------
// Nav structure
// ---------------------------------------------------------------------------
const sections = buildDashboardNavSections();

// ---------------------------------------------------------------------------
// Sidebar component
// ---------------------------------------------------------------------------

export function Sidebar() {
  const pathname = usePathname();
  const { level, levelUp, levelDown } = useLevel();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[260px] flex-col border-r border-sumi-700/40 bg-sumi-900/80 backdrop-blur-md">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5">
        <Sparkles className="text-aozora" size={20} />
        <span className="glow-aozora font-heading text-sm font-bold tracking-[0.2em] text-aozora">
          DHARMA COMMAND
        </span>
      </div>

      {/* Divider */}
      <div className="mx-4 h-px bg-gradient-to-r from-transparent via-sumi-700/60 to-transparent" />

      {/* Nav sections */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {sections.map((section) => (
          <SectionGroup
            key={section.label}
            section={section}
            userLevel={level}
            pathname={pathname}
          />
        ))}
      </nav>

      {/* Divider */}
      <div className="mx-4 h-px bg-gradient-to-r from-transparent via-sumi-700/60 to-transparent" />

      {/* Level control */}
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex flex-col">
          <span className="font-mono text-[10px] uppercase tracking-widest text-sumi-600">
            Disclosure
          </span>
          <span className="font-mono text-xs text-kitsurubami">
            Level {level}/5
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={levelDown}
            disabled={level <= 1}
            className="rounded p-1 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko disabled:opacity-30"
            aria-label="Decrease disclosure level"
          >
            <ChevronDown size={14} />
          </button>
          <button
            onClick={levelUp}
            disabled={level >= 5}
            className="rounded p-1 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko disabled:opacity-30"
            aria-label="Increase disclosure level"
          >
            <ChevronUp size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Section group
// ---------------------------------------------------------------------------

function SectionGroup({
  section,
  userLevel,
  pathname,
}: {
  section: DashboardNavSection;
  userLevel: number;
  pathname: string;
}) {
  const sectionLocked = section.level > userLevel;

  return (
    <div className="mb-4">
      <div
        className={`mb-1 px-3 font-mono text-[10px] font-semibold uppercase tracking-[0.15em] ${
          sectionLocked ? "text-sumi-700" : "text-sumi-600"
        }`}
      >
        {section.label}
      </div>
      {section.items.map((item) => (
        <NavItemLink
          key={item.href}
          item={item}
          active={isDashboardPathActive(item.href, pathname)}
          locked={item.level > userLevel}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nav item link
// ---------------------------------------------------------------------------

function NavItemLink({
  item,
  active,
  locked,
}: {
  item: DashboardNavItem;
  active: boolean;
  locked: boolean;
}) {
  const Icon = iconMap[item.icon] ?? LayoutDashboard;

  const inner: ReactNode = (
    <div
      className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all ${
        locked
          ? "pointer-events-none cursor-default text-sumi-700 opacity-40"
          : active
            ? "bg-sumi-800/80 text-aozora"
            : "text-torinoko/70 hover:bg-sumi-800/50 hover:text-torinoko"
      }`}
    >
      <Icon
        size={16}
        className={
          locked
            ? "text-sumi-700"
            : active
              ? "text-aozora"
              : "text-sumi-600 group-hover:text-torinoko/80"
        }
      />
      <span>{item.label}</span>
      {active && (
        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-aozora shadow-[0_0_6px_var(--color-aozora)]" />
      )}
    </div>
  );

  if (locked) {
    return <div aria-disabled="true">{inner}</div>;
  }

  return (
    <Link href={item.href} prefetch={false}>
      {inner}
    </Link>
  );
}
