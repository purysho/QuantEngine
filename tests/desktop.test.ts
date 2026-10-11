import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

async function configModule() {
  const value = await import('../desktop/config.js').catch(() => null);
  assert.ok(value, 'Persistent desktop settings implementation is missing');
  return value;
}

async function engineModule() {
  const value = await import('../desktop/engine.js').catch(() => null);
  assert.ok(value, 'Sequential engine implementation is missing');
  return value;
}

const report = { parameters: { seed: 17 }, run: { id: 'run-1' } };

test('settings persist independently and startup resumption defaults to opt-in', async () => {
  const { ConfigStore } = await configModule();
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-settings-'));
  try {
    const file = path.join(folder, 'settings.json');
    const store = new ConfigStore(file, folder);
    assert.equal((await store.load()).resumeOnLaunch, false);
    assert.equal(store.value.startAtLogin, false);
    await store.update({ paths: 150000, intervalSeconds: 120 });
    const reopened = new ConfigStore(file, folder);
    assert.equal((await reopened.load()).paths, 150000);
    await assert.rejects(() => reopened.update({ paths: 1000001 }), /paths/i);
    assert.equal(JSON.parse(await readFile(file, 'utf8')).paths, 150000);
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('invalid settings do not trigger login or resume on restart', async () => {
  const { ConfigStore } = await configModule();
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-settings-'));
  try {
    const file = path.join(folder, 'settings.json');
    await writeFile(file, '{broken');
    const config = await new ConfigStore(file, folder).load();
    assert.equal(config.startAtLogin, false);
    assert.equal(config.resumeOnLaunch, false);
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('continuous start and manual run cannot create overlapping work', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  let resolve!: (value: Record<string, unknown>) => void;
  let calls = 0;
  const transport = {
    request: async () => { calls++; return new Promise<Record<string, unknown>>(r => { resolve = r; }); },
    cancel: async () => {},
  };
  const engine = new Engine(defaultConfig('/tmp/quant-test'), transport, async () => {});
  engine.datasets = [{ id: 'sample', kind: 'synthetic', rows: 504, retrieved_at: '2025-01-01' }];
  const pending = engine.start();
  await assert.rejects(() => engine.runOnce(), /already/i);
  assert.equal(calls, 1);
  resolve({ report, runs: [], stats: { completed: 1 } });
  await pending;
  assert.equal(engine.state.phase, 'waiting');
  await engine.pause();
  assert.equal(engine.state.phase, 'paused');
});

test('pause cancels the active worker and retains the last completed report', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  let reject!: (reason: Error) => void;
  let cancellations = 0;
  const transport = {
    request: async (command: string) => command === 'history' ? { runs: [] } : new Promise<Record<string, unknown>>((_, r) => { reject = r; }),
    cancel: async () => { cancellations++; reject(new Error('Cancelled')); },
  };
  const engine = new Engine(defaultConfig('/tmp/quant-test'), transport, async () => {});
  engine.lastReport = report;
  engine.datasets = [{ id: 'sample', kind: 'synthetic', rows: 504, retrieved_at: '2025-01-01' }];
  const pending = engine.runOnce();
  await engine.pause();
  await pending;
  assert.equal(cancellations, 1);
  assert.equal(engine.state.busy, false);
  assert.equal(engine.state.phase, 'paused');
  assert.equal(engine.lastReport, report);
});

test('real transport preserves non-ASCII snapshot paths and asset names across pipe chunks', async () => {
  const { WorkerTransport } = await import('../desktop/transport.js');
  const folder = await mkdtemp(path.join(os.tmpdir(), '量化研究-'));
  try {
    const source = path.join(folder, '价格-énergie.csv');
    const rows = Array.from({ length: 80 }, (_, i) => {
      const date = new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10);
      return `${date},${100 + i * .1 + Math.sin(i)},${80 + i * .2 + Math.cos(i)}`;
    });
    await writeFile(source, 'date,资产一,Énergie\n' + rows.join('\n') + '\n', 'utf8');
    const transport = new WorkerTransport('python3', path.resolve('workers/quant_worker.py'), () => folder, () => true);
    const imported = await transport.request('import', { path: source });
    const dataset = imported.dataset as { id: string; assets: string[]; path: string };
    assert.deepEqual(dataset.assets, ['资产一', 'Énergie']);
    assert.match(dataset.path, /量化研究/);
    const result = await transport.request('analyse', { dataset_id: dataset.id, parameters: { paths: 1000, horizon: 5 } });
    const report = result.report as { assets: string[]; monte_carlo: { assumptions: string[] } };
    assert.deepEqual(report.assets, ['资产一', 'Énergie']);
    assert.ok(report.monte_carlo.assumptions.some(line => line.includes('−100%')));
  } finally { await rm(folder, { recursive: true, force: true }); }
});

test('research variants persist seeds and never use a lookback longer than the dataset', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  const requests: Array<Record<string, unknown>> = [];
  const config = defaultConfig('/tmp/quant-test');
  config.runSequence = 2;
  const engine = new Engine(config, {
    request: async (_command: string, values: Record<string, unknown>) => {
      requests.push(values); return { report, runs: [], stats: { completed: 1 } };
    }, cancel: async () => {},
  }, async () => {});
  engine.datasets = [{ id: 'sample', kind: 'synthetic', rows: 45, retrieved_at: '2025-01-01' }];
  await engine.runOnce();
  const parameters = requests[0].parameters as { lookback: number; seed: number };
  assert.ok(parameters.lookback < 43);
  assert.equal(parameters.seed, config.seed + 2);
  assert.equal(engine.config.runSequence, 3);
});

test('real worker pause recovers interrupted history before the next calculation', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  const { WorkerTransport } = await import('../desktop/transport.js');
  const folder = await mkdtemp(path.join(os.tmpdir(), 'quant-cancel-'));
  const config = defaultConfig(folder);
  config.paths = 1000;
  const transport = new WorkerTransport('python3', path.resolve('workers/quant_worker.py'), () => folder, () => true);
  const engine = new Engine(config, transport, async () => {});
  try {
    await engine.initialize();
    await engine.runOnce();
    const completed = engine.lastReport;
    await engine.configure({ paths: 1000000, horizon: 252 });
    let started!: () => void;
    const startSignal = new Promise<void>(resolve => { started = resolve; });
    engine.onChange = () => { if (engine.state.activeRunId) started(); };
    const pending = engine.runOnce();
    await startSignal;
    await engine.pause();
    await pending;
    assert.equal(engine.state.busy, false);
    assert.equal(engine.runs[0].status, 'interrupted');
    assert.equal(engine.lastReport, completed);
    await engine.configure({ paths: 1000, horizon: 5 });
    await engine.runOnce();
    assert.equal(engine.runs[0].status, 'completed');
    assert.equal(engine.runs[1].status, 'interrupted');
  } finally { await engine.pause(); await rm(folder, { recursive: true, force: true }); }
});

test('concurrent settings save in order and research waits until persistence settles', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  const saves: Array<{ config: Record<string, unknown>; finish: () => void }> = [];
  const engine = new Engine(defaultConfig('/tmp/quant-config-order'), {
    request: async () => ({ report, runs: [] }), cancel: async () => {},
  }, config => new Promise<void>(resolve => { saves.push({ config: { ...config }, finish: resolve }); }));
  const first = engine.configure({ paths: 120000 });
  const second = engine.configure({ horizon: 12 });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(saves.length, 1, 'A later save must wait for the earlier save');
  await assert.rejects(() => engine.start(), /settings.*sav/i);
  saves[0].finish();
  await first;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(saves.length, 2);
  assert.equal(saves[1].config.paths, 120000);
  saves[1].finish();
  await second;
  assert.equal(engine.config.paths, 120000);
  assert.equal(engine.config.horizon, 12);
});

