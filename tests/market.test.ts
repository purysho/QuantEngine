import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { AlpacaClient, RateLimiter, parseOcc, validSymbol, type Fetch } from '../desktop/market/alpaca.js';
import { MarketStream, type SocketLike } from '../desktop/market/stream.js';
import { SecretStore, validateCredentials, type Cipher } from '../desktop/market/secrets.js';
import { MarketService, realisedVol, validateWatchlist } from '../desktop/market/service.js';
import { parseSeries, macroPoint, MACRO_SERIES } from '../desktop/market/macro.js';

const KEYS = { keyId: 'PKTESTKEY1234567890A', secret: 'abcdefghijklmnopqrstuvwxyz0123456789ABCD' };
const noWait = new RateLimiter(1e9);

function fakeFetch(routes: Record<string, unknown>, calls: string[] = []): Fetch {
  return async (url, init) => {
    calls.push(url + ' ' + (init.headers['APCA-API-KEY-ID'] ?? '-'));
    const match = Object.entries(routes).find(([prefix]) => url.startsWith(prefix));
    const body = match ? match[1] : undefined;
    const status = typeof body === 'number' ? body : body === undefined ? 404 : 200;
    return { status, ok: status < 400, headers: { get: () => null }, text: async () => typeof body === 'number' ? '<html>error</html>' : JSON.stringify(body) };
  };
}

test('client only reaches allowlisted read-only market-data paths', async () => {
  const calls: string[] = [];
  const client = new AlpacaClient(KEYS, fakeFetch({ 'https://data.alpaca.markets/v2/stocks/snapshots': { SPY: { latestTrade: { p: 500, s: 1, t: '2026-10-16T19:59:00Z' } } } }, calls), noWait);
  const snaps = await client.snapshots(['SPY'], 'iex');
  assert.equal(snaps.SPY.latestTrade?.p, 500);
  assert.match(calls[0], /feed=iex/);
  assert.match(calls[0], /PKTESTKEY/);
  // Trading endpoints cannot be expressed through the client at all.
  const get = (client as unknown as { get: (host: string, path: string) => Promise<unknown> }).get.bind(client);
  await assert.rejects(() => get('https://paper-api.alpaca.markets', '/v2/orders'), /Blocked/);
  await assert.rejects(() => get('https://data.alpaca.markets', '/v2/positions'), /Blocked/);
  await assert.rejects(() => get('https://evil.example', '/v2/stocks/bars'), /Blocked/);
});

test('HTTP errors are explained without parsing HTML bodies', async () => {
  const client = new AlpacaClient(KEYS, fakeFetch({ 'https://data.alpaca.markets/v2/stocks/snapshots': 401 }), noWait);
  await assert.rejects(() => client.snapshots(['SPY'], 'iex'), /rejected the API keys/);
  const none = new AlpacaClient(null, fakeFetch({}), noWait);
  await assert.rejects(() => none.snapshots(['SPY'], 'iex'), /Add your Alpaca API keys/);
});

test('crypto snapshots work before keys are added (public endpoint, no key header)', async () => {
  const calls: string[] = [];
  const client = new AlpacaClient(null, fakeFetch({ 'https://data.alpaca.markets/v1beta3/crypto/us/snapshots': { snapshots: { 'BTC/USD': { latestTrade: { p: 60000, s: 1, t: 'x' } } } } }, calls), noWait);
  const snaps = await client.snapshots(['BTC/USD'], 'iex');
  assert.equal(snaps['BTC/USD'].latestTrade?.p, 60000);
  assert.match(calls[0], / -$/);
});

