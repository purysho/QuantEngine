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
let previousLearning;
let previousLearningError;
let evolutionTask = 'risk';
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
  const labels = { paper: 'Paper portfolios', monitor: 'Research monitor', datasets: 'Datasets', options: 'Options calculator', evolution: 'Evolution', runs: 'Research runs', preferences: 'Preferences' };
  const kickers = { paper: 'FORWARD / PAPER LEDGER', monitor: 'ENGINE / OVERVIEW', datasets: 'DATA / SNAPSHOTS', options: 'DERIVATIVES / PRICING', evolution: 'LEARNING / SECOND MIND', runs: 'RESEARCH / HISTORY', preferences: 'ENGINE / SETTINGS' };
  $('page-title').textContent = labels[name];
  $('page-kicker').textContent = kickers[name];
  document.querySelectorAll('.page').forEach(section => section.classList.toggle('hidden', section.id !== 'page-' + name));
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === name));
  if (name === 'monitor') requestAnimationFrame(drawChart);
  if (name === 'evolution') requestAnimationFrame(renderEvolution);
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
  $('learn-now').disabled = state.busy || operation || state.settingsPending;
  renderPaper();
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
  if (previousReport !== report) { previousReport = report; renderReport(); drawChart(); updateSurfaces(); renderMaths('report'); }
  if (previousRuns !== current.runs) { previousRuns = current.runs; renderRuns(); }
  if (previousOptions !== current.options) { previousOptions = current.options; renderOptions(); updateSurfaces(); renderMaths('options'); }
  if (previousLearning !== current.learning || previousLearningError !== current.learningError) {
    previousLearning = current.learning; previousLearningError = current.learningError; renderEvolution();
  }
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
    '<br>Signed losses: exact empirical tail mass. Cumulative arithmetic returns; all estimates depend on historical inputs.</div>' +
    (report.conditional_risk ? '<div class="risk-note conditional"><strong>Tomorrow, conditional (GJR-GARCH FHS):</strong> VaR 95% ' + percent(report.conditional_risk.var95) +
      ' · VaR 99% ' + percent(report.conditional_risk.var99) + ' · ES 99% ' + percent(report.conditional_risk.es99) + ' · current vol ' + percent(report.conditional_risk.sigma_annualized, 1) +
      ' vs long-run ' + percent(report.conditional_risk.long_run_sigma_annualized, 1) + ' a year.<br>' + esc(report.conditional_risk.evidence) + '</div>' : '');
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
// Magma-like ramp: lightness rises monotonically with value (readable in grey and for colour-blind viewers).
const SURFACE_RAMP = [[0, [27, 12, 46]], [.28, [90, 20, 112]], [.55, [181, 36, 90]], [.8, [242, 96, 58]], [1, [252, 211, 107]]];
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
  const view = { azimuth: options.azimuth ?? -0.75, elevation: options.elevation ?? 0.55, drag: null, manual: false, playing: true, hold: false };
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
    ctx.strokeStyle = 'rgba(255,42,85,.16)';
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
    ctx.fillStyle = '#bda9b2';
    ctx.font = '9px Consolas, monospace';
    const corner = [[-1, -1], [-1, 1], [1, -1], [1, 1]].map(([x, y]) => ({ x, y, p: project(x, y, -.55) }))
      .sort((a, b) => a.p[0] - b.p[0])[0];
    ctx.strokeStyle = 'rgba(255,42,85,.4)';
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
    ctx.fillStyle = '#f3e9ee';
    ctx.font = '12px Segoe UI, Arial, sans-serif';
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
    const moving = view.playing && !view.hold;  // Auto-motion stops while paused, hovered or focused.
    if (moving && !view.drag && !view.manual) view.azimuth = (options.azimuth ?? -0.75) + Math.sin(now / 9000) * .32;
    if (moving && windowColumns && data) {
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
  canvas.addEventListener('pointerleave', () => { hoverPoint = null; view.hold = false; hover?.classList.add('hidden'); });
  canvas.addEventListener('pointerenter', () => { view.hold = true; });
  canvas.addEventListener('focus', () => { view.hold = true; });
  canvas.addEventListener('blur', () => { view.hold = false; });
  const redraw = () => draw(performance.now());
  const rotate = (da, de = 0) => { view.manual = true; view.azimuth += da; view.elevation = Math.max(.12, Math.min(1.2, view.elevation + de)); redraw(); };
  const reset = () => { view.manual = false; view.azimuth = options.azimuth ?? -0.75; view.elevation = options.elevation ?? 0.55; redraw(); };
  const setPlaying = playing => {
    view.playing = playing;
    if (options.toolbar) { const b = options.toolbar.querySelector('[data-surface=play]'); if (b) { b.setAttribute('aria-pressed', String(!playing)); b.textContent = playing ? 'Ⅱ' : '▶'; b.setAttribute('aria-label', playing ? 'Pause animation' : 'Play animation'); } }
  };
  // Keyboard alternative to dragging (WCAG 2.5.7): arrows rotate/tilt, space plays/pauses, Home resets.
  canvas.addEventListener('keydown', event => {
    const keys = { ArrowLeft: () => rotate(-.15), ArrowRight: () => rotate(.15), ArrowUp: () => rotate(0, .08), ArrowDown: () => rotate(0, -.08),
      ' ': () => setPlaying(!view.playing), Home: reset };
    if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
  });
  if (options.toolbar) {
    options.toolbar.querySelectorAll('[data-surface]').forEach(button => button.addEventListener('click', () => {
      const action = button.dataset.surface;
      if (action === 'play') setPlaying(!view.playing);
      else if (action === 'left') rotate(-.25); else if (action === 'right') rotate(.25); else if (action === 'reset') reset();
    }));
  }
  if (reducedMotion) setPlaying(false);
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

const monitorSurface = createSurface($('surface-chart'), $('chart-hover'), { windowColumns: 72, columnsPerSecond: 4, azimuth: -0.8, xTicks: 2, toolbar: $('surface-toolbar'),
  caption: (date, start, maxOffset) => {
    if (chartMode !== 'surface') return;
    $('chart-subtitle').textContent = (maxOffset && start < maxOffset ? 'Replaying history · through ' : 'Latest · through ') + date + ' · drag or arrow keys to rotate · space pauses';
  } });
const optionsSurface = createSurface($('options-surface'), $('options-surface-hover'), { azimuth: -0.65, toolbar: $('options-surface-toolbar') });

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
  if (visible && page === 'evolution' && current.learning?.tasks) evolutionGraph.start(); else evolutionGraph.stop();
}
document.addEventListener('visibilitychange', syncSurfaceAnimation);

