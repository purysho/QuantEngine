"""Matched-date competitive development replay, not a live performance claim."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np
from workers.quant_data import french,fred
from workers.quant_competitive import account,regime_targets,score,select_policy,passive_vol_targets,core_tactical_targets
from workers.quant_model_selection import newey_west_mean,white_reality_check

PROTOCOL={'selection':['2000-01-01','2010-01-01'],'adoption':['2010-01-01','2015-01-01'],
          'evaluation_start':'2015-01-01','assets':['CRSP_US_total_market','NASDAQ100_total_return'],
          'candidates':['situation_router','router_vol15','momentum_rotation'],
          'parameters':{'trend_sma':200,'efficiency_window':20,'efficiency_cutoff':.25,
                        'stress_volatility':.25,'rsi_period':14,'range_entry':40,'range_exit':60,
                        'momentum_window':126,'router_dispatch_closes':5,'rotation_closes':21,
                        'risk_target':.15,'risk_weight_band':.05},
          'cost_sensitivity_bps':[0,10,25],'fee_sensitivity':.0075,
          'hac_lags':5,'bootstrap_repetitions':500,'bootstrap_expected_block':5,'seed':17,
          'cash':'French realized RF, compounded across any missing common dates',
          'restriction':'Long/cash, no leverage/shorts; source data adjusted total-return research indices, not actual executable quotes.',
          'added_control':'After the initial replay, add strong passive rolling-volatility controls without changing candidate rules; later replay is exposed development.',
          'notice':'Rules selected by author before this replay, but prior broad-market history is exposed. No independently sealed future period.'}


def data(cache,offline):
    f,fm=french('F-F_Research_Data_Factors_daily',cache,offline=offline)
    q,qm=fred(['NASDAQXNDX'],cache,offline=offline)
    rf=f['series']['RF'];market=f['series']['Mkt-RF']+rf
    if not np.isfinite(rf).all() or not np.isfinite(market).all():raise ValueError('Missing market/cash data.')
    prices=np.cumprod(1+market);cash=np.cumprod(1+rf)
    nas={d:v for d,v in zip(q['dates'],q['series']['NASDAQXNDX']) if np.isfinite(v)}
    ix=[i for i,d in enumerate(f['dates']) if d in nas]
    dates=[f['dates'][i] for i in ix];p=np.column_stack([prices[ix],[nas[d] for d in dates]])
    r=np.vstack([np.zeros(2),p[1:]/p[:-1]-1]);c=np.r_[0.,cash[ix][1:]/cash[ix][:-1]-1]
    return dates,p,r,c,{'broad_market':fm,'nasdaq_total_return':qm,
                      'common_closes':len(dates),'raw_nasdaq_missing':int(np.isnan(q['series']['NASDAQXNDX']).sum())}


def mask(dates,start,end):
    return np.array([dt.date.fromisoformat(start)<=d<dt.date.fromisoformat(end) for d in dates])


def conditional(diff,states,state,comparisons):
    hit=np.array([s==state for s in states],dtype=float);count=int(hit.sum())
    if count<3:return {'observations':count,'mean_excess':None}
    mu=float(np.dot(hit,diff)/count)
    # Ratio-mean influence function on the original daily grid, not concatenated state days.
    influence=hit*(diff-mu)/hit.mean()
    ev=newey_west_mean(influence,lags=5);se=ev['standard_error']
    from scipy.stats import norm
    critical=float(norm.ppf(1-.025/comparisons))
    return {'comparisons':comparisons,'family_lower_95':mu-critical*se,'family_upper_95':mu+critical*se,'observations':count,'mean_excess':mu,'lower_95':mu-1.96*se,'upper_95':mu+1.96*se,
            'standard_error':se,'notice':'Exploratory state analysis, original-grid HAC plus Bonferroni over frozen models/states/benchmarks; no independent-custody proof.'}


def run(output,offline=False,core_tactical=False):
    root=Path(__file__).resolve().parents[1];out=Path(output);out.mkdir(parents=True,exist_ok=False)
    files=[root/'workers/quant_competitive.py',Path(__file__).resolve()]
    protocol=dict(PROTOCOL)
    if core_tactical:
        protocol.update({'candidates':['core80_tactical20','nasdaq_slow_vol15'],
                         'parameters':{'warmup':252,'core_nasdaq_weight':.8,'tactical_weight':.2,
                                       'relative_momentum_closes':126,'switch_margin_log':.05,
                                       'confirmation_closes':5,'minimum_switch_closes':21,
                                       'risk_window':20,'risk_target':.15,'risk_band':.1,'minimum_sizing_closes':21},
                         'notice':'All matched history previously exposed. Bounded core/tactical development only; no automatic adoption.',
                         'source_pins':{'broad_market':'2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db',
                                        'nasdaq_total_return':'e4a3f645aa8ae8d5e2e2c3b054c2111c322961770ba28c3662d3035f1bef3afe'}})
    frozen={'protocol':protocol,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            'custody':'Local source freeze; no trusted external timestamp or future-label isolation.'}
    (out/'frozen_protocol.json').write_text(json.dumps(frozen,indent=2)+'\n')
    archive=out/'source';archive.mkdir()
    for p in files:(archive/(p.name+'.txt')).write_bytes(p.read_bytes())
    print('frozen',hashlib.sha256((out/'frozen_protocol.json').read_bytes()).hexdigest(),flush=True)
    dates,p,r,c,sources=data(root/'.cache/data',offline)
    if core_tactical:
        for name,digest in protocol['source_pins'].items():
            if sources[name]['sha256']!=digest:raise ValueError('Competitive source snapshot changed: '+name)
    policies=regime_targets(p);targets=policies['weights'];n=len(dates)
    original_targets=targets
    if core_tactical:targets=core_tactical_targets(p)['weights']
    selection=np.flatnonzero(mask(dates,*PROTOCOL['selection']));adoption=np.flatnonzero(mask(dates,*PROTOCOL['adoption']))
    if len(selection)<2000 or len(adoption)<1000:raise ValueError('Insufficient calibration/adoption data.')
    benchmarks={'broad_buyhold':np.tile([1.,0.],(n,1)),'nasdaq_buyhold':np.tile([0.,1.],(n,1))}
    for name,asset in [('broad_risk15',0),('nasdaq_risk15',1)]:
        vol=float(r[selection,asset].std(ddof=1)*np.sqrt(252));w=min(1.,.15/vol)
        target=np.zeros((n,2));target[:,asset]=w;benchmarks[name]=target
    benchmarks.update(passive_vol_targets(p))
    if core_tactical:benchmarks.update(original_targets)
    all_targets={**benchmarks,**targets}
    shadow={name:account(r,w,c,cost_bps=10) for name,w in all_targets.items()}
    decisions={bench:select_policy({name:shadow[name]['returns'] for name in targets},shadow[bench]['returns'],
                selection=selection,adoption=adoption) for bench in (['broad_buyhold','nasdaq_buyhold','nasdaq_dynamic_vol15'] if core_tactical else ['broad_buyhold','nasdaq_buyhold'])}
    # Evaluate with fresh common starting capital and entry fees at evaluation boundary.
    first=int(np.flatnonzero(mask(dates,PROTOCOL['evaluation_start'],'2100-01-01'))[0]);seed=first-1
    eval_dates=dates[first:];rr=r[seed:].copy();cc=c[seed:].copy();rr[0]=0;cc[0]=0
    evaluated={name:account(rr,w[seed:],cc,cost_bps=10) for name,w in all_targets.items()}
    net={name:np.asarray(v['returns'])[1:] for name,v in evaluated.items()};cash=cc[1:]
    years=(eval_dates[-1]-dates[seed]).days/365.25
    scores={name:score(v,years=years,cash=cash) for name,v in net.items()}
    costs={}
    for bps in PROTOCOL['cost_sensitivity_bps']:
        costs[str(bps)]={name:score(np.asarray(account(rr,w[seed:],cc,cost_bps=bps)['returns'])[1:],years=years,cash=cash)
                         for name,w in targets.items()}
    fee_scores={name:score(np.asarray(account(rr,w[seed:],cc,cost_bps=10,annual_fee=.0075)['returns'])[1:],years=years,cash=cash)
                for name,w in targets.items()}
    states=[policies['regimes'][i-2] if i>=2 else 'warmup' for i in range(first,len(dates))]
    bystate={name:{bench:{state:conditional(net[name]-net[bench],states,state,len(targets)*len(benchmarks)*3) for state in ['trend','range','stress']}
                  for bench in benchmarks} for name in targets}
    periods=[]
    for start,end in [('2015-01-01','2020-01-01'),('2020-01-01','2025-01-01'),('2025-01-01','2100-01-01')]:
        m=mask(eval_dates,start,end)
        if m.any():
            begin=int(np.flatnonzero(m)[0]);previous=dates[seed] if begin==0 else eval_dates[begin-1]
            duration=(eval_dates[np.flatnonzero(m)[-1]]-previous).days/365.25
            periods.append({'start':start,'end_exclusive':end,'partial':end=='2100-01-01',
                            'scores':{name:score(v[m],years=duration,cash=cash[m]) for name,v in net.items()}})
    intervals={}
    for name,start,end in [('aieq_1yr','2024-10-01','2025-10-01'),('aieq_5yr','2020-10-01','2025-10-01'),('hfr_private_2025','2025-01-01','2026-01-01')]:
        m=mask(eval_dates,start,end);span=5 if name=='aieq_5yr' else 1
        if not m.any() or eval_dates[-1]<dt.date.fromisoformat(end)-dt.timedelta(days=4):raise ValueError('Incomplete comparator interval.')
        intervals[name]={'start':start,'end_exclusive':end,'model_scores':{k:score(v[m],years=span,cash=cash[m]) for k,v in net.items()},
                         'model_fee_sensitivity':{k:score(np.asarray(account(rr,w[seed:],cc,cost_bps=10,annual_fee=.0075)['returns'])[1:][m],years=span,cash=cash[m]) for k,w in targets.items()}}
    # Published AIEQ NAV performance: issuer Annual Shareholder Report, 2025-09-30.
    intervals['aieq_1yr'].update({'reference_return':.1968,'reference_type':'NAV total return net fund expenses','source':'https://amplifyetfs.com/wp-content/uploads/files/AIEQ_Annual_Report.pdf'})
    intervals['aieq_5yr'].update({'reference_cagr':.0871,'reference_type':'NAV annualized total return net fund expenses','source':'https://amplifyetfs.com/wp-content/uploads/files/AIEQ_Annual_Report.pdf'})
    intervals['hfr_private_2025']['notice']='Model interval computed; HFR numerical benchmark not bundled or publicly republished. Licensed full history unavailable. Private source comparison only, no hedge-fund population ranking.'
    diagnostics={bench:{'paired':{name:newey_west_mean(net[name]-net[bench],lags=5) for name in targets},
                        'global':white_reality_check(-np.column_stack([net[name] for name in targets]),-net[bench],expected_block=5,repetitions=500,seed=17)} for bench in benchmarks}
    result={'status':'historical_development_competitive_replay','sources':sources,'frozen':frozen,
            'evaluation_first':str(eval_dates[0]),'evaluation_last':str(eval_dates[-1]),'years':years,
            'scores':scores,'selection_and_adoption':decisions,'by_five_year_period':periods,
            'by_pretrade_state':bystate,'cost_sensitivity':costs,'fee_075pct_sensitivity':fee_scores,
            'matched_published_intervals':intervals,'diagnostics':diagnostics,
            'benchmark_risk_weights':{name:w[0].tolist() for name,w in benchmarks.items()},
            'limits':['Revised, publicly exposed historical sources, no independent unseen-label custody.',
                      'Index-level adjusted closes, no actual quotes, ETF tracking/expenses, trade tape or executable fill proof.',
                      'AIEQ only published 1/5yr NAV intervals; no daily paired risk inference; not representative of all AI bots.',
                      'No licensed full HFR histories; annual private comparison cannot establish hedge-fund superiority.',
                      'Regimes and capital risk controls use historical closes; no earnings/news prediction or foresight.']}
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    # Only derived candidate paths are exported; do not publish reconstructible vendor benchmark series.
    import csv
    with (out/'candidate_returns.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['date','pretrade_state',*targets])
        writer.writerows([str(d),s,*[net[name][i] for name in targets]] for i,(d,s) in enumerate(zip(eval_dates,states)))
    print('evaluation',result['evaluation_first'],result['evaluation_last'],flush=True)
    for name,row in scores.items():print(name,'CAGR',round(row['cagr']*100,2),'vol',round(row['annualized_volatility']*100,2),'DD',round(row['max_drawdown']*100,2),'Sharpe',row['sharpe_vs_cash'])
    print('adoption',json.dumps({b:{'selected':d['selected'],'adopted':d['adopted']} for b,d in decisions.items()}))
    print('saved',out)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true');parser.add_argument('--core-tactical',action='store_true');parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();run(args.output_dir,args.offline,args.core_tactical)
