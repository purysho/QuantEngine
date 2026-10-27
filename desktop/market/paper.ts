// Stage 3 paper trading. The only trading host this code can reach is Alpaca's PAPER host, so
// real money is structurally impossible: live-account keys are rejected there, and the live host is
// not in the allowlist. Every order needs the user's approval, passes risk limits first, and is journaled.
import { appendFile, mkdir, readFile, writeFile, rename, unlink } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import type { Credentials } from './alpaca.js';

export const PAPER_HOST = 'https://paper-api.alpaca.markets';
const PATHS: Array<[string, RegExp]> = [
  ['GET', /^\/v2\/account$/], ['GET', /^\/v2\/account\/portfolio\/history$/], ['GET', /^\/v2\/calendar$/], ['GET', /^\/v2\/positions$/], ['GET', /^\/v2\/orders$/], ['GET', /^\/v2\/clock$/],
  ['POST', /^\/v2\/orders$/], ['DELETE', /^\/v2\/orders$/],
];

export type PaperFetch = (url: string, init: { method: string; headers: Record<string, string>; body?: string; signal?: AbortSignal }) => Promise<{
  status: number; ok: boolean; text(): Promise<string>;
}>;
export interface Account { equity: string; last_equity: string; cash: string; buying_power: string; status: string; currency: string;
  trading_blocked: boolean; account_blocked: boolean; pattern_day_trader?: boolean }
export interface Position { symbol: string; qty: string; market_value: string; current_price: string; avg_entry_price: string; unrealized_pl: string }
export interface Order { id: string; client_order_id: string; symbol: string; side: string; qty: string | null; status: string;
  filled_qty: string; filled_avg_price: string | null; submitted_at: string; filled_at: string | null }
/** maxOrderFraction caps one order as a share of equity: it catches sizing bugs (a wrong unit or price) without blocking normal rebalancing. */
export interface RiskLimits { maxOrderFraction: number; maxOrdersPerDay: number; dailyLossStop: number; minOrderNotional: number;
  /** Total positions as a share of equity. 1.0 = no borrowing (default); up to 1.5 only if you opt in to margin. */
  maxGrossExposure: number }
export type Strategy = 'trend' | 'sectors' | 'quality' | 'ensemble';
export interface PaperSettings { enabled: boolean; strategy: Strategy; limits: RiskLimits; killSwitch: boolean;
  /** Once a day at dailyTime in dailyZone: refresh, record equity, check the rule (never submits) and notify. */
  dailyUpdate: boolean; notify: boolean; dailyTime: string; dailyZone: string }

/** Time zones offered for the daily update (the first is the default). */
export const DAILY_ZONES: Record<string, string> = { 'Asia/Shanghai': 'Beijing time', 'America/New_York': 'New York time',
  'Europe/London': 'London time', 'Europe/Berlin': 'Central European time', 'Asia/Tokyo': 'Tokyo time', 'Australia/Sydney': 'Sydney time' };
export interface ProposedOrder { symbol: string; side: 'buy' | 'sell'; qty: number; price: number; notional: number; reason: string }
export interface Proposal { id: string; created: string; strategy: string; asOf: string; equity: number; targets: Record<string, number>;
  orders: ProposedOrder[]; blocked: string[] }

const SECTOR_ETFS = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'XLRE', 'XLC'];
/** Same order as PAPER_UNIVERSE in workers/quant_strategies.py; SPY is always first. */
export const UNIVERSE: Record<Strategy, string[]> = {
  trend: ['SPY'],
  sectors: ['SPY', ...SECTOR_ETFS],
  quality: ['SPY', 'QUAL'],
  ensemble: ['SPY', ...SECTOR_ETFS, 'QUAL', 'IEF'],
};
export const DEFAULT_SETTINGS: PaperSettings = { enabled: false, strategy: 'trend', killSwitch: false, dailyUpdate: true, notify: true,
  dailyTime: '06:00', dailyZone: 'Asia/Shanghai',
  limits: { maxOrderFraction: 1.0, maxOrdersPerDay: 24, dailyLossStop: 0.03, minOrderNotional: 50, maxGrossExposure: 1.0 } };

