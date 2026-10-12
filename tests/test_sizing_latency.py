import importlib
import importlib.util
import unittest
import numpy as np
from workers.quant_competitive import core_tactical_targets

class SizingLatencyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('workers.quant_sizing_latency'),'isolated sizing policy is missing')
        self.policy=importlib.import_module('workers.quant_sizing_latency').latency_targets

    def test_21_close_arm_exactly_reproduces_existing_passive_control(self):
        rng=np.random.default_rng(3);p=100*np.exp(np.cumsum(rng.normal(.0003,.02,(600,2)),axis=0))
        np.testing.assert_array_equal(self.policy(p,minimum_closes=21),core_tactical_targets(p)['weights']['nasdaq_slow_vol15'])

    def test_only_interval_blocks_response_to_same_volatility_shock(self):
        logs=np.full((360,2),.001);logs[253:281,1]=np.where(np.arange(28)%2,.08,-.08)
        p=100*np.exp(np.cumsum(logs,axis=0))
        fast=self.policy(p,minimum_closes=1);slow=self.policy(p,minimum_closes=21)
        self.assertLess(fast[253,1],1);self.assertEqual(slow[253,1],1);self.assertLess(slow[273,1],1)
        np.testing.assert_array_equal(fast[:253],slow[:253])

    def test_each_update_respects_fixed_band_and_minimum_interval(self):
        rng=np.random.default_rng(6);p=100*np.exp(np.cumsum(rng.normal(0,.03,(800,2)),axis=0))
        for interval in [1,5,21]:
            w=self.policy(p,minimum_closes=interval);changes=np.flatnonzero(np.abs(np.diff(w[:,1]))>1e-12)+1
            self.assertGreater(len(changes),2)
            self.assertTrue((np.diff(changes)>=interval).all())
            self.assertTrue((np.abs(w[changes[1:],1]-w[changes[1:]-1,1])>=.1-1e-12).all())
            np.testing.assert_array_equal(w[:252],0);np.testing.assert_array_equal(w[:,0],0)
            self.assertTrue(((w>=0)&(w<=1)).all())

    def test_future_prices_cannot_change_prior_weights(self):
        rng=np.random.default_rng(3);p=100*np.exp(np.cumsum(rng.normal(0,.02,(600,2)),axis=0));q=p.copy();q[450:]*=8
        for interval in [1,5,21]:np.testing.assert_array_equal(self.policy(p,minimum_closes=interval)[:450],self.policy(q,minimum_closes=interval)[:450])

    def test_invalid_inputs_rejected(self):
        p=np.ones((300,2))
        for interval in [0,True,1.5,-1]:
            with self.assertRaises(ValueError):self.policy(p,minimum_closes=interval)
        for bad in [np.zeros((300,2)),np.ones((252,2)),np.ones((300,3)),np.full((300,2),np.nan)]:
            with self.assertRaises(ValueError):self.policy(bad,minimum_closes=1)

if __name__=='__main__':unittest.main()