// ---- 3D "second mind" lineage graph: force-directed layout in 3D, live settling, glow by fitness ----
const FAMILY_ORDER = { risk: ['historical', 'gaussian', 'student_t', 'garch_t', 'gjr_fhs'], alpha: ['zero', 'mean', 'ridge', 'mlp'] };
const FAMILY_COLORS = ['#ff2a55', '#ffb347', '#2de2e6', '#b06cff', '#f4f06b'];  // Fixed order, never cycled.
const EDGE_STYLE = { mutation: 'rgba(255,42,85,.35)', crossover: 'rgba(176,108,255,.45)', elite: 'rgba(240,230,235,.22)', experience: 'rgba(45,226,230,.3)' };

function createGraph3D(canvas, hover, toolbar) {
  const view = { azimuth: .6, elevation: .35, playing: !reducedMotion, hold: false, drag: null };
  let nodes = [], edges = [], heat = 1, running = false, frame = 0, last = 0, projected = [], order = [];
  const family = (task, name) => FAMILY_COLORS[Math.max(0, FAMILY_ORDER[task].indexOf(name)) % FAMILY_COLORS.length];

  function setData(task, graph) {
    const previous = new Map(nodes.map(n => [n.id, n]));
    const families = FAMILY_ORDER[task];
    const scores = graph.nodes.map(n => n.fitness).filter(Number.isFinite).sort((a, b) => a - b);
    const rank = v => scores.length > 1 && Number.isFinite(v) ? scores.findIndex(x => x >= v) / (scores.length - 1) : .3;
    nodes = graph.nodes.map((n, i) => {
      const old = previous.get(n.id);
      const f = Math.max(0, families.indexOf(n.family));
      const angle = f / families.length * Math.PI * 2;  // Families start in separate sectors, then the forces take over.
      return { ...n, color: family(task, n.family), weight: rank(n.fitness),
        x: old?.x ?? Math.cos(angle) * 1.2 + (Math.random() - .5) * .6, y: old?.y ?? (n.generation % 7 - 3) * .18 + (Math.random() - .5) * .3,
        z: old?.z ?? Math.sin(angle) * 1.2 + (Math.random() - .5) * .6, vx: 0, vy: 0, vz: 0, index: i };
    });
    const index = new Map(nodes.map((n, i) => [n.id, i]));
    edges = graph.edges.filter(e => index.has(e.source) && index.has(e.target)).map(e => ({ a: index.get(e.source), b: index.get(e.target), kind: e.kind }));
    heat = 1;
    draw();
  }

  function simulate() {
    const n = nodes.length;
    if (!n || heat < .002) return;
    const k = .55, repulsion = .018 * heat;
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const d2 = dx * dx + dy * dy + dz * dz + .01, f = repulsion / d2;
        dx *= f; dy *= f; dz *= f;
        a.vx += dx; a.vy += dy; a.vz += dz; b.vx -= dx; b.vy -= dy; b.vz -= dz;
      }
    }
    for (const e of edges) {
      const a = nodes[e.a], b = nodes[e.b];
      const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, d = Math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-6;
      const f = (d - k * .5) * .04 * heat / d;
      a.vx += dx * f; a.vy += dy * f; a.vz += dz * f; b.vx -= dx * f; b.vy -= dy * f; b.vz -= dz * f;
    }
    const centroids = {};
    for (const a of nodes) { const c = centroids[a.family] ||= { x: 0, y: 0, z: 0, n: 0 }; c.x += a.x; c.y += a.y; c.z += a.z; c.n++; }
    for (const a of nodes) {
      const c = centroids[a.family];
      a.vx += ((c.x / c.n - a.x) * .02 - a.x * .01) * heat; a.vy += ((c.y / c.n - a.y) * .02 - a.y * .01) * heat; a.vz += ((c.z / c.n - a.z) * .02 - a.z * .01) * heat;
      a.vx *= .82; a.vy *= .82; a.vz *= .82;
      a.x += a.vx; a.y += a.vy; a.z += a.vz;
    }
    heat *= .985;
  }

  function size() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(rect.width * ratio)) { canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio); }
    const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  function draw() {
    const setup = size();
    if (!setup) return;
    const { ctx, width, height } = setup;
    ctx.clearRect(0, 0, width, height);
    if (!nodes.length) return;
    let radius = .5;
    for (const n of nodes) radius = Math.max(radius, Math.hypot(n.x, n.y, n.z));
    const scale = Math.min(width, height) * .42 / radius;
    const ca = Math.cos(view.azimuth), sa = Math.sin(view.azimuth), ce = Math.cos(view.elevation), se = Math.sin(view.elevation);
    projected = nodes.map(n => {
      const xr = n.x * ca - n.z * sa, zr = n.x * sa + n.z * ca;
      const yr = n.y * ce - zr * se, depth = n.y * se + zr * ce;
      const persp = 1 / (1 + depth / radius * .35);
      return { x: width / 2 + xr * scale * persp, y: height / 2 - yr * scale * persp, depth, persp, node: n };
    });
    for (const e of edges) {  // Edges first, faint, so nodes glow above them.
      const a = projected[e.a], b = projected[e.b];
      ctx.strokeStyle = EDGE_STYLE[e.kind] || 'rgba(200,180,190,.18)';
      ctx.lineWidth = e.kind === 'crossover' ? 1.1 : .8;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    order = projected.map((p, i) => i).sort((i, j) => projected[j].depth - projected[i].depth);
    ctx.globalCompositeOperation = 'lighter';
    for (const i of order) {
      const p = projected[i], n = p.node, r = (2 + n.weight * 5) * p.persp;
      const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * (n.champion ? 5 : 3.2));
      glow.addColorStop(0, n.color + (n.champion ? 'cc' : '88')); glow.addColorStop(1, n.color + '00');
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(p.x, p.y, r * (n.champion ? 5 : 3.2), 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
    for (const i of order) {
      const p = projected[i], n = p.node, r = (2 + n.weight * 5) * p.persp;
      ctx.fillStyle = n.color; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
      if (n.champion) { ctx.strokeStyle = '#fff3f6'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2); ctx.stroke(); }
    }
  }

  function tick(now) {
    if (!running) return;
    frame = requestAnimationFrame(tick);
    if (now - last < 33) return;
    last = now;
    simulate();
    if (view.playing && !view.hold && !view.drag) view.azimuth += .0035;
    draw();
  }
  function showHover(mx, my) {
    let best = null, distance = 14;
    for (const p of projected) { const d = Math.hypot(p.x - mx, p.y - my); if (d < distance) { distance = d; best = p; } }
    if (!best) { hover.classList.add('hidden'); return; }
    const n = best.node;
    hover.innerHTML = (n.champion ? '★ CHAMPION<br>' : '') + esc(n.family) + ' · gen ' + esc(n.generation) + ' · ' + esc(n.operator) +
      '<br>' + esc(n.label) + '<br>fitness ' + (Number.isFinite(n.fitness) ? n.fitness.toFixed(3) : 'unscored');
    hover.style.left = Math.max(8, best.x + 12) + 'px'; hover.style.top = Math.max(8, best.y - 60) + 'px';
    hover.classList.remove('hidden');
  }
  canvas.addEventListener('pointerdown', event => { view.drag = { x: event.clientX, y: event.clientY, a: view.azimuth, e: view.elevation }; });
  window.addEventListener('pointerup', () => { view.drag = null; });
  canvas.addEventListener('pointermove', event => {
    const rect = canvas.getBoundingClientRect();
    if (view.drag) { view.azimuth = view.drag.a + (event.clientX - view.drag.x) / 160; view.elevation = Math.max(-1.2, Math.min(1.2, view.drag.e + (event.clientY - view.drag.y) / 200)); if (!running) draw(); }
    showHover(event.clientX - rect.left, event.clientY - rect.top);
  });
  canvas.addEventListener('pointerenter', () => { view.hold = true; });
  canvas.addEventListener('pointerleave', () => { view.hold = false; hover.classList.add('hidden'); });
  canvas.addEventListener('focus', () => { view.hold = true; });
  canvas.addEventListener('blur', () => { view.hold = false; });
  const setPlaying = playing => { view.playing = playing; const b = toolbar.querySelector('[data-surface=play]'); if (b) { b.textContent = playing ? 'Ⅱ' : '▶'; b.setAttribute('aria-pressed', String(!playing)); b.setAttribute('aria-label', playing ? 'Pause animation' : 'Play animation'); } };
  const rotate = (da, de = 0) => { view.azimuth += da; view.elevation = Math.max(-1.2, Math.min(1.2, view.elevation + de)); draw(); };
  canvas.addEventListener('keydown', event => {
    const keys = { ArrowLeft: () => rotate(-.15), ArrowRight: () => rotate(.15), ArrowUp: () => rotate(0, .08), ArrowDown: () => rotate(0, -.08),
      ' ': () => setPlaying(!view.playing), Home: () => { view.azimuth = .6; view.elevation = .35; draw(); } };
    if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
  });
  toolbar.querySelectorAll('[data-surface]').forEach(button => button.addEventListener('click', () => {
    const a = button.dataset.surface;
    if (a === 'play') setPlaying(!view.playing); else if (a === 'left') rotate(-.3); else if (a === 'right') rotate(.3);
    else if (a === 'reset') { view.azimuth = .6; view.elevation = .35; heat = .6; draw(); }
  }));
  if (reducedMotion) setPlaying(false);
  return { setData, start() { if (running) return; if (reducedMotion) { for (let i = 0; i < 200; i++) simulate(); draw(); return; } running = true; last = 0; frame = requestAnimationFrame(tick); },
    stop() { running = false; cancelAnimationFrame(frame); }, draw };
}

