"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Bot, Search, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { fetchChatStatus } from "@/lib/api";
import { resolveChatProfile } from "@/lib/chatProfiles";
import type { ChatStatusOut } from "@/lib/types";
import { colors, glowBorder, glowBox } from "@/lib/theme";

const QWEN_PROFILE_ID = "qwen35_surgeon";

function InfoCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div
      className="rounded-[22px] border border-sumi-700/40 bg-sumi-900/85 p-4"
      style={{ boxShadow: `${glowBorder(accent, 0.24)}, ${glowBox(accent, 0.12)}` }}
    >
      <div className="flex items-center gap-2">
        <div
          className="rounded-xl border p-2"
          style={{
            color: accent,
            borderColor: `color-mix(in srgb, ${accent} 24%, transparent)`,
            background: `color-mix(in srgb, ${accent} 10%, transparent)`,
          }}
        >
          {icon}
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.12em] text-kitsurubami">{label}</p>
          <p className="mt-1 text-sm text-torinoko">{value}</p>
        </div>
      </div>
    </div>
  );
}

export default function Qwen35Page() {
  const { data } = useQuery({
    queryKey: ["chat-status", QWEN_PROFILE_ID],
    queryFn: () => fetchChatStatus(),
    refetchInterval: 15_000,
  });

  const status: ChatStatusOut | null = data?.status === "ok" ? data.data : null;
  const profile = resolveChatProfile(status, QWEN_PROFILE_ID);
  const accent = colors.rokusho;

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="relative overflow-hidden rounded-[30px] border border-sumi-700/40 bg-sumi-900/92 p-6"
        style={{ boxShadow: `${glowBorder(accent, 0.2)}, ${glowBox(accent, 0.12)}` }}
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_18%,rgba(143,168,155,0.24),transparent_28%),radial-gradient(circle_at_82%_18%,rgba(79,209,217,0.16),transparent_24%),linear-gradient(140deg,rgba(13,14,19,0.2),transparent_72%)]" />
        <div className="relative grid gap-6 lg:grid-cols-[1.2fr_0.95fr]">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-rokusho/30 bg-rokusho/10 p-3 text-rokusho">
                <Bot size={24} />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="font-heading text-3xl font-bold tracking-tight text-rokusho">
                    Qwen Surgeon
                  </h1>
                  <span className="rounded-full border border-rokusho/30 bg-rokusho/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-rokusho">
                    bounded scan lane
                  </span>
                </div>
                <p className="mt-2 max-w-3xl text-sm text-sumi-600">
                  A tracked, dedicated coding console for fast repo reconnaissance, surgical edits,
                  and verification. This page is pinned to a real backend chat profile so it no
                  longer depends on an out-of-band local UI layer.
                </p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <InfoCard
                icon={<Sparkles size={15} />}
                label="Profile"
                value={profile.label}
                accent={accent}
              />
              <InfoCard
                icon={<Wrench size={15} />}
                label="Model"
                value={profile.model}
                accent={colors.kinpaku}
              />
              <InfoCard
                icon={<ShieldCheck size={15} />}
                label="Backend"
                value={profile.status_note || "Profile state unavailable."}
                accent={profile.available === false ? colors.bengara : colors.aozora}
              />
            </div>
          </div>

          <div className="rounded-[26px] border border-sumi-700/35 bg-sumi-950/35 p-5">
            <div className="mb-4 flex items-center gap-2">
              <Search size={15} className="text-aozora" />
              <h2 className="font-heading text-lg text-torinoko">Operating Bias</h2>
            </div>
            <div className="space-y-3 text-sm text-sumi-600">
              <p>Use this lane for code-level diagnosis, bounded scans, and quick validation.</p>
              <p>It is intentionally tighter than the strategic control-plane chat so broad prompts do not spiral into endless tool loops.</p>
              <p>If the backend bounces, the chat surface now retries once and exposes a direct retry affordance instead of leaving a dead placeholder bubble.</p>
            </div>
          </div>
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.06 }}
        className="glass-panel h-[calc(100vh-18rem)] min-h-[620px] overflow-hidden"
      >
        <ChatInterface
          className="h-full"
          profileId={QWEN_PROFILE_ID}
          allowProfileSwitch={false}
        />
      </motion.section>
    </div>
  );
}
