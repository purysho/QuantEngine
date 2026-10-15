// Opt-in public data collector; Node 24 built-in WebSocket. No trading API.
// Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [max-tickers]
// Timestamps are independently recorded on receipt. Samples are not complete trade tape.
import { appendFileSync, openSync, closeSync, fsyncSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

const [product = 'BTC-USD', output = '', maxRaw = '25', pilotDir] = process.argv.slice(2);
if (!/^[A-Z0-9]{2,12}-[A-Z0-9]{2,12}$/.test(product)
  || !output || !/^\d+$/.test(maxRaw) || +maxRaw < 1 || +maxRaw > 10000) {
  throw new Error('Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [1..10000]');
}
if (typeof WebSocket !== 'function') throw new Error('Node.js 24 WebSocket support required');
// A run owns fresh evidence paths. Partial files remain for crash inspection.
const journalFd = openSync(output, 'wx', 0o600);
const statusFd = openSync(output + '.status.jsonl', 'wx', 0o600);
function status(record) {
  appendFileSync(statusFd, JSON.stringify(record) + '\n');
  fsyncSync(statusFd);
}
status({state: 'started', product, pilot: Boolean(pilotDir)});
const ws = new WebSocket('wss://ws-feed.exchange.coinbase.com');
let count = 0, previous = null, done = false;
const pilot = pilotDir ? spawn(process.env.QUANT_PYTHON || 'python',
  ['-m', 'experiments.live_pilot', '--root', pilotDir, '--product', product,
   '--model-commit', process.env.QUANT_MODEL_COMMIT || 'momentum-v1'],
  { stdio: ['pipe', 'pipe', 'inherit'] }) : null;
let pilotFailed = false;
let awaitingAck = 0;
let acknowledgementBuffer = '';
let shutdownTimer;
let pendingDigest;
let pilotClosed = false;
let requestedCode = 2;
const finish = (code, why) => {
  clearTimeout(shutdownTimer);
  status({state: code === 0 ? 'complete' : 'failed', count, pending: awaitingAck, reason: why});
  closeSync(journalFd); closeSync(statusFd);
  console.error(why);
  process.exitCode = code;
};
if (pilot) {
  pilot.stdout.on('data', chunk => {
    acknowledgementBuffer += chunk.toString();
    for (let cut; (cut = acknowledgementBuffer.indexOf('\n')) >= 0;) {
      const line = acknowledgementBuffer.slice(0, cut);
      acknowledgementBuffer = acknowledgementBuffer.slice(cut + 1);
      try {
        const response = JSON.parse(line);
        if (response.ack === undefined) continue;
        if (!Number.isSafeInteger(response.ack) || awaitingAck === 0 || response.ack !== awaitingAck) {
          pilotFailed = true;
          return end('Unexpected or duplicate pilot acknowledgement.', 2);
        }
        status({state: 'processed', index: awaitingAck, sample_sha256: pendingDigest});
        awaitingAck = 0;
      } catch {
        pilotFailed = true;
        return end('Invalid pilot acknowledgement.', 2);
      }
    }
  });
  pilot.on('error', () => { pilotFailed = true; end('Pilot process unavailable.', 2); });
  pilot.stdin.on('error', () => { pilotFailed = true; end('Pilot input pipe failed.', 2); });
  pilot.on('close', code => {
    pilotClosed = true;
    const ok = done && requestedCode === 0 && code === 0 && awaitingAck === 0 && !pilotFailed;
    if (!done) end('Pilot exited prematurely.', 2);
    finish(ok ? 0 : 2, ok ? 'Finished collecting and acknowledging ' + count + ' tickers.'
      : 'Pilot failed or final acknowledgement missing.');
  });
}

const end = (why, code) => {
  if (done) { if (code !== 0) { requestedCode = 2; pilotFailed = true; } return; }
  done = true;
  requestedCode = code;
  clearTimeout(timeout);
  try { ws.close(); } catch {}
  if (pilot && !pilotClosed) {
    if (!pilot.stdin.destroyed) pilot.stdin.end();
    // A missing ACK or EOF hang must not keep an apparently successful run alive.
    shutdownTimer = setTimeout(() => {
      pilotFailed = true; requestedCode = 2;
      pilot.kill('SIGKILL');
    }, 5000);
    if (code !== 0) console.error(why);
  } else if (!pilot) finish(code, why);
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
    const raw = JSON.stringify(sample) + '\n';
    pendingDigest = createHash('sha256').update(raw).digest('hex');
    appendFileSync(journalFd, raw); fsyncSync(journalFd);
    status({state: 'received', index: count + 1, sample_sha256: pendingDigest});
    if (pilot) {
      awaitingAck = count + 1;
      if (!pilot.stdin.write(JSON.stringify(sample) + '\n'))
        return end('Pilot backpressure; refusing late forecasts.', 2);
    }
    if (!pilot) status({state: 'archived_only', index: count + 1, sample_sha256: pendingDigest});
    count++;
    if (count >= +maxRaw) { clearTimeout(timeout); end('Finished collecting ' + count + ' tickers.', 0); }
  } catch (err) { end('Malformed exchange message: ' + err.message, 2); }
});
ws.addEventListener('error', () => end('WebSocket transport error.', 2));
ws.addEventListener('close', () => { clearTimeout(timeout); if (!done) end('Feed disconnected; restart manually.', 2); });
