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
        "LEAPS Call",
        "Long Put",
        "LEAPS Put",
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
    horizon: str = "Swing (2-8 weeks)",
) -> list[dict]:
    ideas: list[dict] = []

    if outlook == "Bullish":
        ideas.append(
            {
                "vehicle": "Stock",
                "strategy": "Buy Stock / ETF",
                "structure": "Buy shares and define an invalidation level.",
                "fit": "Direct bullish exposure without option expiration.",
                "risk": "Full share downside; size with a planned exit.",
            }
        )
        if horizon in {"Intermediate (2-6 months)", "Long term (6+ months)"}:
            ideas.append(
                {
                    "vehicle": "LEAPS",
                    "strategy": "Buy LEAPS Call",
                    "structure": "Buy an in-the-money call with 12+ months to expiration.",
                    "fit": "Capital-efficient long-term bullish exposure.",
                    "risk": "Premium can expire worthless; affected by volatility and time decay.",
                }
            )
        ideas.extend(
            [
                {
                    "vehicle": "Spread",
                    "strategy": "Bull Call Debit Spread",
                    "structure": "Buy a call and sell a higher-strike call.",
                    "fit": "Defined-risk bullish exposure with a capped reward.",
                    "risk": "Maximum loss is the net debit paid.",
                },
                {
                    "vehicle": "Spread",
                    "strategy": "Bull Put Credit Spread",
                    "structure": "Sell a put and buy a lower-strike protective put.",
                    "fit": "Defined-risk premium strategy when the bullish thesis is moderate.",
                    "risk": "Maximum loss is spread width minus credit received.",
                },
            ]
        )
    elif outlook == "Bearish":
        if horizon in {"Intermediate (2-6 months)", "Long term (6+ months)"}:
            ideas.append(
                {
                    "vehicle": "LEAPS",
                    "strategy": "Buy LEAPS Put",
                    "structure": "Buy an in-the-money put with 12+ months to expiration.",
                    "fit": "Capital-efficient long-term bearish exposure.",
                    "risk": "Premium can expire worthless; affected by volatility and time decay.",
                }
            )
        ideas.extend(
            [
                {
                    "vehicle": "Spread",
                    "strategy": "Bear Put Debit Spread",
                    "structure": "Buy a put and sell a lower-strike put.",
                    "fit": "Defined-risk bearish exposure with a capped reward.",
                    "risk": "Maximum loss is the net debit paid.",
                },
                {
                    "vehicle": "Spread",
                    "strategy": "Bear Call Credit Spread",
                    "structure": "Sell a call and buy a higher-strike protective call.",
                    "fit": "Defined-risk premium strategy when the bearish thesis is moderate.",
                    "risk": "Maximum loss is spread width minus credit received.",
                },
            ]
        )
    elif outlook == "Neutral":
        ideas.extend(
            [
                {
                    "vehicle": "Spread",
                    "strategy": "Iron Condor",
                    "structure": "Combine a put credit spread and a call credit spread.",
                    "fit": "Range-based, defined-risk premium strategy.",
                    "risk": "Maximum loss is the wider wing width minus credit received.",
                },
                {
                    "vehicle": "Spread",
                    "strategy": "Butterfly Spread",
                    "structure": "Use three strikes to create a narrow, defined-risk payoff.",
                    "fit": "Targeted neutral thesis with limited risk.",
                    "risk": "Maximum loss is typically the net debit paid.",
                },
            ]
        )
    else:
        ideas.extend(
            [
                {
                    "vehicle": "Options",
                    "strategy": "Long Straddle",
                    "structure": "Buy a call and put at the same strike and expiration.",
                    "fit": "Directional uncertainty with an expectation of a large move.",
                    "risk": "Maximum loss is both premiums paid.",
                },
                {
                    "vehicle": "Options",
                    "strategy": "Long Strangle",
                    "structure": "Buy an out-of-the-money call and put.",
                    "fit": "Lower-cost volatility exposure that requires a larger move.",
                    "risk": "Maximum loss is both premiums paid.",
                },
            ]
        )

    if volatility == "High":
        ideas.append(
            {
                "vehicle": "Spread",
                "strategy": "Defined-Risk Credit Spread",
                "structure": "Sell premium with a protective long option.",
                "fit": "Uses defined risk while evaluating elevated option premium.",
                "risk": "Maximum loss depends on spread width and credit.",
            }
        )
    elif volatility == "Low":
        ideas.append(
            {
                "vehicle": "Spread",
                "strategy": "Calendar Spread",
                "structure": "Sell a near-term option and buy a later-dated option.",
                "fit": "Time-spread structure for studying term and volatility differences.",
                "risk": "Maximum loss is generally the net debit paid.",
            }
        )

    if objective == "Income":
        ideas.append(
            {
                "vehicle": "Stock + Option",
                "strategy": "Covered Call",
                "structure": "Hold shares and sell a call against them.",
                "fit": "Income-oriented overlay that caps some upside.",
                "risk": "Share downside remains; assignment can occur.",
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
    return unique[:6]


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

    if objective == "Income":
        preferred = "Covered Call" if outlook != "Bearish" else "Bear Call Credit Spread"
    elif outlook == "Bullish":
        if horizon == "Long term (6+ months)":
            preferred = "Buy Stock / ETF" if risk_tolerance == "Conservative" else "Buy LEAPS Call"
        elif volatility == "High":
            preferred = "Bull Put Credit Spread"
        else:
            preferred = "Bull Call Debit Spread"
    elif outlook == "Bearish":
        if horizon == "Long term (6+ months)" and risk_tolerance != "Conservative":
            preferred = "Buy LEAPS Put"
        else:
            preferred = "Bear Put Debit Spread"
    elif outlook == "Neutral":
        preferred = "Butterfly Spread" if risk_tolerance == "Conservative" else "Iron Condor"
    else:
        preferred = "Long Straddle" if volatility == "Low" else "Long Strangle"

    primary = next(
        (idea for idea in ideas if idea["strategy"] == preferred),
        ideas[0],
    )
    alternatives = [idea for idea in ideas if idea["strategy"] != primary["strategy"]]
    return primary, alternatives
