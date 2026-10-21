// Strategies desk: stage 2 lab results, stage 3 paper trading (proposal → approval → paper orders →
// reconciliation) and the go/no-go ladder. Real money is never reachable from here (see paper.ts).
import { readFile, writeFile, rename, unlink, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import type { JsonRecord } from '../transport.js';
import type { MarketService } from './service.js';
import { PaperBroker, Journal, planOrders, riskCheck, stageThree, validateSettings, proposalId, DEFAULT_SETTINGS, UNIVERSE,
  type Account, type Order, type PaperSettings, type Position, type Proposal } from './paper.js';

export interface DeskHost {
  dataRoot(): string;
  runTask(stage: string, command: string, values: JsonRecord): Promise<JsonRecord>;
  stage(extension: 'csv' | 'json', content: string): Promise<string>;
  riskFreeAnnual(): number;
}

const nyDate = (at = new Date()) => at.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

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
  onChange: () => void = () => {};

  constructor(readonly settingsFile: string, readonly broker: PaperBroker, readonly market: MarketService, readonly host: DeskHost) {}

  private get folder() { return path.join(this.host.dataRoot(), 'paper'); }
  private get journal() { return new Journal(this.folder); }

  async load() {
    try { this.settings = validateSettings(JSON.parse(await readFile(this.settingsFile, 'utf8'))); } catch { /* defaults */ }
    try { this.simulated = JSON.parse(await readFile(path.join(this.folder, 'simulated.json'), 'utf8')); } catch { this.simulated = {}; }
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
      updated: this.updated, journal: this.journalTail.slice(-25).reverse(), stage3: this.stage3,
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
    const enabling = next.enabled && !this.settings.enabled;
    const killChanged = next.killSwitch !== this.settings.killSwitch;
    this.settings = next;
    await this.saveSettings();
    if (enabling) await this.journal.write({ type: 'enabled', strategy: next.strategy });
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

  /** Account, positions and orders from the paper account; one equity point per New York date; reconciliation. */
  async refresh() {
    try {
      const [account, positions, orders] = await Promise.all([this.broker.account(), this.broker.positions(), this.broker.orders()]);
      this.account = account; this.positions = positions; this.orders = orders;
      await this.journal.recordEquity(nyDate(), Number(account.equity), Number(account.cash));
      await this.reconcile();
      this.lastError = null;
    } catch (error) { this.lastError = (error as Error).message; }
    this.updated = new Date().toISOString();
    this.journalTail = await this.journal.read(40);
    this.stage3 = stageThree(await this.journal.equity(), this.simulated, await this.journal.read(5000));
    this.onChange();
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

  /** Today's orders for the chosen strategy, from the traded ETFs' own daily closes. Nothing is sent. */
  async propose(): Promise<Proposal> {
    const strategy = this.settings.strategy;
    const universe = UNIVERSE[strategy];
    const { dates, closes } = await this.market.dailyCloses(universe, 3);
    const file = await this.host.stage('csv', 'date,' + universe.join(',') + '\n' + dates.map((d, i) => d + ',' + closes[i].join(',')).join('\n') + '\n');
    const equityHistory = await this.journal.equity();
    const signal = (await this.host.runTask('Computing today\'s strategy signal', 'strategy-signal', { path: file, family: strategy,
      rf_annual: this.host.riskFreeAnnual(), since: equityHistory[0]?.date ?? null })).signal as {
      targets: Record<string, number>; as_of: string; simulated: Record<string, number>; prices: Record<string, number> };
    this.simulated = { ...this.simulated, ...signal.simulated };
    await mkdir(this.folder, { recursive: true });
    await writeFile(path.join(this.folder, 'simulated.json'), JSON.stringify(this.simulated));
    const [account, positions, snaps] = await Promise.all([this.broker.account(), this.broker.positions(), this.market.client.snapshots(universe, this.market.settings.feed)]);
    this.account = account; this.positions = positions;
    const prices = Object.fromEntries(universe.map(s => [s, snaps[s]?.latestTrade?.p ?? signal.prices[s]]));
    const { orders, blocked } = planOrders(signal.targets, positions, prices, Number(account.equity), universe, this.settings.limits.minOrderNotional);
    this.proposal = { id: proposalId(strategy, signal.as_of), created: new Date().toISOString(), strategy, asOf: signal.as_of,
      equity: Number(account.equity), targets: signal.targets, orders, blocked };
    await this.journal.write({ type: 'proposal', proposal: this.proposal.id, strategy, as_of: signal.as_of, targets: signal.targets, orders, blocked });
    this.journalTail = await this.journal.read(40);
    this.onChange();
    return this.proposal;
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
