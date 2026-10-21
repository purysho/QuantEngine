import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import type { AddressInfo } from 'node:net';

const load = () => import('../desktop/assistant.js');

test('dictated numbers become digits', async () => {
  const { wordsToDigits, normalise } = await load();
  assert.equal(wordsToDigits('strike one hundred and five'), 'strike 105');
  assert.equal(wordsToDigits('fifty thousand paths'), '50000 paths');
  assert.equal(wordsToDigits('vol of twenty five percent'), 'vol of 25 percent');
  assert.equal(wordsToDigits('two point five years'), '2.5 years');
  assert.equal(wordsToDigits('a hundred'), '100');
  assert.equal(wordsToDigits('price a put'), 'price a put');
  assert.equal(normalise('Set paths to 100,000.'), 'set paths to 100000');
});

test('option requests parse spoken or typed parameters with explicit defaults', async () => {
  const { parseCommand } = await load();
  const put = parseCommand('Price a put with strike ninety five, spot one hundred, six months, vol twenty five percent, rate 3%.');
  assert.equal(put.kind, 'price-option');
  if (put.kind !== 'price-option') return;
  assert.deepEqual({ ...put.parameters }, { kind: 'put', spot: 100, strike: 95, time: .5, volatility: .25, rate: .03, dividend: 0 });
  assert.deepEqual(put.assumed, []);
  const bare = parseCommand('price a call option');
  assert.equal(bare.kind, 'price-option');
  if (bare.kind === 'price-option') assert.ok(bare.assumed.includes('spot 100') && bare.assumed.includes('20% volatility'));
  const half = parseCommand('value a call strike 110 expiring in half a year vol 0.3');
  if (half.kind === 'price-option') { assert.equal(half.parameters.time, .5); assert.equal(half.parameters.volatility, .3); }
});

test('intents and permission tiers', async () => {
  const { parseCommand, TIERS } = await load();
  const cases: Array<[string, string]> = [
    ['what is my VaR?', 'answer'], ['How volatile is the portfolio', 'answer'], ['show the vol surface', 'navigate'],
    ['open options', 'navigate'], ['run once', 'run-once'], ['start the engine', 'start'], ['pause', 'pause'],
    ['set paths to fifty thousand', 'configure'], ['enable low cpu mode', 'configure'], ['refresh ECB rates', 'refresh-ecb'],
    ['undo', 'undo'], ['buy 100 shares of the stock', 'refuse'], ['send an order to my broker', 'refuse'],
    ['what are transaction costs in the backtest', 'answer'], ['help', 'help'], ['tell me a joke', 'unknown'],
    ['explain black scholes', 'explain'], ['explain my VaR', 'explain'], ['show me the maths for the portfolio', 'explain'],
    ['explain volatility clustering to me', 'unknown'],
  ];
  for (const [text, kind] of cases) assert.equal(parseCommand(text).kind, kind, text);
  assert.equal(TIERS.configure, 'change');
  assert.equal(TIERS.navigate, 'read');
  const surface = parseCommand('show the vol surface');
  if (surface.kind === 'navigate') assert.equal(surface.chart, 'surface');
  const minutes = parseCommand('set interval to 2 minutes');
  if (minutes.kind === 'configure') assert.equal(minutes.patch.intervalSeconds, 120);
});

function fakeEngine() {
  const calls: string[] = [];
  const engine = {
    config: { paths: 50_000, lowCpu: false } as any,
    snapshot: () => ({ state: { phase: 'paused', completed: 1 }, config: engine.config, report: {
      run: { id: 'r1' }, provenance: { name: 'Sample' }, annualized_volatility: .08, weights: { A: .6, B: .4 },
      monte_carlo: { horizon: 20, var95: .03, es95: .04 }, bootstrap: { var95: .035, es95: .045 },
      student_t: { var95: .033, es95: .05, degrees_of_freedom: 4.2 },
      backtest: { cost_bps: 10, total_return: -.1, sharpe: -.4, max_drawdown: -.2, baselines: { equal_weight: { total_return: .05 } } } }, options: null }),
    runOnce: async () => { calls.push('runOnce'); }, start: async () => { calls.push('start'); }, pause: async () => { calls.push('pause'); },
    configure: async (patch: any) => { calls.push('configure:' + JSON.stringify(patch)); Object.assign(engine.config, patch); },
    calculateOptions: async (p: any) => { calls.push('options'); return { black_scholes: { price: 4.08, delta: -.32 }, trees: { american: 4.15 }, parameters: p }; },
    dataCommand: async () => { calls.push('refresh'); },
  };
  return { engine, calls };
}