export function validateSettings(value: unknown): PaperSettings {
  const v = (value ?? {}) as Partial<PaperSettings>;
  const l = (v.limits ?? {}) as Partial<RiskLimits>;
  const num = (x: unknown, lo: number, hi: number, name: string) => {
    if (typeof x !== 'number' || !Number.isFinite(x) || x < lo || x > hi) throw new Error(`${name} must be between ${lo} and ${hi}.`);
    return x;
  };
  if (!['trend', 'sectors', 'quality', 'ensemble'].includes(v.strategy as string)) throw new Error('Choose one of the registered strategies.');
  return { enabled: v.enabled === true, strategy: v.strategy as Strategy, killSwitch: v.killSwitch === true,
    dailyUpdate: v.dailyUpdate !== false, notify: v.notify !== false,
    // Settings saved before 0.3.2 have no time: they get the default (06:00 Beijing time).
    dailyTime: v.dailyTime === undefined ? DEFAULT_SETTINGS.dailyTime : validTime(v.dailyTime),
    dailyZone: v.dailyZone === undefined ? DEFAULT_SETTINGS.dailyZone : validZone(v.dailyZone), limits: {
    maxOrderFraction: num(l.maxOrderFraction, 0.01, 1.5, 'Maximum order (share of equity)'),
    maxOrdersPerDay: num(l.maxOrdersPerDay, 1, 200, 'Maximum orders per day'),
    dailyLossStop: num(l.dailyLossStop, 0.005, 0.5, 'Daily loss stop'),
    minOrderNotional: num(l.minOrderNotional, 1, 10_000, 'Minimum order size'),
    maxGrossExposure: num(l.maxGrossExposure ?? 1.0, 1.0, 1.5, 'Maximum total exposure') } };
}

function validTime(x: unknown): string {
  if (typeof x !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(x)) throw new Error('Daily update time must be HH:MM (24-hour).');
  return x;
}
function validZone(x: unknown): string {
  if (typeof x !== 'string' || !(x in DAILY_ZONES)) throw new Error('Choose one of the listed time zones for the daily update.');
  return x;
}

/**
 * The scheduled daily update. Each day's slot is the chosen time in the chosen zone; ``key`` names the most recent
 * slot that has passed, so it runs once per slot, including later if the app was closed or asleep at that time.
 * Never while the US market is open, when daily bars are still forming: it then waits for 4:20 p.m. New York time.
 */
export function dailySchedule(now: Date, time: string, zone: string): { key: string; due: boolean; waitingForClose: boolean } {
  const parts = (timeZone: string) => Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', weekday: 'short', hourCycle: 'h23' }).formatToParts(now).map(p => [p.type, p.value]));
  const local = parts(zone), ny = parts('America/New_York');
  const today = `${local.year}-${local.month}-${local.day}`;
  const [h, m] = time.split(':').map(Number);
  const reached = Number(local.hour) * 60 + Number(local.minute) >= h * 60 + m;
  const key = reached ? today : new Date(Date.parse(today + 'T12:00:00Z') - 86_400_000).toISOString().slice(0, 10);
  const nyMinutes = Number(ny.hour) * 60 + Number(ny.minute);
  const session = !['Sat', 'Sun'].includes(ny.weekday) && nyMinutes >= 9 * 60 + 30 && nyMinutes < 16 * 60 + 20;
  return { key, due: !session, waitingForClose: session };
}

/** Orders that move current positions to the target weights: whole shares, sells before buys, no shorts, no leverage. */
export function planOrders(targets: Record<string, number>, positions: Position[], prices: Record<string, number>, equity: number,
                           universe: string[], minNotional: number, maxGross = 1.0): { orders: ProposedOrder[]; blocked: string[] } {
  const blocked: string[] = [];
  const weightSum = Object.values(targets).reduce((a, b) => a + b, 0);
  if (Object.values(targets).some(w => !(w >= 0))) throw new Error('Targets must be long-only.');
  // A rule may ask for more than 100% (the ensemble, up to 150%); without margin opted in it is scaled down to 100%.
  if (weightSum > 1.5 + 1e-9) throw new Error('Targets must sum to at most 150%.');
  const scale = weightSum > maxGross ? maxGross / weightSum : 1;
  targets = Object.fromEntries(Object.entries(targets).map(([s, w]) => [s, w * scale]));
  const held = new Map(positions.map(p => [p.symbol, Number(p.qty)]));
  const orders: ProposedOrder[] = [];
  for (const symbol of new Set([...universe, ...held.keys()])) {
    const price = prices[symbol];
    const have = held.get(symbol) ?? 0;
    const want = universe.includes(symbol) ? targets[symbol] ?? 0 : 0;
    if (!universe.includes(symbol) && have !== 0) { blocked.push(`${symbol}: held outside the strategy universe; left unchanged`); continue; }
    if (!(price > 0)) { if (want > 0 || have !== 0) blocked.push(`${symbol}: no current price`); continue; }
    const wantQty = Math.floor((equity * want) / price);
    const delta = wantQty - have;
    if (delta === 0 || Math.abs(delta) * price < minNotional) continue;
    orders.push({ symbol, side: delta > 0 ? 'buy' : 'sell', qty: Math.abs(delta), price, notional: Math.abs(delta) * price,
      reason: `target ${(want * 100).toFixed(1)}% → ${wantQty} shares (now ${have})` });
  }
  orders.sort((a, b) => (a.side === b.side ? a.symbol.localeCompare(b.symbol) : a.side === 'sell' ? -1 : 1));
  return { orders, blocked };
}

