"""Diagnostics only: exact log attribution and execution-aligned label checks."""
from __future__ import annotations
import numpy as np
from scipy.stats import norm
from workers.quant_competitive import account
from workers.quant_model_selection import newey_west_mean


def attribute(returns, targets, cash, *, cost_bps=10):
    r=np.asarray(returns,dtype=float);w=np.asarray(targets,dtype=float);rf=np.asarray(cash,dtype=float)
    net=account(r,w,rf,cost_bps=cost_bps);gross=account(r,w,rf,cost_bps=0)
    if r.shape[1]!=2:raise ValueError('Require broad market and Nasdaq returns.')
    baseline=np.tile([0.,1.],(len(r),1))
    bg=account(r,baseline,rf,cost_bps=0);bn=account(r,baseline,rf,cost_bps=cost_bps)
    held=np.zeros_like(w);held[2:]=w[:-2];exposure=held.sum(axis=1)
    eligible=(exposure>0).astype(float)
    participation=eligible*r[:,1]+(1-eligible)*rf
    sized=exposure*r[:,1]+(1-exposure)*rf
    g=np.log1p(gross['returns']);n=np.log1p(net['returns'])
    b=np.log1p(bg['returns']);bc=np.log1p(bn['returns'])
    components={'participation':np.log1p(participation)-b,
                'risk_sizing':np.log1p(sized)-np.log1p(participation),
                'asset_choice':g-np.log1p(sized),
                'strategy_cost':n-g,'benchmark_cost_credit':b-bc}
    gap=n-bc;error=float(np.max(np.abs(sum(components.values())-gap)))
    if error>1e-10:raise ArithmeticError('Log attribution failed to reconcile.')
    rows=[];fee=cost_bps/10000
    for t in range(1,len(r)):
        prior=w[t-2] if t>=2 else np.zeros(2);target=w[t-1]
        before_assets=prior*net['wealth'][t]*(1+r[t])
        post=net['wealth'][t+1]
        if t==len(r)-1:post/=1-fee*target.sum()
        delta=target*post-before_assets;buy=float(np.maximum(delta,0).sum());sell=float(np.maximum(-delta,0).sum())
        if buy+sell>1e-12:
            if not np.any(prior):kind='entry'
            elif not np.any(target):kind='exit'
            elif np.allclose(target,prior,rtol=0,atol=1e-12):kind='drift_rebalance'
            elif np.allclose(target/target.sum(),prior/prior.sum(),rtol=0,atol=1e-12):kind='risk_adjustment'
            else:kind='asset_switch'
            rows.append({'close_index':t,'signal_index':t-1,'kind':kind,'buy_notional':buy,'sell_notional':sell,
                         'asset_delta':delta.tolist(),'fee':fee*(buy+sell),'target':target.tolist()})
        if t==len(r)-1 and target.sum()>0:
            notional=float(target.sum()*post)
            rows.append({'close_index':t,'signal_index':None,'kind':'terminal_exit','buy_notional':0.,
                         'sell_notional':notional,'asset_delta':(-target*post).tolist(),'fee':fee*notional,'target':[0.,0.]})
    if abs(sum(row['fee'] for row in rows)-sum(net['costs']))>1e-9*max(net['wealth']):
        raise ArithmeticError('Transaction ledger fees failed to reconcile.')
    return {'components':components,'net_log_gap':float(gap.sum()),'reconciliation_error':error,
            'account':net,'transactions':rows,'held_exposure':exposure,
            'order':'Nasdaq benchmark -> participation -> risk sizing -> asset choice -> net costs; order-dependent accounting, not causal attribution'}


def forward_payoffs(returns,cash,horizon):
    r=np.asarray(returns,dtype=float);rf=np.asarray(cash,dtype=float)
    if r.ndim!=2 or r.shape[1]!=2 or rf.shape!=(len(r),) or not isinstance(horizon,int) or horizon<1 or len(r)<horizon+2:
        raise ValueError('Invalid horizon/arrays.')
    if not np.isfinite(r).all() or not np.isfinite(rf).all() or (r<=-1).any() or (rf<=-1).any():raise ValueError('Invalid returns.')
    indices=np.arange(len(r)-horizon-1)
    assets=np.array([np.prod(1+r[t+2:t+2+horizon],axis=0)-1 for t in indices])
    money=np.array([np.prod(1+rf[t+2:t+2+horizon])-1 for t in indices])
    return {'assets':assets,'cash':money,'signal_indices':indices,'last_outcome_indices':indices+1+horizon}


def state_evidence(values,hit,*,horizon,comparisons):
    v=np.asarray(values,dtype=float);hit=np.asarray(hit,dtype=bool)
    if v.ndim!=1 or hit.shape!=v.shape or not np.isfinite(v).all() or horizon<1 or comparisons<1:raise ValueError('Invalid conditional evidence.')
    count=int(hit.sum())
    if count<3 or (~hit).sum()<3:return {'observations':count,'mean':None,'family_lower':None}
    mu=float(v[hit].mean());other=float(v[~hit].mean());fraction=float(hit.mean());lags=max(5,horizon)
    influence=hit*(v-mu)/fraction
    se=newey_west_mean(influence,lags=lags)['standard_error']
    contrast=influence-(~hit)*(v-other)/(1-fraction)
    contrast_se=newey_west_mean(contrast,lags=lags)['standard_error']
    critical=float(norm.ppf(1-.025/comparisons))
    return {'observations':count,'mean':mu,'lower_95':mu-1.96*se,'upper_95':mu+1.96*se,
            'family_lower':mu-critical*se,'family_upper':mu+critical*se,
            'mean_outside_state':other,'state_minus_outside':mu-other,
            'contrast_family_lower':mu-other-critical*contrast_se,'contrast_family_upper':mu-other+critical*contrast_se,
            'hac_lags':lags,'family_comparisons':comparisons,
            'notice':'Original-grid ratio-mean HAC; overlapping horizons, exposed development and bandwidth uncertainty remain.'}
