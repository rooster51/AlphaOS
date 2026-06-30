from __future__ import annotations


STRATEGY_GROUPS = {
    "Stock / ETF": [
        "Momentum",
        "Pullback",
        "Breakout",
        "Mean Reversion",
        "Swing Core",
        "Pairs Trade",
    ],
    "Single Option": [
        "Long Call",
        "Long Put",
        "Covered Call",
        "Cash-Secured Put",
    ],
    "Option Spread": [
        "Bull Call Debit Spread",
        "Bear Put Debit Spread",
        "Bull Put Credit Spread",
        "Bear Call Credit Spread",
        "Calendar Spread",
        "Diagonal Spread",
        "Iron Condor",
        "Butterfly Spread",
        "Long Straddle",
        "Long Strangle",
    ],
}


def strategies_for_instrument(instrument_type: str) -> list[str]:
    if instrument_type in {"Stock", "ETF"}:
        return STRATEGY_GROUPS["Stock / ETF"]
    if instrument_type == "Option":
        return STRATEGY_GROUPS["Single Option"]
    return STRATEGY_GROUPS["Option Spread"]


def strategy_ideas(
    outlook: str,
    volatility: str,
    risk_tolerance: str,
    objective: str,
) -> list[dict]:
    ideas: list[dict] = []

    if outlook == "Bullish":
        ideas.extend(
            [
                {
                    "strategy": "Bull Call Debit Spread",
                    "structure": "Buy a call and sell a higher-strike call.",
                    "fit": "Defined-risk bullish exposure with a capped reward.",
                },
                {
                    "strategy": "Bull Put Credit Spread",
                    "structure": "Sell a put and buy a lower-strike protective put.",
                    "fit": "Defined-risk premium strategy when the bullish thesis is moderate.",
                },
            ]
        )
    elif outlook == "Bearish":
        ideas.extend(
            [
                {
                    "strategy": "Bear Put Debit Spread",
                    "structure": "Buy a put and sell a lower-strike put.",
                    "fit": "Defined-risk bearish exposure with a capped reward.",
                },
                {
                    "strategy": "Bear Call Credit Spread",
                    "structure": "Sell a call and buy a higher-strike protective call.",
                    "fit": "Defined-risk premium strategy when the bearish thesis is moderate.",
                },
            ]
        )
    elif outlook == "Neutral":
        ideas.extend(
            [
                {
                    "strategy": "Iron Condor",
                    "structure": "Combine a put credit spread and a call credit spread.",
                    "fit": "Range-based, defined-risk premium strategy.",
                },
                {
                    "strategy": "Butterfly Spread",
                    "structure": "Use three strikes to create a narrow, defined-risk payoff.",
                    "fit": "Targeted neutral thesis with limited risk.",
                },
            ]
        )
    else:
        ideas.extend(
            [
                {
                    "strategy": "Long Straddle",
                    "structure": "Buy a call and put at the same strike and expiration.",
                    "fit": "Directional uncertainty with an expectation of a large move.",
                },
                {
                    "strategy": "Long Strangle",
                    "structure": "Buy an out-of-the-money call and put.",
                    "fit": "Lower-cost volatility exposure that requires a larger move.",
                },
            ]
        )

    if volatility == "High":
        ideas.append(
            {
                "strategy": "Defined-Risk Credit Spread",
                "structure": "Sell premium with a protective long option.",
                "fit": "Uses defined risk while evaluating elevated option premium.",
            }
        )
    elif volatility == "Low":
        ideas.append(
            {
                "strategy": "Calendar Spread",
                "structure": "Sell a near-term option and buy a later-dated option.",
                "fit": "Time-spread structure for studying term and volatility differences.",
            }
        )

    if objective == "Income":
        ideas.append(
            {
                "strategy": "Covered Call",
                "structure": "Hold shares and sell a call against them.",
                "fit": "Income-oriented overlay that caps some upside.",
            }
        )

    if risk_tolerance == "Conservative":
        ideas = [
            idea
            for idea in ideas
            if idea["strategy"]
            not in {"Long Straddle", "Long Strangle", "Defined-Risk Credit Spread"}
        ]

    seen = set()
    unique = []
    for idea in ideas:
        if idea["strategy"] not in seen:
            seen.add(idea["strategy"])
            unique.append(idea)
    return unique[:4]
