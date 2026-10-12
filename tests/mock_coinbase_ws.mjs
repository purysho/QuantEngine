// Deterministic local transport fixture: replaces global WebSocket before collector startup.
// This is synthetic traffic generated *during* CI; never classify it as real-market evidence.
class MockWebSocket {
  constructor(url) {
    if (url !== 'wss://ws-feed.exchange.coinbase.com') throw new Error('Unexpected target');
    this.events = new Map();
    this.interval = null;
    queueMicrotask(() => this.emit('open', {}));
  }
  addEventListener(name, listener) {
    if (!this.events.has(name)) this.events.set(name, []);
    this.events.get(name).push(listener);
  }
  emit(name, event) {
    for (const handler of this.events.get(name) || []) handler(event);
  }
  send(payload) {
    const subscription = JSON.parse(payload);
    if (subscription.type !== 'subscribe' || !subscription.channels.includes('ticker'))
      throw new Error('Unexpected subscription');
    let id = 0;
    this.interval = setInterval(() => {
      id++;
      const tick = { type: 'ticker', product_id: 'BTC-USD', price: String(100 + id),
        trade_id: id, sequence: id, time: new Date(Date.now() + (process.env.QUANT_TEST_FEED_MODE === 'future' ? 60000 : -150)).toISOString() };
      if (process.env.QUANT_TEST_FEED_MODE === 'duplicate' && id > 1) { tick.trade_id = 1; tick.sequence = 1; }
      this.emit('message', { data: JSON.stringify(tick) });
      if (id >= 6) clearInterval(this.interval);
    }, process.env.QUANT_TEST_FEED_MODE === 'rapid' ? 1 : 850);
  }
  close() {
    if (this.interval) clearInterval(this.interval);
    queueMicrotask(() => this.emit('close', {}));
  }
}
globalThis.WebSocket = MockWebSocket;
