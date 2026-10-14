"""Prespecified interval-only sizing development experiment; no adoption."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.stats import norm
from experiments.competitive_test import data,mask
from workers.quant_competitive import account,score,passive_vol_targets,core_tactical_targets
from workers.quant_sizing_latency import latency_targets
from workers.quant_trade_audit import attribute
from workers.quant_model_selection import newey_west_mean,stationary_bootstrap_indices

PROTOCOL={'status':'exposed_development_interval_only','minimum_closes':[1,5,21],
          'fixed':{'asset':'Nasdaq100 total return','warmup':252,'volatility_lookback':20,
                   'risk_target':.15,'absolute_weight_band':.10,'periodic_override':False,'leverage':False},
          'evaluation_start':'2015-01-01','cost_bps':[0,10,25],'primary':'paired mean net return at10bps versus21-close arm',
          'hac_lags':20,'primary_family_comparisons':2,'bootstrap_blocks':[5,20,60],
          'bootstrap_repetitions':1000,'bootstrap_seed':17,'bootstrap_family_comparisons':18,
          'bootstrap_metrics':['annual_log_growth_difference','sharpe_difference','drawdown_improvement'],
          'source_pins':{'broad_market':'2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db',
                         'nasdaq_total_return':'e4a3f645aa8ae8d5e2e2c3b054c2111c322961770ba28c3662d3035f1bef3afe'},
          'notice':'Previously exposed history. Only minimum interval varies; no parameter sweep, independent custody, automated adoption or forecasting claim.'}


def run(output):
    root=Path(__file__).resolve().parents[1];out=Path(output);out.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__).resolve(),root/'workers/quant_sizing_latency.py',root/'workers/quant_competitive.py',
           root/'workers/quant_trade_audit.py',root/'workers/quant_model_selection.py',root/'experiments/competitive_test.py',root/'workers/quant_data.py']
    frozen={'protocol':PROTOCOL,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (out/'frozen_protocol.json').write_text(json.dumps(frozen,indent=2)+'\n');archive=out/'source';archive.mkdir()
    for p in files:(archive/(p.name+'.txt')).write_bytes(p.read_bytes())
    print('frozen',hashlib.sha256((out/'frozen_protocol.json').read_bytes()).hexdigest(),flush=True)
    dates,p,r,c,sources=data(root/'.cache/data',True)
    for name,digest in PROTOCOL['source_pins'].items():
        if sources[name]['sha256']!=digest:raise ValueError('Source snapshot changed: '+name)
    targets={str(n):latency_targets(p,minimum_closes=n) for n in PROTOCOL['minimum_closes']}
    if not np.array_equal(targets['21'],core_tactical_targets(p)['weights']['nasdaq_slow_vol15']):
        raise ArithmeticError('21-close control failed exact reproduction.')
    first=int(np.flatnonzero(mask(dates,'2015-01-01','2100-01-01'))[0]);seed=first-1
    rr=r[seed:].copy();cc=c[seed:].copy();rr[0]=0;cc[0]=0;ed=dates[first:];cash=cc[1:]
    years=(ed[-1]-dates[seed]).days/365.25
    controls={'nasdaq_buyhold':np.tile([0.,1.],(len(p),1)),
              'prior_faster_control':passive_vol_targets(p)['nasdaq_dynamic_vol15']}
    all_targets={**targets,**controls}
    net={};scores={};costs={};attribution={};sizing={}
    for name,w in all_targets.items():
        x=attribute(rr,w[seed:],cc,cost_bps=10);net[name]=np.asarray(x['account']['returns'])[1:]
        scores[name]=score(net[name],years=years,cash=cash)
        attribution[name]={k:float(v[1:].sum()/years*100) for k,v in x['components'].items()}
        if name in targets:
            sizing[name]={'mean_risky_exposure':float(x['held_exposure'][1:].mean()),
                          'target_adjustments':int((np.abs(np.diff(w[seed:,1]))>1e-12).sum()),
                          'transaction_rows':len(x['transactions']),
                          'drift_rebalances':sum(row['kind']=='drift_rebalance' for row in x['transactions']),
                          'mean_absolute_deviation_from_current_vol_target':None}
            logs=np.diff(np.log(p),axis=0)
            desired=np.array([min(1.,.15/max(float(logs[t-20:t,1].std(ddof=1)*np.sqrt(252)),1e-12)) for t in range(first,len(p))])
            sizing[name]['mean_absolute_deviation_from_current_vol_target']=float(np.abs(w[first:,1]-desired).mean())
    for bps in PROTOCOL['cost_bps']:
        costs[str(bps)]={name:score(np.asarray(account(rr,w[seed:],cc,cost_bps=bps)['returns'])[1:],years=years,cash=cash) for name,w in targets.items()}
    primary={};z=float(norm.ppf(1-.025/2))
    for name in ['1','5']:
        ev=newey_west_mean(net[name]-net['21'],lags=20)
        primary[name]={**ev,'family_lower':ev['mean']-z*ev['standard_error'],
                       'family_upper':ev['mean']+z*ev['standard_error'],'family_comparisons':2}
    periods=[]
    for start,end in [('2015-01-01','2020-01-01'),('2020-01-01','2025-01-01'),('2025-01-01','2100-01-01')]:
        m=mask(ed,start,end);ix=np.flatnonzero(m);previous=dates[seed] if ix[0]==0 else ed[ix[0]-1]
        span=(ed[ix[-1]]-previous).days/365.25
        periods.append({'start':start,'end_exclusive':end,'partial':end=='2100-01-01',
                        'scores':{name:score(values[m],years=span,cash=cash[m]) for name,values in net.items()}})
    def sharpe(values,rf):
        ex=values-rf;sd=ex.std(ddof=1)
        return float(ex.mean()/sd*np.sqrt(252)) if sd>0 else 0.
    def drawdown(values):
        wealth=np.r_[1.,np.cumprod(1+values)]
        return float((wealth/np.maximum.accumulate(wealth)-1).min())
    def differences(a,b,rf):
        return [float((np.log1p(a)-np.log1p(b)).sum()/years),sharpe(a,rf)-sharpe(b,rf),drawdown(a)-drawdown(b)]
    sensitivity={};alpha=.025/18
    for block in PROTOCOL['bootstrap_blocks']:
        rng=np.random.default_rng(17);values={name:[] for name in ['1','5']}
        for _ in range(1000):
            ix=stationary_bootstrap_indices(len(ed),expected_block=block,rng=rng)
            for name in values:values[name].append(differences(net[name][ix],net['21'][ix],cash[ix]))
        sensitivity[str(block)]={name:{'observed':dict(zip(PROTOCOL['bootstrap_metrics'],differences(net[name],net['21'],cash))),
                 'percentile_95':dict(zip(PROTOCOL['bootstrap_metrics'],np.percentile(v,[2.5,97.5],axis=0).T.tolist())),
                 'family_percentile_interval':dict(zip(PROTOCOL['bootstrap_metrics'],np.percentile(v,[alpha*100,(1-alpha)*100],axis=0).T.tolist()))}
                 for name,v in values.items()}
    result={'status':PROTOCOL['status'],'frozen':frozen,'sources':sources,'first':str(ed[0]),'last':str(ed[-1]),
            'years':years,'scores':scores,'cost_sensitivity':costs,'sizing_diagnostics':sizing,'primary_paired_vs_21':primary,
            'by_five_year_period':periods,'annual_log_gap_components_vs_full_nasdaq':attribution,
            'paired_bootstrap_sensitivity':sensitivity,
            'limits':['Only interval varies in the three-arm comparison; prior faster control also differs in band/override and is contextual only.',
                      'Repeated public-history development, no independent labels or model adoption.',
                      'Daily proportional drift rebalances still occur and are charged; target-update interval is not trade frequency.',
                      'Primary HAC is nominal. Bootstrap percentile intervals are approximate, especially extreme18-way tails with1000 replicates.',
                      'Drawdown bootstrap is path-dependent and stationary-block assumptions may fail under structural change.',
                      'No public daily benchmark return paths exported. Risk protection and raw growth are distinct objectives.']}
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for name,row in scores.items():print(name,'CAGR',round(row['cagr']*100,3),'vol',round(row['annualized_volatility']*100,3),'DD',round(row['max_drawdown']*100,3),'Sharpe',round(row['sharpe_vs_cash'],4),flush=True)
    print('primary',json.dumps(primary),flush=True);print('saved',out,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);args=parser.parse_args();run(args.output_dir)
