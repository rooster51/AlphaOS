from __future__ import annotations


ALLOWED_DAILY_STRATEGIES = (
    "Call Debit Spread",
    "Put Debit Spread",
    "Bull Put Credit Spread",
    "Bear Call Credit Spread",
)

STRATEGY_GROUPS = {
    "Option Spread": list(ALLOWED_DAILY_STRATEGIES),
}


def strategies_for_instrument(instrument_type: str) -> list[str]:
    return STRATEGY_GROUPS["Option Spread"]


def _call_debit_spread() -> dict:
    return {
        "vehicle": "Daily Debit Spread",
        "strategy": "Call Debit Spread",
        "structure": "Buy a near-the-money call and sell a higher-strike call in the same expiration.",
        "fit": "Bullish daily setup with defined debit risk and capped upside.",
        "risk": "Maximum loss is the net debit paid.",
    }


def _put_debit_spread() -> dict:
    return {
        "vehicle": "Daily Debit Spread",
        "strategy": "Put Debit Spread",
        "structure": "Buy a near-the-money put and sell a lower-strike put in the same expiration.",
        "fit": "Bearish daily setup with defined debit risk and capped upside.",
        "risk": "Maximum loss is the net debit paid.",
    }


def _bull_put_credit_spread() -> dict:
    return {
        "vehicle": "Daily Credit Spread",
        "strategy": "Bull Put Credit Spread",
        "structure": "Sell an out-of-the-money put and buy a lower-strike protective put in the same expiration.",
        "fit": "Bullish daily setup where price is expected to stay above the short put.",
        "risk": "Maximum loss is spread width minus credit received.",
    }


def _bear_call_credit_spread() -> dict:
    return {
        "vehicle": "Daily Credit Spread",
        "strategy": "Bear Call Credit Spread",
        "structure": "Sell an out-of-the-money call and buy a higher-strike protective call in the same expiration.",
        "fit": "Bearish daily setup where price is expected to stay below the short call.",
        "risk": "Maximum loss is spread width minus credit received.",
    }


def strategy_ideas(
    outlook: str,
    volatility: str,
    risk_tolerance: str,
    objective: str,
    horizon: str = "Day trade (same day)",
) -> list[dict]:
    if outlook == "Bullish":
        return [_call_debit_spread(), _bull_put_credit_spread()]
    if outlook == "Bearish":
        return [_put_debit_spread(), _bear_call_credit_spread()]
    return [
        {
            "vehicle": "No Trade",
            "strategy": "No Trade",
            "structure": "Wait for a bullish or bearish daily trend before selecting a spread.",
            "fit": "Neutral or choppy tape does not fit the two-strategy daily spread plan.",
            "risk": "No new trade recommended.",
        }
    ]


def primary_strategy_idea(
    outlook: str,
    volatility: str,
    risk_tolerance: str,
    objective: str,
    horizon: str,
) -> tuple[dict, list[dict]]:
    ideas = strategy_ideas(
        outlook,
        volatility,
        risk_tolerance,
        objective,
        horizon,
    )
    return ideas[0], []