/** Risk checks applied immediately before submission; any failure blocks the whole batch. */
export function riskCheck(proposal: Proposal, settings: PaperSettings, account: Account, ordersToday: number, now = Date.now()): string[] {
  const problems: string[] = [];
  if (!settings.enabled) problems.push('Paper trading is turned off in the Strategies page.');
  if (settings.killSwitch) problems.push('The kill switch is on.');
  if (account.trading_blocked || account.account_blocked) problems.push('Alpaca reports the paper account as blocked.');
  if (now - Date.parse(proposal.created) > 30 * 60_000) problems.push('The order list is over 30 minutes old; compute it again.');
  const equity = Number(account.equity), last = Number(account.last_equity);
  if (last > 0 && equity < last * (1 - settings.limits.dailyLossStop) && proposal.orders.some(o => o.side === 'buy')) {
    problems.push(`Daily loss stop: equity is down ${((1 - equity / last) * 100).toFixed(1)}% today, so new buys are blocked.`);
  }
  if (ordersToday + proposal.orders.length > settings.limits.maxOrdersPerDay) problems.push('This would exceed the maximum orders per day.');
  for (const o of proposal.orders) {
    if (o.notional > settings.limits.maxOrderFraction * equity) problems.push(`${o.symbol}: $${o.notional.toFixed(0)} is over ${(settings.limits.maxOrderFraction * 100).toFixed(0)}% of equity, the maximum order size.`);
    if (!UNIVERSE[settings.strategy].includes(o.symbol)) problems.push(`${o.symbol} is outside the strategy universe.`);
  }
  const buys = proposal.orders.filter(o => o.side === 'buy').reduce((a, o) => a + o.notional, 0);
  const borrowing = Math.max(0, settings.limits.maxGrossExposure - 1) * equity;
  if (buys > Number(account.cash) + proposal.orders.filter(o => o.side === 'sell').reduce((a, o) => a + o.notional, 0) + borrowing + 1) {
    problems.push(settings.limits.maxGrossExposure > 1 ? `Buys would exceed cash, sale proceeds and the ${((settings.limits.maxGrossExposure - 1) * 100).toFixed(0)}% borrowing allowance.`
      : 'Buys would exceed cash plus sale proceeds (no leverage).');
  }
  return problems;
}

export class PaperBroker {
  constructor(private credentials: () => Credentials | null, readonly fetcher: PaperFetch) {}

  private async call<T>(method: 'GET' | 'POST' | 'DELETE', pathname: string, query: Record<string, string> = {}, body?: unknown): Promise<T> {
    if (!PATHS.some(([m, p]) => m === method && p.test(pathname))) throw new Error(`Blocked paper request: ${method} ${pathname}`);
    const credentials = this.credentials();
    if (!credentials) throw new Error('Add Alpaca paper-trading keys in Preferences first.');
    const params = new URLSearchParams(query);
    const response = await this.fetcher(PAPER_HOST + pathname + (params.size ? '?' + params : ''), {
      method, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20_000),
      headers: { 'APCA-API-KEY-ID': credentials.keyId, 'APCA-API-SECRET-KEY': credentials.secret, Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) } });
    const text = await response.text();
    if (response.status === 401 || response.status === 403 && pathname === '/v2/account') {
      throw new Error('Alpaca\'s paper host rejected these keys. Paper trading needs keys from the paper-trading dashboard (live-account keys never work here).');
    }
    if (!response.ok && response.status !== 207) {
      let message = '';
      try { message = (JSON.parse(text) as { message?: string }).message ?? ''; } catch { /* HTML error page */ }
      throw new Error(`Alpaca paper API ${response.status}${message ? ': ' + message.slice(0, 200) : ''}`);
    }
    return (text ? JSON.parse(text) : null) as T;
  }

  account() { return this.call<Account>('GET', '/v2/account'); }
  positions() { return this.call<Position[]>('GET', '/v2/positions'); }
  orders(after?: string) { return this.call<Order[]>('GET', '/v2/orders', { status: 'all', limit: '100', direction: 'desc', ...(after ? { after } : {}) }); }
  cancelAll() { return this.call<unknown>('DELETE', '/v2/orders'); }
  /** Daily equity history kept by Alpaca, so days when this laptop was off are not lost. */
  portfolioHistory(period = '3M') {
    return this.call<{ timestamp: number[]; equity: Array<number | null> }>('GET', '/v2/account/portfolio/history', { period, timeframe: '1D' });
  }
  calendar(start: string, end: string) { return this.call<Array<{ date: string; open: string; close: string }>>('GET', '/v2/calendar', { start, end }); }
  /** Market order for whole shares, valid for the day. client_order_id makes a retry of the same proposal idempotent. */
  submit(order: ProposedOrder, proposalId: string) {
    return this.call<Order>('POST', '/v2/orders', {}, { symbol: order.symbol, qty: String(order.qty), side: order.side, type: 'market',
      time_in_force: 'day', client_order_id: `qe-${proposalId}-${order.symbol}`.slice(0, 48) });
  }
}

