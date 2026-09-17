import unittest
import numpy as np
import pandas as pd
from modules.quant_engine import (metrics, weights, apply_costs, walk_forward,
                                  demo_prices, validate_prices, bootstrap, risk_contributions)


class QuantTests(unittest.TestCase):
    def test_initial_loss_drawdown(self):
        result = metrics(pd.Series([-.1, 0., .05]))
        self.assertAlmostEqual(result['Max drawdown'], -.1)

    def test_known_tail_risk(self):
        r = pd.Series(np.arange(-.10, .10, .01))
        m = metrics(r)
        self.assertGreaterEqual(m['Daily ES 95%'], m['Daily VaR 95%'])
        self.assertAlmostEqual(m['Daily ES 95%'], .1)

    def test_lag_no_future_leakage(self):
        p = demo_prices().head(600)
        changed = p.copy()
        changed.iloc[400:] *= 2
        for model in ['Momentum','Inverse volatility','Equal weight']:
            pd.testing.assert_frame_equal(weights(p,model).iloc[:402], weights(changed,model).iloc[:402])

    def test_entry_cost_and_drift(self):
        p = pd.DataFrame({'A':[100.,110.,110.], 'B':[100.,100.,100.]})
        w = pd.DataFrame({'A':[0.,.5,.5], 'B':[0.,.5,.5]})
        ledger = apply_costs(p,w,10)
        self.assertAlmostEqual(ledger.Cost.iloc[1], .001)
        self.assertAlmostEqual(ledger.Net.iloc[1], .049)
        self.assertAlmostEqual(ledger.Turnover.iloc[2], 1/21)

    def test_walk_forward_chronology_and_future_independence(self):
        p = demo_prices().head(800)
        a, folds, aw = walk_forward(p,126,63)
        self.assertTrue((folds['Train end'] < folds['Test start']).all())
        self.assertTrue((folds['Test end'].iloc[:-1].to_numpy() < folds['Test start'].iloc[1:].to_numpy()).all())
        altered = p.copy()
        altered.iloc[500:] *= 1.5
        b, _, bw = walk_forward(altered,126,63)
        pd.testing.assert_series_equal(a.Net.loc[:p.index[499]],b.Net.loc[:p.index[499]])
        self.assertTrue((aw.sum(axis=1) <= 1+1e-9).all())

    def test_bootstrap_repeatable_and_initial_nav(self):
        r = np.array([-.01,.02,0,.01,-.02]*20)
        a, dd = bootstrap(r,63,100,5)
        b, _ = bootstrap(r,63,100,5)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(a[:,0],np.ones(100))
        self.assertTrue((dd <= 0).all())

    def test_risk_contributions_sum(self):
        r = demo_prices().pct_change().dropna()
        c = risk_contributions(r,[.25]*4)
        self.assertAlmostEqual(c['Risk share'].sum(),1.)

    def test_invalid_data_rejected(self):
        p = demo_prices().head(100).rename_axis('date').reset_index()
        p.loc[10,'date'] = p.loc[9,'date']
        with self.assertRaises(ValueError):
            validate_prices(p)
        p = demo_prices().head(100).rename_axis('date').reset_index()
        p.iloc[4,1] = np.nan
        with self.assertRaises(ValueError):
            validate_prices(p)


if __name__ == '__main__':
    unittest.main()
