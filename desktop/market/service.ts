// The terminal's market-data hub: watchlist, live quotes (stream with snapshot fallback), charts,
// news, macro and option chains. Runs in the Electron main process; the window receives plain data.
import { readFile, writeFile, rename, unlink, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { AlpacaClient, AlpacaError, isCrypto, validSymbol, type Bar, type Credentials, type Feed, type Fetch,
  type Snapshot, type Asset, type Clock, parseOcc } from './alpaca.js';
import { MarketStream, STREAM_HOST, MAX_STREAM_SYMBOLS, type SocketFactory, type StreamMessage, type StreamStatus } from './stream.js';
import { SecretStore, maskKey, validateCredentials } from './secrets.js';
import { fetchMacro, type MacroPoint } from './macro.js';

export interface QuoteRow {
  symbol: string; name: string | null; last: number | null; bid: number | null; ask: number | null;
  bidSize: number | null; askSize: number | null; open: number | null; high: number | null; low: number | null;
  prevClose: number | null; volume: number | null; change: number | null; changePct: number | null;
  time: string | null; tick: number; direction: -1 | 0 | 1;
}
export interface MarketSettings { watchlist: string[]; feed: Feed }
export const DEFAULT_WATCHLIST = ['SPY', 'QQQ', 'DIA', 'IWM', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'TSLA', 'BTC/USD', 'ETH/USD'];
export const MAX_WATCHLIST = 40;
export const RANGES: Record<string, { timeframe: string; days: number; intraday: boolean }> = {
  '1D': { timeframe: '1Min', days: 4, intraday: true }, '5D': { timeframe: '5Min', days: 8, intraday: true },
  '1M': { timeframe: '1Hour', days: 32, intraday: true }, '6M': { timeframe: '1Day', days: 186, intraday: false },
  '1Y': { timeframe: '1Day', days: 370, intraday: false }, '5Y': { timeframe: '1Day', days: 1830, intraday: false },
  MAX: { timeframe: '1Week', days: 3650 * 2, intraday: false },
};

export function validateWatchlist(value: unknown): string[] {
  if (!Array.isArray(value)) throw new Error('The watchlist must be a list of symbols.');
  const symbols = [...new Set(value.map(v => typeof v === 'string' ? v.trim().toUpperCase() : v))];
  if (symbols.length > MAX_WATCHLIST) throw new Error(`The watchlist holds up to ${MAX_WATCHLIST} symbols.`);
  for (const symbol of symbols) if (!validSymbol(symbol)) throw new Error(`Not a valid symbol: ${String(symbol).slice(0, 20)}`);
  return symbols as string[];
}

function emptyRow(symbol: string, name: string | null): QuoteRow {
  return { symbol, name, last: null, bid: null, ask: null, bidSize: null, askSize: null, open: null, high: null, low: null,
    prevClose: null, volume: null, change: null, changePct: null, time: null, tick: 0, direction: 0 };
}

export function realisedVol(closes: number[], window: number): number | null {
  if (closes.length <= window) return null;
  const r = closes.slice(-window - 1).slice(1).map((c, i) => Math.log(c / closes[closes.length - window - 1 + i]));
  const mean = r.reduce((a, b) => a + b, 0) / r.length;
  const variance = r.reduce((a, b) => a + (b - mean) ** 2, 0) / (r.length - 1);
  return Math.sqrt(variance * 252);
}

export class MarketService {
  settings: MarketSettings = { watchlist: [...DEFAULT_WATCHLIST], feed: 'iex' };
  quotes = new Map<string, QuoteRow>();
  credentials: Credentials | null = null;
  stockStream: MarketStream | null = null;
  cryptoStream: MarketStream | null = null;
  macro: MacroPoint[] = [];
  macroUpdated: string | null = null;
  clock: Clock | null = null;
  lastError: string | null = null;
  lastPoll: string | null = null;
  assets = new Map<string, Asset>();
  liveBars = new Map<string, Bar>();
  onChange: () => void = () => {};
  /** Synthetic offline market (self-test and screenshots only); the window labels it DEMO DATA. */
  demo = false;
  private publishTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private macroTimer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  readonly client: AlpacaClient;

  constructor(readonly folder: string, readonly secrets: SecretStore, readonly fetcher: Fetch,
              readonly socketFactory: SocketFactory, readonly now = () => Date.now()) {
    this.client = new AlpacaClient(null, fetcher);
  }

  private get settingsFile() { return path.join(this.folder, 'market.json'); }
  private get assetsFile() { return path.join(this.folder, 'assets-cache.json'); }

  async load() {
    try {
      const saved = JSON.parse(await readFile(this.settingsFile, 'utf8')) as Partial<MarketSettings>;
      this.settings = { watchlist: validateWatchlist(saved.watchlist ?? DEFAULT_WATCHLIST),
        feed: ['iex', 'sip', 'delayed_sip'].includes(saved.feed as string) ? saved.feed as Feed : 'iex' };
    } catch { /* First run or unreadable: defaults. */ }
    this.credentials = await this.secrets.load();
    this.client.setCredentials(this.credentials);
    try {
      const cached = JSON.parse(await readFile(this.assetsFile, 'utf8')) as { saved: string; assets: Asset[] };
      for (const asset of cached.assets) this.assets.set(asset.symbol, asset);
    } catch { /* Fetched after keys are added. */ }
    this.resetRows();
  }

  private async saveSettings() {
    await mkdir(this.folder, { recursive: true });
    const temporary = this.settingsFile + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, JSON.stringify(this.settings, null, 2)); await rename(temporary, this.settingsFile); }
    finally { await unlink(temporary).catch(() => {}); }
  }

  private resetRows() {
    const previous = this.quotes;
    this.quotes = new Map(this.settings.watchlist.map(symbol => [symbol, previous.get(symbol) ?? emptyRow(symbol, this.assets.get(symbol)?.name ?? null)]));
  }

  snapshot() {
    const status = (stream: MarketStream | null): { status: StreamStatus; detail: string } =>
      stream ? { status: stream.status, detail: stream.detail } : { status: 'off', detail: '' };
    return {
      configured: Boolean(this.credentials), keyHint: this.credentials ? maskKey(this.credentials.keyId) : null,
      feed: this.settings.feed, watchlist: this.settings.watchlist, quotes: [...this.quotes.values()],
      stream: status(this.stockStream), cryptoStream: status(this.cryptoStream), clock: this.clock,
      macro: this.macro, macroUpdated: this.macroUpdated, lastError: this.lastError, lastPoll: this.lastPoll,
      assetsKnown: this.assets.size, demo: this.demo,
    };
  }

  /** Coalesces bursts of ticks into at most four window updates per second. */
  private publish() {
    if (this.publishTimer) return;
    this.publishTimer = setTimeout(() => { this.publishTimer = null; this.onChange(); }, 250);
  }

  async start() {
    this.running = true;
    this.startStreams();
    void this.poll();
    void this.refreshMacro();
    if (this.credentials && this.assets.size === 0) void this.refreshAssets();
  }

  stop() {
    this.running = false;
    this.stockStream?.stop(); this.cryptoStream?.stop();
    this.stockStream = null; this.cryptoStream = null;
    for (const timer of [this.pollTimer, this.macroTimer, this.publishTimer]) if (timer) clearTimeout(timer);
    this.pollTimer = this.macroTimer = this.publishTimer = null;
  }

  private startStreams() {
    this.stockStream?.stop(); this.cryptoStream?.stop();
    this.stockStream = this.cryptoStream = null;
    if (!this.running || !this.credentials) return;
    const stocks = this.settings.watchlist.filter(s => !isCrypto(s)).slice(0, MAX_STREAM_SYMBOLS);
    const crypto = this.settings.watchlist.filter(isCrypto).slice(0, MAX_STREAM_SYMBOLS);
    const onStatus = () => this.publish();
    const onData = (messages: StreamMessage[]) => this.applyStream(messages);
    if (stocks.length) {
      this.stockStream = new MarketStream(`${STREAM_HOST}/v2/${this.settings.feed}`, this.credentials, this.socketFactory, onData, onStatus);
      this.stockStream.start(stocks);
    }
    if (crypto.length) {
      this.cryptoStream = new MarketStream(`${STREAM_HOST}/v1beta3/crypto/us`, this.credentials, this.socketFactory, onData, onStatus);
      this.cryptoStream.start(crypto);
    }
  }

  applyStream(messages: StreamMessage[]) {
    for (const m of messages) {
      const row = m.S ? this.quotes.get(m.S) : undefined;
      if (!row) continue;
      if (m.T === 't' && typeof m.p === 'number') this.setLast(row, m.p, String(m.t));
      else if (m.T === 'q') {
        row.bid = Number(m.bp) || null; row.ask = Number(m.ap) || null;
        row.bidSize = Number(m.bs) || null; row.askSize = Number(m.as) || null;
      } else if (m.T === 'd' || m.T === 'b' || m.T === 'u') {
        const bar: Bar = { t: String(m.t), o: Number(m.o), h: Number(m.h), l: Number(m.l), c: Number(m.c), v: Number(m.v) };
        if (m.T === 'd') { row.open = bar.o; row.high = bar.h; row.low = bar.l; row.volume = bar.v; }
        else this.liveBars.set(row.symbol, bar);
        if (row.last === null) this.setLast(row, bar.c, bar.t);
      }
    }
    this.publish();
  }

  private setLast(row: QuoteRow, price: number, time: string) {
    if (!Number.isFinite(price) || price <= 0) return;
    row.direction = row.last === null || price === row.last ? row.direction : price > row.last ? 1 : -1;
    row.last = price; row.time = time; row.tick++;
    if (row.prevClose) { row.change = price - row.prevClose; row.changePct = row.change / row.prevClose; }
  }

  applySnapshot(symbol: string, snap: Snapshot) {
    const row = this.quotes.get(symbol);
    if (!row) return;
    const daily = snap.dailyBar, prev = snap.prevDailyBar;
    if (prev?.c) row.prevClose = prev.c;
    if (daily) { row.open = daily.o; row.high = daily.h; row.low = daily.l; row.volume = daily.v; }
    if (snap.latestQuote) {
      row.bid = snap.latestQuote.bp || null; row.ask = snap.latestQuote.ap || null;
      row.bidSize = snap.latestQuote.bs || null; row.askSize = snap.latestQuote.as || null;
    }
    const trade = snap.latestTrade;
    if (trade && (!row.time || Date.parse(trade.t) >= Date.parse(row.time))) this.setLast(row, trade.p, trade.t);
    else if (row.last !== null && row.prevClose) { row.change = row.last - row.prevClose; row.changePct = row.change / row.prevClose; }
  }

  /** Snapshots keep daily change and volume right, and stand in for the stream when it is unavailable. */
  async poll() {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    if (!this.running) return;
    const symbols = this.settings.watchlist.filter(s => this.credentials || isCrypto(s));
    try {
      if (symbols.length) {
        const snaps = await this.client.snapshots(symbols, this.settings.feed);
        for (const [symbol, snap] of Object.entries(snaps)) this.applySnapshot(symbol, snap);
      }
      if (this.credentials) this.clock = await this.client.clock().catch(() => this.clock);
      this.lastPoll = new Date(this.now()).toISOString();
      this.lastError = null;
    } catch (error) { this.lastError = (error as Error).message; }
    this.publish();
    const live = this.stockStream?.status === 'live';
    if (this.running) this.pollTimer = setTimeout(() => void this.poll(), live ? 60_000 : 15_000);
  }

  async refreshMacro() {
    if (this.macroTimer) clearTimeout(this.macroTimer);
    try { this.macro = await fetchMacro(this.fetcher); this.macroUpdated = new Date(this.now()).toISOString(); }
    catch (error) { this.lastError = `Macro data: ${(error as Error).message}`; }
    this.publish();
    if (this.running) this.macroTimer = setTimeout(() => void this.refreshMacro(), 3_600_000);
  }

  async refreshAssets() {
    try {
      const assets = await this.client.assets();
      this.assets = new Map(assets.filter(a => validSymbol(a.symbol)).map(a => [a.symbol, { symbol: a.symbol, name: a.name,
        exchange: a.exchange, class: a.class, status: a.status }]));
      await mkdir(this.folder, { recursive: true });
      await writeFile(this.assetsFile, JSON.stringify({ saved: new Date(this.now()).toISOString(), assets: [...this.assets.values()] }));
      for (const row of this.quotes.values()) row.name = this.assets.get(row.symbol)?.name ?? row.name;
      this.publish();
    } catch { /* Names are a convenience; quotes work without them. */ }
  }

  search(text: string, limit = 12) {
    const query = text.trim().toUpperCase();
    if (!query) return [];
    const exact: Asset[] = [], prefix: Asset[] = [], named: Asset[] = [];
    for (const asset of this.assets.values()) {
      if (asset.symbol === query) exact.push(asset);
      else if (asset.symbol.startsWith(query)) prefix.push(asset);
      else if (query.length >= 3 && asset.name.toUpperCase().includes(query)) named.push(asset);
      if (prefix.length + named.length > 200) break;
    }
    prefix.sort((a, b) => a.symbol.length - b.symbol.length || a.symbol.localeCompare(b.symbol));
    return [...exact, ...prefix, ...named].slice(0, limit).map(a => ({ symbol: a.symbol, name: a.name, exchange: a.exchange }));
  }

  async setCredentials(value: unknown, feed: unknown) {
    const credentials = validateCredentials(value);
    const chosen: Feed = ['iex', 'sip', 'delayed_sip'].includes(feed as string) ? feed as Feed : 'iex';
    const trial = new AlpacaClient(credentials, this.fetcher);
    await trial.test(chosen);  // Never store keys Alpaca does not accept.
    await this.secrets.save(credentials);
    this.credentials = credentials;
    this.client.setCredentials(credentials);
    this.settings.feed = chosen;
    await this.saveSettings();
    this.lastError = null;
    if (this.running) { this.startStreams(); void this.poll(); void this.refreshAssets(); }
    this.publish();
  }

  useDemo(credentials: Credentials) {
    this.demo = true;
    this.credentials = credentials;
    this.client.setCredentials(credentials);
  }

  async clearCredentials() {
    await this.secrets.clear();
    this.credentials = null;
    this.client.setCredentials(null);
    this.stockStream?.stop(); this.cryptoStream?.stop();
    this.stockStream = this.cryptoStream = null;
    this.publish();
  }

  async setWatchlist(value: unknown) {
    this.settings.watchlist = validateWatchlist(value);
    await this.saveSettings();
    this.resetRows();
    if (this.running && this.credentials) {
      const stocks = this.settings.watchlist.filter(s => !isCrypto(s)), crypto = this.settings.watchlist.filter(isCrypto);
      if ((stocks.length > 0) !== Boolean(this.stockStream) || (crypto.length > 0) !== Boolean(this.cryptoStream)) this.startStreams();
      else { this.stockStream?.setSymbols(stocks); this.cryptoStream?.setSymbols(crypto); }
    }
    void this.poll();
    this.publish();
  }

  async chart(symbol: unknown, range: unknown) {
    if (!validSymbol(symbol)) throw new Error('Choose a valid symbol.');
    const spec = RANGES[String(range)] ?? RANGES['6M'];
    const start = new Date(this.now() - spec.days * 86_400_000).toISOString();
    const feed: Feed = spec.intraday && this.settings.feed !== 'sip' ? 'iex' : 'sip';
    let bars = await this.client.bars(symbol, spec.timeframe, start, { feed });
    if (range === '1D' && bars.length) {
      // Show the latest session only (New York date of the last bar).
      const day = (t: string) => new Date(t).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
      const last = day(bars[bars.length - 1].t);
      bars = bars.filter(bar => day(bar.t) === last);
    }
    return { symbol, range: RANGES[String(range)] ? range : '6M', timeframe: spec.timeframe, feed: isCrypto(symbol) ? 'crypto' : feed, bars };
  }

  /** Description page: name, latest snapshot, 52-week range and realised volatility from daily bars. */
  async describe(symbol: unknown) {
    if (!validSymbol(symbol)) throw new Error('Choose a valid symbol.');
    const [snaps, bars] = await Promise.all([
      this.client.snapshots([symbol], this.settings.feed),
      this.client.bars(symbol, '1Day', new Date(this.now() - 370 * 86_400_000).toISOString(), { feed: 'sip' }),
    ]);
    const closes = bars.map(bar => bar.c);
    const yearHigh = bars.length ? Math.max(...bars.map(b => b.h)) : null;
    const yearLow = bars.length ? Math.min(...bars.map(b => b.l)) : null;
    const yearReturn = closes.length > 1 ? closes[closes.length - 1] / closes[0] - 1 : null;
    const averageVolume = bars.length ? bars.slice(-30).reduce((a, b) => a + b.v, 0) / Math.min(30, bars.length) : null;
    return { symbol, asset: this.assets.get(symbol) ?? null, snapshot: snaps[symbol] ?? null, yearHigh, yearLow, yearReturn,
      averageVolume, vol20: realisedVol(closes, 20), vol60: realisedVol(closes, 60), vol252: closes.length > 21 ? realisedVol(closes, Math.min(250, closes.length - 1)) : null,
      bars: bars.length };
  }

  async news(symbol: unknown) {
    const symbols = symbol === undefined || symbol === null || symbol === '' ? [] : validSymbol(symbol) ? [symbol] : null;
    if (!symbols) throw new Error('Choose a valid symbol.');
    const items = await this.client.news(symbols.map(s => s.replace('/', '')), 40);
    return items.map(item => ({ id: item.id, headline: item.headline, summary: item.summary, source: item.source, author: item.author,
      created_at: item.created_at, url: /^https:\/\//.test(item.url) ? item.url : null, symbols: item.symbols.slice(0, 8) }));
  }

  async movers() {
    const [actives, movers] = await Promise.allSettled([this.client.mostActives(20), this.client.movers(10)]);
    return {
      actives: actives.status === 'fulfilled' ? actives.value.most_actives : [],
      gainers: movers.status === 'fulfilled' ? movers.value.gainers : [],
      losers: movers.status === 'fulfilled' ? movers.value.losers : [],
      error: [actives, movers].find((r): r is PromiseRejectedResult => r.status === 'rejected')?.reason?.message ?? null,
    };
  }

  /** Option chain points for the next ~year: strike, expiry, mid price and Alpaca's implied volatility. */
  async optionChain(symbol: unknown) {
    if (typeof symbol !== 'string' || isCrypto(symbol) || !validSymbol(symbol)) throw new Error('Options are available for US stocks and ETFs.');
    const snaps = await this.client.snapshots([symbol], this.settings.feed);
    const spot = snaps[symbol]?.latestTrade?.p ?? snaps[symbol]?.dailyBar?.c;
    if (!spot) throw new Error(`No current price for ${symbol}.`);
    const today = new Date(this.now());
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    const chain = await this.client.optionChain(symbol, { from: iso(new Date(today.getTime() + 86_400_000)),
      to: iso(new Date(today.getTime() + 400 * 86_400_000)), strikeLow: +(spot * 0.6).toFixed(2), strikeHigh: +(spot * 1.4).toFixed(2) });
    const points = [];
    for (const [occ, snap] of Object.entries(chain)) {
      const contract = parseOcc(occ);
      if (!contract) continue;
      const bid = snap.latestQuote?.bp ?? 0, ask = snap.latestQuote?.ap ?? 0;
      points.push({ symbol: occ, ...contract, bid, ask, mid: bid > 0 && ask > 0 ? (bid + ask) / 2 : null,
        last: snap.latestTrade?.p ?? null, iv: snap.impliedVolatility ?? null, delta: snap.greeks?.delta ?? null });
    }
    if (!points.length) throw new Error(`Alpaca returned no option contracts for ${symbol}.`);
    return { symbol, spot, asOf: new Date(this.now()).toISOString(), points, feed: 'indicative' };
  }

  /** Daily adjusted closes for several symbols on common dates, for a research dataset. */
  async dailyCloses(symbols: string[], years: number) {
    const start = new Date(this.now() - years * 365.25 * 86_400_000).toISOString().slice(0, 10);
    const series = await Promise.all(symbols.map(async symbol => {
      const bars = await this.client.bars(symbol, '1Day', start, { feed: 'sip' });
      if (bars.length < 40) throw new Error(`${symbol} has only ${bars.length} daily bars.`);
      // Crypto trades every day; dates are taken in New York time so stock and crypto rows line up.
      return new Map(bars.map(bar => [new Date(bar.t).toLocaleDateString('en-CA', { timeZone: 'America/New_York' }), bar.c]));
    }));
    const dates = [...series[0].keys()].filter(date => series.every(map => map.has(date))).sort();
    if (dates.length < 40) throw new Error('These symbols share fewer than 40 trading days.');
    return { dates, closes: dates.map(date => series.map(map => map.get(date)!)) };
  }
}

export { AlpacaError };
