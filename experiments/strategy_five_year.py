"""Frozen rules on publicly exposed history; never a sealed holdout.

Usage: python -m experiments.strategy_five_year [--offline]
No parameter update is made after a historical block. All wins/losses remain.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from workers.quant_data import us_market_returns
from workers.quant_strategies import signals, backtest, five_year_blocks
from workers.quant_model_selection import newey_west_mean, white_reality_check


def run(*, offline=False):
    root = Path(__file__).resolve().parents[1]
    dates, returns, meta = us_market_returns(root/'.cache/data', offline=offline)
    prices = np.cumprod(1+returns)  # close at dates[0]; first source return excluded from P&L
    rules = signals(prices)
    baseline = backtest(prices, np.ones(len(prices)), cost_bps=10)
    buyhold = np.asarray(baseline['net_returns'])
    runs = {name:backtest(prices,target,cost_bps=10) for name,target in rules.items()}
    gross = {name:backtest(prices,target,cost_bps=0) for name,target in rules.items()}
    stress = {name:backtest(prices,target,cost_bps=25) for name,target in rules.items()}
    blocks=[]
    for block in five_year_blocks(dates[1:]):
        ix = block.pop('indices'); rows={}
        bench = buyhold[ix]
        for name, result in runs.items():
            net = np.asarray(result['net_returns'])[ix]
            g = np.asarray(gross[name]['net_returns'])[ix]
            highcost = np.asarray(stress[name]['net_returns'])[ix]
            wealth = np.r_[1,np.cumprod(1+net)]
            excess = newey_west_mean(net-bench,lags=min(5,len(ix)-1))
            rows[name] = {'net_compounded_return':float(wealth[-1]-1),
                         'gross_compounded_return':float(np.prod(1+g)-1),
                         'cost_25bps_compounded_return':float(np.prod(1+highcost)-1),
                         'max_drawdown':float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
                         'paired_daily_excess_vs_buyhold':excess,
                         'beat_buyhold_realized':bool(np.prod(1+net)>np.prod(1+bench)),
                         'beat_cash_realized':bool(wealth[-1]>1),
                         'diagnostics':{'cost_drag_compounded':float(np.prod(1+g)-wealth[-1]),
                            'mean_daily_cash_opportunity_gap':float((bench-net).mean()),
                            'interpretation':'Descriptive attribution; losses may reflect regime mismatch, opportunity costs or noise. No causal diagnosis or historical retuning.'}}
        blocks.append({**block,'first_observed':str(dates[1:][ix[0]]),
                       'last_observed':str(dates[1:][ix[-1]]),'observations':len(ix),
                       'buyhold_compounded_return':float(np.prod(1+bench)-1), 'cash_return':0,
                       'strategies':rows,
                       'multiple_rule_diagnostic':white_reality_check(
                           -np.column_stack([np.asarray(runs[name]['net_returns'])[ix] for name in rules]),
                           -bench, expected_block=5, repetitions=500,seed=17) if len(ix)>=20 else None})
    return {'status':'historical_development_only','source':meta,
            'source_first':str(dates[0]),'source_last':str(dates[-1]),
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'rule_source_sha256':hashlib.sha256((root/'workers/quant_strategies.py').read_bytes()).hexdigest(),
            'rules':list(rules),'cost_bps':10,'cost_sensitivity_bps':[0,10,25],
            'window_policy':'Nonoverlapping calendar blocks [year,year+5); partial edges marked. Indicators and holdings carry across blocks. No refit/search or per-block liquidation.',
            'benchmark':'CRSP total market Mkt-RF + RF, constructed total-return index; no directly executable price, spreads, individual-stock survivorship or intraday fills.',
            'timing':baseline['timing'],'cash_yield':0,
            'inference':'HAC lag 5 and stationary bootstrap mean block 5/500 repetitions/seed17 prespecified. Return-score diagnostic, not MSE forecasting evidence. Exposed history and repeated inspection invalidate fresh-alpha interpretation.',
            'blocks':blocks,'unsupported':{
                'three_session':'Needs timezone/DST-aware intraday FX bars and explicit rules; session taxonomy is not a unique entry/exit algorithm.',
                'orb':'Needs opening-range OHLCV and exchange calendar; daily index cannot test it.',
                'breakout_retest':'Needs explicit retest/confirmation/fill rules and intraday OHLCV.',
                'gap_earnings_news':'Needs point-in-time publication/catalyst times, premarket/open prices, universe incl. delisted symbols and spreads.',
                'ml_ensemble':'Existing learner remains underperforming; frozen ensemble and independent adoption period required.',
                'statistical_arbitrage':'Existing pairs experiment retained separately; requires executable paired instruments and borrow history for trading claims.'}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true')
    args=parser.parse_args();report=run(offline=args.offline)
    path=Path(__file__).resolve().parent/'results/strategy_five_year.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    complete=[b for b in report['blocks'] if b['complete']]
    print('source',report['source_first'],report['source_last'],'sha256',report['source']['sha256'])
    print('blocks',len(report['blocks']),'complete',len(complete),'partial',len(report['blocks'])-len(complete))
    for name in report['rules']:
        print(name,'beat buyhold in',sum(b['strategies'][name]['beat_buyhold_realized'] for b in complete),'/',len(complete),'complete blocks')
    print('written',path)

if __name__=='__main__':main()
