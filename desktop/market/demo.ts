// Offline demo market: deterministic synthetic prices, news, option chains and a ticking stream.
// Used only by --self-test and --market-demo (screenshots, CI) and always labelled DEMO DATA in the window.
import type { Fetch } from './alpaca.js';
import type { SocketLike } from './stream.js';
import { MACRO_SERIES } from './macro.js';

const BASE: Record<string, [number, string]> = {
  SPY: [670, 'SPDR S&P 500 ETF Trust'], QQQ: [600, 'Invesco QQQ Trust'], DIA: [460, 'SPDR Dow Jones Industrial Average ETF'],
  IWM: [245, 'iShares Russell 2000 ETF'], AAPL: [250, 'Apple Inc.'], MSFT: [520, 'Microsoft Corporation'], NVDA: [185, 'NVIDIA Corporation'],
  AMZN: [225, 'Amazon.com, Inc.'], GOOGL: [245, 'Alphabet Inc. Class A'], TSLA: [430, 'Tesla, Inc.'], TLT: [90, 'iShares 20+ Year Treasury Bond ETF'],
  'BTC/USD': [108000, 'Bitcoin'], 'ETH/USD': [3900, 'Ether'],
  XLB: [90, 'Materials Select Sector SPDR'], XLE: [88, 'Energy Select Sector SPDR'], XLF: [52, 'Financial Select Sector SPDR'],
  XLI: [150, 'Industrial Select Sector SPDR'], XLK: [280, 'Technology Select Sector SPDR'], XLP: [79, 'Consumer Staples Select Sector SPDR'],
  XLU: [86, 'Utilities Select Sector SPDR'], XLV: [140, 'Health Care Select Sector SPDR'], XLY: [235, 'Consumer Discretionary Select Sector SPDR'],
  XLRE: [42, 'Real Estate Select Sector SPDR'], XLC: [115, 'Communication Services Select Sector SPDR'],
  QUAL: [190, 'iShares MSCI USA Quality Factor ETF'], IEF: [95, 'iShares 7-10 Year Treasury Bond ETF'],
  VLUE: [120, 'iShares MSCI USA Value Factor ETF'], MTUM: [230, 'iShares MSCI USA Momentum Factor ETF'],
};

function seeded(text: string) {
  let h = 2166136261;
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => { h = Math.imul(h ^ (h >>> 15), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); h ^= h >>> 16; return (h >>> 0) / 2 ** 32; };
}
const gauss = (rand: () => number) => Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand());
const isOpen = (t: Date) => t.getUTCDay() > 0 && t.getUTCDay() < 6 && t.getUTCHours() * 60 + t.getUTCMinutes() >= 13 * 60 + 30 && t.getUTCHours() < 20;

function bars(symbol: string, timeframe: string, start: number, end: number) {
  const step = { '1Min': 60e3, '5Min': 300e3, '1Hour': 3600e3, '1Day': 86400e3, '1Week': 7 * 86400e3 }[timeframe] ?? 86400e3;
  const crypto = symbol.includes('/');
  const daily = step >= 86400e3;
  const rand = seeded(symbol + timeframe);
  // Trading days per bar: intraday bars are fractions of a 6.5-hour session; weekly bars are five sessions.
  const days = step >= 7 * 86400e3 ? 5 : step >= 86400e3 ? 1 : step / (6.5 * 3600e3);
  const vol = (crypto ? 0.6 : symbol === 'TSLA' || symbol === 'NVDA' ? 0.5 : 0.18) * Math.sqrt(days / 252);
  const out = [];
  let price = (BASE[symbol]?.[0] ?? 100) * 0.8;
  const first = Math.floor(start / step) * step;
  for (let t = first; t <= end; t += step) {
    const at = new Date(daily ? t + 4 * 3600e3 : t);
    if (!crypto && (daily ? at.getUTCDay() === 0 || at.getUTCDay() === 6 : !isOpen(at))) continue;
    const open = price;
    price = Math.max(1, price * Math.exp(vol * gauss(rand) + vol * 0.02));
    const high = Math.max(open, price) * (1 + Math.abs(gauss(rand)) * vol * 0.3), low = Math.min(open, price) * (1 - Math.abs(gauss(rand)) * vol * 0.3);
    out.push({ t: at.toISOString(), o: open, h: high, l: low, c: price, v: Math.round((crypto ? 40 : 2e5) * (1 + rand() * 3) * (daily ? 300 : 1)) });
  }
  // Scale so the latest close matches the symbol's demo level.
  const scale = out.length ? (BASE[symbol]?.[0] ?? 100) / out[out.length - 1].c : 1;
  return out.map(b => ({ ...b, o: b.o * scale, h: b.h * scale, l: b.l * scale, c: b.c * scale }));
}

