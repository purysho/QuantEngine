// Independent, read-only Kraken Spot WebSocket v2 ticker sampling.
// Usage: node experiments/collect_kraken.mjs BTC/USD ./kraken.jsonl 25
// Research provenance ONLY, not a complete trade tape or prediction channel.
import { openSync, appendFileSync, fsyncSync, closeSync } from 'node:fs';

const [symbol = 'BTC/USD', output = '', limitRaw = '25'] = process.argv.slice(2);
if (!/^[A-Z0-9]{2,12}\/[A-Z0-9]{2,12}$/.test(symbol) ||
    !output || !/^\d+$/.test(limitRaw) || +limitRaw < 1 || +limitRaw > 10000) {
  throw new Error('Usage: node experiments/collect_kraken.mjs BTC/USD kraken.jsonl [1..10000]');
}
const ws = new WebSocket('wss://ws.kraken.com/v2');
let count = 0;
let previous = null;
let finished = false;
const finish = (description, code) => {
  if (finished) return;
  finished = true;
  ws.close();
  console.error(description);
  process.exitCode = code;
};
const timeout = setTimeout(() => finish('Kraken collection timed out.', 2), 120000);
ws.addEventListener('open', () => {
  ws.send(JSON.stringify({ method: 'subscribe',
    params: { channel: 'ticker', symbol: [symbol], event_trigger: 'trades', snapshot: false } }));
});
ws.addEventListener('message', event => {
  if (finished) return;
  try {
    const message = JSON.parse(String(event.data));
    if (message.method === 'subscribe' && message.success === false) return finish('Kraken subscription failed.', 2);
    if (message.channel !== 'ticker' || message.type !== 'update') return;
    if (!Array.isArray(message.data) || message.data.length !== 1 ||
        message.data[0].symbol !== symbol) return finish('Unexpected Kraken ticker format.', 2);
    const t = message.data[0];
    const price = Number(t.last), bid = Number(t.bid), ask = Number(t.ask);
    const ts = Date.parse(t.timestamp);
    const received = new Date().toISOString();
    if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(bid) || bid <= 0 ||
        !Number.isFinite(ask) || ask < bid || !Number.isFinite(ts) ||
        ts > Date.parse(received) + 5000 ||
        (previous !== null && ts < previous)) return finish('Invalid market data or clock regression.', 2);
    previous = ts;
    const record = { source: 'kraken_spot_ticker_v2', product_id: symbol,
      event_at: t.timestamp, received_at: received, price, bid, ask,
      feed_is_complete: false, prediction_eligible: false };
    const fd = openSync(output, 'a', 0o600);
    try { appendFileSync(fd, JSON.stringify(record) + '\n'); fsyncSync(fd); }
    finally { closeSync(fd); }
    if (++count >= +limitRaw) { clearTimeout(timeout); finish('Collected Kraken updates: ' + count, 0); }
  } catch (error) { finish('Kraken message rejected: ' + error.message, 2); }
});
ws.addEventListener('error', () => finish('Kraken WebSocket error.', 2));
ws.addEventListener('close', () => { clearTimeout(timeout); if (!finished) finish('Kraken disconnected.', 2); });
