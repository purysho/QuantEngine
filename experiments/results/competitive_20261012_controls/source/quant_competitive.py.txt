"""Frozen, situation-dependent research portfolios; no trading connection.

Two risky total-return indices plus cash. Signals at close s execute at close
s+1, earning the first risky return at s+2. Fees use actual traded notional.
"""
from __future__ import annotations
import numpy as np
from scipy.stats import norm
from workers.quant_strategies import rsi
from workers.quant_model_selection import newey_west_mean


def account(returns,targets,cash,*,cost_bps=10,annual_fee=0):
    r=np.asarray(returns,dtype=float);w=np.asarray(targets,dtype=float);rf=np.asarray(cash,dtype=float)
    if r.ndim!=2 or len(r)<3 or w.shape!=r.shape or rf.shape!=(len(r),):raise ValueError('Mismatched arrays.')
    if not np.isfinite(r).all() or not np.isfinite(w).all() or not np.isfinite(rf).all() or (r<=-1).any() or (rf<=-1).any():raise ValueError('Invalid returns or weights.')
    if (w<0).any() or (w.sum(axis=1)>1+1e-12).any():raise ValueError('Long/cash only, without leverage.')
    if not np.isfinite(cost_bps) or not 0<=cost_bps<=100 or not np.isfinite(annual_fee) or not 0<=annual_fee<=.1:raise ValueError('Invalid fees.')
    fee=cost_bps/10000;assets=np.zeros(r.shape[1]);money=1.;wealth=[1.];costs=[];turn=[];net=[];exposures=[]
    daily_fee=1-np.exp(-annual_fee/252)
    for t in range(len(r)):
        assets*=1+r[t];money*=1+rf[t];before=float(assets.sum()+money)
        charges=0.;notional=0.
        if t>=1:
            target=w[t-1]
            post=before
            # Unique contraction: c * sum(target) < 1. Solve fees and positions jointly.
            for _ in range(50):
                updated=before-fee*float(np.abs(target*post-assets).sum())
                if abs(updated-post)<=1e-13*before:post=updated;break
                post=updated
            notional=float(np.abs(target*post-assets).sum());charges=before-post
            assets=target*post;money=(1-float(target.sum()))*post
        total=float(assets.sum()+money)
        operating=total*daily_fee;assets*=1-daily_fee;money*=1-daily_fee;charges+=operating
        if t==len(r)-1:
            exit_notional=float(assets.sum());exit_cost=fee*exit_notional
            money+=exit_notional-exit_cost;assets[:]=0;charges+=exit_cost;notional+=exit_notional
        total=float(assets.sum()+money)
        net.append(total/wealth[-1]-1);wealth.append(total);costs.append(charges);turn.append(notional)
        exposures.append(float(assets.sum()/total))
    return {'returns':net,'wealth':wealth,'costs':costs,'turnover_notional':turn,'end_close_risky_fraction':exposures,
            'timing':'close s signal; close s+1 execution; first risky return s+2',
            'fee_convention':'cost_bps times actual risky buy/sell notional; cash self-financing; terminal exit charged'}


def regime_targets(prices):
    p=np.asarray(prices,dtype=float)
    if p.ndim!=2 or p.shape[1]!=2 or len(p)<253 or not np.isfinite(p).all() or (p<=0).any():raise ValueError('Require 253 positive finite two-asset closes.')
    n=len(p);logs=np.diff(np.log(p),axis=0)
    strength=rsi(p[:,0]);weights={name:np.zeros_like(p) for name in ['situation_router','router_vol15','momentum_rotation']}
    regimes=['warmup']*n;mean_position=0.;last_router=np.zeros(2);last_risk=np.zeros(2);last_rotate=np.zeros(2)
    for t in range(252,n):
        changes=np.abs(np.diff(p[t-20:t+1,0]));den=float(changes.sum())
        efficiency=abs(p[t,0]-p[t-20,0])/den if den else 0.
        volatility=float(logs[t-20:t,0].std(ddof=1)*np.sqrt(252))
        sma200=p[t-199:t+1,0].mean();up=p[t,0]>sma200
        momentum=np.log(p[t]/p[t-126]);best=int(np.argmax(momentum))
        if not up and volatility>.25:state='stress'
        elif up and efficiency>=.25:state='trend'
        else:state='range'
        regimes[t]=state
        if strength[t]<40:mean_position=1.
        elif strength[t]>60:mean_position=0.
        proposal=np.zeros(2)
        if state=='trend' and momentum[best]>0:proposal[best]=1.
        elif state=='range':proposal[0]=mean_position
        # Dispatch every fifth close, or immediately on stress. Risk changes need a 5% band.
        if t%5==0 or state=='stress':last_router=proposal.copy()
        risk=last_router.copy()
        if risk.sum()>0:
            asset=int(np.argmax(risk));vol=float(logs[t-20:t,asset].std(ddof=1)*np.sqrt(252))
            risk*=min(1.,.15/max(vol,1e-12))
        if t%5==0 or state=='stress' or np.max(np.abs(risk-last_risk))>=.05:last_risk=risk
        if t%21==0:
            last_rotate=np.zeros(2)
            if momentum[best]>0:last_rotate[best]=1.
        weights['situation_router'][t]=last_router;weights['router_vol15'][t]=last_risk;weights['momentum_rotation'][t]=last_rotate
    return {'weights':weights,'regimes':regimes}