/** Append-only journal (JSON lines) of every proposal, decision, order, reconciliation and kill-switch change. */
export class Journal {
  constructor(readonly folder: string) {}
  get file() { return path.join(this.folder, 'journal.jsonl'); }
  get equityFile() { return path.join(this.folder, 'equity.jsonl'); }
  async write(entry: Record<string, unknown>) {
    await mkdir(this.folder, { recursive: true });
    await appendFile(this.file, JSON.stringify({ at: new Date().toISOString(), ...entry }) + '\n', 'utf8');
  }
  async read(limit = 200): Promise<Array<Record<string, unknown>>> {
    try {
      const lines = (await readFile(this.file, 'utf8')).trim().split('\n').filter(Boolean);
      return lines.slice(-limit).map(line => JSON.parse(line));
    } catch { return []; }
  }
  get replacedFile() { return path.join(this.folder, 'equity-replaced.jsonl'); }
  /**
   * One equity point per trading day. A 'close' comes from Alpaca's own end-of-day history; a 'reading' is the
   * account value seen when the app refreshed. A reading never overwrites a close for the same day.
   */
  async recordEquity(date: string, equity: number, cash: number, source: EquitySource = 'reading') {
    const points = await this.equity();
    const existing = points.find(p => p.date === date);
    if (existing?.source === 'close' && source === 'reading') return;
    if (existing && existing.source !== source) await this.keepReplaced([existing], `replaced by a ${source}`);
    await this.writeEquity([...points.filter(p => p.date !== date), { date, equity, cash, source }]);
  }
  /**
   * Merges Alpaca's official daily closes: each replaces any reading for the same day, and readings dated on
   * days the market was shut (inside the calendar range given) are removed. Nothing is lost: every replaced or
   * removed entry is appended to equity-replaced.jsonl first.
   */
  async mergeCloses(closes: Array<{ date: string; equity: number }>, sessions: { first: string; last: string; dates: Set<string> }) {
    const byDate = new Map((await this.equity()).map(p => [p.date, p]));
    const replaced: EquityPoint[] = [], removed: EquityPoint[] = [];
    let added = 0;
    for (const close of closes) {
      if (!sessions.dates.has(close.date) || !(close.equity > 0)) continue;
      const existing = byDate.get(close.date);
      if (existing?.source === 'close' && existing.equity === close.equity) continue;
      if (existing) replaced.push(existing); else added++;
      byDate.set(close.date, { date: close.date, equity: close.equity, cash: existing?.cash ?? null, source: 'close' });
    }
    for (const [date, point] of byDate) {
      if (point.source !== 'close' && date >= sessions.first && date <= sessions.last && !sessions.dates.has(date)) { removed.push(point); byDate.delete(date); }
    }
    if (!added && !replaced.length && !removed.length) return { added, replaced: 0, removed: 0 };
    await this.keepReplaced(replaced, 'replaced by the official close');
    await this.keepReplaced(removed, 'dated on a day the market was closed');
    await this.writeEquity([...byDate.values()]);
    return { added, replaced: replaced.length, removed: removed.length };
  }
  private async keepReplaced(points: EquityPoint[], reason: string) {
    if (!points.length) return;
    await mkdir(this.folder, { recursive: true });
    const at = new Date().toISOString();
    await appendFile(this.replacedFile, points.map(p => JSON.stringify({ at, reason, ...p })).join('\n') + '\n', 'utf8');
  }
  private async writeEquity(points: EquityPoint[]) {
    const next = [...points].sort((a, b) => a.date.localeCompare(b.date));
    await mkdir(this.folder, { recursive: true });
    const temporary = this.equityFile + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, next.map(p => JSON.stringify(p)).join('\n') + '\n'); await rename(temporary, this.equityFile); }
    finally { await unlink(temporary).catch(() => {}); }
  }
  async equity(): Promise<EquityPoint[]> {
    try { return (await readFile(this.equityFile, 'utf8')).trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { return []; }
  }
}

