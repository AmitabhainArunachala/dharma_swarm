import type { ChatProfileOut, ChatStatusOut } from "./types";

export const DEFAULT_CHAT_PROFILE_ID = "codex_operator";

export const DEFAULT_CHAT_PROFILES: ChatProfileOut[] = [
  {
    id: "claude_opus",
    label: "Claude Opus 4.6",
    provider: "openrouter",
    model: "anthropic/claude-opus-4-6",
    accent: "aozora",
    summary: "Strategic operator with full swarm tooling and broad system context.",
  },
  {
    id: "codex_operator",
    label: "Codex 5.4",
    provider: "openrouter",
    model: "openai/gpt-5-codex",
    accent: "kinpaku",
    summary: "Implementation-focused control agent for edits, verification, and fast fixes.",
  },
];

export function getChatProfiles(status: ChatStatusOut | null): ChatProfileOut[] {
  if (status?.profiles?.length) return status.profiles;
  return DEFAULT_CHAT_PROFILES;
}

export function resolveChatProfile(
  status: ChatStatusOut | null,
  profileId: string,
): ChatProfileOut {
  const profiles = getChatProfiles(status);
  return (
    profiles.find((profile) => profile.id === profileId) ??
    profiles.find((profile) => profile.id === status?.default_profile_id) ??
    DEFAULT_CHAT_PROFILES[0]
  );
}

export function shortProfileLabel(profile: ChatProfileOut): string {
  if (profile.label.startsWith("Claude")) return "Claude";
  if (profile.label.startsWith("Codex")) return "Codex";
  return profile.label;
}
