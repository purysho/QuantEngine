'use strict';
// Authored renderer source; packaging/build.mjs emits app/ui.js.

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const percent = (value, digits = 2) => Number.isFinite(value) ? (value * 100).toFixed(digits) + '%' : '—';
const number = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const integer = value => Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
const shortTime = value => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const fullTime = value => value ? new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
let current = { state: { phase: 'paused', busy: false, continuous: false, completed: 0 }, config: {}, datasets: [], runs: [], report: null, options: null, runtime: {} };
let chartMode = 'equity';
let page = 'monitor';
let operation = false;
let previousReport;
let previousRuns;
let previousOptions;
let datasetKey = '';
let toastTimer;
let chartGeometry;

function toast(message, error = false) {
  $('toast').textContent = message;
  $('toast').classList.remove('hidden');
  $('toast').classList.toggle('error', error);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 10000 : 4500);
}

async function action(call, success) {
  operation = true;
  renderControls();
  try {
    const result = await call();
    if (result?.state) receive(result);
    if (success && result !== null) toast(typeof success === 'function' ? success(result) : success);
    return result;
  } catch (error) { toast(error.message || String(error), true); }
  finally { operation = false; renderControls(); }
}

function receive(value) {
  current = { ...current, ...value };
  render();
}

function navigate(name) {
  page = name;
  const labels = { monitor: 'Research monitor', datasets: 'Datasets', options: 'Options calculator', runs: 'Research runs', preferences: 'Preferences' };
  const kickers = { monitor: 'ENGINE / OVERVIEW', datasets: 'DATA / SNAPSHOTS', options: 'DERIVATIVES / PRICING', runs: 'RESEARCH / HISTORY', preferences: 'ENGINE / SETTINGS' };
  $('page-title').textContent = labels[name];
  $('page-kicker').textContent = kickers[name];
  document.querySelectorAll('.page').forEach(section => section.classList.toggle('hidden', section.id !== 'page-' + name));
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === name));
  if (name === 'monitor') requestAnimationFrame(drawChart);
  syncSurfaceAnimation();
}

function renderControls() {
  const state = current.state;
  const locked = state.busy || state.continuous;
  $('toggle-engine').innerHTML = state.busy || state.continuous ? '<span class="play-icon">Ⅱ</span>Pause engine' : '<span class="play-icon">▶</span>Start engine';
  $('toggle-engine').disabled = (operation || state.settingsPending) && !state.busy && !state.continuous;
  $('run-once').disabled = state.busy || operation || state.settingsPending;
  document.querySelectorAll('.config-field').forEach(input => {
    input.disabled = state.busy || operation || state.settingsPending;
    if (document.activeElement === input) return;
    const value = current.config[input.dataset.key];
    if (input.type === 'checkbox') input.checked = Boolean(value);
    else if (value !== undefined) input.value = value;
  });
  ['import-csv', 'refresh-ecb', 'datasets-import', 'datasets-refresh', 'choose-root'].forEach(id => { $(id).disabled = locked || operation; });
  ['export-report', 'runs-export'].forEach(id => { $(id).disabled = !current.report; });
  $('calculate-options').disabled = state.busy || operation || state.settingsPending;
}

function render() {
  const state = current.state;
  const report = current.report;
  document.body.classList.remove('loading');
  $('sidebar-status').textContent = state.busy ? 'Worker computing' : state.continuous ? 'Engine running' : 'Engine paused';
  $('status-dot').className = 'dot' + (state.busy || state.continuous ? ' running' : state.phase === 'error' ? ' error' : '');
  $('footer-status').innerHTML = 'Engine status: <strong>' + esc(state.busy ? 'Computing' : state.continuous ? 'Waiting' : state.phase === 'error' ? 'Error · paused' : 'Paused') + '</strong>';
  $('footer-message').textContent = state.busy ? (state.stage || 'Computing') + ' · ' + Math.round((state.fraction || 0) * 100) + '%' :
    state.nextRunAt ? 'Next actual calculation: ' + shortTime(state.nextRunAt) + ' · ' + (current.config.lowCpu ? '1 numerical thread' : '2 numerical threads maximum') : 'Runs in the system tray while the computer is awake.';
  $('error-banner').textContent = state.lastError || '';
  $('error-banner').classList.toggle('hidden', !state.lastError);
  $('refresh-banner').textContent = state.lastRefreshError || '';
  $('refresh-banner').classList.toggle('hidden', !state.lastRefreshError);
  $('metric-vol').textContent = report ? percent(report.annualized_volatility) : '—';
  $('metric-var').textContent = report ? percent(report.monte_carlo.var95) : '—';
  $('metric-sharpe').textContent = report ? number(report.backtest.sharpe) : '—';
  $('metric-runs').textContent = integer(state.completed || 0);
  $('metric-var-detail').textContent = 'Gaussian · ' + (report?.parameters.horizon || current.config.horizon || 20) + ' observations';
  $('metric-run-detail').textContent = report ? 'Last run · ' + shortTime(report.run.completed_at) : 'Reports saved on this computer';
  renderDatasets();
  renderQueue();
  renderControls();
  $('storage-path').textContent = current.config.dataRoot || 'D:\\Quant-Engine';
  const runtime = current.runtime || {};
  $('runtime-details').innerHTML = ['Python', 'NumPy', 'SciPy'].map(name => '<div class="runtime-row"><span>' + name + '</span><span>' + esc(runtime[name.toLowerCase()] || 'Unavailable') + '</span></div>').join('') +
    '<div class="runtime-row"><span>Maximum numerical threads</span><span>' + (current.config.lowCpu ? '1' : '2') + '</span></div><p class="field-help">The numerical worker owns its research database. It does not send orders or connect to a brokerage.</p>';
  if (previousReport !== report) { previousReport = report; renderReport(); drawChart(); updateSurfaces(); }
  if (previousRuns !== current.runs) { previousRuns = current.runs; renderRuns(); }
  if (previousOptions !== current.options) { previousOptions = current.options; renderOptions(); updateSurfaces(); }
}

