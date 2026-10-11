import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { execFileSync } from 'node:child_process';

const PYTHON = process.env.QUANT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

test('accepted 60,000-observation histories render without argument overflow', async () => {
  const source = await readFile('app/ui-source.js', 'utf8');
  const elements = new Map<string, Record<string, unknown>>();
  const context2d = new Proxy({}, { get: (_t, key) => key === 'createLinearGradient' ? () => ({ addColorStop() {} }) : () => {} });
  function element(id: string): Record<string, unknown> {
    if (!elements.has(id)) elements.set(id, {
      id, style: {}, dataset: {}, textContent: '', innerHTML: '', value: '', type: '',
      classList: { add() {}, remove() {}, toggle() { return false; } },
      addEventListener() {}, setAttribute() {},
      getBoundingClientRect() { return { width: 740, height: 268, left: 0, top: 0 }; },
      getContext() { return context2d; },
    });
    return elements.get(id)!;
  }
  const sandbox = vm.createContext({
    document: { getElementById: element, querySelectorAll: () => [], body: element('body'), activeElement: null, addEventListener() {}, hidden: false },
    window: { devicePixelRatio: 1, addEventListener() {}, quant: { onState() {}, getState: () => new Promise(() => {}) } },
    ResizeObserver: class { observe() {} }, requestAnimationFrame: (callback: () => void) => callback(),
    cancelAnimationFrame() {}, performance: { now: () => 0 }, setTimeout: () => 1, clearTimeout() {}, console,
  });
  vm.runInContext(source, sandbox);
  const curve = Array.from({ length: 60_000 }, (_, i) => ({ date: '2025-01-01', strategy: 1 + i / 100000, equal_weight: 1 + i / 150000, cash: 1 }));
  const report = {
    annualized_volatility: .1, parameters: { horizon: 20, cost_bps: 10, seed: 17, lookback: 20, rebalance: 5, shrinkage: .1 },
    monte_carlo: { var95: .04, es95: .05, paths: 1000, horizon: 20, loss_probability: .5, assumptions: [] },
    bootstrap: { var95: .05, es95: .06, block_size: 5, loss_probability: .5, assumptions: [] },
    backtest: { sharpe: .8, total_return: .6 }, weights: { A: .5, B: .5 }, curve,
    run: { id: 'large-run', completed_at: '2026-10-11T00:00:00Z', duration_ms: 1000 },
    provenance: { kind: 'csv', name: 'Large CSV', sha256: 'a'.repeat(64) },
    observations: 60000, date_range: { start: '2000-01-01', end: '2025-01-01' }, methodology: [], stress: [],
  };
  sandbox.fixture = { state: { phase: 'paused', busy: false, completed: 1 }, config: {}, datasets: [], runs: [], runtime: {}, report };
  assert.doesNotThrow(() => vm.runInContext('receive(fixture)', sandbox));
  assert.equal(elements.get('metric-vol')!.textContent, '10.00%');
  assert.match(String(elements.get('chart-subtitle')!.textContent), /2000-01-01/);
});

test('options page and Student-t risk render from real worker reports', async () => {
  const source = await readFile('app/ui-source.js', 'utf8');
  const elements = new Map<string, Record<string, unknown>>();
  const context2d = new Proxy({}, { get: (_t, key) => key === 'createLinearGradient' ? () => ({ addColorStop() {} }) : () => {} });
  const element = (id: string): Record<string, unknown> => {
    if (!elements.has(id)) elements.set(id, { id, style: {}, dataset: {}, textContent: '', innerHTML: '', value: '', className: '',
      classList: { add() {}, remove() {}, toggle() { return false; } }, addEventListener() {}, setAttribute() {},
      getBoundingClientRect() { return { width: 740, height: 268, left: 0, top: 0 }; }, getContext() { return context2d; } });
    return elements.get(id)!;
  };
  const sandbox = vm.createContext({
    document: { getElementById: element, querySelectorAll: () => [], body: element('body'), activeElement: null, addEventListener() {}, hidden: false },
    window: { devicePixelRatio: 1, addEventListener() {}, quant: { onState() {}, getState: () => new Promise(() => {}) } },
    ResizeObserver: class { observe() {} }, requestAnimationFrame: () => 1,
    cancelAnimationFrame() {}, performance: { now: () => 0 }, setTimeout: () => 1, clearTimeout() {}, console,
  });
  vm.runInContext(source, sandbox);
  const script = 'import json,sys; sys.path.insert(0,"workers"); from quant_options import options_report; from quant_core import analyse, example_prices; ' +
    'o=options_report({"spot":42,"strike":40,"time":.5,"rate":.1,"volatility":.2,"paths":2000,"market_price":4.0}); o["runtime"]={"duration_ms":1}; ' +
    'd,a,p=example_prices(); r=analyse(d,a,p,paths=1000,horizon=5); r["run"]={"id":"x","completed_at":"2026-10-11T00:00:00Z","duration_ms":1}; ' +
    'r["provenance"]={"kind":"synthetic","name":"<b>sample</b>","sha256":"a"*64}; print(json.dumps({"options":o,"report":r}))';
  const fixture = JSON.parse(execFileSync(PYTHON, ['-c', script], { encoding: 'utf8' }));
  sandbox.fixture = { state: { phase: 'paused', busy: false, completed: 1 }, config: {}, datasets: [], runs: [], runtime: {}, ...fixture };
  assert.doesNotThrow(() => vm.runInContext('receive(fixture)', sandbox));
  const prices = String(elements.get('options-prices')!.innerHTML);
  assert.match(prices, /4\.7594/);
  assert.match(prices, /Implied volatility/);
  assert.match(String(elements.get('options-greeks')!.innerHTML), /Delta/);
  assert.match(String(elements.get('options-moves')!.innerHTML), /σ\/16/);
  assert.match(String(elements.get('options-surface-arbitrage')!.textContent), /no-arbitrage/);
  // Switching to the 3D tab renders the realised-volatility surface without throwing.
  assert.doesNotThrow(() => vm.runInContext("chartMode = 'surface'; drawChart(); page = 'options'; syncSurfaceAnimation()", sandbox));
  assert.match(String(elements.get('chart-title')!.textContent), /volatility surface/i);
  const risk = String(elements.get('risk-comparison')!.innerHTML);
  assert.match(risk, /Student-t/);
  assert.match(risk, /VaR 99%/);
  assert.match(String(elements.get('report-provenance')!.innerHTML), /&lt;b&gt;sample/);
});
