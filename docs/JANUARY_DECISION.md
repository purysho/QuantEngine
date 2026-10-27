# The January decision: a QuantEngine strategy or the S&P 500?

Written 2026-10-27, before the tradable check or any paper results for the multi-factor strategy existed. The criteria below are fixed now so that January's answer cannot be shaped by January's numbers. Changing them later must be recorded here with the reason.

## The default

**The default is an S&P 500 index fund.** It costs almost nothing, needs no decisions and has earned about 10–11% a year over long periods. A QuantEngine strategy has to show it is worth its extra complexity, not the other way round.

## The question

Is there a QuantEngine strategy worth putting real money into, through your own brokerage, instead of (or beside) an S&P 500 index fund? QuantEngine itself never trades real money. If the answer is yes, you would buy the funds it names yourself, once a month.

## Evidence so far (data to 2026-08-31)

| Strategy | Annual return vs market | Gates passed | What fails |
|---|---|---|---|
| Multi-factor: quality + value + momentum (registered 2026-10-27) | 13.1% vs 10.9% (since 1963) | 4 of 5 | Last 10 years: Sharpe 0.728 vs the market's 0.732 |
| Quality (most profitable companies) | 12.1% vs 10.9% | 4 of 5 | Deflated Sharpe 0.90 (needs 0.95) |
| Sector momentum (your current paper strategy) | 11.8% vs 10.3% (equal-weight industries) | 4 of 5 | Deflated Sharpe 0.52 |
| Diversified ensemble | 10.0% vs 10.8% | 2 of 5 | Return, significance, last 10 years |
| Trend + volatility target | 8.4% vs 9.7% | 2 of 5 | Return, significance, last 10 years |

The multi-factor result is the strongest evidence QuantEngine has produced:
- **Statistics:** a Newey–West t of 5.4 on its edge over the market, and a deflated Sharpe of 1.000 after correcting for all 49 variants tried.
- **Robustness:** every one of its 6 variants beat the market.
- **The catch:** over the last 10 years it only matched the market. Value stocks lagged the large technology companies for most of that decade.
- **Gate result:** the holdout gate fails by 0.004. That is effectively a tie, but the gate was fixed in advance, so the result stands as a no-go.

## The criteria (all three must hold on the decision date)

1. **Backtest gates:** the strategy passes all five gates when the lab is re-run in January on the latest data. Today, none passes.
2. **Tradable check:** replayed on the actual ETFs it would buy since 2016 (the **Run tradable check** button), the strategy's annual return is no more than 1 percentage point a year below SPY's over the same days. This is a consistency check, not proof. Ten years is too short to prove an edge of 1–2 points a year, but a tradable version that clearly lagged would mean the research edge did not reach real funds.
3. **Paper trading:** all five stage-3 checks pass for that strategy:
   - 63 trading days compared;
   - tracking error at most 5% a year;
   - paper return within the expected band;
   - reconciled;
   - kill switch tested.

   These checks show the strategy can be run correctly. Three months cannot show it is profitable, and paper profit or loss over that time is not evidence either way.

**If all three hold:** at most a satellite. For example, up to 20% of what you invest goes to the strategy's funds and the rest to the S&P 500 fund. Review once a year, and only after an emergency fund and any high-interest debt are dealt with.

**If any fails:** the S&P 500 index fund. QuantEngine stays your research tool and terminal, and the paper test can continue.

**If criterion 1 flips to a pass by a hair** (for example the multi-factor holdout moving from 0.004 below to just above): treat it as borderline. A few extra months of data moving a tie is not new evidence.

## Timetable

- **This week:** switch the paper account to Multi-factor. It holds QUAL, VLUE and MTUM in equal thirds, so it does not need to wait for a month-end, and switching restarts the paper test.
  - If the first fill is on Wednesday Oct 28 New York time, the 63rd day is **Friday Jan 29, 2027**.
  - If it is on Thursday Oct 29, the 63rd day is **Monday Feb 1**.
- **Any time:** run the tradable check (one click, about a minute). It is criterion 2 and does not depend on the paper test.
- **Weekend of Jan 30–31 (or Feb 1–2):** re-run the strategy lab, read the stage-3 checks, export your progress and decide.

## What could still change the answer

- **The lab on newer data:** a few more months of history barely move a 63-year result. Only the last-10-years window moves noticeably.
- **The tradable check:** this is the largest unknown today. The ETFs follow MSCI factor indexes, not the Ken French portfolios the research used.
- **Things that should not change it:**
  - paper profit or loss over three months;
  - news;
  - any result from a strategy or variant not registered before it was tested.
