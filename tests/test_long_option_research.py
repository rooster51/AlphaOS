import unittest
from math import inf

from modules.long_option_research import long_option_trade, research_long_option


class LongOptionResearchTests(unittest.TestCase):
    def test_long_call(self):
        r=research_long_option("QQQ","2030-01-18","call",750,2,748,
                               expected_move=6,as_of="2030-01-17")
        self.assertEqual(r["trade"]["strategy_family"],"long_call")
        self.assertEqual(r["capital_at_risk"],200)
        self.assertEqual(r["max_profit"],inf)
        self.assertEqual(r["breakeven"],752)
        self.assertAlmostEqual(r["required_move_pct"],4/748)
        self.assertFalse(r["expected_move_context"]["breakeven_outside_expected_move"])
        self.assertEqual(r["dte"],1)

    def test_long_put(self):
        r=research_long_option("QQQ","2030-01-18","put",745,1.5,748,
                               expected_move=3,as_of="2030-01-17")
        self.assertEqual(r["trade"]["strategy_family"],"long_put")
        self.assertEqual(r["capital_at_risk"],150)
        self.assertEqual(r["breakeven"],743.5)
        self.assertAlmostEqual(r["required_move"],-4.5)
        self.assertTrue(r["expected_move_context"]["breakeven_outside_expected_move"])

    def test_contract_scaling_and_fees(self):
        r=research_long_option("SPY","2030-02-01","call",600,1.25,598,
                               contracts=2,fees=2)
        self.assertEqual(r["capital_at_risk"],252)
        self.assertEqual(r["breakeven"],601.26)

    def test_structure_context(self):
        r=research_long_option("SPY","2030-02-01","put",590,2,595,
                               structural_level=588)
        self.assertEqual(r["structure_context"]["level"],588)
        self.assertEqual(r["structure_context"]["distance_from_breakeven"],0)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            long_option_trade("QQQ","2030-01-18","invalid",750,2,748)
        with self.assertRaises(ValueError):
            research_long_option("QQQ","2030-01-18","call",750,2,748,expected_move=-1)


if __name__=="__main__":
    unittest.main()
