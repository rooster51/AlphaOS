from __future__ import annotations

from datetime import date, datetime

from modules.options_income import build_income_spread


ALLOWED_RECOMMENDED_STRATEGIES = (
    "Call Debit Spread",
    "Put Debit Spread",
    "Bull Put Credit Spread",
    "Bear Call Credit Spread",
)


STRATEGY_CATALOG = {
    "Call Debit Spread": {
        "category": "Debit Spread",
        "best_for": ["Account Growth"],
        "risk": "Defined risk",
        "status": "Priced when chain supports it",
        "makes_money": "Pays a debit and profits when the underlying rises toward or above the short call.",
        "best_when": "Bullish trend alignment, clean breakout, or pullback bounce with defined invalidation.",
        "avoid_when": "Choppy tape, weak momentum, or when the expected move is smaller than the debit paid.",
    },
    "Put Debit Spread": {
        "category": "Debit Spread",
        "best_for": ["Account Growth", "Hedging"],
        "risk": "Defined risk",
        "status": "Priced when chain supports it",
        "makes_money": "Pays a debit and profits when the underlying falls toward or below the short put.",
        "best_when": "Bearish trend alignment, breakdown, or hedge against downside pressure.",
        "avoid_when": "Bullish trend, failed breakdown, or low expected movement.",
    },
    "Bull Put Credit Spread": {
        "category": "Credit Spread",
        "best_for": ["Income", "Account Growth"],
        "risk": "Defined risk",
        "status": "Priced when chain supports it",
        "makes_money": "Collects a credit and profits if price stays above the short put through exit or expiration.",
        "best_when": "Bullish trend, support hold, or pullback bounce where premium is worth the defined risk.",
        "avoid_when": "Price is breaking down, support is failing, or the credit is too small versus width.",
    },
    "Bear Call Credit Spread": {
        "category": "Credit Spread",
        "best_for": ["Income", "Account Growth"],
        "risk": "Defined risk",
        "status": "Priced when chain supports it",
        "makes_money": "Collects a credit and profits if price stays below the short call through exit or expiration.",
        "best_when": "Bearish trend, resistance rejection, or failed bounce where premium is worth the defined risk.",
        "avoid_when": "Price is breaking out, resistance is failing, or the credit is too small versus width.",
    },
}


def _mid(contract: dict) -> float | None:
    if contract.get("mid") is not None:
        return float(contract["mid"])
    bid = contract.get("bid")
    ask = contract.get("ask")
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2


def _dte(expiration: str, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    parsed = datetime.strptime(expiration[:10], "%Y-%m-%d").date()
    return (parsed - as_of).days


def _contracts(chain: dict, option_type: str, underlying: float) -> list[dict]:
    key = "calls" if option_type == "Call" else "puts"
    rows = []
    for contract in chain.get(key, []):
        mid = _mid(contract)
        strike = contract.get("strike")
        if strike is None or mid is None or mid <= 0:
            continue
        rows.append({**contract, "mid": mid, "strike": float(strike)})
    return sorted(rows, key=lambda row: abs(row["strike"] - underlying))


def _by_delta(contracts: list[dict], target_delta: float) -> dict | None:
    if not contracts:
        return None
    return min(
        contracts,
        key=lambda row: (
            abs(abs(float(row.get("delta") or 0.0)) - target_delta),
            abs(float(row.get("ask") or row["mid"]) - float(row.get("bid") or row["mid"])),
        ),
    )


def _protection(
    contracts: list[dict],
    anchor: float,
    width: float,
    direction: str,
) -> dict | None:
    if direction == "higher":
        candidates = [row for row in contracts if row["strike"] > anchor]
        target = anchor + width
    else:
        candidates = [row for row in contracts if row["strike"] < anchor]
        target = anchor - width
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(row["strike"] - target))


def _legs(*items: tuple[str, dict]) -> list[dict]:
    rows = []
    for action, contract in items:
        rows.append(
            {
                "action": action,
                "quantity": 1,
                "type": contract.get("type"),
                "strike": float(contract["strike"]),
                "contract": contract.get("contract"),
                "bid": contract.get("bid"),
                "ask": contract.get("ask"),
                "mid": contract.get("mid"),
                "delta": contract.get("delta"),
            }
        )
    return rows


def _format_price(value: float) -> str:
    return f"${value:,.2f}"


def _candidate(
    *,
    bucket: str,
    strategy: str,
    expiration: str,
    side: str,
    entry_price: float,
    max_profit: float | None,
    max_loss: float | None,
    breakeven: str,
    legs: list[dict],
    thesis: str,
    fit: str,
) -> dict:
    return {
        "bucket": bucket,
        "strategy": strategy,
        "expiration": expiration[:10],
        "expiration_note": f"{_dte(expiration)} DTE",
        "dte": _dte(expiration),
        "side": side,
        "entry_price": round(entry_price, 2),
        "net_credit": round(entry_price, 2) if "Credit" in side else 0.0,
        "target_width": 0.0,
        "actual_width": 0.0,
        "max_profit": round(max_profit, 2) if max_profit is not None else None,
        "max_loss": round(max_loss, 2) if max_loss is not None else None,
        "breakeven": breakeven,
        "legs": legs,
        "thesis": thesis,
        "fit": fit,
    }