function renderDatasets() {
  const datasets = current.datasets || [];
  const selected = datasets.find(dataset => dataset.id === current.config.datasetId);
  const key = datasets.map(dataset => dataset.id + ':' + dataset.sha256 + ':' + dataset.retrieved_at).join('|');
  if (datasetKey !== key) {
    datasetKey = key;
    $('dataset-select').innerHTML = datasets.map(dataset => '<option value="' + esc(dataset.id) + '">' + esc(dataset.name) + '</option>').join('') || '<option>No dataset available</option>';
    $('dataset-count').textContent = datasets.length + ' local snapshots';
    $('dataset-cards').innerHTML = datasets.map(dataset => {
      const synthetic = dataset.kind === 'synthetic';
      const source = dataset.source_url || dataset.metadata?.original_path || 'Deterministic offline generator · seed 2048';
      return '<article class="dataset-card"><div class="dataset-card-top"><div><h3>' + esc(dataset.name) + '</h3><span class="tag ' + (synthetic ? 'synthetic' : '') + '">' + (synthetic ? 'SYNTHETIC EXAMPLE' : dataset.kind === 'ecb' ? 'ECB REFERENCE RATES' : 'IMPORTED CSV') + '</span></div><button class="secondary select-dataset" data-id="' + esc(dataset.id) + '">Use dataset</button></div>' +
        '<div class="dataset-meta">' + integer(dataset.rows) + ' observations · ' + dataset.assets.length + ' assets · ends ' + esc(dataset.observation_end) + '<br>' + esc(dataset.assets.join(' · ')) + '</div>' +
        '<div class="dataset-source">Source: ' + esc(source) + '<br>Retrieved: ' + esc(fullTime(dataset.retrieved_at)) + (dataset.kind === 'ecb' ? '<br>Currency units per EUR. Reference rates are information-only and are not executable quotes.' : '') + '</div>' +
        '<div class="dataset-hash">SHA-256 ' + esc(dataset.sha256) + '</div></article>';
    }).join('') || '<div class="large-empty">No readable datasets. Choose an accessible storage folder in Preferences.</div>';
    document.querySelectorAll('.select-dataset').forEach(button => button.addEventListener('click', () => action(() => window.quant.configure({ datasetId: button.dataset.id }), 'Dataset selected.')));
  }
  if (selected) {
    $('dataset-status').className = 'data-status' + (selected.kind === 'synthetic' ? ' synthetic' : '');
    $('dataset-status').textContent = selected.kind === 'synthetic' ? 'Synthetic example data' : selected.kind === 'ecb' ? 'Official ECB reference rates' : 'Imported price snapshot';
    const age = Math.floor((Date.now() - Date.parse(selected.observation_end + 'T00:00:00Z')) / 86400000);
    $('dataset-description').textContent = selected.kind === 'synthetic' ? 'Offline sample · ' + selected.rows + ' observations. Not market data.' :
      'Snapshot ends ' + selected.observation_end + (age > 5 ? ' · ' + age + ' days old.' : '.') + (selected.kind === 'ecb' ? ' Rates per EUR.' : ' Prices as supplied.');
  } else { $('dataset-status').textContent = 'No dataset available'; $('dataset-description').textContent = 'Choose a storage folder or import a valid CSV.'; }
}

function renderQueue() {
  const state = current.state;
  const report = current.report;
  const tasks = [
    ['Minimum variance', 'Covariance + long-only optimization', /covariance|optimizing/i],
    ['Monte Carlo risk', 'Gaussian + historical block bootstrap', /Gaussian|resampling|simulation/i],
    ['Walk-forward backtest', 'Momentum, costs + parameter sensitivity', /backtest|chronological/i],
  ];
  $('queue-body').innerHTML = tasks.map(([title, detail, match]) => {
    const computing = state.busy && match.test(state.stage || '');
    const status = computing ? 'Computing' : report ? 'Complete' : state.busy ? 'Queued' : 'Waiting';
    return '<tr><td title="' + esc(detail) + '">' + esc(title) + '</td><td><span class="status-cell ' + (computing ? 'compute' : report ? 'complete' : '') + '"><i></i>' + status + '</span></td><td>' + (report ? shortTime(report.run.completed_at) : '—') + '</td></tr>';
  }).join('');
  $('queue-summary').textContent = state.busy ? state.stage : state.continuous ? 'Next cycle · ' + shortTime(state.nextRunAt) : 'One worker · no overlapping jobs';
  $('job-progress-bar').style.width = state.busy ? ((state.fraction || 0) * 100) + '%' : '0%';
}

function renderReport() {
  const report = current.report;
  $('chart-empty').classList.toggle('hidden', Boolean(report));
  const badge = $('report-badge');
  badge.textContent = report ? report.provenance.kind === 'synthetic' ? 'SYNTHETIC REPORT' : report.provenance.kind === 'ecb' ? 'ECB SNAPSHOT' : 'CSV SNAPSHOT' : 'NO REPORT';
  badge.className = 'tag ' + (report?.provenance.kind === 'synthetic' ? 'synthetic' : report ? '' : 'neutral');
  if (!report) return;
  const gaussian = report.monte_carlo;
  const bootstrap = report.bootstrap;
  $('risk-comparison').className = '';
  // Schema 1 reports have no Student-t model or 99% levels; show only what was computed.
  const student = report.student_t;
  const models = [gaussian, bootstrap, ...(student ? [student] : [])];
  const rows = [['VaR 95%', 'var95'], ['Expected shortfall 95%', 'es95'], ['VaR 99%', 'var99'], ['Expected shortfall 99%', 'es99'], ['Probability of loss', 'loss_probability']]
    .filter(([, key]) => models.some(model => Number.isFinite(model[key])));
  $('risk-comparison').innerHTML = '<table class="risk-table"><thead><tr><th></th><th>Gaussian</th><th>Block bootstrap</th>' + (student ? '<th>Student-t</th>' : '') + '</tr></thead><tbody>' +
    rows.map(([name, key]) => '<tr><td>' + name + '</td>' + models.map(model => '<td>' + percent(model[key]) + '</td>').join('') + '</tr>').join('') +
    '</tbody></table><div class="risk-note">' + integer(gaussian.paths) + ' paths each · ' + gaussian.horizon + ' observations · empirical blocks of ' + bootstrap.block_size +
    (student ? ' · t degrees of freedom ' + number(student.degrees_of_freedom, 1) + (student.hill && Number.isFinite(student.hill.alpha) ? ' · Hill tail index ' + number(student.hill.alpha, 2) : '') : '') +
    '<br>Signed losses: exact empirical tail mass. Cumulative arithmetic returns; all estimates depend on historical inputs.</div>';
  $('allocation').className = 'allocation';
  $('allocation').innerHTML = Object.entries(report.weights).map(([asset, weight]) => '<div class="weight-row"><span class="weight-name" title="' + esc(asset) + '">' + esc(asset) + '</span><div class="weight-track"><div class="weight-fill" data-weight="' + weight + '"></div></div><span class="weight-value">' + percent(weight, 1) + '</span></div>').join('');
  document.querySelectorAll('.weight-fill').forEach(fill => { fill.style.width = Number(fill.dataset.weight) * 100 + '%'; });
  const parameters = report.parameters;
  $('report-provenance').innerHTML = 'RUN ' + esc(report.run.id) + ' · ' + esc(fullTime(report.run.completed_at)) + ' · ' + number(report.run.duration_ms / 1000, 2) + ' s<br>' +
    'SOURCE ' + esc(report.provenance.name) + ' · ' + report.observations + ' observations · ' + esc(report.date_range.start) + ' → ' + esc(report.date_range.end) + '<br>' +
    'SEED ' + parameters.seed + ' · LOOKBACK ' + parameters.lookback + ' · COST ' + parameters.cost_bps + ' bps · REBALANCE ' + parameters.rebalance + ' · SHRINKAGE ' + parameters.shrinkage + '<br>' +
    'SNAPSHOT SHA-256 ' + esc(report.provenance.sha256);
  $('methodology').innerHTML = '<div class="methodology-copy"><div class="section-label">Numerical methods</div><ul>' + report.methodology.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul><div class="section-label">Gaussian assumptions</div><ul>' + gaussian.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul><div class="section-label">Bootstrap assumptions</div><ul>' + bootstrap.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul>' + (report.student_t ? '<div class="section-label">Student-t assumptions</div><ul>' + report.student_t.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul>' : '') + '<div class="section-label">Historical and hypothetical stress</div><ul>' + report.stress.map(item => '<li>' + esc(item.name) + ': ' + percent(item.return) + ' · ' + esc(item.kind) + (item.date ? ' · ' + esc(item.date) : '') + '</li>').join('') + '</ul></div>';
}

