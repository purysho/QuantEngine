'use strict';
// Authored renderer source; packaging/build.mjs emits app/ui.js.

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const percent = (value, digits = 2) => Number.isFinite(value) ? (value * 100).toFixed(digits) + '%' : '—';
const number = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const integer = value => Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
const shortTime = value => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const fullTime = value => value ? new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
let current = { state: { phase: 'paused', busy: false, continuous: false, completed: 0 }, config: {}, datasets: [], runs: [], report: null, runtime: {} };
let chartMode = 'equity';
let page = 'monitor';
let operation = false;
let previousReport;
let previousRuns;
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
  const labels = { monitor: 'Research monitor', datasets: 'Datasets', runs: 'Research runs', preferences: 'Preferences' };
  const kickers = { monitor: 'ENGINE / OVERVIEW', datasets: 'DATA / SNAPSHOTS', runs: 'RESEARCH / HISTORY', preferences: 'ENGINE / SETTINGS' };
  $('page-title').textContent = labels[name];
  $('page-kicker').textContent = kickers[name];
  document.querySelectorAll('.page').forEach(section => section.classList.toggle('hidden', section.id !== 'page-' + name));
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === name));
  if (name === 'monitor') requestAnimationFrame(drawChart);
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
  if (previousReport !== report) { previousReport = report; renderReport(); drawChart(); }
  if (previousRuns !== current.runs) { previousRuns = current.runs; renderRuns(); }
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
  $('risk-comparison').innerHTML = '<table class="risk-table"><thead><tr><th></th><th>Gaussian</th><th>Block bootstrap</th></tr></thead><tbody>' +
    [['VaR 95%', gaussian.var95, bootstrap.var95], ['Expected shortfall', gaussian.es95, bootstrap.es95], ['Probability of loss', gaussian.loss_probability, bootstrap.loss_probability]].map(([name, a, b]) => '<tr><td>' + name + '</td><td>' + percent(a) + '</td><td>' + percent(b) + '</td></tr>').join('') +
    '</tbody></table><div class="risk-note">' + integer(gaussian.paths) + ' paths each · ' + gaussian.horizon + ' observations · empirical blocks of ' + bootstrap.block_size + '<br>Cumulative arithmetic returns. Both estimates depend on historical inputs.</div>';
  $('allocation').className = 'allocation';
  $('allocation').innerHTML = Object.entries(report.weights).map(([asset, weight]) => '<div class="weight-row"><span class="weight-name" title="' + esc(asset) + '">' + esc(asset) + '</span><div class="weight-track"><div class="weight-fill" data-weight="' + weight + '"></div></div><span class="weight-value">' + percent(weight, 1) + '</span></div>').join('');
  document.querySelectorAll('.weight-fill').forEach(fill => { fill.style.width = Number(fill.dataset.weight) * 100 + '%'; });
  const parameters = report.parameters;
  $('report-provenance').innerHTML = 'RUN ' + esc(report.run.id) + ' · ' + esc(fullTime(report.run.completed_at)) + ' · ' + number(report.run.duration_ms / 1000, 2) + ' s<br>' +
    'SOURCE ' + esc(report.provenance.name) + ' · ' + report.observations + ' observations · ' + esc(report.date_range.start) + ' → ' + esc(report.date_range.end) + '<br>' +
    'SEED ' + parameters.seed + ' · LOOKBACK ' + parameters.lookback + ' · COST ' + parameters.cost_bps + ' bps · REBALANCE ' + parameters.rebalance + ' · SHRINKAGE ' + parameters.shrinkage + '<br>' +
    'SNAPSHOT SHA-256 ' + esc(report.provenance.sha256);
  $('methodology').innerHTML = '<div class="methodology-copy"><div class="section-label">Numerical methods</div><ul>' + report.methodology.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul><div class="section-label">Gaussian assumptions</div><ul>' + gaussian.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul><div class="section-label">Bootstrap assumptions</div><ul>' + bootstrap.assumptions.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul><div class="section-label">Historical and hypothetical stress</div><ul>' + report.stress.map(item => '<li>' + esc(item.name) + ': ' + percent(item.return) + ' · ' + esc(item.kind) + (item.date ? ' · ' + esc(item.date) : '') + '</li>').join('') + '</ul></div>';
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
  const chartTitles = { equity: 'Costed strategy & baselines', risk: 'Gaussian horizon-return distribution', correlation: 'Historical return correlations', sensitivity: 'Momentum lookback sensitivity' };
  $('chart-title').textContent = chartTitles[chartMode];
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