const evolutionGraph = createGraph3D($('evo-graph'), $('evo-hover'), $('evo-toolbar'));

function renderEvolution() {
  const learning = current.learning;
  $('evo-error').textContent = current.learningError || '';
  $('evo-memories').textContent = integer(learning?.memories || 0) + ' MEMORIES';
  const task = learning?.tasks?.[evolutionTask];
  if (!task) { syncSurfaceAnimation(); return; }
  evolutionGraph.setData(evolutionTask, task.graph);
  $('evo-subtitle').textContent = task.graph.nodes.length + ' models tested · ' + task.graph.edges.length + ' lineage links · ' + task.blocks +
    ' forward-scored blocks · ' + esc(learning.dataset || '') + ' · drag or arrow keys to rotate';
  // The CSP forbids inline style attributes, so swatch colours are applied through the CSSOM.
  $('evo-legend').innerHTML = FAMILY_ORDER[evolutionTask].map((f, i) => '<span><i class="dot-swatch" data-color="' + i + '"></i>' + esc(f) + '</span>').join('') +
    '<span><i class="line-swatch mutation"></i>mutation</span><span><i class="line-swatch crossover"></i>crossover</span><span>◎ champion</span>';
  $('evo-legend').querySelectorAll?.('[data-color]').forEach(swatch => { swatch.style.background = FAMILY_COLORS[Number(swatch.dataset.color)]; swatch.style.color = FAMILY_COLORS[Number(swatch.dataset.color)]; });
  const card = (name, unit) => {
    const t = learning.tasks[name];
    if (!t) return '';
    const champion = t.champion ? Object.entries(t.champion).map(([k, v]) => esc(k) + '=' + esc(v)).join(' · ') : '—';
    const better = Number.isFinite(t.mean_out_of_sample) && Number.isFinite(t.mean_baseline) && t.mean_out_of_sample > t.mean_baseline;
    return '<div class="champion-card"><div class="champion-head"><span class="tag">' + esc(name.toUpperCase()) + '</span><span class="' + (better ? 'good' : 'neutral') + '">' +
      (better ? '▲ beats baseline' : '■ baseline holds') + '</span></div><div class="champion-genome">' + champion + '</div>' +
      '<div class="champion-stats">out-of-sample ' + number(t.mean_out_of_sample, 3) + ' vs baseline ' + number(t.mean_baseline, 3) + ' ' + unit +
      '<br>' + integer(t.blocks) + ' blocks · incumbent kept ' + percent(t.guard_share, 0) + ' · ' + integer(t.evaluations) + ' evaluations</div></div>';
  };
  $('evo-champions').className = 'champions';
  $('evo-champions').innerHTML = card('risk', '(−pinball ×1e4)') + card('alpha', '(R² %)') +
    '<p class="field-help">' + integer((learning.history || []).length) + ' learning runs · last ' + esc(fullTime(learning.at)) + ' · ' + number(learning.seconds, 1) + ' s</p>';
  drawLearningCurve(task);
  syncSurfaceAnimation();
}