function renderOptions() {
  const report = current.options;
  if (!report) return;
  const bs = report.black_scholes, trees = report.trees, mc = report.monte_carlo, p = report.parameters;
  const price = value => Number.isFinite(value) ? value.toFixed(4) : '—';
  $('options-badge').textContent = esc(p.kind.toUpperCase()) + ' · ' + number(report.runtime?.duration_ms || 0, 0) + ' ms';
  $('options-prices').className = '';
  $('options-prices').innerHTML = '<table class="risk-table"><thead><tr><th>Method</th><th>Price</th><th>Check</th></tr></thead><tbody>' +
    [['Black–Scholes (European)', bs.price, bs.degenerate ? esc(bs.degenerate) : 'analytic'],
     ['CRR tree, European · ' + integer(trees.steps) + ' steps', trees.european, 'error ' + price(trees.european_tree_error)],
     ['CRR tree, American', trees.american, 'early exercise ' + price(trees.early_exercise_premium)],
     ['Monte Carlo · ' + integer(mc.paths) + ' paths', mc.price, '± ' + price(mc.standard_error) + ' s.e. ' + (mc.within_three_standard_errors ? '✓' : '✗')],
     [(p.kind === 'call' ? 'Put' : 'Call') + ' (same contract)', report.counterpart.price, 'parity gap ' + Number(report.put_call_parity_gap).toExponential(1)]]
      .map(([name, value, check]) => '<tr><td>' + name + '</td><td>' + price(value) + '</td><td>' + check + '</td></tr>').join('') +
    (report.implied ? '<tr><td>Implied volatility of ' + price(report.implied.market_price) + '</td><td>' + percent(report.implied.implied_volatility) + '</td><td>Brent root</td></tr>' : '') +
    '</tbody></table><div class="risk-note">Seed ' + esc(p.seed) + ' · rate ' + percent(p.rate) + ' · dividend ' + percent(p.dividend) + ' · volatility ' + percent(p.volatility) + ' · ' + esc(p.time) + ' years</div>';
  if (report.surface) $('options-surface-arbitrage').textContent = report.surface.sufficient_no_arbitrage ?
    'Gatheral–Jacquier sufficient no-arbitrage conditions hold' : 'Warning: η(1+|ρ|) > 2, so static no-arbitrage is not guaranteed';
  const units = report.units;
  $('options-greeks').className = '';
  $('options-greeks').innerHTML = '<table class="risk-table"><thead><tr><th>Greek</th><th>Value</th><th>Unit</th></tr></thead><tbody>' +
    [['Delta', bs.delta, 'per 1 unit of spot'], ['Gamma', bs.gamma, 'per unit spot²'], ['Vega', bs.vega_per_point, units.vega_per_point],
     ['Theta', bs.theta_per_day, units.theta_per_day], ['Rho', bs.rho_per_point, units.rho_per_point],
     ['Vanna', bs.vanna, 'delta per 1.00 volatility'], ['Volga', bs.volga, 'vega per 1.00 volatility']]
      .map(([name, value, unit]) => '<tr><td>' + name + '</td><td>' + (Number.isFinite(value) ? value.toFixed(6) : '—') + '</td><td>' + esc(unit) + '</td></tr>').join('') + '</tbody></table>';
  const daily = report.implied_moves.daily, expiry = report.implied_moves.to_expiry;
  $('options-moves').className = 'methodology-copy';
  $('options-moves').innerHTML = '<div class="section-label">Implied moves</div><ul>' +
    '<li>One-sigma daily move: ' + percent(daily.one_sigma) + ' (σ/√252). The trader rule σ/16 gives ' + percent(daily.rule_of_16) + '.</li>' +
    '<li>Expected absolute daily move: ' + percent(daily.expected_absolute_move) + ' (≈ 0.80σ). A move stays within ±1σ only ' + percent(daily.probability_within_one_sigma, 0) + ' of the time under normality.</li>' +
    (expiry ? '<li>One-sigma move to expiry: ' + percent(expiry.one_sigma) + '.</li>' : '') + '</ul><div class="section-label">Assumptions</div><ul>' +
    report.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul>';
}

