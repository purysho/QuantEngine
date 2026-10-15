# Paper portfolios — first implementation

The desktop **Paper portfolios** page provides a local, durable comparison across100,10,000 and1,000,000 USD. Each scale independently runs a QQQ buy-and-hold comparator and two fixed15% volatility-sizing references with minimum1/5-session adjustments and a10-percentage-point band. This first release establishes accounting and forward-observation infrastructure; it does not supply an independently validated return edge or execute real orders.

## Use

1. Open Paper portfolios, choose **Forward observations** or **Recorded / synthetic replay**, enter a truthful source label and freeze a new campaign. Nine cash accounts appear. The mode, execution assumptions, source label, engine hash and Python version cannot be edited.
2. Supply one daily session quote through **Import daily quote**. No data subscription, background collector or broker is connected automatically. Before forwarding real observations, verify the source's entitlement, timestamps, session calendar and corporate actions. The source and local receipt clock remain unverified.
3. Targets committed after one observation can execute only on a later session. A successful post-commit receipt is required before processing another observation. Forward quotes must be newer than the prior durable-commit watermark and no more than300 seconds old. Recorded imports are always development/replay, even if their dates are recent.
4. Reload/select a saved campaign to reopen it. Halt cancels pending target intents; resuming does not resurrect them. The next accepted quote must create a new intent before another quote can fill it. Session linkage gaps halt execution and permanently mark that campaign incomplete.
5. Export the journal using the native save dialog. It contains frozen configuration, every input, simulated outcome, state hashes and local post-commit receipts, but no application storage path. Keep old campaigns and failed observations when evaluating changes; do not splice favourable campaigns into an invented continuous track record.

Illustrative **recorded synthetic** quote (not real data):

```json
{"event_id":"example-1","symbol":"QQQ","session":"2025-01-02","previous_session":null,"asof":"2025-01-02T20:00:00Z","bid":"99","ask":"101","bid_size":"100","ask_size":"100","split_ratio":"1","dividend_per_share":"0"}
```

The next quote needs a strictly later session/asof, unique event ID and `previous_session` matching the earlier session. The caller's session linkage is not an independently verified exchange calendar. Inputs are limited to8KB each. There is no fill on the first observation. Challenger warmup is21 observed quotes; cash held during warmup remains in the comparison rather than being hidden. Their first eligible fill occurs on a subsequent observation. These are new frozen paper-policy versions using the earlier sizing formula, not claims of exact reproduction of the252-close-warmup index backtest.

## What capital awareness means here

Quantities use Decimal cash/share arithmetic and default0.000001-share increments. Buys must remain affordable including fees and adverse modeled impact; sells cannot exceed holdings. Default minimum notional is1 USD, proportional fee10bps, fixed fee0, quote-side participation cap10%, adverse impact10bps times sqrt(quantity/quoted side size). These are frozen **simulation assumptions**, not verified broker rules. Worker API creation accepts bounded alternative assumptions for explicit scenario testing.

Large accounts can receive partial fills and retain cash; residual IOC quantities expire and are displayed rather than silently filled at the midpoint. Small accounts encounter minimum-order/rounding/fee constraints. Each portfolio is an independent counterfactual using the same observation, not nine simultaneous consumers of a quote. One BBO size snapshot is not total daily liquidity or a measured market-impact curve. No supported capital range is certified by the simulator.

Equity is marked at quote midpoint after simulated trading costs. Future liquidation costs, cash interest, personal taxes and operating/data costs are excluded. It is not an immediately withdrawable cash value. Reports retain full-campaign returns and calendar-period metrics, CAGR only after365 calendar days, and252-observation rolling returns when available; the chart displays at most400 recent observations. Short or incomplete calendar periods are labelled by actual session boundaries in exports.

Splits adjust existing holdings before fills. Dividend-per-share is defined in post-split share units and credits holdings before new purchases; the supplied quote must be ex-distribution when applicable. Split/dividend-aware feature levels prevent corporate actions from being mistaken for price crashes. Bid/ask, spread, size and metadata must come from a coherent provider source; no external correctness is implied by parsing them.

## Durability, controls and limits

SQLite WAL and FULL synchronous transactions atomically persist inputs, fills, target intents and state. After the durable target commit, a separate receipt samples the local clock. A crash before receipt persistence leaves the ledger inspectable but blocks further ingestion; halt/inspect is required before resumption. The full state/event hash chain is verified before each operation. Changed engine code permits read/export but rejects new execution under the old freeze. This is local integrity protection: the filesystem owner can rewrite both data and hashes, so third-party custody is still absent.

Duplicate events, reordered sessions, future/invalid/crossed quotes and clock regression fail without changing the accounts. A source-reported missing session or a gap exceeding7 calendar days halts trading, cancels intents and marks evidence incomplete. Quantity/cash caps,50 campaigns,2,000 observations/campaign and5,000 journal events bound this first implementation. Pausing the desktop worker waits for its owned operation; a cancelled response can still follow a durable commit, so reload before retrying. Duplicate IDs protect against accidental reapplication.

## Evidence and remaining work

`python -m experiments.paper_acceptance --output-dir <new-directory>` runs35 synthetic observations across nine books, partial fills, exact reopening and a missing-session failure. The output explicitly reports no real feed, independent custody or validated capacity. The existing full numerical/desktop/native tests also exercise the ledger, shared worker slot and renderer.

Remaining: a permitted real quote adapter and unattended collector, externally recorded commitments, independent execution/market-performance evaluation, validated actual broker/fractional-order rules, realistic quote/depth/impact estimates, and the separate point-in-time constituent-data research project. No production broker capability is implemented or authorised by this release. The proposed stock-selection hypothesis has not been tested with current-membership substitutes.
