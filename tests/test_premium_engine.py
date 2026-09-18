import unittest
from math import inf, log, sqrt
from datetime import date
from modules.premium_engine import analyze, cdf, demo_chain, generate, payoff, valid_contract


def leg(kind, strike, qty):
    return dict(type=kind, strike=strike, qty=qty)


class PayoffTests(unittest.TestCase):
    def test_put_credit_spread_and_probability(self):
        legs = [leg("Put", 100, -1), leg("Put", 95, 1)]
        r = analyze(legs, 1.5, 102, 30/365, .25, fees=1.30)
        self.assertAlmostEqual(r["max_profit"], 148.7)
        self.assertAlmostEqual(r["max_loss"], 351.3)
        self.assertAlmostEqual(r["breakevens"][0], 98.513)
        scale = .25 * sqrt(30/365)
        expected = 1 - cdf((log(98.513/102) + scale**2/2)/scale)
        self.assertAlmostEqual(r["pop"], expected)

    def test_asymmetric_condor(self):
        legs = [leg("Put", 95, -1), leg("Put", 90, 1), leg("Call", 105, -1), leg("Call", 115, 1)]
        r = analyze(legs, 2, 100, .1, .2)
        self.assertEqual(r["max_loss"], 800)
        self.assertEqual(r["max_profit"], 200)
        self.assertEqual(r["breakevens"], [93, 107])

    def test_unlimited_call_and_covered_call(self):
        legs = [leg("Call", 105, -1)]
        naked = analyze(legs, 2, 100, .1, .2)
        covered = analyze(legs, 2, 100, .1, .2, shares=100)
        self.assertEqual(naked["max_loss"], inf)
        self.assertEqual(covered["max_loss"], 9800)
        self.assertEqual(covered["max_profit"], 700)
        self.assertEqual(covered["breakevens"], [98])

    def test_ratio_and_multiple_profit_intervals(self):
        legs = [leg("Call", 100, 1), leg("Call", 105, -2)]
        r = analyze(legs, 1, 100, .1, .2)
        self.assertEqual(r["max_profit"], 600)
        self.assertEqual(r["max_loss"], inf)
        self.assertEqual(r["breakevens"], [111])
        butterfly = [leg("Call", 95, -1), leg("Call", 100, 2), leg("Call", 105, -1)]
        r = analyze(butterfly, 2, 100, .1, .2)
        self.assertEqual(r["breakevens"], [97, 103])
        scale = .2 * sqrt(.1)
        expected = cdf((log(97/100)+scale**2/2)/scale) + 1-cdf((log(103/100)+scale**2/2)/scale)
        self.assertAlmostEqual(r["pop"], expected)

    def test_missing_iv(self):
        self.assertIsNone(analyze([leg("Put", 100, -1)], 2, 100, .1, None)["pop"])

    def test_bad_quotes(self):
        for bid, ask in [(2, 1), (-1, 1), (float("nan"), 1), (0, float("inf"))]:
            self.assertFalse(valid_contract(dict(strike=100, bid=bid, ask=ask)))

    def test_generated_payoff_extrema(self):
        chain = demo_chain(30)
        rows = generate(chain, 500, 30/365, .25)
        self.assertGreater(len(rows), 15)
        for r in rows:
            self.assertTrue(0 <= r["pop"] <= 1)
            for price in [0, 250, 500, 750, 1000, *[l["strike"] for l in r["legs"]]]:
                value = payoff(r["legs"], r["credit"], price, r["shares"], 500, r["fees"])
                self.assertLessEqual(value, r["max_profit"] + 1e-8)
                self.assertGreaterEqual(value, -r["max_loss"] - 1e-8)
            for root in r["breakevens"]:
                self.assertAlmostEqual(payoff(r["legs"], r["credit"], root, r["shares"], 500, r["fees"]), 0)

    def test_expired_chain(self):
        chain = demo_chain(1, as_of=date(2020, 1, 1))
        self.assertEqual(generate(chain, 500, .1, .25), [])

    def test_credit_floor_and_strike_distance(self):
        rows = generate(demo_chain(30), 500, 30/365, .25)
        self.assertTrue(rows)
        for r in rows:
            self.assertGreaterEqual(r["credit"] * 100 - r["fees"], 50)
            for l in r["legs"]:
                if l["qty"] < 0:
                    self.assertLessEqual(abs(l["strike"] - 500), 25)
        self.assertEqual(generate(demo_chain(30), 500, 30/365, .25, min_net_credit=100000), [])

    def test_two_cent_credit_excluded_after_fees(self):
        chain = {"expiration": "2099-01-01", "calls": [], "puts": [
            dict(type="Put", strike=99, bid=.02, ask=.03)]}
        self.assertEqual(generate(chain, 100, .1, .25), [])
        rows = generate(chain, 100, .1, .25, min_net_credit=0)
        self.assertTrue(rows)
        self.assertAlmostEqual(rows[0]["net_credit"], 1.35)

    def test_strikes_do_not_depend_on_manual_volatility(self):
        chain = demo_chain(30)
        signatures = lambda iv: [(r["strategy"], [(l["type"], l["strike"]) for l in r["legs"]])
                                for r in generate(chain, 500, 30/365, iv)]
        self.assertEqual(signatures(.1), signatures(.8))

    def test_sparse_chain_does_not_substitute_distant_strikes(self):
        chain = {"expiration": "2099-01-01", "calls": [], "puts": [
            dict(type="Put", strike=80, bid=1, ask=1.1)]}
        self.assertEqual(generate(chain, 100, .1, .25), [])


if __name__ == "__main__":
    unittest.main()