function optionInputs() {
  const read = id => { const value = $(id).value.trim(); return value === '' ? null : Number(value); };
  const values = { kind: $('opt-kind').value, spot: read('opt-spot'), strike: read('opt-strike'), time: read('opt-time'),
    volatility: read('opt-volatility') / 100, rate: read('opt-rate') / 100, dividend: read('opt-dividend') / 100,
    steps: read('opt-steps'), paths: read('opt-paths'), seed: read('opt-seed'),
    surface_rho: read('opt-surface-rho'), surface_eta: read('opt-surface-eta') };
  const market = read('opt-market');
  if (market !== null) values.market_price = market;
  for (const [key, value] of Object.entries(values)) if (key !== 'kind' && !Number.isFinite(value)) throw new Error('Enter a number for ' + key.replace('_', ' ') + '.');
  return values;
}

function renderRuns() {
  const runs = current.runs || [];
  $('runs-empty').classList.toggle('hidden', runs.length > 0);
  $('runs-body').innerHTML = runs.map(run => {
    const p = run.parameters || {};
    const duration = typeof run.duration_ms === 'number' ? number(run.duration_ms / 1000, 2) + ' s' : '—';
    return '<tr><td>' + esc(fullTime(run.completed_at || run.started_at)) + '<div class="run-subline">' + esc(run.id) + '</div></td><td>' + esc(run.source?.name || run.dataset_id) + '<div class="run-subline">' + esc(run.source?.kind || '') + '</div></td><td class="run-parameters">' + integer(p.paths || 50000) + ' paths · horizon ' + (p.horizon || 20) + '<br>seed ' + (p.seed ?? 17) + ' · lookback ' + (p.lookback || 20) + '</td><td>' + duration + '</td><td><span class="run-status ' + esc(run.status) + '">' + esc(run.status) + '</span>' + (run.error ? '<div class="run-error">' + esc(run.error) + '</div>' : '') + '</td><td>' + (run.status === 'completed' ? '<button class="secondary run-open" data-run="' + esc(run.id) + '">Open ↗</button>' : '') + '</td></tr>';
  }).join('');
  document.querySelectorAll('.run-open').forEach(button => button.addEventListener('click', async () => { const result = await action(() => window.quant.openRun(button.dataset.run)); if (result) navigate('monitor'); }));
}

// ---- 3D surface renderer (canvas 2D; no WebGL needed on integrated graphics) ----
// Sequential ramp, lightness increasing with value; height also encodes value, so colour is never alone.
const SURFACE_RAMP = [[0, [17, 42, 74]], [.3, [27, 104, 128]], [.58, [76, 182, 184]], [.8, [156, 211, 128]], [1, [236, 196, 120]]];
const reducedMotion = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function surfaceColor(t, shade) {
  t = Math.max(0, Math.min(1, t));
  let i = 1;
  while (i < SURFACE_RAMP.length - 1 && t > SURFACE_RAMP[i][0]) i++;
  const [t0, c0] = SURFACE_RAMP[i - 1], [t1, c1] = SURFACE_RAMP[i];
  const f = (t - t0) / (t1 - t0 || 1);
  return c0.map((c, k) => Math.round(Math.min(255, (c + (c1[k] - c) * f) * shade)));
}

