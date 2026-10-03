"""Research helpers for outright long calls and puts.

Deterministic contract economics only. This module does not rank contracts,
place orders, or treat a modeled probability as a backtested win rate.
"""
from __future__ import annotations

from datetime import date
from math import isfinite

from modules.options_payoff import trade_analysis


def long_option_trade(symbol, expiration, option_type, strike, premium, spot,
                      contracts=1, fees=0, source="Explicit long option"):
    symbol = str(symbol).strip().upper()
    kind = str(option_type).strip().title()
    if kind not in ("Call", "Put"):
        raise ValueError("Long option type must be Call or Put.")
    try:
        strike, premium, spot, contracts, fees = map(
            float, (strike, premium, spot, contracts, fees)
        )
    except (TypeError, ValueError):
        raise ValueError("Long option inputs must be numeric.") from None
    if (not all(isfinite(x) for x in (strike, premium, spot, contracts, fees))
            or strike <= 0 or premium < 0 or spot <= 0 or contracts <= 0
            or contracts != int(contracts) or fees < 0):
        raise ValueError("Use positive spot/strike, nonnegative premium/fees, and whole contracts.")
    expiration = str(expiration)
    try:
        date.fromisoformat(expiration[:10])
    except ValueError:
        raise ValueError("Expiration must be an ISO date.") from None
    return dict(
        symbol=symbol,
        strategy=f"Long {kind.lower()}",
        strategy_family="long_call" if kind == "Call" else "long_put",
        expiration=expiration[:10],
        spot=spot,
        credit=-premium * contracts,
        shares=0,
        fees=fees,
        source=source,
        legs=[dict(type=kind, strike=strike, qty=int(contracts))],
    )


def research_long_option(symbol, expiration, option_type, strike, premium, spot,
                         contracts=1, fees=0, expected_move=None,
                         structural_level=None, as_of=None, source="Explicit long option"):
    """Return normalized economics and move requirements for an outright option.

    expected_move is an optional dollar move for the underlying over the user's
    chosen horizon. It is contextual evidence, not a profitability probability.
    """
    trade = long_option_trade(
        symbol, expiration, option_type, strike, premium, spot,
        contracts=contracts, fees=fees, source=source,
    )
    analysis = trade_analysis(trade)
    kind = trade["legs"][0]["type"]
    breakeven = analysis["breakevens"][0]
    required_move = breakeven - spot
    required_move_pct = required_move / spot
    em = None
    if expected_move is not None:
        expected_move = float(expected_move)
        if not isfinite(expected_move) or expected_move < 0:
            raise ValueError("Expected move must be a nonnegative dollar amount.")
        em = dict(
            expected_move=expected_move,
            expected_move_pct=expected_move / spot,
            required_move_to_expected_move=(
                abs(required_move) / expected_move if expected_move > 0 else None
            ),
            breakeven_outside_expected_move=abs(required_move) > expected_move,
        )
    structure = None
    if structural_level is not None:
        structural_level = float(structural_level)
        if not isfinite(structural_level) or structural_level <= 0:
            raise ValueError("Structural level must be a positive price.")
        structure = dict(
            level=structural_level,
            distance_from_spot=structural_level - spot,
            distance_from_spot_pct=structural_level / spot - 1,
            distance_from_breakeven=structural_level - breakeven,
        )
    dte = None
    if as_of is not None:
        start = date.fromisoformat(str(as_of)[:10])
        expiry = date.fromisoformat(trade["expiration"])
        dte = (expiry - start).days
        if dte < 0:
            raise ValueError("Expiration precedes the research date.")
    return dict(
        version="long-option-v1",
        trade=trade,
        option_type=kind.lower(),
        contracts=int(contracts),
        premium_per_share=float(premium),
        capital_at_risk=analysis["max_loss"],
        max_profit=analysis["max_profit"],
        breakeven=breakeven,
        required_move=required_move,
        required_move_pct=required_move_pct,
        distance_to_strike=float(strike) - spot,
        distance_to_strike_pct=float(strike) / spot - 1,
        dte=dte,
        expected_move_context=em,
        structure_context=structure,
        payoff=analysis,
        caveats=[
            "Expiration payoff economics are deterministic; they are not a forecast.",
            "Expected-move context does not imply probability of profit.",
            "Greeks, implied volatility, liquidity, and executable quotes require contract-market data.",
        ],
    )
