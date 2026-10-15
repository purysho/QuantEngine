import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const tmp = mkdtempSync(path.join(os.tmpdir(), 'quant-journal-'));
try {
  const journal = path.join(tmp, 'ticks.jsonl');
  const original = '{"old_run":true}\n';
  writeFileSync(journal, original);
  const run = spawnSync(process.execPath, ['--import', './tests/mock_coinbase_ws.mjs',
    'experiments/collect_coinbase.mjs', 'BTC-USD', journal, '1'],
    {encoding:'utf8', timeout:10000});
  assert.notEqual(run.status, 0, 'Reusing a journal must fail before connecting');
  assert.equal(readFileSync(journal, 'utf8'), original, 'Existing evidence must not be appended');
  for (const mode of ['missing', 'hang', 'duplicate', 'invalid']) {
    const output = path.join(tmp, mode + '.jsonl');
    const fault = spawnSync(process.execPath, ['--import', './tests/mock_coinbase_ws.mjs',
      '--import', './tests/mock_pilot_spawn.mjs', 'experiments/collect_coinbase.mjs',
      'BTC-USD', output, '1', path.join(tmp, mode)],
      {encoding:'utf8', timeout:12000, env:{...process.env, QUANT_TEST_PILOT_MODE:mode}});
    assert.equal(fault.status, 2, mode + ' must fail, not hang or claim success: ' + fault.stderr);
    const states = readFileSync(output + '.status.jsonl','utf8').trim().split('\n').map(JSON.parse);
    assert.equal(states.at(-1).state, 'failed');
    assert.equal(states.filter(s => s.state === 'complete').length, 0);
    assert.equal(readFileSync(output, 'utf8').trim().split('\n').length, 1);
  }
  for (const mode of ['rapid', 'duplicate', 'future']) {
    const output = path.join(tmp, 'feed-' + mode + '.jsonl');
    const fault = spawnSync(process.execPath, ['--import', './tests/mock_coinbase_ws.mjs',
      'experiments/collect_coinbase.mjs', 'BTC-USD', output, '6', path.join(tmp, 'pilot-' + mode)],
      {encoding:'utf8', timeout:12000, env:{...process.env,
        QUANT_PYTHON:process.env.QUANT_PYTHON || 'python', QUANT_TEST_FEED_MODE:mode}});
    assert.equal(fault.status, 2, mode + ' must fail closed: ' + fault.stderr);
    const states=readFileSync(output+'.status.jsonl','utf8').trim().split('\n').map(JSON.parse);
    assert.equal(states.at(-1).state,'failed');
  }
  console.log('COLLECTOR_INTEGRITY_OK: reuse, missing ACK, hung child, duplicate ACK, malformed ACK');
} finally { rmSync(tmp, {recursive:true, force:true}); }