function createSurface(canvas, hover, options = {}) {
  const view = { azimuth: options.azimuth ?? -0.75, elevation: options.elevation ?? 0.55, drag: null, manual: false };
  let data = null, previous = null, morphStart = 0, frame = 0, running = false, last = 0, offset = 0, projected = [], hoverPoint = null;
  const windowColumns = options.windowColumns || 0;

  function size() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(rect.width * ratio) || canvas.height !== Math.round(rect.height * ratio)) {
      canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  function draw(now) {
    const setup = size();
    if (!setup || !data) return;
    const { ctx, width, height } = setup;
    ctx.clearRect(0, 0, width, height);
    const rows = data.z.length, totalCols = data.z[0].length;
    const span = windowColumns ? Math.min(windowColumns, totalCols) : totalCols;
    const maxOffset = Math.max(0, totalCols - span);
    const start = Math.min(Math.floor(offset), maxOffset), frac = start < maxOffset ? offset - start : 0;
    const cols = Math.min(span + (frac > 0 ? 1 : 0), totalCols - start);
    const morph = previous && previous.length === rows && previous[0].length === totalCols ? Math.min(1, (now - morphStart) / 700) : 1;
    const ease = morph < 1 ? 1 - Math.pow(1 - morph, 3) : 1;
    const value = (i, j) => previous && ease < 1 ? previous[i][j] + (data.z[i][j] - previous[i][j]) * ease : data.z[i][j];
    const zLow = data.zMin, zHigh = data.zMax, zSpan = zHigh - zLow || 1;
    const ca = Math.cos(view.azimuth), sa = Math.sin(view.azimuth), ce = Math.cos(view.elevation), se = Math.sin(view.elevation);
    const raw = (X, Y, Z, cos, sin) => {
      const xr = X * cos - Y * sin, yr = X * sin + Y * cos;
      const depth = yr * ce - Z * se, perspective = 1 / (1 + depth * .12);
      return [xr * perspective, -(Z * ce + yr * se) * perspective, depth];
    };
    let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
    // Fit over the azimuths in use (auto-rotation range, or around a dragged view) to avoid empty space.
    const centre = view.manual ? view.azimuth : (options.azimuth ?? -0.75);
    for (let k = 0; k <= 12; k++) {
      const a = centre - .6 + k / 12 * 1.2, cos = Math.cos(a), sin = Math.sin(a);
      for (const cx0 of [-1, 1]) for (const cy0 of [-1, 1]) for (const cz0 of [-.55, .62]) {
        const [px, py] = raw(cx0, cy0, cz0, cos, sin);
        left = Math.min(left, px); right = Math.max(right, px); top = Math.min(top, py); bottom = Math.max(bottom, py);
      }
    }
    const marginX = 64, marginTop = 22, marginBottom = 40;
    const scale = Math.min((width - 2 * marginX) / (right - left), (height - marginTop - marginBottom) / (bottom - top));
    const cx = width / 2 - (left + right) / 2 * scale, cy = marginTop + (height - marginTop - marginBottom) / 2 - (top + bottom) / 2 * scale;
    const project = (X, Y, Z) => {
      const [px, py, depth] = raw(X, Y, Z, ca, sa);
      return [cx + px * scale, cy + py * scale, depth];
    };
    const X = j => ((j - frac) / Math.max(span - 1, 1)) * 2 - 1;
    const Y = i => (i / Math.max(rows - 1, 1)) * 2 - 1;
    const Z = v => ((v - zLow) / zSpan) * 1.1 - .55;
    // Back walls and floor grid, drawn first, recessive.
    const walls = [[-1, -1, -1, 1], [-1, 1, 1, 1]];
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(132,160,186,.18)';
    ctx.setLineDash([2, 4]);
    for (let t = 0; t <= 4; t++) {
      const z = -.55 + t / 4 * 1.1;
      for (const [x0, y0, x1, y1] of walls) {
        const a = project(x0, y0, z), b = project(x1, y1, z);
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      }
    }
    for (let t = 0; t <= 4; t++) {
      const g = -1 + t / 2;
      if (g > 1) break;
      let a = project(g, -1, -.55), b = project(g, 1, -.55);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      a = project(-1, g, -.55); b = project(1, g, -.55);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }
    ctx.setLineDash([]);
    // Surface quads, far to near (painter's algorithm), lit by a fixed light.
    const quads = [];
    projected = [];
    for (let i = 0; i < rows; i++) for (let jj = 0; jj < cols; jj++) {
      const j = start + jj, x = X(jj);
      if (x < -1.0001 && jj + 1 < cols && X(jj + 1) <= -1) continue;
      const p = project(Math.max(-1, x), Y(i), Z(value(i, j)));
      projected.push({ x: p[0], y: p[1], i, j });
    }
    for (let i = 0; i < rows - 1; i++) for (let jj = 0; jj < cols - 1; jj++) {
      const j = start + jj;
      const xa = Math.max(-1, X(jj)), xb = Math.min(1, X(jj + 1));
      if (xb <= xa) continue;
      const v00 = value(i, j), v01 = value(i, j + 1), v10 = value(i + 1, j), v11 = value(i + 1, j + 1);
      const corners = [[xa, Y(i), Z(v00)], [xb, Y(i), Z(v01)], [xb, Y(i + 1), Z(v11)], [xa, Y(i + 1), Z(v10)]];
      const pts = corners.map(c => project(...c));
      const ux = xb - xa, vy = Y(i + 1) - Y(i), dzx = Z(v01) - Z(v00), dzy = Z(v10) - Z(v00);
      const nx = -dzx * vy, ny = -dzy * ux, nz = ux * vy, len = Math.hypot(nx, ny, nz) || 1;
      const light = (nx * -.35 + ny * -.45 + nz * .82) / len;
      quads.push({ pts, depth: (pts[0][2] + pts[1][2] + pts[2][2] + pts[3][2]) / 4,
        t: ((v00 + v01 + v10 + v11) / 4 - data.cMin) / (data.cMax - data.cMin || 1), shade: .62 + .45 * Math.max(0, light) });
    }
    quads.sort((a, b) => b.depth - a.depth);
    for (const q of quads) {
      const [r, g, b] = surfaceColor(q.t, q.shade);
      ctx.beginPath();
      ctx.moveTo(q.pts[0][0], q.pts[0][1]);
      for (let k = 1; k < 4; k++) ctx.lineTo(q.pts[k][0], q.pts[k][1]);
      ctx.closePath();
      ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
      ctx.fill();
      ctx.strokeStyle = 'rgba(' + Math.min(255, r + 40) + ',' + Math.min(255, g + 40) + ',' + Math.min(255, b + 40) + ',.35)';
      ctx.lineWidth = .6;
      ctx.stroke();
    }
    // Axes: z ticks on the back-left edge, x/y ticks along the floor.
    ctx.fillStyle = '#8fa6bb';
    ctx.font = '9px Consolas, monospace';
    const corner = [[-1, -1], [-1, 1], [1, -1], [1, 1]].map(([x, y]) => ({ x, y, p: project(x, y, -.55) }))
      .sort((a, b) => a.p[0] - b.p[0])[0];
    ctx.strokeStyle = 'rgba(132,160,186,.35)';
    let a0 = project(corner.x, corner.y, -.55), a1 = project(corner.x, corner.y, .55);
    ctx.beginPath(); ctx.moveTo(a0[0], a0[1]); ctx.lineTo(a1[0], a1[1]); ctx.stroke();
    for (let t = 0; t <= 4; t++) {
      const v = zLow + t / 4 * zSpan, p = project(corner.x, corner.y, -.55 + t / 4 * 1.1);
      ctx.textAlign = 'right'; ctx.fillText(data.zFormat(v), p[0] - 6, p[1] + 3);
    }
    const xTicks = options.xTicks || 4;
    for (let t = 0; t <= xTicks; t++) {
      const jj = Math.round(t / xTicks * (span - 1)), j = Math.min(start + jj, totalCols - 1), p = project(X(jj + frac), -1, -.55);
      if (X(jj + frac) < -1.0001 || X(jj + frac) > 1.0001) continue;
      ctx.textAlign = 'center'; ctx.fillText(data.xFormat(data.x[j]), p[0], p[1] + 14);
    }
    for (let t = 0; t <= 3; t++) {
      const i = Math.round(t / 3 * (rows - 1)), p = project(1, Y(i), -.55);
      ctx.textAlign = 'left'; ctx.fillText(data.yFormat(data.y[i]), p[0] + 8, p[1] + 3);
    }
    ctx.fillStyle = '#b4c8da';
    ctx.font = '10px Segoe UI, Arial, sans-serif';
    let p = project(0, -1, -.55); ctx.textAlign = 'center'; ctx.fillText(data.xLabel, p[0], p[1] + 30);
    p = project(1, 0, -.55); ctx.textAlign = 'left'; ctx.fillText(data.yLabel, p[0] + 34, p[1] + 16);
    p = project(corner.x, corner.y, .62); ctx.textAlign = 'center'; ctx.fillText(data.zLabel, p[0], p[1] - 8);
    if (options.caption) options.caption(data.x[Math.min(start + span - 1, totalCols - 1)], start, maxOffset);
    if (hoverPoint) showHover(hoverPoint.mx, hoverPoint.my);
  }

  function tick(now) {
    if (!running) return;
    frame = requestAnimationFrame(tick);
    if (now - last < 33) return;  // About 30 frames per second at most.
    const dt = last ? Math.min(100, now - last) : 0;
    last = now;
    if (!view.drag && !view.manual) view.azimuth = (options.azimuth ?? -0.75) + Math.sin(now / 9000) * .32;
    if (windowColumns && data) {
      const maxOffset = Math.max(0, data.z[0].length - windowColumns);
      offset += dt / 1000 * (options.columnsPerSecond || 3);
      if (offset > maxOffset + 6) offset = 0;  // Short hold on the latest data, then replay.
    }
    draw(now);
  }

  function showHover(mx, my) {
    if (!hover) return;
    let best = null, distance = 16;
    for (const point of projected) {
      const d = Math.hypot(point.x - mx, point.y - my);
      if (d < distance) { distance = d; best = point; }
    }
    if (!best) { hover.classList.add('hidden'); return; }
    hover.innerHTML = esc(data.xLabel) + ' ' + esc(data.xFormat(data.x[best.j])) + '<br>' + esc(data.yLabel) + ' ' + esc(data.yFormat(data.y[best.i])) + '<br>' + esc(data.zLabel) + ' ' + esc(data.zFormat(data.z[best.i][best.j]));
    hover.style.left = Math.max(8, best.x + 12) + 'px';
    hover.style.top = Math.max(8, best.y - 50) + 'px';
    hover.classList.remove('hidden');
  }

  canvas.addEventListener('pointerdown', event => { view.drag = { x: event.clientX, y: event.clientY, a: view.azimuth, e: view.elevation }; view.manual = true; });
  window.addEventListener('pointerup', () => { view.drag = null; });
  canvas.addEventListener('pointermove', event => {
    const rect = canvas.getBoundingClientRect();
    if (view.drag) {
      view.azimuth = view.drag.a + (event.clientX - view.drag.x) / 160;
      view.elevation = Math.max(.12, Math.min(1.2, view.drag.e + (event.clientY - view.drag.y) / 220));
      if (!running) draw(performance.now());
    }
    hoverPoint = { mx: event.clientX - rect.left, my: event.clientY - rect.top };
    showHover(hoverPoint.mx, hoverPoint.my);
  });
  canvas.addEventListener('pointerleave', () => { hoverPoint = null; hover?.classList.add('hidden'); });
  canvas.addEventListener('dblclick', () => { view.manual = false; });

  return {
    setData(next) {
      previous = data && data.z.length === next.z.length && data.z[0].length === next.z[0].length ? data.z.map(row => row.slice()) : null;
      morphStart = performance.now();
      if (!data && windowColumns) offset = Math.max(0, next.z[0].length - windowColumns);  // Open on the latest data.
      data = next;
      if (!running) draw(performance.now());
    },
    start() { if (running || reducedMotion) { draw(performance.now()); return; } running = true; last = 0; frame = requestAnimationFrame(tick); },
    stop() { running = false; cancelAnimationFrame(frame); },
    draw() { draw(performance.now()); },
  };
}

