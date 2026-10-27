import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { PaperBroker, PAPER_HOST, planOrders, riskCheck, stageThree, strategyStart, fillDate, dailySchedule, validateSettings, Journal, DEFAULT_SETTINGS,
  type Account, type PaperFetch, type Proposal } from '../desktop/market/paper.js';

const KEYS = { keyId: 'PKTESTKEY1234567890A', secret: 'abcdefghijklmnopqrstuvwxyz0123456789ABCD' };
const account = (equity = 100_000, last = 100_000, cash = equity): Account => ({ equity: String(equity), last_equity: String(last), cash: String(cash),
  buying_power: String(cash), status: 'ACTIVE', currency: 'USD', trading_blocked: false, account_blocked: false });
const enabled = { ...DEFAULT_SETTINGS, enabled: true, strategy: 'sectors' as const };

test('the broker can only reach the paper host and its allowlisted paths', async () => {
  const urls: string[] = [];
  const fetcher: PaperFetch = async (url, init) => { urls.push(init.method + ' ' + url); return { status: 200, ok: true, text: async () => '[]' }; };
  const broker = new PaperBroker(() => KEYS, fetcher);
  await broker.positions();
  assert.equal(urls[0], 'GET ' + PAPER_HOST + '/v2/positions');
  const call = (broker as unknown as { call: (m: string, p: string) => Promise<unknown> }).call.bind(broker);
  await assert.rejects(() => call('POST', '/v2/positions'), /Blocked/);
  await assert.rejects(() => call('DELETE', '/v2/positions'), /Blocked/);   // No "close all positions" shortcut.
  await assert.rejects(() => call('PATCH', '/v2/account/configurations'), /Blocked/);
  assert.ok(!PAPER_HOST.includes('://api.alpaca.markets'), 'the live trading host must never be used');
});

test('live-account keys are explained, not retried', async () => {
  const broker = new PaperBroker(() => KEYS, async () => ({ status: 401, ok: false, text: async () => '<html>' }));
  await assert.rejects(() => broker.account(), /paper host rejected these keys/);
});

test('orders are whole shares, sells first, long-only and never exceed equity', () => {
  const { orders } = planOrders({ XLK: .5, XLE: .5 }, [{ symbol: 'XLF', qty: '100', market_value: '5200', current_price: '52', avg_entry_price: '50', unrealized_pl: '200' }],
    { XLK: 280, XLE: 88, XLF: 52, SPY: 670 }, 100_000, ['SPY', 'XLK', 'XLE', 'XLF'], 50);
  assert.deepEqual(orders.map(o => [o.side, o.symbol, o.qty]), [['sell', 'XLF', 100], ['buy', 'XLE', 568], ['buy', 'XLK', 178]]);
  assert.ok(orders.filter(o => o.side === 'buy').reduce((a, o) => a + o.notional, 0) <= 100_000);
  const scaled = planOrders({ XLK: .7, XLE: .7 }, [], { XLK: 1, XLE: 1 }, 1000, ['XLK', 'XLE'], 1);  // 140% asked, no margin: scaled to 100%.
  assert.ok(scaled.orders.reduce((a, o) => a + o.notional, 0) <= 1000);
  assert.throws(() => planOrders({ XLK: -.5 }, [], { XLK: 1 }, 1000, ['XLK'], 1), /long-only/);
  const outside = planOrders({}, [{ symbol: 'TSLA', qty: '5', market_value: '1', current_price: '1', avg_entry_price: '1', unrealized_pl: '0' }], {}, 1000, ['SPY'], 1);
  assert.match(outside.blocked[0], /outside the strategy universe/);
});