function drawLearningCurve(task) {
  const canvas = $('evo-curve');
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.font = '11px Consolas, monospace';
  const points = task.curve.filter(c => Number.isFinite(c.out_of_sample_score) && Number.isFinite(c.baseline_score));
  if (!points.length) return;
  const values = points.flatMap(c => [c.out_of_sample_score, c.baseline_score]);
  let low = Math.min(...values), high = Math.max(...values); const pad = (high - low) * .15 || .1; low -= pad; high += pad;
  const plot = grid(ctx, rect.width, rect.height, low, high, v => v.toFixed(1),
    [points[0].period.slice(0, 10), '', '', '', points.at(-1).period.slice(-10)]);
  const x = i => plot.left + (plot.right - plot.left) * (points.length === 1 ? .5 : i / (points.length - 1));
  const y = v => plot.bottom - (v - low) / (high - low) * (plot.bottom - plot.top);
  ctx.setLineDash([5, 4]); ctx.strokeStyle = '#a8939c'; ctx.lineWidth = 1.5; ctx.beginPath();
  points.forEach((c, i) => i ? ctx.lineTo(x(i), y(c.baseline_score)) : ctx.moveTo(x(i), y(c.baseline_score))); ctx.stroke(); ctx.setLineDash([]);
  ctx.strokeStyle = '#ff2a55'; ctx.lineWidth = 2; ctx.beginPath();
  points.forEach((c, i) => i ? ctx.lineTo(x(i), y(c.out_of_sample_score)) : ctx.moveTo(x(i), y(c.out_of_sample_score))); ctx.stroke();
  points.forEach((c, i) => { ctx.beginPath(); ctx.arc(x(i), y(c.out_of_sample_score), 4, 0, Math.PI * 2);
    if (c.guard_kept_baseline) { ctx.strokeStyle = '#ff2a55'; ctx.lineWidth = 1.5; ctx.fillStyle = '#0b0910'; ctx.fill(); ctx.stroke(); }
    else { ctx.fillStyle = '#ff2a55'; ctx.fill(); } });
  const wins = points.filter(c => c.out_of_sample_score > c.baseline_score).length;
  $('evo-curve-badge').textContent = wins + ' of ' + points.length + ' blocks beat the baseline';
  $('evo-curve-legend').innerHTML = '<span><i class="line"></i>Frozen champion, next block</span><span><i class="line dashed"></i>Fixed baseline</span><span>○ incumbent kept (change not significant)</span>';
}

