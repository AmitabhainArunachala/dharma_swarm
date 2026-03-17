"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Globe,
  Leaf,
  Network,
  Sparkles,
} from "lucide-react";
import { useModules } from "@/hooks/useModules";
import type { ModuleHistoryOut, ModuleProcessOut, ModuleProjectOut, ModuleSalientOut, ModuleTruthOut, ModuleWireOut } from "@/lib/types";

const iconMap = {
  control_plane: BrainCircuit,
  living_layers: Sparkles,
  mycelium: Leaf,
  trishula: Network,
  pulse_cron: Activity,
  allout: Clock3,
  jagat_kalyan: Globe,
} as const;

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
};

export default function ModulesTruthPage() {
  return (
    <Suspense fallback={<ModulesLoadingState />}>
      <ModulesTruthClient />
    </Suspense>
  );
}

function ModulesTruthClient() {
  const { modules, isLoading } = useModules();
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("module");
  const selected =
    modules.find((module) => module.id === selectedId) ?? modules[0] ?? null;

  useEffect(() => {
    if (!selectedId && modules.length > 0) {
      router.replace(`/dashboard/modules?module=${modules[0].id}`, { scroll: false });
    }
  }, [modules, router, selectedId]);

  const activeCount = modules.filter((module) => module.status === "active").length;
  const brokenCount = modules.filter((module) => module.status === "broken").length;
  const mixedCount = modules.filter((module) => module.status === "mixed").length;

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <motion.div variants={item} className="glass-panel overflow-hidden p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-2">
            <div className="flex items-center gap-3">
              <Activity size={18} className="text-aozora" />
              <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
                Major Modules Truth Map
              </h1>
            </div>
            <p className="text-sm leading-6 text-sumi-600">
              This view is built from live runtime files, logs, PID surfaces, and
              project artifacts. Click a module card to inspect recent history,
              actual project roots, wiring, and the top ten salient files or events
              that matter right now.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center lg:min-w-[340px]">
            <SummaryChip label="Modules" value={String(modules.length)} />
            <SummaryChip label="Active" value={String(activeCount)} accent="ok" />
            <SummaryChip label="Broken" value={String(brokenCount)} accent="error" />
            <SummaryChip label="Mixed" value={String(mixedCount)} accent="warn" />
            <SummaryChip
              label="Selected"
              value={selected?.name ?? (isLoading ? "Loading" : "None")}
              wide
            />
          </div>
        </div>
      </motion.div>

      <motion.div variants={item} className="grid grid-cols-1 gap-4 xl:grid-cols-[440px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="glass-panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-heading text-lg font-semibold text-torinoko">
                Module Map
              </h2>
              <span className="rounded-full bg-sumi-850 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-sumi-600">
                click to drill in
              </span>
            </div>

            <div className="space-y-3">
              {isLoading && (
                <div className="rounded-2xl border border-dashed border-sumi-700/30 bg-sumi-850/40 p-6 text-sm text-sumi-600">
                  Reading runtime truth surfaces...
                </div>
              )}

              {!isLoading &&
                modules.map((module) => (
                  <ModuleCard
                    key={module.id}
                    module={module}
                    selected={selected?.id === module.id}
                    onSelect={() => {
                      router.replace(`/dashboard/modules?module=${module.id}`, {
                        scroll: false,
                      });
                    }}
                  />
                ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {selected ? (
            <ModuleDetail module={selected} />
          ) : (
            <div className="glass-panel flex min-h-[520px] items-center justify-center p-8 text-center text-sm text-sumi-600">
              No module selected.
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function ModulesLoadingState() {
  return (
    <div className="glass-panel p-6 text-sm text-sumi-600">
      Reading runtime truth surfaces...
    </div>
  );
}

function ModuleCard({
  module,
  selected,
  onSelect,
}: {
  module: ModuleTruthOut;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = iconMap[module.id as keyof typeof iconMap] ?? Activity;
  const status = statusStyles(module.status);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-[22px] border p-4 text-left transition-all ${
        selected
          ? `${status.cardBorder} bg-sumi-800/90 shadow-[0_0_22px_rgba(79,209,217,0.08)]`
          : "border-sumi-700/30 bg-sumi-850/65 hover:border-sumi-600/45 hover:bg-sumi-800/70"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className={`rounded-2xl border ${status.softBorder} ${status.softBg} p-3`}>
          <Icon size={18} className={status.iconClass} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-lg font-semibold text-torinoko">
              {module.name}
            </h3>
            <StatusPill status={module.status} />
            {module.live && (
              <span className="rounded-full bg-rokusho/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-rokusho">
                live
              </span>
            )}
          </div>
          <p className="mt-2 text-sm leading-6 text-sumi-600">{module.summary}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {Object.entries(module.metrics)
              .slice(0, 4)
              .map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-xl border border-sumi-700/20 bg-sumi-900/55 px-3 py-2"
                >
                  <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
                    {humanize(label)}
                  </div>
                  <div className="mt-1 truncate text-sm text-kitsurubami">{value}</div>
                </div>
              ))}
          </div>
          <div className="mt-3 text-xs text-sumi-600">
            Last activity {formatTimestamp(module.last_activity)}
          </div>
        </div>
      </div>
    </button>
  );
}

function ModuleDetail({ module }: { module: ModuleTruthOut }) {
  const Icon = iconMap[module.id as keyof typeof iconMap] ?? Activity;
  const status = statusStyles(module.status);

  return (
    <div className="space-y-4">
      <div className="glass-panel overflow-hidden p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className={`rounded-2xl border ${status.softBorder} ${status.softBg} p-3`}>
                <Icon size={20} className={status.iconClass} />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-heading text-2xl font-bold text-torinoko">
                    {module.name}
                  </h2>
                  <StatusPill status={module.status} />
                </div>
                <div className="mt-1 text-sm text-sumi-600">
                  Last activity {formatTimestamp(module.last_activity)}
                </div>
              </div>
            </div>
            <p className="max-w-3xl text-sm leading-6 text-sumi-600">
              {module.summary}
            </p>
            <div className={`rounded-2xl border ${status.softBorder} bg-sumi-900/65 p-4 text-sm leading-6 text-kitsurubami`}>
              {module.status_reason}
            </div>
          </div>

          <div className="grid min-w-[280px] grid-cols-2 gap-2">
            {Object.entries(module.metrics).map(([label, value]) => (
              <div
                key={label}
                className="rounded-2xl border border-sumi-700/20 bg-sumi-850/65 px-3 py-3"
              >
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
                  {humanize(label)}
                </div>
                <div className="mt-2 break-words text-sm text-torinoko">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <SectionPanel title="Processes" eyebrow="live pids">
          {module.processes.length === 0 ? (
            <EmptyState message="No dedicated process surface for this module." />
          ) : (
            <div className="space-y-3">
              {module.processes.map((process) => (
                <ProcessCard key={`${process.source}-${process.pid}`} process={process} />
              ))}
            </div>
          )}
        </SectionPanel>

        <SectionPanel title="Wiring" eyebrow="how it connects">
          <div className="space-y-3">
            {module.wiring.map((wire, index) => (
              <WireRow key={`${wire.direction}-${wire.target}-${index}`} wire={wire} />
            ))}
          </div>
        </SectionPanel>

        <SectionPanel title="Actual Projects" eyebrow="real paths">
          <div className="space-y-3">
            {module.projects.map((project) => (
              <ProjectRow key={`${project.kind}-${project.path}`} project={project} />
            ))}
          </div>
        </SectionPanel>

        <SectionPanel title="Recent History" eyebrow="observed events">
          {module.history.length === 0 ? (
            <EmptyState message="No recent history surfaced for this module." />
          ) : (
            <div className="space-y-3">
              {module.history.map((event, index) => (
                <HistoryRow key={`${event.source}-${event.timestamp}-${index}`} event={event} />
              ))}
            </div>
          )}
        </SectionPanel>
      </div>

      <SectionPanel title="Top 10 Salient Now" eyebrow="files or history">
        {module.salient.length === 0 ? (
          <EmptyState message="No salient evidence surfaced." />
        ) : (
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {module.salient.map((item, index) => (
              <SalientRow key={`${item.kind}-${item.title}-${index}`} item={item} index={index + 1} />
            ))}
          </div>
        )}
      </SectionPanel>
    </div>
  );
}

function SummaryChip({
  label,
  value,
  accent,
  wide,
}: {
  label: string;
  value: string;
  accent?: "ok" | "warn" | "error";
  wide?: boolean;
}) {
  const accentClass =
    accent === "ok"
      ? "text-rokusho"
      : accent === "warn"
        ? "text-kinpaku"
        : accent === "error"
          ? "text-bengara"
          : "text-torinoko";

  return (
    <div
      className={`rounded-2xl border border-sumi-700/25 bg-sumi-850/65 px-3 py-3 ${
        wide ? "col-span-2" : ""
      }`}
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
        {label}
      </div>
      <div className={`mt-2 break-words font-heading text-lg ${accentClass}`}>{value}</div>
    </div>
  );
}

function SectionPanel({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <div className="glass-panel p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
            {eyebrow}
          </div>
          <h3 className="mt-1 font-heading text-lg font-semibold text-torinoko">
            {title}
          </h3>
        </div>
      </div>
      {children}
    </div>
  );
}

function ProcessCard({ process }: { process: ModuleProcessOut }) {
  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-sumi-850 px-2.5 py-1 font-mono text-[10px] tracking-[0.16em] text-torinoko">
          PID {process.pid}
        </span>
        <StatusPill status={process.live ? "active" : "broken"} compact />
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
          {process.source}
        </span>
      </div>
      <div className="mt-3 break-words font-mono text-xs leading-5 text-kitsurubami">
        {process.command ?? "No command captured"}
      </div>
      {process.observed_paths.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {process.observed_paths.map((path) => (
            <span
              key={path}
              className="rounded-xl border border-sumi-700/20 bg-sumi-850/60 px-2.5 py-1 font-mono text-[11px] text-sumi-600"
            >
              {path}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectRow({ project }: { project: ModuleProjectOut }) {
  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-heading text-sm font-semibold text-torinoko">
          {project.label}
        </span>
        <span className="rounded-full bg-sumi-850 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
          {project.kind}
        </span>
        {project.exists ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-rokusho/12 px-2 py-0.5 text-[11px] text-rokusho">
            <CheckCircle2 size={12} />
            present
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-bengara/12 px-2 py-0.5 text-[11px] text-bengara">
            <AlertTriangle size={12} />
            missing
          </span>
        )}
      </div>
      <div className="mt-3 break-all font-mono text-xs text-kitsurubami">{project.path}</div>
      <div className="mt-2 text-xs text-sumi-600">
        {project.modified_at ? `Touched ${formatTimestamp(project.modified_at)}` : "No timestamp"}
      </div>
    </div>
  );
}

function WireRow({ wire }: { wire: ModuleWireOut }) {
  const directionClass =
    wire.direction === "writes"
      ? "bg-aozora/12 text-aozora"
      : wire.direction === "reads"
        ? "bg-kinpaku/12 text-kinpaku"
        : "bg-botan/12 text-botan";

  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] ${directionClass}`}>
          {wire.direction}
        </span>
        <span className="font-heading text-sm font-semibold text-torinoko">{wire.target}</span>
      </div>
      <div className="mt-2 text-sm leading-6 text-kitsurubami">{wire.detail}</div>
    </div>
  );
}

function HistoryRow({ event }: { event: ModuleHistoryOut }) {
  const pill =
    event.status === "broken"
      ? "bg-bengara/12 text-bengara"
      : event.status === "warn"
        ? "bg-kinpaku/12 text-kinpaku"
        : "bg-rokusho/12 text-rokusho";

  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-heading text-sm font-semibold text-torinoko">{event.title}</span>
        <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] ${pill}`}>
          {event.status}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
          {formatTimestamp(event.timestamp)}
        </span>
      </div>
      <div className="mt-2 text-sm leading-6 text-kitsurubami">{event.detail}</div>
      <div className="mt-2 break-all font-mono text-[11px] text-sumi-600">{event.source}</div>
    </div>
  );
}

function SalientRow({
  item,
  index,
}: {
  item: ModuleSalientOut;
  index: number;
}) {
  return (
    <div className="rounded-2xl border border-sumi-700/20 bg-sumi-900/60 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-aozora/12 font-heading text-sm text-aozora">
          {index}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-heading text-sm font-semibold text-torinoko">
              {item.title}
            </span>
            <span className="rounded-full bg-sumi-850 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
              {item.kind}
            </span>
            <span className="rounded-full bg-sumi-850 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-kitsurubami">
              score {item.score.toFixed(2)}
            </span>
          </div>
          <div className="mt-2 text-sm leading-6 text-kitsurubami">{item.detail}</div>
          <div className="mt-2 text-xs text-sumi-600">{item.reason}</div>
          {item.path && (
            <div className="mt-2 break-all font-mono text-[11px] text-sumi-600">
              {item.path}
            </div>
          )}
          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
            {formatTimestamp(item.timestamp)}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-sumi-700/30 bg-sumi-850/40 p-6 text-sm text-sumi-600">
      {message}
    </div>
  );
}

function StatusPill({
  status,
  compact,
}: {
  status: string;
  compact?: boolean;
}) {
  const style = statusStyles(status);

  return (
    <span
      className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] ${style.pillBg} ${style.pillText} ${
        compact ? "" : "shadow-[0_0_16px_rgba(0,0,0,0.16)]"
      }`}
    >
      {status}
    </span>
  );
}

function statusStyles(status: string) {
  switch (status) {
    case "active":
      return {
        cardBorder: "border-rokusho/40",
        softBorder: "border-rokusho/30",
        softBg: "bg-rokusho/10",
        pillBg: "bg-rokusho/12",
        pillText: "text-rokusho",
        iconClass: "text-rokusho",
      };
    case "mixed":
      return {
        cardBorder: "border-kinpaku/40",
        softBorder: "border-kinpaku/30",
        softBg: "bg-kinpaku/10",
        pillBg: "bg-kinpaku/12",
        pillText: "text-kinpaku",
        iconClass: "text-kinpaku",
      };
    case "broken":
      return {
        cardBorder: "border-bengara/40",
        softBorder: "border-bengara/30",
        softBg: "bg-bengara/10",
        pillBg: "bg-bengara/12",
        pillText: "text-bengara",
        iconClass: "text-bengara",
      };
    default:
      return {
        cardBorder: "border-sumi-600/40",
        softBorder: "border-sumi-600/30",
        softBg: "bg-sumi-800/30",
        pillBg: "bg-sumi-800/70",
        pillText: "text-sumi-600",
        iconClass: "text-sumi-600",
      };
  }
}

function formatTimestamp(value: string | null) {
  if (!value) {
    return "no timestamp";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function humanize(label: string) {
  return label.replaceAll("_", " ");
}
