"""Isolated sizing-interval experiment; existing policies remain unchanged."""
from __future__ import annotations
import numpy as np


def latency_targets(prices, *, minimum_closes):
    p=np.asarray(prices,dtype=float)
    if type(minimum_closes) is not int or minimum_closes<1:raise ValueError('Minimum interval must be a positive integer.')
    if p.ndim!=2 or p.shape[1]!=2 or len(p)<253 or not np.isfinite(p).all() or (p<=0).any():
        raise ValueError('Require253 positive finite two-asset closes.')
    logs=np.diff(np.log(p),axis=0);weights=np.zeros_like(p);held=0.;last=252-minimum_closes
    for t in range(252,len(p)):
        vol=float((logs[t-20:t]@np.array([0.,1.])).std(ddof=1)*np.sqrt(252))
        desired=min(1.,.15/max(vol,1e-12))
        if t-last>=minimum_closes and (t==252 or abs(desired-held)>=.1):
            held=desired;last=t
        weights[t,1]=held
    return weights
