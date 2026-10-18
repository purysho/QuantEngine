// Market terminal: command line, live watchlist, candlestick chart, description, news, economy and movers.
// All data arrives through the sandboxed bridge (window.quant.market); this page has no network access.
import { createChart, CandlestickSeries, HistogramSeries, ColorType, CrosshairMode } from 'lightweight-charts';

const RANGES = ['1D', '5D', '1M', '6M', '1Y', '5Y', 'MAX'];
const FUNCTIONS = new Set(['GP', 'DES', 'N', 'NEWS', 'OMON', 'OVDV', 'VOL', 'MOST', 'MOVERS', 'ECO', 'WEI', 'HELP', ...RANGES]);
const UP = '#35e0a1', DOWN = '#ff4d6d', GRID = '#2a1622', TEXT = '#d8c8cf';

export function initTerminal({ $, esc, toast, navigate, receive }) {
  const bridge = window.quant?.market;
  let market = null;
  let symbol = 'SPY';
  let range = '6M';
  let chart = null, candles = null, volume = null, lastBar = null, chartIntraday = false;
  let quoteKey = '';
  let loadToken = 0;
  let moversLoaded = 0;
  let suggestTimer = null, suggestions = [], suggestIndex = -1;

  // ---- formatting ----
  const digits = value => value >= 1000 ? 2 : value >= 1 ? 2 : 4;
  const price = value => Number.isFinite(value) ? value.toLocaleString('en-US', { minimumFractionDigits: digits(value), maximumFractionDigits: digits(value) }) : '—';
  const signed = (value, d = 2) => Number.isFinite(value) ? (value > 0 ? '+' : '') + value.toFixed(d) : '—';
  const pct = value => Number.isFinite(value) ? (value > 0 ? '+' : '') + (value * 100).toFixed(2) + '%' : '—';
  const big = value => !Number.isFinite(value) ? '—' : value >= 1e9 ? (value / 1e9).toFixed(2) + 'B' : value >= 1e6 ? (value / 1e6).toFixed(2) + 'M' : value >= 1e3 ? (value / 1e3).toFixed(1) + 'K' : String(Math.round(value));
  const tone = value => !Number.isFinite(value) || value === 0 ? '' : value > 0 ? 'up' : 'down';
  const ago = iso => {
    const minutes = Math.round((Date.now() - Date.parse(iso)) / 60000);
    return minutes < 1 ? 'now' : minutes < 60 ? minutes + 'm' : minutes < 1440 ? Math.round(minutes / 60) + 'h' : Math.round(minutes / 1440) + 'd';
  };

  // Exchange time on the axis: shift UTC seconds by New York's offset at that moment.
  const offsetCache = new Map();
  const nyParts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  function nySeconds(iso) {
    const ms = Date.parse(iso);
    const hour = Math.floor(ms / 3_600_000);
    if (!offsetCache.has(hour)) {
      const p = Object.fromEntries(nyParts.formatToParts(new Date(hour * 3_600_000)).map(x => [x.type, x.value]));
      offsetCache.set(hour, Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - hour * 3_600_000);
    }
    return Math.floor((ms + offsetCache.get(hour)) / 1000);
  }
  const nyDate = iso => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

  // ---- chart ----
  function ensureChart() {
    if (chart) return;
    chart = createChart($('term-chart'), {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: TEXT, fontFamily: '"Cascadia Mono", Consolas, monospace', attributionLogo: false },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#3a1a28' },
      timeScale: { borderColor: '#3a1a28', rightOffset: 4 },
    });
    candles = chart.addSeries(CandlestickSeries, { upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN, borderVisible: false });
    volume = chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  }

  async function loadChart() {
    const token = ++loadToken;
    ensureChart();
    $('term-chart-note').textContent = 'Loading ' + symbol + ' · ' + range + '…';
    try {
      const result = await bridge.chart(symbol, range);
      if (token !== loadToken) return;
      chartIntraday = ['1D', '5D', '1M'].includes(range);
      const time = bar => chartIntraday ? nySeconds(bar.t) : nyDate(bar.t);
      const bars = result.bars.map(bar => ({ time: time(bar), open: bar.o, high: bar.h, low: bar.l, close: bar.c, volume: bar.v }));
      candles.setData(bars);
      volume.setData(bars.map(bar => ({ time: bar.time, value: bar.volume, color: bar.close >= bar.open ? '#35e0a155' : '#ff4d6d55' })));
      chart.timeScale().fitContent();
      lastBar = bars.at(-1) ?? null;
      const feed = result.feed === 'iex' ? 'IEX trades only' : result.feed === 'crypto' ? 'Alpaca crypto' : 'all US exchanges, split/dividend adjusted';
      $('term-chart-note').textContent = bars.length ? `${bars.length} ${result.timeframe} bars · ${feed} · times in New York` : 'No bars for this range (market closed or symbol not traded).';
    } catch (error) {
      if (token !== loadToken) return;
      candles.setData([]); volume.setData([]); lastBar = null;
      $('term-chart-note').textContent = error.message || String(error);
    }
  }

  /** Moves the latest candle with live trades (intraday ranges) so the chart is visibly live. */
  function liveCandle(row) {
    if (!chart || !lastBar || !chartIntraday || !Number.isFinite(row.last) || !row.time) return;
    const step = range === '1D' ? 60 : range === '5D' ? 300 : 3600;
    const t = nySeconds(row.time);
    if (t < lastBar.time) return;
    if (t >= lastBar.time + step) lastBar = { time: lastBar.time + Math.floor((t - lastBar.time) / step) * step, open: row.last, high: row.last, low: row.last, close: row.last };
    else lastBar = { ...lastBar, high: Math.max(lastBar.high, row.last), low: Math.min(lastBar.low, row.last), close: row.last };
    candles.update(lastBar);
  }

  // ---- symbol loading ----
  function setRange(next) {
    range = next;
    document.querySelectorAll('#term-ranges .seg').forEach(b => { const on = b.dataset.range === next; b.classList.toggle('active', on); b.setAttribute('aria-checked', String(on)); });
    void loadChart();
  }

  async function loadSymbol(next, focus) {
    symbol = next;
    $('term-symbol').textContent = symbol;
    const row = market?.quotes.find(q => q.symbol === symbol);
    $('term-name').textContent = row?.name || '';
    renderHeadline();
    void loadChart();
    void loadDescription();
    void loadNews(symbol);
    if (focus) document.querySelector('.' + focus)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  async function loadDescription() {
    const wanted = symbol;
    $('term-des').innerHTML = '<p class="term-note">Loading…</p>';
    try {
      const d = await bridge.describe(wanted);
      if (wanted !== symbol) return;
      if (d.asset?.name) $('term-name').textContent = d.asset.name + (d.asset.exchange ? ' · ' + d.asset.exchange : '');
      const s = d.snapshot || {}, day = s.dailyBar || {}, prev = s.prevDailyBar || {}, q = s.latestQuote || {};
      const last = s.latestTrade?.p ?? day.c;
      const spread = q.ap > 0 && q.bp > 0 ? (q.ap - q.bp) / ((q.ap + q.bp) / 2) * 1e4 : NaN;
      const position = Number.isFinite(d.yearHigh) && d.yearHigh > d.yearLow ? (last - d.yearLow) / (d.yearHigh - d.yearLow) : NaN;
      const dailyMove = Number.isFinite(d.vol20) ? d.vol20 / Math.sqrt(252) : NaN;
      const rows = [
        ['Open · prev', price(day.o) + ' · ' + price(prev.c)],
        ['Day range', price(day.l) + ' – ' + price(day.h)],
        ['Bid × size', price(q.bp) + ' × ' + big(q.bs)], ['Ask × size', price(q.ap) + ' × ' + big(q.as)],
        ['Spread', Number.isFinite(spread) ? spread.toFixed(1) + ' bps' : '—'],
        ['52 weeks', price(d.yearLow) + ' – ' + price(d.yearHigh) + (Number.isFinite(position) ? ' · ' + Math.round(position * 100) + '%' : '')],
        ['1-year return', pct(d.yearReturn)], ['Avg volume 30d', big(d.averageVolume)],
        ['Vol 20d · 60d · 1y', [d.vol20, d.vol60, d.vol252].map(v => Number.isFinite(v) ? (v * 100).toFixed(1) + '%' : '—').join(' · ')],
        ['Daily move (σ/√252)', Number.isFinite(dailyMove) ? '±' + (dailyMove * 100).toFixed(2) + '% ≈ ±' + price(last * dailyMove) : '—'],
      ];
      $('term-des').innerHTML = '<dl class="term-stats">' + rows.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>' +
        '<p class="term-note">Volatility from ' + d.bars + ' daily closes (all exchanges, adjusted). One standard deviation covers about two days in three.</p>';
    } catch (error) {
      if (wanted === symbol) $('term-des').innerHTML = '<p class="term-note">' + esc(error.message || String(error)) + '</p>';
    }
  }

  async function loadNews(forSymbol) {
    $('term-news-title').textContent = forSymbol ? forSymbol + ' news' : 'Market news';
    $('term-news').innerHTML = '<li class="term-note">Loading…</li>';
    try {
      const items = await bridge.news(forSymbol || undefined);
      $('term-news').innerHTML = items.length ? items.map(item => '<li><div class="term-news-meta"><time datetime="' + esc(item.created_at) + '">' + esc(ago(item.created_at)) + '</time> · ' + esc(item.source) +
        (item.symbols.length ? ' · ' + item.symbols.slice(0, 4).map(esc).join(' ') : '') + '</div>' +
        (item.url ? '<button type="button" class="term-headline" data-url="' + esc(item.url) + '">' + esc(item.headline) + '</button>' : '<span class="term-headline">' + esc(item.headline) + '</span>') +
        (item.summary ? '<p>' + esc(item.summary) + '</p>' : '') + '</li>').join('') : '<li class="term-note">No recent news.</li>';
    } catch (error) { $('term-news').innerHTML = '<li class="term-note">' + esc(error.message || String(error)) + '</li>'; }
  }

  async function loadMovers() {
    moversLoaded = Date.now();
    $('term-movers').innerHTML = '<p class="term-note">Loading…</p>';
    try {
      const m = await bridge.movers();
      const list = (title, rows, value) => '<div><h3>' + title + '</h3><ol>' + (rows.length ? rows.slice(0, 10).map(r => '<li><button type="button" class="term-sym" data-symbol="' + esc(r.symbol) + '">' + esc(r.symbol) + '</button><span class="' + value(r)[1] + '">' + esc(value(r)[0]) + '</span></li>').join('') : '<li class="term-note">—</li>') + '</ol></div>';
      $('term-movers').innerHTML = list('Most active', m.actives, r => [big(r.volume), '']) + list('Gainers', m.gainers, r => [signed(r.percent_change) + '%', 'up']) +
        list('Losers', m.losers, r => [signed(r.percent_change) + '%', 'down']) + (m.error ? '<p class="term-note">' + esc(m.error) + '</p>' : '');
      $('term-movers-time').textContent = 'updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (error) { $('term-movers').innerHTML = '<p class="term-note">' + esc(error.message || String(error)) + '</p>'; }
  }

  // ---- live rendering from market snapshots ----
  function renderHeadline() {
    const row = market?.quotes.find(q => q.symbol === symbol);
    $('term-last').textContent = row ? price(row.last) : '—';
    $('term-change').textContent = row && Number.isFinite(row.change) ? signed(row.change, row.last < 1 ? 4 : 2) + ' (' + pct(row.changePct) + ')' : '—';
    $('term-change').className = 'term-chg ' + tone(row?.change);
  }

  function renderQuotes() {
    const rows = market.quotes;
    const key = rows.map(r => r.symbol).join(',');
    const body = $('term-quotes');
    if (key !== quoteKey) {
      quoteKey = key;
      body.innerHTML = rows.map(r => '<tr data-symbol="' + esc(r.symbol) + '" tabindex="0"><th scope="row"><span class="term-sym">' + esc(r.symbol) + '</span><small></small></th><td class="num last"></td><td class="num chg"></td><td class="num vol"></td></tr>').join('');
    }
    for (const r of rows) {
      const tr = body.querySelector('tr[data-symbol="' + CSS.escape(r.symbol) + '"]');
      if (!tr) continue;
      tr.classList.toggle('selected', r.symbol === symbol);
      tr.querySelector('small').textContent = r.name ? r.name.slice(0, 26) : '';
      const last = tr.querySelector('.last');
      const text = price(r.last);
      if (last.textContent !== text && last.textContent !== '' && last.textContent !== '—') {
        last.classList.remove('flash-up', 'flash-down');
        void last.offsetWidth;  // Restart the flash animation.
        last.classList.add(r.direction >= 0 ? 'flash-up' : 'flash-down');
      }
      last.textContent = text;
      const chg = tr.querySelector('.chg');
      chg.textContent = pct(r.changePct);
      chg.className = 'num chg ' + tone(r.changePct);
      tr.querySelector('.vol').textContent = big(r.volume);
    }
    const feed = market.feed === 'iex' ? 'IEX' : market.feed === 'delayed_sip' ? 'all exchanges, 15 min delayed' : 'all exchanges';
    $('term-watch-note').textContent = market.configured ? 'Stocks: ' + feed + (market.feed === 'iex' ? ' (volume is IEX only)' : '') + ' · crypto: Alpaca' : 'Crypto updates every 15 s without keys. Add Alpaca keys for stocks.';
  }

  function renderStatus() {
    const pill = $('term-stream');
    const s = market.stream.status;
    const [text, cls] = market.demo ? ['DEMO DATA · SYNTHETIC', 'warn'] : !market.configured ? ['NO KEYS · CRYPTO ONLY', 'off'] : s === 'live' ? ['● LIVE · ' + (market.feed === 'iex' ? 'IEX' : market.feed === 'sip' ? 'SIP' : 'DELAYED'), 'live'] :
      s === 'busy' ? ['SNAPSHOTS · 15 s', 'warn'] : s === 'connecting' ? ['CONNECTING…', 'warn'] : s === 'error' ? ['STREAM ERROR', 'error'] : ['SNAPSHOTS', 'warn'];
    pill.textContent = text;
    pill.className = 'term-pill ' + cls;
    pill.title = market.stream.detail || market.lastError || '';
    $('term-connect').classList.toggle('hidden', market.configured);
    document.body.classList.toggle('market-demo', Boolean(market.demo));
  }

  function renderClock() {
    const clock = market?.clock;
    if (!clock) { $('term-clock').textContent = 'US market —'; return; }
    const target = Date.parse(clock.is_open ? clock.next_close : clock.next_open) - Date.now();
    const h = Math.max(0, Math.floor(target / 3_600_000)), m = Math.max(0, Math.floor(target / 60_000) % 60), sec = Math.max(0, Math.floor(target / 1000) % 60);
    const span = h >= 24 ? Math.floor(h / 24) + 'd ' + (h % 24) + 'h' : h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
    $('term-clock').textContent = clock.is_open ? 'US market OPEN · closes in ' + span : 'US market CLOSED · opens in ' + span;
    $('term-clock').className = 'term-clock ' + (clock.is_open ? 'open' : '');
  }

  function sparkline(history) {
    if (history.length < 2) return '';
    const values = history.map(h => h[1]), low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
    const points = values.map((v, i) => (i / (values.length - 1) * 100).toFixed(1) + ',' + (28 - (v - low) / span * 26).toFixed(1)).join(' ');
    return '<svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><polyline points="' + points + '"/></svg>';
  }

  function renderMacro() {
    if (!market.macro.length) { $('term-macro').innerHTML = '<p class="term-note">Loading FRED data…</p>'; return; }
    $('term-macro').innerHTML = market.macro.map(p => {
      const value = Number.isFinite(p.value) ? p.value.toFixed(p.decimals) + (p.unit === '%' || p.unit === 'pp' ? (p.unit === '%' ? '%' : ' pp') : '') : '—';
      const extra = p.id === 'VIXCLS' && Number.isFinite(p.value) ? '<small>÷ 16 ≈ ±' + (p.value / 16).toFixed(2) + '% a day for the S&amp;P 500</small>' : '';
      return '<div class="term-tile"><span class="label">' + esc(p.label) + '</span><span class="value">' + esc(value) + '</span><span class="' + tone(p.change) + '">' +
        (Number.isFinite(p.change) ? signed(p.change, p.decimals) : '') + '</span>' + sparkline(p.history) + extra + '<small>' + esc(p.date || 'unavailable') + '</small></div>';
    }).join('');
    const dates = market.macro.map(p => p.date).filter(Boolean).sort();
    $('term-macro-date').textContent = 'FRED · latest ' + (dates.at(-1) || '—');
  }

  function renderMarket(next) {
    const symbolsChanged = !market || market.watchlist.join() !== next.watchlist.join();
    const macroChanged = !market || market.macroUpdated !== next.macroUpdated;
    market = next;
    renderQuotes();
    renderStatus();
    renderHeadline();
    renderClock();
    if (macroChanged) renderMacro();
    const row = market.quotes.find(q => q.symbol === symbol);
    if (row) liveCandle(row);
    if (symbolsChanged && !market.watchlist.includes(symbol) && market.watchlist.length && !chart) symbol = market.watchlist[0];
    renderSettings();
  }

  // ---- Preferences: keys ----
  function renderSettings() {
    if (!market) return;
    $('alpaca-badge').textContent = market.configured ? 'CONNECTED ' + market.keyHint : 'NOT CONNECTED';
    $('alpaca-badge').className = 'tag ' + (market.configured ? '' : 'neutral');
    if (document.activeElement !== $('alpaca-feed')) $('alpaca-feed').value = market.feed;
    $('alpaca-clear').disabled = !market.configured;
  }
  $('alpaca-form').addEventListener('submit', async event => {
    event.preventDefault();
    const keyId = $('alpaca-key-id').value, secret = $('alpaca-secret').value, feed = $('alpaca-feed').value;
    $('alpaca-status').textContent = 'Testing the keys with Alpaca…';
    $('alpaca-save').disabled = true;
    try {
      renderMarket(await bridge.setKeys(keyId, secret, feed));
      $('alpaca-key-id').value = ''; $('alpaca-secret').value = '';
      $('alpaca-status').textContent = 'Connected. The keys are stored encrypted on this computer.';
      void loadSymbol(symbol);
    } catch (error) { $('alpaca-status').textContent = error.message || String(error); }
    finally { $('alpaca-save').disabled = false; }
  });
  $('alpaca-clear').addEventListener('click', async () => {
    try { renderMarket(await bridge.clearKeys()); $('alpaca-status').textContent = 'Keys removed from this computer.'; }
    catch (error) { $('alpaca-status').textContent = error.message || String(error); }
  });
  $('alpaca-help').addEventListener('click', () => { void bridge.openLink('https://alpaca.markets/').catch(e => toast(e.message, true)); });
  $('term-tv-link').addEventListener('click', () => { void bridge.openLink('https://www.tradingview.com/').catch(e => toast(e.message, true)); });
  $('term-connect-open').addEventListener('click', () => { navigate('preferences'); $('alpaca-key-id').focus(); });

  // ---- commands ----
  async function updateWatchlist(list, message) {
    try { renderMarket(await bridge.setWatchlist(list)); toast(message); }
    catch (error) { toast(error.message || String(error), true); }
  }

  async function research(symbols) {
    const stocks = symbols.filter(s => !s.includes('/')).slice(0, 20);
    if (!stocks.length) { toast('Choose at least one stock or ETF symbol.', true); return; }
    toast('Downloading 5 years of daily prices for ' + stocks.join(', ') + '…');
    try {
      const state = await bridge.dataset(stocks, 5);
      receive(state);
      navigate('monitor');
      receive(await window.quant.runOnce());
      toast('Dataset saved and analysed. It stays up to date while the engine runs.');
    } catch (error) { toast(error.message || String(error), true); }
  }

  async function surface(forSymbol) {
    toast('Fetching the ' + forSymbol + ' option chain and fitting the surface…');
    try {
      receive(await bridge.surface(forSymbol));
      navigate('options');
      document.querySelector('.surface-panel')?.scrollIntoView({ block: 'start' });
      toast('Market volatility surface for ' + forSymbol + ' fitted.');
    } catch (error) { toast(error.message || String(error), true); }
  }

  function run(text) {
    const words = String(text).trim().toUpperCase().split(/\s+/).filter(Boolean);
    if (!words.length) return;
    const [first, ...rest] = words;
    if (!market) { toast('Market data is still starting.', true); return; }
    if (first === 'HELP' || first === '?') { $('term-help').classList.remove('hidden'); return; }
    if (first === 'ADD' || first === 'W+') { void updateWatchlist([...market.watchlist, ...rest], 'Added ' + rest.join(', ') + '.'); return; }
    if (first === 'DEL' || first === 'W-') { void updateWatchlist(market.watchlist.filter(s => !rest.includes(s)), 'Removed ' + rest.join(', ') + '.'); return; }
    if (first === 'RESEARCH') { void research(rest.length ? rest : market.watchlist); return; }
    if (RANGES.includes(first)) { setRange(first); return; }
    if (first === 'MOST' || first === 'MOVERS') { void loadMovers(); document.querySelector('.term-movers').scrollIntoView({ block: 'nearest' }); return; }
    if (first === 'ECO' || first === 'WEI') { document.querySelector('.term-macro').scrollIntoView({ block: 'nearest' }); return; }
    if (first === 'NEWS' || (first === 'N' && !rest.length)) { void loadNews(null); return; }
    const target = FUNCTIONS.has(first) ? symbol : first;
    const fn = FUNCTIONS.has(first) ? first : rest[0];
    if (!/^[A-Z][A-Z0-9.-]{0,9}$|^[A-Z0-9]{2,10}\/(USD|USDT|USDC|BTC)$/.test(target)) { toast('Unknown command or symbol: ' + text + '. Type HELP.', true); return; }
    if (fn === 'OMON' || fn === 'OVDV' || fn === 'VOL') { void surface(target); return; }
    if (fn === 'N' || fn === 'NEWS') { if (target !== symbol) void loadSymbol(target); else void loadNews(target); return; }
    if (fn && RANGES.includes(fn)) { range = fn; setRange(fn); }
    void loadSymbol(target, fn === 'DES' ? 'term-detail' : 'term-chart-panel');
  }

  // ---- suggestions ----
  function showSuggestions(list) {
    suggestions = list; suggestIndex = -1;
    const box = $('term-suggest');
    box.innerHTML = list.map((s, i) => '<li role="option" id="term-opt-' + i + '" data-symbol="' + esc(s.symbol) + '"><strong>' + esc(s.symbol) + '</strong> ' + esc(s.name) + '<span>' + esc(s.exchange) + '</span></li>').join('');
    box.classList.toggle('hidden', !list.length);
    $('term-input').setAttribute('aria-expanded', String(list.length > 0));
  }
  $('term-input').addEventListener('input', () => {
    clearTimeout(suggestTimer);
    const text = $('term-input').value.trim();
    if (!text || text.includes(' ') || !bridge) { showSuggestions([]); return; }
    suggestTimer = setTimeout(async () => { try { showSuggestions(await bridge.search(text)); } catch { showSuggestions([]); } }, 120);
  });
  $('term-input').addEventListener('keydown', event => {
    if (!suggestions.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      suggestIndex = (suggestIndex + (event.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length;
      document.querySelectorAll('#term-suggest li').forEach((li, i) => li.setAttribute('aria-selected', String(i === suggestIndex)));
      $('term-input').setAttribute('aria-activedescendant', 'term-opt-' + suggestIndex);
    } else if (event.key === 'Escape') showSuggestions([]);
  });
  $('term-suggest').addEventListener('mousedown', event => {
    const li = event.target.closest('li');
    if (!li) return;
    event.preventDefault();
    $('term-input').value = ''; showSuggestions([]);
    run(li.dataset.symbol);
  });
  $('term-form').addEventListener('submit', event => {
    event.preventDefault();
    const text = suggestIndex >= 0 ? suggestions[suggestIndex].symbol : $('term-input').value;
    $('term-input').value = ''; showSuggestions([]);
    run(text);
  });

  // ---- clicks ----
  document.querySelectorAll('.term-key').forEach(b => b.addEventListener('click', () => run(b.dataset.cmd)));
  document.querySelectorAll('#term-ranges .seg').forEach(b => b.addEventListener('click', () => setRange(b.dataset.range)));
  $('term-help-close').addEventListener('click', () => $('term-help').classList.add('hidden'));
  $('term-quotes').addEventListener('click', event => { const tr = event.target.closest('tr'); if (tr) void loadSymbol(tr.dataset.symbol); });
  $('term-quotes').addEventListener('keydown', event => { const tr = event.target.closest('tr'); if (tr && event.key === 'Enter') void loadSymbol(tr.dataset.symbol); });
  $('term-movers').addEventListener('click', event => { const b = event.target.closest('[data-symbol]'); if (b) void loadSymbol(b.dataset.symbol); });
  $('term-news').addEventListener('click', event => {
    const b = event.target.closest('[data-url]');
    if (b) void bridge.openLink(b.dataset.url).catch(e => toast(e.message, true));
  });
  $('term-surface').addEventListener('click', () => run(symbol + ' OMON'));
  $('term-research').addEventListener('click', () => run('RESEARCH'));
  document.addEventListener('keydown', event => {
    // "/" focuses the command line from anywhere on the terminal (like a terminal's command key).
    if (event.key === '/' && document.activeElement?.tagName !== 'INPUT' && !$('page-terminal').classList.contains('hidden')) { event.preventDefault(); $('term-input').focus(); }
  });
  setInterval(() => { if (!$('page-terminal').classList.contains('hidden')) renderClock(); }, 1000);

  if (!bridge) return { shown() {} };
  bridge.onUpdate(renderMarket);
  const ready = bridge.state().then(state => {
    renderMarket(state);
    // Without keys only crypto has data, so start on the first crypto symbol.
    symbol = state.configured ? state.watchlist[0] || 'SPY' : state.watchlist.find(s => s.includes('/')) || 'BTC/USD';
  }).catch(error => toast(error.message, true));

  let started = false;
  return {
    /** Called whenever the Terminal page becomes visible. */
    async shown() {
      await ready;
      if (!started) { started = true; void loadSymbol(symbol); }
      if (market?.configured && Date.now() - moversLoaded > 300_000) void loadMovers();
      if (!market?.configured && !moversLoaded) { moversLoaded = Date.now(); $('term-movers').innerHTML = '<p class="term-note">Add Alpaca keys to see the most active stocks and the day\'s movers.</p>'; }
    },
  };
}
