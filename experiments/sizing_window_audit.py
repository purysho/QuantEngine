"""Retrospective examination of an exposed adverse window; policies unchanged."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.competitive_test import data,mask
from experiments.sizing_latency import PROTOCOL as SIZING_PROTOCOL
from workers.quant_sizing_latency import latency_targets
from workers.quant_trade_audit import attribute

PROTOCOL={'status':'exposed_adverse_window_examination','window':['2015-01-01','2020-01-01'],
          'comparisons':[1,5],'reference':21,'cost_bps':10,'source_pins':SIZING_PROTOCOL['source_pins'],
          'partitions':'less/more held equity crossed with Nasdaq daily return above/below RF; equal/tied separately',
          'intervals':'non-overlapping intervals between either arm changing its held target; signal s affects first return s+2',
          'ranking':'top5 negative intervals per arm for descriptive concentration, never a signal or selection feature',
          'notice':'Diagnostic chosen after observing the adverse window. No new inference, parameter change, model selection or independent validation.'}


def run(output,private_output):
    root=Path(__file__).resolve().parents[1];out=Path(output);private=Path(private_output)
    if out.resolve().is_relative_to(private.resolve()) or private.resolve().is_relative_to(out.resolve()):
        raise ValueError('Public and private output directories must be disjoint.')
    out.mkdir(parents=True,exist_ok=False);private.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__).resolve(),root/'workers/quant_sizing_latency.py',root/'workers/quant_trade_audit.py',
           root/'workers/quant_competitive.py',root/'experiments/competitive_test.py',root/'experiments/sizing_latency.py']
    frozen={'protocol':PROTOCOL,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (out/'frozen_protocol.json').write_text(json.dumps(frozen,indent=2)+'\n');source=out/'source';source.mkdir()
    for p in files:(source/(p.name+'.txt')).write_bytes(p.read_bytes())
    print('frozen',hashlib.sha256((out/'frozen_protocol.json').read_bytes()).hexdigest(),flush=True)
    dates,p,r,c,sources=data(root/'.cache/data',True)
    for name,digest in PROTOCOL['source_pins'].items():
        if sources[name]['sha256']!=digest:raise ValueError('Source pin changed: '+name)
    first=int(np.flatnonzero(mask(dates,'2015-01-01','2100-01-01'))[0]);seed=first-1
    rr=r[seed:].copy();cc=c[seed:].copy();rr[0]=0;cc[0]=0;ed=dates[first:]
    indices=np.flatnonzero(mask(ed,*PROTOCOL['window']));wd=np.array(ed,dtype=object)[indices]
    years=(wd[-1]-dates[seed]).days/365.25
    arms={n:attribute(rr,latency_targets(p,minimum_closes=n)[seed:],cc) for n in [1,5,21]}
    result={}
    for n in [1,5]:
        a=arms[n];b=arms[21]
        gross=sum(a['components'][k][1:]-b['components'][k][1:] for k in ['participation','risk_sizing','asset_choice'])[indices]
        fees=(a['components']['strategy_cost'][1:]-b['components']['strategy_cost'][1:])[indices]
        na=np.log1p(np.asarray(a['account']['returns'])[1:])[indices]
        nb=np.log1p(np.asarray(b['account']['returns'])[1:])[indices]
        if not np.allclose(gross+fees,na-nb,rtol=0,atol=1e-12):raise ArithmeticError('Daily net/gross/cost decomposition mismatch.')
        ea=a['held_exposure'][1:][indices];eb=b['held_exposure'][1:][indices];delta=ea-eb
        excess=(rr[1:,1]-cc[1:])[indices]
        masks={'less_equity_above_cash':(delta<0)&(excess>0),'less_equity_below_cash':(delta<0)&(excess<0),
               'more_equity_above_cash':(delta>0)&(excess>0),'more_equity_below_cash':(delta>0)&(excess<0),
               'equal_exposure_or_return':(delta==0)|(excess==0)}
        if not np.all(sum(hit.astype(int) for hit in masks.values())==1):raise ArithmeticError('Nonexclusive exposure partitions.')
        cells={k:{'days':int(hit.sum()),'gross_log_contribution':float(gross[hit].sum()),
                  'annual_log_percentage_points':float(gross[hit].sum()/years*100)} for k,hit in masks.items()}
        if abs(sum(row['gross_log_contribution'] for row in cells.values())-gross.sum())>1e-12:
            raise ArithmeticError('Exposure partitions failed to reconcile.')
        # Every observed held-target change starts a new outcome interval, not an overlapping event window.
        boundaries=np.r_[0,np.flatnonzero((np.diff(ea)!=0)|(np.diff(eb)!=0))+1,len(indices)]
        intervals=[]
        for start,end in zip(boundaries[:-1],boundaries[1:]):
            sign='less' if delta[start]<0 else 'more' if delta[start]>0 else 'equal'
            row={'start':str(wd[start]),'end_inclusive':str(wd[end-1]),'observations':int(end-start),
                 'fast_exposure':float(ea[start]),'slow_exposure':float(eb[start]),'relative_exposure':sign,
                 'gross_log_difference':float(gross[start:end].sum()),
                 'fee_log_difference_same_calendar_days':float(fees[start:end].sum()),
                 'net_log_difference':float((na[start:end]-nb[start:end]).sum()),
                 'cash_relative_index_log_return':float((np.log1p(rr[1:,1][indices][start:end])-np.log1p(cc[1:][indices][start:end])).sum()),
                 'context_signal_date_for_first_outcome':str(dates[first+indices[start]-2]),
                 'signal_context_notice':'Most recent held-target change may come from either arm. First-return context is signal close two dates earlier; not an inferred trade cause.'}
            context=first+indices[start]-2
            vol=float(np.diff(np.log(p[context-20:context+1,1])).std(ddof=1)*np.sqrt(252))
            row['trailing_volatility_at_context_signal']=vol
            row['desired_fraction_at_context_signal']=min(1.,.15/max(vol,1e-12))
            intervals.append(row)
        if sum(row['observations'] for row in intervals)!=len(indices) or abs(sum(row['net_log_difference'] for row in intervals)-(na-nb).sum())>1e-12:
            raise ArithmeticError('Nonoverlapping intervals failed to reconcile.')
        ledger=private/(str(n)+'_decision_intervals.json');ledger.write_text(json.dumps(intervals,indent=2)+'\n')
        timeline={}
        for year in range(2015,2020):
            hit=np.array([d.year==year for d in wd]);timeline[str(year)]={'gross_log_difference':float(gross[hit].sum()),
                'fee_log_difference':float(fees[hit].sum()),'net_log_difference':float((na-nb)[hit].sum())}
        quarters={}
        for q in range(1,5):
            hit=np.array([d.year==2018 and (d.month-1)//3+1==q for d in wd]);quarters[str(q)]={
                'gross_log_difference':float(gross[hit].sum()),'fee_log_difference':float(fees[hit].sum()),
                'net_log_difference':float((na-nb)[hit].sum())}
        top=sorted(intervals,key=lambda row:row['gross_log_difference'])[:5]
        trades={}
        for name,arm in [('responsive',a),('reference',b)]:
            rows=[row for row in arm['transactions'] if row['close_index']-1 in indices]
            trades[name]=dict(collections.Counter(row['kind'] for row in rows))
        net=float((na-nb).sum())
        result[str(n)]={'gross_log_difference':float(gross.sum()),'fee_log_difference':float(fees.sum()),'net_log_difference':net,
                       'annual_log_percentage_points':{'gross':float(gross.sum()/years*100),'fees':float(fees.sum()/years*100),'net':net/years*100},
                       'fee_share_of_net_shortfall':float(fees.sum()/net),'gross_share_of_net_shortfall':float(gross.sum()/net),
                       'year2018_share_of_net_shortfall':timeline['2018']['net_log_difference']/net,
                       'mean_fast_exposure':float(ea.mean()),'mean_reference_exposure':float(eb.mean()),
                       'exposure_cells':cells,'by_year':timeline,'year2018_by_quarter':quarters,
                       'interval_count':len(intervals),'top5_negative_gross_intervals':top,
                       'transaction_rows_by_kind':trades,'private_interval_ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),
                       'reconciliation_max_error':float(np.max(np.abs(gross+fees-(na-nb))))}
        print('arm',n,json.dumps({k:result[str(n)][k] for k in ['annual_log_percentage_points','fee_share_of_net_shortfall','year2018_share_of_net_shortfall','top5_negative_gross_intervals']}),flush=True)
    report={'status':PROTOCOL['status'],'first':str(wd[0]),'last':str(wd[-1]),'years':years,'frozen':frozen,'sources':sources,'comparisons':result,
            'limits':['Chosen adverse window and ranked intervals are retrospective descriptions, not new statistical discoveries.',
                      'Gross exposure differences describe realized counterfactual portfolios, not causal effects on market prices.',
                      'Fees are attributed to their calendar day; new target execution fees precede its first risky return.',
                      'Full-sample portfolios continue beyond2019; no artificial boundary liquidation is inserted.',
                      'Private complete interval ledger can reconstruct vendor observations and must not be publicly archived.',
                      'All original strategies/parameters remain unchanged; no hindsight rule or model adoption.']}
    (out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);parser.add_argument('--private-dir',required=True)
    args=parser.parse_args();run(args.output_dir,args.private_dir)