function surfaceRange(rows) {
  const values = rows.flat().filter(Number.isFinite).sort((a, b) => a - b);
  const low = values[0], high = values[values.length - 1];
  const pad = (high - low) * .04 || Math.abs(high) * .05 || .01;
  // Colour uses the 2nd–98th percentile so a few spikes cannot flatten the ramp; height keeps the full range.
  const at = q => values[Math.min(values.length - 1, Math.max(0, Math.round(q * (values.length - 1))))];
  return [low - pad, high + pad, at(.02), at(.98)];
}

const monitorSurface = createSurface($('surface-chart'), $('chart-hover'), { windowColumns: 72, columnsPerSecond: 4, azimuth: -0.8, xTicks: 2,
  caption: (date, start, maxOffset) => {
    if (chartMode !== 'surface') return;
    $('chart-subtitle').textContent = (maxOffset && start < maxOffset ? 'Replaying history · through ' : 'Latest · through ') + date + ' · drag to rotate, double-click to resume';
  } });
const optionsSurface = createSurface($('options-surface'), $('options-surface-hover'), { azimuth: -0.65 });

function updateSurfaces() {
  const surface = current.report?.volatility_surface;
  if (surface) {
    const [zMin, zMax, cMin, cMax] = surfaceRange(surface.values);
    monitorSurface.setData({ x: surface.dates, y: surface.windows, z: surface.values, zMin, zMax, cMin, cMax,
      xLabel: 'Date', yLabel: 'Lookback (days)', zLabel: 'Realised vol',
      xFormat: value => String(value), yFormat: value => String(value), zFormat: value => percent(value, 1) });
  }
  const model = current.options?.surface;
  if (model) {
    const [zMin, zMax, cMin, cMax] = surfaceRange(model.implied_volatility);
    optionsSurface.setData({ x: model.log_moneyness, y: model.expiries, z: model.implied_volatility, zMin, zMax, cMin, cMax,
      xLabel: 'Moneyness K/F', yLabel: 'Expiry (years)', zLabel: 'Implied vol',
      xFormat: value => Math.exp(value).toFixed(2), yFormat: value => Number(value).toFixed(2), zFormat: value => percent(value, 1) });
  }
  syncSurfaceAnimation();
}

function syncSurfaceAnimation() {
  const visible = !document.hidden;
  if (visible && page === 'monitor' && chartMode === 'surface' && current.report?.volatility_surface) monitorSurface.start(); else monitorSurface.stop();
  if (visible && page === 'options' && current.options?.surface) optionsSurface.start(); else optionsSurface.stop();
}
document.addEventListener('visibilitychange', syncSurfaceAnimation);

function chartContext() {
  const canvas = $('research-chart');
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext('2d');
  context.scale(ratio, ratio);
  context.clearRect(0, 0, rect.width, rect.height);
  context.font = '9px Consolas, monospace';
  return { context, width: rect.width, height: rect.height };
}

function grid(context, width, height, low, high, format, labels = []) {
  const plot = { left: 43, top: 14, right: width - 15, bottom: height - 30 };
  for (let step = 0; step <= 4; step++) {
    const y = plot.top + (plot.bottom - plot.top) * step / 4;
    context.strokeStyle = '#29405199';
    context.lineWidth = .7;
    context.beginPath(); context.moveTo(plot.left, y); context.lineTo(plot.right, y); context.stroke();
    context.fillStyle = '#7691a8'; context.textAlign = 'right';
    context.fillText(format(high - (high - low) * step / 4), plot.left - 9, y + 3);
  }
  for (let step = 0; step <= 4; step++) {
    const x = plot.left + (plot.right - plot.left) * step / 4;
    context.strokeStyle = '#26394966';
    context.beginPath(); context.moveTo(x, plot.top); context.lineTo(x, plot.bottom); context.stroke();
    if (labels[step] !== undefined) {
      context.fillStyle = '#68869e'; context.textAlign = step === 0 ? 'left' : step === 4 ? 'right' : 'center';
      context.fillText(labels[step], x, height - 10);
    }
  }
  context.textAlign = 'left';
  return plot;
}

