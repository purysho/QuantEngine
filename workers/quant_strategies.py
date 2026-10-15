"""Frozen daily long/cash research rules with next-close execution.

No parameter search, leverage or shorting. Close-only total-return indices are
research proxies, not executable instruments or intraday market data.
"""
from __future__ import annotations
import datetime as dt
import math
import numpy as np


def _prices(values):
    p = np.asarray(values, dtype=float)
    if p.ndim != 1 or len(p) < 3 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError('Require at least three positive finite prices.')
    return p


def rsi(prices, *, period=14):
    p = _prices(prices)
    if type(period) is not int or period < 1:
        raise ValueError('RSI period must be positive integer.')
    out = np.full(len(p), np.nan)
    if len(p) <= period: return out
    changes = np.diff(p)
    gains, losses = np.maximum(changes, 0), np.maximum(-changes, 0)
    gain, loss = gains[:period].mean(), losses[:period].mean()
    for i in range(period, len(p)):
        if i > period:
            gain = ((period-1)*gain + gains[i-1])/period
            loss = ((period-1)*loss + losses[i-1])/period
        out[i] = 50 if gain == loss == 0 else 100 if loss == 0 else 100-100/(1+gain/loss)
    return out


def _ema(p, period):
    out = np.empty(len(p)); out[0] = p[0]
    a = 2/(period+1)
    for i in range(1,len(p)): out[i] = a*p[i] + (1-a)*out[i-1]
    return out


def signals(prices):
    p = _prices(prices)
    out = {name: np.zeros(len(p)) for name in
           ('ma_20_50', 'rsi_14_30_70', 'bollinger_20_2', 'macd_12_26_9', 'volatility_breakout_20_2')}
    strength = rsi(p)
    macd = _ema(p,12)-_ema(p,26)
    trigger = _ema(macd,9)
    log_returns = np.diff(np.log(p))
    rsi_position = band_position = vol_position = 0
    for i in range(len(p)):
        if i >= 49:
            out['ma_20_50'][i] = float(p[i-19:i+1].mean() > p[i-49:i+1].mean())
        if i >= 14:
            if strength[i] < 30: rsi_position = 1
            elif strength[i] > 70: rsi_position = 0
            out['rsi_14_30_70'][i] = rsi_position
        if i >= 19:
            window = p[i-19:i+1]; mean = window.mean(); sd = window.std(ddof=0)
            if p[i] < mean-2*sd: band_position = 1
            elif p[i] >= mean: band_position = 0
            out['bollinger_20_2'][i] = band_position
        if i >= 33: out['macd_12_26_9'][i] = float(macd[i] > trigger[i])
        if i >= 21:
            past = log_returns[i-21:i-1]  # excludes current close-to-close return
            if p[i] > p[i-20:i].max() and log_returns[i-1] > 2*past.std(ddof=1):
                vol_position = 1
            elif p[i] < p[i-19:i+1].mean(): vol_position = 0
            out['volatility_breakout_20_2'][i] = vol_position
    return out


def backtest(prices, targets, *, cost_bps=10):
    p = _prices(prices)
    target = np.asarray(targets, dtype=float)
    if target.shape != p.shape or not np.isfinite(target).all() or not np.isin(target,[0,1]).all():
        raise ValueError('Targets must be matching long/cash values 0 or 1.')
    if type(cost_bps) not in (float,int) or not math.isfinite(cost_bps) or not 0 <= cost_bps <= 1000:
        raise ValueError('Invalid costs.')
    fee = cost_bps/10000
    net = np.zeros(len(p)-1)
    held = 0.; turnover = 0.
    for t in range(1,len(p)-1):
        new = target[t-1]  # signal at t-1 becomes a holding only at close t
        change = abs(new-held); turnover += change
        net[t-1] = (1+net[t-1])*(1-fee*change)-1
        held = new
        net[t] = held*(p[t+1]/p[t]-1)
    turnover += held
    net[-1] = (1+net[-1])*(1-fee*held)-1  # terminal close liquidation
    curve = np.r_[1., np.cumprod(1+net)]
    return {'net_returns': net.tolist(), 'terminal_wealth':float(curve[-1]),
            'turnover':float(turnover),
            'max_drawdown':float(np.min(curve/np.maximum.accumulate(curve)-1)),
            'timing':'signal close s, execution close s+1, first held interval s+1 to s+2',
            'cost_bps':cost_bps, 'terminal_liquidation':True}


def five_year_blocks(dates):
    if not dates or any(type(d) is not dt.date for d in dates) or any(b <= a for a,b in zip(dates,dates[1:])):
        raise ValueError('Dates must be strictly increasing calendar dates.')
    first = dates[0].year//5*5
    blocks=[]
    for year in range(first,dates[-1].year+1,5):
        idx = [i for i,d in enumerate(dates) if year <= d.year < year+5]
        if idx:
            blocks.append({'start_year':year,'end_year':year+5,'indices':idx,
                           'complete':dates[0].year <= year and dates[-1].year >= year+5})
    return blocks
