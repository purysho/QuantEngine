# Broker paper sandbox: staged connection

2026-10-15. Goal: forward QQQ paper comparison at100/10,000/1,000,000 USD, truthful mathematics and no real-money orders. This checkpoint adds a read-only preflight, not an order adapter or continuously running collector.

## Selection and official sources

Alpaca is the first integration candidate: a paper-only account is available separately from live brokerage, with its own keys and paper endpoint. Paper-only data access is IEX, not consolidated US market coverage. SIP requires an appropriate entitlement. Account availability and access from the user's actual location must be verified during signup; this software does not bypass restrictions.

- https://docs.alpaca.markets/us/docs/paper-trading
- https://docs.alpaca.markets/us/reference/stocklatestquotes-1
- https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/
- https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/tws-api-limitations

IBKR is a later alternative, especially for an existing approved/funded account; its documentation describes top-of-book simulated fills and limitations. Neither simulator proves real execution or a profitable strategy.

Alpaca explicitly excludes market impact, latency slippage and dividends from its paper simulation; order size is not checked against NBBO liquidity. Retain our separate scenario ledger and conservative cost/capacity tests. Do not compare broker account equity to a dividend-inclusive benchmark without reconciling distributions. Do not combine IEX observations with NBBO fills as though they were identical datasets. No assumption of nine independent broker accounts is made: nine local counterfactual books remain separate from any actual paper-account balance. Broker account topology and isolation must be designed before orders are submitted.

## Current executable step

Create an Alpaca **Paper Only** account yourself using the official dashboard and generate paper keys. Do not paste keys into chat or commit them. Set `QUANT_ALPACA_PAPER_KEY` and `QUANT_ALPACA_PAPER_SECRET` through your local process environment/secret manager. Do not use live credentials. Then, during the regular US market session:

```
python -m experiments.alpaca_sandbox --feed iex --output .cache/alpaca-preflight-unique.json
```

The output parent must already exist. Use a new path each time. Optional `--feed sip` requires your real-time SIP entitlement; there is no automatic fallback. Only fixed HTTPS GET endpoints for the paper account, market clock and latest QQQ quote are accessible. Redirects are rejected; timeouts/response sizes are bounded. Account IDs/numbers/balances, raw responses and credentials are not exported. Provider error bodies are withheld. Local authenticated transport is not third-party custody. This script is read-only, not an operating-system/container security sandbox.

A zero exit means active/unblocked paper-account metadata and an open-market quote within300 seconds, not trading readiness. Closed/stale/malformed observations or unavailable credentials fail readiness. `ready_for_trading` is always false in this stage. The script submits no orders, writes no portfolio state and does not ingest quotes into the ledger. Missing credentials were actually observed locally; no authenticated broker connection is claimed. Unit fixtures do not establish provider compatibility or geographic access.

## Next gates and execution order

1. Verify authenticated account access and chosen data entitlement from the machine that will run the experiment.
2. Implement and verify actual exchange calendar, corporate actions, quote-size units, provenance and one consistent daily observation cutoff. Freeze these before collection; never fill missing sessions silently.
3. Connect a durable supervised collector to a fresh frozen forward campaign, with restart, stale data and outage tests. A hosted always-on runtime is required for unattended collection; an interactive chat session is not a permanent service.
4. Add paper-only order IDs, intent-before-submit persistence, uncertain-request reconciliation, partial fill/rejection/cancellation handling and broker statement matching. Design independent policy/capital accounts without overlapping positions or double counting. Validate with broker paper fills; never reinterpret local simulated fills as broker executions.
5. Add independent commitment custody and predeclared statistical comparison after enough observations. No main merge or real-money capability follows merely from a connectivity pass.

## Mathematics reporting contract

Every run must identify executed strategy/source version, observations and timestamps, precise return/volatility/sizing/execution/accounting formulas, parameters, data exclusions and failures. List only methods actually executed. A preflight uses timestamp age and quote validity comparisons; it executes **no return forecast, optimization, volatility estimator or trading strategy**. Subsequent ledger runs use the formulas described in `PAPER_PORTFOLIOS.md` and the actual source. Synthetic software evidence and future market evidence must stay distinguishable.
