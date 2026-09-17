"""Same-expiration, standard 100-share option income research.

Exact piecewise-linear expiration payoffs; lognormal model probability, not a
backtested win rate. No brokerage order submission is performed here.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import erf, exp, inf, isfinite, log, sqrt


CATALOG = {
    "Bull put spread": ("Bullish", "Defined", "Sell a put and buy a lower-strike put."),
    "Bear call spread": ("Bearish", "Defined", "Sell a call and buy a higher-strike call."),
    "Iron condor": ("Neutral", "Defined", "Combine out-of-the-money put and call credit spreads."),
    "Iron butterfly": ("Neutral", "Defined", "Sell an ATM straddle; buy protective wings."),
    "Cash-secured put": ("Bullish", "Stock-backed", "Reserve strike × 100 cash for potential assignment."),
    "Covered call": ("Bullish", "Stock-backed", "Buy 100 shares at the displayed spot and sell one call."),
    "Covered strangle": ("Bullish", "Stock-backed", "Buy 100 shares, sell a covered call and a cash-secured put."),
    "Short put": ("Bullish", "Uncovered", "Sell one put; downside extends to a worthless underlying."),
    "Short call": ("Bearish", "Uncovered", "Sell one uncovered call; upside losses are unlimited."),
    "Short strangle": ("Neutral", "Uncovered", "Sell an OTM put and call; upside losses are unlimited."),
    "Short straddle": ("Neutral", "Uncovered", "Sell an ATM put and call; upside losses are unlimited."),
    "Put ratio spread": ("Bullish", "Uncovered", "Buy one higher put and sell two lower puts for a credit."),
    "Call ratio spread": ("Bearish", "Uncovered", "Buy one lower call and sell two higher calls for a credit."),
    "Put broken-wing butterfly": ("Bullish", "Defined", "Buy outer puts and sell two middle puts, with a wider lower wing."),
    "Call broken-wing butterfly": ("Bearish", "Defined", "Buy outer calls and sell two middle calls, with a wider upper wing."),
}


def cdf(z):
    return (1 + erf(z / sqrt(2))) / 2


def payoff(legs, credit, price, shares=0, spot=0, fees=0):
    return credit * 100 - fees + shares * (price - spot) + sum(
        leg["qty"] * 100 * max(0, price - leg["strike"] if leg["type"] == "Call" else leg["strike"] - price)
        for leg in legs
    )


def analyze(legs, credit, spot, years, iv, shares=0, fees=0):
    """Find extrema/roots at every payoff kink, including the infinite tail."""
    knots = sorted({0.0, *[float(x["strike"]) for x in legs]})
    values = [payoff(legs, credit, x, shares, spot, fees) for x in knots]
    slope = shares + 100 * sum(x["qty"] for x in legs if x["type"] == "Call")
    max_profit = inf if slope > 0 else max(values)
    max_loss = inf if slope < 0 else max(0, -min(values))
    roots = []
    for a, b, ya, yb in zip(knots, knots[1:], values, values[1:]):
        if ya == 0:
            roots.append(a)
        if ya * yb < 0:
            roots.append(a - ya * (b - a) / (yb - ya))
    if values[-1] == 0:
        roots.append(knots[-1])
    if slope and values[-1] * slope < 0:
        roots.append(knots[-1] - values[-1] / slope)
    roots = sorted(set(roots))
    pop = None
    if iv is not None and isfinite(iv) and iv > 0 and years > 0:
        # Zero price drift; constant user-selected annualized volatility.
        scale = iv * sqrt(years)
        def terminal_cdf(x):
            if x <= 0:
                return 0.0
            if x == inf:
                return 1.0
            return cdf((log(x / spot) + 0.5 * scale * scale) / scale)
        boundaries = sorted(set([0.0, *knots, *roots, inf]))
        pop = 0.0
        for a, b in zip(boundaries, boundaries[1:]):
            probe = (a + b) / 2 if b != inf else a + max(spot, 1)
            if payoff(legs, credit, probe, shares, spot, fees) > 0:
                pop += terminal_cdf(b) - terminal_cdf(a)
        pop = min(1.0, max(0.0, pop))
    return dict(max_profit=max_profit, max_loss=max_loss, breakevens=roots, pop=pop,
                risk_reward=max_loss / max_profit if max_profit > 0 else inf)


def valid_contract(c):
    try:
        k, bid, ask = (float(c[x]) for x in ("strike", "bid", "ask"))
        return all(isfinite(x) for x in (k, bid, ask)) and k > 0 and 0 <= bid <= ask and ask > 0
    except (KeyError, TypeError, ValueError):
        return False


def generate(chain, spot, years, iv, width=5, fee=0.65, pricing="Natural", as_of=None):
    as_of = as_of or date.today()
    if not isfinite(spot) or spot <= 0 or width <= 0 or years <= 0:
        return []
    if date.fromisoformat(chain["expiration"][:10]) < as_of:
        return []
    pools = {kind: sorted([c for c in chain.get(key, []) if valid_contract(c)], key=lambda c: c["strike"])
             for kind, key in [("Put", "puts"), ("Call", "calls")]}
    def pick(kind, target, side=None, anchor=None):
        rows = pools[kind]
        if side:
            rows = [c for c in rows if (c["strike"] < anchor if side == "below" else c["strike"] > anchor)]
        return min(rows, key=lambda c: abs(c["strike"] - target)) if rows else None
    def leg(c, qty):
        return {**c, "qty": qty} if c else None
    results = []
    def add(name, legs, shares=0):
        if any(x is None for x in legs):
            return
        if len({(x["type"], x["strike"]) for x in legs}) != len(legs):
            return
        credit = -sum(x["qty"] * ((x["bid"] + x["ask"]) / 2 if pricing == "Midpoint" else (x["ask"] if x["qty"] > 0 else x["bid"])) for x in legs)
        fees = fee * sum(abs(x["qty"]) for x in legs)
        if credit * 100 <= fees:
            return
        stats = analyze(legs, credit, spot, years, iv, shares, fees)
        if stats["max_profit"] <= 0 or stats["max_loss"] <= 0:
            return
        # Reject impossible bounded payoff arbitrages / malformed quotes.
        if CATALOG[name][1] == "Defined" and not isfinite(stats["max_loss"]):
            return
        results.append(dict(strategy=name, legs=legs, credit=credit, shares=shares,
                            fees=fees, spot=spot, expiration=chain["expiration"], **stats))
    for offset in (0.5, 1.0, 1.5):
        distance = spot * (iv or 0.25) * sqrt(years) * offset
        p, c = pick("Put", spot - distance, "below", spot), pick("Call", spot + distance, "above", spot)
        pl = pick("Put", p["strike"] - width, "below", p["strike"]) if p else None
        cl = pick("Call", c["strike"] + width, "above", c["strike"]) if c else None
        add("Bull put spread", [leg(p, -1), leg(pl, 1)])
        add("Bear call spread", [leg(c, -1), leg(cl, 1)])
        add("Iron condor", [leg(p, -1), leg(pl, 1), leg(c, -1), leg(cl, 1)])
        for name in ("Cash-secured put", "Short put"):
            add(name, [leg(p, -1)])
        add("Covered call", [leg(c, -1)], 100)
        add("Covered strangle", [leg(p, -1), leg(c, -1)], 100)
        add("Short call", [leg(c, -1)])
        add("Short strangle", [leg(p, -1), leg(c, -1)])
        for kind, short in [("Put", p), ("Call", c)]:
            if short:
                lower = kind == "Put"
                inner = pick(kind, short["strike"] + (width if lower else -width), "above" if lower else "below", short["strike"])
                outer = pick(kind, short["strike"] + (-2 * width if lower else 2 * width), "below" if lower else "above", short["strike"])
                add(f"{kind} ratio spread", [leg(inner, 1), leg(short, -2)])
                if inner and outer and abs(outer["strike"] - short["strike"]) > abs(inner["strike"] - short["strike"]):
                    add(f"{kind} broken-wing butterfly", [leg(inner, 1), leg(short, -2), leg(outer, 1)])
    common = sorted(set(c["strike"] for c in pools["Put"]) & set(c["strike"] for c in pools["Call"]))
    if common:
        atm = min(common, key=lambda k: abs(k - spot))
        p, c = pick("Put", atm), pick("Call", atm)
        add("Short straddle", [leg(p, -1), leg(c, -1)])
        add("Iron butterfly", [leg(p, -1), leg(c, -1), leg(pick("Put", atm - width, "below", atm), 1), leg(pick("Call", atm + width, "above", atm), 1)])
    unique = {}
    for row in results:
        signature = (row["strategy"], tuple((x["type"], x["strike"], x["qty"]) for x in row["legs"]))
        unique[signature] = row
    return list(unique.values())


def demo_chain(days, spot=500, iv=0.25, as_of=None):
    """Synthetic Black-Scholes quotes, deliberately separate from live data."""
    as_of = as_of or date.today()
    t = max(days, 0.25) / 365
    result = {"expiration": (as_of + timedelta(days=days)).isoformat(), "calls": [], "puts": []}
    for strike in range(int(spot * 0.65), int(spot * 1.35) + 1, 5):
        d1 = (log(spot / strike) + iv * iv * t / 2) / (iv * sqrt(t))
        d2 = d1 - iv * sqrt(t)
        for kind, key in [("Call", "calls"), ("Put", "puts")]:
            value = spot * cdf(d1) - strike * cdf(d2) if kind == "Call" else strike * cdf(-d2) - spot * cdf(-d1)
            result[key].append(dict(type=kind, strike=float(strike), bid=round(max(0, value - 0.04), 2),
                                    ask=round(max(0.01, value + 0.04), 2), iv=iv,
                                    contract=f"DEMO-{days}-{kind}-{strike}"))
    return result
