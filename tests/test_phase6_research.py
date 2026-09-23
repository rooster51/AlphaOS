import unittest
import numpy as np
import pandas as pd

from modules.price_structure import price_structure, nearest_levels
from modules.forward_distribution import summarize_forward_distribution
from modules.level_behavior import level_behavior


class Phase6ResearchTests(unittest.TestCase):
    def history(self):
        n=140; dates=pd.bdate_range('2026-01-01',periods=n)
        base=100+np.linspace(0,15,n)+2*np.sin(np.arange(n)/5)
        return pd.DataFrame({'date':dates,'symbol':'SPY','open':base-.2,'high':base+1,'low':base-1,'close':base})

    def analogs(self):
        returns=np.array([.02,.01,0,-.01,-.02])
        result={'analogs':pd.DataFrame({'date':pd.bdate_range('2025-01-01',periods=5),
            'future_return_3s':returns,'future_high_excursion_3s':[.03,.02,.01,.005,.002],
            'future_low_excursion_3s':[-.002,-.005,-.01,-.02,-.03]})}
        result['analogs']['symbol']='SPY'
        result['analogs']['close']=100.
        result['session_dates']=pd.bdate_range('2025-01-01',periods=20)
        result['target']={'date':result['session_dates'][-1],'symbol':'SPY','close':100.}
        return result

    def test_price_structure_returns_both_sides(self):
        r=price_structure(self.history(),lookback=120)
        self.assertEqual(r['config']['symbol'],'SPY')
        self.assertGreater(r['atr'],0)
        levels=nearest_levels(r,3)
        self.assertTrue(set(levels.side).issubset({'support','resistance'}))
        if not levels.empty:
            self.assertTrue((levels[levels.side=='support'].level < r['spot']).all())
            self.assertTrue((levels[levels.side=='resistance'].level > r['spot']).all())

    def test_forward_distribution_is_anchored_to_current_spot(self):
        r=summarize_forward_distribution(self.analogs(),3,200.)
        self.assertEqual(r['n'],5)
        self.assertAlmostEqual(r['summary']['terminal_spot']['p50'],200.)
        self.assertAlmostEqual(r['summary']['upside_spot']['p50'],202.)
        self.assertAlmostEqual(r['summary']['downside_spot']['p50'],198.)

    def test_resistance_behavior(self):
        r=level_behavior(self.analogs(),horizon=3,anchor_spot=100.,level=101.,side='resistance')
        s=r['summary']
        self.assertEqual(s['n'],5)
        self.assertAlmostEqual(s['touch_frequency'],.6)
        self.assertAlmostEqual(s['terminal_beyond_frequency'],.2)
        self.assertAlmostEqual(s['terminal_equal_frequency'],.2)
        self.assertAlmostEqual(s['rejection_given_touch'],1/3)
        self.assertAlmostEqual(s['break_hold_given_touch'],1/3)

    def test_support_behavior(self):
        s=level_behavior(self.analogs(),horizon=3,anchor_spot=100.,level=99.,side='support')['summary']
        self.assertAlmostEqual(s['touch_frequency'],.6)
        self.assertAlmostEqual(s['terminal_beyond_frequency'],.2)
        self.assertAlmostEqual(s['terminal_equal_frequency'],.2)
        self.assertAlmostEqual(s['rejection_given_touch'],1/3)
        self.assertAlmostEqual(s['break_hold_given_touch'],1/3)

    def test_exact_and_near_boundaries(self):
        for side,sign in [('support',-1),('resistance',1)]:
            for offset,equal,beyond in [(0,True,False),(1e-14,True,False),(1e-8,False,True),(-1e-8,False,False)]:
                a=self.analogs()
                a['analogs']=a['analogs'].iloc[:1].copy()
                a['analogs']['future_return_3s']=sign*(.01+offset)
                a['analogs']['future_high_excursion_3s']=.02
                a['analogs']['future_low_excursion_3s']=-.02
                row=level_behavior(a,horizon=3,anchor_spot=100,level=100+sign,side=side)['observations'].iloc[0]
                self.assertEqual(bool(row.terminal_equal),equal)
                self.assertEqual(bool(row.terminal_beyond),beyond)
                self.assertTrue(row.touched)

    def test_validation(self):
        with self.assertRaises(ValueError): summarize_forward_distribution(self.analogs(),4,100)
        with self.assertRaises(ValueError): level_behavior(self.analogs(),horizon=3,anchor_spot=100,level=101,side='other')


if __name__=='__main__': unittest.main()
