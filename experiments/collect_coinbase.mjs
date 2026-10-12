// Opt-in public data collector; Node 24 built-in WebSocket. No trading API.
// Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [max-tickers]
// Timestamps are independently recorded on receipt. Samples are not complete trade tape.
import fs from 'node:fs';
import { appendFileSync, openSync, closeSync, fsyncSync } from 'node:fs';

const [product = 'BTC-USD', output = '', maxRaw = '25'] = process.argv.slice(2);
if (!/^[A-Z0-9]{2,12}-[A-Z0-9]{2,12}$/.test(product)
  || !output || !/^\d+$/.test(maxRaw) || +maxRaw < 1 || +maxRaw > 10000) {
  throw new Error('Usage: node experiments/collect_coinbase.mjs BTC-USD samples.jsonl [1..10000]');
}
if (typeof WebSocket !== 'function') throw new Error('Node.js 24 WebSocket support required');
const ws = new WebSocket('wss://ws-feed.exchange.coinbase.com');
let count = 0, previous = null, done = false;
const end = (why, code) => {
  if (done) return;
  done = true;
  try { ws.close(); } catch {}
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
    previous = msg;
    const observed = new Date().toISOString();
    const sample = { source: 'coinbase_exchange_ticker', product_id: product,
      event_at: msg.time, received_at: observed, sequence: msg.sequence,
      trade_id: msg.trade_id, price: Number(msg.price),
      feed_is_complete: false, prediction_eligible: true };
    const fd = openSync(output, 'a', 0o600);
    try { appendFileSync(fd, JSON.stringify(sample) + '\n'); fsyncSync(fd); }
    finally { closeSync(fd); }
    count++;
    if (count >= +maxRaw) { clearTimeout(timeout); end('Finished collecting ' + count + ' tickers.', 0); }
  } catch (err) { end('Malformed exchange message: ' + err.message, 2); }
});
ws.addEventListener('error', () => end('WebSocket transport error.', 2));
ws.addEventListener('close', () => { clearTimeout(timeout); if (!done) end('Feed disconnected; restart manually.', 2); });
