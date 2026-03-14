"use client";

/**
 * DHARMA COMMAND -- Generic WebSocket hook with auto-reconnect.
 *
 * Usage:
 *   const { connected, lastEvent } = useWebSocket("swarm", {
 *     onMessage: (evt) => console.log(evt),
 *   });
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { DharmaSocket, type DharmaSocketOptions } from "@/lib/ws";
import type { WsEvent } from "@/lib/types";

export interface UseWebSocketOptions
  extends Omit<DharmaSocketOptions, "channel" | "onMessage" | "onOpen" | "onClose"> {
  /** Called for every incoming event. */
  onMessage?: (event: WsEvent) => void;
  /** If false, the socket will not connect (default true). */
  enabled?: boolean;
}

export interface UseWebSocketReturn {
  /** Whether the socket is currently open. */
  connected: boolean;
  /** The last received event, or null. */
  lastEvent: WsEvent | null;
  /** Manually send a JSON payload. */
  send: (data: unknown) => void;
  /** Manually reconnect. */
  reconnect: () => void;
}

export function useWebSocket(
  channel: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { onMessage, enabled = true, ...rest } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);

  // Stable refs so the socket callbacks don't cause re-renders/reconnects.
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const socketRef = useRef<DharmaSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const socket = new DharmaSocket(channel, {
      ...rest,
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
      onMessage: (evt) => {
        setLastEvent(evt);
        onMessageRef.current?.(evt);
      },
    });

    socket.connect();
    socketRef.current = socket;

    return () => {
      socket.close();
      socketRef.current = null;
      setConnected(false);
    };
    // Reconnect only when channel or enabled changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, enabled]);

  const send = useCallback((data: unknown) => {
    socketRef.current?.send(data);
  }, []);

  const reconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current?.connect();
  }, []);

  return { connected, lastEvent, send, reconnect };
}