test('bars follow pages, request split/dividend adjustment and stop SIP history 16 minutes ago', async () => {
  const calls: string[] = [];
  let page = 0;
  const fetcher: Fetch = async url => {
    calls.push(url);
    page++;
    const body = page === 1 ? { bars: { SPY: [{ t: 'a', o: 1, h: 1, l: 1, c: 1, v: 1 }] }, next_page_token: 'n2' }
      : { bars: { SPY: [{ t: 'b', o: 2, h: 2, l: 2, c: 2, v: 2 }] }, next_page_token: null };
    return { status: 200, ok: true, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  };
  const now = Date.parse('2026-10-16T20:00:00Z');
  const client = new AlpacaClient(KEYS, fetcher, noWait, () => now);
  const bars = await client.bars('SPY', '1Day', '2026-01-01');
  assert.deepEqual(bars.map(b => b.t), ['a', 'b']);
  assert.match(calls[0], /adjustment=all/);
  assert.match(decodeURIComponent(calls[0]), /end=2026-10-16T19:44:00/);
  assert.match(calls[1], /page_token=n2/);
});

test('rate limiter spaces requests once the bucket is empty', async () => {
  let clock = 0;
  const sleeps: number[] = [];
  const limiter = new RateLimiter(2, () => clock, async ms => { sleeps.push(ms); clock += ms; });
  await limiter.take(); await limiter.take(); await limiter.take();
  assert.equal(sleeps.length, 1);
  assert.ok(sleeps[0] >= 29_000 && sleeps[0] <= 30_000);
});

test('OCC option symbols, symbols and credentials are validated', () => {
  assert.deepEqual(parseOcc('AAPL240426C00162500'), { underlying: 'AAPL', expiry: '2024-04-26', type: 'call', strike: 162.5 });
  assert.equal(parseOcc('AAPL'), null);
  assert.ok(validSymbol('BRK.B') && validSymbol('BTC/USD') && !validSymbol('spy; rm') && !validSymbol('A'.repeat(11)));
  assert.deepEqual(validateWatchlist([' spy', 'SPY', 'btc/usd']), ['SPY', 'BTC/USD']);
  assert.throws(() => validateWatchlist(['$$$']), /valid symbol/);
  assert.throws(() => validateCredentials({ keyId: 'short', secret: KEYS.secret }), /key ID/);
  assert.deepEqual(validateCredentials({ keyId: ` ${KEYS.keyId} `, secret: KEYS.secret }), KEYS);
});

class FakeSocket implements SocketLike {
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code?: number }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close() { this.onclose?.({}); }
  receive(...messages: unknown[]) { this.onmessage?.({ data: JSON.stringify(messages) }); }
}

test('stream authenticates, subscribes, forwards data and changes subscriptions', () => {
  const sockets: FakeSocket[] = [];
  const data: unknown[] = [];
  const statuses: string[] = [];
  const stream = new MarketStream('wss://x', KEYS, () => { const s = new FakeSocket(); sockets.push(s); return s; },
    messages => data.push(...messages), status => statuses.push(status));
  stream.start(['SPY', 'AAPL']);
  const socket = sockets[0];
  socket.receive({ T: 'success', msg: 'connected' });
  assert.deepEqual(socket.sent[0], { action: 'auth', key: KEYS.keyId, secret: KEYS.secret });
  socket.receive({ T: 'success', msg: 'authenticated' });
  assert.equal(stream.status, 'live');
  assert.deepEqual((socket.sent[1] as { trades: string[] }).trades, ['SPY', 'AAPL']);
  socket.receive({ T: 't', S: 'SPY', p: 501, s: 10, t: 'now' }, { T: 'q', S: 'SPY', bp: 500.9, ap: 501.1, bs: 1, as: 2, t: 'now' });
  assert.equal(data.length, 2);
  stream.setSymbols(['SPY', 'MSFT']);
  assert.deepEqual(socket.sent[2], { action: 'unsubscribe', trades: ['AAPL'], quotes: ['AAPL'], bars: ['AAPL'], dailyBars: ['AAPL'] });
  assert.deepEqual((socket.sent[3] as { trades: string[] }).trades, ['MSFT']);
  stream.stop();
  assert.equal(stream.status, 'off');
});

