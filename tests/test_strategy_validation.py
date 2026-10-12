import datetime as dt
import unittest
import numpy as np
from workers.quant_strategies import signals, backtest, five_year_blocks, rsi


class StrategyValidationTests(unittest.TestCase):
    def test_prefix_invariance_for_all_rules(self):
        p = 100 * np.exp(np.cumsum(np.random.default_rng(23).normal(0, .01, 400)))
        changed = p.copy(); changed[270:] *= 4
        for name in signals(p):
            np.testing.assert_array_equal(signals(p)[name][:270], signals(changed)[name][:270])

    def test_signal_close_cannot_capture_next_close_move(self):
        result = backtest([100, 100, 200, 400], [0, 1, 1, 1], cost_bps=10)
        np.testing.assert_allclose(result['net_returns'], [0, -.001, .998])
        self.assertAlmostEqual(result['terminal_wealth'], .999 * 2 * .999)

    def test_flat_price_round_trip_pays_entry_and_exit(self):
        result = backtest([100]*5, [1]*5, cost_bps=10)
        self.assertAlmostEqual(result['terminal_wealth'], .999**2)
        self.assertEqual(result['turnover'], 2)

    def test_rsi_edges_and_hand_computed_seed(self):
        self.assertEqual(rsi(np.ones(20))[-1], 50)
        self.assertEqual(rsi(np.arange(1,21))[-1], 100)
        self.assertEqual(rsi(np.arange(20,0,-1))[-1], 0)
        self.assertAlmostEqual(rsi([100, 102, 101, 103], period=3)[-1], 80)

    def test_exact_calendar_windows_and_partial_flag(self):
        dates = [dt.date(y, 1, 2) for y in range(1990, 2003)]
        blocks = five_year_blocks(dates)
        self.assertEqual([(b['start_year'], b['end_year'], b['complete']) for b in blocks],
                         [(1990,1995,True),(1995,2000,True),(2000,2005,False)])
        self.assertEqual(sum(len(b['indices']) for b in blocks), len(dates))

    def test_bad_inputs_fail_closed(self):
        for p in ([100,float('nan'),101], [100,0,101]):
            with self.assertRaises(ValueError): signals(p)
        with self.assertRaises(ValueError): backtest([100,101,102], [0,2,0])
        with self.assertRaises(ValueError): backtest([100,101,102], [0,1,0], cost_bps=-1)

if __name__ == '__main__': unittest.main()
