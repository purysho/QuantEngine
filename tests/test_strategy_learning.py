import datetime as dt
import unittest
import numpy as np
from workers.quant_strategy_learning import attribute, remedies, choose, sequential_choices, deployment_targets
from workers.quant_strategies import signals,backtest


class StrategyLearningTests(unittest.TestCase):
    def test_log_attribution_is_exact_not_additive_cagr(self):
        p=np.array([100,110,120,90,130,140.]);t=np.array([0,1,0,1,1,0.])
        a=attribute(p,t,cost_bps=10)
        self.assertAlmostEqual(a['net_log_gap_vs_buyhold'],a['missed_market_log_contribution']+a['relative_cost_log_contribution'])
        self.assertGreater(a['cost_log_drag'],0)
        self.assertEqual(a['exposure_days'],2)

    def test_window_attribution_sums_to_full_accounting(self):
        p=np.array([100,110,120,90,130,140.]);t=np.array([0,1,0,1,1,0.])
        a=attribute(p,t)
        parts=[attribute(p,t,indices=[0,1]),attribute(p,t,indices=[2,3,4])]
        for key in ['net_log_gap_vs_buyhold','missed_market_log_contribution','relative_cost_log_contribution']:
            self.assertAlmostEqual(a[key],sum(part[key] for part in parts))
        with self.assertRaises(ValueError):attribute(p,t,indices=[1,1])

    def test_remedy_signals_never_read_future_prices(self):
        p=100*np.exp(np.cumsum(np.random.default_rng(2).normal(0,.01,600)))
        changed=p.copy();changed[400:]*=3
        for name in remedies(p):
            np.testing.assert_array_equal(remedies(p)[name][:400],remedies(changed)[name][:400])

    def test_noise_or_no_advantage_never_replaces_baseline(self):
        base=np.zeros(300)
        picked=choose({'flat':base.copy(),'worse':base-.01},base)
        self.assertEqual(picked['choice'],'buyhold')
        self.assertFalse(picked['candidate_selected'])

    def test_selection_win_but_adoption_loss_is_rejected(self):
        dates=[dt.date(1990+i//250,1,1)+dt.timedelta(days=i%250) for i in range(250*25)]
        base=np.zeros(len(dates))
        candidate=.001+.00001*np.sin(np.arange(len(dates)))
        candidate[250*10:250*15]=-.001
        ledger=sequential_choices(dates,{'candidate':candidate},base)
        row=next(r for r in ledger if r['deployment_start_year']==2005)
        self.assertEqual(row['proposed'],'candidate')
        self.assertEqual(row['deployed'],'buyhold')
        self.assertEqual(row['adoption']['status'],'rejected')

    def test_model_switches_pay_real_costs_and_use_previous_close_signal(self):
        dates=[dt.date(2004,12,28)+dt.timedelta(days=i) for i in range(7)]
        targets=deployment_targets(dates,{'cash_rule':np.zeros(7)},
            [{'deployment_start_year':2005,'deployment_end_year':2010,'deployed':'cash_rule'}])
        np.testing.assert_array_equal(targets,[1,1,1,0,0,0,1])
        result=backtest([100]*7,targets,cost_bps=10)
        self.assertAlmostEqual(result['terminal_wealth'],.999**2)
        self.assertEqual(result['turnover'],2)

    def test_future_shocks_do_not_change_earlier_choices(self):
        dates=[dt.date(1990+i//250,1,1)+dt.timedelta(days=i%250) for i in range(250*30)]
        rng=np.random.default_rng(5);base=rng.normal(0,.01,len(dates))
        candidate=base+.0005+rng.normal(0,.001,len(dates))
        first=sequential_choices(dates,{'candidate':candidate},base)
        altered=candidate.copy();altered[250*20:]+=1
        second=sequential_choices(dates,{'candidate':altered},base)
        self.assertEqual([r for r in first if r['deployment_start_year']<=2010],
                         [r for r in second if r['deployment_start_year']<=2010])

if __name__=='__main__':unittest.main()