test('rejected keys stop the stream; a busy connection waits a minute before retrying', () => {
  const sockets: FakeSocket[] = [];
  const stream = new MarketStream('wss://x', KEYS, () => { const s = new FakeSocket(); sockets.push(s); return s; }, () => {}, () => {});
  stream.start(['SPY']);
  sockets[0].receive({ T: 'error', code: 402, msg: 'auth failed' });
  sockets[0].close();
  assert.equal(stream.status, 'error');
  assert.match(stream.detail, /rejected/);
  const busy = new MarketStream('wss://x', KEYS, () => { const s = new FakeSocket(); sockets.push(s); return s; }, () => {}, () => {});
  busy.start(['SPY']);
  const socket = sockets.at(-1)!;
  socket.receive({ T: 'error', code: 406, msg: 'connection limit exceeded' });
  socket.close();
  assert.equal(busy.status, 'busy');
  assert.match(busy.detail, /Another program/);
  busy.stop();
});

test('keys are stored only encrypted, and a key Alpaca refuses is never saved', async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-keys-'));
  const cipher: Cipher = { isEncryptionAvailable: () => true,
    encryptString: v => Buffer.from([...Buffer.from(v)].map(b => b ^ 0x5a)), decryptString: b => Buffer.from([...b].map(x => x ^ 0x5a)).toString() };
  try {
    const secrets = new SecretStore(path.join(folder, 'keys.json'), cipher);
    const refused = new MarketService(folder, secrets, fakeFetch({ 'https://data.alpaca.markets/v2/stocks/snapshots': 401 }), () => new FakeSocket());
    await assert.rejects(() => refused.setCredentials(KEYS, 'iex'), /rejected/);
    assert.equal(await secrets.load(), null);
    const accepted = new MarketService(folder, secrets, fakeFetch({ 'https://data.alpaca.markets/v2/stocks/snapshots': { SPY: { latestTrade: { p: 1, s: 1, t: 'x' } } } }), () => new FakeSocket());
    await accepted.setCredentials(KEYS, 'iex');
    const raw = await readFile(path.join(folder, 'keys.json'), 'utf8');
    assert.ok(!raw.includes(KEYS.keyId) && !raw.includes(KEYS.secret));
    assert.deepEqual(await secrets.load(), KEYS);
    assert.equal(accepted.snapshot().keyHint, '••••890A');
    assert.ok(!JSON.stringify(accepted.snapshot()).includes(KEYS.secret));
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('quote rows combine snapshots and live ticks into change from the previous close', async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-market-'));
  try {
    const service = new MarketService(folder, new SecretStore(path.join(folder, 'k.json'), { isEncryptionAvailable: () => false,
      encryptString: () => Buffer.alloc(0), decryptString: () => '' }), fakeFetch({}), () => new FakeSocket());
    await service.load();
    service.applySnapshot('SPY', { prevDailyBar: { t: 'p', o: 1, h: 1, l: 1, c: 500, v: 1 }, dailyBar: { t: 'd', o: 501, h: 506, l: 499, c: 505, v: 1e6 },
      latestTrade: { t: '2026-10-16T19:00:00Z', p: 505, s: 1 } });
    service.applyStream([{ T: 't', S: 'SPY', p: 510, t: '2026-10-16T19:00:01Z' }]);
    const row = service.snapshot().quotes.find(q => q.symbol === 'SPY')!;
    assert.equal(row.last, 510);
    assert.equal(row.change, 10);
    assert.ok(Math.abs(row.changePct! - 0.02) < 1e-12);
    assert.equal(row.direction, 1);
    assert.equal(row.volume, 1e6);
    service.stop();
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('realised volatility and FRED macro parsing', () => {
  const closes = Array.from({ length: 30 }, (_, i) => 100 * Math.exp(0.01 * (i % 2 ? 1 : -1) * i / 30));
  assert.ok(realisedVol(closes, 20)! > 0);
  assert.equal(realisedVol(closes.slice(0, 5), 20), null);
  const history = parseSeries('observation_date,VIXCLS\n2026-10-14,17.1\n2026-10-15,.\n2026-10-16,18.4\n', 'VIXCLS');
  assert.deepEqual(history, [['2026-10-14', 17.1], ['2026-10-16', 18.4]]);
  const point = macroPoint(MACRO_SERIES[0], history);
  assert.equal(point.value, 18.4);
  assert.ok(Math.abs(point.change! - 1.3) < 1e-9);
  assert.throws(() => parseSeries('<html>', 'VIXCLS'), /unexpected/);
});