function snapshot(symbol: string, now: number) {
  const days = bars(symbol, '1Day', now - 10 * 86400e3, now);
  const daily = days.at(-1)!, prev = days.at(-2)!;
  const last = daily.c;
  return { latestTrade: { t: new Date(now).toISOString(), p: last, s: 100 }, latestQuote: { t: new Date(now).toISOString(), bp: last * 0.9998, bs: 3, ap: last * 1.0002, as: 4 },
    dailyBar: daily, prevDailyBar: prev, minuteBar: daily };
}

function optionChain(symbol: string, now: number) {
  const spot = BASE[symbol]?.[0] ?? 100;
  const snapshots: Record<string, unknown> = {};
  const day = 86400e3;
  for (const days of [9, 23, 44, 72, 135, 255, 380]) {
    const expiry = new Date(now + days * day), T = days / 365, forward = spot * Math.exp(0.04 * T);
    const yy = String(expiry.getUTCFullYear()).slice(2), mm = String(expiry.getUTCMonth() + 1).padStart(2, '0'), dd = String(expiry.getUTCDate()).padStart(2, '0');
    for (let strike = Math.round(spot * 0.65); strike <= spot * 1.35; strike += Math.max(1, Math.round(spot / 80))) {
      const k = Math.log(strike / forward);
      const iv = 0.18 + 0.04 / Math.sqrt(T + 0.05) - 0.25 * k + 0.5 * k * k;
      const type = strike < spot ? 'P' : 'C';
      // Black–Scholes price for the demo smile.
      const sd = iv * Math.sqrt(T), d1 = (Math.log(spot / strike) + (0.04 + iv * iv / 2) * T) / sd, d2 = d1 - sd;
      const N = (x: number) => 0.5 * (1 + Math.tanh(Math.sqrt(2 / Math.PI) * (x + 0.044715 * x ** 3) * 1.0));
      const call = spot * N(d1) - strike * Math.exp(-0.04 * T) * N(d2);
      const price = type === 'C' ? call : call - spot + strike * Math.exp(-0.04 * T);
      if (price < 0.05) continue;
      const occ = `${symbol}${yy}${mm}${dd}${type}${String(Math.round(strike * 1000)).padStart(8, '0')}`;
      snapshots[occ] = { latestQuote: { t: '', bp: price * 0.97, bs: 10, ap: price * 1.03, as: 10 }, impliedVolatility: iv, greeks: { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 } };
    }
  }
  return { snapshots, next_page_token: null };
}

function macroCsv(id: string, now: number) {
  const rand = seeded(id);
  const level = { VIXCLS: 17, DGS2: 3.6, DGS10: 4.1, T10Y2Y: 0.5, DFF: 3.9, DTWEXBGS: 121, DCOILBRENTEU: 66 }[id] ?? 1;
  let value = level, rows = 'observation_date,' + id + '\n';
  for (let t = now - 400 * 86400e3; t <= now - 86400e3; t += 86400e3) {
    const d = new Date(t);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    value = Math.max(0.01, value + gauss(rand) * level * 0.01 + (level - value) * 0.02);
    rows += d.toISOString().slice(0, 10) + ',' + value.toFixed(2) + '\n';
  }
  return rows;
}

