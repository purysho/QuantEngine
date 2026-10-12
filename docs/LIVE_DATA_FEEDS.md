# Prospective market-data sources and collection — 2026-10-12

## Evidence review

Reviewed [bytewax/awesome-public-real-time-datasets](https://github.com/bytewax/awesome-public-real-time-datasets) and current vendor docs.

| Source | Type | Practical use | Limitations |
|---|---|---|---|
| Coinbase Exchange | Public WebSocket ticker, heartbeat, matches, level2 | **First pilot**: actual arrival-time trade-price observations without placing orders or using API keys | Crypto-specific; tickers are batched and may omit trades; availability and geographical access differ; no completeness assurance |
| Kraken Spot WebSocket v2 | Public trade/book streams | Alternate venue cross-check and alternative source | Venue semantics differ; verify timestamps, replay and update semantics before implementing |
| Alpaca Markets | Stocks/crypto HTTP/WebSocket | Equities candidate for next phase | Entitlement, authentication, exchange coverage and data latency need specific verification |
| SEC EDGAR | Current company filings | Publication-timestamped event study, earnings/filing features | Not a continuous price feed; filing processing, revisions and publication-time alignment essential |
| Finnhub | API with free limits | Market and event coverage candidate | Rate, redistribution and timestamp constraints; verify actual entitlements |
| FRED/ALFRED | Historical vintage economic series | Macro causality / PIT features | Published releases/revisions, not a tick-level live market feed |

Official Coinbase schema: https://docs.cdp.coinbase.com/exchange/websocket-feed/channels . The ticker gives `sequence`, `trade_id`, `product_id`, `price`, `time` and other fields; the vendor warns that updates are batched, and match messages may be dropped. Heartbeats and the trades REST API are needed for complete recovery. Do not equate a ticker feed with complete trade history.

## Implemented prototype

`workers/quant_live_feed.py` strictly normalizes a ticker, validates timestamps, positive finite prices, product identity, monotonic IDs and event order. Tickers carry **both exchange event time and independent local receipt time** plus explicit `feed_is_complete: false`.

`experiments/collect_coinbase.mjs` is an **opt-in research-only** Node 24 WebSocket collector:

```bash
node experiments/collect_coinbase.mjs BTC-USD ./btc-ticks.jsonl 25
```

It connects to the vendor's public WebSocket, subscribes to heartbeat and ticker, appends JSONL events, synchronously flushes each record, stops at the desired count, and fails on invalid, duplicated or out-of-order data. No API key, account, execution or brokerage operation is involved. Its finite ticker count prevents an unbounded continuous operation.

**Important:** It does not automatically backfill missed trades, handle sequence-gap recovery, verify uninterrupted stream integrity, persist external receipts, supervise reconnects, ensure clock synchronization, or make predictions. It has no live feed service deployment or successful live-connection evidence yet.

## Contract for a genuinely new-data experiment

1. Before connecting: freeze code, model version, unit tests, feature schema, symbols, forecast horizon, allowed feeds and metrics; let an independent custodian record a signed code hash.
2. Establish a timestamped, read-only public feed. On every valid new tick, retain the original message in a custodied append-only journal, with separate local receipt timestamp. Detect gaps/disconnects and mark intervals ineligible until repaired.
3. A model reads only its latest **already received** values. The model submits its prediction with an independent receipt **before** the observation corresponding to its target arrives. Bar and tick prediction horizons must be explicit (e.g., one minute after receipt or next completed 1-minute bar), with non-trading-hour rules.
4. On arrival of the target outcome, a separate process compares the frozen prediction against actual return and zero / historical-mean baselines; add fees, spread, available bid/ask and slippage for any profit claim.
5. Keep previously scored windows retired. Aggregate only settled, complete pairs; report failed/missed/censored forecasts, reconnects, timestamps, missingness and uncertainty.
6. Require at least one independent second provider before making claims of robustness across vendors or securities.

## Status and next work

This is **data-collection groundwork**, not a complete secure prospective pipeline or proven live-forecast advantage. Next steps are a mockable collector acceptance test, provider gap/recovery mechanisms, external immutable timestamp receipts, and an isolated service linking collection to `experiments/prospective.py`, with asynchronous settlement after actual future observations. Then run a live pilot with a frozen model and report all misses.

## Connected live forecast pilot (opt-in)

The collector can now stream each accepted observation to a **long-running** Python pilot process:

```bash
QUANT_MODEL_COMMIT=momentum-v1 node experiments/collect_coinbase.mjs BTC-USD ./btc-ticks.jsonl 25 ./pilot-run
```

The additional fourth argument is the pilot output directory. The producer journals the exchange message and passes it to `python -m experiments.live_pilot` on standard input. Once the required historical ticks have arrived, the pilot commits a *next-tick return* forecast (last observed return) along with **zero** and **past-only mean** baselines. For a *later* tick whose receipt time is strictly after the forecast's durable commitment, the pilot settles squared losses. If a tick was already received before commitment, the pilot **raises an error instead of pretending the forecast was prospective**.

Files `000000000N.forecast.json`, `.receipt.json` and `.settled.json` record each numbered evaluation. The final forecast is deliberately left unsettled if no further ticker arrives. Existing forecast or settlement paths are never overwritten. A restart into the same directory is deliberately rejected rather than resuming with a missing prior history. No trading orders or simulated fees are involved.

This is a limited research **next-received-ticker** experiment. Batched ticker updates, unequal tick intervals, connectivity gaps and feed latency mean it is not a fixed-horizon forecast, complete trade sample, or tradable P&L series. The same local user can still modify both receipt and labels, so a third-party immutable timestamp and genuinely isolated evaluator remain mandatory for externally credible unseen-data claims. Never present a run of archived JSONL rows as a new live prospective run.