export type EquitySource = 'close' | 'reading';
/** Entries written before 0.3.2 have no source; they are treated as readings. */
export interface EquityPoint { date: string; equity: number; cash: number | null; source?: EquitySource }

/**
 * The New York date the current strategy started trading: the first submitted batch after the last batch of a
 * different strategy. Stage 3 compares only the days after it, so switching strategy restarts the paper test.
 */
export function strategyStart(journal: Array<Record<string, unknown>>, strategy: string): string | null {
  const strategyOf = new Map<string, string>();
  let start: string | null = null;
  for (const entry of journal) {
    if (entry.type === 'proposal') strategyOf.set(String(entry.proposal), String(entry.strategy));
    if (entry.type !== 'submitted') continue;
    if (strategyOf.get(String(entry.proposal)) !== strategy) start = null;
    else if (!start) start = fillDate(new Date(String(entry.at)));
  }
  return start;
}

/** New York date on which an order sent at this moment fills: the same weekday before 4 p.m., otherwise the next weekday. */
export function fillDate(at: Date): string {
  const part = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', ...options }).format(at);
  let date = part({ year: 'numeric', month: '2-digit', day: '2-digit' });
  const hour = Number(part({ hour: '2-digit', hourCycle: 'h23' }));
  const weekday = () => new Date(date + 'T12:00:00Z').getUTCDay();
  const next = () => { date = new Date(Date.parse(date + 'T12:00:00Z') + 86_400_000).toISOString().slice(0, 10); };
  if (hour >= 16 && weekday() % 6) next();
  while (!(weekday() % 6)) next();
  return date;
}

/** Stage 3 checklist from the journal and equity history versus the simulated strategy. */
export function stageThree(equity: Array<{ date: string; equity: number }>, simulated: Record<string, number>,
                           journal: Array<Record<string, unknown>>, start: string | null = null) {
  const paired: Array<[number, number]> = [];
  for (let i = 1; i < equity.length; i++) {
    if (start && equity[i - 1].date < start) continue;  // Only whole days held by the current strategy (fills land mid-day on the start date).
    const sim = simulated[equity[i].date];
    if (sim !== undefined && equity[i - 1].equity > 0) paired.push([equity[i].equity / equity[i - 1].equity - 1, sim]);
  }
  const diffs = paired.map(([p, s]) => p - s);
  const mean = diffs.reduce((a, b) => a + b, 0) / Math.max(1, diffs.length);
  const te = diffs.length > 1 ? Math.sqrt(diffs.reduce((a, d) => a + (d - mean) ** 2, 0) / (diffs.length - 1) * 252) : null;
  const cum = (xs: number[]) => xs.reduce((a, r) => a * (1 + r), 1) - 1;
  const paperCum = cum(paired.map(p => p[0])), simCum = cum(paired.map(p => p[1]));
  const band = te !== null ? 2 * te * Math.sqrt(paired.length / 252) : null;
  const recent = journal.filter(e => Date.parse(String(e.at)) > Date.now() - 30 * 86_400_000);
  const killTested = journal.some(e => e.type === 'kill-switch' && e.on === true) && journal.some(e => e.type === 'kill-switch' && e.on === false);
  const checks = {
    days: { pass: paired.length >= 63, detail: `${paired.length} of 63 trading days compared` },
    tracking: { pass: te !== null && te <= 0.05, detail: te === null ? 'not enough days' : `tracking error ${(te * 100).toFixed(2)}% a year (limit 5%)` },
    within_band: { pass: band !== null && Math.abs(paperCum - simCum) <= band, detail: band === null ? 'not enough days' :
      `paper ${(paperCum * 100).toFixed(2)}% vs simulated ${(simCum * 100).toFixed(2)}% (band ±${(band * 100).toFixed(2)}%)` },
    reconciled: { pass: !recent.some(e => e.type === 'reconcile' && e.ok === false), detail: 'no unreconciled differences in the last 30 days' },
    kill_switch_tested: { pass: killTested, detail: killTested ? 'turned on and off at least once' : 'turn the kill switch on and off once to test it' },
  };
  return { checks, passed: Object.values(checks).every(c => c.pass), paperReturn: paperCum, simulatedReturn: simCum, trackingError: te, days: paired.length };
}

export const proposalId = (strategy: string, asOf: string) => createHash('sha256').update(strategy + asOf + Date.now()).digest('hex').slice(0, 12);
