import unittest
import numpy as np
from workers.quant_competitive import account,regime_targets,score,select_policy,passive_vol_targets

class CompetitiveTests(unittest.TestCase):
    def test_costs_are_self_financing_on_actual_traded_notional(self):
        r=np.zeros((4,2));w=np.tile([1.,0.],(4,1))
        result=account(r,w,np.zeros(4),cost_bps=10)
        self.assertAlmostEqual(result['wealth'][-1],(1-.001)/(1+.001))
        self.assertAlmostEqual(sum(result['costs']),1-result['wealth'][-1])

    def test_next_close_delay_and_switch_costs(self):
        r=np.array([[0,0],[1,0],[1,0],[0,0]],float)
        w=np.tile([1.,0.],(4,1))
        result=account(r,w,np.zeros(4),cost_bps=0)
        np.testing.assert_allclose(result['returns'],[0,0,1,0])
        switched=account(np.zeros((5,2)),np.array([[1,0],[0,1],[0,1],[0,1],[0,1]]),np.zeros(5),cost_bps=10)
        self.assertGreater(sum(switched['turnover_notional']),sum(account(np.zeros((5,2)),np.tile([1,0],(5,1)),np.zeros(5),cost_bps=10)['turnover_notional']))

    def test_cash_earns_realized_interest_and_no_leverage(self):
        r=np.zeros((4,2));cash=np.full(4,.001)
        result=account(r,np.zeros_like(r),cash,cost_bps=0)
        self.assertAlmostEqual(result['wealth'][-1],1.001**4)
        with self.assertRaises(ValueError):account(r,np.full_like(r,.75),cash)
        with self.assertRaises(ValueError):account(r,np.zeros_like(r),cash,cost_bps=-1)

    def test_future_prices_do_not_change_regimes_or_prior_returns(self):
        rng=np.random.default_rng(31);p=100*np.exp(np.cumsum(rng.normal(0,.01,(600,2)),axis=0))
        q=p.copy();q[450:]*=4
        first=regime_targets(p);second=regime_targets(q)
        for name in first['weights']:
            np.testing.assert_array_equal(first['weights'][name][:450],second['weights'][name][:450])
        self.assertEqual(first['regimes'][:450],second['regimes'][:450])
        r=np.vstack([np.zeros(2),p[1:]/p[:-1]-1]);changed_r=np.vstack([np.zeros(2),q[1:]/q[:-1]-1])
        for name in first['weights']:
            a=account(r,first['weights'][name],np.zeros(600));b=account(changed_r,second['weights'][name],np.zeros(600))
            np.testing.assert_array_equal(a['returns'][:450],b['returns'][:450])

    def test_passive_risk_control_is_causal_and_capped(self):
        rng=np.random.default_rng(17);p=100*np.exp(np.cumsum(rng.normal(0,.025,(400,2)),axis=0))
        changed=p.copy();changed[300:]*=5
        a=passive_vol_targets(p);b=passive_vol_targets(changed)
        for name in a:
            np.testing.assert_array_equal(a[name][:300],b[name][:300])
            self.assertTrue((a[name]>=0).all());self.assertTrue((a[name].sum(axis=1)<=1).all())

    def test_selection_does_not_use_adoption_outcomes(self):
        rng=np.random.default_rng(1);b=rng.normal(0,.01,500)
        c={'better':b+.001+rng.normal(0,.0001,500),'worse':b-.001}
        decision=select_policy(c,b,selection=range(200),adoption=range(200,400))
        changed={k:v.copy() for k,v in c.items()};changed['better'][200:400]-=.01
        rejected=select_policy(changed,b,selection=range(200),adoption=range(200,400))
        self.assertEqual(decision['selected'],rejected['selected'])
        self.assertTrue(decision['adopted']);self.assertFalse(rejected['adopted'])
        with self.assertRaises(ValueError):select_policy(c,b,selection=range(200),adoption=range(199,400))

    def test_drawdown_includes_initial_capital(self):
        row=score([-.5,.1],years=1,cash=[0,0])
        self.assertAlmostEqual(row['max_drawdown'],-.5)
        self.assertAlmostEqual(row['cagr'],-.45)

if __name__=='__main__':unittest.main()