export function demoFetch(now = () => Date.now()): Fetch {
  return async url => {
    const u = new URL(url);
    const q = (name: string) => u.searchParams.get(name) ?? '';
    let body: unknown;
    if (u.hostname === 'fred.stlouisfed.org') {
      const id = q('id');
      if (!MACRO_SERIES.some(s => s.id === id)) return { status: 404, ok: false, headers: { get: () => null }, text: async () => '' };
      return { status: 200, ok: true, headers: { get: () => null }, text: async () => macroCsv(id, now()) };
    }
    const symbols = q('symbols').split(',').filter(Boolean);
    if (u.pathname.endsWith('/snapshots') && u.pathname.includes('crypto')) body = { snapshots: Object.fromEntries(symbols.map(s => [s, snapshot(s, now())])) };
    else if (u.pathname === '/v2/stocks/snapshots') body = Object.fromEntries(symbols.map(s => [s, snapshot(s, now())]));
    else if (u.pathname.endsWith('/bars')) {
      const end = q('end') ? Date.parse(q('end')) : now();
      body = { bars: { [symbols[0]]: bars(symbols[0], q('timeframe'), Date.parse(q('start')), end) }, next_page_token: null };
    } else if (u.pathname === '/v1beta1/news') {
      const about = symbols[0] ?? 'SPY';
      body = { news: ['Demo: futures steady ahead of earnings', 'Demo: Treasury yields edge lower', `Demo: ${about} options volume picks up`,
        'Demo: chipmakers lead the session', 'Demo: oil slips as inventories rise'].map((headline, i) => ({ id: i + 1, headline,
        summary: 'Synthetic headline for the offline demo. Connect Alpaca for real Benzinga news.', author: 'QuantEngine demo',
        created_at: new Date(now() - (i * 47 + 5) * 60e3).toISOString(), updated_at: '', url: 'https://alpaca.markets/', symbols: [about], source: 'demo' })) };
    } else if (u.pathname.endsWith('/most-actives')) body = { most_actives: ['NVDA', 'TSLA', 'AAPL', 'AMZN', 'SPY'].map((s, i) => ({ symbol: s, volume: 9e7 / (i + 1), trade_count: 1e6 / (i + 1) })), last_updated: new Date(now()).toISOString() };
    else if (u.pathname.endsWith('/movers')) body = { gainers: [['NVDA', 4.2], ['AMZN', 2.9], ['MSFT', 1.4]].map(([s, p]) => ({ symbol: s, percent_change: p, change: 1, price: BASE[s as string][0] })),
      losers: [['TSLA', -3.1], ['GOOGL', -1.2]].map(([s, p]) => ({ symbol: s, percent_change: p, change: -1, price: BASE[s as string][0] })), last_updated: new Date(now()).toISOString() };
    else if (u.pathname.startsWith('/v1beta1/options/snapshots/')) body = optionChain(u.pathname.split('/').pop()!, now());
    else if (u.pathname === '/v2/clock') {
      const t = new Date(now());
      body = { timestamp: t.toISOString(), is_open: isOpen(t), next_open: new Date(now() + 18 * 3600e3).toISOString(), next_close: new Date(now() + 3 * 3600e3).toISOString() };
    } else if (u.pathname === '/v2/assets') body = Object.entries(BASE).filter(([s]) => !s.includes('/')).map(([symbol, [, name]]) => ({ symbol, name, exchange: 'NASDAQ', class: 'us_equity', status: 'active' }));
    else return { status: 404, ok: false, headers: { get: () => null }, text: async () => '' };
    return { status: 200, ok: true, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  };
}

/** A stream that authenticates and then sends a few synthetic trades per second for subscribed symbols. */
export function demoSocket(now = () => Date.now()): (url: string) => SocketLike {
  return () => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let symbols: string[] = [];
    const prices = new Map<string, number>();
    const rand = seeded('stream');
    const socket: SocketLike = {
      onopen: null, onmessage: null, onclose: null, onerror: null,
      send(data: string) {
        const message = JSON.parse(data) as { action: string; trades?: string[] };
        if (message.action === 'auth') setTimeout(() => socket.onmessage?.({ data: JSON.stringify([{ T: 'success', msg: 'authenticated' }]) }), 10);
        if (message.action === 'subscribe') {
          symbols = [...new Set([...symbols, ...(message.trades ?? [])])];
          socket.onmessage?.({ data: JSON.stringify([{ T: 'subscription', trades: symbols }]) });
          timer ??= setInterval(() => {
            const symbol = symbols[Math.floor(rand() * symbols.length)];
            if (!symbol) return;
            const last = prices.get(symbol) ?? snapshot(symbol, now()).latestTrade.p;
            const next = last * (1 + gauss(rand) * 0.0006);
            prices.set(symbol, next);
            socket.onmessage?.({ data: JSON.stringify([{ T: 't', S: symbol, p: next, s: 100, t: new Date(now()).toISOString() }]) });
          }, 250);
        }
      },
      close() { if (timer) clearInterval(timer); timer = null; socket.onclose?.({}); },
    };
    setTimeout(() => socket.onmessage?.({ data: JSON.stringify([{ T: 'success', msg: 'connected' }]) }), 10);
    return socket;
  };
}