test('rules asking for more than 100% are scaled down unless margin is opted in', () => {
  const prices = { SPY: 100, QUAL: 100, IEF: 100 };
  const unlevered = planOrders({ SPY: .5, QUAL: .5, IEF: .5 }, [], prices, 100_000, ['SPY', 'QUAL', 'IEF'], 50, 1.0);
  assert.ok(unlevered.orders.reduce((a, o) => a + o.notional, 0) <= 100_000);
  const levered = planOrders({ SPY: .5, QUAL: .5, IEF: .5 }, [], prices, 100_000, ['SPY', 'QUAL', 'IEF'], 50, 1.5);
  assert.equal(levered.orders.reduce((a, o) => a + o.notional, 0), 150_000);
  assert.throws(() => planOrders({ SPY: 1, QUAL: 1 }, [], prices, 1000, ['SPY', 'QUAL'], 1, 1.5), /150%/);
  const now = Date.now();
  const proposal: Proposal = { id: 'p2', created: new Date(now).toISOString(), strategy: 'ensemble', asOf: '', equity: 100_000, targets: {}, orders: levered.orders, blocked: [] };
  const ensemble = { ...enabled, strategy: 'ensemble' as const };
  assert.match(riskCheck(proposal, ensemble, account(), 0, now).join(), /no leverage/);
  assert.deepEqual(riskCheck(proposal, { ...ensemble, limits: { ...ensemble.limits, maxGrossExposure: 1.5 } }, account(), 0, now), []);
  assert.throws(() => validateSettings({ ...ensemble, limits: { ...ensemble.limits, maxGrossExposure: 2 } }), /total exposure/);
});

test('risk checks block stale, oversized, over-limit, killed and loss-stopped batches', () => {
  const now = Date.parse('2026-10-21T15:00:00Z');
  const proposal: Proposal = { id: 'p1', created: new Date(now - 60_000).toISOString(), strategy: 'sectors', asOf: '2026-10-20', equity: 100_000,
    targets: { XLK: .5 }, orders: [{ symbol: 'XLK', side: 'buy', qty: 178, price: 280, notional: 49_840, reason: '' }], blocked: [] };
  assert.deepEqual(riskCheck(proposal, enabled, account(), 0, now), []);
  assert.match(riskCheck(proposal, { ...enabled, enabled: false }, account(), 0, now).join(), /turned off/);
  assert.match(riskCheck(proposal, { ...enabled, killSwitch: true }, account(), 0, now).join(), /kill switch/);
  assert.match(riskCheck({ ...proposal, created: new Date(now - 31 * 60_000).toISOString() }, enabled, account(), 0, now).join(), /30 minutes/);
  assert.match(riskCheck(proposal, { ...enabled, limits: { ...enabled.limits, maxOrderFraction: .25 } }, account(), 0, now).join(), /maximum order size/);
  assert.match(riskCheck(proposal, enabled, account(96_000, 100_000), 0, now).join(), /Daily loss stop/);
  assert.match(riskCheck(proposal, enabled, account(), 24, now).join(), /maximum orders per day/);
  assert.match(riskCheck(proposal, enabled, account(100_000, 100_000, 1_000), 0, now).join(), /no leverage/);
  assert.match(riskCheck({ ...proposal, orders: [{ ...proposal.orders[0], symbol: 'TSLA' }] }, enabled, account(), 0, now).join(), /outside the strategy universe/);
  assert.throws(() => validateSettings({ ...enabled, limits: { ...enabled.limits, maxOrderFraction: 3 } }), /Maximum order/);
});