function drawChart() {
  if (page !== 'monitor') return;
  const setup = chartContext();
  if (!setup) return;
  const { context: ctx, width, height } = setup;
  const report = current.report;
  chartGeometry = null;
  $('chart-hover').classList.add('hidden');
  const chartTitles = { equity: 'Costed strategy & baselines', risk: 'Gaussian horizon-return distribution', correlation: 'Historical return correlations', sensitivity: 'Momentum lookback sensitivity', surface: 'Realised volatility surface' };
  $('chart-title').textContent = chartTitles[chartMode];
  const surfaceMode = chartMode === 'surface';
  $('research-chart').classList.toggle('hidden', surfaceMode);
  $('chart-wrap').classList.toggle('surface-mode', surfaceMode);
  $('surface-chart').classList.toggle('hidden', !surfaceMode);
  if (surfaceMode) {
    if (!report?.volatility_surface) $('chart-subtitle').textContent = 'Run an analysis with this version to build the surface';
    $('chart-legend').innerHTML = '<span><i class="ramp"></i>Annualised realised volatility of the optimised portfolio · lower → higher</span><span>Trailing windows only · no future returns</span>';
    monitorSurface.draw();
    syncSurfaceAnimation();
    return;
  }
  syncSurfaceAnimation();
  if (!report) { $('chart-subtitle').textContent = 'Real numerical outputs appear after an analysis'; grid(ctx, width, height, 0, 1, () => ''); return; }
  if (chartMode === 'equity') {
    const curve = report.curve;
    let min = Infinity, max = -Infinity;
    for (const point of curve) { min = Math.min(min, point.strategy, point.equal_weight, point.cash); max = Math.max(max, point.strategy, point.equal_weight, point.cash); }
    const pad = Math.max(.03, (max - min) * .13);
    const low = min - pad, high = max + pad;
    const labels = [0, 1, 2, 3, 4].map(step => curve[Math.round(step * (curve.length - 1) / 4)].date.slice(0, 7));
    const plot = grid(ctx, width, height, low, high, x => x.toFixed(2), labels);
    const x = i => plot.left + i / (curve.length - 1) * (plot.right - plot.left);
    const y = value => plot.bottom - (value - low) / (high - low) * (plot.bottom - plot.top);
    const gradient = ctx.createLinearGradient(0, plot.top, 0, plot.bottom);
    gradient.addColorStop(0, '#61cfcb20'); gradient.addColorStop(1, '#61cfcb02');
    ctx.beginPath(); ctx.moveTo(x(0), plot.bottom);
    curve.forEach((point, i) => ctx.lineTo(x(i), y(point.strategy)));
    ctx.lineTo(x(curve.length - 1), plot.bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
    for (const [key, color, dashed] of [['cash', '#526b7e', [2, 5]], ['equal_weight', '#8399ad', [5, 4]], ['strategy', '#61cfcb', []]]) {
      ctx.strokeStyle = color; ctx.lineWidth = key === 'strategy' ? 1.7 : 1.2; ctx.setLineDash(dashed);
      ctx.beginPath(); curve.forEach((point, i) => i ? ctx.lineTo(x(i), y(point[key])) : ctx.moveTo(x(i), y(point[key]))); ctx.stroke();
    }
    ctx.setLineDash([]);
    const last = curve[curve.length - 1]; ctx.fillStyle = '#83e2dc'; ctx.beginPath(); ctx.arc(x(curve.length - 1), y(last.strategy), 3, 0, Math.PI * 2); ctx.fill();
    $('chart-subtitle').textContent = report.date_range.start + ' → ' + report.date_range.end + ' · equity starts at 1.00 · ' + report.parameters.cost_bps + ' bps trading cost';
    $('chart-legend').innerHTML = '<span><i class="line mint"></i>Momentum, net ' + percent(report.backtest.total_return) + '</span><span><i class="line dashed"></i>Equal weight, net</span><span><i class="line cash"></i>Cash</span>';
    chartGeometry = { plot, curve, x, y, width, height };
  } else if (chartMode === 'risk') {
    const bins = report.monte_carlo.histogram;
    const maximum = Math.max(...bins.map(bin => bin.count));
    const left = bins[0].low, right = bins[bins.length - 1].high;
    const labels = [0, 1, 2, 3, 4].map(step => percent(left + step / 4 * (right - left), 1));
    const plot = grid(ctx, width, height, 0, maximum * 1.1, value => Math.round(value).toLocaleString(), labels);
    const barWidth = (plot.right - plot.left) / bins.length;
    bins.forEach((bin, index) => {
      const barHeight = bin.count / (maximum * 1.1) * (plot.bottom - plot.top);
      ctx.fillStyle = bin.high < -report.monte_carlo.var95 ? '#d99c665c' : '#61cfcb8a';
      ctx.fillRect(plot.left + index * barWidth + .6, plot.bottom - barHeight, Math.max(1, barWidth - 1.2), barHeight);
    });
    const q05 = -report.monte_carlo.var95;
    const x = plot.left + (q05 - left) / (right - left) * (plot.right - plot.left);
    ctx.strokeStyle = '#e7b378'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(x, plot.top); ctx.lineTo(x, plot.bottom); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#dcb182'; ctx.fillText('5% tail', Math.min(plot.right - 50, x + 7), plot.top + 11);
    $('chart-subtitle').textContent = integer(report.parameters.paths) + ' simulated paths · ' + report.parameters.horizon + ' observations · seed ' + report.parameters.seed;
    $('chart-legend').innerHTML = '<span><i class="line mint"></i>Gaussian paths per bin</span><span><i class="line bootstrap"></i>Bootstrap VaR ' + percent(report.bootstrap.var95) + '</span>';
  } else if (chartMode === 'correlation') {
    const count = Math.min(12, report.assets.length);
    const cell = Math.min((width - 160) / count, (height - 50) / count, 60);
    const left = 117, top = 16;
    for (let row = 0; row < count; row++) {
      ctx.textAlign = 'right'; ctx.fillStyle = '#91aec5'; ctx.font = '9px Segoe UI, sans-serif';
      ctx.fillText(report.assets[row].length > 17 ? report.assets[row].slice(0, 15) + '…' : report.assets[row], left - 8, top + row * cell + cell / 2 + 3);
      for (let col = 0; col < count; col++) {
        const value = report.correlation[row][col];
        const magnitude = Math.abs(value);
        ctx.fillStyle = value >= 0 ? `rgba(68,176,168,${.10 + magnitude * .65})` : `rgba(191,124,90,${.10 + magnitude * .65})`;
        ctx.fillRect(left + col * cell + 1, top + row * cell + 1, cell - 2, cell - 2);
        if (cell >= 22) { ctx.textAlign = 'center'; ctx.font = '9px Consolas, monospace'; ctx.fillStyle = '#c4ddd8'; ctx.fillText(value.toFixed(2), left + col * cell + cell / 2, top + row * cell + cell / 2 + 3); }
      }
    }
    ctx.textAlign = 'center'; ctx.font = '9px Consolas, monospace'; ctx.fillStyle = '#829bb2';
    for (let col = 0; col < count; col++) ctx.fillText(String(col + 1).padStart(2, '0'), left + col * cell + cell / 2, top + count * cell + 16);
    $('chart-subtitle').textContent = 'Sample return correlations · ' + report.return_observations + ' observations' + (report.assets.length > 12 ? ' · first 12 assets shown' : '');
    $('chart-legend').innerHTML = '<span><i class="line mint"></i>Positive correlation</span><span><i class="line bootstrap"></i>Diagonal = 1.00</span>';
  } else {
    const variants = report.sensitivity;
    const values = variants.map(variant => variant.total_return);
    const low = Math.min(0, ...values) - .03, high = Math.max(0, ...values) + .03;
    const plot = grid(ctx, width, height, low, high, value => percent(value, 0));
    const y = value => plot.bottom - (value - low) / (high - low) * (plot.bottom - plot.top);
    const zero = y(0), step = (plot.right - plot.left) / variants.length;
    variants.forEach((variant, index) => {
      const x = plot.left + step * index + step * .27, end = y(variant.total_return);
      ctx.fillStyle = variant.lookback === report.parameters.lookback ? '#61cfcb' : '#395f66';
      ctx.fillRect(x, Math.min(zero, end), step * .46, Math.max(1, Math.abs(end - zero)));
      ctx.textAlign = 'center'; ctx.fillStyle = '#b0c7d8';
      ctx.fillText(percent(variant.total_return, 1), x + step * .23, end + (variant.total_return >= 0 ? -8 : 15));
      ctx.fillStyle = '#7f9ab1'; ctx.fillText(variant.lookback + ' obs', x + step * .23, height - 10);
    });
    $('chart-subtitle').textContent = 'Net strategy return by lookback · overlapping historical data · different warm-up windows';
    $('chart-legend').innerHTML = '<span><i class="line mint"></i>Current report lookback</span><span><i class="line dashed"></i>Descriptive comparison; no winning-parameter selection</span>';
  }
}

$('research-chart').addEventListener('mousemove', event => {
  if (!chartGeometry || chartMode !== 'equity') return;
  const { plot, curve, width } = chartGeometry;
  const rect = event.currentTarget.getBoundingClientRect();
  const mouse = event.clientX - rect.left;
  if (mouse < plot.left || mouse > plot.right) { $('chart-hover').classList.add('hidden'); return; }
  const index = Math.max(0, Math.min(curve.length - 1, Math.round((mouse - plot.left) / (plot.right - plot.left) * (curve.length - 1))));
  const point = curve[index];
  $('chart-hover').innerHTML = esc(point.date) + '<br>Momentum ' + number(point.strategy, 4) + '<br>Equal weight ' + number(point.equal_weight, 4);
  $('chart-hover').style.left = Math.min(width - 174, Math.max(8, mouse + 12)) + 'px';
  $('chart-hover').style.top = '12px';
  $('chart-hover').classList.remove('hidden');
});
$('research-chart').addEventListener('mouseleave', () => $('chart-hover').classList.add('hidden'));

document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.page)));
document.querySelectorAll('.chart-tab').forEach(button => button.addEventListener('click', () => {
  chartMode = button.dataset.chart;
  document.querySelectorAll('.chart-tab').forEach(tab => { tab.classList.toggle('active', tab === button); tab.setAttribute('aria-selected', String(tab === button)); });
  drawChart();
}));
document.querySelectorAll('.config-field').forEach(input => input.addEventListener('change', () => {
  const value = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
  void action(() => window.quant.configure({ [input.dataset.key]: value })).then(() => renderControls());
}));
$('toggle-engine').addEventListener('click', () => { void action(() => current.state.busy || current.state.continuous ? window.quant.pause() : window.quant.start()); });
$('run-once').addEventListener('click', () => { void action(() => window.quant.runOnce()); });
$('calculate-options').addEventListener('click', () => { void action(async () => window.quant.calculateOptions(optionInputs()), 'Option calculated locally.'); });
['import-csv', 'datasets-import'].forEach(id => $(id).addEventListener('click', () => { void action(() => window.quant.importCSV(), 'Validated prices copied into an immutable local snapshot.'); }));
['refresh-ecb', 'datasets-refresh'].forEach(id => $(id).addEventListener('click', () => { void action(() => window.quant.refreshECB(), 'Official ECB reference-rate snapshot saved.'); }));
['export-report', 'runs-export'].forEach(id => $(id).addEventListener('click', () => { void action(() => window.quant.exportReport(), result => 'Exported ' + result.path); }));
$('choose-root').addEventListener('click', () => { void action(() => window.quant.chooseRoot(), 'Storage folder opened.'); });
$('open-data-folder').addEventListener('click', () => { void action(() => window.quant.openDataFolder()); });
$('toggle-methodology').addEventListener('click', () => {
  const hidden = $('methodology').classList.toggle('hidden');
  $('toggle-methodology').textContent = hidden ? 'Show details ↓' : 'Hide details ↑';
});
new ResizeObserver(() => requestAnimationFrame(drawChart)).observe($('research-chart'));

document.body.classList.add('loading');
if (window.quant) {
  window.quant.onState(receive);
  window.quant.getState().then(value => { receive(value); document.body.dataset.transport = 'ready'; })
    .catch(error => { document.body.classList.remove('loading'); toast(error.message, true); });
} else {
  document.body.classList.remove('loading');
  $('error-banner').textContent = 'The native desktop bridge is unavailable. Open Quant Engine using its desktop application.';
  $('error-banner').classList.remove('hidden');
  document.querySelectorAll('button').forEach(button => { button.disabled = true; });
  document.body.dataset.transport = 'unavailable';
}
