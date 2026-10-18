// Read-only Alpaca market-data client. QuantEngine never trades: only GET requests to an
// explicit allowlist of market-data paths (plus the read-only clock/calendar/assets) are possible.

export interface Credentials { keyId: string; secret: string }
export type Feed = 'iex' | 'sip' | 'delayed_sip';
export type Fetch = (url: string, init: { method: 'GET'; headers: Record<string, string>; signal?: AbortSignal }) => Promise<{
  status: number; ok: boolean; headers: { get(name: string): string | null }; text(): Promise<string>;
}>;

export interface Bar { t: string; o: number; h: number; l: number; c: number; v: number; vw?: number; n?: number }
export interface Trade { t: string; p: number; s: number }
export interface Quote { t: string; bp: number; bs: number; ap: number; as: number }
export interface Snapshot { latestTrade?: Trade; latestQuote?: Quote; minuteBar?: Bar; dailyBar?: Bar; prevDailyBar?: Bar }
export interface NewsItem { id: number; headline: string; summary: string; author: string; created_at: string; updated_at: string;
  url: string; symbols: string[]; source: string }
export interface OptionSnapshot { latestTrade?: Trade; latestQuote?: Quote; impliedVolatility?: number;
  greeks?: { delta: number; gamma: number; theta: number; vega: number; rho: number } }
export interface Clock { timestamp: string; is_open: boolean; next_open: string; next_close: string }
export interface Asset { symbol: string; name: string; exchange: string; class: string; status: string; tradable?: boolean }

export const DATA_HOST = 'https://data.alpaca.markets';
// Paper and live accounts use different hosts for the read-only account-level endpoints; data is shared.
export const INFO_HOSTS = ['https://paper-api.alpaca.markets', 'https://api.alpaca.markets'];

const STOCK = '[A-Z][A-Z0-9.-]{0,9}';
const DATA_PATHS = [
  /^\/v2\/stocks\/(bars|snapshots|trades\/latest|quotes\/latest|bars\/latest)$/,
  new RegExp(`^/v2/stocks/${STOCK}/(bars|snapshot)$`),
  /^\/v1beta1\/news$/,
  /^\/v1beta1\/screener\/stocks\/(most-actives|movers)$/,
  new RegExp(`^/v1beta1/options/snapshots/${STOCK}$`),
  /^\/v1beta3\/crypto\/us\/(bars|snapshots)$/,
];
const INFO_PATHS = [/^\/v2\/clock$/, /^\/v2\/calendar$/, /^\/v2\/assets$/];

export const STOCK_SYMBOL = new RegExp(`^${STOCK}$`);
export const CRYPTO_SYMBOL = /^[A-Z0-9]{2,10}\/(USD|USDT|USDC|BTC)$/;
export const isCrypto = (symbol: string) => symbol.includes('/');
export function validSymbol(symbol: unknown): symbol is string {
  return typeof symbol === 'string' && (STOCK_SYMBOL.test(symbol) || CRYPTO_SYMBOL.test(symbol));
}

export class AlpacaError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

/** Explains Alpaca HTTP failures in plain words; error bodies may be HTML, so they are never parsed. */
function describe(status: number, path: string) {
  if (status === 401 || status === 403 && !path.includes('/bars')) return 'Alpaca rejected the API keys. Check the key ID and secret in Preferences.';
  if (status === 403) return 'Your Alpaca data plan does not include this data (the free plan cannot read the last 15 minutes of full-market history).';
  if (status === 404) return 'Alpaca has no data for that symbol.';
  if (status === 422) return 'Alpaca could not accept the request (check the symbol and dates).';
  if (status === 429) return 'Alpaca rate limit reached; slowing down.';
  return `Alpaca returned HTTP ${status}.`;
}

