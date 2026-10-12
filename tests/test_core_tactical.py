"""Economic invariants for the bounded persistent-core hypothesis."""
import unittest
import numpy as np
from workers import quant_competitive as competitive


class CoreTacticalTests(unittest.TestCase):
    def run_policy(self, p):
        self.assertTrue(hasattr(competitive, 'core_tactical_targets'), 'persistent-core policy is missing')
        return competitive.core_tactical_targets(p)

    def test_noisy_uptrend_keeps_core_and_bounds_tactical_rotation(self):
        t=np.arange(500);p=np.column_stack([100*np.exp(.002*t+.01*np.sin(t)),100*np.exp(.0005*t)])
        result=self.run_policy(p)
        w=result['weights']['core80_tactical20']
        np.testing.assert_array_equal(w[:252],0)
        self.assertGreater(w[-1,0],0)
        self.assertTrue((w[252:,1]>=.8*w[252:].sum(axis=1)-1e-12).all())
        self.assertTrue((w.sum(axis=1)<=1+1e-12).all())
        self.assertTrue((w>=0).all())

    def test_switches_require_confirmation_and_minimum_holding_period(self):
        t=np.arange(650);p=np.column_stack([100*np.exp(.001*t+.15*np.sin(t/40)),100*np.exp(.001*t)])
        result=self.run_policy(p)
        switches=np.flatnonzero(np.diff(result['tactical_asset'])!=0)+1
        self.assertGreater(len(switches),2)
        self.assertTrue((np.diff(switches)>=21).all())
        self.assertTrue(all(result['confirmation_count_at_switch'][s]>=5 for s in switches))

    def test_risk_band_is_not_overridden_by_calendar_dispatch(self):
        rng=np.random.default_rng(17)
        p=100*np.exp(np.cumsum(rng.normal(.001,.02,(500,2)),axis=0))
        result=self.run_policy(p)
        exposure=result['weights']['nasdaq_slow_vol15'].sum(axis=1)
        changes=np.flatnonzero(np.abs(np.diff(exposure))>1e-12)+1
        self.assertTrue((np.diff(changes)>=21).all())
        for i in changes:
            if i>252:self.assertGreaterEqual(abs(exposure[i]-exposure[i-1]),.1-1e-12)

    def test_future_perturbations_leave_prior_targets_and_switches_unchanged(self):
        rng=np.random.default_rng(19);p=100*np.exp(np.cumsum(rng.normal(.0005,.02,(600,2)),axis=0))
        q=p.copy();q[450:]*=7
        a=self.run_policy(p);b=self.run_policy(q)
        for k in a['weights']:np.testing.assert_array_equal(a['weights'][k][:450],b['weights'][k][:450])
        np.testing.assert_array_equal(a['tactical_asset'][:450],b['tactical_asset'][:450])

    def test_invalid_price_input_is_rejected(self):
        self.assertTrue(hasattr(competitive,'core_tactical_targets'))
        for p in [np.ones((252,2)),np.ones((300,3)),np.zeros((300,2)),np.full((300,2),np.nan)]:
            with self.assertRaises(ValueError):competitive.core_tactical_targets(p)

if __name__=='__main__':unittest.main()