test('failed automatic ECB refresh retains cached data and attempts only once per UTC day', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  const config = defaultConfig('/tmp/quant-ecb');
  config.datasetId = 'ecb';
  let refreshes = 0, calculations = 0;
  const engine = new Engine(config, {
    request: async (command: string) => {
      if (command === 'refresh') { refreshes++; throw new Error('Offline'); }
      calculations++;
      return { report, runs: [], stats: { completed: calculations } };
    }, cancel: async () => {},
  }, async () => {});
  engine.datasets = [{ id: 'ecb', kind: 'ecb', rows: 64, retrieved_at: '2025-01-01' }];
  await engine.start();
  await engine.runOnce();
  await engine.pause();
  assert.equal(refreshes, 1);
  assert.equal(calculations, 2);
  assert.match(engine.state.lastRefreshError || '', /saved snapshot.*Offline/);
});

test('shutdown drains an already authorized preference save before stopping the app', async () => {
  const { Engine } = await engineModule();
  const { defaultConfig } = await configModule();
  let finish!: () => void;
  const engine = new Engine(defaultConfig('/tmp/quant-shutdown'), {
    request: async () => ({ runs: [] }), cancel: async () => {},
  }, () => new Promise<void>(resolve => { finish = resolve; }));
  assert.equal(typeof engine.shutdown, 'function', 'Shutdown must drain authorized preference changes');
  const save = engine.configure({ startAtLogin: true });
  await new Promise(resolve => setImmediate(resolve));
  let stopped = false;
  const shutdown = engine.shutdown().then(() => { stopped = true; });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(stopped, false);
  await assert.rejects(() => engine.start(), /shutting down/i);
  finish();
  await save;
  await shutdown;
  assert.equal(stopped, true);
  assert.equal(engine.config.startAtLogin, true);
});
