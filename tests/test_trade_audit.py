import unittest
import numpy as np
import importlib.util
import importlib

class TradeAuditTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("workers.quant_trade_audit"), "trade audit implementation is missing")
        global audit
        audit=importlib.import_module("workers.quant_trade_audit")

    def test_pure_cash_gap_is_participation(self):
        r=np.array([[0,0],[0,0],[.02,.1],[.01,.2]])
        x=audit.attribute(r,np.zeros_like(r),np.zeros(4),cost_bps=0)
        self.assertAlmostEqual(sum(x['components']['participation']),-np.log(1.1*1.2))
        self.assertAlmostEqual(sum(x['components']['risk_sizing']),0)
        self.assertAlmostEqual(x['reconciliation_error'],0)

    def test_half_exposure_has_only_sizing_gap(self):
        r=np.array([[0,0],[0,0],[0,.1],[0,-.1]])
        x=audit.attribute(r,np.tile([0,.5],(4,1)),np.zeros(4),cost_bps=0)
        self.assertAlmostEqual(sum(x['components']['participation']),0)
        self.assertAlmostEqual(sum(x['components']['asset_choice']),0)
        self.assertAlmostEqual(sum(x['components']['risk_sizing']),np.log(1.05*.95)-np.log(1.1*.9))

    def test_asset_choice_switches_and_fees_reconcile(self):
        r=np.array([[0,0],[0,0],[.1,.2],[-.2,.1],[.02,.03]])
        w=np.array([[1,0],[0,1],[.25,.5],[0,0],[0,0]])
        x=audit.attribute(r,w,np.full(5,.001),cost_bps=10)
        self.assertAlmostEqual(sum(sum(v) for v in x['components'].values()),x['net_log_gap'])
        self.assertAlmostEqual(sum(row['fee'] for row in x['transactions']),sum(x['account']['costs']))
        self.assertTrue(any(row['buy_notional']>0 and row['sell_notional']>0 for row in x['transactions']))
        self.assertGreater(len(x['transactions']),0)

    def test_reported_gap_matches_independent_terminal_wealth_ratio(self):
        from workers.quant_competitive import account
        rng=np.random.default_rng(7);r=rng.normal(0,.02,(100,2));w=np.tile([.2,.5],(100,1));cash=np.full(100,.0001)
        x=audit.attribute(r,w,cash)
        baseline=account(r,np.tile([0,1],(100,1)),cash,cost_bps=10)
        self.assertAlmostEqual(x['net_log_gap'],np.log(x['account']['wealth'][-1]/baseline['wealth'][-1]))
        self.assertTrue(any(row['kind']=='drift_rebalance' for row in x['transactions']))

    def test_state_contrast_recovers_planted_difference(self):
        hit=np.arange(200)<100;values=np.where(hit,.01,-.01)
        x=audit.state_evidence(values,hit,horizon=5,comparisons=18)
        self.assertAlmostEqual(x['state_minus_outside'],.02)
        self.assertGreater(x['contrast_family_lower'],0)

    def test_future_outcomes_do_not_change_prior_trade_ledger(self):
        rng=np.random.default_rng(7);r=rng.normal(0,.02,(100,2));q=r.copy();q[80:]=.3
        w=np.tile([.2,.5],(100,1));cash=np.zeros(100)
        a=audit.attribute(r,w,cash);b=audit.attribute(q,w,cash)
        for name in a['components']:np.testing.assert_array_equal(a['components'][name][:80],b['components'][name][:80])
        self.assertEqual([row for row in a['transactions'] if row['close_index']<80],[row for row in b['transactions'] if row['close_index']<80])

    def test_signal_is_aligned_two_closes_before_outcome(self):
        x=audit.forward_payoffs(np.array([[0,0],[0,0],[.1,.2],[.2,.3],[.4,.5]]),np.zeros(5),1)
        np.testing.assert_allclose(x['assets'][0],[.1,.2])
        self.assertEqual(x['signal_indices'][0],0)
        self.assertEqual(x['last_outcome_indices'][-1],4)
        y=audit.forward_payoffs(np.array([[0,0],[0,0],[.1,.2],[.2,.3],[.4,.5]]),np.zeros(5),2)
        np.testing.assert_allclose(y['assets'][0],np.array([1.1*1.2,1.2*1.3])-1)

    def test_short_confirmation_labels_do_not_fake_independent_samples(self):
        values=np.arange(200)/1000;hit=np.arange(200)%2==0
        x=audit.state_evidence(values,hit,horizon=20,comparisons=18)
        self.assertEqual(x['hac_lags'],20)
        self.assertLessEqual(x['family_lower'],x['lower_95'])
        self.assertAlmostEqual(x['mean'],values[hit].mean())

if __name__=='__main__':unittest.main()
