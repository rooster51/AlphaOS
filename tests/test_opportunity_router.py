import unittest

from modules.opportunity_router import opportunity_state, route_strategies


class OpportunityRouterTests(unittest.TestCase):
    def test_bullish_rich_routes_overlap_without_ranking(self):
        state=opportunity_state(direction="bullish",premium_state="rich",
                                volatility_state="elevated",
                                evidence={"direction":"completed-session trend"})
        result=route_strategies(state)
        self.assertEqual(result["routes"][:3],
                         ["put_credit_spread","bullish_bwb","call_debit_spread"])
        self.assertIn("credit_structure",result["routes"])
        self.assertIn("not a ranking",result["route_order"])
        self.assertFalse(result["no_trade_or_insufficient_evidence"])

    def test_bullish_cheap_can_route_long_call(self):
        result=route_strategies(opportunity_state(direction="bullish",
                                                   premium_state="cheap"))
        self.assertIn("long_call",result["routes"])
        self.assertIn("bullish_diagonal",result["routes"])

    def test_unknown_premium_does_not_trigger_long_premium_or_credit(self):
        result=route_strategies(opportunity_state(direction="bullish"))
        self.assertEqual(result["routes"],["call_debit_spread"])
        self.assertNotIn("long_call",result["routes"])
        self.assertNotIn("put_credit_spread",result["routes"])

    def test_all_unknown_can_return_no_route(self):
        state=opportunity_state(time_state="standard")
        result=route_strategies(state)
        self.assertTrue(result["no_trade_or_insufficient_evidence"])
        self.assertEqual(result["routes"],[])
        self.assertIn("premium_state",state["evidence_sufficiency"]["unknown_dimensions"])

    def test_range_pin_large_move_and_late_zero_dte_are_independent_dimensions(self):
        range_result=route_strategies(opportunity_state(movement_state="range_bound"))
        self.assertIn("iron_condor",range_result["routes"])
        pin_result=route_strategies(opportunity_state(movement_state="pin_candidate"))
        self.assertEqual(pin_result["routes"],["butterfly","bwb"])
        move_result=route_strategies(opportunity_state(movement_state="large_move_expected"))
        self.assertIn("long_straddle",move_result["routes"])
        late=route_strategies(opportunity_state(time_state="late_0dte"))
        self.assertEqual(late["routes"],["vertical","iron_condor","butterfly","bwb"])

    def test_invalid_dimension_fails_closed(self):
        with self.assertRaises(ValueError):
            opportunity_state(premium_state="probably_cheap")
        state=opportunity_state()
        state["direction"]="up-ish"
        with self.assertRaises(ValueError):
            route_strategies(state)


if __name__=="__main__":
    unittest.main()
