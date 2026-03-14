/**
 * DHARMA COMMAND -- Reconnecting WebSocket connection factory.
 *
 * Usage:
 *   const ws = new DharmaSocket("swarm", { onMessage: (evt) => ... });
 *   ws.connect();
 *   // later:
 *   ws.close();
 */

import { wsBaseUrl } from "./api";
import type { WsEvent } from "./types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DharmaSocketOptions {
  /** WebSocket channel / topic (appended to the URL path). */
  channel?: string;
  /** Called on every parsed message. */
  onMessage?: (event: WsEvent) => void;
  /** Called when connection opens. */
  onOpen?: () => void;
  /** Called when connection closes. */
  onClose?: (code: number, reason: string) => void;
  /** Called on error. */
  onError?: (error: Event) => void;
  /** Max reconnect attempts (default 10). 0 = infinite. */
  maxRetries?: number;
  /** Base delay in ms before first reconnect (default 1000). Doubles each attempt. */
  baseDelay?: number;
  /** Maximum delay between retries in ms (default 30000). */
  maxDelay?: number;
}

// ---------------------------------------------------------------------------
// DharmaSocket
// ---------------------------------------------------------------------------

export class DharmaSocket {
  private ws: WebSocket | null = null;
  private retries = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private intentionallyClosed = false;
  private readonly url: string;
  private readonly opts: Required<
    Pick<DharmaSocketOptions, "maxRetries" | "baseDelay" | "maxDelay">
  > &
    DharmaSocketOptions;

  constructor(channel: string, options: DharmaSocketOptions = {}) {
    const base = wsBaseUrl();
    const ch = channel.startsWith("/") ? channel : `/${channel}`;
    this.url = `${base}/ws${ch}`;
    this.opts = {
      maxRetries: 10,
      baseDelay: 1000,
      maxDelay: 30_000,
      ...options,
      channel,
    };
  }

  /** Open the WebSocket connection. */
  connect(): void {
    this.intentionallyClosed = false;
    this._open();
  }

  /** Gracefully close and stop reconnecting. */
  close(): void {
    this.intentionallyClosed = true;
    this._clearTimer();
    if (this.ws) {
      this.ws.close(1000, "client_close");
      this.ws = null;
    }
  }

  /** Send a JSON-serializable payload. */
  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /** Current readyState. */
  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  private _open(): void {
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.retries = 0;
      this.opts.onOpen?.();
    };

    this.ws.onmessage = (raw: MessageEvent) => {
      try {
        const parsed: WsEvent = JSON.parse(String(raw.data));
        this.opts.onMessage?.(parsed);
      } catch {
        // Non-JSON messages are silently dropped.
      }
    };

    this.ws.onclose = (ev: CloseEvent) => {
      this.opts.onClose?.(ev.code, ev.reason);
      if (!this.intentionallyClosed) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = (ev: Event) => {
      this.opts.onError?.(ev);
    };
  }

  private _scheduleReconnect(): void {
    const { maxRetries, baseDelay, maxDelay } = this.opts;

    if (maxRetries > 0 && this.retries >= maxRetries) {
      return; // Give up.
    }

    const jitter = Math.random() * 500;
    const delay = Math.min(baseDelay * 2 ** this.retries + jitter, maxDelay);
    this.retries += 1;

    this._clearTimer();
    this.timer = setTimeout(() => this._open(), delay);
  }

  private _clearTimer(): void {
    if (this.timer != null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
