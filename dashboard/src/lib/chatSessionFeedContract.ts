export interface ChatSessionFeedIdentityArgs {
  profileId: string;
  sessionId: string;
  wsPathTemplate?: string;
}

function normalizeIdentityPart(value: string | null | undefined): string {
  return value?.trim() ?? "";
}

export function normalizeChatSessionFeedTemplate(
  value: string | null | undefined,
): string | null {
  const normalized = value?.trim() ?? "";
  return normalized ? normalized : null;
}

export function buildChatSessionFeedIdentity(
  args: ChatSessionFeedIdentityArgs,
): string {
  return [
    normalizeIdentityPart(args.profileId),
    normalizeIdentityPart(args.sessionId),
    normalizeIdentityPart(args.wsPathTemplate),
  ].join("::");
}

export function buildChatSessionFeedChannel(args: {
  sessionId: string;
  wsPathTemplate?: string;
}): string {
  const sessionId = normalizeIdentityPart(args.sessionId);
  const template = normalizeChatSessionFeedTemplate(args.wsPathTemplate);

  if (!sessionId || !template) {
    return "";
  }

  return template
    .replace("{session_id}", encodeURIComponent(sessionId))
    .replace(/^\/ws\//, "")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");
}
