// Strategies page: go/no-go ladder, strategy lab (stages 1–2) and paper trading (stage 3).
const NAMES = { trend: 'Trend + volatility target', sectors: 'Sector momentum', quality: 'Quality (most profitable companies)', ensemble: 'Diversified ensemble', multifactor: 'Multi-factor (quality + value + momentum)' };
const GATE_LABELS = { deflated_sharpe: 'Survives the multiple-testing correction', newey_west: 'Edge over the benchmark is significant',
  walk_forward: 'Beats the benchmark out of sample', holdout: 'Holds up in the last 10 years', robust: 'Most parameter choices beat the benchmark' };

export function initStrategies({ $, esc, toast, receive }) {
  const desk = window.quant?.desk;
  if (!desk) return { shown() {} };
  let state = null;
  let confirming = false;
  const pct = (v, d = 1) => Number.isFinite(v) ? (v * 100).toFixed(d) + '%' : '—';
  const num = (v, d = 2) => Number.isFinite(v) ? v.toFixed(d) : '—';
  const money = v => Number.isFinite(Number(v)) ? '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—';

  async function act(call, success) {
    try { const next = await call(); if (next) render(next); if (success) toast(success); return true; }
    catch (error) { toast(error.message || String(error), true); return false; }
  }

  function renderLadder() {
    const l = state.ladder;
    const card = (n, title, s, locked, failed) => '<div class="ladder-step ' + (s.done ? 'done' : locked ? 'locked' : failed ? 'failed' : '') + '"><span class="ladder-n">' + n + '</span><div><strong>' + title +
      '</strong><span class="ladder-state">' + (s.done ? 'PASSED' : locked ? 'LOCKED' : failed ? 'NO-GO' : 'NOT YET') + '</span><small>' + esc(s.detail) + '</small></div></div>';
    $('ladder').innerHTML = card(1, 'Fixed rules', l.stage1) + card(2, 'Backtest gates', l.stage2, false, Boolean(state.lab)) + card(3, 'Paper trading', l.stage3) +
      card(4, 'Small real money', l.stage4, !(l.stage2.done && l.stage3.done));
  }

  function specCurve(r) {
    const values = r.variants.map(v => v.sharpe), bench = r.benchmark_excess_sharpe;
    const lo = Math.min(0, ...values, bench), hi = Math.max(...values, bench) * 1.1 || 1;
    const y = v => 60 - (v - lo) / (hi - lo) * 56;
    const w = 300 / values.length;
    const bars = values.map((v, i) => '<rect x="' + (i * w + 1).toFixed(1) + '" y="' + Math.min(y(v), y(0)).toFixed(1) + '" width="' + Math.max(1, w - 2).toFixed(1) +
      '" height="' + Math.max(1, Math.abs(y(v) - y(0))).toFixed(1) + '" fill="' + (v > bench ? '#35e0a1' : '#ff4d6d') + '"/>').join('');
    return '<svg class="spec-curve" viewBox="0 0 300 64" preserveAspectRatio="none" role="img" aria-label="Sharpe ratio of every parameter variant against the benchmark">' + bars +
      '<line x1="0" x2="300" y1="' + y(bench).toFixed(1) + '" y2="' + y(bench).toFixed(1) + '" stroke="#ffb347" stroke-dasharray="4 3"/></svg>';
  }

  function renderLab() {
    const lab = state.lab;
    if (!lab) return;
    $('lab-meta').textContent = 'Data ' + lab.data.first + ' to ' + lab.data.last + ' (' + lab.data.days.toLocaleString() + ' days) · rules registered ' + lab.registration.date +
      (lab.registration.extra ? ' (quality and ensemble ' + lab.registration.extra + ')' : '') + (lab.registration.multifactor ? ' (multi-factor ' + lab.registration.multifactor + ')' : '') + ' · gates v' + lab.registration.gates_version + ' · hash ' + lab.registration.hash.slice(0, 12) + (lab.completed_at ? ' · run ' + new Date(lab.completed_at).toLocaleString() : '');
    $('lab-results').innerHTML = Object.values(lab.results).map(r => {
      const rows = [
        ['Sharpe (after costs)', num(r.excess_sharpe), num(r.benchmark_excess_sharpe)],
        ['Annual return', pct(r.summary.annual_return), pct(r.benchmark_summary.annual_return)],
        ['Worst fall (max drawdown)', pct(r.summary.max_drawdown), pct(r.benchmark_summary.max_drawdown)],
        ['Last 10 years Sharpe', num(r.holdout.sharpe), num(r.holdout.benchmark_sharpe)],
        ['Walk-forward Sharpe (from ' + (r.walk_forward.from || '—').slice(0, 4) + ')', num(r.walk_forward.sharpe), num(r.walk_forward.benchmark_sharpe)],
        ['Annual return at the market\'s risk', pct(r.return_at_benchmark_risk), pct(r.benchmark_summary.annual_return)],
      ];
      if (r.reference_60_40) rows.push(['60/40 stocks/bonds (reference)', pct(r.reference_60_40.summary.annual_return) + ' · ' + pct(r.reference_60_40.summary.max_drawdown), '']);
      return '<div class="lab-card"><div class="lab-head"><h3>' + esc(NAMES[r.family] || r.family) + '</h3><span class="tag ' + (r.go_to_paper ? '' : 'neutral') + '">' +
        (r.go_to_paper ? 'GO TO PAPER' : 'NO-GO') + '</span></div><p class="term-note">Primary rule ' + esc(r.primary) + ' · benchmark: ' + esc(r.benchmark) +
        ' · data from ' + esc(r.period[0]) + (r.max_exposure > 1.001 ? ' · borrows up to ' + pct(r.max_exposure - 1, 0) + ' at the risk-free rate + 2.5%' : '') + '</p>' +
        '<table class="term-table"><thead><tr><th scope="col"></th><th scope="col" class="num">Strategy</th><th scope="col" class="num">Benchmark</th></tr></thead><tbody>' +
        rows.map(([k, a, b]) => '<tr><th scope="row">' + esc(k) + '</th><td class="num">' + a + '</td><td class="num">' + b + '</td></tr>').join('') + '</tbody></table>' +
        '<p class="term-note">Chance its Sharpe really beats the benchmark: <strong>' + pct(r.sharpe_vs_benchmark.p_better, 0) + '</strong> (95% range of the difference ' +
        num(r.sharpe_vs_benchmark.ci95[0]) + ' to ' + num(r.sharpe_vs_benchmark.ci95[1]) + ') · deflated Sharpe ' + num(r.deflated.dsr, 3) + ' · t-stat ' + num(r.newey_west_active.t) + '</p>' +
        specCurve(r) + '<p class="term-note">Each bar is one of ' + r.variants.length + ' parameter choices; green beats the benchmark (dashed line).</p>' +
        '<ul class="checks">' + Object.entries(r.gates).map(([k, ok]) => '<li class="' + (ok ? 'pass' : 'fail') + '"><span>' + (ok ? '✓' : '✗') + '</span>' + esc(GATE_LABELS[k] || k) + '</li>').join('') + '</ul></div>';
    }).join('') + '<p class="term-note lab-foot">All of these ideas are well published, and industry momentum was already examined on this data earlier, so the last 10 years are not a pristine test. Later strategies are judged against all ' + (lab.registration.total_trials || '') + ' variants tried so far. Forward paper trading is the only clean test.</p>';
  }

  function renderEtf() {
    const check = state.etfCheck;
    if (!check) return;
    const rows = Object.entries(check.results || {}).map(([family, r]) => {
      const better = (a, b) => a > b ? 'up' : a < b ? 'down' : '';
      const cell = (a, b, f) => '<td class="num"><span class="' + better(a, b) + '">' + f(a) + '</span><div class="run-subline">SPY ' + f(b) + '</div></td>';
      return '<tr><th scope="row">' + esc(NAMES[family] || family) + '<div class="run-subline">' + esc(r.symbols.slice(family === 'trend' ? 0 : 1).join(' ')) + '</div></th>' +
        '<td>' + esc(r.from.slice(0, 7)) + '<div class="run-subline">to ' + esc(r.to) + '</div></td>' +
        cell(r.rule.annual_return, r.spy.annual_return, pct) + cell(r.rule.sharpe, r.spy.sharpe, num) + cell(r.rule.max_drawdown, r.spy.max_drawdown, pct) +
        cell(r.rule.growth_of_10000, r.spy.growth_of_10000, money) + '<td class="num">' + r.beat_spy_years + ' of ' + r.full_years + '</td></tr>';
    }).join('');
    const failed = Object.entries(check.errors || {}).map(([family, message]) => '<li>' + esc(NAMES[family] || family) + ': ' + esc(message) + '</li>').join('');
    $('etf-results').innerHTML = (rows ? '<table class="term-table"><thead><tr><th scope="col">Strategy (ETFs)</th><th scope="col">Since</th><th scope="col" class="num">Annual return</th>' +
      '<th scope="col" class="num">Sharpe</th><th scope="col" class="num">Worst fall</th><th scope="col" class="num">$10,000 became</th><th scope="col" class="num">Years ahead of SPY</th></tr></thead><tbody>' +
      rows + '</tbody></table>' : '') + (failed ? '<ul class="term-note">' + failed + '</ul>' : '') +
      '<p class="term-note">Run ' + esc(new Date(check.run_at).toLocaleString()) + '. Each strategy starts when all its ETFs have prices and its rule has enough history; SPY is measured over exactly the same days. 10 bps trading cost per trade; cash earns today\'s rate. Past results on a few years of data are noisy evidence, not a forecast.</p>';
  }

  function renderPaper() {
    const s = state.settings;
    const go = state.lab?.go_to_paper?.[s.strategy];
    $('paper-badge').textContent = s.killSwitch ? 'KILL SWITCH ON' : s.enabled ? 'PAPER · ' + s.strategy.toUpperCase() : 'OFF';
    $('paper-badge').className = 'tag ' + (s.enabled && !s.killSwitch ? '' : 'neutral');
    const form = document.activeElement?.closest?.('#paper-form');
    if (!form) {
      $('paper-enabled').checked = s.enabled; $('paper-strategy').value = s.strategy;
      $('limit-order').value = +(s.limits.maxOrderFraction * 100).toFixed(1); $('limit-orders').value = s.limits.maxOrdersPerDay;
      $('limit-loss').value = +(s.limits.dailyLossStop * 100).toFixed(2); $('limit-min').value = s.limits.minOrderNotional;
      $('limit-gross').value = Math.round((s.limits.maxGrossExposure ?? 1) * 100);
      $('paper-daily').checked = s.dailyUpdate !== false; $('paper-notify').checked = s.notify !== false;
      $('paper-daily-time').value = s.dailyTime || '06:00'; $('paper-daily-zone').value = s.dailyZone || 'Asia/Shanghai';
    }
    renderRefreshed();
    $('paper-kill').textContent = s.killSwitch ? 'Turn kill switch off' : 'Kill switch';
    $('paper-kill').setAttribute('aria-pressed', String(s.killSwitch));
    const warning = go === false ? 'This strategy did not pass the backtest gates. Paper trading it is for learning and tracking only; it is not evidence of an edge.' :
      go === undefined ? 'Run the strategy lab first so you know whether this strategy passed its backtest gates.' : '';
    $('paper-warning').textContent = warning;
    $('paper-warning').classList.toggle('hidden', !warning);
    const a = state.account;
    $('paper-account').innerHTML = a ? [['Equity', money(a.equity)], ['Cash', money(a.cash)], ['Today', pct(Number(a.equity) / Number(a.last_equity) - 1, 2)],
      ['Status', a.status + (a.trading_blocked ? ' · blocked' : '')]].map(([k, v]) => '<dt>' + k + '</dt><dd>' + esc(v) + '</dd>').join('') :
      '<dt>Status</dt><dd>' + esc(state.lastError || 'Not loaded. Add paper keys in Preferences, enable paper trading, then Refresh.') + '</dd>';
    $('paper-positions').innerHTML = state.positions.length ? state.positions.map(p => '<tr><th scope="row">' + esc(p.symbol) + '</th><td class="num">' + esc(p.qty) + '</td><td class="num">' +
      money(p.market_value) + '</td><td class="num ' + (Number(p.unrealized_pl) >= 0 ? 'up' : 'down') + '">' + money(p.unrealized_pl) + '</td></tr>').join('') : '<tr><td colspan="4" class="term-note">No positions.</td></tr>';
    const p = state.proposal;
    $('paper-submit').disabled = !p || !p.orders.length || !s.enabled || s.killSwitch;
    if (!p) { if (!confirming) $('paper-submit').textContent = 'Submit to paper account'; }
    $('paper-proposal').innerHTML = p ? '<p class="term-note">Signal from closes up to ' + esc(p.asOf) + ' · targets ' + esc(Object.entries(p.targets).map(([k, v]) => k + ' ' + pct(v)).join(', ') || 'all cash') +
      ' · equity ' + money(p.equity) + '</p>' + (p.orders.length ? '<table class="term-table"><thead><tr><th scope="col">Side</th><th scope="col">Symbol</th><th scope="col" class="num">Shares</th><th scope="col" class="num">≈ Value</th><th scope="col">Why</th></tr></thead><tbody>' +
      p.orders.map(o => '<tr><td class="' + (o.side === 'buy' ? 'up' : 'down') + '">' + o.side.toUpperCase() + '</td><th scope="row">' + esc(o.symbol) + '</th><td class="num">' + o.qty + '</td><td class="num">' + money(o.notional) + '</td><td>' + esc(o.reason) + '</td></tr>').join('') +
      '</tbody></table>' : '<p class="term-note">No orders needed: the paper account already matches the targets.</p>') + (p.blocked.length ? '<p class="paper-warning">' + p.blocked.map(esc).join('<br>') + '</p>' : '') :
      '<p class="term-note">The rule uses the latest daily closes; orders are market orders for whole shares (filled now if the market is open, otherwise at the next open).</p>';
    const c = state.stage3?.checks;
    $('paper-checks').innerHTML = c ? Object.entries(c).map(([k, v]) => '<li class="' + (v.pass ? 'pass' : 'fail') + '"><span>' + (v.pass ? '✓' : '·') + '</span>' + esc(v.detail) + '</li>').join('') :
      '<li class="fail"><span>·</span>Starts with the first paper account reading.</li>';
    $('paper-journal').innerHTML = state.journal.map(e => '<li><time>' + esc(new Date(e.at).toLocaleString()) + '</time> <strong>' + esc(e.type) + '</strong> ' +
      esc(e.symbol ? e.side + ' ' + e.qty + ' ' + e.symbol + ' (' + (e.status || e.error) + ')' : e.problems ? e.problems.join(' ') : e.type === 'reconcile' ? (e.ok ? 'matches plan' : 'DIFFERENCES: ' + JSON.stringify(e.differences)) : e.type === 'kill-switch' ? (e.on ? 'on' : 'off') :
        e.type === 'strategy' ? (NAMES[e.from] || e.from) + ' → ' + (NAMES[e.to] || e.to) + ' (the paper test restarts at the first trade)' :
        e.type === 'equity-closes' ? e.replaced + ' readings replaced and ' + e.removed + ' removed by official closes (kept in equity-replaced.jsonl)' :
        e.type === 'enabled' || e.type === 'disabled' ? (NAMES[e.strategy] || e.strategy || '') : '') + '</li>').join('') || '<li class="term-note">Empty.</li>';
  }

  const TRIGGERS = { manual: 'by you', scheduled: 'scheduled daily update', startup: 'when the app opened', automatic: 'automatically' };
  const ZONES = { 'Asia/Shanghai': 'Beijing time', 'America/New_York': 'New York time', 'Europe/London': 'London time',
    'Europe/Berlin': 'Central European time', 'Asia/Tokyo': 'Tokyo time', 'Australia/Sydney': 'Sydney time' };
  let shownRefresh = null;
  /** "Last refreshed" line under the account; it flashes whenever a new refresh lands, whoever started it. */
  function renderRefreshed() {
    const r = state.lastRefresh, s = state.settings;
    const next = s.enabled && s.dailyUpdate !== false ? ' · next automatic update ' + (s.dailyTime || '06:00') + ' ' + (ZONES[s.dailyZone] || 'Beijing time') : '';
    const el = $('paper-refreshed');
    el.textContent = r ? (r.ok ? '✓ Refreshed ' : '✕ Refresh failed ') + new Date(r.at).toLocaleTimeString() + ' (' + (TRIGGERS[r.trigger] || r.trigger) + ')' + next
      : 'Not refreshed yet' + next;
    el.classList.toggle('failed', Boolean(r && !r.ok));
    if (r && r.at !== shownRefresh) {
      if (shownRefresh !== null) { el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
      shownRefresh = r.at;
    }
  }

  function renderBrief() {
    const b = state.brief;
    if (!b) return;
    const signed = v => Number.isFinite(v) ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '—';
    const tile = (label, value, cls = '') => '<div class="brief-tile"><span class="label">' + esc(label) + '</span><span class="value ' + cls + '">' + esc(value) + '</span></div>';
    const tone = v => !Number.isFinite(v) || v === 0 ? '' : v > 0 ? 'up' : 'down';
    $('paper-brief').innerHTML = tile('Equity', money(b.equity)) + tile('Today', signed(b.day_change), tone(b.day_change)) +
      tile('Since ' + (b.since || 'start'), signed(b.since_start), tone(b.since_start)) + tile('SPY, same days', signed(b.spy_since_start), tone(b.spy_since_start)) +
      tile('The rule, simulated', signed(b.rule_since_start), tone(b.rule_since_start)) + tile('Next rebalance', b.next_rebalance || '—') +
      tile('Orders proposed', b.orders_needed === null ? '—' : String(b.orders_needed)) + tile('Stage 3', b.stage3 || '—') +
      '<p class="term-note brief-foot">Updated ' + esc(new Date(b.updated).toLocaleString()) + (b.trigger ? ' (' + esc(TRIGGERS[b.trigger] || b.trigger) + ')' : '') + ' · ' + esc(NAMES[b.strategy] || b.strategy) + ' · ' + b.days + ' days recorded' +
      (b.backfilled ? ' · ' + b.backfilled + ' missed days filled from Alpaca' : '') + (b.signal_error ? ' · rule check failed: ' + esc(b.signal_error) : '') +
      (b.orders_needed ? ' · <strong>orders are waiting for your approval below</strong>' : '') + '</p>';
  }

  function render(next) {
    state = next;
    renderLadder();
    renderLab();
    renderPaper();
    renderBrief();
    renderEtf();
  }

  $('lab-run').addEventListener('click', async () => {
    $('lab-run').disabled = true; $('lab-run').textContent = 'Running…';
    await act(() => desk.runLab(), 'Strategy lab finished.');
    $('lab-run').disabled = false; $('lab-run').textContent = 'Run strategy lab';
  });
  $('paper-form').addEventListener('submit', event => {
    event.preventDefault();
    void act(() => desk.configure({ enabled: $('paper-enabled').checked, strategy: $('paper-strategy').value, killSwitch: state.settings.killSwitch,
      limits: { maxOrderFraction: Number($('limit-order').value) / 100, maxOrdersPerDay: Number($('limit-orders').value),
        dailyLossStop: Number($('limit-loss').value) / 100, minOrderNotional: Number($('limit-min').value),
        maxGrossExposure: Number($('limit-gross').value) / 100 }, dailyUpdate: $('paper-daily').checked, notify: $('paper-notify').checked,
      dailyTime: $('paper-daily-time').value, dailyZone: $('paper-daily-zone').value }), 'Paper settings saved.');
  });
  $('paper-kill').addEventListener('click', () => { void act(() => desk.kill(!state.settings.killSwitch), state.settings.killSwitch ? 'Kill switch off.' : 'Kill switch on: open paper orders cancelled.'); });
  // Manual refresh: the button shows progress, then a message says exactly what was read and when.
  $('paper-refresh').addEventListener('click', async () => {
    const button = $('paper-refresh');
    button.disabled = true; button.textContent = 'Refreshing…';
    await act(() => desk.refresh());
    button.disabled = false; button.textContent = 'Refresh ↻';
    const r = state.lastRefresh;
    if (r?.ok) toast('Paper account refreshed at ' + new Date(r.at).toLocaleTimeString() + (r.equity !== null ? ' · equity ' + money(r.equity) : '') + '.');
    else if (r) toast('Refresh failed: ' + (r.error || 'unknown error'), true);
  });
  $('paper-daily-now').addEventListener('click', async () => {
    const button = $('paper-daily-now');
    button.disabled = true; button.textContent = 'Updating…';
    const ok = await act(() => desk.daily());
    button.disabled = false; button.textContent = 'Update now ↻';
    if (ok && state.brief) toast('Daily update recorded at ' + new Date(state.brief.updated).toLocaleTimeString() + ' · equity ' + money(state.brief.equity) + '.');
  });
  $('etf-run').addEventListener('click', async () => {
    const button = $('etf-run');
    button.disabled = true; button.textContent = 'Replaying on real ETFs…';
    await act(() => desk.etfCheck(), 'Tradable check finished.');
    button.disabled = false; button.textContent = 'Run tradable check';
  });
  $('paper-export').addEventListener('click', async () => {
    try {
      const saved = await desk.exportProgress();
      if (saved?.path) toast('Progress saved to ' + saved.path + '. It holds no keys, so it is safe to back up or share.');
    } catch (error) { toast(error.message, true); }
  });
  $('paper-propose').addEventListener('click', async () => {
    confirming = false;
    $('paper-propose').disabled = true; $('paper-propose').textContent = 'Computing…';
    await act(() => desk.propose());
    $('paper-propose').disabled = false; $('paper-propose').textContent = "Compute today's orders";
  });
  // Two-step approval: the first click arms, the second submits.
  $('paper-submit').addEventListener('click', async () => {
    const p = state.proposal;
    if (!p) return;
    if (!confirming) { confirming = true; $('paper-submit').textContent = 'Confirm: send ' + p.orders.length + ' paper orders'; $('paper-submit').classList.add('danger'); return; }
    confirming = false; $('paper-submit').classList.remove('danger');
    await act(() => desk.submit(p.id), 'Paper orders sent and journaled.');
  });

  desk.onUpdate(render);
  desk.state().then(render).catch(error => toast(error.message, true));
  return { shown() { if (state?.settings.enabled && !state.account) void act(() => desk.refresh()); } };
}
