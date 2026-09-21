import unittest
from math import inf

from modules.options_payoff import trade_analysis, validate_trade
from modules.premium_engine import payoff


def trade(legs, credit, spot=769, **kwargs):
    return dict(legs=[dict(type=k,strike=s,qty=q) for k,s,q in legs],
                credit=credit,spot=spot,shares=0,fees=0,**kwargs)


class OptionsPayoffTests(unittest.TestCase):
    def check_position(self, position, profit, loss, roots):
        result = trade_analysis(position)
        self.assertAlmostEqual(result['max_profit'],profit)
        self.assertAlmostEqual(result['max_loss'],loss)
        self.assertEqual(len(result['breakevens']),len(roots))
        for actual, expected in zip(result['breakevens'],roots):
            self.assertAlmostEqual(actual,expected)
        prices = [r['Terminal underlying ($)'] for r in result['grid']]
        for point in [position['spot'], *result['strikes'], *result['breakevens']]:
            self.assertIn(point,prices)
        self.assertEqual(prices, sorted(set(prices)))
        self.assertLessEqual(len(prices),401+2*(1+len(result['strikes'])+len(roots)))
        for row in result['grid']+result['extremes']:
            actual = row['Expiration P&L ($)']
            expected = payoff(position['legs'],position['credit'],row['Terminal underlying ($)'],
                              position['shares'],position.get('stock_basis',position['spot']),position['fees'])
            self.assertAlmostEqual(actual,expected)
            self.assertLessEqual(actual,profit+1e-7)
            self.assertGreaterEqual(actual,-loss-1e-7)
        return result

    def test_one_dollar_put_credit(self):
        r=self.check_position(trade([('Put',768,-1),('Put',767,1)],.18),18,82,[767.82])
        self.assertAlmostEqual(r['return_on_risk'],18/82)
        self.assertEqual(r['width'],1)
        self.assertAlmostEqual(r['credit_width'],.18)

    def test_one_dollar_call_credit(self):
        self.check_position(trade([('Call',770,-1),('Call',771,1)],.18),18,82,[770.18])

    def test_condor_multiple_breakevens(self):
        r=self.check_position(trade([('Put',767,1),('Put',768,-1),('Call',770,-1),('Call',771,1)],.4),40,60,[767.6,770.4])
        self.assertIsNone(r['width'])
        self.assertIsNone(r['credit_width'])

    def test_symmetric_butterfly(self):
        self.check_position(trade([('Call',768,1),('Call',769,-2),('Call',770,1)],-.4),60,40,[768.4,769.6])

    def test_broken_wing_butterfly(self):
        self.check_position(trade([('Put',766,1),('Put',768,-2),('Put',769,1)],.2),120,80,[766.8])

    def test_debit_spread(self):
        r=self.check_position(trade([('Call',768,1),('Call',769,-1)],-.4),60,40,[768.4])
        self.assertEqual(r['net_cash'],-40)
        self.assertIsNone(r['credit_width'])

    def test_spot_at_strike_has_both_labels(self):
        r=trade_analysis(trade([('Put',769,-1),('Put',768,1)],.18))
        rows=[p for p in r['grid'] if p['Terminal underlying ($)']==769]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['Landmark'],'Spot · Strike')

    def test_very_narrow_spacing(self):
        r=self.check_position(trade([('Call',769.01,-1),('Call',769.02,1)],.003),.3,.7,[769.013])
        self.assertGreaterEqual(sum(769.01 < p['Terminal underlying ($)'] < 769.02 for p in r['grid']),3)

    def test_unlimited_loss_and_profit(self):
        short=self.check_position(trade([('Call',770,-1)],2),200,inf,[772])
        long=self.check_position(trade([('Call',770,1)],-2),inf,200,[772])
        self.assertIsNone(short['return_on_risk'])
        self.assertIsNone(long['return_on_risk'])
        self.assertTrue(all(r['Return on max risk (%)'] is None for r in short['grid']))

    def test_stock_basis_fees_and_scaling(self):
        t=trade([('Call',105,-1)],2,spot=100)
        t.update(shares=100,stock_basis=90,fees=1)
        r=self.check_position(t,1699,8801,[88.01])
        scaled=trade_analysis(t,3)
        self.assertEqual(scaled['max_profit'],5097)
        self.assertEqual(scaled['net_cash'],597)
        self.assertEqual(scaled['breakevens'],r['breakevens'])
        self.assertIsNone(scaled['width'])
        for a,b in zip(r['grid'],scaled['grid']):
            self.assertAlmostEqual(3*a['Expiration P&L ($)'],b['Expiration P&L ($)'])

    def test_quantity_normalized_width(self):
        t=trade([('Put',768,-2),('Put',767,2)],.36)
        t['fees']=2.6
        r=trade_analysis(t,2)
        self.assertAlmostEqual(r['credit_width'],.18)
        self.assertAlmostEqual(r['max_profit'],66.8)

    def test_wide_grid_is_bounded(self):
        r=trade_analysis(trade([('Call',1,-1),('Call',1000000,1)],.5,spot=500))
        self.assertLess(len(r['grid']),420)

    def test_zero_risk_denominator(self):
        r=trade_analysis(trade([('Call',770,1),('Call',770,-1)],0))
        self.assertEqual(r['max_loss'],0)
        self.assertIsNone(r['return_on_risk'])

    def test_invalid_inputs(self):
        good=trade([('Put',768,-1),('Put',767,1)],.18)
        for change in ({'spot':0},{'spot':float('nan')},{'fees':-1},{'legs':[]},{'credit':None},
                       {'legs':[dict(type='Invalid',strike=100,qty=1)]},
                       {'legs':[dict(type='Put',strike=100,qty=.5)]}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_trade({**good,**change})
        with self.assertRaises(ValueError):
            trade_analysis({})


if __name__=='__main__':
    unittest.main()
