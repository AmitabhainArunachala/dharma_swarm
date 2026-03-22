"use client";

import { useMemo, useState } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import {
  buildChatSessionFeedChannel,
  buildChatSessionFeedIdentity,
} from "@/lib/chatSessionFeedContract";
import type { WsEvent } from "@/lib/types";

export interface ChatSessionFeedEvent {
  id: string;
  profileId: string;
  sessionId: string;
  event: string;
  headline: string;
  detail: string;
  timestamp: string;
}

interface UseChatSessionFeedArgs {
  profileId: string;
  profileLabel: string;
  sessionId: string;
  wsPathTemplate?: string;
}

interface UseChatSessionFeedReturn {
  connected: boolean;
  events: ChatSessionFeedEvent[];
  lastEvent: ChatSessionFeedEvent | null;
  snapshotTurns: number;
}

interface ChatSessionFeedState {
  identity: string;
  events: ChatSessionFeedEvent[];
  snapshotTurns: number;
}

const MAX_EVENTS = 18;

function shorten(value: unknown, limit: number = 120): string {
  const text = typeof value === "string" ? value.trim() : String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 3).trimEnd()}...`;
}

function summarizeEvent(
  rawEvent: WsEvent & Record<string, unknown>,
  profileId: string,
  profileLabel: string,
  sessionId: string,
): ChatSessionFeedEvent | null {
  const timestamp =
    typeof rawEvent.timestamp === "string" ? rawEvent.timestamp : new Date().toISOString();
  const event = typeof rawEvent.event === "string" ? rawEvent.event : "";

  if (!event) return null;

  let headline = "";
  let detail = "";

  switch (event) {
    case "chat_snapshot": {
      const turns = Array.isArray(rawEvent.turns) ? rawEvent.turns.length : 0;
      headline = `${profileLabel} snapshot`;
      detail = `${turns} persisted turns loaded`;
      break;
    }
    case "chat_session_ready":
      headline = `${profileLabel} online`;
      detail = `${shorten(rawEvent.provider, 40)} · ${shorten(rawEvent.model, 60)}`;
      break;
    case "chat_user_turn":
      headline = `Operator -> ${profileLabel}`;
      detail = shorten(rawEvent.content, 140);
      break;
    case "chat_assistant_turn":
      headline = `${profileLabel} replied`;
      detail = shorten(rawEvent.content, 140);
      break;
    case "chat_text":
      headline = `${profileLabel} streaming`;
      detail = shorten(rawEvent.content, 140);
      break;
    case "chat_tool_call":
      headline = `${profileLabel} tool call`;
      detail = shorten(rawEvent.tool_name, 80);
      break;
    case "chat_tool_result":
      headline = `${profileLabel} tool result`;
      detail = `${shorten(rawEvent.tool_name, 60)} · ${shorten(rawEvent.summary, 120)}`;
      break;
    case "chat_done":
      headline = `${profileLabel} turn complete`;
      detail = shorten(rawEvent.stopped ?? rawEvent.provider ?? "stream finished", 100);
      break;
    case "chat_error":
      headline = `${profileLabel} error`;
      detail = shorten(rawEvent.error, 140);
      break;
    default:
      return null;
  }

  return {
    id: `${profileId}-${event}-${timestamp}-${Math.random().toString(16).slice(2, 8)}`,
    profileId,
    sessionId,
    event,
    headline,
    detail,
    timestamp,
  };
}

export function useChatSessionFeed({
  profileId,
  profileLabel,
  sessionId,
  wsPathTemplate,
}: UseChatSessionFeedArgs): UseChatSessionFeedReturn {
  const [feedState, setFeedState] = useState<ChatSessionFeedState>({
    identity: "",
    events: [],
    snapshotTurns: 0,
  });
  const feedIdentity = useMemo(
    () => buildChatSessionFeedIdentity({ profileId, sessionId, wsPathTemplate }),
    [profileId, sessionId, wsPathTemplate],
  );

  const channel = useMemo(() => {
    return buildChatSessionFeedChannel({ sessionId, wsPathTemplate });
  }, [sessionId, wsPathTemplate]);
  const visibleFeedState = feedState.identity === feedIdentity
    ? feedState
    : {
        identity: feedIdentity,
        events: [],
        snapshotTurns: 0,
      };

  const { connected } = useWebSocket(channel, {
    enabled: Boolean(channel),
    onMessage: (message) => {
      const rawEvent = message as WsEvent & Record<string, unknown>;
      const eventProfileId = typeof rawEvent.profile_id === "string" ? rawEvent.profile_id : "";
      const eventSessionId = typeof rawEvent.session_id === "string" ? rawEvent.session_id : "";

      if (sessionId) {
        if (eventSessionId && eventSessionId !== sessionId && rawEvent.event !== "chat_snapshot") {
          return;
        }
      } else if (eventProfileId && eventProfileId !== profileId) {
        return;
      }

      const summarized = summarizeEvent(rawEvent, profileId, profileLabel, sessionId);
      setFeedState((prev) => {
        const base =
          prev.identity === feedIdentity
            ? prev
            : { identity: feedIdentity, events: [], snapshotTurns: 0 };
        const nextSnapshotTurns =
          rawEvent.event === "chat_snapshot"
            ? Array.isArray(rawEvent.turns)
              ? rawEvent.turns.length
              : 0
            : base.snapshotTurns;

        if (!summarized) {
          if (base.snapshotTurns === nextSnapshotTurns && base.identity === prev.identity) {
            return prev;
          }
          return {
            ...base,
            snapshotTurns: nextSnapshotTurns,
          };
        }

        if (
          summarized.event === "chat_text" &&
          base.events[0] &&
          base.events[0].event === "chat_text" &&
          base.events[0].profileId === summarized.profileId &&
          base.events[0].sessionId === summarized.sessionId
        ) {
          const merged = {
            ...base.events[0],
            detail: shorten(`${base.events[0].detail} ${summarized.detail}`, 220),
            timestamp: summarized.timestamp,
          };
          return {
            identity: feedIdentity,
            snapshotTurns: nextSnapshotTurns,
            events: [merged, ...base.events.slice(1)].slice(0, MAX_EVENTS),
          };
        }

        return {
          identity: feedIdentity,
          snapshotTurns: nextSnapshotTurns,
          events: [summarized, ...base.events].slice(0, MAX_EVENTS),
        };
      });
    },
  });

  return {
    connected,
    events: visibleFeedState.events,
    lastEvent: visibleFeedState.events[0] ?? null,
    snapshotTurns: visibleFeedState.snapshotTurns,
  };
}
