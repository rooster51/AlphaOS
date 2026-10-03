import unittest

from modules.long_option_discovery import discover_long_options


CHAIN = {
    "symbol": "QQQ",
    "expiration": "2030-01-18",
    "calls": [
        {"contract":"C748","type":"Call","strike":748,"bid":2.8,"ask":3.0,"mid":2.9,
         "delta":.52,"gamma":.04,"theta":-.3,"vega":.1,"rho":.01,"iv":.22,
         "volume":1000,"open_interest":5000},
        {"contract":"C760","type":"Call","strike":760,"bid":.4,"ask":.5,"open_interest":20},
    ],
    "puts": [
        {"contract":"P746","type":"Put","strike":746,"bid":1.8,"ask":2.0,"mid":1.9,
         "delta":-.42,"gamma":.04,"theta":-.25,"vega":.09,"iv":.23,
         "volume":900,"open_interest":4000},
    ],
}


class LongOptionDiscoveryTests(unittest.TestCase):
    def test_public_chain_contracts_become_unranked_candidates(self):
        r=discover_long_options(CHAIN,748,expected_move=6,as_of="2030-01-17")
        self.assertEqual(r["provider"],"Public")
        self.assertEqual(len(r["candidates"]),3)
        call=next(x for x in r["candidates"] if x["contract"]=="C748")
        self.assertEqual(call["entry_assumption"],"ask")
        self.assertEqual(call["entry_premium"],3)
        self.assertEqual(call["delta"],.52)
        self.assertEqual(call["open_interest"],5000)
        self.assertEqual(call["research"]["capital_at_risk"],300)
        self.assertEqual(call["research"]["breakeven"],751)

    def test_distance_and_capital_filters_are_constraints_not_scores(self):
        r=discover_long_options(CHAIN,748,max_distance_pct=.01,max_premium=2.5,
                                min_open_interest=100)
        self.assertEqual([x["contract"] for x in r["candidates"]],["P746"])
        self.assertIn("not a ranking",r["candidate_order"])

    def test_call_only(self):
        r=discover_long_options(CHAIN,748,option_types=("Call",))
        self.assertTrue(all(x["option_type"]=="call" for x in r["candidates"]))

    def test_missing_greeks_are_allowed(self):
        chain={**CHAIN,"calls":[{"contract":"C749","type":"Call","strike":749,
                                "bid":1,"ask":1.2,"open_interest":200}],"puts":[]}
        r=discover_long_options(chain,748)
        self.assertIsNone(r["candidates"][0]["delta"])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            discover_long_options(CHAIN,0)
        with self.assertRaises(ValueError):
            discover_long_options(CHAIN,748,option_types=("Invalid",))


if __name__=="__main__":
    unittest.main()