def _catalog_key(strategy: str) -> str:
    return strategy


def objective_score(suggestion: dict, objective: str) -> tuple[int, str]:
    strategy = suggestion.get("strategy", "")
    profile = STRATEGY_CATALOG.get(_catalog_key(strategy), {})
    score = 50
    reasons = []

    if objective in profile.get("best_for", []):
        score += 25
        reasons.append(f"fits {objective.lower()}")

    side = suggestion.get("side", "")
    max_profit = suggestion.get("max_profit")
    max_loss = suggestion.get("max_loss")
    entry = suggestion.get("entry_price")
    strategy_text = strategy.lower()

    if objective == "Account Growth":
        if side == "Long / Debit":
            score += 12
            reasons.append("directional upside")
        if max_profit is None and entry is not None:
            score += 8
            reasons.append("open-ended profit profile")
        if "leaps" in strategy_text:
            score += 10
            reasons.append("longer runway")
    elif objective == "Income":
        if side == "Short / Credit":
            score += 18
            reasons.append("premium collection")
        if "condor" in strategy_text:
            score += 8
            reasons.append("range income structure")
    elif objective == "Capital Preservation":
        if max_loss is not None:
            score += 12
            reasons.append("defined max loss")
        if max_loss is not None and max_profit is not None and max_loss <= max_profit * 2:
            score += 6
            reasons.append("risk is not extreme versus reward")
    elif objective == "Volatility Expansion":
        if "straddle" in strategy_text:
            score += 25
            reasons.append("profits from movement")
        if side == "Long / Debit":
            score += 6
            reasons.append("long premium exposure")
    elif objective == "Hedging":
        if "put" in strategy_text:
            score += 20
            reasons.append("downside exposure")
        if max_loss is not None:
            score += 6
            reasons.append("defined hedge cost")

    if entry is None:
        score -= 30
        reasons.append("not fully priced")
    if max_loss is None and objective in {"Capital Preservation", "Income"}:
        score -= 12
        reasons.append("unknown max loss")

    return max(0, min(100, score)), ", ".join(reasons) or "general fit"


def rank_option_suggestions(
    suggestions: dict[str, list[dict]],
    objective: str,
) -> dict[str, list[dict]]:
    ranked = {}
    for bucket, rows in suggestions.items():
        enriched = []
        for row in rows:
            score, reason = objective_score(row, objective)
            enriched.append(
                {
                    **row,
                    "objective": objective,
                    "objective_score": score,
                    "objective_reason": reason,
                }
            )
        ranked[bucket] = sorted(
            enriched,
            key=lambda item: (
                item.get("entry_price") is None,
                -int(item.get("objective_score") or 0),
                item.get("strategy", ""),
            ),
        )
    return ranked


def strategy_catalog_rows(objective: str, priced_strategies: set[str]) -> list[dict]:
    rows = []
    for strategy, profile in STRATEGY_CATALOG.items():
        rows.append(
            {
                "Strategy": strategy,
                "Category": profile["category"],
                "Best For": ", ".join(profile["best_for"]),
                "Risk Profile": profile["risk"],
                "How It Makes Money": profile["makes_money"],
                "Availability": "Priced in current results"
                if strategy in priced_strategies
                else profile["status"],
                "Growth Fit": "High"
                if objective in profile["best_for"]
                else "Secondary",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["Growth Fit"] != "High",
            row["Availability"] != "Priced in current results",
            row["Strategy"],
        ),
    )


def strategy_explanation(strategy: str) -> dict:
    if strategy == "Auto - best fit":
        return {
            "Strategy": strategy,
            "Category": "Dynamic",
            "How It Makes Money": "Chooses bullish debit/credit spreads in bullish tape and bearish debit/credit spreads in bearish tape.",
            "Best When": "You want AlphaOS to pick daily defined-risk spreads that match the current directional bias.",
            "Avoid When": "The session is neutral, choppy, or the option chain cannot produce a valid spread.",
            "Risk Profile": "Defined debit or defined credit-spread risk",
            "Availability": "Only debit spreads and credit spreads",
        }
    profile = STRATEGY_CATALOG.get(strategy)
    if not profile:
        return {
            "Strategy": strategy,
            "Category": "Unknown",
            "How It Makes Money": "No strategy profile is available yet.",
            "Best When": "N/A",
            "Avoid When": "N/A",
            "Risk Profile": "N/A",
            "Availability": "Unavailable",
        }
    return {
        "Strategy": strategy,
        "Category": profile["category"],
        "How It Makes Money": profile["makes_money"],
        "Best When": profile["best_when"],
        "Avoid When": profile["avoid_when"],
        "Risk Profile": profile["risk"],
        "Availability": profile["status"],
    }


