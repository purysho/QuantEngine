"""Audit frozen decisions; never fit or modify a trading policy."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.competitive_test import data,mask
from workers.quant_competitive import regime_targets,core_tactical_targets,passive_vol_targets
from workers.quant_trade_audit import attribute,forward_payoffs,state_evidence
from workers.quant_strategies import rsi

PROTOCOL={'status':'exposed_historical_diagnostics','evaluation_start':'2015-01-01','cost_bps':10,
          'attribution_order':['participation','risk_sizing','asset_choice','strategy_cost','benchmark_cost_credit'],
          'horizons_closes':[1,5,20],'classifier_family_comparisons':18,
          'hac_lags':'max(5,horizon); original time grid; Bonferroni for 9 conditional edges and 9 state contrasts',
          'source_pins':{'broad_market':'2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db',
                         'nasdaq_total_return':'e4a3f645aa8ae8d5e2e2c3b054c2111c322961770ba28c3662d3035f1bef3afe'},
          'notice':'No signal, model, threshold, execution or adoption change. Outcome labels for diagnosis only. Local freeze is not independent custody.'}


def run(output,private_output):
    root=Path(__file__).resolve().parents[1];out=Path(output);private=Path(private_output)
    if out.resolve()==private.resolve():raise ValueError('Public summaries and private ledgers must be separate.')
    out.mkdir(parents=True,exist_ok=False);private.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__).resolve(),root/'workers/quant_trade_audit.py',root/'workers/quant_competitive.py',root/'experiments/competitive_test.py']
    frozen={'protocol':PROTOCOL,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (out/'frozen_protocol.json').write_text(json.dumps(frozen,indent=2)+'\n');archive=out/'source';archive.mkdir()
    for p in files:(archive/(p.name+'.txt')).write_bytes(p.read_bytes())
    print('frozen',hashlib.sha256((out/'frozen_protocol.json').read_bytes()).hexdigest(),flush=True)
    dates,p,r,c,sources=data(root/'.cache/data',True)
    for name,digest in PROTOCOL['source_pins'].items():
        if sources[name]['sha256']!=digest:raise ValueError('Source pin changed: '+name)
    policies=regime_targets(p);core=core_tactical_targets(p)
    targets={**policies['weights'],**passive_vol_targets(p),**core['weights']}
    first=int(np.flatnonzero(mask(dates,'2015-01-01','2100-01-01'))[0]);seed=first-1
    rr=r[seed:].copy();cc=c[seed:].copy();rr[0]=0;cc[0]=0;ed=dates[first:]
    years=(ed[-1]-dates[seed]).days/365.25
    held_states=[policies['regimes'][i-2] for i in range(first,len(dates))]
    summaries={};private_hashes={}
    for name,w in targets.items():
        x=attribute(rr,w[seed:],cc,cost_bps=10);components={k:v[1:] for k,v in x['components'].items()}
        aggregate=lambda m:{k:float(v[m].sum()) for k,v in components.items()}
        full=aggregate(np.ones(len(ed),dtype=bool))
        kinds=collections.Counter(row['kind'] for row in x['transactions'])
        fees={k:sum(row['fee'] for row in x['transactions'] if row['kind']==k) for k in kinds}
        windows={a:aggregate(mask(ed,a,b)) for a,b in [('2015-01-01','2020-01-01'),('2020-01-01','2025-01-01'),('2025-01-01','2100-01-01')]}
        states={s:aggregate(np.array(held_states)==s) for s in ['trend','range','stress']}
        for row in x['transactions']:
            t=row['close_index'];sig=row['signal_index'];row['date']=str(dates[seed+t])
            row['signal_date']=str(dates[seed+sig]) if sig is not None else None
            row['signal_state']=policies['regimes'][seed+sig] if sig is not None else 'terminal'
            if sig is not None and seed+sig>=252:
                i=seed+sig;changes=np.abs(np.diff(p[i-20:i+1,0]));den=changes.sum()
                row['decision_context']={'sma200':float(p[i-199:i+1,0].mean()),'broad_close':float(p[i,0]),
                    'efficiency20':float(abs(p[i,0]-p[i-20,0])/den) if den else 0.,
                    'relative_momentum126':np.log(p[i]/p[i-126]).tolist()}
            next_end=min(len(rr),t+6)
            row['subsequent_5close_realized_strategy_return']=float(np.prod(1+np.asarray(x['account']['returns'])[t+1:next_end])-1) if t+1<len(rr) else None
            row['outcome_notice']='Descriptive subsequent actual strategy path; overlapping outcomes, not causal profit of this trade.'
        ledger=private/(name+'_transactions.json')
        ledger.write_text(json.dumps({'transactions':x['transactions'],'daily_components':{k:v.tolist() for k,v in components.items()}},indent=2)+'\n')
        private_hashes[name]=hashlib.sha256(ledger.read_bytes()).hexdigest()
        summaries[name]={'components_log_wealth':full,'components_annual_log_percentage_points':{k:100*v/years for k,v in full.items()},
                         'net_log_gap_vs_nasdaq':float(sum(full.values())),'reconciliation_error':x['reconciliation_error'],
                         'mean_risky_exposure':float(x['held_exposure'][1:].mean()),
                         'cash_days':int((x['held_exposure'][1:]==0).sum()),'observations':len(ed),
                         'transaction_rows_by_kind':dict(kinds),'fees_by_kind_initial_capital_units':fees,
                         'by_five_year_window_log':windows,'by_holding_signal_state_log':states}
    # Fixed proposals evaluated everywhere so the state-vs-outside contrast is meaningful.
    strength=rsi(p[:,0]);mean_position=0.;proposals={s:np.zeros(len(p),dtype=int) for s in ['trend','range','stress']}
    # Code: 0=cash, 1=broad, 2=Nasdaq. No future outcome enters a proposal.
    for t in range(252,len(p)):
        if strength[t]<40:mean_position=1.
        elif strength[t]>60:mean_position=0.
        momentum=np.log(p[t]/p[t-126]);best=int(np.argmax(momentum))
        proposals['trend'][t]=best+1 if momentum[best]>0 else 0
        proposals['range'][t]=int(mean_position)
    checks={}
    for h in PROTOCOL['horizons_closes']:
        f=forward_payoffs(r,c,h);ix=f['signal_indices'];keep=(ix>=252)&(ix+2>=first)
        ix=ix[keep];asset=f['assets'][keep];cash=f['cash'][keep];labels=np.array(policies['regimes'])[ix]
        choices=np.column_stack([cash,asset]);rows={}
        for state,proposal in proposals.items():
            predicted=choices[np.arange(len(ix)),proposal[ix]]
            advantage=np.log1p(predicted)-np.log1p(asset[:,0]);hit=labels==state
            row=state_evidence(advantage,hit,horizon=h,comparisons=18)
            row.update({'broad_mean_forward_return':float(asset[hit,0].mean()),'broad_negative_fraction':float((asset[hit,0]<0).mean()),
                        'gross_rule_vs_broad_notice':'Fixed cash/all-in recommendation held from execution close for horizon; no fees, no intrahorizon switches, not traded strategy P&L.'})
            rows[state]=row
        checks[str(h)]=rows
    result={'status':PROTOCOL['status'],'sources':sources,'frozen':frozen,'first':str(ed[0]),'last':str(ed[-1]),'years':years,
            'attribution':summaries,'classifier_checks':checks,'private_ledger_sha256':private_hashes,
            'limits':['Telescoping attribution is order-dependent counterfactual accounting, not causal identification.',
                      'Classifier labels are hypotheses, not objectively observed market regimes.',
                      'All observations are already exposed development; no forecasting-superiority claim.',
                      'HAC intervals are nominal; bandwidth sensitivity, finite samples, repeated earlier research remain.',
                      'Private ledgers can reveal vendor return paths and must not be publicly uploaded. Public output is aggregate only.']}
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for name,row in summaries.items():print(name,json.dumps(row['components_annual_log_percentage_points']),flush=True)
    for h,rows in checks.items():print('classifier',h,json.dumps({s:{k:row[k] for k in ['mean','family_lower','family_upper','state_minus_outside','contrast_family_lower','contrast_family_upper']} for s,row in rows.items()}),flush=True)
    print('saved aggregate evidence',out,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);parser.add_argument('--private-dir',required=True)
    args=parser.parse_args();run(args.output_dir,args.private_dir)
