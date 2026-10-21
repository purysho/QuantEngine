import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { PaperBroker, PAPER_HOST, planOrders, riskCheck, stageThree, validateSettings, Journal, DEFAULT_SETTINGS,
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
  assert.throws(() => planOrders({ XLK: .7, XLE: .7 }, [], { XLK: 1, XLE: 1 }, 1000, ['XLK', 'XLE'], 1), /at most 100%/);
  assert.throws(() => planOrders({ XLK: -.5 }, [], { XLK: 1 }, 1000, ['XLK'], 1), /long-only/);
  const outside = planOrders({}, [{ symbol: 'TSLA', qty: '5', market_value: '1', current_price: '1', avg_entry_price: '1', unrealized_pl: '0' }], {}, 1000, ['SPY'], 1);
  assert.match(outside.blocked[0], /outside the strategy universe/);
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
