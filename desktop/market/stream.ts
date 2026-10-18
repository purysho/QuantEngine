// Alpaca real-time stream (stocks or crypto): authenticate, subscribe, reconnect with backoff.
import type { Credentials } from './alpaca.js';

export interface SocketLike {
  send(data: string): void;
  close(): void;
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code?: number }) => void) | null;
  onerror: ((event: unknown) => void) | null;
}
export type SocketFactory = (url: string) => SocketLike;
export type StreamStatus = 'off' | 'connecting' | 'live' | 'busy' | 'error';
export interface StreamMessage { T: string; S?: string; [key: string]: unknown }

export const STREAM_HOST = 'wss://stream.data.alpaca.markets';
export const MAX_STREAM_SYMBOLS = 30;  // Free plan limit per connection.

/** Plain-language meaning of Alpaca stream error codes; `retry` says whether reconnecting can help. */
export function streamError(code: number): { message: string; retry: boolean; delay?: number } {
  switch (code) {
    case 402: return { message: 'Alpaca rejected the API keys for live streaming.', retry: false };
    case 404: return { message: 'Live stream authentication timed out; reconnecting.', retry: true };
    case 405: return { message: 'Too many live symbols for your Alpaca plan (free plan: 30).', retry: false };
    case 406: return { message: 'Another program is already using your Alpaca live stream (the free plan allows one connection). Showing 15-second snapshots instead.', retry: true, delay: 60_000 };
    case 407: return { message: 'The live stream fell behind and was disconnected; reconnecting.', retry: true };
    case 409: return { message: 'Your Alpaca plan does not include this feed. Choose the IEX feed in Preferences.', retry: false };
    default: return { message: `Alpaca stream error ${code}.`, retry: true };
  }
}

export class MarketStream {
  status: StreamStatus = 'off';
  detail = '';
  private socket: SocketLike | null = null;
  private symbols = new Set<string>();
  private subscribed = new Set<string>();
  private stopped = true;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private nextDelay: number | null = null;

  constructor(readonly url: string, private credentials: Credentials, readonly factory: SocketFactory,
              readonly onData: (messages: StreamMessage[]) => void,
              readonly onStatus: (status: StreamStatus, detail: string) => void) {}

  start(symbols: string[]) {
    this.symbols = new Set(symbols.slice(0, MAX_STREAM_SYMBOLS));
    this.stopped = false;
    if (!this.socket && !this.timer) this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const socket = this.socket;
    this.socket = null;
    this.subscribed.clear();
    socket?.close();
    this.setStatus('off', '');
  }

  setSymbols(symbols: string[]) {
    this.symbols = new Set(symbols.slice(0, MAX_STREAM_SYMBOLS));
    if (this.status === 'live') this.syncSubscriptions();
  }

  private setStatus(status: StreamStatus, detail: string) {
    this.status = status; this.detail = detail;
    this.onStatus(status, detail);
  }

  private connect() {
    this.timer = null;
    this.setStatus('connecting', 'Connecting to the Alpaca live stream');
    let socket: SocketLike;
    try { socket = this.factory(this.url); } catch (error) { this.retry(String((error as Error).message)); return; }
    this.socket = socket;
    socket.onmessage = event => {
      if (this.socket !== socket) return;
      let messages: StreamMessage[];
      try {
        const parsed = JSON.parse(typeof event.data === 'string' ? event.data : String(event.data));
        messages = Array.isArray(parsed) ? parsed : [parsed];
      } catch { return; }
      const data: StreamMessage[] = [];
      for (const message of messages) {
        if (message.T === 'success' && message.msg === 'connected') {
          socket.send(JSON.stringify({ action: 'auth', key: this.credentials.keyId, secret: this.credentials.secret }));
        } else if (message.T === 'success' && message.msg === 'authenticated') {
          this.attempt = 0;
          this.subscribed.clear();
          this.setStatus('live', 'Live');
          this.syncSubscriptions();
        } else if (message.T === 'error') {
          const problem = streamError(Number(message.code));
          this.nextDelay = problem.delay ?? null;
          if (!problem.retry) this.stopped = true;
          this.setStatus(Number(message.code) === 406 ? 'busy' : 'error', problem.message);
        } else if (message.T === 'subscription') {
          const trades = Array.isArray(message.trades) ? message.trades as string[] : [];
          this.subscribed = new Set(trades);
        } else data.push(message);
      }
      if (data.length) this.onData(data);
    };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.subscribed.clear();
      if (this.stopped) { if (this.status !== 'error') this.setStatus('off', ''); return; }
      this.retry(this.status === 'busy' || this.status === 'error' ? this.detail : 'Live stream disconnected; reconnecting');
    };
    socket.onerror = () => { /* onclose follows and handles reconnection. */ };
  }

  private retry(detail: string) {
    if (this.stopped) return;
    const delay = this.nextDelay ?? Math.min(60_000, 1000 * 2 ** this.attempt);
    this.nextDelay = null;
    this.attempt++;
    if (this.status !== 'busy') this.setStatus('connecting', detail);
    this.timer = setTimeout(() => this.connect(), delay);
  }

  private syncSubscriptions() {
    if (!this.socket || this.status !== 'live') return;
    const add = [...this.symbols].filter(s => !this.subscribed.has(s));
    const remove = [...this.subscribed].filter(s => !this.symbols.has(s));
    if (remove.length) this.socket.send(JSON.stringify({ action: 'unsubscribe', trades: remove, quotes: remove, bars: remove, dailyBars: remove }));
    if (add.length) this.socket.send(JSON.stringify({ action: 'subscribe', trades: add, quotes: add, bars: add, dailyBars: add }));
    this.subscribed = new Set(this.symbols);
  }
}