def _debit_spread(
    chain: dict,
    underlying: float,
    outlook: str,
    bucket: str,
    width: float,
) -> dict | None:
    option_type = "Call" if outlook == "Bullish" else "Put"
    contracts = _contracts(chain, option_type, underlying)
    long_leg = _by_delta(contracts, 0.50)
    if long_leg is None:
        return None
    short_leg = _protection(
        contracts,
        long_leg["strike"],
        width,
        "higher" if option_type == "Call" else "lower",
    )
    if short_leg is None:
        return None
    debit = round(long_leg["mid"] - short_leg["mid"], 2)
    actual_width = abs(short_leg["strike"] - long_leg["strike"])
    if debit <= 0 or debit >= actual_width:
        return None
    max_profit = (actual_width - debit) * 100
    max_loss = debit * 100
    breakeven_value = (
        long_leg["strike"] + debit
        if option_type == "Call"
        else long_leg["strike"] - debit
    )
    strategy = "Call Debit Spread" if option_type == "Call" else "Put Debit Spread"
    candidate = _candidate(
        bucket=bucket,
        strategy=strategy,
        expiration=chain["expiration"],
        side="Long / Debit",
        entry_price=debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=_format_price(breakeven_value),
        legs=_legs(("Buy", long_leg), ("Sell", short_leg)),
        thesis=f"{outlook} directional structure with defined risk.",
        fit="Uses the selected expiration bucket and caps both risk and reward.",
    )
    candidate["actual_width"] = round(actual_width, 2)
    candidate["target_width"] = round(width, 2)
    return candidate


def build_option_suggestions(
    chains: dict[str, dict],
    underlying: float,
    outlook: str,
    width: float,
    expirations: list[str],
    include_unpriced: bool = True,
) -> dict[str, list[dict]]:
    suggestions: dict[str, list[dict]] = {}
    for bucket, chain in chains.items():
        rows = []
        if outlook in {"Bullish", "Bearish"}:
            debit = _debit_spread(chain, underlying, outlook, bucket, width)
            if debit:
                rows.append(debit)
            credit = build_income_spread(
                chain,
                underlying,
                outlook,
                bucket,
                spread_width=width,
            )
            if credit:
                credit["side"] = "Short / Credit"
                credit["entry_price"] = credit["net_credit"]
                credit["thesis"] = f"{outlook} credit spread with defined risk."
                credit["fit"] = "Uses the same daily expiration bucket and sells premium in the direction of the tape."
                rows.append(credit)
        suggestions[bucket] = rows
    return suggestions


def suggestion_management_plan(suggestion: dict) -> list[dict]:
    entry = suggestion.get("entry_price")
    if entry is None:
        return [
            {
                "Rule": "Insufficient priced structure",
                "Trigger": "Do not take until near and far legs can be priced from the option chain",
                "Reason": "The app should not fabricate debit, credit, max loss, or breakeven.",
            }
        ]
    entry = float(entry)
    if suggestion.get("side") == "Short / Credit":
        profit_50 = round(entry * 0.50, 2)
        profit_75 = round(entry * 0.25, 2)
        stop_value = round(entry * 2.0, 2)
        return [
            {
                "Rule": "Credit profit target",
                "Trigger": f"Consider closing around ${profit_50:,.2f} to ${profit_75:,.2f}",
                "Reason": "Captures roughly 50-75% of credit before tail risk dominates remaining reward.",
            },
            {
                "Rule": "Credit spread stop",
                "Trigger": f"Exit or reduce if spread value reaches about ${stop_value:,.2f}",
                "Reason": "Prevents a premium idea from turning into a max-loss fight.",
            },
            {
                "Rule": "No final-dollars rule",
                "Trigger": "Do not hold only to collect a few remaining dollars while max risk remains large",
                "Reason": "Remaining reward can become too small relative to remaining risk.",
            },
        ]
    target_1 = round(entry * 1.50, 2)
    target_2 = round(entry * 2.00, 2)
    stop_value = round(max(0.01, entry * 0.50), 2)
    return [
        {
            "Rule": "Debit stop",
            "Trigger": f"Exit or reduce near ${stop_value:,.2f} if underlying thesis fails",
            "Reason": "Chart invalidation leads; option price is only an estimate.",
        },
        {
            "Rule": "Target 1",
            "Trigger": f"Consider profit protection near ${target_1:,.2f}",
            "Reason": "Protects a winner before reversal risk takes back the move.",
        },
        {
            "Rule": "Target 2",
            "Trigger": f"Consider full exit or tight trail near ${target_2:,.2f}",
            "Reason": "Prevents holding for extra cents when momentum has already paid.",
        },
    ]