document.querySelectorAll('[data-task]').forEach(button => button.addEventListener('click', () => {
  evolutionTask = button.dataset.task;
  document.querySelectorAll('[data-task]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-checked', String(b === button)); });
  renderEvolution();
}));
$('learn-now').addEventListener('click', async () => {
  const button = $('learn-now');
  button.setAttribute('aria-busy', 'true'); button.textContent = 'Evolving…';
  await action(() => window.quant.learnNow(), 'Learning step complete.');
  button.removeAttribute('aria-busy'); button.textContent = 'Learn now';
});

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
  context.font = '11px Consolas, monospace';
  return { context, width: rect.width, height: rect.height };
}

function grid(context, width, height, low, high, format, labels = []) {
  const plot = { left: 43, top: 14, right: width - 15, bottom: height - 30 };
  for (let step = 0; step <= 4; step++) {
    const y = plot.top + (plot.bottom - plot.top) * step / 4;
    context.strokeStyle = '#3a1a2899';
    context.lineWidth = .7;
    context.beginPath(); context.moveTo(plot.left, y); context.lineTo(plot.right, y); context.stroke();
    context.fillStyle = '#bda9b2'; context.textAlign = 'right';
    context.fillText(format(high - (high - low) * step / 4), plot.left - 9, y + 3);
  }
  for (let step = 0; step <= 4; step++) {
    const x = plot.left + (plot.right - plot.left) * step / 4;
    context.strokeStyle = '#3a1a2866';
    context.beginPath(); context.moveTo(x, plot.top); context.lineTo(x, plot.bottom); context.stroke();
    if (labels[step] !== undefined) {
      context.fillStyle = '#bda9b2'; context.textAlign = step === 0 ? 'left' : step === 4 ? 'right' : 'center';
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
  $('surface-toolbar').classList.toggle('hidden', !surfaceMode);
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
    gradient.addColorStop(0, '#ff2a5520'); gradient.addColorStop(1, '#ff2a5502');
    ctx.beginPath(); ctx.moveTo(x(0), plot.bottom);
    curve.forEach((point, i) => ctx.lineTo(x(i), y(point.strategy)));
    ctx.lineTo(x(curve.length - 1), plot.bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
    for (const [key, color, dashed] of [['cash', '#6b5560', [2, 5]], ['equal_weight', '#a8939c', [5, 4]], ['strategy', '#ff2a55', []]]) {
      ctx.strokeStyle = color; ctx.lineWidth = key === 'strategy' ? 1.7 : 1.2; ctx.setLineDash(dashed);
      ctx.beginPath(); curve.forEach((point, i) => i ? ctx.lineTo(x(i), y(point[key])) : ctx.moveTo(x(i), y(point[key]))); ctx.stroke();
    }
    ctx.setLineDash([]);
    const last = curve[curve.length - 1]; ctx.fillStyle = '#ff7a95'; ctx.beginPath(); ctx.arc(x(curve.length - 1), y(last.strategy), 3, 0, Math.PI * 2); ctx.fill();
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
      ctx.fillStyle = bin.high < -report.monte_carlo.var95 ? '#ff2a555c' : '#ff2a558a';
      ctx.fillRect(plot.left + index * barWidth + .6, plot.bottom - barHeight, Math.max(1, barWidth - 1.2), barHeight);
    });
    const q05 = -report.monte_carlo.var95;
    const x = plot.left + (q05 - left) / (right - left) * (plot.right - plot.left);
    ctx.strokeStyle = '#ffb347'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(x, plot.top); ctx.lineTo(x, plot.bottom); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#ffb347'; ctx.fillText('5% tail', Math.min(plot.right - 50, x + 7), plot.top + 11);
    $('chart-subtitle').textContent = integer(report.parameters.paths) + ' simulated paths · ' + report.parameters.horizon + ' observations · seed ' + report.parameters.seed;
    $('chart-legend').innerHTML = '<span><i class="line mint"></i>Gaussian paths per bin</span><span><i class="line bootstrap"></i>Bootstrap VaR ' + percent(report.bootstrap.var95) + '</span>';
  } else if (chartMode === 'correlation') {
    const count = Math.min(12, report.assets.length);
    const cell = Math.min((width - 160) / count, (height - 50) / count, 60);
    const left = 117, top = 16;
    for (let row = 0; row < count; row++) {
      ctx.textAlign = 'right'; ctx.fillStyle = '#d8c8cf'; ctx.font = '9px Segoe UI, sans-serif';
      ctx.fillText(report.assets[row].length > 17 ? report.assets[row].slice(0, 15) + '…' : report.assets[row], left - 8, top + row * cell + cell / 2 + 3);
      for (let col = 0; col < count; col++) {
        const value = report.correlation[row][col];
        const magnitude = Math.abs(value);
        ctx.fillStyle = value >= 0 ? `rgba(45,226,230,${.10 + magnitude * .65})` : `rgba(255,42,85,${.10 + magnitude * .65})`;
        ctx.fillRect(left + col * cell + 1, top + row * cell + 1, cell - 2, cell - 2);
        if (cell >= 22) { ctx.textAlign = 'center'; ctx.font = '11px Consolas, monospace'; ctx.fillStyle = '#fff3f6'; ctx.fillText(value.toFixed(2), left + col * cell + cell / 2, top + row * cell + cell / 2 + 3); }
      }
    }
    ctx.textAlign = 'center'; ctx.font = '11px Consolas, monospace'; ctx.fillStyle = '#bda9b2';
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
      ctx.fillStyle = variant.lookback === report.parameters.lookback ? '#ff2a55' : '#5a1a30';
      ctx.fillRect(x, Math.min(zero, end), step * .46, Math.max(1, Math.abs(end - zero)));
      ctx.textAlign = 'center'; ctx.fillStyle = '#d8c8cf';
      ctx.fillText(percent(variant.total_return, 1), x + step * .23, end + (variant.total_return >= 0 ? -8 : 15));
      ctx.fillStyle = '#bda9b2'; ctx.fillText(variant.lookback + ' obs', x + step * .23, height - 10);
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
$('calculate-options').addEventListener('click', async () => {
  const button = $('calculate-options');
  $('options-error').textContent = '';
  let inputs;
  try { inputs = optionInputs(); } catch (error) { $('options-error').textContent = error.message; return; }
  button.setAttribute('aria-busy', 'true'); button.textContent = 'Calculating…';
  const result = await action(async () => window.quant.calculateOptions(inputs), 'Option calculated locally.');
  button.removeAttribute('aria-busy'); button.textContent = 'Calculate option';
  if (!result && current.state.lastError) $('options-error').textContent = current.state.lastError;
});
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

// ---- Assistant (typed or dictated with Handy / Win+H) ----
let askPending = null;
function askOpen(open = true) {
  $('ask-panel').classList.toggle('hidden', !open);
  $('ask-backdrop').classList.toggle('hidden', !open);
  if (open) { $('ask-input').focus(); $('ask-input').select?.(); } else $('open-ask').focus();
}
function askEntry(kind, meta, text) {
  const item = document.createElement('li');
  item.className = kind;
  item.innerHTML = '<span class="meta">' + esc(meta) + '</span>' + esc(text);
  $('ask-log').prepend(item);
  while ($('ask-log').children.length > 40) $('ask-log').lastChild.remove();
  return item;
}
function askApply(result) {
  if (result.snapshot) receive(result.snapshot);
  const kind = result.tier === 'refused' ? 'refused' : result.source === 'local-model' ? 'model' : 'engine';
  const meta = (result.source === 'local-model' ? 'LOCAL MODEL · UNVERIFIED' : 'ENGINE') + ' · ' + result.tier.toUpperCase();
  const item = askEntry(kind, meta, result.reply);
  if (result.options) {
    const o = result.options, set = (id, value) => { if (value !== undefined && $(id)) $(id).value = value; };
    set('opt-kind', o.kind); set('opt-spot', o.spot); set('opt-strike', o.strike); set('opt-time', Number(o.time.toFixed(4)));
    set('opt-volatility', +(o.volatility * 100).toFixed(4)); set('opt-rate', +(o.rate * 100).toFixed(4)); set('opt-dividend', +(o.dividend * 100).toFixed(4));
  }
  if (result.navigate) {
    navigate(result.navigate.page);
    if (result.navigate.chart) document.querySelector('.chart-tab[data-chart="' + result.navigate.chart + '"]')?.click();
  }
  if (result.confirm) {
    askPending = result.confirm.token;
    const actions = document.createElement('div');
    actions.className = 'ask-actions';
    actions.innerHTML = '<button type="button" class="primary" data-accept="true">Confirm</button><button type="button" class="secondary" data-accept="false">Cancel</button>';
    actions.querySelectorAll('button').forEach(button => button.addEventListener('click', async () => {
      actions.remove();
      const token = askPending; askPending = null;
      try { askApply(await window.quant.confirmAsk(token, button.dataset.accept === 'true')); }
      catch (error) { askEntry('refused', 'ERROR', error.message || String(error)); }
    }));
    item.append(actions);
    actions.querySelector('button').focus();
  }
}
async function askSend(text) {
  text = String(text || '').trim();
  if (!text) return;
  askEntry('you', 'YOU', text);
  $('ask-input').value = '';
  try { askApply(await window.quant.ask(text)); }
  catch (error) { askEntry('refused', 'ERROR', error.message || String(error)); }
}
$('open-ask').addEventListener('click', () => askOpen(true));
$('close-ask').addEventListener('click', () => askOpen(false));
$('ask-backdrop').addEventListener('click', () => askOpen(false));
$('ask-form').addEventListener('submit', event => { event.preventDefault(); void askSend($('ask-input').value); });
document.querySelectorAll('[data-ask]').forEach(chip => chip.addEventListener('click', () => { void askSend(chip.dataset.ask); }));
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); askOpen($('ask-panel').classList.contains('hidden')); }
  else if (event.key === 'Escape' && !$('ask-panel').classList.contains('hidden')) askOpen(false);
});

