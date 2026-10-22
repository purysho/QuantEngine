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
  /** After each US close: refresh, record equity, check the rule (never submits) and show a notification. */
  dailyUpdate: boolean; notify: boolean }
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
    dailyUpdate: v.dailyUpdate !== false, notify: v.notify !== false, limits: {
    maxOrderFraction: num(l.maxOrderFraction, 0.01, 1.5, 'Maximum order (share of equity)'),
    maxOrdersPerDay: num(l.maxOrdersPerDay, 1, 200, 'Maximum orders per day'),
    dailyLossStop: num(l.dailyLossStop, 0.005, 0.5, 'Daily loss stop'),
    minOrderNotional: num(l.minOrderNotional, 1, 10_000, 'Minimum order size'),
    maxGrossExposure: num(l.maxGrossExposure ?? 1.0, 1.0, 1.5, 'Maximum total exposure') } };
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
  /** One equity point per New York date (the latest reading wins). */
  async recordEquity(date: string, equity: number, cash: number) {
    const points = await this.equity();
    const next = [...points.filter(p => p.date !== date), { date, equity, cash }].sort((a, b) => a.date.localeCompare(b.date));
    await mkdir(this.folder, { recursive: true });
    const temporary = this.equityFile + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, next.map(p => JSON.stringify(p)).join('\n') + '\n'); await rename(temporary, this.equityFile); }
    finally { await unlink(temporary).catch(() => {}); }
  }
  async equity(): Promise<Array<{ date: string; equity: number; cash: number }>> {
    try { return (await readFile(this.equityFile, 'utf8')).trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { return []; }
  }
}

/** Stage 3 checklist from the journal and equity history versus the simulated strategy. */
export function stageThree(equity: Array<{ date: string; equity: number }>, simulated: Record<string, number>,
                           journal: Array<Record<string, unknown>>) {
  const paired: Array<[number, number]> = [];
  for (let i = 1; i < equity.length; i++) {
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