/** Token bucket below the free plan's 200 requests per minute, shared by every caller. */
export class RateLimiter {
  private tokens: number;
  private last: number;
  constructor(readonly perMinute = 180, readonly now = () => Date.now(), readonly sleep = (ms: number) => new Promise(r => setTimeout(r, ms))) {
    this.tokens = perMinute; this.last = now();
  }
  async take(): Promise<void> {
    for (;;) {
      const now = this.now();
      this.tokens = Math.min(this.perMinute, this.tokens + (now - this.last) * this.perMinute / 60_000);
      this.last = now;
      if (this.tokens >= 1) { this.tokens -= 1; return; }
      await this.sleep(Math.ceil((1 - this.tokens) * 60_000 / this.perMinute));
    }
  }
}

export class AlpacaClient {
  private infoHost: string | null = null;
  constructor(private credentials: Credentials | null, readonly fetcher: Fetch, readonly limiter = new RateLimiter(),
              readonly now = () => Date.now()) {}

  get configured() { return Boolean(this.credentials); }
  setCredentials(credentials: Credentials | null) { this.credentials = credentials; this.infoHost = null; }

  private async get<T>(host: string, path: string, query: Record<string, string | number | undefined> = {}, auth = true): Promise<T> {
    const allowed = host === DATA_HOST ? DATA_PATHS : INFO_HOSTS.includes(host) ? INFO_PATHS : [];
    if (!allowed.some(pattern => pattern.test(path))) throw new Error(`Blocked request to a non-market-data endpoint: ${path}`);
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== '') params.set(key, String(value));
    const url = host + path + (params.size ? '?' + params.toString() : '');
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (auth) {
      if (!this.credentials) throw new AlpacaError('Add your Alpaca API keys in Preferences to load market data.', 401);
      headers['APCA-API-KEY-ID'] = this.credentials.keyId;
      headers['APCA-API-SECRET-KEY'] = this.credentials.secret;
    }
    for (let attempt = 0; ; attempt++) {
      await this.limiter.take();
      const response = await this.fetcher(url, { method: 'GET', headers, signal: AbortSignal.timeout(20_000) });
      if (response.status === 429 && attempt < 3) {
        const reset = Number(response.headers.get('X-RateLimit-Reset')) * 1000;
        const wait = Number.isFinite(reset) && reset > this.now() ? Math.min(reset - this.now(), 60_000) : 2000 * 2 ** attempt;
        await new Promise(r => setTimeout(r, wait));
        continue;
      }
      if (response.status >= 500 && attempt < 2) { await new Promise(r => setTimeout(r, 1000 * 2 ** attempt)); continue; }
      if (!response.ok) throw new AlpacaError(describe(response.status, path), response.status);
      const text = await response.text();
      if (text.length > 64 * 1024 * 1024) throw new Error('Alpaca response was unexpectedly large.');
      return JSON.parse(text) as T;
    }
  }

  /** Clock, calendar and asset list live on the account host; try paper first, then live. */
  private async info<T>(path: string, query: Record<string, string | number | undefined> = {}): Promise<T> {
    const hosts = this.infoHost ? [this.infoHost] : INFO_HOSTS;
    let last: unknown;
    for (const host of hosts) {
      try {
        const value = await this.get<T>(host, path, query);
        this.infoHost = host;
        return value;
      } catch (error) {
        last = error;
        if (!(error instanceof AlpacaError) || ![401, 403].includes(error.status)) throw error;
      }
    }
    throw last;
  }

  async test(feed: Feed): Promise<Snapshot> {
    const snapshots = await this.snapshots(['SPY'], feed);
    if (!snapshots.SPY) throw new Error('Alpaca answered, but returned no SPY snapshot.');
    return snapshots.SPY;
  }

  async snapshots(symbols: string[], feed: Feed): Promise<Record<string, Snapshot>> {
    const stocks = symbols.filter(s => !isCrypto(s)), crypto = symbols.filter(isCrypto);
    const result: Record<string, Snapshot> = {};
    if (stocks.length) Object.assign(result, await this.get<Record<string, Snapshot>>(DATA_HOST, '/v2/stocks/snapshots', { symbols: stocks.join(','), feed }));
    if (crypto.length) {
      // Crypto history and snapshots are public: they work before keys are added.
      const value = await this.get<{ snapshots: Record<string, Snapshot> }>(DATA_HOST, '/v1beta3/crypto/us/snapshots', { symbols: crypto.join(',') }, this.configured);
      Object.assign(result, value.snapshots);
    }
    return result;
  }

  /** All pages of bars for one symbol, oldest first. Full-market (SIP) history ends 16 minutes ago on the free plan. */
  async bars(symbol: string, timeframe: string, start: string, options: { end?: string; feed?: Feed; limit?: number } = {}): Promise<Bar[]> {
    const crypto = isCrypto(symbol);
    const path = crypto ? '/v1beta3/crypto/us/bars' : '/v2/stocks/bars';
    const feed = options.feed === 'iex' ? 'iex' : 'sip';
    const end = options.end ?? (crypto || feed === 'iex' ? undefined : new Date(this.now() - 16 * 60_000).toISOString());
    const out: Bar[] = [];
    let token: string | undefined;
    do {
      const page = await this.get<{ bars: Record<string, Bar[]> | null; next_page_token: string | null }>(DATA_HOST, path, {
        symbols: symbol, timeframe, start, end, limit: 10_000, page_token: token,
        ...(crypto ? {} : { adjustment: 'all', feed }),
      }, crypto ? this.configured : true);
      out.push(...(page.bars?.[symbol] ?? []));
      token = page.next_page_token ?? undefined;
    } while (token && out.length < (options.limit ?? 50_000));
    return out;
  }

  async news(symbols: string[] = [], limit = 30): Promise<NewsItem[]> {
    const value = await this.get<{ news: NewsItem[] }>(DATA_HOST, '/v1beta1/news',
      { symbols: symbols.join(','), limit: Math.min(50, limit), sort: 'desc', exclude_contentless: 'true' });
    return value.news ?? [];
  }

  async mostActives(top = 20) {
    return this.get<{ most_actives: Array<{ symbol: string; volume: number; trade_count: number }>; last_updated: string }>(
      DATA_HOST, '/v1beta1/screener/stocks/most-actives', { by: 'volume', top });
  }

  async movers(top = 10) {
    return this.get<{ gainers: Array<{ symbol: string; percent_change: number; change: number; price: number }>;
      losers: Array<{ symbol: string; percent_change: number; change: number; price: number }>; last_updated: string }>(
      DATA_HOST, '/v1beta1/screener/stocks/movers', { top });
  }

  /** Option chain snapshots (free "indicative" feed) with Alpaca's implied volatility and Greeks. */
  async optionChain(underlying: string, options: { from: string; to: string; strikeLow?: number; strikeHigh?: number; maxContracts?: number }) {
    const out: Record<string, OptionSnapshot> = {};
    let token: string | undefined;
    do {
      const page = await this.get<{ snapshots: Record<string, OptionSnapshot>; next_page_token: string | null }>(DATA_HOST,
        `/v1beta1/options/snapshots/${underlying}`, { feed: 'indicative', limit: 1000, expiration_date_gte: options.from,
          expiration_date_lte: options.to, strike_price_gte: options.strikeLow, strike_price_lte: options.strikeHigh, page_token: token });
      Object.assign(out, page.snapshots ?? {});
      token = page.next_page_token ?? undefined;
    } while (token && Object.keys(out).length < (options.maxContracts ?? 4000));
    return out;
  }

  clock() { return this.info<Clock>('/v2/clock'); }
  assets() { return this.info<Asset[]>('/v2/assets', { status: 'active', asset_class: 'us_equity' }); }
}

/** OCC option symbol, e.g. AAPL240426C00162500 → underlying, expiry, type, strike. */
export function parseOcc(symbol: string) {
  const match = /^([A-Z.]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/.exec(symbol);
  if (!match) return null;
  return { underlying: match[1], expiry: `20${match[2]}-${match[3]}-${match[4]}`, type: match[5] === 'C' ? 'call' as const : 'put' as const,
    strike: Number(match[6]) / 1000 };
}