export const DEMO_KEYS = { keyId: 'PKDEMO0000000000DEMO', secret: 'demo-secret-not-a-real-key-000000000000' };

/** In-memory demo paper account: market orders fill immediately at the demo price. Used only in demo mode. */
export function demoPaperFetch(now = () => Date.now()) {
  let cash = 100_000;
  const positions = new Map<string, number>();
  const orders: Array<Record<string, unknown>> = [];
  const price = (symbol: string) => snapshot(symbol, now()).latestTrade.p;
  const equity = () => cash + [...positions].reduce((a, [s, q]) => a + q * price(s), 0);
  const reply = (status: number, body: unknown) => ({ status, ok: status < 400, text: async () => JSON.stringify(body) });
  return async (url: string, init: { method: string; body?: string }) => {
    const u = new URL(url);
    if (u.pathname === '/v2/account') return reply(200, { equity: String(equity()), last_equity: '100000', cash: String(cash), buying_power: String(cash),
      status: 'ACTIVE', currency: 'USD', trading_blocked: false, account_blocked: false });
    if (u.pathname === '/v2/positions') return reply(200, [...positions].filter(([, q]) => q !== 0).map(([symbol, qty]) => ({ symbol, qty: String(qty),
      market_value: String(qty * price(symbol)), current_price: String(price(symbol)), avg_entry_price: String(price(symbol)), unrealized_pl: '0' })));
    if (u.pathname === '/v2/orders' && init.method === 'GET') return reply(200, [...orders].reverse());
    if (u.pathname === '/v2/account/portfolio/history') {
      const days = Array.from({ length: 5 }, (_, i) => now() - (5 - i) * 86_400_000);
      return reply(200, { timestamp: days.map(t => Math.floor(t / 1000)), equity: days.map((_, i) => 100_000 + i * 50) });
    }
    if (u.pathname === '/v2/calendar') {
      const out = [];
      for (let t = Date.parse(u.searchParams.get('start') + 'T12:00:00Z'); t <= Date.parse(u.searchParams.get('end') + 'T12:00:00Z'); t += 86_400_000) {
        const d = new Date(t); if (d.getUTCDay() % 6) out.push({ date: d.toISOString().slice(0, 10), open: '09:30', close: '16:00' });
      }
      return reply(200, out);
    }
    if (u.pathname === '/v2/orders' && init.method === 'DELETE') return reply(207, []);
    if (u.pathname === '/v2/orders' && init.method === 'POST') {
      const o = JSON.parse(init.body ?? '{}') as { symbol: string; qty: string; side: string; client_order_id: string };
      if (orders.some(x => x.client_order_id === o.client_order_id)) return reply(422, { message: 'client_order_id must be unique' });
      const qty = Number(o.qty), p = price(o.symbol), signed = o.side === 'buy' ? qty : -qty;
      cash -= signed * p;
      positions.set(o.symbol, (positions.get(o.symbol) ?? 0) + signed);
      const order = { id: 'demo-' + (orders.length + 1), client_order_id: o.client_order_id, symbol: o.symbol, side: o.side, qty: o.qty,
        status: 'filled', filled_qty: o.qty, filled_avg_price: String(p), submitted_at: new Date(now()).toISOString(), filled_at: new Date(now()).toISOString() };
      orders.push(order);
      return reply(200, order);
    }
    return reply(404, { message: 'not found' });
  };
}
