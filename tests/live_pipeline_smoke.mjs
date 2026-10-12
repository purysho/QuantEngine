// End-to-end synthetic transport -> Node journal -> Python durable forecast -> settlement.
// No internet access, no trading, no npm dependencies beyond Node built-ins.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const temp = mkdtempSync(path.join(os.tmpdir(), 'quant-live-test-'));
try {
  const samples = path.join(temp, 'ticks.jsonl');
  const pilot = path.join(temp, 'pilot');
  const run = spawnSync(process.execPath, [
    '--import', './tests/mock_coinbase_ws.mjs',
    'experiments/collect_coinbase.mjs',
    'BTC-USD', samples, '6', pilot
  ], { cwd: process.cwd(), env: {
    ...process.env, QUANT_PYTHON: process.env.QUANT_PYTHON || 'python',
    QUANT_MODEL_COMMIT: 'synthetic-ci-frozen'
  }, encoding: 'utf8', timeout: 20000 });
  assert.equal(run.status, 0, 'Collector+pilot failed:\n' + run.stdout + '\n' + run.stderr);
  const ticks = readFileSync(samples, 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(ticks.length, 6);
  const status = readFileSync(samples + '.status.jsonl', 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(status.at(-1).state, 'complete');
  assert.equal(status.filter(s => s.state === 'received').length, 6);
  assert.equal(status.filter(s => s.state === 'processed').length, 6);
  for (const received of status.filter(s => s.state === 'received')) {
    const ack = status.find(s => s.state === 'processed' && s.index === received.index);
    assert.equal(ack.sample_sha256, received.sample_sha256);
  }
  const files = readdirSync(pilot);
  const committed = files.filter(file => file.endsWith('.forecast.json'));
  const settled = files.filter(file => file.endsWith('.settled.json'));
  assert.equal(committed.length, 3, 'Expected three forward predictions after warmup');
  assert.equal(settled.length, 2, 'Only later arrivals may settle an earlier prediction');
  for (const file of settled) {
    const result = JSON.parse(readFileSync(path.join(pilot, file), 'utf8'));
    assert.equal(result.model_commit, 'synthetic-ci-frozen');
    assert.ok(Number.isFinite(result.squared_losses.candidate));
  }
  console.log('MOCK_LIVE_PIPELINE_OK');
} finally {
  rmSync(temp, { recursive: true, force: true });
}