// ---- "Show the maths": step-by-step workings rendered from the report's own explanation ----
const mathsSelection = { options: 'black_scholes', report: 'gaussian_var' };
function renderMaths(scope) {
  const source = scope === 'options' ? current.options : current.report;
  const list = $(scope === 'options' ? 'maths-options' : 'maths-report');
  const steps = source?.explanation?.[mathsSelection[scope]];
  if (!steps || !steps.length) {
    list.innerHTML = '<li class="details-empty">' + (source ? 'Not available for this result (e.g. an older report or a degenerate input).' : scope === 'options' ? 'Calculate an option to see its workings.' : 'Run an analysis to see its workings.') + '</li>';
    return;
  }
  list.innerHTML = steps.map(step => '<li class="step"><span class="step-title">' + esc(step.title) + '</span><span class="step-formula">' + esc(step.formula) + '</span>' +
    (step.substitution ? '<span class="step-sub">= ' + esc(step.substitution) + '</span>' : '') + (step.result !== '' ? '<span class="step-result">= ' + esc(step.result) + '</span>' : '') +
    (step.note ? '<span class="step-note">' + esc(step.note) + '</span>' : '') + '</li>').join('') +
    (source.explanation.sources ? '<li class="maths-sources">Sources: ' + source.explanation.sources.map(esc).join(' · ') + '</li>' : '');
}
document.querySelectorAll('[data-maths]').forEach(button => button.addEventListener('click', () => {
  const [scope, key] = button.dataset.maths.split(':');
  mathsSelection[scope] = key;
  document.querySelectorAll('[data-maths^="' + scope + ':"]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-selected', String(b === button)); });
  renderMaths(scope);
}));