def score(returns,*,years,cash):
    r=np.asarray(returns,dtype=float);rf=np.asarray(cash,dtype=float)
    if r.ndim!=1 or not len(r) or rf.shape!=r.shape or not np.isfinite(r).all() or not np.isfinite(rf).all() or (r<=-1).any() or years<=0:raise ValueError('Invalid scored series.')
    wealth=np.r_[1.,np.cumprod(1+r)];excess=r-rf;sd=float(excess.std(ddof=1)) if len(r)>1 else 0.
    return {'observations':len(r),'total_return':float(wealth[-1]-1),
            'cagr':float(wealth[-1]**(1/years)-1),'annualized_volatility':float(r.std(ddof=1)*np.sqrt(252)) if len(r)>1 else 0.,
            'sharpe_vs_cash':float(excess.mean()/sd*np.sqrt(252)) if sd>0 else None,
            'max_drawdown':float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
            'worst_day':float(r.min())}


def select_policy(candidates,baseline,*,selection,adoption):
    s=np.asarray(list(selection));a=np.asarray(list(adoption));b=np.asarray(baseline,dtype=float)
    if s.ndim!=1 or a.ndim!=1 or len(s)<100 or len(a)<100 or s.dtype.kind not in 'iu' or a.dtype.kind not in 'iu' or (np.diff(s)<=0).any() or (np.diff(a)<=0).any() or s.min()<0 or a.max()>=len(b) or s.max()>=a.min():raise ValueError('Require distinct past selection and later adoption blocks.')
    if not candidates:raise ValueError('No frozen candidates.')
    evidence={};critical=float(norm.ppf(1-.025/len(candidates)))
    for name,values in candidates.items():
        v=np.asarray(values,dtype=float)
        if v.shape!=b.shape:raise ValueError('Candidate/baseline shape mismatch.')
        ev=newey_west_mean(v[s]-b[s],lags=5);ev['adjusted_lower']=ev['mean']-critical*ev['standard_error'];evidence[name]=ev
    eligible=[k for k,v in evidence.items() if v['adjusted_lower']>0 and v['standard_error']>0]
    picked=max(eligible,key=lambda name:evidence[name]['adjusted_lower']) if eligible else None
    check=newey_west_mean(np.asarray(candidates[picked])[a]-b[a],lags=5) if picked else None
    accepted=bool(check and check['lower_95']>0 and check['standard_error']>0)
    return {'selected':picked,'adopted':accepted,'selection_evidence':evidence,'adoption_evidence':check,
            'notice':'Nominal net-return gate; repeated development, covariance and custody limits remain.'}


def passive_vol_targets(prices):
    """Strong passive controls: same 20-close volatility, 15% cap and 5% band."""
    p=np.asarray(prices,dtype=float)
    if p.ndim!=2 or p.shape[1]!=2 or len(p)<21 or not np.isfinite(p).all() or (p<=0).any():raise ValueError('Invalid passive-control prices.')
    logs=np.diff(np.log(p),axis=0);out={}
    for name,asset in [('broad_dynamic_vol15',0),('nasdaq_dynamic_vol15',1)]:
        targets=np.zeros_like(p);held=0.
        for t in range(20,len(p)):
            vol=float(logs[t-20:t,asset].std(ddof=1)*np.sqrt(252));desired=min(1.,.15/max(vol,1e-12))
            if t%5==0 or abs(desired-held)>=.05:held=desired
            targets[t,asset]=held
        out[name]=targets
    return out
