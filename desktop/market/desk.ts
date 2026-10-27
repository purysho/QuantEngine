// Strategies desk: stage 2 lab results, stage 3 paper trading (proposal → approval → paper orders →
// reconciliation) and the go/no-go ladder. Real money is never reachable from here (see paper.ts).
import { readFile, writeFile, rename, unlink, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import type { JsonRecord } from '../transport.js';
import type { MarketService } from './service.js';
import { PaperBroker, Journal, planOrders, riskCheck, stageThree, strategyStart, validateSettings, proposalId, DEFAULT_SETTINGS, UNIVERSE,
  type Account, type Order, type PaperSettings, type Position, type Proposal } from './paper.js';

export interface DeskHost {
  notify(title: string, body: string): void;
  dataRoot(): string;
  runTask(stage: string, command: string, values: JsonRecord): Promise<JsonRecord>;
  stage(extension: 'csv' | 'json', content: string): Promise<string>;
  riskFreeAnnual(): number;
}

const nyDate = (at = new Date()) => at.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
/** 'YYYY-MM-DD HH:MM' in New York, comparable as text with the calendar's session times. */
const nyStamp = (at = new Date()) => {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(at).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
};
const shiftDate = (date: string, days: number) => new Date(Date.parse(date + 'T12:00:00Z') + days * 86_400_000).toISOString().slice(0, 10);

export type RefreshTrigger = 'manual' | 'scheduled' | 'startup' | 'automatic';

export class StrategyDesk {
  settings: PaperSettings = structuredClone(DEFAULT_SETTINGS);
  lab: JsonRecord | null = null;
  account: Account | null = null;
  positions: Position[] = [];
  orders: Order[] = [];
  proposal: Proposal | null = null;
  lastError: string | null = null;
  updated: string | null = null;
  simulated: Record<string, number> = {};
  journalTail: Array<Record<string, unknown>> = [];
  stage3: ReturnType<typeof stageThree> | null = null;
  brief: Record<string, unknown> | null = null;
  marketReturns: Record<string, number> = {};
  private backfilledOn: string | null = null;
  /** The last refresh: when, what started it, whether it worked and the equity it read (shown in the app). */
  lastRefresh: { at: string; trigger: RefreshTrigger; ok: boolean; equity: number | null; error: string | null } | null = null;
  onChange: () => void = () => {};

  constructor(readonly settingsFile: string, readonly broker: PaperBroker, readonly market: MarketService, readonly host: DeskHost) {}

  private get folder() { return path.join(this.host.dataRoot(), 'paper'); }
  private get journal() { return new Journal(this.folder); }

  async load() {
    try { this.settings = validateSettings(JSON.parse(await readFile(this.settingsFile, 'utf8'))); } catch { /* defaults */ }
    try { this.simulated = JSON.parse(await readFile(path.join(this.folder, 'simulated.json'), 'utf8')); } catch { this.simulated = {}; }
    try { this.marketReturns = JSON.parse(await readFile(path.join(this.folder, 'market.json'), 'utf8')); } catch { this.marketReturns = {}; }
    try { this.brief = JSON.parse(await readFile(path.join(this.folder, 'brief.json'), 'utf8')); } catch { this.brief = null; }
    this.journalTail = await this.journal.read(40);
  }

  private async saveSettings() {
    await mkdir(path.dirname(this.settingsFile), { recursive: true });
    const temporary = this.settingsFile + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, JSON.stringify(this.settings, null, 2)); await rename(temporary, this.settingsFile); }
    finally { await unlink(temporary).catch(() => {}); }
  }

  snapshot() {
    return { settings: this.settings, universe: UNIVERSE[this.settings.strategy], lab: this.lab, account: this.account,
      positions: this.positions, orders: this.orders.slice(0, 30), proposal: this.proposal, lastError: this.lastError,
      updated: this.updated, lastRefresh: this.lastRefresh, journal: this.journalTail.slice(-25).reverse(), stage3: this.stage3, brief: this.brief,
      ladder: this.ladder() };
  }

  /** The four-stage go/no-go ladder. Stage 4 (real money) is never automated by QuantEngine. */
  ladder() {
    const go = (this.lab?.go_to_paper ?? null) as Record<string, boolean> | null;
    const strategy = this.settings.strategy;
    return {
      stage1: { done: true, detail: 'Rules registered in code with a hash; reports carry it' },
      stage2: { done: go ? go[strategy] === true : false, detail: go ? (go[strategy] ? 'All backtest gates passed' : 'Backtest gates not passed') : 'Run the strategy lab' },
      stage3: { done: this.stage3?.passed ?? false, detail: this.stage3 ? `${Object.values(this.stage3.checks).filter(c => c.pass).length} of 5 paper checks passed` : 'No paper history yet' },
      stage4: { done: false, detail: 'Real money is your decision, outside QuantEngine. Only consider it after stages 2 and 3 pass, with a small amount you can afford to lose.' },
    };
  }

  /** Last lab results saved by the worker; read directly so start-up never occupies the worker slot. */
  async loadSavedLab() {
    try { this.lab = JSON.parse(await readFile(path.join(this.host.dataRoot(), 'strategies', 'lab.json'), 'utf8')) as JsonRecord; } catch { this.lab = null; }
  }

  async runLab() {
    this.lab = (await this.host.runTask('Running the strategy lab', 'strategy-lab', {})).lab as JsonRecord;
    await this.journal.write({ type: 'lab', go_to_paper: this.lab.go_to_paper, registration: (this.lab.registration as JsonRecord)?.hash });
    this.onChange();
  }

  async configure(value: unknown) {
    const next = validateSettings(value);
    const previous = this.settings;
    const enabling = next.enabled && !previous.enabled;
    const killChanged = next.killSwitch !== previous.killSwitch;
    this.settings = next;
    await this.saveSettings();
    if (enabling) await this.journal.write({ type: 'enabled', strategy: next.strategy });
    if (!next.enabled && previous.enabled) await this.journal.write({ type: 'disabled', strategy: next.strategy });
    // Every change of strategy or risk limit is journaled, so the history shows what was traded under which rules.
    if (next.strategy !== previous.strategy) await this.journal.write({ type: 'strategy', from: previous.strategy, to: next.strategy });
    if (JSON.stringify(next.limits) !== JSON.stringify(previous.limits)) await this.journal.write({ type: 'limits', from: previous.limits, to: next.limits });
    if (next.strategy !== previous.strategy) this.proposal = null;
    if (killChanged) await this.kill(next.killSwitch, false);
    this.journalTail = await this.journal.read(40);
    this.onChange();
  }

  async kill(on: boolean, save = true) {
    this.settings.killSwitch = on;
    if (save) await this.saveSettings();
    let cancelled: unknown = null;
    if (on && this.market.credentials) { try { cancelled = await this.broker.cancelAll(); } catch (error) { this.lastError = (error as Error).message; } }
    this.proposal = null;
    await this.journal.write({ type: 'kill-switch', on, cancelled_open_orders: Array.isArray(cancelled) ? cancelled.length : null });
    this.journalTail = await this.journal.read(40);
    await this.refresh().catch(() => {});
    this.onChange();
  }

  /**
   * Account, positions and orders from the paper account; reconciliation; and one equity reading dated by the
   * last completed trading day (none while the market is open, when the value is mid-day). Once a day, Alpaca's
   * official closes replace the readings.
   */
  async refresh(trigger: RefreshTrigger = 'automatic') {
    try {
      const [account, positions, orders] = await Promise.all([this.broker.account(), this.broker.positions(), this.broker.orders()]);
      this.account = account; this.positions = positions; this.orders = orders;
      const session = await this.sessionNow().catch(() => null);
      if (session && !session.open && session.last) await this.journal.recordEquity(session.last, Number(account.equity), Number(account.cash));
      await this.reconcile();
      if (this.backfilledOn !== nyDate() && await this.backfill().then(() => true, () => false)) this.backfilledOn = nyDate();
      this.lastError = null;
    } catch (error) { this.lastError = (error as Error).message; }
    this.updated = new Date().toISOString();
    this.lastRefresh = { at: this.updated, trigger, ok: !this.lastError, equity: this.account && !this.lastError ? Number(this.account.equity) : null,
      error: this.lastError };
    this.journalTail = await this.journal.read(40);
    this.stage3 = await this.stageThreeNow();
    this.onChange();
  }

  private async stageThreeNow() {
    const journal = await this.journal.read(1e9);
    return stageThree(await this.journal.equity(), this.simulated, journal, strategyStart(journal, this.settings.strategy) ?? '9999-12-31');
  }

  /** Trading sessions of the last two weeks: the last completed one and whether the market is open now. */
  private async sessionNow() {
    const today = nyDate(), stamp = nyStamp();
    const days = await this.broker.calendar(shiftDate(today, -14), today);
    const done = days.filter(d => `${d.date} ${d.close}` <= stamp);
    const open = days.some(d => d.date === today && `${d.date} ${d.open}` <= stamp && stamp < `${d.date} ${d.close}`);
    return { last: done.at(-1)?.date ?? null, open };
  }

  /** After a submitted batch settles, every order must be filled and positions must equal the plan. */
  private async reconcile() {
    const entries = await this.journal.read(500);
    const submitted = [...entries].reverse().find(e => e.type === 'submitted') as { proposal: string; expected: Record<string, number> } | undefined;
    if (!submitted || entries.some(e => e.type === 'reconcile' && e.proposal === submitted.proposal)) return;
    const mine = this.orders.filter(o => o.client_order_id.startsWith(`qe-${submitted.proposal}-`));
    if (mine.some(o => ['new', 'accepted', 'pending_new', 'partially_filled', 'held'].includes(o.status))) return;  // Still working.
    const held = new Map(this.positions.map(p => [p.symbol, Number(p.qty)]));
    const differences = Object.entries(submitted.expected).filter(([symbol, qty]) => (held.get(symbol) ?? 0) !== qty)
      .map(([symbol, qty]) => ({ symbol, expected: qty, actual: held.get(symbol) ?? 0 }));
    const problems = mine.filter(o => o.status !== 'filled').map(o => ({ symbol: o.symbol, status: o.status }));
    await this.journal.write({ type: 'reconcile', proposal: submitted.proposal, ok: !differences.length && !problems.length, differences, problems });
  }

  /**
   * Alpaca's own end-of-day equity for the last three months: fills days this laptop missed and replaces
   * readings with official closes. Replaced readings are kept in equity-replaced.jsonl, never discarded.
   */
  async backfill() {
    const history = await this.broker.portfolioHistory('3M');
    const session = await this.sessionNow();
    if (!session.last || !history.timestamp.length) return 0;
    // Daily points are left-labelled (start of the day); +12 h lands mid-day whether that start is midnight in New York or UTC.
    const closes = history.timestamp.map((t, i) => ({ date: nyDate(new Date(t * 1000 + 12 * 3_600_000)), equity: history.equity[i] }))
      .filter((c): c is { date: string; equity: number } => typeof c.equity === 'number' && c.equity > 0 && c.date <= session.last!);
    if (!closes.length) return 0;
    const first = closes[0].date;
    const calendar = await this.broker.calendar(first, session.last);
    const merged = await this.journal.mergeCloses(closes, { first, last: session.last, dates: new Set(calendar.map(d => d.date)) });
    if (merged.replaced || merged.removed) await this.journal.write({ type: 'equity-closes', ...merged });
    return merged.added;
  }

  /** The last trading day of this month (or next month, if this month's has passed): when monthly rules rebalance. */
  async nextRebalance(): Promise<string | null> {
    const now = new Date(), today = nyDate(now);
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 2, 0)).toISOString().slice(0, 10);
    const days = (await this.broker.calendar(today, end)).map(d => d.date);
    const month = (d: string) => d.slice(0, 7);
    const last = days.filter((d, i) => i === days.length - 1 || month(days[i + 1]) !== month(d));
    return last.find(d => d >= today) ?? null;
  }

  /**
   * After each US close: refresh the account, fill missed days, check the rule (proposal only, never submitted)
   * and summarise the day. Called by the app's scheduler and by the "Update now" button.
   */
  async dailyUpdate(trigger: RefreshTrigger = 'manual'): Promise<Record<string, unknown>> {
    await this.refresh(trigger);
    if (!this.account || this.lastError) throw new Error(this.lastError || 'The paper account could not be read.');
    const session = (await this.sessionNow().catch(() => null))?.last ?? null;
    // A scheduled run with no new US close since the last summary (e.g. Sunday and Monday mornings in Asia)
    // only refreshes; it does not repeat the summary or the notification.
    if (trigger === 'scheduled' && session && this.brief?.session === session) return this.brief;
    const added = await this.backfill().catch(() => 0);
    let proposal: Proposal | null = null, signalError: string | null = null;
    try { proposal = await this.propose(); } catch (error) { signalError = (error as Error).message; }
    const equity = await this.journal.equity();
    const first = equity[0], last = equity.at(-1)!, previous = equity.at(-2);
    const cumulative = (series: Record<string, number>) => Object.entries(series).filter(([d]) => first && d > first.date)
      .reduce((a, [, r]) => a * (1 + r), 1) - 1;
    this.stage3 = await this.stageThreeNow();
    const nextRebalance = await this.nextRebalance().catch(() => null);
    this.brief = {
      date: nyDate(), session, trigger, updated: new Date().toISOString(), strategy: this.settings.strategy, equity: last.equity,
      day_change: previous ? last.equity / previous.equity - 1 : null, since: first?.date ?? null,
      since_start: first ? last.equity / first.equity - 1 : null, spy_since_start: first ? cumulative(this.marketReturns) : null,
      rule_since_start: first ? cumulative(this.simulated) : null, days: equity.length, orders_needed: proposal ? proposal.orders.length : null,
      next_rebalance: nextRebalance, signal_error: signalError, backfilled: added,
      stage3: this.stage3 ? `${Object.values(this.stage3.checks).filter(c => c.pass).length} of 5 checks` : null,
    };
    await mkdir(this.folder, { recursive: true });
    await writeFile(path.join(this.folder, 'brief.json'), JSON.stringify(this.brief));
    await this.journal.write({ type: 'daily-update', ...this.brief });
    this.journalTail = await this.journal.read(40);
    if (this.settings.notify) {
      const pct = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '—';
      this.host.notify(`QuantEngine paper · ${pct(this.brief.day_change)} today`,
        `Equity $${Math.round(last.equity).toLocaleString('en-US')} · since ${this.brief.since}: ${pct(this.brief.since_start)} (SPY ${pct(this.brief.spy_since_start)})` +
        (proposal?.orders.length ? ` · ${proposal.orders.length} orders proposed — review in Strategies` : ' · no orders needed'));
    }
    this.onChange();
    return this.brief;
  }

  /** Today's orders for the chosen strategy, from the traded ETFs' own daily closes. Nothing is sent. */
  async propose(): Promise<Proposal> {
    const strategy = this.settings.strategy;
    const universe = UNIVERSE[strategy];
    const { dates, closes } = await this.market.dailyCloses(universe, 3);
    const file = await this.host.stage('csv', 'date,' + universe.join(',') + '\n' + dates.map((d, i) => d + ',' + closes[i].join(',')).join('\n') + '\n');
    const equityHistory = await this.journal.equity();
    const since = strategyStart(await this.journal.read(1e9), strategy) ?? equityHistory[0]?.date ?? null;
    const signal = (await this.host.runTask('Computing today\'s strategy signal', 'strategy-signal', { path: file, family: strategy,
      rf_annual: this.host.riskFreeAnnual(), since })).signal as {
      targets: Record<string, number>; as_of: string; simulated: Record<string, number>; prices: Record<string, number>;
      market_returns: Record<string, number> };
    this.simulated = { ...this.simulated, ...signal.simulated };
    this.marketReturns = { ...this.marketReturns, ...signal.market_returns };
    await mkdir(this.folder, { recursive: true });
    await writeFile(path.join(this.folder, 'simulated.json'), JSON.stringify(this.simulated));
    await writeFile(path.join(this.folder, 'market.json'), JSON.stringify(this.marketReturns));
    const [account, positions, snaps] = await Promise.all([this.broker.account(), this.broker.positions(), this.market.client.snapshots(universe, this.market.settings.feed)]);
    this.account = account; this.positions = positions;
    const prices = Object.fromEntries(universe.map(s => [s, snaps[s]?.latestTrade?.p ?? signal.prices[s]]));
    const { orders, blocked } = planOrders(signal.targets, positions, prices, Number(account.equity), universe,
      this.settings.limits.minOrderNotional, this.settings.limits.maxGrossExposure);
    this.proposal = { id: proposalId(strategy, signal.as_of), created: new Date().toISOString(), strategy, asOf: signal.as_of,
      equity: Number(account.equity), targets: signal.targets, orders, blocked };
    await this.journal.write({ type: 'proposal', proposal: this.proposal.id, strategy, as_of: signal.as_of, targets: signal.targets, orders, blocked });
    this.journalTail = await this.journal.read(40);
    this.onChange();
    return this.proposal;
  }

  /**
   * Everything needed to review or restore the paper record in one file: settings (never keys), every journal
   * entry, every equity point, replaced readings, simulated returns and the lab verdict.
   */
  async exportBundle(version: string) {
    const read = async (name: string) => { try { return await readFile(path.join(this.folder, name), 'utf8'); } catch { return ''; } };
    const lines = (text: string) => text.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
    const journal = await this.journal.read(1e9);
    const results = (this.lab?.results ?? {}) as Record<string, JsonRecord>;
    return {
      kind: 'quantengine-paper-progress', format: 1, app_version: version, exported_at: new Date().toISOString(),
      data_folder: this.folder, settings: this.settings, strategy_since: strategyStart(journal, this.settings.strategy),
      stage3: await this.stageThreeNow(), brief: this.brief, equity: await this.journal.equity(),
      equity_replaced: lines(await read('equity-replaced.jsonl')), journal, simulated: this.simulated, market_returns: this.marketReturns,
      lab: this.lab ? { registration: (this.lab.registration as JsonRecord)?.hash, data: this.lab.data, go_to_paper: this.lab.go_to_paper,
        gates: Object.fromEntries(Object.entries(results).map(([k, r]) => [k, r.gates])) } : null,
    };
  }

  /** Submits the current proposal after the user approved it. Risk checks can block the whole batch. */
  async submit(id: unknown) {
    const proposal = this.proposal;
    if (!proposal || proposal.id !== id) throw new Error('That order list is no longer current. Compute it again.');
    if (!proposal.orders.length) throw new Error('Nothing to trade: the paper account already matches the targets.');
    const account = await this.broker.account();
    const today = nyDate();
    const ordersToday = (await this.journal.read(5000)).filter(e => e.type === 'order' && nyDate(new Date(String(e.at))) === today).length;
    const problems = riskCheck(proposal, this.settings, account, ordersToday);
    if (problems.length) {
      await this.journal.write({ type: 'blocked', proposal: proposal.id, problems });
      this.journalTail = await this.journal.read(40);
      this.onChange();
      throw new Error(problems.join(' '));
    }
    const held = new Map(this.positions.map(p => [p.symbol, Number(p.qty)]));
    const expected = Object.fromEntries(proposal.orders.map(o => [o.symbol, (held.get(o.symbol) ?? 0) + (o.side === 'buy' ? o.qty : -o.qty)]));
    await this.journal.write({ type: 'approved', proposal: proposal.id, orders: proposal.orders.length });
    for (const order of proposal.orders) {
      try {
        const placed = await this.broker.submit(order, proposal.id);
        await this.journal.write({ type: 'order', proposal: proposal.id, symbol: order.symbol, side: order.side, qty: order.qty, id: placed.id, status: placed.status });
      } catch (error) {
        await this.journal.write({ type: 'order-error', proposal: proposal.id, symbol: order.symbol, error: (error as Error).message });
      }
    }
    await this.journal.write({ type: 'submitted', proposal: proposal.id, expected });
    this.proposal = null;
    await this.refresh();
  }
}