function renderPaper() {
  const p=current.paper; const active=Boolean(p?.id); const locked=Boolean(current.state.busy||operation||current.state.settingsPending);
  $('paper-create').disabled=locked;
  ['paper-import','paper-halt','paper-export'].forEach(id=>$(id).disabled=locked||!active);
  $('paper-refresh').disabled=locked;
  $('paper-error').textContent=current.paperError||'';
  $('paper-source').textContent=active ? p.config.mode+' · '+p.config.source+' · QQQ · local unverified custody' : 'No campaign or quote feed connected.';
  $('paper-health').textContent=active ? (p.engine_compatible===false?'Engine changed: export this campaign; new observations require a new freeze. ':'')+(p.halted?'Execution halted. ':'')+(p.evidence_complete?'':'Incomplete evidence: session gap recorded. ')+(p.feed_status||'')+' · '+p.quotes+' observations · '+p.warmup_quotes+' warmup quotes remaining'+(p.quote_age_seconds==null?'':' · quote age '+number(p.quote_age_seconds/3600,1)+' hours') : 'Freeze a campaign to start a separate, durable comparison.';
  $('paper-halt').textContent=p?.halted?'Resume paper execution':'Halt paper execution';
  $('paper-freeze').textContent=active?'Frozen engine '+p.config.engine_sha256.slice(0,12):'';
  const choices=(p?.campaigns||[]).map(c=>'<option value="'+esc(c.id)+'">'+esc(c.source)+' · '+esc(c.mode)+' · '+esc(c.id.slice(0,8))+'</option>').join('');
  if ($('paper-campaign').innerHTML!==choices) $('paper-campaign').innerHTML=choices;
  if(active)$('paper-campaign').value=p.id;
  const policyLabel=name=>({buyhold:'Nasdaq buy & hold',vol15_interval1:'Risk sizing · 1 close',vol15_interval5:'Risk sizing · 5 closes'}[name]||name);
  const money=x=>'$'+Number(x||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  $('paper-rows').innerHTML=(p?.books||[]).map(b=>'<tr><td>'+money(b.initial)+'</td><td>'+esc(policyLabel(b.strategy))+'</td><td>'+money(b.equity)+'</td><td>'+money(b.cash)+'</td><td>'+number(b.shares,6)+'</td><td>'+percent(b.net_return)+'</td><td>'+percent(b.drawdown)+'</td><td>'+money(b.fees)+'</td><td>'+money(b.excess_dollars)+'</td></tr>').join('')||'<tr><td colspan="9">No observations or positions yet.</td></tr>';
  $('paper-fills').innerHTML=(p?.recent_fills||[]).map(f=>'<div class="runtime-row"><span>'+esc(f.book.split(':')[1])+' USD · '+esc(policyLabel(f.book.split(':')[0]))+' · '+esc(f.side)+' · '+esc(f.status)+'</span><span>'+esc(f.quantity)+' shares · fee '+money(f.fee)+'</span></div>').join('')||'<p class="subtle">No execution outcomes yet.</p>';
  const curve=p?.curve||[];const scale=$('paper-scale').value||'100';const policies=['buyhold','vol15_interval1','vol15_interval5'];const colors=['#2de2e6','#ffb347','#ff2a55'];
  if(curve.length<2){$('paper-chart').innerHTML='<p class="subtle">Two or more observations are needed for a comparison curve.</p>';return;}
  const values=curve.flatMap(point=>policies.map(name=>Number(point.equity[name+':'+scale])));const lo=Math.min(...values),hi=Math.max(...values);const span=hi-lo||1;
  $('paper-chart').innerHTML='<svg viewBox="0 0 800 180" role="img" aria-label="Matched-capital simulated equity"><text x="12" y="16" fill="#b9aab1">'+esc(money(hi))+'</text>'+policies.map((name,i)=>'<polyline fill="none" stroke="'+colors[i]+'" stroke-width="2" points="'+curve.map((point,j)=>(j/(curve.length-1)*780+10).toFixed(2)+','+(165-(Number(point.equity[name+':'+scale])-lo)/span*135).toFixed(2)).join(' ')+'"/>').join('')+'</svg><p class="subtle">Cyan: buy-and-hold · gold: 1-close sizing · pink: 5-close sizing. Last '+curve.length+' observations; full returns remain in the journal.</p>';
}
$('paper-scale').addEventListener('change',renderPaper);
$('paper-create').addEventListener('click',()=>action(()=>window.quant.paperCommand({operation:'create',mode:$('paper-mode').value,source:$('paper-label').value}),'Paper campaign frozen'));
$('paper-refresh').addEventListener('click',()=>action(()=>window.quant.paperCommand({operation:'summary',id:$('paper-campaign').value||undefined})));
$('paper-campaign').addEventListener('change',()=>action(()=>window.quant.paperCommand({operation:'summary',id:$('paper-campaign').value})));
$('paper-import').addEventListener('click',()=>action(()=>window.quant.importPaperQuote(current.paper.id),'Quote processed'));
$('paper-halt').addEventListener('click',()=>action(()=>window.quant.paperCommand({operation:'control',id:current.paper.id,halted:!current.paper.halted})));
$('paper-export').addEventListener('click',async()=>{try{const result=await window.quant.exportPaper(current.paper.id);if(result)toast('Paper journal exported');}catch(error){toast(error.message,true);}});
