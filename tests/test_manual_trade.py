import unittest
from datetime import date
from math import inf
from modules.manual_trade import build_manual_trade


class ManualTests(unittest.TestCase):
    def trade(self, rows, **kwargs):
        return build_manual_trade('SPY',date(2030,2,1),100,rows,as_of=date(2030,1,1),**kwargs)

    def test_credit_spread(self):
        r=self.trade([{'Action':'Sell','Type':'Put','Contracts':2,'Strike':95,'Entry premium':2},
                      {'Action':'Buy','Type':'Put','Contracts':2,'Strike':90,'Entry premium':1}],fees=2.6)
        self.assertAlmostEqual(r['max_profit'],197.4)
        self.assertAlmostEqual(r['max_loss'],802.6)

    def test_debit_call(self):
        r=self.trade([{'Action':'Buy','Type':'Call','Contracts':1,'Strike':105,'Entry premium':2}])
        self.assertEqual(r['credit'],-2)
        self.assertEqual(r['max_profit'],inf)
        self.assertEqual(r['max_loss'],200)
        self.assertEqual(r['breakevens'],[107])

    def test_stock_cost_basis(self):
        r=self.trade([{'Action':'Sell','Type':'Call','Contracts':1,'Strike':105,'Entry premium':2}],shares=100,stock_basis=90)
        self.assertEqual(r['max_profit'],1700)
        self.assertEqual(r['max_loss'],8800)
        self.assertEqual(r['breakevens'],[88])

    def test_invalid_leg(self):
        for contracts in [0,1.5,float('nan')]:
            with self.assertRaises(ValueError):
                self.trade([{'Action':'Sell','Type':'Put','Contracts':contracts,'Strike':95,'Entry premium':2}])

    def test_same_day_pop(self):
        r=build_manual_trade('SPY',date(2030,1,1),100,[{'Action':'Sell','Type':'Put','Contracts':1,'Strike':95,'Entry premium':2}],as_of=date(2030,1,1))
        self.assertIsNone(r['pop'])