test('stage 3 needs 63 tracked days, low tracking error, reconciliation and a tested kill switch', async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-paper-'));
  try {
    const journal = new Journal(folder);
    const equity: Array<{ date: string; equity: number; cash: number }> = [];
    const simulated: Record<string, number> = {};
    let value = 100_000;
    for (let i = 0; i < 70; i++) {
      const date = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
      const r = 0.001 * Math.sin(i);
      if (i) { value *= 1 + r + 0.0001 * (i % 2 ? 1 : -1); simulated[date] = r; }
      equity.push({ date, equity: value, cash: 0 });
    }
    await journal.write({ type: 'kill-switch', on: true });
    await journal.write({ type: 'kill-switch', on: false });
    const result = stageThree(equity, simulated, await journal.read());
    assert.equal(result.days, 69);
    assert.ok(result.checks.tracking.pass && result.checks.within_band.pass && result.checks.kill_switch_tested.pass);
    assert.equal(result.passed, true);
    const short = stageThree(equity.slice(0, 20), simulated, []);
    assert.equal(short.passed, false);
    assert.equal(short.checks.kill_switch_tested.pass, false);
    await journal.recordEquity('2026-03-01', 1, 1);
    await journal.recordEquity('2026-03-01', 2, 2);
    assert.deepEqual((await journal.equity()).map(p => p.equity), [2]);
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('official closes replace mis-dated readings without losing anything (a real 0.3.0 history)', async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-paper-'));
  try {
    // equity.jsonl exactly as 0.3.0 wrote it on the first tester's laptop: readings dated by the day the app was opened.
    const original = [
      { date: '2026-10-21', equity: 100148.39, cash: 139.08 }, { date: '2026-10-22', equity: 99427.73, cash: 139.07 },
      { date: '2026-10-25', equity: 100075.74, cash: 139.07 }, { date: '2026-10-26', equity: 100001.34, cash: 139.07 },
      { date: '2026-10-27', equity: 100805.64, cash: 139.07 }];
    await writeFile(path.join(folder, 'equity.jsonl'), original.map(p => JSON.stringify(p)).join('\n') + '\n');
    const journal = new Journal(folder);
    const sessions = { first: '2026-10-20', last: '2026-10-26', dates: new Set(['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26']) };
    const closes = [{ date: '2026-10-20', equity: 100000 }, { date: '2026-10-21', equity: 100148.39 }, { date: '2026-10-22', equity: 99427.73 },
      { date: '2026-10-23', equity: 100075.74 }, { date: '2026-10-26', equity: 100010.5 }];
    const merged = await journal.mergeCloses(closes, sessions);
    assert.deepEqual(merged, { added: 2, replaced: 3, removed: 1 });
    const after = await journal.equity();
    assert.deepEqual(after.map(p => p.date), ['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27']);
    assert.equal(after.find(p => p.date === '2026-10-26')!.equity, 100010.5);
    assert.equal(after.find(p => p.date === '2026-10-21')!.cash, 139.08, 'cash from the reading is kept');
    assert.equal(after.at(-1)!.source, undefined, 'a day not yet in the official history stays a reading');
    // Every original entry still exists, either in equity.jsonl unchanged or in equity-replaced.jsonl.
    const replaced = (await readFile(path.join(folder, 'equity-replaced.jsonl'), 'utf8')).trim().split('\n').map(l => JSON.parse(l));
    for (const point of original) {
      assert.ok(replaced.some(r => r.date === point.date && r.equity === point.equity) || after.some(a => a.date === point.date && a.equity === point.equity && !a.source),
        `${point.date} must be preserved`);
    }
    assert.equal(replaced.find(r => r.date === '2026-10-25').reason, 'dated on a day the market was closed');
    // A later reading never overwrites an official close; merging the same closes again changes nothing.
    await journal.recordEquity('2026-10-26', 1, 1);
    assert.equal((await journal.equity()).find(p => p.date === '2026-10-26')!.equity, 100010.5);
    assert.deepEqual(await journal.mergeCloses(closes, sessions), { added: 0, replaced: 0, removed: 0 });
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('switching strategy restarts the paper test from the first fill of the new strategy', () => {
  const entries = [
    { at: '2026-10-21T11:29:53Z', type: 'proposal', proposal: 'a', strategy: 'sectors' },
    { at: '2026-10-21T11:30:20Z', type: 'submitted', proposal: 'a' },              // 07:30 New York: fills at that day's open.
    { at: '2026-10-31T02:00:00Z', type: 'strategy', from: 'sectors', to: 'quality' },
    { at: '2026-10-31T02:01:00Z', type: 'proposal', proposal: 'b', strategy: 'quality' },
    { at: '2026-10-31T02:02:00Z', type: 'submitted', proposal: 'b' },              // Friday 10 p.m. New York: fills Monday.
  ];
  assert.equal(strategyStart(entries.slice(0, 2), 'sectors'), '2026-10-21');
  assert.equal(strategyStart(entries, 'sectors'), null);
  assert.equal(strategyStart(entries, 'quality'), '2026-11-02');
  assert.equal(strategyStart(entries.slice(0, 4), 'quality'), null, 'no trades yet under the new strategy');
  assert.equal(fillDate(new Date('2026-10-23T19:59:00Z')), '2026-10-23');   // Friday 3:59 p.m. New York.
  assert.equal(fillDate(new Date('2026-10-23T20:00:00Z')), '2026-10-26');   // Friday 4 p.m. → Monday.
  assert.equal(fillDate(new Date('2026-10-25T03:00:00Z')), '2026-10-26');   // Saturday night.
  const equity = ['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'].map((date, i) => ({ date, equity: 100 + i }));
  const simulated = { '2026-10-21': 0.5, '2026-10-22': 0.0099, '2026-10-23': 0.0098 };
  assert.equal(stageThree(equity, simulated, [], null).days, 3);
  assert.equal(stageThree(equity, simulated, [], '2026-10-21').days, 2, 'the partial first day is not compared');
  assert.equal(stageThree(equity, simulated, [], '9999-12-31').days, 0);
});

test('the daily update runs once a day from 06:00 Beijing time, never during the US session', () => {
  const at = (iso: string) => dailySchedule(new Date(iso), '06:00', 'Asia/Shanghai');
  assert.equal(at('2026-10-27T21:59:00Z').key, '2026-10-27', '05:59 Beijing still belongs to yesterday\'s slot');
  assert.deepEqual(at('2026-10-27T22:00:00Z'), { key: '2026-10-28', due: true, waitingForClose: false });   // 06:00 Beijing = 6 p.m. New York.
  assert.equal(at('2026-10-28T03:00:00Z').key, '2026-10-28', 'opening the app later that day catches up once, not twice');
  assert.equal(at('2026-11-02T22:00:00Z').due, true, 'after the US clock change 06:00 Beijing is 5 p.m. New York, still after the close');
  // A slot inside US trading hours (22:00 Beijing = 10 a.m. New York) waits for the close, past Beijing midnight.
  assert.deepEqual(dailySchedule(new Date('2026-10-28T14:00:00Z'), '22:00', 'Asia/Shanghai'), { key: '2026-10-28', due: false, waitingForClose: true });
  assert.deepEqual(dailySchedule(new Date('2026-10-28T20:25:00Z'), '22:00', 'Asia/Shanghai'), { key: '2026-10-28', due: true, waitingForClose: false });
  assert.equal(dailySchedule(new Date('2026-10-31T14:00:00Z'), '22:00', 'Asia/Shanghai').due, true, 'Saturday: no session to wait for');
  // Settings saved by 0.3.0/0.3.1 load with the new default; bad values are refused.
  const legacy = validateSettings({ enabled: true, strategy: 'sectors', killSwitch: false, dailyUpdate: true, notify: true,
    limits: { maxOrderFraction: .5, maxOrdersPerDay: 24, dailyLossStop: .03, minOrderNotional: 50, maxGrossExposure: 1 } });
  assert.equal(legacy.dailyTime, '06:00'); assert.equal(legacy.dailyZone, 'Asia/Shanghai'); assert.equal(legacy.limits.maxOrderFraction, .5);
  assert.throws(() => validateSettings({ ...legacy, dailyTime: '6am' }), /HH:MM/);
  assert.throws(() => validateSettings({ ...legacy, dailyZone: 'Mars/Base' }), /time zones/);
});
