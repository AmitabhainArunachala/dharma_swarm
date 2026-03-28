import type { ChatProfileOut, ChatStatusOut } from "./types";

export const DEFAULT_CHAT_PROFILE_ID = "claude_opus";
export const CHAT_CONTRACT_VERSION_STORAGE_KEY = "dharma-chat-contract-version";
const CODEX_OPERATOR_PROFILE_ID = "codex_operator";

export interface ResolveChatProfileIdOptions {
  allowAdvertisedFallback?: boolean;
}

function fallbackChatProfile(profileId?: string): ChatProfileOut {
  return {
    id: profileId || DEFAULT_CHAT_PROFILE_ID,
    label: "Operator Chat",
    provider: "backend",
    model: "loading",
    accent: "aozora",
    summary: "Waiting for the dashboard backend to advertise chat profiles.",
    available: true,
    availability_kind: "bootstrap",
    status_note: "Waiting for /api/chat/status.",
  };
}

export function getChatProfiles(status: ChatStatusOut | null): ChatProfileOut[] {
  return status?.profiles ?? [];
}

export function findAdvertisedChatProfile(
  status: ChatStatusOut | null,
  profileId?: string | null,
): ChatProfileOut | null {
  if (!profileId) {
    return null;
  }
  return getChatProfiles(status).find((profile) => profile.id === profileId) ?? null;
}

export function isAdvertisedChatProfileAvailable(
  status: ChatStatusOut | null,
  profileId?: string | null,
): boolean {
  const profile = findAdvertisedChatProfile(status, profileId);
  return profile != null && profile.available !== false;
}

export function resolveCanonicalChatStatus(
  ...statuses: Array<ChatStatusOut | null | undefined>
): ChatStatusOut | null {
  return statuses.find((status): status is ChatStatusOut => status != null) ?? null;
}

function usableProfiles(status: ChatStatusOut | null): ChatProfileOut[] {
  const profiles = getChatProfiles(status);
  const available = profiles.filter((profile) => profile.available !== false);
  return available.length > 0 ? available : profiles;
}

export function resolveChatProfileId(
  status: ChatStatusOut | null,
  requestedProfileId?: string | null,
  options?: ResolveChatProfileIdOptions,
): string {
  const allowAdvertisedFallback = options?.allowAdvertisedFallback ?? true;
  const advertisedProfiles = getChatProfiles(status);
  const profiles = usableProfiles(status);
  if (
    requestedProfileId &&
    advertisedProfiles.some((profile) => profile.id === requestedProfileId)
  ) {
    return requestedProfileId;
  }
  if (!allowAdvertisedFallback && requestedProfileId) {
    return requestedProfileId;
  }
  if (
    status?.default_profile_id &&
    profiles.some((profile) => profile.id === status.default_profile_id)
  ) {
    return status.default_profile_id;
  }
  if (profiles[0]?.id) {
    return profiles[0].id;
  }
  return requestedProfileId || status?.default_profile_id || DEFAULT_CHAT_PROFILE_ID;
}

export function resolveCommandPostPeerProfileId(status: ChatStatusOut | null): string | null {
  const peerProfiles = usableProfiles(status).filter(
    (profile) => profile.id !== CODEX_OPERATOR_PROFILE_ID,
  );
  if (peerProfiles.some((profile) => profile.id === DEFAULT_CHAT_PROFILE_ID)) {
    return DEFAULT_CHAT_PROFILE_ID;
  }
  return peerProfiles[0]?.id ?? null;
}

export function resolveChatProfile(
  status: ChatStatusOut | null,
  profileId?: string | null,
): ChatProfileOut {
  const profiles = getChatProfiles(status);
  const resolvedId = resolveChatProfileId(status, profileId);
  return (
    profiles.find((profile) => profile.id === resolvedId) ??
    profiles.find((profile) => profile.id === status?.default_profile_id) ??
    fallbackChatProfile(resolvedId)
  );
}

export function shortProfileLabel(profile: ChatProfileOut): string {
  if (profile.label.startsWith("Claude Sonnet")) return "Sonnet";
  if (profile.label.startsWith("Claude")) return "Claude";
  if (profile.label.startsWith("Codex")) return "Codex";
  if (profile.label.startsWith("Kimi")) return "Kimi";
  if (profile.label.startsWith("GLM")) return "GLM";
  if (profile.label.startsWith("Qwen")) return "Qwen";
  return profile.label;
}