test('changes require confirmation, are logged and can be undone', async () => {
  const { Assistant } = await load();
  const { engine, calls } = fakeEngine();
  const log: any[] = [];
  const assistant = new Assistant(engine as any, async entry => { log.push(entry); });
  const asked = await assistant.handle('set paths to 100000');
  assert.ok(asked.confirm);
  assert.deepEqual(calls, [], 'Nothing changes before confirmation');
  await assistant.confirm(asked.confirm!.token, true);
  assert.equal(engine.config.paths, 100_000);
  await assert.rejects(() => assistant.confirm(asked.confirm!.token, true), /expired/);
  const undo = await assistant.handle('undo');
  await assistant.confirm(undo.confirm!.token, true);
  assert.equal(engine.config.paths, 50_000);
  const declined = await assistant.handle('enable low cpu');
  const cancelled = await assistant.confirm(declined.confirm!.token, false);
  assert.match(cancelled.reply, /nothing changed/i);
  assert.equal(engine.config.lowCpu, false);
  assert.ok(log.length >= 5);
  assert.ok(log.every(entry => typeof entry.at === 'string'));
});

test('answers come from the real report and refusals never touch the engine', async () => {
  const { Assistant } = await load();
  const { engine, calls } = fakeEngine();
  const assistant = new Assistant(engine as any);
  assert.match((await assistant.handle('what is my VaR')).reply, /Gaussian 3\.00%.*bootstrap 3\.50%.*Student-t 3\.30%/);
  assert.match((await assistant.handle('what is the sharpe ratio')).reply, /Sharpe -0\.40/);
  const refused = await assistant.handle('sell all my shares now');
  assert.equal(refused.tier, 'refused');
  const priced = await assistant.handle('price a put strike 95 spot 100 6 months vol 25%');
  assert.equal(priced.navigate?.page, 'options');
  assert.deepEqual(calls, ['options']);
});

test('local model is optional, localhost-only and answer-only', async () => {
  const { Assistant, validateLocalEndpoint } = await load();
  assert.throws(() => validateLocalEndpoint('https://api.example.com/v1'), /this computer/);
  let received: any;
  const server = http.createServer((request, response) => {
    let body = '';
    request.on('data', chunk => { body += chunk; });
    request.on('end', () => {
      received = { url: request.url, body: JSON.parse(body) };
      response.setHeader('content-type', 'application/json');
      response.end(JSON.stringify({ choices: [{ message: { content: 'Volatility clustering means calm and turbulent periods bunch together.' } }] }));
    });
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const port = (server.address() as AddressInfo).port;
    const { engine, calls } = fakeEngine();
    const assistant = new Assistant(engine as any, async () => {}, () => ({ endpoint: `http://127.0.0.1:${port}`, model: 'qwen' }));
    const reply = await assistant.handle('explain volatility clustering to me like a teacher');
    assert.equal(reply.source, 'local-model');
    assert.match(reply.reply, /bunch together/);
    assert.equal(received.url, '/v1/chat/completions');
    assert.equal(received.body.model, 'qwen');
    assert.match(received.body.messages[0].content, /cannot run calculations/);
    assert.doesNotMatch(received.body.messages[0].content, /report_path|\/tmp|D:\\\\/);
    assert.deepEqual(calls, []);
  } finally { server.close(); }
});

test('assistant settings accept only local endpoints', async () => {
  const { validatePatch } = await import('../desktop/config.js');
  assert.doesNotThrow(() => validatePatch({ assistantEndpoint: 'http://127.0.0.1:8080', assistantModel: 'qwen2.5:3b' }));
  assert.doesNotThrow(() => validatePatch({ assistantEndpoint: '' }));
  assert.throws(() => validatePatch({ assistantEndpoint: 'https://api.openai.com/v1' }), /localhost/);
});

test('navigation reaches the market terminal', async () => {
  const { parseCommand } = await import('../desktop/assistant.js');
  assert.deepEqual(parseCommand('open the terminal'), { kind: 'navigate', page: 'terminal', chart: undefined });
  assert.deepEqual(parseCommand('show market news'), { kind: 'navigate', page: 'terminal', chart: undefined });
  assert.equal(parseCommand('show the vol surface').kind, 'navigate');
});
