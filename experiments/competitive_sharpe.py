"""Post-replay paired Sharpe sensitivity; not a prespecified alpha gate."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.competitive_test import data,mask
from workers.quant_competitive import account,passive_vol_targets
from workers.quant_model_selection import stationary_bootstrap_indices


def run(output):
    root=Path(__file__).resolve().parents[1]
    dates,prices,returns,cash,_=data(root/'.cache/data',True)
    first=int(np.flatnonzero(mask(dates,'2015-01-01','2100-01-01'))[0]);seed=first-1
    r=returns[seed:].copy();c=cash[seed:].copy();r[0]=0;c[0]=0
    b=np.asarray(account(r,np.tile([0.,1.],(len(r),1)),c)['returns'])[1:]-c[1:]
    w=passive_vol_targets(prices)['nasdaq_dynamic_vol15'][seed:]
    a=np.asarray(account(r,w,c)['returns'])[1:]-c[1:]
    def sharpe(x):return float(x.mean()/x.std(ddof=1)*np.sqrt(252))
    result={'status':'post_replay_exploratory_risk_control_diagnostic',
            'observed_sharpe_difference':sharpe(a)-sharpe(b),
            'candidate':'passive_Nasdaq_vol15','benchmark':'Nasdaq_buyhold','blocks':{}}
    for block in (5,20,60):
        rng=np.random.default_rng(17);values=[]
        for _ in range(1000):
            ix=stationary_bootstrap_indices(len(a),expected_block=block,rng=rng)
            values.append(sharpe(a[ix])-sharpe(b[ix]))
        result['blocks'][str(block)]={'repetitions':1000,'percentile_95':np.percentile(values,[2.5,97.5]).tolist()}
    with Path(output).open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args();run(args.output)
