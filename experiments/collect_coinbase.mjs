// Opt-in public data collector; Node 24 built-in WebSocket. No trading API.
// Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [max-tickers]
// Timestamps are independently recorded on receipt. Samples are not complete trade tape.
import { appendFileSync, openSync, closeSync, fsyncSync } from 'node:fs';
import { spawn } from 'node:child_process';

const [product = 'BTC-USD', output = '', maxRaw = '25', pilotDir] = process.argv.slice(2);
if (!/^[A-Z0-9]{2,12}-[A-Z0-9]{2,12}$/.test(product)
  || !output || !/^\d+$/.test(maxRaw) || +maxRaw < 1 || +maxRaw > 10000) {
  throw new Error('Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [1..10000]');
}
if (typeof WebSocket !== 'function') throw new Error('Node.js 24 WebSocket support required');
const ws = new WebSocket('wss://ws-feed.exchange.coinbase.com');
let count = 0, previous = null, done = false;
const pilot = pilotDir ? spawn(process.env.QUANT_PYTHON || 'python',
  ['-m', 'experiments.live_pilot', '--root', pilotDir, '--product', product,
   '--model-commit', process.env.QUANT_MODEL_COMMIT || 'momentum-v1'],
  { stdio: ['pipe', 'pipe', 'inherit'] }) : null;
let pilotFailed = false;
let awaitingAck = 0;
let acknowledgementBuffer = '';
if (pilot) {
  pilot.stdout.on('data', chunk => {
    acknowledgementBuffer += chunk.toString();
    for (let cut; (cut = acknowledgementBuffer.indexOf('\n')) >= 0;) {
      const line = acknowledgementBuffer.slice(0, cut);
      acknowledgementBuffer = acknowledgementBuffer.slice(cut + 1);
      try {
        const response = JSON.parse(line);
        if (response.ack === undefined) continue;
        if (response.ack !== awaitingAck) {
          pilotFailed = true;
          return end('Unexpected or duplicate pilot acknowledgement.', 2);
        }
        awaitingAck = 0;
      } catch {
        pilotFailed = true;
        return end('Invalid pilot acknowledgement.', 2);
      }
    }
  });
  pilot.on('error', () => { pilotFailed = true; end('Pilot process unavailable.', 2); });
  pilot.on('exit', code => { if (code !== 0) { pilotFailed = true; end('Pilot process failed.', 2); } });
}

const end = (why, code) => {
  if (done) return;
  done = true;
  try { ws.close(); } catch {}
  if (pilot && !pilot.stdin.destroyed) pilot.stdin.end();
  console.error(why);
  process.exitCode = code;
};
const timeout = setTimeout(() => end('Feed timeout; no prediction claims.', 2), 120000);
ws.addEventListener('open', () => {
  ws.send(JSON.stringify({ type: 'subscribe', product_ids: [product], channels: ['ticker', 'heartbeat'] }));
});
ws.addEventListener('message', event => {
  if (done) return;
  try {
    const msg = JSON.parse(String(event.data));
    if (msg.type === 'error') return end('Exchange rejected subscription.', 2);
    if (msg.type !== 'ticker') return;
    if (msg.product_id !== product || !/^[0-9]+$/.test(String(msg.trade_id))
      || !Number.isSafeInteger(msg.sequence) || !Number.isSafeInteger(msg.trade_id)
      || !Number.isFinite(Number(msg.price)) || Number(msg.price) <= 0
      || !Number.isFinite(Date.parse(msg.time))) return end('Invalid ticker payload.', 2);
    if (previous && (msg.sequence <= previous.sequence || msg.trade_id <= previous.trade_id
      || Date.parse(msg.time) < Date.parse(previous.time))) return end('Non-monotonic feed; manual restart required.', 2);
    const observed = new Date().toISOString();
    if (Date.parse(msg.time) > Date.parse(observed) + 5000) return end('Exchange event time is ahead of receipt clock.', 2);
    if (pilotFailed || (pilot && (pilot.exitCode !== null || pilot.stdin.destroyed))) return end('Pilot unavailable, refusing unscored samples.', 2);
    if (pilot && awaitingAck !== 0) return end('Tick arrived before durable pilot acknowledgement; prospective interval invalid.', 2);
    previous = msg;
    const sample = { source: 'coinbase_exchange_ticker', product_id: product,
      event_at: msg.time, received_at: observed, sequence: msg.sequence,
      trade_id: msg.trade_id, price: Number(msg.price),
      feed_is_complete: false, prediction_eligible: true };
    const fd = openSync(output, 'a', 0o600);
    try { appendFileSync(fd, JSON.stringify(sample) + '\n'); fsyncSync(fd); }
    finally { closeSync(fd); }
    if (pilot) {
      awaitingAck = count + 1;
      if (!pilot.stdin.write(JSON.stringify(sample) + '\n'))
        return end('Pilot backpressure; refusing late forecasts.', 2);
    }
    count++;
    if (count >= +maxRaw) { clearTimeout(timeout); end('Finished collecting ' + count + ' tickers.', 0); }
  } catch (err) { end('Malformed exchange message: ' + err.message, 2); }
});
ws.addEventListener('error', () => end('WebSocket transport error.', 2));
ws.addEventListener('close', () => { clearTimeout(timeout); if (!done) end('Feed disconnected; restart manually.', 2); });
